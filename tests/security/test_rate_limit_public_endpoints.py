"""BOB-111 — the §11.4.196(F) guard: boba's REAL public endpoints are rate
limited AT RUNTIME, not merely configured.

WHY THIS FILE EXISTS (it does not duplicate `tests/unit/test_rate_limit.py`).
`tests/unit/test_rate_limit.py` builds its OWN `FastAPI()` app, installs the
limiter on it, and decorates a locally-defined handler. That proves slowapi
works. It structurally CANNOT notice if a production route loses its
`@_rl(...)` decorator, if `install()` stops being called from
`api/__init__.py`, or if the router include order moves above the middleware
registration — in every one of those regressions the unit test stays GREEN
while boba's public surface is wide open. This file closes exactly that gap
by driving `api.app` — the same object uvicorn serves.

EVIDENCE CLASS (§11.4.226), stated honestly: RUNTIME-ON-THE-REAL-ASGI-APP.
Starlette's `TestClient` executes the real middleware stack, the real routers
and the real slowapi decorators against the real `api.app`. It is NOT a
live-socket test — no uvicorn, no TCP, no container. It sits one layer below
that and several layers above a synthetic-app unit test. A socket-level
check belongs in the integration tier (owned elsewhere; see the module
docstring note in `download-proxy/src/api/rate_limit.py`).

BOTH DIRECTIONS ARE ASSERTED (§11.4.201(1)): every endpoint class carries an
under-threshold control proving requests below the limit SUCCEED. A limiter
that refuses everything is exactly as broken as one that refuses nothing —
and a stale-limiter regression really did produce blanket 429s on this app,
so the control is load-bearing, not ceremony.

ISOLATION BOUNDARY (stated explicitly, §11.4.27(A)). Exactly ONE thing is
stubbed: `SearchOrchestrator._run_search`, the background tracker fan-out. It
is replaced with an async no-op so a rate-limit test does not fire real
network traffic at RuTracker/Kinozal/NNMClub, shell out to the nova3 plugin
engine, or leak subprocess transports into the pytest session (measured: the
un-stubbed version spawned real `asyncio.create_subprocess_exec` children per
accepted request — `download-proxy/src/merge_service/search.py`). EVERYTHING
that this file actually asserts on stays real: the real `api.app`, the real
middleware stack, the real router, the real slowapi decorators, the real
env-driven limit resolution, and the real 429 handler. The fan-out is
downstream of the limiter and is not what is under test here.

§11.4.263: no subprocess/proc object is mocked anywhere in this file, so no
`mock.pid` is involved; the fan-out stub is a plain async function.
"""

from __future__ import annotations

import importlib
import os
import sys

import pytest
from fastapi.testclient import TestClient

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_SRC_PATH = os.path.join(_REPO_ROOT, "download-proxy", "src")
if _SRC_PATH not in sys.path:
    sys.path.insert(0, _SRC_PATH)

# Limits used by this file. Deliberately small so a test costs milliseconds,
# and injected through the SAME public env knobs an operator uses in
# production (`RATE_LIMIT_*`) — so the test also proves the knobs are wired.
_SEARCH_LIMIT = 4
_DASHBOARD_LIMIT = 6
_SSE_LIMIT = 3
_DEFAULT_LIMIT = 50


def _purge_api_modules() -> None:
    """Drop every `api*` module so the next import re-executes them in order.

    `importlib.reload(api)` is NOT sufficient and is actively harmful here:
    reloading the package does not reload the cached `api.routes` submodule,
    so the production routes stay bound to the PREVIOUS generation's Limiter
    while the middleware uses the new one. The two disagree, and the stale
    limiter keeps enforcing its old, already-exhausted counters — producing
    blanket false-positive 429s (§11.4.201(1)). Purging is the deterministic
    fix: one generation, one limiter, one set of counters.
    """
    for name in [m for m in sys.modules if m == "api" or m.startswith("api.")]:
        del sys.modules[name]


def _build_app(**limits: int):
    """Import the REAL production app with the given limits in force."""
    os.environ.pop("RATE_LIMIT_DISABLED", None)
    os.environ["RATE_LIMIT_SEARCH"] = f"{limits.get('search', _SEARCH_LIMIT)}/minute"
    os.environ["RATE_LIMIT_DASHBOARD"] = f"{limits.get('dashboard', _DASHBOARD_LIMIT)}/minute"
    os.environ["RATE_LIMIT_SSE_STREAM"] = f"{limits.get('sse', _SSE_LIMIT)}/minute"
    os.environ["RATE_LIMIT_DEFAULT"] = f"{limits.get('default', _DEFAULT_LIMIT)}/minute"

    _purge_api_modules()
    api_mod = importlib.import_module("api")
    rl_mod = importlib.import_module("api.rate_limit")
    # Counters must start empty even if a sibling module generation ran
    # earlier in this pytest session (§11.4.14 quiescent baseline).
    rl_mod.reset_counters()
    return api_mod, rl_mod


