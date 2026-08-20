"""SearchRequest field bounds — amplification guard (BOB-074 follow-up).

FORENSIC ANCHOR (measured 2026-08-20). `SearchRequest.query` carried only
`min_length=1` and NO `max_length`, so an arbitrarily large query string was
accepted and forwarded into the 43-tracker fan-out. `category`, `sort_by`,
`sort_order` and `trackers` were unbounded too. That is an amplification
surface: one cheap request costs the service N expensive upstream requests,
each carrying attacker-controlled payload.

Rate limiting alone does NOT close it — a client inside its allowance can
still send a multi-megabyte query, and the per-request cost is what matters
here, not the request rate.

BOUNDS ARE EVIDENCE-BASED, not taste. Measured across the whole repo, the
longest legitimate query in any test or source is 14 characters
("boba-111-probe"); the longest category is "boundary-max-length-url" (23).
There are 43 managed plugins, so a tracker filter never legitimately exceeds
that by much. The limits below leave generous headroom over observed usage
while removing the unbounded tail.

§11.4.201(1): every bound is tested in BOTH directions — an over-limit value
must be REFUSED and a realistic value must still be ACCEPTED. A validator that
rejects legitimate traffic is as broken as one that accepts anything.
"""

from __future__ import annotations

import importlib
import os
import sys

import pytest
from fastapi.testclient import TestClient

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_SRC_PATH = os.path.join(_REPO_ROOT, "download-proxy", "src")
if _SRC_PATH not in sys.path:
    sys.path.insert(0, _SRC_PATH)


@pytest.fixture(autouse=True)
def _no_real_tracker_fanout(monkeypatch):
    """Never let a probe reach real trackers (§12 host safety)."""
    from merge_service.search import SearchOrchestrator

    async def _no_fanout(self, search_id, query, category="all"):  # noqa: ANN001
        meta = self._active_searches.get(search_id)
        if meta is not None:
            meta.status = "completed"

    monkeypatch.setattr(SearchOrchestrator, "_run_search", _no_fanout)


@pytest.fixture()
def client():
    # Generous limits: these tests are about VALIDATION, not rate limiting.
    os.environ["RATE_LIMIT_SEARCH"] = "1000/minute"
    os.environ["RATE_LIMIT_DEFAULT"] = "1000/minute"
    for mod in [m for m in sys.modules if m == "api" or m.startswith("api.")]:
        sys.modules.pop(mod, None)
    api_mod = importlib.import_module("api")
    importlib.import_module("api.rate_limit").reset_counters()
    yield TestClient(api_mod.app, raise_server_exceptions=False)
    for k in ("RATE_LIMIT_SEARCH", "RATE_LIMIT_DEFAULT"):
        os.environ.pop(k, None)


@pytest.mark.security
class TestSearchRequestBounds:
    def test_oversized_query_is_refused(self, client):
        """The amplification vector: a huge query must not reach the fan-out."""
        r = client.post("/api/v1/search", json={"query": "A" * 100_000})
        assert r.status_code == 422, (
            f"a 100,000-character query was accepted (status={r.status_code}) — "
            "it is forwarded to the 43-tracker fan-out, so one cheap request "
            "costs N expensive upstream requests carrying attacker payload"
        )

    def test_realistic_query_still_accepted(self, client):
        """§11.4.201(1) control: the bound must not refuse legitimate traffic."""
        r = client.post("/api/v1/search", json={"query": "interstellar 2014 1080p"})
        assert r.status_code == 200, (
            f"a realistic 23-character query was refused (status={r.status_code}: "
            f"{r.text[:200]}) — the max_length bound is too tight"
        )

    def test_oversized_category_is_refused(self, client):
        r = client.post(
            "/api/v1/search", json={"query": "ok", "category": "C" * 10_000}
        )
        assert r.status_code == 422, "an unbounded category was accepted"

    def test_oversized_sort_fields_are_refused(self, client):
        r = client.post(
            "/api/v1/search", json={"query": "ok", "sort_by": "S" * 10_000}
        )
        assert r.status_code == 422, "an unbounded sort_by was accepted"
        r2 = client.post(
            "/api/v1/search", json={"query": "ok", "sort_order": "O" * 10_000}
        )
        assert r2.status_code == 422, "an unbounded sort_order was accepted"

    def test_oversized_tracker_filter_is_refused(self, client):
        """A huge trackers list multiplies the fan-out selection cost."""
        r = client.post(
            "/api/v1/search", json={"query": "ok", "trackers": ["t"] * 10_000}
        )
        assert r.status_code == 422, "an unbounded trackers list was accepted"

    def test_realistic_tracker_filter_still_accepted(self, client):
        """Control: a normal subset selection must still work."""
        r = client.post(
            "/api/v1/search",
            json={"query": "ok", "trackers": ["rutracker", "kinozal", "nnmclub"]},
        )
        assert r.status_code == 200, (
            f"a 3-tracker filter was refused (status={r.status_code}: "
            f"{r.text[:200]}) — the list bound is too tight"
        )
