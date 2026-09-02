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

import importlib
import inspect
import os
import sys
import types

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


# Mirrors the production truthiness rule in api/__init__.py:174 verbatim
# (`os.getenv(...).strip().lower() not in ("1", "true", "yes")`). Re-deriving it
# differently here would let the guard and the code under test disagree about
# what "disabled" means.
_DISABLED_VALUES = ("1", "true", "yes")


def _rate_limiting_disabled_by_env() -> bool:
    return os.getenv("RATE_LIMIT_DISABLED", "").strip().lower() in _DISABLED_VALUES


def _api_with_rate_limits_active():
    """Return the `api` module with rate limiting PROVEN active, or skip loudly.

    §11.4.201(6) — CLOSING A FALSE-NULL CHANNEL.

    ``api._rate_limits_active`` is latched ONCE, at the moment ``api`` is first
    imported, from ``RATE_LIMIT_DISABLED`` as it stood THEN. The environment can
    move afterwards; the latch cannot. Reading the latch alone therefore cannot
    distinguish two very different states:

      * rate limiting is legitimately off for this run (an integration harness
        set RATE_LIMIT_DISABLED — a real, documented configuration, used by
        ``tests/ddos/conftest.py``), and
      * rate limiting SHOULD be on, but some earlier test purged ``api`` from
        ``sys.modules`` and re-imported it with the flag set, leaving a stale
        rate-limits-DISABLED module cached for the rest of the session.

    A bare ``pytest.skip`` on the latch reports the SAME quiet zero for both. In
    the second case all three BOB-129 guards would vanish while the summary line
    stayed green — a blind instrument and a clean codebase reading identical.

    That second case is not hypothetical. Two tests in this very tree do exactly
    the purge-and-reimport-with-the-flag-set dance:
    ``tests/unit/api_layer/test_routes_coverage.py`` (via ``_purge_api_module``)
    and ``tests/unit/test_tracker_stats_shape.py``. ``monkeypatch`` restores the
    ENVIRONMENT at teardown, but nothing restores ``sys.modules``. Measured
    2026-09-01: running those files ahead of this one currently leaves
    ``RATE_LIMIT_DISABLED`` unset and ``_rate_limits_active`` True, so the
    channel is open but NOT firing today. It is closed here rather than left to
    an ordering coincidence.

    The resolution is deliberately three-way, not "delete the skip":

      1. Flag set in the CURRENT environment -> the disabled configuration is
         genuine. SKIP, naming the variable and its value so the skip is
         attributable rather than anonymous. Failing here would be the
         §11.4.201(1) false-positive refusal — a guard that refuses a correct
         configuration is as broken as one that passes a defective one.
      2. Flag NOT set but the latch is False -> the latch disagrees with the
         environment, i.e. the stale-module case. REPAIR it: drop the cached
         ``api*`` modules and re-import under the environment that actually
         applies, so the guard RUNS instead of evaporating. The purge is reached
         only in this already-wrong state, so the healthy path is untouched.
      3. Still False after a clean re-import -> something structural is wrong.
         FAIL, because at this point a skip would be an assertion that nothing
         is wrong, and that assertion would be false.
    """
    import api

    if _rate_limiting_disabled_by_env():
        pytest.skip(
            "rate limiting is disabled for this run by RATE_LIMIT_DISABLED="
            f"{os.getenv('RATE_LIMIT_DISABLED')!r}, so the slowapi header-injection "
            "path under guard is not wired. This is a legitimate configuration "
            "(integration harnesses); the guard is inapplicable, not silent."
        )

    if not getattr(api, "_rate_limits_active", False):
        # The env says rate limiting should be ON, so a False latch means the
        # cached module was built under a different environment. Rebuild it.
        for name in [k for k in list(sys.modules) if k == "api" or k.startswith("api.")]:
            del sys.modules[name]
        api = importlib.import_module("api")

    if not getattr(api, "_rate_limits_active", False):
        pytest.fail(
            "RATE_LIMIT_DISABLED is not set, so api._rate_limits_active MUST be True, "
            f"but it is {getattr(api, '_rate_limits_active', 'ABSENT')!r} even after a "
            "clean re-import. The BOB-129 guards cannot observe the slowapi header "
            "path in this state. Reporting a SKIP here would claim 'nothing to check' "
            "when the truth is 'unable to check' (§11.4.201(6)) — so this fails loudly "
            "instead."
        )
    return api


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


def _identity(function) -> tuple[str, str]:  # type: ignore[no-untyped-def]
    """Alias-proof identity of a handler: (real source file, qualname).

    slowapi keys ``__marked_for_limiting`` by the handler's MODULE PATH, so one
    production function re-executed under a second module alias registers under
    a SECOND key. Keying the exemptions on those module paths made this guard
    order-dependent: a test that exec'd ``api/routes.py`` as ``api_routes``
    minted ``api_routes.search_stream``, which missed the
    ``api.routes.search_stream`` allowlist entry and failed the guard on the
    very function that entry had already cleared — a false-positive refusal
    (§11.4.201(1)) with no product defect behind it. The leak itself is fixed at
    source in ``tests/unit/merge_service/test_quality_detection.py``; this
    identity closes the channel so no future alias can reopen it.

    ``(realpath(code file), qualname)`` is invariant under import aliasing while
    remaining fully discriminating: a genuinely NEW endpoint has a different
    qualname (or lives in a different file) and is still caught. ``unwrap``
    steps past slowapi's own ``functools.wraps`` wrapper, whose ``__code__``
    points at ``slowapi/extension.py`` rather than the handler's real source.
    """
    return (
        os.path.realpath(inspect.unwrap(function).__code__.co_filename),
        inspect.unwrap(function).__qualname__,
    )


