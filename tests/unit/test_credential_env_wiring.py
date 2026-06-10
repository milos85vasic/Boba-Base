"""Anti-bluff: tracker credentials wired from the environment.

The SearchOrchestrator decides which private trackers are enabled and
authenticated purely from environment variables (see search.py
``_get_enabled_trackers`` + ``_is_tracker_authenticated``). These tests
pin the OBSERVABLE wiring: with FAKE credentials present in the env the
orchestrator reports the matching tracker as enabled + authenticated;
with them absent it reports neither.

Each test fails against a no-op stub of the env-reading logic (a stub
that ignores the env would report the wrong enabled/authenticated set).

NOTE: every credential value here is a literal FAKE test token — never a
real secret. The constitution credentials mandate (§11.4.10) is honoured
because nothing read here is real and nothing is printed.

Imports merge_service.search via the spec pattern shared with
tests/unit/merge_service/test_tracker_stats.py so the module loads without
the package being installed.
"""

from __future__ import annotations

import importlib.util
import os
import sys

import pytest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_SRC_PATH = os.path.join(_REPO_ROOT, "download-proxy", "src")
_MS_PATH = os.path.join(_SRC_PATH, "merge_service")

if _SRC_PATH not in sys.path:
    sys.path.insert(0, _SRC_PATH)

# Module roots this file injects/replaces in sys.modules so it can exec
# merge_service/search.py without the package being installed. They MUST be
# snapshotted + restored around every test (NOT clobbered unconditionally at
# import time) — otherwise the FAKE namespace stub leaks into a sibling that
# expects the REAL merge_service package, a latent §11.4.50 pollution that
# the host suite only masks via run order. The autouse fixture below provides
# the teardown; tests request it transitively through ``search_mod``.
_INJECTED_MODULE_KEYS = ("merge_service", "merge_service.search", "merge_service.retry")


def _install_merge_service_namespace_stub() -> None:
    """Install the throw-away ``merge_service`` namespace package used so
    ``merge_service/search.py`` can be exec'd standalone."""
    sys.modules.setdefault("merge_service", type(sys)("merge_service"))
    sys.modules["merge_service"].__path__ = [_MS_PATH]


# FAKE, non-secret test credential values. NEVER real.
_FAKE_USER = "fake-test-user-not-real"
_FAKE_PASS = "fake-test-pass-not-real"  # noqa: S105 — literal test fixture, not a secret

# All private-tracker credential env vars the orchestrator consults; cleared
# at the start of every test so the env is deterministic regardless of the
# host's real .env / shell exports.
_PRIVATE_CRED_VARS = (
    "RUTRACKER_USERNAME",
    "RUTRACKER_PASSWORD",
    "KINOZAL_USERNAME",
    "KINOZAL_PASSWORD",
    "NNMCLUB_COOKIES",
    "IPTORRENTS_USERNAME",
    "IPTORRENTS_PASSWORD",
)


