"""Property-based tests for scheduler payload handling.

The fix to ``Scheduler._execute_search`` must accept dict, object, and ``None``
results from the search callback. These tests use Hypothesis to generate a
variety of payload shapes and assert the scheduler state transitions correctly.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path


def _repo_root() -> Path:
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "download-proxy" / "src").is_dir():
            return parent
    raise RuntimeError("cannot find repo root with download-proxy/src")


import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC_PATH = _REPO_ROOT / "download-proxy" / "src"
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
ScheduleStatus = _scheduler_mod.ScheduleStatus

pytestmark = pytest.mark.property


class _ResultObject:
    def __init__(self, merged_results: int):
        self.merged_results = merged_results


@st.composite
def _payloads(draw):
    shape = draw(st.sampled_from(["dict", "object", "none"]))
    count = draw(st.integers(min_value=0, max_value=10000))
    return shape, count


async def _run(shape: str, count: int) -> Scheduler:
    scheduler = Scheduler(config_path="/dev/null")

    async def callback(query, category):
        if shape == "dict":
            return {"merged_results": count}
        if shape == "object":
            return _ResultObject(count)
        return None

    scheduler.set_search_callback(callback)
    search = scheduler.add_scheduled_search("prop-test", "ubuntu")
    await scheduler._execute_search(search)
    return scheduler, search


@given(_payloads())
@settings(max_examples=50, deadline=5_000, suppress_health_check=[HealthCheck.too_slow])
def test_scheduler_never_crashes_on_any_payload(payload):
    shape, count = payload
    scheduler, search = asyncio.run(_run(shape, count))
    assert search.status == ScheduleStatus.COMPLETED
    if shape == "dict" or shape == "object":
        assert search.results_count == count
    else:
        assert search.results_count == 0
    assert search.error_message is None


@given(count=st.integers(min_value=0, max_value=10000))
@settings(max_examples=30, deadline=5_000, suppress_health_check=[HealthCheck.too_slow])
def test_dict_payload_results_count_equals_merged_results(count):
    scheduler, search = asyncio.run(_run("dict", count))
    assert search.results_count == count


@given(count=st.integers(min_value=0, max_value=10000))
@settings(max_examples=30, deadline=5_000, suppress_health_check=[HealthCheck.too_slow])
def test_object_payload_results_count_equals_attribute(count):
    scheduler, search = asyncio.run(_run("object", count))
    assert search.results_count == count
