"""Deep coverage tests for plugins/community/rockbox.py.

Covers: HTMLParser init/feed/__findTorrents (single, multi, empty, malformed),
search (URL construction, pagination, sleep, noTorrents termination),
download_torrent, datetime handling, category mapping, exception handling.
"""

import importlib.util
import os
import sys
import types
from unittest.mock import patch

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PLUGINS_DIR = os.path.join(REPO, "plugins", "community")


def _load_rockbox(captured=None):
    if captured is None:
        captured = []
    np_mod = types.ModuleType("novaprinter")
    np_mod.prettyPrinter = lambda d: captured.append(dict(d))
    sys.modules["novaprinter"] = np_mod

    helpers_mod = types.ModuleType("helpers")
    helpers_mod.retrieve_url = lambda url: ""
    sys.modules["helpers"] = helpers_mod

    module_name = "rockbox"
    if module_name in sys.modules:
        del sys.modules[module_name]

    path = os.path.join(PLUGINS_DIR, "rockbox.py")
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules[module_name] = mod
    cls = getattr(mod, "rockbox", None)
    if cls is not None and isinstance(cls, type):
        return cls(), captured
    return mod, captured


# ─── HTML fixtures (regex match: peers details"> not peers details</a>) ───

RB_SINGLE = (
    '<TABLE><TR> <td align="center"><a HREF="details.php?id=123"'
    ' title="details: Test Album (2025)"><img src="icon.gif"></a>'
    '</td> <td><a HREF=download.php?id=123>Download</a></td>'
    ' <td class="lista">15/01/2025</td> <td>1.5 GB</td>'
    ' <td>peers details">25</td>'
    ' <td>peers details">5</td> </TR></TABLE>'
)

RB_MULTI = (
    '<TABLE><TR> <td align="center"><a HREF="details.php?id=1"'
    ' title="details: First Album (2025)"><img src="icon.gif"></a>'
    '</td> <td><a HREF=download.php?id=1>Download</a></td>'
    ' <td class="lista">01/06/2025</td> <td>500 MB</td>'
    ' <td>peers details">10</td>'
    ' <td>peers details">2</td> </TR>'
    '<TR> <td align="center"><a HREF="details.php?id=2"'
    ' title="details: Second Album (2025)"><img src="icon.gif"></a>'
    '</td> <td><a HREF=download.php?id=2>Download</a></td>'
    ' <td class="lista">10/06/2025</td> <td>2.5 GB</td>'
    ' <td>peers details">100</td>'
    ' <td>peers details">20</td> </TR></TABLE>'
)

RB_EMPTY = "<html><body><TABLE><TR><td>No torrents</td></TR></TABLE></body></html>"

RB_MALFORMED = '<TABLE><TR> <td align="center">garbage row no links</td> </TR></TABLE>'

RB_KILOBYTES = (
    '<TABLE><TR> <td align="center"><a HREF="details.php?id=5"'
    ' title="details: Small Album (2025)"><img src="icon.gif"></a>'
    '</td> <td><a HREF=download.php?id=5>Download</a></td>'
    ' <td class="lista">01/03/2025</td> <td>256 KB</td>'
    ' <td>peers details">3</td>'
    ' <td>peers details">1</td> </TR></TABLE>'
)

RB_MB_RESULT = (
    '<TABLE><TR> <td align="center"><a HREF="details.php?id=6"'
    ' title="details: Medium Album (2025)"><img src="icon.gif"></a>'
    '</td> <td><a HREF=download.php?id=6>Download</a></td>'
    ' <td class="lista">15/05/2025</td> <td>750 MB</td>'
    ' <td>peers details">42</td>'
    ' <td>peers details">7</td> </TR></TABLE>'
)

RB_TB_RESULT = (
    '<TABLE><TR> <td align="center"><a HREF="details.php?id=7"'
    ' title="details: Huge Collection (2025)"><img src="icon.gif"></a>'
    '</td> <td><a HREF=download.php?id=7>Download</a></td>'
    ' <td class="lista">01/01/2025</td> <td>1 TB</td>'
    ' <td>peers details">5</td>'
    ' <td>peers details">1</td> </TR></TABLE>'
)

