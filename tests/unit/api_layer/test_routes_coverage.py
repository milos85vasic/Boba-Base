"""
Additional coverage for api/routes.py — exercises uncovered branches:
429 queue-full, 404 not-found, abort flow, download/file/magnet endpoints,
size/quality helpers, qbittorrent auth, active-downloads error handling.

These are unit tests: the orchestrator and aiohttp are mocked so no real
tracker/network access happens. Assertions inspect response bodies and
state deltas (anti-bluff), not just status codes.
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SRC_PATH = _REPO_ROOT / "download-proxy" / "src"
if str(_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(_SRC_PATH))


def _purge_api_module() -> None:
    for key in [k for k in list(sys.modules) if k == "api" or k.startswith("api.")]:
        del sys.modules[key]


def _make_orch(**overrides):
    """A MagicMock orchestrator with the attributes the routes touch."""
    orch = MagicMock()
    orch._max_concurrent_searches = 8
    orch.is_search_queue_full.return_value = False
    orch._active_searches = {}
    orch._last_merged_results = {}
    orch._search_tasks = {}
    for k, v in overrides.items():
        setattr(orch, k, v)
    return orch


@pytest.fixture
def client_factory(tmp_path, monkeypatch):
    """Returns a callable that builds a TestClient with a given orchestrator
    installed at api.orchestrator_instance and hooks writing to tmp."""
    created = []

    def _build(orch):
        _purge_api_module()
        import api
        import api.hooks

        monkeypatch.setattr(api.hooks, "HOOKS_FILE", str(tmp_path / "hooks.json"))
        api.orchestrator_instance = orch
        c = TestClient(api.app)
        created.append(c)
        return c

    return _build


# ---------------------------------------------------------------------------
# Pure helpers — no app needed.
# ---------------------------------------------------------------------------


class TestSizeAndQualityHelpers:
    def test_parse_size_empty(self):
        _purge_api_module()
        from api.routes import _parse_size_to_bytes

        assert _parse_size_to_bytes("") == 0

    def test_parse_size_numeric_string(self):
        from api.routes import _parse_size_to_bytes

        assert _parse_size_to_bytes("1024") == 1024.0

    def test_parse_size_gb(self):
        from api.routes import _parse_size_to_bytes

        assert _parse_size_to_bytes("4.0 GB") == 4.0 * 1024**3

    def test_parse_size_unparseable(self):
        from api.routes import _parse_size_to_bytes

        assert _parse_size_to_bytes("not a size") == 0

    def test_detect_quality_by_size_uhd(self):
        from api.routes import _detect_quality

        # No quality token in name -> falls back to size buckets.
        assert _detect_quality("randomname", str(50 * 1024**3)) == "uhd_4k"

    def test_detect_quality_by_size_sd(self):
        from api.routes import _detect_quality

        assert _detect_quality("randomname", str(400 * 1024**2)) == "sd"

    def test_detect_quality_unknown(self):
        from api.routes import _detect_quality

        assert _detect_quality("randomname", "10") == "unknown"


class TestTrackerUrlDetection:
    def test_rutracker(self):
        _purge_api_module()
        from api.routes import _is_tracker_url

        assert _is_tracker_url("https://rutracker.org/forum/viewtopic.php?t=1") == "rutracker"

    def test_kinozal_subdomain(self):
        from api.routes import _is_tracker_url

        assert _is_tracker_url("https://dl.kinozal.tv/download.php?id=9") == "kinozal"

    def test_nnmclub(self):
        from api.routes import _is_tracker_url

        assert _is_tracker_url("https://nnmclub.to/forum/x") == "nnmclub"

    def test_iptorrents(self):
        from api.routes import _is_tracker_url

        assert _is_tracker_url("https://iptorrents.com/t/1") == "iptorrents"

    def test_non_tracker(self):
        from api.routes import _is_tracker_url

        assert _is_tracker_url("https://example.com/file.torrent") is None

    def test_malformed_url(self):
        from api.routes import _is_tracker_url

        assert _is_tracker_url("::::not a url") is None


# ---------------------------------------------------------------------------
# /search and /search/sync — queue-full 429.
# ---------------------------------------------------------------------------


class TestSearchQueueFull:
    def test_search_429_when_full(self, client_factory):
        orch = _make_orch()
        orch.is_search_queue_full.return_value = True
        c = client_factory(orch)
        resp = c.post("/api/v1/search", json={"query": "ubuntu"})
        assert resp.status_code == 429
        assert "MAX_CONCURRENT_SEARCHES" in resp.json()["detail"]

    def test_search_sync_429_when_full(self, client_factory):
        orch = _make_orch()
        orch.is_search_queue_full.return_value = True
        c = client_factory(orch)
        resp = c.post("/api/v1/search/sync", json={"query": "ubuntu"})
        assert resp.status_code == 429
        assert "MAX_CONCURRENT_SEARCHES" in resp.json()["detail"]

    def test_search_running_response(self, client_factory):
        """POST /search returns running + a stream token without fanning out."""
        orch = _make_orch()
        meta = MagicMock()
        meta.search_id = "sid-123"
        meta.query = "ubuntu"
        meta.trackers_searched = ["rutracker"]
        meta.total_results = 0
        meta.merged_results = 0
        meta.to_dict.return_value = {"tracker_stats": []}
        from datetime import datetime

        meta.started_at = datetime(2026, 1, 1)
        orch.start_search.return_value = meta
        # _run_search awaited in background -> make it a no-op coroutine.
        orch._run_search = AsyncMock(return_value=None)
        orch.issue_stream_token.return_value = "tok-abc"
        c = client_factory(orch)
        resp = c.post("/api/v1/search", json={"query": "ubuntu"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "running"
        assert body["search_id"] == "sid-123"
        assert body["stream_token"] == "tok-abc"
        orch.start_search.assert_called_once()


# ---------------------------------------------------------------------------
# /search/{id}, /search/stream/{id}, /search/{id}/abort.
# ---------------------------------------------------------------------------


class TestGetSearch:
    def test_get_search_404(self, client_factory):
        orch = _make_orch()
        orch.get_search_status.return_value = None
        c = client_factory(orch)
        resp = c.get("/api/v1/search/unknown-id")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Search not found"

    def test_get_search_found_no_results(self, client_factory):
        orch = _make_orch()
        meta = MagicMock()
        meta.search_id = "sid"
        meta.query = "q"
        meta.status = "completed"
        meta.total_results = 0
        meta.merged_results = 0
        meta.trackers_searched = []
        meta.errors = []
        meta.to_dict.return_value = {"tracker_stats": []}
        from datetime import datetime

        meta.started_at = datetime(2026, 1, 1)
        meta.completed_at = datetime(2026, 1, 1)
        orch.get_search_status.return_value = meta
        orch._last_merged_results = {}
        c = client_factory(orch)
        resp = c.get("/api/v1/search/sid")
        assert resp.status_code == 200
        body = resp.json()
        assert body["search_id"] == "sid"
        assert body["status"] == "completed"
        assert body["results"] == []


class TestSearchStream:
    def test_stream_404_correct_route(self, client_factory):
        orch = _make_orch()
        orch._active_searches = {}
        c = client_factory(orch)
        resp = c.get("/api/v1/search/stream/nope")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Search not found"

    def test_stream_403_when_token_required(self, client_factory, monkeypatch):
        orch = _make_orch()
        orch._active_searches = {"sid": MagicMock()}
        orch.validate_stream_token.return_value = False
        monkeypatch.setenv("SSE_REQUIRE_TOKEN", "1")
        c = client_factory(orch)
        resp = c.get("/api/v1/search/stream/sid")
        assert resp.status_code == 403
        assert "stream token" in resp.json()["detail"]


class TestAbortSearch:
    def test_abort_active(self, client_factory):
        orch = _make_orch()
        orch._active_searches = {"sid": MagicMock()}
        orch.cancel_search.return_value = True
        c = client_factory(orch)
        resp = c.post("/api/v1/search/sid/abort")
        assert resp.status_code == 200
        assert resp.json() == {"search_id": "sid", "status": "aborted"}
        orch.cancel_search.assert_called_once_with("sid")

    def test_abort_not_found(self, client_factory):
        orch = _make_orch()
        orch._active_searches = {}
        c = client_factory(orch)
        resp = c.post("/api/v1/search/ghost/abort")
        assert resp.status_code == 200
        assert resp.json() == {"search_id": "ghost", "status": "not_found"}


# ---------------------------------------------------------------------------
# /downloads/active — auth failure & unavailable paths.
# ---------------------------------------------------------------------------


def _aiohttp_response(text="", status=200, json_data=None):
    resp = AsyncMock()
    resp.text = AsyncMock(return_value=text)
    resp.status = status
    if json_data is not None:
        resp.json = AsyncMock(return_value=json_data)
    resp.cookies = {}
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


class TestActiveDownloads:
    def test_auth_failed(self, client_factory):
        orch = _make_orch()
        c = client_factory(orch)
        login = _aiohttp_response(text="Fails.", status=403)
        session = AsyncMock()
        session.post = MagicMock(return_value=login)
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        with patch("aiohttp.ClientSession", return_value=session):
            resp = c.get("/api/v1/downloads/active")
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 0
        assert body["error"] == "auth failed"

    def test_success_with_torrents(self, client_factory):
        orch = _make_orch()
        c = client_factory(orch)
        login = _aiohttp_response(text="Ok.", status=200)
        info = _aiohttp_response(
            status=200,
            json_data=[
                {"name": "t1", "size": 100, "progress": 0.5, "dlspeed": 10, "upspeed": 1, "state": "downloading",
                 "hash": "abc", "eta": 60}
            ],
        )
        session = AsyncMock()
        session.post = MagicMock(return_value=login)
        session.get = MagicMock(return_value=info)
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        with patch("aiohttp.ClientSession", return_value=session):
            resp = c.get("/api/v1/downloads/active")
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 1
        assert body["downloads"][0]["name"] == "t1"
        assert body["downloads"][0]["progress"] == 50.0

    def test_unavailable_on_exception(self, client_factory):
        orch = _make_orch()
        c = client_factory(orch)
        with patch("aiohttp.ClientSession", side_effect=Exception("boom")):
            resp = c.get("/api/v1/downloads/active")
        assert resp.status_code == 200
        body = resp.json()
        assert body["error"] == "unavailable"


# ---------------------------------------------------------------------------
# /auth/qbittorrent.
# ---------------------------------------------------------------------------


class TestAuthQbittorrent:
    def test_authenticated(self, client_factory):
        orch = _make_orch()
        c = client_factory(orch)
        login = _aiohttp_response(text="Ok.", status=200)
        version = _aiohttp_response(text="4.6.0", status=200)
        session = AsyncMock()
        session.post = MagicMock(return_value=login)
        session.get = MagicMock(return_value=version)
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        with patch("aiohttp.ClientSession", return_value=session):
            resp = c.post("/api/v1/auth/qbittorrent", json={"username": "admin", "password": "admin"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "authenticated"
        assert body["version"] == "4.6.0"

    def test_invalid_credentials(self, client_factory):
        orch = _make_orch()
        c = client_factory(orch)
        login = _aiohttp_response(text="Fails.", status=200)
        session = AsyncMock()
        session.post = MagicMock(return_value=login)
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        with patch("aiohttp.ClientSession", return_value=session):
            resp = c.post("/api/v1/auth/qbittorrent", json={"username": "x", "password": "y"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "failed"
        assert body["error"] == "Invalid credentials"

    def test_error_on_exception(self, client_factory):
        orch = _make_orch()
        c = client_factory(orch)
        with patch("aiohttp.ClientSession", side_effect=Exception("down")):
            resp = c.post("/api/v1/auth/qbittorrent", json={})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "error"
        assert "down" in body["error"]


# ---------------------------------------------------------------------------
# /download — auth failure, tracker fetch failure, magnet/direct add.
# ---------------------------------------------------------------------------


class TestInitiateDownload:
    def test_auth_failed(self, client_factory):
        orch = _make_orch()
        c = client_factory(orch)
        login = _aiohttp_response(text="Fails.", status=403)
        session = AsyncMock()
        session.post = MagicMock(return_value=login)
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        with patch("aiohttp.ClientSession", return_value=session):
            resp = c.post(
                "/api/v1/download",
                json={"result_id": "r1", "download_urls": ["https://example.com/x.torrent"]},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "auth_failed"

    def test_connection_failed(self, client_factory):
        orch = _make_orch()
        c = client_factory(orch)
        with patch("aiohttp.ClientSession", side_effect=Exception("net")):
            resp = c.post(
                "/api/v1/download",
                json={"result_id": "r1", "download_urls": ["https://example.com/x.torrent"]},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "connection_failed"
        assert "net" in body["error"]

    def test_tracker_fetch_returns_none(self, client_factory):
        """Tracker URL but orchestrator can't fetch the torrent -> per-url failed."""
        orch = _make_orch()
        orch.fetch_torrent = AsyncMock(return_value=None)
        c = client_factory(orch)
        login = _aiohttp_response(text="Ok.", status=200)
        session = AsyncMock()
        session.post = MagicMock(return_value=login)
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        with patch("aiohttp.ClientSession", return_value=session):
            resp = c.post(
                "/api/v1/download",
                json={"result_id": "r1", "download_urls": ["https://rutracker.org/forum/dl.php?t=1"]},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "failed"
        assert body["added_count"] == 0
        assert body["results"][0]["status"] == "failed"
        assert "could not fetch" in body["results"][0]["detail"]

    def test_direct_url_added(self, client_factory):
        """Non-tracker URL added via qBittorrent /torrents/add -> added_count 1."""
        orch = _make_orch()
        c = client_factory(orch)
        login = _aiohttp_response(text="Ok.", status=200)
        add = _aiohttp_response(text="Ok.", status=200)
        session = AsyncMock()
        # First .post is login, subsequent .post is the add — return both via side_effect.
        session.post = MagicMock(side_effect=[login, add])
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        with patch("aiohttp.ClientSession", return_value=session):
            resp = c.post(
                "/api/v1/download",
                json={"result_id": "r1", "download_urls": ["https://example.com/file.torrent"]},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "initiated"
        assert body["added_count"] == 1
        assert body["results"][0]["status"] == "added"


# ---------------------------------------------------------------------------
# /download/file.
# ---------------------------------------------------------------------------


class TestDownloadFile:
    def test_magnet_returns_text(self, client_factory):
        orch = _make_orch()
        c = client_factory(orch)
        resp = c.post(
            "/api/v1/download/file",
            json={"result_id": "r1", "download_urls": ["magnet:?xt=urn:btih:abc"]},
        )
        assert resp.status_code == 200
        assert resp.text == "magnet:?xt=urn:btih:abc"
        assert ".magnet" in resp.headers["content-disposition"]

    def test_tracker_torrent_stream(self, client_factory):
        orch = _make_orch()
        orch.fetch_torrent = AsyncMock(return_value=b"d8:announce")
        c = client_factory(orch)
        resp = c.post(
            "/api/v1/download/file",
            json={"result_id": "r1", "download_urls": ["https://rutracker.org/forum/dl.php?t=1"]},
        )
        assert resp.status_code == 200
        assert resp.content == b"d8:announce"
        assert resp.headers["content-type"] == "application/x-bittorrent"

    def test_no_downloadable_404(self, client_factory):
        orch = _make_orch()
        orch.fetch_torrent = AsyncMock(return_value=None)
        c = client_factory(orch)
        # tracker URL but fetch returns None, and no other url types -> 404
        resp = c.post(
            "/api/v1/download/file",
            json={"result_id": "r1", "download_urls": ["https://rutracker.org/forum/dl.php?t=2"]},
        )
        assert resp.status_code == 404
        assert "No downloadable" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# /magnet.
# ---------------------------------------------------------------------------


class TestGenerateMagnet:
    def test_from_btih(self, client_factory):
        orch = _make_orch()
        c = client_factory(orch)
        h = "a" * 40
        resp = c.post(
            "/api/v1/magnet",
            json={"result_id": "My Movie", "download_urls": [f"https://x/y?btih:{h}"]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert h in body["hashes"]
        assert body["magnet"].startswith("magnet:?dn=")
        assert f"xt=urn:btih:{h}" in body["magnet"]
        # default public trackers folded in
        assert "tracker.opentrackr.org" in body["magnet"]

    def test_magnet_link_trackers_merged(self, client_factory):
        orch = _make_orch()
        c = client_factory(orch)
        magnet_in = "magnet:?xt=urn:btih:" + ("b" * 40) + "&tr=udp%3A%2F%2Fcustom%3A80"
        resp = c.post(
            "/api/v1/magnet",
            json={"result_id": "x", "download_urls": [magnet_in]},
        )
        assert resp.status_code == 200
        body = resp.json()
        # The custom tracker from the magnet is unquoted then re-quoted into tr=.
        import urllib.parse

        assert "tr=" + urllib.parse.quote("udp://custom:80") in body["magnet"]

    def test_invalid_request_body(self, client_factory):
        orch = _make_orch()
        c = client_factory(orch)
        # Missing required result_id field -> handler returns 400 JSON.
        resp = c.post("/api/v1/magnet", json={"download_urls": []})
        assert resp.status_code == 400
        assert resp.json()["error"] == "Invalid request"


# ---------------------------------------------------------------------------
# qbit credential helpers (saved-file path).
# ---------------------------------------------------------------------------


class TestQbitCredentialHelpers:
    def test_username_from_saved(self):
        _purge_api_module()
        import api.routes as routes

        with patch.object(routes, "_load_saved_qbit_credentials", return_value={"username": "saved", "password": "p"}):
            assert routes._get_qbit_username() == "saved"
            assert routes._get_qbit_password() == "p"

    def test_username_env_fallback(self, monkeypatch):
        _purge_api_module()
        import api.routes as routes

        monkeypatch.setenv("QBITTORRENT_USER", "envuser")
        monkeypatch.setenv("QBITTORRENT_PASS", "envpass")
        with patch.object(routes, "_load_saved_qbit_credentials", return_value=None):
            assert routes._get_qbit_username() == "envuser"
            assert routes._get_qbit_password() == "envpass"
