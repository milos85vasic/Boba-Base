"""BOB-006: NNMClub username/password -> session-cookie login.

These tests prove the operator-provided NNMCLUB_USERNAME / NNMCLUB_PASSWORD
are actually used (today the code consumes only NNMCLUB_COOKIES).

RED-first (CONST §11.4.43 / §11.4.115): each test fails against the
pre-BOB-006 code (nnmclub only enabled via NNMCLUB_COOKIES; _search_nnmclub
returns [] when cookies are unset).

Mocks are used ONLY here in unit tests (CONST §11.4.27).
"""

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SRC_PATH = _REPO_ROOT / "download-proxy" / "src"
_MS_PATH = _SRC_PATH / "merge_service"
if str(_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(_SRC_PATH))

sys.modules.setdefault("merge_service", type(sys)("merge_service"))
sys.modules["merge_service"].__path__ = [str(_MS_PATH)]


def _make_orch():
    from merge_service.search import SearchOrchestrator

    return SearchOrchestrator()


# --- Enablement + auth-availability -------------------------------------


class TestNnmclubEnabledByCredentials:
    def test_enabled_when_username_password_set(self, monkeypatch):
        for k in ("NNMCLUB_COOKIES",):
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setenv("NNMCLUB_USERNAME", "alice")
        monkeypatch.setenv("NNMCLUB_PASSWORD", "s3cret")

        orch = _make_orch()
        names = {t.name for t in orch._get_enabled_trackers()}
        assert "nnmclub" in names

    def test_auth_available_when_username_password_set(self, monkeypatch):
        monkeypatch.delenv("NNMCLUB_COOKIES", raising=False)
        monkeypatch.setenv("NNMCLUB_USERNAME", "alice")
        monkeypatch.setenv("NNMCLUB_PASSWORD", "s3cret")

        orch = _make_orch()
        assert orch._is_tracker_authenticated("nnmclub") is True

    def test_still_enabled_via_cookies_only(self, monkeypatch):
        monkeypatch.delenv("NNMCLUB_USERNAME", raising=False)
        monkeypatch.delenv("NNMCLUB_PASSWORD", raising=False)
        monkeypatch.setenv("NNMCLUB_COOKIES", "phpbb2mysql_4_sid=abc")

        orch = _make_orch()
        names = {t.name for t in orch._get_enabled_trackers()}
        assert "nnmclub" in names
        assert orch._is_tracker_authenticated("nnmclub") is True

    def test_not_enabled_without_any_credentials(self, monkeypatch):
        for k in ("NNMCLUB_COOKIES", "NNMCLUB_USERNAME", "NNMCLUB_PASSWORD"):
            monkeypatch.delenv(k, raising=False)

        orch = _make_orch()
        names = {t.name for t in orch._get_enabled_trackers()}
        assert "nnmclub" not in names
        assert orch._is_tracker_authenticated("nnmclub") is False

    def test_username_only_not_enough(self, monkeypatch):
        for k in ("NNMCLUB_COOKIES", "NNMCLUB_PASSWORD"):
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setenv("NNMCLUB_USERNAME", "alice")

        orch = _make_orch()
        names = {t.name for t in orch._get_enabled_trackers()}
        assert "nnmclub" not in names
        assert orch._is_tracker_authenticated("nnmclub") is False


# --- Login path stores a real session cookie ----------------------------


class _FakeCookie:
    def __init__(self, key, value):
        self.key = key
        self.value = value


class _FakeCookies:
    def __init__(self, mapping):
        self._m = {k: _FakeCookie(k, v) for k, v in mapping.items()}

    def values(self):
        return self._m.values()


class _FakeResp:
    def __init__(self, *, cookies=None, body=b""):
        self.cookies = _FakeCookies(cookies or {})
        self._body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def read(self):
        return self._body

    async def text(self):
        return self._body.decode("cp1251", "ignore")


class _FakeSession:
    """aiohttp.ClientSession stand-in.

    POST (login) -> returns the login response carrying Set-Cookie.
    GET (search) -> returns an empty results page.
    """

    def __init__(self, *, login_cookies):
        self._login_cookies = login_cookies

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def post(self, *a, **k):
        return _FakeResp(cookies=self._login_cookies)

    def get(self, *a, **k):
        return _FakeResp(body=b"<html>no results</html>")


@pytest.mark.asyncio
async def test_login_stores_session_cookie(monkeypatch):
    monkeypatch.delenv("NNMCLUB_COOKIES", raising=False)
    monkeypatch.setenv("NNMCLUB_USERNAME", "alice")
    monkeypatch.setenv("NNMCLUB_PASSWORD", "s3cret")

    orch = _make_orch()

    fake = _FakeSession(login_cookies={"phpbb2mysql_4_sid": "SID123", "other": "x"})
    with patch("aiohttp.ClientSession", return_value=fake):
        await orch._search_nnmclub("ubuntu", "all")

    session = orch._tracker_sessions.get("nnmclub")
    assert session is not None, "login must populate _tracker_sessions['nnmclub']"
    assert session["base_url"] == "https://nnm-club.me"
    assert session["cookies"].get("phpbb2mysql_4_sid") == "SID123"


@pytest.mark.asyncio
async def test_login_does_not_leak_credentials_into_session(monkeypatch):
    monkeypatch.delenv("NNMCLUB_COOKIES", raising=False)
    monkeypatch.setenv("NNMCLUB_USERNAME", "alice")
    monkeypatch.setenv("NNMCLUB_PASSWORD", "s3cret")

    orch = _make_orch()
    fake = _FakeSession(login_cookies={"phpbb2mysql_4_sid": "SID123"})
    with patch("aiohttp.ClientSession", return_value=fake):
        await orch._search_nnmclub("ubuntu", "all")

    session = orch._tracker_sessions.get("nnmclub")
    blob = repr(session)
    assert "s3cret" not in blob
    assert "alice" not in blob


@pytest.mark.asyncio
async def test_login_graceful_when_no_session_cookie(monkeypatch):
    """Login returning no phpbb2mysql_4_sid cookie must NOT crash and must
    NOT store a bogus session."""
    monkeypatch.delenv("NNMCLUB_COOKIES", raising=False)
    monkeypatch.setenv("NNMCLUB_USERNAME", "alice")
    monkeypatch.setenv("NNMCLUB_PASSWORD", "wrong")

    orch = _make_orch()
    fake = _FakeSession(login_cookies={"unrelated": "x"})
    with patch("aiohttp.ClientSession", return_value=fake):
        results = await orch._search_nnmclub("ubuntu", "all")

    assert results == []
    assert orch._tracker_sessions.get("nnmclub") is None


@pytest.mark.asyncio
async def test_cookies_take_precedence_over_password(monkeypatch):
    """When NNMCLUB_COOKIES is set the existing cookie path is used (no login
    POST required)."""
    monkeypatch.setenv("NNMCLUB_COOKIES", "phpbb2mysql_4_sid=COOKIESID")
    monkeypatch.setenv("NNMCLUB_USERNAME", "alice")
    monkeypatch.setenv("NNMCLUB_PASSWORD", "s3cret")

    orch = _make_orch()

    class _CookieOnlySession(_FakeSession):
        def post(self, *a, **k):  # pragma: no cover - must not be called
            raise AssertionError("login POST must not run when cookies are set")

    fake = _CookieOnlySession(login_cookies={})
    with patch("aiohttp.ClientSession", return_value=fake):
        await orch._search_nnmclub("ubuntu", "all")

    session = orch._tracker_sessions.get("nnmclub")
    assert session is not None
    assert session["cookies"].get("phpbb2mysql_4_sid") == "COOKIESID"