@pytest.fixture(autouse=True)
def _no_real_tracker_fanout(monkeypatch):
    """Neutralise the background tracker fan-out (see ISOLATION BOUNDARY).

    monkeypatch restores the real method after every test, so nothing here
    leaks into the rest of the suite (§11.4.14).
    """
    from merge_service.search import SearchOrchestrator

    async def _no_fanout(self, search_id, query, category="all"):  # noqa: ANN001
        metadata = self._active_searches.get(search_id)
        if metadata is not None:
            metadata.status = "completed"

    monkeypatch.setattr(SearchOrchestrator, "_run_search", _no_fanout)


@pytest.fixture(autouse=True)
def _isolate_rate_limit_env():
    saved = {k: v for k, v in os.environ.items() if k.startswith("RATE_LIMIT_")}
    yield
    for k in [k for k in os.environ if k.startswith("RATE_LIMIT_")]:
        os.environ.pop(k, None)
    os.environ.update(saved)
    _purge_api_modules()


@pytest.mark.security
class TestPublicEndpointsRateLimitedOnRealApp:
    """The three public classes BOB-111 names, exercised on `api.app`."""

    def test_search_below_threshold_succeeds_then_429_at_threshold(self):
        """POST /api/v1/search — control below the limit, 429 at it."""
        api_mod, _ = _build_app()
        client = TestClient(api_mod.app, raise_server_exceptions=False)

        # CONTROL (§11.4.201(1)): every request below the limit must succeed.
        for i in range(_SEARCH_LIMIT):
            r = client.post("/api/v1/search", json={"query": "boba-111-probe"})
            assert r.status_code == 200, (
                f"request {i + 1}/{_SEARCH_LIMIT} is BELOW the configured "
                f"{_SEARCH_LIMIT}/minute limit and must succeed, got "
                f"{r.status_code}: {r.text[:200]}"
            )

        # GUARD: the next one crosses the threshold.
        over = client.post("/api/v1/search", json={"query": "boba-111-probe"})
        assert over.status_code == 429, (
            f"request {_SEARCH_LIMIT + 1} exceeds the configured "
            f"{_SEARCH_LIMIT}/minute limit and must be refused with 429, got "
            f"{over.status_code}"
        )

    def test_dashboard_below_threshold_succeeds_then_429_at_threshold(self):
        """GET /dashboard — the SPA entry point."""
        api_mod, _ = _build_app()
        client = TestClient(api_mod.app, raise_server_exceptions=False)

        for i in range(_DASHBOARD_LIMIT):
            r = client.get("/dashboard")
            assert r.status_code == 200, (
                f"request {i + 1}/{_DASHBOARD_LIMIT} is below the limit and "
                f"must succeed, got {r.status_code}"
            )

        assert client.get("/dashboard").status_code == 429, (
            f"request {_DASHBOARD_LIMIT + 1} must be refused with 429"
        )

    def test_sse_stream_below_threshold_succeeds_then_429_at_threshold(self):
        """GET /api/v1/search/stream/{id} — long-lived SSE.

        An unknown search id yields 404 from the handler; that is a SUCCESSFUL
        trip THROUGH the limiter (the request was admitted and reached the
        route), which is exactly what the control needs to show. The limiter
        refusal is the distinct 429.
        """
        api_mod, _ = _build_app()
        client = TestClient(api_mod.app, raise_server_exceptions=False)

        for i in range(_SSE_LIMIT):
            r = client.get("/api/v1/search/stream/no-such-search")
            assert r.status_code == 404, (
                f"request {i + 1}/{_SSE_LIMIT} is below the limit and must be "
                f"admitted to the handler (404 unknown id), got {r.status_code}"
            )

        assert client.get("/api/v1/search/stream/no-such-search").status_code == 429, (
            f"request {_SSE_LIMIT + 1} must be refused with 429"
        )

    def test_429_body_is_minimal_and_leaks_nothing(self):
        """§11.4.10 — the refusal names no IP, no limit, no bucket internals."""
        api_mod, _ = _build_app()
        client = TestClient(api_mod.app, raise_server_exceptions=False)
        for _ in range(_SEARCH_LIMIT):
            client.post("/api/v1/search", json={"query": "x"})
        r = client.post("/api/v1/search", json={"query": "x"})

        assert r.status_code == 429
        assert r.json() == {"error": "rate_limited"}, (
            f"429 body must be the opaque token only, got {r.text[:300]}"
        )
        assert "retry-after" in {k.lower() for k in r.headers}, (
            "a 429 must tell the caller when to retry"
        )
        for leak in ("127.0.0.1", "testclient", f"{_SEARCH_LIMIT}/minute", "remote_address"):
            assert leak not in r.text, f"429 body leaked {leak!r}: {r.text[:300]}"

    def test_limits_come_from_env_not_hardcoded(self):
        """The operator knob is real: a different env value changes behaviour."""
        api_mod, _ = _build_app(search=2)
        client = TestClient(api_mod.app, raise_server_exceptions=False)

        assert client.post("/api/v1/search", json={"query": "x"}).status_code == 200
        assert client.post("/api/v1/search", json={"query": "x"}).status_code == 200
        assert client.post("/api/v1/search", json={"query": "x"}).status_code == 429, (
            "RATE_LIMIT_SEARCH=2/minute must refuse the 3rd call — if this is "
            "200 the env knob is decorative and the limit is hardcoded"
        )

    def test_production_routes_are_registered_with_the_live_limiter(self):
        """Structural guard: the decorators are on the LIVE limiter instance.

        Catches the regression where a route's limit is registered against a
        stale Limiter object while the middleware consults a different one —
        the routes then silently fall through to the global default (or worse,
        inherit an exhausted stale bucket).
        """
        api_mod, rl_mod = _build_app()
        live = api_mod.app.state.limiter
        assert rl_mod.get_limiter() is live, (
            "the module singleton and app.state.limiter must be the SAME "
            "object, otherwise per-route limits and the middleware disagree"
        )
        registered = set(getattr(live, "_route_limits", {}))
        # Decorator-bound routes (@_rl) register here.
        for endpoint in ("api.routes.search_stream", "api.dashboard"):
            assert endpoint in registered, (
                f"{endpoint} has no per-route limit on the live limiter — its "
                f"@_rl(...) decorator was lost. Registered: {sorted(registered)}"
            )

        # /api/v1/search is DEPENDENCY-bound, not decorator-bound: a decorator
        # cannot see a 422 because FastAPI validates the body before entering
        # the endpoint, which left malformed requests entirely un-limited
        # (measured: 135 invalid POSTs -> 429:0). Reconciled per §11.4.120 —
        # this asserts the NEW mechanism rather than the removed one, and is
        # NOT weakened: it still fails if the wiring is lost.
        # The app mounts its APIRouter via an _IncludedRouter wrapper, so the
        # POST /search route is NOT on app.routes directly and its stored path
        # is the UN-PREFIXED "/search" (the "/api/v1" prefix is applied at
        # include time). Verified by enumeration, not assumed.
        def _find_post_search(routes):
            for r in routes:
                if getattr(r, "path", None) in ("/search", "/api/v1/search") and (
                    "POST" in (getattr(r, "methods", None) or set())
                ):
                    yield r
                sub = getattr(r, "original_router", None)
                if sub is not None:
                    yield from _find_post_search(getattr(sub, "routes", []))

        search_routes = list(_find_post_search(api_mod.app.routes))
        assert search_routes, "POST /api/v1/search is not registered at all"
        dep_calls = [
            d.call
            for d in search_routes[0].dependant.dependencies
            if getattr(d, "call", None) is not None
        ]
        dep_modules = {getattr(c, "__module__", "") for c in dep_calls}
        assert any("rate_limit" in m for m in dep_modules), (
            "POST /api/v1/search has no rate-limit dependency — the 422-bypass "
            f"closure was lost. Dependencies: {sorted(dep_modules)}"
        )
        # And it must NOT also carry the decorator, or valid requests are
        # charged twice (once by the dependency, once by @_rl).
        assert "api.routes.search" not in registered, (
            "POST /api/v1/search is BOTH dependency-bound and decorator-bound — "
            "well-formed requests would be charged twice"
        )


