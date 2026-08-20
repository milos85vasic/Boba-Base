"""Slow-client / slow-request resilience (§11.4.27(B) ddos, BOB-074).

THE ATTACK. A slowloris-class attacker does not send volume — it sends its
request SLOWLY, occupying a worker for as long as the server permits. The
resilience property is that a slow request occupies only ITSELF: other clients
keep being served PROMPTLY while it is in flight. A server that serialises on
the slow request has been taken down by one cheap connection.

THE ORACLE, AND HOW IT WAS ARRIVED AT (§11.4.115(F), §11.4.201).
Two earlier versions of this file were BLUFFS, and the paired §1.1 mutation
(`mutations/run_mutation_check.sh` M5 — a synchronous `time.sleep` in the
request path, i.e. real head-of-line blocking) is what exposed both:

  v1 asserted ORDERING (fast requests complete before the slow one). A blocking
     request still finishes last, so the ordering held and the test stayed green
     while the server was genuinely serialising.
  v2 asserted per-probe LATENCY. Also green — and the measurement explains why:
     a blocked event loop does not make the bystander probe SLOW, it stops
     scheduling it at all. Measured under M5: worst probe latency 0.0129s (well
     under any bar) while only 2 probes ran in a 0.948s window.

The observable that actually moves is bystander THROUGHPUT. With the loop free,
paced probes run for the whole slow window (~20 probes at 20ms over 0.4s);
blocked, they are starved (2 of an expected ~47 under M5). Both signals are
asserted below — throughput as the primary oracle, latency as a secondary that
catches a server which is scheduling bystanders but serving them slowly.

THE THRESHOLDS ARE SELF-CALIBRATING (§11.4.107(13) — never literature constants).
The throughput floor is computed from the slow request's OWN measured duration
and the pacing interval, then halved — so it adapts to whatever the host does
rather than hardcoding a count. The latency bar is derived from this package's
own `SLOW_REQUEST_DELAY_S`. Each test first measures the host's baseline
`/health` latency and SKIPs with `host_too_loaded_to_measure` if the baseline
already exceeds the bar (§11.4.3, §11.4.201(6)) — on a machine this busy a
false red would be as much a defect as a false green.

WHAT THIS LAYER CANNOT PROVE (§11.4.6, stated as fact, not hedged). These tests
drive the real ASGI app in-process, so they prove the APPLICATION does not
serialise. They say NOTHING about the TCP layer: partial headers, a dribbled TLS
handshake, kernel accept-queue exhaustion and uvicorn's own connection and
keep-alive timeouts all live below ASGI and are unreachable from here. That gap
is real and is recorded in `docs/TESTING.md` "DDoS tests — what this does NOT
cover"; a true socket-level slowloris probe is covered by NEITHER this suite nor
`challenges/scripts/ddos_resilience_challenge.sh`.
"""

from __future__ import annotations

import asyncio
import importlib
import time

import httpx
import pytest

from .conftest import (
    LIVENESS_PROBE_INTERVAL_S,
    MAX_CONCURRENT_CLIENTS,
    MAX_LIVENESS_PROBES,
    SLOW_REQUEST_DELAY_S,
    build_app,
)

#: The whole package must stay far inside the 60s pytest timeout.
_TEST_BUDGET_S = 15

#: A bystander request must be served in well under the time the slow request
#: occupies the server.
_FAST_LATENCY_CEILING_S = SLOW_REQUEST_DELAY_S / 2

#: Fraction of the theoretically-available probe slots that must actually run
#: while the slow request is in flight. 0.4 leaves generous room for scheduler
#: noise on a loaded host while still catching the ~4% starvation M5 produces.
_MIN_THROUGHPUT_FRACTION = 0.4


def _asgi_client(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://ddos.invalid",
        timeout=_TEST_BUDGET_S,
    )


async def _baseline_latency(client: httpx.AsyncClient, n: int) -> tuple[float, list[int]]:
    """Worst of `n` back-to-back /health probes, with no slow request running."""
    worst = 0.0
    codes: list[int] = []
    for _ in range(n):
        started = time.perf_counter()
        response = await client.get("/health")
        worst = max(worst, time.perf_counter() - started)
        codes.append(response.status_code)
    return worst, codes


async def _probe_until(
    client: httpx.AsyncClient, finished: asyncio.Event
) -> tuple[float, list[int]]:
    """Probe /health, PACED, for as long as the slow request is in flight.

    Pacing is load-bearing. Probes fired back-to-back drain in ~2ms, long before
    a slow request reaches its blocking section, so they sample the wrong window
    entirely. Spacing them by `LIVENESS_PROBE_INTERVAL_S` makes them SPAN the
    slow window; the resulting COUNT is what collapses when the loop is starved.
    Bounded by `MAX_LIVENESS_PROBES` so a hung slow request cannot spin here.
    """
    worst = 0.0
    codes: list[int] = []
    while not finished.is_set() and len(codes) < MAX_LIVENESS_PROBES:
        started = time.perf_counter()
        response = await client.get("/health")
        worst = max(worst, time.perf_counter() - started)
        codes.append(response.status_code)
        await asyncio.sleep(LIVENESS_PROBE_INTERVAL_S)
    return worst, codes


