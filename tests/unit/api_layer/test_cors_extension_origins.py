"""
BE-1 — CORS must allow browser-extension origins (BobaLink extension).

A browser extension's background fetch sends ``Origin: chrome-extension://<id>``
or ``Origin: moz-extension://<id>``. The merge service must echo that origin
back in ``Access-Control-Allow-Origin`` so the extension's cross-origin call
is not blocked by the browser.

§11.4.43 / §11.4.115 RED-first: against the pre-fix code (the default
allowlist is a fixed list of localhost origins with NO extension-scheme
support) the assertions below FAIL — Starlette omits the ACAO header for an
unrecognised origin, so the extension is blocked. After the fix (an
``allow_origin_regex`` covering ``chrome-extension://`` + ``moz-extension://``)
they GREEN.

Anti-bluff (§11.4.107): assertions inspect the user-observable response header
the browser actually consults (``Access-Control-Allow-Origin``), not just the
status code — a stub that 200s without the header still FAILs.
"""

import importlib
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SRC_PATH = _REPO_ROOT / "download-proxy" / "src"
if str(_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(_SRC_PATH))


def _purge_api_module() -> None:
    for key in [k for k in list(sys.modules) if k == "api" or k.startswith("api.")]:
        del sys.modules[key]


def _import_api_with_env(monkeypatch, allowed_origins):
    """Re-import the api package so module-level CORS config re-evaluates."""
    _purge_api_module()
    if allowed_origins is None:
        monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    else:
        monkeypatch.setenv("ALLOWED_ORIGINS", allowed_origins)
    import api

    return importlib.reload(api) if "api" in sys.modules else api


def _preflight_acao(client, origin):
    resp = client.options(
        "/api/v1/stats",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
        },
    )
    return resp.headers.get("access-control-allow-origin")


def _simple_acao(client, origin):
    resp = client.get("/api/v1/stats", headers={"Origin": origin})
    return resp.headers.get("access-control-allow-origin")


class TestExtensionOriginsAllowed:
    CHROME = "chrome-extension://abcdefghijklmnopabcdefghijklmnop"
    FIREFOX = "moz-extension://12345678-1234-1234-1234-1234567890ab"

    def test_chrome_extension_origin_preflight_allowed(self, monkeypatch):
        api = _import_api_with_env(monkeypatch, None)
        client = TestClient(api.app)
        assert _preflight_acao(client, self.CHROME) == self.CHROME

    def test_firefox_extension_origin_preflight_allowed(self, monkeypatch):
        api = _import_api_with_env(monkeypatch, None)
        client = TestClient(api.app)
        assert _preflight_acao(client, self.FIREFOX) == self.FIREFOX

    def test_chrome_extension_origin_simple_request_allowed(self, monkeypatch):
        api = _import_api_with_env(monkeypatch, None)
        client = TestClient(api.app)
        assert _simple_acao(client, self.CHROME) == self.CHROME


class TestExistingOriginsStillWork:
    """The extension support must NOT break the localhost dashboard origins."""

    def test_localhost_dashboard_origin_still_allowed(self, monkeypatch):
        api = _import_api_with_env(monkeypatch, None)
        client = TestClient(api.app)
        assert _preflight_acao(client, "http://localhost:4200") == "http://localhost:4200"

    def test_merge_service_origin_still_allowed(self, monkeypatch):
        api = _import_api_with_env(monkeypatch, None)
        port = api._MERGE_PORT
        origin = f"http://localhost:{port}"
        client = TestClient(api.app)
        assert _preflight_acao(client, origin) == origin


class TestUnknownOriginsStillRejected:
    """A random website must still NOT be granted the ACAO header."""

    def test_evil_website_origin_rejected(self, monkeypatch):
        api = _import_api_with_env(monkeypatch, None)
        client = TestClient(api.app)
        acao = _preflight_acao(client, "http://evil.example")
        assert acao != "http://evil.example"
        assert acao != "*"

    def test_extension_scheme_lookalike_on_other_host_rejected(self, monkeypatch):
        """An http origin that merely contains 'chrome-extension' must not match."""
        api = _import_api_with_env(monkeypatch, None)
        client = TestClient(api.app)
        acao = _preflight_acao(client, "http://chrome-extension.evil.example")
        assert acao != "http://chrome-extension.evil.example"
        assert acao != "*"


@pytest.fixture(autouse=True)
def _restore_api_module():
    yield
    _purge_api_module()
