"""Integration: ``config.proxy.proxy_env()`` does not leak into ``os.environ``.

The recent fix introduced ``proxy_env()`` so public-tracker subprocesses and
private aiohttp sessions can receive resolved proxy variables WITHOUT mutating
the parent process environment. This test exercises the real function under
concurrent load and asserts the global ``os.environ`` is unchanged.
"""

from __future__ import annotations

import os
import sys
import threading
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


def test_proxy_env_does_not_mutate_os_environ(monkeypatch):
    for v in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy", "NO_PROXY", "no_proxy", "BOBA_UPSTREAM_PROXY"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("BOBA_UPSTREAM_PROXY", "http://egress.example:8080")

    before = os.environ.copy()
    env = proxy_config.proxy_env()
    after = os.environ.copy()

    assert after == before, "proxy_env() mutated the global os.environ"
    assert env["HTTP_PROXY"] == "http://egress.example:8080"
    assert env["HTTPS_PROXY"] == "http://egress.example:8080"
    assert "localhost" in env["NO_PROXY"].lower()


def test_proxy_env_is_thread_safe_no_leak(monkeypatch):
    for v in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy", "NO_PROXY", "no_proxy", "BOBA_UPSTREAM_PROXY"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("BOBA_UPSTREAM_PROXY", "http://egress.example:8080")

    errors: list[str] = []
    results: list[dict[str, str]] = []
    lock = threading.Lock()

    def worker():
        try:
            env = proxy_config.proxy_env()
            with lock:
                results.append({k: env.get(k, "") for k in ("HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY")})
            # Mutating the returned dict must not touch os.environ either.
            env["HTTP_PROXY"] = "http://tampered.example:9999"
            if os.environ.get("HTTP_PROXY") == "http://tampered.example:9999":
                errors.append("mutation of returned dict leaked into os.environ")
        except Exception as exc:
            errors.append(str(exc))

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert not errors, f"concurrent proxy_env errors: {errors}"
    assert len(results) == 20
    for r in results:
        assert r["HTTP_PROXY"] == "http://egress.example:8080"
        assert r["HTTPS_PROXY"] == "http://egress.example:8080"
        assert "localhost" in r["NO_PROXY"].lower()

    # Global environment must be exactly as before all the calls.
    assert os.environ.get("HTTP_PROXY") != "http://tampered.example:9999"
