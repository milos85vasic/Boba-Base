"""BOB-167 — ``GET /theme/stream`` must carry the SAME rate-limit class as
``GET /search/stream/{search_id}``.

Both routes are the SAME expensive resource shape: a long-lived Server-Sent-
Events connection that pins a worker + a generator for the connection's
lifetime. Only ``/search/stream`` carried ``@_rl("sse_stream")``;
``/theme/stream`` fell through to the application's looser ``default`` class
(measured pre-fix: ``default`` = 120/minute vs. ``sse_stream`` = 5/minute) —
even though it holds the identical shape the ``sse_stream`` class exists to
bound.

WHY THIS FILE + LOCATION (§11.4.35). This lives in ``tests/unit/api_layer/``,
matching the existing SSE-route test location convention
(``test_theme_stream.py``, ``test_sse_client_gone.py``,
``test_sse_token_auth.py``). Its env-driven-limits + real-``api.app`` +
module-purge technique mirrors ``tests/security/test_rate_limit_public_
endpoints.py`` (that file's own docstring explains why a synthetic FastAPI
app cannot notice a production route losing its decorator — the same reason
applies here: a unit test against a hand-built app would never have caught
BOB-167).

EVIDENCE CLASS (§11.4.226): RUNTIME-ON-THE-REAL-ASGI-APP. Starlette's
``TestClient``/raw ASGI call drives the real middleware stack, the real
router, and the real ``@_rl(...)`` decorators against the real ``api.app`` —
the same object uvicorn serves.

§11.4.201(1) — both directions asserted: distinct env-driven limits for
``sse_stream`` and ``default`` prove the test is reading the CLASS-SPECIFIC
value, not merely "a header exists" (a header carrying the wrong class's
number would still pass a weaker assertion).

WHY ``/theme/stream`` IS DRIVEN VIA RAW ASGI, NOT ``client.stream(...)``.
``/theme/stream`` has no self-terminating condition other than client
disconnect or a PUT — with nobody PUTting, an ``httpx``-level read only
notices the client-side context-manager exit on the SSE generator's NEXT
poll cycle (a 15s keepalive wait), which pushed one measured run of this
test to ~60s and within a signal of this repo's own ``--timeout=60``
(``pyproject.toml``). Rate-limit headers, however, are injected onto the
``StreamingResponse`` OBJECT the instant the route function returns it
(``slowapi``'s decorator wraps the awaited return value, and constructing
``StreamingResponse(gen(), ...)`` does not execute a single line of ``gen()``
— an async generator runs nothing until first iterated) — so the headers are
already final in the ASGI ``http.response.start`` message, before ANY body
byte is sent. Driving the raw ASGI interface and stopping the instant that
message arrives (the SAME technique this repo's own
``test_theme_stream.py::test_sse_endpoint_serves_initial_event`` already
uses, there to stop after the first body frame; here even earlier, at the
header frame) gets the header value in milliseconds without ever touching
the keepalive path. ``/search/stream/{search_id}`` needs no such care: a
*completed* search's generator drains and closes on its own, so
``client.stream(...)`` (the convention ``tests/unit/api_layer/
test_sse_token_auth.py`` already uses) returns promptly.

§11.4.263: no subprocess/proc object is mocked anywhere in this file.
"""

from __future__ import annotations

import asyncio
import importlib
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SRC_PATH = _REPO_ROOT / "download-proxy" / "src"
if str(_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(_SRC_PATH))

# Deliberately distinct from every other env-driven-limit test file in this
# repo, and deliberately distinct from each other, so a test reading the
# WRONG class's header value is caught rather than accidentally matching.
_SSE_STREAM_LIMIT = 5
_DEFAULT_LIMIT = 37


def _purge_api_modules() -> None:
    """Drop every ``api*`` module so the next import re-executes them.

    ``importlib.reload(api)`` is NOT sufficient (see
    ``tests/security/test_rate_limit_public_endpoints.py`` for the full
    forensic explanation): it does not reload the cached ``api.routes``
    submodule, so production routes stay bound to the PREVIOUS generation's
    Limiter while the middleware consults the new one.
    """
    for name in [m for m in sys.modules if m == "api" or m.startswith("api.")]:
        del sys.modules[name]


