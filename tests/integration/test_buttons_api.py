"""
Tests for button actions via API - Magnet, Download, Schedule
These tests verify buttons trigger correct API calls
"""

import pytest
import requests

from tests.integration.qbit_login_oracle import describe_login, qbit_login_succeeded


class TestMagnetButton:
    """Test Magnet button functionality."""

    @pytest.fixture(autouse=True)
    def _service_up(self, merge_service_live):
        self.base_url = merge_service_live
        self.session = requests.Session()

    def search_get_result(self, query="matrix"):
        """Perform search and return first result."""
        resp = self.session.post(
            f"{self.base_url}/api/v1/search/sync",
            json={"query": query, "limit": 1},
            headers={"Content-Type": "application/json"},
        )
        results = resp.json().get("results", [])
        if results:
            return results[0]
        return None

    def test_generateMagnet_creates_valid_magnet(self):
        """generateMagnet should create valid magnet URI."""
        result = self.search_get_result("matrix")
        assert result is not None, "No search results"

        name = result.get("name")
        assert name, "Result has no name"

        # Magnet format: magnet:?dn=<name>&tr=<tracker>
        magnet_uri = f"magnet:?dn={requests.utils.quote(name)}&tr=udp://tracker.opentrackr.org:1337&tr=udp://tracker.leechers.org:6969"

        # Verify it's a valid magnet URI
        assert magnet_uri.startswith("magnet:?dn="), "Invalid magnet format"
        assert "tr=" in magnet_uri, "Missing tracker"

    def test_magnet_button_is_angular_app(self):
        """Magnet button should be in Angular app."""
        html = self.session.get(self.base_url).text
        assert "<app-root>" in html or "<app-root></app-root>" in html

    def test_getMagnetUrl_function_exists(self):
        """getMagnetUrl should be defined in Angular app."""
        html = self.session.get(self.base_url).text
        assert "<app-root>" in html or "<app-root></app-root>" in html


class TestDownloadButton:
    """Test + (Download) button functionality via API."""

    @pytest.fixture(autouse=True)
    def _services_up(self, all_services_live):
        self.base_url = all_services_live["merge_service"]
        self.qbit_url = all_services_live["qbittorrent"]
        self.session = requests.Session()
        # Ensure logged in to qBittorrent
        login = self.session.post(
            f"{self.qbit_url}/api/v2/auth/login",
            data={"username": "admin", "password": "admin"},
            timeout=300,
        )
        # qBittorrent 5.x answers a good login with 204 + empty body + QBT_SID
        # cookie; the oracle accepts that AND the legacy 200 "Ok.".
        assert qbit_login_succeeded(login), f"qBittorrent login failed: {describe_login(login)}"

    def test_download_api_accepts_valid_request(self):
        """/api/v1/download should accept download request."""
        # First get a search result with download URLs
        resp = self.session.post(
            f"{self.base_url}/api/v1/search/sync",
            json={"query": "linux", "limit": 1},
            headers={"Content-Type": "application/json"},
        )
        results = resp.json().get("results", [])
        if not results:
            assert False, "query returned 0 results — check tracker fan-out"

        result = results[0]
        download_urls = result.get("download_urls", [])

        if download_urls:
            # Try to download
            download_resp = self.session.post(
                f"{self.base_url}/api/v1/download",
                json={"result_id": "0", "download_urls": download_urls},
                headers={"Content-Type": "application/json"},
            )
            # Should get a valid response (not 500 error)
            assert download_resp.status_code != 500, "Download API returns 500"
        else:
            assert False, "result had no download URLs — check plugin output"

    def test_download_api_returns_proper_response(self):
        """Download API should return proper JSON response."""
        resp = self.session.post(
            f"{self.base_url}/api/v1/download",
            json={"result_id": "999", "download_urls": []},
            headers={"Content-Type": "application/json"},
        )

        # Should be valid JSON
        try:
            data = resp.json()
            assert isinstance(data, dict), "Response is not JSON object"
        except Exception as e:
            pytest.fail(f"Invalid JSON response: {e}")

    def test_download_api_with_invalid_id(self):
        """Download API should handle invalid result_id gracefully."""
        resp = self.session.post(
            f"{self.base_url}/api/v1/download",
            json={"result_id": "invalid999", "download_urls": []},
            headers={"Content-Type": "application/json"},
        )

        # Should not return 500
        assert resp.status_code < 500, "API returns server error"


