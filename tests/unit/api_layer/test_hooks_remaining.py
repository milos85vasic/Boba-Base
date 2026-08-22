"""
Cover remaining api/hooks.py uncovered paths — save error, log filtering, dispatch with hooks.
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SRC_PATH = _REPO_ROOT / "download-proxy" / "src"
if str(_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(_SRC_PATH))


def _purge_api_module() -> None:
    for key in [k for k in list(sys.modules) if k == "api" or k.startswith("api.")]:
        del sys.modules[key]


class TestSaveHooksError:
    """BOB-173 reconciliation (§11.4.120).

    This case used to be ``test_save_hooks_error_swallowed`` and asserted only
    that no exception escaped ``_save_hooks`` — it encoded the BOB-173 defect
    (a write failure with no channel to report it) as the contract, so the fix
    correctly broke it. It is rewritten to assert the NEW mechanism rather than
    deleted or weakened: swallowing is now the failure, propagating is the
    contract. The paired negative half below keeps it honest — the guard must
    stay silent on a healthy write.
    """

    def test_save_hooks_error_propagates(self, tmp_path, monkeypatch):
        _purge_api_module()
        import api.hooks
        import os
        import stat
        non_writable = tmp_path / "no-write"
        non_writable.mkdir()
        os.chmod(non_writable, stat.S_IRUSR | stat.S_IXUSR)
        target = non_writable / "hooks.json"

        # Control needle (§11.4.201(7)(b)): prove the directory really refuses a
        # new file before concluding anything from what _save_hooks does.
        try:
            probe = non_writable / ".probe"
            probe.write_text("x")
            probe.unlink()
            os.chmod(non_writable, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
            # SKIP-OK: BOB-173 — host cannot make an unwritable directory.
            pytest.skip("host does not enforce 0500 directory permissions")
        except OSError:
            pass

        monkeypatch.setattr(api.hooks, "HOOKS_FILE", str(target))
        try:
            with pytest.raises(api.hooks.HookPersistenceError):
                api.hooks._save_hooks([{"hook_id": "abc"}])
        finally:
            os.chmod(non_writable, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)

    def test_save_hooks_does_not_raise_on_a_healthy_write(self, tmp_path, monkeypatch):
        """Negative control (§11.4.201(1)) — failing closed ALWAYS is not a fix."""
        _purge_api_module()
        import api.hooks
        import json
        target = tmp_path / "writable" / "hooks.json"
        monkeypatch.setattr(api.hooks, "HOOKS_FILE", str(target))
        api.hooks._save_hooks([{"hook_id": "abc"}])
        assert json.loads(target.read_text()) == [{"hook_id": "abc"}]


class TestHookLogFiltering:
    @pytest.mark.asyncio
    async def test_get_execution_logs_with_hook_name(self, tmp_path, monkeypatch):
        _purge_api_module()
        import api.hooks
        fake_path = tmp_path / "hooks.json"
        monkeypatch.setattr(api.hooks, "HOOKS_FILE", str(fake_path))
        api.hooks._execution_logs.clear()
        await api.hooks.append_hook_log({"hook_name": "h1", "status": "ok"})
        await api.hooks.append_hook_log({"hook_name": "h2", "status": "ok"})
        snapshot = list(api.hooks._execution_logs)
        filtered = [line for line in snapshot if line.get("hook_name") == "h1"]
        assert len(filtered) == 1
        assert filtered[0]["hook_name"] == "h1"


class TestHooksDispatchBranch:
    @pytest.mark.asyncio
    async def test_dispatch_event_with_disabled_hook(self, tmp_path, monkeypatch):
        _purge_api_module()
        import api.hooks
        import json
        fake_path = tmp_path / "hooks.json"
        fake_path.write_text(json.dumps([
            {
                "hook_id": "h1",
                "name": "disabled-hook",
                "event": "search_complete",
                "script_path": "/bin/echo",
                "enabled": False,
                "timeout": 30,
                "environment": {},
            },
        ]))
        monkeypatch.setattr(api.hooks, "HOOKS_FILE", str(fake_path))
        api.hooks._execution_logs.clear()
        await api.hooks.dispatch_event("search_complete", {"search_id": "s1"})

    @pytest.mark.asyncio
    async def test_dispatch_event_wrong_event_type(self, tmp_path, monkeypatch):
        _purge_api_module()
        import api.hooks
        import json
        fake_path = tmp_path / "hooks.json"
        fake_path.write_text(json.dumps([
            {
                "hook_id": "h1",
                "name": "wrong-event",
                "event": "search_start",
                "script_path": "/bin/echo",
                "enabled": True,
                "timeout": 30,
                "environment": {},
            },
        ]))
        monkeypatch.setattr(api.hooks, "HOOKS_FILE", str(fake_path))
        api.hooks._execution_logs.clear()
        await api.hooks.dispatch_event("search_complete", {"search_id": "s1"})


class TestDispatchWithHook:
    @pytest.mark.asyncio
    async def test_dispatch_with_hooks(self, tmp_path, monkeypatch):
        _purge_api_module()
        import api.hooks
        import json
        fake_path = tmp_path / "hooks.json"
        fake_path.write_text(json.dumps([
            {
                "hook_id": "h1",
                "name": "dispatch-test",
                "event": "search_complete",
                "script_path": "/bin/echo",
                "enabled": True,
                "timeout": 30,
                "environment": {},
            },
        ]))
        monkeypatch.setattr(api.hooks, "HOOKS_FILE", str(fake_path))
        api.hooks._execution_logs.clear()
        await api.hooks.dispatch_event("search_complete", {"search_id": "s1"})

    @pytest.mark.asyncio
    async def test_dispatch_without_hooks(self, tmp_path, monkeypatch):
        _purge_api_module()
        import api.hooks
        fake_path = tmp_path / "hooks.json"
        fake_path.write_text("[]")
        monkeypatch.setattr(api.hooks, "HOOKS_FILE", str(fake_path))
        api.hooks._execution_logs.clear()
        await api.hooks.dispatch_event("search_start", {"search_id": "s1"})


class TestHookEndpointLogFiltering:
    def test_get_logs_with_hook_name(self, client):
        resp = client.get("/api/v1/hooks/logs?hook_name=nonexistent")
        assert resp.status_code == 200

    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        _purge_api_module()
        import api
        import api.hooks
        fake_path = tmp_path / "hooks.json"
        monkeypatch.setattr(api.hooks, "HOOKS_FILE", str(fake_path))
        return TestClient(api.app)
