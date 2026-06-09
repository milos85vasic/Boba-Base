"""Deep-coverage tests for plugins/community/torrentproject.py.

Covers: MyHTMLParser (handle_starttag, handle_endtag, handle_data, get_single_data),
search (pagination, URL construction, category, exception), download_torrent
(magnet URL, info-page magnet extraction, no-magnet error), _fetch_magnet_from_page
(success, failure), datetime handling, edge cases.
"""

import importlib.util
import os
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PLUGINS_DIR = os.path.join(REPO, "plugins", "community")


def _load_torrentproject(captured=None):
    """Import torrentproject plugin with stub modules. Returns (instance, captured)."""
    if captured is None:
        captured = []
    np_mod = types.ModuleType("novaprinter")
    np_mod.prettyPrinter = lambda d: captured.append(dict(d))
    sys.modules["novaprinter"] = np_mod

    helpers_mod = types.ModuleType("helpers")
    helpers_mod.retrieve_url = MagicMock(return_value="")
    sys.modules["helpers"] = helpers_mod

    sys.modules.pop("torrentproject", None)

    path = os.path.join(PLUGINS_DIR, "torrentproject.py")
    spec = importlib.util.spec_from_file_location("torrentproject", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules["torrentproject"] = mod
    cls = getattr(mod, "torrentproject", None)
    if cls is not None and isinstance(cls, type):
        return cls(), captured
    return mod, captured


class TestMyHTMLParserIsolated:
    """Tests that call parser methods directly with controlled state."""

    def setup_method(self):
        self.plugin, self.cap = _load_torrentproject()
        self.parser = self.plugin.MyHTMLParser(self.plugin.url, self.plugin)

    def test_get_single_data_has_all_keys(self):
        data = self.parser.get_single_data()
        expected = {"name", "seeds", "leech", "size", "link", "desc_link", "engine_url", "pub_date"}
        assert set(data.keys()) == expected
        assert data["engine_url"] == self.plugin.url
        for k in ("name", "seeds", "leech", "size", "link", "desc_link", "pub_date"):
            assert data[k] == "-1"

    def test_handle_starttag_div_nav_sets_page_complete(self):
        self.parser.handle_starttag("div", [("id", "nav")])
        assert self.parser.pageComplete is True

    def test_handle_starttag_div_similarfiles_sets_inside_results(self):
        self.parser.handle_starttag("div", [("id", "similarfiles")])
        assert self.parser.insideResults is True

    def test_handle_starttag_div_without_gac_bb_sets_inside_data_div(self):
        self.parser.insideResults = True
        self.parser.handle_starttag("div", [("class", "result_row")])
        assert self.parser.insideDataDiv is True

    def test_handle_starttag_div_with_gac_bb_does_not_set_inside_data_div(self):
        self.parser.insideResults = True
        self.parser.handle_starttag("div", [("class", "gac_bb something")])
        assert self.parser.insideDataDiv is False

    def test_handle_starttag_span_increments_count(self):
        self.parser.insideDataDiv = True
        assert self.parser.spanCount == -1
        self.parser.handle_starttag("span", [])
        assert self.parser.spanCount == 0
        self.parser.handle_starttag("span", [])
        assert self.parser.spanCount == 1

    def test_handle_starttag_verified_span_does_not_increment_count(self):
        self.parser.insideDataDiv = True
        self.parser.handle_starttag("span", [("title", "verified")])
        assert self.parser.spanCount == -1

    def test_handle_starttag_a_at_span_zero_captures_links(self):
        self.parser.insideDataDiv = True
        self.parser.spanCount = 0
        self.parser.handle_starttag("a", [("href", "/torrent/abc123")])
        assert self.parser.singleResData["desc_link"] == "https://torrentproject.com.se/torrent/abc123"
        assert self.parser.singleResData["_info_link"] == "https://torrentproject.com.se/torrent/abc123"

    def test_handle_starttag_a_not_at_span_zero_does_not_capture(self):
        self.parser.insideDataDiv = True
        self.parser.spanCount = 3
        self.parser.handle_starttag("a", [("href", "/torrent/abc123")])
        assert self.parser.singleResData["desc_link"] == "-1"
        assert "_info_link" not in self.parser.singleResData

    def test_handle_endtag_div_closes_data_div_and_resets_span_count(self):
        self.parser.insideDataDiv = True
        self.parser.spanCount = 5
        self.parser.handle_endtag("div")
        assert self.parser.insideDataDiv is False
        assert self.parser.spanCount == -1

    def test_handle_endtag_skips_when_page_complete(self):
        self.parser.pageComplete = True
        self.parser.singleResData["name"] = "Test"
        self.parser.singleResData["size"] = "1 GB"
        self.parser.singleResData["desc_link"] = "https://example.com"
        self.parser.handle_endtag("div")
        assert len(self.parser.pageRes) == 0

    def test_handle_data_captures_name_at_span_zero(self):
        self.parser.insideDataDiv = True
        self.parser.spanCount = 0
        self.parser.handle_data("  Ubuntu 22.04  ")
        assert self.parser.singleResData["name"] == "Ubuntu 22.04"

    def test_handle_data_captures_seeds_at_span_two(self):
        self.parser.insideDataDiv = True
        self.parser.spanCount = 2
        self.parser.handle_data("  150  ")
        assert self.parser.singleResData["seeds"] == "150"

    def test_handle_data_captures_leech_at_span_three(self):
        self.parser.insideDataDiv = True
        self.parser.spanCount = 3
        self.parser.handle_data("  25  ")
        assert self.parser.singleResData["leech"] == "25"

    def test_handle_data_captures_pub_date_at_span_four(self):
        self.parser.insideDataDiv = True
        self.parser.spanCount = 4
        self.parser.handle_data("  2024-01-15 12:30:00  ")
        assert self.parser.singleResData["pub_date"] == "2024-01-15 12:30:00"

    def test_handle_data_captures_size_at_span_five(self):
        self.parser.insideDataDiv = True
        self.parser.spanCount = 5
        self.parser.handle_data("  3.2 GB  ")
        assert self.parser.singleResData["size"] == "3.2 GB"

    def test_handle_data_ignores_span_one(self):
        self.parser.insideDataDiv = True
        self.parser.spanCount = 1
        self.parser.handle_data("ignored-data")
        for k in ("name", "seeds", "leech", "pub_date", "size"):
            assert self.parser.singleResData[k] == "-1"


# ─── HTML fixtures for full feed tests ────────────────────────────────

TP_SINGLE_RESULT = """<div id="similarfiles">
<div>
<span>Ubuntu 22.04 LTS</span>
<a href="/torrent/abc123">torrent</a>
<span>something</span>
<span>150</span>
<span>25</span>
<span>2024-01-15 12:30:00</span>
<span>3.2 GB</span>
</div>
</div>
<div id="nav"></div>"""

TP_MULTI_RESULT = """<div id="similarfiles">
<div>
<span>Ubuntu 22.04 LTS</span>
<a href="/torrent/abc123">torrent</a>
<span>x</span>
<span>150</span>
<span>25</span>
<span>2024-01-15 12:30:00</span>
<span>3.2 GB</span>
</div>
<div>
<span>Debian 12</span>
<a href="/torrent/def456">torrent</a>
<span>x</span>
<span>80</span>
<span>10</span>
<span>2024-02-20 08:00:00</span>
<span>4.0 GB</span>
</div>
</div>
<div id="nav"></div>"""

TP_EMPTY_RESULTS = """<div id="similarfiles">
</div>
<div id="nav"></div>"""

TP_NO_SIMILARFILES = "<html><body><div id=\"nav\">no results</div></body></html>"

TP_MISSING_LINKS = """<div id="similarfiles">
<div>
<span>Ubuntu 22.04 LTS</span>
<span>x</span>
<span>150</span>
<span>25</span>
<span>2024-01-15 12:30:00</span>
<span>3.2 GB</span>
</div>
</div>
<div id="nav"></div>"""

TP_NOME_SKIPPED = """<div id="similarfiles">
<div>
<span>Nome</span>
<a href="/torrent/abc123">torrent</a>
<span>x</span>
<span>150</span>
<span>25</span>
<span>2024-01-15 12:30:00</span>
<span>3.2 GB</span>
</div>
</div>
<div id="nav"></div>"""

TP_GAC_BB_SKIPPED = """<div id="similarfiles">
<div class="gac_bb ad">
<span>Ad content</span>
</div>
<div>
<span>Valid Result</span>
<a href="/torrent/abc123">torrent</a>
<span>x</span>
<span>100</span>
<span>10</span>
<span>2024-03-10 10:00:00</span>
<span>1.0 GB</span>
</div>
</div>
<div id="nav"></div>"""

TP_INVALID_DATE = """<div id="similarfiles">
<div>
<span>File With Bad Date</span>
<a href="/torrent/baddate">torrent</a>
<span>x</span>
<span>50</span>
<span>5</span>
<span>not-a-real-date</span>
<span>500 MB</span>
</div>
</div>
<div id="nav"></div>"""


class TestFeedResults:
    def setup_method(self):
        self.plugin, self.cap = _load_torrentproject()

    @patch("torrentproject.torrentproject._fetch_magnet_from_page", return_value="magnet:?xt=urn:btih:abc123")
    def test_feed_single_result(self, mock_fetch):
        parser = self.plugin.MyHTMLParser(self.plugin.url, self.plugin)
        parser.feed(TP_SINGLE_RESULT)
        parser.close()
        assert len(self.cap) == 1
        result = self.cap[0]
        assert result["name"] == "Ubuntu 22.04 LTS"
        assert result["seeds"] == "150"
        assert result["leech"] == "25"
        assert result["size"] == "3.2 GB"
        assert result["link"] == "magnet:?xt=urn:btih:abc123"
        assert result["engine_url"] == self.plugin.url

    @patch("torrentproject.torrentproject._fetch_magnet_from_page", return_value="magnet:?xt=urn:btih:abc123")
    def test_feed_single_result_pub_date_as_timestamp(self, mock_fetch):
        parser = self.plugin.MyHTMLParser(self.plugin.url, self.plugin)
        parser.feed(TP_SINGLE_RESULT)
        parser.close()
        assert isinstance(self.cap[0]["pub_date"], int)
        from datetime import datetime

        expected_dt = datetime.strptime("2024-01-15 12:30:00", "%Y-%m-%d %H:%M:%S")
        assert self.cap[0]["pub_date"] == int(expected_dt.timestamp())

    @patch("torrentproject.torrentproject._fetch_magnet_from_page", return_value="magnet:?xt=urn:btih:abc123")
    def test_feed_multi_result(self, mock_fetch):
        parser = self.plugin.MyHTMLParser(self.plugin.url, self.plugin)
        parser.feed(TP_MULTI_RESULT)
        parser.close()
        assert len(self.cap) == 2
        assert self.cap[0]["name"] == "Ubuntu 22.04 LTS"
        assert self.cap[1]["name"] == "Debian 12"

    def test_feed_empty(self):
        parser = self.plugin.MyHTMLParser(self.plugin.url, self.plugin)
        parser.feed(TP_EMPTY_RESULTS)
        parser.close()
        assert len(self.cap) == 0

    def test_feed_no_similarfiles_div(self):
        parser = self.plugin.MyHTMLParser(self.plugin.url, self.plugin)
        parser.feed(TP_NO_SIMILARFILES)
        parser.close()
        assert len(self.cap) == 0

    def test_feed_missing_links_no_emission(self):
        parser = self.plugin.MyHTMLParser(self.plugin.url, self.plugin)
        parser.feed(TP_MISSING_LINKS)
        parser.close()
        assert len(self.cap) == 0

    @patch("torrentproject.torrentproject._fetch_magnet_from_page", return_value="magnet:?xt=urn:btih:abc123")
    def test_feed_nome_skipped(self, mock_fetch):
        parser = self.plugin.MyHTMLParser(self.plugin.url, self.plugin)
        parser.feed(TP_NOME_SKIPPED)
        parser.close()
        assert len(self.cap) == 0

    @patch("torrentproject.torrentproject._fetch_magnet_from_page", return_value="magnet:?xt=urn:btih:abc123")
    def test_feed_gac_bb_div_skipped(self, mock_fetch):
        self.cap.clear()
        parser = self.plugin.MyHTMLParser(self.plugin.url, self.plugin)
        parser.feed(TP_GAC_BB_SKIPPED)
        parser.close()
        assert len(self.cap) == 1
        assert self.cap[0]["name"] == "Valid Result"

    @patch("torrentproject.torrentproject._fetch_magnet_from_page", return_value="magnet:?xt=urn:btih:bad")
    def test_feed_invalid_date_still_emits(self, mock_fetch):
        parser = self.plugin.MyHTMLParser(self.plugin.url, self.plugin)
        parser.feed(TP_INVALID_DATE)
        parser.close()
        assert len(self.cap) == 1
        assert self.cap[0]["pub_date"] == "not-a-real-date"


class TestFetchMagnet:
    def setup_method(self):
        self.plugin, self.cap = _load_torrentproject()

    def test_fetch_magnet_success(self):
        html = '<html><a href="magnet:?xt=urn:btih:abcdef123456&amp;dn=test_file">link</a></html>'
        helpers = sys.modules["helpers"]
        helpers.retrieve_url.return_value = html
        result = self.plugin._fetch_magnet_from_page("https://torrentproject.com.se/torrent/abc")
        assert result == "magnet:?xt=urn:btih:abcdef123456&amp;dn=test_file"

    def test_fetch_magnet_no_match(self):
        helpers = sys.modules["helpers"]
        helpers.retrieve_url.return_value = "<html>no magnet</html>"
        result = self.plugin._fetch_magnet_from_page("https://torrentproject.com.se/torrent/abc")
        assert result == ""

    def test_fetch_magnet_exception_returns_empty(self):
        helpers = sys.modules["helpers"]
        helpers.retrieve_url.side_effect = Exception("connection refused")
        result = self.plugin._fetch_magnet_from_page("https://torrentproject.com.se/torrent/abc")
        assert result == ""


class TestSearch:
    def setup_method(self):
        self.plugin, self.cap = _load_torrentproject()

    @patch("torrentproject.torrentproject._fetch_magnet_from_page", return_value="magnet:?xt=urn:btih:abc123")
    def test_search_url_construction(self, mock_fetch):
        self.plugin.search("ubuntu 22.04", "all")
        helpers = sys.modules["helpers"]
        assert helpers.retrieve_url.called
        url = helpers.retrieve_url.call_args[0][0]
        assert "p=0" in url
        assert self.plugin.url in url

    @patch("torrentproject.torrentproject._fetch_magnet_from_page", return_value="magnet:?xt=urn:btih:abc123")
    def test_search_percent20_replaced_with_plus(self, mock_fetch):
        self.plugin.search("hello%20world", "all")
        helpers = sys.modules["helpers"]
        url = helpers.retrieve_url.call_args[0][0]
        assert "hello+world" in url
        assert "%20" not in url

    def test_search_exception_propagates(self):
        helpers = sys.modules["helpers"]
        helpers.retrieve_url.side_effect = Exception("network error")
        with pytest.raises(Exception, match="network error"):
            self.plugin.search("test", "all")


class TestDownloadTorrent:
    def setup_method(self):
        self.plugin, self.cap = _load_torrentproject()

    def test_download_magnet_link_direct(self, capsys):
        self.plugin.download_torrent("magnet:?xt=urn:btih:abc123&dn=test")
        out = capsys.readouterr().out
        assert "magnet:?xt=urn:btih:abc123&dn=test" in out

    def test_download_info_page_finds_magnet(self, capsys):
        helpers = sys.modules["helpers"]
        helpers.retrieve_url.return_value = '<a href="magnet:?xt=urn:btih:abcdef&amp;dn=file">link</a>'
        self.plugin.download_torrent("https://torrentproject.com.se/torrent/abc")
        out = capsys.readouterr().out
        assert "magnet:?xt=urn:btih:abcdef&amp;dn=file" in out
        assert "https://torrentproject.com.se/torrent/abc" in out

    def test_download_info_page_no_magnet(self, capsys):
        helpers = sys.modules["helpers"]
        helpers.retrieve_url.return_value = "<html>no links here</html>"
        self.plugin.download_torrent("https://torrentproject.com.se/torrent/no-magnet")
        err = capsys.readouterr().err
        assert "Could not find magnet link" in err


class TestPluginAttributes:
    def test_class_attributes(self):
        plugin, _ = _load_torrentproject()
        assert plugin.url == "https://torrentproject.com.se"
        assert plugin.name == "TorrentProject"
        assert plugin.supported_categories == {"all": "0"}
        assert "all" in plugin.supported_categories
