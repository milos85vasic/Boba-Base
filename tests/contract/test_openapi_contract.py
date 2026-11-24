"""Contract tests — pin the FastAPI OpenAPI schema.

These tests build the in-process `api.app` (no live HTTP) and assert
that a stable set of operations + key fields exist. They do not assert
every field to avoid false positives on additive changes; a regression
catches *removal* of documented operations.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[2] / "download-proxy" / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


@pytest.fixture(scope="module")
def openapi_schema() -> dict:
    # Import inside the fixture so the autouse conftest isolation hook
    # can snapshot/restore sys.modules cleanly between tests.
    os.environ.setdefault("ALLOWED_ORIGINS", "http://localhost")  # silence wildcard warning
    from api import app

    return app.openapi()


REQUIRED_OPERATIONS: set[str] = {
    "GET /health",
    "GET /api/v1/config",
    "GET /api/v1/stats",
    "POST /api/v1/search",
    "GET /api/v1/search/{search_id}",
    "POST /api/v1/download",
    "POST /api/v1/magnet",
    "GET /api/v1/theme",
    "PUT /api/v1/theme",
    "GET /api/v1/theme/stream",
}


def _list_operations(schema: dict) -> set[str]:
    out: set[str] = set()
    for path, methods in schema.get("paths", {}).items():
        for method in methods:
            if method.lower() in {"parameters", "summary", "description"}:
                continue
            out.add(f"{method.upper()} {path}")
    return out


def test_openapi_has_all_required_operations(openapi_schema: dict) -> None:
    operations = _list_operations(openapi_schema)
    missing = REQUIRED_OPERATIONS - operations
    assert not missing, f"OpenAPI lost required operations: {missing}"


def test_openapi_info_has_title_and_version(openapi_schema: dict) -> None:
    info = openapi_schema.get("info", {})
    assert info.get("title") == "Боба Search Service"
    assert info.get("version"), "info.version must be set"


def test_openapi_components_define_schemas(openapi_schema: dict) -> None:
    # We don't pin exact schemas here — just assert the components
    # block exists. Phase 7's OpenAPI freeze step will snapshot the
    # full schema for drift detection.
    assert "components" in openapi_schema
    assert "schemas" in openapi_schema["components"]
    assert openapi_schema["components"]["schemas"], "schemas must not be empty"


def test_health_endpoint_has_no_required_auth(openapi_schema: dict) -> None:
    health = openapi_schema["paths"]["/health"]["get"]
    # No 'security' requirement means it's public — required for the
    # stack's external healthcheck.
    assert "security" not in health or health["security"] == [], "health endpoint must be public"
