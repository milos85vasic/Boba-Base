"""Deep coverage tests for plugins/community/pirateiro.py.

Covers: HTMLParser.feed/__findTorrents (single/multi/empty/malformed),
search (URL construction, category mapping, pagination, exception),
download_torrent (magnet, torrent file, recursive, no link, URLError),
category mapping, edge cases.
"""

import importlib.util
import os
import sys
import types
from unittest.mock import patch

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PLUGINS_DIR = os.path.join(REPO, "plugins", "community")

_np_mod = types.ModuleType("novaprinter")
_np_mod.prettyPrinter = lambda d: None
sys.modules["novaprinter"] = _np_mod

_helpers_mod = types.ModuleType("helpers")
_helpers_mod.retrieve_url = lambda url: ""
sys.modules["helpers"] = _helpers_mod

_path = os.path.join(PLUGINS_DIR, "pirateiro.py")
_spec = importlib.util.spec_from_file_location("pirateiro", _path)
_pirateiro_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_pirateiro_mod)
sys.modules["pirateiro"] = _pirateiro_mod


def _load_pirateiro(captured=None):
    if captured is None:
        captured = []
    _pirateiro_mod.prettyPrinter = lambda d: captured.append(dict(d))
    cls = getattr(_pirateiro_mod, "pirateiro", None)
    if cls is not None and isinstance(cls, type):
        return cls(), captured
    return _pirateiro_mod, captured


SINGLE_TORRENT = '<a href="https://pirateiro.io/torrent/12345" title="Details"><h6 class="text-break">Ubuntu 24.04 LTS Desktop</h6><span>150</span><span>12</span> </a>'

MULTI_TORRENT = '<a href="https://pirateiro.io/torrent/111" title="Details"><h6 class="text-break">Debian 12 Netinstall</h6><span>300</span><span>5</span> </a><a href="https://pirateiro.io/torrent/222" title="Details"><h6 class="text-break">Fedora 40 Workstation</h6><span>200</span><span>20</span> </a><a href="https://pirateiro.io/torrent/333" title="Details"><h6 class="text-break">Arch Linux 2024.06</h6><span>90</span><span>3</span> </a>'

EMPTY_HTML = '<div class="no-results"><p>No torrents found</p></div>'

MALFORMED_HTML = "<div><p>Completely broken &amp; garbage &lt;html&gt;</p></div>"

EDGE_CASE_NAMES = '<a href="https://pirateiro.io/torrent/999" title="Details"><h6 class="text-break">Game: Subtitle &amp; More - (2024) [v1.0]</h6><span>42</span><span>7</span> </a>'

NOISY_HTML = '<a href="https://pirateiro.io/torrent/555" title="Details" class="something"><h6 class="text-break">Noisy Entry</h6><span class="seed">250</span><span class="leech">18</span> </a>'

MAGNET_PAGE = '<html><a href="magnet:?xt=urn:btih:abc123def&dn=test">Magnet</a></html>'

TORRENT_DL_PAGE = '<html><a class="btn-down" href="https://katcr.co/download/123">DL</a>X</a></html>'

NO_LINK_PAGE = "<html><body>Nothing here</body></html>"


