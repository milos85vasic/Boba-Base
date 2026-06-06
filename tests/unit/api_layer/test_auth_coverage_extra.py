"""
Extra coverage for api/auth.py — the RuTracker CAPTCHA flow
(fetch_captcha + login_with_captcha) and remaining branches not covered by
tests/unit/test_auth_coverage.py.

Unit tests: orchestrator + aiohttp are mocked, no real network. Assertions
inspect returned bodies, HTTP status codes, and the captcha-token store
state (anti-bluff).
"""

import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SRC_PATH = _REPO_ROOT / "download-proxy" / "src"
if str(_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(_SRC_PATH))


def _aiohttp_response(text="", status=200, read_bytes=b""):
    resp = AsyncMock()
    resp.text = AsyncMock(return_value=text)
    resp.read = AsyncMock(return_value=read_bytes)
    resp.status = status
    resp.cookies = {}
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


def _session_returning(get_responses=None, post_responses=None):
    session = AsyncMock()
    if get_responses is not None:
        session.get = MagicMock(side_effect=get_responses)
    if post_responses is not None:
        session.post = MagicMock(side_effect=post_responses)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


CAPTCHA_HTML = (
    '<form><img src="https://static.rutracker.cc/captcha/abc.png">'
    '<input name="cap_sid" value="SID123">'
    '<input name="cap_code_field_xyz" value=""></form>'
)


class TestFetchCaptcha:
    @pytest.mark.asyncio
    async def test_missing_credentials_400(self):
        from api.auth import rutracker_fetch_captcha

        orch = MagicMock()
        orch._load_env = MagicMock()
        with (
            patch("api.auth._get_orchestrator", return_value=orch),
            patch.dict(os.environ, {}, clear=True),
        ):
            with pytest.raises(Exception) as exc:
                await rutracker_fetch_captcha()
            assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_captcha_detected(self):
        from api.auth import rutracker_fetch_captcha
        import api.auth as auth_mod

        orch = MagicMock()
        orch._load_env = MagicMock()
        orch._tracker_sessions = {}
        # login.php GET returns the captcha form; captcha image GET returns bytes.
        login_page = _aiohttp_response(text=CAPTCHA_HTML, status=200)
        img = _aiohttp_response(read_bytes=b"\x89PNG", status=200)
        session = _session_returning(get_responses=[login_page, img])
        with (
            patch("api.auth._get_orchestrator", return_value=orch),
            patch.dict(os.environ, {"RUTRACKER_USERNAME": "u", "RUTRACKER_PASSWORD": "p"}, clear=False),
            patch("aiohttp.ClientSession", return_value=session),
            patch("aiohttp.ClientTimeout", return_value=None),
        ):
            result = await rutracker_fetch_captcha()
        assert result["captcha_required"] is True
        token = result["captcha_token"]
        assert token
        # The token must be persisted in the pending-captcha store.
        assert token in auth_mod._pending_captchas
        assert auth_mod._pending_captchas[token]["cap_sid"] == "SID123"

    @pytest.mark.asyncio
    async def test_no_captcha_logged_in_directly(self):
        """No captcha image on first page; secondary login succeeds via cookie."""
        from api.auth import rutracker_fetch_captcha

        orch = MagicMock()
        orch._load_env = MagicMock()
        orch._tracker_sessions = {}
        plain = _aiohttp_response(text="<html>no captcha here</html>", status=200)
        login_ok = _aiohttp_response(text="<html>welcome</html>", status=200)
        # cookies on the login POST carry bb_session
        cookie = MagicMock()
        cookie.key = "bb_session"
        cookie.value = "sess"
        login_ok.cookies = {"bb_session": cookie}
        session = AsyncMock()
        session.get = MagicMock(side_effect=[plain])
        session.post = MagicMock(side_effect=[login_ok])
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        with (
            patch("api.auth._get_orchestrator", return_value=orch),
            patch.dict(os.environ, {"RUTRACKER_USERNAME": "u", "RUTRACKER_PASSWORD": "p"}, clear=False),
            patch("aiohttp.ClientSession", return_value=session),
            patch("aiohttp.ClientTimeout", return_value=None),
        ):
            result = await rutracker_fetch_captcha()
        assert result["captcha_required"] is False
        assert result["authenticated"] is True
        assert orch._tracker_sessions["rutracker"]["cookies"]["bb_session"] == "sess"

    @pytest.mark.asyncio
    async def test_no_captcha_no_login(self):
        """No captcha and secondary login does not authenticate -> informative msg."""
        from api.auth import rutracker_fetch_captcha

        orch = MagicMock()
        orch._load_env = MagicMock()
        orch._tracker_sessions = {}
        plain = _aiohttp_response(text="<html>no captcha here</html>", status=200)
        login_fail = _aiohttp_response(text="<html>bad login</html>", status=200)
        session = AsyncMock()
        session.get = MagicMock(side_effect=[plain])
        session.post = MagicMock(side_effect=[login_fail])
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        with (
            patch("api.auth._get_orchestrator", return_value=orch),
            patch.dict(os.environ, {"RUTRACKER_USERNAME": "u", "RUTRACKER_PASSWORD": "p"}, clear=False),
            patch("aiohttp.ClientSession", return_value=session),
            patch("aiohttp.ClientTimeout", return_value=None),
        ):
            result = await rutracker_fetch_captcha()
        assert result["captcha_required"] is False
        assert result["authenticated"] is False
        assert "No CAPTCHA found" in result["message"]

    @pytest.mark.asyncio
    async def test_network_error_502(self):
        from api.auth import rutracker_fetch_captcha

        orch = MagicMock()
        orch._load_env = MagicMock()
        with (
            patch("api.auth._get_orchestrator", return_value=orch),
            patch.dict(os.environ, {"RUTRACKER_USERNAME": "u", "RUTRACKER_PASSWORD": "p"}, clear=False),
            patch("aiohttp.ClientSession", side_effect=Exception("network down")),
        ):
            with pytest.raises(Exception) as exc:
                await rutracker_fetch_captcha()
            assert exc.value.status_code == 502


