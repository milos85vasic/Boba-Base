"""Regression guard for bitsearch.py unbounded-pagination defect.

bitsearch.py search() ran ``while True:`` (no page cap), incrementing
``current_page`` from 1 with no upper bound and breaking ONLY when a page
yields zero torrent rows (``parser.noTorrents``). An upstream / interstitial
server that re-serves matching rows for every ``&page=N`` index makes the
loop run FOREVER (compounded by the per-iteration ``sleep(3)``).

Same defect class as kickass.py (TestKickassSearchPageCap). Fix: a
``MAX_PAGES`` class attribute bounding the loop ``while current_page
<= self.MAX_PAGES:`` while preserving normal pagination.

§11.4.115 polarity-switch RED-on-broken-artifact:
- On the PRE-FIX artifact the unbounded loop never terminates, so the fake
  ``retrieve_url``'s hard-limit assertion trips -> FAIL (defect reproduced).
- On the POST-FIX artifact the loop is bounded by ``MAX_PAGES`` (50), so the
  fake serves <= 51 search pages -> GREEN guard (defect absent).
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from typing import Callable
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
    sys.modules["helpers"] = helpers_mod

    spec = importlib.util.spec_from_file_location("plugin_bitsearch", PLUGINS / "bitsearch.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod, captured


class TestBitsearchSearchPageCap:
    # A single torrent row that satisfies the HTMLParser.__findTorrents
    # outer + inner regex AFTER search()'s ``re.sub(r"\s+", " ", ...)``
    # whitespace collapse, so ``parser.noTorrents`` NEVER trips. An
    # index-ignoring server re-serving this body for every page index would
    # otherwise make search() loop forever (no page cap + per-row sleep(3)).
    _ROW = (
        '<div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6 '
        'hover:shadow-md transition duration-150 ease-in-out">'
        '<a href="/torrent/12345" class="title"> Some Torrent Name </a>'
        "<span>1.0 GB</span>"
        "<i></i> <span>01/02/2024</span>"
        '<span class="medium">42</span>'
        '<span class="medium">7</span>'
        '<a href="magnet:?xt=urn:btih:deadbeef">dl</a>'
        "</div> <!-- Mobile"
    )

    def _make_fake_retrieve(self, hard_limit: int) -> tuple[Callable[[str], str], dict]:
        """Return ``(fake, counter)``.

        The fake ALWAYS serves a matching torrent row (``noTorrents`` never
        trips) and counts search-page fetches; exceeding ``hard_limit`` raises
        AssertionError, which on the unbounded pre-fix code trips because the
        loop never terminates.
        """
        counter = {"search": 0}

        def fake(url: str) -> str:
            counter["search"] += 1
            if counter["search"] > hard_limit:
                raise AssertionError(
                    f"search() exceeded {hard_limit} search-page fetches "
                    f"-> unbounded loop (no page cap)"
                )
            return self._ROW

        return fake, counter

    def test_row_is_genuinely_always_matching(self) -> None:
        # Anti-bluff guard (§11.4.1): if _ROW matched no torrent rows the
        # cap test below would pass trivially on the pre-fix code (noTorrents
        # trips at once). Prove the row DOES parse to exactly one result so
        # the loop genuinely never self-terminates.
        mod, captured = _load_plugin()
        engine = mod.bitsearch()
        with patch.object(mod, "retrieve_url", return_value=self._ROW), patch.object(
            mod, "sleep", lambda _seconds: None
        ):
            # bound via MAX_PAGES on post-fix; pre-fix relies on this test's
            # own design — exercised by the cap test, here we only confirm a
            # single page yields a parsed row.
            engine.HTMLParser(engine.url)
            import re

            html = re.sub(r"\s+", " ", self._ROW).strip()
            parser = engine.HTMLParser(engine.url)
            parser.feed(html)
        assert parser.noTorrents is False, "_ROW must parse to >=1 torrent row"
        assert len(captured) == 1, f"expected exactly 1 parsed row, got {len(captured)}"

    def test_search_caps_pages_on_index_ignoring_server(self) -> None:
        # RED on pre-fix code: ``while True:`` with no page cap loops forever
        # against a server that re-serves matching rows for every index, so
        # the fake's hard-limit assertion trips. GREEN after MAX_PAGES bounds
        # the loop: search() returns after <= MAX_PAGES (50) search fetches.
        mod, _captured = _load_plugin()
        engine = mod.bitsearch()
        hard_limit = 200
        fake, counter = self._make_fake_retrieve(hard_limit)
        with patch.object(mod, "retrieve_url", side_effect=fake), patch.object(
            mod, "sleep", lambda _seconds: None
        ):
            engine.search("test query")
        # post-fix: bounded by MAX_PAGES (current_page starts at 1 and the
        # loop runs while current_page <= MAX_PAGES, so exactly MAX_PAGES
        # fetches).
        assert counter["search"] <= 51, (
            f"search() made {counter['search']} search-page fetches; "
            f"expected <= 51 (MAX_PAGES=50)"
        )
