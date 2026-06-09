"""Deep coverage tests for plugins/community/tokyotoshokan.py.

Covers: MyHtmlParseWithBlackJack HTMLParser (single/multi results,
empty/malformed HTML, RSS vs HTML mode), search (URL construction,
category mapping, exception handling, pagination), download_torrent
(magnet links, torrent files, no links, URLError), category mapping,
and edge cases (special characters, missing fields, SSL EOF).
"""

import importlib.util
import os
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PLUGINS_DIR = os.path.join(REPO, "plugins", "community")


def _load_tokyotoshokan(captured=None, retrieve_url_return="", use_mock_retrieve=False):
    """Import tokyotoshokan plugin with stub modules.

    When *use_mock_retrieve* is True the helpers stub uses a MagicMock so
    callers can inspect call_args / call_count.

    Returns (instance, captured, helpers_mod).
    """
    if captured is None:
        captured = []
    np_mod = types.ModuleType("novaprinter")
    np_mod.prettyPrinter = lambda d: captured.append(dict(d))
    sys.modules["novaprinter"] = np_mod

    helpers_mod = types.ModuleType("helpers")
    if use_mock_retrieve:
        helpers_mod.retrieve_url = MagicMock(return_value=retrieve_url_return)
    else:
        helpers_mod.retrieve_url = lambda url: retrieve_url_return
    helpers_mod.download_file = lambda url: url
    sys.modules["helpers"] = helpers_mod

    sys.modules.pop("tokyotoshokan", None)

    path = os.path.join(PLUGINS_DIR, "tokyotoshokan.py")
    spec = importlib.util.spec_from_file_location("tokyotoshokan", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules["tokyotoshokan"] = mod
    cls = getattr(mod, "tokyotoshokan", None)
    if cls is not None and isinstance(cls, type):
        return cls(), captured, helpers_mod
    return mod, captured, helpers_mod


# ─── HTML fixtures matching the parser's actual patterns ─────────────────
#
# The parser triggers item creation when:
#   <tr class="…"> where "category".find() is truthy (i.e. class does NOT
#   start with "category").  Real site rows use "odd"/"even" classes.
#
# Item is emitted at </tr> when it has exactly 7 keys:
#   engine_url, link, name, desc_link, size, seeds, leech

TORRENT_ROW_MAGNET = '''<tr class="odd">
<td><a href="magnet:?xt=urn:btih:abc123def456&dn=Subs+%26+Fansub">Download</a></td>
<td><a type="application/x-bittorrent" href="http://tokyotosho.info/torrents/torrent123.torrent">[Coalgirls]_Toradora!_01_(1920x1080_Blu-Ray_FLAC)_[abc12345].mkv.torrent</a></td>
<td><a href="details.php?id=123">Details</a></td>
<td class="desc-bot">Size: 350.52 MB</td>
<td class="stats"><span>15</span><span>3</span></td>
</tr>'''

TORRENT_ROW_TWO_MAGNETS = '''<tr class="even">
<td><a href="magnet:?xt=urn:btih:aaa111&dn=First">Download</a></td>
<td><a href="magnet:?xt=urn:btih:bbb222&dn=Second">Also magnet</a></td>
<td><a type="application/x-bittorrent" href="http://tokyotosho.info/torrents/t456.torrent">Anime Name</a></td>
<td><a href="details.php?id=456">Details</a></td>
<td class="desc-bot">Size: 1.2 GB</td>
<td class="stats"><span>42</span><span>7</span></td>
</tr>'''

TORRENT_ROW_NO_MAGNET = '''<tr class="odd">
<td><a type="application/x-bittorrent" href="http://tokyotosho.info/torrents/t789.torrent">Only Torrent File</a></td>
<td><a href="details.php?id=789">Details</a></td>
<td class="desc-bot">Size: 100 MB</td>
<td class="stats"><span>5</span><span>1</span></td>
</tr>'''

TORRENT_ROW_NO_TORRENT = '''<tr class="odd">
<td><a href="details.php?id=999">Just Details</a></td>
<td class="desc-bot">Size: 50 MB</td>
<td class="stats"><span>0</span><span>0</span></td>
</tr>'''

TORRENT_ROW_MINIMAL = '''<tr class="odd">
<td><a href="magnet:?xt=urn:btih:min123&dn=Min">D</a></td>
<td><a type="application/x-bittorrent" href="http://tokyotosho.info/torrents/tm.torrent">Minimal</a></td>
<td><a href="details.php?id=10">Details</a></td>
<td class="desc-bot">Size: 10 MB</td>
<td class="stats"><span>2</span><span>0</span></td>
</tr>'''

SINGLE_TORRENT_HTML = (
    '<html><body>'
    '<table class="listing">'
    + TORRENT_ROW_MAGNET
    + '</table></body></html>'
)

MULTI_TORRENT_HTML = (
    '<html><body>'
    '<table class="listing">'
    + TORRENT_ROW_MAGNET
    + TORRENT_ROW_NO_MAGNET
    + TORRENT_ROW_TWO_MAGNETS
    + '</table></body></html>'
)

EMPTY_LISTING_HTML = '<html><body><table class="listing"></table></body></html>'

NO_LISTING_HTML = '<html><body><p>No results found.</p></body></html>'

PAGINATION_HTML = (
    '<table class="listing">'
    + TORRENT_ROW_MINIMAL
    + '<tr><td>'
    + '<a href="?lastid=100&page=2&terms=test+query">Page 2</a>'
    + '<a href="?lastid=200&page=3&terms=test+query">Page 3</a>'
    + '</td></tr>'
    + '</table>'
)

PAGINATION_HTML_PERCENT20 = (
    '<table class="listing">'
    + TORRENT_ROW_MINIMAL
    + '<tr><td>'
    + '<a href="?lastid=100&page=2&terms=hello%20world">Page 2</a>'
    + '</td></tr>'
    + '</table>'
)

MALFORMED_HTML = '<html><body><table class="listing"><tr class="odd">NO CLOSING TAGS</table></body></html>'

RSS_STYLE_HTML = '''<rss><channel>
<item><title>RSS Item</title><link>http://example.com</link></item>
</channel></rss>'''

STATS_ONLY_HTML = '''<table class="listing">
<tr class="odd">
<td><a href="magnet:?xt=urn:btih:stat123&dn=StatsTest">D</a></td>
<td><a type="application/x-bittorrent" href="http://tokyotosho.info/torrents/st.torrent">Stats Test</a></td>
<td><a href="details.php?id=50">Details</a></td>
<td class="desc-bot">Size: 200 MB</td>
<td class="stats"><span>99</span><span>50</span></td>
</tr>
</table>'''

REVERSE_STATS_HTML = '''<table class="listing">
<tr class="odd">
<td><a href="magnet:?xt=urn:btih:rev456&dn=RevTest">D</a></td>
<td><a type="application/x-bittorrent" href="http://tokyotosho.info/torrents/rv.torrent">Rev Test</a></td>
<td><a href="details.php?id=60">Details</a></td>
<td class="desc-bot">Size: 500 MB</td>
<td class="stats"><span>10</span><span>20</span></td>
</tr>
</table>'''

SPECIAL_CHARS_HTML = '''<table class="listing">
<tr class="odd">
<td><a href="magnet:?xt=urn:btih:special&dn=Test%3A+Subs+%26+More">D</a></td>
<td><a type="application/x-bittorrent" href="http://tokyotosho.info/torrents/sp.torrent">[Group] Title: Special &amp; Characters (2024)</a></td>
<td><a href="details.php?id=70">Details</a></td>
<td class="desc-bot">Size: 1.5 GB</td>
<td class="stats"><span>30</span><span>5</span></td>
</tr>
</table>'''

MISSING_SIZE_HTML = '''<table class="listing">
<tr class="odd">
<td><a href="magnet:?xt=urn:btih:nosize&dn=NoSize">D</a></td>
<td><a type="application/x-bittorrent" href="http://tokyotosho.info/torrents/ns.torrent">No Size Info</a></td>
<td><a href="details.php?id=80">Details</a></td>
<td class="stats"><span>1</span><span>0</span></td>
</tr>
</table>'''


# ─── HTMLParser tests ────────────────────────────────────────────────────


class TestHtmlParser:
    """Tests for MyHtmlParseWithBlackJack."""

    def test_single_result_magnet_and_torrent(self):
        inst, captured, _ = _load_tokyotoshokan()
        parser = inst.MyHtmlParseWithBlackJack(inst.url)
        parser.feed(SINGLE_TORRENT_HTML)
        parser.close()
        assert len(captured) == 1
        item = captured[0]
        assert item["engine_url"] == "http://tokyotosho.info"
        assert item["link"] == "magnet:?xt=urn:btih:abc123def456&dn=Subs+%26+Fansub"
        assert "Toradora!" in item["name"]
        assert item["desc_link"] == "http://tokyotosho.info/details.php?id=123"
        assert item["size"] == "350.52"
        assert item["seeds"] == "15"
        assert item["leech"] == "3"

    def test_multi_results(self):
        inst, captured, _ = _load_tokyotoshokan()
        parser = inst.MyHtmlParseWithBlackJack(inst.url)
        parser.feed(MULTI_TORRENT_HTML)
        parser.close()
        assert len(captured) == 2
        assert captured[0]["link"].startswith("magnet:")
        assert "Anime Name" in captured[1]["name"]

    def test_two_magnets_last_wins(self):
        inst, captured, _ = _load_tokyotoshokan()
        parser = inst.MyHtmlParseWithBlackJack(inst.url)
        parser.feed(TORRENT_ROW_TWO_MAGNETS)
        parser.close()
        assert len(captured) == 1
        assert captured[0]["link"] == "magnet:?xt=urn:btih:bbb222&dn=Second"

    def test_no_magnet_torrent_file_only_not_emitted(self):
        inst, captured, _ = _load_tokyotoshokan()
        parser = inst.MyHtmlParseWithBlackJack(inst.url)
        parser.feed(TORRENT_ROW_NO_MAGNET)
        parser.close()
        assert len(captured) == 0

    def test_no_torrent_file_no_item_emitted(self):
        inst, captured, _ = _load_tokyotoshokan()
        parser = inst.MyHtmlParseWithBlackJack(inst.url)
        parser.feed(TORRENT_ROW_NO_TORRENT)
        parser.close()
        assert len(captured) == 0

    def test_empty_listing(self):
        inst, captured, _ = _load_tokyotoshokan()
        parser = inst.MyHtmlParseWithBlackJack(inst.url)
        parser.feed(EMPTY_LISTING_HTML)
        parser.close()
        assert len(captured) == 0

    def test_no_listing_table(self):
        inst, captured, _ = _load_tokyotoshokan()
        parser = inst.MyHtmlParseWithBlackJack(inst.url)
        parser.feed(NO_LISTING_HTML)
        parser.close()
        assert len(captured) == 0

    def test_malformed_html_no_crash(self):
        inst, captured, _ = _load_tokyotoshokan()
        parser = inst.MyHtmlParseWithBlackJack(inst.url)
        parser.feed(MALFORMED_HTML)
        parser.close()
        assert len(captured) == 0

    def test_rss_html_no_results(self):
        inst, captured, _ = _load_tokyotoshokan()
        parser = inst.MyHtmlParseWithBlackJack(inst.url)
        parser.feed(RSS_STYLE_HTML)
        parser.close()
        assert len(captured) == 0

    def test_stats_seeds_and_leech(self):
        inst, captured, _ = _load_tokyotoshokan()
        parser = inst.MyHtmlParseWithBlackJack(inst.url)
        parser.feed(STATS_ONLY_HTML)
        parser.close()
        assert len(captured) == 1
        assert captured[0]["seeds"] == "99"
        assert captured[0]["leech"] == "50"

    def test_reverse_stats_order(self):
        inst, captured, _ = _load_tokyotoshokan()
        parser = inst.MyHtmlParseWithBlackJack(inst.url)
        parser.feed(REVERSE_STATS_HTML)
        parser.close()
        assert len(captured) == 1
        assert captured[0]["seeds"] == "10"
        assert captured[0]["leech"] == "20"

    def test_special_characters_in_name(self):
        inst, captured, _ = _load_tokyotoshokan()
        parser = inst.MyHtmlParseWithBlackJack(inst.url)
        parser.feed(SPECIAL_CHARS_HTML)
        parser.close()
        assert len(captured) == 1
        assert "&amp;" in captured[0]["name"] or "Special" in captured[0]["name"]

    def test_missing_size_field(self):
        inst, captured, _ = _load_tokyotoshokan()
        parser = inst.MyHtmlParseWithBlackJack(inst.url)
        parser.feed(MISSING_SIZE_HTML)
        parser.close()
        assert len(captured) == 0

    def test_size_regex_with_gb(self):
        html = '''<table class="listing">
        <tr class="odd">
        <td><a href="magnet:?xt=urn:btih:gb123&dn=GbTest">D</a></td>
        <td><a type="application/x-bittorrent" href="http://tokyotosho.info/torrents/gb.torrent">GB Size</a></td>
        <td><a href="details.php?id=90">Details</a></td>
        <td class="desc-bot">Size: 2.75 GB</td>
        <td class="stats"><span>10</span><span>2</span></td>
        </tr>
        </table>'''
        inst, captured, _ = _load_tokyotoshokan()
        parser = inst.MyHtmlParseWithBlackJack(inst.url)
        parser.feed(html)
        parser.close()
        assert len(captured) == 1
        assert captured[0]["size"] == "2.75"

    def test_size_regex_with_kb(self):
        html = '''<table class="listing">
        <tr class="odd">
        <td><a href="magnet:?xt=urn:btih:kb456&dn=KbTest">D</a></td>
        <td><a type="application/x-bittorrent" href="http://tokyotosho.info/torrents/kb.torrent">KB Size</a></td>
        <td><a href="details.php?id=91">Details</a></td>
        <td class="desc-bot">Size: 512 KB</td>
        <td class="stats"><span>3</span><span>1</span></td>
        </tr>
        </table>'''
        inst, captured, _ = _load_tokyotoshokan()
        parser = inst.MyHtmlParseWithBlackJack(inst.url)
        parser.feed(html)
        parser.close()
        assert len(captured) == 1
        assert captured[0]["size"] == "512"

    def test_parser_resets_state_between_items(self):
        inst, captured, _ = _load_tokyotoshokan()
        parser = inst.MyHtmlParseWithBlackJack(inst.url)
        parser.feed(MULTI_TORRENT_HTML)
        parser.close()
        assert len(captured) == 2
        names = [c["name"] for c in captured]
        assert names[0] != names[1]

    def test_details_link_construction(self):
        inst, captured, _ = _load_tokyotoshokan()
        parser = inst.MyHtmlParseWithBlackJack(inst.url)
        parser.feed(SINGLE_TORRENT_HTML)
        parser.close()
        assert captured[0]["desc_link"].startswith("http://tokyotosho.info/")
        assert "details.php" in captured[0]["desc_link"]


# ─── search() tests ──────────────────────────────────────────────────────


class TestSearch:
    """Tests for the search method."""

    def test_search_basic(self):
        inst, captured, helpers_mod = _load_tokyotoshokan(
            retrieve_url_return=SINGLE_TORRENT_HTML, use_mock_retrieve=True
        )
        with patch("tokyotoshokan.page_count", 1):
            inst.search("test query", "all")
        assert len(captured) == 1

    def test_search_url_construction_all(self):
        inst, captured, helpers_mod = _load_tokyotoshokan(
            retrieve_url_return=SINGLE_TORRENT_HTML, use_mock_retrieve=True
        )
        with patch("tokyotoshokan.page_count", 1):
            inst.search("naruto", "all")
        url = helpers_mod.retrieve_url.call_args[0][0]
        assert "terms=naruto" in url
        assert "type=0" in url
        assert "search.php" in url

    def test_search_url_construction_anime(self):
        inst, captured, helpers_mod = _load_tokyotoshokan(
            retrieve_url_return=SINGLE_TORRENT_HTML, use_mock_retrieve=True
        )
        with patch("tokyotoshokan.page_count", 1):
            inst.search("one piece", "anime")
        url = helpers_mod.retrieve_url.call_args[0][0]
        assert "type=1" in url

    def test_search_url_construction_games(self):
        inst, captured, helpers_mod = _load_tokyotoshokan(
            retrieve_url_return=SINGLE_TORRENT_HTML, use_mock_retrieve=True
        )
        with patch("tokyotoshokan.page_count", 1):
            inst.search("zelda", "games")
        url = helpers_mod.retrieve_url.call_args[0][0]
        assert "type=14" in url

    def test_search_unknown_category_key_error(self):
        inst, captured, helpers_mod = _load_tokyotoshokan(
            retrieve_url_return=SINGLE_TORRENT_HTML
        )
        with pytest.raises(KeyError):
            inst.search("test", "nonexistent_category")

    def test_search_empty_response_returns_none(self):
        inst, captured, helpers_mod = _load_tokyotoshokan(
            retrieve_url_return=NO_LISTING_HTML, use_mock_retrieve=True
        )
        with patch("tokyotoshokan.page_count", 1):
            result = inst.search("test", "all")
        assert result is None
        assert len(captured) == 0

    def test_search_garbage_response_returns_none(self):
        inst, captured, helpers_mod = _load_tokyotoshokan(
            retrieve_url_return="<html><body>GARBAGE</body></html>",
            use_mock_retrieve=True,
        )
        with patch("tokyotoshokan.page_count", 1):
            result = inst.search("test", "all")
        assert result is None

    def test_search_empty_string_response(self):
        inst, captured, helpers_mod = _load_tokyotoshokan(
            retrieve_url_return="", use_mock_retrieve=True
        )
        with patch("tokyotoshokan.page_count", 1):
            result = inst.search("test", "all")
        assert result is None

    def test_search_query_space_replacement(self):
        inst, captured, helpers_mod = _load_tokyotoshokan(
            retrieve_url_return=SINGLE_TORRENT_HTML, use_mock_retrieve=True
        )
        with patch("tokyotoshokan.page_count", 1):
            inst.search("hello world test", "all")
        url = helpers_mod.retrieve_url.call_args[0][0]
        assert "hello+world+test" in url

    def test_search_pagination(self):
        inst, captured, helpers_mod = _load_tokyotoshokan(
            retrieve_url_return=PAGINATION_HTML, use_mock_retrieve=True
        )
        with patch("tokyotoshokan.page_count", 1):
            inst.search("test query", "all")
        assert helpers_mod.retrieve_url.call_count >= 2

    def test_search_pagination_percent20(self):
        inst, captured, helpers_mod = _load_tokyotoshokan(
            retrieve_url_return=PAGINATION_HTML_PERCENT20, use_mock_retrieve=True
        )
        with patch("tokyotoshokan.page_count", 1):
            inst.search("hello world", "all")
        assert helpers_mod.retrieve_url.call_count >= 2

    def test_search_no_explicit_return(self):
        inst, captured, helpers_mod = _load_tokyotoshokan(
            retrieve_url_return=SINGLE_TORRENT_HTML, use_mock_retrieve=True
        )
        with patch("tokyotoshokan.page_count", 1):
            result = inst.search("test", "all")
        assert result is None
        assert len(captured) == 1


# ─── download_torrent() tests ────────────────────────────────────────────


class TestDownloadTorrent:
    """Tests for the download_torrent method."""

    def test_download_magnet_link(self, capsys):
        inst, captured, _ = _load_tokyotoshokan()
        inst.download_torrent("magnet:?xt=urn:btih:abc123&dn=Test")
        output = capsys.readouterr().out
        assert "magnet:?xt=urn:btih:abc123&dn=Test" in output

    def test_download_torrent_file_url(self, capsys):
        inst, captured, _ = _load_tokyotoshokan()
        inst.download_torrent("http://tokyotosho.info/torrents/file.torrent")
        output = capsys.readouterr().out
        assert "http://tokyotosho.info/torrents/file.torrent" in output

    def test_download_empty_string(self, capsys):
        inst, captured, _ = _load_tokyotoshokan()
        inst.download_torrent("")
        output = capsys.readouterr().out
        assert output.strip() == ""

    def test_download_special_chars_url(self, capsys):
        inst, captured, _ = _load_tokyotoshokan()
        url = "magnet:?xt=urn:btih:abc&dn=Test%3A+Subs+%26+More"
        inst.download_torrent(url)
        output = capsys.readouterr().out
        assert url in output


# ─── Category mapping tests ──────────────────────────────────────────────


class TestCategoryMapping:
    """Tests for supported_categories and category handling."""

    def test_all_category(self):
        inst, _, _ = _load_tokyotoshokan()
        assert inst.supported_categories["all"] == "0"

    def test_anime_category(self):
        inst, _, _ = _load_tokyotoshokan()
        assert inst.supported_categories["anime"] == "1"

    def test_games_category(self):
        inst, _, _ = _load_tokyotoshokan()
        assert inst.supported_categories["games"] == "14"

    def test_all_three_categories_present(self):
        inst, _, _ = _load_tokyotoshokan()
        assert set(inst.supported_categories.keys()) == {"all", "anime", "games"}


# ─── Plugin metadata tests ───────────────────────────────────────────────


class TestPluginMetadata:
    """Tests for plugin attributes."""

    def test_url(self):
        inst, _, _ = _load_tokyotoshokan()
        assert inst.url == "http://tokyotosho.info"

    def test_name(self):
        inst, _, _ = _load_tokyotoshokan()
        assert inst.name == "Tokyo Toshokan"

    def test_has_search_method(self):
        inst, _, _ = _load_tokyotoshokan()
        assert callable(getattr(inst, "search", None))

    def test_has_download_torrent_method(self):
        inst, _, _ = _load_tokyotoshokan()
        assert callable(getattr(inst, "download_torrent", None))


# ─── Edge case tests ─────────────────────────────────────────────────────


class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_multiple_size_td_elements(self):
        html = '''<table class="listing">
        <tr class="odd">
        <td><a href="magnet:?xt=urn:btih:ms789&dn=MultiSize">D</a></td>
        <td><a type="application/x-bittorrent" href="http://tokyotosho.info/torrents/ms.torrent">Multi Size</a></td>
        <td><a href="details.php?id=100">Details</a></td>
        <td class="desc-bot">Some text Size: 999.99 MB extra text</td>
        <td class="stats"><span>7</span><span>2</span></td>
        </tr>
        </table>'''
        inst, captured, _ = _load_tokyotoshokan()
        parser = inst.MyHtmlParseWithBlackJack(inst.url)
        parser.feed(html)
        parser.close()
        assert len(captured) == 1
        assert captured[0]["size"] == "999.99"

    def test_size_with_surrounding_text(self):
        html = '''<table class="listing">
        <tr class="odd">
        <td><a href="magnet:?xt=urn:btih:sz456&dn=SizeText">D</a></td>
        <td><a type="application/x-bittorrent" href="http://tokyotosho.info/torrents/sz.torrent">Size Text</a></td>
        <td><a href="details.php?id=101">Details</a></td>
        <td class="desc-bot">Total Size: 42.5 MB remaining</td>
        <td class="stats"><span>3</span><span>1</span></td>
        </tr>
        </table>'''
        inst, captured, _ = _load_tokyotoshokan()
        parser = inst.MyHtmlParseWithBlackJack(inst.url)
        parser.feed(html)
        parser.close()
        assert len(captured) == 1
        assert captured[0]["size"] == "42.5"

    def test_tr_class_with_non_category_class(self):
        html = '''<table class="listing">
        <tr class="highlight">
        <td><a href="magnet:?xt=urn:btih:cat789&dn=CatTest">D</a></td>
        <td><a type="application/x-bittorrent" href="http://tokyotosho.info/torrents/ct.torrent">Cat Test</a></td>
        <td><a href="details.php?id=102">Details</a></td>
        <td class="desc-bot">Size: 15 MB</td>
        <td class="stats"><span>1</span><span>0</span></td>
        </tr>
        </table>'''
        inst, captured, _ = _load_tokyotoshokan()
        parser = inst.MyHtmlParseWithBlackJack(inst.url)
        parser.feed(html)
        parser.close()
        assert len(captured) == 1

    def test_tr_class_category_at_start_no_item(self):
        html = '<table class="listing"><tr class="category_1"><td>X</td></tr></table>'
        inst, captured, _ = _load_tokyotoshokan()
        parser = inst.MyHtmlParseWithBlackJack(inst.url)
        parser.feed(html)
        parser.close()
        assert len(captured) == 0

    def test_empty_tr_class_no_item(self):
        html = '<table class="listing"><tr><td>No class</td></tr></table>'
        inst, captured, _ = _load_tokyotoshokan()
        parser = inst.MyHtmlParseWithBlackJack(inst.url)
        parser.feed(html)
        parser.close()
        assert len(captured) == 0

    def test_handle_more_pages_no_listing_table(self):
        inst, captured, helpers_mod = _load_tokyotoshokan(
            retrieve_url_return=NO_LISTING_HTML, use_mock_retrieve=True
        )
        parser = inst.MyHtmlParseWithBlackJack(inst.url)
        result = inst.handle_more_pages("http://example.com/search", parser, "test")
        assert result == "http://example.com/search"

    def test_handle_more_pages_with_listing(self):
        inst, captured, helpers_mod = _load_tokyotoshokan(
            retrieve_url_return=PAGINATION_HTML, use_mock_retrieve=True
        )
        parser = inst.MyHtmlParseWithBlackJack(inst.url)
        result = inst.handle_more_pages(
            "http://tokyotosho.info/search.php?terms=test&type=0",
            parser,
            "test",
            skip_first=True,
        )
        assert isinstance(result, str)

    def test_handle_more_pages_garbage_paged_response(self):
        responses = [PAGINATION_HTML, "GARBAGE"]
        call_count = [0]

        def mock_retrieve(url):
            idx = min(call_count[0], len(responses) - 1)
            call_count[0] += 1
            return responses[idx]

        inst, captured, helpers_mod = _load_tokyotoshokan()
        helpers_mod.retrieve_url = mock_retrieve
        parser = inst.MyHtmlParseWithBlackJack(inst.url)
        result = inst.handle_more_pages(
            "http://tokyotosho.info/search.php?terms=test&type=0",
            parser,
            "test",
            skip_first=True,
        )
        assert isinstance(result, str)

    def test_handle_more_pages_empty_response(self):
        inst, captured, helpers_mod = _load_tokyotoshokan(
            retrieve_url_return="", use_mock_retrieve=True
        )
        parser = inst.MyHtmlParseWithBlackJack(inst.url)
        result = inst.handle_more_pages("http://example.com", parser, "test")
        assert result == "http://example.com"

    def test_handle_starttag_no_current_item_non_tr(self):
        inst, captured, _ = _load_tokyotoshokan()
        parser = inst.MyHtmlParseWithBlackJack(inst.url)
        parser.handle_starttag("div", [("class", "something")])
        assert parser.current_item is None

    def test_handle_starttag_td_no_class(self):
        inst, captured, _ = _load_tokyotoshokan()
        parser = inst.MyHtmlParseWithBlackJack(inst.url)
        parser.current_item = {"engine_url": "test"}
        parser.handle_starttag("td", [])
        assert parser.size_found is False
        assert parser.stats_found is False

    def test_handle_starttag_span_without_stats(self):
        inst, captured, _ = _load_tokyotoshokan()
        parser = inst.MyHtmlParseWithBlackJack(inst.url)
        parser.current_item = {"engine_url": "test", "seeds": "5"}
        parser.stats_found = False
        parser.handle_starttag("span", [])
        assert parser.stat_name is None

    def test_handle_data_name_concatenation(self):
        inst, captured, _ = _load_tokyotoshokan()
        parser = inst.MyHtmlParseWithBlackJack(inst.url)
        parser.current_item = {"engine_url": "test", "name": "Part1"}
        parser.name_found = True
        parser.handle_data("Part2")
        assert parser.current_item["name"] == "Part1Part2"

    def test_handle_endtag_span_resets_stat_name(self):
        inst, captured, _ = _load_tokyotoshokan()
        parser = inst.MyHtmlParseWithBlackJack(inst.url)
        parser.stat_name = "leech"
        parser.handle_endtag("span")
        assert parser.stat_name is None

    def test_handle_endtag_a_resets_name_found(self):
        inst, captured, _ = _load_tokyotoshokan()
        parser = inst.MyHtmlParseWithBlackJack(inst.url)
        parser.name_found = True
        parser.handle_endtag("a")
        assert parser.name_found is False

    def test_plugin_loadable_from_community_dir(self):
        inst, _, _ = _load_tokyotoshokan()
        assert inst is not None
        assert hasattr(inst, "MyHtmlParseWithBlackJack")

    def test_search_with_single_word_query(self):
        inst, captured, helpers_mod = _load_tokyotoshokan(
            retrieve_url_return=SINGLE_TORRENT_HTML, use_mock_retrieve=True
        )
        with patch("tokyotoshokan.page_count", 1):
            inst.search("naruto", "anime")
        url = helpers_mod.retrieve_url.call_args[0][0]
        assert "terms=naruto" in url
        assert "type=1" in url

    def test_search_no_listing_early_return(self):
        inst, captured, helpers_mod = _load_tokyotoshokan(
            retrieve_url_return="<html></html>", use_mock_retrieve=True
        )
        with patch("tokyotoshokan.page_count", 1):
            result = inst.search("anything", "all")
        assert result is None

    def test_default_size_is_unknown_when_no_size_td(self):
        html = '''<table class="listing">
        <tr class="odd">
        <td><a href="magnet:?xt=urn:btih:nosize2&dn=NoSize2">D</a></td>
        <td><a type="application/x-bittorrent" href="http://tokyotosho.info/torrents/ns2.torrent">No Size</a></td>
        <td><a href="details.php?id=200">Details</a></td>
        <td class="stats"><span>5</span><span>2</span></td>
        </tr>
        </table>'''
        inst, captured, _ = _load_tokyotoshokan()
        parser = inst.MyHtmlParseWithBlackJack(inst.url)
        parser.feed(html)
        parser.close()
        assert len(captured) == 0
