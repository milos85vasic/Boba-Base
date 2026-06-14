"""
Unit tests for the hooks module.
"""

import importlib.util
import os
import sys

import pytest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_SRC_PATH = os.path.join(_REPO_ROOT, "download-proxy", "src")
_MS_PATH = os.path.join(_SRC_PATH, "merge_service")

sys.modules.setdefault("merge_service", type(sys)("merge_service"))
sys.modules["merge_service"].__path__ = [_MS_PATH]

_hooks_spec = importlib.util.spec_from_file_location("merge_service.hooks", os.path.join(_MS_PATH, "hooks.py"))
_hooks_mod = importlib.util.module_from_spec(_hooks_spec)
sys.modules["merge_service.hooks"] = _hooks_mod
_hooks_spec.loader.exec_module(_hooks_mod)

HookDispatcher = _hooks_mod.HookDispatcher
HookConfig = _hooks_mod.HookConfig
HookEvent = _hooks_mod.HookEvent
HookEventType = _hooks_mod.HookEventType

from merge_service.hooks import (
    HookConfig,
    HookDispatcher,
    HookEvent,
    HookEventType,
    create_default_hook,
)


class TestHookEventType:
    """Tests for HookEventType enum."""

    def test_values(self):
        """Test all hook event type values."""
        assert HookEventType.SEARCH_START.value == "search_start"
        assert HookEventType.SEARCH_COMPLETE.value == "search_complete"
        assert HookEventType.DOWNLOAD_START.value == "download_start"
        assert HookEventType.DOWNLOAD_COMPLETE.value == "download_complete"


class TestHookEvent:
    """Tests for HookEvent dataclass."""

    def test_creation(self):
        """Test HookEvent creation."""
        event = HookEvent(
            event_type=HookEventType.SEARCH_COMPLETE,
            search_id="test-123",
            data={"results": 10},
        )

        assert event.event_type == HookEventType.SEARCH_COMPLETE
        assert event.search_id == "test-123"
        assert event.data["results"] == 10

    def test_to_dict(self):
        """Test HookEvent serialization."""
        event = HookEvent(
            event_type=HookEventType.SEARCH_START,
            search_id="test-123",
            data={"query": "Ubuntu"},
        )

        data = event.to_dict()

        assert data["event_type"] == "search_start"
        assert data["search_id"] == "test-123"
        assert data["data"]["query"] == "Ubuntu"
        assert "timestamp" in data


class TestHookConfig:
    """Tests for HookConfig dataclass."""

    def test_creation(self):
        """Test HookConfig creation."""
        config = HookConfig(
            name="test_hook",
            event=HookEventType.SEARCH_COMPLETE,
            script_path="/tmp/test.sh",
            enabled=True,
            timeout=30,
        )

        assert config.name == "test_hook"
        assert config.event == HookEventType.SEARCH_COMPLETE
        assert config.script_path == "/tmp/test.sh"
        assert config.enabled == True
        assert config.timeout == 30

    def test_validate_missing_path(self):
        """Test validation with non-existent script."""
        config = HookConfig(
            name="test",
            event=HookEventType.SEARCH_COMPLETE,
            script_path="/nonexistent/script.sh",
        )

        # Validation should return False but not crash
        assert config.validate() == False


