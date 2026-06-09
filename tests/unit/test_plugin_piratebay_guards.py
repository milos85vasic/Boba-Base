"""Regression guards for the piratebay plugin crash (BOB-015 GAP-1).

The apibay.org backend is expected to return a JSON ARRAY of result
objects. When it instead returns a JSON OBJECT (observed shape:
``{"data": null}``), the old ``search()`` crashed:

* ``json.loads('{"data": null}')`` -> dict ``{"data": None}``
* the empty-check ``if len(response_json) == 0`` sees ``len == 1`` so
  does NOT fire
* ``for result in response_json:`` iterates the dict KEYS (strings)
* ``result["info_hash"]`` indexes a ``str`` with a ``str`` ->
  ``TypeError: string indices must be integers``

This is reachable because ``retrieve_url`` returns whatever the site
sends; a sibling plugin (anilibra) was already hardened against this
exact non-list / null-data shape. The guard mirrors anilibra's
``if not isinstance(..., list): return``.

piratebay defines its OWN ``retrieve_url`` METHOD on the class (it does
NOT ``from helpers import retrieve_url``), so we patch the method on the
plugin class via ``patch.object``.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
PLUGINS = REPO / "plugins"


def _load_plugin(name: str):
    """Import a plugin file outside the nova3 harness.

    piratebay does ``import helpers`` and
    ``from novaprinter import prettyPrinter``. Install lightweight stub
    modules before import so the plugin loads cleanly, and capture every
    ``prettyPrinter`` call so tests can assert on yielded rows.
    """
    captured: list[dict] = []

    np_mod = types.ModuleType("novaprinter")
    np_mod.prettyPrinter = lambda d: captured.append(d)  # type: ignore[attr-defined]

    class _SR:
        pass

    np_mod.SearchResults = _SR  # type: ignore[attr-defined]
    sys.modules["novaprinter"] = np_mod

    helpers_mod = types.ModuleType("helpers")
    helpers_mod.retrieve_url = lambda url: ""  # type: ignore[attr-defined]
    helpers_mod.download_file = lambda url: url  # type: ignore[attr-defined]
    helpers_mod.htmlentitydecode = lambda s: s  # type: ignore[attr-defined]
    sys.modules["helpers"] = helpers_mod

    spec = importlib.util.spec_from_file_location(f"plugin_{name}", PLUGINS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod, captured


def _run_search(body: str) -> list[dict]:
    """Run piratebay.search with retrieve_url stubbed to return ``body``."""
    mod, captured = _load_plugin("piratebay")
    instance = mod.piratebay()
    with patch.object(mod.piratebay, "retrieve_url", return_value=body):
        instance.search("linux")
    return captured


def test_piratebay_handles_data_null_object_response() -> None:
    """The confirmed crasher: ``{"data": null}`` must NOT raise."""
    captured = _run_search('{"data": null}')
    assert captured == [], "no rows for a non-list object response"


def test_piratebay_handles_bare_null_response() -> None:
    """A bare JSON ``null`` decodes to ``None`` and must not crash."""
    captured = _run_search("null")
    assert captured == []


def test_piratebay_handles_array_of_non_dicts() -> None:
    """An array whose elements are strings (not result dicts)."""
    captured = _run_search('["x"]')
    assert captured == []


def test_piratebay_handles_empty_object_response() -> None:
    """An empty object ``{}`` (len 0 dict) must not crash."""
    captured = _run_search("{}")
    assert captured == []


def test_piratebay_handles_malformed_json() -> None:
    """Malformed JSON returns no rows, no crash."""
    captured = _run_search("not json at all {{{")
    assert captured == []


def test_piratebay_handles_valid_empty_result_set() -> None:
    """A well-formed but empty array yields nothing."""
    captured = _run_search("[]")
    assert captured == []


def test_piratebay_yields_row_for_wellformed_array() -> None:
    """POSITIVE control: a well-formed array with one real row MUST
    yield a row (the guard must not suppress valid results).
    """
    body = (
        "["
        '{"id": "12345", "name": "Ubuntu 24.04 LTS",'
        ' "info_hash": "AABBCCDDEEFF00112233445566778899AABBCCDD",'
        ' "seeders": "42", "leechers": "3", "size": "1500000000",'
        ' "added": "1700000000"}'
        "]"
    )
    captured = _run_search(body)
    assert len(captured) == 1, "a well-formed result row must be yielded"
    assert captured[0]["name"] == "Ubuntu 24.04 LTS"
    assert captured[0]["link"].startswith("magnet:?xt=urn:btih:")
