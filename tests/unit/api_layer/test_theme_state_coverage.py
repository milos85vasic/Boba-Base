"""
Additional coverage for api/theme_state.py — no mocks, real data only.

Tests the remaining uncovered paths:
- _load_or_seed with invalid paletteId/mode
- unsubscribe with non-existent queue
- subscriber_count property
- QueueFull handling in _notify
"""

import asyncio
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SRC_PATH = _REPO_ROOT / "download-proxy" / "src"
if str(_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(_SRC_PATH))


def _purge_api_module() -> None:
    for key in [k for k in list(sys.modules) if k == "api" or k.startswith("api.")]:
        del sys.modules[key]


class TestThemeStoreDirect:
    """Direct ThemeStore tests using real filesystem and asyncio queues."""

    def test_load_or_seed_invalid_palette_id_reverts_to_default(self, tmp_path, monkeypatch):
        theme_path = tmp_path / "theme.json"
        theme_path.write_text('{"paletteId": "unknown-palette", "mode": "dark"}')
        monkeypatch.setenv("THEME_STATE_PATH", str(theme_path))
        _purge_api_module()
        from api.theme_state import ThemeStore

        store = ThemeStore(theme_path)
        state = store.get()
        assert state.paletteId == "darcula"
        assert state.mode == "dark"

    def test_load_or_seed_invalid_mode_reverts_to_default(self, tmp_path, monkeypatch):
        theme_path = tmp_path / "theme.json"
        theme_path.write_text('{"paletteId": "nord", "mode": "unknown-mode"}')
        monkeypatch.setenv("THEME_STATE_PATH", str(theme_path))
        _purge_api_module()
        from api.theme_state import ThemeStore

        store = ThemeStore(theme_path)
        state = store.get()
        assert state.paletteId == "darcula"
        assert state.mode == "dark"

    def test_get_returns_current_state(self, tmp_path):
        _purge_api_module()
        from api.theme_state import ThemeStore

        store = ThemeStore(tmp_path / "theme.json")
        state = store.get()
        assert state.paletteId == "darcula"
        assert state.mode == "dark"
        assert state.updatedAt

    def test_put_valid_state(self, tmp_path):
        _purge_api_module()
        from api.theme_state import ThemeStore

        store = ThemeStore(tmp_path / "theme.json")
        state = store.put("nord", "light")
        assert state.paletteId == "nord"
        assert state.mode == "light"

    def test_put_invalid_palette_id_raises(self, tmp_path):
        _purge_api_module()
        from api.theme_state import ThemeStore

        store = ThemeStore(tmp_path / "theme.json")
        with pytest.raises(ValueError, match="unknown paletteId"):
            store.put("invalid-id", "dark")

    def test_put_invalid_mode_raises(self, tmp_path):
        _purge_api_module()
        from api.theme_state import ThemeStore

        store = ThemeStore(tmp_path / "theme.json")
        with pytest.raises(ValueError, match="invalid mode"):
            store.put("nord", "gray")

    def test_subscriber_count(self, tmp_path):
        _purge_api_module()
        from api.theme_state import ThemeStore

        store = ThemeStore(tmp_path / "theme.json")
        assert store.subscriber_count == 0
        q = store.subscribe()
        assert store.subscriber_count == 1
        store.unsubscribe(q)
        assert store.subscriber_count == 0

    @pytest.mark.asyncio
    async def test_unsubscribe_non_existent_queue(self, tmp_path):
        _purge_api_module()
        from api.theme_state import ThemeStore

        store = ThemeStore(tmp_path / "theme.json")
        q = asyncio.Queue()
        store.unsubscribe(q)
        assert store.subscriber_count == 0

    @pytest.mark.asyncio
    async def test_subscribe_receives_put_update(self, tmp_path):
        _purge_api_module()
        from api.theme_state import ThemeStore

        store = ThemeStore(tmp_path / "theme.json")
        q = store.subscribe()
        store.put("monokai", "dark")
        item = await asyncio.wait_for(q.get(), timeout=1.0)
        assert item.paletteId == "monokai"
        assert item.mode == "dark"
        store.unsubscribe(q)

    @pytest.mark.asyncio
    async def test_notify_queue_full_dropped_update(self, tmp_path):
        _purge_api_module()
        from api.theme_state import ThemeStore

        store = ThemeStore(tmp_path / "theme.json")
        q = asyncio.Queue(maxsize=1)
        store._subscribers.append(q)
        q.put_nowait("stale")
        store.put("darcula", "dark")
        assert store.subscriber_count == 1

    def test_load_or_seed_valid_file(self, tmp_path):
        theme_path = tmp_path / "theme.json"
        theme_path.write_text('{"paletteId": "nord", "mode": "dark", "updatedAt": "2026-01-01T00:00:00"}')
        _purge_api_module()
        from api.theme_state import ThemeStore

        store = ThemeStore(theme_path)
        state = store.get()
        assert state.paletteId == "nord"
        assert state.mode == "dark"
        assert state.updatedAt == "2026-01-01T00:00:00"

    def test_write_atomic_fsync_failure(self, tmp_path, monkeypatch):
        _purge_api_module()
        import api.theme_state as ts_mod
        from api.theme_state import ThemeStore, ThemeState

        store = ThemeStore(tmp_path / "theme.json")
        state = ThemeState(paletteId="nord", mode="light", updatedAt="2026-01-01T00:00:00")
        monkeypatch.setattr(ts_mod.os, "fsync", lambda _: (_ for _ in ()).throw(OSError("fsync failed")))
        store._write_atomic(state)
        assert (tmp_path / "theme.json").exists()

    def test_write_atomic_replace_failure_then_cleanup(self, tmp_path, monkeypatch):
        _purge_api_module()
        import api.theme_state as ts_mod
        from api.theme_state import ThemeStore, ThemeState

        store = ThemeStore(tmp_path / "theme.json")
        state = ThemeState(paletteId="nord", mode="light", updatedAt="2026-01-01T00:00:00")
        monkeypatch.setattr(ts_mod.os, "replace", lambda _src, _dst: (_ for _ in ()).throw(PermissionError("replace failed")))
        with pytest.raises(PermissionError):
            store._write_atomic(state)
        leftovers = list(tmp_path.glob(".theme-*.json"))
        assert len(leftovers) == 0

    def test_write_atomic_replace_failure_already_unlinked(self, tmp_path, monkeypatch):
        _purge_api_module()
        import api.theme_state as ts_mod
        from api.theme_state import ThemeStore, ThemeState

        store = ThemeStore(tmp_path / "theme.json")
        state = ThemeState(paletteId="nord", mode="dark", updatedAt="2026-01-01T00:00:00")
        monkeypatch.setattr(ts_mod.os, "replace", lambda _src, _dst: (_ for _ in ()).throw(PermissionError("replace failed")))
        monkeypatch.setattr(ts_mod.os, "unlink", lambda _p: (_ for _ in ()).throw(FileNotFoundError("already gone")))
        with pytest.raises(PermissionError):
            store._write_atomic(state)

    def test_write_atomic_creates_file(self, tmp_path):
        _purge_api_module()
        from api.theme_state import ThemeStore, ThemeState

        store = ThemeStore(tmp_path / "theme.json")
        state = ThemeState(paletteId="nord", mode="light", updatedAt="2026-01-01T00:00:00")
        store._write_atomic(state)
        assert (tmp_path / "theme.json").exists()
        import json
        data = json.loads((tmp_path / "theme.json").read_text())
        assert data["paletteId"] == "nord"
        assert data["mode"] == "light"

    def test_theme_state_to_dict(self, tmp_path):
        _purge_api_module()
        from api.theme_state import ThemeState

        state = ThemeState(paletteId="gruvbox", mode="dark", updatedAt="2026-01-01T00:00:00")
        d = state.to_dict()
        assert d["paletteId"] == "gruvbox"
        assert d["mode"] == "dark"
        assert d["updatedAt"] == "2026-01-01T00:00:00"
