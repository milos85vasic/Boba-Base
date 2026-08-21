"""
BOB-144 — ``GET /api/v1/theme/stream`` must fail closed BY CONSTRUCTION.

The defect this file guards is subtle and easy to mis-test: the endpoint's
OUTCOME was already correct before the fix. A raising ``request.is_disconnected()``
killed the generator, the enclosing ``finally: store.unsubscribe(queue)`` still
ran, and no subscriber leaked. Fail-closed — but reached by an UNCAUGHT
traceback rather than a deliberate refusal.

So a test that only asserts "the stream stopped" or "nothing leaked" PASSES
against the broken code and proves nothing (§11.4/§11.4.1 — a green test on a
defective path is worse than no test). These tests assert the MECHANISM
instead:

* the generator terminates NORMALLY (no exception escapes);
* it emits an explicit ``event: close`` sentinel naming the unresolved
  precondition (``disconnect_probe_failed``) so the client sees a reason
  rather than a truncated stream;
* the probe failure is LOGGED, so a systematically raising probe is
  diagnosable instead of appearing as anonymous recurring tracebacks.

Both directions are proven per §11.4.201(1): a raising probe closes the
stream cleanly AND a normally-connected client keeps streaming uninterrupted
(a guard that refuses healthy traffic is as broken as one that permits
broken traffic).

§11.4.252: a path combining a mutating subscription with an unverifiable
precondition must refuse explicitly, naming what it could not resolve —
never arrive at safety by accident.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SRC_PATH = _REPO_ROOT / "download-proxy" / "src"
if str(_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(_SRC_PATH))


def _purge_api_module() -> None:
    for key in [k for k in list(sys.modules) if k == "api" or k.startswith("api.")]:
        del sys.modules[key]


def _load_api(tmp_path, monkeypatch):
    """Load a pristine ``api`` package bound to a throwaway theme file."""
    monkeypatch.setenv("THEME_STATE_PATH", str(tmp_path / "theme.json"))
    monkeypatch.setenv("RATE_LIMIT_DISABLED", "1")
    _purge_api_module()
    from api import routes
    from api import streaming as st
    from api import theme_state as ts

    ts._store = None  # type: ignore[attr-defined]
    return routes, ts, st


async def _drain(response, limit: int = 8) -> list[bytes]:
    """Collect up to ``limit`` frames from a StreamingResponse body."""
    frames: list[bytes] = []
    async for chunk in response.body_iterator:
        frames.append(chunk)
        if len(frames) >= limit:
            break
    return frames


def _close_frames(frames: list[bytes]) -> list[dict]:
    """Parse every ``event: close`` frame's JSON payload."""
    out: list[dict] = []
    for raw in frames:
        text = raw.decode()
        if "event: close" not in text:
            continue
        for line in text.splitlines():
            if line.startswith("data: "):
                out.append(json.loads(line[len("data: ") :]))
    return out


@pytest.mark.asyncio
async def test_probe_failure_closes_stream_deliberately_not_by_traceback(tmp_path, monkeypatch):
    """A raising probe must produce a NAMED close event, not an escaped exception.

    RED against the pre-fix code twice over: the ``RuntimeError`` escapes
    ``async for`` (so the test errors before reaching any assertion), and no
    ``event: close`` frame is ever emitted.
    """
    routes, ts, _ = _load_api(tmp_path, monkeypatch)

    async def raising_probe() -> bool:
        raise RuntimeError("receive channel gone")

    request = SimpleNamespace(is_disconnected=raising_probe)

    response = await routes.stream_theme(request)
    # No exception may escape: the refusal is a normal generator return.
    frames = await _drain(response)

    closes = _close_frames(frames)
    assert closes, (
        "stream_theme emitted no 'event: close' frame when the disconnect probe "
        f"raised - the client sees a truncated stream with no reason. frames={frames!r}"
    )
    assert closes[0]["reason"] == "disconnect_probe_failed", (
        f"the close event must name the specific unresolved precondition (§11.4.252), got {closes[0]!r}"
    )