def _import_search_module():
    spec = importlib.util.spec_from_file_location("merge_service.search", os.path.join(_MS_PATH, "search.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["merge_service.search"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def search_mod():
    """Import merge_service.search via the standalone-exec pattern, restoring
    every sys.modules key this file injects on teardown so the FAKE
    ``merge_service`` namespace stub never leaks into a sibling test that
    expects the REAL package (§11.4.50 deterministic-consistency)."""
    saved = {k: sys.modules.get(k) for k in _INJECTED_MODULE_KEYS}
    _install_merge_service_namespace_stub()
    try:
        yield _import_search_module()
    finally:
        for k in _INJECTED_MODULE_KEYS:
            prev = saved[k]
            if prev is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = prev


@pytest.fixture
def clean_cred_env(monkeypatch):
    """Start from a known-empty private-credential environment."""
    for var in _PRIVATE_CRED_VARS:
        monkeypatch.delenv(var, raising=False)
    # Keep the public-tracker fan-out small + deterministic.
    monkeypatch.delenv("ENABLE_DEAD_TRACKERS", raising=False)
    monkeypatch.delenv("JACKETT_API_KEY", raising=False)
    monkeypatch.delenv("JACKETT_INDEXER_MAP", raising=False)
    return monkeypatch


def _enabled_names(orch) -> set[str]:
    return {t.name for t in orch._get_enabled_trackers()}


def test_rutracker_and_iptorrents_enabled_and_authed_when_creds_set(search_mod, clean_cred_env):
    clean_cred_env.setenv("RUTRACKER_USERNAME", _FAKE_USER)
    clean_cred_env.setenv("RUTRACKER_PASSWORD", _FAKE_PASS)
    clean_cred_env.setenv("IPTORRENTS_USERNAME", _FAKE_USER)
    clean_cred_env.setenv("IPTORRENTS_PASSWORD", _FAKE_PASS)

    orch = search_mod.SearchOrchestrator()
    enabled = _enabled_names(orch)

    # Observable: both private trackers appear in the enabled fan-out set.
    assert "rutracker" in enabled
    assert "iptorrents" in enabled
    # Observable: both report authenticated via the chip-state method.
    assert orch._is_tracker_authenticated("rutracker") is True
    assert orch._is_tracker_authenticated("iptorrents") is True


def test_trackers_absent_and_unauthed_when_creds_unset(search_mod, clean_cred_env):
    orch = search_mod.SearchOrchestrator()
    enabled = _enabled_names(orch)

    # Observable: neither private tracker is in the enabled set.
    assert "rutracker" not in enabled
    assert "iptorrents" not in enabled
    # Observable: neither reports authenticated.
    assert orch._is_tracker_authenticated("rutracker") is False
    assert orch._is_tracker_authenticated("iptorrents") is False


def test_partial_creds_do_not_enable_tracker(search_mod, clean_cred_env):
    """A username without its password must NOT enable/auth the tracker —
    proves the wiring checks BOTH halves, not just presence of one var."""
    clean_cred_env.setenv("RUTRACKER_USERNAME", _FAKE_USER)
    # RUTRACKER_PASSWORD deliberately left unset.

    orch = search_mod.SearchOrchestrator()
    assert "rutracker" not in _enabled_names(orch)
    assert orch._is_tracker_authenticated("rutracker") is False


def test_iptorrents_independent_of_rutracker(search_mod, clean_cred_env):
    """Setting only IPTorrents creds enables iptorrents but not rutracker —
    proves per-tracker wiring, not a single global flag."""
    clean_cred_env.setenv("IPTORRENTS_USERNAME", _FAKE_USER)
    clean_cred_env.setenv("IPTORRENTS_PASSWORD", _FAKE_PASS)

    orch = search_mod.SearchOrchestrator()
    enabled = _enabled_names(orch)
    assert "iptorrents" in enabled
    assert "rutracker" not in enabled
    assert orch._is_tracker_authenticated("iptorrents") is True
    assert orch._is_tracker_authenticated("rutracker") is False


def test_start_search_marks_authenticated_in_tracker_stats(search_mod, clean_cred_env):
    """End-observable: the per-tracker stat surfaced to the SSE/UI layer
    carries authenticated=True for a credentialed private tracker and
    False for a public one."""
    clean_cred_env.setenv("RUTRACKER_USERNAME", _FAKE_USER)
    clean_cred_env.setenv("RUTRACKER_PASSWORD", _FAKE_PASS)

    orch = search_mod.SearchOrchestrator()
    metadata = orch.start_search(query="q", category="all")

    assert "rutracker" in metadata.tracker_stats
    assert metadata.tracker_stats["rutracker"].authenticated is True
    # piratebay is a public tracker → always present, never authenticated.
    assert "piratebay" in metadata.tracker_stats
    assert metadata.tracker_stats["piratebay"].authenticated is False
