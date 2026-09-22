"""Per-IP rate limiting for the merge service's public HTTP surface (BOB-111).

SCOPE — THIS MODULE COVERS :7187 ONLY. An earlier revision of this docstring
claimed `install()` also covered "the proxy service on :7186 (same FastAPI app
object today)". That was MEASURED FALSE on 2026-08-21 against the operator's
live stack:

    Server: uvicorn                        (:7187 — this app)
    Server: BaseHTTP/0.6 Python/3.12.13    (:7186 — NOT this app)
    150 sequential GET :7186/  ->  200:150  429:0

:7186 is served by `plugins/download_proxy.py::run_server()`, a stdlib
`ThreadingHTTPServer` started on a SEPARATE THREAD by
`download-proxy/src/main.py::start_original_proxy`. It is not an ASGI app, so
`SlowAPIMiddleware` cannot reach it and never did. :7186 now carries its own
limiter, implemented in `plugins/download_proxy.py` under the SAME policy
contract (limit-string grammar, `RATE_LIMIT_<CLASS>` env naming,
`RATE_LIMIT_DISABLED`, `TRUST_FORWARDED_FOR` opt-in, fixed window, and an
identical `{"error": "rate_limited"}` + `Retry-After` refusal) — see the
BOB-111 block comment there for why the transport adapter has to differ and
why it stays stdlib-only. Guarded by
`tests/security/test_rate_limit_download_proxy.py`.

The merge service's public endpoints MUST NOT be open to unbounded request
rates — the BOB-112 forensics showed unlimited
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

§11.4.196(F) CONFIGURED != IN USE: `tests/security/test_rate_limit_public_endpoints.py`
drives the REAL `api.app` and asserts each public class refuses at its
configured threshold AND succeeds below it. The unit test above builds its own
FastAPI app, so it alone cannot notice a production route losing its decorator.

Per-IP isolation (caller A throttled does NOT throttle caller B) and the
burst-behaviour check live in `tests/unit/test_rate_limit.py`
(`test_green_different_ip_is_not_rate_limited`, `test_chaos_burst_produces_429s_no_5xx`).

RELOAD HAZARD (measured 2026-08-20): `importlib.reload(api)` does NOT reload the
cached `api.routes` submodule, so production routes stay bound to the PREVIOUS
generation's Limiter while `SlowAPIMiddleware` consults the new one. The stale
limiter keeps enforcing its already-exhausted counters and every request is
refused with a false-positive 429 (§11.4.201(1)). A harness needing a fresh app
MUST purge `api*` from `sys.modules` instead of reloading, then call
`reset_counters()`.
"""

from __future__ import annotations

import ipaddress
import logging
import os
from collections.abc import Callable
from typing import Any

import limits
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from slowapi.wrappers import Limit

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

#
# BOB-171 FIX (closes the BOB-111 review M3 follow-up). X-Forwarded-For's
# LEFTMOST entry is CLIENT-SUPPLIED and therefore forgeable by design: behind
# a proxy that APPENDS (rather than REPLACES) the header, an attacker who
# rotates a fabricated leftmost value mints an unlimited sequence of fresh
# per-IP buckets, both bypassing the rate limit AND defeating the bucket
# map's LRU/idle-reap eviction cap (forged identities crowd out real ones).
# This behaviour was EXACT PARITY with `plugins/download_proxy.py`'s
# `_rate_limit_client` (the :7186 proxy) — see that module's matching BOB-171
# block comment; both sites are fixed identically here so the two surfaces
# never disagree on client identity (§11.4.251).
#
# THE FIX — a trusted-proxy CIDR allowlist (`TRUSTED_PROXY_CIDRS`, a
# comma-separated list of CIDR blocks). X-Forwarded-For is honoured ONLY when
# BOTH (1) TRUST_FORWARDED_FOR is on AND (2) the REAL, socket-level peer
# address is inside an allowlisted CIDR — i.e. only a request arriving
# directly from a proxy the operator has explicitly vouched for may assert an
# XFF value at all. When it is trusted, the RIGHTMOST entry is used (the
# address that trusted proxy itself appended for whoever connected to IT,
# which an attacker sitting in front of that proxy cannot set — the leftmost
# entry always can). An unset/empty TRUSTED_PROXY_CIDRS, or a peer outside
# every allowlisted CIDR, means "trust nothing" and falls back to the raw
# peer address — IDENTICAL to TRUST_FORWARDED_FOR being off, which is the
# safe default an operator gets by doing nothing further.
#
# WHY THIS MECHANISM, NOT THE ALTERNATIVE. BOB-171 names two closure options:
# (i) rightmost-minus-N-trusted-hops, or (ii) a trusted-proxy CIDR allowlist
# (this one), framing the choice between them as "a deployment-topology
# decision [that] should be recorded, not assumed" — no operator decision on
# THIS specific choice exists yet. The CIDR allowlist was CHOSEN BY THE
# IMPLEMENTING AGENT fixing BOB-171 as the more conservative default for a
# project with no recorded reverse-proxy deployment topology: it degrades
# safely to today's behaviour with zero configuration, whereas a bare hop
# count has no such safe zero-config default. This is an implementation
# choice, not an operator-made one — if the real deployment topology later
# needs multiple CHAINED trusted proxies (option i's shape), an operator can
# swap this function for hop-count parsing instead.
#
# Honest scope note: this closes the header-forgery bypass. It does not make
# per-IP limiting fair behind NAT, where many real users legitimately share
# one address — that is a distinct, out-of-scope problem.


