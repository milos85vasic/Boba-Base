"""
Integration tests for the merge service API endpoints.
Uses FastAPI TestClient with mocked SearchOrchestrator.
"""

import os
import sys
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_SRC_PATH = os.path.join(_REPO_ROOT, "download-proxy", "src")
sys.path.insert(0, _SRC_PATH)

# Previously this file ``del``'d every ``merge_service.*`` module from
# ``sys.modules`` at import time. That wiped out the module objects
# referenced by OTHER test files' module-level ``from merge_service
# import ...`` captures — notably ``tests/e2e/test_full_pipeline.py``
# — and produced "coroutine was never awaited" / KeyError cascades in
# pytest-asyncio teardown. We now merely ensure the module is
# importable + point __path__ at the download-proxy source tree.
import merge_service as _ms

_ms_path = os.path.join(_SRC_PATH, "merge_service")
if _ms_path not in _ms.__path__:
    _ms.__path__.insert(0, _ms_path)

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _create_test_client():
    app = FastAPI()

    @app.get("/health")
    async def health_check():
        return {"status": "healthy", "service": "merge-search", "version": "1.0.0"}

    from api.hooks import router as hooks_router
    from api.routes import router as api_router

    app.include_router(api_router, prefix="/api/v1")
    app.include_router(hooks_router, prefix="/api/v1/hooks")
    return TestClient(app)


@pytest.fixture
def client():
    return _create_test_client()


@pytest.fixture(autouse=True)
def _reset_hooks_state(tmp_path, monkeypatch):
    hooks_file = str(tmp_path / "hooks.json")
    monkeypatch.setattr("api.hooks.HOOKS_FILE", hooks_file)
    # RW-01 (§11.4.120 reconciliation): hook script_path is now restricted to an
    # allowlisted dir. Point BOBA_HOOKS_DIR at a real tmp dir so the hook-create
    # tests can register scripts that live INSIDE the allowlist.
    hooks_dir = tmp_path / "hooks"
    hooks_dir.mkdir()
    monkeypatch.setenv("BOBA_HOOKS_DIR", str(hooks_dir))
    return


@pytest.fixture
def allowed_script(tmp_path):
    """Create a script inside the BOBA_HOOKS_DIR allowlist and return its path."""

    def _make(name="hook.sh"):
        p = tmp_path / "hooks" / name
        p.write_text("#!/bin/sh\necho ok\n")
        p.chmod(0o755)
        return str(p)

    return _make


class TestHealthEndpoint:
    def test_health_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["service"] == "merge-search"
        assert "version" in data


