"""Integration tests for jackett_autoconfig against a running Jackett.

Requires the full compose stack to be up. Skips if Jackett unreachable.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "..", "download-proxy", "src"),
)

import importlib.util

import pytest
import requests

JACKETT_URL = os.getenv("JACKETT_URL", "http://localhost:9117")

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_MS_PATH = os.path.join(_REPO_ROOT, "download-proxy", "src", "merge_service")
sys.modules.setdefault("merge_service", type(sys)("merge_service"))
sys.modules["merge_service"].__path__ = [_MS_PATH]
_ac_spec = importlib.util.spec_from_file_location(
    "merge_service.jackett_autoconfig",
    os.path.join(_MS_PATH, "jackett_autoconfig.py"),
)
_ac_mod = importlib.util.module_from_spec(_ac_spec)
sys.modules["merge_service.jackett_autoconfig"] = _ac_mod
_ac_spec.loader.exec_module(_ac_mod)


def _read_jackett_api_key() -> str:
    path = os.path.join(_REPO_ROOT, "config", "jackett", "Jackett", "ServerConfig.json")
    if not os.path.isfile(path):
        return ""
    with open(path) as f:
        return json.load(f).get("APIKey", "")


@pytest.fixture(scope="module")
def jackett_ready():
    try:
        r = requests.get(f"{JACKETT_URL}/UI/Login", timeout=3)
        if r.status_code >= 500:
            pytest.skip(f"Jackett unhealthy ({r.status_code})")
    except requests.RequestException:
        pytest.skip("Jackett unreachable")  # allow-skip: integration data-dependent — Jackett may not be up
    key = _read_jackett_api_key()
    if not key:
        pytest.skip("Jackett API key not yet generated")
    return key


def test_module_orchestrator_is_idempotent_on_second_invocation(jackett_ready):
    """Calling autoconfigure_jackett() twice in a row should report
    already_present (or skip) the second time, never re-configure."""
    import asyncio

    autoconfigure_jackett = _ac_mod.autoconfigure_jackett

    async def run_twice():
        env = {"TESTONLY_USERNAME": "a", "TESTONLY_PASSWORD": "b"}
        r1 = await autoconfigure_jackett(
            jackett_url=JACKETT_URL, api_key=jackett_ready, env=env, timeout=8.0
        )
        r2 = await autoconfigure_jackett(
            jackett_url=JACKETT_URL, api_key=jackett_ready, env=env, timeout=8.0
        )
        return r1, r2

    r1, r2 = asyncio.run(run_twice())
    # Whatever r1 configured, r2 must NOT configure-now again.
    for indexer in r1.configured_now:
        assert indexer not in r2.configured_now, (
            f"indexer {indexer} configured twice — idempotency broken"
        )
