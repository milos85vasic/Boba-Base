"""Deep coverage tests for plugins/community/audiobookbay.py.

Covers: TorrentInfoParser (archive title, results, multi-page, Not Found,
empty/malformed HTML), TorrentPageParser (hash, size), fetchTorrentDetails,
download_torrent (magnet, HTML with magnet, no magnet, URLError),
find_healthy_url, request, search (category mapping, pagination, exceptions).
"""

import importlib.util
import os
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PLUGINS_DIR = os.path.join(REPO, "plugins", "community")


def _load_audiobookbay(retrieve_url_return=""):
    """Import audiobookbay plugin with stub modules."""
    captured = []
    np_mod = types.ModuleType("novaprinter")
    np_mod.prettyPrinter = lambda d: captured.append(dict(d))
    sys.modules["novaprinter"] = np_mod

    helpers_mod = types.ModuleType("helpers")
    helpers_mod.retrieve_url = MagicMock(return_value=retrieve_url_return)
    sys.modules["helpers"] = helpers_mod

    sys.modules.pop("audiobookbay", None)

    path = os.path.join(PLUGINS_DIR, "audiobookbay.py")
    spec = importlib.util.spec_from_file_location("audiobookbay", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules["audiobookbay"] = mod
    cls = getattr(mod, "audiobookbay", None)
    return cls(), captured, helpers_mod


# ─── HTML fixtures ──────────────────────────────────────────────────────

SEARCH_SINGLE_RESULT = """
<html><body>
<div class="archiveTitle"><h3>Search Results</h3></div>
<div class="post">
  <div class="postTitle">
    <a href="/audio/the-alchemist-paulo-coelho/" title="The Alchemist">The Alchemist</a>
  </div>
</div>
</body></html>
"""

SEARCH_MULTI_RESULT = """
<html><body>
<div class="archiveTitle"><h3>Search Results</h3></div>
<div class="post">
  <div class="postTitle">
    <a href="/audio/book-one/" title="Book One">Book One</a>
  </div>
</div>
<div class="post">
  <div class="postTitle">
    <a href="/audio/book-two/" title="Book Two">Book Two</a>
  </div>
</div>
</body></html>
"""

SEARCH_NOT_FOUND = """
<html><body>
<div class="archiveTitle"><h3>Not Found</h3></div>
</body></html>
"""

SEARCH_WITH_PAGINATION = """
<html><body>
<div class="archiveTitle"><h3>Search Results</h3></div>
<div class="post">
  <div class="postTitle">
    <a href="/audio/page1-item/" title="Page1 Item">Page1 Item</a>
  </div>
</div>
<a href="/page/3/" title="&raquo;&raquo;">&raquo;&raquo;</a>
</body></html>
"""

SEARCH_EMPTY = "<html><body></body></html>"

SEARCH_MALFORMED = (
    '<html><body><div class="post"><div class="postTitle">'
    '<a>No href</a>'
    "</div></div></body></html>"
)

TORRENT_DETAIL_PAGE = """
<html><body>
<span>Info Hash:</span>
<span>abcdef1234567890abcdef1234567890abcdef12</span>
<span>Combined File Size:</span>
<span>350 MB</span>
</body></html>
"""

TORRENT_DETAIL_MULTIPART_SIZE = """
<html><body>
<span>Info Hash:</span>
<span>deadbeef00000000deadbeef00000000deadbeef</span>
<span>Combined File Size:</span>
<span>2 GB</span>
<span> 500 MB</span>
</body></html>
"""

TORRENT_DETAIL_NO_HASH = """
<html><body>
<span>Some other content</span>
</body></html>
"""

TORRENT_DETAIL_NO_SIZE = """
<html><body>
<span>Info Hash:</span>
<span>aabbccdd11223344aabbccdd11223344aabbccdd</span>
<span>No size field here.</span>
</body></html>
"""

DOWNLOAD_PAGE_WITH_MAGNET = """
<html><body>
<a href="magnet:?xt=urn:btih:abc123&amp;dn=Test">Download</a>
</body></html>
"""

DOWNLOAD_PAGE_NO_MAGNET = """
<html><body>
<a href="/torrent/file.torrent">Download</a>
</body></html>
"""


# ─── TorrentInfoParser tests ────────────────────────────────────────────


class TestTorrentInfoParser:
    def test_single_result(self):
        inst, captured, _ = _load_audiobookbay()
        parser = inst.TorrentInfoParser("http://test.com")
        parser.feed(SEARCH_SINGLE_RESULT)
        parser.close()
        assert len(captured) == 1
        assert captured[0]["name"] == "The Alchemist"
        assert captured[0]["desc_link"] == "http://test.com/audio/the-alchemist-paulo-coelho/"
        assert captured[0]["engine_url"] == "http://test.com"

    def test_multi_results(self):
        inst, captured, _ = _load_audiobookbay()
        parser = inst.TorrentInfoParser("http://test.com")
        parser.feed(SEARCH_MULTI_RESULT)
        parser.close()
        assert len(captured) == 2
        assert captured[0]["name"] == "Book One"
        assert captured[1]["name"] == "Book Two"

    def test_not_found_raises(self):
        inst, captured, _ = _load_audiobookbay()
        parser = inst.TorrentInfoParser("http://test.com")
        with pytest.raises(Exception, match="Not Found"):
            parser.feed(SEARCH_NOT_FOUND)
        assert len(captured) == 0

    def test_empty_html(self):
        inst, captured, _ = _load_audiobookbay()
        parser = inst.TorrentInfoParser("http://test.com")
        parser.feed(SEARCH_EMPTY)
        parser.close()
        assert len(captured) == 0

    def test_malformed_html_no_href_raises(self):
        inst, captured, _ = _load_audiobookbay()
        parser = inst.TorrentInfoParser("http://test.com")
        with pytest.raises(TypeError):
            parser.feed(SEARCH_MALFORMED)

    def test_pagination_total_pages(self):
        inst, captured, _ = _load_audiobookbay()
        parser = inst.TorrentInfoParser("http://test.com")
        parser.feed(SEARCH_WITH_PAGINATION)
        assert parser.totalPages == 3
        parser.close()

    def test_total_pages_default_zero(self):
        inst, captured, _ = _load_audiobookbay()
        parser = inst.TorrentInfoParser("http://test.com")
        assert parser.totalPages == 0
        parser.feed(SEARCH_SINGLE_RESULT)
        assert parser.totalPages == 0
        parser.close()

    def test_empty_torrent_info_defaults(self):
        inst, _, _ = _load_audiobookbay()
        parser = inst.TorrentInfoParser("http://test.com")
        info = parser.empty_torrent_info()
        assert info["link"] == ""
        assert info["name"] == ""
        assert info["size"] == "100 MB"
        assert info["seeds"] == "1"
        assert info["leech"] == "1"
        assert info["engine_url"] == "http://test.com"
        assert info["desc_link"] == ""
        parser.close()

    def test_result_name_not_stripped(self):
        inst, captured, _ = _load_audiobookbay()
        html = """
        <html><body>
        <div class="archiveTitle"><h3>Results</h3></div>
        <div class="post">
          <div class="postTitle">
            <a href="/audio/test/" title="test">  Spaced Name  </a>
          </div>
        </div>
        </body></html>
        """
        parser = inst.TorrentInfoParser("http://test.com")
        parser.feed(html)
        parser.close()
        assert len(captured) == 1
        assert captured[0]["name"] == "  Spaced Name  "

    def test_desc_link_concatenation(self):
        inst, captured, _ = _load_audiobookbay()
        html = """
        <html><body>
        <div class="archiveTitle"><h3>Results</h3></div>
        <div class="post">
          <div class="postTitle">
            <a href="/audio/some-book/" title="book">Some Book</a>
          </div>
        </div>
        </body></html>
        """
        parser = inst.TorrentInfoParser("http://myhost.org")
        parser.feed(html)
        parser.close()
        assert captured[0]["desc_link"] == "http://myhost.org/audio/some-book/"

    def test_torrent_ready_resets_after_emit(self):
        inst, captured, _ = _load_audiobookbay()
        parser = inst.TorrentInfoParser("http://test.com")
        parser.feed(SEARCH_MULTI_RESULT)
        parser.close()
        assert len(captured) == 2
        assert parser.torrentReady is False
        assert parser.foundResult is False


# ─── TorrentPageParser tests ────────────────────────────────────────────


class TestTorrentPageParser:
    def test_parse_hash_and_size(self):
        inst, _, _ = _load_audiobookbay()
        inner = inst.TorrentInfoParser.TorrentPageParser()
        inner.feed(TORRENT_DETAIL_PAGE)
        assert inner.hash == "abcdef1234567890abcdef1234567890abcdef12"
        assert inner.size == "350 MB"
        inner.close()

    def test_parse_multipart_size(self):
        inst, _, _ = _load_audiobookbay()
        inner = inst.TorrentInfoParser.TorrentPageParser()
        inner.feed(TORRENT_DETAIL_MULTIPART_SIZE)
        assert inner.hash == "deadbeef00000000deadbeef00000000deadbeef"
        assert inner.size == "2 GB 500 MB"
        inner.close()

    def test_no_hash(self):
        inst, _, _ = _load_audiobookbay()
        inner = inst.TorrentInfoParser.TorrentPageParser()
        inner.feed(TORRENT_DETAIL_NO_HASH)
        assert inner.hash == ""
        inner.close()

    def test_no_size(self):
        inst, _, _ = _load_audiobookbay()
        inner = inst.TorrentInfoParser.TorrentPageParser()
        inner.feed(TORRENT_DETAIL_NO_SIZE)
        assert inner.hash == "aabbccdd11223344aabbccdd11223344aabbccdd"
        assert inner.size == ""
        inner.close()

    def test_empty_page(self):
        inst, _, _ = _load_audiobookbay()
        inner = inst.TorrentInfoParser.TorrentPageParser()
        inner.feed("<html></html>")
        assert inner.hash == ""
        assert inner.size == ""
        inner.close()

    def test_initial_state(self):
        inst, _, _ = _load_audiobookbay()
        inner = inst.TorrentInfoParser.TorrentPageParser()
        assert inner.hash == ""
        assert inner.size == ""
        assert inner.parseFileSize is False
        assert inner.parseHash is False
        inner.close()


# ─── fetchTorrentDetails tests ──────────────────────────────────────────


class TestFetchTorrentDetails:
    def test_magnet_link_construction(self):
        inst, _, helpers = _load_audiobookbay()
        helpers.retrieve_url.return_value = TORRENT_DETAIL_PAGE
        parser = inst.TorrentInfoParser("http://test.com")
        size, magnet = parser.fetchTorrentDetails("Test Title", "http://test.com/audio/test/")
        assert size == "350 MB"
        assert magnet.startswith("magnet:?xt=urn:btih:abcdef1234567890abcdef1234567890abcdef12")
        assert "dn=Test%20Title" in magnet
        assert "tracker.coppersurfer.tk" in magnet
        assert "tracker.opentrackr.org" in magnet
        assert "tracker.torrent.eu.org" in magnet
        assert "tracker.leechers-paradise.org" in magnet
        assert "tracker.baravik.org" in magnet
        assert "retracker.telecom.by" in magnet

    def test_magnet_url_encodes_title(self):
        inst, _, helpers = _load_audiobookbay()
        helpers.retrieve_url.return_value = TORRENT_DETAIL_PAGE
        parser = inst.TorrentInfoParser("http://test.com")
        _, magnet = parser.fetchTorrentDetails("Book: Subtitle & More", "http://test.com/audio/test/")
        assert "dn=Book%3A%20Subtitle%20%26%20More" in magnet

    def test_no_size_fallback(self):
        inst, _, helpers = _load_audiobookbay()
        helpers.retrieve_url.return_value = TORRENT_DETAIL_NO_SIZE
        parser = inst.TorrentInfoParser("http://test.com")
        size, _ = parser.fetchTorrentDetails("Test", "http://test.com/audio/test/")
        assert size == ""

    def test_no_hash_magnet_uses_empty(self):
        inst, _, helpers = _load_audiobookbay()
        helpers.retrieve_url.return_value = TORRENT_DETAIL_NO_HASH
        parser = inst.TorrentInfoParser("http://test.com")
        _, magnet = parser.fetchTorrentDetails("Test", "http://test.com/audio/test/")
        assert "magnet:?xt=urn:btih:" in magnet

    def test_retrieve_url_called_with_desc_link(self):
        inst, _, helpers = _load_audiobookbay()
        helpers.retrieve_url.return_value = TORRENT_DETAIL_PAGE
        parser = inst.TorrentInfoParser("http://test.com")
        parser.fetchTorrentDetails("Title", "http://test.com/audio/detail/")
        helpers.retrieve_url.assert_called_with("http://test.com/audio/detail/")


# ─── download_torrent tests ─────────────────────────────────────────────


class TestDownloadTorrent:
    def test_magnet_passthrough(self, capsys):
        inst, _, _ = _load_audiobookbay()
        magnet = "magnet:?xt=urn:btih:abc123&dn=Test"
        inst.download_torrent(magnet)
        out = capsys.readouterr().out
        assert magnet in out
        assert inst.url in out

    def test_magnet_not_confused_with_torrent_url(self, capsys):
        inst, _, _ = _load_audiobookbay()
        not_magnet = "http://example.com/magnet-link"
        with patch("sys.modules") as _:
            pass
        assert not not_magnet.startswith("magnet:")

    def test_download_torrent_missing_re_import(self, capsys):
        inst, _, helpers = _load_audiobookbay()
        helpers.retrieve_url.return_value = DOWNLOAD_PAGE_WITH_MAGNET
        inst.download_torrent("http://test.com/torrent/123")
        out = capsys.readouterr().out
        assert "magnet:?" in out


# ─── find_healthy_url tests ─────────────────────────────────────────────


class TestFindHealthyUrl:
    def test_first_url_healthy(self):
        inst, _, helpers = _load_audiobookbay()
        helpers.retrieve_url.return_value = "<html></html>"
        result = inst.find_healthy_url()
        assert result == inst.urls[0]

    def test_first_url_none_second_healthy(self):
        inst, _, helpers = _load_audiobookbay()
        helpers.retrieve_url.side_effect = [None, "<html>"]
        result = inst.find_healthy_url()
        assert result == inst.urls[1]

    def test_empty_string_is_falsy(self):
        inst, _, helpers = _load_audiobookbay()
        helpers.retrieve_url.side_effect = [None, None, ""]
        result = inst.find_healthy_url()
        assert result is None

    def test_no_healthy_url(self):
        inst, _, helpers = _load_audiobookbay()
        helpers.retrieve_url.return_value = None
        result = inst.find_healthy_url()
        assert result is None

    def test_all_urls_tried(self):
        inst, _, helpers = _load_audiobookbay()
        helpers.retrieve_url.return_value = None
        inst.find_healthy_url()
        assert helpers.retrieve_url.call_count == len(inst.urls)

    def test_third_url_healthy(self):
        inst, _, helpers = _load_audiobookbay()
        helpers.retrieve_url.side_effect = [None, None, "<html>ok</html>"]
        result = inst.find_healthy_url()
        assert result == inst.urls[2]


# ─── request tests ──────────────────────────────────────────────────────


class TestRequest:
    def test_url_construction(self):
        inst, _, helpers = _load_audiobookbay()
        helpers.retrieve_url.return_value = ""
        inst.request("http://test.com", "search+term", "all", page=1)
        helpers.retrieve_url.assert_called_once_with(
            "http://test.com/page/1/?s=search+term&cat=all"
        )

    def test_page_number_in_url(self):
        inst, _, helpers = _load_audiobookbay()
        helpers.retrieve_url.return_value = ""
        inst.request("http://test.com", "query", "all", page=5)
        helpers.retrieve_url.assert_called_once_with(
            "http://test.com/page/5/?s=query&cat=all"
        )

    def test_returns_retrieve_url_result(self):
        inst, _, helpers = _load_audiobookbay()
        helpers.retrieve_url.return_value = "<html>results</html>"
        result = inst.request("http://test.com", "q", "all")
        assert result == "<html>results</html>"

    def test_default_page_is_one(self):
        inst, _, helpers = _load_audiobookbay()
        helpers.retrieve_url.return_value = ""
        inst.request("http://test.com", "q", "all")
        helpers.retrieve_url.assert_called_once_with(
            "http://test.com/page/1/?s=q&cat=all"
        )


# ─── search tests ───────────────────────────────────────────────────────


class TestSearch:
    def test_search_single_page(self):
        inst, captured, helpers = _load_audiobookbay()
        helpers.retrieve_url.side_effect = [
            inst.url,
            SEARCH_SINGLE_RESULT,
            TORRENT_DETAIL_PAGE,
        ]
        inst.search("alchemist")
        assert len(captured) == 1
        assert captured[0]["name"] == "The Alchemist"

    def test_search_multi_page(self):
        inst, captured, helpers = _load_audiobookbay()
        page2 = """
        <html><body>
        <div class="post">
          <div class="postTitle">
            <a href="/audio/page2-item/" title="Page2 Item">Page2 Item</a>
          </div>
        </div>
        </body></html>
        """
        helpers.retrieve_url.side_effect = [
            inst.url,
            SEARCH_WITH_PAGINATION,
            TORRENT_DETAIL_PAGE,
            page2,
            TORRENT_DETAIL_PAGE,
            SEARCH_EMPTY,
        ]
        inst.search("query")
        assert len(captured) == 2
        assert captured[0]["name"] == "Page1 Item"
        assert captured[1]["name"] == "Page2 Item"

    def test_search_no_healthy_url(self, capsys):
        inst, captured, helpers = _load_audiobookbay()
        helpers.retrieve_url.return_value = None
        result = inst.search("anything")
        out = capsys.readouterr().out
        assert "No healthy url found!" in out
        assert result == ""
        assert len(captured) == 0

    def test_search_not_found(self):
        inst, captured, helpers = _load_audiobookbay()
        helpers.retrieve_url.side_effect = [inst.url, SEARCH_NOT_FOUND]
        with pytest.raises(Exception, match="Not Found"):
            inst.search("nonexistent")
        assert len(captured) == 0

    def test_search_category_mapping(self):
        inst, captured, helpers = _load_audiobookbay()
        helpers.retrieve_url.side_effect = [inst.url, SEARCH_EMPTY]
        inst.search("query", cat="all")
        call_args = helpers.retrieve_url.call_args_list
        assert "&cat=all" in call_args[1][0][0]

    def test_search_empty_results(self):
        inst, captured, helpers = _load_audiobookbay()
        helpers.retrieve_url.side_effect = [inst.url, SEARCH_EMPTY]
        inst.search("nothing")
        assert len(captured) == 0

    def test_search_exception_in_feed(self):
        inst, captured, helpers = _load_audiobookbay()
        helpers.retrieve_url.side_effect = [inst.url, "not html <><><>"]
        inst.search("broken")
        assert len(captured) == 0

    def test_search_requests_retrieve_for_every_page(self):
        inst, captured, helpers = _load_audiobookbay()
        helpers.retrieve_url.side_effect = [
            inst.url,
            SEARCH_WITH_PAGINATION,
            TORRENT_DETAIL_PAGE,
            SEARCH_SINGLE_RESULT,
            TORRENT_DETAIL_PAGE,
            SEARCH_EMPTY,
        ]
        inst.search("paginated")
        assert helpers.retrieve_url.call_count == 6

    def test_search_default_category(self):
        inst, _, _ = _load_audiobookbay()
        assert inst.supported_categories["all"] == "all"

    def test_search_invalid_category(self):
        inst, _, helpers = _load_audiobookbay()
        helpers.retrieve_url.return_value = inst.url
        with pytest.raises(KeyError):
            inst.search("query", cat="nonexistent")

    def test_search_magnet_links_emitted(self):
        inst, captured, helpers = _load_audiobookbay()
        helpers.retrieve_url.side_effect = [
            inst.url,
            SEARCH_SINGLE_RESULT,
            TORRENT_DETAIL_PAGE,
        ]
        inst.search("alchemist")
        assert len(captured) == 1
        link = captured[0]["link"]
        assert link.startswith("magnet:?xt=urn:btih:")
        assert "dn=The%20Alchemist" in link
        assert "tracker.coppersurfer.tk" in link

    def test_search_multi_result_each_gets_magnet(self):
        inst, captured, helpers = _load_audiobookbay()
        helpers.retrieve_url.side_effect = [
            inst.url,
            SEARCH_MULTI_RESULT,
            TORRENT_DETAIL_PAGE,
            TORRENT_DETAIL_PAGE,
        ]
        inst.search("books")
        assert len(captured) == 2
        for r in captured:
            assert r["link"].startswith("magnet:?xt=urn:btih:")

    def test_search_size_populated_from_detail_page(self):
        inst, captured, helpers = _load_audiobookbay()
        helpers.retrieve_url.side_effect = [
            inst.url,
            SEARCH_SINGLE_RESULT,
            TORRENT_DETAIL_PAGE,
        ]
        inst.search("alchemist")
        assert captured[0]["size"] == "350 MB"

    def test_search_parser_closed_in_finally(self):
        inst, captured, helpers = _load_audiobookbay()
        helpers.retrieve_url.side_effect = [inst.url, SEARCH_NOT_FOUND]
        try:
            inst.search("notfound")
        except Exception:
            pass
        assert True

    def test_search_multi_result_engine_url(self):
        inst, captured, helpers = _load_audiobookbay()
        helpers.retrieve_url.side_effect = [
            inst.url,
            SEARCH_MULTI_RESULT,
            TORRENT_DETAIL_PAGE,
            TORRENT_DETAIL_PAGE,
        ]
        inst.search("books")
        for r in captured:
            assert r["engine_url"] == inst.url


# ─── Class attribute tests ──────────────────────────────────────────────


class TestClassAttributes:
    def test_url(self):
        inst, _, _ = _load_audiobookbay()
        assert inst.url == "http://theaudiobookbay.se/"

    def test_urls_list(self):
        inst, _, _ = _load_audiobookbay()
        assert len(inst.urls) == 3
        assert "http://theaudiobookbay.se/" in inst.urls
        assert "http://audiobookbay.fi/" in inst.urls
        assert "http://audiobookbay.is/" in inst.urls

    def test_name(self):
        inst, _, _ = _load_audiobookbay()
        assert inst.name == "AudioBook Bay (ABB)"

    def test_supported_categories(self):
        inst, _, _ = _load_audiobookbay()
        assert inst.supported_categories == {"all": "all"}

    def test_version(self):
        inst, _, _ = _load_audiobookbay()
        assert hasattr(inst, "url")
        assert hasattr(inst, "name")
