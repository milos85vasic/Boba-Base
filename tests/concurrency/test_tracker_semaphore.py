"""Verify the per-search tracker semaphore caps concurrent _search_one calls.

Creates 40 mock trackers and asserts that at no point do more than
MAX_CONCURRENT_TRACKERS (default 8) run simultaneously.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[2] / "download-proxy" / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

os.environ.setdefault("ALLOWED_ORIGINS", "http://localhost")


def _fresh_orchestrator(cap: int):
    os.environ["MAX_CONCURRENT_TRACKERS"] = str(cap)
    for mod_name in [k for k in list(sys.modules) if k.startswith("merge_service")]:
        del sys.modules[mod_name]
    from merge_service.search import SearchOrchestrator, TrackerSource

    orch = SearchOrchestrator()
    return orch, TrackerSource


NUM_TRACKERS = 40
CAP = 5


@pytest.mark.asyncio
async def test_tracker_semaphore_never_exceeds_cap():
    orch, TrackerSource = _fresh_orchestrator(cap=CAP)
    assert orch._max_concurrent_trackers == CAP

    peak = 0
    current = 0
    gate = asyncio.Event()

    async def _slow_tracker(_self, tracker, _q, _c):
        nonlocal peak, current
        current += 1
        peak = max(peak, current)
        await gate.wait()
        current -= 1
        return []

    orch._search_tracker = _slow_tracker.__get__(orch, type(orch))

    trackers = [TrackerSource(name=f"tracker-{i:02d}", url=f"https://t{i}.example") for i in range(NUM_TRACKERS)]
    orch._get_enabled_trackers = lambda: trackers

    metadata = orch.start_search("test query", "all")
    metadata.total_results = 0

    run_task = asyncio.create_task(orch._run_search(metadata.search_id, "test query", "all"))

    for _ in range(50):
        await asyncio.sleep(0)
        if peak >= CAP:
            break

    await asyncio.sleep(0.05)
    gate.set()
    await run_task

    assert peak <= CAP, f"semaphore breached: peak inflight = {peak}, cap = {CAP}"
    assert current == 0, f"leaked inflight: {current} tasks still counted"
    assert metadata.status == "completed"


@pytest.mark.asyncio
async def test_tracker_semaphore_default_cap_is_8():
    # RW-08: default raised 5 -> 8.
    for mod_name in [k for k in list(sys.modules) if k.startswith("merge_service")]:
        del sys.modules[mod_name]
    os.environ.pop("MAX_CONCURRENT_TRACKERS", None)
    from merge_service.search import SearchOrchestrator

    orch = SearchOrchestrator()
    assert orch._max_concurrent_trackers == 8


@pytest.mark.asyncio
async def test_tracker_semaphore_respects_env_override():
    orch, _ = _fresh_orchestrator(cap=2)
    assert orch._max_concurrent_trackers == 2

    peak = 0
    current = 0
    gate = asyncio.Event()

    async def _slow_tracker(_self, tracker, _q, _c):
        nonlocal peak, current
        current += 1
        peak = max(peak, current)
        await gate.wait()
        current -= 1
        return []

    orch._search_tracker = _slow_tracker.__get__(orch, type(orch))

    from merge_service.search import TrackerSource

    trackers = [TrackerSource(name=f"t-{i}", url=f"https://t{i}.x") for i in range(10)]
    orch._get_enabled_trackers = lambda: trackers

    metadata = orch.start_search("q", "all")
    metadata.total_results = 0

    run_task = asyncio.create_task(orch._run_search(metadata.search_id, "q", "all"))
    await asyncio.sleep(0.05)
    gate.set()
    await run_task

    assert peak <= 2, f"semaphore breached with cap=2: peak = {peak}"
    assert metadata.status == "completed"
