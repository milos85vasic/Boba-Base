"""Security regression tests — RW-03 (SSRF) + RW-04 (magnet auth).

§11.4.115 RED-on-broken-artifact: each assertion below FAILS against the
pre-fix ``download-proxy/src/api/routes.py`` and PASSES after the fix.

RW-03 (HIGH) — SSRF: ``download_torrent_file`` fetched arbitrary user-supplied
URLs server-side (``aiohttp...session.get(url)``) with NO validation, letting a
caller make the proxy GET ``http://169.254.169.254/`` (cloud metadata),
``http://127.0.0.1:7185/`` (loopback), or LAN/RFC-1918 hosts and receive the
body. Fix: ``_is_safe_fetch_url`` resolves the host and REJECTS loopback /
private / link-local / metadata / multicast / reserved IPs; the endpoint skips
rejected URLs and returns 404 when none are fetchable.

RW-04 (MED) — auth consistency: ``/api/v1/magnet`` lacked the
``Depends(require_api_token)`` gate its siblings (``/download``,
``/download/file``) carry. Fix adds it. BACKWARD-COMPAT: ``require_api_token``
is a NO-OP when ``BOBA_API_TOKEN`` is unset, so the token-less operator
workflow is unchanged; the gate only bites WHEN a token is configured.

These are unit-style tests: aiohttp + getaddrinfo are mocked so no real
network/DNS happens. Assertions inspect helper return values, response bodies,
and which URLs were actually fetched (anti-bluff §11.4.107), not just statuses.
"""

import socket
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC_PATH = _REPO_ROOT / "download-proxy" / "src"
if str(_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(_SRC_PATH))


def _purge_api_module() -> None:
    for key in [k for k in list(sys.modules) if k == "api" or k.startswith("api.")]:
        del sys.modules[key]


def _getaddrinfo_returning(ip: str):
    """A fake socket.getaddrinfo that resolves every host to ``ip``."""

    def _fake(host, *args, **kwargs):
        family = socket.AF_INET6 if ":" in ip else socket.AF_INET
        return [(family, socket.SOCK_STREAM, 0, "", (ip, 0))]

    return _fake


# ---------------------------------------------------------------------------
# RW-03 — _is_safe_fetch_url helper (direct, deterministic).
# ---------------------------------------------------------------------------


class TestIsSafeFetchUrlHelper:
    @pytest.fixture(autouse=True)
    def _load(self):
        _purge_api_module()
        from api.routes import _is_safe_fetch_url

        self.f = _is_safe_fetch_url

    @pytest.mark.parametrize(
        "host_ip",
        [
            "127.0.0.1",  # loopback
            "169.254.169.254",  # cloud metadata (link-local)
            "10.0.0.5",  # RFC-1918 private
            "192.168.1.10",  # RFC-1918 private
            "172.16.0.1",  # RFC-1918 private
            "0.0.0.0",  # reserved/unspecified
            "224.0.0.1",  # multicast
            "::1",  # IPv6 loopback
            "fd00::1",  # IPv6 unique-local (private)
        ],
    )
    def test_rejects_internal_targets(self, host_ip):
        with patch("socket.getaddrinfo", _getaddrinfo_returning(host_ip)):
            assert self.f("http://malicious.example/x.torrent") is False, (
                f"URL resolving to {host_ip} MUST be rejected (SSRF)"
            )

    def test_allows_public_host(self):
        with patch("socket.getaddrinfo", _getaddrinfo_returning("93.184.216.34")):
            assert self.f("https://example.com/file.torrent") is True

    def test_rejects_non_http_scheme(self):
        # file://, gopher://, etc. are not fetchable torrent sources.
        assert self.f("file:///etc/passwd") is False

    def test_rejects_unresolvable_host(self):
        with patch("socket.getaddrinfo", side_effect=socket.gaierror("no such host")):
            assert self.f("http://does-not-resolve.invalid/x") is False


# ---------------------------------------------------------------------------
# Shared aiohttp response/session mock helpers.
# ---------------------------------------------------------------------------


def _resp(status=200, body=b"torrent data"):
    r = AsyncMock()
    r.status = status
    r.read = AsyncMock(return_value=body)
    r.__aenter__ = AsyncMock(return_value=r)
    r.__aexit__ = AsyncMock(return_value=False)
    return r


def _session_for(resp):
    s = AsyncMock()
    s.get = MagicMock(return_value=resp)
    s.__aenter__ = AsyncMock(return_value=s)
    s.__aexit__ = AsyncMock(return_value=False)
    return s


@pytest.fixture
def client(tmp_path, monkeypatch):
    _purge_api_module()
    import api
    import api.hooks

    monkeypatch.setattr(api.hooks, "HOOKS_FILE", str(tmp_path / "hooks.json"))
    api.orchestrator_instance = MagicMock()
    # A non-tracker, non-magnet URL routes into the direct-fetch branch.
    api.orchestrator_instance.fetch_torrent = AsyncMock(return_value=None)
    return TestClient(api.app)


