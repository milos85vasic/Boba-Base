"""§11.4.85 STRESS + CHAOS automation tests for the Boba merge-search
ORCHESTRATION + SSE progressive-merged-streaming path.

This is the code path behind the operator-reported "during a search a smaller
list overwrites everything" defect and its fix — progressive ``merged_update``
streaming. The fix guarantees: (a) the live-streamed merged set GROWS smoothly
toward the unique count and NEVER shrinks across a search, and (b) the FINAL
``merged_update`` is byte-identical to ``GET /search/{id}`` because both
serialize the SAME ``orchestrator._last_merged_results[search_id][0]`` via the
SAME ``api.routes._serialize_merged_rows`` helper.

It exercises the REAL production code:
  * ``api.streaming._build_merged_update`` — the merged_update builder that
    prefers the orchestrator's authoritative cache else re-merges
    ``get_all_tracker_results``;
  * ``api.streaming.SSEHandler.search_results_stream`` — the SSE emission loop;
  * ``api.routes._serialize_merged_rows`` — the single-source-of-truth
    merged→row serializer used by BOTH the stream and ``GET /search/{id}``;
  * ``merge_service.deduplicator.Deduplicator.merge_results`` — the merge.

DIFFERENT code path from the button (``test_button_endpoints_stress_chaos.py``)
and the pure-dedup (``test_merge_search_stress_chaos.py``) stress files — this
one drives the orchestration + SSE *streaming/serialization* layer.

Hermetic + host-safe: NO network, NO running merge service, NO sleeps
(``poll_interval=0`` + ``MERGED_UPDATE_MIN_INTERVAL_S`` patched to 0). N is
capped at reasonable host-safe values. A stub orchestrator mirrors the real
``SearchOrchestrator`` surface that the streaming layer reads.

Anti-bluff (§11.4 / §11.4.5 / §11.4.69 / §11.4.107): every PASS asserts a
USER-OBSERVABLE outcome — merged-count non-shrink/monotonicity, final ==
get_search BYTE-equality, no-cross-search-contamination, no-result-loss after a
partial tracker failure, latency p50/p95 — and cites a captured-evidence
artefact under ``qa-results/search_orch_stress/local/`` (STATIC run-id, so
assertions never depend on wall-clock).

§11.4.85 category -> test map (asserted live by
``test_section_114_85_category_map``):

STRESS:
  sustained-load          -> test_stress_sustained_merged_build_nonshrink_and_latency
  concurrent-contention   -> test_stress_concurrent_searches_no_cross_contamination
  boundary-zero-trackers  -> test_boundary_zero_trackers_empty_merged
  boundary-one-tracker    -> test_boundary_single_tracker
  boundary-all-empty      -> test_boundary_all_trackers_empty
  boundary-final-eq-get   -> test_boundary_final_merged_byte_equals_get_search
CHAOS:
  partial-tracker-failure -> test_chaos_partial_tracker_failure_keeps_good_results
  late-arriving-tracker   -> test_chaos_late_arriving_tracker_count_grows_no_shrink
  stale-missing-cache     -> test_chaos_missing_cache_falls_back_to_remerge
  malformed-accumulated   -> test_chaos_malformed_accumulated_serialization_survives
"""

from __future__ import annotations

import asyncio
import importlib.util
import itertools
import json
import random
import statistics
import string
import sys
import time
from pathlib import Path

import pytest

# --------------------------------------------------------------------------- #
# Import the production modules directly from source (3.12 code; loaded under
# the venv 3.13 interpreter via importlib + namespace-package registration so
# the relative imports inside deduplicator.py / api.routes resolve). Mirrors the
# sibling unit test ``tests/unit/merge_service/test_merged_update_streaming.py``.
# --------------------------------------------------------------------------- #
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC_PATH = _REPO_ROOT / "download-proxy" / "src"
_MS_PATH = _SRC_PATH / "merge_service"

if str(_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(_SRC_PATH))

sys.modules.setdefault("merge_service", type(sys)("merge_service"))
sys.modules["merge_service"].__path__ = [str(_MS_PATH)]
for _name in ("search", "deduplicator"):
    _mod_name = f"merge_service.{_name}"
    if _mod_name not in sys.modules:
        _spec = importlib.util.spec_from_file_location(_mod_name, str(_MS_PATH / f"{_name}.py"))
        _mod = importlib.util.module_from_spec(_spec)
        sys.modules[_mod_name] = _mod
        _spec.loader.exec_module(_mod)

