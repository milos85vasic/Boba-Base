"""§11.4.135 regression-guard suite — BUG-1 provider selection.

Audit ref: docs/qa/search-flow-audit-20260615/findings.md BUG-1.

Before the fix there was NO way to search one or a chosen subset of
providers — every search silently fanned out to ALL enabled trackers, so
the single/selected UI modes had nothing to exercise.

These tests are anti-bluff (§11.4): each asserts on the *actual set of
trackers searched* (the user-observable ``metadata.trackers_searched``
plus the set the orchestrator dispatched ``_search_tracker`` against),
not a status code. RED on the pre-fix code: ``search(... trackers=...)``
rejects the kwarg with a TypeError.
"""

from __future__ import annotations

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


def _make_orch_with_recorder(search_mod, enabled_names):
    """Build an orchestrator with a fixed enabled-tracker set whose
    ``_search_tracker`` records which tracker names were dispatched.
    """
    TrackerSource = search_mod.TrackerSource
    orch = search_mod.SearchOrchestrator()

    sources = [TrackerSource(name=n, url=f"https://{n}.example", enabled=True) for n in enabled_names]
    orch._get_enabled_trackers = lambda: list(sources)  # type: ignore[method-assign]

    recorded: list[str] = []

    async def _fake_search_tracker(tracker, query, category):  # type: ignore[no-untyped-def]
        recorded.append(tracker.name)
        return []

    orch._search_tracker = _fake_search_tracker  # type: ignore[method-assign]
    orch._is_tracker_authenticated = lambda name: False  # type: ignore[method-assign]
    return orch, recorded


@pytest.mark.asyncio
async def test_single_provider_filters_fanout(search_mod):
    """trackers=["rutracker"] dispatches to ONLY rutracker."""
    orch, recorded = _make_orch_with_recorder(search_mod, ["rutracker", "rutor", "nyaa"])

    metadata = await orch.search(query="debian", trackers=["rutracker"])

    assert set(recorded) == {"rutracker"}, f"expected only rutracker dispatched, got {recorded}"
    assert metadata.trackers_searched == ["rutracker"]


@pytest.mark.asyncio
async def test_subset_provider_filters_fanout(search_mod):
    """A two-element subset dispatches to exactly those two."""
    orch, recorded = _make_orch_with_recorder(search_mod, ["rutracker", "rutor", "nyaa"])

    metadata = await orch.search(query="debian", trackers=["rutor", "nyaa"])

    assert set(recorded) == {"rutor", "nyaa"}
    assert set(metadata.trackers_searched) == {"rutor", "nyaa"}


@pytest.mark.asyncio
async def test_none_filter_fans_out_to_all(search_mod):
    """trackers=None searches every enabled tracker (back-compat)."""
    orch, recorded = _make_orch_with_recorder(search_mod, ["rutracker", "rutor", "nyaa"])

    metadata = await orch.search(query="debian", trackers=None)

    assert set(recorded) == {"rutracker", "rutor", "nyaa"}
    assert set(metadata.trackers_searched) == {"rutracker", "rutor", "nyaa"}


@pytest.mark.asyncio
async def test_empty_filter_fans_out_to_all(search_mod):
    """trackers=[] is treated as 'all enabled' (back-compat)."""
    orch, recorded = _make_orch_with_recorder(search_mod, ["rutracker", "rutor", "nyaa"])

    metadata = await orch.search(query="debian", trackers=[])

    assert set(recorded) == {"rutracker", "rutor", "nyaa"}


@pytest.mark.asyncio
async def test_filter_is_case_insensitive(search_mod):
    """Filter names are matched case-insensitively against tracker.name."""
    orch, recorded = _make_orch_with_recorder(search_mod, ["rutracker", "rutor"])

    await orch.search(query="debian", trackers=["RuTracker"])

    assert set(recorded) == {"rutracker"}


@pytest.mark.asyncio
async def test_unknown_name_yields_empty_fanout_gracefully(search_mod):
    """An unknown tracker name selects nothing — no crash, zero dispatch."""
    orch, recorded = _make_orch_with_recorder(search_mod, ["rutracker", "rutor"])

    metadata = await orch.search(query="debian", trackers=["does-not-exist"])

    assert recorded == []
    assert metadata.trackers_searched == []
    assert metadata.status == "completed"


@pytest.mark.asyncio
async def test_start_search_seeds_filtered_trackers(search_mod):
    """start_search (the async POST /search entry) seeds tracker_stats for
    only the selected subset, so the immediate response is accurate."""
    orch, _ = _make_orch_with_recorder(search_mod, ["rutracker", "rutor", "nyaa"])

    metadata = orch.start_search(query="debian", trackers=["rutor"])

    assert metadata.trackers_searched == ["rutor"]
    assert set(metadata.tracker_stats.keys()) == {"rutor"}