RB_COMMA_SEEDS = (
    '<TABLE><TR> <td align="center"><a HREF="details.php?id=8"'
    ' title="details: Popular Album (2025)"><img src="icon.gif"></a>'
    '</td> <td><a HREF=download.php?id=8>Download</a></td>'
    ' <td class="lista">20/06/2025</td> <td>800 MB</td>'
    ' <td>peers details">1,234</td>'
    ' <td>peers details">56</td> </TR></TABLE>'
)

RB_DATE_DIFFERENT = (
    '<TABLE><TR> <td align="center"><a HREF="details.php?id=9"'
    ' title="details: Leap Year Album (2024)"><img src="icon.gif"></a>'
    '</td> <td><a HREF=download.php?id=9>Download</a></td>'
    ' <td class="lista">29/02/2024</td> <td>300 MB</td>'
    ' <td>peers details">15</td>'
    ' <td>peers details">3</td> </TR></TABLE>'
)

RB_GIGABYTES_INT = (
    '<TABLE><TR> <td align="center"><a HREF="details.php?id=10"'
    ' title="details: Round Size Album (2025)"><img src="icon.gif"></a>'
    '</td> <td><a HREF=download.php?id=10>Download</a></td>'
    ' <td class="lista">01/01/2025</td> <td>5 GB</td>'
    ' <td>peers details">50</td>'
    ' <td>peers details">10</td> </TR></TABLE>'
)

RB_MIXED_SIZE = (
    '<TABLE>'
    '<TR> <td align="center"><a HREF="details.php?id=a"'
    ' title="details: Mix Album A (2025)"><img src="icon.gif"></a>'
    '</td> <td><a HREF=download.php?id=a>Download</a></td>'
    ' <td class="lista">01/01/2025</td> <td>512 KB</td>'
    ' <td>peers details">1</td>'
    ' <td>peers details">0</td> </TR>'
    '<TR> <td align="center"><a HREF="details.php?id=b"'
    ' title="details: Mix Album B (2025)"><img src="icon.gif"></a>'
    '</td> <td><a HREF=download.php?id=b>Download</a></td>'
    ' <td class="lista">01/01/2025</td> <td>1 TB</td>'
    ' <td>peers details">2</td>'
    ' <td>peers details">0</td> </TR></TABLE>'
)


# ─── Test classes ──────────────────────────────────────────────────────


