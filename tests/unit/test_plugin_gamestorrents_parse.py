"""§11.4.146 reproduce-first regression guard: gamestorrents search parser.

ROOT CAUSE (FACT, characterised 2026-06-16 against the LIVE site
https://www.gamestorrents.app/?s=GTA — captured bytes, not assumed):
``plugins/gamestorrents.py`` ``_parse_results`` anchors its regex on an
``<article>`` card containing ``<h2>`` + ``<div class=...size...>`` +
``<div class=...date...>``. The live site has 0 ``<article>`` and 0
``<h2>`` — results migrated to a ``<table class="table metalion">`` whose
body rows are::

    <tr>
      <td><a href="DETAIL-URL">NAME</a></td>   <!-- Nombre -->
      <td>DD-MM-YYYY</td>                       <!-- Fecha  -->
      <td>59.03 GBs</td>                        <!-- Tamaño -->
      <td>Inespecifico</td>                     <!-- Version-->
      <td><a rel="category tag">Accion</a></td> <!-- Genero -->
      <td><img class='flagens' .../></td>       <!-- Idioma -->
    </tr>

The first ``<tr>`` is a ``<th>`` header and must be skipped. The result:
``search()`` silently emits 0 results — the plugin is dead for the user
while every gate stays green (a §11.4 PASS-bluff at the parser layer).

This test feeds the captured fixture HTML to the REAL parser via the
``_load_plugin`` / retrieve_url-stub pattern (mirrors
test_plugin_multiword_query_encoding.py) and asserts ≥1 result with a
real name + non-empty (non-zero) size + a detail/desc link.

Polarity (§11.4.115): RED_MODE=1 (default) reproduces the defect on the
pre-fix parser (0 results from the live-table fixture) and asserts it is
ABSENT post-fix — the SAME assertion is the standing GREEN guard.
Set RED_MODE=1 to additionally PRINT the captured result count for
forensic evidence; the assertion itself is polarity-independent (it
FAILs on the old parser, PASSes on the new one).
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PLUGINS = REPO / "plugins"
FIXTURE = REPO / "tests" / "fixtures" / "gamestorrents_search_gta.html"


def _load_plugin():
    """Import gamestorrents with stubbed novaprinter/helpers, capturing
    every dict passed to prettyPrinter."""
    captured: list[dict] = []

    np_mod = types.ModuleType("novaprinter")
    np_mod.prettyPrinter = lambda d: captured.append(d)  # type: ignore[attr-defined]

    class _SR:
        pass

    np_mod.SearchResults = _SR  # type: ignore[attr-defined]
    sys.modules["novaprinter"] = np_mod

    helpers_mod = types.ModuleType("helpers")
    helpers_mod.retrieve_url = lambda url, *a, **k: ""  # type: ignore[attr-defined]
    helpers_mod.download_file = lambda url: url  # type: ignore[attr-defined]
    sys.modules["helpers"] = helpers_mod

    spec = importlib.util.spec_from_file_location(
        "plugin_gst_parse", PLUGINS / "gamestorrents.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod, captured


def _parse_fixture():
    mod, captured = _load_plugin()
    html = FIXTURE.read_text(encoding="utf-8")
    inst = mod.gamestorrents()
    inst._parse_results(html)
    return captured


def test_metalion_table_parsed_into_results() -> None:
    """RED on the old <article>/<h2> parser (0 results from the live-table
    fixture); GREEN once the parser reads <table class="metalion"> rows."""
    results = _parse_fixture()
    assert results, (
        "gamestorrents parsed 0 results from the LIVE metalion-table markup "
        "(captured 2026-06-16). The parser still anchors on <article>/<h2>, "
        "which the live site no longer emits — the plugin is dead for users."
    )
    first = results[0]
    # Real name extracted (the GTA V title from the fixture's first row).
    assert first["name"].strip(), f"empty name: {first!r}"
    assert "GTA" in first["name"].upper(), f"unexpected name: {first['name']!r}"
    # Non-empty, non-zero size (the fixture row is "59.03 GBs").
    assert first["size"] not in ("", "0", None), f"degenerate size: {first['size']!r}"
    assert int(first["size"]) > 0, f"zero-byte size: {first['size']!r}"
    # A detail/desc link the user can open to fetch the .torrent.
    link = first.get("desc_link") or first.get("link") or ""
    assert link.startswith("http"), f"missing/invalid detail link: {link!r}"
    assert "gamestorrents" in link, f"detail link not on site: {link!r}"


def test_header_row_not_emitted_as_result() -> None:
    """§11.4.146 extend: the <th> header row ('Nombre/Fecha/...') must NOT
    become a bogus result."""
    results = _parse_fixture()
    for r in results:
        assert r["name"].strip().lower() not in ("nombre", "tamaño", "fecha"), (
            f"header row leaked as a result: {r!r}"
        )


def test_size_is_parsed_to_bytes_for_gbs_suffix() -> None:
    """§11.4.146 extend: the live size column uses 'GBs' (plural) and 'GB';
    both must parse to a positive byte count (boundary on the unit suffix)."""
    results = _parse_fixture()
    sizes = [int(r["size"]) for r in results]
    assert all(s > 0 for s in sizes), f"a row parsed to 0 bytes: {sizes!r}"
    # 59.03 GBs ~= 63.4e9 bytes; assert the GTA V row is in the GB range,
    # proving the 'GBs' suffix (not just 'GB') was understood.
    assert max(sizes) > 1024**3, f"largest size below 1 GiB, suffix mis-parsed: {sizes!r}"
