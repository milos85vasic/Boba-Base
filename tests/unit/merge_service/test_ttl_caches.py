"""
TTL caches for ephemeral state.

Orchestrator state (_active_searches, _last_merged_results) and
auth._pending_captchas previously grew without bound and kept entries
forever, leaking memory over long sessions.  They are now `cachetools.TTLCache`
instances bounded by size + age.

These tests freeze the cache's notion of time via its built-in ``timer`` kwarg
so we do not need an external freezegun dep.
"""

from __future__ import annotations

import importlib.util
import os
import sys

from cachetools import TTLCache

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_SRC_PATH = os.path.join(_REPO_ROOT, "download-proxy", "src")
_MS_PATH = os.path.join(_SRC_PATH, "merge_service")

if _SRC_PATH not in sys.path:
    sys.path.insert(0, _SRC_PATH)

sys.modules.setdefault("merge_service", type(sys)("merge_service"))
sys.modules["merge_service"].__path__ = [_MS_PATH]


def _reimport_search():
    for k in [k for k in list(sys.modules) if k.startswith("merge_service")]:
        if k == "merge_service":
            continue
        del sys.modules[k]

    for submodule in ("retry", "search", "deduplicator", "validator"):
        sub_spec = importlib.util.spec_from_file_location(
            f"merge_service.{submodule}", os.path.join(_MS_PATH, f"{submodule}.py")
        )
        sub_mod = importlib.util.module_from_spec(sub_spec)
        sys.modules[f"merge_service.{submodule}"] = sub_mod
        sub_spec.loader.exec_module(sub_mod)

    return sys.modules["merge_service.search"]


def _reimport_auth():
    for k in [k for k in list(sys.modules) if k == "api" or k.startswith("api.")]:
        del sys.modules[k]
    spec = importlib.util.spec_from_file_location("api.auth", os.path.join(_SRC_PATH, "api", "auth.py"))
    mod = importlib.util.module_from_spec(spec)
    # Parent package shim so relative imports work if any.
    sys.modules.setdefault("api", type(sys)("api"))
    sys.modules["api.auth"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_active_searches_is_ttlcache(monkeypatch):
    monkeypatch.setenv("MAX_ACTIVE_SEARCHES", "8")
    monkeypatch.setenv("ACTIVE_SEARCH_TTL_SECONDS", "3600")
    search_mod = _reimport_search()
    orch = search_mod.SearchOrchestrator()

    assert isinstance(orch._active_searches, TTLCache)
    assert orch._active_searches.maxsize == 8
    assert orch._active_searches.ttl == 3600


def test_last_merged_results_is_ttlcache(monkeypatch):
    monkeypatch.setenv("MAX_ACTIVE_SEARCHES", "4")
    monkeypatch.setenv("ACTIVE_SEARCH_TTL_SECONDS", "120")
    search_mod = _reimport_search()
    orch = search_mod.SearchOrchestrator()

    assert isinstance(orch._last_merged_results, TTLCache)
    assert orch._last_merged_results.maxsize == 4
    assert orch._last_merged_results.ttl == 120


def test_ttlcache_eviction_on_maxsize(monkeypatch):
    monkeypatch.setenv("MAX_ACTIVE_SEARCHES", "5")
    search_mod = _reimport_search()
    orch = search_mod.SearchOrchestrator()

    for i in range(20):
        orch._active_searches[f"sid{i}"] = f"meta{i}"

    assert len(orch._active_searches) <= 5


def test_ttlcache_expires_after_ttl(monkeypatch):
    # Use fake timer on a fresh TTLCache to prove expiry semantics without
    # mutating global time.  Implementation detail: we just assert the cache
    # type we construct in SearchOrchestrator honours ttl; cachetools does
    # the real work.
    clock = {"t": 0.0}

    cache = TTLCache(maxsize=10, ttl=60, timer=lambda: clock["t"])
    cache["a"] = 1
    assert "a" in cache
    clock["t"] = 30.0
    assert "a" in cache
    clock["t"] = 90.0
    assert "a" not in cache


def test_pending_captchas_is_ttlcache():
    auth_mod = _reimport_auth()
    pc = auth_mod._pending_captchas
    assert isinstance(pc, TTLCache)
    assert pc.maxsize == 1024
    assert pc.ttl == 900