class TestHTMLParser:
    def test_init_sets_url_and_noTorrents_false(self):
        mod, _ = _load_rockbox()
        parser = mod.HTMLParser("https://rawkbawx.rocks/")
        assert parser.url == "https://rawkbawx.rocks/"
        assert parser.noTorrents is False

    def test_feed_single_result_emits_correct_fields(self):
        mod, cap = _load_rockbox()
        mod.HTMLParser(mod.url).feed(RB_SINGLE)
        assert len(cap) == 1
        r = cap[0]
        assert r["name"] == "Test Album (2025)"
        assert r["size"] == "1.5 GB"
        assert r["seeds"] == "25"
        assert r["leech"] == "5"
        assert r["engine_url"] == "https://rawkbawx.rocks/"
        assert "download.php" in r["link"]
        assert "details.php" in r["desc_link"]

    def test_feed_multi_result_emits_all(self):
        mod, cap = _load_rockbox()
        mod.HTMLParser(mod.url).feed(RB_MULTI)
        assert len(cap) == 2
        assert cap[0]["name"] == "First Album (2025)"
        assert cap[1]["name"] == "Second Album (2025)"
        assert cap[0]["seeds"] == "10"
        assert cap[1]["seeds"] == "100"

    def test_feed_empty_html_sets_noTorrents_true(self):
        mod, cap = _load_rockbox()
        parser = mod.HTMLParser(mod.url)
        parser.feed(RB_EMPTY)
        assert parser.noTorrents is True
        assert len(cap) == 0

    def test_feed_malformed_tr_sets_noTorrents_true(self):
        mod, cap = _load_rockbox()
        parser = mod.HTMLParser(mod.url)
        parser.feed(RB_MALFORMED)
        assert parser.noTorrents is True
        assert len(cap) == 0

    def test_feed_extracts_pub_date_as_timestamp(self):
        mod, cap = _load_rockbox()
        mod.HTMLParser(mod.url).feed(RB_SINGLE)
        from datetime import datetime as dt

        assert isinstance(cap[0]["pub_date"], int)
        expected_ts = int(dt(2025, 1, 15).timestamp())
        assert cap[0]["pub_date"] == expected_ts

    def test_feed_extracts_leap_year_date(self):
        mod, cap = _load_rockbox()
        mod.HTMLParser(mod.url).feed(RB_DATE_DIFFERENT)
        assert len(cap) == 1
        from datetime import datetime as dt

        expected_ts = int(dt(2024, 2, 29).timestamp())
        assert cap[0]["pub_date"] == expected_ts

    def test_feed_kilobyte_size_preserved(self):
        mod, cap = _load_rockbox()
        mod.HTMLParser(mod.url).feed(RB_KILOBYTES)
        assert cap[0]["size"] == "256 KB"

    def test_feed_megabyte_size_preserved(self):
        mod, cap = _load_rockbox()
        mod.HTMLParser(mod.url).feed(RB_MB_RESULT)
        assert cap[0]["size"] == "750 MB"

    def test_feed_terabyte_size_preserved(self):
        mod, cap = _load_rockbox()
        mod.HTMLParser(mod.url).feed(RB_TB_RESULT)
        assert cap[0]["size"] == "1 TB"

    def test_feed_integer_gigabyte_size_preserved(self):
        mod, cap = _load_rockbox()
        mod.HTMLParser(mod.url).feed(RB_GIGABYTES_INT)
        assert cap[0]["size"] == "5 GB"

    def test_feed_comma_in_seeds_preserved_as_string(self):
        mod, cap = _load_rockbox()
        mod.HTMLParser(mod.url).feed(RB_COMMA_SEEDS)
        assert cap[0]["seeds"] == "1,234"
        assert cap[0]["leech"] == "56"

    def test_feed_mixed_size_units_in_same_feed(self):
        mod, cap = _load_rockbox()
        mod.HTMLParser(mod.url).feed(RB_MIXED_SIZE)
        assert len(cap) == 2
        assert cap[0]["size"] == "512 KB"
        assert cap[1]["size"] == "1 TB"

    def test_feed_link_contains_base_url(self):
        mod, cap = _load_rockbox()
        mod.HTMLParser(mod.url).feed(RB_SINGLE)
        assert "/download.php" in cap[0]["link"]
        assert "rawkbawx.rocks" in cap[0]["link"]

    def test_feed_desc_link_contains_base_url(self):
        mod, cap = _load_rockbox()
        mod.HTMLParser(mod.url).feed(RB_SINGLE)
        assert cap[0]["desc_link"] == "https://rawkbawx.rocks/details.php?id=123"

    def test_feed_second_call_resets_noTorrents(self):
        mod, cap = _load_rockbox()
        parser = mod.HTMLParser(mod.url)
        parser.feed(RB_EMPTY)
        assert parser.noTorrents is True
        parser.feed(RB_SINGLE)
        assert parser.noTorrents is False
        assert len(cap) == 1


