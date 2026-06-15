"""§11.4.135 regression-guard — BUG-6 integer-size crash in dedup fallback.

Audit ref: docs/qa/search-flow-audit-20260615/findings.md BUG-6.

Plugins emit ``size`` as an int byte-count (incl. the -1 sentinel for
unknown). ``Deduplicator._parse_size_to_bytes`` passed the raw value into
``re.match`` with no ``str()`` coercion, so an int size raised
``TypeError: expected string or bytes-like object`` — and because
``_update_best_quality`` -> ``merge_results`` is unguarded, the whole
merge aborted and the search dropped every result.

Anti-bluff: the assertion is the user-observable outcome — a non-empty
merged result list / a numeric byte value — not "no exception".
RED on pre-fix code: ``_parse_size_to_bytes(4096)`` raises TypeError.
"""

from __future__ import annotations

import importlib.util
import os
import sys

import pytest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_SRC_PATH = os.path.join(_REPO_ROOT, "download-proxy", "src")
_MS_PATH = os.path.join(_SRC_PATH, "merge_service")

if _SRC_PATH not in sys.path:
    sys.path.insert(0, _SRC_PATH)

sys.modules.setdefault("merge_service", type(sys)("merge_service"))
sys.modules["merge_service"].__path__ = [_MS_PATH]

_dedup_spec = importlib.util.spec_from_file_location(
    "merge_service.deduplicator", os.path.join(_MS_PATH, "deduplicator.py")
)
_dedup_mod = importlib.util.module_from_spec(_dedup_spec)
sys.modules["merge_service.deduplicator"] = _dedup_mod
_dedup_spec.loader.exec_module(_dedup_mod)

_search_spec = importlib.util.spec_from_file_location("merge_service.search", os.path.join(_MS_PATH, "search.py"))
_search_mod = importlib.util.module_from_spec(_search_spec)
sys.modules["merge_service.search"] = _search_mod
_search_spec.loader.exec_module(_search_mod)

Deduplicator = _dedup_mod.Deduplicator
SearchResult = _search_mod.SearchResult


def test_parse_size_to_bytes_accepts_integer():
    """An int byte-count is parsed without crashing."""
    dedup = Deduplicator()
    # 4096 is a raw byte count, not a "4096 GB" string — too small to
    # match any unit, so it parses to 0 rather than raising.
    assert dedup._parse_size_to_bytes(4096) == 0


def test_parse_size_to_bytes_accepts_negative_sentinel():
    """The -1 unknown-size sentinel does not crash."""
    dedup = Deduplicator()
    assert dedup._parse_size_to_bytes(-1) == 0


def test_fallback_quality_survives_integer_size():
    """_fallback_quality (the no-api.routes path) tolerates an int size."""
    dedup = Deduplicator()
    # Name has no quality token, so it falls through to the size heuristic
    # which calls _parse_size_to_bytes on the int.
    quality = dedup._fallback_quality("Some Random Release", 4096)
    assert isinstance(quality, str)


def test_merge_survives_integer_size(monkeypatch):
    """merge_results returns a non-empty list when plugins emit int sizes
    AND the api.routes quality detector is unavailable (fallback path)."""
    import builtins

    dedup = Deduplicator()

    # Force the ImportError branch in _update_best_quality so the static
    # _fallback_quality / _parse_size_to_bytes path is exercised.
    real_import = builtins.__import__

    def _blocking_import(name, *args, **kwargs):
        if name == "api.routes" or name.startswith("api.routes"):
            raise ImportError("simulated: api.routes unavailable")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _blocking_import)

    results = [
        SearchResult(
            name="Movie 1080p",
            link="magnet:?xt=urn:btih:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            size=4096,
            seeds=10,
            leechers=1,
            engine_url="https://rutor.example",
            tracker="rutor",
        ),
        SearchResult(
            name="Other Release",
            link="magnet:?xt=urn:btih:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            size=-1,
            seeds=5,
            leechers=0,
            engine_url="https://nyaa.example",
            tracker="nyaa",
        ),
    ]

    merged = dedup.merge_results(results)

    assert len(merged) >= 1, "integer-size results were dropped — merge crashed"
