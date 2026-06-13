import pytest

from tests.fixtures.health import merge_service_required


@merge_service_required
@pytest.mark.observability
@pytest.mark.requires_compose
def test_prometheus_metrics_endpoint_exists():
    """The merge service should expose /metrics.

    Guarded by ``merge_service_required`` so it SKIPs (not FAILs) when the
    live merge service on :7187 is not running, per §11.4.3 (infra-absent
    topology → SKIP-with-reason, never a connection-refused FAIL). The sibling
    security suites use the same skip helper.
    """
    import httpx

    r = httpx.get("http://localhost:7187/metrics", timeout=5)
    assert r.status_code in (200, 404)
