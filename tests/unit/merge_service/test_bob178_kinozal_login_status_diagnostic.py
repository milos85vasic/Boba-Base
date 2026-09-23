"""BOB-178 — kinozal login-leg HTTP failure sets no diagnostic.

FORENSIC ANCHOR (BOB-178, verbatim from the tracked item).
``_search_kinozal``'s LOGIN response handling is:

    if login_resp.status not in (200, 301, 302):
        logger.error(...)
        return []

and sets NO diagnostic. Failing scenario: Cloudflare returns 403 on
kinozal's ``takelogin.php``. The kinozal result chip then reads
``status=empty, error=None`` — the exact BOB-172 false-null signature: a
refusal reported to the user as an empty result set, indistinguishable
from "no matches found".

CONTRAST ESTABLISHING THIS IS AN OVERSIGHT, NOT A DESIGN CHOICE. The
rutracker and nnmclub login failures DO set diagnostics (their own
``auth_failure`` / ``upstream_captcha`` classifications, keyed on "no
session cookie obtained" rather than raw HTTP status, since neither of
those two sites inspects the login POST's status code at all before
extracting cookies). The iptorrents login failure falls through to the
search fetch, where the shared ``_check_search_response`` guard (BOB-172/
BOB-177) catches it. Kinozal's login leg is the ONE path with neither: it
explicitly inspects ``login_resp.status`` and returns ``[]`` immediately on
a bad status, before ever reaching the search fetch the shared guard could
catch.

THE FIX. Because kinozal (unlike rutracker/nnmclub) already performs an
explicit HTTP-status check on its login response — the SAME class of
refusal ``_classify_upstream_http_status``/``_check_search_response``
(BOB-172/BOB-177) already exist to classify for the search leg — the
correct mirror here is to classify the LOGIN leg's status with the same
shared helper (``_classify_upstream_http_status``) and stash the resulting
diagnostic on ``self._last_public_tracker_diag["kinozal"]`` before the
early return, exactly as the search leg already does via
``_check_search_response``. This keeps kinozal speaking the SAME
diagnostic dialect the rest of the module already speaks (§11.4.28:
vocabulary deliberately shared, not re-minted), rather than inventing a
kinozal-only shape. A "no session cookie obtained despite 200/301/302"
gap (the rutracker/nnmclub failure mode) does NOT currently exist in
kinozal's code at all — kinozal never checks cookie presence after a
200/301/302 login response — and is a SEPARATE, pre-existing gap outside
this item's scope (out of scope per the tracked item's own acceptance
criteria, which is specifically about the HTTP-status leg).

NEGATIVE CONTROL (§11.4.201(1), mandatory). A HEALTHY kinozal login
(200/301/302, with a real session cookie obtained) must proceed to the
search leg with NO diagnostic stashed for the login leg. A fix that stashes
a diagnostic on every login response — even a successful one — would be
WORSE than the gap it closes: it would make a working tracker report a
spurious error. ``TestNegativeControlHealthyLoginIsNeverStashed`` below is
that guard, and it explicitly exercises statuses 200, 301, AND 302 (all
three are kinozal's own definition of a healthy login response — a
regression that narrowed the accepted set, or a fix that treats 301/302 as
failures, would be caught here).
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


# ---------------------------------------------------------------------------
# Minimal aiohttp stand-ins — same shapes as
# tests/unit/merge_service/test_bob177_guard_wiring_collapse.py (this
# file's direct sibling, exercising the same ``_search_kinozal`` call
# path), duplicated locally per this codebase's own convention of
# self-contained per-item test files rather than cross-file test imports.
# ---------------------------------------------------------------------------


class _FakeCookie:
    def __init__(self, key: str, value: str) -> None:
        self.key = key
        self.value = value


class _FakeResp:
    def __init__(self, status: int, body: str = "", cookies: dict | None = None) -> None:
        self.status = status
        self._body = body
        self.cookies = cookies or {}

    async def text(self, *a, **kw) -> str:
        return self._body

    async def read(self, *a, **kw) -> bytes:
        return self._body.encode("utf-8", "ignore")

    async def __aenter__(self) -> _FakeResp:
        return self

    async def __aexit__(self, *exc) -> bool:
        return False


class _FakeSession:
    """Stands in for ``aiohttp.ClientSession``.

    ``login_status``/``login_cookies`` answer the ``takelogin.php`` POST;
    ``status``/``body`` answer the ``browse.php`` GET that follows a
    successful login. A test that only cares about the login leg's
    behaviour never reaches the search leg (kinozal returns ``[]``
    immediately on a bad login status), so the GET-side fixture values are
    irrelevant to the RED/GREEN tests below and only matter to the
    negative-control tests that need a full healthy round-trip.
    """

    def __init__(self, *, status: int = 200, body: str = "", login_status: int = 200, login_cookies: dict | None = None) -> None:
        self._status = status
        self._body = body
        self._login_status = login_status
        self._login_cookies = login_cookies or {}

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *exc) -> bool:
        return False

    def get(self, *a, **kw) -> _FakeResp:
        return _FakeResp(self._status, self._body)

    def post(self, *a, **kw) -> _FakeResp:
        return _FakeResp(self._login_status, "", cookies=self._login_cookies)


def _run(coro):
    return asyncio.run(coro)


def _set_kinozal_env(monkeypatch) -> None:
    monkeypatch.setenv("KINOZAL_USERNAME", "test-user-not-a-real-account")
    monkeypatch.setenv("KINOZAL_PASSWORD", "test-value-not-a-real-secret")
    monkeypatch.setenv("KINOZAL_MIRRORS", "https://kinozal.example")


# ===========================================================================
# 1. RED/GREEN — the defect itself. A stubbed 403 on the kinozal login
#    endpoint must produce a non-``None`` diagnostic on the kinozal chip.
#    Run unmodified against pre-fix code, this class's first test FAILS
#    (diag is ``None``) — that failure IS the RED evidence (§11.4.115).
# ===========================================================================


class TestKinozalLoginFailureSetsDiagnostic:
    def test_login_403_sets_non_none_diagnostic(self, monkeypatch):
        _set_kinozal_env(monkeypatch)

        orch = SearchOrchestrator()
        fake_session = _FakeSession(login_status=403)
        import aiohttp

        monkeypatch.setattr(aiohttp, "ClientSession", lambda *a, **kw: fake_session)

        results = _run(orch._search_kinozal("debian", "all"))

        assert results == []
        diag = orch._last_public_tracker_diag.get("kinozal")
        assert diag is not None, "kinozal login-failure diagnostic must be set on a 403 login response (BOB-178)"
        assert diag.get("error") is not None
        assert diag.get("http_status") == 403

    @pytest.mark.parametrize("status", [401, 404, 429, 500, 503])
    def test_other_non_success_login_statuses_also_set_diagnostic(self, monkeypatch, status):
        _set_kinozal_env(monkeypatch)

        orch = SearchOrchestrator()
        fake_session = _FakeSession(login_status=status)
        import aiohttp

        monkeypatch.setattr(aiohttp, "ClientSession", lambda *a, **kw: fake_session)

        results = _run(orch._search_kinozal("debian", "all"))

        assert results == []
        diag = orch._last_public_tracker_diag.get("kinozal")
        assert diag is not None, f"kinozal login-failure diagnostic must be set on a {status} login response"
        assert diag.get("http_status") == status

    def test_atypical_2xx_login_status_still_sets_a_real_diagnostic(self, monkeypatch):
        """201 is not in kinozal's accepted (200, 301, 302) set but IS a 2xx,
        so the shared classifier (``_classify_upstream_http_status``) alone
        would return ``None`` for it — the exact shape that, if stashed
        unguarded, would silently re-introduce the ``error=None`` defect for
        this one status value. The fix must not depend on the classifier's
        2xx-passthrough; it must always produce a real diagnostic dict for
        any status outside kinozal's own accepted set.
        """
        _set_kinozal_env(monkeypatch)

        orch = SearchOrchestrator()
        fake_session = _FakeSession(login_status=201)
        import aiohttp

        monkeypatch.setattr(aiohttp, "ClientSession", lambda *a, **kw: fake_session)

        results = _run(orch._search_kinozal("debian", "all"))

        assert results == []
        diag = orch._last_public_tracker_diag.get("kinozal")
        assert diag is not None, "an atypical 2xx login status must still produce a non-None diagnostic"
        assert diag.get("error") is not None


# ===========================================================================
# 2. Negative control (§11.4.201(1), mandatory). A healthy login must NOT
#    have a diagnostic stashed for the login leg — the fix must not make a
#    healthy login path start reporting a spurious error.
# ===========================================================================


class TestNegativeControlHealthyLoginIsNeverStashed:
    @pytest.mark.parametrize("status", [200, 301, 302])
    def test_healthy_login_status_leaves_no_diagnostic(self, monkeypatch, status):
        _set_kinozal_env(monkeypatch)

        orch = SearchOrchestrator()
        fake_session = _FakeSession(
            status=200,
            body="<html><body>no matches</body></html>",
            login_status=status,
            login_cookies={"klid": _FakeCookie("klid", "synthetic-session")},
        )
        import aiohttp

        monkeypatch.setattr(aiohttp, "ClientSession", lambda *a, **kw: fake_session)

        _run(orch._search_kinozal("debian", "all"))

        assert "kinozal" not in orch._last_public_tracker_diag, (
            f"a healthy login status ({status}) must not stash a diagnostic — this fix must not make "
            "a healthy login path start reporting a spurious error"
        )