class TestSearch:
    def setup_method(self):
        self.mod, self.cap = _load_rockbox()

    @patch("rockbox.retrieve_url")
    @patch("rockbox.sleep")
    def test_search_url_construction_with_space(self, mock_sleep, mock_retrieve):
        mock_retrieve.side_effect = [RB_SINGLE, RB_EMPTY]
        self.mod.search("test query", "all")
        called_url = mock_retrieve.call_args_list[0][0][0]
        assert "search=test%20query" in called_url or "search=test query" in called_url
        assert "page=0" in called_url
        assert called_url.startswith("https://rawkbawx.rocks/torrents.php")

    @patch("rockbox.retrieve_url")
    @patch("rockbox.sleep")
    def test_search_replaces_percent20_with_plus(self, mock_sleep, mock_retrieve):
        mock_retrieve.side_effect = [RB_SINGLE, RB_EMPTY]
        self.mod.search("test%20query", "all")
        called_url = mock_retrieve.call_args_list[0][0][0]
        assert "search=test+query" in called_url
        assert "test%20query" not in called_url

    @patch("rockbox.retrieve_url")
    @patch("rockbox.sleep")
    def test_search_paginates_multiple_pages(self, mock_sleep, mock_retrieve):
        mock_retrieve.side_effect = [RB_MULTI, RB_SINGLE, RB_EMPTY]
        self.mod.search("test", "all")
        assert mock_retrieve.call_count == 3
        assert "page=0" in mock_retrieve.call_args_list[0][0][0]
        assert "page=1" in mock_retrieve.call_args_list[1][0][0]
        assert "page=2" in mock_retrieve.call_args_list[2][0][0]
        assert len(self.cap) == 3

    @patch("rockbox.retrieve_url", return_value=RB_EMPTY)
    @patch("rockbox.sleep")
    def test_search_stops_on_empty_page(self, mock_sleep, mock_retrieve):
        self.mod.search("notfound", "all")
        assert mock_retrieve.call_count == 1

    @patch("rockbox.retrieve_url")
    @patch("rockbox.sleep")
    def test_search_sleeps_between_pages(self, mock_sleep, mock_retrieve):
        mock_retrieve.side_effect = [RB_SINGLE, RB_EMPTY]
        self.mod.search("test", "all")
        mock_sleep.assert_called_once_with(3)

    @patch("rockbox.retrieve_url")
    @patch("rockbox.sleep")
    def test_search_does_not_sleep_on_last_page(self, mock_sleep, mock_retrieve):
        mock_retrieve.side_effect = [RB_SINGLE, RB_SINGLE, RB_EMPTY]
        self.mod.search("test", "all")
        assert mock_sleep.call_count == 2

    @patch("rockbox.retrieve_url", side_effect=Exception("network error"))
    @patch("rockbox.sleep")
    def test_search_exception_propagates(self, mock_sleep, mock_retrieve):
        with pytest.raises(Exception, match="network error"):
            self.mod.search("test", "all")

    @patch("rockbox.retrieve_url")
    @patch("rockbox.sleep")
    def test_search_default_category_all(self, mock_sleep, mock_retrieve):
        mock_retrieve.side_effect = [RB_SINGLE, RB_EMPTY]
        self.mod.search("test")
        mock_retrieve.assert_called()

    @patch("rockbox.retrieve_url")
    @patch("rockbox.sleep")
    def test_search_collapses_html_whitespace(self, mock_sleep, mock_retrieve):
        multiline = (
            "<HTML>\n  <TABLE>\n<TR> <td align=\"center\">"
            "<a HREF=\"details.php?id=99\" title=\"details: Whitespace Album (2025)\">"
            "<img src=\"icon.gif\"></a></td>"
            " <td><a HREF=download.php?id=99>Download</a></td>"
            " <td class=\"lista\">01/01/2025</td> <td>100 MB</td>"
            " <td>peers details\">7</td>"
            " <td>peers details\">2</td> </TR>\n</TABLE>\n</HTML>"
        )
        mock_retrieve.side_effect = [multiline, RB_EMPTY]
        self.mod.search("whitespace", "all")
        assert len(self.cap) == 1
        assert self.cap[0]["name"] == "Whitespace Album (2025)"


class TestDownloadTorrent:
    def setup_method(self):
        self.mod, self.cap = _load_rockbox()

    def test_download_torrent_unquotes_and_prints_twice(self, capsys):
        self.mod.download_torrent(
            "https%3A%2F%2Frawkbawx.rocks%2Fdownload.php%3Fid%3D123"
        )
        out = capsys.readouterr().out
        expected = "https://rawkbawx.rocks/download.php?id=123"
        assert out.count(expected) == 2
        assert out.strip() == f"{expected} {expected}"

    def test_download_torrent_with_plain_url_noop(self, capsys):
        self.mod.download_torrent("https://rawkbawx.rocks/download.php?id=456")
        out = capsys.readouterr().out
        assert "https://rawkbawx.rocks/download.php?id=456" in out

    def test_download_torrent_with_encoded_special_chars(self, capsys):
        self.mod.download_torrent("magnet%3A%3Fxt%3Durn%3Abtih%3Aabc123")
        out = capsys.readouterr().out
        assert "magnet:?xt=urn:btih:abc123" in out

    def test_download_torrent_empty_string(self, capsys):
        self.mod.download_torrent("")
        out = capsys.readouterr().out
        assert out.strip() == ""


class TestPluginAttributes:
    def test_url_attribute(self):
        mod, _ = _load_rockbox()
        assert mod.url == "https://rawkbawx.rocks/"

    def test_name_attribute(self):
        mod, _ = _load_rockbox()
        assert mod.name == "RockBox"

    def test_supported_categories_only_all(self):
        mod, _ = _load_rockbox()
        assert mod.supported_categories == {"all": "0"}
        assert "all" in mod.supported_categories
        assert len(mod.supported_categories) == 1
