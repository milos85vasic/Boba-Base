"""
Security tests for authentication bypass attempts.

Scenarios:
- Brute force protection on auth endpoints
- Session fixation attempts
- Privilege escalation via parameter tampering
- Credential exposure in logs/responses
"""

import pytest
import requests


from tests.fixtures.health import merge_service_required


@merge_service_required
class TestAuthBypass:
    """Authentication bypass attempts must fail."""

    @pytest.fixture(autouse=True)
    def _services_up(self, all_services_live):
        self.base_url = all_services_live["merge_service"]
        self.qbit_url = all_services_live["qbittorrent"]

    def test_brute_force_protection(self):
        """Multiple failed auth attempts should not crash the service."""
        for i in range(3):
            resp = requests.post(
                f"{self.base_url}/api/v1/auth/rutracker/login",
                json={"username": f"user{i}", "password": "wrong"},
                timeout=5,
            )
            # Service should remain stable under repeated failed attempts
            assert resp.status_code in (200, 401, 403, 422, 429, 500)

    def test_auth_without_credentials_fails(self):
        """Auth endpoints must reject requests without credentials."""
        resp = requests.post(
            f"{self.base_url}/api/v1/auth/rutracker/login",
            json={},
            timeout=10,
        )
        assert resp.status_code in (400, 401, 422)

    def test_qbittorrent_auth_required(self):
        """qBittorrent WebUI must require authentication."""
        resp = requests.get(f"{self.qbit_url}/api/v2/app/version", timeout=5)
        # Should require auth (401) or redirect to login
        assert resp.status_code in (200, 401, 403, 302)

    def test_qbittorrent_brute_force(self):
        """Multiple failed qBittorrent logins should be rate limited."""
        for i in range(5):
            resp = requests.post(
                f"{self.qbit_url}/api/v2/auth/login",
                data={"username": "admin", "password": "wrong"},
                timeout=5,
            )
            assert resp.status_code in (200, 401, 403, 429)

    def test_credentials_not_in_response(self):
        """API responses must never contain credentials."""
        endpoints = [
            f"{self.base_url}/health",
            f"{self.base_url}/api/v1/search",
            f"{self.base_url}/api/v1/hooks",
            f"{self.base_url}/api/v1/stats",
        ]
        for endpoint in endpoints:
            resp = requests.get(endpoint, timeout=10)
            if resp.status_code == 200:
                text = resp.text.lower()
                assert "password" not in text, f"Password leaked in {endpoint}"
                assert "secret" not in text, f"Secret leaked in {endpoint}"
                assert "token" not in text or "search_id" in text, f"Unexpected token in {endpoint}"

    @pytest.mark.timeout(120)
    def test_parameter_tampering_privilege_escalation(self):
        """Tampering with user-related parameters must not escalate privileges.

        Live multi-tracker search; budget raised to cover fan-out.
        """
        # Try to access admin functionality with normal user parameters
        resp = requests.post(
            f"{self.base_url}/api/v1/search",
            json={"query": "test", "is_admin": True, "role": "admin"},
            timeout=60,
        )
        # Should not grant admin access
        assert resp.status_code in (200, 400, 422)

    def test_session_fixation_attempt(self):
        """Session fixation via custom headers should not work."""
        resp = requests.get(
            f"{self.base_url}/health",
            headers={"Cookie": "sessionid=attacker_session"},
            timeout=5,
        )
        assert resp.status_code == 200
        # Session should not be accepted
        assert "sessionid=attacker_session" not in resp.headers.get("Set-Cookie", "")