def _require_measurable_baseline(baseline: float) -> None:
    """Control needle: refuse to render a verdict the host cannot support."""
    if baseline >= _FAST_LATENCY_CEILING_S:
        pytest.skip(
            f"host_too_loaded_to_measure: baseline /health latency {baseline:.3f}s "
            f"already exceeds the {_FAST_LATENCY_CEILING_S:.3f}s bar, so an "
            "under-load measurement could not distinguish blocking from host noise"
        )


def _assert_bystanders_were_served(
    *, codes: list[int], worst: float, duration: float, baseline: float, what: str
) -> None:
    """The shared oracle: throughput first, then latency."""
    assert codes, f"no bystander probe ran at all while {what}"
    assert all(c == 200 for c in codes), f"bystanders were not served while {what}: {codes}"

    slots = duration / LIVENESS_PROBE_INTERVAL_S
    floor = max(2, int(slots * _MIN_THROUGHPUT_FRACTION))
    assert len(codes) >= floor, (
        f"event-loop starvation while {what}: only {len(codes)} bystander probes "
        f"completed during a {duration:.3f}s window that had room for ~{slots:.0f} "
        f"(floor {floor}). The slow request is occupying the whole server, not "
        "just its own connection."
    )
    assert worst < _FAST_LATENCY_CEILING_S, (
        f"head-of-line blocking while {what}: a bystander /health took "
        f"{worst:.3f}s (baseline {baseline:.3f}s, bar {_FAST_LATENCY_CEILING_S:.3f}s)"
    )


@pytest.mark.ddos
async def test_slow_handler_does_not_starve_concurrent_clients():
    """One slow in-flight request must not starve bystanders.

    The slowness is injected into the handler's OWN awaited
    `dispatch_event("search_start", ...)` — a real await inside the real request
    path, not a sleep bolted onto the test — so a server that serialises
    genuinely cannot serve the bystanders until it returns.
    """
    api_mod, _ = build_app(search="60/minute", default="500/minute")
    hooks = importlib.import_module("api.hooks")
    real_dispatch = hooks.dispatch_event

    async def slow_dispatch(event_type, event_data):  # noqa: ANN001
        if event_type == "search_start":
            await asyncio.sleep(SLOW_REQUEST_DELAY_S)
        return await real_dispatch(event_type, event_data)

    try:
        async with _asgi_client(api_mod.app) as client:
            baseline, baseline_codes = await _baseline_latency(client, MAX_CONCURRENT_CLIENTS)
            assert all(c == 200 for c in baseline_codes), f"baseline probe failed: {baseline_codes}"
            _require_measurable_baseline(baseline)

            hooks.dispatch_event = slow_dispatch
            finished = asyncio.Event()
            elapsed: list[float] = []

            async def slow() -> int:
                started = time.perf_counter()
                try:
                    r = await client.post(
                        "/api/v1/search",
                        json={"query": "slow-client", "validate_trackers": False},
                    )
                    return r.status_code
                finally:
                    elapsed.append(time.perf_counter() - started)
                    finished.set()

            slow_code, (worst, codes) = await asyncio.wait_for(
                asyncio.gather(slow(), _probe_until(client, finished)),
                timeout=_TEST_BUDGET_S,
            )
    finally:
        hooks.dispatch_event = real_dispatch

    assert slow_code < 500, f"the slow request itself 5xx'd: {slow_code}"
    _assert_bystanders_were_served(
        codes=codes,
        worst=worst,
        duration=elapsed[0],
        baseline=baseline,
        what="one request was slow",
    )


@pytest.mark.ddos
async def test_slow_request_body_does_not_starve_concurrent_clients():
    """A dribbled request BODY must not stall the service either.

    This is the closest reachable analogue of slowloris at the ASGI layer: the
    client streams its body in chunks with a pause between them, so the app is
    genuinely awaiting `receive()` while other requests arrive. It is NOT a
    partial-header slowloris on a real socket (see module docstring).
    """
    api_mod, _ = build_app(search="60/minute", default="500/minute")

    chunks = [b'{"query": "slow', b'-body", "validate_trackers"', b": false}"]
    per_chunk_pause = SLOW_REQUEST_DELAY_S / len(chunks)

    async def dribble():
        for chunk in chunks:
            await asyncio.sleep(per_chunk_pause)
            yield chunk

    async with _asgi_client(api_mod.app) as client:
        baseline, baseline_codes = await _baseline_latency(client, MAX_CONCURRENT_CLIENTS)
        assert all(c == 200 for c in baseline_codes), f"baseline probe failed: {baseline_codes}"
        _require_measurable_baseline(baseline)

        finished = asyncio.Event()
        elapsed: list[float] = []

        async def slow() -> int:
            started = time.perf_counter()
            try:
                r = await client.post(
                    "/api/v1/search",
                    content=dribble(),
                    headers={"Content-Type": "application/json"},
                )
                return r.status_code
            finally:
                elapsed.append(time.perf_counter() - started)
                finished.set()

        slow_code, (worst, codes) = await asyncio.wait_for(
            asyncio.gather(slow(), _probe_until(client, finished)),
            timeout=_TEST_BUDGET_S,
        )

    assert slow_code < 500, f"the slow-body request 5xx'd: {slow_code}"
    _assert_bystanders_were_served(
        codes=codes,
        worst=worst,
        duration=elapsed[0],
        baseline=baseline,
        what="a body was being dribbled",
    )
