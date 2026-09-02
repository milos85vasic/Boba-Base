"""Integration-test conftest.

Autouse fixtures:

*   ``_serialize_live_searches`` — holds the shared file lock from
    ``tests/fixtures/live_search.py`` for the duration of each test
    so the batch can't saturate MAX_CONCURRENT_SEARCHES.
*   ``_wait_for_idle_orchestrator`` — before yielding the lock to
    the test, block (with a short timeout) until the merge service
    reports zero active searches. This handles the case where a
    previous test's POST /api/v1/search returned quickly but its
    background fan-out was still chewing CPU.

Taken together these two keep one slow test from spilling into the
next. The lock is re-exported via ``_file_lock`` for tests that
intentionally want to burst the endpoint (none today).
"""

from __future__ import annotations

import os
import time

import pytest
import requests

from tests.fixtures.live_search import _file_lock as _live_search_lock


_WAIT_FOR_IDLE_MAX: float = float(os.environ.get("WAIT_FOR_IDLE_MAX_SECONDS", "180.0"))


def _wait_for_idle(base_url: str, max_wait: float | None = None) -> None:
    """Poll ``/api/v1/stats`` for ``active_searches == 0``.

    Bounded so a genuinely-stuck service fails the NEXT test
    explicitly (with a useful error message) rather than hanging
    the pytest session indefinitely.
    """
    max_wait = max_wait if max_wait is not None else _WAIT_FOR_IDLE_MAX
    deadline = time.monotonic() + max_wait
    while time.monotonic() < deadline:
        try:
            resp = requests.get(f"{base_url}/api/v1/stats", timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("active_searches", 0) == 0:
                    return
        except Exception:
            # Service hiccup — give it another beat.
            pass
        time.sleep(2)
    raise RuntimeError(
        f"orchestrator did not reach idle within {max_wait:.0f}s — "
        f"{base_url}/api/v1/stats still reports active searches. "
        "Abort any stuck searches or restart the merge service."
    )


@pytest.fixture(autouse=True)
def _serialize_live_searches():
    """Hold the shared live-search lock + wait for orchestrator idle."""
    base_url = os.environ.get("MERGE_SERVICE_URL", "http://localhost:7187")
    with _live_search_lock():
        _wait_for_idle(base_url)
        yield


# ---------------------------------------------------------------------------
# MISSING PLAYWRIGHT BROWSER BINARY -> HONEST SKIP (§11.4.3 / §11.4.27(11))
#
# Added 2026-09-01. tests/integration/test_streaming_browser.py uses the
# pytest-playwright plugin's session-scoped `browser` fixture (parametrised
# `[chromium]`), not a manual sync_playwright() launch — so the skip guard
# added to tests/e2e/test_{crossapp_theme,theme_runtime}.py does not reach it,
# and six tests ERRORED at fixture setup instead.
#
# A missing browser DOWNLOAD is an environment condition, not a product defect.
# Playwright itself IS installed; on this host its bundled Chromium refuses to
# install at all ("does not support chromium on ubuntu26.04-x64"). Reporting a
# healthy product as ERROR is a §11.4.201(1) false-positive refusal.
#
# NARROW BY CONSTRUCTION: this only fires for tests that actually request the
# `browser` fixture AND only when the resolved executable is genuinely absent
# on disk. It cannot mask a real browser failure — if the binary exists, the
# test runs and any failure surfaces normally.
# ---------------------------------------------------------------------------

_CHROMIUM_PRESENT: bool | None = None


def _chromium_binary_present() -> bool:
    """True when Playwright's Chromium executable actually exists on disk."""
    global _CHROMIUM_PRESENT
    if _CHROMIUM_PRESENT is not None:
        return _CHROMIUM_PRESENT
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            _CHROMIUM_PRESENT = os.path.exists(pw.chromium.executable_path)
    except Exception:
        # Playwright itself unavailable/unusable — also not a product defect.
        _CHROMIUM_PRESENT = False
    return _CHROMIUM_PRESENT


def pytest_collection_modifyitems(config, items):
    """Mark browser-driven tests SKIP at COLLECTION time when Chromium is absent.

    This must run at collection, not as an autouse fixture: pytest-playwright's
    `browser` fixture is SESSION-scoped and is therefore set up BEFORE any
    function-scoped autouse guard, so a fixture-based check fires too late and
    the tests still ERROR at setup. Measured: an autouse guard left all six
    tests/integration/test_streaming_browser.py tests ERRORing unchanged.
    """
    if _chromium_binary_present():
        return
    skip_marker = pytest.mark.skip(
        reason=(
            "SKIP-reason=browser_binary_not_installed: Playwright's Chromium "
            "binary is not present on this host (Playwright itself IS installed "
            "— only the browser download is missing). Install it with: "
            ".venv/bin/python -m playwright install chromium"
        )
    )
    for item in items:
        fixtures = getattr(item, "fixturenames", ())
        if "browser" in fixtures or "page" in fixtures or "context" in fixtures:
            item.add_marker(skip_marker)
