"""BOB-235 — kinozal transport failure is reported as an empty result set.

FORENSIC ANCHOR (live, 2026-09-23 — docs/qa/BOB-235/investigation_20260923.md).
The live credential guard
``tests/integration/test_tracker_auth_live.py::test_private_tracker_credentials_authenticate[kinozal]``
failed with ``authenticated=False status='empty' error=''``. The container log
for the same search read::

    ERROR - Kinozal search error: Cannot connect to host kinozal.tv:443
            ssl:default [Connect call failed ('127.0.0.1', 443)]

i.e. the kinozal leg never reached the tracker (``kinozal.tv``'s public A
record is ``127.0.0.1``), yet the user-facing chip said "empty, no error" —
the §11.4.201(6) FALSE-NULL that BOB-172/BOB-178 closed for the HTTP-status
legs, still open on the transport-exception leg: ``_search_kinozal``'s
``except Exception`` only logs, stashes NO diagnostic, and returns ``[]``.

THE FIX mirrors the orchestrator's own exception dialect (``_search_one``:
``error_type = e.__class__.__name__``, ``error = str(e)``) by stashing that
diagnostic on ``self._last_public_tracker_diag["kinozal"]`` — no new
vocabulary is minted (§11.4.28), and no classification is guessed (a
"Cannot connect ... ssl:default" string would be MIS-read as a TLS failure by
``_classify_plugin_stderr`` because it contains ``ssl:``).

NEGATIVE CONTROL (§11.4.201(1)): a healthy kinozal round-trip stashes NO
diagnostic — a fix that stashed on every call would make a working tracker
report a spurious error.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_MS_PATH = os.path.join(_REPO_ROOT, "download-proxy", "src", "merge_service")

sys.modules.setdefault("merge_service", type(sys)("merge_service"))
sys.modules["merge_service"].__path__ = [_MS_PATH]

_search_spec = importlib.util.spec_from_file_location("merge_service.search", os.path.join(_MS_PATH, "search.py"))
_search_mod = importlib.util.module_from_spec(_search_spec)
sys.modules["merge_service.search"] = _search_mod
_search_spec.loader.exec_module(_search_mod)

SearchOrchestrator = _search_mod.SearchOrchestrator

_CONNECT_MSG = "Cannot connect to host kinozal.example:443 ssl:default [Connect call failed ('127.0.0.1', 443)]"


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

    async def read(self, *a, **kw) -> bytes:
        return self._body.encode("cp1251", "ignore")

    async def __aenter__(self) -> _FakeResp:
        return self

    async def __aexit__(self, *exc) -> bool:
        return False


class _RaisingCtx:
    """An ``async with`` target that raises on entry, like aiohttp does on connect failure."""

    def __init__(self, exc: BaseException) -> None:
        self._exc = exc

    async def __aenter__(self):
        raise self._exc

    async def __aexit__(self, *exc) -> bool:
        return False


class _FakeSession:
    def __init__(self, *, post_exc: BaseException | None = None, body: str = "") -> None:
        self._post_exc = post_exc
        self._body = body

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *exc) -> bool:
        return False

    def post(self, *a, **kw):
        if self._post_exc is not None:
            return _RaisingCtx(self._post_exc)
        return _FakeResp(302, "", cookies={"uid": _FakeCookie("uid", "1")})

    def get(self, *a, **kw):
        return _FakeResp(200, self._body)


def _set_env(monkeypatch) -> None:
    monkeypatch.setenv("KINOZAL_USERNAME", "test-user-not-a-real-account")
    monkeypatch.setenv("KINOZAL_PASSWORD", "test-value-not-a-real-secret")
    monkeypatch.setenv("KINOZAL_MIRRORS", "https://kinozal.example")


def _patch_session(monkeypatch, session: _FakeSession) -> None:
    import aiohttp

    monkeypatch.setattr(aiohttp, "ClientSession", lambda *a, **kw: session)


class TestKinozalTransportFailureSetsDiagnostic:
    def test_connect_failure_stashes_non_empty_diagnostic(self, monkeypatch):
        import aiohttp

        _set_env(monkeypatch)
        orch = SearchOrchestrator()
        _patch_session(monkeypatch, _FakeSession(post_exc=aiohttp.ClientConnectionError(_CONNECT_MSG)))

        results = asyncio.run(orch._search_kinozal("ubuntu", "all"))

        assert results == []
        diag = orch._last_public_tracker_diag.get("kinozal")
        assert diag is not None, "a kinozal transport failure must not be reported as a silent empty result (BOB-235)"
        assert diag.get("error_type") == "ClientConnectionError"
        assert "Cannot connect to host kinozal.example:443" in (diag.get("error") or "")

    def test_diagnostic_is_not_misclassified_as_tls(self, monkeypatch):
        """The message contains ``ssl:`` — the stderr classifier would call it a TLS failure."""
        import aiohttp

        _set_env(monkeypatch)
        orch = SearchOrchestrator()
        _patch_session(monkeypatch, _FakeSession(post_exc=aiohttp.ClientConnectionError(_CONNECT_MSG)))

        asyncio.run(orch._search_kinozal("ubuntu", "all"))

        assert orch._last_public_tracker_diag["kinozal"]["error_type"] != "tls_failure"


class TestNegativeControlHealthyRoundTripStashesNothing:
    def test_healthy_round_trip_has_no_diagnostic(self, monkeypatch):
        _set_env(monkeypatch)
        orch = SearchOrchestrator()
        _patch_session(monkeypatch, _FakeSession(body="<html>no rows</html>"))

        asyncio.run(orch._search_kinozal("ubuntu", "all"))

        assert "kinozal" not in orch._last_public_tracker_diag
        assert "kinozal" in orch._tracker_sessions