class TestHTMLParser:
    def test_single_torrent(self):
        plugin, cap = _load_pirateiro()
        parser = plugin.HTMLParser(plugin.url)
        parser.feed(SINGLE_TORRENT)
        assert len(cap) == 1
        assert cap[0]["name"] == "Ubuntu 24.04 LTS Desktop"
        assert cap[0]["link"] == "https://pirateiro.io/torrent/12345"
        assert cap[0]["seeds"] == "150"
        assert cap[0]["leech"] == "12"
        assert cap[0]["engine_url"] == plugin.url
        assert cap[0]["desc_link"] == "https://pirateiro.io/torrent/12345"

    def test_multi_torrent(self):
        plugin, cap = _load_pirateiro()
        parser = plugin.HTMLParser(plugin.url)
        parser.feed(MULTI_TORRENT)
        assert len(cap) == 3
        names = [r["name"] for r in cap]
        assert names == [
            "Debian 12 Netinstall",
            "Fedora 40 Workstation",
            "Arch Linux 2024.06",
        ]

    def test_empty_html_sets_no_torrents(self):
        plugin, _ = _load_pirateiro()
        parser = plugin.HTMLParser(plugin.url)
        parser.feed(EMPTY_HTML)
        assert parser.noTorrents is True

    def test_malformed_html_sets_no_torrents(self):
        plugin, _ = _load_pirateiro()
        parser = plugin.HTMLParser(plugin.url)
        parser.feed(MALFORMED_HTML)
        assert parser.noTorrents is True

    def test_no_torrents_flag_resets(self):
        plugin, _ = _load_pirateiro()
        parser = plugin.HTMLParser(plugin.url)
        parser.feed(EMPTY_HTML)
        assert parser.noTorrents is True
        parser.feed(SINGLE_TORRENT)
        assert parser.noTorrents is False

    def test_size_always_negative_one(self):
        plugin, cap = _load_pirateiro()
        parser = plugin.HTMLParser(plugin.url)
        parser.feed(SINGLE_TORRENT)
        assert cap[0]["size"] == -1

    def test_special_characters_in_name(self):
        plugin, cap = _load_pirateiro()
        parser = plugin.HTMLParser(plugin.url)
        parser.feed(EDGE_CASE_NAMES)
        assert len(cap) == 1
        assert cap[0]["name"] == "Game: Subtitle &amp; More - (2024) [v1.0]"

    def test_noisy_html_still_parsed(self):
        plugin, cap = _load_pirateiro()
        parser = plugin.HTMLParser(plugin.url)
        parser.feed(NOISY_HTML)
        assert len(cap) == 1
        assert cap[0]["name"] == "Noisy Entry"
        assert cap[0]["seeds"] == "250"

    def test_whitespace_collapsed_html(self):
        plugin, cap = _load_pirateiro()
        parser = plugin.HTMLParser(plugin.url)
        collapsed = " ".join(SINGLE_TORRENT.split())
        parser.feed(collapsed)
        assert len(cap) == 1


class TestSearch:
    @patch("pirateiro.retrieve_url", return_value=EMPTY_HTML)
    def test_search_all_category(self, mock_url):
        plugin, _ = _load_pirateiro()
        plugin.search("ubuntu")
        call_url = mock_url.call_args_list[0][0][0]
        assert "query=ubuntu" in call_url
        assert "page=1" in call_url
        assert "category=" not in call_url

    @patch("pirateiro.retrieve_url", return_value=EMPTY_HTML)
    def test_search_specific_category(self, mock_url):
        plugin, _ = _load_pirateiro()
        plugin.search("game", cat="games")
        call_url = mock_url.call_args_list[0][0][0]
        assert "category=3" in call_url

    @patch("pirateiro.retrieve_url", return_value=EMPTY_HTML)
    def test_search_anime_category(self, mock_url):
        plugin, _ = _load_pirateiro()
        plugin.search("anime", cat="anime")
        call_url = mock_url.call_args_list[0][0][0]
        assert "category=2" in call_url

    @patch("pirateiro.retrieve_url", return_value=EMPTY_HTML)
    def test_search_movie_category(self, mock_url):
        plugin, _ = _load_pirateiro()
        plugin.search("movie", cat="movies")
        call_url = mock_url.call_args_list[0][0][0]
        assert "category=1" in call_url

    @patch("pirateiro.retrieve_url", return_value=EMPTY_HTML)
    def test_search_music_category(self, mock_url):
        plugin, _ = _load_pirateiro()
        plugin.search("album", cat="music")
        call_url = mock_url.call_args_list[0][0][0]
        assert "category=4" in call_url

    @patch("pirateiro.retrieve_url", return_value=EMPTY_HTML)
    def test_search_tv_category(self, mock_url):
        plugin, _ = _load_pirateiro()
        plugin.search("show", cat="tv")
        call_url = mock_url.call_args_list[0][0][0]
        assert "category=5" in call_url

    @patch("pirateiro.retrieve_url", return_value=EMPTY_HTML)
    def test_search_software_category(self, mock_url):
        plugin, _ = _load_pirateiro()
        plugin.search("app", cat="software")
        call_url = mock_url.call_args_list[0][0][0]
        assert "category=6" in call_url

    @patch("pirateiro.retrieve_url", return_value=EMPTY_HTML)
    def test_search_encodes_plus(self, mock_url):
        plugin, _ = _load_pirateiro()
        plugin.search("my%20query")
        call_url = mock_url.call_args_list[0][0][0]
        assert "query=my+query" in call_url

    @patch("pirateiro.retrieve_url")
    def test_search_parses_results(self, mock_url):
        plugin, cap = _load_pirateiro()
        mock_url.side_effect = [SINGLE_TORRENT, EMPTY_HTML]
        plugin.search("ubuntu")
        assert len(cap) == 1
        assert cap[0]["name"] == "Ubuntu 24.04 LTS Desktop"

    @patch("pirateiro.retrieve_url", return_value=EMPTY_HTML)
    def test_search_stops_on_empty_page(self, mock_url):
        plugin, _ = _load_pirateiro()
        plugin.search("nonexistent")
        assert mock_url.call_count == 1

    @patch("pirateiro.retrieve_url", return_value=SINGLE_TORRENT)
    def test_search_multi_page(self, mock_url):
        plugin, cap = _load_pirateiro()
        plugin.search("test")
        assert mock_url.call_count == plugin.max_pages - 1

    @patch("pirateiro.retrieve_url")
    def test_search_pagination_stops_early(self, mock_url):
        plugin, cap = _load_pirateiro()
        results = [MULTI_TORRENT, SINGLE_TORRENT, EMPTY_HTML]
        mock_url.side_effect = results
        plugin.search("test")
        assert mock_url.call_count == 3

    @patch("pirateiro.retrieve_url", return_value=SINGLE_TORRENT)
    def test_search_url_base(self, mock_url):
        plugin, _ = _load_pirateiro()
        plugin.search("x")
        call_url = mock_url.call_args_list[0][0][0]
        assert call_url.startswith("https://pirateiro.io/search")

    @patch("pirateiro.retrieve_url", return_value=EMPTY_HTML)
    def test_search_strips_whitespace(self, mock_url):
        plugin, _ = _load_pirateiro()
        plugin.search("test")
        call_url = mock_url.call_args_list[0][0][0]
        assert "  " not in call_url

    @patch("pirateiro.retrieve_url")
    def test_search_with_noisy_html(self, mock_url):
        plugin, cap = _load_pirateiro()
        mock_url.side_effect = [NOISY_HTML, EMPTY_HTML]
        plugin.search("noisy")
        assert len(cap) == 1
        assert cap[0]["name"] == "Noisy Entry"


