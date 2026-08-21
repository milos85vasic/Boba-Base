"""BOB-129 — permanent regression guard for the slowapi rate-limit header contract.

WHAT THIS GUARDS
----------------
slowapi's ``Limiter.limit()`` decorator injects the ``X-RateLimit-*`` headers
into the decorated endpoint's OWN return value, but only when that value is a
``starlette.responses.Response``. When it is not (a plain dict / a Pydantic
model that FastAPI serializes LATER, above the slowapi wrapper), slowapi falls
back to ``kwargs.get("response")`` and hands the result to
``Limiter._inject_headers``, which raises::

    Exception: parameter `response` must be an instance of
    starlette.responses.Response

on EVERY request, because without a declared ``response: Response`` parameter
that lookup returns ``None``. slowapi's own documentation states the contract:
"if the returned response is not an instance of `Response` and will be built at
an upper level in the middleware stack, you'll need to provide the response
object explicitly if you want the `Limiter` to modify the headers
(`headers_enabled=True`)" — https://github.com/laurentS/slowapi/blob/master/docs/index.md
(verified 2026-08-21). ``api.rate_limit._build_limiter()`` sets
``headers_enabled=True``, so this project is squarely inside that contract.

This is an API-USAGE contract, NOT a slowapi/starlette version incompatibility:
the mechanism reproduces identically on starlette 1.4.1 (host venv) and
starlette 1.6.0 (the qbittorrent-proxy container), both on slowapi 0.1.10.

WHY A DEDICATED GUARD (§11.4.135 / §11.4.238)
---------------------------------------------
The production fix landed in 44f3bbe, but nothing failed when it was absent:
the only pre-existing "BOB-129" references were COMMENTS in
``test_api_init_coverage.py``, whose tests bypass the decorator entirely via
``__wrapped__`` and therefore never execute slowapi's ``async_wrapper``. A fixed
defect with no falsifiable guard is the silent-recurrence vector §11.4.135
forbids, so the regression is guarded here at the RUNTIME layer (§11.4.226 —
the evidence class must match the defect layer; a signature grep cannot observe
a request blowing up in the middleware stack).

The guarded branch is LATENT in the deployed stack today: ``_serve_index_html()``
returns a ``FileResponse`` whenever the Angular dist is present, which takes
slowapi's safe branch. It returns a plain ``dict`` when the dist is missing —
and THAT is the branch that raises. These tests drive that exact branch.
"""

from __future__ import annotations

import inspect
import os
import sys

import pytest
from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient
from slowapi import Limiter
from starlette.responses import Response as StarletteResponse
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "download-proxy", "src"))

# The exact upstream message; asserted verbatim so a slowapi upgrade that
# changes the contract surfaces here instead of silently disarming the guard.
_SLOWAPI_CONTRACT_ERROR = "parameter `response` must be an instance of starlette.responses.Response"

# Endpoints allowed to carry `@limiter.limit()` WITHOUT a `response: Response`
# parameter, because every one of their success paths returns a
# `starlette.responses.Response` subclass (slowapi then takes its safe branch).
# Each entry is a reviewed exemption, not a blanket opt-out — adding a name here
# requires proving the endpoint cannot return a non-Response.
_RESPONSE_RETURNING_EXEMPTIONS = {
    # Single `return` is `SSEHandler.create_streaming_response(...)`
    # (a StreamingResponse); every other exit raises HTTPException, which
    # propagates before slowapi's header injection runs.
    "api.routes.search_stream",
}


@pytest.fixture(autouse=True)
def _quiescent_limiter():
    """§11.4.14 — leave the shared per-IP counters clean on every exit path."""
    from api.rate_limit import get_limiter, reset_counters

    if get_limiter() is not None:
        reset_counters()
    yield
    if get_limiter() is not None:
        reset_counters()


def _marked_for_limiting(limiter: Limiter) -> dict:
    """Return slowapi's private map of endpoints carrying a `.limit()` decorator."""
    return getattr(limiter, "_Limiter__marked_for_limiting", {})