def _exemption_identities() -> set[tuple[str, str]]:
    """Resolve each dotted exemption name to its alias-proof `_identity`.

    Resolution goes through the CANONICAL module path, so an exemption naming a
    module/attribute that no longer exists raises here rather than silently
    exempting nothing (§11.4.201(6) — a quiet zero is not evidence).
    """
    identities: set[tuple[str, str]] = set()
    for dotted in _RESPONSE_RETURNING_EXEMPTIONS:
        module_name, _, attribute = dotted.rpartition(".")
        module = importlib.import_module(module_name)
        identities.add(_identity(getattr(module, attribute)))
    return identities


class TestGuardCannotSilentlySkip:
    """§1.1 — the skip-suppression logic must itself be falsifiable.

    ``_api_with_rate_limits_active`` exists to convert a silent skip into either
    a real run or a loud failure. A branch that never executes under test is
    decoration, so both of its non-obvious branches are exercised here: the
    repair path (proven by the module-level tests running at all under a
    poisoned cache) and the terminal failure path below.
    """

    def test_unrepairable_latch_fails_rather_than_skipping(self, monkeypatch) -> None:
        """A latch that stays False after a clean re-import MUST fail, not skip.

        Reaching this state legitimately is hard by design — which is exactly
        why it is forced here. If this branch ever regressed to `pytest.skip`,
        the module would go back to reporting a green, empty result while
        unable to observe anything.
        """
        monkeypatch.delenv("RATE_LIMIT_DISABLED", raising=False)

        stub = types.ModuleType("api")
        stub._rate_limits_active = False  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "api", stub)
        # Make even a clean re-import yield the broken module.
        monkeypatch.setattr(importlib, "import_module", lambda name, *a, **k: stub)

        # NOT `pytest.raises(pytest.fail.Exception)`. `pytest.skip` raises
        # `Skipped`, which pytest.raises does not swallow — it propagates and
        # SKIPS this test. A mutation of the guard from `fail` to `skip` would
        # therefore turn this test green-ish (skipped, exit 0) instead of red,
        # reproducing the exact false-null one level up. Measured 2026-09-01:
        # with `pytest.raises`, that mutation yielded "1 skipped" rather than a
        # failure. The outcome is captured explicitly and asserted instead.
        outcome: str
        message = ""
        try:
            _api_with_rate_limits_active()
        except pytest.fail.Exception as exc:  # Failed — the required behaviour
            outcome, message = "fail", str(exc)
        except BaseException as exc:  # noqa: BLE001 — Skipped and anything else
            outcome, message = type(exc).__name__, str(exc)
        else:
            outcome = "returned-normally"

        assert outcome == "fail", (
            "an unrepairable latch MUST raise a test FAILURE. Got "
            f"{outcome!r} instead — a skip or a silent return here would report "
            f"'nothing to check' while the guard is blind. Message: {message!r}"
        )
        assert "MUST be True" in message, message
        assert "unable to check" in message, (
            "the failure must say WHY a skip would have been dishonest, not just that "
            f"something is wrong. Got: {message}"
        )


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
        api = _api_with_rate_limits_active()

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
        api = _api_with_rate_limits_active()

        marked = _marked_for_limiting(api.app.state.limiter)
        assert marked, (
            "slowapi reports ZERO decorated endpoints — either the limiter was not "
            "installed or slowapi renamed its internal registry. Refusing to report a "
            "vacuous PASS over an empty set (§11.4.201(6) false-null)."
        )

        exempt = _exemption_identities()

        offenders: list[str] = []
        for name, functions in marked.items():
            for function in functions:
                # Exempt by alias-proof identity, never by slowapi's module-path
                # key — see `_identity`. A second registration of an ALREADY
                # reviewed function is the same function, not a new endpoint.
                if _identity(function) in exempt:
                    continue
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
        api = _api_with_rate_limits_active()

        marked_identities = {
            _identity(function)
            for functions in _marked_for_limiting(api.app.state.limiter).values()
            for function in functions
        }
        stale = sorted(
            dotted
            for dotted in _RESPONSE_RETURNING_EXEMPTIONS
            if _identity(
                getattr(importlib.import_module(dotted.rpartition(".")[0]), dotted.rpartition(".")[2])
            )
            not in marked_identities
        )
        assert not stale, (
            f"exemption(s) name endpoints slowapi no longer decorates: {stale}. "
            "Remove them so the allowlist cannot exempt an unrelated future endpoint."
        )