@pytest.mark.security
class TestInstallPublishesModuleState:
    """`install()` must never return without publishing the module singleton.

    `routes.py`'s `_rl()` helper decides at import time whether to apply a real
    limit or a passthrough, and it decides by calling `get_limiter()`. If
    `install()` returns early (app already wired) while leaving the module
    singleton at None, every per-route decorator silently degrades to a no-op
    and the public endpoints go unlimited — while `app.state.rate_limit_config`
    keeps reporting a perfectly healthy configuration. That is the
    §11.4.196(F) CONFIGURED-but-not-IN-USE shape, and it is invisible to any
    check that only reads the config.
    """

    def test_second_install_still_publishes_the_limiter(self):
        from fastapi import FastAPI

        _purge_api_modules()
        rl_mod = importlib.import_module("api.rate_limit")

        app = FastAPI()
        first = rl_mod.install(app)
        assert rl_mod.get_limiter() is first

        # Simulate the module being re-imported while the app object survives
        # (harness reload, embedding process, double-wiring). The singleton is
        # cleared, but app.state.limiter still holds the original.
        rl_mod = importlib.reload(rl_mod)
        assert rl_mod.get_limiter() is None, "precondition: singleton cleared by reload"

        second = rl_mod.install(app)
        assert second is first, "must not build a second limiter for one app"
        assert rl_mod.get_limiter() is not None, (
            "install() returned early WITHOUT publishing the module singleton — "
            "_rl() in routes.py would now return a passthrough and every public "
            "endpoint would be silently unlimited"
        )
        assert rl_mod.get_limiter() is first
        assert rl_mod.limit_for("search"), "limit config must be published too"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


