"""BOB-176 — rutracker enablement gate ignores RUTRACKER_COOKIES.

FORENSIC ANCHOR (BOB-176, verbatim from the tracked item). ``_get_enabled_
trackers()`` gated rutracker on ``RUTRACKER_USERNAME`` and ``RUTRACKER_
PASSWORD`` ONLY — it never consulted ``RUTRACKER_COOKIES``. An operator
configured with cookies alone (no username, no password) therefore NEVER
had rutracker enabled at all: the tracker was silently absent from every
fan-out instead of failing visibly.

This is incoherent with the rest of the codebase: ``_search_rutracker``
itself treats ``RUTRACKER_COOKIES`` as the PREFERRED auth path (checked
BEFORE username/password, see the module comment above that branch), and
the nnmclub sibling function's OWN enablement check already honours
``NNMCLUB_COOKIES`` as independently sufficient
(``os.getenv("NNMCLUB_COOKIES") or (os.getenv("NNMCLUB_USERNAME") and
os.getenv("NNMCLUB_PASSWORD"))``). So the same codebase held three
inconsistent positions at once: cookies preferred at the search site,
cookies ignored at the enablement gate, cookies honoured for a sibling
tracker.

It matters because ``CLAUDE.md`` documents a standing operator mandate
(2026-08-15) that per-tracker Netscape cookies files are auto-loaded into
``.env`` as ``<TRACKER>_COOKIES`` before every service start/restart, and
rutracker is named in that set — so the SANCTIONED, DOCUMENTED
configuration path for this tracker produced exactly the state this gate
ignored.

THE FIX. ``_get_enabled_trackers()`` now enables rutracker when EITHER
``RUTRACKER_COOKIES`` is set OR both ``RUTRACKER_USERNAME`` and
``RUTRACKER_PASSWORD`` are set — mirroring the nnmclub pattern exactly.

NEGATIVE CONTROL (§11.4.201(1), mandatory). A configuration with NO
credentials at all (no username, no password, no cookies) must still leave
rutracker DISABLED. A fix that enables an unauthenticated tracker is WORSE
than the gap it closes — it produces failing searches instead of absent
ones. ``test_credential_less_config_disables_rutracker`` below is that
false-positive guard and is asserted to hold both BEFORE and AFTER the fix
(it is not new behaviour; it is the boundary the fix must not cross).

AUDIT OF SIBLING TRACKERS (acceptance criterion (e)). Read in full
firsthand: ``_search_kinozal`` and ``_search_iptorrents`` never reference
any ``*_COOKIES`` environment variable anywhere in their bodies — both
require a live username/password login round-trip unconditionally, with no
cookie-bypass branch to be asymmetric against. Their enablement gates
(``KINOZAL_USERNAME``/``KINOZAL_PASSWORD``,
``IPTORRENTS_USERNAME``/``IPTORRENTS_PASSWORD``) are therefore already
consistent with their own search-site logic — the asymmetry described by
this item exists ONLY for rutracker (nnmclub's sibling gate already
handled it correctly, and is asserted unaffected here as a control).
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

# Same package-shadowing + restore convention as
# tests/unit/merge_service/test_dead_tracker_bucket.py (see that file's
# header comment for the full root-cause explanation of why a hand-built
# ``merge_service`` shadow package is unavoidable here and why its lifetime
# must be scoped to exactly this file's collection+test run).
_PRE_EXISTING_MERGE_SERVICE = sys.modules.get("merge_service")
_PRE_EXISTING_MERGE_SERVICE_SEARCH = sys.modules.get("merge_service.search")

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
    sys.modules entries once every test in THIS module has run -- see the
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


def _enabled_names(env: dict[str, str]) -> set[str]:
    """Drive the REAL ``_get_enabled_trackers`` under a fully-isolated
    environment (``clear=True`` -- no ambient RUTRACKER_*/NNMCLUB_* leakage
    from the real operator ``.env`` or a sibling test's monkeypatching can
    contaminate the result).
    """
    orch = _search.SearchOrchestrator()
    with patch.dict(os.environ, env, clear=True):
        return {t.name for t in orch._get_enabled_trackers()}


def test_cookies_only_config_enables_rutracker() -> None:
    """Acceptance criterion (a)+(b): RUTRACKER_COOKIES alone, with no
    username/password set at all, must enable rutracker -- matching what
    ``_search_rutracker`` already prefers and what the nnmclub sibling gate
    already does. Drives the REAL ``_get_enabled_trackers`` function, not a
    reimplementation of its logic.
    """
    enabled = _enabled_names({"RUTRACKER_COOKIES": "bb_session=abc123; bb_data=xyz"})
    assert "rutracker" in enabled, (
        "RUTRACKER_COOKIES alone did not enable rutracker -- the enablement "
        "gate is still ignoring cookies even though _search_rutracker "
        "treats them as the preferred auth path and the nnmclub sibling "
        "gate already honours its own cookies variable."
    )


def test_credential_less_config_disables_rutracker() -> None:
    """NEGATIVE CONTROL (§11.4.201(1), mandatory, acceptance criterion
    (d)): a configuration with NO credentials at all -- no username, no
    password, no cookies -- must still leave rutracker DISABLED. This is
    the false-positive guard for the cookies fix: enabling an
    unauthenticated tracker is worse than the gap this item closes, because
    it produces failing searches instead of absent ones. Verified to hold
    both before and after the fix -- it is a boundary, not new behaviour.
    """
    enabled = _enabled_names({})
    assert "rutracker" not in enabled, (
        "rutracker was enabled with ZERO credentials configured (no "
        "username, no password, no cookies) -- an unauthenticated tracker "
        "enabled is worse than the cookies-only gap this item closes, "
        "because it produces failing searches instead of an absent one."
    )


def test_username_password_only_still_enables_rutracker() -> None:
    """Regression guard: the pre-existing username/password path must keep
    working exactly as before -- the fix is additive (cookies as an
    INDEPENDENTLY sufficient credential), never a replacement for the
    existing gate.
    """
    enabled = _enabled_names({"RUTRACKER_USERNAME": "op", "RUTRACKER_PASSWORD": "secret"})
    assert "rutracker" in enabled


def test_partial_credentials_without_cookies_still_disables_rutracker() -> None:
    """Regression guard: a lone username (no password, no cookies) --
    or a lone password -- must still leave rutracker disabled. The fix adds
    exactly one new independently-sufficient path (cookies); it must not
    loosen the existing username+password pairing requirement.
    """
    assert "rutracker" not in _enabled_names({"RUTRACKER_USERNAME": "op"})
    assert "rutracker" not in _enabled_names({"RUTRACKER_PASSWORD": "secret"})


def test_kinozal_and_iptorrents_have_no_cookies_bypass_to_be_asymmetric_against() -> None:
    """AUDIT (acceptance criterion (e)): kinozal and iptorrents were read
    in full firsthand -- neither ``_search_kinozal`` nor
    ``_search_iptorrents`` references any ``*_COOKIES`` environment
    variable anywhere in its body; both require a live username/password
    login round-trip unconditionally. Their enablement gates
    (username+password only) are therefore already consistent with their
    own search-site logic -- there is no cookies-preferred-at-search-but-
    ignored-at-gate asymmetry to fix for either tracker. This test pins
    that reading as an executable fact: a credential-less config leaves
    both disabled (same negative-control shape as rutracker's), and a
    hypothetical ``KINOZAL_COOKIES``/``IPTORRENTS_COOKIES`` value alone
    (no username/password) does NOT enable them, because no such bypass
    exists in the search functions for either.
    """
    enabled = _enabled_names(
        {
            "KINOZAL_COOKIES": "phpbb2mysql_4_sid=fake",
            "IPTORRENTS_COOKIES": "uid=fake",
        }
    )
    assert "kinozal" not in enabled
    assert "iptorrents" not in enabled


def test_nnmclub_sibling_gate_unaffected_and_still_correct() -> None:
    """Control: the already-correct nnmclub sibling gate (cookies OR
    username+password) must be unaffected by this fix -- both its
    cookies-only-enables and its credential-less-disables behaviour are
    unchanged.
    """
    assert "nnmclub" in _enabled_names({"NNMCLUB_COOKIES": "phpbb2mysql_4_sid=abc"})
    assert "nnmclub" not in _enabled_names({})
