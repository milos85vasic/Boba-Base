"""
CORS configuration tests — the default origin policy must NOT be a
wildcard, and the ALLOWED_ORIGINS env var must override it (including an
explicit opt-in back to "*").

§11.4.43 RED-first: against the pre-fix code (_DEFAULT_ORIGINS == ["*"])
the default-policy assertions below FAIL, proving they catch the wide-open
default. After the fix they GREEN.
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


class TestCorsDefault:
    def test_default_origins_are_not_wildcard(self, monkeypatch):
        api = _import_api_with_env(monkeypatch, None)
        assert "*" not in api._DEFAULT_ORIGINS, (
            "Default CORS policy must not be wide-open; tighten _DEFAULT_ORIGINS"
        )
        assert api._allowed_origins, "default allowlist must be non-empty"
        assert "*" not in api._allowed_origins

    def test_default_allows_localhost_dashboard_origin(self, monkeypatch):
        api = _import_api_with_env(monkeypatch, None)
        # The Angular dev server + the served SPA must keep working.
        assert any("localhost" in o or "127.0.0.1" in o for o in api._allowed_origins)

    def test_preflight_from_unknown_origin_is_not_allowed(self, monkeypatch):
        api = _import_api_with_env(monkeypatch, None)
        client = TestClient(api.app)
        resp = client.options(
            "/api/v1/stats",
            headers={
                "Origin": "http://evil.example",
                "Access-Control-Request-Method": "GET",
            },
        )
        # Starlette omits the ACAO header entirely when the origin is rejected.
        acao = resp.headers.get("access-control-allow-origin")
        assert acao != "http://evil.example"
        assert acao != "*"


class TestCorsEnvOverride:
    def test_env_allowlist_is_honored(self, monkeypatch):
        api = _import_api_with_env(monkeypatch, "https://app.example.com")
        assert api._allowed_origins == ["https://app.example.com"]
        client = TestClient(api.app)
        resp = client.options(
            "/api/v1/stats",
            headers={
                "Origin": "https://app.example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.headers.get("access-control-allow-origin") == "https://app.example.com"

    def test_explicit_wildcard_optin_still_works(self, monkeypatch):
        api = _import_api_with_env(monkeypatch, "*")
        assert api._allowed_origins == ["*"]

    def test_csv_parsing_and_whitespace(self, monkeypatch):
        api = _import_api_with_env(monkeypatch, " http://a.test , http://b.test ,")
        assert api._allowed_origins == ["http://a.test", "http://b.test"]


@pytest.fixture(autouse=True)
def _restore_api_module():
    yield
    _purge_api_module()
