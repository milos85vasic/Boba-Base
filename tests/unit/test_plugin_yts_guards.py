"""Degenerate-input guards for the ``plugins/yts.py`` YTS plugin (BOB-015).

YTS uses a JSON API (``/api/v2/list_movies.json``). The finding flagged
yts as "intermittent (external)", NOT a confirmed code crash, so this
suite probes the JSON parse/search path with degenerate inputs to
determine whether a real unhandled crash exists:

* empty body ``""``
* malformed JSON
* valid JSON that is NOT a dict (array / bare ``null``)
* valid JSON dict with ``"data": null``
* valid JSON dict with missing ``data`` key
* valid JSON dict with empty ``movies`` list / zero ``movie_count``
* HTTP-error-shaped JSON (``{"status": "error", ...}``)

The plugin is pulled from ``plugins/`` and installed into the nova3
engines dir, so the guard lives in the source of truth here.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import patch

import pytest

REPO = Path(__file__).resolve().parents[2]
PLUGINS = REPO / "plugins"


def _load_yts() -> tuple[types.ModuleType, list[dict]]:
    """Import ``plugins/yts.py`` outside the nova3 harness.

    yts does ``from novaprinter import prettyPrinter`` and
    ``from helpers import retrieve_url``; we install lightweight stub
    modules before import so the plugin loads cleanly. Returns the
    module plus the list that captures every ``prettyPrinter`` row.
    """
    captured: list[dict] = []

    np_mod = types.ModuleType("novaprinter")
    np_mod.prettyPrinter = lambda d: captured.append(d)  # type: ignore[attr-defined]
    sys.modules["novaprinter"] = np_mod

    helpers_mod = types.ModuleType("helpers")
    helpers_mod.retrieve_url = lambda url: ""  # type: ignore[attr-defined]
    helpers_mod.download_file = lambda url: url  # type: ignore[attr-defined]
    sys.modules["helpers"] = helpers_mod

    spec = importlib.util.spec_from_file_location("plugin_yts", PLUGINS / "yts.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod, captured


def _run_search(body: str) -> list[dict]:
    """Drive ``yts().search()`` with ``retrieve_url`` returning ``body``.

    yts.py does ``from helpers import retrieve_url`` at import time, binding
    the name into the plugin module's own namespace, so the patch MUST target
    that bound reference (``plugin_yts.retrieve_url``), not the helpers module.
    """
    mod, captured = _load_yts()
    instance = mod.yts()
    with patch.object(mod, "retrieve_url", return_value=body):
        instance.search("linux")
    return captured


def test_empty_body_yields_no_rows() -> None:
    """Empty upstream body must NOT crash and capture 0 rows."""
    assert _run_search("") == []


def test_malformed_json_yields_no_rows() -> None:
    """Malformed JSON must be swallowed by the parse guard."""
    assert _run_search("not json <<<>>>") == []


def test_non_dict_array_json_yields_no_rows() -> None:
    """Valid JSON that decodes to a list — ``j.get`` would crash."""
    assert _run_search('["unexpected", "array"]') == []


def test_bare_null_json_yields_no_rows() -> None:
    """Valid JSON ``null`` — ``j.get`` would crash on NoneType."""
    assert _run_search("null") == []


def test_data_null_yields_no_rows() -> None:
    """``{"data": null}`` — ``.get("data", {}).get(...)`` crashes on None."""
    assert _run_search('{"data": null}') == []


def test_missing_data_key_yields_no_rows() -> None:
    """Dict without a ``data`` key must short-circuit cleanly."""
    assert _run_search('{"meta": "no data here"}') == []


def test_empty_movies_list_yields_no_rows() -> None:
    """Zero ``movie_count`` / empty ``movies`` must yield 0 rows."""
    body = '{"data": {"movie_count": 0, "movies": [], "page_number": 1, "limit": 20}}'
    assert _run_search(body) == []


def test_http_error_shaped_json_yields_no_rows() -> None:
    """An error-shaped API response must yield 0 rows without crashing."""
    body = '{"status": "error", "status_message": "Query was empty", "data": null}'
    assert _run_search(body) == []


def test_valid_json_with_one_movie_captures_one_row() -> None:
    """Positive control: a well-formed response yields exactly one row,
    proving the guards do not over-suppress real results."""
    body = (
        '{"data": {"movie_count": 1, "limit": 20, "page_number": 1, "movies": ['
        '{"title": "Big Buck Bunny", "year": 2008, "rating": 7.5, '
        '"genres": ["Animation", "Short"], "url": "https://yts.lt/movie/bbb", '
        '"torrents": [{"hash": "' + "a" * 40 + '", "quality": "1080p", '
        '"size": "700 MB", "seeds": 100, "peers": 50}]}]}}'
    )
    rows = _run_search(body)
    assert len(rows) == 1
    assert rows[0]["name"].startswith("Big Buck Bunny (2008) [1080p]")
    assert rows[0]["link"].startswith("magnet:?xt=urn:btih:" + "a" * 40)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
