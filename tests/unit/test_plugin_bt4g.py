"""Deep coverage tests for plugins/community/bt4g.py.

Covers: HTMLParser.feed (single/multi/empty/malformed), __findTorrents regex,
search (URL construction, category mapping, pagination, exceptions),
download_torrent (magnet, no-magnet, exception), category mapping, edge cases.
"""

import importlib.util
import os
import sys
import types
from datetime import datetime
from unittest.mock import patch

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PLUGINS_DIR = os.path.join(REPO, "plugins", "community")


def _load_bt4g(captured=None):
    """Import bt4g plugin with stub modules. Returns (instance, captured)."""
    if captured is None:
        captured = []
    np_mod = types.ModuleType("novaprinter")
    np_mod.prettyPrinter = lambda d: captured.append(dict(d))
    sys.modules["novaprinter"] = np_mod

    helpers_mod = types.ModuleType("helpers")
    helpers_mod.retrieve_url = lambda url: ""
    sys.modules["helpers"] = helpers_mod

    sys.modules.pop("bt4g", None)

    path = os.path.join(PLUGINS_DIR, "bt4g.py")
    spec = importlib.util.spec_from_file_location("bt4g", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules["bt4g"] = mod
    cls = getattr(mod, "bt4g", None)
    if cls is not None and isinstance(cls, type):
        return cls(), captured
    return mod, captured


def _collapse(html):
    """Simulate search()'s re.sub(r'\\s+', ' ', ...).strip()."""
    import re
    return re.sub(r"\s+", " ", html).strip()


# ─── HTML fixtures (single-line, matching bt4g regex) ───────────────────────
# Pattern expects:
#   <div class="list-group-item result-item">
#     ...title="NAME" href="HREF"...Creation Time: YYYY-MM-DD<...
#     Total Size...>SIZE(TB|GB|MB|KB)...seeders">SEEDS...leechers">LEECH
#   </div>

BT4G_SINGLE = '<div class="list-group-item result-item"><a title="Ubuntu 22.04 LTS" href="/torrent/12345" >Download</a> Creation Time: 2025-03-15<br>Total Size:>4.7GB<br><span class="seeders">120</span><span class="leechers">15</span></div>'

BT4G_MULTI = (
    '<div class="list-group-item result-item"><a title="Ubuntu 22.04 LTS" href="/torrent/12345" >Download</a> Creation Time: 2025-03-15<br>Total Size:>4.7GB<br><span class="seeders">120</span><span class="leechers">15</span></div>'
    '<div class="list-group-item result-item"><a title="Fedora 40 Workstation" href="/torrent/67890" >Download</a> Creation Time: 2024-12-01<br>Total Size:>2.1GB<br><span class="seeders">85</span><span class="leechers">10</span></div>'
)

BT4G_TB_SIZE = '<div class="list-group-item result-item"><a title="Large Dataset" href="/torrent/11111" >Download</a> Creation Time: 2025-01-01<br>Total Size:>1.5TB<br><span class="seeders">5</span><span class="leechers">1</span></div>'

BT4G_KB_SIZE = '<div class="list-group-item result-item"><a title="Tiny Patch" href="/torrent/22222" >Download</a> Creation Time: 2025-06-01<br>Total Size:>128KB<br><span class="seeders">50</span><span class="leechers">0</span></div>'

BT4G_MB_SIZE = '<div class="list-group-item result-item"><a title="Medium ISO" href="/torrent/33333" >Download</a> Creation Time: 2025-04-10<br>Total Size:>750.5MB<br><span class="seeders">200</span><span class="leechers">30</span></div>'

BT4G_COMMA_SIZE = '<div class="list-group-item result-item"><a title="Big Archive" href="/torrent/44444" >Download</a> Creation Time: 2025-02-20<br>Total Size:>1,024.5GB<br><span class="seeders">10</span><span class="leechers">2</span></div>'

BT4G_EMPTY = '<html><body><p>No results found.</p></body></html>'

BT4G_MALFORMED = '<div class="list-group-item result-item"><a title="Broken Entry" href="/torrent/99999" >Download</a> Missing required fields here</div>'

BT4G_SPECIAL_CHARS = '<div class="list-group-item result-item"><a title="C++ &amp; Python Guide" href="/torrent/55555" >Download</a> Creation Time: 2025-05-20<br>Total Size:>15.3GB<br><span class="seeders">300</span><span class="leechers">45</span></div>'

BT4G_PAGE2 = '<div class="list-group-item result-item"><a title="Page2 Result" href="/torrent/77777" >Download</a> Creation Time: 2025-04-01<br>Total Size:>8.2GB<br><span class="seeders">60</span><span class="leechers">8</span></div>'


# ─── HTMLParser tests ───────────────────────────────────────────────────────

class TestHTMLParserFeed:
    def test_single_result(self):
        inst, cap = _load_bt4g()
        parser = inst.HTMLParser(inst.url)
        parser.feed(BT4G_SINGLE)
        assert len(cap) == 1
        assert cap[0]["name"] == "Ubuntu 22.04 LTS"
        assert cap[0]["link"] == "https%3A//bt4gprx.com/torrent/12345"
        assert cap[0]["desc_link"] == "https://bt4gprx.com/torrent/12345"
        assert cap[0]["engine_url"] == "https://bt4gprx.com/"
        assert cap[0]["size"] == "4.7GB"
        assert cap[0]["seeds"] == "120"
        assert cap[0]["leech"] == "15"
        assert isinstance(cap[0]["pub_date"], int)

    def test_multi_results(self):
        inst, cap = _load_bt4g()
        parser = inst.HTMLParser(inst.url)
        parser.feed(BT4G_MULTI)
        assert len(cap) == 2
        assert cap[0]["name"] == "Ubuntu 22.04 LTS"
        assert cap[1]["name"] == "Fedora 40 Workstation"
        assert cap[1]["seeds"] == "85"
        assert cap[1]["leech"] == "10"

    def test_empty_html_sets_no_torrents(self):
        inst, _ = _load_bt4g()
        parser = inst.HTMLParser(inst.url)
        parser.feed(BT4G_EMPTY)
        assert parser.noTorrents is True

    def test_malformed_entry_skipped(self):
        inst, cap = _load_bt4g()
        parser = inst.HTMLParser(inst.url)
        parser.feed(BT4G_MALFORMED)
        assert parser.noTorrents is True
        assert len(cap) == 0

    def test_no_torrents_flag_reset_on_feed(self):
        inst, _ = _load_bt4g()
        parser = inst.HTMLParser(inst.url)
        parser.feed(BT4G_EMPTY)
        assert parser.noTorrents is True
        parser.feed(BT4G_SINGLE)
        assert parser.noTorrents is False

    def test_tb_size(self):
        inst, cap = _load_bt4g()
        parser = inst.HTMLParser(inst.url)
        parser.feed(BT4G_TB_SIZE)
        assert len(cap) == 1
        assert cap[0]["size"] == "1.5TB"

    def test_kb_size(self):
        inst, cap = _load_bt4g()
        parser = inst.HTMLParser(inst.url)
        parser.feed(BT4G_KB_SIZE)
        assert len(cap) == 1
        assert cap[0]["size"] == "128KB"

    def test_mb_size(self):
        inst, cap = _load_bt4g()
        parser = inst.HTMLParser(inst.url)
        parser.feed(BT4G_MB_SIZE)
        assert len(cap) == 1
        assert cap[0]["size"] == "750.5MB"

    def test_comma_in_size(self):
        inst, cap = _load_bt4g()
        parser = inst.HTMLParser(inst.url)
        parser.feed(BT4G_COMMA_SIZE)
        assert len(cap) == 1
        assert cap[0]["size"] == "1,024.5GB"

    def test_special_characters_in_name(self):
        inst, cap = _load_bt4g()
        parser = inst.HTMLParser(inst.url)
        parser.feed(BT4G_SPECIAL_CHARS)
        assert len(cap) == 1
        assert cap[0]["name"] == "C++ &amp; Python Guide"

    def test_pub_date_is_unix_timestamp(self):
        inst, cap = _load_bt4g()
        parser = inst.HTMLParser(inst.url)
        parser.feed(BT4G_SINGLE)
        expected_ts = int(datetime.strptime("2025-03-15", "%Y-%m-%d").timestamp())
        assert cap[0]["pub_date"] == expected_ts

    def test_link_is_url_encoded(self):
        inst, cap = _load_bt4g()
        parser = inst.HTMLParser(inst.url)
        parser.feed(BT4G_SINGLE)
        from urllib.parse import unquote

        decoded = unquote(cap[0]["link"])
        assert decoded == "https://bt4gprx.com/torrent/12345"

    def test_feed_after_whitespace_collapsed(self):
        inst, cap = _load_bt4g()
        parser = inst.HTMLParser(inst.url)
        messy = '<div  class="list-group-item result-item">  <a title="W" href="/t/1" >D</a> Creation Time: 2025-01-01<br>Total Size:>1GB<br> <span class="seeders">1</span><span class="leechers">0</span> </div>'
        parser.feed(_collapse(messy))
        assert len(cap) == 1
        assert cap[0]["name"] == "W"

    def test_multiple_divs_in_single_line(self):
        inst, cap = _load_bt4g()
        parser = inst.HTMLParser(inst.url)
        html = BT4G_SINGLE + "  " + BT4G_TB_SIZE
        parser.feed(html)
        assert len(cap) == 2


# ─── search tests ───────────────────────────────────────────────────────────

class TestSearch:
    def setup_method(self):
        self.inst, self.cap = _load_bt4g()

    def test_search_all_category_url(self):
        with patch("bt4g.retrieve_url", return_value=BT4G_EMPTY) as mock:
            self.inst.search("python", "all")
            called_url = mock.call_args[0][0]
            assert called_url == "https://bt4gprx.com/search?q=python&p=1"

    def test_search_movies_category_url(self):
        with patch("bt4g.retrieve_url", return_value=BT4G_EMPTY) as mock:
            self.inst.search("matrix", "movies")
            called_url = mock.call_args[0][0]
            assert called_url == "https://bt4gprx.com/search?q=matrix&category=movie&p=1"

    def test_search_music_category_url(self):
        with patch("bt4g.retrieve_url", return_value=BT4G_EMPTY) as mock:
            self.inst.search("album", "music")
            called_url = mock.call_args[0][0]
            assert called_url == "https://bt4gprx.com/search?q=album&category=audio&p=1"

    def test_search_books_category_url(self):
        with patch("bt4g.retrieve_url", return_value=BT4G_EMPTY) as mock:
            self.inst.search("python cookbook", "books")
            called_url = mock.call_args[0][0]
            assert called_url == "https://bt4gprx.com/search?q=python cookbook&category=doc&p=1"

    def test_search_software_category_url(self):
        with patch("bt4g.retrieve_url", return_value=BT4G_EMPTY) as mock:
            self.inst.search("vscode", "software")
            called_url = mock.call_args[0][0]
            assert called_url == "https://bt4gprx.com/search?q=vscode&category=app&p=1"

    def test_search_results_emitted(self):
        with patch("bt4g.retrieve_url", side_effect=[BT4G_SINGLE, BT4G_EMPTY]):
            self.inst.search("ubuntu")
            assert len(self.cap) == 1
            assert self.cap[0]["name"] == "Ubuntu 22.04 LTS"

    def test_search_pagination_stops_on_empty(self):
        call_count = 0

        def fake_retrieve(url):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return BT4G_SINGLE
            return BT4G_EMPTY

        with patch("bt4g.retrieve_url", side_effect=fake_retrieve):
            self.inst.search("test")
            assert len(self.cap) == 1
            assert call_count == 2

    def test_search_pagination_fetches_multiple_pages(self):
        call_count = 0

        def fake_retrieve(url):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return BT4G_SINGLE
            return BT4G_EMPTY

        with patch("bt4g.retrieve_url", side_effect=fake_retrieve):
            self.inst.search("test")
            assert len(self.cap) == 2
            assert call_count == 3

    def test_search_whitespace_in_html_stripped(self):
        with patch("bt4g.retrieve_url", return_value="  <div>  no match  </div>  "):
            self.inst.search("noise")
            assert len(self.cap) == 0

    def test_search_html_whitespace_normalized(self):
        with patch("bt4g.retrieve_url", side_effect=[_collapse(BT4G_SINGLE), BT4G_EMPTY]):
            self.inst.search("query")
            assert len(self.cap) == 1

    def test_search_special_chars_in_query(self):
        with patch("bt4g.retrieve_url", return_value=BT4G_EMPTY) as mock:
            self.inst.search("c++ & python", "all")
            called_url = mock.call_args[0][0]
            assert "c++ & python" in called_url

    def test_search_key_error_on_bad_category(self):
        with patch("bt4g.retrieve_url", return_value=BT4G_EMPTY):
            with pytest.raises(KeyError):
                self.inst.search("test", "nonexistent")

    def test_search_first_page_is_one(self):
        with patch("bt4g.retrieve_url", return_value=BT4G_EMPTY) as mock:
            self.inst.search("x")
            called_url = mock.call_args[0][0]
            assert "p=1" in called_url

    def test_search_page_increments(self):
        call_count = 0

        def fake_retrieve(url):
            nonlocal call_count
            call_count += 1
            if "p=1" in url:
                return BT4G_SINGLE
            if "p=2" in url:
                return BT4G_SINGLE
            return BT4G_EMPTY

        with patch("bt4g.retrieve_url", side_effect=fake_retrieve) as mock:
            self.inst.search("test")
            urls = [c[0][0] for c in mock.call_args_list]
            assert "p=1" in urls[0]
            assert "p=2" in urls[1]
            assert "p=3" in urls[2]


# ─── download_torrent tests ────────────────────────────────────────────────

class TestDownloadTorrent:
    def setup_method(self):
        self.inst, self.cap = _load_bt4g()

    def test_download_magnet_found(self, capsys):
        magnet_html = '<a href="magnet:?xt=urn:btih:abc123def456&dn=ubuntu">Download</a>'
        with patch("bt4g.retrieve_url", return_value=magnet_html):
            self.inst.download_torrent("https://bt4gprx.com/torrent/12345")
            out = capsys.readouterr().out
            assert "magnet:?xt=urn:btih:abc123def456&dn=ubuntu" in out
            assert "https://bt4gprx.com/torrent/12345" in out

    def test_download_no_magnet_silent(self, capsys):
        with patch("bt4g.retrieve_url", return_value="<html>no magnet</html>"):
            self.inst.download_torrent("https://bt4gprx.com/torrent/12345")
            out = capsys.readouterr().out
            assert out.strip() == ""

    def test_download_retrieve_url_called_with_decoded_info(self):
        from urllib.parse import quote

        encoded = quote("https://bt4gprx.com/torrent/12345")
        with patch("bt4g.retrieve_url", return_value="<html>no magnet</html>") as mock:
            self.inst.download_torrent(encoded)
            mock.assert_called_once_with("https://bt4gprx.com/torrent/12345")

    def test_download_magnet_with_special_chars(self, capsys):
        magnet_html = 'href="magnet:?xt=urn:btih:aaa111&dn=hello+world&tr=udp://tracker.example.com:6969/announce"'
        with patch("bt4g.retrieve_url", return_value=magnet_html):
            self.inst.download_torrent("https://bt4gprx.com/torrent/99999")
            out = capsys.readouterr().out
            assert "magnet:?xt=urn:btih:aaa111" in out
            assert "tracker.example.com" in out

    def test_download_magnet_in_large_html(self, capsys):
        html = "<html>" + "<p>noise</p>" * 100
        html += '<a href="magnet:?xt=urn:btih:bbb222&dn=test">Get</a>'
        html += "<p>more noise</p>" * 100 + "</html>"
        with patch("bt4g.retrieve_url", return_value=html):
            self.inst.download_torrent("https://bt4gprx.com/torrent/55555")
            out = capsys.readouterr().out
            assert "magnet:?xt=urn:btih:bbb222" in out

    def test_download_magnet_with_quotes_around_href(self, capsys):
        magnet_html = """<a href="magnet:?xt=urn:btih:deadbeef&dn=file">DL</a>"""
        with patch("bt4g.retrieve_url", return_value=magnet_html):
            self.inst.download_torrent("https://bt4gprx.com/torrent/42")
            out = capsys.readouterr().out
            assert "magnet:?xt=urn:btih:deadbeef" in out


# ─── Category mapping tests ────────────────────────────────────────────────

class TestCategoryMapping:
    def setup_method(self):
        self.inst, _ = _load_bt4g()

    def test_all_maps_to_empty(self):
        assert self.inst.supported_categories["all"] == ""

    def test_movies_maps_to_movie(self):
        assert self.inst.supported_categories["movies"] == "movie"

    def test_music_maps_to_audio(self):
        assert self.inst.supported_categories["music"] == "audio"

    def test_books_maps_to_doc(self):
        assert self.inst.supported_categories["books"] == "doc"

    def test_software_maps_to_app(self):
        assert self.inst.supported_categories["software"] == "app"

    def test_all_categories_present(self):
        expected_keys = {"all", "movies", "music", "books", "software"}
        assert set(self.inst.supported_categories.keys()) == expected_keys


# ─── Class attribute tests ─────────────────────────────────────────────────

class TestClassAttributes:
    def setup_method(self):
        self.inst, _ = _load_bt4g()

    def test_url(self):
        assert self.inst.url == "https://bt4gprx.com/"

    def test_name(self):
        assert self.inst.name == "BT4G"

    def test_html_parser_url_propagation(self):
        parser = self.inst.HTMLParser(self.inst.url)
        assert parser.url == "https://bt4gprx.com/"

    def test_no_torrents_default_false(self):
        parser = self.inst.HTMLParser(self.inst.url)
        assert parser.noTorrents is False
