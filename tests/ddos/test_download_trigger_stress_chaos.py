"""DDoS-class coverage for the download-TRIGGER endpoints (BOB-097, canonical
impl of BOB-074's RD2-07/RD2-32 gap; §11.4.27(B) ddos, §11.4.169).

WHY THESE THREE, WHY NOW. `download-proxy/src/api/routes.py` exposes
`POST /api/v1/download`, `POST /api/v1/download/file` and `POST /api/v1/magnet`
alongside `/api/v1/search` and `/api/v1/download/upload` — but only the latter
two were previously exercised by `tests/ddos/`. These three are HIGHER
DDoS-relevance, not lower: `POST /download` is the endpoint that causes a REAL
write against the downstream qBittorrent instance (an `/api/v2/torrents/add`
call), so an unbounded flood here amplifies past this service into qBittorrent
itself — precisely the "genuine downstream write" shape the sibling
`/api/v1/download/upload` test in `test_payload_abuse.py` does not cover (that
route accepts bytes but never forwards a SUCCESSFUL add under test).

WHAT THIS FILE DOES NOT RE-TEST (§11.4.251 — no second dialect).
`tests/stress/test_button_endpoints_stress_chaos.py` already gives
`initiate_download` and `generate_magnet` exhaustive §11.4.85 stress+chaos
coverage — sustained load, concurrency, boundary inputs, upstream-death,
primary/fallback, auth-rejection — but it calls those FUNCTIONS DIRECTLY
(`await initiate_download(req, MagicMock())`), never through the real ASGI app,
its middleware stack, or an HTTP client. That answers "is the business logic
robust?". It does NOT answer the DDoS question, which is specifically about the
HTTP/ASGI layer under a driven burst of REAL requests: does a burst get refused
or survived cleanly, does one abusive caller starve another, is the service
still answering afterwards? This file answers THAT question, reusing the exact
`_qbit_login_succeeded`/`_qbit_add_succeeded`-observing mock shape the stress
file already established (`_login_resp`/`_add_resp`/`_session_with_post_sequence`
here are the SAME shape, re-derived locally rather than imported across test
packages — `tests/stress` and `tests/ddos` are independent suites with their own
conftest/host-safety scope, and importing across them would couple two
independently-run packages for no shared benefit).

HONEST SCOPE (§11.4.6): NONE of these three routes carries a rate-limit
decorator or dependency (confirmed by inspection of
`download-proxy/src/api/routes.py` — only `/search`, `/search/stream/{id}` and
`/theme/stream` are rate-limited). Every test below therefore asserts what is
ACTUALLY true under a burst — no 5xx, the service survives, a bystander is not
starved, a bounded/oversized payload does not explode the handler's cost — and
never asserts a 429 refusal these routes have no mechanism to produce. This
absence is reported to the conductor as an observation, not silently assumed
away (see the BOB-097 closure evidence file).

`/api/v1/download/file` and `/api/v1/magnet` require NO network mocking at all
when driven with a magnet URL: `download_torrent_file` returns the magnet as a
`PlainTextResponse` without touching qBittorrent (routes.py:1690-1700), and
`generate_magnet` is pure string/regex computation (routes.py:1738-1788). Only
`/api/v1/download` performs the real login+add round-trip and needs
`aiohttp.ClientSession` mocked — the SAME `patch("aiohttp.ClientSession", ...)`
target the stress file uses, so this file proves the identical mock boundary
holds at the HTTP layer too.

HOST SAFETY (§12, §12.6, §12.11): every burst is capped at `MAX_BURST_REQUESTS`
(24) from `tests/ddos/conftest.py`; no real network, no sleeps, no unbounded
loop. §11.4.263: every mock session below sets `.post = MagicMock(...)`
explicitly — no bare `AsyncMock()` object stands in for a `pid`/`pgid`, so no
`mock.pid` ambiguity is possible anywhere in this file.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
from fastapi.testclient import TestClient

from .conftest import MAX_BURST_REQUESTS, build_app

_ATTACKER = "203.0.113.21"  # TEST-NET-3 (RFC 5737) — never a routable host
_BYSTANDER = "198.51.100.55"  # TEST-NET-2 (RFC 5737)

#: A syntactically valid magnet — routes every one of the three handlers down
#: their non-tracker, non-orchestrator-fetch path (the direct `data={"urls":
#: url}` add for `/download`, the `PlainTextResponse` fast path for
#: `/download/file`, and the pure-computation path for `/magnet`), so none of
#: these tests needs to mock `SearchOrchestrator.fetch_torrent`.
_MAGNET_URL = "magnet:?xt=urn:btih:" + ("a" * 40)


def _client(app):
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _download_endpoints_are_open(monkeypatch):
    """`require_api_token` is OPEN by default (`BOBA_API_TOKEN` unset).

    Mirrors `test_payload_abuse.py::_upload_endpoint_is_open` exactly: the DDoS
    property under test is the burst/abuse-resilience behaviour of the size/
    admission/rate-limit guards, not the OPTIONAL token gate, and clearing the
    variable explicitly keeps this from silently degrading into a 401
    assertion if some other suite leaves it set in the environment.
    """
    monkeypatch.delenv("BOBA_API_TOKEN", raising=False)


# ---------------------------------------------------------------------------
# aiohttp/qBittorrent mock helpers for POST /api/v1/download
# (shape mirrored from tests/stress/test_button_endpoints_stress_chaos.py —
#  re-derived locally per the module docstring; not a second dialect, the
#  same observed contract of api.routes._qbit_login_succeeded /
#  _qbit_add_succeeded, driven at a different layer.)
# ---------------------------------------------------------------------------


def _login_resp(*, ok: bool) -> AsyncMock:
    resp = AsyncMock()
    resp.text = AsyncMock(return_value="Ok." if ok else "Fails.")
    resp.status = 200
    resp.cookies = {}
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


def _add_resp(*, ok: bool) -> AsyncMock:
    resp = AsyncMock()
    resp.text = AsyncMock(return_value="Ok." if ok else "Fails.")
    resp.status = 200
    resp.cookies = MagicMock()
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


def _success_session() -> AsyncMock:
    """A fresh mocked `ClientSession` whose `.post` calls succeed (login+add)."""
    session = AsyncMock()
    session.post = MagicMock(side_effect=[_login_resp(ok=True), _add_resp(ok=True)])
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


def _patch_success_qbit():
    """`aiohttp.ClientSession(...)` returns a FRESH success session EVERY call.

    `initiate_download` constructs one `ClientSession` per request
    (`async with aiohttp.ClientSession(...) as session:`), so a single shared
    mock session's `side_effect` list would be exhausted after one request. A
    `side_effect` CALLABLE re-invoked on every construction is what makes a
    burst of N requests each get their own two-call (login, add) sequence.
    """
    return patch("aiohttp.ClientSession", side_effect=lambda *a, **kw: _success_session())


def _patch_unreachable_qbit():
    """`aiohttp.ClientSession(...)` raises on construction — qBittorrent down."""
    return patch(
        "aiohttp.ClientSession",
        side_effect=aiohttp.ClientConnectionError("qBittorrent unreachable"),
    )


# ===========================================================================
# POST /api/v1/download — the real qBittorrent-write trigger
# ===========================================================================


@pytest.mark.ddos
class TestDownloadTriggerBurstSurvives:
    def test_burst_produces_no_5xx_and_service_survives(self):
        """A capped burst of real-write-triggering requests must not 5xx, and
        the service must still answer /health afterwards (post-attack
        liveness — the same oracle `test_request_flood.py` uses)."""
        api_mod, _ = build_app(default="200/minute")
        with _patch_success_qbit(), _client(api_mod.app) as c:
            codes = [
                c.post(
                    "/api/v1/download",
                    json={"result_id": "flood-probe", "download_urls": [_MAGNET_URL]},
                    headers={"X-Forwarded-For": _ATTACKER},
                ).status_code
                for _ in range(MAX_BURST_REQUESTS)
            ]
            after = c.get("/health")

        assert [s for s in codes if s >= 500] == [], f"5xx leaked under a /download burst: codes={codes}"
        assert after.status_code == 200, (
            f"service stopped answering /health after a {MAX_BURST_REQUESTS}-request "
            f"/download burst: HTTP {after.status_code}"
        )

    def test_flooding_client_does_not_deny_service_to_another_client(self):
        """No collateral DoS: a bystander's /download request still succeeds
        while another client is bursting the same endpoint.

        HONEST SCOPE: this route carries no rate limiter, so there is no
        429-refusal precondition to assert (unlike the sibling assertion in
        `test_request_flood.py`) — the property under test is purely that the
        burst does not WEDGE the server for anyone else.
        """
        api_mod, _ = build_app(default="200/minute")
        with _patch_success_qbit(), _client(api_mod.app) as c:
            attacker_codes = [
                c.post(
                    "/api/v1/download",
                    json={"result_id": "flood-probe", "download_urls": [_MAGNET_URL]},
                    headers={"X-Forwarded-For": _ATTACKER},
                ).status_code
                for _ in range(MAX_BURST_REQUESTS)
            ]
            bystander = c.post(
                "/api/v1/download",
                json={"result_id": "bystander-probe", "download_urls": [_MAGNET_URL]},
                headers={"X-Forwarded-For": _BYSTANDER},
            )

        assert [s for s in attacker_codes if s >= 500] == [], f"5xx during attacker burst: {attacker_codes}"
        assert 200 <= bystander.status_code < 300, (
            f"collateral denial of service: a bystander's /download got HTTP "
            f"{bystander.status_code} while another client was bursting the same route"
        )
        body = bystander.json()
        assert body.get("status") == "initiated" and body.get("added_count") == 1, (
            f"bystander request must have been genuinely serviced, not merely non-5xx: {body}"
        )


@pytest.mark.ddos
class TestDownloadTriggerPayloadShapedAbuse:
    def test_oversized_download_urls_list_is_bounded_by_code_not_by_payload_size(self):
        """`DownloadRequest.download_urls` has NO `max_length` — the handler's
        own bound (`request.download_urls[:5]`, routes.py:1438) is what
        prevents a caller submitting hundreds of URLs from fanning out into
        hundreds of qBittorrent add attempts. This proves that CODE-level
        bound genuinely holds under a large list, not merely under the
        1-2-URL fixtures the function-level stress suite uses.
        """
        api_mod, _ = build_app(default="200/minute")
        # 200 URLs: well past the [:5] truncation point, cheap (magnets, no
        # network per-URL beyond the mocked session), bounded well under any
        # host-safety concern.
        urls = [_MAGNET_URL for _ in range(200)]

        # Every truncated URL takes the SAME (login, add) pair; the mocked
        # session must supply enough responses for the up-to-5 add attempts
        # the handler will actually make (it BREAKS after the first
        # "added" result, so exactly one add attempt is made here).
        with _patch_success_qbit(), _client(api_mod.app) as c:
            r = c.post(
                "/api/v1/download",
                json={"result_id": "oversized-list-probe", "download_urls": urls},
                headers={"X-Forwarded-For": _ATTACKER},
            )
            after = c.get("/health")

        assert r.status_code < 500, f"an oversized download_urls list produced a server error: HTTP {r.status_code}"
        body = r.json()
        assert body.get("urls_count") == 200, f"the full submitted count must be echoed back: {body}"
        assert body.get("added_count") == 1, (
            f"the handler must still only attempt the bounded [:5] prefix and "
            f"stop at the first success, regardless of list size: {body}"
        )
        assert after.status_code == 200, (
            f"service stopped answering /health after an oversized-list /download call: HTTP {after.status_code}"
        )

    def test_qbittorrent_unreachable_under_repeated_calls_reports_connection_failed_not_5xx(self):
        """Process/upstream death, repeated across a capped burst: qBittorrent
        unreachable must degrade to a deliberate `connection_failed` body on
        EVERY call, never an incidental 5xx, and the service must survive."""
        api_mod, _ = build_app(default="200/minute")
        with _patch_unreachable_qbit(), _client(api_mod.app) as c:
            responses = [
                c.post(
                    "/api/v1/download",
                    json={"result_id": "unreachable-probe", "download_urls": [_MAGNET_URL]},
                    headers={"X-Forwarded-For": _ATTACKER},
                )
                for _ in range(MAX_BURST_REQUESTS)
            ]
            after = c.get("/health")

        codes = [r.status_code for r in responses]
        assert [s for s in codes if s >= 500] == [], f"5xx leaked while qBittorrent was unreachable: codes={codes}"
        statuses = {r.json().get("status") for r in responses}
        assert statuses == {"connection_failed"}, (
            f"every call during a qBittorrent outage must report connection_failed, got: {statuses}"
        )
        assert after.status_code == 200, (
            f"service stopped answering /health after a burst of qBittorrent-unreachable "
            f"/download calls: HTTP {after.status_code}"
        )


# ===========================================================================
# POST /api/v1/download/file — no network on the magnet path
# ===========================================================================


@pytest.mark.ddos
class TestDownloadFileTriggerBurstSurvives:
    def test_burst_of_magnet_download_file_requests_produces_no_5xx_and_survives(self):
        """`download_torrent_file` short-circuits to a `PlainTextResponse` for
        a magnet URL (routes.py:1690-1700) with no qBittorrent round-trip, so
        this burst exercises the ASGI/routing/response layer directly."""
        api_mod, _ = build_app(default="200/minute")
        with _client(api_mod.app) as c:
            codes = [
                c.post(
                    "/api/v1/download/file",
                    json={"result_id": "file-flood-probe", "download_urls": [_MAGNET_URL]},
                    headers={"X-Forwarded-For": _ATTACKER},
                ).status_code
                for _ in range(MAX_BURST_REQUESTS)
            ]
            after = c.get("/health")

        assert [s for s in codes if s >= 500] == [], f"5xx leaked under a /download/file burst: codes={codes}"
        assert set(codes) == {200}, f"every magnet-URL /download/file call must succeed with 200: codes={codes}"
        assert after.status_code == 200, (
            f"service stopped answering /health after a /download/file burst: HTTP {after.status_code}"
        )

    def test_flooding_client_does_not_deny_service_to_another_client(self):
        api_mod, _ = build_app(default="200/minute")
        with _client(api_mod.app) as c:
            attacker_codes = [
                c.post(
                    "/api/v1/download/file",
                    json={"result_id": "file-flood-probe", "download_urls": [_MAGNET_URL]},
                    headers={"X-Forwarded-For": _ATTACKER},
                ).status_code
                for _ in range(MAX_BURST_REQUESTS)
            ]
            bystander = c.post(
                "/api/v1/download/file",
                json={"result_id": "bystander-probe", "download_urls": [_MAGNET_URL]},
                headers={"X-Forwarded-For": _BYSTANDER},
            )

        assert [s for s in attacker_codes if s >= 500] == [], f"5xx during attacker burst: {attacker_codes}"
        assert bystander.status_code == 200, (
            f"collateral denial of service: a bystander's /download/file got HTTP "
            f"{bystander.status_code} while another client was bursting the same route"
        )


# ===========================================================================
# POST /api/v1/magnet — pure computation, no network at all
# ===========================================================================


@pytest.mark.ddos
class TestMagnetTriggerBurstSurvives:
    def test_burst_of_magnet_requests_produces_no_5xx_and_survives(self):
        api_mod, _ = build_app(default="200/minute")
        with _client(api_mod.app) as c:
            codes = [
                c.post(
                    "/api/v1/magnet",
                    json={"result_id": "magnet-flood-probe", "download_urls": [_MAGNET_URL]},
                    headers={"X-Forwarded-For": _ATTACKER},
                ).status_code
                for _ in range(MAX_BURST_REQUESTS)
            ]
            after = c.get("/health")

        assert [s for s in codes if s >= 500] == [], f"5xx leaked under a /magnet burst: codes={codes}"
        assert set(codes) == {200}, f"every well-formed /magnet call must succeed with 200: codes={codes}"
        assert after.status_code == 200, f"service stopped answering /health after a /magnet burst: HTTP {after.status_code}"

    def test_oversized_download_urls_list_does_not_5xx_or_hang(self):
        """`generate_magnet` loops over EVERY entry in `download_urls`
        (routes.py:1757-1764, no `[:5]`-style truncation) — the amplification
        shape this route actually has, distinct from `/download`'s bounded
        loop. A large list must still resolve promptly with no 5xx."""
        api_mod, _ = build_app(default="200/minute")
        urls = [_MAGNET_URL for _ in range(500)]

        with _client(api_mod.app) as c:
            r = c.post(
                "/api/v1/magnet",
                json={"result_id": "oversized-list-probe", "download_urls": urls},
                headers={"X-Forwarded-For": _ATTACKER},
            )
            after = c.get("/health")

        assert r.status_code < 500, f"an oversized download_urls list produced a server error: HTTP {r.status_code}"
        body = r.json()
        assert "magnet" in body and "hashes" in body, f"malformed /magnet response body: {body}"
        assert len(body["hashes"]) == 500, f"expected 500 extracted infohashes, got {len(body['hashes'])}"
        assert after.status_code == 200, (
            f"service stopped answering /health after an oversized-list /magnet call: HTTP {after.status_code}"
        )
