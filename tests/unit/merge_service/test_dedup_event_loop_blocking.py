"""BOB-145 — regression guard: ``Deduplicator.merge_results`` must not starve
the asyncio event loop, and must not change which results it merges.

WHY THIS TEST EXISTS
--------------------
BOB-137 diagnosed a wedge in which port 7187 stopped answering for minutes
(measured episodes of 9m37s and 5m56s) while port 7186 — served by the *same*
process — kept answering. The asymmetry is the whole tell: 7186 is served by a
poll loop that releases the GIL, while 7187's asyncio loop needs sustained
Python execution time. ``merge_results`` is invoked as a **plain synchronous
call** from an ``async def`` (``merge_service/search.py:914``), so every
microsecond it spends is a microsecond during which the event loop runs no
callback at all: no accept, no read, no write.

There are therefore TWO polarities to guard, and a fix that only satisfies one
of them is a different defect (§11.4.201(1)):

  1. LIVENESS  — a coroutine that wants to run while a merge is in flight
     actually gets to run. This is asserted by a heartbeat coroutine that ticks
     on a fixed period; the *maximum gap* between its ticks is a direct,
     user-observable measure of how long the loop was frozen.

  2. CORRECTNESS — the merge still produces exactly the same grouping. A change
     that speeds merging up while changing which duplicates are detected would
     silently corrupt search results, which is strictly worse than the wedge it
     cures. Guarded by a golden characterization of the pre-fix output.

THRESHOLD PROVENANCE (§11.4.6 — measured, not invented)
-------------------------------------------------------
Measured on the pre-fix code on this host, corpus of ``CORPUS_SIZE`` results,
heartbeat period 5 ms:

    N=100  merge_wall=  445.5ms  max_heartbeat_gap=  448.7ms
    N=200  merge_wall= 1063.8ms  max_heartbeat_gap= 1068.0ms
    N=400  merge_wall= 3802.5ms  max_heartbeat_gap= 3805.7ms
    N=800  merge_wall= 7337.1ms  max_heartbeat_gap= 7341.3ms

The max gap tracks the merge wall-clock to within ~4 ms at every size, i.e. the
loop is frozen for *the entire duration of the merge* — zero heartbeat ticks
occur while it runs.

Post-fix, same host, N=400, 12 consecutive runs (ms):

    247 274 278 286 302 330 367 405 438 582 602 655
    min=247  median=349  max=655

``MAX_LOOP_BLOCK_S`` is therefore set at 1.5 s: ~2.3x above the worst observed
post-fix run (so it does not flake when the host is busy — this box runs other
work concurrently and the spread above is real contention, not variance in the
code under test) and ~2.6x below the pre-fix measurement (so it genuinely fails
on the old code, which it was observed to do at 3970 ms).

WHAT THIS TEST DOES *NOT* CLAIM (§11.4.6)
------------------------------------------
It does not claim the loop is never blocked. ``merge_results`` is a synchronous
method invoked synchronously; while it runs, the loop is stopped, and the only
ways to change that are to offload it to an executor or to make it a coroutine
that awaits — both of which are changes at the CALL SITE in ``search.py``, not
in the deduplicator. What this test asserts is that the blocked window is
bounded and small, instead of being minutes long as BOB-137 measured.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
import time

import pytest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_SRC_PATH = os.path.join(_REPO_ROOT, "download-proxy", "src")
_MS_PATH = os.path.join(_SRC_PATH, "merge_service")

sys.modules.setdefault("merge_service", type(sys)("merge_service"))
sys.modules["merge_service"].__path__ = [_MS_PATH]

_dedup_spec = importlib.util.spec_from_file_location(
    "merge_service.deduplicator", os.path.join(_MS_PATH, "deduplicator.py")
)
_dedup_mod = importlib.util.module_from_spec(_dedup_spec)
sys.modules["merge_service.deduplicator"] = _dedup_mod
_dedup_spec.loader.exec_module(_dedup_mod)

_search_spec = importlib.util.spec_from_file_location("merge_service.search", os.path.join(_MS_PATH, "search.py"))
_search_mod = importlib.util.module_from_spec(_search_spec)
sys.modules["merge_service.search"] = _search_mod
_search_spec.loader.exec_module(_search_mod)

Deduplicator = _dedup_mod.Deduplicator
SearchResult = _search_mod.SearchResult

GOLDEN_PATH = os.path.join(os.path.dirname(__file__), "bob145_dedup_golden.json")

# ---------------------------------------------------------------------------
# Corpus
# ---------------------------------------------------------------------------
# A realistic multi-tracker fan-out: MANY DISTINCT titles with a handful of
# near-duplicate releases each. This shape matters — a corpus of near-identical
# names collapses into a few merge groups and hides the quadratic behaviour
# entirely, because the outer loop then runs only a few times. Real searches
# return mostly-distinct titles, which is the worst case by code structure.

_TRACKERS = ("rutracker", "kinozal", "nnmclub", "rutor")
_RESOLUTIONS = ("720p", "1080p", "2160p")
_CODECS = ("x264", "x265", "HEVC")
_FORMATS = ("BluRay", "WEB-DL", "WEBRip", "HDRip")
_GROUPS = ("RARBG", "YTS", "NTb", "FLUX", "CMRG")
_TITLES = (
    "Inception",
    "Gladiator",
    "Interstellar",
    "Casablanca",
    "Whiplash",
    "Arrival",
    "Parasite",
    "Oppenheimer",
    "Dune",
    "Amadeus",
    "Chinatown",
    "Braveheart",
    "Memento",
    "Vertigo",
    "Alien",
    "Predator",
    "Heat",
    "Sicario",
    "Prisoners",
    "Nightcrawler",
)
_EDITIONS = ("Directors Cut", "Extended", "Remastered", "Theatrical", "Anniversary")

CORPUS_SIZE = 400

#: Ceiling on how long the event loop may be frozen by one merge, in seconds.
#: Pre-fix 3.806-3.970 s; post-fix worst-of-12 0.655 s (see module docstring).
MAX_LOOP_BLOCK_S = 1.5

#: Heartbeat tick period. Small enough that a freeze of interest spans many
#: missed ticks, large enough that the heartbeat itself is not the load.
HEARTBEAT_PERIOD_S = 0.005


def build_corpus(count: int) -> list[SearchResult]:
    """Build a deterministic, realistic multi-tracker result set."""
    results: list[SearchResult] = []
    for i in range(count):
        release = i // 3
        title = (
            f"{_TITLES[release % len(_TITLES)]} "
            f"{_EDITIONS[(release // len(_TITLES)) % len(_EDITIONS)]} "
            f"{release} {2015 + (i % 8)}"
        )
        results.append(
            SearchResult(
                name=(f"{title} {_RESOLUTIONS[i % 3]} {_FORMATS[i % 4]} {_CODECS[i % 3]}-{_GROUPS[i % 5]}"),
                link=f"magnet:?xt=urn:btih:{i:040x}",
                size=f"{1 + (i % 40) / 10:.1f} GB",
                seeds=(i * 7) % 300,
                leechers=i % 50,
                engine_url="https://example.com",
                tracker=_TRACKERS[i % 4],
            )
        )
    return results


def canonical_signature(merged: list) -> list[dict]:
    """Serialise a merge result set into an order-stable, comparable form.

    Captures exactly what "which duplicates were detected" means: the grouping
    (which source links landed together) plus every derived field the merge
    itself decides — the canonical identity and the elected best quality.
    ``created_at`` is deliberately excluded: it is a wall-clock timestamp, not
    a merge decision.
    """
    groups = []
    for m in merged:
        identity = m.canonical_identity
        groups.append(
            {
                "members": sorted(r.link for r in m.original_results),
                "title": identity.title,
                "year": identity.year,
                "content_type": identity.content_type.value if identity.content_type else None,
                "season": identity.season,
                "episode": identity.episode,
                "resolution": identity.resolution,
                "codec": identity.codec,
                "best_quality": m.best_quality.value if m.best_quality else None,
                "total_seeds": m.total_seeds,
                "total_leechers": m.total_leechers,
            }
        )
    groups.sort(key=lambda g: g["members"])
    return groups


async def _heartbeat(stop: asyncio.Event, gaps: list[float]) -> None:
    """Tick on a fixed period, recording the real interval between ticks.

    Each recorded gap is how long this coroutine was denied the loop. On a
    healthy loop every gap is ~HEARTBEAT_PERIOD_S; while a synchronous merge
    runs on the loop thread, no tick happens at all and the next gap equals the
    whole frozen window.
    """
    last = time.perf_counter()
    while not stop.is_set():
        await asyncio.sleep(HEARTBEAT_PERIOD_S)
        now = time.perf_counter()
        gaps.append(now - last)
        last = now


class TestMergeResultsDoesNotBlockTheEventLoop:
    """BOB-145 liveness + correctness guards."""

    @pytest.mark.asyncio
    async def test_merge_does_not_starve_a_concurrent_coroutine(self) -> None:
        """A merge must leave the event loop able to run other callbacks.

        This is the defect BOB-137 observed as "7187 answers nothing": the
        heartbeat below stands in for uvicorn's accept/read/write callbacks.
        """
        dedup = Deduplicator()
        dedup.merge_results(build_corpus(20))  # warm-up: lazy imports, not measured

        corpus = build_corpus(CORPUS_SIZE)
        stop = asyncio.Event()
        gaps: list[float] = []
        beat = asyncio.create_task(_heartbeat(stop, gaps))
        await asyncio.sleep(0.05)  # let the heartbeat reach steady state
        settled_ticks = len(gaps)

        started = time.perf_counter()
        merged = dedup.merge_results(corpus)  # exactly as search.py:914 calls it
        merge_wall = time.perf_counter() - started

        stop.set()
        await beat

        assert merged, "merge produced no groups — corpus or merge is broken"
        assert settled_ticks > 0, "heartbeat never ticked before the merge; instrument is blind"

        ticks_during_merge = len(gaps) - settled_ticks
        worst_gap = max(gaps)
        assert worst_gap <= MAX_LOOP_BLOCK_S, (
            f"event loop was frozen for {worst_gap * 1000:.1f}ms "
            f"(ceiling {MAX_LOOP_BLOCK_S * 1000:.0f}ms). "
            f"merge wall-clock {merge_wall * 1000:.1f}ms over {len(corpus)} results "
            f"-> {len(merged)} groups; only {ticks_during_merge} heartbeat tick(s) "
            f"ran during the merge. While the loop is frozen, port 7187 answers "
            f"nothing (BOB-137)."
        )

    def test_merge_output_is_unchanged_against_the_prefix_golden(self) -> None:
        """Dedup decisions must be byte-identical to the pre-fix behaviour.

        The golden was captured from the code as it stood BEFORE the BOB-145
        fix. Any speed-up that changes which results merge together is a new
        defect, not a fix.
        """
        with open(GOLDEN_PATH, encoding="utf-8") as fh:
            golden = json.load(fh)

        assert golden["corpus_size"] == CORPUS_SIZE, "golden was captured for a different corpus size"

        dedup = Deduplicator()
        signature = canonical_signature(dedup.merge_results(build_corpus(CORPUS_SIZE)))

        assert len(signature) == len(golden["groups"]), (
            f"merge produced {len(signature)} groups, pre-fix code produced "
            f"{len(golden['groups'])} — the fix changed which duplicates are detected"
        )
        assert signature == golden["groups"], "merge grouping diverged from the pre-fix golden"

    def test_merge_is_order_independent_after_the_fix(self) -> None:
        """Shuffling the input must not change the grouping.

        Memoisation caches derived values across calls; if a cache key were
        wrong (e.g. keyed on identity rather than on the string that actually
        determines the value) this is where it would surface as a
        result-dependent-on-history failure.
        """
        # Deterministic shuffle: this is a test-ordering permutation, not a
        # security primitive, and a fixed seed keeps the test reproducible.
        import random  # noqa: S311 — deterministic test permutation, not crypto

        corpus = build_corpus(120)
        forward = canonical_signature(Deduplicator().merge_results(list(corpus)))

        shuffled = list(corpus)
        random.Random(20260821).shuffle(shuffled)  # noqa: S311
        reverse = canonical_signature(Deduplicator().merge_results(shuffled))

        assert forward == reverse, "grouping depends on input order"


class TestPrecomputedPathAgreesWithTheReferencePath:
    """Anti-divergence guard for the BOB-145 refactor.

    The fix introduced a second expression of two predicates: the matcher now
    runs over precomputed ``_ResultView`` values, while the original
    ``CanonicalIdentity``/``SearchResult`` forms remain as the reference (they
    are public enough that other tests call them directly).

    Two implementations of one predicate is exactly the shape that silently
    drifts when someone later edits a threshold in one place. These tests fail
    the moment the two disagree on any pair — which is what makes the
    "behaviour is unchanged" claim in those docstrings checkable rather than
    merely asserted.
    """

    @staticmethod
    def _pairs(count: int = 60):
        """Every ordered pair from a small corpus — includes self-pairs."""
        corpus = build_corpus(count)
        for a in corpus:
            for b in corpus:
                yield a, b

    def test_identity_comparison_agrees(self) -> None:
        dedup = Deduplicator()
        checked = 0
        for a, b in self._pairs():
            reference = dedup._compare_identities(
                dedup._extract_identity_from_result(a),
                dedup._extract_identity_from_result(b),
            )
            precomputed = dedup._compare_identity_views(dedup._build_view(a), dedup._build_view(b))
            assert reference == precomputed, (
                f"tier-1 predicates disagree on {a.name!r} vs {b.name!r}: "
                f"_compare_identities={reference} _compare_identity_views={precomputed}"
            )
            checked += 1
        assert checked > 0, "no pairs compared; the guard is blind"

    def test_name_and_size_comparison_agrees(self) -> None:
        dedup = Deduplicator()
        for a, b in self._pairs():
            reference = dedup._compare_name_and_size(a, b)
            precomputed = dedup._compare_name_and_size_views(dedup._build_view(a), dedup._build_view(b))
            assert reference == precomputed, (
                f"tier-3 predicates disagree on {a.name!r} vs {b.name!r}: "
                f"_compare_name_and_size={reference} _compare_name_and_size_views={precomputed}"
            )

    def test_hash_comparison_agrees(self) -> None:
        dedup = Deduplicator()
        for a, b in self._pairs():
            reference = dedup._compare_hashes(a, b)
            va, vb = dedup._build_view(a), dedup._build_view(b)
            precomputed = bool(va.infohash_lower and vb.infohash_lower and va.infohash_lower == vb.infohash_lower)
            assert reference == precomputed, f"tier-2 predicates disagree on {a.link!r} vs {b.link!r}"

    def test_similarity_wrapper_agrees_with_lowered_form(self) -> None:
        """``_calculate_similarity`` must stay a pure lowering wrapper."""
        dedup = Deduplicator()
        samples = [r.name for r in build_corpus(24)] + ["", "Mixed CASE Name", "ALL UPPER 1080p"]
        for a in samples:
            for b in samples:
                assert dedup._calculate_similarity(a, b) == dedup._similarity_of_lowered(a.lower(), b.lower())