def _trusted_proxy_networks() -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    """Parse `TRUSTED_PROXY_CIDRS` (comma-separated) into ip_network objects.

    Unset/empty -> `[]` -> `_peer_is_trusted_proxy` always returns False ->
    the same "ignore X-Forwarded-For entirely" behaviour as
    TRUST_FORWARDED_FOR being off (the safe default). An unparsable entry is
    skipped with a loud log line rather than raising (§11.4.201: a malformed
    knob degrades only the feature it configures, never the whole process —
    the same loud-fallback shape `_env_limit` already uses for limit
    strings).
    """
    raw = os.getenv("TRUSTED_PROXY_CIDRS", "").strip()
    if not raw:
        return []
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        try:
            networks.append(ipaddress.ip_network(entry, strict=False))
        except ValueError:
            logger.warning("TRUSTED_PROXY_CIDRS: ignoring unparsable entry %r", entry)
    return networks


def _peer_is_trusted_proxy(peer: str) -> bool:
    """True iff `peer` (the RAW socket peer address) is inside an allowlisted CIDR."""
    networks = _trusted_proxy_networks()
    if not networks:
        return False
    try:
        addr = ipaddress.ip_address(peer)
    except ValueError:
        return False
    return any(addr in net for net in networks)


def _client_key(request: Request) -> str:
    peer = get_remote_address(request)
    if os.getenv("TRUST_FORWARDED_FOR", "").strip().lower() not in ("1", "true", "yes"):
        return peer

    if not _peer_is_trusted_proxy(peer):
        # TRUST_FORWARDED_FOR is on, but this connection did not arrive
        # directly from an allowlisted proxy — never honour XFF from an
        # untrusted peer. Same behaviour as the flag being off.
        return peer

    fwd = request.headers.get("x-forwarded-for", "").strip()
    if not fwd:
        return peer

    # RIGHTMOST entry only — see the block comment above. The leftmost entry
    # (the pre-fix behaviour) is always attacker-controlled.
    parts = [p.strip() for p in fwd.split(",") if p.strip()]
    return parts[-1] if parts else peer


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