class TestDownloadTorrent:
    @patch("pirateiro.retrieve_url", return_value=MAGNET_PAGE)
    def test_magnet_link(self, mock_url, capsys):
        plugin, _ = _load_pirateiro()
        plugin.download_torrent("https%3A%2F%2Fpirateiro.io%2Ftorrent%2F123")
        out = capsys.readouterr().out
        assert "magnet:?xt=urn:btih:abc123def" in out
        assert "https%3A%2F%2Fpirateiro.io%2Ftorrent%2F123" in out

    @patch("pirateiro.retrieve_url", return_value=NO_LINK_PAGE)
    def test_no_link_raises(self, mock_url):
        plugin, _ = _load_pirateiro()
        with pytest.raises(Exception, match="bug report"):
            plugin.download_torrent("https://pirateiro.io/torrent/999")

    @patch("pirateiro.retrieve_url", return_value=MAGNET_PAGE)
    def test_magnet_unquoted_url(self, mock_url, capsys):
        plugin, _ = _load_pirateiro()
        plugin.download_torrent("https://pirateiro.io/torrent/abc")
        out = capsys.readouterr().out
        assert "magnet:" in out

    @patch("pirateiro.retrieve_url")
    def test_recursive_katcr_redirect(self, mock_url, capsys):
        plugin, _ = _load_pirateiro()
        katcr_page = '<a class="btn-down" href="https://kickasstorrents.to/dl/123">DL</a>X</a>'
        final_page = '<a href="magnet:?xt=urn:btih:finalhash&dn=final">Magnet</a>'
        mock_url.side_effect = [katcr_page, final_page]
        plugin.download_torrent("https://pirateiro.io/torrent/42")
        out = capsys.readouterr().out
        assert "magnet:?xt=urn:btih:finalhash" in out
        assert mock_url.call_count == 2

    @patch("pirateiro.retrieve_url")
    def test_torrent_file_fallback(self, mock_url, capsys):
        plugin, _ = _load_pirateiro()
        dl_page = '<a class="btn-down" href="https://katcr.co/download/456">DL</a>X</a>'
        final = '<a href="magnet:?xt=urn:btih:deeper&dn=x">M</a>'
        mock_url.side_effect = [dl_page, final]
        plugin.download_torrent("https://pirateiro.io/torrent/77")
        out = capsys.readouterr().out
        assert "magnet:?xt=urn:btih:deeper" in out

    @patch("pirateiro.retrieve_url", return_value='<html>"magnet:?xt=urn:btih:quoted&dn=q"</html>')
    def test_magnet_in_quotes(self, mock_url, capsys):
        plugin, _ = _load_pirateiro()
        plugin.download_torrent("https://pirateiro.io/torrent/1")
        out = capsys.readouterr().out
        assert "magnet:?xt=urn:btih:quoted" in out

    @patch("pirateiro.retrieve_url", return_value="partial magnet:?xt=broken")
    def test_no_magnet_and_no_btn_down(self, mock_url):
        plugin, _ = _load_pirateiro()
        with pytest.raises(Exception, match="bug report"):
            plugin.download_torrent("https://pirateiro.io/torrent/bad")


