"""E2E: full stack already up → autoconfig endpoint live → search succeeds.

Does not perform a clean-slate boot itself (the standalone challenge
script does that). Validates the running stack as configured.
"""

from __future__ import annotations

import os
import time

import pytest
import requests

MERGE_BASE = os.getenv("MERGE_SERVICE_URL", "http://localhost:7187")


@pytest.fixture(scope="module")
def stack_ready():
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            if requests.get(f"{MERGE_BASE}/health", timeout=2).ok:
                return
        except requests.RequestException:
            pass
        time.sleep(2)
    pytest.skip("merge service not healthy within 30s")  # allow-skip: E2E data-dependent — stack may not be up


def test_autoconfig_endpoint_returns_200_or_404(stack_ready):
    pytest.skip(
        "endpoint moved to boba-jackett:7189 — see qBitTorrent-go/tests/e2e/jackett_management_test.go"
    )


def test_autoconfig_payload_structure_when_present(stack_ready):
    pytest.skip(
        "endpoint moved to boba-jackett:7189 — see qBitTorrent-go/tests/e2e/jackett_management_test.go"
    )


def test_search_endpoint_does_not_5xx(stack_ready):
    """Smoke: search through merge service must not 5xx — not asserting
    result content because tracker availability is non-deterministic."""
    r = requests.post(
        f"{MERGE_BASE}/api/v1/search",
        json={"query": "ubuntu", "category": "all"},
        timeout=15,
    )
    assert r.status_code < 500, r.text