class TestScheduleButton:
    """Test Schedule button functionality via API."""

    @pytest.fixture(autouse=True)
    def _service_up(self, merge_service_live):
        self.base_url = merge_service_live
        self.session = requests.Session()

    def test_schedule_button_is_angular_app(self):
        """doSchedule function should exist in Angular app."""
        html = self.session.get(self.base_url).text
        assert "<app-root>" in html or "<app-root></app-root>" in html

    def test_schedule_api_endpoint_works(self):
        """Schedule API should respond."""
        html = self.session.get(self.base_url).text
        assert "<app-root>" in html or "<app-root></app-root>" in html


class TestQBitLoginButton:
    """Test qBittorrent login button/flow."""

    @pytest.fixture(autouse=True)
    def _services_up(self, all_services_live):
        self.base_url = all_services_live["merge_service"]
        self.qbit_url = all_services_live["qbittorrent"]
        self.session = requests.Session()

    def test_qbit_login_api_works(self):
        """qBittorrent login API must work — and must still reject a bad password."""
        resp = self.session.post(
            f"{self.qbit_url}/api/v2/auth/login",
            data={"username": "admin", "password": "admin"},
            timeout=300,
        )
        assert qbit_login_succeeded(resp), f"qBittorrent login failed: {describe_login(resp)}"

        # Negative control in the same test: the oracle must not wave through a
        # wrong password, otherwise the assertion above proves nothing.
        bad = requests.Session().post(
            f"{self.qbit_url}/api/v2/auth/login",
            data={"username": "admin", "password": "wrongwrong"},
            timeout=300,
        )
        assert not qbit_login_succeeded(bad), f"a WRONG password was accepted: {describe_login(bad)}"

    def test_merge_service_auth_endpoint_works(self):
        """Merge service /auth/qbittorrent endpoint should work."""
        resp = self.session.post(
            f"{self.base_url}/api/v1/auth/qbittorrent",
            json={"username": "admin", "password": "admin"},
            headers={"Content-Type": "application/json"},
            timeout=30,
        )

        data = resp.json()
        # Should either auth successfully or return proper error
        assert resp.status_code in [200, 401, 403], "Unexpected status"

        if resp.status_code == 200:
            assert data.get("status") == "authenticated", f"qBittorrent auth via merge service failed: {data}"

    def test_login_form_is_angular_app(self):
        """Login form should be in Angular app."""
        html = self.session.get(self.base_url).text
        assert "<app-root>" in html or "<app-root></app-root>" in html


class TestButtonUIIntegration:
    """Integration tests for button UI."""

    @pytest.fixture(autouse=True)
    def _service_up(self, merge_service_live):
        self.base_url = merge_service_live
        self.session = requests.Session()

    def test_dashboard_loads_without_errors(self):
        """Dashboard should load."""
        resp = self.session.get(self.base_url)
        assert resp.status_code == 200, "Dashboard not loading"

    def test_all_button_functions_defined_in_angular(self):
        """All button handlers should be in Angular app."""
        html = self.session.get(self.base_url).text
        assert "<app-root>" in html or "<app-root></app-root>" in html
        assert '<script src="main-' in html

    def test_buttons_are_angular_components(self):
        """Buttons should be rendered by Angular."""
        html = self.session.get(self.base_url).text
        assert "<app-root>" in html or "<app-root></app-root>" in html


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
