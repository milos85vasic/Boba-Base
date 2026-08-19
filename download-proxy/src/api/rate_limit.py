"""Per-IP rate limiting for the merge service's public HTTP surface (BOB-111).

Public endpoints on ports 7186 (proxy) + 7187 (merge dashboard/API) MUST NOT be
open to unbounded request rates — the BOB-112 forensics showed unlimited
POST /api/v1/search calls can DDoS the tracker fan-out (`wrk` hit >1000 req/s
against an untuned service and starved every legitimate caller). This module
adds slowapi-backed per-IP rate limiting with three closed classes:

  * POST /api/v1/search            — 10/minute per IP (expensive fan-out)
  * GET  /  and  /dashboard         — 60/minute per IP (SPA loads)
  * GET  /api/v1/search/stream/*    — 5/minute per IP  (long-lived SSE)

A rejected request returns HTTP 429 with a MINIMAL JSON body
`{"error": "rate_limited"}` and a `Retry-After` header — NO §11.4.10-sensitive
data is leaked (no client IP, no limit configuration, no bucket internals). A
consuming operator MAY override per-endpoint limits via env vars — see
`_env_limit` — the vars carry limit strings only, never secrets.

§11.4.115 RED-first: `tests/unit/test_rate_limit.py` proves the 11th request in
a minute is refused with 429 AND that dropping the middleware (paired §1.1
mutation) makes the test FAIL — the assertion catches its own negation.

§11.4.85 chaos: `tests/integration/test_rate_limit_chaos.py` proves 100 requests
from one IP produce some 429s while a different IP stays UNTHROTTLED — the
mechanism is per-IP + does not brown-out the service for other callers.
"""

from __future__ import annotations

import logging
import os
from typing import Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Limit resolution: hardcoded defaults, env-overridable per class. NEVER a
# per-request runtime value — that would defeat the point (an attacker cannot
# lift their own limit by sending a header). §11.4.6: values are FACT here.
# ---------------------------------------------------------------------------

DEFAULT_LIMITS: dict[str, str] = {
    # Expensive: cross-tracker search fan-out.
    "search": "10/minute",
    # Cheap-ish: static SPA + JSON reads.
    "dashboard": "60/minute",
    # Long-lived + costs a persistent connection.
    "sse_stream": "5/minute",
    # Fallback for any endpoint that opts in without a specific class.
    "default": "120/minute",
}


def _env_limit(class_name: str) -> str:
    """Return the limit string for `class_name`, honouring env override.

    Env var: `RATE_LIMIT_<CLASS>` (uppercased) — e.g. `RATE_LIMIT_SEARCH`.
    """
    key = f"RATE_LIMIT_{class_name.upper()}"
    raw = os.getenv(key, "").strip()
    if raw:
        return raw
    return DEFAULT_LIMITS[class_name]


# ---------------------------------------------------------------------------
# Key function: per-IP, but honours X-Forwarded-For's LEFTMOST entry when the
# service is deployed behind a reverse proxy the operator has explicitly
# trusted via TRUST_FORWARDED_FOR=1. Default OFF — a naive X-Forwarded-For
# trust lets any client claim any source IP + trivially bypass per-IP limits.
# ---------------------------------------------------------------------------

def _client_key(request: Request) -> str:
    if os.getenv("TRUST_FORWARDED_FOR", "").strip().lower() in ("1", "true", "yes"):
        fwd = request.headers.get("x-forwarded-for", "").strip()
        if fwd:
            # Leftmost = the original client, per RFC 7239 / de-facto convention.
            return fwd.split(",")[0].strip()
    return get_remote_address(request)


# ---------------------------------------------------------------------------
# The Limiter instance. `storage_uri` defaults to in-memory (single-process);
# a Redis / memcached URI keeps per-IP counters coherent across workers.
# `strategy=fixed-window` matches the 10/minute contract literally — a sliding
# window would allow bursts at the boundary the wrk RED test measures against.
# ---------------------------------------------------------------------------

def _build_limiter() -> Limiter:
    return Limiter(
        key_func=_client_key,
        default_limits=[_env_limit("default")],
        storage_uri=os.getenv("RATE_LIMIT_STORAGE_URI", "memory://"),
        strategy=os.getenv("RATE_LIMIT_STRATEGY", "fixed-window"),
        headers_enabled=True,
    )


