"""DDoS-class coverage for the qBittorrent-login-driving endpoints (BOB-097,
canonical impl of BOB-074's RD2-07/RD2-32 gap; §11.4.27(B) ddos, §11.4.169).

TWO ROUTES, ONE RISK SHAPE. `POST /api/v1/auth/qbittorrent` and
`GET /api/v1/downloads/active` are grouped in this file because both perform a
REAL `POST /api/v2/auth/login` round-trip against the configured qBittorrent
instance on EVERY call, and NEITHER carries a rate limiter (confirmed by
inspection of `download-proxy/src/api/routes.py`: only `/search`,
`/search/stream/{id}` and `/theme/stream` are rate-limited). That combination
is exactly the CREDENTIAL-STUFFING-SHAPED risk this workable item calls out for
`/auth/qbittorrent` — many rapid login attempts, each a genuine attempt against
the downstream service — and `/downloads/active` carries the SAME login-per-call
shape even though it is nominally a read-only status route (routes.py:1127-1166
performs `auth/login` THEN `torrents/info` on every GET).

DISTINCT FROM `tests/stress/test_auth_stress_chaos.py` (verified before writing
this file — do not duplicate, §11.4.251). That existing suite gives
`api.auth.all_trackers_auth_status` (`GET /api/v1/auth/status`, a DIFFERENT
router mounted from `api/auth.py`, prefix `/auth`) exhaustive §11.4.85
stress+chaos coverage — but `all_trackers_auth_status` NEVER calls
`/api/v2/auth/login`; it PROBES qBittorrent read-only and reports the result.
`POST /api/v1/auth/qbittorrent` (`api/routes.py:1169`) is a completely separate
handler that actually PERFORMS a login attempt (and optionally persists
credentials to disk on `save=True` — never exercised here, so no disk I/O is
in scope for these tests). No existing suite drives either of THIS file's two
routes through the real ASGI app under a burst.

HOST SAFETY (§12, §12.6, §12.11): every burst capped at `MAX_BURST_REQUESTS`
(24, from `tests/ddos/conftest.py`); no real network; no sleeps; no `save=True`
credential-persistence path exercised (that would touch disk under
`/config/download-proxy/`, out of scope and unsafe for this in-process suite).
§11.4.263: every mock response below is an explicit `AsyncMock()`/`MagicMock()`
with no bare pid/pgid attribute ever touched.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
from fastapi.testclient import TestClient

from .conftest import MAX_BURST_REQUESTS, build_app

_ATTACKER = "203.0.113.31"  # TEST-NET-3 (RFC 5737) — never a routable host
_BYSTANDER = "198.51.100.66"  # TEST-NET-2 (RFC 5737)


def _client(app):
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# aiohttp/qBittorrent mock helpers (shape mirrored from
# tests/stress/test_auth_stress_chaos.py's `_qbit_resp`/`_qbit_session`; see
# module docstring for why this is a re-derivation, not a duplicate — that
# file exercises `all_trackers_auth_status`, a different function entirely).
# ---------------------------------------------------------------------------


def _login_resp(*, ok: bool) -> AsyncMock:
    resp = AsyncMock()
    resp.text = AsyncMock(return_value="Ok." if ok else "Fails.")
    resp.status = 200 if ok else 403
    resp.cookies = {}
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


def _version_resp() -> AsyncMock:
    resp = AsyncMock()
    resp.text = AsyncMock(return_value="v4.6.0")
    resp.status = 200
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


def _torrents_info_resp(*, torrents: list[dict] | None = None) -> AsyncMock:
    resp = AsyncMock()
    resp.json = AsyncMock(return_value=torrents or [])
    resp.status = 200
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


def _success_auth_session() -> AsyncMock:
    """login(Ok.) -> version(200) — the exact sequence `auth_qbittorrent` awaits."""
    session = AsyncMock()
    session.post = MagicMock(return_value=_login_resp(ok=True))
    session.get = MagicMock(return_value=_version_resp())
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


def _failure_auth_session() -> AsyncMock:
    """login(Fails.) only — `_qbit_login_succeeded` is False, no version call."""
    session = AsyncMock()
    session.post = MagicMock(return_value=_login_resp(ok=False))
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


def _success_active_downloads_session() -> AsyncMock:
    """login(Ok.) -> torrents/info([]) — the sequence `get_active_downloads` awaits."""
    session = AsyncMock()
    session.post = MagicMock(return_value=_login_resp(ok=True))
    session.get = MagicMock(return_value=_torrents_info_resp())
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


def _patch_success_auth():
    return patch("aiohttp.ClientSession", side_effect=lambda *a, **kw: _success_auth_session())


def _patch_failure_auth():
    return patch("aiohttp.ClientSession", side_effect=lambda *a, **kw: _failure_auth_session())


def _patch_unreachable_qbit():
    return patch(
        "aiohttp.ClientSession",
        side_effect=aiohttp.ClientConnectionError("qBittorrent unreachable"),
    )


def _patch_success_active_downloads():
    return patch("aiohttp.ClientSession", side_effect=lambda *a, **kw: _success_active_downloads_session())


# ===========================================================================
# POST /api/v1/auth/qbittorrent — the real login trigger
# ===========================================================================


@pytest.mark.ddos
class TestQbitAuthBurstSurvives:
    def test_burst_of_login_attempts_produces_no_5xx_and_survives(self):
        """A capped burst of successful-login attempts must not 5xx, and the
        service must still answer /health afterwards."""
        api_mod, _ = build_app(default="200/minute")
        with _patch_success_auth(), _client(api_mod.app) as c:
            codes = [
                c.post(
                    "/api/v1/auth/qbittorrent",
                    json={"username": "admin", "password": "admin", "save": False},
                    headers={"X-Forwarded-For": _ATTACKER},
                ).status_code
                for _ in range(MAX_BURST_REQUESTS)
            ]
            after = c.get("/health")

        assert [s for s in codes if s >= 500] == [], f"5xx leaked under an auth burst: codes={codes}"
        assert set(codes) == {200}, f"every successful-login call must return 200: codes={codes}"
        assert after.status_code == 200, (
            f"service stopped answering /health after an auth burst: HTTP {after.status_code}"
        )

    def test_repeated_failed_login_attempts_credential_stuffing_shaped_no_5xx(self):
        """The credential-stuffing-shaped risk this item explicitly names: many
        RAPID login attempts, each with a DIFFERENT bogus password, and no rate
        limiter to bound them. Every attempt must be handled gracefully — a
        deliberate `{"status":"failed"}` body, never a 5xx — and the service
        must survive the burst.

        HONEST SCOPE (§11.4.6): NO rate limiter guards this route, so this test
        does NOT assert a 429 refusal — see the module docstring and the
        BOB-097 closure evidence for that observation reported to the
        conductor. What IS asserted is that the absence of a rate limiter does
        not ALSO mean the absence of graceful degradation: every one of the
        MAX_BURST_REQUESTS distinct-password attempts must still resolve
        cleanly.
        """
        api_mod, _ = build_app(default="200/minute")
        with _patch_failure_auth(), _client(api_mod.app) as c:
            responses = [
                c.post(
                    "/api/v1/auth/qbittorrent",
                    json={"username": "admin", "password": f"guess-{i}", "save": False},
                    headers={"X-Forwarded-For": _ATTACKER},
                )
                for i in range(MAX_BURST_REQUESTS)
            ]
            after = c.get("/health")

        codes = [r.status_code for r in responses]
        assert [s for s in codes if s >= 500] == [], f"5xx leaked during a credential-stuffing-shaped burst: {codes}"
        assert set(codes) == {200}, f"every failed-login attempt must still resolve with 200: codes={codes}"
        statuses = {r.json().get("status") for r in responses}
        assert statuses == {"failed"}, f"every failed attempt must report status 'failed', got: {statuses}"
        assert after.status_code == 200, (
            f"service stopped answering /health after a credential-stuffing-shaped burst: HTTP {after.status_code}"
        )

    def test_qbittorrent_unreachable_under_repeated_calls_reports_error_not_5xx(self):
        """Process/upstream death, repeated across a burst: qBittorrent
        unreachable must degrade to a deliberate error body, never a 5xx."""
        api_mod, _ = build_app(default="200/minute")
        with _patch_unreachable_qbit(), _client(api_mod.app) as c:
            responses = [
                c.post(
                    "/api/v1/auth/qbittorrent",
                    json={"username": "admin", "password": "admin", "save": False},
                    headers={"X-Forwarded-For": _ATTACKER},
                )
                for _ in range(MAX_BURST_REQUESTS)
            ]
            after = c.get("/health")

        codes = [r.status_code for r in responses]
        assert [s for s in codes if s >= 500] == [], f"5xx leaked while qBittorrent was unreachable: codes={codes}"
        statuses = {r.json().get("status") for r in responses}
        assert statuses == {"error"}, f"every call during an outage must report status 'error', got: {statuses}"
        assert after.status_code == 200, (
            f"service stopped answering /health after a qBittorrent-unreachable auth burst: HTTP {after.status_code}"
        )


@pytest.mark.ddos
class TestQbitAuthBystanderNotBlocked:
    def test_auth_flood_does_not_block_bystander_health_check(self):
        api_mod, _ = build_app(default="200/minute")
        with _patch_success_auth(), _client(api_mod.app) as c:
            attacker_codes = [
                c.post(
                    "/api/v1/auth/qbittorrent",
                    json={"username": "admin", "password": "admin", "save": False},
                    headers={"X-Forwarded-For": _ATTACKER},
                ).status_code
                for _ in range(MAX_BURST_REQUESTS)
            ]
            bystander = c.get("/health", headers={"X-Forwarded-For": _BYSTANDER})

        assert [s for s in attacker_codes if s >= 500] == [], f"5xx during attacker burst: {attacker_codes}"
        assert bystander.status_code == 200, (
            f"collateral denial of service: a bystander's /health got HTTP "
            f"{bystander.status_code} while another client was flooding /auth/qbittorrent"
        )


# ===========================================================================
# GET /api/v1/downloads/active — same login-per-call shape, nominally read-only
# ===========================================================================


@pytest.mark.ddos
class TestActiveDownloadsBurstSurvives:
    def test_burst_produces_no_5xx_and_service_survives(self):
        """This route performs a REAL qBittorrent login on every call
        (routes.py:1127-1166) despite being a GET — the same amplification
        shape as /auth/qbittorrent, and equally unrated-limited."""
        api_mod, _ = build_app(default="200/minute")
        with _patch_success_active_downloads(), _client(api_mod.app) as c:
            codes = [
                c.get("/api/v1/downloads/active", headers={"X-Forwarded-For": _ATTACKER}).status_code
                for _ in range(MAX_BURST_REQUESTS)
            ]
            after = c.get("/health")

        assert [s for s in codes if s >= 500] == [], f"5xx leaked under a /downloads/active burst: codes={codes}"
        assert set(codes) == {200}, f"every successful call must return 200: codes={codes}"
        assert after.status_code == 200, (
            f"service stopped answering /health after a /downloads/active burst: HTTP {after.status_code}"
        )

    def test_qbittorrent_unreachable_reports_empty_result_not_5xx(self):
        """The handler's own `except Exception` (routes.py:1163) degrades an
        unreachable qBittorrent to `{"downloads": [], "count": 0, "error":
        "unavailable"}` — never a 5xx — proven here across a full burst."""
        api_mod, _ = build_app(default="200/minute")
        with _patch_unreachable_qbit(), _client(api_mod.app) as c:
            responses = [
                c.get("/api/v1/downloads/active", headers={"X-Forwarded-For": _ATTACKER})
                for _ in range(MAX_BURST_REQUESTS)
            ]
            after = c.get("/health")

        codes = [r.status_code for r in responses]
        assert [s for s in codes if s >= 500] == [], f"5xx leaked while qBittorrent was unreachable: codes={codes}"
        bodies = [r.json() for r in responses]
        assert all(b.get("downloads") == [] and b.get("count") == 0 for b in bodies), (
            f"every call during an outage must report an empty, well-formed result: {bodies}"
        )
        assert after.status_code == 200, (
            f"service stopped answering /health after an unreachable-qBittorrent burst: HTTP {after.status_code}"
        )

    def test_flooding_client_does_not_deny_service_to_another_client(self):
        api_mod, _ = build_app(default="200/minute")
        with _patch_success_active_downloads(), _client(api_mod.app) as c:
            attacker_codes = [
                c.get("/api/v1/downloads/active", headers={"X-Forwarded-For": _ATTACKER}).status_code
                for _ in range(MAX_BURST_REQUESTS)
            ]
            bystander = c.get("/api/v1/downloads/active", headers={"X-Forwarded-For": _BYSTANDER})

        assert [s for s in attacker_codes if s >= 500] == [], f"5xx during attacker burst: {attacker_codes}"
        assert bystander.status_code == 200, (
            f"collateral denial of service: a bystander's /downloads/active got HTTP "
            f"{bystander.status_code} while another client was bursting the same route"
        )