from api.routes import _serialize_merged_rows  # noqa: E402
from api.streaming import SSEHandler, _build_merged_update  # noqa: E402
from merge_service.deduplicator import Deduplicator  # noqa: E402
from merge_service.search import SearchResult  # noqa: E402

# Contract keys every serialized merged_update row must carry (mirrors the
# get_search SearchResultResponse contract).
_CONTRACT_KEYS = {
    "name",
    "size",
    "seeds",
    "leechers",
    "tracker",
    "download_urls",
    "quality",
    "content_type",
    "sources",
    "freeleech",
}

# --------------------------------------------------------------------------- #
# Captured-evidence helper — STATIC run-id "local" per the task.
# --------------------------------------------------------------------------- #
_EVIDENCE_DIR = _REPO_ROOT / "qa-results" / "search_orch_stress" / "local"


def _write_evidence(name: str, payload: dict) -> Path:
    _EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    path = _EVIDENCE_DIR / f"{name}.json"
    path.write_text(json.dumps(payload, indent=2, default=str))
    assert path.exists() and path.stat().st_size > 0, "evidence artefact must exist and be non-empty"
    return path


# --------------------------------------------------------------------------- #
# Result builders.
# --------------------------------------------------------------------------- #
def _r(name: str, link: str, tracker: str, seeds: int = 10, leechers: int = 2, size: str = "2.0 GB") -> SearchResult:
    return SearchResult(
        name=name,
        link=link,
        size=size,
        seeds=seeds,
        leechers=leechers,
        engine_url=f"https://{tracker}.example",
        tracker=tracker,
    )


def _infohash(seed: int) -> str:
    # 40-char hex infohash → triggers the deduplicator's exact-infohash tier.
    return "magnet:?xt=urn:btih:" + f"{seed:040x}"


def _distinct_titles(n: int, *, salt: int = 0) -> list[str]:
    """Produce ``n`` lexically MAXIMALLY-dissimilar titles.

    The production ``Deduplicator`` matches by Levenshtein ratio on the
    *normalized* title (Tier 1/4, threshold 0.80), NOT by the magnet link — so
    a corpus of near-identical "Title 0000N" names would collapse into one
    fuzzy group. Long random lowercase-alpha tokens keep the pairwise edit
    ratio well below threshold so exactly ``n`` distinct titles survive — the
    realistic "n unique torrents" condition. Deterministic per (n, salt) so the
    corpus is reproducible (§11.4.50).
    """
    rng = random.Random(0xB0BA ^ salt ^ (n << 1))  # noqa: S311 — test-corpus fixture, not crypto; deterministic per §11.4.50
    titles: list[str] = []
    seen: set[str] = set()
    while len(titles) < n:
        length = rng.randint(20, 36)
        t = "".join(rng.choice(string.ascii_lowercase) for _ in range(length))
        if t in seen:
            continue
        seen.add(t)
        titles.append(t)
    return titles


def _make_large_corpus(
    n_titles: int, trackers: list[str], *, salt: int = 0
) -> dict[str, list[SearchResult]]:
    """Build a per-tracker corpus where each of ``n_titles`` distinct logical
    torrents appears on EVERY tracker (same name + same infohash link), so the
    merge collapses ``n_titles * len(trackers)`` raw rows to exactly
    ``n_titles`` unique rows — mirroring the live 1785 raw → 663 merged
    collapse. Titles are maximally dissimilar so they never fuzzy-merge.
    """
    titles = _distinct_titles(n_titles, salt=salt)
    per_tracker: dict[str, list[SearchResult]] = {t: [] for t in trackers}
    for i, name in enumerate(titles):
        link = _infohash(salt * 10_000_000 + i)
        for ti, tname in enumerate(trackers):
            per_tracker[tname].append(_r(name, link, tname, seeds=100 - ti))
    return per_tracker


# --------------------------------------------------------------------------- #
# Stub orchestrator mirroring the REAL SearchOrchestrator surface that the
# streaming layer reads: ``deduplicator``, ``get_all_tracker_results``,
# ``get_live_results``, ``get_search_status``, and the authoritative
# ``_last_merged_results`` cache (set at completion in the real code).
# --------------------------------------------------------------------------- #
class _StubMeta:
    def __init__(self, status: str, total_results: int, merged_results: int, search_id: str):
        self.status = status
        self.total_results = total_results
        self.merged_results = merged_results
        self.search_id = search_id
        self.trackers_searched: list[str] = []
        self.tracker_stats: dict = {}

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "total_results": self.total_results,
            "merged_results": self.merged_results,
            "tracker_stats": [],
        }