class TestControlNeedle:
    """§11.4.201(7)(b) — prove the instrument can still SEE the defect.

    Without this, a GREEN from the guards below is unfalsifiable: if a future
    slowapi release stopped raising, those guards would pass for a reason that
    has nothing to do with this project's code, and the guard would be a blind
    instrument reporting a quiet zero.
    """

    def test_undeclared_response_param_still_raises_on_installed_slowapi(self) -> None:
        app = FastAPI()
        limiter = Limiter(key_func=lambda *a, **k: "203.0.113.7", headers_enabled=True)
        app.state.limiter = limiter

        @app.get("/needle")
        @limiter.limit("50/minute")
        async def needle(request: Request):  # type: ignore[no-untyped-def]
            return {"shape": "dict-fallback"}  # NOT a Response

        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/needle")

        assert response.status_code == 500, (
            "control needle did not fire: the installed slowapi no longer raises on a "
            "decorated endpoint returning a non-Response without `response: Response`. "
            "The guards in this module are therefore no longer proving anything — "
            "re-derive the contract against the installed version before trusting them."
        )

    def test_declared_response_param_satisfies_the_contract(self) -> None:
        """The positive half: declaring `response: Response` yields 200 + headers."""
        app = FastAPI()
        limiter = Limiter(key_func=lambda *a, **k: "203.0.113.8", headers_enabled=True)
        app.state.limiter = limiter

        @app.get("/needle")
        @limiter.limit("50/minute")
        async def needle(request: Request, response: Response):  # type: ignore[no-untyped-def]
            return {"shape": "dict-fallback"}

        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/needle")

        assert response.status_code == 200
        assert response.headers.get("x-ratelimit-limit") == "50"


class TestProductionDashboardDictFallback:
    """RUNTIME guard on the REAL app, driving the latent dict-fallback branch.

    ``_serve_index_html()`` is patched to return its no-Angular-dist ``dict``
    so the request takes slowapi's ``kwargs.get("response")`` path — the exact
    branch that raised before 44f3bbe.
    """

    @pytest.mark.parametrize("path", ["/", "/dashboard"])
    def test_dict_fallback_serves_200_with_rate_limit_headers(self, path: str) -> None:
        import api

        if not getattr(api, "_rate_limits_active", False):
            pytest.skip("rate limiting disabled at import time (RATE_LIMIT_DISABLED)")

        with patch("api._serve_index_html") as serve:
            serve.return_value = {"message": "Merge Search API", "dashboard": "not found"}
            with TestClient(api.app, raise_server_exceptions=False) as client:
                response = client.get(path)

        assert response.status_code == 200, (
            f"GET {path} returned {response.status_code} on the dict-fallback branch. "
            f"If the body carries {_SLOWAPI_CONTRACT_ERROR!r}, the handler lost its "
            f"`response: Response` parameter — restore it (BOB-129). Body: {response.text[:300]}"
        )
        assert response.headers.get("x-ratelimit-limit") is not None, (
            f"GET {path} produced no X-RateLimit-Limit header; slowapi's header "
            "injection did not run, so the rate-limit contract is not being honoured."
        )


class TestDecoratedEndpointContract:
    """Drift detector — catches the precondition ARRIVING LATER.

    A future endpoint that gains `@_rl(...)`/`@limiter.limit()` while returning a
    dict or a Pydantic model re-introduces BOB-129. This fails the moment such an
    endpoint is added without either a `response: Response` parameter or a
    reviewed exemption proving it always returns a Response.
    """

    def test_every_decorated_endpoint_declares_response_or_is_exempt(self) -> None:
        import api

        if not getattr(api, "_rate_limits_active", False):
            pytest.skip("rate limiting disabled at import time (RATE_LIMIT_DISABLED)")

        marked = _marked_for_limiting(api.app.state.limiter)
        assert marked, (
            "slowapi reports ZERO decorated endpoints — either the limiter was not "
            "installed or slowapi renamed its internal registry. Refusing to report a "
            "vacuous PASS over an empty set (§11.4.201(6) false-null)."
        )

        offenders: list[str] = []
        for name, functions in marked.items():
            if name in _RESPONSE_RETURNING_EXEMPTIONS:
                continue
            for function in functions:
                parameters = inspect.signature(function).parameters
                declares_response = any(
                    parameter.annotation is Response or parameter.annotation is StarletteResponse
                    for parameter in parameters.values()
                )
                if not declares_response:
                    offenders.append(f"{name} (params: {list(parameters)})")

        assert not offenders, (
            "slowapi-decorated endpoint(s) declare no `response: Response` parameter and "
            "are not a reviewed always-returns-Response exemption. With "
            "`headers_enabled=True` these raise "
            f"{_SLOWAPI_CONTRACT_ERROR!r} on every request whose handler returns a "
            f"non-Response (BOB-129): {offenders}"
        )

    def test_exemptions_are_still_decorated(self) -> None:
        """An exemption naming an endpoint that no longer exists is stale.

        Prevents the allowlist from silently accumulating dead entries that would
        exempt a future endpoint reusing the name.
        """
        import api

        if not getattr(api, "_rate_limits_active", False):
            pytest.skip("rate limiting disabled at import time (RATE_LIMIT_DISABLED)")

        marked = set(_marked_for_limiting(api.app.state.limiter))
        stale = _RESPONSE_RETURNING_EXEMPTIONS - marked
        assert not stale, (
            f"exemption(s) name endpoints slowapi no longer decorates: {sorted(stale)}. "
            "Remove them so the allowlist cannot exempt an unrelated future endpoint."
        )
