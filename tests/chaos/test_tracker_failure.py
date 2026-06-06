import os

import httpx
import pytest

# Collection-time check — skip the entire module if the service isn't up.
_CHAOS_UP: bool = bool(os.environ.get("CHAOS_TESTS_ENABLED"))
if _CHAOS_UP:
    try:
        _CHAOS_UP = httpx.get("http://localhost:7187/healthz", timeout=5).status_code == 200
    except Exception:
        _CHAOS_UP = False


@pytest.mark.chaos
@pytest.mark.skipif(not _CHAOS_UP, reason="Merge service not available")
def test_service_recovers_from_tracker_timeout():
    """When a tracker times out, the merge service should still return results from others."""
    r = httpx.get(
        "http://localhost:7187/api/v1/search?q=test&trackers=nonexistent_tracker",
        timeout=30,
    )
    assert r.status_code == 200
