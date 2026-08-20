"""BOB-139 — the SSE disconnect probe must fail CLOSED, not fail OPEN.

Defect (pre-fix)
----------------
Both SSE generators in ``api/streaming.py`` guarded their ``while True``
loop with::

    try:
        return await request.is_disconnected()
    except Exception:
        return False

The bare ``except Exception: return False`` meant that if the disconnect
probe itself raised, the generator concluded the client was STILL
CONNECTED and streamed forever, holding a socket and a task.  That is
fail-OPEN on the *only* condition that terminates the loop.

Two anchors bind this:

* §11.4.252 fail-closed-on-dangerous-combination — the safe default for
  "I cannot determine whether the client is gone" is to treat it as GONE.
  SSE clients reconnect by design (``EventSource`` retry), so stopping is
  cheap and recoverable; streaming forever is neither.
* §11.4.201(6) false-null — a raising probe and a genuinely-connected
  client both returned the identical ``False``, so the loop could not
  distinguish "the client is here" from "I am blind".

User-visible consequence (why this is not merely untidy):
``api/routes.py`` wraps ``search_results_stream`` in a ``_sse_stream_count``
guard capped at ``_SSE_STREAM_MAX`` (default 32).  A generator that never
returns never runs its ``finally``, so the counter never decrements — once
32 streams have leaked, every subsequent client gets HTTP 429 and the SSE
feature is dead for everyone.

Both polarities are asserted (§11.4.201(1)) — a fix that terminates every
stream would be exactly as broken as the fail-open it replaced:

* raising probe    -> the stream TERMINATES          (the fix)
* connected client -> the stream CONTINUES untouched (the control)

Both generators are covered; they are separate code paths.
"""

from __future__ import annotations

import asyncio
import importlib.util
import logging
import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_SRC_PATH = os.path.join(_REPO_ROOT, "download-proxy", "src")
if _SRC_PATH not in sys.path:
    sys.path.insert(0, _SRC_PATH)

# A loop that fails OPEN never ends.  Rather than hanging on a wall-clock
# timeout (non-deterministic, §11.4.50), every stub counts its own polls
# and raises this sentinel once the budget is spent.  The generators call
# ``get_search_status`` / ``get_progress`` outside any ``try``, so the
# sentinel propagates straight out of the generator and the test fails
# with an actionable message instead of stalling the suite.
_MAX_POLLS = 50


class _StreamDidNotStop(RuntimeError):
    """Raised by a stub when the generator kept polling past its budget."""


@pytest.fixture(autouse=True)
def _restore_api_modules():
    """Restore the real ``api.*`` module graph after every test.

    Same sys.modules isolation rationale as test_sse_disconnect.py /
    test_concurrent_writers.py.
    """
    saved = {k: v for k, v in sys.modules.items() if k == "api" or k.startswith("api.")}
    try:
        yield
    finally:
        for k in [k for k in list(sys.modules) if k == "api" or k.startswith("api.")]:
            del sys.modules[k]
        sys.modules.update(saved)


