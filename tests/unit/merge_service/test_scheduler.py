"""
Unit tests for the scheduler module.
"""

import asyncio
import os
import sys

import pytest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_SRC_PATH = os.path.join(_REPO_ROOT, "download-proxy", "src")
_MS_PATH = os.path.join(_SRC_PATH, "merge_service")

sys.modules.setdefault("merge_service", type(sys)("merge_service"))
sys.modules["merge_service"].__path__ = [_MS_PATH]

import importlib.util

_sched_spec = importlib.util.spec_from_file_location("merge_service.scheduler", os.path.join(_MS_PATH, "scheduler.py"))
_sched_mod = importlib.util.module_from_spec(_sched_spec)
sys.modules["merge_service.scheduler"] = _sched_mod
_sched_spec.loader.exec_module(_sched_mod)

Scheduler = _sched_mod.Scheduler
ScheduledSearch = _sched_mod.ScheduledSearch
ScheduleStatus = _sched_mod.ScheduleStatus


class TestScheduledSearch:
    def test_defaults(self):
        s = ScheduledSearch(id="abc", name="test", query="ubuntu")
        assert s.id == "abc"
        assert s.name == "test"
        assert s.query == "ubuntu"
        assert s.category == "all"
        assert s.interval_minutes == 60
        assert s.enabled is True
        assert s.status == ScheduleStatus.ACTIVE

    def test_custom_values(self):
        s = ScheduledSearch(
            id="xyz",
            name="my search",
            query="debian",
            category="linux",
            interval_minutes=30,
            enabled=False,
            status=ScheduleStatus.PAUSED,
        )
        assert s.category == "linux"
        assert s.interval_minutes == 30
        assert s.enabled is False
        assert s.status == ScheduleStatus.PAUSED


class TestScheduler:
    @pytest.fixture
    def tmp_path_file(self, tmp_path):
        return str(tmp_path / "scheduling.yaml")

    @pytest.fixture
    def scheduler(self, tmp_path_file):
        return Scheduler(config_path=tmp_path_file)

    def test_init(self, scheduler):
        assert scheduler._running is False
        assert len(scheduler._scheduled_searches) == 0

    def test_add_scheduled_search(self, scheduler):
        s = scheduler.add_scheduled_search("test", "ubuntu", interval_minutes=30)
        assert s.name == "test"
        assert s.query == "ubuntu"
        assert s.interval_minutes == 30
        assert s.id in scheduler._scheduled_searches

    def test_remove_scheduled_search(self, scheduler):
        s = scheduler.add_scheduled_search("test", "ubuntu")
        assert scheduler.remove_scheduled_search(s.id) is True
        assert scheduler.remove_scheduled_search("nonexistent") is False

    def test_get_scheduled_search(self, scheduler):
        s = scheduler.add_scheduled_search("test", "ubuntu")
        found = scheduler.get_scheduled_search(s.id)
        assert found is s
        assert scheduler.get_scheduled_search("nonexistent") is None

    def test_get_all_scheduled_searches(self, scheduler):
        scheduler.add_scheduled_search("a", "ubuntu")
        scheduler.add_scheduled_search("b", "debian")
        all_s = scheduler.get_all_scheduled_searches()
        assert len(all_s) == 2

    def test_get_active_scheduled_searches(self, scheduler):
        s1 = scheduler.add_scheduled_search("active", "ubuntu")
        s2 = scheduler.add_scheduled_search("disabled", "debian")
        s2.enabled = False
        active = scheduler.get_active_scheduled_searches()
        assert len(active) == 1
        assert active[0].name == "active"

    def test_save_and_load(self, scheduler, tmp_path_file):
        scheduler.add_scheduled_search("test", "ubuntu", interval_minutes=120)
        asyncio.run(scheduler.save())

        scheduler2 = Scheduler(config_path=tmp_path_file)
        asyncio.run(scheduler2.load())
        searches = scheduler2.get_all_scheduled_searches()
        assert len(searches) == 1
        assert searches[0].name == "test"
        assert searches[0].query == "ubuntu"
        assert searches[0].interval_minutes == 120

    def test_start_and_stop(self, scheduler):
        asyncio.run(scheduler.start())
        assert scheduler._running is True
        asyncio.run(scheduler.stop())
        assert scheduler._running is False

    def test_double_start(self, scheduler):
        asyncio.run(scheduler.start())
        asyncio.run(scheduler.start())
        assert scheduler._running is True
        asyncio.run(scheduler.stop())

    def test_callback(self, scheduler):
        called = []
        scheduler.set_search_callback(lambda q, c: called.append((q, c)))
        scheduler._search_callback("ubuntu", "all")
        assert called == [("ubuntu", "all")]

    @pytest.mark.asyncio
    async def test_execute_search_with_metadata_object(self, scheduler):
        """Scheduler callback may return a SearchMetadata-like object.

        ``api/__init__.py`` historically wired the scheduler callback to
        ``SearchOrchestrator.search()``, which returns a ``SearchMetadata``
        object. ``Scheduler._execute_search()`` then called
        ``result.get("merged_results", 0)``, raising ``AttributeError``.
        This test reproduces that live bug and guards the fix.
        """

        class FakeMetadata:
            merged_results = 7

        async def callback(query, category):
            return FakeMetadata()

        scheduler.set_search_callback(callback)
        search = scheduler.add_scheduled_search("metadata-test", "ubuntu")
        search.last_run = None
        await scheduler._execute_search(search)
        assert search.results_count == 7
        assert search.status == ScheduleStatus.COMPLETED


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
