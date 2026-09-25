"""BOB-179 — close the two gaps the BOB-172 independent review stated but
did not fix.

FORENSIC ANCHOR (verbatim from the tracked item, appended to
docs/qa/BOB-172/fix_evidence_20260822.log 2026-08-23 per the review's
IMPORTANT-3, and closed here):

GAP A — an exception raised BEFORE resp.status is read. Reviewer probe B,
captured: a connection-refused rutracker yields status='empty', error=None,
http_status=None, metadata.errors=[], metadata.status='completed'. Each
``_search_*`` method swallowed exceptions (``except Exception:
logger.error; return results``) before ``_search_one``'s own error handling
could observe them -- a tracker that is DOWN was indistinguishable from one
that is genuinely empty, because the BOB-172 HTTP-status guard never runs:
control never reaches the status check.

GAP B — a soft refusal delivered at HTTP 200. Reviewer probe A, captured:
``_classify_upstream_http_status(200, <cf-chl body>)`` returns ``None`` --
CORRECT by design and must stay so (a 2xx is a usable response; widening
that trigger to fire on body markers would risk exactly the over-fire the
negative controls exist to prevent, §11.4.201(1)). But all five
private-tracker search GETs use aiohttp's default ``allow_redirects=True``,
so a session-expiry ``302 -> login-page-200`` chain parses to zero rows and
reports empty.

THE FIX.
  Gap A: each ``_search_*`` method's ``except Exception:`` clause now
  stashes the real exception (``error_type`` = the exception's class name,
  ``error`` = a human-readable message) onto
  ``self._last_public_tracker_diag[<tracker>]``, mirroring the established
  BOB-235 kinozal pattern (this session's prior fix for the identical class
  of gap on kinozal specifically) -- no second diagnostic dialect is
  minted (§11.4.28). nnmclub gets the fix at BOTH of its two call frames:
  ``_search_nnmclub``'s own search-leg except, AND ``_nnmclub_login``'s
  login-leg except (the username/password auth path never reaches
  ``_search_nnmclub``'s except at all when the login POST itself is
  refused -- the identical false-null one call frame deeper).

  Gap B: a NEW, DISTINCT detector, ``_detect_session_expired_redirect``,
  inspects aiohttp's own redirect-chain bookkeeping (``resp.history`` /
  ``resp.url``) -- authoritative facts about what happened on the wire,
  never a body-text proxy. It is wired in at all five search-GET call
  sites, AFTER ``_check_search_response`` (which correctly passes a 2xx
  through) and BEFORE the row parser runs. It is explicitly NOT a widening
  of ``_classify_upstream_http_status``'s status-code trigger -- that
  function is untouched by this change and its own negative controls
  (test_bob172_tracker_http_error_not_empty.py) stay green.

NEGATIVE CONTROLS (§11.4.201(1), mandatory, both gaps):
  Gap A: a healthy round-trip with no exception must stash NO diagnostic
  (already covered per-tracker by the sibling BOB-177/BOB-235 files; this
  file adds one covering the two NEW call frames Gap A's fix touches:
  ``_nnmclub_login``'s except, and the rutracker CREDENTIAL path's except).
  Gap B: (a) a legitimate HTTP 200 whose body happens to mention "login"
  somewhere, but which was NOT reached via any redirect (``resp.history``
  empty) -- the aiohttp-level signal ``_detect_session_expired_redirect``
  keys on, never a body-text scan, so this must NOT trigger; (b) a redirect
  chain that lands back on the SAME search-endpoint path (e.g. an
  http -> https upgrade) -- not a session-expiry signature, must NOT
  trigger either.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys

import pytest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_SRC_PATH = os.path.join(_REPO_ROOT, "download-proxy", "src")
_MS_PATH = os.path.join(_SRC_PATH, "merge_service")

sys.modules.setdefault("merge_service", type(sys)("merge_service"))
sys.modules["merge_service"].__path__ = [_MS_PATH]

_search_spec = importlib.util.spec_from_file_location("merge_service.search", os.path.join(_MS_PATH, "search.py"))
_search_mod = importlib.util.module_from_spec(_search_spec)
sys.modules["merge_service.search"] = _search_mod
_search_spec.loader.exec_module(_search_mod)

SearchOrchestrator = _search_mod.SearchOrchestrator
_detect_session_expired_redirect = _search_mod._detect_session_expired_redirect


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Minimal aiohttp stand-ins. A unit test, so a stub is the sanctioned
# mechanism (§11.4.27(A)). Shapes mirror the sibling BOB-172/177/178/235
# fixtures in this same directory, extended with `.history` / `.url` so the
# Gap B detector (which reads both) can be driven directly.
# ---------------------------------------------------------------------------


class _FakeCookie:
    def __init__(self, key: str, value: str) -> None:
        self.key = key
        self.value = value


class _FakeResp:
    def __init__(
        self,
        status: int,
        body: str = "",
        *,
        cookies: dict | None = None,
        history: tuple = (),
        url: str = "",
    ) -> None:
        self.status = status
        self._body = body
        self.cookies = cookies or {}
        self.history = history
        self.url = url

    async def text(self, *a, **kw) -> str:
        return self._body

    async def read(self, *a, **kw) -> bytes:
        return self._body.encode("utf-8", "ignore")

    async def __aenter__(self) -> _FakeResp:
        return self

    async def __aexit__(self, *exc) -> bool:
        return False


class _RaisingCtx:
    """An ``async with`` target that raises on entry, like aiohttp does on
    a connection-refused / DNS-failure / TLS-failure transport error.
    """

    def __init__(self, exc: BaseException) -> None:
        self._exc = exc

    async def __aenter__(self):
        raise self._exc

    async def __aexit__(self, *exc) -> bool:
        return False


class _FakeSession:
    """Stands in for ``aiohttp.ClientSession``.

    ``get_exc``/``post_exc`` make the corresponding call raise on entry
    (the Gap A transport-failure shape). Otherwise ``get()``/``post()``
    return a configured ``_FakeResp`` (the Gap B redirect-shape, or a plain
    healthy/refused response).
    """

    def __init__(
        self,
        *,
        get_status: int = 200,
        get_body: str = "",
        get_history: tuple = (),
        get_url: str = "",
        get_exc: BaseException | None = None,
        post_status: int = 200,
        post_cookies: dict | None = None,
        post_exc: BaseException | None = None,
    ) -> None:
        self._get_status = get_status
        self._get_body = get_body
        self._get_history = get_history
        self._get_url = get_url
        self._get_exc = get_exc
        self._post_status = post_status
        self._post_cookies = post_cookies or {}
        self._post_exc = post_exc

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *exc) -> bool:
        return False

    def get(self, *a, **kw):
        if self._get_exc is not None:
            return _RaisingCtx(self._get_exc)
        return _FakeResp(self._get_status, self._get_body, history=self._get_history, url=self._get_url)

    def post(self, *a, **kw):
        if self._post_exc is not None:
            return _RaisingCtx(self._post_exc)
        return _FakeResp(self._post_status, "", cookies=self._post_cookies)


def _patch_session(monkeypatch, session: _FakeSession) -> None:
    import aiohttp

    monkeypatch.setattr(aiohttp, "ClientSession", lambda *a, **kw: session)


_CONNECT_REFUSED = ConnectionRefusedError("Connect call failed ('127.0.0.1', 443)")


# ===========================================================================
# GAP A — a connection-refused / DOWN tracker must stash a diagnostic,
# never be swallowed into a silent empty result.
# ===========================================================================


class TestGapAConnectionRefusedSetsDiagnostic:
    def test_rutracker_cookie_path(self, monkeypatch):
        monkeypatch.setenv("RUTRACKER_COOKIES", "bb_session=SYNTHETIC-TEST-FIXTURE-VALUE")
        monkeypatch.setenv("RUTRACKER_MIRRORS", "https://rutracker.example")
        monkeypatch.delenv("RUTRACKER_USERNAME", raising=False)
        monkeypatch.delenv("RUTRACKER_PASSWORD", raising=False)

        orch = SearchOrchestrator()
        _patch_session(monkeypatch, _FakeSession(get_exc=_CONNECT_REFUSED))

        results = _run(orch._search_rutracker("debian", "all"))

        assert results == []
        diag = orch._last_public_tracker_diag.get("rutracker")
        assert diag is not None, (
            "a connection-refused rutracker (cookie path) must not be reported as a "
            "silent empty result (BOB-179 Gap A)"
        )
        assert diag.get("error_type") == "ConnectionRefusedError"
        assert diag.get("error")

    def test_rutracker_credential_path(self, monkeypatch):
        monkeypatch.delenv("RUTRACKER_COOKIES", raising=False)
        monkeypatch.setenv("RUTRACKER_USERNAME", "test-user-not-a-real-account")
        monkeypatch.setenv("RUTRACKER_PASSWORD", "test-value-not-a-real-secret")
        monkeypatch.setenv("RUTRACKER_MIRRORS", "https://rutracker.example")

        orch = SearchOrchestrator()
        # The login POST succeeds (real bb_* cookie) so the failure is
        # isolated to the search GET -- the credential-path except clause
        # under test, distinct from the cookie-path one above.
        _patch_session(
            monkeypatch,
            _FakeSession(
                post_cookies={"bb_session": _FakeCookie("bb_session", "synthetic-session")},
                get_exc=_CONNECT_REFUSED,
            ),
        )

        results = _run(orch._search_rutracker("debian", "all"))

        assert results == []
        diag = orch._last_public_tracker_diag.get("rutracker")
        assert diag is not None, (
            "a connection-refused rutracker (credential path) must not be reported as "
            "a silent empty result (BOB-179 Gap A)"
        )
        assert diag.get("error_type") == "ConnectionRefusedError"

    def test_nnmclub_search_leg_with_explicit_cookies(self, monkeypatch):
        monkeypatch.setenv("NNMCLUB_COOKIES", "phpbb2mysql_4_sid=SYNTHETIC-TEST-FIXTURE-VALUE")
        monkeypatch.setenv("NNMCLUB_MIRRORS", "https://nnmclub.example")

        orch = SearchOrchestrator()
        _patch_session(monkeypatch, _FakeSession(get_exc=_CONNECT_REFUSED))

        results = _run(orch._search_nnmclub("debian", "all"))

        assert results == []
        diag = orch._last_public_tracker_diag.get("nnmclub")
        assert diag is not None, (
            "a connection-refused nnmclub (explicit-cookies search leg) must not be "
            "reported as a silent empty result (BOB-179 Gap A)"
        )
        assert diag.get("error_type") == "ConnectionRefusedError"

    def test_nnmclub_login_leg_with_username_password(self, monkeypatch):
        """Distinct call frame: no NNMCLUB_COOKIES, so `_search_nnmclub`
        delegates to `_nnmclub_login`, whose OWN except clause is the one
        under test here -- it never propagates up to `_search_nnmclub`'s
        except at all.
        """
        monkeypatch.delenv("NNMCLUB_COOKIES", raising=False)
        monkeypatch.setenv("NNMCLUB_USERNAME", "test-user-not-a-real-account")
        monkeypatch.setenv("NNMCLUB_PASSWORD", "test-value-not-a-real-secret")
        monkeypatch.setenv("NNMCLUB_MIRRORS", "https://nnmclub.example")

        orch = SearchOrchestrator()
        _patch_session(monkeypatch, _FakeSession(post_exc=_CONNECT_REFUSED))

        results = _run(orch._search_nnmclub("debian", "all"))

        assert results == []
        diag = orch._last_public_tracker_diag.get("nnmclub")
        assert diag is not None, (
            "a connection-refused nnmclub LOGIN leg (username/password path) must not "
            "be reported as a silent empty result (BOB-179 Gap A)"
        )
        assert diag.get("error_type") == "ConnectionRefusedError"

    def test_iptorrents(self, monkeypatch):
        monkeypatch.setenv("IPTORRENTS_USERNAME", "test-user-not-a-real-account")
        monkeypatch.setenv("IPTORRENTS_PASSWORD", "test-value-not-a-real-secret")

        orch = SearchOrchestrator()
        _patch_session(
            monkeypatch,
            _FakeSession(
                post_cookies={"uid": _FakeCookie("uid", "synthetic")},
                get_exc=_CONNECT_REFUSED,
            ),
        )

        results = _run(orch._search_iptorrents("debian", "all"))

        assert results == []
        diag = orch._last_public_tracker_diag.get("iptorrents")
        assert diag is not None, (
            "a connection-refused iptorrents must not be reported as a silent empty "
            "result (BOB-179 Gap A)"
        )
        assert diag.get("error_type") == "ConnectionRefusedError"


class TestGapANegativeControlHealthyRoundTripStashesNothing:
    """§11.4.201(1): the two NEW call frames Gap A's fix touches must not
    stash a spurious diagnostic on a healthy round-trip. The other three
    (rutracker cookie path, kinozal, iptorrents) are already covered by
    the sibling BOB-177/BOB-235 negative controls this session did not
    change the healthy-path behaviour of.
    """

    def test_rutracker_credential_path_healthy(self, monkeypatch):
        monkeypatch.delenv("RUTRACKER_COOKIES", raising=False)
        monkeypatch.setenv("RUTRACKER_USERNAME", "u")
        monkeypatch.setenv("RUTRACKER_PASSWORD", "p")
        monkeypatch.setenv("RUTRACKER_MIRRORS", "https://rutracker.example")

        orch = SearchOrchestrator()
        _patch_session(
            monkeypatch,
            _FakeSession(
                post_cookies={"bb_session": _FakeCookie("bb_session", "x")},
                get_status=200,
                get_body="<html><body>no matches</body></html>",
            ),
        )

        _run(orch._search_rutracker("debian", "all"))

        assert "rutracker" not in orch._last_public_tracker_diag

    def test_nnmclub_login_leg_healthy(self, monkeypatch):
        monkeypatch.delenv("NNMCLUB_COOKIES", raising=False)
        monkeypatch.setenv("NNMCLUB_USERNAME", "u")
        monkeypatch.setenv("NNMCLUB_PASSWORD", "p")
        monkeypatch.setenv("NNMCLUB_MIRRORS", "https://nnmclub.example")

        orch = SearchOrchestrator()
        _patch_session(
            monkeypatch,
            _FakeSession(
                post_cookies={"phpbb2mysql_4_sid": _FakeCookie("phpbb2mysql_4_sid", "x")},
                get_status=200,
                get_body="<html><body>no matches</body></html>",
            ),
        )

        _run(orch._search_nnmclub("debian", "all"))

        assert "nnmclub" not in orch._last_public_tracker_diag


# ===========================================================================
# GAP B — a session-expiry redirect-to-login chain (302 -> login page 200)
# must be classified, never parsed to a silent zero-row "empty".
# ===========================================================================


class TestGapBRedirectToLoginSetsDiagnostic:
    def test_rutracker_cookie_path(self, monkeypatch):
        monkeypatch.setenv("RUTRACKER_COOKIES", "bb_session=SYNTHETIC-TEST-FIXTURE-VALUE")
        monkeypatch.setenv("RUTRACKER_MIRRORS", "https://rutracker.example")
        monkeypatch.delenv("RUTRACKER_USERNAME", raising=False)
        monkeypatch.delenv("RUTRACKER_PASSWORD", raising=False)

        orch = SearchOrchestrator()
        _patch_session(
            monkeypatch,
            _FakeSession(
                get_status=200,
                get_body="<html><body>please log in</body></html>",
                get_history=(_FakeResp(302),),
                get_url="https://rutracker.example/forum/login.php",
            ),
        )

        results = _run(orch._search_rutracker("debian", "all"))

        assert results == []
        diag = orch._last_public_tracker_diag.get("rutracker")
        assert diag is not None, (
            "a rutracker search redirected to a login page must not be reported as a "
            "silent empty result (BOB-179 Gap B)"
        )
        assert diag.get("error_type") == "upstream_session_expired"

    def test_rutracker_credential_path(self, monkeypatch):
        monkeypatch.delenv("RUTRACKER_COOKIES", raising=False)
        monkeypatch.setenv("RUTRACKER_USERNAME", "test-user-not-a-real-account")
        monkeypatch.setenv("RUTRACKER_PASSWORD", "test-value-not-a-real-secret")
        monkeypatch.setenv("RUTRACKER_MIRRORS", "https://rutracker.example")

        orch = SearchOrchestrator()
        _patch_session(
            monkeypatch,
            _FakeSession(
                post_cookies={"bb_session": _FakeCookie("bb_session", "synthetic-session")},
                get_status=200,
                get_body="<html><body>please log in</body></html>",
                get_history=(_FakeResp(302),),
                get_url="https://rutracker.example/forum/login.php",
            ),
        )

        results = _run(orch._search_rutracker("debian", "all"))

        assert results == []
        diag = orch._last_public_tracker_diag.get("rutracker")
        assert diag is not None
        assert diag.get("error_type") == "upstream_session_expired"

    def test_kinozal(self, monkeypatch):
        monkeypatch.setenv("KINOZAL_USERNAME", "test-user-not-a-real-account")
        monkeypatch.setenv("KINOZAL_PASSWORD", "test-value-not-a-real-secret")
        monkeypatch.setenv("KINOZAL_MIRRORS", "https://kinozal.example")

        orch = SearchOrchestrator()
        _patch_session(
            monkeypatch,
            _FakeSession(
                post_cookies={"klid": _FakeCookie("klid", "synthetic")},
                get_status=200,
                get_body="<html><body>please log in</body></html>",
                get_history=(_FakeResp(302),),
                get_url="https://kinozal.example/login.php",
            ),
        )

        results = _run(orch._search_kinozal("debian", "all"))

        assert results == []
        diag = orch._last_public_tracker_diag.get("kinozal")
        assert diag is not None, (
            "a kinozal search redirected to a login page must not be reported as a "
            "silent empty result (BOB-179 Gap B)"
        )
        assert diag.get("error_type") == "upstream_session_expired"

    def test_nnmclub(self, monkeypatch):
        monkeypatch.setenv("NNMCLUB_COOKIES", "phpbb2mysql_4_sid=SYNTHETIC-TEST-FIXTURE-VALUE")
        monkeypatch.setenv("NNMCLUB_MIRRORS", "https://nnmclub.example")

        orch = SearchOrchestrator()
        _patch_session(
            monkeypatch,
            _FakeSession(
                get_status=200,
                get_body="<html><body>please log in</body></html>",
                get_history=(_FakeResp(302),),
                get_url="https://nnmclub.example/forum/login.php",
            ),
        )

        results = _run(orch._search_nnmclub("debian", "all"))

        assert results == []
        diag = orch._last_public_tracker_diag.get("nnmclub")
        assert diag is not None, (
            "an nnmclub search redirected to a login page must not be reported as a "
            "silent empty result (BOB-179 Gap B)"
        )
        assert diag.get("error_type") == "upstream_session_expired"

    def test_iptorrents(self, monkeypatch):
        monkeypatch.setenv("IPTORRENTS_USERNAME", "test-user-not-a-real-account")
        monkeypatch.setenv("IPTORRENTS_PASSWORD", "test-value-not-a-real-secret")

        orch = SearchOrchestrator()
        _patch_session(
            monkeypatch,
            _FakeSession(
                post_cookies={"uid": _FakeCookie("uid", "synthetic")},
                get_status=200,
                get_body="<html><body>please log in</body></html>",
                get_history=(_FakeResp(302),),
                get_url="https://iptorrents.com/do-login.php",
            ),
        )

        results = _run(orch._search_iptorrents("debian", "all"))

        assert results == []
        diag = orch._last_public_tracker_diag.get("iptorrents")
        assert diag is not None, (
            "an iptorrents search redirected to a login page must not be reported as "
            "a silent empty result (BOB-179 Gap B)"
        )
        assert diag.get("error_type") == "upstream_session_expired"


class TestGapBNegativeControls:
    """§11.4.201(1), mandatory. A guard that over-fires is a worse defect
    than the false-null being fixed -- these two must stay green both
    before AND after the fix, pinning the boundary explicitly.
    """

    def test_legitimate_200_mentioning_login_in_body_is_not_flagged(self, monkeypatch):
        """No redirect occurred (``resp.history`` empty) -- the detector
        keys on aiohttp's OWN redirect bookkeeping, never a body-text scan,
        so a real search-results page that happens to mention the word
        "login" somewhere (a forum signature, a help link, ...) must NOT
        be misclassified as a session-expiry redirect.
        """
        monkeypatch.setenv("RUTRACKER_COOKIES", "bb_session=SYNTHETIC-TEST-FIXTURE-VALUE")
        monkeypatch.setenv("RUTRACKER_MIRRORS", "https://rutracker.example")
        monkeypatch.delenv("RUTRACKER_USERNAME", raising=False)
        monkeypatch.delenv("RUTRACKER_PASSWORD", raising=False)

        orch = SearchOrchestrator()
        _patch_session(
            monkeypatch,
            _FakeSession(
                get_status=200,
                get_body="<html><body>see also: how to <a href='/login.php'>login</a></body></html>",
                get_history=(),  # no redirect at all
                get_url="https://rutracker.example/forum/tracker.php?nm=debian&fo=1",
            ),
        )

        _run(orch._search_rutracker("debian", "all"))

        assert "rutracker" not in orch._last_public_tracker_diag, (
            "a body merely mentioning 'login' with NO redirect must not trigger the "
            "session-expiry detector -- over-firing is a §11.4.201(1) FAIL-bluff"
        )

    def test_redirect_that_lands_back_on_the_search_endpoint_is_not_flagged(self, monkeypatch):
        """A redirect chain occurred (e.g. an http -> https upgrade) but the
        FINAL resolved path is the same search endpoint that was requested
        -- not a session-expiry signature, must not be flagged.
        """
        monkeypatch.setenv("RUTRACKER_COOKIES", "bb_session=SYNTHETIC-TEST-FIXTURE-VALUE")
        monkeypatch.setenv("RUTRACKER_MIRRORS", "https://rutracker.example")
        monkeypatch.delenv("RUTRACKER_USERNAME", raising=False)
        monkeypatch.delenv("RUTRACKER_PASSWORD", raising=False)

        orch = SearchOrchestrator()
        _patch_session(
            monkeypatch,
            _FakeSession(
                get_status=200,
                get_body="<html><body>no matches</body></html>",
                get_history=(_FakeResp(301),),
                get_url="https://rutracker.example/forum/tracker.php",
            ),
        )

        _run(orch._search_rutracker("debian", "all"))

        assert "rutracker" not in orch._last_public_tracker_diag, (
            "a redirect that lands back on the requested search endpoint is not a "
            "session-expiry signature and must not be flagged"
        )


# ===========================================================================
# Unit coverage of the detector function itself, isolated from any tracker
# call site.
# ===========================================================================


class TestDetectSessionExpiredRedirectUnit:
    def test_none_when_no_history(self):
        assert (
            _detect_session_expired_redirect(
                "probe", "https://example.test/search?q=x", (), "https://example.test/search?q=x"
            )
            is None
        )

    def test_none_when_final_path_matches_requested_path(self):
        assert (
            _detect_session_expired_redirect(
                "probe",
                "https://example.test/search?q=x",
                (_FakeResp(301),),
                "https://example.test/search?q=y",
            )
            is None
        )

    def test_none_when_final_path_does_not_look_like_login(self):
        assert (
            _detect_session_expired_redirect(
                "probe",
                "https://example.test/search?q=x",
                (_FakeResp(302),),
                "https://example.test/maintenance.html",
            )
            is None
        )

    def test_diagnostic_when_redirected_to_login_path(self):
        diag = _detect_session_expired_redirect(
            "probe",
            "https://example.test/search?q=x",
            (_FakeResp(302),),
            "https://example.test/login.php",
            200,
        )
        assert diag is not None
        assert diag["error_type"] == "upstream_session_expired"
        assert diag["http_status"] == 200
        assert "login" in diag["error"].lower()