@pytest.mark.asyncio
async def test_probe_failure_is_logged_as_a_probe_failure(tmp_path, monkeypatch, caplog):
    """The failure must be diagnosable, not an anonymous recurring traceback."""
    routes, ts, _ = _load_api(tmp_path, monkeypatch)

    async def raising_probe() -> bool:
        raise RuntimeError("receive channel gone")

    request = SimpleNamespace(is_disconnected=raising_probe)

    with caplog.at_level(logging.WARNING):
        response = await routes.stream_theme(request)
        await _drain(response)

    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert warnings, "a failing disconnect probe was not logged at WARNING - undiagnosable"
    joined = " | ".join(r.getMessage() for r in warnings)
    assert "probe failed" in joined.lower(), f"no log record identifies this as a disconnect-probe failure: {joined!r}"
    assert "RuntimeError" in joined, f"the log record drops the underlying cause: {joined!r}"


@pytest.mark.asyncio
async def test_probe_failure_still_releases_the_subscriber(tmp_path, monkeypatch):
    """The SAFE OUTCOME the endpoint already had must be preserved exactly.

    This is the do-not-weaken guard: whatever the mechanism, the subscriber
    queue must still be unsubscribed and the stream must still stop.
    """
    routes, ts, _ = _load_api(tmp_path, monkeypatch)
    store = ts.get_store()
    baseline = store.subscriber_count

    async def raising_probe() -> bool:
        raise RuntimeError("receive channel gone")

    response = await routes.stream_theme(SimpleNamespace(is_disconnected=raising_probe))
    await _drain(response)

    assert store.subscriber_count == baseline, "the subscriber queue leaked - the fail-closed guarantee regressed"


@pytest.mark.asyncio
async def test_confirmed_disconnect_closes_with_client_disconnected_reason(tmp_path, monkeypatch):
    """A real disconnect and an unresolvable probe are DIFFERENT facts.

    Reporting one as the other would be a §11.4.6 misstatement inside the
    event stream, so the two reasons must stay distinct - matching the two
    SSE generators in ``streaming.py``.
    """
    routes, ts, _ = _load_api(tmp_path, monkeypatch)

    async def disconnected_probe() -> bool:
        return True

    response = await routes.stream_theme(SimpleNamespace(is_disconnected=disconnected_probe))
    frames = await _drain(response)

    closes = _close_frames(frames)
    assert closes, f"no close event on a confirmed disconnect. frames={frames!r}"
    assert closes[0]["reason"] == "client_disconnected", (
        f"a confirmed disconnect must not be reported as a probe failure: {closes[0]!r}"
    )


@pytest.mark.asyncio
async def test_connected_client_streams_uninterrupted(tmp_path, monkeypatch):
    """§11.4.201(1) - the other direction: no spurious close for a healthy client.

    A guard that refuses working traffic is a FAIL-bluff, exactly as bad as
    one that permits broken traffic. A never-raising, never-disconnected
    probe must yield real theme events and NO close frame.
    """
    routes, ts, _ = _load_api(tmp_path, monkeypatch)
    store = ts.get_store()

    async def connected_probe() -> bool:
        return False

    response = await routes.stream_theme(SimpleNamespace(is_disconnected=connected_probe))
    it = response.body_iterator

    first = await asyncio.wait_for(it.__anext__(), timeout=2.0)
    assert b"event: theme" in first, f"initial state frame missing: {first!r}"

    # Drive a real PUT so the loop's queue.get() resolves with an update.
    store.put("nord", "light")
    second = await asyncio.wait_for(it.__anext__(), timeout=2.0)

    assert b"event: theme" in second, f"expected a theme update, got {second!r}"
    assert b"nord" in second, f"the update payload did not reach the stream: {second!r}"
    assert not _close_frames([first, second]), (
        "a healthy, connected client was closed spuriously - the guard fails open "
        "in the refusal direction (§11.4.201(1))"
    )

    await it.aclose()
    assert store.subscriber_count == 0, "subscriber not released on generator close"


@pytest.mark.asyncio
async def test_cancellation_still_propagates(tmp_path, monkeypatch):
    """Cancellation is NOT a probe failure and must not be converted into one.

    Swallowing ``CancelledError`` into an ordinary close would break
    structured cancellation, so it must keep propagating.
    """
    routes, ts, _ = _load_api(tmp_path, monkeypatch)
    store = ts.get_store()

    async def cancelled_probe() -> bool:
        raise asyncio.CancelledError()

    response = await routes.stream_theme(SimpleNamespace(is_disconnected=cancelled_probe))

    with pytest.raises(asyncio.CancelledError):
        await _drain(response)

    assert store.subscriber_count == 0, "subscriber leaked on cancellation"
