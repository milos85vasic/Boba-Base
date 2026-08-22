"""§11.4.135 regression guard for BOB-173 — hook persistence failure must be REPORTED.

The defect (read from source, `download-proxy/src/api/hooks.py`):

    def _save_hooks(hooks) -> None:
        try:
            ...write...
        except Exception as e:
            logger.error(f"Failed to save hooks: {e}")

``_save_hooks`` caught EVERY exception and returned ``None``. The signature had
no failure channel, so both mutating endpoints reported success unconditionally:
``create_hook`` returned HTTP 200 with a ``hook_id`` for a hook that was never
written, and ``delete_hook`` returned ``{"message": "Hook deleted"}`` for a hook
still sitting in the file. Both reported the OPPOSITE of what happened, with
only an unwatched log line as evidence.

This is the §11.4.252 shape: the path combines MUTATION of a shared resource (a
filesystem write) with an EXTERNAL SIDE EFFECT (a hook is an outbound call the
system will or will not make later), so it must FAIL CLOSED. At the product
layer it is also a §11.4.201(6) FALSE-NULL — a successful write and a swallowed
failure were indistinguishable to the caller.

Not hypothetical. During the BOB-135 investigation the real ``EACCES`` on
``/config`` surfaced ONLY as an ERROR log line from ``hooks.py:102`` while the
endpoint kept returning 200, so the failing test died on its own
``assert 0 == 1`` with the actual cause visible nowhere in the verdict. That
much is recorded in BOB-135's evidence; how much investigation time it cost is
not, and is not claimed here (§11.4.6).

ASSERTION LAYER (§11.4.226 / §11.4.262): every assertion below is on the
USER-OBSERVABLE outcome — the HTTP status, the response body, and what a
subsequent ``GET /api/v1/hooks`` lists. Nothing here asserts on a log line; a
log-only assertion would re-certify the exact bluff the defect consists of.

CONTROL NEEDLE (§11.4.201(7)(b)): unwritability is never assumed, it is PROVEN
by a real probe before any assertion runs, and there are TWO needles because
there are two different operations. The first draft of this guard had ONE — it
sealed the directory and probed by creating a new file — and the delete tests
"went red" while the delete write had in fact SUCCEEDED: a read-only directory
does not stop an existing file being rewritten, because directory write
permission governs creating and unlinking entries, not modifying a file already
in them. That is a §11.4.199 false reproduction — a repro that never reaches the
precondition it claims to test proves nothing, and the red it produces is worth
nothing. ``seal_for_create``/``_create_is_refused`` cover the create path (new
file, needs the DIRECTORY); ``seal_for_rewrite``/``_rewrite_is_refused`` cover
the delete path (existing file, needs the FILE). Each needle performs the same
kind of write as the code it certifies. If this host can produce neither, the
test SKIPs loudly rather than passing vacuously.

HONEST NOTE on one member (§11.4.6): ``test_phantom_hook_is_not_listed_after_
failed_create`` passes against the BROKEN code too, because the hook genuinely
never reached the file. It does not capture the escape by itself and is not
claimed to — it asserts the REALITY half ("the hook does not exist") that makes
the other half ("the API said 200") a lie. The status and hook_id assertions are
the ones that captured the defect; all five were observed failing pre-fix.

NEGATIVE CONTROL (§11.4.201(1)): ``TestHappyPathStillWorks`` proves the fix did
not simply make every write fail. A guard that refuses the healthy case is a
FAIL-bluff exactly as a guard that passes the broken case is a PASS-bluff.

BOB-135 TRAP: ``monkeypatch.setattr`` is called with the MODULE OBJECT
(``api.hooks``), never the dotted string ``"api.hooks.HOOKS_FILE"``. The string
form walks the parent package ATTRIBUTE while ``api.app``'s router came from the
``sys.modules`` entry, and when those two diverge the patch lands on a module the
app does not use. ``_assert_single_hooks_module`` asserts they have not diverged,
so this file can never silently patch the wrong object.
"""

import json
import os
import stat
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SRC_PATH = _REPO_ROOT / "download-proxy" / "src"
if str(_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(_SRC_PATH))

_RO_DIR_MODE = stat.S_IRUSR | stat.S_IXUSR          # r-x------ : readable, not writable
_RW_DIR_MODE = stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR


def _purge_api_module() -> None:
    for key in [k for k in list(sys.modules) if k == "api" or k.startswith("api.")]:
        del sys.modules[key]


def _assert_single_hooks_module(hooks_mod) -> None:
    """Guard the BOB-135 two-live-modules split before trusting any patch."""
    assert sys.modules["api.hooks"] is hooks_mod
    assert sys.modules["api"].hooks is hooks_mod


