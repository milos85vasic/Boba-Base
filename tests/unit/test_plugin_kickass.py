"""Deep coverage tests for plugins/kickass.py.

Covers: HTMLParser.feed (single/multi/empty/malformed), __findTorrents
(regex edge cases), __retrieve_download_link (magnet extraction),
search (URL construction, category mapping, pagination, strong-tag
stripping), download_torrent (magnet passthrough, page fetch, no-link).

Known fragility:
  - BOB-015: sleep(1) in __findTorrents per-result; patched out below.
  - Plugin re-fetches detail page per result; every result in the search
    page triggers a retrieve_url call for its magnet link.
  - Comma-separated sizes (e.g. "1,234.5 MB") are NOT matched by the
    inner regex \\d+\\.\\d+ — this is a real parsing gap.
"""

import importlib.util
import os
import re
import sys
import types
from urllib.error import URLError
from unittest.mock import MagicMock, patch

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PLUGINS_DIR = os.path.join(REPO, "plugins")


def _load_kickass(captured=None, retrieve_return=""):
    """Import kickass plugin with stub modules.

    Args:
        captured: list that prettyPrinter results are appended to.
        retrieve_return: return value for helpers.retrieve_url — can be
            a string (HTML) or a callable(url) -> str.
    """
    if captured is None:
        captured = []

    np_mod = types.ModuleType("novaprinter")
    np_mod.prettyPrinter = lambda d: captured.append(dict(d))
    sys.modules["novaprinter"] = np_mod

    helpers_mod = types.ModuleType("helpers")
    if callable(retrieve_return):
        helpers_mod.retrieve_url = retrieve_return
    else:
        helpers_mod.retrieve_url = lambda url: retrieve_return
    sys.modules["helpers"] = helpers_mod

    sys.modules.pop("kickass", None)

    path = os.path.join(PLUGINS_DIR, "kickass.py")
    spec = importlib.util.spec_from_file_location("kickass", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules["kickass"] = mod

    cls = getattr(mod, "kickass", None)
    if cls is not None and isinstance(cls, type):
        return cls(), captured
    return mod, captured


# ─── HTML fixtures ────────────────────────────────────────────────────────────

MAGNET_LINK = "magnet:?xt=urn:btih:abc123def&dn=Test+Torrent"

DETAIL_PAGE_WITH_MAGNET = f'''<html><body>
<a href="{MAGNET_LINK}" class="magnetLink">Download</a>
</body></html>'''

DETAIL_PAGE_NO_MAGNET = "<html><body>No magnet found here.</body></html>"

TR_ROW = '''<tr class="odd">
<td class="icon"><img src="/static/img/blank.png" /></td>
<td>
<div class="torrentname">
<a href="details/test-torrent-12345"  class="cellMainLink">
  Test Torrent Name
</a>
</div>
</td>
<td>1.5 GB</td>
<td class="green center"> 123 </td>
<td class="red lasttd center"> 45 </td>
</tr>'''

TR_ROW_EVEN = '''<tr class="even">
<td class="icon"><img src="/static/img/blank.png" /></td>
<td>
<div class="torrentname">
<a href="details/another-torrent-67890"  class="cellMainLink">
  Another Torrent
</a>
</div>
</td>
<td>500 MB</td>
<td class="green center"> 10 </td>
<td class="red lasttd center"> 2 </td>
</tr>'''

TR_ROW_SMALL = '''<tr class="odd">
<td class="icon"><img src="/static/img/blank.png" /></td>
<td>
<div class="torrentname">
<a href="details/small-torrent"  class="cellMainLink">
  Small Torrent
</a>
</div>
</td>
<td>25.5 KB</td>
<td class="green center"> 5 </td>
<td class="red lasttd center"> 1 </td>
</tr>'''

TR_ROW_TB = '''<tr class="odd">
<td class="icon"><img src="/static/img/blank.png" /></td>
<td>
<div class="torrentname">
<a href="details/big-torrent"  class="cellMainLink">
  Big Torrent
</a>
</div>
</td>
<td>2.3 TB</td>
<td class="green center"> 500 </td>
<td class="red lasttd center"> 100 </td>
</tr>'''

TR_ROW_COMMA_SIZE = '''<tr class="odd">
<td class="icon"><img src="/static/img/blank.png" /></td>
<td>
<div class="torrentname">
<a href="details/comma-torrent"  class="cellMainLink">
  Comma Torrent
</a>
</div>
</td>
<td>1,234.5 MB</td>
<td class="green center"> 1000 </td>
<td class="red lasttd center"> 200 </td>
</tr>'''

TR_ROW_STRONG = '''<tr class="odd">
<td class="icon"><img src="/static/img/blank.png" /></td>
<td>
<div class="torrentname">
<a href="details/strong-torrent"  class="cellMainLink">
  <strong>Bold</strong> Torrent
</a>
</div>
</td>
<td>100 MB</td>
<td class="green center"> 10 </td>
<td class="red lasttd center"> 3 </td>
</tr>'''

SINGLE_RESULT_HTML = TR_ROW
MULTI_RESULT_HTML = TR_ROW + "\n" + TR_ROW_EVEN
THREE_RESULT_HTML = TR_ROW + "\n" + TR_ROW_EVEN + "\n" + TR_ROW_TB
EMPTY_HTML = "<html><body>No results</body></html>"
MALFORMED_HTML = '<tr class="odd"><td>incomplete</td></tr>'
INCOMPLETE_TR = '<tr class="odd"><td>missing fields</td></tr>'


# ─── HTMLParser.feed tests ────────────────────────────────────────────────────

class TestHTMLParserFeed:
    def test_single_result(self):
        plugin, captured = _load_kickass(retrieve_return=DETAIL_PAGE_WITH_MAGNET)
        parser = plugin.HTMLParser(plugin.url)
        parser.feed(SINGLE_RESULT_HTML)
        assert parser.noTorrents is False
        assert len(captured) == 1
        assert captured[0]["name"] == "Test Torrent Name"
        assert captured[0]["size"] == "1.5 GB"
        assert captured[0]["seeds"] == "123"
        assert captured[0]["leech"] == "45"
        assert captured[0]["desc_link"].endswith("details/test-torrent-12345")
        assert captured[0]["link"] == MAGNET_LINK

    def test_multi_results(self):
        plugin, captured = _load_kickass(retrieve_return=DETAIL_PAGE_WITH_MAGNET)
        parser = plugin.HTMLParser(plugin.url)
        parser.feed(MULTI_RESULT_HTML)
        assert parser.noTorrents is False
        assert len(captured) == 2
        assert captured[0]["name"] == "Test Torrent Name"
        assert captured[1]["name"] == "Another Torrent"
        assert captured[1]["size"] == "500 MB"

    def test_three_results(self):
        plugin, captured = _load_kickass(retrieve_return=DETAIL_PAGE_WITH_MAGNET)
        parser = plugin.HTMLParser(plugin.url)
        parser.feed(THREE_RESULT_HTML)
        assert len(captured) == 3
        assert captured[2]["name"] == "Big Torrent"
        assert captured[2]["size"] == "2.3 TB"
        assert captured[2]["seeds"] == "500"
        assert captured[2]["leech"] == "100"

    def test_empty_html(self):
        plugin, captured = _load_kickass()
        parser = plugin.HTMLParser(plugin.url)
        parser.feed(EMPTY_HTML)
        assert parser.noTorrents is True
        assert len(captured) == 0

    def test_malformed_html_tr_matches_but_inner_fails(self):
        """<tr class='odd'> matches the outer regex even with incomplete
        inner content. noTorrents stays False because TRs were found, but
        no results are emitted because the inner regex doesn't match."""
        plugin, captured = _load_kickass()
        parser = plugin.HTMLParser(plugin.url)
        parser.feed(MALFORMED_HTML)
        assert parser.noTorrents is False
        assert len(captured) == 0

    def test_incomplete_tr_same_as_malformed(self):
        """Same behavior: TR regex matches, inner regex fails, no results."""
        plugin, captured = _load_kickass()
        parser = plugin.HTMLParser(plugin.url)
        parser.feed(INCOMPLETE_TR)
        assert parser.noTorrents is False
        assert len(captured) == 0

    def test_feed_resets_no_torrents(self):
        plugin, captured = _load_kickass(retrieve_return=DETAIL_PAGE_WITH_MAGNET)
        parser = plugin.HTMLParser(plugin.url)
        parser.feed(EMPTY_HTML)
        assert parser.noTorrents is True
        parser.feed(SINGLE_RESULT_HTML)
        assert parser.noTorrents is False
        assert len(captured) == 1

    def test_comma_in_size_now_matched_by_regex(self):
        """The regex now includes commas in the size pattern, so
        '1,234.5 MB' is correctly matched and commas are stripped."""
        plugin, captured = _load_kickass(retrieve_return=DETAIL_PAGE_WITH_MAGNET)
        parser = plugin.HTMLParser(plugin.url)
        parser.feed(TR_ROW_COMMA_SIZE)
        assert parser.noTorrents is False
        assert len(captured) == 1
        assert captured[0]["size"] == "1234.5 MB"

    def test_kb_size(self):
        plugin, captured = _load_kickass(retrieve_return=DETAIL_PAGE_WITH_MAGNET)
        parser = plugin.HTMLParser(plugin.url)
        parser.feed(TR_ROW_SMALL)
        assert captured[0]["size"] == "25.5 KB"

    def test_tb_size(self):
        plugin, captured = _load_kickass(retrieve_return=DETAIL_PAGE_WITH_MAGNET)
        parser = plugin.HTMLParser(plugin.url)
        parser.feed(TR_ROW_TB)
        assert captured[0]["size"] == "2.3 TB"

    def test_even_class_row(self):
        plugin, captured = _load_kickass(retrieve_return=DETAIL_PAGE_WITH_MAGNET)
        parser = plugin.HTMLParser(plugin.url)
        parser.feed(TR_ROW_EVEN)
        assert len(captured) == 1
        assert captured[0]["name"] == "Another Torrent"

    def test_strong_tags_preserved_by_parser(self):
        """The parser does NOT strip <strong> tags. Only search() does via
        re.sub before feeding. The raw tag content passes through."""
        plugin, captured = _load_kickass(retrieve_return=DETAIL_PAGE_WITH_MAGNET)
        parser = plugin.HTMLParser(plugin.url)
        parser.feed(TR_ROW_STRONG)
        assert len(captured) == 1
        assert "<strong>" in captured[0]["name"]

    def test_engine_url_set(self):
        plugin, captured = _load_kickass(retrieve_return=DETAIL_PAGE_WITH_MAGNET)
        parser = plugin.HTMLParser(plugin.url)
        parser.feed(SINGLE_RESULT_HTML)
        assert captured[0]["engine_url"] == plugin.url

    def test_detail_link_prefix(self):
        plugin, captured = _load_kickass(retrieve_return=DETAIL_PAGE_WITH_MAGNET)
        parser = plugin.HTMLParser(plugin.url)
        parser.feed(SINGLE_RESULT_HTML)
        assert captured[0]["desc_link"].startswith("https://kickasstorrents.to/")


# ─── __retrieve_download_link tests ───────────────────────────────────────────

class TestRetrieveDownloadLink:
    def test_magnet_found(self):
        plugin, captured = _load_kickass(retrieve_return=DETAIL_PAGE_WITH_MAGNET)
        parser = plugin.HTMLParser(plugin.url)
        result = parser._HTMLParser__retrieve_download_link("http://fake/detail")
        assert result == MAGNET_LINK

    def test_magnet_not_found(self):
        plugin, captured = _load_kickass(retrieve_return=DETAIL_PAGE_NO_MAGNET)
        parser = plugin.HTMLParser(plugin.url)
        result = parser._HTMLParser__retrieve_download_link("http://fake/detail")
        assert result == "NotFound"

    def test_magnet_in_various_positions(self):
        html = f'<html><a href="other">x</a><a href="{MAGNET_LINK}">dl</a></html>'
        plugin, captured = _load_kickass(retrieve_return=html)
        parser = plugin.HTMLParser(plugin.url)
        result = parser._HTMLParser__retrieve_download_link("http://fake/detail")
        assert result == MAGNET_LINK

    def test_magnet_with_extra_attrs(self):
        magnet = "magnet:?xt=urn:btih:abc123&dn=Test&tr=http://tracker:8080"
        html = f'<a href="{magnet}" class="download">Download</a>'
        plugin, captured = _load_kickass(retrieve_return=html)
        parser = plugin.HTMLParser(plugin.url)
        result = parser._HTMLParser__retrieve_download_link("http://fake/detail")
        assert result.startswith("magnet:")

    def test_empty_page_returns_not_found(self):
        plugin, captured = _load_kickass(retrieve_return="")
        parser = plugin.HTMLParser(plugin.url)
        result = parser._HTMLParser__retrieve_download_link("http://fake/detail")
        assert result == "NotFound"

    def test_exception_in_retrieve_returns_not_found(self):
        """__retrieve_download_link catches Exception from retrieve_url and
        returns 'NotFound'."""

        def fail_url(url):
            raise ConnectionError("refused")

        plugin, captured = _load_kickass(retrieve_return=fail_url)
        parser = plugin.HTMLParser(plugin.url)
        result = parser._HTMLParser__retrieve_download_link("http://fake/detail")
        assert result == "NotFound"


# ─── search() tests ───────────────────────────────────────────────────────────

class TestSearch:
    def test_url_construction_all_category(self):
        urls_seen = []

        def capture_url(url):
            urls_seen.append(url)
            return EMPTY_HTML

        plugin, captured = _load_kickass(retrieve_return=capture_url)
        plugin.search("ubuntu")
        assert len(urls_seen) >= 1
        assert urls_seen[0] == "https://kickasstorrents.to/search/ubuntu/0/"

    def test_url_construction_movies_category(self):
        urls_seen = []

        def capture_url(url):
            urls_seen.append(url)
            return EMPTY_HTML

        plugin, captured = _load_kickass(retrieve_return=capture_url)
        plugin.search("matrix", cat="movies")
        assert urls_seen[0] == "https://kickasstorrents.to/search/matrix/category/movies/0/"

    def test_url_construction_tv_category(self):
        urls_seen = []

        def capture_url(url):
            urls_seen.append(url)
            return EMPTY_HTML

        plugin, captured = _load_kickass(retrieve_return=capture_url)
        plugin.search("breaking", cat="tv")
        assert urls_seen[0] == "https://kickasstorrents.to/search/breaking/category/tv/0/"

    def test_url_construction_music_category(self):
        urls_seen = []

        def capture_url(url):
            urls_seen.append(url)
            return EMPTY_HTML

        plugin, captured = _load_kickass(retrieve_return=capture_url)
        plugin.search("beatles", cat="music")
        assert urls_seen[0] == "https://kickasstorrents.to/search/beatles/category/music/0/"

    def test_url_construction_games_category(self):
        urls_seen = []

        def capture_url(url):
            urls_seen.append(url)
            return EMPTY_HTML

        plugin, captured = _load_kickass(retrieve_return=capture_url)
        plugin.search("witcher", cat="games")
        assert urls_seen[0] == "https://kickasstorrents.to/search/witcher/category/games/0/"

    def test_url_construction_anime_category(self):
        urls_seen = []

        def capture_url(url):
            urls_seen.append(url)
            return EMPTY_HTML

        plugin, captured = _load_kickass(retrieve_return=capture_url)
        plugin.search("naruto", cat="anime")
        assert urls_seen[0] == "https://kickasstorrents.to/search/naruto/category/anime/0/"

    def test_url_construction_software_category(self):
        urls_seen = []

        def capture_url(url):
            urls_seen.append(url)
            return EMPTY_HTML

        plugin, captured = _load_kickass(retrieve_return=capture_url)
        plugin.search("photoshop", cat="software")
        assert urls_seen[0] == "https://kickasstorrents.to/search/photoshop/category/apps/0/"

    def test_pagination_stops_on_empty(self):
        """Search page with 1 result triggers 3 retrieve_url calls:
        search(1) -> detail(1) -> search(2)=EMPTY -> break."""
        call_count = 0

        def first_page_then_empty(url):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return SINGLE_RESULT_HTML
            return EMPTY_HTML

        plugin, captured = _load_kickass(retrieve_return=first_page_then_empty)
        with patch("kickass.sleep"):
            plugin.search("test")
        assert call_count == 3
        assert len(captured) == 1

    def test_pagination_advances_counter(self):
        search_urls = []

        def two_pages_then_empty(url):
            if "search/" in url:
                search_urls.append(url)
                if len(search_urls) <= 2:
                    return SINGLE_RESULT_HTML
                return EMPTY_HTML
            return DETAIL_PAGE_WITH_MAGNET

        plugin, captured = _load_kickass(retrieve_return=two_pages_then_empty)
        with patch("kickass.sleep"):
            plugin.search("query")
        assert len(search_urls) == 3
        assert search_urls[0] == "https://kickasstorrents.to/search/query/0/"
        assert search_urls[1] == "https://kickasstorrents.to/search/query/1/"
        assert len(captured) == 2

    def test_strong_tags_stripped_by_search(self):
        """search() runs re.sub to strip <strong> tags before feeding."""
        html_with_strong = (
            '<tr class="odd"><td><div class="torrentname">'
            '<a href="details/x" class="cellMainLink">'
            '  <strong>Bold</strong> Name  </a></div></td>'
            '<td>100 MB</td><td class="green center"> 10 </td>'
            '<td class="red lasttd center"> 3 </td></tr>'
        )
        call_count = 0

        def serve_first_only(url):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return html_with_strong
            return EMPTY_HTML

        plugin, captured = _load_kickass(retrieve_return=serve_first_only)
        with patch("kickass.sleep"):
            plugin.search("bold")
        assert len(captured) == 1
        assert captured[0]["name"] == "Bold Name"

    def test_search_with_special_characters(self):
        """Plugin does not URL-encode the query; it passes through raw."""
        urls_seen = []

        def capture_url(url):
            urls_seen.append(url)
            return EMPTY_HTML

        plugin, captured = _load_kickass(retrieve_return=capture_url)
        plugin.search("c++ & friends")
        assert urls_seen[0] == "https://kickasstorrents.to/search/c++ & friends/0/"

    def test_search_exception_breaks_loop_silently(self):
        """search() catches Exception from retrieve_url and breaks the loop,
        returning without raising. This is the actual plugin behavior."""
        def fail_url(url):
            raise URLError("timeout")

        plugin, captured = _load_kickass(retrieve_return=fail_url)
        plugin.search("test")
        assert len(captured) == 0

    def test_sleep_called_between_pages(self):
        call_count = 0

        def two_pages(url):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return SINGLE_RESULT_HTML
            return EMPTY_HTML

        plugin, captured = _load_kickass(retrieve_return=two_pages)
        with patch("kickass.sleep") as mock_sleep:
            plugin.search("test")
        assert mock_sleep.called


# ─── download_torrent() tests ─────────────────────────────────────────────────

class TestDownloadTorrent:
    def test_magnet_passthrough(self, capsys):
        plugin, _ = _load_kickass()
        plugin.download_torrent(MAGNET_LINK)
        out = capsys.readouterr().out
        assert MAGNET_LINK in out
        assert plugin.url in out

    def test_non_magnet_fetches_page(self, capsys):
        page_html = f'<html><a href="{MAGNET_LINK}">Download</a></html>'
        plugin, _ = _load_kickass(retrieve_return=page_html)
        plugin.download_torrent("http://example.com/detail")
        out = capsys.readouterr().out
        assert MAGNET_LINK in out

    def test_no_magnet_on_page_prints_url(self, capsys):
        plugin, _ = _load_kickass(retrieve_return=DETAIL_PAGE_NO_MAGNET)
        plugin.download_torrent("http://example.com/detail")
        out = capsys.readouterr().out
        assert "http://example.com/detail" in out
        assert plugin.url in out

    def test_magnet_in_various_positions_on_page(self, capsys):
        magnet = "magnet:?xt=urn:btih:aaa&dn=Deep"
        html = f"<html><p>stuff</p><a href='{magnet}'>click</a></html>"
        plugin, _ = _load_kickass(retrieve_return=html)
        plugin.download_torrent("http://example.com/page")
        out = capsys.readouterr().out
        assert magnet in out

    def test_download_torrent_returns_none(self):
        plugin, _ = _load_kickass(retrieve_return=DETAIL_PAGE_WITH_MAGNET)
        result = plugin.download_torrent("http://example.com/detail")
        assert result is None

    def test_download_torrent_exception_prints_url(self, capsys):
        """download_torrent catches exceptions from retrieve_url and prints
        the URL as fallback."""

        def fail_url(url):
            raise ConnectionError("refused")

        plugin, _ = _load_kickass(retrieve_return=fail_url)
        plugin.download_torrent("http://example.com/detail")
        out = capsys.readouterr().out
        assert "http://example.com/detail" in out
        assert plugin.url in out

    def test_download_torrent_empty_response_prints_url(self, capsys):
        plugin, _ = _load_kickass(retrieve_return="")
        plugin.download_torrent("http://example.com/detail")
        out = capsys.readouterr().out
        assert "http://example.com/detail" in out

    def test_magnet_regex_captures_full_string(self, capsys):
        """The download_torrent regex uses [^\"\\s]+ to capture the full
        magnet URI including query params."""
        long_magnet = "magnet:?xt=urn:btih:abc123&dn=Hello+World&tr=http://tracker:6969/announce"
        plugin, _ = _load_kickass(retrieve_return=f'<a href="{long_magnet}">dl</a>')
        plugin.download_torrent("http://example.com/page")
        out = capsys.readouterr().out
        assert long_magnet in out


# ─── Category mapping tests ───────────────────────────────────────────────────

class TestCategoryMapping:
    def test_all_categories_present(self):
        plugin, _ = _load_kickass()
        expected = {"all", "movies", "tv", "music", "games", "anime", "software"}
        assert set(plugin.supported_categories.keys()) == expected

    def test_all_maps_to_empty(self):
        plugin, _ = _load_kickass()
        assert plugin.supported_categories["all"] == ""

    def test_software_maps_to_apps(self):
        plugin, _ = _load_kickass()
        assert plugin.supported_categories["software"] == "apps"


# ─── Plugin metadata tests ────────────────────────────────────────────────────

class TestPluginMetadata:
    def test_name(self):
        plugin, _ = _load_kickass()
        assert plugin.name == "Kickasstorrents"

    def test_url(self):
        plugin, _ = _load_kickass()
        assert plugin.url == "https://kickasstorrents.to/"


# ─── BOB-015: sleep timing fragility ──────────────────────────────────────────

class TestBOB015SleepFragility:
    """Document the sleep(1) per-result in __findTorrents.

    Each result triggers a 1-second sleep. For a search page with N results,
    this adds N seconds of blocking. With multiple paginated pages, the total
    sleep time is sum(results_per_page) * 1s. This is the root cause of
    BOB-015 (timeout issues on large result sets).

    These tests verify the sleep is called but mock it away for speed.
    """

    def test_sleep_called_per_result(self):
        call_count = 0

        def first_page(url):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return MULTI_RESULT_HTML
            return EMPTY_HTML

        plugin, captured = _load_kickass(retrieve_return=first_page)
        with patch("kickass.sleep") as mock_sleep:
            plugin.search("test")
        assert mock_sleep.call_count == 2

    def test_sleep_called_once_per_result(self):
        call_count = 0

        def first_page(url):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return THREE_RESULT_HTML
            return EMPTY_HTML

        plugin, captured = _load_kickass(retrieve_return=first_page)
        with patch("kickass.sleep") as mock_sleep:
            plugin.search("test")
        assert mock_sleep.call_count == 3

    def test_sleep_arg_is_one(self):
        call_count = 0

        def first_page(url):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return SINGLE_RESULT_HTML
            return EMPTY_HTML

        plugin, captured = _load_kickass(retrieve_return=first_page)
        with patch("kickass.sleep") as mock_sleep:
            plugin.search("test")
        mock_sleep.assert_called_with(1)


# ─── Edge cases ───────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_url_class_attribute(self):
        plugin, _ = _load_kickass()
        assert hasattr(plugin, "url")
        assert plugin.url.startswith("https://")

    def test_htmlparser_class_exists(self):
        plugin, _ = _load_kickass()
        assert hasattr(plugin, "HTMLParser")

    def test_notorrens_initial_state(self):
        plugin, _ = _load_kickass()
        parser = plugin.HTMLParser(plugin.url)
        assert parser.noTorrents is False

    def test_no_results_across_many_pages(self):
        call_count = 0

        def always_empty(url):
            nonlocal call_count
            call_count += 1
            return EMPTY_HTML

        plugin, captured = _load_kickass(retrieve_return=always_empty)
        plugin.search("nonexistent")
        assert call_count == 1
        assert len(captured) == 0

    def test_single_page_results_only(self):
        call_count = 0

        def one_page(url):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return SINGLE_RESULT_HTML
            return EMPTY_HTML

        plugin, captured = _load_kickass(retrieve_return=one_page)
        with patch("kickass.sleep"):
            plugin.search("test")
        assert len(captured) == 1

    def test_retrieve_url_called_for_each_detail_page(self):
        detail_urls = []
        search_count = 0

        def dispatch(url):
            nonlocal search_count
            if "details/" in url:
                detail_urls.append(url)
                return DETAIL_PAGE_WITH_MAGNET
            search_count += 1
            if search_count == 1:
                return MULTI_RESULT_HTML
            return EMPTY_HTML

        plugin, captured = _load_kickass(retrieve_return=dispatch)
        with patch("kickass.sleep"):
            plugin.search("test")
        assert len(detail_urls) == 2
        assert all("details/" in u for u in detail_urls)
