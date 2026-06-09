"""Regression guard for torrentgalaxy.py search() unbounded pagination.

torrentgalaxy.search() drove pagination with `while True:` and an
unbounded `current_page += 1`, breaking only on `parser.noTorrents`.
A tracker (or interstitial / index-ignoring server) that re-serves a
matching torrent row for every page index makes the loop run FOREVER
(compounded by the per-page sleep(3)). Same defect class as
kickass.py / bitsearch.py.

Fix: a class attribute MAX_PAGES bounds the loop so search() always
terminates after at most MAX_PAGES page fetches, while preserving
normal pagination (it still advances page-by-page until noTorrents).
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
PLUGINS = REPO / "plugins"


def _load_plugin() -> tuple[types.ModuleType, list[dict]]:
    captured: list[dict] = []

    np_mod = types.ModuleType("novaprinter")
    np_mod.prettyPrinter = lambda d: captured.append(d)
    sys.modules["novaprinter"] = np_mod

    helpers_mod = types.ModuleType("helpers")
    helpers_mod.retrieve_url = lambda url: ""
    helpers_mod.download_file = lambda url: url
    sys.modules["helpers"] = helpers_mod

    spec = importlib.util.spec_from_file_location(
        "plugin_torrentgalaxy", PLUGINS / "torrentgalaxy.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, captured


class TestTorrentgalaxySearchPageCap:
    # A single torrent row that satisfies HTMLParser.__findTorrents (outer
    # tgxtablerow + inner <b>/href/size/green/seeds/leech regex) so that
    # parser.noTorrents NEVER trips. An index-ignoring server that re-serves
    # this body for every page index would otherwise make search() loop
    # forever (compounded by the per-page sleep(3)).
    _ROW = (
        '<div class="tgxtablerow txlight">'
        "<b>Some Torrent</b>"
        '<a href="/torrent/abc">link</a>'
        "1.5 GB"
        '<span class="green">42</span>'
        "<span>7</span>"
        "</table></div>"
    )

    def _make_fake_retrieve(self, hard_limit: int):
        """Return (fake, counter).

        The fake ALWAYS serves a matching torrent row (noTorrents never
        trips). It counts page fetches; exceeding hard_limit raises
        AssertionError, which on the unbounded pre-fix code trips because
        the loop never terminates.
        """
        counter = {"pages": 0}

        def fake(url: str) -> str:
            counter["pages"] += 1
            if counter["pages"] > hard_limit:
                raise AssertionError(
                    f"search() exceeded {hard_limit} page fetches "
                    f"-> unbounded loop (no page cap)"
                )
            return self._ROW

        return fake, counter

    def test_search_caps_pages_on_index_ignoring_server(self) -> None:
        # RED on pre-fix code: `while True:` with no page cap loops forever
        # against a server that re-serves matching rows for every index, so
        # the fake's hard-limit assertion trips. GREEN after MAX_PAGES bounds
        # the loop: search() returns after <= MAX_PAGES (50) page fetches.
        mod, _captured = _load_plugin()
        engine = mod.torrentgalaxy()
        hard_limit = 200
        fake, counter = self._make_fake_retrieve(hard_limit)
        with patch.object(mod, "retrieve_url", side_effect=fake), patch.object(
            mod, "sleep", lambda _seconds: None
        ):
            engine.search("test query")
        # post-fix: bounded by MAX_PAGES (counter is incremented before the
        # cap check, so it lands at MAX_PAGES + 1 fetches at most).
        assert counter["pages"] <= 51, (
            f"search() made {counter['pages']} page fetches; "
            f"expected <= 51 (MAX_PAGES=50 + 1)"
        )
