"""Chaos tests for partial/corrupt tracker responses.

The recent fixes in ``merge_service/search.py`` route private-tracker calls
through a local proxy transport and classify upstream HTTP statuses before
parsing. These tests feed the real HTML parsers truncated/corrupt input and
assert they return empty lists instead of crashing.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _repo_root() -> Path:
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "download-proxy" / "src").is_dir():
            return parent
    raise RuntimeError("cannot find repo root with download-proxy/src")


import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC_PATH = _REPO_ROOT / "download-proxy" / "src"
_MS_PATH = _SRC_PATH / "merge_service"

if str(_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(_SRC_PATH))

sys.modules.setdefault("merge_service", type(sys)("merge_service"))
sys.modules["merge_service"].__path__ = [str(_MS_PATH)]  # type: ignore[attr-defined]

_spec = importlib.util.spec_from_file_location("merge_service.search", str(_MS_PATH / "search.py"))
_search_mod = importlib.util.module_from_spec(_spec)
sys.modules["merge_service.search"] = _search_mod
_spec.loader.exec_module(_search_mod)  # type: ignore[union-attr]

SearchOrchestrator = _search_mod.SearchOrchestrator


@pytest.mark.chaos
def test_rutracker_parser_handles_empty_html():
    orch = SearchOrchestrator()
    results = orch._parse_rutracker_html("", "https://rutracker.org")
    assert results == []


@pytest.mark.chaos
def test_rutracker_parser_handles_truncated_table():
    html = '<tr id="trs-tr-123"><td>partial row without closing'
    orch = SearchOrchestrator()
    results = orch._parse_rutracker_html(html, "https://rutracker.org")
    assert results == []


@pytest.mark.chaos
def test_kinozal_parser_handles_empty_html():
    orch = SearchOrchestrator()
    results = orch._parse_kinozal_html("", "https://kinozal.tv")
    assert results == []


@pytest.mark.chaos
def test_kinozal_parser_handles_garbage():
    orch = SearchOrchestrator()
    results = orch._parse_kinozal_html("<html><body>no torrents here</body></html>", "https://kinozal.tv")
    assert results == []


@pytest.mark.chaos
def test_nnmclub_parser_handles_empty_html():
    orch = SearchOrchestrator()
    results = orch._parse_nnmclub_html("", "https://nnmclub.to")
    assert results == []


@pytest.mark.chaos
def test_iptorrents_parser_handles_empty_html():
    orch = SearchOrchestrator()
    results = orch._parse_iptorrents_html("", "https://iptorrents.com")
    assert results == []


@pytest.mark.chaos
def test_iptorrents_parser_handles_partial_table():
    html = '<table id="torrents"><tr><th>Name</th></tr><tr><td>row</td></tr></table>'
    orch = SearchOrchestrator()
    results = orch._parse_iptorrents_html(html, "https://iptorrents.com")
    assert results == []
