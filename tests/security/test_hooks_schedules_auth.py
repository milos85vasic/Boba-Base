"""Security hardening for the hooks + schedules mutating routes.

Three fixes, all BACKWARD-COMPATIBLE (the no-auth contract is preserved when
``BOBA_API_TOKEN`` is unset — current operator state):

RW-01 (Fix 1) — sandbox hook script execution.
    ``merge_service/hooks.py`` runs ``subprocess.run([hook.script_path], …)`` on
    event fire. An unauth caller could register a hook whose ``script_path`` is
    ANY existing in-container executable. We now restrict ``script_path`` to an
    ALLOWLISTED directory (``BOBA_HOOKS_DIR``, default
    ``/config/download-proxy/hooks``). Registration rejects (400) any path that
    does not realpath-resolve inside the allowlisted dir; execution refuses the
    same at dispatch time (defence in depth, no symlink escape).

RW-01/RW-02 (Fix 2) — token-gate the mutating hooks + schedules routes.
    ``POST/DELETE /api/v1/hooks`` and ``POST/DELETE /api/v1/schedules`` now carry
    ``Depends(require_api_token)`` (imported from ``api.routes``). GET (read)
    routes stay open. The gate is a NO-OP when ``BOBA_API_TOKEN`` is unset, so the
    operator's current contract is unchanged; it activates when a token is set.

RW-02 (Fix 3) — loud startup warning when the write surface is open.
    On startup, if ``BOBA_API_TOKEN`` is unset, the app logs a clear WARNING that
    the mutating endpoints are UNAUTHENTICATED.

§11.4.115 RED-first: against the pre-fix code there is NO allowlist and NO auth on
hooks/schedules — so (a) an out-of-allowlist registration returns 200 (NOT 400),
(b) the no-token POST/DELETE return their success/404 codes (NOT 401), and (c) no
warning is logged. Every assertion FAILs RED, then GREEN after the fixes.

§11.4.107 (anti-bluff): assertions inspect user-observable outcomes — the HTTP
status code, the response body, and the captured log record — never "no error".

§11.4.10: the token is a SYNTHETIC per-run uuid value, never a real secret,
never logged.

RD2-23 (§11.4.135 permanent regression guard): ``TestMutatingRoutesTokenGate``
below (parametrized over ``_MUTATING``, which includes
``PATCH /api/v1/schedules/{id}`` and ``PUT /api/v1/theme`` since RD2-22) IS
the standing regression guard for the RD2-22 fix -- no separate/duplicate
guard test was authored. Polarity-switch proof (§11.4.115), captured in this
session: with ``Depends(require_api_token)`` commented out of
``scheduler.py::update_schedule`` and ``routes.py::put_theme`` (reverting
RD2-22 to its pre-fix state), ``test_no_token_is_401_when_token_set`` and
``test_wrong_token_is_401_when_token_set`` for BOTH of those two
parametrize ids go RED (4 failures, each "expected 401 ... got 200" -- the
right reason, auth bypassed, not a script-bug crash). Restoring
``Depends(require_api_token)`` returns the full 31/31 suite to GREEN with
zero diff against the fixed source. This proves the guard would catch a
reversion of the RD2-22 fix.
"""

import logging
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC_PATH = _REPO_ROOT / "download-proxy" / "src"
if str(_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(_SRC_PATH))

_TOKEN = f"test-token-{uuid.uuid4()}"


def _purge_api_module() -> None:
    for key in [k for k in list(sys.modules) if k == "api" or k.startswith("api.")]:
        del sys.modules[key]


@pytest.fixture(autouse=True)
def _restore_api_module():
    yield
    _purge_api_module()


def _make_scheduler():
    """A scheduler test-double whose mutating ops succeed so the route handler
    runs to a 2xx — proving the request reached the handler (NOT short-circuited
    at 401)."""
    sched = MagicMock()
    created = MagicMock()
    created.id = "sched-1"
    created.name = "nightly"
    created.query = "ubuntu"
    created.interval_minutes = 60
    created.enabled = True
    created.status = MagicMock(value="active")
    created.next_run = None
    sched.add_scheduled_search.return_value = created

    # GA-11: a JSON-serializable double for get_scheduled_search, so
    # PATCH /schedules/{id}'s `{"id": search.id, "name": search.name,
    # "enabled": search.enabled}` response body encodes cleanly instead of
    # crashing on an un-serialized nested MagicMock.
    found = MagicMock()
    found.id = "sched-1"
    found.name = "nightly"
    found.enabled = True
    sched.get_scheduled_search.return_value = found

    async def _save():
        return None

    sched.save.side_effect = _save
    sched.remove_scheduled_search.return_value = True
    return sched