def reset_counters() -> None:
    """Drop every per-IP counter currently held by the active limiter.

    A real lifecycle operation, not a test-only stub: it is the supported way
    to return the limiter to a quiescent baseline without rebuilding the app —
    used when a harness needs deterministic isolation between cases
    (§11.4.14), and by an operator clearing buckets after a storage-backend
    rotation. No-op when rate limiting is disabled.

    Errors from the storage backend are NOT swallowed (§11.4.252): a caller
    that asked for a clean baseline must learn if it did not get one.
    """
    if _limiter is None:
        return
    _limiter._storage.reset()


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
    `@limiter.limit("10/minute")` on the route function. Called by
    `download-proxy/src/api/__init__.py` — the merge service on :7187, and
    ONLY that. :7186 is a separate stdlib server on its own thread and carries
    its own limiter (see this module's SCOPE note).

    Idempotent: calling twice is a no-op — the second call returns the same
    Limiter without stacking middleware (guards against import-order surprises
    in test harnesses that reload the module).
    """
    global _limiter, _active_limits
    resolved = {
        "search": search_limit or _env_limit("search"),
        "dashboard": dashboard_limit or _env_limit("dashboard"),
        "sse_stream": sse_limit or _env_limit("sse_stream"),
        "default": _env_limit("default"),
    }

    existing: Limiter | None = getattr(app.state, "limiter", None)
    if existing is not None:
        # Already wired on this app — do NOT stack a second middleware. But we
        # MUST still publish the module-level state: `_rl()` in routes.py reads
        # `get_limiter()`, and returning early with `_limiter` still None makes
        # every per-route decorator a silent passthrough, leaving the public
        # endpoints unlimited while `app.state.rate_limit_config` still reports
        # a healthy configuration (§11.4.196(F) CONFIGURED != IN USE).
        _limiter = existing
        _active_limits = resolved
        app.state.rate_limit_config = dict(resolved)
        return existing

    limiter = _build_limiter()
    _limiter = limiter
    app.state.limiter = limiter
    _active_limits = resolved
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


def search_limit_decorator(app: FastAPI) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
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


def dashboard_limit_decorator(app: FastAPI) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    limiter: Limiter = app.state.limiter
    return limiter.limit(app.state.rate_limit_config["dashboard"])


def sse_limit_decorator(app: FastAPI) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    limiter: Limiter = app.state.limiter
    return limiter.limit(app.state.rate_limit_config["sse_stream"])


# ---------------------------------------------------------------------------
# 422-BYPASS CLOSURE (BOB-111 follow-up, measured 2026-08-20)
#
# THE HOLE. FastAPI validates the request body BEFORE calling the endpoint
# function, so a `@limiter.limit()` decorator wrapping that function never runs
# when validation fails. slowapi's middleware ALSO refuses to apply its default
# limits to any endpoint carrying an explicit decorator — see extension.py's
# guard `not (in_middleware and endpoint_func_name in self.__marked_for_limiting)`
# — because it expects the decorator to do the work. Neither fires on a 422, so
# malformed requests to a decorated public endpoint cost NOTHING:
#
#     135 invalid POSTs to /api/v1/search -> 422:135  429:0   (TOTAL bypass)
#     control, undecorated /health        -> first 429 at #121 (default works)
#
# THE CLOSURE. Route-level DEPENDENCIES run before the 422 is raised (verified:
# an invalid body yields status=422 with the dependency already executed). So
# the charge is moved into a dependency, which is reached on BOTH the valid and
# the invalid path. It raises the same RateLimitExceeded the decorator would, so
# `_rate_limited_response` formats an identical minimal 429 — no second response
# shape to keep in sync.
#
# IMPORTANT: a route using this dependency must NOT also carry `@_rl(<class>)`,
# or a well-formed request would be charged twice. Guarded by
# tests/security/test_rate_limit_public_endpoints.py::
#   test_valid_requests_are_not_double_charged
# ---------------------------------------------------------------------------


def rate_limit_dependency(class_name: str) -> Callable[[Request], None]:
    """Return a FastAPI dependency charging `class_name`'s bucket per IP.

    Use INSTEAD OF the `@_rl(class_name)` decorator on any endpoint that parses
    a request body, so malformed payloads are charged too. No-op when rate
    limiting is disabled (RATE_LIMIT_DISABLED=1), matching `_rl`'s passthrough.
    """

    def _charge(request: Request) -> None:
        limiter = get_limiter()
        if limiter is None:
            return
        parsed = limits.parse(limit_for(class_name))
        wrapped = Limit(
            parsed,
            limiter._key_func,
            f"boba:{class_name}",
            False,
            None,
            None,
            None,
            1,
            False,
        )
        key = limiter._key_func(request)
        scope = f"boba:{class_name}"
        # slowapi's `_rate_limit_exceeded_handler` AND its middleware both read
        # `request.state.view_rate_limit` to build Retry-After / X-RateLimit-*
        # headers. The decorator sets it (extension.py:530); a hand-rolled
        # dependency must too, or the 429 handler dies with
        # `AttributeError: 'State' object has no attribute 'view_rate_limit'`
        # (measured). Shape is (RateLimitItem, [identifiers]) — the SAME
        # identifiers passed to hit(), so get_window_stats() can find the bucket.
        # Set on BOTH paths: successful responses get headers too.
        request.state.view_rate_limit = (parsed, [key, scope])
        # One shared bucket per (client, class) — the scope keeps the invalid
        # and valid paths on the SAME counter rather than giving malformed
        # requests their own free allowance.
        if not limiter.limiter.hit(parsed, key, scope):
            raise RateLimitExceeded(wrapped)

    return _charge