class TestLoginWithCaptcha:
    @pytest.mark.asyncio
    async def test_missing_credentials_400(self):
        from api.auth import rutracker_login_with_captcha, CaptchaLoginRequest

        orch = MagicMock()
        orch._load_env = MagicMock()
        req = CaptchaLoginRequest(
            cap_sid="s", cap_code_field="c", captcha_text="t", captcha_token="tok"
        )
        with (
            patch("api.auth._get_orchestrator", return_value=orch),
            patch.dict(os.environ, {}, clear=True),
        ):
            with pytest.raises(Exception) as exc:
                await rutracker_login_with_captcha(req)
            assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_invalid_token_400(self):
        from api.auth import rutracker_login_with_captcha, CaptchaLoginRequest

        orch = MagicMock()
        orch._load_env = MagicMock()
        req = CaptchaLoginRequest(
            cap_sid="s", cap_code_field="c", captcha_text="t", captcha_token="does-not-exist"
        )
        with (
            patch("api.auth._get_orchestrator", return_value=orch),
            patch.dict(os.environ, {"RUTRACKER_USERNAME": "u", "RUTRACKER_PASSWORD": "p"}, clear=False),
        ):
            with pytest.raises(Exception) as exc:
                await rutracker_login_with_captcha(req)
            assert exc.value.status_code == 400
            assert "Invalid or expired captcha_token" in exc.value.detail

    @pytest.mark.asyncio
    async def test_successful_login(self):
        from api.auth import rutracker_login_with_captcha, CaptchaLoginRequest
        import api.auth as auth_mod

        orch = MagicMock()
        orch._load_env = MagicMock()
        orch._tracker_sessions = {}
        token = "valid-token-1"
        auth_mod._pending_captchas[token] = {
            "cap_sid": "SID",
            "cap_code_field": "cap_code_x",
            "base_url": "https://rutracker.org",
        }
        login_ok = _aiohttp_response(text='<span id="logged-in-username">u</span>', status=200)
        session = _session_returning(post_responses=[login_ok])
        req = CaptchaLoginRequest(
            cap_sid="SID", cap_code_field="cap_code_x", captcha_text="abcd", captcha_token=token
        )
        with (
            patch("api.auth._get_orchestrator", return_value=orch),
            patch.dict(os.environ, {"RUTRACKER_USERNAME": "u", "RUTRACKER_PASSWORD": "p"}, clear=False),
            patch("aiohttp.ClientSession", return_value=session),
        ):
            result = await rutracker_login_with_captcha(req)
        assert result["authenticated"] is True
        assert orch._tracker_sessions["rutracker"]["base_url"] == "https://rutracker.org"
        # token consumed
        assert token not in auth_mod._pending_captchas

    @pytest.mark.asyncio
    async def test_wrong_captcha_returns_new_one(self):
        from api.auth import rutracker_login_with_captcha, CaptchaLoginRequest
        import api.auth as auth_mod

        orch = MagicMock()
        orch._load_env = MagicMock()
        orch._tracker_sessions = {}
        token = "valid-token-2"
        auth_mod._pending_captchas[token] = {
            "cap_sid": "SID",
            "cap_code_field": "cap_code_x",
            "base_url": "https://rutracker.org",
        }
        # login response: not authed, but a fresh captcha form present
        login_retry = _aiohttp_response(text=CAPTCHA_HTML, status=200)
        img = _aiohttp_response(read_bytes=b"\x89PNG", status=200)
        session = AsyncMock()
        session.post = MagicMock(side_effect=[login_retry])
        session.get = MagicMock(side_effect=[img])
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        req = CaptchaLoginRequest(
            cap_sid="SID", cap_code_field="cap_code_x", captcha_text="wrong", captcha_token=token
        )
        with (
            patch("api.auth._get_orchestrator", return_value=orch),
            patch.dict(os.environ, {"RUTRACKER_USERNAME": "u", "RUTRACKER_PASSWORD": "p"}, clear=False),
            patch("aiohttp.ClientSession", return_value=session),
        ):
            result = await rutracker_login_with_captcha(req)
        assert result["authenticated"] is False
        assert result["captcha_required"] is True
        new_token = result["captcha_token"]
        assert new_token and new_token != token
        assert new_token in auth_mod._pending_captchas

    @pytest.mark.asyncio
    async def test_login_failure_no_captcha(self):
        from api.auth import rutracker_login_with_captcha, CaptchaLoginRequest
        import api.auth as auth_mod

        orch = MagicMock()
        orch._load_env = MagicMock()
        orch._tracker_sessions = {}
        token = "valid-token-3"
        auth_mod._pending_captchas[token] = {
            "cap_sid": "SID",
            "cap_code_field": "cap_code_x",
            "base_url": "https://rutracker.org",
        }
        login_fail = _aiohttp_response(text="<html>nope</html>", status=200)
        session = _session_returning(post_responses=[login_fail])
        req = CaptchaLoginRequest(
            cap_sid="SID", cap_code_field="cap_code_x", captcha_text="bad", captcha_token=token
        )
        with (
            patch("api.auth._get_orchestrator", return_value=orch),
            patch.dict(os.environ, {"RUTRACKER_USERNAME": "u", "RUTRACKER_PASSWORD": "p"}, clear=False),
            patch("aiohttp.ClientSession", return_value=session),
        ):
            result = await rutracker_login_with_captcha(req)
        assert result["authenticated"] is False
        assert "Login failed" in result["message"]

    @pytest.mark.asyncio
    async def test_network_error_500(self):
        from api.auth import rutracker_login_with_captcha, CaptchaLoginRequest
        import api.auth as auth_mod

        orch = MagicMock()
        orch._load_env = MagicMock()
        token = "valid-token-4"
        auth_mod._pending_captchas[token] = {
            "cap_sid": "SID",
            "cap_code_field": "cap_code_x",
            "base_url": "https://rutracker.org",
        }
        req = CaptchaLoginRequest(
            cap_sid="SID", cap_code_field="cap_code_x", captcha_text="x", captcha_token=token
        )
        with (
            patch("api.auth._get_orchestrator", return_value=orch),
            patch.dict(os.environ, {"RUTRACKER_USERNAME": "u", "RUTRACKER_PASSWORD": "p"}, clear=False),
            patch("aiohttp.ClientSession", side_effect=Exception("boom")),
        ):
            with pytest.raises(Exception) as exc:
                await rutracker_login_with_captcha(req)
            assert exc.value.status_code == 500