@pytest.fixture(autouse=True)
def _isolated_rate_limit_env():
    saved = {k: v for k, v in os.environ.items() if k.startswith("RATE_LIMIT_")}
    yield
    for k in [k for k in os.environ if k.startswith("RATE_LIMIT_")]:
        os.environ.pop(k, None)
    os.environ.update(saved)
    _purge_api_modules()


def _build_app():
    """Import the REAL production app with deterministic, distinct limits."""
    os.environ.pop("RATE_LIMIT_DISABLED", None)
    os.environ["RATE_LIMIT_SSE_STREAM"] = f"{_SSE_STREAM_LIMIT}/minute"
    os.environ["RATE_LIMIT_DEFAULT"] = f"{_DEFAULT_LIMIT}/minute"
    # Leave search/dashboard at their compiled-in defaults — irrelevant here.
    os.environ.pop("RATE_LIMIT_SEARCH", None)
    os.environ.pop("RATE_LIMIT_DASHBOARD", None)

    _purge_api_modules()
    api_mod = importlib.import_module("api")
    rl_mod = importlib.import_module("api.rate_limit")
    rl_mod.reset_counters()
    return api_mod, rl_mod


def _new_completed_search(api_mod):
    """Start (and mark completed) a real search so ``/search/stream/{id}``
    returns a genuine ``StreamingResponse`` instead of a 404.

    A 404 short-circuits BEFORE the route body runs, but it also means the
    ``@_rl(...)`` decorator's wrapped call RAISES ``HTTPException`` rather
    than returning a ``Response`` — slowapi only injects the
    ``x-ratelimit-*`` headers onto a RETURNED ``Response`` object (see
    ``slowapi/extension.py``'s ``async_wrapper``: ``response = await
    func(...)`` then ``self._inject_headers(response, ...)`` — an exception
    from ``func`` skips that injection entirely), so a 404 response never
    carries them. The class assertion below therefore needs a REAL,
    resolvable search id. Marked completed so the generator drains and
    closes on its own rather than idling on a still-running search.
    """
    import merge_service.search as ms

    orch = ms.SearchOrchestrator()
    meta = orch.start_search(query="bob167-probe", category="all", validate_trackers=False)
    meta.status = "completed"
    return orch, meta.search_id


def _binding_limit(header_value: object) -> int | None:
    """Smallest limit named in an ``x-ratelimit-limit`` header value.

    When more than one limit applies to a route (slowapi's middleware
    default-limit pass AND a per-route decorator both fire), the header is
    emitted MORE THAN ONCE and httpx/ASGI join repeats into e.g. ``"5, 5"``
    (or bytes for a raw ASGI header list) — a bare string/bytes compare
    against a single expected integer breaks on the very headers this test
    exists to read. The BINDING ceiling is the smallest of whatever values
    are present. Mirrors the identical technique already established in
    ``tests/scaling/test_scaling_envelope.py::_binding_limit``.
    """
    if header_value is None:
        return None
    if isinstance(header_value, bytes):
        header_value = header_value.decode("latin-1")
    parts = [p.strip() for p in str(header_value).split(",") if p.strip()]
    values = [int(p) for p in parts if p.lstrip("-").isdigit()]
    return min(values) if values else None