def _create_is_refused(directory: Path) -> bool:
    """Control needle for the CREATE path: can a NEW file be made here?

    Matches the load-bearing operation exactly (§11.4.201(7)(b)) — ``create_hook``
    writes a hooks.json that does not exist yet, which needs write permission on
    the DIRECTORY.
    """
    probe = directory / ".boba173-probe"
    try:
        probe.write_text("x")
    except OSError:
        return True
    probe.unlink()
    return False


def _rewrite_is_refused(target: Path) -> bool:
    """Control needle for the DELETE path: can an EXISTING file be rewritten?

    A DIFFERENT needle on purpose. A read-only directory does NOT stop an
    existing file being rewritten — directory write permission governs creating
    and unlinking entries, not modifying a file already in them. The first draft
    of this guard sealed only the directory and the delete write sailed straight
    through, so the "RED" it produced was a §11.4.199 false reproduction: the
    repro never reached the precondition it claimed to test. The permission that
    actually matters here is on the FILE.
    """
    try:
        with open(target, "a"):
            pass
    except OSError:
        return True
    return False


class _HooksHarness:
    """A TestClient plus the knobs to seal/unseal the hooks-file directory."""

    def __init__(self, client: TestClient, store_dir: Path, hooks_file: Path, scripts_dir: Path):
        self.client = client
        self.store_dir = store_dir
        self.hooks_file = hooks_file
        self.scripts_dir = scripts_dir

    def seal_for_create(self) -> None:
        """Block CREATION of hooks.json. Proven, or the test skips loudly."""
        assert not self.hooks_file.exists(), (
            "seal_for_create seals the DIRECTORY, which does not block rewriting "
            "an existing file — use seal_for_rewrite when hooks.json already exists"
        )
        os.chmod(self.store_dir, _RO_DIR_MODE)
        if not _create_is_refused(self.store_dir):
            os.chmod(self.store_dir, _RW_DIR_MODE)
            # SKIP-OK: BOB-173 — cannot construct an unwritable dir on this host
            # (root / permissive fs). Refusing to run beats a vacuous green.
            pytest.skip(
                "host cannot refuse file creation in a 0500 directory "
                "(euid=%d) — the instrument would be blind" % os.geteuid()
            )

    def seal_for_rewrite(self) -> None:
        """Block REWRITING an existing hooks.json. Proven, or the test skips."""
        assert self.hooks_file.exists(), "seal_for_rewrite needs an existing hooks.json"
        os.chmod(self.hooks_file, stat.S_IRUSR)
        if not _rewrite_is_refused(self.hooks_file):
            os.chmod(self.hooks_file, stat.S_IRUSR | stat.S_IWUSR)
            # SKIP-OK: BOB-173 — see seal_for_create.
            pytest.skip(
                "host cannot refuse a rewrite of a 0400 file "
                "(euid=%d) — the instrument would be blind" % os.geteuid()
            )

    def unseal(self) -> None:
        os.chmod(self.store_dir, _RW_DIR_MODE)
        if self.hooks_file.exists():
            os.chmod(self.hooks_file, stat.S_IRUSR | stat.S_IWUSR)

    def make_script(self, name: str = "hook.sh") -> Path:
        script = self.scripts_dir / name
        script.write_text("#!/bin/sh\necho ok\n")
        script.chmod(0o755)
        return script

    def create_payload(self, name: str = "bob173-hook") -> dict:
        return {
            "name": name,
            "event": "search_start",
            "script_path": str(self.make_script()),
        }

    def listed_hook_ids(self) -> list[str]:
        resp = self.client.get("/api/v1/hooks")
        assert resp.status_code == 200, resp.text
        return [h["hook_id"] for h in resp.json()["hooks"]]


@pytest.fixture
def harness(tmp_path, monkeypatch):
    monkeypatch.delenv("BOBA_API_TOKEN", raising=False)

    store_dir = tmp_path / "hooks-store"
    store_dir.mkdir()
    hooks_file = store_dir / "hooks.json"

    scripts_dir = tmp_path / "hooks"
    scripts_dir.mkdir()
    monkeypatch.setenv("BOBA_HOOKS_DIR", str(scripts_dir))

    _purge_api_module()
    import api
    import api.hooks

    _assert_single_hooks_module(api.hooks)
    monkeypatch.setattr(api.hooks, "HOOKS_FILE", str(hooks_file))

    h = _HooksHarness(TestClient(api.app), store_dir, hooks_file, scripts_dir)
    try:
        yield h
    finally:
        # Always restore write permission or tmp_path teardown fails.
        os.chmod(store_dir, _RW_DIR_MODE)
        if hooks_file.exists():
            os.chmod(hooks_file, stat.S_IRUSR | stat.S_IWUSR)


