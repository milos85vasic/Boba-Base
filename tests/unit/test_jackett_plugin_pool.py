"""
BOB-015 (jackett slice) regression: the Jackett plugin must not crash when
zero indexers are configured.

Root cause (reproduced 2026-06-06 via systematic-debugging): plugins/community/
jackett.py search() does

    with Pool(min(len(indexers), self.thread_count)) as pool:

When Jackett has no configured indexers, `indexers == []` so
`min(0, thread_count) == 0` and `multiprocessing.dummy.Pool(0)` raises
`ValueError: Number of processes must be at least 1`. The orchestrator then
classifies it as "plugin raised an unhandled exception" on EVERY search. This
is deterministic (unlike the network-flaky BOB-015 trackers).

§11.4.43 RED-first: against the pre-fix plugin this test raises ValueError.
After adding the empty-indexers guard it returns gracefully (0 results).
"""

import importlib.util
import sys
import types
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_JACKETT_SRC = _REPO_ROOT / "plugins" / "community" / "jackett.py"


def _load_jackett(tmp_path, monkeypatch):
    # Stub the nova3 framework modules the plugin imports at module top so it
    # loads outside a qBittorrent environment.
    helpers_stub = types.ModuleType("helpers")
    helpers_stub.enable_socks_proxy = lambda enable: None
    helpers_stub.retrieve_url = lambda *a, **k: ""
    helpers_stub.download_file = lambda *a, **k: ""
    np_stub = types.ModuleType("novaprinter")
    np_stub.prettyPrinter = lambda d: None
    monkeypatch.setitem(sys.modules, "helpers", helpers_stub)
    monkeypatch.setitem(sys.modules, "novaprinter", np_stub)
    # Import from a temp copy so the plugin's config-file write lands in tmp,
    # not in the repo's plugins/community/ directory.
    dst = tmp_path / "jackett_mod.py"
    dst.write_text(_JACKETT_SRC.read_text())
    spec = importlib.util.spec_from_file_location("jackett_mod", dst)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["jackett_mod"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_jackett_zero_indexers_does_not_crash(tmp_path, monkeypatch):
    mod = _load_jackett(tmp_path, monkeypatch)
    eng = mod.jackett()
    eng.api_key = "testkey123"  # bypass the api-key-error early return
    eng.thread_count = 8  # force the multithreaded Pool branch
    monkeypatch.setattr(eng, "get_jackett_indexers", lambda what: [])
    # Must NOT raise ValueError("Number of processes must be at least 1").
    eng.search("ubuntu", "all")


def test_jackett_with_indexers_still_uses_pool(tmp_path, monkeypatch):
    """Guard must not break the normal path: with indexers present the plugin
    fans out via the pool (search_jackett_indexer called once per indexer)."""
    mod = _load_jackett(tmp_path, monkeypatch)
    eng = mod.jackett()
    eng.api_key = "testkey123"
    eng.thread_count = 8
    monkeypatch.setattr(eng, "get_jackett_indexers", lambda what: ["idx1", "idx2", "idx3"])
    called = []
    monkeypatch.setattr(eng, "search_jackett_indexer", lambda *a: called.append(a))
    eng.search("ubuntu", "all")
    assert len(called) == 3
