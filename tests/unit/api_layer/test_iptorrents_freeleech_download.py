"""IPTorrents freeleech enforcement at download time.

The deduplicator already refuses to merge non-freeleech IPTorrents results
with other trackers, but ``POST /api/v1/download`` did not block adding such
a torrent to qBittorrent. These tests guard the download-time gate.

§11.4.122 (regression): freeleech IPTorrents results and non-tracker URLs
must not be blocked. Non-freeleech IPTorrents results are blocked unless the
operator explicitly opts in via ``ENABLE_NON_FREELEECH_IPTORRENTS=1``.
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

from merge_service.search import SearchResult


def _purge_api_module() -> None:
    for key in [k for k in list(sys.modules) if k == "api" or k.startswith("api.")]:
        del sys.modules[key]


def _make_orch():
    orch = MagicMock()
    orch._max_concurrent_searches = 8
    orch.is_search_queue_full.return_value = False
    orch._active_searches = {}
    orch._last_merged_results = {}
    orch._search_tasks = {}
    orch.fetch_torrent = AsyncMock(return_value=None)
    return orch


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


def _mocked_qbit_session():
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


def _seed_iptorrents_result(orch, url: str, *, freeleech: bool) -> None:
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


class TestIPTorrentsFreeleechDownload:
    def test_non_freeleech_iptorrents_blocked(self, client, monkeypatch):
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
        assert "freeleech" in resp.text.lower(), "error must name the freeleech policy"

    def test_non_freeleech_iptorrents_allowed_with_opt_in(self, client, monkeypatch):
        monkeypatch.setenv("ENABLE_NON_FREELEECH_IPTORRENTS", "1")
        import api

        orch = api.orchestrator_instance
        url = "https://iptorrents.com/download.php/123/foo.torrent"
        _seed_iptorrents_result(orch, url, freeleech=False)

        with patch("aiohttp.ClientSession", return_value=_mocked_qbit_session()):
            resp = client.post(
                "/api/v1/download",
                json={"result_id": "r1", "download_urls": [url]},
            )

        assert resp.status_code != 403, f"opt-in must bypass block, got {resp.status_code}: {resp.text}"

    def test_freeleech_iptorrents_allowed(self, client, monkeypatch):
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

    def test_unrelated_url_not_blocked(self, client, monkeypatch):
        monkeypatch.delenv("ENABLE_NON_FREELEECH_IPTORRENTS", raising=False)

        with patch("aiohttp.ClientSession", return_value=_mocked_qbit_session()):
            resp = client.post(
                "/api/v1/download",
                json={"result_id": "r1", "download_urls": ["https://example.test/x.torrent"]},
            )

        assert resp.status_code != 403, f"unrelated URL must not be blocked, got {resp.status_code}: {resp.text}"
