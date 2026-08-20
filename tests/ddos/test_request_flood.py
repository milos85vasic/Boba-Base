"""Capped-burst flood resilience (§11.4.27(B) ddos, BOB-074).

The DDoS question is not "is the threshold 10 or 60" (that is
`tests/security/test_rate_limit_public_endpoints.py`). It is:

  1. under a burst, are excess requests REFUSED rather than SERVED?
  2. does the refusal path itself stay clean — zero 5xx?
  3. does the service SURVIVE — still answering after the burst?
  4. can one abusive client deny service to a DIFFERENT client?

(4) is the property that makes this a DDoS test and not a rate-limit test: a
limiter that throttles *everyone* when *one* attacker floods has converted an
attack on one key into an outage for all keys.

CLIENT'S-EYE VIEW (deliberate). Every client here is built with
`raise_server_exceptions=False` so the harness reports what a real attacker or
user would OBSERVE over the wire — a status code — instead of re-raising a
server-side exception into the test. A 500 therefore shows up as `500` and is
caught by the no-5xx assertions, rather than aborting the test with a traceback
that never exercises the rest of the burst. Under the default
`raise_server_exceptions=True` the first server-side hiccup ends the run and the
"did it survive?" question is never asked at all.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from .conftest import MAX_BURST_REQUESTS, build_app

_ATTACKER = "203.0.113.7"  # TEST-NET-3 (RFC 5737) — never a routable host
_BYSTANDER = "198.51.100.42"  # TEST-NET-2 (RFC 5737)

_SEARCH_LIMIT = 6


def _client(app):
    return TestClient(app, raise_server_exceptions=False)


def _post_search(client: TestClient, ip: str):
    return client.post(
        "/api/v1/search",
        json={"query": "flood-probe", "validate_trackers": False},
        headers={"X-Forwarded-For": ip},
    )


def _burst(client: TestClient, ip: str, n: int) -> list[int]:
    """Issue exactly `n` requests. Hard-capped by MAX_BURST_REQUESTS."""
    assert n <= MAX_BURST_REQUESTS, f"host-safety cap: {n} > {MAX_BURST_REQUESTS}"
    return [_post_search(client, ip).status_code for _ in range(n)]


@pytest.mark.ddos
class TestCappedBurstIsRefusedNotServed:
    def test_burst_serves_only_up_to_the_limit_and_refuses_the_rest(self):
        """Observable: the served population is bounded; the rest are 429."""
        api_mod, _ = build_app(search=f"{_SEARCH_LIMIT}/minute")
        with _client(api_mod.app) as c:
            codes = _burst(c, _ATTACKER, MAX_BURST_REQUESTS)

        served = [s for s in codes if 200 <= s < 300]
        refused = [s for s in codes if s == 429]

        # The load-bearing DDoS assertion: the flood did NOT get served.
        assert len(served) == _SEARCH_LIMIT, (
            f"expected exactly {_SEARCH_LIMIT} served under a "
            f"{MAX_BURST_REQUESTS}-request burst, got {len(served)}; codes={codes}"
        )
        assert len(refused) == MAX_BURST_REQUESTS - _SEARCH_LIMIT, (
            f"expected the remaining {MAX_BURST_REQUESTS - _SEARCH_LIMIT} to be "
            f"refused with 429, got {len(refused)}; codes={codes}"
        )

    def test_burst_produces_no_5xx(self):
        """The refusal path must not itself fail. A 500 under flood is a defect."""
        api_mod, _ = build_app(search=f"{_SEARCH_LIMIT}/minute")
        with _client(api_mod.app) as c:
            codes = _burst(c, _ATTACKER, MAX_BURST_REQUESTS)

        assert [s for s in codes if s >= 500] == [], f"5xx leaked under burst: codes={codes}"

    def test_refusal_body_is_the_opaque_token_not_a_stack_trace(self):
        """Observable body — a refused flood must leak nothing (§11.4.10)."""
        api_mod, _ = build_app(search=f"{_SEARCH_LIMIT}/minute")
        with _client(api_mod.app) as c:
            _burst(c, _ATTACKER, _SEARCH_LIMIT)
            refused = _post_search(c, _ATTACKER)

        assert refused.status_code == 429, f"expected 429, got {refused.status_code}"
        assert refused.json() == {"error": "rate_limited"}, (
            f"refusal body must be the opaque token, got {refused.text[:200]!r}"
        )


@pytest.mark.ddos
class TestServiceSurvivesTheBurst:
    def test_health_still_answers_after_the_burst(self):
        """Post-attack liveness: the flood must not take the service down."""
        api_mod, _ = build_app(search=f"{_SEARCH_LIMIT}/minute")
        with _client(api_mod.app) as c:
            _burst(c, _ATTACKER, MAX_BURST_REQUESTS)
            after = c.get("/health", headers={"X-Forwarded-For": _BYSTANDER})

        assert after.status_code == 200, (
            f"service stopped answering /health after a "
            f"{MAX_BURST_REQUESTS}-request burst: HTTP {after.status_code}"
        )

    def test_flooding_client_does_not_deny_service_to_another_client(self):
        """No collateral DoS: the bystander is still served after the flood.

        This is the DDoS-specific property. It is asserted on the REAL app —
        `tests/unit/test_rate_limit.py::test_green_different_ip_is_not_rate_limited`
        asserts per-IP isolation on a SYNTHETIC app and so cannot notice a
        production route or middleware regression that collapses the key
        function to a constant (which would throttle every caller at once).
        """
        api_mod, _ = build_app(search=f"{_SEARCH_LIMIT}/minute")
        with _client(api_mod.app) as c:
            attacker_codes = _burst(c, _ATTACKER, MAX_BURST_REQUESTS)
            bystander = _post_search(c, _BYSTANDER)

        assert 429 in attacker_codes, (
            f"precondition: the attacker must actually have been throttled; codes={attacker_codes}"
        )
        assert 200 <= bystander.status_code < 300, (
            f"collateral denial of service: a bystander got HTTP "
            f"{bystander.status_code} while another client was being throttled"
        )


@pytest.mark.ddos
class TestSseStreamFloodIsRefused:
    def test_sse_stream_burst_is_refused_without_5xx(self):
        """The cheapest amplification surface: repeated stream attaches.

        An unknown search id 404s immediately (no open stream, no fan-out), so
        this exercises the limiter on the SSE class without holding resources.
        """
        api_mod, _ = build_app(sse=f"{_SEARCH_LIMIT}/minute")
        bogus = str(uuid.uuid4())
        with _client(api_mod.app) as c:
            codes = [
                c.get(
                    f"/api/v1/search/stream/{bogus}",
                    headers={"X-Forwarded-For": _ATTACKER},
                ).status_code
                for _ in range(MAX_BURST_REQUESTS)
            ]

        assert [s for s in codes if s >= 500] == [], f"5xx leaked on the SSE flood: {codes}"
        assert 429 in codes, f"SSE stream flood was never refused; codes={codes}"
        assert codes.count(404) == _SEARCH_LIMIT, (
            f"expected exactly {_SEARCH_LIMIT} attaches to reach the handler "
            f"before the limiter engaged; codes={codes}"
        )