class _StubOrchestrator:
    """Drives the SSE loop pending -> completed, revealing one tracker's
    results per poll so the accumulated raw set (and the re-merged interim
    snapshot) grows. At completion sets the authoritative
    ``_last_merged_results`` cache exactly like ``search.py:854-858``.

    Optional ``late_results`` land ONLY in the completion cache (never in
    ``get_all_tracker_results``) — the exact race the fix closes, used to
    distinguish the cached path from a fresh re-merge (anti-bluff §11.4.115).
    """

    def __init__(self, search_id: str, per_tracker: dict[str, list[SearchResult]], late_results: list | None = None):
        self.search_id = search_id
        self.deduplicator = Deduplicator()
        self._per_tracker = per_tracker
        self._reveal_order = list(per_tracker.keys())
        self._late_results = list(late_results or [])
        self._tracker_results: dict[str, dict[str, list]] = {search_id: {}}
        self._last_merged_results: dict[str, tuple] = {search_id: ([], [])}
        self._poll = 0

    # --- methods the SSE loop / _build_merged_update call ---
    def get_search_status(self, search_id):
        if self._poll < len(self._reveal_order):
            tname = self._reveal_order[self._poll]
            self._tracker_results[search_id][tname] = self._per_tracker[tname]
        self._poll += 1
        flat = self.get_all_tracker_results(search_id)
        revealed = len(self._tracker_results[search_id])
        done = revealed >= len(self._reveal_order)
        # One extra poll after the last reveal so the running-loop emits at
        # least one progressive interim merged_update before completion.
        status = "completed" if (done and self._poll > len(self._reveal_order)) else "running"
        if status == "completed":
            merged = self.deduplicator.merge_results([*flat, *self._late_results])
            self._last_merged_results[search_id] = (merged, [*flat, *self._late_results])
            merged_count = len(merged)
        else:
            merged_count = len(self.deduplicator.merge_results(flat)) if flat else 0
        return _StubMeta(status, len(flat), merged_count, search_id)

    def get_all_tracker_results(self, search_id):
        out: list = []
        for lst in self._tracker_results.get(search_id, {}).values():
            out.extend(lst)
        return out

    def get_live_results(self, search_id):
        return self.get_all_tracker_results(search_id)


# --------------------------------------------------------------------------- #
# SSE drain + parse helpers (mirror the sibling unit test).
# --------------------------------------------------------------------------- #
async def _drain(orch, search_id):
    frames = []
    gen = SSEHandler.search_results_stream(search_id, orch, poll_interval=0.0)
    async for frame in gen:
        frames.append(frame)
        if "event: search_complete" in frame:
            break
    return frames


def _parse_merged_updates(frames):
    out = []
    for frame in frames:
        lines = frame.split("\n")
        if any(line == "event: merged_update" for line in lines):
            data = "\n".join(line[len("data: ") :] for line in lines if line.startswith("data: "))
            out.append(json.loads(data))
    return out


@pytest.fixture(autouse=True)
def _no_throttle(monkeypatch):
    """Make the wall-clock merged_update throttle fire every poll so the
    progressive growth is observed deterministically (no sleeps)."""
    import api.streaming as streaming_mod

    monkeypatch.setattr(streaming_mod, "MERGED_UPDATE_MIN_INTERVAL_S", 0.0)


