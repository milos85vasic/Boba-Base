"""
Additional coverage for api/auth.py — status, cookie-login, captcha flow, logout.
"""

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "download-proxy", "src"))


class TestGetOrchestrator:
    def test_returns_global_instance_when_set(self):
        import api

        mock_orch = MagicMock()
        with patch.object(api, "orchestrator_instance", mock_orch):
            from api.auth import _get_orchestrator

            assert _get_orchestrator() is mock_orch

    def test_creates_new_when_none(self):
        import api

        with patch.object(api, "orchestrator_instance", None):
            from api.auth import _get_orchestrator

            orch = _get_orchestrator()
            assert orch is not None


class TestRutrackerAuthStatus:
    @pytest.mark.asyncio
    async def test_no_session(self):
        from api.auth import rutracker_auth_status

        mock_orch = MagicMock()
        mock_orch._tracker_sessions = {}
        with patch("api.auth._get_orchestrator", return_value=mock_orch):
            result = await rutracker_auth_status()
            assert result["authenticated"] is False
            assert result["status"] == "no_session"

    @pytest.mark.asyncio
    async def test_session_no_cookie(self):
        from api.auth import rutracker_auth_status

        mock_orch = MagicMock()
        mock_orch._tracker_sessions = {"rutracker": {"cookies": {}, "base_url": "https://rutracker.org"}}
        with patch("api.auth._get_orchestrator", return_value=mock_orch):
            result = await rutracker_auth_status()
            assert result["authenticated"] is False
            assert result["status"] == "no_cookie"

    @pytest.mark.asyncio
    async def test_session_active(self):
        from api.auth import rutracker_auth_status

        mock_orch = MagicMock()
        mock_orch._tracker_sessions = {
            "rutracker": {
                "cookies": {"bb_session": "abc123"},
                "base_url": "https://rutracker.org",
            }
        }
        mock_resp = AsyncMock()
        mock_resp.text = AsyncMock(return_value='<span id="logged-in-username">user</span>')
        mock_resp.status = 200
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("api.auth._get_orchestrator", return_value=mock_orch),
            patch("aiohttp.ClientSession", return_value=mock_session),
            patch("aiohttp.ClientTimeout", return_value=None),
        ):
            result = await rutracker_auth_status()
            assert result["authenticated"] is True
            assert result["status"] == "active"

    @pytest.mark.asyncio
    async def test_session_expired(self):
        from api.auth import rutracker_auth_status

        mock_orch = MagicMock()
        mock_orch._tracker_sessions = {
            "rutracker": {
                "cookies": {"bb_session": "abc123"},
                "base_url": "https://rutracker.org",
            }
        }
        mock_resp = AsyncMock()
        mock_resp.text = AsyncMock(return_value="<html>login page</html>")
        mock_resp.status = 200
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("api.auth._get_orchestrator", return_value=mock_orch),
            patch("aiohttp.ClientSession", return_value=mock_session),
            patch("aiohttp.ClientTimeout", return_value=None),
        ):
            result = await rutracker_auth_status()
            assert result["authenticated"] is False
            assert result["status"] == "expired"

    @pytest.mark.asyncio
    async def test_connection_error(self):
        from api.auth import rutracker_auth_status

        mock_orch = MagicMock()
        mock_orch._tracker_sessions = {
            "rutracker": {
                "cookies": {"bb_session": "abc123"},
                "base_url": "https://rutracker.org",
            }
        }

        with (
            patch("api.auth._get_orchestrator", return_value=mock_orch),
            patch("aiohttp.ClientSession", side_effect=Exception("network error")),
        ):
            result = await rutracker_auth_status()
            assert result["authenticated"] is False
            assert result["status"] == "error"


class TestRutrackerCookieLogin:
    @pytest.mark.asyncio
    async def test_missing_bb_session(self):
        from api.auth import rutracker_cookie_login
        from api.auth import CookieLoginRequest

        req = CookieLoginRequest(cookie_string="sid=abc; other=def")
        with pytest.raises(Exception) as exc_info:
            await rutracker_cookie_login(req)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_invalid_cookie(self):
        from api.auth import rutracker_cookie_login
        from api.auth import CookieLoginRequest

        mock_orch = MagicMock()
        mock_resp = AsyncMock()
        mock_resp.text = AsyncMock(return_value="<html>login page</html>")
        mock_resp.status = 200
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        req = CookieLoginRequest(cookie_string="bb_session=abc123")
        with (
            patch("api.auth._get_orchestrator", return_value=mock_orch),
            patch("aiohttp.ClientSession", return_value=mock_session),
            patch("aiohttp.ClientTimeout", return_value=None),
        ):
            with pytest.raises(Exception) as exc_info:
                await rutracker_cookie_login(req)
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_valid_cookie(self):
        from api.auth import rutracker_cookie_login
        from api.auth import CookieLoginRequest

        mock_orch = MagicMock()
        mock_orch._tracker_sessions = {}
        mock_resp = AsyncMock()
        mock_resp.text = AsyncMock(return_value='<span id="logged-in-username">user</span>')
        mock_resp.status = 200
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        req = CookieLoginRequest(cookie_string="bb_session=abc123")
        with (
            patch("api.auth._get_orchestrator", return_value=mock_orch),
            patch("aiohttp.ClientSession", return_value=mock_session),
            patch("aiohttp.ClientTimeout", return_value=None),
        ):
            result = await rutracker_cookie_login(req)
            assert result["authenticated"] is True


