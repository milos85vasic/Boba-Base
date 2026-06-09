"""Deep coverage tests for plugins/torlock.py.

Covers: MyHtmlParser (article parsing, item_bad/nofollow, date formats,
empty/malformed HTML, size/seeds/leech extraction), search (URL construction,
category mapping, pagination, exception handling), download_torrent,
category mapping dict.
"""

import importlib.util
import os
import sys
import types
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PLUGINS_DIR = os.path.join(REPO, "plugins")


def _load_torlock(captured=None):
    """Import torlock plugin with stub modules. Returns (instance, captured)."""
    if captured is None:
        captured = []
    np_mod = types.ModuleType("novaprinter")
    np_mod.prettyPrinter = lambda d: captured.append(dict(d))
    sys.modules["novaprinter"] = np_mod

    helpers_mod = types.ModuleType("helpers")
    helpers_mod.retrieve_url = lambda url: ""
    helpers_mod.download_file = lambda url, path: url
    sys.modules["helpers"] = helpers_mod

    sys.modules.pop("torlock", None)

    path = os.path.join(PLUGINS_DIR, "torlock.py")
    spec = importlib.util.spec_from_file_location("torlock", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules["torlock"] = mod
    cls = getattr(mod, "torlock", None)
    if cls is not None and isinstance(cls, type):
        return cls(), captured
    return mod, captured


# ─── HTML fixtures ───────────────────────────────────────────────────────────

BASE = "https://torlock2.com"

SINGLE_RESULT = f'''<article>
<table>
<tr>
<td><a href="/torrent/12345/movie/the-matrix.html">The Matrix</a></td>
<td class="ts">2.1 GB</td>
<td class="tul">150</td>
<td class="tdl">20</td>
<td class="td">06/15/2025</td>
</tr>
</table>
</article>'''

MULTI_RESULT = f'''<article>
<table>
<tr>
<td><a href="/torrent/11111/movie/inception.html">Inception</a></td>
<td class="ts">4.5 GB</td>
<td class="tul">300</td>
<td class="tdl">50</td>
<td class="td">01/01/2024</td>
</tr>
</table>
<table>
<tr>
<td><a href="/torrent/22222/movie/interstellar.html">Interstellar</a></td>
<td class="ts">8.2 GB</td>
<td class="tul">500</td>
<td class="tdl">10</td>
<td class="td">12/25/2023</td>
</tr>
</table>
</article>'''

TODAY_RESULT = f'''<article>
<table>
<tr>
<td><a href="/torrent/99999/game/new-game.html">New Game</a></td>
<td class="ts">50.0 GB</td>
<td class="tul">10</td>
<td class="tdl">5</td>
<td class="td">Today</td>
</tr>
</table>
</article>'''

YESTERDAY_RESULT = f'''<article>
<table>
<tr>
<td><a href="/torrent/88888/game/old-game.html">Old Game</a></td>
<td class="ts">10.0 GB</td>
<td class="tul">25</td>
<td class="tdl">3</td>
<td class="td">Yesterday</td>
</tr>
</table>
</article>'''

NOFOLLOW_RESULT = f'''<article>
<table>
<tr>
<td><a href="/torrent/77777/game/bad-game.html" rel="nofollow">Bad Game</a></td>
<td class="ts">5.0 GB</td>
<td class="tul">100</td>
<td class="tdl">10</td>
<td class="td">03/10/2025</td>
</tr>
</table>
</article>'''

NO_ARTICLE_HTML = '<html><body><p>No results found.</p></body></html>'

MALFORMED_NO_DATE = f'''<article>
<table>
<tr>
<td><a href="/torrent/55555/movie/broken.html">Broken Movie</a></td>
<td class="ts">1.0 GB</td>
<td class="tul">5</td>
<td class="tdl">1</td>
</tr>
</table>
</article>'''

MALFORMED_UNPARSEABLE_DATE = f'''<article>
<table>
<tr>
<td><a href="/torrent/44444/movie/weird.html">Weird Date</a></td>
<td class="ts">3.0 GB</td>
<td class="tul">20</td>
<td class="tdl">5</td>
<td class="td">not-a-date</td>
</tr>
</table>
</article>'''

LINK_NO_HREF = '''<article>
<table>
<tr>
<td><a>The No Link</a></td>
<td class="ts">1.0 GB</td>
<td class="tul">1</td>
<td class="tdl">0</td>
<td class="td">01/01/2025</td>
</tr>
</table>
</article>'''

LINK_NOT_TORRENT = '''<article>
<table>
<tr>
<td><a href="https://example.com/page">Not Torrent</a></td>
<td class="ts">1.0 GB</td>
<td class="tul">1</td>
<td class="tdl">0</td>
<td class="td">01/01/2025</td>
</tr>
</table>
</article>'''

UNKNOWN_TD_CLASS = f'''<article>
<table>
<tr>
<td><a href="/torrent/33333/movie/unknown.html">Unknown Class</a></td>
<td class="ts">2.0 GB</td>
<td class="tul">50</td>
<td class="tdl">5</td>
<td class="td">05/20/2025</td>
<td class="zzz">should be ignored</td>
</tr>
</table>
</article>'''

EMPTY_TABLE_DATA = f'''<article>
<table>
<tr>
<td><a href="/torrent/22222/game/empty.html">Empty Data</a></td>
<td class="ts"></td>
<td class="tul"></td>
<td class="tdl"></td>
<td class="td"></td>
</tr>
</table>
</article>'''

PAGE_20_ITEMS = '''<article>
''' + ''.join(
    f'''<table><tr><td><a href="/torrent/{i}/movie/item{i}.html">Item {i}</a></td>
<td class="ts">1.0 GB</td><td class="tul">10</td><td class="tdl">1</td>
<td class="td">01/01/2025</td></tr></table>'''
    for i in range(20)
) + '''
</article>'''

LESS_THAN_20_ITEMS = '''<article>
<table><tr><td><a href="/torrent/1/movie/short.html">Short</a></td>
<td class="ts">1.0 GB</td><td class="tul">5</td><td class="tdl">1</td>
<td class="td">01/01/2025</td></tr></table>
</article>'''


# ─── Parser tests ────────────────────────────────────────────────────────────

class TestHtmlParser:
    def _parse(self, html, url=BASE):
        plugin, captured = _load_torlock()
        parser = plugin.MyHtmlParser(url)
        parser.feed(html)
        parser.close()
        return parser, captured

    def test_single_result(self):
        parser, captured = self._parse(SINGLE_RESULT)
        assert len(captured) == 1
        item = captured[0]
        assert item["name"] == "The Matrix"
        assert item["desc_link"] == f"{BASE}/torrent/12345/movie/the-matrix.html"
        assert item["link"] == f"{BASE}/tor/12345.torrent"
        assert item["engine_url"] == BASE
        assert item["size"] == "2.1 GB"
        assert item["seeds"] == "150"
        assert item["leech"] == "20"

    def test_multi_results(self):
        parser, captured = self._parse(MULTI_RESULT)
        assert len(captured) == 2
        assert captured[0]["name"] == "Inception"
        assert captured[1]["name"] == "Interstellar"
        assert captured[0]["seeds"] == "300"
        assert captured[1]["leech"] == "10"

    def test_empty_html(self):
        parser, captured = self._parse(NO_ARTICLE_HTML)
        assert len(captured) == 0

    def test_no_article_tag(self):
        parser, captured = self._parse("<html><body><p>hello</p></body></html>")
        assert len(captured) == 0

    def test_article_without_table_rows(self):
        parser, captured = self._parse("<article><p>nothing here</p></article>")
        assert len(captured) == 0

    def test_date_today(self):
        parser, captured = self._parse(TODAY_RESULT)
        assert len(captured) == 1
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        assert captured[0]["pub_date"] == int(today.timestamp())

    def test_date_yesterday(self):
        parser, captured = self._parse(YESTERDAY_RESULT)
        assert len(captured) == 1
        yesterday = datetime.now() - timedelta(days=1)
        yesterday = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
        assert captured[0]["pub_date"] == int(yesterday.timestamp())

    def test_date_mdy_format(self):
        parser, captured = self._parse(SINGLE_RESULT)
        assert len(captured) == 1
        expected = datetime(2025, 6, 15).timestamp()
        assert captured[0]["pub_date"] == int(expected)

    def test_nofollow_item_skipped(self):
        parser, captured = self._parse(NOFOLLOW_RESULT)
        assert len(captured) == 0

    def test_malformed_no_date_fallback(self):
        parser, captured = self._parse(MALFORMED_NO_DATE)
        assert len(captured) == 1
        assert captured[0]["pub_date"] == -1

    def test_unparseable_date_fallback(self):
        parser, captured = self._parse(MALFORMED_UNPARSEABLE_DATE)
        assert len(captured) == 1
        assert captured[0]["pub_date"] == -1

    def test_link_no_href_skipped(self):
        parser, captured = self._parse(LINK_NO_HREF)
        assert len(captured) == 0

    def test_link_not_torrent_path_skipped(self):
        parser, captured = self._parse(LINK_NOT_TORRENT)
        assert len(captured) == 0

    def test_unknown_td_class_ignored(self):
        parser, captured = self._parse(UNKNOWN_TD_CLASS)
        assert len(captured) == 1
        item = captured[0]
        assert item["name"] == "Unknown Class"
        assert "zzz" not in item
        assert item["size"] == "2.0 GB"
        assert item["seeds"] == "50"
        assert item["leech"] == "5"

    def test_empty_table_data_fields(self):
        parser, captured = self._parse(EMPTY_TABLE_DATA)
        assert len(captured) == 1
        item = captured[0]
        assert item["name"] == "Empty Data"
        assert item["size"] == ""
        assert item["seeds"] == ""
        assert item["leech"] == ""

    def test_custom_base_url(self):
        custom_url = "https://custom-torlock.example.com"
        plugin, captured = _load_torlock()
        parser = plugin.MyHtmlParser(custom_url)
        parser.feed(SINGLE_RESULT)
        parser.close()
        assert len(captured) == 1
        assert captured[0]["desc_link"].startswith(custom_url)
        assert captured[0]["link"].startswith(custom_url)
        assert captured[0]["engine_url"] == custom_url

    def test_page_items_counter(self):
        parser, captured = self._parse(MULTI_RESULT)
        assert parser.page_items == 2

    def test_page_items_counter_empty(self):
        parser, captured = self._parse(NO_ARTICLE_HTML)
        assert parser.page_items == 0

    def test_article_close_resets_flag(self):
        plugin, captured = _load_torlock()
        parser = plugin.MyHtmlParser(BASE)
        parser.feed("<article></article>")
        assert parser.article_found is False

    def test_multiple_articles(self):
        html = SINGLE_RESULT + MULTI_RESULT
        parser, captured = self._parse(html)
        assert len(captured) == 3

    def test_torrent_id_extraction(self):
        parser, captured = self._parse(SINGLE_RESULT)
        assert captured[0]["link"] == f"{BASE}/tor/12345.torrent"

    def test_name_strips_whitespace(self):
        html = '''<article>
<table><tr>
<td><a href="/torrent/11111/movie/whitespace.html">
  Spaced Name  </a></td>
<td class="ts">1.0 GB</td><td class="tul">1</td><td class="tdl">0</td>
<td class="td">01/01/2025</td>
</tr></table>
</article>'''
        parser, captured = self._parse(html)
        assert len(captured) == 1
        assert "Spaced Name" in captured[0]["name"]


# ─── Search tests ────────────────────────────────────────────────────────────

class TestSearch:
    def setup_method(self):
        self.plugin, self.captured = _load_torlock()

    @patch("torlock.retrieve_url", return_value=SINGLE_RESULT)
    def test_search_all_category(self, mock_retrieve):
        self.plugin.search("the-matrix", "all")
        called_url = mock_retrieve.call_args_list[0][0][0]
        assert called_url == f"{BASE}/all/torrents/the-matrix.html?sort=seeds&page=1"

    @patch("torlock.retrieve_url", return_value=SINGLE_RESULT)
    def test_search_movies_category(self, mock_retrieve):
        self.plugin.search("inception", "movies")
        called_url = mock_retrieve.call_args_list[0][0][0]
        assert called_url == f"{BASE}/movie/torrents/inception.html?sort=seeds&page=1"

    @patch("torlock.retrieve_url", return_value=SINGLE_RESULT)
    def test_search_games_category(self, mock_retrieve):
        self.plugin.search("elden-ring", "games")
        called_url = mock_retrieve.call_args_list[0][0][0]
        assert called_url == f"{BASE}/game/torrents/elden-ring.html?sort=seeds&page=1"

    @patch("torlock.retrieve_url", return_value=SINGLE_RESULT)
    def test_search_music_category(self, mock_retrieve):
        self.plugin.search("dark-side", "music")
        called_url = mock_retrieve.call_args_list[0][0][0]
        assert called_url == f"{BASE}/music/torrents/dark-side.html?sort=seeds&page=1"

    @patch("torlock.retrieve_url", return_value=SINGLE_RESULT)
    def test_search_tv_category(self, mock_retrieve):
        self.plugin.search("breaking-bad", "tv")
        called_url = mock_retrieve.call_args_list[0][0][0]
        assert called_url == f"{BASE}/television/torrents/breaking-bad.html?sort=seeds&page=1"

    @patch("torlock.retrieve_url", return_value=SINGLE_RESULT)
    def test_search_anime_category(self, mock_retrieve):
        self.plugin.search("naruto", "anime")
        called_url = mock_retrieve.call_args_list[0][0][0]
        assert called_url == f"{BASE}/anime/torrents/naruto.html?sort=seeds&page=1"

    @patch("torlock.retrieve_url", return_value=SINGLE_RESULT)
    def test_search_software_category(self, mock_retrieve):
        self.plugin.search("photoshop", "software")
        called_url = mock_retrieve.call_args_list[0][0][0]
        assert called_url == f"{BASE}/software/torrents/photoshop.html?sort=seeds&page=1"

    @patch("torlock.retrieve_url", return_value=SINGLE_RESULT)
    def test_search_books_category(self, mock_retrieve):
        self.plugin.search("dune", "books")
        called_url = mock_retrieve.call_args_list[0][0][0]
        assert called_url == f"{BASE}/ebooks/torrents/dune.html?sort=seeds&page=1"

    @patch("torlock.retrieve_url", return_value=SINGLE_RESULT)
    def test_query_percent20_replaced_with_dash(self, mock_retrieve):
        self.plugin.search("the%20matrix", "all")
        called_url = mock_retrieve.call_args_list[0][0][0]
        assert "the-matrix" in called_url
        assert "%20" not in called_url

    @patch("torlock.retrieve_url", return_value=SINGLE_RESULT)
    def test_search_results_emitted(self, mock_retrieve):
        self.plugin.search("the-matrix", "all")
        assert len(self.captured) == 1
        assert self.captured[0]["name"] == "The Matrix"

    @patch("torlock.retrieve_url", return_value=NO_ARTICLE_HTML)
    def test_search_no_results_stops_early(self, mock_retrieve):
        self.plugin.search("nonexistent", "all")
        assert len(self.captured) == 0
        assert mock_retrieve.call_count == 1

    @patch("torlock.retrieve_url", return_value=LESS_THAN_20_ITEMS)
    def test_search_less_than_20_stops_after_page(self, mock_retrieve):
        self.plugin.search("short", "all")
        assert len(self.captured) == 1
        assert mock_retrieve.call_count == 1

    @patch("torlock.retrieve_url", return_value=PAGE_20_ITEMS)
    def test_search_20_items_continues_pagination(self, mock_retrieve):
        self.plugin.search("many", "all")
        assert len(self.captured) == 80
        assert mock_retrieve.call_count == 4

    @patch("torlock.retrieve_url", side_effect=Exception("network error"))
    def test_search_exception_propagates(self, mock_retrieve):
        with pytest.raises(Exception, match="network error"):
            self.plugin.search("error", "all")

    @patch("torlock.retrieve_url", return_value=SINGLE_RESULT)
    def test_search_invalid_category_raises(self, mock_retrieve):
        with pytest.raises(KeyError):
            self.plugin.search("test", "nonexistent")

    @patch("torlock.retrieve_url", return_value=NOFOLLOW_RESULT)
    def test_search_nofollow_results_filtered(self, mock_retrieve):
        self.plugin.search("bad", "all")
        assert len(self.captured) == 0


# ─── download_torrent tests ─────────────────────────────────────────────────

class TestDownloadTorrent:
    def setup_method(self):
        self.plugin, self.captured = _load_torlock()

    @patch("torlock.download_file", return_value="magnet:?xt=urn:btih:abc123")
    def test_download_prints_result(self, mock_download, capsys):
        self.plugin.download_torrent("https://torlock2.com/torrent/12345/movie/test.html")
        out = capsys.readouterr().out
        assert "magnet:?xt=urn:btih:abc123" in out

    @patch("torlock.download_file", return_value="/tmp/test.torrent")
    def test_download_torrent_file(self, mock_download, capsys):
        self.plugin.download_torrent("https://torlock2.com/torrent/12345/movie/test.html")
        out = capsys.readouterr().out
        assert "/tmp/test.torrent" in out
        mock_download.assert_called_once_with("https://torlock2.com/torrent/12345/movie/test.html")

    @patch("torlock.download_file", return_value=None)
    def test_download_returns_none(self, mock_download, capsys):
        self.plugin.download_torrent("https://example.com/test")
        out = capsys.readouterr().out
        assert "None" in out


# ─── Category mapping tests ─────────────────────────────────────────────────

class TestCategoryMapping:
    def setup_method(self):
        self.plugin, _ = _load_torlock()

    def test_all_category(self):
        assert self.plugin.supported_categories["all"] == "all"

    def test_anime_category(self):
        assert self.plugin.supported_categories["anime"] == "anime"

    def test_software_category(self):
        assert self.plugin.supported_categories["software"] == "software"

    def test_games_category(self):
        assert self.plugin.supported_categories["games"] == "game"

    def test_movies_category(self):
        assert self.plugin.supported_categories["movies"] == "movie"

    def test_music_category(self):
        assert self.plugin.supported_categories["music"] == "music"

    def test_tv_category(self):
        assert self.plugin.supported_categories["tv"] == "television"

    def test_books_category(self):
        assert self.plugin.supported_categories["books"] == "ebooks"

    def test_all_categories_present(self):
        expected_keys = {"all", "anime", "software", "games", "movies", "music", "tv", "books"}
        assert set(self.plugin.supported_categories.keys()) == expected_keys


# ─── Class attributes tests ─────────────────────────────────────────────────

class TestPluginAttributes:
    def setup_method(self):
        self.plugin, _ = _load_torlock()

    def test_url(self):
        assert self.plugin.url == "https://torlock2.com"

    def test_name(self):
        assert self.plugin.name == "TorLock"

    def test_has_search_method(self):
        assert callable(getattr(self.plugin, "search", None))

    def test_has_download_torrent_method(self):
        assert callable(getattr(self.plugin, "download_torrent", None))

    def test_has_parser_class(self):
        assert hasattr(self.plugin, "MyHtmlParser")