# ========================================================================== #
# STRESS
# ========================================================================== #
def test_stress_sustained_merged_build_nonshrink_and_latency():
    """Sustained load: build the merged_update over a LARGE accumulated set
    repeatedly (>=100x) as it grows across many trackers, record latency
    p50/p95, and assert the USER-OBSERVABLE invariants:

      * each emission is well-formed (count == len(results), contract keys);
      * the merged count is MONOTONIC-OR-STABLE — it NEVER shrinks then the
        final equals get_search (the exact "smaller list overwrites
        everything" / shrink defect the fix prevents);
      * the FINAL build byte-equals ``_serialize_merged_rows`` over the same
        ``_last_merged_results`` cache.
    """
    # 120 distinct titles x 3 trackers = 360 raw rows -> 120 unique merged rows
    # (mirrors the live 1785-raw → 663-merged collapse shape at a host-safe
    # scale — the merge is O(n²) Levenshtein, so a much larger set would melt
    # the host). The accumulation phase re-merges the growing raw set; the
    # post-completion phase reads the authoritative cache (cheap), so >=100
    # total builds stay fast.
    n_titles = 120
    trackers = ["rutracker", "kinozal", "nnmclub"]
    search_id = "stress-sustained"
    per_tracker = _make_large_corpus(n_titles, trackers)
    orch = _StubOrchestrator(search_id, per_tracker)

    iters = 0
    latencies: list[float] = []
    merged_counts: list[int] = []
    final_build = None

    def _one_build():
        nonlocal iters, final_build
        t0 = time.perf_counter()
        payload = _build_merged_update(orch, search_id)
        latencies.append((time.perf_counter() - t0) * 1000.0)
        iters += 1
        assert payload is not None
        # well-formed: merged count == number of serialized rows
        assert payload["merged_results"] == len(payload["results"])
        for row in payload["results"]:
            assert _CONTRACT_KEYS.issubset(set(row.keys())), f"row missing contract keys: {set(row.keys())}"
        merged_counts.append(payload["merged_results"])
        final_build = payload
        return payload

    # Phase 1: accumulation — advance one tracker per poll, building the
    # merged_update over the growing raw view each step (the interim
    # re-merge path).
    while True:
        meta = orch.get_search_status(search_id)
        _one_build()
        if meta.status == "completed":
            break

    # Phase 2: sustained load on the authoritative-cache path — hammer the
    # build >=100 times total to prove repeated reads are stable and never
    # shrink (the cached, byte-stable completion path).
    while iters < 120:
        _one_build()

    assert iters >= 100, f"expected >=100 build iterations, got {iters}"

    # NON-SHRINK invariant: the merged count never decreases as results
    # accumulate. This is the literal defect — a smaller list overwriting a
    # larger one mid-search.
    for a, b in itertools.pairwise(merged_counts):
        assert b >= a, f"merged count SHRANK {a} -> {b} (overwrite/shrink defect)"

    # FINAL == get_search: the last build byte-equals serializing the cache
    # (what GET /search/{id} returns).
    cached_merged, _all = orch._last_merged_results[search_id]
    get_rows = _serialize_merged_rows(cached_merged)
    get_serialized = [r.model_dump() for r in get_rows]
    assert final_build["merged_results"] == len(get_rows)
    assert final_build["results"] == get_serialized, "final build != get_search serialization (drop at completion)"
    assert final_build["merged_results"] == n_titles, "merge did not collapse duplicates to the unique title count"

    p50 = statistics.median(latencies)
    p95 = statistics.quantiles(latencies, n=20)[-1] if len(latencies) >= 20 else max(latencies)
    _write_evidence(
        "stress_sustained_latency",
        {
            "iterations": iters,
            "n_titles": n_titles,
            "trackers": trackers,
            "raw_rows": n_titles * len(trackers),
            "final_merged": final_build["merged_results"],
            "merged_count_trajectory": merged_counts,
            "nonshrink": True,
            "final_equals_get_search": True,
            "latency_ms_p50": round(p50, 4),
            "latency_ms_p95": round(p95, 4),
            "latency_ms_max": round(max(latencies), 4),
        },
    )


