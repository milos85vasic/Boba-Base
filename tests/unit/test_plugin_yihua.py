"""Deep coverage tests for plugins/community/yihua.py.

Covers: _parse_results (div cards, single/multi, malformed), _parse_size
(all units, edge cases — includes known "B"-substring bug for KB/MB/GB/TB),
search (URL construction, category mapping), download_torrent (magnet link,
.torrent, URLError, no links).
"""

import importlib.util
import os
import sys
import types
from unittest.mock import patch

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PLUGINS_DIR = os.path.join(REPO, "plugins", "community")


def _load_yihua(captured=None):
    """Import yihua plugin with stub modules. Returns (instance, captured)."""
    if captured is None:
        captured = []
    np_mod = types.ModuleType("novaprinter")
    np_mod.prettyPrinter = lambda d: captured.append(dict(d))
    sys.modules["novaprinter"] = np_mod

    helpers_mod = types.ModuleType("helpers")
    helpers_mod.retrieve_url = lambda url: ""
    sys.modules["helpers"] = helpers_mod

    sys.modules.pop("yihua", None)

    path = os.path.join(PLUGINS_DIR, "yihua.py")
    spec = importlib.util.spec_from_file_location("yihua", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules["yihua"] = mod
    cls = getattr(mod, "yihua", None)
    if cls is not None and isinstance(cls, type):
        return cls(), captured
    return mod, captured


YH_SINGLE = '''<div class="torrent-item">
<a href="/details/1234">Test Movie 2025</a>
<span class="size">3758096384 B</span>
<span class="seed">42</span>
<span class="leech">7</span>
</div>'''

YH_MULTI = '''<div class="torrent-item">
<a href="/details/111">Alpha Movie</a>
<span class="size">1073741824 B</span>
<span class="seed">10</span>
<span class="leech">2</span>
</div>
<div class="torrent-item">
<a href="/details/222">Beta Movie</a>
<span class="size">524288000 B</span>
<span class="seed">55</span>
<span class="leech">12</span>
</div>'''

YH_EMPTY = '<html><body><p>No results found.</p></body></html>'

YH_MALFORMED = '''<div class="torrent-item">
<a href="/details/broken">Broken</a>
</div>'''

YH_SEED_ZERO = '''<div class="torrent-item">
<a href="/details/seedless">Seedless Movie</a>
<span class="size">1024 B</span>
<span class="seed">unknown</span>
<span class="leech">3</span>
</div>'''

YH_LEECH_ZERO = '''<div class="torrent-item">
<a href="/details/leechless">Leechless Movie</a>
<span class="size">2048 B</span>
<span class="seed">15</span>
<span class="leech">N/A</span>
</div>'''

YH_CLASS_VARIANT = '''<div class="panel torrent-item-v2">
<a href="/details/variant">Variant Class</a>
<span class="label size-info">4096 B</span>
<span class="label seed-info">8</span>
<span class="label leech-info">1</span>
</div>'''

YH_GB_SIZE_BUG = '''<div class="torrent-item">
<a href="/details/big">Big File</a>
<span class="size">3.5 GB</span>
<span class="seed">20</span>
<span class="leech">5</span>
</div>'''

YH_MB_SIZE_BUG = '''<div class="torrent-item">
<a href="/details/med">Medium File</a>
<span class="size">500 MB</span>
<span class="seed">30</span>
<span class="leech">10</span>
</div>'''

YH_GARBAGE_SIZE = '''<div class="torrent-item">
<a href="/details/garbage">Garbage Size</a>
<span class="size">unknown</span>
<span class="seed">5</span>
<span class="leech">1</span>
</div>'''


class TestParseResults:
    def test_single_result(self):
        mod, cap = _load_yihua()
        mod._parse_results(YH_SINGLE)
        assert len(cap) == 1
        assert cap[0]["name"] == "Test Movie 2025"
        assert cap[0]["link"] == "https://www.yihua.biz/details/1234"
        assert cap[0]["desc_link"] == cap[0]["link"]
        assert cap[0]["engine_url"] == "https://www.yihua.biz"
        assert cap[0]["seeds"] == "42"
        assert cap[0]["leech"] == "7"
        assert cap[0]["size"] == "3758096384"
        assert "pub_date" in cap[0]
        assert int(cap[0]["pub_date"]) > 0

    def test_multi_results(self):
        mod, cap = _load_yihua()
        mod._parse_results(YH_MULTI)
        assert len(cap) == 2
        assert cap[0]["name"] == "Alpha Movie"
        assert cap[0]["size"] == "1073741824"
        assert cap[1]["name"] == "Beta Movie"
        assert cap[1]["size"] == "524288000"

    def test_empty_html(self):
        mod, cap = _load_yihua()
        mod._parse_results(YH_EMPTY)
        assert len(cap) == 0

    def test_malformed_div_skipped(self):
        mod, cap = _load_yihua()
        mod._parse_results(YH_MALFORMED)
        assert len(cap) == 0

    def test_non_digit_seeds_defaults_to_zero(self):
        mod, cap = _load_yihua()
        mod._parse_results(YH_SEED_ZERO)
        assert len(cap) == 1
        assert cap[0]["seeds"] == "0"
        assert cap[0]["leech"] == "3"
        assert cap[0]["size"] == "1024"

    def test_non_digit_leech_defaults_to_zero(self):
        mod, cap = _load_yihua()
        mod._parse_results(YH_LEECH_ZERO)
        assert len(cap) == 1
        assert cap[0]["seeds"] == "15"
        assert cap[0]["leech"] == "0"
        assert cap[0]["size"] == "2048"

    def test_class_variant_matches(self):
        mod, cap = _load_yihua()
        mod._parse_results(YH_CLASS_VARIANT)
        assert len(cap) == 1
        assert cap[0]["name"] == "Variant Class"
        assert cap[0]["size"] == "4096"

    def test_garbage_size_results_in_zero(self):
        mod, cap = _load_yihua()
        mod._parse_results(YH_GARBAGE_SIZE)
        assert len(cap) == 1
        assert cap[0]["name"] == "Garbage Size"
        assert cap[0]["size"] == "0"

    def test_size_parsing_gb(self):
        mod, cap = _load_yihua()
        mod._parse_results(YH_GB_SIZE_BUG)
        assert len(cap) == 1
        assert cap[0]["size"] == str(int(3.5 * 1024**3))

    def test_mb_size(self):
        mod, cap = _load_yihua()
        mod._parse_results(YH_MB_SIZE_BUG)
        assert len(cap) == 1
        assert cap[0]["size"] == str(int(500 * 1024**2))

    def test_pub_date_is_fresh_timestamp(self):
        mod, cap = _load_yihua()
        mod._parse_results(YH_SINGLE)
        import time
        now = int(time.time())
        pub = int(cap[0]["pub_date"])
        assert abs(now - pub) <= 5


class TestParseSize:
    def setup_method(self):
        self.mod, _ = _load_yihua()

    def test_bytes(self):
        assert self.mod._parse_size("1024 B") == 1024

    def test_kilobytes_zero_due_to_b_substring(self):
        assert self.mod._parse_size("512 KB") == 512 * 1024

    def test_megabytes(self):
        assert self.mod._parse_size("100 MB") == int(100 * 1024**2)

    def test_gigabytes(self):
        assert self.mod._parse_size("3.5 GB") == int(3.5 * 1024**3)

    def test_terabytes_zero_due_to_b_substring(self):
        assert self.mod._parse_size("1.5 TB") == int(1.5 * 1024**4)

    def test_garbage_returns_zero(self):
        assert self.mod._parse_size("unknown") == 0

    def test_empty_string(self):
        assert self.mod._parse_size("") == 0

    def test_no_unit_returns_zero(self):
        assert self.mod._parse_size("42") == 0

    def test_lowercase_b(self):
        assert self.mod._parse_size("  500 b  ") == 500

    def test_comma_in_bytes(self):
        assert self.mod._parse_size("1,024 B") == 1024


class TestSearch:
    def setup_method(self):
        self.mod, self.cap = _load_yihua()

    @patch("yihua.retrieve_url", return_value=YH_SINGLE)
    def test_search_all_category(self, mock_retrieve):
        self.mod.search("witcher", "all")
        called_url = mock_retrieve.call_args[0][0]
        assert called_url == "https://www.yihua.biz/search/?keyword=witcher&category=0"

    @patch("yihua.retrieve_url", return_value=YH_SINGLE)
    def test_search_movies_category(self, mock_retrieve):
        self.mod.search("avatar", "movies")
        called_url = mock_retrieve.call_args[0][0]
        assert called_url == "https://www.yihua.biz/search/?keyword=avatar&category=1"

    @patch("yihua.retrieve_url", return_value=YH_SINGLE)
    def test_search_tv_category(self, mock_retrieve):
        self.mod.search("show", "tv")
        called_url = mock_retrieve.call_args[0][0]
        assert called_url == "https://www.yihua.biz/search/?keyword=show&category=2"

    @patch("yihua.retrieve_url", return_value=YH_SINGLE)
    def test_search_music_category(self, mock_retrieve):
        self.mod.search("album", "music")
        called_url = mock_retrieve.call_args[0][0]
        assert called_url == "https://www.yihua.biz/search/?keyword=album&category=3"

    @patch("yihua.retrieve_url", return_value=YH_SINGLE)
    def test_search_games_category(self, mock_retrieve):
        self.mod.search("zelda", "games")
        called_url = mock_retrieve.call_args[0][0]
        assert called_url == "https://www.yihua.biz/search/?keyword=zelda&category=4"

    @patch("yihua.retrieve_url", return_value=YH_SINGLE)
    def test_search_software_category(self, mock_retrieve):
        self.mod.search("office", "software")
        called_url = mock_retrieve.call_args[0][0]
        assert called_url == "https://www.yihua.biz/search/?keyword=office&category=5"

    @patch("yihua.retrieve_url", return_value=YH_SINGLE)
    def test_search_anime_category(self, mock_retrieve):
        self.mod.search("naruto", "anime")
        called_url = mock_retrieve.call_args[0][0]
        assert called_url == "https://www.yihua.biz/search/?keyword=naruto&category=6"

    @patch("yihua.retrieve_url", return_value=YH_SINGLE)
    def test_search_books_category(self, mock_retrieve):
        self.mod.search("python", "books")
        called_url = mock_retrieve.call_args[0][0]
        assert called_url == "https://www.yihua.biz/search/?keyword=python&category=7"

    @patch("yihua.retrieve_url", return_value=YH_SINGLE)
    def test_search_unknown_category_falls_back_to_all(self, mock_retrieve):
        self.mod.search("witcher", "nonexistent")
        called_url = mock_retrieve.call_args[0][0]
        assert called_url == "https://www.yihua.biz/search/?keyword=witcher&category=0"

    @patch("yihua.retrieve_url", return_value=YH_SINGLE)
    def test_search_results_emitted(self, mock_retrieve):
        self.mod.search("movie", "all")
        assert len(self.cap) == 1
        assert self.cap[0]["name"] == "Test Movie 2025"

    @patch("yihua.retrieve_url", side_effect=Exception("network error"))
    def test_search_exception_does_not_crash(self, mock_retrieve):
        self.mod.search("witcher", "all")
        assert len(self.cap) == 0


class TestDownloadTorrent:
    def setup_method(self):
        self.mod, self.cap = _load_yihua()

    @patch("yihua.retrieve_url")
    def test_download_magnet_link(self, mock_retrieve, capsys):
        html = '<a href="magnet:?xt=urn:btih:abc123&dn=movie">Magnet</a>'
        mock_retrieve.return_value = html
        self.mod.download_torrent("https://example.com/details/1234")
        out = capsys.readouterr().out
        assert "magnet:?xt=urn:btih:abc123&dn=movie" in out
        assert " https://example.com/details/1234" in out

    @patch("yihua.retrieve_url")
    def test_download_torrent_file(self, mock_retrieve, capsys):
        html = '<a href="/download/1234.torrent">Download</a>'
        mock_retrieve.return_value = html
        self.mod.download_torrent("https://example.com/details/1234")
        out = capsys.readouterr().out
        assert "https://www.yihua.biz/download/1234.torrent" in out
        assert " https://example.com/details/1234" in out

    @patch("yihua.retrieve_url", side_effect=Exception("network error"))
    def test_download_exception_exits(self, mock_retrieve):
        with pytest.raises(SystemExit) as excinfo:
            self.mod.download_torrent("https://example.com/details/1234")
        assert excinfo.value.code == 1

    @patch("yihua.retrieve_url", return_value="<html>no links at all</html>")
    def test_download_no_magnet_no_torrent(self, mock_retrieve, capsys):
        self.mod.download_torrent("https://example.com/details/1234")
        out = capsys.readouterr().out
        assert out.strip() == ""

    @patch("yihua.retrieve_url")
    def test_download_magnet_over_torrent(self, mock_retrieve, capsys):
        html = '''<a href="magnet:?xt=urn:btih:magnet123">Magnet</a>
<a href="/download/file.torrent">Torrent</a>'''
        mock_retrieve.return_value = html
        self.mod.download_torrent("https://example.com/details/1234")
        out = capsys.readouterr().out
        assert "magnet:?xt=urn:btih:magnet123" in out
        assert "/download/file.torrent" not in out
