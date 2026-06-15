"""§11.4.135 regression-guard — W1 (BUG-7 follow-up): the distinct
``all_trackers_errored`` status + per-tracker ``errors`` MUST reach the
dashboard through the live ``search_complete`` SSE event.

Audit ref: docs/qa/search-flow-audit-20260615/findings.md BUG-7, code-review W1.

BUG-7 made the orchestrator set ``status == "all_trackers_errored"`` when
every searched tracker errored with zero results. But the dashboard's
PRIMARY path is SSE-driven: ``POST /api/v1/search`` returns immediately
and the live grid reacts to the ``search_complete`` event. Pre-fix that
event payload carried only ``total_results``/``merged_results`` — NOT the
status, NOT the errors — so the dashboard could only show the generic
"No results found." and never the actionable
"All trackers failed — check credentials/CAPTCHA" message.

Anti-bluff: the assertions are the user-observable contract — the
``search_complete`` event payload MUST expose the distinct status AND the
populated per-tracker error list, so the dashboard CAN render the
actionable banner. RED on pre-fix code: the dispatched payload has no
``status`` / ``errors`` keys.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import types

import pytest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_SRC_PATH = os.path.join(_REPO_ROOT, "download-proxy", "src")
_MS_PATH = os.path.join(_SRC_PATH, "merge_service")

if _SRC_PATH not in sys.path:
    sys.path.insert(0, _SRC_PATH)

sys.modules.setdefault("merge_service", types.ModuleType("merge_service"))
sys.modules["merge_service"].__path__ = [_MS_PATH]  # type: ignore[attr-defined]


def _import_search_module():
    spec = importlib.util.spec_from_file_location(
        "merge_service.search", os.path.join(_MS_PATH, "search.py")
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["merge_service.search"] = mod
    spec.loader.exec_module(mod)
    return mod


def _make_all_errored_orch(search_mod, names):
    TrackerSource = search_mod.TrackerSource
    orch = search_mod.SearchOrchestrator()
    sources = [TrackerSource(name=n, url=f"https://{n}.example", enabled=True) for n in names]
    orch._get_enabled_trackers = lambda: list(sources)  # type: ignore[method-assign]
    orch._is_tracker_authenticated = lambda name: False  # type: ignore[method-assign]

    async def _fake_search_tracker(tracker, query, category):  # type: ignore[no-untyped-def]
        raise RuntimeError(f"{tracker.name} auth failed")

    orch._search_tracker = _fake_search_tracker  # type: ignore[method-assign]
    return orch


@pytest.mark.asyncio
async def test_search_complete_sse_carries_status_and_errors(monkeypatch):
    """When every tracker errors, the live ``search_complete`` SSE event
    payload MUST include the distinct ``all_trackers_errored`` status and
    the per-tracker errors — the dashboard's only live signal."""
    import api
    from api import routes as routes_mod
    from api.routes import SearchRequest

    search_mod = _import_search_module()
    orch = _make_all_errored_orch(search_mod, ["rutracker", "rutor", "nyaa"])

    # Point the route layer at our all-errored orchestrator.
    monkeypatch.setattr(api, "orchestrator_instance", orch, raising=False)

    # Capture every dispatched SSE/hook event.
    dispatched: list[tuple[str, dict]] = []

    async def _capture(event_type, event_data):  # type: ignore[no-untyped-def]
        dispatched.append((event_type, event_data))

    # dispatch_event is imported lazily inside the route via `from .hooks import dispatch_event`.
    monkeypatch.setattr("api.hooks.dispatch_event", _capture, raising=True)

    # Minimal fake Request whose .app.state has the orchestrator (the route
    # also falls back to module-level orchestrator_instance we set above).
    class _FakeApp:
        class state:  # noqa: N801
            search_orchestrator = orch

    fake_req = types.SimpleNamespace(app=_FakeApp())

    resp = await routes_mod.search(SearchRequest(query="debian"), fake_req)
    assert resp.status == "running"

    # Let the fire-and-forget background task finish (it dispatches search_complete).
    task = orch._search_tasks.get(resp.search_id)
    assert task is not None
    await asyncio.wait_for(task, timeout=10)
    # The background coroutine in the route awaits _run_search then dispatches;
    # give the event loop a tick for the dispatch to land.
    for _ in range(50):
        if any(ev == "search_complete" for ev, _ in dispatched):
            break
        await asyncio.sleep(0.02)

    complete = [data for ev, data in dispatched if ev == "search_complete"]
    assert complete, f"no search_complete event dispatched; saw {[e for e, _ in dispatched]}"
    payload = complete[-1]

    # USER-OBSERVABLE CONTRACT: the dashboard's live path needs both fields.
    assert payload.get("status") == "all_trackers_errored", (
        f"search_complete must carry the distinct status; got {payload.get('status')!r}"
    )
    assert payload.get("errors"), "search_complete must carry the per-tracker errors"
    assert len(payload["errors"]) == 3, f"expected 3 surfaced errors, got {payload['errors']}"
