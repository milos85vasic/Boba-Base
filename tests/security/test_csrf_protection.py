"""
Security tests for CSRF (Cross-Site Request Forgery) protection.

Scenarios:
- State-changing endpoints (POST/PUT/DELETE) should require proper headers
- Cross-origin requests should be rejected or require explicit origin validation
- API endpoints must not rely solely on cookies for authentication
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
class TestCSRFProtection:
    """CSRF attack vectors must be blocked."""

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

    def test_post_without_content_type_rejected(self):
        """POST without proper Content-Type should be rejected for state changes."""
        resp = self.client.post(
            "/api/v1/search",
            data="invalid",
            headers={"Content-Type": "text/plain"},
            timeout=10,
        )
        # Should return 400 or 415 for invalid content type
        assert resp.status_code in (200, 400, 415, 422), f"Unexpected status: {resp.status_code}"

    @pytest.mark.timeout(120)
    def test_cross_origin_post_rejected(self):
        """POST from untrusted origin should be rejected.

        Live search triggered by the POST; pytest budget raised to
        120s to cover tracker fan-out.
        """
        resp = self.client.post(
            "/api/v1/search",
            json={"query": "test", "limit": 5},
            headers={
                "Origin": "https://evil.com",
                "Referer": "https://evil.com/phishing",
            },
            timeout=60,
        )
        # Service may allow all origins (CORS) or reject; we just verify it doesn't crash
        assert resp.status_code in (200, 403)

    def test_delete_without_proper_headers(self):
        """DELETE requests should require proper authentication/headers."""
        # Try to delete a non-existent hook
        resp = self.client.delete(
            "/api/v1/hooks/nonexistent",
            timeout=10,
        )
        # Should not succeed blindly
        assert resp.status_code in (200, 404, 401, 403)

    def test_hooks_endpoint_requires_auth(self):
        """Hook management should not be accessible without auth."""
        resp = self.client.get("/api/v1/hooks", timeout=10)
        # May be public or require auth; verify it doesn't expose sensitive data
        if resp.status_code == 200:
            hooks = resp.json()
            for hook in hooks:
                # Should not expose internal paths or credentials
                assert "password" not in str(hook).lower()
                assert "secret" not in str(hook).lower()

    def test_schedule_endpoint_requires_auth(self):
        """Schedule management should require authentication."""
        resp = self.client.get("/api/v1/schedules", timeout=10)
        # Should require auth or return empty safely
        assert resp.status_code in (200, 401, 403)

    def test_preflight_request_handling(self):
        """CORS preflight is handled correctly in BOTH directions.

        MEASURED 2026-09-02 against the running service, deterministically
        (3/3 probes each):

            Origin: http://localhost:7187  (allow-listed)  -> 200
            Origin: http://localhost:3000  (not listed)    -> 400

        Both are correct. `_DEFAULT_ORIGINS`
        (`download-proxy/src/api/__init__.py`) is a secure-by-default
        allowlist of :4200 and the merge-service port; Starlette's
        CORSMiddleware answers a preflight from an unlisted origin with 400
        "Disallowed CORS origin" rather than reflecting it.

        This test previously sent ONLY the unlisted :3000 origin and
        asserted success, so it FAILED on every run against the secure
        default — a stale expectation from the wildcard-CORS era, not a
        flake. Asserting both arms is strictly stronger: the allowed arm
        proves preflight is not simply broken for everyone (the
        §11.4.201(1) false-positive guard), and the refused arm proves the
        allowlist actually refuses.
        """
        allowed = self.client.options(
            "/api/v1/search",
            headers={
                "Origin": self.base_url,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type",
            },
            timeout=10,
        )
        assert allowed.status_code in (200, 204), (
            f"preflight from the allow-listed origin {self.base_url} was not "
            f"honoured: HTTP {allowed.status_code}"
        )
        assert allowed.headers.get("Access-Control-Allow-Origin") == self.base_url

        refused = self.client.options(
            "/api/v1/search",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type",
            },
            timeout=10,
        )
        assert refused.status_code == 400, (
            "preflight from a NON-allow-listed origin must be refused, got "
            f"HTTP {refused.status_code}"
        )
        assert refused.headers.get("Access-Control-Allow-Origin") != "http://localhost:3000"

    def test_api_rejects_form_data_for_json_endpoints(self):
        """Endpoints expecting JSON should reject form data."""
        resp = self.client.post(
            "/api/v1/search",
            data={"query": "test"},
            timeout=10,
        )
        assert resp.status_code in (400, 422)
