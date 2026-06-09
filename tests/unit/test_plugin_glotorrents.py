"""Deep coverage tests for plugins/community/glotorrents.py.

Covers: HTMLParser.feed (single/multi/malformed/empty/flag-reset),
search (URL construction, category mapping, pagination, sleep,
exception handling), download_torrent (magnet, magnet extraction,
no magnet, exception propagation), attributes.
"""

import importlib.util
import os
import sys
import types
from unittest.mock import patch

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PLUGINS_DIR = os.path.join(REPO, "plugins")


def _load_glotorrents(captured=None):
    if captured is None:
        captured = []
    np_mod = types.ModuleType("novaprinter")
    np_mod.prettyPrinter = lambda d: captured.append(dict(d))
    sys.modules["novaprinter"] = np_mod

    helpers_mod = types.ModuleType("helpers")
    helpers_mod.retrieve_url = lambda url: ""
    sys.modules["helpers"] = helpers_mod

    sys.modules.pop("glotorrents", None)

    path = os.path.join(PLUGINS_DIR, "community", "glotorrents.py")
    spec = importlib.util.spec_from_file_location("glotorrents", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules["glotorrents"] = mod
    cls = getattr(mod, "glotorrents", None)
    if cls is not None and isinstance(cls, type):
        return cls(), captured, helpers_mod
    return mod, captured, helpers_mod


# ---------------------------------------------------------------------------
# HTML fixtures -- must match the regex inside __findTorrents
# ---------------------------------------------------------------------------

GLOTR_ROW = (
    "<tr class='t-row'> <td class='ttable_col1'>"
    '<a title="Ubuntu 24.04 LTS" href="/torrent/ubuntu-2404-lts/">Ubuntu 24.04 LTS</a>'
    "<td align='center'> <a href=\"magnet:?xt=urn:btih:abc123def&dn=Ubuntu2404\">DL</a> "
    "4,321.5 GB "
    "<font color='green'><b>1,234</b></font> "
    "<font color='#ff0000'><b>567</b></font></td></tr>"
)

GLOTR_MULTI = (
    "<tr class='t-row'> <td class='ttable_col1'>"
    '<a title="First Torrent" href="/torrent/first/">First Torrent</a>'
    "<td align='center'> <a href=\"magnet:?xt=urn:btih:aaa111&dn=First\">DL</a> "
    "2.5 GB "
    "<font color='green'><b>100</b></font> "
    "<font color='#00ff00'><b>50</b></font></td></tr>"
    "<tr class='t-row'> <td class='ttable_col1'>"
    '<a title="Second Torrent" href="/torrent/second/">Second Torrent</a>'
    "<td align='center'> <a href=\"magnet:?xt=urn:btih:bbb222&dn=Second\">DL</a> "
    "10.0 MB "
    "<font color='green'><b>200</b></font> "
    "<font color='#0000ff'><b>25</b></font></td></tr>"
)

GLOTR_EMPTY = "<html><body><p>No results found.</p></body></html>"

GLOTR_MALFORMED = "<tr class='t-row'> <td class='ttable_col1'>broken no href no magnet no font</tr>"

GLOTR_SEEDS_COMMAS = (
    "<tr class='t-row'> <td class='ttable_col1'>"
    '<a title="Popular Torrent" href="/torrent/popular/">Popular Torrent</a>'
    "<td align='center'> <a href=\"magnet:?xt=urn:btih:ccc333&dn=Popular\">DL</a> "
    "1,000.0 GB "
    "<font color='green'><b>12,345</b></font> "
    "<font color='#ff8800'><b>9,876</b></font></td></tr>"
)

GLOTR_DL_HTML_WITH_MAGNET = '<a href="magnet:?xt=urn:btih:xyz789&dn=Movie">Link</a>'
GLOTR_DL_HTML_NO_MAGNET = "<html><body><p>No download links</p></body></html>"


# ---------------------------------------------------------------------------
# HTMLParser feed / __findTorrents
# ---------------------------------------------------------------------------


class TestHTMLParserFeed:
    def setup_method(self):
        self.mod, self.cap, _ = _load_glotorrents()

    def test_feed_single_result(self):
        parser = self.mod.HTMLParser(self.mod.url)
        parser.feed(GLOTR_ROW)
        assert len(self.cap) == 1
        assert self.cap[0]["name"] == "Ubuntu 24.04 LTS"
        assert self.cap[0]["link"] == "magnet:?xt=urn:btih:abc123def&dn=Ubuntu2404"
        assert self.cap[0]["size"] == "4321.5 GB"
        assert self.cap[0]["seeds"] == "1234"
        assert self.cap[0]["leech"] == "567"
        assert self.cap[0]["engine_url"] == "https://glodls.to/"
        assert self.cap[0]["desc_link"] == "https://glodls.to//torrent/ubuntu-2404-lts/"
        assert parser.noTorrents is False

    def test_feed_multiple_results(self):
        parser = self.mod.HTMLParser(self.mod.url)
        parser.feed(GLOTR_MULTI)
        assert len(self.cap) == 2
        assert self.cap[0]["name"] == "First Torrent"
        assert self.cap[1]["name"] == "Second Torrent"
        assert self.cap[0]["link"] == "magnet:?xt=urn:btih:aaa111&dn=First"
        assert self.cap[1]["link"] == "magnet:?xt=urn:btih:bbb222&dn=Second"

    def test_feed_empty_html_sets_no_torrents(self):
        parser = self.mod.HTMLParser(self.mod.url)
        parser.feed(GLOTR_EMPTY)
        assert len(self.cap) == 0
        assert parser.noTorrents is True

    def test_feed_malformed_html_skipped(self):
        parser = self.mod.HTMLParser(self.mod.url)
        parser.feed(GLOTR_MALFORMED)
        assert len(self.cap) == 0

    def test_feed_no_torrents_flag_resets_on_subsequent_feed(self):
        parser = self.mod.HTMLParser(self.mod.url)
        parser.feed(GLOTR_EMPTY)
        assert parser.noTorrents is True
        parser.feed(GLOTR_ROW)
        assert parser.noTorrents is False
        assert len(self.cap) == 1

    def test_feed_seeds_leeches_commas_stripped(self):
        parser = self.mod.HTMLParser(self.mod.url)
        parser.feed(GLOTR_SEEDS_COMMAS)
        assert len(self.cap) == 1
        assert self.cap[0]["seeds"] == "12345"
        assert self.cap[0]["leech"] == "9876"
        assert self.cap[0]["size"] == "1000.0 GB"

    def test_feeding_without_results_resets_no_torrents(self):
        parser = self.mod.HTMLParser(self.mod.url)
        parser.feed(GLOTR_ROW)
        assert parser.noTorrents is False
        parser.feed(GLOTR_EMPTY)
        assert parser.noTorrents is True


class TestHTMLParserDescLink:
    def setup_method(self):
        self.mod, self.cap, _ = _load_glotorrents()

    def test_desc_link_constructed_correctly(self):
        parser = self.mod.HTMLParser("https://glodls.to/")
        parser.feed(GLOTR_ROW)
        assert self.cap[0]["desc_link"] == "https://glodls.to//torrent/ubuntu-2404-lts/"

    def test_desc_link_with_custom_base_url(self):
        parser = self.mod.HTMLParser("https://custom.url/")
        row = (
            "<tr class='t-row'> <td class='ttable_col1'>"
            '<a title="A" href="/a/">A</a>'
            "<td align='center'> <a href=\"magnet:?x\">DL</a> "
            "1.0 GB "
            "<font color='green'><b>1</b></font> "
            "<font color='#ff0000'><b>1</b></font></td></tr>"
        )
        parser.feed(row)
        assert self.cap[0]["desc_link"] == "https://custom.url//a/"
        assert self.cap[0]["engine_url"] == "https://custom.url/"


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


class TestSearchURL:
    def setup_method(self):
        self.mod, self.cap, _ = _load_glotorrents()

    @patch("glotorrents.retrieve_url", return_value=GLOTR_EMPTY)
    def test_search_all_category(self, mock_retrieve):
        self.mod.search("ubuntu", "all")
        called = mock_retrieve.call_args[0][0]
        assert "search_results.php" in called
        assert "search=ubuntu" in called
        assert "cat=0" in called
        assert "page=0" in called

    @patch("glotorrents.retrieve_url", return_value=GLOTR_EMPTY)
    def test_search_movies_category(self, mock_retrieve):
        self.mod.search("test", "movies")
        called = mock_retrieve.call_args[0][0]
        assert "cat=1" in called

    @patch("glotorrents.retrieve_url", return_value=GLOTR_EMPTY)
    def test_search_tv_category(self, mock_retrieve):
        self.mod.search("test", "tv")
        called = mock_retrieve.call_args[0][0]
        assert "cat=41" in called

    @patch("glotorrents.retrieve_url", return_value=GLOTR_EMPTY)
    def test_search_music_category(self, mock_retrieve):
        self.mod.search("test", "music")
        called = mock_retrieve.call_args[0][0]
        assert "cat=22" in called

    @patch("glotorrents.retrieve_url", return_value=GLOTR_EMPTY)
    def test_search_games_category(self, mock_retrieve):
        self.mod.search("test", "games")
        called = mock_retrieve.call_args[0][0]
        assert "cat=10" in called

    @patch("glotorrents.retrieve_url", return_value=GLOTR_EMPTY)
    def test_search_anime_category(self, mock_retrieve):
        self.mod.search("test", "anime")
        called = mock_retrieve.call_args[0][0]
        assert "cat=28" in called

    @patch("glotorrents.retrieve_url", return_value=GLOTR_EMPTY)
    def test_search_software_category(self, mock_retrieve):
        self.mod.search("test", "software")
        called = mock_retrieve.call_args[0][0]
        assert "cat=18" in called

    @patch("glotorrents.retrieve_url", return_value=GLOTR_EMPTY)
    def test_search_books_category(self, mock_retrieve):
        self.mod.search("test", "books")
        called = mock_retrieve.call_args[0][0]
        assert "cat=51" in called

    @patch("glotorrents.retrieve_url", return_value=GLOTR_EMPTY)
    def test_search_pictures_category(self, mock_retrieve):
        self.mod.search("test", "pictures")
        called = mock_retrieve.call_args[0][0]
        assert "cat=70" in called

    @patch("glotorrents.retrieve_url", return_value=GLOTR_EMPTY)
    def test_search_replaces_percent20_with_plus(self, mock_retrieve):
        self.mod.search("hello%20world", "all")
        called = mock_retrieve.call_args[0][0]
        assert "search=hello+world" in called


class TestSearchPagination:
    def setup_method(self):
        self.mod, self.cap, _ = _load_glotorrents()

    @patch("glotorrents.sleep")
    @patch("glotorrents.retrieve_url", side_effect=[GLOTR_ROW, GLOTR_EMPTY])
    def test_search_paginates_until_no_torrents(self, mock_retrieve, mock_sleep):
        self.mod.search("ubuntu", "all")
        assert mock_retrieve.call_count == 2
        first_url = mock_retrieve.call_args_list[0][0][0]
        second_url = mock_retrieve.call_args_list[1][0][0]
        assert "page=0" in first_url
        assert "page=1" in second_url

    @patch("glotorrents.sleep")
    @patch("glotorrents.retrieve_url", side_effect=[GLOTR_ROW, GLOTR_EMPTY])
    def test_search_sleep_called_between_pages(self, mock_retrieve, mock_sleep):
        self.mod.search("ubuntu", "all")
        mock_sleep.assert_called_once_with(3)

    @patch("glotorrents.sleep")
    @patch("glotorrents.retrieve_url", side_effect=[GLOTR_ROW, GLOTR_EMPTY])
    def test_search_results_accumulated_across_pages(self, mock_retrieve, mock_sleep):
        self.mod.search("ubuntu", "all")
        assert len(self.cap) == 1
        assert self.cap[0]["name"] == "Ubuntu 24.04 LTS"

    @patch("glotorrents.sleep")
    @patch("glotorrents.retrieve_url", side_effect=[GLOTR_ROW, GLOTR_ROW, GLOTR_EMPTY])
    def test_search_multiple_result_pages(self, mock_retrieve, mock_sleep):
        self.mod.search("ubuntu", "all")
        assert mock_retrieve.call_count == 3
        assert len(self.cap) == 2
        assert mock_sleep.call_count == 2

    @patch("glotorrents.sleep")
    @patch("glotorrents.retrieve_url", side_effect=[GLOTR_EMPTY])
    def test_search_stops_immediately_on_empty(self, mock_retrieve, mock_sleep):
        self.mod.search("ubuntu", "all")
        assert mock_retrieve.call_count == 1
        mock_sleep.assert_not_called()


class TestSearchExceptions:
    def setup_method(self):
        self.mod, self.cap, _ = _load_glotorrents()

    @patch("glotorrents.sleep")
    @patch("glotorrents.retrieve_url", side_effect=Exception("upstream error"))
    def test_search_exception_propagates(self, mock_retrieve, mock_sleep):
        with pytest.raises(Exception, match="upstream error"):
            self.mod.search("ubuntu", "all")
        assert len(self.cap) == 0

    def test_search_unknown_category_raises_keyerror(self):
        with pytest.raises(KeyError):
            self.mod.search("test", "nonexistent")


# ---------------------------------------------------------------------------
# download_torrent
# ---------------------------------------------------------------------------


class TestDownloadTorrent:
    def setup_method(self):
        self.mod, self.cap, self.helpers_mod = _load_glotorrents()

    def test_download_appends_engine_url_to_magnet(self, capsys):
        self.mod.download_torrent("magnet:?xt=urn:btih:XXX&dn=Test")
        out = capsys.readouterr().out
        assert "magnet:?xt=urn:btih:XXX&dn=Test" in out
        assert "https://glodls.to/" in out

    def test_download_magnet_prints_magnet_and_engine(self, capsys):
        self.mod.download_torrent("magnet:?xt=urn:btih:aaaa&dn=Test")
        out = capsys.readouterr().out.strip()
        assert out == "magnet:?xt=urn:btih:aaaa&dn=Test https://glodls.to/"

    def test_download_extracts_magnet_from_html(self, capsys):
        self.helpers_mod.retrieve_url = lambda u: GLOTR_DL_HTML_WITH_MAGNET
        self.mod.download_torrent("https://glodls.to/torrent/test")
        out = capsys.readouterr().out.strip()
        assert out == "magnet:?xt=urn:btih:xyz789&dn=Movie https://glodls.to/"

    def test_download_no_magnet_in_html_prints_page_url(self, capsys):
        self.helpers_mod.retrieve_url = lambda u: GLOTR_DL_HTML_NO_MAGNET
        self.mod.download_torrent("https://glodls.to/torrent/none")
        out = capsys.readouterr().out.strip()
        assert out == "https://glodls.to/torrent/none https://glodls.to/"

    def test_download_page_with_magnet_partial_attr(self, capsys):
        self.helpers_mod.retrieve_url = lambda u: '<a href="magnet:?xt=urn:btih:abc&dn=Files with spaces">Link</a>'
        self.mod.download_torrent("https://glodls.to/torrent/x")
        out = capsys.readouterr().out.strip()
        assert "magnet:" in out
        assert "https://glodls.to/" in out

    def test_download_exception_propagates(self):
        self.helpers_mod.retrieve_url = lambda u: (_ for _ in ()).throw(Exception("network error"))
        with pytest.raises(Exception, match="network error"):
            self.mod.download_torrent("https://glodls.to/torrent/fail")


# ---------------------------------------------------------------------------
# Attributes
# ---------------------------------------------------------------------------


class TestAttributes:
    def setup_method(self):
        self.mod, self.cap, _ = _load_glotorrents()

    def test_url(self):
        assert self.mod.url == "https://glodls.to/"

    def test_name(self):
        assert self.mod.name == "GloTorrents"

    def test_supported_categories_keys(self):
        expected = {"all", "movies", "tv", "music", "games", "anime", "software", "books", "pictures"}
        assert set(self.mod.supported_categories.keys()) == expected

    def test_supported_categories_values_are_strings(self):
        for v in self.mod.supported_categories.values():
            assert isinstance(v, str)

    def test_all_category_value(self):
        assert self.mod.supported_categories["all"] == "0"

    def test_movies_category_value(self):
        assert self.mod.supported_categories["movies"] == "1"

    def test_books_category_value(self):
        assert self.mod.supported_categories["books"] == "51"

    def test_pictures_category_value(self):
        assert self.mod.supported_categories["pictures"] == "70"
