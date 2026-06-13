"""Security/penetration tests for jackett_autoconfig.

Asserts no credential value reaches: HTTP response body, exception
tracebacks, log streams, or the Jackett log on disk. Also runs bandit
against the module.
"""

from __future__ import annotations

import importlib.util
import io
import json
import logging
import os
import subprocess
import sys

import pytest
import requests

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MERGE_BASE = os.getenv("MERGE_SERVICE_URL", "http://localhost:7187")
SENTINEL_PASSWORD = "p@ssw0rd_DO_NOT_LEAK_4f8a"
SENTINEL_COOKIE = "leak_canary_8b2c=evidence"

sys.path.insert(0, os.path.join(PROJECT_ROOT, "download-proxy", "src"))
sys.modules.setdefault("merge_service", type(sys)("merge_service"))
sys.modules["merge_service"].__path__ = [
    os.path.join(PROJECT_ROOT, "download-proxy", "src", "merge_service")
]
_ac_spec = importlib.util.spec_from_file_location(
    "merge_service.jackett_autoconfig",
    os.path.join(PROJECT_ROOT, "download-proxy", "src", "merge_service", "jackett_autoconfig.py"),
)
_ac_mod = importlib.util.module_from_spec(_ac_spec)
sys.modules["merge_service.jackett_autoconfig"] = _ac_mod
_ac_spec.loader.exec_module(_ac_mod)


def test_endpoint_response_contains_no_sentinel_credentials():
    pytest.skip(
        "endpoint moved to boba-jackett:7189 — see qBitTorrent-go/tests/security/credential_leak_test.go"
    )


@pytest.mark.asyncio
async def test_traceback_from_forced_failure_excludes_credentials():
    log_stream = io.StringIO()
    handler = logging.StreamHandler(log_stream)
    handler.setLevel(logging.DEBUG)
    root = logging.getLogger()
    root.addHandler(handler)
    try:
        result = await _ac_mod.autoconfigure_jackett(
            jackett_url="http://127.0.0.1:1",
            api_key=SENTINEL_PASSWORD,
            env={
                "TESTRACKER_USERNAME": "u",
                "TESTRACKER_PASSWORD": SENTINEL_PASSWORD,
                "TESTRACKER_COOKIES": SENTINEL_COOKIE,
            },
            timeout=1.0,
        )
    finally:
        root.removeHandler(handler)
    captured = log_stream.getvalue()
    assert SENTINEL_PASSWORD not in captured, "password leaked into logs"
    assert SENTINEL_COOKIE not in captured, "cookie leaked into logs"
    assert SENTINEL_PASSWORD not in repr(result)
    assert SENTINEL_COOKIE not in repr(result)
    body_json = result.model_dump_json(by_alias=True)
    assert SENTINEL_PASSWORD not in body_json
    assert SENTINEL_COOKIE not in body_json


def test_jackett_log_file_does_not_contain_sentinels():
    log_path = os.path.join(PROJECT_ROOT, "config", "jackett", "Jackett", "log.txt")
    if not os.path.isfile(log_path):
        pytest.skip("Jackett log not present")
    with open(log_path, encoding="utf-8", errors="ignore") as f:
        content = f.read()
    assert SENTINEL_PASSWORD not in content
    assert SENTINEL_COOKIE not in content


def _resolve_bandit() -> str | None:
    """Locate the ``bandit`` executable.

    Prefer the running interpreter's own bin directory (so the venv's
    ``bandit`` is found even when it is not on the bare ``PATH``), then fall
    back to ``PATH``. Returns ``None`` when bandit is genuinely unavailable so
    the test SKIPs (§11.4.3) instead of raising FileNotFoundError.
    """
    import shutil

    candidate = os.path.join(os.path.dirname(sys.executable), "bandit")
    if os.path.exists(candidate):
        return candidate
    return shutil.which("bandit")


def test_bandit_scan_module_clean():
    target = os.path.join(
        PROJECT_ROOT, "download-proxy", "src", "merge_service", "jackett_autoconfig.py"
    )
    bandit_exe = _resolve_bandit()
    if bandit_exe is None:
        pytest.skip("bandit not installed — pip install bandit")
    result = subprocess.run(
        [bandit_exe, "-q", "-f", "json", target],
        capture_output=True,
        text=True,
        check=False,
    )
    if not result.stdout.strip():
        pytest.skip("bandit produced no output")
    data = json.loads(result.stdout)
    high = [r for r in data.get("results", []) if r.get("issue_severity") == "HIGH"]
    assert high == [], f"bandit HIGH findings: {high}"