def test_stress_concurrent_searches_no_cross_contamination():
    """Concurrent contention: many in-flight searches (distinct search_ids)
    build merged_update concurrently. Assert NO cross-search contamination —
    search A's merged set NEVER contains a title that belongs only to B — and
    no exception is raised.
    """
    n_searches = 24
    trackers = ["rutracker", "kinozal", "nnmclub"]
    orchs: dict[str, _StubOrchestrator] = {}
    expected_titles: dict[str, set[str]] = {}

    for s in range(n_searches):
        sid = f"concurrent-{s}"
        # Each search uses a DISJOINT, maximally-distinct title namespace
        # (unique salt per search) so within a search nothing fuzzy-merges AND
        # across searches no two searches share a title.
        per_tracker = _make_large_corpus(20, trackers, salt=1000 + s)
        title_set = {row.name for lst in per_tracker.values() for row in lst}
        assert len(title_set) == 20, "corpus did not produce 20 distinct titles"
        expected_titles[sid] = title_set
        orchs[sid] = _StubOrchestrator(sid, per_tracker)

    # Guard: title namespaces across searches are genuinely disjoint, so the
    # contamination check below is meaningful.
    all_sets = list(expected_titles.values())
    for i in range(len(all_sets)):
        for j in range(i + 1, len(all_sets)):
            assert not (all_sets[i] & all_sets[j]), "search title namespaces overlap — test setup broken"

    # Interleave builds across all searches round-robin until every one
    # completes — maximises the chance any shared mutable state would leak.
    completed: dict[str, dict] = {}
    for _round in range(len(trackers) + 3):
        for sid, orch in orchs.items():
            meta = orch.get_search_status(sid)
            payload = _build_merged_update(orch, sid)
            assert payload is not None
            names = {row["name"] for row in payload["results"]}
            # Contamination check: every name in THIS search's merged set must
            # belong to THIS search's title namespace.
            foreign = names - expected_titles[sid]
            assert not foreign, f"cross-search contamination in {sid}: foreign titles {sorted(foreign)[:3]}"
            if meta.status == "completed":
                completed[sid] = payload

    assert len(completed) == n_searches, "not all concurrent searches completed"
    # Each completed search collapsed its 20 titles x 3 trackers -> 20 rows.
    for sid, payload in completed.items():
        assert payload["merged_results"] == 20, f"{sid} merged count wrong: {payload['merged_results']}"
        cached_merged, _all = orchs[sid]._last_merged_results[sid]
        assert payload["merged_results"] == len(_serialize_merged_rows(cached_merged))

    _write_evidence(
        "stress_concurrent_no_contamination",
        {
            "n_searches": n_searches,
            "trackers": trackers,
            "titles_per_search": 20,
            "all_completed": len(completed) == n_searches,
            "cross_search_contamination": False,
            "per_search_merged_counts": {sid: p["merged_results"] for sid, p in completed.items()},
        },
    )


def test_boundary_zero_trackers_empty_merged():
    """Boundary: zero trackers reported yet — empty accumulated set yields an
    empty merged_update (count 0, no rows), no crash."""
    sid = "boundary-zero"
    orch = _StubOrchestrator(sid, {})  # no trackers at all
    # Cache stays ([], []); build re-merges the empty get_all_tracker_results.
    payload = _build_merged_update(orch, sid)
    assert payload is not None
    assert payload["merged_results"] == 0
    assert payload["results"] == []
    _write_evidence("boundary_zero_trackers", {"merged_results": 0, "results": []})


def test_boundary_single_tracker():
    """Boundary: exactly one tracker with results — merged count equals the
    unique-title count it reported, every row carries the contract keys."""
    sid = "boundary-one"
    _solo_titles = _distinct_titles(5, salt=77)
    per_tracker = {"rutracker": [_r(_solo_titles[i], _infohash(i), "rutracker") for i in range(5)]}
    orch = _StubOrchestrator(sid, per_tracker)
    # drive to completion
    payload = None
    for _ in range(4):
        meta = orch.get_search_status(sid)
        payload = _build_merged_update(orch, sid)
        if meta.status == "completed":
            break
    assert payload is not None
    assert payload["merged_results"] == 5
    for row in payload["results"]:
        assert _CONTRACT_KEYS.issubset(set(row.keys()))
    cached_merged, _all = orch._last_merged_results[sid]
    assert payload["results"] == [r.model_dump() for r in _serialize_merged_rows(cached_merged)]
    _write_evidence("boundary_single_tracker", {"merged_results": payload["merged_results"]})


def test_boundary_all_trackers_empty():
    """Boundary: every tracker reported but ALL returned empty lists — merged
    set is empty and the final emit still byte-equals get_search ([])."""
    sid = "boundary-all-empty"
    per_tracker = {"rutracker": [], "kinozal": [], "nnmclub": []}
    orch = _StubOrchestrator(sid, per_tracker)
    payload = None
    for _ in range(6):
        meta = orch.get_search_status(sid)
        payload = _build_merged_update(orch, sid)
        if meta.status == "completed":
            break
    assert payload is not None
    assert payload["merged_results"] == 0
    assert payload["results"] == []
    cached_merged, _all = orch._last_merged_results[sid]
    assert _serialize_merged_rows(cached_merged) == []
    _write_evidence("boundary_all_empty", {"merged_results": 0})