class TestAllTrackersAuthStatus:
    @pytest.mark.asyncio
    async def test_all_trackers_status(self):
        from http.cookies import SimpleCookie

        from api.auth import all_trackers_auth_status

        mock_orch = MagicMock()
        mock_orch._tracker_sessions = {
            "rutracker": {"cookies": {"bb_session": "x"}, "base_url": "https://rutracker.org"}
        }
        mock_resp = AsyncMock()
        mock_resp.text = AsyncMock(return_value="Ok.")
        mock_resp.status = 200
        # Realistic cookie jar: modern qBittorrent sets a QBT_SID cookie on a
        # successful login. A bare AsyncMock for `.cookies` raises when the
        # has_session check iterates `.values()` — the exception is swallowed by
        # auth.py's `except: pass`, leaving has_session false and turning a real
        # product assertion into a §11.4.1 FAIL-bluff. SimpleCookie exercises the
        # genuine cookie-presence path.
        _jar = SimpleCookie()
        _jar["QBT_SID"] = "test-session-id"
        mock_resp.cookies = _jar
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("api.auth._get_orchestrator", return_value=mock_orch),
            patch("api.auth._load_qbit_credentials", return_value={"username": "admin", "password": "admin"}),
            patch("aiohttp.ClientSession", return_value=mock_session),
            patch("aiohttp.ClientTimeout", return_value=None),
        ):
            result = await all_trackers_auth_status()
            assert "trackers" in result
            assert result["trackers"]["rutracker"]["has_session"] is True
            assert result["trackers"]["qbittorrent"]["has_session"] is True

    @pytest.mark.asyncio
    async def test_no_credentials(self):
        from api.auth import all_trackers_auth_status

        mock_orch = MagicMock()
        mock_orch._tracker_sessions = {}

        with (
            patch("api.auth._get_orchestrator", return_value=mock_orch),
            patch("api.auth._load_qbit_credentials", return_value=None),
        ):
            result = await all_trackers_auth_status()
            assert result["trackers"]["qbittorrent"]["has_session"] is False


class TestQbittorrentLogout:
    @pytest.mark.asyncio
    async def test_logout_success(self):
        from api.auth import qbittorrent_logout

        with patch("os.path.exists", return_value=True), patch("os.remove"):
            result = await qbittorrent_logout()
            assert result["status"] == "logged_out"

    @pytest.mark.asyncio
    async def test_logout_no_file(self):
        from api.auth import qbittorrent_logout

        with patch("os.path.exists", return_value=False):
            result = await qbittorrent_logout()
            assert result["status"] == "logged_out"

    @pytest.mark.asyncio
    async def test_logout_error(self):
        from api.auth import qbittorrent_logout

        with patch("os.path.exists", return_value=True), patch("os.remove", side_effect=PermissionError("denied")):
            result = await qbittorrent_logout()
            assert result["status"] == "error"


class TestLoadQbitCredentialsEdge:
    def test_corrupt_json_file(self):
        from api.auth import _load_qbit_credentials

        with patch("os.path.exists", return_value=True), patch("builtins.open", side_effect=Exception("read error")):
            with patch.dict(os.environ, {"QBITTORRENT_USER": "u", "QBITTORRENT_PASS": "p"}, clear=False):
                creds = _load_qbit_credentials()
                assert creds is not None
                assert creds["username"] == "u"

    def test_fallback_to_env_vars(self):
        from api.auth import _load_qbit_credentials

        with (
            patch("os.path.exists", return_value=False),
            patch.dict(os.environ, {"QBITTORRENT_USERNAME": "envu", "QBITTORRENT_PASSWORD": "envp"}, clear=False),
        ):
            creds = _load_qbit_credentials()
            assert creds == {"username": "envu", "password": "envp"}