# ---------------------------------------------------------------------------
# 422-BYPASS (BOB-111 follow-up)
#
# FastAPI validates the request body BEFORE entering the endpoint function, so
# a @limiter.limit() decorator wrapping that function never runs on a 422. And
# slowapi's middleware deliberately SKIPS applying default limits to endpoints
# that carry an explicit decorator (extension.py: the guard
# `not (in_middleware and endpoint_func_name in self.__marked_for_limiting)`),
# expecting the decorator to do the work. Net effect measured 2026-08-20:
#
#     135 invalid POSTs to /api/v1/search -> 422:135  429:0   (TOTAL bypass)
#     control, undecorated /health        -> first 429 at #121 (default works)
#
# So an unauthenticated client could issue unbounded malformed requests to a
# public endpoint at zero rate-limit cost. Route-level dependencies DO run
# before the 422 is raised (verified), which is what closes the hole.
# ---------------------------------------------------------------------------


def test_invalid_body_requests_are_rate_limited():
    """A malformed body must still consume the endpoint's rate-limit budget."""
    limit = _SEARCH_LIMIT
    api_mod, _ = _build_app()
    client = TestClient(api_mod.app, raise_server_exceptions=False)

    codes = [
        client.post("/api/v1/search", json={"bogus": 1}).status_code
        for _ in range(limit * 3)
    ]
    assert 429 in codes, (
        "invalid-body requests were NEVER rate limited — the 422 path bypasses "
        f"the limiter entirely (codes={codes[:12]}...)"
    )
    first_429 = codes.index(429) + 1
    assert first_429 <= limit + 1, (
        f"first 429 at request #{first_429}, expected <= {limit + 1}; the "
        "invalid-body path is not charged against the search bucket"
    )


def test_invalid_body_and_valid_body_share_one_budget():
    """Malformed requests must not get a separate, free allowance."""
    limit = _SEARCH_LIMIT
    api_mod, _ = _build_app()
    client = TestClient(api_mod.app, raise_server_exceptions=False)

    # Spend the whole budget on malformed requests...
    for _ in range(limit):
        client.post("/api/v1/search", json={"bogus": 1})
    # ...then a WELL-FORMED request must already be refused.
    assert client.post("/api/v1/search", json={"query": "x"}).status_code == 429, (
        "a valid request still succeeded after the budget was spent on invalid "
        "ones — the two paths are counted separately"
    )


def test_valid_requests_are_not_double_charged():
    """§11.4.201(1): closing the bypass must not over-count legitimate traffic."""
    limit = _SEARCH_LIMIT
    api_mod, _ = _build_app()
    client = TestClient(api_mod.app, raise_server_exceptions=False)

    codes = [
        client.post("/api/v1/search", json={"query": "x"}).status_code
        for _ in range(limit)
    ]
    assert 429 not in codes, (
        f"a valid request was refused INSIDE the allowance (codes={codes}) — the "
        "fix is charging twice per request"
    )
