import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "download-proxy", "src"))

# Work around pytest importlib mode creating namespace package for 'api'
if "api" in sys.modules and not getattr(sys.modules.get("api"), "__file__", None):
    del sys.modules["api"]

from fastapi.testclient import TestClient

from api import app

client = TestClient(app)


def _aiohttp_response(text="", status=200):
    """Fake aiohttp response usable as an async context manager.

    Mirrors the established session-mock helper in
    tests/unit/api_layer/test_routes_coverage.py so the qBittorrent auth
    endpoint can be exercised without any real network connection.
    """
    resp = AsyncMock()
    resp.text = AsyncMock(return_value=text)
    resp.status = status
    resp.cookies = {}
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


class TestDashboardEndpoint:
    def test_root_returns_html(self):
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    def test_dashboard_returns_html(self):
        response = client.get("/dashboard")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    def test_dashboard_is_angular_app(self):
        response = client.get("/dashboard")
        html = response.text
        assert "<app-root>" in html
        assert "</app-root>" in html
        assert "ng-version=" in html or "main-" in html


class TestConfigEndpoint:
    def test_config_returns_qbittorrent_url(self):
        response = client.get("/api/v1/config")
        assert response.status_code == 200
        data = response.json()
        assert "qbittorrent_url" in data
        assert "qbittorrent_host" in data
        assert data["qbittorrent_port"] == 7185

    def test_config_qbittorrent_url_points_at_proxy(self):
        """qBittorrent WebUI link must go through the authenticated proxy.

        The in-container WebUI (port 7185) answers 401 without the proxy
        shim, so the dashboard link must target the proxy port instead.
        """
        response = client.get("/api/v1/config")
        assert response.status_code == 200
        data = response.json()
        # The proxy port defaults to 7186 and is what the browser should hit.
        assert str(data.get("proxy_port", "")).endswith("7186")
        assert "7186" in data["qbittorrent_url"]
        # Internal URL is still exposed for tooling.
        assert "qbittorrent_internal_url" in data
        assert "7185" in data["qbittorrent_internal_url"]


class TestHealthEndpoint:
    def test_health_check(self):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"


class TestBridgeHealthEndpoint:
    def test_bridge_health_endpoint_exists(self):
        """GET /api/v1/bridge/health always returns 200 with {healthy: bool}.

        The probe itself talks to 127.0.0.1:<BRIDGE_PORT> with a 2s
        timeout, so the endpoint never raises — it just reports
        ``healthy: false`` when the host bridge is down.
        """
        response = client.get("/api/v1/bridge/health")
        assert response.status_code == 200
        data = response.json()
        assert "healthy" in data
        assert isinstance(data["healthy"], bool)
        assert "bridge_url" in data

    def test_bridge_health_reports_down_when_unreachable(self, monkeypatch):
        """If the bridge URL is misconfigured to a dead port, healthy=False."""
        monkeypatch.setenv("BRIDGE_URL", "http://127.0.0.1:1")
        response = client.get("/api/v1/bridge/health")
        assert response.status_code == 200
        data = response.json()
        assert data["healthy"] is False


class TestStatsEndpoint:
    def test_stats_endpoint(self):
        response = client.get("/api/v1/stats")
        assert response.status_code == 200


class TestQBitAuthEndpoint:
    def test_qbittorrent_auth_endpoint_exists(self):
        # Mock aiohttp.ClientSession so the endpoint makes NO real network
        # connection to qBittorrent (localhost:7185). The handler does a
        # login POST followed by a version GET; the fake session returns a
        # successful login + version so we assert on user-observable output.
        login = _aiohttp_response(text="Ok.", status=200)
        version = _aiohttp_response(text="4.6.0", status=200)
        session = AsyncMock()
        session.post = MagicMock(return_value=login)
        session.get = MagicMock(return_value=version)
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        with patch("aiohttp.ClientSession", return_value=session):
            response = client.post("/api/v1/auth/qbittorrent", json={"username": "admin", "password": "admin"})
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] == "authenticated"
        assert data["version"] == "4.6.0"

    def test_qbittorrent_login_modal_in_angular(self):
        response = client.get("/dashboard")
        html = response.text
        assert "<app-root>" in html
        assert "</app-root>" in html

    def test_angular_scripts_loaded(self):
        response = client.get("/dashboard")
        html = response.text
        assert '<script src="main-' in html or 'src="main-' in html
        assert "</body>" in html
