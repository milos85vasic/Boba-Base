"""Unit test pinning the shape of the ``tracker_stats`` field on SearchResponse.

Asserts both /api/v1/search/sync (blocking) and /api/v1/search/{id}
(follow-up GET) expose tracker_stats as a list of dicts whose shape
matches the 15-field TrackerSearchStat.to_dict() contract.

This is a UNIT-level test: it monkeypatches
``SearchOrchestrator._get_enabled_trackers`` /
``SearchOrchestrator._search_tracker`` so the shape can be pinned
cheaply and deterministically, with no real tracker network traffic.
Per CLAUDE.md / constitution §11.4.27 ("No fakes beyond unit tests"),
mocking orchestrator internals is permitted ONLY here, in
``tests/unit/`` — this file used to live at
``tests/contract/test_tracker_stats_contract.py`` under that same
mocked implementation, which mislabelled it as a "contract" test even
though it never exercised the real system. The real contract test —
a live HTTP call against a real running merge-search service, with
no mocking of SearchOrchestrator anywhere — now lives at
``tests/contract/test_tracker_stats_contract.py``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_SRC = Path(__file__).resolve().parents[2] / "download-proxy" / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


REQUIRED_FIELDS = {
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
    "attempt",
    "http_status",
    "category",
    "query",
    "notes",
}


@pytest.fixture
def client(monkeypatch):
    os.environ.setdefault("ALLOWED_ORIGINS", "http://localhost")
    monkeypatch.delenv("RUTRACKER_USERNAME", raising=False)
    monkeypatch.delenv("RUTRACKER_PASSWORD", raising=False)
    monkeypatch.delenv("KINOZAL_USERNAME", raising=False)
    monkeypatch.delenv("KINOZAL_PASSWORD", raising=False)
    monkeypatch.delenv("NNMCLUB_COOKIES", raising=False)
    monkeypatch.delenv("IPTORRENTS_USERNAME", raising=False)
    monkeypatch.delenv("IPTORRENTS_PASSWORD", raising=False)
    # BOB-126-followup: the real `/api/v1/search` handler carries the
    # BOB-111 `@_rl("search")` slowapi decorator, whose post-call header
    # injection (`Limiter._inject_headers`) raises
    # ``Exception: parameter `response` must be an instance of
    # starlette.responses.Response`` because the handler's signature has
    # no `response: Response` param for FastAPI to inject one into (a
    # pre-existing slowapi/starlette compatibility defect, tracked
    # separately — see docs/qa / Task 7 warnings audit). This file only
    # pins the ``tracker_stats`` response SHAPE, nothing about rate
    # limiting, so disable it before the app is (re)built — matching the
    # proven bypass pattern from BOB-122 (d7da1af).
    monkeypatch.setenv("RATE_LIMIT_DISABLED", "1")

    # Cleanly drop any cached api.* modules so we rebuild the app fresh.
    for k in [k for k in list(sys.modules) if k == "api" or k.startswith("api.")]:
        del sys.modules[k]
    from api import app

    # Patch the orchestrator class methods to short-circuit network
    # traffic.  Two public trackers, no real HTTP.
    from merge_service.search import SearchOrchestrator, SearchResult, TrackerSource

    def _fake_trackers(self):
        return [
            TrackerSource(name="alpha", url="https://alpha.example", enabled=True),
            TrackerSource(name="beta", url="https://beta.example", enabled=True),
        ]

    async def _fake_search_tracker(self, tracker, query, category):
        return [
            SearchResult(
                name=f"{tracker.name}-1",
                link="magnet:?xt=urn:btih:" + "a" * 40,
                size="1 MB",
                seeds=1,
                leechers=0,
                engine_url=tracker.url,
                tracker=tracker.name,
            )
        ]

    monkeypatch.setattr(SearchOrchestrator, "_get_enabled_trackers", _fake_trackers)
    monkeypatch.setattr(SearchOrchestrator, "_search_tracker", _fake_search_tracker)

    with TestClient(app) as c:
        yield c


def test_search_sync_returns_tracker_stats_with_required_fields(client):
    resp = client.post("/api/v1/search/sync", json={"query": "ubuntu", "limit": 5})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "tracker_stats" in body
    stats = body["tracker_stats"]
    assert isinstance(stats, list)
    assert len(stats) == 2
    for s in stats:
        assert isinstance(s, dict)
        assert set(s.keys()) == REQUIRED_FIELDS
        assert s["name"] in {"alpha", "beta"}
        assert s["status"] in {"pending", "running", "success", "empty", "error", "timeout", "cancelled"}


def test_get_search_echoes_same_shape(client):
    resp = client.post("/api/v1/search/sync", json={"query": "ubuntu", "limit": 5})
    body = resp.json()
    sid = body["search_id"]

    followup = client.get(f"/api/v1/search/{sid}")
    assert followup.status_code == 200, followup.text
    fbody = followup.json()
    assert "tracker_stats" in fbody
    fstats = fbody["tracker_stats"]
    assert isinstance(fstats, list)
    for s in fstats:
        assert set(s.keys()) == REQUIRED_FIELDS


def test_search_kickoff_returns_pending_tracker_stats(client):
    """The non-blocking POST /search returns immediately — stats will
    all be ``pending`` or ``running`` depending on how much of the
    background task has executed by the time the response serialises.
    The contract only pins shape + that every expected tracker shows
    up."""
    resp = client.post("/api/v1/search", json={"query": "ubuntu", "limit": 5})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "tracker_stats" in body
    names = {s["name"] for s in body["tracker_stats"]}
    assert names == {"alpha", "beta"}
