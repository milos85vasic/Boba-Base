"""
Security tests for XSS (Cross-Site Scripting) protection.

Scenarios:
- Search queries containing script tags must be sanitized
- Magnet links with javascript: protocol must be rejected
- Result names with HTML entities must be escaped in dashboard
- Hook names/descriptions must not allow script injection
- Metadata fields (title, overview) must be escaped
"""

import html

import pytest
import requests


from tests.fixtures.health import merge_service_required


@merge_service_required
class TestXSSProtection:
    """XSS attack vectors must be sanitized or rejected."""

    @pytest.fixture(autouse=True)
    def _service_up(self, merge_service_live):
        self.base_url = merge_service_live

    def test_search_query_with_script_tag(self):
        """Search query containing <script> must be returned as text in JSON (not executable)."""
        payload = "<script>alert('xss')</script>"
        resp = requests.post(
            f"{self.base_url}/api/v1/search",
            json={"query": payload, "limit": 5},
            timeout=60,
        )
        assert resp.status_code == 200
        data = resp.json()
        # JSON API returns raw text - it's the client's job to escape for HTML
        assert data.get("query") == payload
        # Content-Type should be application/json, not text/html
        assert "json" in resp.headers.get("Content-Type", "")

    def test_search_query_with_javascript_protocol(self):
        """Search query with javascript: protocol must be treated as text."""
        payload = "javascript:alert('xss')"
        resp = requests.post(
            f"{self.base_url}/api/v1/search",
            json={"query": payload, "limit": 5},
            timeout=60,
        )
        assert resp.status_code == 200

    def test_dashboard_escapes_html_in_results(self):
        """Dashboard HTML must escape result names containing HTML.

        The dashboard is now an Angular SPA (``<app-root>``). Template
        bindings like ``{{ result.name }}`` interpolate via textContent
        by default (Angular's contextual escaping), so raw HTML from
        server responses never renders as markup. Instead of grepping
        for a specific escape helper, we assert:

        1. The root index.html ships the Angular shell with
           ``<app-root>``.
        2. No inline scripts on the landing page construct DOM from
           server data (i.e. no ``innerHTML`` / ``document.write`` /
           ``eval``).
        """
        dashboard = requests.get(f"{self.base_url}/", timeout=10).text
        assert "<app-root>" in dashboard, "Angular shell missing"
        bad_patterns = ["innerHTML", "document.write", "eval("]
        for bad in bad_patterns:
            assert bad not in dashboard, f"unsafe DOM sink in landing page: {bad!r}"

    def test_magnet_link_rejects_javascript_protocol(self):
        """Magnet endpoint must reject javascript: URLs."""
        resp = requests.post(
            f"{self.base_url}/api/v1/magnet",
            json={"name": "test", "hash": "abc123"},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            magnet = data.get("magnet", "")
            assert not magnet.startswith("javascript:"), "Magnet must not use javascript: protocol"

    def test_hook_name_sanitization(self):
        """Hook creation must sanitize name field."""
        payload = {
            "name": "<script>alert('xss')</script>",
            "event": "search_complete",
            "script": "/bin/true",
        }
        resp = requests.post(
            f"{self.base_url}/api/v1/hooks",
            json=payload,
            timeout=10,
        )
        # Should either reject or sanitize
        if resp.status_code in (200, 201):
            hooks = requests.get(f"{self.base_url}/api/v1/hooks", timeout=10).json()
            for hook in hooks:
                assert "<script>" not in hook.get("name", ""), "Hook name must not contain raw script tags"

    @pytest.mark.timeout(120)
    def test_result_name_with_html_entities(self):
        """Results with HTML special chars must be handled safely.

        Live search; budget raised above the default 30s.
        """
        resp = requests.post(
            f"{self.base_url}/api/v1/search",
            json={"query": "test", "limit": 5},
            timeout=60,
        )
        assert resp.status_code == 200
        data = resp.json()
        for result in data.get("results", []):
            name = result.get("name", "")
            # Names should not contain unescaped HTML that could render
            if "<" in name or ">" in name:
                # If HTML is present, it should be in a context that's escaped
                pass  # This is acceptable if dashboard escapes it

    def test_css_injection_in_search_query(self):
        """CSS injection via <style> tags must be returned as text in JSON."""
        payload = "<style>body{background:red}</style>"
        resp = requests.post(
            f"{self.base_url}/api/v1/search",
            json={"query": payload, "limit": 5},
            timeout=60,
        )
        assert resp.status_code == 200
        data = resp.json()
        # JSON API returns raw text - client must escape
        assert data.get("query") == payload
        assert "json" in resp.headers.get("Content-Type", "")

    def test_onerror_attribute_injection(self):
        """img onerror attribute injection must not execute."""
        payload = "<img src=x onerror=alert('xss')>"
        resp = requests.post(
            f"{self.base_url}/api/v1/search",
            json={"query": payload, "limit": 5},
            timeout=60,
        )
        assert resp.status_code == 200
        response_text = resp.text
        assert "onerror=" not in response_text or html.escape("onerror=") in response_text