class TestCategoryMapping:
    def test_all_categories_present(self):
        plugin, _ = _load_pirateiro()
        expected = {"all", "anime", "games", "movies", "music", "software", "tv"}
        assert set(plugin.supported_categories.keys()) == expected

    def test_category_values_are_strings(self):
        plugin, _ = _load_pirateiro()
        for v in plugin.supported_categories.values():
            assert isinstance(v, str)

    def test_known_values(self):
        plugin, _ = _load_pirateiro()
        assert plugin.supported_categories["all"] == "0"
        assert plugin.supported_categories["anime"] == "2"
        assert plugin.supported_categories["games"] == "3"
        assert plugin.supported_categories["movies"] == "1"
        assert plugin.supported_categories["music"] == "4"
        assert plugin.supported_categories["software"] == "6"
        assert plugin.supported_categories["tv"] == "5"


class TestEdgeCases:
    def test_url_attribute(self):
        plugin, _ = _load_pirateiro()
        assert plugin.url == "https://pirateiro.io/"

    def test_name_attribute(self):
        plugin, _ = _load_pirateiro()
        assert plugin.name == "Pirateiro"

    def test_max_pages(self):
        plugin, _ = _load_pirateiro()
        assert plugin.max_pages == 10

    def test_empty_string_search(self):
        plugin, cap = _load_pirateiro()
        with patch("pirateiro.retrieve_url", return_value=EMPTY_HTML) as mock_url:
            plugin.search("")
            call_url = mock_url.call_args_list[0][0][0]
            assert "query=" in call_url

    def test_special_chars_search(self):
        plugin, _ = _load_pirateiro()
        with patch("pirateiro.retrieve_url", return_value=EMPTY_HTML) as mock_url:
            plugin.search("C%2B%2B")
            call_url = mock_url.call_args_list[0][0][0]
            assert "query=C%2B%2B" in call_url

    def test_parser_stores_url(self):
        plugin, _ = _load_pirateiro()
        parser = plugin.HTMLParser("https://example.com/")
        assert parser.url == "https://example.com/"

    def test_no_torrents_initial_state(self):
        plugin, _ = _load_pirateiro()
        parser = plugin.HTMLParser(plugin.url)
        assert parser.noTorrents is False

    def test_magnet_page_with_newlines(self):
        plugin, _ = _load_pirateiro()
        page = '\n<a\nhref="magnet:?xt=urn:btih:nltest&dn=nl"\n>DL\n</a>\n'
        with patch("pirateiro.retrieve_url", return_value=page):
            parser = plugin.HTMLParser(plugin.url)
            assert parser.noTorrents is False

    def test_multiple_feeds_accumulate(self):
        plugin, cap = _load_pirateiro()
        parser = plugin.HTMLParser(plugin.url)
        parser.feed(SINGLE_TORRENT)
        parser.feed(SINGLE_TORRENT)
        assert len(cap) == 2

    def test_zero_seeds_zero_leech(self):
        plugin, cap = _load_pirateiro()
        html = '<a href="https://pirateiro.io/torrent/000" title="Details"><h6 class="text-break">Dead Torrent</h6><span>0</span><span>0</span> </a>'
        parser = plugin.HTMLParser(plugin.url)
        parser.feed(html)
        assert len(cap) == 1
        assert cap[0]["seeds"] == "0"
        assert cap[0]["leech"] == "0"
