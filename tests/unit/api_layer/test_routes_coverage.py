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


# ---------------------------------------------------------------------------
# _get_orchestrator fallback path (when global instance is None).
# ---------------------------------------------------------------------------


class TestGetOrchestratorFallback:
    def test_creates_search_orchestrator_when_none(self):
        _purge_api_module()
        import api
        import api.routes as routes
        from fastapi import Request

        api.orchestrator_instance = None
        req = MagicMock(spec=Request)
        orch = routes._get_orchestrator(req)
        from merge_service.search import SearchOrchestrator

        assert isinstance(orch, SearchOrchestrator)


# ---------------------------------------------------------------------------
# _detect_quality — full branch coverage.
# ---------------------------------------------------------------------------


class TestDetectQualityFull:
    def test_bluray_maps_to_full_hd(self):
        _purge_api_module()
        from api.routes import _detect_quality

        assert _detect_quality("Movie 2023 BluRay x264", "15 GB") == "full_hd"

    def test_bdrip_maps_to_full_hd(self):
        from api.routes import _detect_quality

        assert _detect_quality("Movie 2023 BDRip x264", "15 GB") == "full_hd"

    def test_bdremux_maps_to_uhd_4k(self):
        from api.routes import _detect_quality

        assert _detect_quality("Movie 2023 BDRemux 2160p", "50 GB") == "uhd_4k"

    def test_webdl_maps_to_hd(self):
        from api.routes import _detect_quality

        assert _detect_quality("Movie 2023 WEB-DL", "8 GB") == "hd"

    def test_webrip_maps_to_hd(self):
        from api.routes import _detect_quality

        assert _detect_quality("Movie 2023 WEBRip", "4 GB") == "hd"

    def test_hdrip_maps_to_hd(self):
        from api.routes import _detect_quality

        assert _detect_quality("Movie 2023 HDRip", "4 GB") == "hd"

    def test_hdtv_maps_to_hd(self):
        from api.routes import _detect_quality

        assert _detect_quality("Show S01E01 HDTV x264", "2 GB") == "hd"

    def test_dvd_maps_to_sd(self):
        from api.routes import _detect_quality

        assert _detect_quality("Movie DVD 1999", "1 GB") == "sd"

    def test_dvdrip_maps_to_sd(self):
        from api.routes import _detect_quality

        assert _detect_quality("Movie DVDRip 1999", "700 MB") == "sd"

    def test_size_based_full_hd_between_8gb_and_40gb(self):
        from api.routes import _detect_quality

        assert _detect_quality("random name", str(10 * 1024**3)) == "full_hd"

    def test_size_based_hd_between_2gb_and_8gb(self):
        from api.routes import _detect_quality

        assert _detect_quality("random name", str(4 * 1024**3)) == "hd"


# ---------------------------------------------------------------------------
# _to_response quality fallback.
# ---------------------------------------------------------------------------


class TestToResponseQualityFallback:
    def test_detects_quality_when_missing(self):
        _purge_api_module()
        from api.routes import _to_response
        from merge_service.search import SearchResult

        r = SearchResult(name="random", link="http://x", size="4 GB", seeds=1, leechers=0, engine_url="", quality=None)
        resp = _to_response(r)
        assert resp.quality == "hd"

    def test_detects_quality_when_empty(self):
        from api.routes import _to_response
        from merge_service.search import SearchResult

        r = SearchResult(name="random", link="http://x", size="4 GB", seeds=1, leechers=0, engine_url="", quality="")
        resp = _to_response(r)
        assert resp.quality == "hd"


# ---------------------------------------------------------------------------
# /search/sync — blocking search with results, sorting, CAPTCHA.
# ---------------------------------------------------------------------------


