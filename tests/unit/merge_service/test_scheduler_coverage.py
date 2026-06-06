"""
Additional coverage for merge_service/scheduler.py — no mocks, real I/O.
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

_sched_spec = importlib.util.spec_from_file_location(
    "merge_service.scheduler", os.path.join(_MS_PATH, "scheduler.py"),
)
_sched_mod = importlib.util.module_from_spec(_sched_spec)
sys.modules["merge_service.scheduler"] = _sched_mod
_sched_spec.loader.exec_module(_sched_mod)

Scheduler = _sched_mod.Scheduler
ScheduledSearch = _sched_mod.ScheduledSearch
ScheduleStatus = _sched_mod.ScheduleStatus
get_scheduler = _sched_mod.get_scheduler


class TestSchedulerLoadSave:
    @pytest.mark.asyncio
    async def test_load_with_nonexistent_file(self, tmp_path):
        path = str(tmp_path / "nonexistent.json")
        s = Scheduler(config_path=path)
        await s.load()
        assert len(s._scheduled_searches) == 0

    @pytest.mark.asyncio
    async def test_load_with_invalid_json(self, tmp_path):
        path = str(tmp_path / "invalid.json")
        def _write():
            with open(path, "w") as f:
                f.write("not json at all")
        await asyncio.to_thread(_write)
        s = Scheduler(config_path=path)
        await s.load()
        assert len(s._scheduled_searches) == 0

    @pytest.mark.asyncio
    async def test_save_creates_directory(self, tmp_path):
        nested = tmp_path / "nested" / "dir" / "scheduler.json"
        s = Scheduler(config_path=str(nested))
        s.add_scheduled_search("test", "ubuntu")
        await s.save()
        assert nested.exists()

    @pytest.mark.asyncio
    async def test_save_and_load_roundtrip(self, tmp_path):
        path = str(tmp_path / "scheduler.json")
        s1 = Scheduler(config_path=path)
        s1.add_scheduled_search("search1", "debian", category="linux", interval_minutes=30)
        s1.add_scheduled_search("search2", "kubuntu")
        await s1.save()

        s2 = Scheduler(config_path=path)
        await s2.load()
        all_s = s2.get_all_scheduled_searches()
        assert len(all_s) == 2
        names = {s.name for s in all_s}
        assert names == {"search1", "search2"}

    @pytest.mark.asyncio
    async def test_save_error_path(self, tmp_path):
        import stat
        non_writable = tmp_path / "no-write"
        non_writable.mkdir()
        os.chmod(non_writable, stat.S_IRUSR | stat.S_IXUSR)
        path = str(non_writable / "scheduler.json")
        s = Scheduler(config_path=path)
        s.add_scheduled_search("test", "ubuntu")
        try:
            await s.save()
        finally:
            os.chmod(non_writable, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)


class TestGetScheduler:
    def test_get_scheduler_creates_singleton(self, tmp_path):
        path = str(tmp_path / "singleton.json")
        s1 = get_scheduler(config_path=path)
        assert s1 is not None
        s2 = get_scheduler(config_path=path)
        assert s1 is s2

    def test_get_scheduler_resets_after_clear(self, tmp_path):
        path = str(tmp_path / "reset.json")
        _sched_mod._scheduler = None
        s1 = get_scheduler(config_path=path)
        _sched_mod._scheduler = None
        s2 = get_scheduler(config_path=path)
        assert s1 is not s2


class TestExecuteSearch:
    @pytest.mark.asyncio
    async def test_execute_search_with_callback(self, tmp_path):
        path = str(tmp_path / "exec.json")
        s = Scheduler(config_path=path)
        results = []

        async def callback(query, category):
            results.append((query, category))
            return {"merged_results": 5}

        s.set_search_callback(callback)
        search = s.add_scheduled_search("exec-test", "ubuntu")
        search.last_run = None
        await s._execute_search(search)
        assert search.results_count == 5
        assert search.status == ScheduleStatus.COMPLETED
        assert search.error_message is None

    @pytest.mark.asyncio
    async def test_execute_search_no_callback(self, tmp_path):
        path = str(tmp_path / "no-cb.json")
        s = Scheduler(config_path=path)
        search = s.add_scheduled_search("no-cb", "ubuntu")
        search.last_run = None
        await s._execute_search(search)
        assert search.results_count == 0

    @pytest.mark.asyncio
    async def test_execute_search_callback_raises(self, tmp_path):
        path = str(tmp_path / "raise.json")
        s = Scheduler(config_path=path)

        async def failing_callback(query, category):
            raise RuntimeError("search failed")

        s.set_search_callback(failing_callback)
        search = s.add_scheduled_search("fail-test", "ubuntu")
        search.last_run = None
        await s._execute_search(search)
        assert search.status == ScheduleStatus.FAILED
        assert search.error_message == "search failed"


class TestSchedulerStop:
    @pytest.mark.asyncio
    async def test_stop_with_running_task(self, tmp_path):
        path = str(tmp_path / "stop.json")
        s = Scheduler(config_path=path)
        await s.start()
        assert s._running is True
        assert s._task is not None
        await s.stop()
        assert s._running is False
        assert s._task is None or s._task.done()

    @pytest.mark.asyncio
    async def test_stop_without_starting(self, tmp_path):
        path = str(tmp_path / "stop-no-start.json")
        s = Scheduler(config_path=path)
        await s.stop()
        assert s._running is False

    @pytest.mark.asyncio
    async def test_double_stop(self, tmp_path):
        path = str(tmp_path / "double-stop.json")
        s = Scheduler(config_path=path)
        await s.start()
        await s.stop()
        await s.stop()
        assert s._running is False


class TestSearchLoadedSearches:
    @pytest.mark.asyncio
    async def test_save_and_load_with_status(self, tmp_path):
        import json
        path = str(tmp_path / "status.json")
        s = Scheduler(config_path=path)
        search = s.add_scheduled_search("status-test", "ubuntu")
        search.status = ScheduleStatus.FAILED
        search.error_message = "previous failure"
        search.results_count = 3
        await s.save()

        s2 = Scheduler(config_path=path)
        await s2.load()
        loaded = s2.get_scheduled_search(search.id)
        assert loaded is not None
        assert loaded.status == ScheduleStatus.FAILED
        assert loaded.error_message == "previous failure"
        assert loaded.results_count == 3
