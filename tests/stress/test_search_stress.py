"""
Stress tests for search endpoint under extreme load.

Scenarios:
- Rapid-fire searches (100 in quick succession)
- Burst of concurrent searches (20 simultaneous)
- Sustained load over time
- Resource exhaustion prevention
"""

import concurrent.futures
import http.cookiejar
import json as _json
import sys
import time
import urllib.parse
import urllib.request

import pytest
import requests

QBIT_PROXY_URL = "http://localhost:7186"


# ---------------------------------------------------------------------------
# DIFF-SCOPED TEARDOWN (§11.4.14 / §9 data safety) — rewritten 2026-09-01.
#
# WHAT WAS HERE BEFORE, AND WHY IT WAS A DATA-SAFETY DEFECT:
# `_purge_qbittorrent_torrents()` listed EVERY torrent in the instance and
# deleted the whole list, from an autouse fixture running before AND after
# every test in the class. On the operator's live instance that silently
# de-registered their entire library. `deleteFiles=false` meant the bytes on
# disk survived, but the session, categories, tags, ratio history and seeding
# state did not — none of which the operator can get back from the files.
#
# THE RULE NOW: a test may only remove what that test ADDED.
#   before = snapshot()          # taken while the class is still pristine
#   ... tests run, may add torrents ...
#   added  = snapshot() - before # exactly this suite's own debris
#   delete(added)                # never a hash present in `before`
# This is the same shape `tests/integration/test_webui_bridge_auth_live.py`
# already uses (`added = _torrent_hashes(...) - before`); it is reused rather
# than reinvented (§11.4.251 — a second divergent copy is how the two
# `_qbit_add_succeeded` implementations drifted into opposite verdicts).
#
# CONSERVATIVE-SAFE DEFAULT ON A BLIND READ (§11.4.201(4)):
# if the BEFORE snapshot could not be taken, `before` is None and the teardown
# DELETES NOTHING. A reader that cannot see the baseline cannot compute a diff,
# and `None - anything` must never degrade into "everything". Leaving debris is
# recoverable; deleting the operator's library is not.
#
# LOUD, NEVER SILENT (§11.4.201(6)):
# the old `except Exception: pass` meant a cleanup that stopped working
# re-accumulated state with nothing observing it — the exact invisibility that
# let eighteen stray tags pile up unnoticed (see
# scripts/pre_build/check_cm_no_test_tag_debris.sh). Every failure below names
# what it could not do, on stderr, with the hashes involved.
#
# WHY A FAILED PURGE DOES NOT FAIL THE TEST:
# the purge is teardown, not the unit under test. Raising here would fail a run
# for a script-internal reason rather than a product defect — a §11.4.1
# FAIL-bluff — and, worse, would mask a genuine product FAIL behind a cleanup
# error. The blocking observer is the independent pre-build gate
# `scripts/pre_build/check_cm_no_unscoped_live_destruction.sh`, which reads the
# source rather than trusting the cleanup code that is supposed to have run.
# ---------------------------------------------------------------------------


def _qbit_opener(qbit_url: str):
    """Authenticated urllib opener, or None with a named reason on stderr."""
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    data = urllib.parse.urlencode({"username": "admin", "password": "admin"}).encode()
    try:
        opener.open(
            urllib.request.Request(f"{qbit_url}/api/v2/auth/login", data=data, method="POST"),
            timeout=10,
        )
    except Exception as exc:
        print(f"[stress-cleanup] could not authenticate to {qbit_url}: {exc!r}", file=sys.stderr)
        return None
    return opener


def _snapshot_torrent_hashes(qbit_url: str = QBIT_PROXY_URL):
    """Set of infohashes currently in the instance, or None if unreadable.

    None is load-bearing: it is NOT an empty set. A caller that receives None
    must refuse to delete (see `_purge_added_torrents`).
    """
    opener = _qbit_opener(qbit_url)
    if opener is None:
        return None
    try:
        resp = opener.open(f"{qbit_url}/api/v2/torrents/info", timeout=10)
        rows = _json.loads(resp.read().decode("utf-8") or "[]")
        return {t["hash"] for t in rows}
    except Exception as exc:
        print(f"[stress-cleanup] could not read torrents/info: {exc!r}", file=sys.stderr)
        return None


def _purge_added_torrents(before, qbit_url: str = QBIT_PROXY_URL) -> None:
    """Delete ONLY the torrents that appeared since `before` was taken."""
    if before is None:
        print(
            "[stress-cleanup] REFUSING to purge: the baseline snapshot was "
            "unreadable, so this suite's own additions cannot be told apart "
            "from the operator's torrents. Nothing was deleted.",
            file=sys.stderr,
        )
        return

    after = _snapshot_torrent_hashes(qbit_url)
    if after is None:
        print(
            "[stress-cleanup] could not re-read torrents/info at teardown — "
            "nothing deleted; any torrents this suite added are still present.",
            file=sys.stderr,
        )
        return

    added = after - before
    if not added:
        return

    opener = _qbit_opener(qbit_url)
    if opener is None:
        print(
            f"[stress-cleanup] {len(added)} torrent(s) added by this suite were "
            f"NOT removed (login failed): {sorted(added)}",
            file=sys.stderr,
        )
        return
    try:
        opener.open(
            urllib.request.Request(
                f"{qbit_url}/api/v2/torrents/delete",
                # deleteFiles stays false: this suite never owns files on disk,
                # and a scoping bug must never escalate into data loss.
                data=urllib.parse.urlencode(
                    {"hashes": "|".join(sorted(added)), "deleteFiles": "false"}
                ).encode(),
                method="POST",
            ),
            timeout=15,
        )
    except Exception as exc:
        print(
            f"[stress-cleanup] delete FAILED for {len(added)} torrent(s) this "
            f"suite added: {sorted(added)} — {exc!r}",
            file=sys.stderr,
        )


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
        # Record the instance as we found it. Everything present here is the
        # operator's and is NEVER touched; only what appears afterwards is
        # this suite's own debris. A snapshot that could not be read is None,
        # and a None baseline disarms the teardown entirely.
        before = _snapshot_torrent_hashes()
        yield
        _purge_added_torrents(before)

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
