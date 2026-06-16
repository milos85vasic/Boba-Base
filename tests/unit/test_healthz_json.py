"""
§11.4.43 TDD regression test for the machine-parsable JSON health endpoint.

CONTEXT (nezha validation): a bare GET /healthz fell through the SPA
catch-all (api/__init__.py:spa_catch_all) and returned the dashboard
index.html — so a machine health-probe could not parse a JSON status.
The real probes are /health (app-level) and /api/v1/auth/status. This
test pins a JSON health route on the routes.py router (mounted at
/api/v1) so a probe gets {"status": "ok", ...} with an
application/json content-type, NOT text/html.

RED on the pre-fix code: the route does not exist, so GET
/api/v1/healthz is handled by spa_catch_all and returns HTML (or, for
the `api/`-prefixed path, a 404) — never a parseable JSON health body.
"""

import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "download-proxy", "src"))


@pytest.fixture
def client():
    from api import app

    return TestClient(app)


class TestHealthzJson:
    def test_healthz_returns_json_not_html(self, client):
        """A machine probe of /api/v1/healthz MUST get parseable JSON."""
        resp = client.get("/api/v1/healthz")
        assert resp.status_code == 200, resp.text

        content_type = resp.headers.get("content-type", "")
        # The defect: catch-all served text/html. Assert JSON content-type
        # and an actually-parseable body — NOT the SPA index document.
        assert "application/json" in content_type, (
            f"expected JSON content-type, got {content_type!r}; "
            f"body starts: {resp.text[:80]!r}"
        )
        assert "<html" not in resp.text.lower(), "got HTML dashboard, not a health body"

        body = resp.json()  # raises if not valid JSON (catch-all HTML would)
        assert body.get("status") == "ok", body

    def test_healthz_body_carries_service_identity(self, client):
        """Mirror the existing /health shape so probes can identify us."""
        body = client.get("/api/v1/healthz").json()
        assert body.get("service") == "merge-search", body
        assert "version" in body, body
