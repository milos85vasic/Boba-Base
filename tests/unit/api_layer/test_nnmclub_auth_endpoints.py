"""BOB-006: NNMClub auth endpoints (status + password login).

Mirrors the existing /rutracker/status + /rutracker/login endpoint tests.
Endpoints are mounted under /api/v1/auth (see api/__init__.py).

RED-first (CONST §11.4.43): fails against pre-BOB-006 code (no
/nnmclub/status, no /nnmclub/login endpoints exist).

Mocks used ONLY here in unit tests (CONST §11.4.27).
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SRC_PATH = _REPO_ROOT / "download-proxy" / "src"
if str(_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(_SRC_PATH))


def _purge_api_module() -> None:
    for key in [k for k in list(sys.modules) if k == "api" or k.startswith("api.")]:
        del sys.modules[key]


@pytest.fixture
def client():
    _purge_api_module()
    import api
    from merge_service.search import SearchOrchestrator

    # Pin a single orchestrator so the endpoint under test and the test's
    # assertions share the same _tracker_sessions store (lifespan does not
    # run for a plain TestClient, leaving orchestrator_instance None which
    # would make _get_orchestrator() return a fresh instance each call).
    api.orchestrator_instance = SearchOrchestrator()
    return TestClient(api.app)


# --- /nnmclub/status -----------------------------------------------------


class TestNnmclubStatus:
    def test_status_no_session(self, client):
        import api

        orch = api.auth._get_orchestrator()
        orch._tracker_sessions._cache.clear()

        resp = client.get("/api/v1/auth/nnmclub/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["authenticated"] is False
        assert body["status"] == "no_session"
        assert "message" in body

    def test_status_no_cookie(self, client):
        import api

        orch = api.auth._get_orchestrator()
        orch._tracker_sessions["nnmclub"] = {
            "cookies": {"unrelated": "x"},
            "base_url": "https://nnm-club.me",
        }

        resp = client.get("/api/v1/auth/nnmclub/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["authenticated"] is False
        assert body["status"] == "no_cookie"


# --- /nnmclub/login ------------------------------------------------------


class _FakeCookie:
    def __init__(self, key, value):
        self.key = key
        self.value = value


class _FakeResp:
    def __init__(self, cookies):
        self.cookies = {k: _FakeCookie(k, v) for k, v in cookies.items()}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class _FakeSession:
    def __init__(self, cookies):
        self._cookies = cookies

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def post(self, *a, **k):
        return _FakeResp(self._cookies)


class TestNnmclubLogin:
    def test_login_requires_credentials(self, client, monkeypatch):
        for k in ("NNMCLUB_USERNAME", "NNMCLUB_PASSWORD"):
            monkeypatch.delenv(k, raising=False)

        resp = client.post("/api/v1/auth/nnmclub/login")
        assert resp.status_code == 400

    def test_login_success_stores_session(self, client, monkeypatch):
        import api

        monkeypatch.setenv("NNMCLUB_USERNAME", "alice")
        monkeypatch.setenv("NNMCLUB_PASSWORD", "s3cret")

        orch = api.auth._get_orchestrator()
        orch._tracker_sessions._cache.clear()

        fake = _FakeSession({"phpbb2mysql_4_sid": "SID999"})
        with patch("aiohttp.ClientSession", return_value=fake):
            resp = client.post("/api/v1/auth/nnmclub/login")

        assert resp.status_code == 200
        body = resp.json()
        assert body["authenticated"] is True
        # user-observable side effect: session cookie persisted
        session = orch._tracker_sessions.get("nnmclub")
        assert session["cookies"].get("phpbb2mysql_4_sid") == "SID999"

    def test_login_failure_no_session_cookie(self, client, monkeypatch):
        import api

        monkeypatch.setenv("NNMCLUB_USERNAME", "alice")
        monkeypatch.setenv("NNMCLUB_PASSWORD", "wrong")

        orch = api.auth._get_orchestrator()
        orch._tracker_sessions._cache.clear()

        fake = _FakeSession({"unrelated": "x"})
        with patch("aiohttp.ClientSession", return_value=fake):
            resp = client.post("/api/v1/auth/nnmclub/login")

        assert resp.status_code == 401
        # no bogus session stored
        assert orch._tracker_sessions.get("nnmclub") is None

    def test_login_does_not_leak_credentials(self, client, monkeypatch):
        monkeypatch.setenv("NNMCLUB_USERNAME", "alice")
        monkeypatch.setenv("NNMCLUB_PASSWORD", "s3cret")

        fake = _FakeSession({"phpbb2mysql_4_sid": "SID999"})
        with patch("aiohttp.ClientSession", return_value=fake):
            resp = client.post("/api/v1/auth/nnmclub/login")

        assert "s3cret" not in resp.text
        assert "alice" not in resp.text