class TestSearchEndpoint:
    @patch("api.routes._get_orchestrator")
    def test_search_with_valid_query(self, mock_get_orch, client):
        orch = MagicMock()
        orch.is_search_queue_full.return_value = False
        meta = MagicMock()
        meta.search_id = "test-search-123"
        meta.query = "interstellar"
        meta.total_results = 5
        meta.trackers_searched = ["rutracker", "kinozal"]
        meta.started_at = datetime(2025, 1, 1, 12, 0, 0)
        meta.completed_at = datetime(2025, 1, 1, 12, 0, 5)
        orch.search = AsyncMock(return_value=meta)
        orch._search_tracker = AsyncMock(return_value=[])
        orch.deduplicator = MagicMock()
        orch.deduplicator.merge_results.return_value = []
        mock_get_orch.return_value = orch

        with patch.dict(
            "sys.modules",
            {"merge_service.search": MagicMock(TrackerSource=MagicMock())},
        ):
            resp = client.post("/api/v1/search/sync", json={"query": "interstellar"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["query"] == "interstellar"
        assert data["search_id"] == "test-search-123"
        assert "results" in data
        assert "trackers_searched" in data

    def test_search_with_empty_query_returns_422(self, client):
        resp = client.post("/api/v1/search/sync", json={"query": ""})
        assert resp.status_code == 422

    def test_search_with_missing_body_returns_422(self, client):
        resp = client.post("/api/v1/search/sync")
        assert resp.status_code == 422

    @patch("api.routes._get_orchestrator")
    def test_search_with_defaults(self, mock_get_orch, client):
        orch = MagicMock()
        orch.is_search_queue_full.return_value = False
        meta = MagicMock()
        meta.search_id = "abc"
        meta.query = "test"
        meta.total_results = 0
        meta.trackers_searched = []
        meta.started_at = datetime(2025, 1, 1)
        meta.completed_at = datetime(2025, 1, 1)
        orch.search = AsyncMock(return_value=meta)
        orch._search_tracker = AsyncMock(return_value=[])
        orch.deduplicator = MagicMock()
        orch.deduplicator.merge_results.return_value = []
        mock_get_orch.return_value = orch

        with patch.dict(
            "sys.modules",
            {"merge_service.search": MagicMock(TrackerSource=MagicMock())},
        ):
            resp = client.post("/api/v1/search/sync", json={"query": "test"})

        assert resp.status_code == 200


class TestSearchByIdEndpoint:
    @patch("api.routes._get_orchestrator")
    def test_get_unknown_search_returns_404(self, mock_get_orch, client):
        orch = MagicMock()
        orch.is_search_queue_full.return_value = False
        orch.get_search_status.return_value = None
        orch._last_merged_results = {}
        mock_get_orch.return_value = orch

        resp = client.get("/api/v1/search/nonexistent-id")
        assert resp.status_code == 404

    @patch("api.routes._get_orchestrator")
    def test_get_existing_search_returns_200(self, mock_get_orch, client):
        orch = MagicMock()
        orch.is_search_queue_full.return_value = False
        meta = MagicMock()
        meta.search_id = "known-id"
        meta.query = "ubuntu"
        meta.status = "completed"
        meta.total_results = 3
        meta.merged_results = 2
        meta.trackers_searched = ["rutracker"]
        meta.started_at = datetime(2025, 1, 1, 12, 0, 0)
        meta.completed_at = datetime(2025, 1, 1, 12, 0, 5)
        orch.get_search_status.return_value = meta
        orch._last_merged_results = {}
        mock_get_orch.return_value = orch

        resp = client.get("/api/v1/search/known-id")
        assert resp.status_code == 200
        data = resp.json()
        assert data["search_id"] == "known-id"
        assert data["status"] == "completed"


class TestHooksEndpoint:
    def test_list_hooks_empty(self, client):
        resp = client.get("/api/v1/hooks")
        assert resp.status_code == 200
        data = resp.json()
        assert data["hooks"] == []
        assert data["count"] == 0

    def test_create_hook_returns_hook_id(self, client, allowed_script):
        hook_data = {
            "name": "test-hook",
            "event": "search_complete",
            "script_path": allowed_script("test.sh"),
            "enabled": True,
        }
        resp = client.post("/api/v1/hooks", json=hook_data)
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "test-hook"
        assert data["event"] == "search_complete"
        assert "hook_id" in data

    def test_create_hook_any_event_accepted(self, client):
        hook_data = {
            "name": "custom-hook",
            "event": "custom_event",
            "script_path": "/tmp/custom.sh",
        }
        resp = client.post("/api/v1/hooks", json=hook_data)
        assert resp.status_code == 400

    def test_list_hooks_after_create(self, client, allowed_script):
        hook_data = {
            "name": "my-hook",
            "event": "download_complete",
            "script_path": allowed_script("dl.sh"),
        }
        client.post("/api/v1/hooks", json=hook_data)
        resp = client.get("/api/v1/hooks")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["hooks"][0]["name"] == "my-hook"

    def test_delete_hook(self, client, allowed_script):
        hook_data = {
            "name": "to-delete",
            "event": "search_complete",
            "script_path": allowed_script("del.sh"),
        }
        create_resp = client.post("/api/v1/hooks", json=hook_data)
        hook_id = create_resp.json()["hook_id"]

        resp = client.delete(f"/api/v1/hooks/{hook_id}")
        assert resp.status_code == 200
        assert resp.json()["hook_id"] == hook_id

        list_resp = client.get("/api/v1/hooks")
        assert list_resp.json()["count"] == 0

    def test_delete_nonexistent_hook_returns_404(self, client):
        resp = client.delete("/api/v1/hooks/no-such-hook")
        assert resp.status_code == 404

    def test_create_hook_missing_name_returns_422(self, client):
        resp = client.post(
            "/api/v1/hooks",
            json={"event": "search_complete", "script_path": "/tmp/a.sh"},
        )
        assert resp.status_code == 422

    def test_create_hook_returns_created_at(self, client, allowed_script):
        hook_data = {
            "name": "dated-hook",
            "event": "merge_complete",
            "script_path": allowed_script("merge.sh"),
        }
        resp = client.post("/api/v1/hooks", json=hook_data)
        assert resp.status_code == 200
        data = resp.json()
        assert "created_at" in data
        assert data["enabled"] is True

    def test_hook_lifecycle_create_list_delete(self, client, allowed_script):
        hooks_to_create = [
            {"name": "hook-a", "event": "search_start", "script_path": allowed_script("a.sh")},
            {"name": "hook-b", "event": "download_start", "script_path": allowed_script("b.sh")},
        ]
        created_ids = []
        for h in hooks_to_create:
            r = client.post("/api/v1/hooks", json=h)
            assert r.status_code == 200
            created_ids.append(r.json()["hook_id"])

        list_resp = client.get("/api/v1/hooks")
        assert list_resp.json()["count"] == 2

        for hid in created_ids:
            del_resp = client.delete(f"/api/v1/hooks/{hid}")
            assert del_resp.status_code == 200

        assert client.get("/api/v1/hooks").json()["count"] == 0


class TestAbortSearchEndpoint:
    @patch("api.routes._get_orchestrator")
    def test_abort_existing_search(self, mock_get_orch, client):
        orch = MagicMock()
        orch.is_search_queue_full.return_value = False
        search_obj = MagicMock(status="running")
        orch._active_searches = {"search-123": search_obj}
        mock_get_orch.return_value = orch

        def _cancel(sid):
            if sid in orch._active_searches:
                orch._active_searches[sid].status = "aborted"

        orch.cancel_search = _cancel

        resp = client.post("/api/v1/search/search-123/abort")
        assert resp.status_code == 200
        data = resp.json()
        assert data["search_id"] == "search-123"
        assert data["status"] == "aborted"
        assert orch._active_searches["search-123"].status == "aborted"

    @patch("api.routes._get_orchestrator")
    def test_abort_unknown_search(self, mock_get_orch, client):
        orch = MagicMock()
        orch.is_search_queue_full.return_value = False
        orch._active_searches = {}
        mock_get_orch.return_value = orch

        resp = client.post("/api/v1/search/nonexistent/abort")
        assert resp.status_code == 200
        data = resp.json()
        assert data["search_id"] == "nonexistent"
        assert data["status"] == "not_found"


class TestMagnetEndpoint:
    def test_generate_magnet_with_hash(self, client):
        resp = client.post(
            "/api/v1/magnet",
            json={
                "result_id": "Test Movie",
                "download_urls": ["magnet:?xt=urn:btih:abc123def4567890abc123def4567890"],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "magnet" in data
        assert "abc123def4567890abc123def4567890" in data["magnet"]
        assert data["hashes"] == ["abc123def4567890abc123def4567890"]

    def test_generate_magnet_without_hash(self, client):
        resp = client.post(
            "/api/v1/magnet",
            json={
                "result_id": "Test Movie",
                "download_urls": ["https://example.com/file.torrent"],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "magnet" in data
        assert data["hashes"] == []

    def test_generate_magnet_invalid_request(self, client):
        # httpx 0.27+ deprecated `data=<str>` for raw body — use `content=`.
        resp = client.post("/api/v1/magnet", content="not-json")
        assert resp.status_code == 400


class TestDownloadEndpoint:
    @patch("api.routes._get_orchestrator")
    @patch("api.routes.aiohttp.ClientSession")
    def test_download_auth_failed_403(self, mock_session_cls, mock_get_orch, client):
        orch = MagicMock()
        orch.is_search_queue_full.return_value = False
        mock_get_orch.return_value = orch

        mock_session = MagicMock()
        mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_resp = MagicMock()
        mock_resp.status = 403
        mock_resp.text = AsyncMock(return_value="Forbidden")
        mock_session.post.return_value.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_session.post.return_value.__aexit__ = AsyncMock(return_value=False)

        resp = client.post(
            "/api/v1/download",
            json={"result_id": "test-1", "download_urls": ["https://example.com/file.torrent"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "auth_failed"

    @patch("api.routes._get_orchestrator")
    @patch("api.routes.aiohttp.ClientSession")
    def test_download_auth_failed_200_body_fails(self, mock_session_cls, mock_get_orch, client):
        """qBittorrent returns HTTP 200 with body 'Fails.' on bad credentials."""
        orch = MagicMock()
        orch.is_search_queue_full.return_value = False
        mock_get_orch.return_value = orch

        mock_session = MagicMock()
        mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.text = AsyncMock(return_value="Fails.")
        mock_session.post.return_value.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_session.post.return_value.__aexit__ = AsyncMock(return_value=False)

        resp = client.post(
            "/api/v1/download",
            json={"result_id": "test-1", "download_urls": ["https://example.com/file.torrent"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "auth_failed"

    @patch("api.routes._get_orchestrator")
    @patch("api.routes.aiohttp.ClientSession")
    def test_download_empty_urls(self, mock_session_cls, mock_get_orch, client):
        """Download with empty URLs should return failed status, not crash."""
        orch = MagicMock()
        orch.is_search_queue_full.return_value = False
        mock_get_orch.return_value = orch

        mock_session = MagicMock()
        mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        login_resp = MagicMock()
        login_resp.status = 200
        login_resp.text = AsyncMock(return_value="Ok.")
        login_resp.cookies = {}

        mock_session.post.return_value.__aenter__ = AsyncMock(return_value=login_resp)
        mock_session.post.return_value.__aexit__ = AsyncMock(return_value=False)

        resp = client.post(
            "/api/v1/download",
            json={"result_id": "test-1", "download_urls": []},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "failed"
        assert data["added_count"] == 0

    @patch("api.routes._get_orchestrator")
    @patch("api.routes.aiohttp.ClientSession")
    def test_download_connection_error(self, mock_session_cls, mock_get_orch, client):
        """Download when qBittorrent is unreachable should return connection_failed."""
        orch = MagicMock()
        orch.is_search_queue_full.return_value = False
        mock_get_orch.return_value = orch

        mock_session_cls.side_effect = Exception("Connection refused")

        resp = client.post(
            "/api/v1/download",
            json={
                "result_id": "test-1",
                "download_urls": ["magnet:?xt=urn:btih:e9bb4ead5d7ed51aa7d310d7cfef92b9b273a77f"],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "connection_failed"

    @patch("api.routes._get_orchestrator")
    @patch("api.routes.aiohttp.ClientSession")
    def test_download_qbit_rejects_add(self, mock_session_cls, mock_get_orch, client):
        """Download when qBittorrent auth succeeds but add-torrent fails."""
        orch = MagicMock()
        orch.is_search_queue_full.return_value = False
        mock_get_orch.return_value = orch

        mock_session = MagicMock()
        mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        login_resp = MagicMock()
        login_resp.status = 200
        login_resp.text = AsyncMock(return_value="Ok.")
        login_resp.cookies = {}

        add_resp = MagicMock()
        add_resp.status = 400
        add_resp.text = AsyncMock(return_value="Bad Request")

        def post_side_effect(*args, **kwargs):
            mock_r = MagicMock()
            if "/auth/login" in args[0]:
                mock_r.__aenter__ = AsyncMock(return_value=login_resp)
            else:
                mock_r.__aenter__ = AsyncMock(return_value=add_resp)
            mock_r.__aexit__ = AsyncMock(return_value=False)
            return mock_r

        mock_session.post.side_effect = post_side_effect

        resp = client.post(
            "/api/v1/download",
            json={
                "result_id": "test-1",
                "download_urls": ["magnet:?xt=urn:btih:e9bb4ead5d7ed51aa7d310d7cfef92b9b273a77f"],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "failed"
        assert data["added_count"] == 0
        assert len(data["results"]) == 1
        assert data["results"][0]["status"] == "failed"

    @patch("api.routes._get_orchestrator")
    @patch("api.routes.aiohttp.ClientSession")
    def test_download_successful_add(self, mock_session_cls, mock_get_orch, client):
        """Download when qBittorrent accepts the torrent."""
        orch = MagicMock()
        orch.is_search_queue_full.return_value = False
        mock_get_orch.return_value = orch

        mock_session = MagicMock()
        mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        login_resp = MagicMock()
        login_resp.status = 200
        login_resp.text = AsyncMock(return_value="Ok.")
        login_resp.cookies = {}

        add_resp = MagicMock()
        add_resp.status = 200
        add_resp.text = AsyncMock(return_value="Ok.")

        def post_side_effect(*args, **kwargs):
            mock_r = MagicMock()
            if "/auth/login" in args[0]:
                mock_r.__aenter__ = AsyncMock(return_value=login_resp)
            else:
                mock_r.__aenter__ = AsyncMock(return_value=add_resp)
            mock_r.__aexit__ = AsyncMock(return_value=False)
            return mock_r

        mock_session.post.side_effect = post_side_effect

        resp = client.post(
            "/api/v1/download",
            json={
                "result_id": "test-1",
                "download_urls": ["magnet:?xt=urn:btih:e9bb4ead5d7ed51aa7d310d7cfef92b9b273a77f"],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "initiated"
        assert data["added_count"] == 1
        assert len(data["results"]) == 1
        assert data["results"][0]["status"] == "added"


class TestActiveDownloadsEndpoint:
    @patch("api.routes.aiohttp.ClientSession")
    def test_active_downloads_auth_failed(self, mock_session_cls, client):
        mock_session = MagicMock()
        mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_resp = MagicMock()
        mock_resp.status = 403
        mock_session.post.return_value.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_session.post.return_value.__aexit__ = AsyncMock(return_value=False)

        resp = client.get("/api/v1/downloads/active")
        assert resp.status_code == 200
        data = resp.json()
        assert data["downloads"] == []
        assert data["count"] == 0
        assert "error" in data
