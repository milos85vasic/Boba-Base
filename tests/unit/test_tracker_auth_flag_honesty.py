"""BOB-173 — the per-tracker ``authenticated`` flag must mean AUTHENTICATED.

Forensic anchor (captured live 2026-09-02 against the running merge service
on :7187, ``POST /api/v1/search`` then ``GET /api/v1/search/{id}``)::

    nnmclub    status=error  authenticated=True  results=0  error_type=upstream_captcha
        error: nnmclub login.php is gated by a Cloudflare Turnstile JS CAPTCHA;
               a password POST cannot obtain a session cookie. ...
    rutracker  status=error  authenticated=True  results=0  error_type=upstream_captcha
        error: rutracker login.php returned no session cookie -- this is the
               rutracker anti-abuse CAPTCHA wall ...

Both trackers reported ``authenticated: true`` while the very same stat
carried the proof that the login round-trip obtained NO session cookie.
The flag was never measuring authentication: ``_is_tracker_authenticated``
fell back to *environment-variable presence*, and the stat was seeded
BEFORE the login attempt and never re-evaluated afterwards.  An operator
reading ``authenticated: true`` beside ``status: error`` is told the
opposite of the truth -- a §11.4/§11.4.6 report-layer bluff.

The fix splits the two facts that were conflated:

  * ``credentials_configured`` -- credentials/cookies are present in the
    environment (what the old flag actually measured).
  * ``authenticated``          -- a real session exists for this tracker,
    proven by the session store (or by operator-supplied browser cookies,
    matching the ``GET /api/v1/auth/status`` ``has_session`` semantics), and
    re-evaluated once the tracker's login round-trip has completed.

Every test below FAILS against the pre-fix code, so it catches the defect
rather than merely agreeing with the fix (§11.4.115).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[2] / "download-proxy" / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from merge_service.search import SearchOrchestrator, TrackerSearchStat  # noqa: E402

_PRIVATE_ENV = (
    "RUTRACKER_USERNAME",
    "RUTRACKER_PASSWORD",
    "RUTRACKER_COOKIES",
    "KINOZAL_USERNAME",
    "KINOZAL_PASSWORD",
    "NNMCLUB_USERNAME",
    "NNMCLUB_PASSWORD",
    "NNMCLUB_COOKIES",
    "IPTORRENTS_USERNAME",
    "IPTORRENTS_PASSWORD",
)


@pytest.fixture
def orch(monkeypatch):
    """A clean orchestrator with every tracker credential env var cleared."""
    for name in _PRIVATE_ENV:
        monkeypatch.delenv(name, raising=False)
    return SearchOrchestrator()


def test_credentials_present_but_no_session_is_not_authenticated(orch, monkeypatch):
    """RED against pre-fix: username+password alone reported authenticated=True.

    This is the exact live condition captured for rutracker and nnmclub --
    ``*_USERNAME``/``*_PASSWORD`` set, ``*_COOKIES`` absent, login refused by
    a CAPTCHA wall so no session was ever stored.
    """
    monkeypatch.setenv("RUTRACKER_USERNAME", "u")
    monkeypatch.setenv("RUTRACKER_PASSWORD", "p")

    assert orch._has_tracker_session("rutracker") is False, (
        "no session was ever stored for rutracker, so it is NOT authenticated"
    )
    assert orch._tracker_credentials_configured("rutracker") is True, (
        "username+password ARE configured -- that fact must still be reported"
    )


def test_session_presence_is_what_makes_a_tracker_authenticated(orch, monkeypatch):
    """A stored session -- and only that -- proves authentication."""
    monkeypatch.setenv("IPTORRENTS_USERNAME", "u")
    monkeypatch.setenv("IPTORRENTS_PASSWORD", "p")
    assert orch._has_tracker_session("iptorrents") is False

    orch._tracker_sessions["iptorrents"] = {"cookies": {"k": "v"}, "base_url": "https://x"}
    assert orch._has_tracker_session("iptorrents") is True


def test_operator_supplied_browser_cookies_count_as_a_session(orch, monkeypatch):
    """Parity with ``GET /api/v1/auth/status``: real cookies ARE a session.

    ``auth.py::all_trackers_auth_status`` already treats an operator-exported
    ``bb_session=`` / ``phpbb2mysql_4_sid=`` cookie as ``has_session: true``
    before any search runs.  The tracker_stats flag must agree, or the two
    surfaces contradict each other for the same tracker (§11.4.186).
    """
    monkeypatch.setenv("RUTRACKER_COOKIES", "bb_session=abc; other=1")
    monkeypatch.setenv("NNMCLUB_COOKIES", "phpbb2mysql_4_sid=def")
    assert orch._has_tracker_session("rutracker") is True
    assert orch._has_tracker_session("nnmclub") is True


def test_cookie_string_without_the_session_key_is_not_a_session(orch, monkeypatch):
    """A cookie jar carrying no session key does not authenticate anything."""
    monkeypatch.setenv("RUTRACKER_COOKIES", "cf_clearance=xyz")
    monkeypatch.setenv("NNMCLUB_COOKIES", "cf_clearance=xyz")
    assert orch._has_tracker_session("rutracker") is False
    assert orch._has_tracker_session("nnmclub") is False


def test_public_tracker_is_never_authenticated_nor_credentialed(orch):
    assert orch._has_tracker_session("rutor") is False
    assert orch._tracker_credentials_configured("rutor") is False


def test_stat_carries_both_facts_distinctly(orch):
    """RED against pre-fix: ``credentials_configured`` did not exist."""
    stat = TrackerSearchStat(name="rutracker", credentials_configured=True)
    payload = stat.to_dict()
    assert payload["authenticated"] is False
    assert payload["credentials_configured"] is True
    assert "authenticated" in payload and "credentials_configured" in payload


def test_seeded_stats_report_session_state_not_credential_presence(orch, monkeypatch):
    """RED against pre-fix: ``start_search`` seeded authenticated=True on env vars.

    Drives the real ``start_search`` seeding path -- the code that produced
    the misleading live report -- and asserts the seeded chip separates the
    two facts.
    """
    monkeypatch.setenv("RUTRACKER_USERNAME", "u")
    monkeypatch.setenv("RUTRACKER_PASSWORD", "p")

    metadata = orch.start_search(query="ubuntu", category="all")
    stat = metadata.tracker_stats.get("rutracker")
    assert stat is not None, "rutracker is enabled by its credentials, so it must be seeded"
    assert stat.authenticated is False, (
        "seeded before any login round-trip -- no session exists yet, so the "
        "honest report is authenticated=False"
    )
    assert stat.credentials_configured is True


def test_login_that_succeeds_during_the_search_flips_the_flag(orch, monkeypatch):
    """The flag must be re-evaluated after the tracker's round-trip completes.

    Pre-fix, ``authenticated`` was frozen at seed time and never revisited,
    so a session obtained DURING the search was invisible to that search's
    own report -- the mirror image of the captured defect.
    """
    monkeypatch.setenv("RUTRACKER_USERNAME", "u")
    monkeypatch.setenv("RUTRACKER_PASSWORD", "p")

    metadata = orch.start_search(query="ubuntu", category="all")
    stat = metadata.tracker_stats["rutracker"]
    assert stat.authenticated is False

    # The login succeeds mid-search and stores a session.
    orch._tracker_sessions["rutracker"] = {"cookies": {"bb_session": "x"}, "base_url": "https://rutracker.org"}
    orch._refresh_stat_auth_state(stat)
    assert stat.authenticated is True
    assert stat.credentials_configured is True


def test_failed_login_leaves_the_flag_false_after_completion(orch, monkeypatch):
    """The captured live defect, pinned: CAPTCHA-refused login stays False.

    Reproduces the exact shape of the 2026-09-02 evidence -- an errored stat
    carrying ``error_type='upstream_captcha'`` -- and asserts the report no
    longer claims the tracker is authenticated.
    """
    monkeypatch.setenv("NNMCLUB_USERNAME", "u")
    monkeypatch.setenv("NNMCLUB_PASSWORD", "p")

    metadata = orch.start_search(query="ubuntu", category="all")
    stat = metadata.tracker_stats["nnmclub"]
    stat.status = "error"
    stat.error_type = "upstream_captcha"
    stat.error = "nnmclub login.php is gated by a Cloudflare Turnstile JS CAPTCHA"

    orch._refresh_stat_auth_state(stat)

    assert stat.authenticated is False, (
        "no session cookie was obtained -- reporting authenticated=True beside "
        "status='error' is the §11.4 report-layer bluff this test guards"
    )
    assert stat.credentials_configured is True, (
        "the operator's credentials ARE configured -- that distinct fact must "
        "survive, so the report says 'configured but not logged in'"
    )
    assert stat.to_dict()["authenticated"] is False
    assert stat.to_dict()["credentials_configured"] is True
