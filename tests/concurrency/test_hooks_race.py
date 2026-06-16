"""Verify that concurrent async writers to _execution_logs lose no data
under heavy fan-out (200 parallel coroutines).
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[2] / "download-proxy" / "src"
_HOOKS_PATH = _SRC / "api" / "hooks.py"


def _load_hooks():
    # Load hooks.py *within* the `api` package so its relative import
    # `from .routes import require_api_token` (added by the P0-security work)
    # resolves. The previous standalone spec_from_file_location("_test_hooks_race")
    # load gave the module no parent package → ImportError, so these race tests
    # silently FAILed-on-load (a §11.4.1 FAIL-bluff — they tested nothing).
    # We force a fresh module each call (pop from sys.modules + import) so
    # per-test _execution_logs state never bleeds across tests.
    if str(_SRC) not in sys.path:
        sys.path.insert(0, str(_SRC))
    for key in list(sys.modules):
        if key == "api.hooks":
            del sys.modules[key]
    return importlib.import_module("api.hooks")


@pytest.mark.asyncio
async def test_200_parallel_append_no_data_loss():
    hooks = _load_hooks()
    hooks._execution_logs.clear()

    async def writer(i):
        await hooks.append_hook_log({"index": i, "id": f"entry-{i}"})

    await asyncio.gather(*[writer(i) for i in range(200)])

    assert len(hooks._execution_logs) == 200
    indices = sorted(entry["index"] for entry in hooks._execution_logs)
    assert indices == list(range(200))


@pytest.mark.asyncio
async def test_20_parallel_extend_no_data_loss():
    hooks = _load_hooks()
    hooks._execution_logs.clear()

    async def extender(batch_id):
        await hooks.extend_hook_logs([{"batch": batch_id, "j": j} for j in range(10)])

    await asyncio.gather(*[extender(i) for i in range(20)])

    assert len(hooks._execution_logs) == 200


@pytest.mark.asyncio
async def test_mixed_append_and_extend_no_data_loss():
    hooks = _load_hooks()
    hooks._execution_logs.clear()

    async def appender(i):
        await hooks.append_hook_log({"op": "append", "i": i})

    async def extender(i):
        await hooks.extend_hook_logs([{"op": "extend", "i": i}])

    coros = [appender(i) for i in range(100)] + [extender(i) for i in range(50)]
    await asyncio.gather(*coros)

    assert len(hooks._execution_logs) == 150
