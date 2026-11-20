"""Contract tests for ``POST /api/v1/download``.

OpenAPI-driven checks for the endpoint schema, response shapes, auth, and the
non-freeleech IPTorrents rejection contract. Uses the real ASGI app via
TestClient so no live tracker credentials are required.
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path


def _repo_root() -> Path:
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "download-proxy" / "src").is_dir():
            return parent
    raise RuntimeError("cannot find repo root with download-proxy/src")


from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from typing import Any

_SRC = _repo_root() / "download-proxy" / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from merge_service.search import SearchResult


def _purge_api_module() -> None:
    for key in [k for k in list(sys.modules) if k == "api" or k.startswith("api.")]:
        del sys.modules[key]


def _make_orch() -> MagicMock:
    orch = MagicMock()
    orch._max_concurrent_searches = 8
    orch.is_search_queue_full.return_value = False
    orch._active_searches = {}
    orch._last_merged_results = {}
    orch._search_tasks = {}
    orch.fetch_torrent = AsyncMock(return_value=None)
    return orch


def _mocked_qbit_session() -> MagicMock:
    login = AsyncMock()
    login.text = AsyncMock(return_value="Fails.")
    login.status = 403
    login.cookies = {}
    login.__aenter__ = AsyncMock(return_value=login)
    login.__aexit__ = AsyncMock(return_value=False)
    session = AsyncMock()
    session.post = MagicMock(return_value=login)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


@pytest.fixture(autouse=True)
def _restore_api_module():
    yield
    _purge_api_module()


@pytest.fixture
def app(monkeypatch, tmp_path):
    _purge_api_module()
    os.environ.setdefault("ALLOWED_ORIGINS", "http://localhost")
    import api
    import api.hooks

    monkeypatch.setattr(api.hooks, "HOOKS_FILE", str(tmp_path / "hooks.json"))
    api.orchestrator_instance = _make_orch()
    return api.app


def _seed_iptorrents_result(orch: MagicMock, url: str, *, freeleech: bool) -> None:
    result = SearchResult(
        name="Some Movie [free]" if freeleech else "Some Movie",
        link=url,
        size="1.0 GB",
        seeds=1,
        leechers=0,
        engine_url="https://iptorrents.com",
        tracker="iptorrents",
        freeleech=freeleech,
    )
    orch._last_merged_results["search-1"] = ([], [result])


def _resolve_ref(openapi: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    ref = schema.get("$ref")
    if not ref:
        return schema
    assert ref.startswith("#/components/"), f"unexpected external ref: {ref}"
    parts = ref.split("/")[1:]  # ['components', 'schemas', 'DownloadRequest']
    resolved = openapi
    for part in parts:
        resolved = resolved[part]
    return resolved


@pytest.mark.contract
def test_openapi_download_endpoint_exists(app):
    openapi = app.openapi()
    assert "/api/v1/download" in openapi["paths"]
    methods = openapi["paths"]["/api/v1/download"]
    assert "post" in methods
    post = methods["post"]
    schema = _resolve_ref(openapi, post["requestBody"]["content"]["application/json"]["schema"])
    assert schema["type"] == "object"
    assert "result_id" in schema["properties"]
    assert "download_urls" in schema["properties"]


@pytest.mark.contract
def test_non_freeleech_iptorrents_rejection_body(app, monkeypatch):
    monkeypatch.delenv("ENABLE_NON_FREELEECH_IPTORRENTS", raising=False)
    import api

    orch = api.orchestrator_instance
    url = "https://iptorrents.com/download.php/123/foo.torrent"
    _seed_iptorrents_result(orch, url, freeleech=False)

    client = TestClient(app)
    with patch("aiohttp.ClientSession", return_value=_mocked_qbit_session()):
        resp = client.post(
            "/api/v1/download",
            json={"result_id": "r1", "download_urls": [url]},
        )

    assert resp.status_code == 403
    body = resp.json()
    assert "detail" in body
    assert "freeleech" in body["detail"].lower()
    assert url in body["detail"]


@pytest.mark.contract
def test_download_requires_token_when_configured(app, monkeypatch):
    token = f"test-token-{uuid.uuid4()}"
    monkeypatch.setenv("BOBA_API_TOKEN", token)

    client = TestClient(app)
    resp = client.post(
        "/api/v1/download",
        json={"result_id": "r1", "download_urls": ["https://example.test/x.torrent"]},
    )
    assert resp.status_code == 401
    assert "Unauthorized" in resp.json()["detail"]


@pytest.mark.contract
def test_download_accepts_token_via_bearer_header(app, monkeypatch):
    token = f"test-token-{uuid.uuid4()}"
    monkeypatch.setenv("BOBA_API_TOKEN", token)
    monkeypatch.delenv("ENABLE_NON_FREELEECH_IPTORRENTS", raising=False)

    client = TestClient(app)
    with patch("aiohttp.ClientSession", return_value=_mocked_qbit_session()):
        resp = client.post(
            "/api/v1/download",
            json={"result_id": "r1", "download_urls": ["https://example.test/x.torrent"]},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code != 401


@pytest.mark.contract
def test_download_empty_urls_returns_422(app):
    client = TestClient(app)
    resp = client.post(
        "/api/v1/download",
        json={"result_id": "r1", "download_urls": []},
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"][0]
    assert "download_urls" in str(detail)
