"""
Optional, env-gated shared-secret check on the three download-WRITE endpoints
(operator decision responding to a HIGH security finding).

Endpoints gated:
  * ``POST /api/v1/download``          (initiate_download)
  * ``POST /api/v1/download/upload``   (upload_torrent)
  * ``POST /api/v1/download/file``     (download_torrent_file)

Contract:
  * ``BOBA_API_TOKEN`` UNSET/empty  -> OPEN (no auth — current contract, default).
  * ``BOBA_API_TOKEN`` SET          -> request MUST present the matching token in
    either ``Authorization: Bearer <token>`` OR ``X-Boba-Token: <token>``.
    Missing/mismatch -> 401. Comparison is constant-time (``hmac.compare_digest``).

§11.4.43 / §11.4.115 RED-first: against the pre-fix code there is NO token gate,
so with the env var SET the no-token / wrong-token requests reach the handler and
return 200 (NOT 401) — every (a)/(b) assertion FAILs. After the fix they GREEN.

§11.4.122 (pure addition): with the env var UNSET the no-token request MUST still
reach the handler (NOT 401) — the regression guard that the extension's current
no-auth contract is unchanged.

§11.4.107 (anti-bluff): assertions inspect the user-observable HTTP status
(401 vs not-401). The qBittorrent call is mocked so the "correct token reaches
the handler" cases exercise the real handler path without a live qBittorrent.

§11.4.10: the token here is a SYNTHETIC per-run value (uuid) — never a real
secret, never logged.
"""

import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SRC_PATH = _REPO_ROOT / "download-proxy" / "src"
if str(_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(_SRC_PATH))

_TOKEN = f"test-token-{uuid.uuid4()}"


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
    # download_torrent_file iterates urls and calls _is_tracker_url; a
    # non-tracker url list never reaches fetch_torrent, but keep it safe.
    orch.fetch_torrent = AsyncMock(return_value=None)
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


@pytest.fixture(autouse=True)
def _restore_api_module():
    yield
    _purge_api_module()


def _aiohttp_response(text="", status=200):
    resp = AsyncMock()
    resp.text = AsyncMock(return_value=text)
    resp.status = status
    resp.cookies = {}
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


def _valid_torrent_bytes() -> bytes:
    return (
        b"d8:announce20:http://tracker.test"
        b"4:infod6:lengthi12e4:name8:demo.bin"
        b"12:piece lengthi16384e6:pieces20:" + (b"\x00" * 20) + b"ee"
    )


def _mocked_session():
    """A qBittorrent login that 'fails' (403) so initiate_download/upload
    short-circuit to a 200 ``auth_failed`` body WITHOUT a real network call —
    enough to prove the request reached the handler (i.e. NOT 401)."""
    login = _aiohttp_response(text="Fails.", status=403)
    session = AsyncMock()
    session.post = MagicMock(return_value=login)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


# (endpoint-id, callable(client, headers) -> Response). Each invocation sends a
# minimal-but-valid request for that endpoint; ``headers`` carries (or omits)
# the auth token.
def _call_download(c, headers):
    return c.post(
        "/api/v1/download",
        json={"result_id": "r1", "download_urls": ["https://example.test/x.torrent"]},
        headers=headers,
    )


def _call_upload(c, headers):
    return c.post(
        "/api/v1/download/upload",
        files={"file": ("demo.torrent", _valid_torrent_bytes(), "application/x-bittorrent")},
        headers=headers,
    )


def _call_download_file(c, headers):
    return c.post(
        "/api/v1/download/file",
        json={"result_id": "r1", "download_urls": ["https://example.test/x.torrent"]},
        headers=headers,
    )


_ENDPOINTS = [
    ("POST /api/v1/download", _call_download),
    ("POST /api/v1/download/upload", _call_upload),
    ("POST /api/v1/download/file", _call_download_file),
]


@pytest.mark.parametrize("name,call", _ENDPOINTS, ids=[e[0] for e in _ENDPOINTS])
class TestTokenSet:
    """With BOBA_API_TOKEN SET, all three write endpoints require it."""

    def test_no_token_header_is_401(self, name, call, client_factory, monkeypatch):
        monkeypatch.setenv("BOBA_API_TOKEN", _TOKEN)
        c = client_factory(_make_orch())
        with patch("aiohttp.ClientSession", return_value=_mocked_session()):
            resp = call(c, {})
        assert resp.status_code == 401, f"{name}: expected 401 w/o token, got {resp.status_code}: {resp.text}"

    def test_wrong_token_is_401(self, name, call, client_factory, monkeypatch):
        monkeypatch.setenv("BOBA_API_TOKEN", _TOKEN)
        c = client_factory(_make_orch())
        with patch("aiohttp.ClientSession", return_value=_mocked_session()):
            resp = call(c, {"Authorization": "Bearer wrong-token"})
        assert resp.status_code == 401, f"{name}: expected 401 on wrong token, got {resp.status_code}"

    def test_correct_bearer_token_not_401(self, name, call, client_factory, monkeypatch):
        monkeypatch.setenv("BOBA_API_TOKEN", _TOKEN)
        c = client_factory(_make_orch())
        with patch("aiohttp.ClientSession", return_value=_mocked_session()):
            resp = call(c, {"Authorization": f"Bearer {_TOKEN}"})
        assert resp.status_code != 401, f"{name}: correct Bearer token must reach handler, got 401: {resp.text}"

    def test_correct_x_boba_token_not_401(self, name, call, client_factory, monkeypatch):
        monkeypatch.setenv("BOBA_API_TOKEN", _TOKEN)
        c = client_factory(_make_orch())
        with patch("aiohttp.ClientSession", return_value=_mocked_session()):
            resp = call(c, {"X-Boba-Token": _TOKEN})
        assert resp.status_code != 401, f"{name}: correct X-Boba-Token must reach handler, got 401: {resp.text}"


@pytest.mark.parametrize("name,call", _ENDPOINTS, ids=[e[0] for e in _ENDPOINTS])
class TestTokenUnset:
    """Regression guard (§11.4.122): env UNSET -> OPEN, no token needed."""

    def test_no_token_header_not_401_when_unset(self, name, call, client_factory, monkeypatch):
        monkeypatch.delenv("BOBA_API_TOKEN", raising=False)
        c = client_factory(_make_orch())
        with patch("aiohttp.ClientSession", return_value=_mocked_session()):
            resp = call(c, {})
        assert resp.status_code != 401, f"{name}: default (env-unset) path must stay OPEN, got 401: {resp.text}"
