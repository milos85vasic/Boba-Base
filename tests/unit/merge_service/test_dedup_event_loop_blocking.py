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

BOB-156 — WALL-CLOCK CEILINGS ARE NOT A LOAD-INDEPENDENT ORACLE (root-cause
investigation, §11.4.102, before any number was changed)
----------------------------------------------------------------------------
The original ``MAX_LOOP_BLOCK_S`` ceiling (1.5 s, first 900 ms) bounded
``worst_gap`` — the wall-clock gap between heartbeat ticks, which this test's
own docstring above already documents as tracking ``merge_wall`` to within a
few ms, because ``merge_results`` never yields (see "WHAT THIS TEST DOES NOT
CLAIM"). BOB-156 reported 8786 ms against that ceiling under real host
contention ("host load 18-24 on 8 cores") on UNCHANGED post-fix code.

REPRODUCED on this development host (16 cores) by oversubscribing it with
independent, unrelated CPU-bound Python processes (pure integer arithmetic
busy-loops — no I/O, no shared state, no relation to this test) and re-running
the *unmodified* pytest file:

    ambient (load average ~9-19, no injected load): worst_gap ~105-160ms  -> PASS
    +40  busy procs (2.5x/core oversubscription):    worst_gap  428-732ms -> PASS
    +80  busy procs (5x/core oversubscription):       worst_gap 1077-2152ms -> intermittent FAIL
    +100 busy procs (~6x/core, live pytest run):      worst_gap 2044.3ms  -> FAIL:
        "event loop was frozen for 2044.3ms (ceiling 1500ms) ... only 1
        heartbeat tick(s) ran during the merge." (captured pytest output,
        unmodified test, unmodified deduplicator.py — same shape as BOB-156)

Repeating the identical measurement with ``time.process_time()`` (CPU time
consumed by THIS process — user+sys seconds actually spent executing, as
opposed to wall-clock seconds elapsed while the OS scheduler may have
descheduled this process in favour of the competing busy-loops) around the
SAME merge call, at the SAME contention levels:

    ambient:              merge_cpu ~105-160ms  (== wall, host was not saturated)
    +40  busy procs:      merge_cpu  167-203ms
    +80  busy procs:      merge_cpu  170-201ms
    +120 busy procs (7.5x/core): merge_cpu 174-193ms

``merge_cpu`` stays inside a <2x band across a >7x range of induced core
oversubscription, while ``worst_gap``/``merge_wall`` inflates by up to ~20x
over the SAME range and SAME code. The mechanism: ``merge_results`` is pure
CPU-bound Python with no I/O, so the *work* it does — and therefore the CPU
time the OS attributes to this process — does not change when unrelated
processes compete for the same cores; only the WALL-CLOCK time to get that
fixed amount of work scheduled does, because the kernel now time-slices this
process's core(s) among more runnable competitors. A wall-clock ceiling
therefore measures "how contended was the host", not "did this code regress" —
exactly the "weather report" the tracked item (BOB-156) names.

The SAME technique, applied to the PRE-FIX ``deduplicator.py`` (the parent of
the BOB-145 fix commit, loaded standalone, ambient host conditions, no
induced contention needed since the regression itself is the dominant cost):

    merge_cpu ~3300-3470ms  (== merge_wall to within a few ms, as documented above)

The regression is ~17-25x the worst *contended* post-fix ``merge_cpu``
measured above and ~9-13x the fixed 1.5 s ceiling adopted below — CPU time
distinguishes "the code got slower" from "the host got busier" by construc-
tion, because contention delays scheduling without adding CPU-seconds to a
process that was not itself doing more work.

``MAX_MERGE_CPU_S`` is the PRIMARY regression gate, set at 1.5 s (the same
number the wall-clock ceiling used, applied to a different, load-insensitive
metric): comfortably above every post-fix ``merge_cpu`` measurement above
(worst 203 ms, >7x margin) and comfortably below the pre-fix regression
(~3300 ms, >2.2x margin) — the identical safety-margin shape the original
provenance note used, now anchored to a quantity that does not move when the
host is merely busy.

