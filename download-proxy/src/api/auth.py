"""
Tracker authentication endpoints — CAPTCHA proxy for RuTracker.
"""

import base64
import logging
import os
import re
import secrets
import sys

_src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from typing import Any  # noqa: E402

from fastapi import APIRouter, HTTPException  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# Bounded + self-expiring store for outstanding CAPTCHA challenges.
# Previously a plain dict that grew without bound and kept entries forever,
# leaking memory over long sessions.
from cachetools import TTLCache  # noqa: E402

_PENDING_CAPTCHAS_MAX = int(os.getenv("PENDING_CAPTCHAS_MAX", "1024"))
_PENDING_CAPTCHAS_TTL = int(os.getenv("PENDING_CAPTCHAS_TTL_SECONDS", "900"))
_pending_captchas: TTLCache[str, dict[str, Any]] = TTLCache(maxsize=_PENDING_CAPTCHAS_MAX, ttl=_PENDING_CAPTCHAS_TTL)


def _get_orchestrator() -> Any:
    from api import orchestrator_instance

    if orchestrator_instance is not None:
        return orchestrator_instance
    from merge_service.search import SearchOrchestrator

    return SearchOrchestrator()


class CaptchaLoginRequest(BaseModel):
    cap_sid: str = Field(..., description="CAPTCHA session ID")
    cap_code_field: str = Field(..., description="CAPTCHA code field name")
    captcha_text: str = Field(..., description="User-entered CAPTCHA text")
    captcha_token: str = Field(..., description="Token from /captcha endpoint")


class CookieLoginRequest(BaseModel):
    cookie_string: str = Field(..., description="Full cookie string from browser")


