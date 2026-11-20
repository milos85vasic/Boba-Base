"""DDoS-class malformed-request flood coverage (BOB-074 RD2-07 gap).

This file closes the "malformed=0" finding from the original
`challenges/scripts/ddos_resilience_challenge.sh` audit: it drives the real
ASGI app with a capped burst of structurally-invalid or semantically-empty
payloads and asserts the service refuses them without 5xx, survives the burst,
and keeps serving bystanders.

HOST SAFETY (§12, §12.6, §12.11): every burst is capped at
`MAX_BURST_REQUESTS` (24) from `tests/ddos/conftest.py`; no real network;
no disk writes; no unbounded allocations. The malformed bodies are small
(hundreds of bytes) except for one pathological JSON string that is still
bounded under `OVERSIZE_QUERY_BYTES`.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from .conftest import MAX_BURST_REQUESTS, build_app

_ATTACKER = "203.0.113.31"  # TEST-NET-3 (RFC 5737)
_BYSTANDER = "198.51.100.66"  # TEST-NET-2 (RFC 5737)


def _client(app):
    return TestClient(app, raise_server_exceptions=False)


def _attack_header():
    return {"X-Forwarded-For": _ATTACKER}


def _bystander_header():
    return {"X-Forwarded-For": _BYSTANDER}


@pytest.mark.ddos
class TestMalformedJsonFloodSurvives:
    def test_invalid_json_body_flood_on_search_produces_no_5xx(self):
        """A burst of unparseable JSON to `/search` must be rejected cleanly."""
        api_mod, _ = build_app(search="200/minute", default="200/minute")
        with _client(api_mod.app) as c:
            codes = [
                c.post(
                    "/api/v1/search",
                    content=b"{this is not json",
                    headers={"Content-Type": "application/json", **(_attack_header())},
                ).status_code
                for _ in range(MAX_BURST_REQUESTS)
            ]
            after = c.get("/health")

        assert [s for s in codes if s >= 500] == [], f"5xx leaked under invalid-JSON flood: codes={codes}"
        assert all(c in (400, 422) for c in codes), f"expected 400/422, got: {codes}"
        assert after.status_code == 200, f"service stopped answering /health: HTTP {after.status_code}"

    def test_empty_json_object_flood_on_search_is_refused_not_5xx(self):
        """A burst of `{}` to `/search` (missing required `query`) must not 5xx."""
        api_mod, _ = build_app(search="200/minute", default="200/minute")
        with _client(api_mod.app) as c:
            codes = [
                c.post(
                    "/api/v1/search",
                    json={},
                    headers=_attack_header(),
                ).status_code
                for _ in range(MAX_BURST_REQUESTS)
            ]
            after = c.get("/health")

        assert [s for s in codes if s >= 500] == [], f"5xx leaked under empty-body flood: codes={codes}"
        assert all(c == 422 for c in codes), f"expected 422 for missing query, got: {codes}"
        assert after.status_code == 200


@pytest.mark.ddos
class TestMalformedAuthQbittorrentFloodSurvives:
    def test_missing_fields_flood_on_auth_qbittorrent_produces_no_5xx(self):
        """A burst of `{}` to `/auth/qbittorrent` must not 5xx.

        The production endpoint defaults missing credentials to the documented
        hardcoded `admin`/`admin` values, so an empty body is accepted rather
        than rejected. The DDoS-relevant assertion is therefore "no 5xx leaks"
        and "service remains alive", not "empty body returns 4xx".
        """
        api_mod, _ = build_app(default="200/minute")
        with _client(api_mod.app) as c:
            codes = [
                c.post(
                    "/api/v1/auth/qbittorrent",
                    json={},
                    headers=_attack_header(),
                ).status_code
                for _ in range(MAX_BURST_REQUESTS)
            ]
            after = c.get("/health")

        assert [s for s in codes if s >= 500] == [], f"5xx leaked under auth missing-field flood: codes={codes}"
        assert all(c < 500 for c in codes), f"expected <500, got: {codes}"
        assert after.status_code == 200


@pytest.mark.ddos
class TestMalformedDownloadFloodSurvives:
    def test_invalid_url_list_flood_on_download_produces_no_5xx(self):
        """A burst of `download_urls` that are not URLs must be rejected cleanly."""
        api_mod, _ = build_app(default="200/minute")
        with _client(api_mod.app) as c:
            codes = [
                c.post(
                    "/api/v1/download",
                    json={"download_urls": ["not-a-url", "", 123]},
                    headers=_attack_header(),
                ).status_code
                for _ in range(MAX_BURST_REQUESTS)
            ]
            after = c.get("/health")

        assert [s for s in codes if s >= 500] == [], f"5xx leaked under invalid-download-url flood: codes={codes}"
        assert all(c in (400, 422) for c in codes), f"expected 400/422, got: {codes}"
        assert after.status_code == 200


@pytest.mark.ddos
class TestMalformedMagnetFloodSurvives:
    def test_missing_fields_flood_on_magnet_produces_no_5xx(self):
        """A burst of `{}` to `/magnet` must not 5xx."""
        api_mod, _ = build_app(default="200/minute")
        with _client(api_mod.app) as c:
            codes = [
                c.post(
                    "/api/v1/magnet",
                    json={},
                    headers=_attack_header(),
                ).status_code
                for _ in range(MAX_BURST_REQUESTS)
            ]
            after = c.get("/health")

        assert [s for s in codes if s >= 500] == [], f"5xx leaked under magnet missing-field flood: codes={codes}"
        assert all(c in (400, 422) for c in codes), f"expected 400/422, got: {codes}"
        assert after.status_code == 200


@pytest.mark.ddos
class TestMalformedFloodDoesNotBlockBystander:
    def test_malformed_search_flood_does_not_deny_bystander_health(self):
        """An attacker flooding bad JSON must not stop a bystander's /health."""
        api_mod, _ = build_app(search="200/minute", default="200/minute")
        with _client(api_mod.app) as c:
            attack_codes = [
                c.post(
                    "/api/v1/search",
                    content=b"{bad",
                    headers={"Content-Type": "application/json", **(_attack_header())},
                ).status_code
                for _ in range(MAX_BURST_REQUESTS)
            ]
            bystander = c.get("/health", headers=_bystander_header())

        assert [s for s in attack_codes if s >= 500] == []
        assert bystander.status_code == 200, (
            f"bystander /health blocked by malformed flood: HTTP {bystander.status_code}"
        )