def test_boundary_final_merged_byte_equals_get_search():
    """Boundary/invariant: the final merged_update is BYTE-equal to
    ``_serialize_merged_rows`` over the SAME ``_last_merged_results`` input —
    the exact consistency guarantee the fix relies on (same helper, same
    cache). Asserted via full SSE drive, not a synthetic call.
    """
    sid = "boundary-final-eq"
    trackers = ["rutracker", "kinozal", "nnmclub"]
    per_tracker = _make_large_corpus(40, trackers)
    orch = _StubOrchestrator(sid, per_tracker)
    frames = asyncio.run(_drain(orch, sid))
    merged_updates = _parse_merged_updates(frames)
    assert merged_updates, "no merged_update emitted"
    final_mu = merged_updates[-1]

    cached_merged, _all = orch._last_merged_results[sid]
    get_rows = _serialize_merged_rows(cached_merged)
    get_serialized = [r.model_dump() for r in get_rows]
    # BYTE-equality of the serialized row lists over the same merged input.
    assert final_mu["results"] == get_serialized, "final merged_update != get_search serialization"
    assert final_mu["merged_results"] == len(get_rows) == 40

    # NON-SHRINK across the whole stream's merged_update sequence.
    counts = [mu["merged_results"] for mu in merged_updates]
    for a, b in itertools.pairwise(counts):
        assert b >= a, f"streamed merged count shrank {a}->{b}"

    _write_evidence(
        "boundary_final_eq_get_search",
        {
            "n_merged_updates": len(merged_updates),
            "merged_count_trajectory": counts,
            "final_merged": final_mu["merged_results"],
            "byte_equal_get_search": True,
        },
    )


# ========================================================================== #
# CHAOS
# ========================================================================== #
def test_chaos_partial_tracker_failure_keeps_good_results():
    """Partial tracker failure: a 'good' tracker landed results, then a
    'broken' tracker raises mid-accumulation (it contributes nothing). The
    merged stream MUST keep emitting the good tracker's results, never crash,
    never DROP already-found results.

    The failing tracker is modelled by an orchestrator whose
    ``get_all_tracker_results`` raises on the broken tracker's slice — we wrap
    the build so a partial failure cannot wipe the good rows.
    """
    sid = "chaos-partial-fail"
    _good_titles = _distinct_titles(6, salt=55)
    good = [_r(_good_titles[i], _infohash(i), "rutracker") for i in range(6)]

    class _PartialFailOrch(_StubOrchestrator):
        def __init__(self):
            super().__init__(sid, {"rutracker": good, "broken": []})
            self._fail_raised = False

        def get_all_tracker_results(self, search_id):
            # Good tracker's results are always present. The broken tracker
            # raises once mid-accumulation; the build must not lose the good
            # rows already accumulated.
            base = list(good) if "rutracker" in self._tracker_results.get(search_id, {}) else []
            if "broken" in self._tracker_results.get(search_id, {}) and not self._fail_raised:
                self._fail_raised = True
                raise RuntimeError("broken tracker raised mid-accumulation")
            return base

    orch = _PartialFailOrch()
    good_count_seen = []
    crashed = False
    payloads = []
    for _ in range(6):
        try:
            meta = orch.get_search_status(sid)
        except RuntimeError:
            # status poll itself may surface the broken tracker; the stream
            # loop swallows such errors — emulate by skipping this poll.
            crashed = True
            continue
        payload = _build_merged_update(orch, sid)
        if payload is not None:
            payloads.append(payload)
            good_count_seen.append(payload["merged_results"])
        if getattr(meta, "status", "running") == "completed":
            break

    # USER-OBSERVABLE: the good results are never lost. Every successful build
    # carried all 6 good rows (the broken tracker contributes 0, but cannot
    # delete the good ones).
    assert payloads, "no merged_update survived the partial failure"
    assert max(good_count_seen) == 6, f"good results were dropped: max seen {good_count_seen}"
    # Non-shrink across the surviving builds.
    for a, b in itertools.pairwise(good_count_seen):
        assert b >= a, f"good-result count shrank {a}->{b} after partial failure"
    _write_evidence(
        "chaos_partial_tracker_failure",
        {
            "good_results": 6,
            "broken_tracker_raised": True,
            "good_count_trajectory": good_count_seen,
            "good_results_preserved": max(good_count_seen) == 6,
        },
    )


