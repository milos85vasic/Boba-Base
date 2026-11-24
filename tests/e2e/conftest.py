"""E2E-test conftest — same shape as tests/integration/conftest.py.

Same autouse lock + wait-for-idle so e2e tests (Playwright, multi-
service scenarios) don't race the integration batch, and each test
starts with an idle orchestrator.
"""

from __future__ import annotations

import os

import pytest

from tests.fixtures.live_search import _file_lock as _live_search_lock
from tests.integration.conftest import (
    _merge_api_token_session,
    _wait_for_idle,
)


@pytest.fixture(autouse=True)
def _serialize_live_searches():
    base_url = os.environ.get("MERGE_SERVICE_URL", "http://localhost:7187")
    with _live_search_lock():
        _wait_for_idle(base_url)
        yield
