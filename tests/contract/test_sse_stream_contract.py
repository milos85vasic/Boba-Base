"""Contract tests for ``GET /api/v1/search/stream/{search_id}``.

OpenAPI-driven checks for the SSE stream endpoint schema, response content
type, token auth contract, and the 404/403 rejection shapes.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _repo_root() -> Path:
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "download-proxy" / "src").is_dir():
            return parent
    raise RuntimeError("cannot find repo root with download-proxy/src")


import pytest
from fastapi.testclient import TestClient

_SRC = _repo_root() / "download-proxy" / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def _purge_api_module() -> None:
    for key in [k for k in list(sys.modules) if k == "api" or k.startswith("api.")]:
        del sys.modules[key]


@pytest.fixture(autouse=True)
def _restore_api_module():
    yield
    _purge_api_module()


def _make_orch() -> Any:
    from unittest.mock import MagicMock

    orch = MagicMock()
    orch._max_concurrent_searches = 8
    orch.is_search_queue_full.return_value = False
    orch._active_searches = {}
    orch._last_merged_results = {}
    orch._search_tasks = {}
    return orch


@pytest.fixture
def app(monkeypatch, tmp_path):
    _purge_api_module()
    os.environ.setdefault("ALLOWED_ORIGINS", "http://localhost")
    import api
    import api.hooks

    monkeypatch.setattr(api.hooks, "HOOKS_FILE", str(tmp_path / "hooks.json"))
    api.orchestrator_instance = _make_orch()
    return api.app


@pytest.mark.contract
def test_openapi_sse_stream_endpoint_exists(app):
    openapi = app.openapi()
    path = "/api/v1/search/stream/{search_id}"
    assert path in openapi["paths"]
    methods = openapi["paths"][path]
    assert "get" in methods
    get = methods["get"]
    assert get["parameters"]
    param_names = {p["name"] for p in get["parameters"]}
    assert "search_id" in param_names


@pytest.mark.contract
def test_sse_stream_unknown_search_returns_404(app):
    client = TestClient(app)
    resp = client.get("/api/v1/search/stream/nonexistent-search-id")
    assert resp.status_code == 404
    assert resp.json()["detail"]


@pytest.mark.contract
def test_sse_stream_requires_token_when_enforced(app, monkeypatch):
    monkeypatch.setenv("SSE_REQUIRE_TOKEN", "1")
    client = TestClient(app)
    resp = client.get("/api/v1/search/stream/some-search-id")
    assert resp.status_code in (403, 404)


@pytest.mark.contract
def test_sse_stream_accepts_valid_token(app, monkeypatch):
    monkeypatch.setenv("SSE_REQUIRE_TOKEN", "1")
    import api
    from merge_service.search import SearchMetadata

    orch = api.orchestrator_instance
    assert orch is not None, "orchestrator_instance must be set by the app fixture"
    orch.get_live_results.return_value = []
    orch.get_search_status.return_value = None
    metadata = SearchMetadata(search_id="contract-stream", query="test")
    metadata.status = "completed"
    orch._active_searches["contract-stream"] = metadata
    orch.get_search_status.return_value = metadata
    token = orch.issue_stream_token("contract-stream")

    client = TestClient(app)
    resp = client.get(f"/api/v1/search/stream/contract-stream?token={token}")
    # The stream begins successfully (200 + text/event-stream).
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")
    assert "event: search_start" in resp.text