``worst_gap`` and its heartbeat instrumentation are RETAINED as diagnostic
evidence (they still directly demonstrate the loop-freeze phenomenon the
BOB-137 wedge exhibited, and the "instrument is not blind" sanity check below
is unaffected by any of this) plus a generous, load-tolerant
``WALL_CLOCK_HANG_CEILING_S`` backstop (15 s) that only fires on a genuinely
catastrophic freeze (the kind BOB-137 measured in *minutes*) — not on ordinary
contention, and not as the mechanism that is supposed to catch a re-introduced
BOB-145 regression (that is ``MAX_MERGE_CPU_S``'s job).

WHAT THIS TEST DOES *NOT* CLAIM (§11.4.6)
------------------------------------------
It does not claim the loop is never blocked. ``merge_results`` is a synchronous
method invoked synchronously; while it runs, the loop is stopped, and the only
ways to change that are to offload it to an executor or to make it a coroutine
that awaits — both of which are changes at the CALL SITE in ``search.py``, not
in the deduplicator. What this test asserts is that the blocked window is
bounded and small, instead of being minutes long as BOB-137 measured.

It does not claim ``time.process_time()`` is immune to ALL host effects (cache
contention and extra context-switch overhead under oversubscription did add a
modest ~1.3-1.9x over the ambient baseline in the measurements above) — only
that it is far less sensitive to scheduling contention than wall-clock time
for a single-threaded, non-blocking, CPU-bound call, which is the specific
property BOB-156 needed.
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

#: PRIMARY regression gate (BOB-156): ceiling on CPU time (``time.process_time``)
#: consumed by one merge, in seconds. Unlike wall-clock, this does not inflate
#: when unrelated processes contend for the host's cores (see module docstring
#: "BOB-156 — wall-clock ceilings are not a load-independent oracle" for the
#: measured wall-vs-CPU comparison across induced contention levels).
#: Post-fix worst observed (7.5x/core induced oversubscription) 0.203 s;
#: pre-fix (BOB-145 regression) ~3.3-3.47 s.
MAX_MERGE_CPU_S = 1.5

#: DEFENSE-IN-DEPTH backstop only (BOB-156): a generous wall-clock ceiling that
#: exists to catch a genuinely catastrophic freeze (the BOB-137 wedge measured
#: *minutes*), not ordinary host contention. Deliberately far above anything
#: observed under induced contention up to 7.5x/core oversubscription (worst
#: 2.25 s) so it does not flake; deliberately far below "minutes" so it still
#: means something. ``MAX_MERGE_CPU_S`` above, not this constant, is what is
#: expected to catch a re-introduced BOB-145 regression.
WALL_CLOCK_HANG_CEILING_S = 15.0

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

        BOB-156: the PRIMARY assertion is on CPU time (``merge_cpu``), not on
        the heartbeat's wall-clock gap (``worst_gap``) — see the module
        docstring section "BOB-156 — wall-clock ceilings are not a
        load-independent oracle" for why. ``worst_gap`` is still measured and
        still asserted, but only against a generous, load-tolerant backstop
        (``WALL_CLOCK_HANG_CEILING_S``); it is retained as diagnostic evidence
        of the loop-freeze phenomenon, not as the regression detector.
        """
        dedup = Deduplicator()
        dedup.merge_results(build_corpus(20))  # warm-up: lazy imports, not measured

        corpus = build_corpus(CORPUS_SIZE)
        stop = asyncio.Event()
        gaps: list[float] = []
        beat = asyncio.create_task(_heartbeat(stop, gaps))
        await asyncio.sleep(0.05)  # let the heartbeat reach steady state
        settled_ticks = len(gaps)

        wall_started = time.perf_counter()
        cpu_started = time.process_time()
        merged = dedup.merge_results(corpus)  # exactly as search.py:914 calls it
        merge_cpu = time.process_time() - cpu_started
        merge_wall = time.perf_counter() - wall_started

        stop.set()
        await beat

        assert merged, "merge produced no groups — corpus or merge is broken"
        assert settled_ticks > 0, "heartbeat never ticked before the merge; instrument is blind"

        ticks_during_merge = len(gaps) - settled_ticks
        worst_gap = max(gaps)
        diagnostics = (
            f"merge_cpu={merge_cpu * 1000:.1f}ms (ceiling {MAX_MERGE_CPU_S * 1000:.0f}ms) "
            f"merge_wall={merge_wall * 1000:.1f}ms worst_gap={worst_gap * 1000:.1f}ms "
            f"(hang backstop {WALL_CLOCK_HANG_CEILING_S * 1000:.0f}ms) "
            f"over {len(corpus)} results -> {len(merged)} groups; "
            f"only {ticks_during_merge} heartbeat tick(s) ran during the merge."
        )

        # PRIMARY regression gate (BOB-156): CPU time is what "the code got
        # slower" actually looks like, and it does not inflate merely because
        # the host is contended (see module docstring for the measured
        # wall-vs-CPU comparison across induced contention levels).
        assert merge_cpu <= MAX_MERGE_CPU_S, (
            f"merge consumed {merge_cpu * 1000:.1f}ms of CPU time "
            f"(ceiling {MAX_MERGE_CPU_S * 1000:.0f}ms) — this is a regression in "
            f"the work merge_results does, not host contention (CPU time is not "
            f"inflated by scheduling delays the way wall-clock is). {diagnostics} "
            f"This is the BOB-145 signature: while a merge this expensive runs, "
            f"port 7187 answers nothing (BOB-137)."
        )

        # DEFENSE-IN-DEPTH backstop only: catches a genuinely catastrophic
        # freeze (BOB-137 measured *minutes*); deliberately not the mechanism
        # relied on to catch a re-introduced BOB-145 regression.
        assert worst_gap <= WALL_CLOCK_HANG_CEILING_S, (
            f"event loop was frozen for {worst_gap * 1000:.1f}ms, past the "
            f"{WALL_CLOCK_HANG_CEILING_S * 1000:.0f}ms catastrophic-hang backstop "
            f"(this is far above ordinary host contention). {diagnostics} While "
            f"the loop is frozen, port 7187 answers nothing (BOB-137)."
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