@pytest.fixture
def client_factory(tmp_path, monkeypatch):
    """Build a TestClient with: HOOKS_FILE redirected to tmp, BOBA_HOOKS_DIR set
    to a real tmp allowlist dir, THEME_STATE_PATH redirected to tmp (the real
    default `/config/merge-service/theme.json` is not writable outside a
    container and would crash `PUT /theme` with an unrelated PermissionError,
    masking the auth-gate signal), and app.state.scheduler swapped for a
    double so schedule routes never touch a live scheduler loop."""
    created_clients = []
    hooks_dir = tmp_path / "hooks"
    hooks_dir.mkdir()
    monkeypatch.setenv("BOBA_HOOKS_DIR", str(hooks_dir))
    monkeypatch.setenv("THEME_STATE_PATH", str(tmp_path / "theme.json"))

    def _build():
        _purge_api_module()
        import api
        import api.hooks

        monkeypatch.setattr(api.hooks, "HOOKS_FILE", str(tmp_path / "hooks.json"))
        client = TestClient(api.app)
        client.__enter__()  # run lifespan so app.state.scheduler exists
        client.app.state.scheduler = _make_scheduler()
        created_clients.append(client)
        return client, hooks_dir

    yield _build

    for c in created_clients:
        try:
            c.__exit__(None, None, None)
        except Exception:
            pass


def _allowed_script(hooks_dir: Path) -> str:
    p = hooks_dir / "ok.sh"
    p.write_text("#!/bin/sh\necho ok\n")
    p.chmod(0o755)
    return str(p)


# ---------------------------------------------------------------------------
# Fix 1 (RW-01) — hook script_path allowlist at REGISTRATION
# ---------------------------------------------------------------------------


class TestHookScriptPathAllowlist:
    def test_script_inside_allowlist_is_accepted(self, client_factory, monkeypatch):
        monkeypatch.delenv("BOBA_API_TOKEN", raising=False)
        c, hooks_dir = client_factory()
        resp = c.post(
            "/api/v1/hooks",
            json={"name": "h-ok", "event": "search_start", "script_path": _allowed_script(hooks_dir)},
        )
        assert resp.status_code == 200, f"in-allowlist script must be accepted, got {resp.status_code}: {resp.text}"

    def test_script_outside_allowlist_is_rejected(self, client_factory, monkeypatch):
        monkeypatch.delenv("BOBA_API_TOKEN", raising=False)
        c, _ = client_factory()
        resp = c.post(
            "/api/v1/hooks",
            json={"name": "h-evil", "event": "search_start", "script_path": "/bin/sh"},
        )
        assert resp.status_code == 400, (
            f"out-of-allowlist script (/bin/sh) must be rejected with 400, got {resp.status_code}: {resp.text}"
        )

    def test_symlink_escape_outside_allowlist_is_rejected(self, client_factory, monkeypatch, tmp_path):
        """A symlink INSIDE the allowlist dir pointing OUTSIDE it must not slip
        through a naive prefix check — realpath resolution catches it."""
        monkeypatch.delenv("BOBA_API_TOKEN", raising=False)
        c, hooks_dir = client_factory()
        outside = tmp_path / "outside_target"
        outside.write_text("#!/bin/sh\necho pwned\n")
        link = hooks_dir / "escape.sh"
        link.symlink_to(outside)
        resp = c.post(
            "/api/v1/hooks",
            json={"name": "h-symlink", "event": "search_start", "script_path": str(link)},
        )
        assert resp.status_code == 400, (
            f"symlink escaping the allowlist must be rejected with 400, got {resp.status_code}: {resp.text}"
        )


# ---------------------------------------------------------------------------
# Fix 2 (RW-01/RW-02) — token gate on mutating hooks + schedules routes
# ---------------------------------------------------------------------------


def _post_hook(c, headers, hooks_dir):
    return c.post(
        "/api/v1/hooks",
        json={"name": "h1", "event": "search_start", "script_path": _allowed_script(hooks_dir)},
        headers=headers,
    )


def _delete_hook(c, headers, _hooks_dir):
    return c.delete("/api/v1/hooks/does-not-exist", headers=headers)


def _post_schedule(c, headers, _hooks_dir):
    return c.post("/api/v1/schedules", json={"name": "s1", "query": "ubuntu"}, headers=headers)


def _delete_schedule(c, headers, _hooks_dir):
    return c.delete("/api/v1/schedules/some-id", headers=headers)


def _patch_schedule(c, headers, _hooks_dir):
    return c.patch("/api/v1/schedules/some-id", json={"enabled": False}, headers=headers)


def _put_theme(c, headers, _hooks_dir):
    return c.put("/api/v1/theme", json={"paletteId": "darcula", "mode": "dark"}, headers=headers)