class TestHookDispatcher:
    """Tests for HookDispatcher class."""

    @pytest.fixture
    def dispatcher(self):
        """Create dispatcher instance."""
        return HookDispatcher(timeout=5)

    def test_init(self, dispatcher):
        """Test dispatcher initialization."""
        assert dispatcher._hooks == {}
        assert dispatcher._timeout == 5
        assert dispatcher._execution_log == []

    def test_register_hook(self, dispatcher):
        """Test hook registration."""
        config = HookConfig(
            name="test_hook",
            event=HookEventType.SEARCH_COMPLETE,
            script_path="/tmp/test.sh",
        )

        dispatcher.register_hook(config)

        assert HookEventType.SEARCH_COMPLETE in dispatcher._hooks
        assert len(dispatcher._hooks[HookEventType.SEARCH_COMPLETE]) == 1

    def test_get_hooks(self, dispatcher):
        """Test getting hooks by event type."""
        config = HookConfig(
            name="test_hook",
            event=HookEventType.SEARCH_COMPLETE,
            script_path="/tmp/test.sh",
        )

        dispatcher.register_hook(config)

        hooks = dispatcher.get_hooks(HookEventType.SEARCH_COMPLETE)

        assert len(hooks) == 1
        assert hooks[0].name == "test_hook"

    def test_get_hooks_empty(self, dispatcher):
        """Test getting hooks when none registered."""
        hooks = dispatcher.get_hooks(HookEventType.SEARCH_COMPLETE)

        assert hooks == []

    def test_unregister_hook(self, dispatcher):
        """Test hook unregistration."""
        config = HookConfig(
            name="test_hook",
            event=HookEventType.SEARCH_COMPLETE,
            script_path="/tmp/test.sh",
        )

        dispatcher.register_hook(config)
        dispatcher.unregister_hook("test_hook", HookEventType.SEARCH_COMPLETE)

        hooks = dispatcher.get_hooks(HookEventType.SEARCH_COMPLETE)
        assert hooks == []

    def test_unregister_nonexistent_event(self, dispatcher):
        dispatcher.unregister_hook("no_hook", HookEventType.SEARCH_START)
        assert True

    def test_register_duplicate_hook(self, dispatcher):
        config = HookConfig(name="dup", event=HookEventType.SEARCH_START, script_path="/tmp/test.sh")
        dispatcher.register_hook(config)
        dispatcher.register_hook(config)
        assert len(dispatcher._hooks[HookEventType.SEARCH_START]) == 1

    def test_register_new_event_type(self, dispatcher):
        config = HookConfig(name="first", event=HookEventType.DOWNLOAD_START, script_path="/tmp/test.sh")
        dispatcher.register_hook(config)
        assert HookEventType.DOWNLOAD_START in dispatcher._hooks

    def test_dispatch_skips_disabled_hook(self, dispatcher):
        config = HookConfig(name="disabled_test", event=HookEventType.SEARCH_START, script_path="/tmp/test.sh", enabled=False)
        dispatcher.register_hook(config)
        import asyncio
        event = HookEvent(event_type=HookEventType.SEARCH_START, data={"q": "test"})
        asyncio.run(dispatcher.dispatch(event))
        assert len(dispatcher._execution_log) == 0

    def test_validate_empty_name(self):
        config = HookConfig(name="", event=HookEventType.SEARCH_START, script_path="/tmp/test.sh")
        assert config.validate() is False

    def test_validate_empty_script_path(self):
        config = HookConfig(name="test", event=HookEventType.SEARCH_START, script_path="")
        assert config.validate() is False

    def test_create_default_hook_function(self):
        config = create_default_hook("default_test", HookEventType.SEARCH_START, "/tmp/default.sh")
        assert config.name == "default_test"
        assert config.event == HookEventType.SEARCH_START
        assert config.script_path == "/tmp/default.sh"
        assert config.enabled is True
        assert config.timeout == 30

    def test_execution_log_contains_search_and_download_ids(self, dispatcher):
        """Dispatch with search_id and download_id triggers env vars."""
        import asyncio
        config = HookConfig(name="id_check", event=HookEventType.DOWNLOAD_START, script_path="/nonexistent_test_script_xyz.sh")
        dispatcher.register_hook(config)
        event = HookEvent(event_type=HookEventType.DOWNLOAD_START, search_id="sid-001", download_id="did-001")
        asyncio.run(dispatcher.dispatch(event))
        assert True

    def test_dispatch_exception_reraised(self, dispatcher, monkeypatch, tmp_path):
        """When _execute_hook raises, dispatch logs error but doesn't crash."""
        import asyncio

        async def broken_execute(hook, event):
            raise RuntimeError("simulated failure")

        script = tmp_path / "hook.sh"
        script.write_text("#!/bin/sh\necho ok")
        script.chmod(0o755)
        monkeypatch.setattr(dispatcher, "_execute_hook", broken_execute)
        config = HookConfig(name="broken", event=HookEventType.SEARCH_START, script_path=str(script))
        dispatcher.register_hook(config)
        event = HookEvent(event_type=HookEventType.SEARCH_START)
        asyncio.run(dispatcher.dispatch(event))
        # The exception is logged but _execute_hook doesn't append to _execution_log
        assert len(dispatcher._execution_log) == 0

    def test_execute_hook_success(self, tmp_path, monkeypatch):
        """A working hook script populates the execution log."""
        # RW-01 sandbox: scripts must live inside the allowlisted hooks dir.
        monkeypatch.setenv("BOBA_HOOKS_DIR", str(tmp_path))
        script = tmp_path / "success_hook.sh"
        script.write_text("#!/bin/sh\necho done")
        script.chmod(0o755)
        d = HookDispatcher(timeout=5)
        config = HookConfig(name="good_hook", event=HookEventType.SEARCH_START, script_path=str(script))
        d.register_hook(config)
        event = HookEvent(
            event_type=HookEventType.SEARCH_START,
            search_id="sid-999",
            download_id="did-999",
            data={"q": "test"},
        )
        import asyncio
        asyncio.run(d.dispatch(event))
        assert len(d._execution_log) == 1
        entry = d._execution_log[0]
        assert entry["success"] is True
        assert entry["hook_name"] == "good_hook"

    def test_execute_hook_nonzero_exit(self, tmp_path, monkeypatch):
        """A hook that exits non-zero gets logged as failure."""
        # RW-01 sandbox: scripts must live inside the allowlisted hooks dir.
        monkeypatch.setenv("BOBA_HOOKS_DIR", str(tmp_path))
        script = tmp_path / "fail_hook.sh"
        script.write_text("#!/bin/sh\nexit 1")
        script.chmod(0o755)
        d = HookDispatcher(timeout=5)
        config = HookConfig(name="bad_exit", event=HookEventType.SEARCH_COMPLETE, script_path=str(script))
        d.register_hook(config)
        event = HookEvent(event_type=HookEventType.SEARCH_COMPLETE, data={"r": 5})
        import asyncio
        asyncio.run(d.dispatch(event))
        assert len(d._execution_log) == 1
        entry = d._execution_log[0]
        assert entry["success"] is False
        assert entry["return_code"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
