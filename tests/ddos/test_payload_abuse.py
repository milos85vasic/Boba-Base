"""Payload-size abuse resilience (§11.4.27(B) ddos, BOB-074).

THE ATTACK. Rather than many requests, send a few very LARGE ones. The
resilience properties are that an oversized payload is (a) REFUSED by an
explicit guard rather than buffered and processed, (b) refused with a
deliberate 4xx rather than an incidental 5xx, and (c) survivable — the service
still answers afterwards.

Nothing here is asserted on "no exception raised": every assertion reads a
status code, a response body, or a post-attack liveness probe (§11.4/§11.4.1).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from .conftest import OVERSIZE_QUERY_BYTES, OVERSIZE_UPLOAD_BYTES, build_app

_ATTACKER = "203.0.113.9"  # TEST-NET-3 (RFC 5737)

#: Production's declared ceiling — `api/routes.py:_MAX_TORRENT_UPLOAD_BYTES`.
_PRODUCTION_UPLOAD_LIMIT = 10 * 1024 * 1024


@pytest.fixture(autouse=True)
def _upload_endpoint_is_open(monkeypatch):
    """The upload guard is what is under test, not the optional token gate.

    `BOBA_API_TOKEN` unset is the documented DEFAULT (routes.py:89 — "OPEN").
    Clearing it explicitly keeps the test from silently degrading into a 401
    assertion if some other suite leaves the variable set in the environment.
    """
    monkeypatch.delenv("BOBA_API_TOKEN", raising=False)


@pytest.mark.ddos
class TestOversizedUploadIsRefused:
    def test_oversized_torrent_upload_is_refused_with_413(self):
        """A payload over the 10 MiB ceiling must be refused, not forwarded."""
        api_mod, _ = build_app(default="200/minute")
        blob = b"d" + b"\0" * (OVERSIZE_UPLOAD_BYTES - 1)
        assert len(blob) > _PRODUCTION_UPLOAD_LIMIT, "fixture must actually exceed the guard"

        with TestClient(api_mod.app, raise_server_exceptions=False) as c:
            r = c.post(
                "/api/v1/download/upload",
                files={"file": ("huge.torrent", blob, "application/x-bittorrent")},
                headers={"X-Forwarded-For": _ATTACKER},
            )

        assert r.status_code == 413, (
            f"oversized upload was not refused with 413; got HTTP {r.status_code}: {r.text[:200]!r}"
        )

    def test_undersized_upload_is_not_refused_by_the_size_guard(self):
        """Control (§11.4.201(1)): the guard must not refuse everything.

        A guard that 413s every upload is exactly as broken as one that 413s
        none. A small (still invalid) .torrent must get PAST the size check and
        be rejected by the CONTENT sniff instead — a different, 400 refusal.
        """
        api_mod, _ = build_app(default="200/minute")

        with TestClient(api_mod.app, raise_server_exceptions=False) as c:
            r = c.post(
                "/api/v1/download/upload",
                files={"file": ("small.bin", b"not-a-torrent", "application/octet-stream")},
                headers={"X-Forwarded-For": _ATTACKER},
            )

        assert r.status_code != 413, (
            "the size guard fired on a 13-byte upload — it is refusing on "
            "something other than size (§11.4.201(1) false-positive refusal)"
        )
        assert r.status_code == 400, (
            f"expected the content sniff to reject a small non-torrent with 400; got {r.status_code}"
        )

    def test_service_survives_the_oversized_upload(self):
        """Post-attack liveness: a rejected 10 MiB body must not wedge anything."""
        api_mod, _ = build_app(default="200/minute")
        blob = b"d" + b"\0" * (OVERSIZE_UPLOAD_BYTES - 1)

        with TestClient(api_mod.app, raise_server_exceptions=False) as c:
            c.post(
                "/api/v1/download/upload",
                files={"file": ("huge.torrent", blob, "application/x-bittorrent")},
                headers={"X-Forwarded-For": _ATTACKER},
            )
            after = c.get("/health")

        assert after.status_code == 200, (
            f"service stopped answering /health after an oversized upload: HTTP {after.status_code}"
        )


@pytest.mark.ddos
class TestOversizedJsonBody:
    def test_oversized_query_does_not_5xx_and_service_stays_live(self):
        """A very large JSON `query` must not crash the service.

        HONEST SCOPE (§11.4.6 — this asserts what is TRUE, not what would be
        nice). `SearchRequest.query` (api/routes.py:187) declares `min_length=1`
        and **no `max_length`**, so an oversized query is ACCEPTED, not refused.
        This test therefore does not assert a refusal that does not exist — it
        pins the two properties that do hold (no 5xx, service still live) so a
        regression that turns a large body into a crash is caught. The missing
        `max_length` is a real amplification gap: an accepted oversized query is
        forwarded to the tracker fan-out. It is recorded as an open gap in
        `docs/TESTING.md` "DDoS tests — what this does NOT cover"; closing it is
        a production-source change and is out of scope for this test package.
        """
        api_mod, _ = build_app(search="60/minute", default="200/minute")
        payload = {"query": "A" * OVERSIZE_QUERY_BYTES, "validate_trackers": False}

        with TestClient(api_mod.app, raise_server_exceptions=False) as c:
            r = c.post("/api/v1/search", json=payload, headers={"X-Forwarded-For": _ATTACKER})
            after = c.get("/health")

        assert r.status_code < 500, (
            f"an oversized JSON body produced a server error: HTTP {r.status_code}: {r.text[:200]!r}"
        )
        assert after.status_code == 200, (
            f"service stopped answering /health after an oversized JSON body: HTTP {after.status_code}"
        )

    def test_oversized_body_cannot_bypass_the_rate_limiter(self):
        """Size must not buy extra budget.

        If oversized requests were rejected BEFORE the limiter saw them, an
        attacker could burn the service's parsing budget for free without ever
        consuming their own quota. The limiter must count them.
        """
        limit = 4
        api_mod, _ = build_app(search=f"{limit}/minute", default="200/minute")
        payload = {"query": "A" * OVERSIZE_QUERY_BYTES, "validate_trackers": False}

        with TestClient(api_mod.app, raise_server_exceptions=False) as c:
            codes = [
                c.post(
                    "/api/v1/search", json=payload, headers={"X-Forwarded-For": _ATTACKER}
                ).status_code
                for _ in range(limit + 2)
            ]

        assert codes[-1] == 429, (
            f"oversized bodies bypassed the per-IP limiter — {limit + 2} were "
            f"issued against a {limit}/minute limit and the last was not refused; codes={codes}"
        )