async def _theme_stream_response_headers(api_mod) -> dict[bytes, list[bytes]]:
    """Drive ``GET /api/v1/theme/stream`` through the raw ASGI interface and
    return every response header captured at ``http.response.start`` —
    WITHOUT ever reading the (otherwise keepalive-interval-bound) SSE body.
    See the module docstring for why this technique is used instead of
    ``client.stream(...)`` for this specific route.
    """
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/api/v1/theme/stream",
        "raw_path": b"/api/v1/theme/stream",
        "query_string": b"",
        "headers": [(b"host", b"test")],
        "client": ("127.0.0.1", 12345),
        "server": ("test", 80),
        "root_path": "",
    }
    disconnect_event = asyncio.Event()
    started = asyncio.Event()
    response_headers: dict[bytes, list[bytes]] = {}

    async def receive():
        if not disconnect_event.is_set():
            await asyncio.sleep(0.01)
            return {"type": "http.request", "body": b"", "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message):
        if message["type"] == "http.response.start":
            for k, v in message["headers"]:
                response_headers.setdefault(k.lower(), []).append(v)
            started.set()

    task = asyncio.create_task(api_mod.app(scope, receive, send))
    try:
        await asyncio.wait_for(started.wait(), timeout=5.0)
    finally:
        disconnect_event.set()
        try:
            await asyncio.wait_for(task, timeout=2.0)
        except TimeoutError:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

    return response_headers


class TestSSERoutesShareOneRateLimitClass:
    """Criterion (b): both SSE routes advertise the SAME sse_stream class."""

    @pytest.mark.asyncio
    async def test_theme_stream_and_search_stream_report_the_same_sse_class(self, monkeypatch):
        api_mod, _rl_mod = _build_app()
        orch, search_id = _new_completed_search(api_mod)
        monkeypatch.setattr(api_mod, "orchestrator_instance", orch)

        theme_headers = await _theme_stream_response_headers(api_mod)
        raw_theme_values = theme_headers.get(b"x-ratelimit-limit", [])
        assert raw_theme_values, (
            "/theme/stream produced no x-ratelimit-limit header at all — "
            "the limiter is unwired for this route"
        )
        theme_limit = min(v for v in (_binding_limit(x) for x in raw_theme_values) if v is not None)

        client = TestClient(api_mod.app, raise_server_exceptions=False)
        with client.stream("GET", f"/api/v1/search/stream/{search_id}") as search_resp:
            assert search_resp.status_code == 200, (
                f"/search/stream/{{id}} did not admit a below-threshold "
                f"request: {search_resp.status_code}"
            )
            search_limit = _binding_limit(search_resp.headers.get("x-ratelimit-limit"))

        # This is the BOB-167 assertion, pre-fix it FAILS: theme_limit is
        # 37 (the default class) while search_limit is 5 (sse_stream).
        assert theme_limit == _SSE_STREAM_LIMIT, (
            f"/theme/stream advertised binding x-ratelimit-limit={theme_limit!r} "
            f"(raw={raw_theme_values!r}), expected the sse_stream class's "
            f"{_SSE_STREAM_LIMIT!r} — it is carrying no explicit rate-limit "
            f"class and has fallen through to the application default (BOB-167)."
        )
        assert search_limit == _SSE_STREAM_LIMIT, (
            f"/search/stream/{{id}} advertised binding x-ratelimit-limit="
            f"{search_limit!r}, expected the sse_stream class's {_SSE_STREAM_LIMIT!r}"
        )
        assert theme_limit == search_limit, (
            "the two SSE-shaped routes report DIFFERENT rate-limit classes: "
            f"theme_stream={theme_limit!r} search_stream={search_limit!r} — "
            "same resource shape (long-lived connection + generator + "
            "worker) must carry the same class (BOB-167)."
        )

    def test_default_class_control_differs_from_sse_stream(self):
        """§11.4.201(1) control: proves the test reads a CLASS-SPECIFIC
        value, not just "a header exists". If sse_stream and default were
        ever configured to the same number the assertion above would be
        meaningless even when GREEN, so this pins them apart and proves the
        `default` class is genuinely reachable and distinct."""
        api_mod, _rl_mod = _build_app()
        assert _SSE_STREAM_LIMIT != _DEFAULT_LIMIT

        client = TestClient(api_mod.app, raise_server_exceptions=False)
        # A plain GET carries no per-route decorator, so it reports the
        # `default` class — the control most directly comparable to a
        # would-be-broken /theme/stream (which, pre-fix, ALSO reported the
        # default class purely by falling through, not by design).
        root_resp = client.get("/api/v1/healthz")
        default_limit = _binding_limit(root_resp.headers.get("x-ratelimit-limit"))
        assert default_limit == _DEFAULT_LIMIT, (
            f"control endpoint reported binding limit {default_limit!r}, "
            f"expected the default class's {_DEFAULT_LIMIT!r} — env knob not wired"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
