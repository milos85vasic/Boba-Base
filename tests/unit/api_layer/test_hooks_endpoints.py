"""
Tests for hooks HTTP endpoints and dispatch_event — no mocks.
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


@pytest.fixture
def client(tmp_path, monkeypatch):
    _purge_api_module()
    import api
    import api.hooks
    fake_path = tmp_path / "hooks.json"
    monkeypatch.setattr(api.hooks, "HOOKS_FILE", str(fake_path))
    # RW-01 sandbox: register hook scripts only inside the allowlisted dir.
    hooks_dir = tmp_path / "hooks"
    hooks_dir.mkdir()
    monkeypatch.setenv("BOBA_HOOKS_DIR", str(hooks_dir))
    c = TestClient(api.app)
    c._boba_hooks_dir = hooks_dir  # type: ignore[attr-defined]
    return c


class TestHooksEndpoints:
    def test_list_hooks_empty(self, client):
        resp = client.get("/api/v1/hooks")
        assert resp.status_code == 200
        data = resp.json()
        assert data["hooks"] == []
        assert data["count"] == 0

    def _create_hook(self, client):
        script = client._boba_hooks_dir / "test.sh"  # type: ignore[attr-defined]
        script.write_text("#!/bin/sh\necho ok\n")
        script.chmod(0o755)
        payload = {
            "name": "test-hook",
            "event": "search_start",
            "script_path": str(script),
        }
        resp = client.post("/api/v1/hooks", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["hook_id"]
        return data["hook_id"]

    def test_create_hook(self, client):
        hook_id = self._create_hook(client)
        assert hook_id

    def test_list_hooks_after_create(self, client):
        self._create_hook(client)
        resp = client.get("/api/v1/hooks")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1

    def test_create_hook_invalid_event(self, client):
        payload = {
            "name": "bad-hook",
            "event": "nonexistent_event",
            "script_path": "/usr/local/bin/test.sh",
        }
        resp = client.post("/api/v1/hooks", json=payload)
        assert resp.status_code == 400
        assert "Invalid event type" in resp.text

    def test_create_hook_path_traversal(self, client):
        payload = {
            "name": "traversal-hook",
            "event": "search_start",
            "script_path": "/usr/../etc/passwd",
        }
        resp = client.post("/api/v1/hooks", json=payload)
        assert resp.status_code == 400
        assert "path traversal" in resp.text

    def test_delete_hook(self, client):
        hook_id = self._create_hook(client)
        resp = client.delete(f"/api/v1/hooks/{hook_id}")
        assert resp.status_code == 200
        assert resp.json()["message"] == "Hook deleted"

    def test_delete_nonexistent_hook(self, client):
        resp = client.delete("/api/v1/hooks/nonexistent-id")
        assert resp.status_code == 404

    def test_get_execution_logs_empty(self, client):
        resp = client.get("/api/v1/hooks/logs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["logs"] == []
        assert data["count"] == 0


class TestDispatchEvent:
    @pytest.mark.asyncio
    async def test_dispatch_event_unknown_type(self, tmp_path, monkeypatch):
        _purge_api_module()
        import api
        import api.hooks
        fake_path = tmp_path / "hooks.json"
        monkeypatch.setattr(api.hooks, "HOOKS_FILE", str(fake_path))
        await api.hooks.dispatch_event("nonexistent_event", {})

    @pytest.mark.asyncio
    async def test_dispatch_event_empty_hooks(self, tmp_path, monkeypatch):
        _purge_api_module()
        import api
        import api.hooks
        fake_path = tmp_path / "hooks.json"
        monkeypatch.setattr(api.hooks, "HOOKS_FILE", str(fake_path))
        await api.hooks.dispatch_event("search_start", {"search_id": "test-123"})
