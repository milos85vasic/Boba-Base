"""
Bounded concurrency on tracker fan-out.

SearchOrchestrator must cap how many _search_one coroutines are in flight at
once via an asyncio.Semaphore sized from the MAX_CONCURRENT_TRACKERS env var
(default 5).  The semaphore body also bumps an instance-level
`_inflight_count` that tests — and Phase 6 observability — assert against.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys

import pytest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_SRC_PATH = os.path.join(_REPO_ROOT, "download-proxy", "src")
_MS_PATH = os.path.join(_SRC_PATH, "merge_service")

if _SRC_PATH not in sys.path:
    sys.path.insert(0, _SRC_PATH)

sys.modules.setdefault("merge_service", type(sys)("merge_service"))
sys.modules["merge_service"].__path__ = [_MS_PATH]


def _import_search_module():
    spec = importlib.util.spec_from_file_location("merge_service.search", os.path.join(_MS_PATH, "search.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["merge_service.search"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def search_mod():
    return _import_search_module()


async def _run_bounded_search(orch, search_mod, num_trackers: int, tick: float = 0.02):
    """Mimic the production fan-out code path by invoking `search()` against
    a patched `_get_enabled_trackers` + `_search_tracker` where each tracker
    spends ``tick`` seconds "working" so we can observe peak in-flight count.
    """
    peak = {"n": 0}
    tracker_source_cls = search_mod.TrackerSource

    fake_trackers = [
        tracker_source_cls(name=f"t{i}", url=f"http://tracker-{i}.invalid", enabled=True) for i in range(num_trackers)
    ]

    calls: list[str] = []

    orch._get_enabled_trackers = lambda: fake_trackers

    async def fake_search_tracker(tracker, query, category):
        # we cannot observe the semaphore from here if caller didn't enter;
        # _inflight_count is bumped inside the _bounded() wrapper
        peak["n"] = max(peak["n"], orch._inflight_count)
        calls.append(tracker.name)
        await asyncio.sleep(tick)
        return []

    orch._search_tracker = fake_search_tracker

    await orch.search(query="q", category="all", enable_metadata=False, validate_trackers=False)
    return peak["n"], calls


@pytest.mark.asyncio
async def test_custom_cap_is_respected(monkeypatch, search_mod):
    monkeypatch.setenv("MAX_CONCURRENT_TRACKERS", "3")
    orch = search_mod.SearchOrchestrator()

    peak, calls = await _run_bounded_search(orch, search_mod, num_trackers=20, tick=0.02)

    assert peak <= 3, f"peak inflight {peak} exceeded configured cap 3"
    assert len(calls) == 20
    assert len(set(calls)) == 20


@pytest.mark.asyncio
async def test_default_cap_is_eight(monkeypatch, search_mod):
    # RW-08: default tracker fan-out cap raised 5 -> 8 to cut the wave count
    # (~6 -> ~4) without dropping any tracker. Env override still wins.
    monkeypatch.delenv("MAX_CONCURRENT_TRACKERS", raising=False)
    orch = search_mod.SearchOrchestrator()

    assert orch._max_concurrent_trackers == 8

    peak, calls = await _run_bounded_search(orch, search_mod, num_trackers=20, tick=0.02)

    assert peak <= 8, f"peak inflight {peak} exceeded default cap 8"
    assert peak > 5, f"peak inflight {peak} did not exceed the old cap of 5 — fan-out not widened"
    assert len(calls) == 20


@pytest.mark.asyncio
async def test_each_tracker_runs_exactly_once(monkeypatch, search_mod):
    monkeypatch.setenv("MAX_CONCURRENT_TRACKERS", "2")
    orch = search_mod.SearchOrchestrator()

    _peak, calls = await _run_bounded_search(orch, search_mod, num_trackers=20, tick=0.005)

    assert sorted(calls) == sorted(f"t{i}" for i in range(20))


@pytest.mark.asyncio
async def test_inflight_counter_returns_to_zero(monkeypatch, search_mod):
    monkeypatch.setenv("MAX_CONCURRENT_TRACKERS", "4")
    orch = search_mod.SearchOrchestrator()

    await _run_bounded_search(orch, search_mod, num_trackers=10, tick=0.005)

    assert orch._inflight_count == 0