class TestCreateReportsPersistenceFailure:
    """POST must not hand back an id for a hook that was never written."""

    def test_create_returns_error_status_when_write_fails(self, harness):
        payload = harness.create_payload()
        harness.seal_for_create()

        resp = harness.client.post("/api/v1/hooks", json=payload)

        assert resp.status_code >= 500, (
            "create_hook returned %d for a hook whose write FAILED — the API told "
            "the user their webhook exists when it does not (BOB-173)" % resp.status_code
        )

    def test_create_does_not_return_a_hook_id_when_write_fails(self, harness):
        payload = harness.create_payload()
        harness.seal_for_create()

        resp = harness.client.post("/api/v1/hooks", json=payload)

        assert "hook_id" not in resp.json(), (
            "create_hook handed back a hook_id for a hook that was never persisted "
            "— an id for a thing that does not exist is the same lie in a smaller box"
        )

    def test_phantom_hook_is_not_listed_after_failed_create(self, harness):
        payload = harness.create_payload()
        harness.seal_for_create()
        harness.client.post("/api/v1/hooks", json=payload)
        harness.unseal()

        assert harness.listed_hook_ids() == [], (
            "a hook the API reported as created must not appear, and the API must "
            "not have reported it as created"
        )


class TestDeleteReportsPersistenceFailure:
    """DELETE must not claim removal of a hook still in the file."""

    def _seed_one_hook(self, harness) -> str:
        hook_id = "bob173-seeded-hook"
        harness.hooks_file.write_text(
            json.dumps(
                [
                    {
                        "hook_id": hook_id,
                        "name": "seeded",
                        "event": "search_start",
                        "script_path": str(harness.make_script()),
                        "enabled": True,
                        "timeout": 30,
                        "environment": {},
                        "created_at": "2026-01-01T00:00:00+00:00",
                    }
                ]
            )
        )
        return hook_id

    def test_delete_returns_error_status_when_write_fails(self, harness):
        hook_id = self._seed_one_hook(harness)
        harness.seal_for_rewrite()

        resp = harness.client.delete(f"/api/v1/hooks/{hook_id}")

        assert resp.status_code >= 500, (
            "delete_hook returned %d for a hook that is STILL in the file — it will "
            "keep firing after restart while the API said it was gone (BOB-173)"
            % resp.status_code
        )

    def test_delete_does_not_claim_success_when_write_fails(self, harness):
        hook_id = self._seed_one_hook(harness)
        harness.seal_for_rewrite()

        resp = harness.client.delete(f"/api/v1/hooks/{hook_id}")

        assert resp.json().get("message") != "Hook deleted", (
            "delete_hook reported 'Hook deleted' for a hook that was not deleted"
        )

    def test_hook_survives_a_failed_delete_and_the_api_admits_it(self, harness):
        """The two halves together: the hook is still there AND the API said so."""
        hook_id = self._seed_one_hook(harness)
        harness.seal_for_rewrite()
        resp = harness.client.delete(f"/api/v1/hooks/{hook_id}")
        harness.unseal()

        still_there = hook_id in harness.listed_hook_ids()
        assert still_there, "precondition: the failed write must have left the hook in place"
        assert resp.status_code >= 500, (
            "the hook survived the delete, so a 2xx response is a false report of "
            "removal — the user believes a hook that will still fire is gone"
        )


class TestHappyPathStillWorks:
    """NEGATIVE CONTROL (§11.4.201(1)) — a fix that fails closed ALWAYS is not a fix."""

    def test_create_succeeds_and_persists_on_a_writable_store(self, harness):
        resp = harness.client.post("/api/v1/hooks", json=harness.create_payload())

        assert resp.status_code == 200, resp.text
        hook_id = resp.json()["hook_id"]
        assert hook_id

        # User-observable: it is listed, AND it really reached the file.
        assert hook_id in harness.listed_hook_ids()
        on_disk = json.loads(harness.hooks_file.read_text())
        assert [h["hook_id"] for h in on_disk] == [hook_id]

    def test_delete_succeeds_and_persists_on_a_writable_store(self, harness):
        created = harness.client.post("/api/v1/hooks", json=harness.create_payload())
        hook_id = created.json()["hook_id"]

        resp = harness.client.delete(f"/api/v1/hooks/{hook_id}")

        assert resp.status_code == 200, resp.text
        assert resp.json()["message"] == "Hook deleted"
        assert harness.listed_hook_ids() == []
        assert json.loads(harness.hooks_file.read_text()) == []

    def test_missing_hook_still_404s_not_500s(self, harness):
        """A persistence guard must not swallow the ordinary not-found path."""
        resp = harness.client.delete("/api/v1/hooks/no-such-hook")
        assert resp.status_code == 404, resp.text