# ---------------------------------------------------------------------------
# RW-03 — endpoint behaviour (/download/file).
# ---------------------------------------------------------------------------


class TestDownloadFileSSRF:
    def test_internal_url_not_fetched_returns_404(self, client):
        """A download_url whose host resolves to the metadata IP MUST be
        skipped (never fetched). With no other URLs -> 404."""
        resp_mock = _resp()
        session = _session_for(resp_mock)
        with (
            patch("socket.getaddrinfo", _getaddrinfo_returning("169.254.169.254")),
            patch("aiohttp.ClientSession", return_value=session),
        ):
            resp = client.post(
                "/api/v1/download/file",
                json={"result_id": "r1", "download_urls": ["http://metadata.evil/latest/meta-data/"]},
            )
        assert resp.status_code == 404, "SSRF target must not be fetched -> 404"
        # Anti-bluff: prove the proxy NEVER issued the GET.
        session.get.assert_not_called()

    def test_loopback_url_not_fetched(self, client):
        resp_mock = _resp()
        session = _session_for(resp_mock)
        with (
            patch("socket.getaddrinfo", _getaddrinfo_returning("127.0.0.1")),
            patch("aiohttp.ClientSession", return_value=session),
        ):
            resp = client.post(
                "/api/v1/download/file",
                json={"result_id": "r1", "download_urls": ["http://localhost:7185/api/v2/torrents/info"]},
            )
        assert resp.status_code == 404
        session.get.assert_not_called()

    def test_public_url_still_fetched(self, client):
        """BACKWARD-COMPAT: a legit public-host URL is allowed + fetched."""
        resp_mock = _resp(status=200, body=b"d8:announce")
        session = _session_for(resp_mock)
        with (
            patch("socket.getaddrinfo", _getaddrinfo_returning("93.184.216.34")),
            patch("aiohttp.ClientSession", return_value=session),
        ):
            resp = client.post(
                "/api/v1/download/file",
                json={"result_id": "r1", "download_urls": ["https://example.com/file.torrent"]},
            )
        assert resp.status_code == 200
        assert resp.content == b"d8:announce"
        session.get.assert_called_once()

    def test_private_then_public_skips_private_fetches_public(self, client):
        """Mixed list: the private URL is skipped, the public one is fetched."""
        public_resp = _resp(status=200, body=b"d8:good")

        def _addr(host, *a, **k):
            ip = "10.1.2.3" if "internal" in host else "93.184.216.34"
            return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", (ip, 0))]

        session = _session_for(public_resp)
        with (
            patch("socket.getaddrinfo", _addr),
            patch("aiohttp.ClientSession", return_value=session),
        ):
            resp = client.post(
                "/api/v1/download/file",
                json={
                    "result_id": "r1",
                    "download_urls": [
                        "http://internal.evil/x.torrent",
                        "https://public.example/x.torrent",
                    ],
                },
            )
        assert resp.status_code == 200
        assert resp.content == b"d8:good"
        # Exactly one GET — only the public URL.
        session.get.assert_called_once()

    def test_magnet_url_unaffected(self, client):
        """Magnet links do no fetch -> never touched by the SSRF guard."""
        resp = client.post(
            "/api/v1/download/file",
            json={"result_id": "r1", "download_urls": ["magnet:?xt=urn:btih:abc"]},
        )
        assert resp.status_code == 200
        assert resp.text == "magnet:?xt=urn:btih:abc"


# ---------------------------------------------------------------------------
# RW-04 — /api/v1/magnet token gate.
# ---------------------------------------------------------------------------


class TestMagnetAuth:
    def test_magnet_401_when_token_set_and_missing(self, client, monkeypatch):
        monkeypatch.setenv("BOBA_API_TOKEN", "s3cret")
        resp = client.post(
            "/api/v1/magnet",
            json={"result_id": "x", "download_urls": ["magnet:?xt=urn:btih:" + "a" * 40]},
        )
        assert resp.status_code == 401, "magnet endpoint must be token-gated like its siblings"

    def test_magnet_200_with_token(self, client, monkeypatch):
        monkeypatch.setenv("BOBA_API_TOKEN", "s3cret")
        resp = client.post(
            "/api/v1/magnet",
            json={"result_id": "x", "download_urls": ["magnet:?xt=urn:btih:" + "a" * 40]},
            headers={"X-Boba-Token": "s3cret"},
        )
        assert resp.status_code == 200
        assert resp.json()["magnet"].startswith("magnet:?dn=")

    def test_magnet_open_when_token_unset(self, client, monkeypatch):
        """BACKWARD-COMPAT: token-less operator setup keeps working (no 401)."""
        monkeypatch.delenv("BOBA_API_TOKEN", raising=False)
        resp = client.post(
            "/api/v1/magnet",
            json={"result_id": "x", "download_urls": ["magnet:?xt=urn:btih:" + "a" * 40]},
        )
        assert resp.status_code == 200
        assert resp.json()["magnet"].startswith("magnet:?dn=")
