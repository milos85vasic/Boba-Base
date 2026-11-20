"""Chaos tests for ``config.proxy`` under malformed/bad proxy variables.

The new ``proxy_env()`` function must tolerate nonsense inputs without raising
and without corrupting the global environment.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _repo_root() -> Path:
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "download-proxy" / "src").is_dir():
            return parent
    raise RuntimeError("cannot find repo root with download-proxy/src")


import pytest

_SRC = _repo_root() / "download-proxy" / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from config import proxy as proxy_config


@pytest.mark.chaos
def test_proxy_env_tolerates_empty_boba_upstream_proxy(monkeypatch):
    for v in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy", "NO_PROXY", "no_proxy", "BOBA_UPSTREAM_PROXY"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("BOBA_UPSTREAM_PROXY", "")

    before = os.environ.copy()
    env = proxy_config.proxy_env()
    after = os.environ.copy()

    assert after == before
    assert env.get("HTTP_PROXY") in (None, "")


@pytest.mark.chaos
def test_proxy_env_tolerates_malformed_url(monkeypatch):
    for v in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy", "NO_PROXY", "no_proxy", "BOBA_UPSTREAM_PROXY"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("BOBA_UPSTREAM_PROXY", "://not-a-url")

    before = os.environ.copy()
    env = proxy_config.proxy_env()
    after = os.environ.copy()

    assert after == before
    assert env.get("HTTP_PROXY") == "://not-a-url"


@pytest.mark.chaos
def test_proxy_env_tolerates_whitespace_only_values(monkeypatch):
    for v in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy", "NO_PROXY", "no_proxy", "BOBA_UPSTREAM_PROXY"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("BOBA_UPSTREAM_PROXY", "   ")
    monkeypatch.setenv("NO_PROXY", "  ,  ,  ")

    before = os.environ.copy()
    env = proxy_config.proxy_env()
    after = os.environ.copy()

    assert after == before
    assert env.get("HTTP_PROXY") in (None, "")


@pytest.mark.chaos
def test_proxy_env_tolerates_conflicting_case_vars(monkeypatch):
    for v in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy", "NO_PROXY", "no_proxy", "BOBA_UPSTREAM_PROXY"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("HTTP_PROXY", "http://existing:8080")
    monkeypatch.setenv("BOBA_UPSTREAM_PROXY", "http://new:9090")

    env = proxy_config.proxy_env()
    # Operator-set HTTP_PROXY is preserved; BOBA_UPSTREAM_PROXY only fills blanks.
    assert env["HTTP_PROXY"] == "http://existing:8080"
    # HTTPS_PROXY gets filled from BOBA_UPSTREAM_PROXY.
    assert env["HTTPS_PROXY"] == "http://new:9090"