def _rate_limited_response(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Minimal 429 body — never leaks IP / limit config / bucket internals.

    §11.4.10 — response body carries a stable error token only. The `Retry-After`
    header comes from slowapi's `_rate_limit_exceeded_handler` (it computes the
    seconds-until-reset without exposing which key was hit).
    """
    # Delegate to slowapi to get the correct `Retry-After` + rate-limit headers,
    # then REPLACE the verbose default body with a fixed opaque token.
    original: JSONResponse = _rate_limit_exceeded_handler(request, exc)  # type: ignore[assignment]
    return JSONResponse(
        status_code=429,
        content={"error": "rate_limited"},
        headers={k: v for k, v in original.headers.items() if k.lower() in {"retry-after", "x-ratelimit-limit", "x-ratelimit-remaining", "x-ratelimit-reset"}},
    )


# Module-level shared limiter — assigned by `install()`. Other modules
# (routes.py, streaming.py) grab this AFTER install() has run at import time
# in api/__init__.py, avoiding a circular import back to the FastAPI app.
_limiter: Limiter | None = None
_active_limits: dict[str, str] = dict(DEFAULT_LIMITS)


def get_limiter() -> Limiter | None:
    """Return the shared Limiter, or None if rate limiting is disabled."""
    return _limiter


def limit_for(class_name: str) -> str:
    """Return the effective limit string for the given class."""
    return _active_limits.get(class_name, DEFAULT_LIMITS.get(class_name, "60/minute"))


def install(
    app: FastAPI,
    *,
    search_limit: str | None = None,
    dashboard_limit: str | None = None,
    sse_limit: str | None = None,
) -> Limiter:
    """Wire per-IP rate limiting into the given FastAPI `app`.

    Returns the `Limiter` so callers can attach per-endpoint decorators — the
    global middleware enforces `default_limits`; per-endpoint overrides use
    `@limiter.limit("10/minute")` on the route function. Called by both
    `download-proxy/src/api/__init__.py` (merge service :7187) and the proxy
    service on :7186 (same FastAPI app object today).

    Idempotent: calling twice is a no-op — the second call returns the same
    Limiter without stacking middleware (guards against import-order surprises
    in test harnesses that reload the module).
    """
    global _limiter, _active_limits
    existing: Limiter | None = getattr(app.state, "limiter", None)
    if existing is not None:
        return existing

    limiter = _build_limiter()
    _limiter = limiter
    app.state.limiter = limiter
    _active_limits = {
        "search": search_limit or _env_limit("search"),
        "dashboard": dashboard_limit or _env_limit("dashboard"),
        "sse_stream": sse_limit or _env_limit("sse_stream"),
        "default": _env_limit("default"),
    }
    app.state.rate_limit_config = dict(_active_limits)
    app.add_exception_handler(RateLimitExceeded, _rate_limited_response)  # type: ignore[arg-type]
    app.add_middleware(SlowAPIMiddleware)
    logger.info(
        "Rate limiting enabled: search=%s dashboard=%s sse=%s (key=%s)",
        app.state.rate_limit_config["search"],
        app.state.rate_limit_config["dashboard"],
        app.state.rate_limit_config["sse_stream"],
        "x-forwarded-for" if os.getenv("TRUST_FORWARDED_FOR", "").strip().lower() in ("1", "true", "yes") else "remote-addr",
    )
    return limiter


def search_limit_decorator(app: FastAPI) -> Callable[[Callable], Callable]:
    """Return a decorator applying the current `search` limit to a route.

    Usage in `routes.py`:

        from ..rate_limit import search_limit_decorator
        @router.post("/search")
        @search_limit_decorator(app)
        async def search(...): ...

    The indirection lets tests override `app.state.rate_limit_config['search']`
    before the route is registered.
    """
    limiter: Limiter = app.state.limiter
    return limiter.limit(app.state.rate_limit_config["search"])


def dashboard_limit_decorator(app: FastAPI) -> Callable[[Callable], Callable]:
    limiter: Limiter = app.state.limiter
    return limiter.limit(app.state.rate_limit_config["dashboard"])


def sse_limit_decorator(app: FastAPI) -> Callable[[Callable], Callable]:
    limiter: Limiter = app.state.limiter
    return limiter.limit(app.state.rate_limit_config["sse_stream"])
