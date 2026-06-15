"""§11.4.135 regression-guard — BUG-7 all-tracker failure swallowed.

Audit ref: docs/qa/search-flow-audit-20260615/findings.md BUG-7.

When every enabled tracker errors (expired cookies, missing creds,
CAPTCHA, network), the async path still completed with
status="completed", total_results=0 and an EMPTY errors list — making
"all providers errored" indistinguishable from "genuinely empty". The
dashboard then showed a misleading "No results found."

Anti-bluff: the assertion is the user-observable outcome — a distinct
status AND a populated per-tracker error list — so the dashboard can tell
the user to fix auth/CAPTCHA. RED on pre-fix code: status=="completed",
errors carries the per-tracker strings but no all-errored signal exists.
"""

from __future__ import annotations

import importlib.util
import os
import sys

import pytest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_SRC_PATH = os.path.join(_REPO_ROOT, "download-proxy", "src")
_MS_PATH = os.path.join(_SRC_PATH, "merge_service")

if _SRC_PATH not in sys.path:
    sys.path.insert(0, _SRC_PATH)

sys.modules.setdefault("merge_service", type(sys)("merge_service"))
sys.modules["merge_service"].__path__ = [_MS_PATH]


def _import_search_module():
    spec = importlib.util.spec_from_file_location("merge_service.search", os.path.join(_MS_PATH, "search.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["merge_service.search"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def search_mod():
    return _import_search_module()


def _make_orch(search_mod, enabled_names, *, raise_for_all=False):
    TrackerSource = search_mod.TrackerSource
    orch = search_mod.SearchOrchestrator()
    sources = [TrackerSource(name=n, url=f"https://{n}.example", enabled=True) for n in enabled_names]
    orch._get_enabled_trackers = lambda: list(sources)  # type: ignore[method-assign]
    orch._is_tracker_authenticated = lambda name: False  # type: ignore[method-assign]

    async def _fake_search_tracker(tracker, query, category):  # type: ignore[no-untyped-def]
        if raise_for_all:
            raise RuntimeError(f"{tracker.name} auth failed")
        return []

    orch._search_tracker = _fake_search_tracker  # type: ignore[method-assign]
    return orch


@pytest.mark.asyncio
async def test_all_trackers_error_is_distinguishable(search_mod):
    """Every tracker raises -> status is NOT plain 'completed' and the
    per-tracker errors are surfaced so the dashboard can act on them."""
    orch = _make_orch(search_mod, ["rutracker", "rutor", "nyaa"], raise_for_all=True)

    metadata = await orch.search(query="debian")

    assert metadata.total_results == 0
    # The status must distinguish all-errored from genuinely-empty.
    assert metadata.status != "completed", "all-errored search masqueraded as a clean completion"
    # Every tracker's failure must be surfaced.
    assert len(metadata.errors) == 3, f"expected 3 surfaced errors, got {metadata.errors}"


@pytest.mark.asyncio
async def test_genuinely_empty_stays_completed(search_mod):
    """No errors + zero results stays 'completed' (back-compat) — empty is
    NOT an error state."""
    orch = _make_orch(search_mod, ["rutracker", "rutor"], raise_for_all=False)

    metadata = await orch.search(query="zzznoresults")

    assert metadata.total_results == 0
    assert metadata.status == "completed"
    assert metadata.errors == []
