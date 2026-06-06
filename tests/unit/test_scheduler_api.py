"""
Unit tests for the scheduler API endpoints.
"""

import os
import sys

import pytest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_SRC_PATH = os.path.join(_REPO_ROOT, "download-proxy", "src")
_API_PATH = os.path.join(_SRC_PATH, "api")
_MS_PATH = os.path.join(_SRC_PATH, "merge_service")

sys.modules.setdefault("merge_service", type(sys)("merge_service"))
sys.modules["merge_service"].__path__ = [_MS_PATH]
sys.modules.setdefault("api", type(sys)("api"))
sys.modules["api"].__path__ = [_API_PATH]

import importlib.util

_sched_api_spec = importlib.util.spec_from_file_location("api.scheduler", os.path.join(_API_PATH, "scheduler.py"))
_sched_api_mod = importlib.util.module_from_spec(_sched_api_spec)
sys.modules["api.scheduler"] = _sched_api_mod
_sched_api_spec.loader.exec_module(_sched_api_mod)

from fastapi import FastAPI
from fastapi.testclient import TestClient


class MockScheduler:
    def __init__(self):
        self._searches = {}
        self._next_id = 0

    def add_scheduled_search(self, name, query, category="all", interval_minutes=60):
        from merge_service.scheduler import ScheduledSearch, ScheduleStatus

        self._next_id += 1
        sid = f"test-id-{self._next_id}"
        s = ScheduledSearch(
            id=sid,
            name=name,
            query=query,
            category=category,
            interval_minutes=interval_minutes,
            status=ScheduleStatus.ACTIVE,
        )
        self._searches[sid] = s
        return s

    def get_scheduled_search(self, sid):
        return self._searches.get(sid)

    def get_all_scheduled_searches(self):
        return list(self._searches.values())

    def remove_scheduled_search(self, sid):
        if sid in self._searches:
            del self._searches[sid]
            return True
        return False

    async def save(self):
        pass


def _make_app():
    app = FastAPI()
    from api.scheduler import router

    app.include_router(router, prefix="/api/v1/schedules")
    app.state.scheduler = MockScheduler()
    return app


class TestSchedulerAPI:
    @pytest.fixture
    def client(self):
        return TestClient(_make_app())

    def test_list_schedules_empty(self, client):
        resp = client.get("/api/v1/schedules")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 0
        assert data["schedules"] == []

    def test_create_schedule(self, client):
        resp = client.post(
            "/api/v1/schedules",
            json={
                "name": "test search",
                "query": "ubuntu",
                "interval_minutes": 30,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "test search"
        assert data["query"] == "ubuntu"
        assert data["interval_minutes"] == 30

    def test_create_and_list(self, client):
        client.post(
            "/api/v1/schedules",
            json={
                "name": "test",
                "query": "ubuntu",
            },
        )
        resp = client.get("/api/v1/schedules")
        assert resp.json()["count"] == 1

    def test_get_schedule(self, client):
        create = client.post(
            "/api/v1/schedules",
            json={
                "name": "test",
                "query": "debian",
            },
        ).json()
        sid = create["id"]
        resp = client.get(f"/api/v1/schedules/{sid}")
        assert resp.status_code == 200
        assert resp.json()["query"] == "debian"

    def test_get_schedule_not_found(self, client):
        resp = client.get("/api/v1/schedules/nonexistent")
        assert resp.status_code == 404

    def test_delete_schedule(self, client):
        create = client.post(
            "/api/v1/schedules",
            json={
                "name": "test",
                "query": "ubuntu",
            },
        ).json()
        sid = create["id"]
        resp = client.delete(f"/api/v1/schedules/{sid}")
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True
        resp2 = client.get("/api/v1/schedules")
        assert resp2.json()["count"] == 0

    def test_delete_schedule_not_found(self, client):
        resp = client.delete("/api/v1/schedules/nonexistent")
        assert resp.status_code == 404

    def test_update_schedule(self, client):
        create = client.post(
            "/api/v1/schedules",
            json={
                "name": "test",
                "query": "ubuntu",
            },
        ).json()
        sid = create["id"]
        resp = client.patch(
            f"/api/v1/schedules/{sid}",
            json={
                "enabled": False,
                "interval_minutes": 120,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False

    def test_update_not_found(self, client):
        resp = client.patch(
            "/api/v1/schedules/nonexistent",
            json={
                "enabled": False,
            },
        )
        assert resp.status_code == 404

    def test_create_invalid_interval(self, client):
        resp = client.post(
            "/api/v1/schedules",
            json={
                "name": "test",
                "query": "ubuntu",
                "interval_minutes": 1,
            },
        )
        assert resp.status_code == 422

    def test_update_schedule_name(self, client):
        create = client.post(
            "/api/v1/schedules",
            json={"name": "old-name", "query": "ubuntu"},
        ).json()
        sid = create["id"]
        resp = client.patch(
            f"/api/v1/schedules/{sid}",
            json={"name": "new-name"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "new-name"

    def test_create_short_name_rejected(self, client):
        resp = client.post(
            "/api/v1/schedules",
            json={"name": "", "query": "ubuntu"},
        )
        assert resp.status_code == 422


def test_scheduler_not_initialized_503():
    """_get_scheduler raises 503 when app.state has no scheduler."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.scheduler import router

    app = FastAPI()
    app.include_router(router, prefix="/api/v1/schedules")
    client = TestClient(app)
    resp = client.get("/api/v1/schedules")
    assert resp.status_code == 503
    assert "Scheduler not initialized" in resp.text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
