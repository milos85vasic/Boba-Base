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
    def test_save_hooks_error_swallowed(self, tmp_path, monkeypatch):
        _purge_api_module()
        import api.hooks
        import os
        import stat
        non_writable = tmp_path / "no-write"
        non_writable.mkdir()
        os.chmod(non_writable, stat.S_IRUSR | stat.S_IXUSR)
        monkeypatch.setattr(api.hooks, "HOOKS_FILE", str(non_writable / "hooks.json"))
        try:
            api.hooks._save_hooks([{"hook_id": "abc"}])
        finally:
            os.chmod(non_writable, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)


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
