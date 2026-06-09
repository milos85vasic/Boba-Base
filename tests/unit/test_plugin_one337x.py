"""Deep coverage tests for plugins/community/one337x.py.

Covers: HTMLParser.feed (single/multi/empty/malformed), _parse_size (all units,
edge cases), search (URL construction, category mapping, exception handling),
download_torrent (magnet link, torrent file, no links, URLError).
"""

import importlib.util
import os
import sys
import types
from unittest.mock import patch

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PLUGINS_DIR = os.path.join(REPO, "plugins", "community")


def _load_one337x(captured=None):
    """Import one337x plugin with stub modules. Returns (instance, captured)."""
    if captured is None:
        captured = []
    np_mod = types.ModuleType("novaprinter")
    np_mod.prettyPrinter = lambda d: captured.append(dict(d))
    sys.modules["novaprinter"] = np_mod

    helpers_mod = types.ModuleType("helpers")
    helpers_mod.retrieve_url = lambda url: ""
    sys.modules["helpers"] = helpers_mod

    sys.modules.pop("one337x", None)

    path = os.path.join(PLUGINS_DIR, "one337x.py")
    spec = importlib.util.spec_from_file_location("one337x", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules["one337x"] = mod
    cls = getattr(mod, "one337x", None)
    if cls is not None and isinstance(cls, type):
        return cls(), captured
    return mod, captured


# ─── HTML fixtures ──────────────────────────────────────────────────────────

SINGLE_ROW = '''<table>
<tr>
<td class="coll-1"><a href="/category1/">All</a></td>
<td><a href="/torrent/12345/my-movie-2024/">My Movie 2024</a></td>
<td class="coll-2 seeds">150</td>
<td class="coll-3 leeches">25</td>
<td class="coll-4 size mob-uploader">2.5 GB</td>
<td class="coll-date date added">Jun. 5th, 2024</td>
</tr>
</table>'''

MULTI_ROWS = '''<table>
<tr>
<td class="coll-1"><a href="/category1/">All</a></td>
<td><a href="/torrent/11111/ubuntu-24-04/">Ubuntu 24.04</a></td>
<td class="coll-2 seeds">500</td>
<td class="coll-3 leeches">10</td>
<td class="coll-4 size mob-uploader">4.2 GB</td>
<td class="coll-date date added">May 1st, 2024</td>
</tr>
<tr>
<td class="coll-1"><a href="/category1/">All</a></td>
<td><a href="/torrent/22222/ubuntu-server/">Ubuntu Server</a></td>
<td class="coll-2 seeds">300</td>
<td class="coll-3 leeches">5</td>
<td class="coll-4 size mob-uploader">890 MB</td>
<td class="coll-date date added">Apr. 10th, 2024</td>
</tr>
</table>'''

EMPTY_HTML = '<html><body><p>No results found.</p></body></html>'

MALFORMED_ROW = '''<table>
<tr>
<td class="coll-1"><a href="/category1/">All</a></td>
<td>no link here</td>
</tr>
</table>'''

SMALL_SIZE_ROW = '''<table>
<tr>
<td class="coll-1"><a href="/category1/">All</a></td>
<td><a href="/torrent/33333/small-file/">Small File</a></td>
<td class="coll-2 seeds">5</td>
<td class="coll-3 leeches">1</td>
<td class="coll-4 size mob-uploader">512 KB</td>
<td class="coll-date date added">Jan. 1st, 2024</td>
</tr>
</table>'''

BYTE_SIZE_ROW = '''<table>
<tr>
<td class="coll-1"><a href="/category1/">All</a></td>
<td><a href="/torrent/44444/tiny/">Tiny File</a></td>
<td class="coll-2 seeds">1</td>
<td class="coll-3 leeches">0</td>
<td class="coll-4 size mob-uploader">100 B</td>
<td class="coll-date date added">Jan. 1st, 2024</td>
</tr>
</table>'''

TB_SIZE_ROW = '''<table>
<tr>
<td class="coll-1"><a href="/category1/">All</a></td>
<td><a href="/torrent/55555/huge/">Huge File</a></td>
<td class="coll-2 seeds">20</td>
<td class="coll-3 leeches">3</td>
<td class="coll-4 size mob-uploader">1.5 TB</td>
<td class="coll-date date added">Jan. 1st, 2024</td>
</tr>
</table>'''

MB_SIZE_ROW = '''<table>
<tr>
<td class="coll-1"><a href="/category1/">All</a></td>
<td><a href="/torrent/66666/medium/">Medium File</a></td>
<td class="coll-2 seeds">75</td>
<td class="coll-3 leeches">12</td>
<td class="coll-4 size mob-uploader">750.5 MB</td>
<td class="coll-date date added">Jan. 1st, 2024</td>
</tr>
</table>'''

GARBAGE_SIZE_ROW = '''<table>
<tr>
<td class="coll-1"><a href="/category1/">All</a></td>
<td><a href="/torrent/77777/garbage/">Garbage Size</a></td>
<td class="coll-2 seeds">10</td>
<td class="coll-3 leeches">2</td>
<td class="coll-4 size mob-uploader">unknown</td>
<td class="coll-date date added">Jan. 1st, 2024</td>
</tr>
</table>'''

MAGNET_DETAIL = '<a href="magnet:?xt=urn:btih:abc123def456&dn=My+Movie">Download</a>'

TORRENT_DETAIL = '<a href="/download/12345/my-movie.torrent">Download</a>'

NO_LINK_DETAIL = '<html><body><p>No download available</p></body></html>'

MAGNET_AND_TORRENT_DETAIL = '''<a href="magnet:?xt=urn:btih:aaa111&dn=Both">Magnet</a>
<a href="/download/99999/both.torrent">Torrent</a>'''


# ─── Parser tests ───────────────────────────────────────────────────────────

class TestHTMLParserFeed:
    def test_single_result(self):
        inst, cap = _load_one337x()
        parser = inst.HTMLParser("https://1337x.to")
        parser.feed(SINGLE_ROW)
        assert len(cap) == 1
        assert cap[0]["name"] == "My Movie 2024"
        assert cap[0]["link"] == "https://1337x.to/torrent/12345/my-movie-2024/"
        assert cap[0]["desc_link"] == cap[0]["link"]
        assert cap[0]["engine_url"] == "https://1337x.to"
        assert cap[0]["seeds"] == "150"
        assert cap[0]["leech"] == "25"

    def test_multi_results(self):
        inst, cap = _load_one337x()
        parser = inst.HTMLParser("https://1337x.to")
        parser.feed(MULTI_ROWS)
        assert len(cap) == 2
        assert cap[0]["name"] == "Ubuntu 24.04"
        assert cap[1]["name"] == "Ubuntu Server"
        assert cap[0]["seeds"] == "500"
        assert cap[1]["seeds"] == "300"

    def test_empty_html(self):
        inst, cap = _load_one337x()
        parser = inst.HTMLParser("https://1337x.to")
        parser.feed(EMPTY_HTML)
        assert len(cap) == 0

    def test_malformed_row_skipped(self):
        inst, cap = _load_one337x()
        parser = inst.HTMLParser("https://1337x.to")
        parser.feed(MALFORMED_ROW)
        assert len(cap) == 0

    def test_size_parsed_to_bytes_b_unit_only(self):
        inst, cap = _load_one337x()
        parser = inst.HTMLParser("https://1337x.to")
        parser.feed(BYTE_SIZE_ROW)
        assert cap[0]["size"] == str(100)

    def test_size_parsed_correctly(self):
        inst, cap = _load_one337x()
        parser = inst.HTMLParser("https://1337x.to")
        parser.feed(SINGLE_ROW)
        assert cap[0]["size"] == str(int(2.5 * 1024**3))


class TestParseSize:
    def setup_method(self):
        self.inst, _ = _load_one337x()
        self.parser = self.inst.HTMLParser("https://1337x.to")

    def test_bytes(self):
        assert self.parser._parse_size("1024 B") == 1024

    def test_kilobytes(self):
        assert self.parser._parse_size("512 KB") == 512 * 1024

    def test_megabytes(self):
        assert self.parser._parse_size("750.5 MB") == int(750.5 * 1024**2)

    def test_gigabytes(self):
        assert self.parser._parse_size("35.2 GB") == int(35.2 * 1024**3)

    def test_terabytes(self):
        assert self.parser._parse_size("1.5 TB") == int(1.5 * 1024**4)

    def test_garbage_returns_zero(self):
        assert self.parser._parse_size("unknown") == 0

    def test_empty_string_returns_zero(self):
        assert self.parser._parse_size("") == 0

    def test_whitespace_and_case_b_only(self):
        assert self.parser._parse_size("  1024 B  ") == 1024

    def test_no_unit_returns_zero(self):
        assert self.parser._parse_size("12345") == 0

    def test_comma_in_mb(self):
        assert self.parser._parse_size("1,024 MB") == 1024 * 1024**2

    def test_unparseable_number_returns_zero(self):
        assert self.parser._parse_size("abc GB") == 0

    def test_kb_exact(self):
        result = self.parser._parse_size("10 KB")
        assert result == 10 * 1024

    def test_bare_number_no_suffix(self):
        assert self.parser._parse_size("9999") == 0


# ─── Search tests ───────────────────────────────────────────────────────────

class TestSearch:
    def setup_method(self):
        self.inst, self.cap = _load_one337x()

    @patch("one337x.retrieve_url", return_value=SINGLE_ROW)
    def test_search_all_category(self, mock_retrieve):
        self.inst.search("ubuntu", "all")
        called_url = mock_retrieve.call_args[0][0]
        assert called_url == "https://1337x.to/search/ubuntu/1/"

    @patch("one337x.retrieve_url", return_value=SINGLE_ROW)
    def test_search_movies_category(self, mock_retrieve):
        self.inst.search("my movie", "movies")
        called_url = mock_retrieve.call_args[0][0]
        assert called_url == "https://1337x.to/category-search/my-movie/Movies/1/"

    @patch("one337x.retrieve_url", return_value=SINGLE_ROW)
    def test_search_tv_category(self, mock_retrieve):
        self.inst.search("breaking bad", "tv")
        called_url = mock_retrieve.call_args[0][0]
        assert called_url == "https://1337x.to/category-search/breaking-bad/TV/1/"

    @patch("one337x.retrieve_url", return_value=SINGLE_ROW)
    def test_search_music_category(self, mock_retrieve):
        self.inst.search("pink floyd", "music")
        called_url = mock_retrieve.call_args[0][0]
        assert called_url == "https://1337x.to/category-search/pink-floyd/Music/1/"

    @patch("one337x.retrieve_url", return_value=SINGLE_ROW)
    def test_search_games_category(self, mock_retrieve):
        self.inst.search("cyberpunk", "games")
        called_url = mock_retrieve.call_args[0][0]
        assert called_url == "https://1337x.to/category-search/cyberpunk/Games/1/"

    @patch("one337x.retrieve_url", return_value=SINGLE_ROW)
    def test_search_anime_category(self, mock_retrieve):
        self.inst.search("naruto", "anime")
        called_url = mock_retrieve.call_args[0][0]
        assert called_url == "https://1337x.to/category-search/naruto/Anime/1/"

    @patch("one337x.retrieve_url", return_value=SINGLE_ROW)
    def test_search_software_category(self, mock_retrieve):
        self.inst.search("photoshop", "software")
        called_url = mock_retrieve.call_args[0][0]
        assert called_url == "https://1337x.to/category-search/photoshop/Apps/1/"

    @patch("one337x.retrieve_url", return_value=SINGLE_ROW)
    def test_search_books_category(self, mock_retrieve):
        self.inst.search("linux bible", "books")
        called_url = mock_retrieve.call_args[0][0]
        assert called_url == "https://1337x.to/category-search/linux-bible/Documentaries/1/"

    @patch("one337x.retrieve_url", return_value=SINGLE_ROW)
    def test_search_unknown_category_falls_back_to_all(self, mock_retrieve):
        self.inst.search("ubuntu", "nonexistent")
        called_url = mock_retrieve.call_args[0][0]
        assert called_url == "https://1337x.to/search/ubuntu/1/"

    @patch("one337x.retrieve_url", return_value=SINGLE_ROW)
    def test_search_results_emitted(self, mock_retrieve):
        self.inst.search("ubuntu", "all")
        assert len(self.cap) == 1
        assert self.cap[0]["name"] == "My Movie 2024"

    @patch("one337x.retrieve_url", side_effect=Exception("network error"))
    def test_search_exception_does_not_crash(self, mock_retrieve):
        self.inst.search("ubuntu", "all")
        assert len(self.cap) == 0

    @patch("one337x.retrieve_url", return_value=EMPTY_HTML)
    def test_search_empty_results(self, mock_retrieve):
        self.inst.search("nonexistent12345", "all")
        assert len(self.cap) == 0

    @patch("one337x.retrieve_url", return_value=SINGLE_ROW)
    def test_search_url_encodes_spaces(self, mock_retrieve):
        self.inst.search("hello world test", "all")
        called_url = mock_retrieve.call_args[0][0]
        assert "hello-world-test" in called_url

    @patch("one337x.retrieve_url", return_value=SINGLE_ROW)
    def test_search_url_lowercases(self, mock_retrieve):
        self.inst.search("Ubuntu", "all")
        called_url = mock_retrieve.call_args[0][0]
        assert "ubuntu" in called_url
        assert "Ubuntu" not in called_url.split("/search/")[1]

    @patch("one337x.retrieve_url", return_value=SINGLE_ROW)
    def test_search_decodes_percent_encoded_input(self, mock_retrieve):
        self.inst.search("hello%20world", "all")
        called_url = mock_retrieve.call_args[0][0]
        assert "hello-world" in called_url

    @patch("one337x.retrieve_url", return_value=MULTI_ROWS)
    def test_search_multi_results_emitted(self, mock_retrieve):
        self.inst.search("ubuntu", "all")
        assert len(self.cap) == 2
        assert self.cap[0]["name"] == "Ubuntu 24.04"
        assert self.cap[1]["name"] == "Ubuntu Server"


# ─── download_torrent tests ────────────────────────────────────────────────

class TestDownloadTorrent:
    def setup_method(self):
        self.inst, self.cap = _load_one337x()

    @patch("one337x.retrieve_url")
    def test_download_magnet_link(self, mock_retrieve, capsys):
        mock_retrieve.return_value = MAGNET_DETAIL
        self.inst.download_torrent("https://1337x.to/torrent/12345/my-movie/")
        out = capsys.readouterr().out
        assert "magnet:?xt=urn:btih:abc123def456&dn=My+Movie" in out
        assert "https://1337x.to/torrent/12345/my-movie/" in out

    @patch("one337x.retrieve_url")
    def test_download_torrent_file(self, mock_retrieve, capsys):
        mock_retrieve.return_value = TORRENT_DETAIL
        self.inst.download_torrent("https://1337x.to/torrent/12345/my-movie/")
        out = capsys.readouterr().out
        assert "https://1337x.to/download/12345/my-movie.torrent" in out
        assert "https://1337x.to/torrent/12345/my-movie/" in out

    @patch("one337x.retrieve_url")
    def test_download_no_links_outputs_nothing(self, mock_retrieve, capsys):
        mock_retrieve.return_value = NO_LINK_DETAIL
        self.inst.download_torrent("https://1337x.to/torrent/12345/empty/")
        out = capsys.readouterr().out
        assert out.strip() == ""

    @patch("one337x.retrieve_url", side_effect=Exception("network error"))
    def test_download_exception_exits(self, mock_retrieve):
        with pytest.raises(SystemExit):
            self.inst.download_torrent("https://1337x.to/torrent/12345/fail/")

    @patch("one337x.retrieve_url")
    def test_download_prefers_magnet_over_torrent(self, mock_retrieve, capsys):
        mock_retrieve.return_value = MAGNET_AND_TORRENT_DETAIL
        self.inst.download_torrent("https://1337x.to/torrent/99999/both/")
        out = capsys.readouterr().out
        assert "magnet:?xt=urn:btih:aaa111&dn=Both" in out
        assert "/download/99999/both.torrent" not in out

    @patch("one337x.retrieve_url", side_effect=Exception("timeout"))
    def test_download_url_error_exits(self, mock_retrieve):
        with pytest.raises(SystemExit):
            self.inst.download_torrent("https://1337x.to/torrent/00000/timeout/")

    @patch("one337x.retrieve_url", return_value="<html></html>")
    def test_download_empty_page(self, mock_retrieve, capsys):
        self.inst.download_torrent("https://1337x.to/torrent/00000/empty/")
        out = capsys.readouterr().out
        assert out.strip() == ""


# ─── Category mapping tests ────────────────────────────────────────────────

class TestCategoryMapping:
    def setup_method(self):
        self.inst, _ = _load_one337x()

    def test_all_maps_to_all(self):
        assert self.inst.supported_categories["all"] == "All"

    def test_movies_maps_to_movies(self):
        assert self.inst.supported_categories["movies"] == "Movies"

    def test_tv_maps_to_tv(self):
        assert self.inst.supported_categories["tv"] == "TV"

    def test_music_maps_to_music(self):
        assert self.inst.supported_categories["music"] == "Music"

    def test_games_maps_to_games(self):
        assert self.inst.supported_categories["games"] == "Games"

    def test_anime_maps_to_anime(self):
        assert self.inst.supported_categories["anime"] == "Anime"

    def test_software_maps_to_apps(self):
        assert self.inst.supported_categories["software"] == "Apps"

    def test_books_maps_to_documentaries(self):
        assert self.inst.supported_categories["books"] == "Documentaries"

    def test_all_categories_present(self):
        expected = {"all", "movies", "tv", "music", "games", "anime", "software", "books"}
        assert set(self.inst.supported_categories.keys()) == expected


# ─── Plugin metadata tests ─────────────────────────────────────────────────

class TestPluginMetadata:
    def setup_method(self):
        self.inst, _ = _load_one337x()

    def test_url(self):
        assert self.inst.url == "https://1337x.to"

    def test_name(self):
        assert self.inst.name == "1337x"
