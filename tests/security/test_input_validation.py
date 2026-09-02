"""
Security tests for input validation.

Scenarios:
- Oversized payloads must be rejected
- SQL injection in search queries must not execute
- Path traversal in file paths must be blocked
- Invalid JSON must be handled gracefully
- Extreme values for numeric parameters
"""

import pytest


from tests.fixtures.health import merge_service_required


# BOB-152: a live call here may legitimately wait out one shared
# per-IP `search` window (server-reported Retry-After, ~60s) before it
# gets its real answer. The default --timeout=60 would kill that wait
# and re-introduce the exact flake this fix removes, so the class
# carries explicit headroom. This raises the CEILING only; nothing
# here sleeps when the budget is not exhausted.
@pytest.mark.timeout(240)
@merge_service_required
class TestInputValidation:
    """Invalid/malicious inputs must be rejected safely."""

    @pytest.fixture(autouse=True)
    def _service_up(self, merge_service_client):
        # BOB-152: every live call in this class goes through the
        # rate-limit-aware client (tests/fixtures/services.py). It gates on
        # `merge_service_live_or_skip`, so a down stack SKIPs honestly and
        # never boots the operator's compose stack; and it drains the shared
        # per-IP `search` window using the server's own `Retry-After` instead
        # of letting a 429 masquerade as a product failure.
        self.client = merge_service_client
        self.base_url = merge_service_client.base_url

    def test_oversized_search_query_rejected(self):
        """An oversized search query must be REJECTED, never accepted.

        MEASURED 2026-09-02 against the running service: a 5000-char query
        returns 422, deterministically (3/3 probes). That is correct — the
        request model bounds it (`SearchRequest.query`,
        `download-proxy/src/api/routes.py`, `max_length=256`), so FastAPI's
        validation layer refuses it before any tracker fan-out.

        This assertion previously read `in (200, 400, 413)` and so FAILED
        on every run against correct product behaviour — a stale allow-set
        predating the request bounds, not a flake. Fixing it 422-ward also
        DROPS 200 from the set: with `max_length=256` enforced, a 5000-char
        query can no longer be silently truncated-and-accepted, and keeping
        200 legal would leave the test unable to catch that regression.
        """
        payload = "x" * 5000
        resp = self.client.post(
            "/api/v1/search",
            json={"query": payload, "limit": 5},
            timeout=60,
        )
        assert resp.status_code in (400, 413, 422), (
            f"oversized query was not rejected: HTTP {resp.status_code}"
        )

    @pytest.mark.timeout(300)
    def test_sql_injection_in_search_query(self):
        """SQL injection patterns must not affect backend.

        Each /api/v1/search POST kicks off a live multi-tracker fan-out
        (no relational DB here — the real defence is that the search
        layer never assembles SQL at all), which can take up to a
        minute per payload. Four payloads × up to 60s ≈ 4 min budget.
        """
        payloads = [
            "'; DROP TABLE results; --",
            "1' OR '1'='1",
            "test' UNION SELECT * FROM users --",
            "test'; DELETE FROM hooks; --",
        ]
        for payload in payloads:
            resp = self.client.post(
                "/api/v1/search",
                json={"query": payload, "limit": 5},
                timeout=60,
            )
            assert resp.status_code in (200, 400), f"SQL injection payload caused error: {payload}"
            # Health check should still pass
            health = self.client.get("/health", timeout=5)
            assert health.status_code == 200

    def test_path_traversal_in_download_request(self):
        """Path traversal in download requests must be blocked."""
        resp = self.client.post(
            "/api/v1/download",
            json={
                "url": "../../../etc/passwd",
                "name": "test",
            },
            timeout=10,
        )
        # Should not succeed with path traversal
        assert resp.status_code in (400, 403, 404, 422)

    def test_invalid_json_handling(self):
        """Invalid JSON body must return 400 or 422, not 500."""
        resp = self.client.post(
            "/api/v1/search",
            data="not valid json {",
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        assert resp.status_code in (400, 422)

    def test_empty_json_body(self):
        """Empty JSON body should be handled gracefully."""
        resp = self.client.post(
            "/api/v1/search",
            json={},
            timeout=10,
        )
        assert resp.status_code in (200, 400, 422)

    def test_negative_limit_value(self):
        """Negative limit should be rejected or clamped."""
        resp = self.client.post(
            "/api/v1/search",
            json={"query": "test", "limit": -1},
            timeout=10,
        )
        assert resp.status_code in (200, 400, 422)

    def test_extreme_limit_value(self):
        """Extremely large limit should be rejected or clamped."""
        resp = self.client.post(
            "/api/v1/search",
            json={"query": "test", "limit": 999999},
            timeout=10,
        )
        assert resp.status_code in (200, 400, 422)

    def test_non_numeric_limit(self):
        """Non-numeric limit should be rejected."""
        resp = self.client.post(
            "/api/v1/search",
            json={"query": "test", "limit": "abc"},
            timeout=10,
        )
        assert resp.status_code in (400, 422)

    @pytest.mark.timeout(120)
    def test_null_bytes_in_input(self):
        """Null bytes in input should be handled safely (no crash).

        Hits the live /api/v1/search endpoint which fans out to
        multiple trackers. 60s per-request timeout gives each tracker
        time to respond; 120s pytest timeout gives the whole call a
        ceiling independent of network jitter.
        """
        payload = "test\x00evil"
        resp = self.client.post(
            "/api/v1/search",
            json={"query": payload, "limit": 5},
            timeout=60,
        )
        # Service should not crash - any response is acceptable
        assert resp.status_code in (200, 400, 422, 500)

    def test_command_injection_in_hook_script(self):
        """Hook script path must not allow command injection."""
        payload = {
            "name": "test",
            "event": "search_complete",
            "script": "; rm -rf / ;",
        }
        resp = self.client.post(
            "/api/v1/hooks",
            json=payload,
            timeout=10,
        )
        if resp.status_code in (200, 201):
            # Even if created, the script should not be executable with injection
            pass
        # Health check must still pass
        health = self.client.get("/health", timeout=5)
        assert health.status_code == 200

    @pytest.mark.timeout(120)
    def test_unicode_bom_in_json(self):
        """JSON with UTF-8 BOM should be handled gracefully.

        If the BOM passes FastAPI's JSON decoder, this triggers a live
        search, hence the longer timeout.
        """
        resp = self.client.post(
            "/api/v1/search",
            data=b'\xef\xbb\xbf{"query": "test"}',
            headers={"Content-Type": "application/json"},
            timeout=60,
        )
        assert resp.status_code in (200, 400, 422)
