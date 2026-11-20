"""Integration: scheduler executes dict/object/None callback results safely.

The recent fix to ``merge_service.scheduler.Scheduler._execute_search`` makes
it accept dict, object, and ``None`` return values from the search callback
without raising. This test exercises the real scheduler class with each shape
and asserts the persisted schedule row reflects the expected outcome.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
from pathlib import Path


def _repo_root() -> Path:
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "download-proxy" / "src").is_dir():
            return parent
    raise RuntimeError("cannot find repo root with download-proxy/src")


import pytest

_SRC_PATH = _repo_root() / "download-proxy" / "src"
_MS_PATH = _SRC_PATH / "merge_service"

if str(_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(_SRC_PATH))

sys.modules.setdefault("merge_service", type(sys)("merge_service"))
sys.modules["merge_service"].__path__ = [str(_MS_PATH)]  # type: ignore[attr-defined]

_spec = importlib.util.spec_from_file_location("merge_service.scheduler", str(_MS_PATH / "scheduler.py"))
_scheduler_mod = importlib.util.module_from_spec(_spec)
sys.modules["merge_service.scheduler"] = _scheduler_mod
_spec.loader.exec_module(_scheduler_mod)  # type: ignore[union-attr]

Scheduler = _scheduler_mod.Scheduler
ScheduledSearch = _scheduler_mod.ScheduledSearch
ScheduleStatus = _scheduler_mod.ScheduleStatus


@pytest.fixture
def scheduler(tmp_path):
    return Scheduler(config_path=str(tmp_path / "scheduling.json"))


async def test_scheduler_executes_dict_payload(scheduler):
    async def callback(query, category):
        return {"merged_results": 13}

    scheduler.set_search_callback(callback)
    search = scheduler.add_scheduled_search("dict-test", "ubuntu")
    await scheduler._execute_search(search)

    assert search.results_count == 13
    assert search.status == ScheduleStatus.COMPLETED
    assert search.error_message is None


async def test_scheduler_executes_object_payload(scheduler):
    class FakeMetadata:
        merged_results = 42

    async def callback(query, category):
        return FakeMetadata()

    scheduler.set_search_callback(callback)
    search = scheduler.add_scheduled_search("object-test", "debian")
    await scheduler._execute_search(search)

    assert search.results_count == 42
    assert search.status == ScheduleStatus.COMPLETED
    assert search.error_message is None


async def test_scheduler_executes_none_payload(scheduler):
    async def callback(query, category):
        return None

    scheduler.set_search_callback(callback)
    search = scheduler.add_scheduled_search("none-test", "arch")
    await scheduler._execute_search(search)

    assert search.results_count == 0
    assert search.status == ScheduleStatus.COMPLETED
    assert search.error_message is None


async def test_scheduler_persists_completed_status(scheduler, tmp_path):
    async def callback(query, category):
        return {"merged_results": 7}

    scheduler.set_search_callback(callback)
    search = scheduler.add_scheduled_search("persist-test", "fedora")
    await scheduler._execute_search(search)

    await scheduler.save()

    scheduler2 = Scheduler(config_path=str(tmp_path / "scheduling.json"))
    await scheduler2.load()
    loaded = scheduler2.get_scheduled_search(search.id)
    assert loaded is not None
    assert loaded.results_count == 7
    assert loaded.status == ScheduleStatus.COMPLETED
