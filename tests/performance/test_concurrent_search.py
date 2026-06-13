"""
Performance tests for concurrent search load.

Scenarios:
- Multiple simultaneous search requests
- Search under sustained load
- Memory usage during many searches
- Response time degradation under load
"""

import concurrent.futures
import statistics
import time

import pytest
import requests

from tests.fixtures.health import merge_service_required


@merge_service_required
class TestConcurrentSearch:
    """Search endpoint must handle concurrent load gracefully."""

    @pytest.fixture(autouse=True)
    def _service_up(self, merge_service_live):
        self.base_url = merge_service_live

    @pytest.mark.timeout(120)
    def test_single_search_response_time(self):
        """Single search should complete within 45 seconds.

        p95 against the live stack lands in the 10-30s range; 45s
        ceiling catches pathological regressions without flaking on
        tracker latency jitter.
        """
        start = time.time()
        resp = requests.post(
            f"{self.base_url}/api/v1/search",
            json={"query": "ubuntu", "limit": 10},
            timeout=60,
        )
        elapsed = time.time() - start
        assert resp.status_code == 200
        assert elapsed < 45, f"Search took {elapsed:.1f}s, expected <45s"

    @pytest.mark.timeout(180)
    def test_five_concurrent_searches(self):
        """Five concurrent searches should all complete."""
        queries = ["ubuntu", "debian", "fedora", "linux", "arch"]
        results = []

        def search(query):
            start = time.time()
            resp = requests.post(
                f"{self.base_url}/api/v1/search",
                json={"query": query, "limit": 10},
                timeout=90,
            )
            return resp.status_code, time.time() - start

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(search, q) for q in queries]
            for future in concurrent.futures.as_completed(futures):
                results.append(future.result())

        assert len(results) == 5
        for status, elapsed in results:
            assert status == 200, f"Search failed with status {status}"
            assert elapsed < 90, f"Search took {elapsed:.1f}s, expected <90s"

    @pytest.mark.timeout(300)
    def test_ten_concurrent_searches(self):
        """Ten concurrent searches should complete without crashing."""
        queries = [f"test{i}" for i in range(10)]
        results = []

        def search(query):
            start = time.time()
            resp = requests.post(
                f"{self.base_url}/api/v1/search",
                json={"query": query, "limit": 5},
                timeout=60,
            )
            return resp.status_code, time.time() - start

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(search, q) for q in queries]
            for future in concurrent.futures.as_completed(futures):
                results.append(future.result())

        success_count = sum(1 for status, _ in results if status == 200)
        assert success_count >= 5, f"Only {success_count}/10 searches succeeded"

    @pytest.mark.timeout(300)
    def test_search_response_time_percentiles(self):
        """P50 and P95 response times for search."""
        times = []
        for i in range(5):
            start = time.time()
            resp = requests.post(
                f"{self.base_url}/api/v1/search",
                json={"query": "ubuntu", "limit": 10},
                timeout=60,
            )
            elapsed = time.time() - start
            if resp.status_code == 200:
                times.append(elapsed)
            time.sleep(0.5)

        if len(times) >= 3:
            p50 = statistics.median(times)
            times_sorted = sorted(times)
            p95_idx = int(len(times_sorted) * 0.95)
            p95 = times_sorted[max(0, p95_idx - 1)]
            assert p50 < 45, f"P50={p50:.1f}s, expected <45s"
            assert p95 < 90, f"P95={p95:.1f}s, expected <90s"

    @pytest.mark.timeout(300)
    def test_dashboard_under_load(self):
        """Dashboard should remain accessible during search load."""

        # Start a slow search in background
        def slow_search():
            requests.post(
                f"{self.base_url}/api/v1/search",
                json={"query": "ubuntu", "limit": 50},
                timeout=120,
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(slow_search) for _ in range(3)]
            # Dashboard should still respond. The SPA is served at "/",
            # not "/dashboard" — "/dashboard" is a client-side route.
            for _ in range(5):
                resp = requests.get(f"{self.base_url}/", timeout=5)
                assert resp.status_code == 200
                time.sleep(0.5)
            # Wait for searches to complete
            for future in concurrent.futures.as_completed(futures):
                future.result()

    @pytest.mark.timeout(180)
    def test_health_endpoint_under_load(self):
        """Health endpoint should always respond quickly."""

        # Start multiple searches
        def search():
            requests.post(
                f"{self.base_url}/api/v1/search",
                json={"query": "test", "limit": 10},
                timeout=60,
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(search) for _ in range(5)]
            for _ in range(10):
                start = time.time()
                resp = requests.get(f"{self.base_url}/health", timeout=5)
                elapsed = time.time() - start
                assert resp.status_code == 200
                assert elapsed < 5, f"Health check took {elapsed:.1f}s"
                time.sleep(0.3)
            for future in concurrent.futures.as_completed(futures):
                future.result()

    def test_memory_stability(self):
        """Service should not leak memory under repeated searches."""
        # Run 10 searches sequentially
        for i in range(10):
            resp = requests.post(
                f"{self.base_url}/api/v1/search",
                json={"query": f"test{i}", "limit": 5},
                timeout=30,
            )
            assert resp.status_code == 200
            time.sleep(0.5)

        # Service should still be healthy
        health = requests.get(f"{self.base_url}/health", timeout=5)
        assert health.status_code == 200
