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
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

# Make download-proxy/src importable without a full install.
_DP_SRC = Path(__file__).resolve().parents[2] / "download-proxy" / "src"
if str(_DP_SRC) not in sys.path:
    sys.path.insert(0, str(_DP_SRC))


def _fresh_app(*, disabled: bool = False, search_limit: str = "10/minute") -> FastAPI:
    """Build a FastAPI app with the BOB-111 rate limiter installed.

    Uses a minimal app — we do NOT boot the full merge-service so unit tests
    stay hermetic + fast.
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
        return (lambda f: f) if lim is None else lim.limit(rl.limit_for("search"))

    @app.post("/api/v1/search")
    @_decor()
    async def search(request: Request):
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


def test_green_different_ip_is_not_rate_limited(monkeypatch):
    """Per-IP scope: caller A being throttled does NOT throttle caller B."""
    app = _fresh_app(disabled=False, search_limit="2/minute")
    client = TestClient(app)

    # Simulate distinct client IPs by patching the key function used by
    # slowapi. In production this maps to the real remote_addr.
    import api.rate_limit as rl

    current_ip = {"v": "10.0.0.1"}
    monkeypatch.setattr(rl, "_client_key", lambda req: current_ip["v"])

    # Re-install a Limiter that uses the patched key.
    limiter = rl._build_limiter()
    # Rebuild the app's limiter with the patched key.
    app.state.limiter._key_func = lambda req: current_ip["v"]  # type: ignore[attr-defined]
    _ = limiter  # keep reference

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
