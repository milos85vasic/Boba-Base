"""Tests for per-tracker search stats (TrackerSearchStat).

Stats are populated synchronously at search start and mutated in place
as each tracker transitions pending → running → success/empty/error.
The SSE streamer diffs ``metadata.tracker_stats`` between polls to emit
``tracker_started`` / ``tracker_completed`` events, so these tests pin
the observable transitions.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from datetime import datetime

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


def _fake_trackers(search_mod, names):
    return [search_mod.TrackerSource(name=n, url=f"https://{n}.example", enabled=True) for n in names]


def test_tracker_stat_dataclass_defaults(search_mod):
    stat = search_mod.TrackerSearchStat(name="rutracker")
    assert stat.name == "rutracker"
    assert stat.status == "pending"
    assert stat.results_count == 0
    assert stat.started_at is None
    assert stat.completed_at is None
    assert stat.duration_ms is None
    assert stat.error is None
    assert stat.error_type is None
    assert stat.authenticated is False
    assert stat.credentials_configured is False
    assert stat.attempt == 1
    assert stat.http_status is None
    assert stat.category == "all"
    assert stat.query == ""
    assert stat.notes == {}


def test_tracker_stat_starts_pending(search_mod, monkeypatch):
    orch = search_mod.SearchOrchestrator()
    names = ["alpha", "beta"]
    orch._get_enabled_trackers = lambda: _fake_trackers(search_mod, names)

    metadata = orch.start_search(query="q", category="all")

    assert set(metadata.tracker_stats.keys()) == set(names)
    for name in names:
        stat = metadata.tracker_stats[name]
        assert stat.status == "pending"
        assert stat.results_count == 0
        assert stat.started_at is None
        assert stat.completed_at is None
        assert stat.query == "q"
        assert stat.category == "all"


@pytest.mark.asyncio
async def test_tracker_stat_transitions_to_success_when_results_returned(search_mod):
    orch = search_mod.SearchOrchestrator()
    orch._get_enabled_trackers = lambda: _fake_trackers(search_mod, ["alpha"])

    async def fake_search_tracker(tracker, query, category):
        return [
            search_mod.SearchResult(name="a", link="m1", size="1 MB", seeds=1, leechers=0, engine_url="u"),
            search_mod.SearchResult(name="b", link="m2", size="2 MB", seeds=2, leechers=0, engine_url="u"),
            search_mod.SearchResult(name="c", link="m3", size="3 MB", seeds=3, leechers=0, engine_url="u"),
        ]

    orch._search_tracker = fake_search_tracker
    metadata = await orch.search(query="q", enable_metadata=False, validate_trackers=False)
    stat = metadata.tracker_stats["alpha"]
    assert stat.status == "success"
    assert stat.results_count == 3
    assert stat.duration_ms is not None and stat.duration_ms >= 0
    assert stat.started_at is not None
    assert stat.completed_at is not None
    assert stat.error is None


@pytest.mark.asyncio
async def test_tracker_stat_transitions_to_empty_when_no_results(search_mod):
    orch = search_mod.SearchOrchestrator()
    orch._get_enabled_trackers = lambda: _fake_trackers(search_mod, ["alpha"])

    async def fake_search_tracker(tracker, query, category):
        return []

    orch._search_tracker = fake_search_tracker
    metadata = await orch.search(query="q", enable_metadata=False, validate_trackers=False)
    stat = metadata.tracker_stats["alpha"]
    assert stat.status == "empty"
    assert stat.results_count == 0
    assert stat.duration_ms is not None and stat.duration_ms >= 0


@pytest.mark.asyncio
async def test_tracker_stat_transitions_to_error_on_exception(search_mod):
    orch = search_mod.SearchOrchestrator()
    orch._get_enabled_trackers = lambda: _fake_trackers(search_mod, ["alpha"])

    async def fake_search_tracker(tracker, query, category):
        raise RuntimeError("boom")

    orch._search_tracker = fake_search_tracker
    metadata = await orch.search(query="q", enable_metadata=False, validate_trackers=False)
    stat = metadata.tracker_stats["alpha"]
    assert stat.status == "error"
    assert stat.error == "boom"
    assert stat.error_type == "RuntimeError"


@pytest.mark.asyncio
async def test_tracker_stat_transitions_to_timeout(search_mod):
    orch = search_mod.SearchOrchestrator()
    orch._get_enabled_trackers = lambda: _fake_trackers(search_mod, ["alpha"])

    async def fake_search_tracker(tracker, query, category):
        raise TimeoutError("too slow")

    orch._search_tracker = fake_search_tracker
    metadata = await orch.search(query="q", enable_metadata=False, validate_trackers=False)
    stat = metadata.tracker_stats["alpha"]
    assert stat.status == "timeout"
    assert stat.error_type == "TimeoutError"


def test_tracker_stat_records_authentication_flag(search_mod, monkeypatch):
    monkeypatch.setenv("RUTRACKER_USERNAME", "u")
    monkeypatch.setenv("RUTRACKER_PASSWORD", "p")
    monkeypatch.delenv("KINOZAL_USERNAME", raising=False)
    monkeypatch.delenv("KINOZAL_PASSWORD", raising=False)
    monkeypatch.delenv("NNMCLUB_COOKIES", raising=False)
    monkeypatch.delenv("IPTORRENTS_USERNAME", raising=False)
    monkeypatch.delenv("IPTORRENTS_PASSWORD", raising=False)

    orch = search_mod.SearchOrchestrator()
    orch._get_enabled_trackers = lambda: _fake_trackers(search_mod, ["rutracker", "piratebay"])

    metadata = orch.start_search(query="q", category="all")
    # BOB-173: credentials being configured is NOT authentication. This stat is
    # seeded before any login round-trip, so no session exists yet and the
    # honest chip is credentials_configured=True / authenticated=False.
    assert metadata.tracker_stats["rutracker"].credentials_configured is True
    assert metadata.tracker_stats["rutracker"].authenticated is False
    assert metadata.tracker_stats["piratebay"].authenticated is False
    assert metadata.tracker_stats["piratebay"].credentials_configured is False


def test_tracker_stat_serialises_to_isoformat(search_mod):
    stat = search_mod.TrackerSearchStat(name="alpha")
    stat.started_at = datetime(2026, 4, 19, 12, 0, 0)
    stat.completed_at = datetime(2026, 4, 19, 12, 0, 1)
    d = stat.to_dict()
    assert d["started_at"].startswith("2026-04-19T12:00:00")
    assert d["completed_at"].startswith("2026-04-19T12:00:01")
    # Round-trip back to datetime should succeed.
    datetime.fromisoformat(d["started_at"])
    datetime.fromisoformat(d["completed_at"])


def test_tracker_stat_serialises_none_timestamps(search_mod):
    stat = search_mod.TrackerSearchStat(name="alpha")
    d = stat.to_dict()
    assert d["started_at"] is None
    assert d["completed_at"] is None


def test_search_metadata_to_dict_includes_sorted_tracker_stats(search_mod):
    orch = search_mod.SearchOrchestrator()
    orch._get_enabled_trackers = lambda: _fake_trackers(search_mod, ["zeta", "alpha", "mike"])
    metadata = orch.start_search(query="q", category="all")
    stats = metadata.to_dict()["tracker_stats"]
    names = [s["name"] for s in stats]
    assert names == sorted(names)
    assert names == ["alpha", "mike", "zeta"]
    # All 16 fields are present on each stat dict.
    expected_fields = {
        "name",
        "tracker_url",
        "status",
        "results_count",
        "started_at",
        "completed_at",
        "duration_ms",
        "error",
        "error_type",
        "authenticated",
        "credentials_configured",
        "attempt",
        "http_status",
        "category",
        "query",
        "notes",
    }
    for s in stats:
        assert set(s.keys()) == expected_fields


@pytest.mark.asyncio
async def test_tracker_stats_survive_exception_and_still_complete(search_mod):
    """If one tracker fails the others should still register a stat."""
    orch = search_mod.SearchOrchestrator()
    orch._get_enabled_trackers = lambda: _fake_trackers(search_mod, ["good", "bad"])

    async def fake_search_tracker(tracker, query, category):
        if tracker.name == "bad":
            raise ValueError("nope")
        return [
            search_mod.SearchResult(name="r", link="m", size="1 MB", seeds=1, leechers=0, engine_url="u"),
        ]

    orch._search_tracker = fake_search_tracker
    metadata = await orch.search(query="q", enable_metadata=False, validate_trackers=False)
    assert metadata.tracker_stats["good"].status == "success"
    assert metadata.tracker_stats["good"].results_count == 1
    assert metadata.tracker_stats["bad"].status == "error"
    assert metadata.tracker_stats["bad"].error_type == "ValueError"


def test_has_tracker_session_returns_true_when_session_present(search_mod, monkeypatch):
    """BOB-173: a stored session — and only that — proves authentication."""
    monkeypatch.delenv("IPTORRENTS_USERNAME", raising=False)
    monkeypatch.delenv("IPTORRENTS_PASSWORD", raising=False)
    orch = search_mod.SearchOrchestrator()
    assert orch._has_tracker_session("iptorrents") is False
    orch._tracker_sessions["iptorrents"] = {"cookies": {"x": "y"}}
    assert orch._has_tracker_session("iptorrents") is True
