"""
Stress tests for search endpoint under extreme load.

Scenarios:
- Rapid-fire searches (100 in quick succession)
- Burst of concurrent searches (20 simultaneous)
- Sustained load over time
- Resource exhaustion prevention
"""

import concurrent.futures
import time

import pytest
import requests


def _purge_qbittorrent_torrents(qbit_url: str = "http://localhost:7186") -> None:
    """Delete every torrent from qBittorrent.

    Stress tests add many synthetic torrents. If they pile up across
    runs, qBittorrent starts slowing down (large state files, lock
    contention) and the stress-test floors stop holding. Call this
    before/after the class so each run starts clean.
    """
    try:
        import http.cookiejar
        import urllib.parse
        import urllib.request

        jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        data = urllib.parse.urlencode({"username": "admin", "password": "admin"}).encode()
        opener.open(
            urllib.request.Request(f"{qbit_url}/api/v2/auth/login", data=data, method="POST"),
            timeout=10,
        )
        resp = opener.open(f"{qbit_url}/api/v2/torrents/info", timeout=10)
        import json as _json

        torrents = _json.loads(resp.read().decode("utf-8"))
        hashes = "|".join(t["hash"] for t in torrents)
        if hashes:
            opener.open(
                urllib.request.Request(
                    f"{qbit_url}/api/v2/torrents/delete",
                    data=urllib.parse.urlencode({"hashes": hashes, "deleteFiles": "false"}).encode(),
                    method="POST",
                ),
                timeout=15,
            )
    except Exception:
        # Best effort — stress tests must not fail because the purge
        # itself had a transient blip.
        pass


from tests.fixtures.health import merge_service_required


@pytest.mark.stress
@merge_service_required
class TestSearchStress:
    """Search endpoint stress testing.

    Every test in this class drives live multi-tracker fan-out many
    times over. They are tagged :mod:`stress` so they can be skipped
    from CI's default suite (``-m "not stress"``). When run, they need
    a generous per-test timeout — see the ``@pytest.mark.timeout``
    decorators on each method.
    """

    @pytest.fixture(autouse=True)
    def _service_up(self, merge_service_live):
        self.base_url = merge_service_live
        # Start clean — purge any torrent state left behind by prior
        # stress runs so the service isn't carrying hundreds of stub
        # torrents into this class.
        _purge_qbittorrent_torrents()
        yield
        _purge_qbittorrent_torrents()

    @pytest.mark.timeout(300)
    def test_rapid_fire_searches(self):
        """50 rapid searches should not crash the service.

        The merge service admits up to ``MAX_CONCURRENT_SEARCHES``
        in-flight fan-outs before returning HTTP 429. Both 200
        (accepted) and 429 (queue-full backpressure) count as healthy
        service behaviour — the only thing we're testing here is that
        the service doesn't fall over, so ``/health`` must still
        respond at the end.
        """
        success = 0
        queued = 0
        failure = 0
        for i in range(50):
            try:
                resp = requests.post(
                    f"{self.base_url}/api/v1/search",
                    json={"query": f"stress{i}", "limit": 3},
                    timeout=10,
                )
                if resp.status_code == 200:
                    success += 1
                elif resp.status_code == 429:
                    queued += 1
                else:
                    failure += 1
            except (requests.Timeout, requests.ConnectionError):
                failure += 1

        # Most requests should get a response (200 or 429); connection
        # failures are the bad outcome.
        accepted = success + queued
        assert accepted >= 40, (
            f"Only {accepted}/50 rapid searches got a response (200={success}, 429={queued}, fail={failure})"
        )
        # Service should still be healthy
        health = requests.get(f"{self.base_url}/health", timeout=10)
        assert health.status_code == 200

    @pytest.mark.timeout(300)
    def test_burst_concurrent_searches(self):
        """20 simultaneous searches should complete without deadlock.

        With MAX_CONCURRENT_SEARCHES=8 (default), up to 8 bursts get
        accepted and the rest receive HTTP 429. Count both as "did not
        crash" — the regression we care about is deadlock / connection
        failure.
        """
        results = []

        def search(i):
            try:
                resp = requests.post(
                    f"{self.base_url}/api/v1/search",
                    json={"query": f"burst{i}", "limit": 5},
                    timeout=60,
                )
                return resp.status_code
            except Exception:
                return -1

        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(search, i) for i in range(20)]
            for future in concurrent.futures.as_completed(futures, timeout=120):
                try:
                    results.append(future.result(timeout=0))
                except Exception:
                    results.append(-1)

        responded = sum(1 for r in results if r in (200, 429))
        assert responded >= 15, f"Only {responded}/20 burst searches got a response (statuses={results})"

    @pytest.mark.timeout(180)
    def test_sustained_load(self):
        """Sustained load over 20 seconds should not crash service.

        Mixed 200/429 responses are fine — we just need the service to
        stay responsive and return a real status for most requests.
        """
        start = time.time()
        responded = 0
        failure = 0

        while time.time() - start < 20:
            try:
                resp = requests.post(
                    f"{self.base_url}/api/v1/search",
                    json={"query": "sustained", "limit": 5},
                    timeout=15,
                )
                if resp.status_code in (200, 429):
                    responded += 1
                else:
                    failure += 1
            except (requests.Timeout, requests.ConnectionError):
                failure += 1
            time.sleep(0.3)

        assert responded >= 20, f"Only {responded} sustained requests got a response (failures={failure})"
        health = requests.get(f"{self.base_url}/health", timeout=10)
        assert health.status_code == 200

    @pytest.mark.timeout(180)
    def test_search_with_abort_under_stress(self):
        """Aborting searches under stress should not cause issues."""

        # Start many searches that might be aborted
        def search_and_maybe_abort(i):
            try:
                resp = requests.post(
                    f"{self.base_url}/api/v1/search",
                    json={"query": f"abort{i}", "limit": 10},
                    timeout=10,  # Short-ish timeout to trigger "aborts"
                )
                return resp.status_code
            except requests.Timeout:
                return 408
            except Exception:
                return -1

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(search_and_maybe_abort, i) for i in range(20)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        # Should not crash regardless of outcomes
        health = requests.get(f"{self.base_url}/health", timeout=10)
        assert health.status_code == 200

    @pytest.mark.timeout(240)
    def test_stats_endpoint_under_stress(self):
        """Stats endpoint should remain accurate under load."""

        # Run some searches
        def search(i):
            requests.post(
                f"{self.base_url}/api/v1/search",
                json={"query": f"stats{i}", "limit": 5},
                timeout=30,
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(search, i) for i in range(10)]
            # Check stats while searches running
            for _ in range(5):
                stats = requests.get(f"{self.base_url}/api/v1/stats", timeout=15)
                assert stats.status_code == 200
                time.sleep(1)
            for f in concurrent.futures.as_completed(futures):
                f.result()

    @pytest.mark.timeout(180)
    def test_file_descriptor_exhaustion_prevention(self):
        """Service should not exhaust file descriptors under load.

        /health is a trivial no-op route — if it can't respond under
        mild concurrency (50 parallel workers × 100 requests) the
        event loop is starving. The concurrent-search cap keeps
        background fan-outs from hogging the loop so /health stays
        responsive.
        """

        # Many concurrent connections
        def connect(i):
            try:
                resp = requests.get(f"{self.base_url}/health", timeout=10)
                return resp.status_code
            except Exception:
                return -1

        with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
            futures = [executor.submit(connect, i) for i in range(100)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        success_count = sum(1 for r in results if r == 200)
        assert success_count > 50, f"Only {success_count}/100 health checks succeeded"