def _reimport_streaming():
    for k in [k for k in list(sys.modules) if k == "api" or k.startswith("api.")]:
        del sys.modules[k]
    fake_api = type(sys)("api")
    fake_api.__path__ = [os.path.join(_SRC_PATH, "api")]  # type: ignore[attr-defined]
    sys.modules["api"] = fake_api
    spec = importlib.util.spec_from_file_location("api.streaming", os.path.join(_SRC_PATH, "api", "streaming.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["api.streaming"] = mod
    spec.loader.exec_module(mod)
    return mod


def _meta(status: str) -> SimpleNamespace:
    return SimpleNamespace(
        status=status,
        total_results=0,
        merged_results=0,
        trackers_searched=[],
        tracker_stats={},
        to_dict=lambda: {"status": status},
    )


class _BudgetedOrch:
    """Orchestrator stub that stays 'running' for a bounded number of polls.

    ``complete_after`` = None  -> never completes; ONLY a stop-decision can
    end the stream, and overrunning the budget raises ``_StreamDidNotStop``.
    ``complete_after`` = int   -> flips to 'completed' after N polls, so a
    correctly-continuing stream terminates on its own.
    """

    def __init__(self, complete_after: int | None = None) -> None:
        self.polls = 0
        self._complete_after = complete_after

    def get_search_status(self, sid):
        self.polls += 1
        if self.polls > _MAX_POLLS:
            raise _StreamDidNotStop(
                f"search_results_stream kept polling for {self.polls} iterations — it never stopped (fail-OPEN)"
            )
        if self._complete_after is not None and self.polls > self._complete_after:
            return _meta("completed")
        return _meta("running")

    def get_live_results(self, sid):
        return []


def _budgeted_progress(complete_after: int | None = None):
    """get_progress stub mirroring _BudgetedOrch for the download stream."""
    state = {"calls": 0}

    def get_progress(download_id: str):
        state["calls"] += 1
        if state["calls"] > _MAX_POLLS:
            raise _StreamDidNotStop(
                f"download_progress_stream kept polling for {state['calls']} iterations — it never stopped (fail-OPEN)"
            )
        if complete_after is not None and state["calls"] > complete_after:
            return None  # -> download_complete
        return {"complete": False, "percent": 10}

    return get_progress, state


async def _drain(gen) -> list[str]:
    return [evt async for evt in gen]


def _reasons(events: list[str]) -> list[str]:
    """Close reasons present in the stream, matched structurally."""
    return [r for r in ("client_disconnected", "disconnect_probe_failed") if any(r in e for e in events)]


# --------------------------------------------------------------------------
# search_results_stream  (streaming.py ~line 153)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_stream_terminates_when_probe_raises():
    """RED-capturing: a raising probe must STOP the stream, not stream forever."""
    streaming_mod = _reimport_streaming()
    request = SimpleNamespace(is_disconnected=AsyncMock(side_effect=RuntimeError("receive channel gone")))
    orch = _BudgetedOrch()  # never completes on its own

    gen = streaming_mod.SSEHandler.search_results_stream("sid-raise", orch, poll_interval=0.001, request=request)
    events = await _drain(gen)

    assert any("event: close" in e for e in events), (
        f"expected an 'event: close' sentinel when the probe raises, got: {events!r}"
    )
    # Honest reason: we do NOT know the client disconnected, only that we
    # cannot see.  Claiming 'client_disconnected' here would be a §11.4.6
    # misstatement inside the event stream itself.
    assert "disconnect_probe_failed" in "".join(events), (
        f"expected the distinct 'disconnect_probe_failed' close reason, got: {events!r}"
    )
    assert "client_disconnected" not in "".join(events), (
        "a probe failure must not be reported as a confirmed client disconnect"
    )
    # Fail closed on the FIRST unresolvable probe — no unbounded retry.
    assert orch.polls == 0, f"stream should stop before polling the orchestrator, polled {orch.polls}x"


@pytest.mark.asyncio
async def test_search_stream_continues_while_client_connected():
    """CONTROL (§11.4.201(1)): a healthy client's stream must NOT be terminated."""
    streaming_mod = _reimport_streaming()
    request = SimpleNamespace(is_disconnected=AsyncMock(return_value=False))
    orch = _BudgetedOrch(complete_after=5)

    gen = streaming_mod.SSEHandler.search_results_stream("sid-live", orch, poll_interval=0.001, request=request)
    events = await _drain(gen)

    joined = "".join(events)
    assert "event: close" not in joined, f"a connected client's stream was terminated: {events!r}"
    assert "event: search_complete" in joined, f"stream did not run to completion: {events!r}"
    assert orch.polls >= 5, f"stream stopped early after {orch.polls} polls"
    assert request.is_disconnected.await_count >= 5


@pytest.mark.asyncio
async def test_search_stream_genuine_disconnect_keeps_its_own_reason():
    """CONTROL: a real disconnect still reports 'client_disconnected', not the probe reason."""
    streaming_mod = _reimport_streaming()
    request = SimpleNamespace(is_disconnected=AsyncMock(return_value=True))

    gen = streaming_mod.SSEHandler.search_results_stream(
        "sid-gone", _BudgetedOrch(), poll_interval=0.001, request=request
    )
    events = await _drain(gen)

    assert _reasons(events) == ["client_disconnected"], f"unexpected close reasons: {events!r}"


@pytest.mark.asyncio
async def test_search_stream_propagates_cancellation():
    """asyncio.CancelledError is task teardown, NOT a probe failure — it must propagate.

    Swallowing it (or converting it into a normal 'close' event) would break
    structured cancellation, which is a different defect from the one fixed here.
    """
    streaming_mod = _reimport_streaming()
    request = SimpleNamespace(is_disconnected=AsyncMock(side_effect=asyncio.CancelledError()))

    gen = streaming_mod.SSEHandler.search_results_stream(
        "sid-cancel", _BudgetedOrch(), poll_interval=0.001, request=request
    )
    with pytest.raises(asyncio.CancelledError):
        await _drain(gen)


@pytest.mark.asyncio
async def test_search_stream_without_request_is_not_failed_closed():
    """CONTROL: request=None means 'no probe was asked for', not 'indeterminate'.

    Fail-closed must NOT leak into the request-less path or every caller that
    omits the kwarg would have its stream killed on the first iteration.
    """
    streaming_mod = _reimport_streaming()
    orch = _BudgetedOrch(complete_after=3)

    gen = streaming_mod.SSEHandler.search_results_stream("sid-noreq", orch, poll_interval=0.001)
    events = await _drain(gen)

    assert "event: close" not in "".join(events), f"request-less stream was killed: {events!r}"
    assert any("event: search_complete" in e for e in events)


@pytest.mark.asyncio
async def test_search_stream_logs_probe_failure(caplog):
    """A silent fail-closed is better than fail-open but still hides a real fault."""
    streaming_mod = _reimport_streaming()
    request = SimpleNamespace(is_disconnected=AsyncMock(side_effect=RuntimeError("receive channel gone")))

    with caplog.at_level(logging.WARNING, logger="api.streaming"):
        gen = streaming_mod.SSEHandler.search_results_stream(
            "sid-log", _BudgetedOrch(), poll_interval=0.001, request=request
        )
        await _drain(gen)

    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert warnings, "a failing disconnect probe must be logged, not silently swallowed"
    blob = " ".join(r.getMessage() for r in warnings)
    assert "sid-log" in blob, f"log must identify the stream, got: {blob!r}"
    assert "receive channel gone" in blob, f"log must carry the underlying error, got: {blob!r}"


# --------------------------------------------------------------------------
# download_progress_stream  (streaming.py ~line 351)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_download_stream_terminates_when_probe_raises():
    """RED-capturing: separate code path, same fail-open defect."""
    streaming_mod = _reimport_streaming()
    request = SimpleNamespace(is_disconnected=AsyncMock(side_effect=RuntimeError("receive channel gone")))
    get_progress, state = _budgeted_progress()  # never completes on its own

    gen = streaming_mod.SSEHandler.download_progress_stream(
        "dl-raise", get_progress, poll_interval=0.001, request=request
    )
    events = await _drain(gen)

    joined = "".join(events)
    assert "event: close" in joined, f"expected an 'event: close' sentinel, got: {events!r}"
    assert "disconnect_probe_failed" in joined, f"expected the distinct probe-failure reason, got: {events!r}"
    assert "client_disconnected" not in joined
    assert state["calls"] == 0, f"stream should stop before polling progress, polled {state['calls']}x"


@pytest.mark.asyncio
async def test_download_stream_continues_while_client_connected():
    """CONTROL (§11.4.201(1)): a healthy download stream must NOT be terminated."""
    streaming_mod = _reimport_streaming()
    request = SimpleNamespace(is_disconnected=AsyncMock(return_value=False))
    get_progress, state = _budgeted_progress(complete_after=5)

    gen = streaming_mod.SSEHandler.download_progress_stream(
        "dl-live", get_progress, poll_interval=0.001, request=request
    )
    events = await _drain(gen)

    joined = "".join(events)
    assert "event: close" not in joined, f"a connected client's stream was terminated: {events!r}"
    assert "event: download_complete" in joined, f"stream did not run to completion: {events!r}"
    assert state["calls"] >= 5, f"stream stopped early after {state['calls']} polls"


@pytest.mark.asyncio
async def test_download_stream_genuine_disconnect_keeps_its_own_reason():
    """CONTROL: a real disconnect still reports 'client_disconnected'."""
    streaming_mod = _reimport_streaming()
    request = SimpleNamespace(is_disconnected=AsyncMock(return_value=True))
    get_progress, _ = _budgeted_progress()

    gen = streaming_mod.SSEHandler.download_progress_stream(
        "dl-gone", get_progress, poll_interval=0.001, request=request
    )
    events = await _drain(gen)

    assert _reasons(events) == ["client_disconnected"], f"unexpected close reasons: {events!r}"


@pytest.mark.asyncio
async def test_download_stream_propagates_cancellation():
    """CancelledError must propagate out of the download generator too."""
    streaming_mod = _reimport_streaming()
    request = SimpleNamespace(is_disconnected=AsyncMock(side_effect=asyncio.CancelledError()))
    get_progress, _ = _budgeted_progress()

    gen = streaming_mod.SSEHandler.download_progress_stream(
        "dl-cancel", get_progress, poll_interval=0.001, request=request
    )
    with pytest.raises(asyncio.CancelledError):
        await _drain(gen)


@pytest.mark.asyncio
async def test_download_stream_without_request_is_not_failed_closed():
    """CONTROL: request=None must not be treated as indeterminate."""
    streaming_mod = _reimport_streaming()
    get_progress, _ = _budgeted_progress(complete_after=3)

    gen = streaming_mod.SSEHandler.download_progress_stream("dl-noreq", get_progress, poll_interval=0.001)
    events = await _drain(gen)

    assert "event: close" not in "".join(events), f"request-less stream was killed: {events!r}"
    assert any("event: download_complete" in e for e in events)


@pytest.mark.asyncio
async def test_download_stream_logs_probe_failure(caplog):
    """The download path must surface the fault too."""
    streaming_mod = _reimport_streaming()
    request = SimpleNamespace(is_disconnected=AsyncMock(side_effect=RuntimeError("receive channel gone")))
    get_progress, _ = _budgeted_progress()

    with caplog.at_level(logging.WARNING, logger="api.streaming"):
        gen = streaming_mod.SSEHandler.download_progress_stream(
            "dl-log", get_progress, poll_interval=0.001, request=request
        )
        await _drain(gen)

    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert warnings, "a failing disconnect probe must be logged, not silently swallowed"
    blob = " ".join(r.getMessage() for r in warnings)
    assert "dl-log" in blob, f"log must identify the stream, got: {blob!r}"
