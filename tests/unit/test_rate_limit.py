"""BOB-111 — per-IP rate limiting: RED-first + paired-mutation coverage.

The RED baseline: without rate limiting (`RATE_LIMIT_DISABLED=1`) an
unbounded number of POST /api/v1/search calls succeeds (all 200). The GREEN
guard: with rate limiting installed at the default 10/minute, the 11th call
from one IP within a minute is refused with HTTP 429 + `error=rate_limited`
body + `Retry-After` header.

§11.4.115(F): each verdict is machine-written (status-code arithmetic +
JSON parse), the fingerprint of the paired-mutation revert (RATE_LIMIT_DISABLED)
is different from the GREEN fingerprint, so the assertion CATCHES its own
negation. §11.4.10: the 429 body carries no client IP, no limit value —
only a stable `rate_limited` token.

§11.4.14 cleanup: every test resets the shared limiter storage before
returning so a leftover per-IP counter cannot contaminate a sibling test.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient

# Make download-proxy/src importable without a full install.
_DP_SRC = Path(__file__).resolve().parents[2] / "download-proxy" / "src"
if str(_DP_SRC) not in sys.path:
    sys.path.insert(0, str(_DP_SRC))


def _fresh_app(
    *,
    disabled: bool = False,
    search_limit: str = "10/minute",
    key_func=None,
) -> FastAPI:
    """Build a FastAPI app with the BOB-111 rate limiter installed.

    Uses a minimal app — we do NOT boot the full merge-service so unit tests
    stay hermetic + fast.

    ``key_func``, when given, is passed straight through to
    ``Limiter.limit(..., key_func=...)`` so the PER-ROUTE limit is keyed by
    it. slowapi's ``Limiter.limit()`` resolves ``key_func or self._key_func``
    and bakes the resolved callable into the route's ``Limit``/``LimitGroup``
    objects AT DECORATION TIME (i.e. right here, inside this function) — a
    monkeypatch of ``api.rate_limit._client_key`` (or of
    ``app.state.limiter._key_func``) applied by the CALLER *after*
    ``_fresh_app()`` returns has no effect on the already-decorated route,
    because the route never re-reads the Limiter's key func at request time.
    Passing the desired key func in HERE, before decoration happens, is the
    only way to make a per-caller-identity simulation actually reach the
    per-route check.
    """
    if disabled:
        os.environ["RATE_LIMIT_DISABLED"] = "1"
    else:
        os.environ.pop("RATE_LIMIT_DISABLED", None)
    os.environ["RATE_LIMIT_SEARCH"] = search_limit

    # Fresh module load — the module-level `_limiter` is stateful across
    # imports; reload guarantees per-test isolation.
    import importlib

    import api.rate_limit as rl

    importlib.reload(rl)

    app = FastAPI()
    if not disabled:
        rl.install(app)

    def _decor():
        lim = rl.get_limiter()
        return (lambda f: f) if lim is None else lim.limit(rl.limit_for("search"), key_func=key_func)

    @app.post("/api/v1/search")
    @_decor()
    async def search(request: Request, response: Response):
        # BOB-126-followup: slowapi's post-call header injection
        # (`Limiter._inject_headers`) requires the decorated endpoint to
        # accept a real `starlette.responses.Response` via FastAPI's
        # `response:` special parameter — without it slowapi's wrapper
        # calls `kwargs.get("response")`, gets `None`, and raises
        # ``Exception: parameter `response` must be an instance of
        # starlette.responses.Response`` on every request that does NOT
        # hit the rate limit (the 429 path never reaches this code —
        # slowapi raises `RateLimitExceeded` before calling `func`).
        # Declaring `response: Response` here mirrors the proven fix
        # pattern from BOB-122 (d7da1af) applied to this test's own
        # locally-defined FastAPI app.
        return {"ok": True}

    return app


def _reset_env() -> None:
    for k in list(os.environ):
        if k.startswith("RATE_LIMIT_"):
            os.environ.pop(k, None)


# ---------------------------------------------------------------------------
# RED baseline — rate limiting disabled, N > limit calls all succeed.
# ---------------------------------------------------------------------------


def test_red_baseline_unlimited_when_disabled():
    """Paired-mutation RED: strip rate limiting -> 20 calls all 200."""
    app = _fresh_app(disabled=True)
    client = TestClient(app)
    codes = [client.post("/api/v1/search").status_code for _ in range(20)]
    assert codes.count(200) == 20, f"expected 20x 200, got {codes}"
    assert 429 not in codes, "429 must NOT appear when rate limiting is disabled (proves the guard is off)"
    _reset_env()


# ---------------------------------------------------------------------------
# GREEN guard — 11th call within one minute returns 429 + minimal body.
# ---------------------------------------------------------------------------


def test_green_11th_call_returns_429_with_minimal_body():
    app = _fresh_app(disabled=False, search_limit="10/minute")
    client = TestClient(app)
    for i in range(10):
        r = client.post("/api/v1/search")
        assert r.status_code == 200, f"call {i + 1} should succeed, got {r.status_code}"

    r11 = client.post("/api/v1/search")
    assert r11.status_code == 429, f"11th call must be rate-limited, got {r11.status_code}"

    body = r11.json()
    assert body == {"error": "rate_limited"}, (
        "429 body must be MINIMAL — the exact opaque token, no client IP, no "
        "limit value, no bucket internals leaked (§11.4.10). Got: " + repr(body)
    )
    assert "retry-after" in {k.lower() for k in r11.headers.keys()}, "Retry-After header required"
    _reset_env()


def test_green_body_never_leaks_client_ip_or_limit_value():
    """§11.4.10: the 429 response text must not contain the IP or the limit."""
    app = _fresh_app(disabled=False, search_limit="3/minute")
    client = TestClient(app)
    for _ in range(3):
        client.post("/api/v1/search")
    r = client.post("/api/v1/search")
    assert r.status_code == 429
    payload = r.text
    for forbidden in ("127.0.0.1", "testclient", "3/minute", "3 per 1 minute", "remote_address"):
        assert forbidden not in payload, f"429 body leaked {forbidden!r}: {payload}"
    _reset_env()


def test_green_different_ip_is_not_rate_limited():
    """Per-IP scope: caller A being throttled does NOT throttle caller B."""
    # Simulate distinct client IPs by supplying the key function used by
    # slowapi's per-route Limit *at decoration time* (see the `key_func`
    # docstring on `_fresh_app`) — in production this maps to the real
    # remote_addr. A post-hoc monkeypatch of `api.rate_limit._client_key`
    # or of `app.state.limiter._key_func` (the original approach here)
    # has NO effect: slowapi's `Limiter.limit()` resolves and bakes the
    # key func into the route's `Limit` object the moment the decorator
    # is applied, so by the time the app object exists it is already too
    # late to change which key the route checks against.
    current_ip = {"v": "10.0.0.1"}

    # NOTE: slowapi's `__evaluate_limits` introspects the key func's
    # signature and only passes the `request` positional arg when a
    # parameter is literally named `request` (`"request" in
    # inspect.signature(lim.key_func).parameters.keys()`) — otherwise it
    # calls `lim.key_func()` with ZERO arguments. The parameter MUST be
    # named `request` (matching `api.rate_limit._client_key`'s own
    # signature), not merely accept one positionally.
    def _key_func(request):  # noqa: ARG001 - required by slowapi's signature probe
        return current_ip["v"]

    app = _fresh_app(
        disabled=False,
        search_limit="2/minute",
        key_func=_key_func,
    )
    client = TestClient(app)

    # Caller A: exhaust the 2/minute budget.
    for _ in range(2):
        assert client.post("/api/v1/search").status_code == 200
    assert client.post("/api/v1/search").status_code == 429

    # Caller B (different IP) is a separate bucket → still allowed.
    current_ip["v"] = "10.0.0.2"
    assert client.post("/api/v1/search").status_code == 200
    _reset_env()


# ---------------------------------------------------------------------------
# §11.4.85 chaos-light: burst 50 -> some 429s, but the service stays
# responsive (no crash, no 5xx, every response is either 200 or 429).
# ---------------------------------------------------------------------------


def test_chaos_burst_produces_429s_no_5xx():
    app = _fresh_app(disabled=False, search_limit="5/minute")
    client = TestClient(app)
    codes = [client.post("/api/v1/search").status_code for _ in range(50)]
    ok = codes.count(200)
    limited = codes.count(429)
    assert ok == 5, f"exactly 5 should succeed under 5/minute; got {ok} — codes: {codes}"
    assert limited == 45, f"remaining should be 429; got {limited} — codes: {codes}"
    assert all(c in (200, 429) for c in codes), f"no 5xx allowed during burst; got {codes}"
    _reset_env()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
