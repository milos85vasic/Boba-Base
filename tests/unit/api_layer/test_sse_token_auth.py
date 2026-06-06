"""
Per-search SSE stream token (CONTINUATION #6 / Phase 3).

Beyond the UUID barrier, each search issues a single-use bearer token; the
stream endpoint can be hardened to require it (env SSE_REQUIRE_TOKEN). The
token is accepted via ``?token=`` (EventSource can't set headers) or an
``Authorization: Bearer`` header. Enforcement is opt-in so the shipped
dashboard keeps working, but the mechanism is fully built and tested.

§11.4.43 RED-first: against pre-fix code SearchResponse has no
``stream_token`` field, the orchestrator has no issue/validate methods, and
the stream endpoint ignores tokens — so the assertions below FAIL. After
the fix they GREEN.

§1.1 paired mutation: make validate_stream_token always return True →
test_stream_rejected_without_token (enforcement on) FAILs.
"""

import os
import sys

import pytest
from fastapi.testclient import TestClient

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_SRC_PATH = os.path.join(_REPO_ROOT, "download-proxy", "src")
if _SRC_PATH not in sys.path:
    sys.path.insert(0, _SRC_PATH)


def _purge_api() -> None:
    for key in [k for k in list(sys.modules) if k == "api" or k.startswith("api.")]:
        del sys.modules[key]


@pytest.fixture
def env(monkeypatch):
    """Provide (api_module, client, orch) with a freshly-injected orchestrator."""
    _purge_api()
    import api
    import merge_service.search as ms

    orch = ms.SearchOrchestrator()
    monkeypatch.setattr(api, "orchestrator_instance", orch)
    client = TestClient(api.app)
    yield api, client, orch
    _purge_api()


def _new_search(orch, *, completed=False):
    meta = orch.start_search(query="ubuntu", category="all", validate_trackers=False)
    if completed:
        # A completed search makes the SSE stream finite (emit search_start +
        # search_complete then close) so TestClient.stream doesn't hang on a
        # forever-"running" search.
        meta.status = "completed"
    token = orch.issue_stream_token(meta.search_id)
    return meta.search_id, token


class TestTokenIssuance:
    def test_orchestrator_issues_and_validates(self, env):
        _api, _client, orch = env
        sid, token = _new_search(orch)
        assert isinstance(token, str) and len(token) >= 16
        assert orch.validate_stream_token(sid, token) is True
        assert orch.validate_stream_token(sid, "wrong") is False
        assert orch.validate_stream_token(sid, None) is False
        assert orch.validate_stream_token("unknown-sid", token) is False

    def test_search_response_model_has_stream_token(self):
        _purge_api()
        from api.routes import SearchResponse

        fields = SearchResponse.model_fields
        assert "stream_token" in fields


class TestEnforcementOn:
    @pytest.fixture(autouse=True)
    def _require(self, monkeypatch):
        monkeypatch.setenv("SSE_REQUIRE_TOKEN", "1")

    def test_stream_rejected_without_token(self, env):
        _api, client, orch = env
        sid, _token = _new_search(orch)
        resp = client.get(f"/api/v1/search/stream/{sid}")
        assert resp.status_code == 403

    def test_stream_rejected_with_wrong_token(self, env):
        _api, client, orch = env
        sid, _token = _new_search(orch)
        resp = client.get(f"/api/v1/search/stream/{sid}?token=nope")
        assert resp.status_code == 403

    def test_stream_allowed_with_query_token(self, env):
        _api, client, orch = env
        sid, token = _new_search(orch, completed=True)
        with client.stream("GET", f"/api/v1/search/stream/{sid}?token={token}") as r:
            assert r.status_code == 200

    def test_stream_allowed_with_bearer_header(self, env):
        _api, client, orch = env
        sid, token = _new_search(orch, completed=True)
        with client.stream(
            "GET",
            f"/api/v1/search/stream/{sid}",
            headers={"Authorization": f"Bearer {token}"},
        ) as r:
            assert r.status_code == 200

    def test_unknown_search_is_404_not_403(self, env):
        _api, client, _orch = env
        resp = client.get("/api/v1/search/stream/does-not-exist?token=x")
        assert resp.status_code == 404


class TestEnforcementOff:
    def test_stream_allowed_without_token_when_disabled(self, env, monkeypatch):
        monkeypatch.delenv("SSE_REQUIRE_TOKEN", raising=False)
        _api, client, orch = env
        sid, _token = _new_search(orch, completed=True)
        with client.stream("GET", f"/api/v1/search/stream/{sid}") as r:
            assert r.status_code == 200
