"""
Additional coverage for api/hooks.py — no mocks, real I/O on temp paths.
"""

import sys
import uuid
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SRC_PATH = _REPO_ROOT / "download-proxy" / "src"
if str(_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(_SRC_PATH))


def _purge_hooks_module() -> None:
    for key in [k for k in list(sys.modules) if k == "api.hooks"]:
        del sys.modules[key]


class TestHooksInternal:
    """Direct tests for hooks internal functions — file I/O, no mocks."""

    def test_load_hooks_no_file(self, tmp_path, monkeypatch):
        _purge_hooks_module()
        import api.hooks
        fake_path = tmp_path / "hooks.json"
        monkeypatch.setattr(api.hooks, "HOOKS_FILE", str(fake_path))
        hooks = api.hooks._load_hooks()
        assert hooks == []

    def test_load_hooks_empty_list(self, tmp_path, monkeypatch):
        _purge_hooks_module()
        import api.hooks
        fake_path = tmp_path / "hooks.json"
        fake_path.write_text("[]")
        monkeypatch.setattr(api.hooks, "HOOKS_FILE", str(fake_path))
        hooks = api.hooks._load_hooks()
        assert hooks == []

    def test_load_hooks_valid(self, tmp_path, monkeypatch):
        _purge_hooks_module()
        import api.hooks
        fake_path = tmp_path / "hooks.json"
        data = [{"hook_id": "abc", "name": "test-hook", "event": "search_start", "enabled": True}]
        import json
        fake_path.write_text(json.dumps(data))
        monkeypatch.setattr(api.hooks, "HOOKS_FILE", str(fake_path))
        hooks = api.hooks._load_hooks()
        assert len(hooks) == 1
        assert hooks[0]["hook_id"] == "abc"

    def test_load_hooks_invalid_json(self, tmp_path, monkeypatch):
        _purge_hooks_module()
        import api.hooks
        fake_path = tmp_path / "hooks.json"
        fake_path.write_text("not json")
        monkeypatch.setattr(api.hooks, "HOOKS_FILE", str(fake_path))
        hooks = api.hooks._load_hooks()
        assert hooks == []

    def test_load_hooks_not_a_list(self, tmp_path, monkeypatch):
        _purge_hooks_module()
        import api.hooks
        fake_path = tmp_path / "hooks.json"
        fake_path.write_text('{"key": "value"}')
        monkeypatch.setattr(api.hooks, "HOOKS_FILE", str(fake_path))
        hooks = api.hooks._load_hooks()
        assert hooks == []

    def test_save_hooks_creates_file(self, tmp_path, monkeypatch):
        _purge_hooks_module()
        import api.hooks
        fake_path = tmp_path / "hooks.json"
        monkeypatch.setattr(api.hooks, "HOOKS_FILE", str(fake_path))
        data = [{"hook_id": "abc", "name": "saved-hook"}]
        api.hooks._save_hooks(data)
        assert fake_path.exists()
        import json
        loaded = json.loads(fake_path.read_text())
        assert len(loaded) == 1
        assert loaded[0]["hook_id"] == "abc"

    def test_save_hooks_overwrites(self, tmp_path, monkeypatch):
        _purge_hooks_module()
        import api.hooks
        fake_path = tmp_path / "hooks.json"
        monkeypatch.setattr(api.hooks, "HOOKS_FILE", str(fake_path))
        api.hooks._save_hooks([{"hook_id": "first"}])
        api.hooks._save_hooks([{"hook_id": "second"}])
        import json
        loaded = json.loads(fake_path.read_text())
        assert len(loaded) == 1
        assert loaded[0]["hook_id"] == "second"


class TestHookLog:
    """Tests for hook execution log functions — no mocks."""

    @pytest.mark.asyncio
    async def test_append_hook_log(self):
        _purge_hooks_module()
        import api.hooks
        api.hooks._execution_logs.clear()
        entry = {"hook_name": "test-hook", "status": "success"}
        await api.hooks.append_hook_log(entry)
        assert len(api.hooks._execution_logs) == 1
        assert api.hooks._execution_logs[0] == entry

    @pytest.mark.asyncio
    async def test_extend_hook_logs(self):
        _purge_hooks_module()
        import api.hooks
        api.hooks._execution_logs.clear()
        entries = [
            {"hook_name": "h1", "status": "success"},
            {"hook_name": "h2", "status": "failure"},
        ]
        await api.hooks.extend_hook_logs(entries)
        assert len(api.hooks._execution_logs) == 2

    @pytest.mark.asyncio
    async def test_log_maxlen_is_bounded(self):
        _purge_hooks_module()
        import api.hooks
        api.hooks._execution_logs.clear()
        maxlen = api.hooks._execution_logs.maxlen
        for i in range(maxlen + 100):
            await api.hooks.append_hook_log({"idx": i})
        assert len(api.hooks._execution_logs) <= maxlen


class TestValidEvents:
    def test_valid_events_list(self):
        _purge_hooks_module()
        import api.hooks
        expected = [
            "search_start",
            "search_progress",
            "search_complete",
            "download_start",
            "download_progress",
            "download_complete",
            "merge_complete",
            "validation_complete",
        ]
        assert expected == api.hooks.VALID_EVENTS

    def test_hook_uuid_is_unique(self):
        _purge_hooks_module()
        ids = {str(uuid.uuid4()) for _ in range(100)}
        assert len(ids) == 100
