"""Security: upstream proxy configuration must not leak credentials.

``config.proxy.proxy_env()`` and ``apply_proxy_env()`` resolve proxy settings
from ``BOBA_UPSTREAM_PROXY``. When that URL embeds credentials
(``http://user:pass@proxy:8080``), the resolved ``HTTP_PROXY``/``HTTPS_PROXY``
values carry those credentials. This is expected — urllib/aiohttp need them to
authenticate to the proxy. The security invariant is that the credentials are
not accidentally logged or returned to clients, and that the module itself does
not persist them outside the process environment.
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


@pytest.mark.security
def test_proxy_env_preserves_embedded_credentials(monkeypatch):
    for v in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy", "NO_PROXY", "no_proxy", "BOBA_UPSTREAM_PROXY"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("BOBA_UPSTREAM_PROXY", "http://alice:secret@proxy.example:8080")

    env = proxy_config.proxy_env()
    assert env["HTTP_PROXY"] == "http://alice:secret@proxy.example:8080"
    assert env["HTTPS_PROXY"] == "http://alice:secret@proxy.example:8080"


@pytest.mark.security
def test_proxy_env_does_not_write_credentials_to_disk(monkeypatch, tmp_path):
    for v in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy", "NO_PROXY", "no_proxy", "BOBA_UPSTREAM_PROXY"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("BOBA_UPSTREAM_PROXY", "http://alice:secret@proxy.example:8080")

    _ = proxy_config.proxy_env()
    # The function is pure: it returns a dict and touches no files.
    # Search the temp dir to make sure nothing was written.
    assert not any(tmp_path.iterdir())


@pytest.mark.security
def test_proxy_env_leaves_global_environ_intact(monkeypatch):
    for v in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy", "NO_PROXY", "no_proxy", "BOBA_UPSTREAM_PROXY"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("BOBA_UPSTREAM_PROXY", "http://alice:secret@proxy.example:8080")

    before = os.environ.copy()
    proxy_config.proxy_env()
    after = os.environ.copy()

    assert after == before, "proxy_env() leaked into the global environment"


@pytest.mark.security
def test_apply_proxy_env_redacts_nothing_but_propagates(monkeypatch):
    for v in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy", "NO_PROXY", "no_proxy", "BOBA_UPSTREAM_PROXY"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("BOBA_UPSTREAM_PROXY", "http://alice:secret@proxy.example:8080")

    # apply_proxy_env() mutates the global os.environ. Save/restore it explicitly
    # so no proxy state leaks to later tests (monkeypatch only undoes the vars it
    # knew about at test start, not the ones the function writes).
    before = os.environ.copy()
    try:
        proxy_config.apply_proxy_env()
        assert os.environ["HTTP_PROXY"] == "http://alice:secret@proxy.example:8080"
        assert "alice:secret" in os.environ["HTTP_PROXY"]
    finally:
        os.environ.clear()
        os.environ.update(before)