_MUTATING = [
    ("POST /api/v1/hooks", _post_hook),
    ("DELETE /api/v1/hooks/{id}", _delete_hook),
    ("POST /api/v1/schedules", _post_schedule),
    ("DELETE /api/v1/schedules/{id}", _delete_schedule),
    # GA-11 (docs/GOVERNANCE_AUDIT_2026-08-07.md): RW-02's original _MUTATING
    # enumeration never included these two — the fix and its test were scoped
    # incompletely together, leaving both routes open even with a token set.
    ("PATCH /api/v1/schedules/{id}", _patch_schedule),
    ("PUT /api/v1/theme", _put_theme),
]


@pytest.mark.parametrize("name,call", _MUTATING, ids=[e[0] for e in _MUTATING])
class TestMutatingRoutesTokenGate:
    def test_no_token_is_401_when_token_set(self, name, call, client_factory, monkeypatch):
        monkeypatch.setenv("BOBA_API_TOKEN", _TOKEN)
        c, hooks_dir = client_factory()
        resp = call(c, {}, hooks_dir)
        assert resp.status_code == 401, f"{name}: expected 401 w/o token, got {resp.status_code}: {resp.text}"

    def test_wrong_token_is_401_when_token_set(self, name, call, client_factory, monkeypatch):
        monkeypatch.setenv("BOBA_API_TOKEN", _TOKEN)
        c, hooks_dir = client_factory()
        resp = call(c, {"Authorization": "Bearer nope"}, hooks_dir)
        assert resp.status_code == 401, f"{name}: expected 401 on wrong token, got {resp.status_code}"

    def test_correct_token_not_401_when_token_set(self, name, call, client_factory, monkeypatch):
        monkeypatch.setenv("BOBA_API_TOKEN", _TOKEN)
        c, hooks_dir = client_factory()
        resp = call(c, {"X-Boba-Token": _TOKEN}, hooks_dir)
        assert resp.status_code != 401, f"{name}: correct token must reach handler, got 401: {resp.text}"


@pytest.mark.parametrize("name,call", _MUTATING, ids=[e[0] for e in _MUTATING])
class TestMutatingRoutesOpenWhenUnset:
    """Regression guard (§11.4.122 / BACKWARD-COMPAT): env UNSET -> OPEN."""

    def test_no_token_not_401_when_unset(self, name, call, client_factory, monkeypatch):
        monkeypatch.delenv("BOBA_API_TOKEN", raising=False)
        c, hooks_dir = client_factory()
        resp = call(c, {}, hooks_dir)
        assert resp.status_code != 401, f"{name}: default (env-unset) path must stay OPEN, got 401: {resp.text}"


class TestReadRoutesStayOpen:
    """GET (read) routes are NOT gated even with a token set."""

    def test_get_hooks_open_with_token_set(self, client_factory, monkeypatch):
        monkeypatch.setenv("BOBA_API_TOKEN", _TOKEN)
        c, _ = client_factory()
        resp = c.get("/api/v1/hooks")
        assert resp.status_code == 200, f"GET /hooks must stay open, got {resp.status_code}: {resp.text}"

    def test_get_schedules_open_with_token_set(self, client_factory, monkeypatch):
        monkeypatch.setenv("BOBA_API_TOKEN", _TOKEN)
        c, _ = client_factory()
        c.app.state.scheduler.get_all_scheduled_searches.return_value = []
        resp = c.get("/api/v1/schedules")
        assert resp.status_code == 200, f"GET /schedules must stay open, got {resp.status_code}: {resp.text}"


# ---------------------------------------------------------------------------
# Fix 3 (RW-02) — loud startup warning when the write surface is open
# ---------------------------------------------------------------------------


class TestStartupWarning:
    def test_warning_logged_when_token_unset(self, client_factory, monkeypatch, caplog):
        monkeypatch.delenv("BOBA_API_TOKEN", raising=False)
        with caplog.at_level(logging.WARNING):
            client_factory()  # builds + enters lifespan
        joined = " ".join(r.getMessage() for r in caplog.records).lower()
        assert "boba_api_token" in joined, f"startup warning must name BOBA_API_TOKEN; got: {joined!r}"
        assert "unauthenticated" in joined, f"startup warning must say UNAUTHENTICATED; got: {joined!r}"

    def test_no_warning_when_token_set(self, client_factory, monkeypatch, caplog):
        monkeypatch.setenv("BOBA_API_TOKEN", _TOKEN)
        with caplog.at_level(logging.WARNING):
            client_factory()
        joined = " ".join(r.getMessage() for r in caplog.records).lower()
        assert "unauthenticated" not in joined, (
            f"no open-write-surface warning expected when token set; got: {joined!r}"
        )
