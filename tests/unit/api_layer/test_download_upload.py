"""
BE-2 — raw .torrent file-bytes upload endpoint for the BobaLink extension.

``POST /api/v1/download/upload`` accepts a multipart file field (the raw bytes
of a user-picked ``.torrent``), logs into qBittorrent (admin/admin, mirroring
``/api/v1/download`` at routes.py:776-789), and forwards the bytes to
qBittorrent's ``/api/v2/torrents/add`` as a multipart ``torrents`` field
(mirroring routes.py:810-822). It returns a user-observable success body.

§11.4.43 / §11.4.115 RED-first: against the pre-fix code the endpoint does not
exist, so the POST 404s and the success/forward assertions FAIL. After the fix
they GREEN.

Anti-bluff (§11.4.107): the tests assert the user-observable outcome
(``status: "added"`` body field) AND that the handler actually built the
multipart ``torrents`` upload to qBittorrent (inspecting the mocked
``session.post`` call) — a stub that 200s without forwarding the bytes FAILs.
These are unit tests: aiohttp is mocked so no real qBittorrent is contacted.
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SRC_PATH = _REPO_ROOT / "download-proxy" / "src"
if str(_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(_SRC_PATH))


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
    return orch


@pytest.fixture
def client_factory(tmp_path, monkeypatch):
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


def _aiohttp_response(text="", status=200):
    resp = AsyncMock()
    resp.text = AsyncMock(return_value=text)
    resp.status = status
    resp.cookies = {}
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


# A minimal but structurally valid bencoded .torrent: a dict with an "info"
# dict carrying name/piece length/pieces — enough to pass content sniffing.
def _valid_torrent_bytes() -> bytes:
    return (
        b"d8:announce20:http://tracker.test"
        b"4:infod6:lengthi12e4:name8:demo.bin"
        b"12:piece lengthi16384e6:pieces20:" + (b"\x00" * 20) + b"ee"
    )


@pytest.fixture(autouse=True)
def _restore_api_module():
    yield
    _purge_api_module()


class TestUploadSuccess:
    def test_upload_forwards_bytes_and_reports_added(self, client_factory):
        orch = _make_orch()
        c = client_factory(orch)
        login = _aiohttp_response(text="Ok.", status=200)
        add = _aiohttp_response(text="Ok.", status=200)
        session = AsyncMock()
        # First .post is the qBittorrent login, second is the torrents/add.
        session.post = MagicMock(side_effect=[login, add])
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)

        torrent = _valid_torrent_bytes()
        with patch("aiohttp.ClientSession", return_value=session):
            resp = c.post(
                "/api/v1/download/upload",
                files={"file": ("demo.torrent", torrent, "application/x-bittorrent")},
            )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        # User-observable success outcome.
        assert body["status"] == "added"
        assert body["filename"] == "demo.torrent"
        assert "download_id" in body

        # Anti-bluff: the handler actually forwarded the bytes to qBittorrent's
        # /api/v2/torrents/add as a multipart "torrents" form field.
        assert session.post.call_count == 2
        add_call = session.post.call_args_list[1]
        add_url = add_call.args[0] if add_call.args else add_call.kwargs.get("url")
        assert add_url.endswith("/api/v2/torrents/add")
        form = add_call.kwargs["data"]
        assert isinstance(form, aiohttp.FormData)
        # The multipart payload must carry the uploaded bytes under "torrents".
        # aiohttp stores each field as (type_options, headers, value).
        fields = form._fields
        assert len(fields) == 1
        type_options, headers, value = fields[0]
        assert type_options.get("name") == "torrents"
        assert "application/x-bittorrent" in headers.get("Content-Type", "")
        assert value == torrent  # the exact uploaded bytes were forwarded


class TestUploadRejection:
    def test_auth_failure_reported(self, client_factory):
        orch = _make_orch()
        c = client_factory(orch)
        login = _aiohttp_response(text="Fails.", status=403)
        session = AsyncMock()
        session.post = MagicMock(return_value=login)
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        with patch("aiohttp.ClientSession", return_value=session):
            resp = c.post(
                "/api/v1/download/upload",
                files={"file": ("demo.torrent", _valid_torrent_bytes(), "application/x-bittorrent")},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "auth_failed"

    def test_empty_file_rejected(self, client_factory):
        orch = _make_orch()
        c = client_factory(orch)
        # Must reject BEFORE contacting qBittorrent (no session needed).
        resp = c.post(
            "/api/v1/download/upload",
            files={"file": ("empty.torrent", b"", "application/x-bittorrent")},
        )
        assert resp.status_code == 400
        assert "empty" in resp.json()["detail"].lower()

    def test_oversize_file_rejected(self, client_factory):
        orch = _make_orch()
        c = client_factory(orch)
        big = b"d4:infod" + (b"x" * (10 * 1024 * 1024 + 1)) + b"ee"
        resp = c.post(
            "/api/v1/download/upload",
            files={"file": ("big.torrent", big, "application/x-bittorrent")},
        )
        assert resp.status_code == 413
        assert "10" in resp.json()["detail"]

    def test_non_torrent_content_rejected(self, client_factory):
        orch = _make_orch()
        c = client_factory(orch)
        # Bytes that are not bencoded -> content sniff must reject.
        resp = c.post(
            "/api/v1/download/upload",
            files={"file": ("not.torrent", b"<html>nope</html>", "application/x-bittorrent")},
        )
        assert resp.status_code == 400
        assert "torrent" in resp.json()["detail"].lower()