class TestSearchSync:
    @pytest.fixture
    def orch_with_results(self):
        from merge_service.search import SearchResult, MergedResult, CanonicalIdentity, ContentType

        results = [
            SearchResult(name="Alpha", link="http://a/1", size="4 GB", seeds=10, leechers=1, engine_url="",
                         tracker="a", quality="hd"),
            SearchResult(name="Beta", link="http://b/1", size="2 GB", seeds=5, leechers=0, engine_url="",
                         tracker="b", quality="sd"),
        ]
        merged = []
        for r in results:
            ci = CanonicalIdentity(title=r.name, content_type=ContentType.MOVIE)
            m = MergedResult(canonical_identity=ci)
            m.add_source(r)
            merged.append(m)
        orch = _make_orch()
        orch._last_merged_results = {"sid": (merged, results)}
        meta = MagicMock()
        meta.search_id = "sid"
        meta.query = "test"
        meta.total_results = 2
        meta.merged_results = 2
        meta.trackers_searched = ["a", "b"]
        meta.errors = []
        meta.status = "completed"
        from datetime import datetime

        meta.started_at = datetime(2026, 1, 1)
        meta.completed_at = datetime(2026, 1, 1)
        meta.to_dict.return_value = {"tracker_stats": []}
        orch.search = AsyncMock(return_value=meta)
        return orch

    def test_sync_search_with_results(self, client_factory, orch_with_results):
        c = client_factory(orch_with_results)
        resp = c.post("/api/v1/search/sync", json={"query": "test"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"
        assert len(body["results"]) == 2

    def test_sync_search_sort_by_name_asc(self, client_factory, orch_with_results):
        c = client_factory(orch_with_results)
        resp = c.post("/api/v1/search/sync", json={"query": "test", "sort_by": "name", "sort_order": "asc"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["results"][0]["name"] == "Alpha"

    def test_sync_search_sort_by_size(self, client_factory, orch_with_results):
        c = client_factory(orch_with_results)
        resp = c.post("/api/v1/search/sync", json={"query": "test", "sort_by": "size"})
        assert resp.status_code == 200
        body = resp.json()
        names = [r["name"] for r in body["results"]]
        assert names == ["Alpha", "Beta"]

    def test_sync_search_no_results(self, client_factory):
        orch = _make_orch()
        orch._last_merged_results = {}
        meta = MagicMock()
        meta.search_id = "sid"
        meta.query = "test"
        meta.total_results = 0
        meta.merged_results = 0
        meta.trackers_searched = []
        meta.errors = []
        from datetime import datetime

        meta.started_at = datetime(2026, 1, 1)
        meta.completed_at = datetime(2026, 1, 1)
        meta.to_dict.return_value = {"tracker_stats": []}
        orch.search = AsyncMock(return_value=meta)
        c = client_factory(orch)
        resp = c.post("/api/v1/search/sync", json={"query": "test"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "no_results"

    def test_sync_search_captcha_required(self, client_factory):
        orch = _make_orch()
        orch._last_merged_results = {}
        meta = MagicMock()
        meta.search_id = "sid"
        meta.query = "test"
        meta.total_results = 0
        meta.merged_results = 0
        meta.trackers_searched = []
        meta.errors = ["CAPTCHA required for rutracker"]
        from datetime import datetime

        meta.started_at = datetime(2026, 1, 1)
        meta.completed_at = datetime(2026, 1, 1)
        meta.to_dict.return_value = {"tracker_stats": []}
        orch.search = AsyncMock(return_value=meta)
        c = client_factory(orch)
        resp = c.post("/api/v1/search/sync", json={"query": "test"})
        assert resp.status_code == 403
        assert resp.json()["status"] == "captcha_required"

    def test_sync_search_sort_by_type(self, client_factory, orch_with_results):
        c = client_factory(orch_with_results)
        resp = c.post("/api/v1/search/sync", json={"query": "test", "sort_by": "type"})
        assert resp.status_code == 200
        assert len(resp.json()["results"]) == 2

    def test_sync_search_sort_by_leechers(self, client_factory, orch_with_results):
        c = client_factory(orch_with_results)
        resp = c.post("/api/v1/search/sync", json={"query": "test", "sort_by": "leechers"})
        assert resp.status_code == 200
        assert len(resp.json()["results"]) == 2

    def test_sync_search_sort_by_quality(self, client_factory, orch_with_results):
        c = client_factory(orch_with_results)
        resp = c.post("/api/v1/search/sync", json={"query": "test", "sort_by": "quality"})
        assert resp.status_code == 200
        assert len(resp.json()["results"]) == 2

    def test_sync_search_sort_by_sources(self, client_factory, orch_with_results):
        c = client_factory(orch_with_results)
        resp = c.post("/api/v1/search/sync", json={"query": "test", "sort_by": "sources"})
        assert resp.status_code == 200
        assert len(resp.json()["results"]) == 2

    def test_sync_search_with_metadata_enrichment(self, client_factory, orch_with_results):
        orch = orch_with_results
        orch._last_merged_results = {}
        meta = MagicMock()
        meta.search_id = "sid"
        meta.query = "test"
        meta.total_results = 2
        meta.merged_results = 2
        meta.trackers_searched = ["a", "b"]
        meta.errors = []
        from datetime import datetime

        meta.started_at = datetime(2026, 1, 1)
        meta.completed_at = datetime(2026, 1, 1)
        meta.to_dict.return_value = {"tracker_stats": []}
        orch.search = AsyncMock(return_value=meta)
        c = client_factory(orch)
        enricher = AsyncMock()
        enricher.resolve.return_value = None
        c.app.state.enricher = enricher
        resp = c.post("/api/v1/search/sync", json={"query": "test", "enable_metadata": True})
        assert resp.status_code == 200
        # Metadata enrichment shouldn't crash even though there are no stored results
        assert resp.json()["status"] == "completed"


# ---------------------------------------------------------------------------
# SSE stream cap 429.
# ---------------------------------------------------------------------------


class TestSseStreamCap:
    def test_429_when_streams_full(self, client_factory):
        orch = _make_orch()
        orch._active_searches = {"sid": MagicMock()}
        c = client_factory(orch)
        import api.routes as routes

        with patch.object(routes, "_sse_stream_count", 999):
            resp = c.get("/api/v1/search/stream/sid")
            assert resp.status_code == 429
            assert "SSE streams" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# /search/{id} with merged results.
# ---------------------------------------------------------------------------


class TestGetSearchWithResults:
    def test_get_search_with_merged(self, client_factory):
        from merge_service.search import SearchResult, MergedResult, CanonicalIdentity, ContentType

        sr = SearchResult(name="Movie A", link="http://x/a", size="4 GB", seeds=10, leechers=1, engine_url="",
                          tracker="x", quality="hd")
        ci = CanonicalIdentity(title="Movie A", content_type=ContentType.MOVIE)
        merged = MergedResult(canonical_identity=ci)
        merged.add_source(sr)
        orch = _make_orch()
        orch._last_merged_results = {"sid": ([merged], [sr])}
        meta = MagicMock()
        meta.search_id = "sid"
        meta.query = "q"
        meta.status = "completed"
        meta.total_results = 1
        meta.merged_results = 1
        meta.trackers_searched = ["x"]
        meta.errors = []
        meta.to_dict.return_value = {"tracker_stats": []}
        from datetime import datetime

        meta.started_at = datetime(2026, 1, 1)
        meta.completed_at = datetime(2026, 1, 1)
        orch.get_search_status = MagicMock(return_value=meta)
        c = client_factory(orch)
        resp = c.get("/api/v1/search/sid")
        assert resp.status_code == 200
        body = resp.json()
        assert body["search_id"] == "sid"
        assert len(body["results"]) == 1
        assert body["results"][0]["name"] == "Movie A"
        assert body["results"][0]["sources"][0]["tracker"] == "x"


# ---------------------------------------------------------------------------
# /auth/qbittorrent — bad JSON + save credentials.
# ---------------------------------------------------------------------------


class TestAuthQbittorrentEdgeCases:
    def test_bad_json_falls_back_to_defaults(self, client_factory):
        orch = _make_orch()
        c = client_factory(orch)
        login = _aiohttp_response(text="Fails.", status=200)
        session = AsyncMock()
        session.post = MagicMock(return_value=login)
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        with patch("aiohttp.ClientSession", return_value=session):
            resp = c.post(
                "/api/v1/auth/qbittorrent",
                content=b"not json at all",
                headers={"Content-Type": "text/plain"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "failed"

    def test_login_saves_credentials(self, client_factory, tmp_path):
        orch = _make_orch()
        c = client_factory(orch)
        login = _aiohttp_response(text="Ok.", status=200)
        version = _aiohttp_response(text="4.6.0", status=200)
        session = AsyncMock()
        session.post = MagicMock(return_value=login)
        session.get = MagicMock(return_value=version)
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        creds_dir = str(tmp_path / "creds")
        with (
            patch("aiohttp.ClientSession", return_value=session),
            patch("api.routes._save_qbit_credentials") as mock_save,
        ):
            resp = c.post("/api/v1/auth/qbittorrent", json={"username": "admin", "password": "admin", "save": True})
        assert resp.status_code == 200
        assert resp.json()["status"] == "authenticated"
        mock_save.assert_called_once()
        args = mock_save.call_args[0]
        assert args[1]["username"] == "admin"
        assert args[1]["password"] == "admin"


# ---------------------------------------------------------------------------
# _save_qbit_credentials — exception handling.
# ---------------------------------------------------------------------------


class TestSaveQbitCredentials:
    def test_exception_logged(self, caplog):
        _purge_api_module()
        import api.routes as routes
        import logging

        caplog.set_level(logging.ERROR)
        with patch("builtins.open") as m:
            m.side_effect = PermissionError("denied")
            routes._save_qbit_credentials("/nonexistent/creds.json", {"u": "p"})
        assert "Failed to save qBittorrent credentials" in caplog.text

    def test_load_returns_none_when_no_file(self):
        _purge_api_module()
        import api.routes as routes

        with patch("os.path.isfile", return_value=False):
            assert routes._load_saved_qbit_credentials() is None


# ---------------------------------------------------------------------------
# /download — tracker path (temp file, upload), non-tracker failure, per-URL exception.
# ---------------------------------------------------------------------------


class TestInitiateDownloadTrackerPath:
    def test_tracker_success(self, client_factory):
        orch = _make_orch()
        orch.fetch_torrent = AsyncMock(return_value=b"d8:announce42e")
        c = client_factory(orch)
        login = _aiohttp_response(text="Ok.", status=200)
        add = _aiohttp_response(text="Ok.", status=200)
        session = AsyncMock()
        session.post = MagicMock(side_effect=[login, add])
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        with patch("aiohttp.ClientSession", return_value=session):
            resp = c.post(
                "/api/v1/download",
                json={"result_id": "r1", "download_urls": ["https://rutracker.org/forum/dl.php?t=1"]},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "initiated"
        assert body["added_count"] == 1
        assert body["results"][0]["status"] == "added"

    def test_tracker_upload_fails(self, client_factory):
        orch = _make_orch()
        orch.fetch_torrent = AsyncMock(return_value=b"d8:announce42e")
        c = client_factory(orch)
        login = _aiohttp_response(text="Ok.", status=200)
        add = _aiohttp_response(text="Fails.", status=200)
        session = AsyncMock()
        session.post = MagicMock(side_effect=[login, add])
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
        assert body["results"][0]["status"] == "failed"

    def test_non_tracker_fail(self, client_factory):
        orch = _make_orch()
        c = client_factory(orch)
        login = _aiohttp_response(text="Ok.", status=200)
        add = _aiohttp_response(text="Fails.", status=200)
        session = AsyncMock()
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
        assert body["status"] == "failed"
        assert body["results"][0]["status"] == "failed"

    def test_per_url_exception(self, client_factory):
        orch = _make_orch()
        c = client_factory(orch)
        login = _aiohttp_response(text="Ok.", status=200)
        session = AsyncMock()
        session.post = MagicMock(return_value=login)
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        with (
            patch("aiohttp.ClientSession", return_value=session),
            patch("api.routes._is_tracker_url", side_effect=ValueError("boom")),
        ):
            resp = c.post(
                "/api/v1/download",
                json={"result_id": "r1", "download_urls": ["https://example.com/x"]},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "failed"
        assert body["results"][0]["status"] == "error"


# ---------------------------------------------------------------------------
# /download/file — direct URL path.
# ---------------------------------------------------------------------------


class TestDownloadFileDirectUrl:
    def test_non_tracker_non_magnet_direct_url(self, client_factory):
        orch = _make_orch()
        c = client_factory(orch)
        data_resp = _aiohttp_response(status=200)
        data_resp.read = AsyncMock(return_value=b"torrent data")
        session = AsyncMock()
        session.get = MagicMock(return_value=data_resp)
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        with patch("aiohttp.ClientSession", return_value=session):
            resp = c.post(
                "/api/v1/download/file",
                json={"result_id": "r1", "download_urls": ["https://example.com/file.torrent"]},
            )
        assert resp.status_code == 200
        assert resp.content == b"torrent data"
        assert resp.headers["content-type"] == "application/x-bittorrent"

    def test_direct_url_not_200_falls_through(self, client_factory):
        orch = _make_orch()
        c = client_factory(orch)
        data_resp = _aiohttp_response(status=404)
        session = AsyncMock()
        session.get = MagicMock(return_value=data_resp)
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        with patch("aiohttp.ClientSession", return_value=session):
            resp = c.post(
                "/api/v1/download/file",
                json={"result_id": "r1", "download_urls": ["https://example.com/file.torrent"]},
            )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# /magnet — multi-hash extraction.
# ---------------------------------------------------------------------------


class TestGenerateMagnetMultiHash:
    def test_multiple_btih_hashes(self, client_factory):
        orch = _make_orch()
        c = client_factory(orch)
        h1 = "a" * 40
        h2 = "b" * 40
        resp = c.post(
            "/api/v1/magnet",
            json={
                "result_id": "multi",
                "download_urls": [
                    f"https://x/y?btih:{h1}",
                    f"https://x/y?btih:{h2}",
                ],
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["hashes"]) == 2
        assert h1 in body["hashes"]
        assert h2 in body["hashes"]
        assert body["magnet"].count("xt=urn:btih:") == 2
        assert "tracker.opentrackr.org" in body["magnet"]

    def test_magnet_with_existing_trackers(self, client_factory):
        orch = _make_orch()
        c = client_factory(orch)
        h = "c" * 40
        resp = c.post(
            "/api/v1/magnet",
            json={
                "result_id": "with_tr",
                "download_urls": [
                    f"magnet:?xt=urn:btih:{h}&tr=udp%3A%2F%2Fcustom%3A80&tr=udp%3A%2F%2Fother%3A81"
                ],
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["hashes"]) == 1
        assert "tr=" in body["magnet"]
        assert "tracker.opentrackr.org" in body["magnet"]
