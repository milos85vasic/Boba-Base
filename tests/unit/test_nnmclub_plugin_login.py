"""BOB-006: nnmclub plugin username/password login fallback.

The plugin previously only authenticated via raw cookies (config.cookies).
When no cookies are configured but username+password are, login() must fall
back to a POST-based session login that populates the cookie jar with
``phpbb2mysql_4_sid``.

RED-first (CONST §11.4.43): fails against pre-BOB-006 plugin (login() raises
"Empty cookies in config file" with no password fallback; Config has no
password field).

Mocks used ONLY here in unit tests (CONST §11.4.27).
"""

import importlib.util
import sys
import types
from http.cookiejar import Cookie
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def nnmclub_mod(tmp_path, monkeypatch):
    """Import the plugin with novaprinter/socks stubbed (qBittorrent nova3
    deps not present in the test env) and a temp cwd so the real
    plugins/nnmclub.json is never touched."""
    monkeypatch.chdir(tmp_path)

    np_mod = types.ModuleType("novaprinter")
    np_mod.prettyPrinter = lambda d: None  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "novaprinter", np_mod)

    if "socks" not in sys.modules:
        socks_stub = types.ModuleType("socks")
        socks_stub.PROXY_TYPE_SOCKS5 = 2  # type: ignore[attr-defined]
        socks_stub.set_default_proxy = lambda *a, **k: None  # type: ignore[attr-defined]
        socks_stub.socksocket = object  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "socks", socks_stub)

    for k in [k for k in list(sys.modules) if k == "nnmclub_under_test"]:
        del sys.modules[k]
    spec = importlib.util.spec_from_file_location(
        "nnmclub_under_test", str(_REPO_ROOT / "plugins" / "nnmclub.py")
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["nnmclub_under_test"] = mod
    spec.loader.exec_module(mod)
    base = tmp_path / "store"
    base.mkdir()
    monkeypatch.setattr(mod, "FILE_C", base / "nnmclub.cookie")
    monkeypatch.setattr(mod, "FILE_J", base / "nnmclub.json")
    monkeypatch.setattr(mod, "FILE_L", base / "nnmclub.log")
    return mod


def _make_cookie(name, value):
    return Cookie(
        0, name, value, None, False, "nnmclub.to", True, False,
        "/", True, False, None, False, None, None, {},
    )


def test_config_has_password_field(nnmclub_mod):
    # The module-level config instance must expose the new password field
    # so credentials can be supplied via plugins/nnmclub.json.
    assert hasattr(nnmclub_mod.config, "password")
    assert "password" in nnmclub_mod.config.to_dict()


def test_password_login_populates_session_cookie(nnmclub_mod, monkeypatch):
    mod = nnmclub_mod
    monkeypatch.setattr(mod.config, "cookies", "COOKIES")
    monkeypatch.setattr(mod.config, "username", "alice")
    monkeypatch.setattr(mod.config, "password", "s3cret")

    engine = mod.nnmclub()

    captured = {}

    def fake_request(url, data=None, repeated=False):
        captured["url"] = url
        captured["data"] = data
        # Simulate server Set-Cookie landing in the shared jar.
        engine.mcj.set_cookie(_make_cookie("phpbb2mysql_4_sid", "SID42"))
        return b""

    monkeypatch.setattr(engine, "_request", fake_request)

    engine.login()

    assert "login.php" in captured["url"]
    # credentials must not appear in the dispatched data as plaintext kwargs
    # but ARE in the urlencoded body (cp1251) — verify the session cookie set.
    names = [c.name for c in engine.mcj]
    assert "phpbb2mysql_4_sid" in names


def test_password_login_raises_without_session_cookie(nnmclub_mod, monkeypatch):
    mod = nnmclub_mod
    monkeypatch.setattr(mod.config, "cookies", "COOKIES")
    monkeypatch.setattr(mod.config, "username", "alice")
    monkeypatch.setattr(mod.config, "password", "wrong")

    engine = mod.nnmclub()
    monkeypatch.setattr(engine, "_request", lambda *a, **k: b"")

    with pytest.raises(mod.EngineError):
        engine.login()


def test_login_still_raises_when_no_creds_and_no_cookies(nnmclub_mod, monkeypatch):
    mod = nnmclub_mod
    monkeypatch.setattr(mod.config, "cookies", "COOKIES")
    monkeypatch.setattr(mod.config, "username", "USERNAME")
    monkeypatch.setattr(mod.config, "password", "PASSWORD")

    engine = mod.nnmclub()
    with pytest.raises(mod.EngineError):
        engine.login()