@router.get("/rutracker/status")
async def rutracker_auth_status():  # type: ignore[no-untyped-def]
    orch = _get_orchestrator()
    session = orch._tracker_sessions.get("rutracker")

    if not session:
        return {
            "authenticated": False,
            "status": "no_session",
            "message": "No RuTracker session found. Login required.",
        }

    cookies = session.get("cookies", {})
    if "bb_session" not in cookies:
        return {
            "authenticated": False,
            "status": "no_cookie",
            "message": "Session exists but no valid cookie. Re-login required.",
        }

    import aiohttp

    base_url = session.get("base_url", "https://rutracker.org")
    try:
        async with (
            aiohttp.ClientSession() as client,
            client.get(
                f"{base_url}/forum/index.php",
                cookies=cookies,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp,
        ):
            text = await resp.text()
            if 'id="logged-in-username"' in text:
                return {
                    "authenticated": True,
                    "status": "active",
                    "message": "RuTracker session is active.",
                }
            return {
                "authenticated": False,
                "status": "expired",
                "message": "Session expired. Re-login required.",
            }
    except Exception as e:
        return {
            "authenticated": False,
            "status": "error",
            "message": f"Could not verify session: {e}",
        }


@router.get("/rutracker/captcha")
async def rutracker_fetch_captcha():  # type: ignore[no-untyped-def]
    import aiohttp

    orch = _get_orchestrator()
    orch._load_env()

    username = os.getenv("RUTRACKER_USERNAME")
    password = os.getenv("RUTRACKER_PASSWORD")

    if not username or not password:
        raise HTTPException(
            status_code=400,
            detail="RUTRACKER_USERNAME and RUTRACKER_PASSWORD not configured",
        )

    base_url = os.getenv("RUTRACKER_MIRRORS", "https://rutracker.org").split(",")[0].strip()

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{base_url}/forum/login.php",
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                login_html = await resp.text()

            captcha_img = re.search(
                r'<img[^>]+src="(https://static\.rutracker\.cc/captcha/[^"]+)"',
                login_html,
            )

            if not captcha_img:
                try:
                    async with session.post(
                        f"{base_url}/forum/login.php",
                        data={
                            "login_username": username,
                            "login_password": password,
                            "login": "\u0412\u0445\u043e\u0434",
                        },
                    ) as login_resp:
                        login_text = await login_resp.text()
                        cookies = {c.key: c.value for c in login_resp.cookies.values()}

                    if 'id="logged-in-username"' in login_text or "bb_session" in cookies:
                        orch._tracker_sessions["rutracker"] = {
                            "cookies": cookies,
                            "base_url": base_url,
                        }
                        return {
                            "captcha_required": False,
                            "authenticated": True,
                            "message": "Logged in successfully without CAPTCHA.",
                        }

                    captcha_img = re.search(
                        r'<img[^>]+src="(https://static\.rutracker\.cc/captcha/[^"]+)"',
                        login_text,
                    )
                    if not captcha_img:
                        login_html = login_text
                except Exception as e:
                    logger.debug(f"Secondary login page fetch failed: {e}")

            if not captcha_img:
                return {
                    "captcha_required": False,
                    "authenticated": False,
                    "message": "No CAPTCHA found on login page. Try logging in directly.",
                }

            cap_sid_match = re.search(r'name="cap_sid"\s+value="([^"]+)"', login_html)
            cap_code_match = re.search(r'name="(cap_code_[^"]+)"', login_html)

            if not cap_sid_match or not cap_code_match:
                raise HTTPException(
                    status_code=502,
                    detail="Could not parse CAPTCHA form fields from login page",
                )

            captcha_image_url = captcha_img.group(1)
            async with session.get(captcha_image_url) as img_resp:
                img_bytes = await img_resp.read()
                img_b64 = base64.b64encode(img_bytes).decode()

            captcha_token = secrets.token_urlsafe(32)
            _pending_captchas[captcha_token] = {
                "cap_sid": cap_sid_match.group(1),
                "cap_code_field": cap_code_match.group(1),
                "base_url": base_url,
            }

            return {
                "captcha_required": True,
                "authenticated": False,
                "captcha_image": f"data:image/png;base64,{img_b64}",
                "captcha_token": captcha_token,
                "message": "CAPTCHA detected. Submit the text via /auth/rutracker/login.",
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching RuTracker CAPTCHA: {e}")
        raise HTTPException(status_code=502, detail=f"Failed to fetch login page: {e}") from e


@router.post("/rutracker/login")
async def rutracker_login_with_captcha(request: CaptchaLoginRequest):  # type: ignore[no-untyped-def]
    import aiohttp

    orch = _get_orchestrator()
    orch._load_env()

    username = os.getenv("RUTRACKER_USERNAME")
    password = os.getenv("RUTRACKER_PASSWORD")

    if not username or not password:
        raise HTTPException(
            status_code=400,
            detail="RUTRACKER_USERNAME and RUTRACKER_PASSWORD not configured",
        )

    pending = _pending_captchas.pop(request.captcha_token, None)
    if not pending:
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired captcha_token. Fetch a new one from /auth/rutracker/captcha.",
        )

    base_url = pending["base_url"]

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{base_url}/forum/login.php",
                data={
                    "login_username": username,
                    "login_password": password,
                    "login": "\u0412\u0445\u043e\u0434",
                    "cap_sid": request.cap_sid,
                    request.cap_code_field: request.captcha_text,
                },
            ) as resp:
                text = await resp.text()
                cookies = {c.key: c.value for c in resp.cookies.values()}

            if 'id="logged-in-username"' in text or "bb_session" in cookies:
                orch._tracker_sessions["rutracker"] = {
                    "cookies": cookies,
                    "base_url": base_url,
                }
                return {
                    "authenticated": True,
                    "message": "Successfully authenticated with RuTracker.",
                }

            captcha_img = re.search(r'<img[^>]+src="(https://static\.rutracker\.cc/captcha/[^"]+)"', text)
            if captcha_img:
                cap_sid_match = re.search(r'name="cap_sid"\s+value="([^"]+)"', text)
                cap_code_match = re.search(r'name="(cap_code_[^"]+)"', text)
                if cap_sid_match and cap_code_match:
                    async with session.get(captcha_img.group(1)) as img_resp:
                        img_bytes = await img_resp.read()
                        img_b64 = base64.b64encode(img_bytes).decode()

                    new_token = secrets.token_urlsafe(32)
                    _pending_captchas[new_token] = {
                        "cap_sid": cap_sid_match.group(1),
                        "cap_code_field": cap_code_match.group(1),
                        "base_url": base_url,
                    }
                    return {
                        "authenticated": False,
                        "captcha_required": True,
                        "captcha_image": f"data:image/png;base64,{img_b64}",
                        "captcha_token": new_token,
                        "message": "Wrong CAPTCHA. A new one has been generated.",
                    }

            return {
                "authenticated": False,
                "message": "Login failed. Check credentials.",
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during RuTracker login: {e}")
        raise HTTPException(status_code=500, detail=f"Login failed: {e}") from e


@router.post("/rutracker/cookie-login")
async def rutracker_cookie_login(request: CookieLoginRequest):  # type: ignore[no-untyped-def]
    orch = _get_orchestrator()

    cookie_jar = {}
    for pair in request.cookie_string.split(";"):
        pair = pair.strip()
        if "=" in pair:
            k, v = pair.split("=", 1)
            cookie_jar[k.strip()] = v.strip()

    if "bb_session" not in cookie_jar:
        raise HTTPException(
            status_code=400,
            detail="Cookie string must contain bb_session cookie.",
        )

    base_url = os.getenv("RUTRACKER_MIRRORS", "https://rutracker.org").split(",")[0].strip()

    import aiohttp

    try:
        async with (
            aiohttp.ClientSession() as session,
            session.get(
                f"{base_url}/forum/index.php",
                cookies=cookie_jar,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp,
        ):
            text = await resp.text()
            if 'id="logged-in-username"' not in text:
                raise HTTPException(
                    status_code=401,
                    detail="Cookie is invalid or expired.",
                )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not verify cookie: {e}") from e

    orch._tracker_sessions["rutracker"] = {
        "cookies": cookie_jar,
        "base_url": base_url,
    }

    return {
        "authenticated": True,
        "message": "Successfully authenticated with RuTracker via cookie.",
    }


@router.get("/nnmclub/status")
async def nnmclub_auth_status():  # type: ignore[no-untyped-def]
    """BOB-006: report NNMClub session state. Mirrors /rutracker/status.

    The session cookie of interest is ``phpbb2mysql_4_sid``.
    """
    orch = _get_orchestrator()
    session = orch._tracker_sessions.get("nnmclub")

    if not session:
        return {
            "authenticated": False,
            "status": "no_session",
            "message": "No NNMClub session found. Login required.",
        }

    cookies = session.get("cookies", {})
    if "phpbb2mysql_4_sid" not in cookies:
        return {
            "authenticated": False,
            "status": "no_cookie",
            "message": "Session exists but no valid cookie. Re-login required.",
        }

    import aiohttp

    base_url = session.get("base_url", "https://nnmclub.to")
    try:
        async with (
            aiohttp.ClientSession() as client,
            client.get(
                f"{base_url}/forum/index.php",
                cookies=cookies,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp,
        ):
            raw = await resp.read()
            text = raw.decode("cp1251", "ignore")
            if "logout.php" in text or "profile.php?mode=editprofile" in text:
                return {
                    "authenticated": True,
                    "status": "active",
                    "message": "NNMClub session is active.",
                }
            return {
                "authenticated": False,
                "status": "expired",
                "message": "Session expired. Re-login required.",
            }
    except Exception as e:
        return {
            "authenticated": False,
            "status": "error",
            "message": f"Could not verify session: {e}",
        }


@router.post("/nnmclub/login")
async def nnmclub_password_login():  # type: ignore[no-untyped-def]
    """BOB-006: log in to NNMClub using NNMCLUB_USERNAME/NNMCLUB_PASSWORD and
    persist the resulting session cookie in the orchestrator.

    Credentials come from the environment (gitignored .env) — never the
    request body — so they are never logged or echoed.
    """
    username = os.getenv("NNMCLUB_USERNAME")
    password = os.getenv("NNMCLUB_PASSWORD")
    if not username or not password:
        raise HTTPException(
            status_code=400,
            detail="NNMCLUB_USERNAME and NNMCLUB_PASSWORD must be set.",
        )

    orch = _get_orchestrator()
    base_url = os.getenv("NNMCLUB_MIRRORS", "https://nnmclub.to").split(",")[0].strip()

    import aiohttp

    try:
        async with (
            aiohttp.ClientSession() as session,
            session.post(
                f"{base_url}/forum/login.php",
                data={
                    "username": username,
                    "password": password,
                    "login": "вход",
                },
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp,
        ):
            cookie_dict = {c.key: c.value for c in resp.cookies.values()}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Login request failed: {e}") from e

    if "phpbb2mysql_4_sid" not in cookie_dict:
        raise HTTPException(
            status_code=401,
            detail="NNMClub login returned no session cookie. Check credentials.",
        )

    orch._tracker_sessions["nnmclub"] = {
        "cookies": cookie_dict,
        "base_url": base_url,
    }

    return {
        "authenticated": True,
        "message": "Successfully authenticated with NNMClub.",
    }


def _load_qbit_credentials() -> Any:
    import json

    creds_path = "/config/download-proxy/qbittorrent_creds.json"
    if os.path.exists(creds_path):
        try:
            with open(creds_path) as f:
                return json.load(f)
        except Exception:  # noqa: S110
            pass
    username = os.getenv("QBITTORRENT_USER", os.getenv("QBITTORRENT_USERNAME", ""))
    password = os.getenv("QBITTORRENT_PASS", os.getenv("QBITTORRENT_PASSWORD", ""))
    if username and password:
        return {"username": username, "password": password}
    return None


@router.get("/status")
async def all_trackers_auth_status():  # type: ignore[no-untyped-def]
    import aiohttp

    orch = _get_orchestrator()
    trackers = {}

    for name in ["rutracker", "kinozal", "nnmclub", "iptorrents"]:
        session = orch._tracker_sessions.get(name)
        trackers[name] = {
            "has_session": session is not None,
            "base_url": session.get("base_url", "") if session else "",
        }

    creds = _load_qbit_credentials()
    qbit_has_session = False
    # Always probe qBittorrent with the EFFECTIVE creds — saved if present, else
    # the default admin/admin (the hardcoded WebUI creds). qBittorrent always
    # accepts these, so the dashboard auto-authenticates and the qBit button
    # never has to prompt for a login. Previously this ran only ``if creds:``, so
    # with no saved creds ``has_session`` stayed false and every qBit-button
    # click re-prompted for a login that never "stuck".
    qbit_user = creds.get("username", "admin") if creds else os.getenv("QBITTORRENT_USER", "admin")
    qbit_pass = creds.get("password", "admin") if creds else os.getenv("QBITTORRENT_PASS", "admin")
    qbit_username = qbit_user
    qbit_url = os.getenv("QBITTORRENT_URL", "http://localhost:7185")
    try:
        async with (
            aiohttp.ClientSession() as session,
            session.post(
                f"{qbit_url}/api/v2/auth/login",
                data={"username": qbit_user, "password": qbit_pass},
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp,
        ):
            login_text = await resp.text()
            # Modern qBittorrent (4.6+/5.x, linuxserver:latest) returns 204 +
            # QBT_SID cookie on success, NOT the legacy 200 "Ok." — the old check
            # left has_session permanently false. Mirror routes._qbit_login_succeeded.
            qbit_has_session = (resp.status in (200, 204)) and (
                any(c.key == "QBT_SID" or c.key.startswith("QBT_SID_") for c in resp.cookies.values())
                or login_text.strip() == "Ok."
            )
    except Exception:  # noqa: S110
        pass
    trackers["qbittorrent"] = {
        "has_session": qbit_has_session,
        "username": qbit_username,
    }

    return {"trackers": trackers}


@router.post("/qbittorrent/logout")
async def qbittorrent_logout():  # type: ignore[no-untyped-def]
    creds_path = "/config/download-proxy/qbittorrent_creds.json"
    try:
        if os.path.exists(creds_path):  # noqa: ASYNC240
            os.remove(creds_path)
        return {"status": "logged_out", "message": "Credentials cleared"}
    except Exception as e:
        logger.error(f"qBittorrent logout error: {e}")
        return {"status": "error", "error": str(e)}


__all__ = ["router"]
