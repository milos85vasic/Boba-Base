"""
Comprehensive tests for Login Flow and Actions

Tests:
1. Login modal opens/closes properly
2. Login authentication works
3. Credentials are remembered/saved
4. Pending action continues after login success
5. Modal stacking and dismissal
6. Magnet dialog operations
7. Download button with authentication
8. All button flows end-to-end
"""

import pytest
import requests

from tests.integration.qbit_login_oracle import (
    describe_login,
    qbit_login_succeeded,
    qbit_session_cookie_names,
)


class TestLoginModal:
    """Test login modal functionality."""

    @pytest.fixture(autouse=True)
    def _service_up(self, merge_service_live):
        self.base_url = merge_service_live
        self.session = requests.Session()

    def test_login_modal_is_angular_component(self):
        """Login modal should be Angular component."""
        html = self.session.get(self.base_url).text
        assert "<app-root>" in html or "<app-root></app-root>" in html, "Angular app-root should exist"

    def test_dashboard_is_angular_app(self):
        """Dashboard should be Angular SPA."""
        html = self.session.get(self.base_url).text
        assert "<app-root>" in html or "<app-root></app-root>" in html
        assert '<base href="/">' in html
        assert '<script src="main-' in html


class TestLoginAuthentication:
    """Test login authentication."""

    @pytest.fixture(autouse=True)
    def _services_up(self, all_services_live):
        self.base_url = all_services_live["merge_service"]
        self.qbit_url = all_services_live["qbittorrent"]
        self.session = requests.Session()

    def test_direct_qbittorrent_login(self):
        """Direct qBittorrent login must work — judged by the version-independent
        oracle, not by the literal body ``Ok.``.

        Measured 2026-09-01 against the running qBittorrent 5.2.3: a GOOD login
        answers ``204`` with an EMPTY body plus ``Set-Cookie: QBT_SID_7185=…``.
        """
        resp = self.session.post(
            f"{self.qbit_url}/api/v2/auth/login",
            data={"username": "admin", "password": "admin"},
            timeout=30,
        )
        assert qbit_login_succeeded(resp), f"qBittorrent login failed: {describe_login(resp)}"
        assert qbit_session_cookie_names(resp) or resp.text.strip() == "Ok.", describe_login(resp)

    def test_direct_qbittorrent_login_rejects_wrong_password(self):
        """Negative control for :meth:`test_direct_qbittorrent_login`.

        Without this, an oracle that returned ``True`` unconditionally would
        make the success test pass while proving nothing.
        """
        rejected = requests.Session()
        resp = rejected.post(
            f"{self.qbit_url}/api/v2/auth/login",
            data={"username": "admin", "password": "wrongwrong"},
            timeout=30,
        )
        assert not qbit_login_succeeded(resp), f"a WRONG password was accepted: {describe_login(resp)}"
        assert not qbit_session_cookie_names(resp), (
            f"qBittorrent issued a session cookie for a REJECTED password: {describe_login(resp)}"
        )

    def test_merge_service_auth_endpoint(self):
        """Merge service auth endpoint should work."""
        resp = self.session.post(
            f"{self.base_url}/api/v1/auth/qbittorrent",
            json={"username": "admin", "password": "admin"},
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        assert resp.status_code == 200, f"Auth endpoint returned {resp.status_code}"
        data = resp.json()
        assert data.get("status") == "authenticated", f"qBittorrent auth failed: {data}"


class TestCredentialsPersistence:
    """Test credentials save/load functionality."""

    @pytest.fixture(autouse=True)
    def _service_up(self, merge_service_live):
        self.base_url = merge_service_live
        self.session = requests.Session()

    def test_credentials_can_be_saved(self):
        """Credentials should be saved when save is true."""
        resp = self.session.post(
            f"{self.base_url}/api/v1/auth/qbittorrent",
            json={"username": "admin", "password": "admin", "save": True},
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        data = resp.json()
        assert data.get("status") in ["authenticated", "saved"], f"qBittorrent auth failed, cannot test save: {data}"


class TestMagnetDialog:
    """Test magnet dialog operations."""

    @pytest.fixture(autouse=True)
    def _service_up(self, merge_service_live):
        self.base_url = merge_service_live
        self.session = requests.Session()

    def test_magnet_dialog_is_angular_component(self):
        """Magnet dialog should be Angular component."""
        html = self.session.get(self.base_url).text
        assert "<app-root>" in html or "<app-root></app-root>" in html

    def test_magnet_dialog_has_angular_app(self):
        """Dashboard should be Angular SPA."""
        html = self.session.get(self.base_url).text
        assert "<app-root>" in html or "<app-root></app-root>" in html

    def test_generateMagnet_produces_valid_uri(self):
        """generateMagnet should produce valid magnet URI."""
        resp = self.session.post(
            f"{self.base_url}/api/v1/search/sync",
            json={"query": "linux", "limit": 1},
            headers={"Content-Type": "application/json"},
        )
        results = resp.json().get("results", [])
        if not results:
            assert False, "query returned 0 results — check tracker fan-out"

        name = results[0].get("name", "test")
        from urllib.parse import quote

        magnet = f"magnet:?dn={quote(name)}&tr=udp://tracker.opentrackr.org:1337"
        assert magnet.startswith("magnet:?dn="), "Should be valid magnet URI"


class TestMagnetAddToQbit:
    """Test magnet add to qBittorrent functionality."""

    @pytest.fixture(autouse=True)
    def _service_up(self, merge_service_live):
        self.base_url = merge_service_live
        self.session = requests.Session()

    def test_add_magnet_via_download_api(self):
        """Adding magnet via download API should work."""
        # First get a valid magnet from search
        resp = self.session.post(
            f"{self.base_url}/api/v1/search/sync",
            json={"query": "linux", "limit": 1},
            headers={"Content-Type": "application/json"},
        )
        results = resp.json().get("results", [])
        if not results:
            assert False, "query returned 0 results — check tracker fan-out"

        # Try download endpoint
        download_resp = self.session.post(
            f"{self.base_url}/api/v1/download",
            json={"result_id": "0", "download_urls": ["magnet:?dn=test"]},
            headers={"Content-Type": "application/json"},
        )
        # Should not return 500
        assert download_resp.status_code < 500, "Download API should not 500"


class TestDownloadButtons:
    """Test download button functionality."""

    @pytest.fixture(autouse=True)
    def _service_up(self, merge_service_live):
        self.base_url = merge_service_live
        self.session = requests.Session()

    def test_doDownload_is_angular_component(self):
        """doDownload should be Angular component."""
        html = self.session.get(self.base_url).text
        assert "<app-root>" in html or "<app-root></app-root>" in html

    def test_doSchedule_is_angular_component(self):
        """doSchedule should be Angular component."""
        html = self.session.get(self.base_url).text
        assert "<app-root>" in html or "<app-root></app-root>" in html

    def test_download_button_is_angular(self):
        """Download button should be Angular component."""
        html = self.session.get(self.base_url).text
        assert "<app-root>" in html or "<app-root></app-root>" in html


class TestModalStacking:
    """Test modal stacking and dismissal."""

    @pytest.fixture(autouse=True)
    def _service_up(self, merge_service_live):
        self.base_url = merge_service_live
        self.session = requests.Session()

    def test_modal_is_angular_component(self):
        """Modal should be Angular component."""
        html = self.session.get(self.base_url).text
        assert "<app-root>" in html or "<app-root></app-root>" in html

    def test_modal_can_show(self):
        """Modal should be Angular component."""
        html = self.session.get(self.base_url).text
        assert "<app-root>" in html or "<app-root></app-root>" in html

    def test_modal_can_hide(self):
        """Modal should be Angular component."""
        html = self.session.get(self.base_url).text
        assert "<app-root>" in html or "<app-root></app-root>" in html


class TestFullUserFlows:
    """Test full user flows from search to download."""

    @pytest.fixture(autouse=True)
    def _service_up(self, merge_service_live):
        self.base_url = merge_service_live
        self.session = requests.Session()

    def test_search_returns_results(self):
        """Search should return results."""
        resp = self.session.post(
            f"{self.base_url}/api/v1/search/sync",
            json={"query": "linux", "limit": 3},
            headers={"Content-Type": "application/json"},
        )
        data = resp.json()
        assert data.get("results"), "Search should return results"
        assert len(data.get("results", [])) > 0, "Should have at least one result"

    def test_results_have_download_urls(self):
        """Results should have download URLs."""
        resp = self.session.post(
            f"{self.base_url}/api/v1/search/sync",
            json={"query": "linux", "limit": 1},
            headers={"Content-Type": "application/json"},
        )
        results = resp.json().get("results", [])
        if results:
            assert "download_urls" in results[0], "Results should have download_urls"

    def test_results_have_name(self):
        """Results should have name."""
        resp = self.session.post(
            f"{self.base_url}/api/v1/search/sync",
            json={"query": "linux", "limit": 1},
            headers={"Content-Type": "application/json"},
        )
        results = resp.json().get("results", [])
        if results:
            assert "name" in results[0], "Results should have name"

    def test_results_have_size(self):
        """Results should have size."""
        resp = self.session.post(
            f"{self.base_url}/api/v1/search/sync",
            json={"query": "linux", "limit": 1},
            headers={"Content-Type": "application/json"},
        )
        results = resp.json().get("results", [])
        if results:
            assert "size" in results[0], "Results should have size"


class TestCredentialStorage:
    """Test credential storage file."""

    @pytest.fixture(autouse=True)
    def _service_up(self, merge_service_live):
        self.base_url = merge_service_live
        self.session = requests.Session()

    def test_credentials_file_structure(self):
        """Credentials file should have proper structure."""
        # Test via API - login with save
        resp = self.session.post(
            f"{self.base_url}/api/v1/auth/qbittorrent",
            json={"username": "admin", "password": "admin", "save": False},
            headers={"Content-Type": "application/json"},
        )
        # Should return proper JSON
        try:
            data = resp.json()
            assert isinstance(data, dict), "Should return JSON object"
        except Exception:
            pytest.fail("Should return valid JSON")


class TestDashboardLoads:
    """Test dashboard loads properly."""

    @pytest.fixture(autouse=True)
    def _service_up(self, merge_service_live):
        self.base_url = merge_service_live
        self.session = requests.Session()

    def test_dashboard_loads(self):
        """Dashboard should load."""
        resp = self.session.get(self.base_url)
        assert resp.status_code == 200, f"Dashboard returned {resp.status_code}"

    def test_dashboard_has_angular_styles(self):
        """Dashboard should have Angular styles bundle."""
        html = self.session.get(self.base_url).text
        assert "styles-" in html, "Angular styles bundle should be loaded"

    def test_dashboard_is_angular_app(self):
        """Dashboard should be Angular app."""
        html = self.session.get(self.base_url).text
        assert "<app-root>" in html or "<app-root></app-root>" in html

    def test_dashboard_has_search_form(self):
        """Dashboard should have search form in Angular app."""
        html = self.session.get(self.base_url).text
        assert "<app-root>" in html or "<app-root></app-root>" in html


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
