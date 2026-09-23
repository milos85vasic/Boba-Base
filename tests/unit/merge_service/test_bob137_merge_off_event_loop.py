"""BOB-137 — the dedup merge must run OFF the asyncio event-loop thread.

WHY THIS TEST EXISTS
--------------------
BOB-137: port 7187 (the asyncio merge service) stops answering while port
7186, served by the SAME process, keeps answering. 1dd7b0a captured the root
cause from 16 real stack dumps: ``Deduplicator.merge_results()`` invoked as a
plain synchronous call on the event-loop thread. BOB-145 made the merge
~17x cheaper but explicitly left the CALL SITE synchronous, and the
2026-08-21 live soak still measured 2/141 dead 7187 probes with the loop
thread sampled at state R / wchan 0 — the residual BOB-145 itself predicted.

There are two synchronous call sites on the loop thread:

  * ``SearchOrchestrator._run_search``  (merge_service/search.py)
  * ``api.streaming._build_merged_update`` driven from the SSE generator
    (re-merges the accumulated raw results for every interim
    ``merged_update`` — once per open SSE client per throttle window).

The fix offloads both to a worker thread. A pure-Python worker still takes
the GIL, but CPython hands the GIL back every ``sys.getswitchinterval()``
(5 ms default), so the loop thread gets scheduled throughout the merge
instead of not at all. That is exactly the difference between "7187 slow
during a merge" and "7187 dead during a merge".

ORACLES (§11.4.245)
-------------------
1. STRUCTURAL (primary, load-independent): the thread identity on which
   ``merge_results`` actually executes, recorded by the fake merge, must
   differ from the event-loop thread identity. Contention cannot flip this.
2. USER-OBSERVABLE (secondary): a 5 ms heartbeat coroutine stands in for
   uvicorn's accept/read/write callbacks. While a merge that spins for
   ``SPIN_S`` runs ON the loop, the heartbeat gets zero ticks and its worst
   gap is >= SPIN_S. Off the loop it keeps ticking.
3. RE-ENTRANCY: once merges can run on worker threads, two concurrent
   searches may call ``merge_results`` on the SAME shared ``Deduplicator``
   instance at the same time. The pre-fix implementation kept its working
   list in ``self._merged_groups`` and rebound it at the start of every
   call, so an interleaved second call made the first one append into —
   and return — the second one's list. Guarded deterministically by forcing
   the interleave from inside the first merge.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

_REPO = Path(__file__).resolve().parents[3]
_SRC = _REPO / "download-proxy" / "src"
_MS = _SRC / "merge_service"

if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

sys.modules.setdefault("merge_service", type(sys)("merge_service"))
sys.modules["merge_service"].__path__ = [str(_MS)]  # type: ignore[attr-defined]
for _name in ("search", "deduplicator"):
    _mod_name = f"merge_service.{_name}"
    if _mod_name not in sys.modules:
        _spec = importlib.util.spec_from_file_location(_mod_name, str(_MS / f"{_name}.py"))
        _mod = importlib.util.module_from_spec(_spec)
        sys.modules[_mod_name] = _mod
        _spec.loader.exec_module(_mod)  # type: ignore[union-attr]

_search = sys.modules["merge_service.search"]
_dedup_mod = sys.modules["merge_service.deduplicator"]

from api.streaming import SSEHandler  # noqa: E402

SearchResult = _search.SearchResult
Deduplicator = _dedup_mod.Deduplicator

#: How long the fake merge busy-spins (pure Python, GIL-holding).
SPIN_S = 0.4
#: Heartbeat period — the same 5 ms the BOB-145 guard uses.
HEARTBEAT_S = 0.005
#: If the loop was frozen for the entire merge the worst gap is >= SPIN_S.
#: Off-loop, the loop is rescheduled every GIL switch interval (5 ms), so a
#: gap anywhere near SPIN_S means it was NOT offloaded. Half of SPIN_S keeps
#: a wide margin on a contended host while still discriminating.
MAX_GAP_S = SPIN_S / 2


#: Mutually dissimilar titles so no two fixtures fuzzy-match (similarity
#: threshold 0.85) — each fixture is its own merge group.
_TITLES = (
    "Inception",
    "Gladiator",
    "Casablanca",
    "Whiplash",
    "Parasite",
    "Oppenheimer",
    "Amadeus",
    "Chinatown",
    "Braveheart",
    "Nightcrawler",
    "Sicario",
    "Vertigo",
)


def _result(i: int, tracker: str = "rutracker") -> SearchResult:
    return SearchResult(
        name=f"{_TITLES[i % len(_TITLES)]} {2000 + i} 1080p WEB-DL x264",
        link=f"magnet:?xt=urn:btih:{i:040x}",
        size="1.5 GB",
        seeds=10 + i,
        leechers=1,
        engine_url="https://example.com",
        tracker=tracker,
    )


class _RecordingMerge:
    """Wraps a real ``merge_results``: records the executing thread, spins
    for ``SPIN_S`` holding the GIL (the BOB-137 CPU-bound shape), then
    delegates so downstream behaviour is the real one."""

    def __init__(self, real) -> None:
        self._real = real
        self.threads: list[int] = []

    def __call__(self, results):
        self.threads.append(threading.get_ident())
        end = time.perf_counter() + SPIN_S
        while time.perf_counter() < end:  # pure-Python busy work, holds the GIL
            pass
        return self._real(results)


async def _heartbeat(stop: asyncio.Event, gaps: list[float]) -> None:
    last = time.perf_counter()
    while not stop.is_set():
        await asyncio.sleep(HEARTBEAT_S)
        now = time.perf_counter()
        gaps.append(now - last)
        last = now


# --------------------------------------------------------------------------- #
# Site 1 — SearchOrchestrator._run_search
# --------------------------------------------------------------------------- #
def test_run_search_merges_off_the_event_loop_thread() -> None:
    orch = _search.SearchOrchestrator()
    recorder = _RecordingMerge(orch.deduplicator.merge_results)
    orch.deduplicator.merge_results = recorder  # type: ignore[method-assign]

    async def fake_tracker(self, tracker, query, category):
        return [_result(i, tracker.name) for i in range(3)]

    async def scenario() -> tuple[int, list[float], str]:
        loop_thread = threading.get_ident()
        stop = asyncio.Event()
        gaps: list[float] = []
        beat = asyncio.create_task(_heartbeat(stop, gaps))
        await asyncio.sleep(0.05)
        metadata = orch.start_search("q", "all", enable_metadata=False, validate_trackers=False)
        with patch.object(_search.SearchOrchestrator, "_search_tracker", fake_tracker):
            await orch._run_search(metadata.search_id, "q", "all")
        stop.set()
        await beat
        return loop_thread, gaps, metadata.status

    loop_thread, gaps, status = asyncio.run(scenario())

    assert recorder.threads, "merge_results was never invoked; instrument is blind"
    assert status == "completed", f"search did not complete (status={status})"
    assert all(t != loop_thread for t in recorder.threads), (
        "SearchOrchestrator._run_search ran Deduplicator.merge_results ON the event-loop "
        "thread — while it runs, port 7187 services no request (BOB-137)."
    )
    worst = max(gaps)
    assert worst < MAX_GAP_S, (
        f"event loop frozen {worst * 1000:.0f}ms during a {SPIN_S * 1000:.0f}ms merge "
        f"(ceiling {MAX_GAP_S * 1000:.0f}ms) — the BOB-137 7187 wedge signature."
    )
    merged, _raw = orch._last_merged_results[metadata_id(orch)]
    assert merged, "offloaded merge result was not stored — the fix lost the output"


def metadata_id(orch) -> str:
    ids = list(orch._last_merged_results.keys())
    assert len(ids) == 1, f"expected exactly one completed search, got {ids}"
    return ids[0]


# --------------------------------------------------------------------------- #
# Site 2 — SSE interim merged_update re-merge
# --------------------------------------------------------------------------- #
class _Meta:
    def __init__(self, status: str, total: int, search_id: str) -> None:
        self.status = status
        self.total_results = total
        self.merged_results = 0
        self.search_id = search_id
        self.trackers_searched: list[str] = []
        self.tracker_stats: dict = {}

    def to_dict(self) -> dict:
        return {"status": self.status, "total_results": self.total_results}


class _Orch:
    """Two running polls with raw results accumulated, then completed with
    an EMPTY authoritative cache so every merged_update re-merges."""

    def __init__(self, search_id: str) -> None:
        self.deduplicator = Deduplicator()
        self._raw = [_result(i) for i in range(4)]
        self._last_merged_results: dict = {search_id: ([], [])}
        self._polls = 0

    def get_search_status(self, search_id):
        self._polls += 1
        status = "completed" if self._polls > 2 else "running"
        return _Meta(status, len(self._raw), search_id)

    def get_all_tracker_results(self, search_id):
        return list(self._raw)

    def get_live_results(self, search_id):
        return []


def test_sse_merged_update_remerges_off_the_event_loop_thread() -> None:
    sid = "bob137-sse"
    orch = _Orch(sid)
    recorder = _RecordingMerge(orch.deduplicator.merge_results)
    orch.deduplicator.merge_results = recorder  # type: ignore[method-assign]

    async def scenario() -> tuple[int, list[float], list[str]]:
        loop_thread = threading.get_ident()
        stop = asyncio.Event()
        gaps: list[float] = []
        beat = asyncio.create_task(_heartbeat(stop, gaps))
        await asyncio.sleep(0.05)
        frames: list[str] = []
        async for frame in SSEHandler.search_results_stream(sid, orch, poll_interval=0.0):
            frames.append(frame)
            if "event: search_complete" in frame:
                break
        stop.set()
        await beat
        return loop_thread, gaps, frames

    loop_thread, gaps, frames = asyncio.run(scenario())

    assert recorder.threads, "no merged_update re-merge happened; instrument is blind"
    assert any("event: merged_update" in f for f in frames), "no merged_update frame was emitted"
    assert all(t != loop_thread for t in recorder.threads), (
        "the SSE generator re-merged ON the event-loop thread — every open SSE client "
        "freezes port 7187 for the merge duration (BOB-137)."
    )
    worst = max(gaps)
    assert worst < MAX_GAP_S, (
        f"event loop frozen {worst * 1000:.0f}ms during an SSE re-merge (ceiling {MAX_GAP_S * 1000:.0f}ms)"
    )


# --------------------------------------------------------------------------- #
# Re-entrancy of the shared Deduplicator once merges run on worker threads
# --------------------------------------------------------------------------- #
def test_interleaved_merges_on_one_deduplicator_do_not_share_output() -> None:
    dedup = Deduplicator()
    batch_a = [_result(i) for i in range(0, 3)]
    batch_b = [_result(i) for i in range(100, 105)]
    expected_a = {r.link for r in batch_a}
    expected_b = {r.link for r in batch_b}

    real_update = dedup._update_best_quality
    fired: list[bool] = []
    inner: dict[str, list] = {}

    def interleave(merged):
        # Simulate a second thread's merge landing in the middle of the first.
        if not fired:
            fired.append(True)
            inner["b"] = dedup.merge_results(batch_b)
        return real_update(merged)

    with patch.object(dedup, "_update_best_quality", side_effect=interleave):
        out_a = dedup.merge_results(batch_a)

    assert fired, "interleave never fired; instrument is blind"
    links_a = {link for m in out_a for link in (r.link for r in m.original_results)}
    links_b = {link for m in inner["b"] for link in (r.link for r in m.original_results)}
    assert links_a == expected_a, (
        f"merge A returned groups from merge B ({sorted(links_a - expected_a)[:3]}...) — "
        "Deduplicator shares its working list across concurrent calls"
    )
    assert links_b == expected_b, "merge B was corrupted by merge A appending into it"
    assert out_a is not inner["b"], "two merges returned the very same list object"


@pytest.mark.parametrize("n", [0, 1, 5])
def test_merge_output_unchanged_by_reentrancy_fix(n: int) -> None:
    """Sequential behaviour is unchanged: results and `_merged_groups` agree."""
    dedup = Deduplicator()
    out = dedup.merge_results([_result(i) for i in range(n)])
    assert len(out) == n
    assert dedup._merged_groups == out