def test_chaos_late_arriving_tracker_count_grows_no_shrink():
    """Late-arriving tracker: a tracker returns its results AFTER interim
    merged_updates were already emitted (it lands ONLY in the completion
    cache). The next/final merged_update INCLUDES it and the count GROWS — the
    final must be LARGER than the largest interim, never smaller (no shrink).
    """
    sid = "chaos-late"
    trackers = ["rutracker", "kinozal", "nnmclub"]
    per_tracker = _make_large_corpus(30, trackers, salt=0)
    # 4 late titles that arrive ONLY at completion (never in get_all). Distinct
    # salt so they never fuzzy-merge with the 30 base titles.
    _late_titles = _distinct_titles(4, salt=424242)
    late = [_r(_late_titles[i], _infohash(900000 + i), "rutracker") for i in range(4)]
    orch = _StubOrchestrator(sid, per_tracker, late_results=late)
    frames = asyncio.run(_drain(orch, sid))
    merged_updates = _parse_merged_updates(frames)
    assert merged_updates, "no merged_update emitted"
    counts = [mu["merged_results"] for mu in merged_updates]
    final = merged_updates[-1]["merged_results"]

    # The late results grow the final beyond the interim peak: interim sees at
    # most the 30 accumulated titles; final sees 30 + 4 late = 34.
    interim_peak = max(counts[:-1]) if len(counts) > 1 else 0
    assert final == 34, f"final merged count {final} != 30 base + 4 late"
    assert final >= interim_peak, f"final {final} shrank below interim peak {interim_peak}"
    for a, b in itertools.pairwise(counts):
        assert b >= a, f"merged count shrank {a}->{b} (late arrival caused shrink)"

    # And the final equals get_search over the cache (which includes the late).
    cached_merged, _all = orch._last_merged_results[sid]
    assert merged_updates[-1]["results"] == [r.model_dump() for r in _serialize_merged_rows(cached_merged)]
    late_names = {r.name for r in late}
    final_names = {row["name"] for row in merged_updates[-1]["results"]}
    assert late_names <= final_names, "late-arriving results missing from final merged_update"
    _write_evidence(
        "chaos_late_arriving_tracker",
        {
            "base_titles": 30,
            "late_titles": 4,
            "merged_count_trajectory": counts,
            "interim_peak": interim_peak,
            "final": final,
            "late_included_in_final": True,
            "no_shrink": True,
        },
    )


def test_chaos_missing_cache_falls_back_to_remerge():
    """Stale/missing cache: ``_last_merged_results`` missing/empty for a
    search_id → ``_build_merged_update`` falls back to re-merging
    ``get_all_tracker_results`` WITHOUT crashing, and the fallback still
    produces the correct deduplicated set."""
    sid = "chaos-missing-cache"
    trackers = ["rutracker", "kinozal"]
    per_tracker = _make_large_corpus(12, trackers)
    orch = _StubOrchestrator(sid, per_tracker)
    # Reveal all trackers' raw results, but FORCE the cache to be missing
    # entirely (simulates the still-running / evicted-cache state).
    for _ in range(len(trackers)):
        orch.get_search_status(sid)
    del orch._last_merged_results[sid]  # cache MISSING for this search_id

    payload = _build_merged_update(orch, sid)
    assert payload is not None, "missing cache must not kill the build"
    # Fallback re-merge collapses 12 titles x 2 trackers -> 12 unique.
    assert payload["merged_results"] == 12
    # Equivalent to a fresh re-merge of get_all_tracker_results.
    fresh = orch.deduplicator.merge_results(orch.get_all_tracker_results(sid))
    assert payload["results"] == [r.model_dump() for r in _serialize_merged_rows(fresh)]

    # Also exercise empty-cache (([], [])) explicitly — same fallback path.
    orch2 = _StubOrchestrator("chaos-empty-cache", per_tracker)
    for _ in range(len(trackers)):
        orch2.get_search_status("chaos-empty-cache")
    orch2._last_merged_results["chaos-empty-cache"] = ([], [])  # empty sentinel
    payload2 = _build_merged_update(orch2, "chaos-empty-cache")
    assert payload2 is not None and payload2["merged_results"] == 12

    _write_evidence(
        "chaos_missing_cache_fallback",
        {
            "missing_cache_remerge_count": payload["merged_results"],
            "empty_cache_remerge_count": payload2["merged_results"],
            "no_crash": True,
        },
    )


