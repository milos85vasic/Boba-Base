"""
Unit tests for the shared theme-state HTTP endpoints.

Phase A of the Cross-app Theme Plan
(see docs/CROSS_APP_THEME_PLAN.md) introduces three REST routes on the
merge service that let both the Angular dashboard at :7187 and any
other app we proxy read/write the active palette + mode:

* ``GET  /api/v1/theme``
* ``PUT  /api/v1/theme``
* ``GET  /api/v1/theme/stream`` (SSE; tested in test_theme_stream.py)

These specs use a fresh ``theme.json`` path per test so runs stay
isolated from each other (and from the production file at
``/config/merge-service/theme.json``).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SRC_PATH = _REPO_ROOT / "download-proxy" / "src"
_MS_PATH = _SRC_PATH / "merge_service"
if str(_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(_SRC_PATH))


def _ensure_merge_service_package() -> None:
    """Ensure merge_service is a proper package with correct __path__."""
    from importlib.util import spec_from_file_location, module_from_spec

    ms = sys.modules.get("merge_service")
    if ms is None or not hasattr(ms, "__path__"):
        sys.modules.setdefault("merge_service", type(sys)("merge_service"))
        sys.modules["merge_service"].__path__ = [str(_MS_PATH)]
    elif str(_MS_PATH) not in getattr(ms, "__path__", []):
        ms.__path__ = [str(_MS_PATH)]

    _search_spec = spec_from_file_location("merge_service.search", str(_MS_PATH / "search.py"))
    _search_mod = module_from_spec(_search_spec)
    sys.modules["merge_service.search"] = _search_mod
    _search_spec.loader.exec_module(_search_mod)


def _purge_api_module() -> None:
    _ensure_merge_service_package()
    for key in [k for k in list(sys.modules) if k == "api" or k.startswith("api.")]:
        del sys.modules[key]


@pytest.fixture
def theme_client(tmp_path, monkeypatch):
    """Boot a fresh FastAPI app wired to a unique theme.json per test."""
    theme_path = tmp_path / "theme.json"
    monkeypatch.setenv("THEME_STATE_PATH", str(theme_path))
    _purge_api_module()
    import api

    # Reset the module-level singleton so every test starts fresh.
    from api import theme_state as ts

    ts._store = None  # type: ignore[attr-defined]

    client = TestClient(api.app)
    return client, theme_path


def test_get_theme_returns_default_when_file_missing(theme_client):
    client, path = theme_client
    assert not path.exists()
    r = client.get("/api/v1/theme")
    assert r.status_code == 200
    body = r.json()
    assert body["paletteId"] == "darcula"
    assert body["mode"] == "dark"
    assert isinstance(body["updatedAt"], str) and body["updatedAt"]


def test_put_theme_persists_and_get_reflects(theme_client):
    client, path = theme_client
    r = client.put("/api/v1/theme", json={"paletteId": "nord", "mode": "light"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["paletteId"] == "nord"
    assert body["mode"] == "light"
    assert body["updatedAt"]

    # File is written atomically.
    assert path.exists(), "theme.json should be persisted after PUT"
    on_disk = json.loads(path.read_text())
    assert on_disk["paletteId"] == "nord"
    assert on_disk["mode"] == "light"

    # GET reflects.
    r2 = client.get("/api/v1/theme")
    assert r2.status_code == 200
    assert r2.json()["paletteId"] == "nord"
    assert r2.json()["mode"] == "light"


def test_put_theme_rejects_unknown_palette_id(theme_client):
    client, _ = theme_client
    r = client.put("/api/v1/theme", json={"paletteId": "not-a-real-palette", "mode": "dark"})
    assert r.status_code == 422
    assert "paletteId" in r.text.lower() or "palette" in r.text.lower()


def test_put_theme_rejects_invalid_mode(theme_client):
    client, _ = theme_client
    r = client.put("/api/v1/theme", json={"paletteId": "nord", "mode": "sepia"})
    assert r.status_code == 422
    assert "mode" in r.text.lower()


def test_put_theme_accepts_every_catalogued_palette(theme_client):
    client, _ = theme_client
    # Catalogue is pinned at exactly eight palettes — keep the test in
    # sync with frontend/src/app/models/palette.model.ts.
    for pid in (
        "darcula",
        "dracula",
        "solarized",
        "nord",
        "monokai",
        "gruvbox",
        "one-dark",
        "tokyo-night",
    ):
        for mode in ("light", "dark"):
            r = client.put("/api/v1/theme", json={"paletteId": pid, "mode": mode})
            assert r.status_code == 200, f"{pid}/{mode}: {r.status_code} {r.text}"
            assert r.json()["paletteId"] == pid
            assert r.json()["mode"] == mode


def test_theme_state_seed_file_corrupted_reverts_to_default(tmp_path, monkeypatch):
    theme_path = tmp_path / "theme.json"
    theme_path.write_text("{this is not json}")
    monkeypatch.setenv("THEME_STATE_PATH", str(theme_path))
    _purge_api_module()
    import api
    from api import theme_state as ts

    ts._store = None  # type: ignore[attr-defined]

    client = TestClient(api.app)
    r = client.get("/api/v1/theme")
    assert r.status_code == 200
    assert r.json()["paletteId"] == "darcula"
    assert r.json()["mode"] == "dark"
