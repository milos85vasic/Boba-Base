"""Deep coverage tests for plugins/community/yourbittorrent.py.

Covers: HTMLParser (feed, __findTorrents, table-div guard, noTorrents flag,
name/size/seed/leech extraction, tag stripping, comma removal),
search (URL construction, category mapping, %20→- replacement),
download_torrent (success + failure paths, exception handling),
supported_categories integrity.
"""

import importlib.util
import os
import re
import sys
import types
from unittest.mock import patch

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PLUGINS_DIR = os.path.join(REPO, "plugins", "community")


def _load_plugin(captured=None):
    if captured is None:
        captured = []
    np_mod = types.ModuleType("novaprinter")
    np_mod.prettyPrinter = lambda d: captured.append(dict(d))
    sys.modules["novaprinter"] = np_mod

    helpers_mod = types.ModuleType("helpers")
    helpers_mod.retrieve_url = lambda url: ""
    helpers_mod.download_file = lambda url, referer=None, ssl_context=None: "/tmp/test.torrent " + url
    sys.modules["helpers"] = helpers_mod

    sys.modules.pop("yourbittorrent", None)

    path = os.path.join(PLUGINS_DIR, "yourbittorrent.py")
    spec = importlib.util.spec_from_file_location("yourbittorrent", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules["yourbittorrent"] = mod
    return mod.yourbittorrent(), captured


BOX = '<div class="table-responsive"><table>'


def _row(href, title, size, seeds, leech):
    return (
        f'<tr class="table-default"><a href="{href}" title="{title}">x</a> '
        f'{size} <td class="sd">{seeds}</td> <td class="pr">{leech}</td></tr>'
    )


def _wrap_two_divs(*rows):
    return "{0}<tr class=\"table-default\">x</tr></table></div>{0}{1}</table></div>".format(
        BOX, "".join(rows)
    )


# ─── HTML fixtures (no newlines — parser receives search()-style collapsed HTML) ───

YB_EMPTY = ""

YB_NO_DIVS = "<html><body>No results found.</body></html>"

YB_ONE_DIV = f'{BOX}<tr class="table-default">x</tr></table></div>'

YB_TWO_DIVS_NO_ROWS = (
    '<div class="table-responsive"><table></table></div>'
    '<div class="table-responsive"><table></table></div>'
)

YB_SINGLE = _wrap_two_divs(_row("/t/1", "Test Torrent", "2.5 GB", "42", "7"))

YB_MULTI = _wrap_two_divs(
    _row("/t/1", "First", "1.0 GB", "10", "2"),
    _row("/t/2", "Second", "3.0 GB", "20", "5"),
    _row("/t/3", "Third", "500 MB", "5", "1"),
)

YB_BOLD_NAME = _wrap_two_divs(_row("/t/b", "<b>Bold Title</b>", "100 MB", "1", "0"))

YB_SPAN_NAME = _wrap_two_divs(
    _row("/t/s", "<span style=color:#39a8bb>Colored</span>", "50 MB", "3", "1")
)

YB_COMMA_NUMBERS = _wrap_two_divs(_row("/t/c", "Big File", "1,234.56 GB", "12,345", "6,789"))

YB_KB_UNIT = _wrap_two_divs(_row("/t/k", "Kilo File", "512 kB", "8", "2"))

YB_ROWS_WITHOUT_FIELDS = _wrap_two_divs(
    '<tr class="table-default"><td>no href</td></tr>',
    '<tr class="table-default"><a href="/t/g">no title</a></tr>',
    '<tr class="table-default"><a href="/t/h" title="Has">no size</a> sd">1< pr">2<</tr>',
)

YB_MIXED_VALID_INVALID = _wrap_two_divs(
    _row("/t/ok", "Good One", "1.0 GB", "10", "2"),
    '<tr class="table-default"><td>junk row</td></tr>',
    _row("/t/ok2", "Good Two", "2.0 GB", "20", "3"),
)

YB_DOWNLOAD_PAGE = '<html><body><a href="down/test123.torrent">Download</a></body></html>'

YB_NO_DOWNLOAD_PAGE = "<html><body>No download link here.</body></html>"


# ─── class yourbittorrent ───


class TestYourBittorrentInit:
    def test_url_and_name(self):
        instance, cap = _load_plugin()
        assert instance.url == "https://yourbittorrent.com/"
        assert instance.name == "YourBittorrent"

    def test_supported_categories_keys(self):
        instance, cap = _load_plugin()
        expected = {"all", "movies", "tv", "music", "games", "anime", "software"}
        assert set(instance.supported_categories.keys()) == expected

    def test_supported_categories_values_non_empty(self):
        instance, cap = _load_plugin()
        for k, v in instance.supported_categories.items():
            assert isinstance(v, str)
            assert v != ""


# ─── HTMLParser ───


class TestHTMLParser:
    def test_empty_html_no_results(self):
        instance, cap = _load_plugin()
        parser = instance.HTMLParser(instance.url)
        parser.feed(YB_EMPTY)
        assert parser.noTorrents is True
        assert len(cap) == 0

    def test_no_table_divs_returns_empty(self):
        instance, cap = _load_plugin()
        parser = instance.HTMLParser(instance.url)
        parser.feed(YB_NO_DIVS)
        assert parser.noTorrents is True
        assert len(cap) == 0

    def test_one_table_div_returns_empty(self):
        instance, cap = _load_plugin()
        parser = instance.HTMLParser(instance.url)
        parser.feed(YB_ONE_DIV)
        assert parser.noTorrents is True
        assert len(cap) == 0

    def test_two_divs_no_matching_rows_returns_empty(self):
        instance, cap = _load_plugin()
        parser = instance.HTMLParser(instance.url)
        parser.feed(YB_TWO_DIVS_NO_ROWS)
        assert parser.noTorrents is True
        assert len(cap) == 0

    def test_rows_without_required_fields_are_skipped(self):
        instance, cap = _load_plugin()
        parser = instance.HTMLParser(instance.url)
        parser.feed(YB_ROWS_WITHOUT_FIELDS)
        assert parser.noTorrents is True
        assert len(cap) == 0

    def test_single_torrent_parsed(self):
        instance, cap = _load_plugin()
        parser = instance.HTMLParser(instance.url)
        parser.feed(YB_SINGLE)
        assert parser.noTorrents is False
        assert len(cap) == 1
        assert cap[0]["name"] == "Test Torrent"
        assert cap[0]["size"] == "2.5 GB"
        assert cap[0]["seeds"] == "42"
        assert cap[0]["leech"] == "7"
        assert "yourbittorrent.com" in cap[0]["link"]
        assert cap[0]["engine_url"] == instance.url

    def test_multiple_torrents_parsed(self):
        instance, cap = _load_plugin()
        parser = instance.HTMLParser(instance.url)
        parser.feed(YB_MULTI)
        assert parser.noTorrents is False
        assert len(cap) == 3
        assert cap[0]["name"] == "First"
        assert cap[1]["name"] == "Second"
        assert cap[2]["name"] == "Third"
        assert cap[0]["seeds"] == "10"
        assert cap[2]["leech"] == "1"

    def test_bold_tags_stripped_from_name(self):
        instance, cap = _load_plugin()
        parser = instance.HTMLParser(instance.url)
        parser.feed(YB_BOLD_NAME)
        assert len(cap) == 1
        assert cap[0]["name"] == "Bold Title"
        assert "<b>" not in cap[0]["name"]
        assert "</b>" not in cap[0]["name"]

    def test_span_tags_stripped_from_name(self):
        instance, cap = _load_plugin()
        parser = instance.HTMLParser(instance.url)
        parser.feed(YB_SPAN_NAME)
        assert len(cap) == 1
        assert cap[0]["name"] == "Colored"
        assert "<span" not in cap[0]["name"]
        assert "</span>" not in cap[0]["name"]

    def test_comma_removal_from_numbers(self):
        instance, cap = _load_plugin()
        parser = instance.HTMLParser(instance.url)
        parser.feed(YB_COMMA_NUMBERS)
        assert len(cap) == 1
        assert cap[0]["size"] == "1234.56 GB"
        assert cap[0]["seeds"] == "12345"
        assert cap[0]["leech"] == "6789"

    def test_kb_unit_parsed(self):
        instance, cap = _load_plugin()
        parser = instance.HTMLParser(instance.url)
        parser.feed(YB_KB_UNIT)
        assert len(cap) == 1
        assert cap[0]["size"] == "512 kB"

    def test_mixed_valid_and_invalid_rows(self):
        instance, cap = _load_plugin()
        parser = instance.HTMLParser(instance.url)
        parser.feed(YB_MIXED_VALID_INVALID)
        assert parser.noTorrents is False
        assert len(cap) == 2
        assert cap[0]["name"] == "Good One"
        assert cap[1]["name"] == "Good Two"

    def test_link_is_encoded_desc_link_is_unquoted(self):
        instance, cap = _load_plugin()
        parser = instance.HTMLParser(instance.url)
        parser.feed(YB_SINGLE)
        assert len(cap) == 1
        assert cap[0]["link"] != cap[0]["desc_link"]
        import urllib.parse
        assert urllib.parse.quote(cap[0]["desc_link"], safe="") != cap[0]["desc_link"]
        assert cap[0]["desc_link"] == urllib.parse.unquote(cap[0]["link"])

    def test_noTorrents_reset_on_subsequent_feed(self):
        instance, cap = _load_plugin()
        parser = instance.HTMLParser(instance.url)
        parser.feed(YB_EMPTY)
        assert parser.noTorrents is True
        parser.feed(YB_SINGLE)
        assert parser.noTorrents is False
        assert len(cap) == 1


# ─── search() ───


class TestSearch:
    def test_url_all_category_no_c_param(self):
        instance, cap = _load_plugin()
        mod = sys.modules["yourbittorrent"]
        with patch.object(mod, "retrieve_url", return_value=YB_TWO_DIVS_NO_ROWS) as mock_get:
            instance.search("test", "all")
            call_arg = mock_get.call_args[0][0]
        assert "q=test" in call_arg
        assert "&c=" not in call_arg

    def test_url_specific_category_adds_c_param(self):
        instance, cap = _load_plugin()
        mod = sys.modules["yourbittorrent"]
        with patch.object(mod, "retrieve_url", return_value=YB_TWO_DIVS_NO_ROWS) as mock_get:
            instance.search("test", "movies")
            call_arg = mock_get.call_args[0][0]
        assert "&c=1" in call_arg
        assert "q=test" in call_arg

    def test_url_tv_category(self):
        instance, cap = _load_plugin()
        mod = sys.modules["yourbittorrent"]
        with patch.object(mod, "retrieve_url", return_value=YB_TWO_DIVS_NO_ROWS) as mock_get:
            instance.search("show", "tv")
            call_arg = mock_get.call_args[0][0]
        assert "&c=3" in call_arg

    def test_what_spaces_replaced_with_dashes(self):
        instance, cap = _load_plugin()
        mod = sys.modules["yourbittorrent"]
        with patch.object(mod, "retrieve_url", return_value=YB_TWO_DIVS_NO_ROWS) as mock_get:
            instance.search("hello%20world", "all")
            call_arg = mock_get.call_args[0][0]
        assert "q=hello-world" in call_arg

    def test_all_categories_map_to_correct_values(self):
        instance, cap = _load_plugin()
        expected = {"all": "0", "movies": "1", "tv": "3", "music": "2", "games": "4", "anime": "6", "software": "5"}
        for cat_name, cat_val in expected.items():
            mod = sys.modules["yourbittorrent"]
            with patch.object(mod, "retrieve_url", return_value=YB_TWO_DIVS_NO_ROWS) as mock_get:
                instance.search("x", cat_name)
                call_arg = mock_get.call_args[0][0]
            if cat_name == "all":
                assert "&c=" not in call_arg
                continue
            assert f"&c={cat_val}" in call_arg

    def test_search_feeds_results_to_parser(self):
        instance, cap = _load_plugin()
        mod = sys.modules["yourbittorrent"]
        with patch.object(mod, "retrieve_url", return_value=YB_SINGLE):
            instance.search("test", "all")
        assert len(cap) == 1
        assert cap[0]["name"] == "Test Torrent"

    def test_invalid_category_raises_keyerror(self):
        instance, cap = _load_plugin()
        with pytest.raises(KeyError):
            instance.search("test", "nonexistent")


# ─── download_torrent() ───


class TestDownloadTorrent:
    def test_download_torrent_success_prints_path(self):
        instance, cap = _load_plugin()
        mod = sys.modules["yourbittorrent"]
        with patch.object(mod, "retrieve_url", return_value=YB_DOWNLOAD_PAGE):
            with patch("builtins.print") as mock_print:
                instance.download_torrent("https://yourbittorrent.com//torrent/123")
        mock_print.assert_called_once()
        printed = mock_print.call_args[0][0]
        assert "test123.torrent" in printed

    def test_download_torrent_calls_retrieve_url_with_unquoted_info(self):
        instance, cap = _load_plugin()
        mod = sys.modules["yourbittorrent"]
        import urllib.parse
        encoded_info = urllib.parse.quote("https://yourbittorrent.com//torrent/abc")
        with patch.object(mod, "retrieve_url", return_value=YB_DOWNLOAD_PAGE) as mock_get:
            with patch("builtins.print"):
                instance.download_torrent(encoded_info)
                call_arg = mock_get.call_args[0][0]
        assert call_arg == "https://yourbittorrent.com//torrent/abc"
        assert "%" not in call_arg

    def test_download_torrent_no_match_raises_exception(self):
        instance, cap = _load_plugin()
        mod = sys.modules["yourbittorrent"]
        with patch.object(mod, "retrieve_url", return_value=YB_NO_DOWNLOAD_PAGE):
            with pytest.raises(Exception) as exc_info:
                with patch("builtins.print"):
                    instance.download_torrent("https://yourbittorrent.com//torrent/456")
        assert "bug report" in str(exc_info.value)

    def test_download_torrent_empty_response_raises(self):
        instance, cap = _load_plugin()
        mod = sys.modules["yourbittorrent"]
        with patch.object(mod, "retrieve_url", return_value=""):
            with pytest.raises(Exception) as exc_info:
                with patch("builtins.print"):
                    instance.download_torrent("https://yourbittorrent.com//torrent/789")
        assert "bug report" in str(exc_info.value)


# ─── HTMLParser edge cases ───


class TestHTMLParserEdgeCases:
    def test_all_size_units_accepted(self):
        for size_str in ("1.5 TB", "3.2 GB", "100 MB", "512 kB"):
            html = _wrap_two_divs(_row("/t/u", "UnitTest", size_str, "10", "2"))
            instance, cap = _load_plugin()
            parser = instance.HTMLParser(instance.url)
            parser.feed(html)
            assert len(cap) == 1
            assert cap[0]["size"] == size_str

    def test_parser_preserves_engine_url(self):
        custom_url = "https://example.xyz/"
        instance, cap = _load_plugin()
        instance.url = custom_url
        parser = instance.HTMLParser(custom_url)
        parser.feed(_wrap_two_divs(_row("/t/e", "ETest", "1.0 GB", "5", "3")))
        assert len(cap) == 1
        assert cap[0]["engine_url"] == custom_url
