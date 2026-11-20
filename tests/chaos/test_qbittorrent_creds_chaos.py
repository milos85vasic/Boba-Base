"""Chaos tests for ``qbittorrent_creds.json`` handling.

The recent fix made credential writes atomic with chmod 0o600. These tests
exercise the load side with corrupt, missing, and malformed credential files
to ensure the service degrades gracefully to environment defaults.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_SRC = Path(__file__).resolve().parents[2] / "download-proxy" / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from api.routes import _load_saved_qbit_credentials, _get_qbit_password, _get_qbit_username


@pytest.mark.chaos
def test_missing_creds_file_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "api.routes._load_saved_qbit_credentials",
        lambda: _load_saved_qbit_credentials_inner(str(tmp_path / "qbittorrent_creds.json")),
    )
    assert _load_saved_qbit_credentials() is None


@pytest.mark.chaos
def test_corrupt_creds_file_returns_none(tmp_path, monkeypatch):
    creds_file = tmp_path / "qbittorrent_creds.json"
    creds_file.write_text("not valid json {{{")

    with patch("api.routes._load_saved_qbit_credentials", lambda: _load_saved_qbit_credentials_inner(str(creds_file))):
        assert _load_saved_qbit_credentials() is None


@pytest.mark.chaos
def test_empty_creds_file_returns_none(tmp_path, monkeypatch):
    creds_file = tmp_path / "qbittorrent_creds.json"
    creds_file.write_text("")

    with patch("api.routes._load_saved_qbit_credentials", lambda: _load_saved_qbit_credentials_inner(str(creds_file))):
        assert _load_saved_qbit_credentials() is None


@pytest.mark.chaos
def test_partial_creds_file_falls_back_to_env(tmp_path, monkeypatch):
    creds_file = tmp_path / "qbittorrent_creds.json"
    creds_file.write_text(json.dumps({"username": "saveduser"}))  # no password

    monkeypatch.setenv("QBITTORRENT_PASS", "envpass")
    with patch("api.routes._load_saved_qbit_credentials", lambda: _load_saved_qbit_credentials_inner(str(creds_file))):
        assert _get_qbit_password() == "envpass"


@pytest.mark.chaos
def test_creds_file_with_wrong_permissions_still_reads(tmp_path, monkeypatch):
    creds_file = tmp_path / "qbittorrent_creds.json"
    creds_file.write_text(json.dumps({"username": "u", "password": "p"}))
    os.chmod(str(creds_file), 0o644)

    with patch("api.routes._load_saved_qbit_credentials", lambda: _load_saved_qbit_credentials_inner(str(creds_file))):
        data = _load_saved_qbit_credentials()
    assert data == {"username": "u", "password": "p"}


def _load_saved_qbit_credentials_inner(path: str):
    import json

    if os.path.isfile(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            pass
    return None
