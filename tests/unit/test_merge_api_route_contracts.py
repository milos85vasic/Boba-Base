"""
Unit-level route-contract tests for the merge service API.

Uses FastAPI ``TestClient`` with a mocked ``SearchOrchestrator`` (via
``@patch("api.routes._get_orchestrator")``). These tests verify the HTTP
contract of each route — request validation, response shape, status codes,
and error-path branching — WITHOUT exercising the real orchestrator, real
qBittorrent, or real tracker network calls.

Per CLAUDE.md / the project's inherited anti-bluff rule (§11.4.27): mocks
and stubs are permitted ONLY in ``tests/unit/``. This file previously lived
at ``tests/integration/test_merge_api.py`` and mocked the exact component
("SearchOrchestrator" via ``_get_orchestrator``) an integration test is
supposed to exercise for real — a directory-naming contract violation
(GA-14, ``docs/GOVERNANCE_AUDIT_2026-08-07.md`` /
``docs/GOVERNANCE_AUDIT_2026-08-08_ROUND2.md``). The route-contract coverage
here is genuinely valuable — it just belongs in ``tests/unit/`` where mocking
is permitted. The real, live-service replacement now lives at
``tests/integration/test_merge_api.py`` and issues real HTTP calls to a real
running merge-search service (see that file's docstring).
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
# (Now that this file lives under tests/unit/, the top-level
# tests/conftest.py::_isolate_download_proxy_modules autouse fixture
# ALSO snapshots + restores every ``merge_service.*`` / ``api.*`` module
# around this file's tests, which supersedes the old del-based approach
# even more thoroughly. Kept here for clarity + defense in depth.)
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
        """An empty/blank ``download_urls`` is REFUSED at the request boundary (422).

        CONTRACT CHANGED 2026-09-01 — this test previously asserted
        ``200 {"status": "failed", "added_count": 0}``. That 200 was never an
        asserted "empty list is a no-op that succeeds" contract: the test was
        added in fcb610c as one of a six-case error-surface sweep, its docstring
        pinned only "should return failed status, NOT CRASH", and the body it
        pinned already said ``status: "failed"`` — the endpoint always called
        this input a failure. The 200 envelope was the incidental shape of that
        failure, not a promise to any caller.

        Why it had to change — the permissive boundary made a REAL PASS-bluff
        reachable on the primary download path. qBittorrent's ``torrents/add``
        answers **409 Conflict** for BOTH a genuine duplicate (success: the
        torrent is present) AND a request that carried no payload at all
        (total failure: nothing was added). Both measured against qBittorrent
        v5.2.3 on 2026-09-01. ``_qbit_add_succeeded`` reads 409 as success, so a
        blank URL — which reaches qBittorrent as ``urls=""``, the no-payload
        409 — was reported to the user as an added torrent that never existed:

            POST /api/v1/download {"download_urls":[""]}
            -> {"status":"initiated","added_count":1,...}
            qBittorrent torrent count: UNCHANGED

        The 409 clause itself is correct for a real payload, so the fix belongs
        where the bad input enters. Rejecting empty URLs at the boundary is what
        makes "409 reaching the add-success predicate" imply a genuine
        duplicate. Loosening that predicate instead would break real duplicate
        adds (§11.4.120: reconcile the gate to the new mechanism, never
        fake-pass it).

        No consumer relied on the old 200: the Jinja dashboard guards the call
        (``if (urls.length === 0) { alert('No download URLs available'); return; }``
        — download-proxy/src/ui/templates/dashboard.html:1042), the Angular
        dashboard only forwards URL lists taken from real search results and
        surfaces failures as a toast, and neither ``webui-bridge.py`` nor
        ``plugins/`` call this endpoint at all. Both dashboards DO normalise a
        missing link to ``['']`` (dashboard.component.ts:504,
        dashboard.html:597) — the exact blank-URL input this now refuses loudly
        instead of reporting a phantom add.
        """
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
        assert resp.status_code == 422
        # The refusal must name the offending field, not merely be "some 422".
        assert "download_urls" in resp.text
        # The load-bearing outcome: qBittorrent is never contacted, so no 409
        # can be misread as an add. This is what the old contract permitted.
        assert mock_session.post.call_count == 0

    @patch("api.routes._get_orchestrator")
    @patch("api.routes.aiohttp.ClientSession")
    def test_download_blank_url_string_rejected(self, mock_session_cls, mock_get_orch, client):
        """A whitespace-only URL is refused exactly like an empty list.

        This is the input that actually produced the live PASS-bluff documented
        on ``test_download_empty_urls``: ``[""]`` passes a bare
        ``min_length``-style check but reaches qBittorrent as ``urls=""``.
        """
        orch = MagicMock()
        orch.is_search_queue_full.return_value = False
        mock_get_orch.return_value = orch

        mock_session = MagicMock()
        mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        resp = client.post(
            "/api/v1/download",
            json={"result_id": "test-1", "download_urls": ["   "]},
        )
        assert resp.status_code == 422
        assert "download_urls" in resp.text
        assert mock_session.post.call_count == 0

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

    # --- the 409 contract, asserted at the HTTP layer -------------------
    #
    # COVERAGE ESCAPE THIS CLOSES (§11.4.238, measured 2026-09-02). Flipping the
    # 409 clause in ``merge_service/qbit_add.py`` — the single shared predicate —
    # left this entire 29-test HTTP suite GREEN while the direct-import suites
    # (``test_qbit_login_compat.py`` / ``test_qbit_add_shared_predicate.py``)
    # went red. The layer CLOSEST TO THE USER never exercised the 409 path at
    # all, so the acceptance criterion ("one mutation reddens both consumers")
    # was met only below the HTTP boundary. These three tests drive
    # ``POST /api/v1/download`` for real and assert the user-visible envelope.
    #
    # WHY 409 MEANS SUCCESS HERE, and why that is not ambiguous any more
    # (measured against qBittorrent v5.2.3 / WebAPI 2.15.1, 2026-09-01):
    #
    #     duplicate add   -> 409  -> already present  -> SUCCESS
    #     no payload sent -> 409  -> nothing added    -> FAILURE
    #
    # The status alone cannot separate them. What separates them is the
    # boundary: ``DownloadRequest._reject_empty_urls`` refuses an empty or
    # whitespace-only URL with 422 before qBittorrent is contacted, so a 409
    # that reaches the predicate FROM THIS ROUTE is necessarily the duplicate.
    # ``test_download_409_no_payload_case_cannot_reach_the_predicate`` asserts
    # that enforcement point holds at the HTTP layer, with the ambiguous 409
    # armed and waiting — proving it is unreachable rather than merely unused.

    @staticmethod
    def _session_answering_add_with(mock_session_cls, add_status, add_body):
        """Wire a mocked aiohttp session: login succeeds, add answers as given."""
        mock_session = MagicMock()
        mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        login_resp = MagicMock()
        login_resp.status = 200
        login_resp.text = AsyncMock(return_value="Ok.")
        login_resp.cookies = {}

        add_resp = MagicMock()
        add_resp.status = add_status
        add_resp.text = AsyncMock(return_value=add_body)

        def post_side_effect(*args, **kwargs):
            mock_r = MagicMock()
            mock_r.__aenter__ = AsyncMock(return_value=login_resp if "/auth/login" in args[0] else add_resp)
            mock_r.__aexit__ = AsyncMock(return_value=False)
            return mock_r

        mock_session.post.side_effect = post_side_effect
        return mock_session

    @patch("api.routes._get_orchestrator")
    @patch("api.routes.aiohttp.ClientSession")
    def test_download_duplicate_409_is_reported_to_the_user_as_added(self, mock_session_cls, mock_get_orch, client):
        """A duplicate add (409) surfaces as an ADDED torrent, not a failure.

        The user asked for a torrent that is already in the session; their goal
        is satisfied, and reporting "failed" would make an ordinary client retry
        of this non-idempotent POST look like a broken download.

        RED under the §1.1 mutation of the shared predicate (flip the 409 clause
        to ``return False``): this asserts the exact user-visible envelope, so
        the flip turns ``initiated``/``added_count: 1``/``added`` into
        ``failed``/``0``/``failed``.
        """
        self._session_answering_add_with(mock_session_cls, 409, "Conflict")

        orch = MagicMock()
        orch.is_search_queue_full.return_value = False
        mock_get_orch.return_value = orch

        resp = client.post(
            "/api/v1/download",
            json={
                "result_id": "test-409",
                "download_urls": ["magnet:?xt=urn:btih:e9bb4ead5d7ed51aa7d310d7cfef92b9b273a77f"],
            },
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "initiated"
        assert data["added_count"] == 1
        assert len(data["results"]) == 1
        assert data["results"][0]["status"] == "added"

    @patch("api.routes._get_orchestrator")
    @patch("api.routes.aiohttp.ClientSession")
    def test_download_415_is_still_a_failure_not_a_blanket_4xx_success(self, mock_session_cls, mock_get_orch, client):
        """§11.4.201(1) false-positive guard for the test above.

        A predicate rewritten to "any 4xx is success" would satisfy the 409 test
        while reporting every corrupt torrent as added. 415 is the measured
        response to a corrupt/truncated/empty ``.torrent`` and MUST stay a
        failure, so 409 has to be special-cased rather than swept up.
        """
        self._session_answering_add_with(mock_session_cls, 415, "Error: 'x.torrent' is not a valid torrent file.")

        orch = MagicMock()
        orch.is_search_queue_full.return_value = False
        mock_get_orch.return_value = orch

        resp = client.post(
            "/api/v1/download",
            json={
                "result_id": "test-415",
                "download_urls": ["magnet:?xt=urn:btih:e9bb4ead5d7ed51aa7d310d7cfef92b9b273a77f"],
            },
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "failed"
        assert data["added_count"] == 0
        assert data["results"][0]["status"] == "failed"

    @patch("api.routes._get_orchestrator")
    @patch("api.routes.aiohttp.ClientSession")
    def test_download_409_no_payload_case_cannot_reach_the_predicate(self, mock_session_cls, mock_get_orch, client):
        """The OTHER 409 — "nothing was sent" — is unreachable from this route.

        This is the live-proven PASS-bluff input: ``{"download_urls": [""]}``
        reached qBittorrent as ``urls=""``, drew the no-payload 409, and was
        reported as ``{"status":"added"}`` for a torrent that never existed.

        The mock here is ARMED with exactly that 409 — so if the boundary ever
        stops refusing, this test does not merely fail to reproduce the bug, it
        reproduces it: the request would sail through and be reported as added.
        Instead the 422 lands and ``post`` is never called, which is what makes
        the SUCCESS reading of 409 in the test above sound.
        """
        mock_session = self._session_answering_add_with(mock_session_cls, 409, "Conflict")

        orch = MagicMock()
        orch.is_search_queue_full.return_value = False
        mock_get_orch.return_value = orch

        resp = client.post(
            "/api/v1/download",
            json={"result_id": "test-409-empty", "download_urls": [""]},
        )

        assert resp.status_code == 422
        assert "download_urls" in resp.text
        # The load-bearing outcome: qBittorrent is never contacted, so the
        # ambiguous 409 the stub is holding can never be read as an add.
        assert mock_session.post.call_count == 0


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
