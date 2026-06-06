"""
Tracker-session at-rest encryption (CONTINUATION #7 / Phase 2.3).

The orchestrator's ``_tracker_sessions`` store must Fernet-encrypt session
values at rest so private-tracker cookies never sit as plaintext in the
in-memory cache. Access must stay transparent for the ~14 existing call
sites (set / get / `in` / len / del).

§11.4.43 RED-first: against the pre-fix plain TTLCache the store is not an
EncryptedSessionStore, has no raw accessor, and the secret cookie value IS
present in the backing store — so the assertions below FAIL. After the fix
they GREEN.

§1.1 paired mutation: make EncryptedSessionStore._encrypt return the
plaintext json bytes unchanged → test_secret_not_plaintext_at_rest FAILs.
"""

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


SearchOrchestrator = _import_search_module().SearchOrchestrator

_SECRET = "bb_session_SUPERSECRET_DO_NOT_LEAK_42"
_SESSION = {"cookies": {"bb_session": _SECRET}, "base_url": "https://rutracker.org"}


@pytest.fixture
def orch():
    return SearchOrchestrator()


class TestTransparentAccess:
    def test_set_get_roundtrip(self, orch):
        orch._tracker_sessions["rutracker"] = dict(_SESSION)
        assert orch._tracker_sessions.get("rutracker") == _SESSION
        assert orch._tracker_sessions["rutracker"]["cookies"]["bb_session"] == _SECRET

    def test_membership_and_len_and_del(self, orch):
        orch._tracker_sessions["kinozal"] = {"cookies": {"a": "b"}, "base_url": "x"}
        assert "kinozal" in orch._tracker_sessions
        assert len(orch._tracker_sessions) == 1
        del orch._tracker_sessions["kinozal"]
        assert "kinozal" not in orch._tracker_sessions
        assert len(orch._tracker_sessions) == 0

    def test_get_missing_returns_default(self, orch):
        assert orch._tracker_sessions.get("nope") is None
        assert orch._tracker_sessions.get("nope", "fallback") == "fallback"


class TestAtRestEncryption:
    def test_store_is_encrypted_type(self, orch):
        assert type(orch._tracker_sessions).__name__ == "EncryptedSessionStore"

    def test_secret_not_plaintext_at_rest(self, orch):
        orch._tracker_sessions["rutracker"] = dict(_SESSION)
        # The raw backing values are Fernet tokens — the cleartext secret
        # must not appear anywhere in them.
        raw_blob = repr(orch._tracker_sessions._raw_values())
        assert _SECRET not in raw_blob, "cookie secret found in plaintext at rest"
        assert "bb_session" not in raw_blob

    def test_raw_values_are_fernet_tokens(self, orch):
        orch._tracker_sessions["rutracker"] = dict(_SESSION)
        for token in orch._tracker_sessions._raw_values():
            assert isinstance(token, bytes)
            # Fernet tokens are urlsafe-base64 and start with version byte 0x80 ('gAAAAA').
            assert token.startswith(b"gAAAAA")
