"""Deep coverage tests for plugins/community/torrentdownload.py.

Covers: HTMLParser.feed / __findTorrents (single, multi, empty, malformed,
special chars, all size units), search (URL construction, pagination,
empty page breaks loop, sleep, max pages), download_torrent (print twice),
category mapping (unused param).
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


def _load_torrentdownload(captured=None):
    if captured is None:
        captured = []
    np_mod = types.ModuleType("novaprinter")
    np_mod.prettyPrinter = lambda d: captured.append(dict(d))
    sys.modules["novaprinter"] = np_mod

    helpers_mod = types.ModuleType("helpers")
    helpers_mod.retrieve_url = lambda url: ""
    sys.modules["helpers"] = helpers_mod

    sys.modules.pop("torrentdownload", None)

    path = os.path.join(PLUGINS_DIR, "torrentdownload.py")
    spec = importlib.util.spec_from_file_location("torrentdownload", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules["torrentdownload"] = mod
    cls = getattr(mod, "torrentdownload", None)
    if cls is not None and isinstance(cls, type):
        return cls(), captured
    return mod, captured


def _collapse(html):
    return re.sub(r"\s+", " ", html).strip()


# ─── HTML fixtures (single-line; regex .+? does not match newlines) ─────

TD_SINGLE = (
    '<tr><td class="tt-name"><a href="/path/to/my-torrent-here">My Torrent Here</a></td>'
    '<td class="tdnormal">1.5 GB</td>'
    '<td class="tdseed">100</td>'
    '<td class="tdleech">20</td></tr>'
)

TD_MULTI = (
    '<tr><td class="tt-name"><a href="/path/torrent-a">Torrent A</a></td>'
    '<td class="tdnormal">35.2 GB</td>'
    '<td class="tdseed">500</td>'
    '<td class="tdleech">50</td></tr>'
    '<tr><td class="tt-name"><a href="/path/torrent-b">Torrent B</a></td>'
    '<td class="tdnormal">750 MB</td>'
    '<td class="tdseed">25</td>'
    '<td class="tdleech">5</td></tr>'
)

TD_EMPTY = '<html><body><p>No results.</p></body></html>'

TD_MALFORMED = '<tr><td class="tt-name"><a href="/path/broken">Broken</a></td></tr>'

TD_TB_SIZE = (
    '<tr><td class="tt-name"><a href="/path/huge">Huge File</a></td>'
    '<td class="tdnormal">2.5 TB</td>'
    '<td class="tdseed">10</td>'
    '<td class="tdleech">1</td></tr>'
)

TD_KB_SIZE = (
    '<tr><td class="tt-name"><a href="/path/tiny">Tiny File</a></td>'
    '<td class="tdnormal">512 KB</td>'
    '<td class="tdseed">5</td>'
    '<td class="tdleech">0</td></tr>'
)

TD_COMMA_SIZE = (
    '<tr><td class="tt-name"><a href="/path/big">Big File</a></td>'
    '<td class="tdnormal">1,024.5 MB</td>'
    '<td class="tdseed">1,200</td>'
    '<td class="tdleech">300</td></tr>'
)

TD_SPECIAL_CHARS = (
    '<tr><td class="tt-name"><a href="/path/name">Name &amp; "Quotes" &lt;Tag&gt;</a></td>'
    '<td class="tdnormal">10 GB</td>'
    '<td class="tdseed">50</td>'
    '<td class="tdleech">10</td></tr>'
)

TD_SPAN_IN_NAME = (
    '<tr><td class="tt-name"><a href="/path/span">Before<span class="na">Highlight</span>After</a></td>'
    '<td class="tdnormal">5 GB</td>'
    '<td class="tdseed">30</td>'
    '<td class="tdleech">3</td></tr>'
)


class TestHTMLParserFeed:
    def test_single_result(self):
        inst, cap = _load_torrentdownload()
        parser = inst.HTMLParser(inst.url)
        parser.feed(_collapse(TD_SINGLE))
        assert len(cap) == 1
        assert cap[0]["name"] == "My Torrent Here"
        assert "magnet:?xt=urn:btih:" in cap[0]["link"]
        assert cap[0]["size"] == "1.5 GB"
        assert cap[0]["seeds"] == "100"
        assert cap[0]["leech"] == "20"
        assert cap[0]["desc_link"] == inst.url + "path/to/my-torrent-here"
        assert cap[0]["engine_url"] == inst.url

    def test_multi_results(self):
        inst, cap = _load_torrentdownload()
        parser = inst.HTMLParser(inst.url)
        parser.feed(_collapse(TD_MULTI))
        assert len(cap) == 2
        assert cap[0]["name"] == "Torrent A"
        assert cap[1]["name"] == "Torrent B"
        assert cap[0]["size"] == "35.2 GB"
        assert cap[1]["size"] == "750 MB"

    def test_empty_html(self):
        inst, cap = _load_torrentdownload()
        parser = inst.HTMLParser(inst.url)
        parser.feed(_collapse(TD_EMPTY))
        assert len(cap) == 0
        assert parser.pageResSize == 0

    def test_malformed_row_skipped(self):
        inst, cap = _load_torrentdownload()
        parser = inst.HTMLParser(inst.url)
        parser.feed(_collapse(TD_MALFORMED))
        assert len(cap) == 0
        assert parser.pageResSize == 0

    def test_page_res_size_set(self):
        inst, _ = _load_torrentdownload()
        parser = inst.HTMLParser(inst.url)
        parser.feed(_collapse(TD_MULTI))
        assert parser.pageResSize == 2

    def test_page_res_size_resets_on_re_feed(self):
        inst, _ = _load_torrentdownload()
        parser = inst.HTMLParser(inst.url)
        parser.feed(_collapse(TD_MULTI))
        assert parser.pageResSize == 2
        parser.feed(_collapse(TD_EMPTY))
        assert parser.pageResSize == 0

    def test_tb_size_parsed(self):
        inst, cap = _load_torrentdownload()
        parser = inst.HTMLParser(inst.url)
        parser.feed(_collapse(TD_TB_SIZE))
        assert len(cap) == 1
        assert cap[0]["size"] == "2.5 TB"

    def test_kb_size_parsed(self):
        inst, cap = _load_torrentdownload()
        parser = inst.HTMLParser(inst.url)
        parser.feed(_collapse(TD_KB_SIZE))
        assert len(cap) == 1
        assert cap[0]["size"] == "512 KB"

    def test_comma_in_size_and_seeds(self):
        inst, cap = _load_torrentdownload()
        parser = inst.HTMLParser(inst.url)
        parser.feed(_collapse(TD_COMMA_SIZE))
        assert len(cap) == 1
        assert cap[0]["size"] == "1024.5 MB"
        assert cap[0]["seeds"] == "1200"
        assert cap[0]["leech"] == "300"

    def test_special_chars_in_name(self):
        inst, cap = _load_torrentdownload()
        parser = inst.HTMLParser(inst.url)
        parser.feed(_collapse(TD_SPECIAL_CHARS))
        assert len(cap) == 1
        assert cap[0]["name"] == 'Name &amp; "Quotes" &lt;Tag&gt;'

    def test_span_stripped_from_name(self):
        inst, cap = _load_torrentdownload()
        parser = inst.HTMLParser(inst.url)
        parser.feed(_collapse(TD_SPAN_IN_NAME))
        assert len(cap) == 1
        assert cap[0]["name"] == "BeforeHighlightAfter"

    def test_magnet_link_format(self):
        inst, cap = _load_torrentdownload()
        parser = inst.HTMLParser(inst.url)
        parser.feed(_collapse(TD_SINGLE))
        magnet = cap[0]["link"]
        assert magnet.startswith("magnet:?xt=urn:btih:")
        btih = magnet.split("btih:")[1].split("&")[0]
        assert btih == "path"
        assert "tracker" in magnet

    def test_desc_link_construction(self):
        inst, cap = _load_torrentdownload()
        parser = inst.HTMLParser(inst.url)
        parser.feed(_collapse(TD_SINGLE))
        assert cap[0]["desc_link"] == inst.url + "path/to/my-torrent-here"

    def test_empty_string_no_crash(self):
        inst, _ = _load_torrentdownload()
        parser = inst.HTMLParser(inst.url)
        parser.feed("")
        assert parser.pageResSize == 0

    def test_whitespace_only_no_crash(self):
        inst, _ = _load_torrentdownload()
        parser = inst.HTMLParser(inst.url)
        parser.feed("   \n\t  ")
        assert parser.pageResSize == 0


class TestSearch:
    def setup_method(self):
        self.inst, self.cap = _load_torrentdownload()

    @patch("torrentdownload.sleep")
    @patch("torrentdownload.retrieve_url", return_value=TD_SINGLE)
    def test_search_url_construction(self, mock_retrieve, _sleep):  # noqa: PT019
        self.inst.search("hello+world", "all")
        first_url = mock_retrieve.call_args_list[0][0][0]
        assert first_url == "https://www.torrentdownload.info/search?q=hello+world&p=1"

    @patch("torrentdownload.sleep")
    @patch("torrentdownload.retrieve_url", return_value=TD_SINGLE)
    def test_search_replaces_pct20(self, mock_retrieve, _sleep):  # noqa: PT019
        self.inst.search("hello%20world", "all")
        first_url = mock_retrieve.call_args_list[0][0][0]
        assert "q=hello+world" in first_url

    @patch("torrentdownload.sleep")
    @patch("torrentdownload.retrieve_url", return_value=TD_SINGLE)
    def test_search_results_emitted(self, mock_retrieve, _sleep):  # noqa: PT019
        mock_retrieve.side_effect = [TD_SINGLE, TD_EMPTY]
        self.inst.search("test", "all")
        assert len(self.cap) == 1
        assert self.cap[0]["name"] == "My Torrent Here"

    @patch("torrentdownload.retrieve_url", return_value=TD_EMPTY)
    def test_search_empty_page_breaks_loop(self, mock_retrieve):
        self.inst.search("nothing", "all")
        assert mock_retrieve.call_count == 1

    @patch("torrentdownload.sleep")
    @patch("torrentdownload.retrieve_url", return_value=TD_SINGLE)
    def test_search_sleeps_between_pages(self, mock_retrieve, mock_sleep):
        self.inst.search("test", "all")
        mock_sleep.assert_called_with(3)

    @patch("torrentdownload.retrieve_url", return_value=TD_EMPTY)
    def test_search_no_results_no_sleep(self, mock_retrieve):
        with patch("torrentdownload.sleep") as mock_sleep:
            self.inst.search("nothing", "all")
            mock_sleep.assert_not_called()

    @patch("torrentdownload.sleep")
    @patch("torrentdownload.retrieve_url", return_value=TD_MULTI)
    def test_search_multiple_pages(self, mock_retrieve, mock_sleep):
        self.inst.search("test", "all")
        assert mock_retrieve.call_count == 9
        assert mock_sleep.call_count == 9

    @patch("torrentdownload.sleep")
    @patch("torrentdownload.retrieve_url", return_value=TD_SINGLE)
    def test_search_category_unused(self, mock_retrieve, _sleep):  # noqa: PT019
        self.inst.search("test", "movies")
        first_url = mock_retrieve.call_args_list[0][0][0]
        assert "movies" not in first_url

    @patch("torrentdownload.retrieve_url", side_effect=Exception("network error"))
    def test_search_exception_does_not_crash(self, mock_retrieve):
        with pytest.raises(Exception, match="network error"):
            self.inst.search("test", "all")
        assert len(self.cap) == 0

    @patch("torrentdownload.sleep")
    @patch("torrentdownload.retrieve_url", return_value=TD_SINGLE)
    def test_search_max_pages_respected(self, mock_retrieve, _sleep):  # noqa: PT019
        self.inst.max_pages = 2
        self.inst.search("test", "all")
        assert mock_retrieve.call_count == 1

    @patch("torrentdownload.sleep")
    @patch("torrentdownload.retrieve_url")
    def test_search_paginator_page_index(self, mock_retrieve, _sleep):  # noqa: PT019
        mock_retrieve.return_value = TD_EMPTY
        self.inst.search("test", "all")
        first_url = mock_retrieve.call_args_list[0][0][0]
        assert "p=1" in first_url

    @patch("torrentdownload.sleep")
    @patch("torrentdownload.retrieve_url")
    def test_search_html_whitespace_collapsed(self, mock_retrieve, _sleep):  # noqa: PT019
        spaced = TD_SINGLE + "  \n  " + TD_SINGLE
        mock_retrieve.side_effect = [spaced, TD_EMPTY]
        self.inst.search("test", "all")
        assert len(self.cap) == 2

    @patch("torrentdownload.sleep")
    @patch("torrentdownload.retrieve_url", return_value=TD_SINGLE)
    def test_search_second_page_empty_stops(self, mock_retrieve, mock_sleep):
        mock_retrieve.side_effect = [TD_SINGLE, TD_EMPTY]
        self.inst.search("test", "all")
        assert mock_retrieve.call_count == 2
        assert mock_sleep.call_count == 1

    @patch("torrentdownload.sleep")
    @patch("torrentdownload.retrieve_url", return_value=TD_SINGLE)
    def test_search_special_chars_in_query(self, mock_retrieve, _sleep):  # noqa: PT019
        self.inst.search("name%20with%20spaces", "all")
        first_url = mock_retrieve.call_args_list[0][0][0]
        assert "q=name+with+spaces" in first_url


class TestDownloadTorrent:
    def setup_method(self):
        self.inst, self.cap = _load_torrentdownload()

    def test_download_prints_url_twice(self, capsys):
        self.inst.download_torrent("https://example.com/torrent/123")
        out = capsys.readouterr().out
        assert out.count("https://example.com/torrent/123") == 2

    def test_download_with_magnet(self, capsys):
        self.inst.download_torrent("magnet:?xt=urn:btih:abc123")
        out = capsys.readouterr().out
        assert "magnet:?xt=urn:btih:abc123 magnet:?xt=urn:btih:abc123" in out

    def test_download_empty_url(self, capsys):
        self.inst.download_torrent("")
        out = capsys.readouterr().out
        assert out == " \n"


class TestPluginMetadata:
    def test_url_attribute(self):
        inst, _ = _load_torrentdownload()
        assert inst.url == "https://www.torrentdownload.info/"

    def test_name_attribute(self):
        inst, _ = _load_torrentdownload()
        assert inst.name == "TorrentDownload"

    def test_max_pages_attribute(self):
        inst, _ = _load_torrentdownload()
        assert inst.max_pages == 10