class TestCookieLoginNetworkError:
    @pytest.mark.asyncio
    async def test_verify_network_error_502(self):
        from api.auth import rutracker_cookie_login, CookieLoginRequest

        orch = MagicMock()
        req = CookieLoginRequest(cookie_string="bb_session=abc123")
        with (
            patch("api.auth._get_orchestrator", return_value=orch),
            patch("aiohttp.ClientSession", side_effect=Exception("dns fail")),
        ):
            with pytest.raises(Exception) as exc:
                await rutracker_cookie_login(req)
            assert exc.value.status_code == 502


class TestAllTrackersStatusQbitException:
    @pytest.mark.asyncio
    async def test_qbit_probe_exception_swallowed(self):
        from api.auth import all_trackers_auth_status

        orch = MagicMock()
        orch._tracker_sessions = {}
        with (
            patch("api.auth._get_orchestrator", return_value=orch),
            patch("api.auth._load_qbit_credentials", return_value={"username": "a", "password": "b"}),
            patch("aiohttp.ClientSession", side_effect=Exception("qbit down")),
        ):
            result = await all_trackers_auth_status()
        # Exception swallowed -> has_session stays False but username reported.
        assert result["trackers"]["qbittorrent"]["has_session"] is False
        assert result["trackers"]["qbittorrent"]["username"] == "a"
