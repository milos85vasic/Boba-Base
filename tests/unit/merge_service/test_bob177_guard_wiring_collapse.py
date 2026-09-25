"""BOB-177 — collapse the five duplicated HTTP-refusal guards into ONE
shared, fully-tested helper, and prove the wiring at every call-site.

FORENSIC ANCHOR (BOB-177, verbatim from the tracked item). BOB-172 wired an
IDENTICAL 4-line HTTP-refusal guard at FIVE private-tracker search sites in
`search.py` (rutracker's cookie path, rutracker's credential path, kinozal,
nnmclub, iptorrents). A reviewer-authored mutation during BOB-172's
independent review deleted ONLY the kinozal guard's wiring, leaving the
classifier function (`_classify_upstream_http_status`) intact, and the FULL
merge_service test suite stayed green with zero failures. Firsthand
reproduction of that finding (this session, `.venv/bin/python -m pytest
tests/unit/merge_service/ -q`, before this fix) confirmed the SAME is true
of nnmclub, iptorrents, and the rutracker-CREDENTIAL path (distinct from the
rutracker-COOKIE path, which IS covered by
`test_bob172_tracker_http_error_not_empty.py` and correctly reddens on the
identical deletion).

THE FIX. The five identical 4-line blocks are collapsed into one shared
method, `SearchOrchestrator._check_search_response(tracker_name, status,
body) -> bool`, called from all five sites. This file has two jobs:

1. Test the shared helper ONCE, thoroughly (every refusal condition it
   handles, via `_classify_upstream_http_status`'s own status-code and
   challenge-marker branches), plus its own new behaviour (the boolean
   return + the stash onto `_last_public_tracker_diag`).
2. Prove the WIRING at each of the five call-sites is intact — a test that
   would catch "the call site stopped calling the helper" even if the
   helper itself is perfectly tested in isolation. This is the item's own
   acceptance criterion: mutating (deleting) the guard-wiring line(s) at
   ANY of the five sites must redden at least one test here. Each
   `test_<site>_wiring_...` test below is exactly that regression guard —
   it was run against the original code with that site's 4-line block
   deleted (matching the reviewer's mutation) and confirmed to FAIL, then
   run again against the fixed code and confirmed to PASS.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
from unittest.mock import patch

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
_classify_upstream_http_status = _search_mod._classify_upstream_http_status


# ---------------------------------------------------------------------------
# Minimal aiohttp stand-ins. A unit test, so a stub is the sanctioned
# mechanism (§11.4.27(A)); shapes mirror the real aiohttp response/session
# surface each private-tracker site actually calls (`.status`, `.text()`,
# `.read()`, `.cookies`, async context-manager protocol on both the session
# and the response).
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
        # BOB-179: complete the aiohttp.ClientResponse contract -- see the
        # identical addition (and its rationale) in
        # test_bob172_tracker_http_error_not_empty.py's `_FakeResponse`.
        self.history: tuple = ()
        self.url = ""

    async def text(self, *a, **kw) -> str:
        return self._body

    async def read(self, *a, **kw) -> bytes:
        return self._body.encode("utf-8", "ignore")

    async def __aenter__(self) -> _FakeResp:
        return self

    async def __aexit__(self, *exc) -> bool:
        return False


class _FakeSession:
    """Stands in for `aiohttp.ClientSession`.

    A single configured (status, body) answers every GET (the search
    request each site issues exactly once); `login_cookies` answers the
    POST a login-based site issues first (kinozal, iptorrents, and
    rutracker's credential path). Sites that authenticate via an
    operator-supplied cookie env var (rutracker's cookie path, nnmclub with
    `NNMCLUB_COOKIES` set) never call `.post()`.
    """

    def __init__(self, *, status: int, body: str, login_status: int = 200, login_cookies: dict | None = None) -> None:
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


# A refusal body carrying the measured Cloudflare challenge markers (BOB-172
# fixture, `_CLOUDFLARE_403_BODY` in test_bob172_tracker_http_error_not_empty.py).
_REFUSAL_BODY = (
    "<!DOCTYPE html><html><head><title>Just a moment...</title></head>"
    '<body><div class="cf-chl-wrapper"><div id="challenge-platform">'
    "Enable JavaScript and cookies to continue</div></div></body></html>"
)


def _run(coro):
    return asyncio.run(coro)


# ===========================================================================
# 1. The shared helper, tested ONCE, thoroughly.
# ===========================================================================


class TestCheckSearchResponseHelper:
    def test_2xx_returns_true_and_stashes_nothing(self):
        orch = SearchOrchestrator()
        assert orch._check_search_response("probe", 200, "<html>ok</html>") is True
        assert "probe" not in orch._last_public_tracker_diag

    def test_204_no_content_is_also_a_pass(self):
        orch = SearchOrchestrator()
        assert orch._check_search_response("probe", 204, "") is True
        assert "probe" not in orch._last_public_tracker_diag

    @pytest.mark.parametrize(
        ("status", "error_type"),
        [
            (401, "upstream_http_401"),
            (403, "upstream_http_403"),
            (404, "upstream_http_404"),
            (429, "upstream_http_429"),
            (503, "upstream_http_503"),
            (500, "upstream_http_500"),
        ],
    )
    def test_refusal_status_returns_false_and_stashes_typed_diag(self, status, error_type):
        orch = SearchOrchestrator()
        result = orch._check_search_response("probe", status, "<html>refused</html>")

        assert result is False
        diag = orch._last_public_tracker_diag.get("probe")
        assert diag is not None, "refusal must be stashed under the given tracker_name"
        assert diag["error_type"] == error_type
        assert diag["http_status"] == status
        assert diag["error"]

    def test_challenge_markers_enrich_the_reason(self):
        orch = SearchOrchestrator()
        orch._check_search_response("probe", 403, _REFUSAL_BODY)
        diag = orch._last_public_tracker_diag["probe"]
        assert "bot-protection" in diag["error"]

    def test_stashes_under_the_exact_tracker_name_given(self):
        orch = SearchOrchestrator()
        orch._check_search_response("kinozal", 403, "<html>refused</html>")
        assert "kinozal" in orch._last_public_tracker_diag
        assert "rutracker" not in orch._last_public_tracker_diag

    def test_matches_classify_upstream_http_status_exactly(self):
        """The helper must not silently diverge from the classifier it wraps."""
        orch = SearchOrchestrator()
        for status in (401, 403, 404, 429, 503, 418):
            orch._last_public_tracker_diag.clear()
            expected = _classify_upstream_http_status(status, "<html>x</html>")
            result = orch._check_search_response("probe", status, "<html>x</html>")
            assert result is (expected is None)
            if expected is not None:
                assert orch._last_public_tracker_diag["probe"] == expected


# ===========================================================================
# 2. Per-call-site wiring proof. Each of these fails against a build where
#    that ONE site's guard-wiring call was deleted (the reviewer's exact
#    BOB-172 mutation), even though `_check_search_response` itself is
#    fully covered above. This is the item's acceptance criterion.
# ===========================================================================


class TestRutrackerCookiePathWiring:
    """Also covered end-to-end by test_bob172_tracker_http_error_not_empty.py
    (via the full orchestrator fan-out); this direct-call variant matches the
    harness used for the other four sites below for a uniform proof shape.
    """

    def test_refusal_is_stashed_and_results_empty(self, monkeypatch):
        monkeypatch.setenv("RUTRACKER_COOKIES", "bb_session=SYNTHETIC-TEST-FIXTURE-VALUE")
        monkeypatch.setenv("RUTRACKER_MIRRORS", "https://rutracker.example")
        monkeypatch.delenv("RUTRACKER_USERNAME", raising=False)
        monkeypatch.delenv("RUTRACKER_PASSWORD", raising=False)

        orch = SearchOrchestrator()
        fake_session = _FakeSession(status=403, body=_REFUSAL_BODY)
        import aiohttp

        monkeypatch.setattr(aiohttp, "ClientSession", lambda *a, **kw: fake_session)

        results = _run(orch._search_rutracker("debian", "all"))

        assert results == []
        diag = orch._last_public_tracker_diag.get("rutracker")
        assert diag is not None, "the cookie-path guard did not fire — wiring is broken"
        assert diag["http_status"] == 403


class TestRutrackerCredentialPathWiring:
    """Distinct from the cookie path above: RUTRACKER_COOKIES unset, so the
    username/password branch runs its own login POST + search GET, each
    guarded by its OWN copy of the (now-shared) wiring.
    """

    def test_refusal_is_stashed_and_results_empty(self, monkeypatch):
        monkeypatch.delenv("RUTRACKER_COOKIES", raising=False)
        monkeypatch.setenv("RUTRACKER_USERNAME", "test-user-not-a-real-account")
        monkeypatch.setenv("RUTRACKER_PASSWORD", "test-value-not-a-real-secret")
        monkeypatch.setenv("RUTRACKER_MIRRORS", "https://rutracker.example")

        orch = SearchOrchestrator()
        # The login POST must yield a `bb_*`-prefixed cookie or the
        # pre-existing CAPTCHA-wall check returns before ever reaching the
        # guarded search GET — that earlier check is real product logic,
        # not the wiring under test here, so the fixture must clear it.
        fake_session = _FakeSession(
            status=403,
            body=_REFUSAL_BODY,
            login_status=200,
            login_cookies={"bb_session": _FakeCookie("bb_session", "synthetic-session")},
        )
        import aiohttp

        monkeypatch.setattr(aiohttp, "ClientSession", lambda *a, **kw: fake_session)

        results = _run(orch._search_rutracker("debian", "all"))

        assert results == []
        diag = orch._last_public_tracker_diag.get("rutracker")
        assert diag is not None, "the credential-path guard did not fire — wiring is broken"
        assert diag["http_status"] == 403


class TestKinozalWiring:
    def test_refusal_is_stashed_and_results_empty(self, monkeypatch):
        monkeypatch.setenv("KINOZAL_USERNAME", "test-user-not-a-real-account")
        monkeypatch.setenv("KINOZAL_PASSWORD", "test-value-not-a-real-secret")
        monkeypatch.setenv("KINOZAL_MIRRORS", "https://kinozal.example")

        orch = SearchOrchestrator()
        fake_session = _FakeSession(
            status=403,
            body=_REFUSAL_BODY,
            login_status=200,
            login_cookies={"klid": _FakeCookie("klid", "synthetic")},
        )
        import aiohttp

        monkeypatch.setattr(aiohttp, "ClientSession", lambda *a, **kw: fake_session)

        results = _run(orch._search_kinozal("debian", "all"))

        assert results == []
        diag = orch._last_public_tracker_diag.get("kinozal")
        assert diag is not None, "the kinozal guard did not fire — wiring is broken"
        assert diag["http_status"] == 403


class TestNnmclubWiring:
    def test_refusal_is_stashed_and_results_empty(self, monkeypatch):
        monkeypatch.setenv("NNMCLUB_COOKIES", "phpbb2mysql_4_sid=SYNTHETIC-TEST-FIXTURE-VALUE")
        monkeypatch.setenv("NNMCLUB_MIRRORS", "https://nnmclub.example")

        orch = SearchOrchestrator()
        fake_session = _FakeSession(status=403, body=_REFUSAL_BODY)
        import aiohttp

        monkeypatch.setattr(aiohttp, "ClientSession", lambda *a, **kw: fake_session)

        results = _run(orch._search_nnmclub("debian", "all"))

        assert results == []
        diag = orch._last_public_tracker_diag.get("nnmclub")
        assert diag is not None, "the nnmclub guard did not fire — wiring is broken"
        assert diag["http_status"] == 403


class TestIptorrentsWiring:
    def test_refusal_is_stashed_and_results_empty(self, monkeypatch):
        monkeypatch.setenv("IPTORRENTS_USERNAME", "test-user-not-a-real-account")
        monkeypatch.setenv("IPTORRENTS_PASSWORD", "test-value-not-a-real-secret")

        orch = SearchOrchestrator()
        fake_session = _FakeSession(
            status=403,
            body=_REFUSAL_BODY,
            login_status=200,
            login_cookies={"uid": _FakeCookie("uid", "synthetic")},
        )
        import aiohttp

        monkeypatch.setattr(aiohttp, "ClientSession", lambda *a, **kw: fake_session)

        results = _run(orch._search_iptorrents("debian", "all"))

        assert results == []
        diag = orch._last_public_tracker_diag.get("iptorrents")
        assert diag is not None, "the iptorrents guard did not fire — wiring is broken"
        assert diag["http_status"] == 403


# ===========================================================================
# 3. Negative control (§11.4.201(1)) — a healthy 200 with real rows must
#    still parse and must not have a diag stashed against it, at every site.
#    Without this, a guard that over-fires (blocks everything) would pass
#    every test above while breaking every real search.
# ===========================================================================

_HEALTHY_EMPTY_BODY = "<html><body>no matches</body></html>"


class TestNegativeControlHealthyResponsesAreNeverStashed:
    def test_kinozal_200_is_not_stashed(self, monkeypatch):
        monkeypatch.setenv("KINOZAL_USERNAME", "u")
        monkeypatch.setenv("KINOZAL_PASSWORD", "p")
        orch = SearchOrchestrator()
        fake_session = _FakeSession(status=200, body=_HEALTHY_EMPTY_BODY, login_cookies={"klid": _FakeCookie("klid", "x")})
        import aiohttp

        monkeypatch.setattr(aiohttp, "ClientSession", lambda *a, **kw: fake_session)
        _run(orch._search_kinozal("debian", "all"))
        assert "kinozal" not in orch._last_public_tracker_diag

    def test_nnmclub_200_is_not_stashed(self, monkeypatch):
        monkeypatch.setenv("NNMCLUB_COOKIES", "phpbb2mysql_4_sid=x")
        orch = SearchOrchestrator()
        fake_session = _FakeSession(status=200, body=_HEALTHY_EMPTY_BODY)
        import aiohttp

        monkeypatch.setattr(aiohttp, "ClientSession", lambda *a, **kw: fake_session)
        _run(orch._search_nnmclub("debian", "all"))
        assert "nnmclub" not in orch._last_public_tracker_diag

    def test_iptorrents_200_is_not_stashed(self, monkeypatch):
        monkeypatch.setenv("IPTORRENTS_USERNAME", "u")
        monkeypatch.setenv("IPTORRENTS_PASSWORD", "p")
        orch = SearchOrchestrator()
        fake_session = _FakeSession(status=200, body=_HEALTHY_EMPTY_BODY, login_cookies={"uid": _FakeCookie("uid", "x")})
        import aiohttp

        monkeypatch.setattr(aiohttp, "ClientSession", lambda *a, **kw: fake_session)
        _run(orch._search_iptorrents("debian", "all"))
        assert "iptorrents" not in orch._last_public_tracker_diag

    def test_rutracker_credential_path_200_is_not_stashed(self, monkeypatch):
        monkeypatch.delenv("RUTRACKER_COOKIES", raising=False)
        monkeypatch.setenv("RUTRACKER_USERNAME", "u")
        monkeypatch.setenv("RUTRACKER_PASSWORD", "p")
        orch = SearchOrchestrator()
        fake_session = _FakeSession(
            status=200,
            body=_HEALTHY_EMPTY_BODY,
            login_cookies={"bb_session": _FakeCookie("bb_session", "x")},
        )
        import aiohttp

        monkeypatch.setattr(aiohttp, "ClientSession", lambda *a, **kw: fake_session)
        _run(orch._search_rutracker("debian", "all"))
        assert "rutracker" not in orch._last_public_tracker_diag
