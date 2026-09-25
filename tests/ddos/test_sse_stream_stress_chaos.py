"""DDoS-class coverage for `GET /api/v1/theme/stream` (BOB-097, canonical impl
of BOB-074's RD2-07/RD2-32 gap; §11.4.27(B) ddos, §11.4.169).

THE SLOW-LORIS-SHAPED QUESTION. `stream_theme` (routes.py:160-260) is a
long-lived Server-Sent-Events generator: it emits the current theme
immediately, then holds the connection open indefinitely, waiting on
`asyncio.wait_for(queue.get(), timeout=15)` and re-checking a disconnect probe
each cycle. `GET /search/stream/{search_id}` carries the identical
`@_rl("sse_stream")` class and IS burst-tested in `test_request_flood.py` — but
that test drives an UNKNOWN search id, which 404s immediately with no open
stream and no held resource, so it never exercises a GENUINELY LONG-LIVED
connection. `/theme/stream` always succeeds (there is always a "current theme"
to emit) and always holds the connection open — so a client that opens the
stream and simply never closes it is the specific abuse shape the workable
item calls out, and nothing in the existing suite drives it.

TWO PROPERTIES, TWO ORACLES:

  1. BURST-REFUSAL AT THE ROUTE, NOT JUST THE CLASS. `/theme/stream` and
     `/search/stream/{id}` share the `sse_stream` rate-limit CLASS, but each
     route carries its OWN `@_rl("sse_stream")` decorator independently. A
     regression that drops the decorator from JUST `/theme/stream` (while
     leaving the search-stream one intact) would be invisible to
     `test_request_flood.py`. Tested here by driving a capped burst of STREAM
     OPENS against this specific route and asserting the SAME refused/served
     population properties `test_request_flood.py` already establishes for
     the sibling route.

  2. AN OPEN STREAM MUST NOT STARVE BYSTANDERS (the slow-loris property
     itself). This is the SAME class of question `test_slow_request.py`
     answers for a synthetic in-handler sleep — but here the "slow" resource
     is the REAL production generator's own `asyncio.wait_for(queue.get(),
     timeout=15)` loop, not an injected delay. One stream is opened and held,
     its first SSE event is read to prove it is genuinely live, and WHILE it
     is still open a batch of bystander `/health` probes must all be served
     promptly — proving the generator's `await` genuinely yields the event
     loop rather than blocking it.

HOW A STREAM IS OPENED-WITHOUT-HANGING (host safety, §12/§12.6/§12.11). Every
open stream in this file is entered via `httpx`'s streaming context manager
(`client.stream(...)` / an async `AsyncClient.stream(...)`), which returns as
soon as response HEADERS arrive — it never waits for the (never-ending) body.
Every opened stream is explicitly closed by exiting its `with`/`async with`
block before the next one is opened; nothing here holds more than ONE stream
connection open at a time, and no sleep or wall-clock wait of any kind is used
— the bystander probes fire immediately after the held stream's first SSE
event is observed, never after a timed wait.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

from .conftest import MAX_BURST_REQUESTS, build_app

_ATTACKER = "203.0.113.41"  # TEST-NET-3 (RFC 5737) — never a routable host
_BYSTANDER = "198.51.100.77"  # TEST-NET-2 (RFC 5737)

_STREAM_LIMIT = 6

#: Bystander probes fired while one theme stream is held open. Cheap
#: in-process /health GETs; small and bounded, well under
#: tests/ddos/conftest.py's MAX_CONCURRENT_CLIENTS ceiling intent for this
#: kind of concurrent-probe burst.
_BYSTANDER_PROBE_COUNT = 5


def _sync_client(app) -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def _async_client(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://ddos.invalid")


@pytest.mark.ddos
class TestThemeStreamBurstIsRefusedNotServed:
    def test_burst_of_stream_opens_is_refused_past_the_limit_with_no_5xx(self):
        """Mirrors `test_request_flood.py::TestSseStreamFloodIsRefused`, but
        against `/theme/stream` specifically — proving THIS route's own
        `@_rl("sse_stream")` decorator, not merely the shared class."""
        api_mod, _ = build_app(sse=f"{_STREAM_LIMIT}/minute")

        codes: list[int] = []
        with _sync_client(api_mod.app) as c:
            for _ in range(MAX_BURST_REQUESTS):
                with c.stream(
                    "GET", "/api/v1/theme/stream", headers={"X-Forwarded-For": _ATTACKER}
                ) as response:
                    codes.append(response.status_code)
            after = c.get("/health")

        assert [s for s in codes if s >= 500] == [], f"5xx leaked on the theme-stream flood: codes={codes}"
        assert codes.count(200) == _STREAM_LIMIT, (
            f"expected exactly {_STREAM_LIMIT} stream opens to reach the handler "
            f"before the limiter engaged; codes={codes}"
        )
        assert codes.count(429) == MAX_BURST_REQUESTS - _STREAM_LIMIT, (
            f"expected the remaining {MAX_BURST_REQUESTS - _STREAM_LIMIT} stream-open "
            f"attempts to be refused with 429; codes={codes}"
        )
        assert after.status_code == 200, (
            f"service stopped answering /health after a theme-stream flood: HTTP {after.status_code}"
        )

    def test_flooding_client_does_not_deny_a_bystander_a_stream(self):
        api_mod, _ = build_app(sse=f"{_STREAM_LIMIT}/minute")

        with _sync_client(api_mod.app) as c:
            attacker_codes = []
            for _ in range(MAX_BURST_REQUESTS):
                with c.stream(
                    "GET", "/api/v1/theme/stream", headers={"X-Forwarded-For": _ATTACKER}
                ) as response:
                    attacker_codes.append(response.status_code)
            with c.stream(
                "GET", "/api/v1/theme/stream", headers={"X-Forwarded-For": _BYSTANDER}
            ) as bystander:
                bystander_code = bystander.status_code

        assert 429 in attacker_codes, (
            f"precondition: the attacker must actually have been throttled; codes={attacker_codes}"
        )
        assert bystander_code == 200, (
            f"collateral denial of service: a bystander's /theme/stream open got HTTP "
            f"{bystander_code} while another client was being throttled"
        )


@pytest.mark.ddos
class TestThemeStreamOpenConnectionDoesNotStarveBystanders:
    async def test_one_open_stream_does_not_block_concurrent_health_probes(self):
        """The slow-loris-shaped property itself: a client that opens the
        stream and holds it open (never sends the disconnect the generator's
        loop is waiting to observe) must not prevent OTHER clients from being
        served — proving the real production generator's own `await` yields
        the event loop rather than serialising the server on one connection.
        """
        api_mod, _ = build_app(sse="60/minute", default="500/minute")

        async with _async_client(api_mod.app) as client:
            async with client.stream(
                "GET", "/api/v1/theme/stream", headers={"X-Forwarded-For": _ATTACKER}
            ) as held:
                assert held.status_code == 200, (
                    f"precondition: the held stream must open successfully, got {held.status_code}"
                )
                # Read the immediate "current theme" emission to prove the
                # stream is GENUINELY live (not merely headers-only) before
                # asserting anything about bystanders while it stays open.
                first_event = await anext(held.aiter_bytes())
                assert b"event: theme" in first_event, (
                    f"expected the immediate current-theme SSE event, got: {first_event!r}"
                )

                # WHILE the stream is still open (this `async with` has not
                # exited), fire the bystander probes concurrently.
                probes = await asyncio.gather(
                    *[client.get("/health", headers={"X-Forwarded-For": _BYSTANDER}) for _ in range(_BYSTANDER_PROBE_COUNT)]
                )

            # The held stream is now closed (block exited) — confirm the
            # service is still healthy afterwards too (post-attack liveness).
            after = await client.get("/health")

        assert all(p.status_code == 200 for p in probes), (
            f"a bystander /health probe was not served while a theme stream was held open: "
            f"{[p.status_code for p in probes]}"
        )
        assert after.status_code == 200, (
            f"service stopped answering /health after closing the held theme stream: HTTP {after.status_code}"
        )
