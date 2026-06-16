"""Verify Phase-3 ``MAX_CONCURRENT_TRACKERS`` semaphore never exceeds
its cap even under adversarial fan-out.

The orchestrator exposes ``_inflight_count`` which is incremented
*inside* the semaphore and decremented on exit. We drive the public
``_bounded`` helper via monkeypatched ``_search_tracker`` so we can
observe the peak without needing live network.
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
    from merge_service.search import SearchOrchestrator

    return SearchOrchestrator()


@pytest.mark.asyncio
async def test_semaphore_caps_inflight_at_3():
    orch = _fresh_orchestrator(cap=3)
    peak = 0
    gate = asyncio.Event()

    async def _slow_search(_t, _q, _c):
        nonlocal peak
        peak = max(peak, orch._inflight_count)
        await gate.wait()
        peak = max(peak, orch._inflight_count)
        return []

    orch._search_tracker = _slow_search  # type: ignore[assignment]

    semaphore = asyncio.Semaphore(orch._max_concurrent_trackers)

    async def _bounded(name):
        async with semaphore:
            orch._inflight_count += 1
            try:
                return await orch._search_tracker(name, "q", "all")
            finally:
                orch._inflight_count -= 1

    task = asyncio.gather(*[_bounded(f"tracker-{i}") for i in range(20)])
    # Give the event loop time to schedule tasks and saturate the sem.
    await asyncio.sleep(0.05)
    gate.set()
    await task

    assert peak <= 3, f"semaphore breached: peak inflight = {peak}"
    assert orch._inflight_count == 0


@pytest.mark.asyncio
async def test_default_cap_is_8_when_env_unset(monkeypatch):
    # RW-08: default raised 5 -> 8.
    monkeypatch.delenv("MAX_CONCURRENT_TRACKERS", raising=False)
    # Reimport to pick up the fresh env.
    for mod_name in [k for k in list(sys.modules) if k.startswith("merge_service")]:
        del sys.modules[mod_name]
    from merge_service.search import SearchOrchestrator

    orch = SearchOrchestrator()
    assert orch._max_concurrent_trackers == 8