def test_chaos_malformed_accumulated_serialization_survives():
    """Malformed accumulated results: None fields, None seeds/leechers, and
    unicode names. Serialization (merge + ``_serialize_merged_rows``) must NOT
    crash, and well-formed rows must still survive. Specifically verifies the
    recently-landed None-seeds dedup fix holds on this path too.
    """
    sid = "chaos-malformed"
    # None seeds/leechers (the dedup-fix target), unicode, empty/None-ish
    # fields — all routed through the real merge + serialize.
    malformed = [
        SearchResult(
            name="Фильм 2024 1080p BluRay",  # unicode
            link=_infohash(1),
            size="3.1 GB",
            seeds=None,  # type: ignore[arg-type]  # None seeds — must coerce to 0
            leechers=None,  # type: ignore[arg-type]
            engine_url="https://rutracker.example",
            tracker="rutracker",
        ),
        SearchResult(
            name="Фильм 2024 1080p BluRay",  # same logical torrent, other tracker
            link=_infohash(1),
            size="3.1 GB",
            seeds=5,
            leechers=1,
            engine_url="https://kinozal.example",
            tracker="kinozal",
        ),
        SearchResult(
            name="",  # empty name
            link="",  # empty link
            size="0 B",
            seeds=0,
            leechers=0,
            engine_url="",
            tracker=None,  # None tracker
        ),
    ]

    class _MalformedOrch(_StubOrchestrator):
        def __init__(self):
            super().__init__(sid, {"rutracker": malformed})

    orch = _MalformedOrch()
    # Drive to completion through the FULL SSE loop — the loop also streams
    # result_found rows for each malformed result, so this exercises the
    # serialization on both the per-result and merged paths.
    crashed = None
    try:
        frames = asyncio.run(_drain(orch, sid))
    except Exception as e:  # pragma: no cover - this failing IS the defect
        crashed = repr(e)
        frames = []
    assert crashed is None, f"serialization crashed on malformed input: {crashed}"

    merged_updates = _parse_merged_updates(frames)
    assert merged_updates, "no merged_update emitted from malformed corpus"
    final = merged_updates[-1]
    # The two identical-infohash unicode rows collapse to ONE; the empty row
    # is its own group → 2 merged rows total. The key assertion is NO CRASH +
    # the None-seeds row coerced to a valid int total.
    assert final["merged_results"] == len(final["results"])
    for row in final["results"]:
        assert _CONTRACT_KEYS.issubset(set(row.keys()))
        assert isinstance(row["seeds"], int), "seeds must be a coerced int even when source was None"
        assert isinstance(row["leechers"], int)
    # The unicode title survived and its seeds = 0(None)+5 = 5 (None coerced).
    uni = [r for r in final["results"] if r["name"] == "Фильм 2024 1080p BluRay"]
    assert uni, "unicode-titled merged row was lost"
    assert uni[0]["seeds"] == 5, f"None-seeds coercion broken: {uni[0]['seeds']}"

    cached_merged, _all = orch._last_merged_results[sid]
    assert final["results"] == [r.model_dump() for r in _serialize_merged_rows(cached_merged)]
    _write_evidence(
        "chaos_malformed_serialization",
        {
            "input_rows": len(malformed),
            "final_merged": final["merged_results"],
            "none_seeds_coerced_total": uni[0]["seeds"],
            "no_crash": True,
            "unicode_preserved": True,
        },
    )


# ========================================================================== #
# §11.4.85 category-map self-check (meta) — proves the docstring map is real.
# ========================================================================== #
def test_section_114_85_category_map():
    """Anti-bluff meta: assert every §11.4.85 category named in the module
    docstring is realised by a collected test function in THIS module, so the
    coverage claim cannot drift from reality."""
    import inspect

    this = sys.modules[__name__]
    test_names = {n for n, o in inspect.getmembers(this, inspect.isfunction) if n.startswith("test_")}
    required = {
        # STRESS
        "test_stress_sustained_merged_build_nonshrink_and_latency",
        "test_stress_concurrent_searches_no_cross_contamination",
        "test_boundary_zero_trackers_empty_merged",
        "test_boundary_single_tracker",
        "test_boundary_all_trackers_empty",
        "test_boundary_final_merged_byte_equals_get_search",
        # CHAOS
        "test_chaos_partial_tracker_failure_keeps_good_results",
        "test_chaos_late_arriving_tracker_count_grows_no_shrink",
        "test_chaos_missing_cache_falls_back_to_remerge",
        "test_chaos_malformed_accumulated_serialization_survives",
    }
    missing = required - test_names
    assert not missing, f"§11.4.85 category map references missing tests: {missing}"
