"""Guards the dead-tracker exclusion so the dashboard doesn't drown
in permanently-red chips.

Every entry in ``DEAD_PUBLIC_TRACKERS`` has been observed returning
consistent failures in the diagnostic pass run on 2026-04-23 (403/404,
DNS failures, TLS handshake breaks, or plugin-level crashes on stale
regex). They remain in ``PUBLIC_TRACKERS`` so the classifier still
reports the real reason — but ``_get_enabled_trackers`` filters them
out of the fan-out unless ``ENABLE_DEAD_TRACKERS=1``.

These tests:

1. Assert every name in ``DEAD_PUBLIC_TRACKERS`` is also a key in
   ``PUBLIC_TRACKERS`` (no typos or orphaned entries).
2. Assert ``_get_enabled_trackers()`` omits the dead set by default.
3. Assert ``ENABLE_DEAD_TRACKERS=1`` forces them back in.
4. Assert healthy public trackers (piratebay, linuxtracker, rutor,
   torrentscsv) always make it into the fan-out so a future careless
   `DEAD_PUBLIC_TRACKERS` edit can't silently black-hole them.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO = Path(__file__).resolve().parents[3]
_MS_PATH = REPO / "download-proxy" / "src" / "merge_service"

# Root-caused 2026-09-22 (systematic-debugging, discovered while verifying a
# DEAD_PUBLIC_TRACKERS edit). Two compounding facts make this file's loading
# genuinely different from its siblings (test_merge_trackers.py,
# test_public_tracker_subprocess.py), which just do a plain
# ``sys.path.insert`` + ``from merge_service.search import ...``:
#
# 1. search.py uses PACKAGE-RELATIVE imports (``from .quality import ...``,
#    ``from .retry import ...``, ``from .trackers import ...``) -- it MUST be
#    loaded as a real submodule of a package literally named ``merge_service``
#    with the correct ``__path__``, not as a bare file. A plain
#    ``sys.path.insert`` + ``from merge_service import search`` cannot skip
#    this requirement.
# 2. This test file itself lives at ``tests/unit/merge_service/`` -- a real
#    Python package (``tests/unit/merge_service/__init__.py`` exists) whose
#    PARENTS (``tests/``, ``tests/unit/``) do NOT have ``__init__.py``. Pytest
#    therefore inserts ``tests/unit/`` onto sys.path and registers THIS
#    package under the bare top-level name ``merge_service`` -- directly
#    colliding with the production package of the same name. By the time this
#    file's top-level code runs, ``sys.modules["merge_service"]`` is ALREADY
#    bound to ``tests/unit/merge_service/__init__.py``, not the real package
#    (confirmed live: ``from merge_service import search`` raised
#    ``ImportError: cannot import name 'search' from 'merge_service'
#    (.../tests/unit/merge_service/__init__.py)``).
#
# So a hand-built shadow package under the ``merge_service`` name is
# genuinely UNAVOIDABLE here (fact 1) — the bug was never doing that, it was
# doing it WITHOUT restoring the pre-existing ``sys.modules["merge_service"]``
# / ``["merge_service.search"]`` entries afterward. Because the injection
# happens at COLLECTION time (module top level, before any test runs),
# tests/conftest.py's own ``_POLLUTING_ROOTS`` snapshot/restore fixture
# explicitly cannot help (its comment documents that a name already present
# at collection time becomes the fixture's own restore baseline and is never
# purged). Left unrestored, this file's shadow ``merge_service.search``
# permanently replaced the real package for the rest of the pytest process
# once this file was collected, which broke
# tests/unit/test_merge_trackers.py's routing tests (``from config import
# load_env`` inside ``search.py`` resolved against the shadow module's
# different loading context and failed) whenever this file ran first in the
# same session — reproduced BOTH before and after the DEAD_PUBLIC_TRACKERS
# edit that surfaced it, so it was always latent, not introduced by that
# edit. Fixed by explicitly saving the pre-injection ``sys.modules`` state
# and restoring it via a module-scoped autouse fixture that runs after this
# file's own tests finish, so the shadow package's lifetime is scoped to
# exactly this file's collection+test run and never leaks to siblings
# collected afterward in the same session.
_PRE_EXISTING_MERGE_SERVICE = sys.modules.get("merge_service")
_PRE_EXISTING_MERGE_SERVICE_SEARCH = sys.modules.get("merge_service.search")

# search.py's ``_load_env()`` does a LAZY, function-scoped ``from config
# import load_env`` (called only when a tracker search actually runs, not at
# module-load time) — an ABSOLUTE import of the real ``download-proxy/src/
# config`` package, unrelated to the merge_service shadow-package problem
# above. It needs ``download-proxy/src`` on sys.path at CALL time, which may
# be much later than collection time (e.g. triggered by a DIFFERENT test
# file's mocked-search-orchestration test, under pytest-randomly's
# interleaved execution order, while this module's shadow ``search.py`` is
# still the cached ``merge_service.search``). sys.path mutation, unlike
# sys.modules replacement, is the accepted permanent-for-the-process pattern
# this whole suite already uses (test_merge_trackers.py,
# test_public_tracker_subprocess.py do the identical insert) — no restore
# needed here, only the sys.modules shadowing above requires one.
_SRC = str(REPO / "download-proxy" / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

sys.modules["merge_service"] = type(sys)("merge_service")
sys.modules["merge_service"].__path__ = [str(_MS_PATH)]  # type: ignore[attr-defined]
_spec = importlib.util.spec_from_file_location("merge_service.search", str(_MS_PATH / "search.py"))
_search = importlib.util.module_from_spec(_spec)
sys.modules["merge_service.search"] = _search
_spec.loader.exec_module(_search)  # type: ignore[union-attr]


@pytest.fixture(scope="module", autouse=True)
def _restore_merge_service_module_identity():
    """Undo this file's shadow ``merge_service``/``merge_service.search``
    sys.modules entries once every test in THIS module has run, so a
    sibling test file collected afterward in the same pytest session sees
    the real package again (or the real absence of one) -- see the
    root-cause comment above ``_PRE_EXISTING_MERGE_SERVICE``.
    """
    yield
    if _PRE_EXISTING_MERGE_SERVICE is None:
        sys.modules.pop("merge_service", None)
    else:
        sys.modules["merge_service"] = _PRE_EXISTING_MERGE_SERVICE
    if _PRE_EXISTING_MERGE_SERVICE_SEARCH is None:
        sys.modules.pop("merge_service.search", None)
    else:
        sys.modules["merge_service.search"] = _PRE_EXISTING_MERGE_SERVICE_SEARCH


def test_dead_set_is_subset_of_public_registry() -> None:
    stray = set(_search.DEAD_PUBLIC_TRACKERS) - set(_search.PUBLIC_TRACKERS)
    assert not stray, (
        f"DEAD_PUBLIC_TRACKERS contains names not in PUBLIC_TRACKERS: {sorted(stray)}. "
        "Typos or orphaned entries defeat the filter — every dead name must "
        "round-trip through the public registry."
    )


def test_default_fan_out_excludes_dead_trackers() -> None:
    orch = _search.SearchOrchestrator()
    with patch.dict(os.environ, {"ENABLE_DEAD_TRACKERS": "0"}, clear=True):
        enabled = {t.name for t in orch._get_enabled_trackers()}
    leaked = enabled & set(_search.DEAD_PUBLIC_TRACKERS)
    assert not leaked, (
        f"Dead trackers leaked into the default fan-out: {sorted(leaked)}. "
        "Dashboard will show permanently-red chips for these."
    )


def test_env_flag_forces_dead_trackers_back_in() -> None:
    orch = _search.SearchOrchestrator()
    with patch.dict(os.environ, {"ENABLE_DEAD_TRACKERS": "1"}, clear=False):
        enabled = {t.name for t in orch._get_enabled_trackers()}
    missing = set(_search.DEAD_PUBLIC_TRACKERS) - enabled
    assert not missing, (
        f"ENABLE_DEAD_TRACKERS=1 should include dead trackers but these were still missing: {sorted(missing)}"
    )


@pytest.mark.parametrize(
    "canary",
    [
        "piratebay",
        "linuxtracker",
        "rutor",
        "torrentscsv",
        "academictorrents",
        "yts",
        "yourbittorrent",
        # "glotorrents" REMOVED 2026-09-22 (systematic-debugging root-cause
        # investigation): re-verified live, from inside the production
        # container, using the real urllib code path — glodls.to now serves
        # a domain-parking page (plain HTTP/80 returns a "lander.parity.
        # domains" parking template with a 200; HTTPS/443 raises `SSL:
        # UNEXPECTED_EOF_WHILE_READING`, the exact error captured in the
        # original fan-out failure). This is a §11.4.7-class demotion:
        # positive same-conditions evidence that the canary's premise (this
        # is a known-good tracker) has expired, not a defect in this test or
        # in the DEAD_PUBLIC_TRACKERS edit that surfaced it. It is correctly
        # a member of DEAD_PUBLIC_TRACKERS now — see the taxonomy comment
        # above that frozenset in search.py for the full captured evidence.
    ],
)
def test_canary_trackers_stay_in_default_fan_out(canary: str) -> None:
    """Canaries are trackers known to return results for common queries
    like ``linux``. They must never accidentally end up in the dead set."""
    assert canary in _search.PUBLIC_TRACKERS, (
        f"{canary!r} disappeared from PUBLIC_TRACKERS — that's a much "
        "bigger problem than this test but we want to catch it here too."
    )
    assert canary not in _search.DEAD_PUBLIC_TRACKERS, (
        f"{canary!r} was added to DEAD_PUBLIC_TRACKERS. It is a known-good "
        "tracker; adding it there will silently black-hole its results."
    )


def test_dead_list_reflects_documented_categories() -> None:
    """Keep docs/MERGE_SEARCH_DIAGNOSTICS.md in sync with code.

    The diagnostics doc publishes the known-dead list; when we drop
    entries in or out, the doc should reflect it. This test reads the
    doc and asserts every DEAD_PUBLIC_TRACKERS name is mentioned.
    """
    doc = (REPO / "docs" / "MERGE_SEARCH_DIAGNOSTICS.md").read_text(encoding="utf-8")
    missing = [name for name in _search.DEAD_PUBLIC_TRACKERS if name not in doc]
    assert not missing, (
        f"DEAD_PUBLIC_TRACKERS entries not documented in "
        f"docs/MERGE_SEARCH_DIAGNOSTICS.md: {sorted(missing)}. "
        "Add them to the 'The known-dead list' section."
    )
