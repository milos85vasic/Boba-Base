"""Integration: download endpoint rejects non-freeleech IPTorrents.

Exercises the REAL FastAPI app end-to-end via TestClient, but stubs the
orchestrator so no live IPTorrents credentials or qBittorrent instance is
needed. The gate under test lives in ``api.routes._is_non_freeleech_iptorrents_url``
and is enforced by ``POST /api/v1/download``.
"""

from __future__ import annotations

import sys
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
    """qBittorrent login fails so the handler returns without real network."""
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


@pytest.fixture(autouse=True)
def _restore_api_module():
    yield
    _purge_api_module()


@pytest.fixture
def client(tmp_path, monkeypatch):
    _purge_api_module()
    import api
    import api.hooks

    monkeypatch.setattr(api.hooks, "HOOKS_FILE", str(tmp_path / "hooks.json"))
    api.orchestrator_instance = _make_orch()
    return TestClient(api.app)


def test_non_freeleech_iptorrents_blocked_with_expected_body(client, monkeypatch):
    monkeypatch.delenv("ENABLE_NON_FREELEECH_IPTORRENTS", raising=False)
    import api

    orch = api.orchestrator_instance
    url = "https://iptorrents.com/download.php/123/foo.torrent"
    _seed_iptorrents_result(orch, url, freeleech=False)

    with patch("aiohttp.ClientSession", return_value=_mocked_qbit_session()):
        resp = client.post(
            "/api/v1/download",
            json={"result_id": "r1", "download_urls": [url]},
        )

    assert resp.status_code == 403, f"expected 403, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert "detail" in body
    assert "freeleech" in body["detail"].lower()
    assert url in body["detail"]


def test_freeleech_iptorrents_allowed(client, monkeypatch):
    monkeypatch.delenv("ENABLE_NON_FREELEECH_IPTORRENTS", raising=False)
    import api

    orch = api.orchestrator_instance
    url = "https://iptorrents.com/download.php/123/foo.torrent"
    _seed_iptorrents_result(orch, url, freeleech=True)

    with patch("aiohttp.ClientSession", return_value=_mocked_qbit_session()):
        resp = client.post(
            "/api/v1/download",
            json={"result_id": "r1", "download_urls": [url]},
        )

    assert resp.status_code != 403, f"freeleech must be allowed, got {resp.status_code}: {resp.text}"


def test_non_iptorrents_url_not_blocked(client, monkeypatch):
    monkeypatch.delenv("ENABLE_NON_FREELEECH_IPTORRENTS", raising=False)

    with patch("aiohttp.ClientSession", return_value=_mocked_qbit_session()):
        resp = client.post(
            "/api/v1/download",
            json={"result_id": "r1", "download_urls": ["https://example.test/x.torrent"]},
        )

    assert resp.status_code != 403, f"unrelated URL must not be blocked, got {resp.status_code}: {resp.text}"
