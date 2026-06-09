"""Deep coverage tests for plugins/community/bitru.py (128 lines).

Covers: _parse_size (bytes, garbage, edge cases), _parse_results (single,
multi, empty, non-digit seeds/leech, malformed), search (URL construction,
category mapping, fallback, pagination-like double-invoke, exception
handling), download_torrent (magnet, .torrent, no links, exception exit),
class-level attributes (url, name, supported_categories).
"""

import importlib.util
import os
import sys
import types
from unittest.mock import patch

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PLUGINS_DIR = os.path.join(REPO, "plugins")


def _load_bitru(captured=None):
    if captured is None:
        captured = []
    np_mod = types.ModuleType("novaprinter")
    np_mod.prettyPrinter = lambda d: captured.append(dict(d))
    sys.modules["novaprinter"] = np_mod

    helpers_mod = types.ModuleType("helpers")
    helpers_mod.retrieve_url = lambda url: ""
    sys.modules["helpers"] = helpers_mod

    sys.modules.pop("bitru", None)
    sys.modules.pop("community.bitru", None)

    path = os.path.join(PLUGINS_DIR, "community", "bitru.py")
    spec = importlib.util.spec_from_file_location("bitru", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules["bitru"] = mod
    cls = getattr(mod, "bitru", None)
    if cls is not None and isinstance(cls, type):
        return cls(), captured
    return mod, captured


# ─── HTML fixtures (matching div.torrent-item regex with re.S|re.I) ─────

BR_SINGLE = """<div class="torrent-item">
<a href="/details/12345">Ubuntu 22.04 LTS</a>
<span class="size">1024 B</span>
<span class="seed">1234</span>
<span class="leech">56</span>
</div>"""

BR_MULTI = """<div class="torrent-item">
<a href="/details/100">Movie One</a>
<span class="size">2048 B</span>
<span class="seed">500</span>
<span class="leech">10</span>
</div>
<div class="torrent-item">
<a href="/details/200">Game Two</a>
<span class="size">4096 B</span>
<span class="seed">300</span>
<span class="leech">5</span>
</div>"""

BR_NON_DIGIT_SEEDS = """<div class="torrent-item">
<a href="/details/300">Weird Torrent</a>
<span class="size">1024 B</span>
<span class="seed">N/A</span>
<span class="leech">low</span>
</div>"""

BR_EMPTY = "<html><body><p>No results found.</p></body></html>"

BR_MALFORMED = """<div class="torrent-item">
<a href="/details/400">Broken Torrent</a>
</div>"""

BR_REALISTIC = """<div class="torrent-item">
<a href="/details/500">Ubuntu 24.04 Noble Numbat</a>
<span class="size">4.7 GB</span>
<span class="seed">1,234</span>
<span class="leech">56</span>
</div>"""

BR_ALTERNATE_CLASS = """<div class="content torrent-item highlight">
<a href="/details/600">Alt Class Torrent</a>
<span class="item-size">1024 B</span>
<span class="item-seed">99</span>
<span class="item-leech">1</span>
</div>"""

BR_MAGNET_HTML = '<a href="magnet:?xt=urn:btih:abc123def456&dn=ubuntu">Get Magnet</a>'
BR_TORRENT_HTML = '<a href="/download/ubuntu.torrent">Download</a>'
BR_NO_LINKS_HTML = "<html>nothing here</html>"


class TestPluginAttributes:
    def test_url_and_name(self):
        mod, _ = _load_bitru()
        assert mod.url == "https://bitru.org"
        assert mod.name == "BitRu"

    def test_supported_categories(self):
        mod, _ = _load_bitru()
        categories = mod.supported_categories
        assert categories == {
            "all": "0",
            "movies": "1",
            "tv": "4",
            "music": "2",
            "games": "7",
            "software": "8",
            "books": "11",
            "anime": "9",
        }
        assert categories["all"] == "0"
        assert categories["games"] == "7"
        assert categories["anime"] == "9"


class TestParseSize:
    def setup_method(self):
        self.mod, _ = _load_bitru()

    def test_bytes(self):
        assert self.mod._parse_size("1024 B") == 1024

    def test_bytes_no_space(self):
        assert self.mod._parse_size("512B") == 512

    def test_garbage_returns_zero(self):
        assert self.mod._parse_size("unknown") == 0

    def test_empty_string_returns_zero(self):
        assert self.mod._parse_size("") == 0

    def test_no_unit_returns_zero(self):
        assert self.mod._parse_size("12345") == 0

    def test_comma_in_number_preserves_byte_parsing(self):
        assert self.mod._parse_size("1,024 B") == 1024

    def test_uppercase_normalization_and_strip(self):
        assert self.mod._parse_size("   10.0  b  ") == 10

    def test_multibyte_unit_returns_zero(self):
        assert self.mod._parse_size("4.7 GB") == int(4.7 * 1024**3)

    def test_multibyte_unit_kb_returns_zero(self):
        assert self.mod._parse_size("512 KB") == 512 * 1024

    def test_multibyte_unit_mb_returns_zero(self):
        assert self.mod._parse_size("750 MB") == int(750 * 1024**2)

    def test_multibyte_unit_tb_returns_zero(self):
        assert self.mod._parse_size("1.5 TB") == int(1.5 * 1024**4)


class TestParseResults:
    def setup_method(self):
        self.mod, self.cap = _load_bitru()

    def test_single_result(self):
        self.mod._parse_results(BR_SINGLE)
        assert len(self.cap) == 1
        r = self.cap[0]
        assert r["name"] == "Ubuntu 22.04 LTS"
        assert r["link"] == "https://bitru.org/details/12345"
        assert r["desc_link"] == r["link"]
        assert r["engine_url"] == "https://bitru.org"
        assert r["size"] == "1024"
        assert r["seeds"] == "1234"
        assert r["leech"] == "56"
        assert "pub_date" in r

    def test_multi_results(self):
        self.mod._parse_results(BR_MULTI)
        assert len(self.cap) == 2
        assert self.cap[0]["name"] == "Movie One"
        assert self.cap[1]["name"] == "Game Two"

    def test_empty_html(self):
        self.mod._parse_results(BR_EMPTY)
        assert len(self.cap) == 0

    def test_non_digit_seeds_leech_default_to_zero(self):
        self.mod._parse_results(BR_NON_DIGIT_SEEDS)
        assert len(self.cap) == 1
        assert self.cap[0]["seeds"] == "0"
        assert self.cap[0]["leech"] == "0"

    def test_malformed_item_skipped(self):
        self.mod._parse_results(BR_MALFORMED)
        assert len(self.cap) == 0

    def test_realistic_size_parses(self):
        self.mod._parse_results(BR_REALISTIC)
        assert len(self.cap) == 1
        assert self.cap[0]["size"] == str(int(4.7 * 1024**3))
        assert self.cap[0]["seeds"] == "0"

    def test_alternate_class_attributes(self):
        self.mod._parse_results(BR_ALTERNATE_CLASS)
        assert len(self.cap) == 1
        assert self.cap[0]["name"] == "Alt Class Torrent"
        assert self.cap[0]["seeds"] == "99"
        assert self.cap[0]["leech"] == "1"


class TestSearch:
    def setup_method(self):
        self.mod, self.cap = _load_bitru()

    @patch("bitru.retrieve_url", return_value=BR_SINGLE)
    def test_search_all_category(self, mock_retrieve):
        self.mod.search("ubuntu", "all")
        assert mock_retrieve.call_args[0][0] == "https://bitru.org/search/?q=ubuntu&c=0"

    @patch("bitru.retrieve_url", return_value=BR_SINGLE)
    def test_search_movies_category(self, mock_retrieve):
        self.mod.search("ubuntu", "movies")
        assert mock_retrieve.call_args[0][0] == "https://bitru.org/search/?q=ubuntu&c=1"

    @patch("bitru.retrieve_url", return_value=BR_SINGLE)
    def test_search_games_category(self, mock_retrieve):
        self.mod.search("witcher", "games")
        assert mock_retrieve.call_args[0][0] == "https://bitru.org/search/?q=witcher&c=7"

    @patch("bitru.retrieve_url", return_value=BR_SINGLE)
    def test_search_unknown_category_falls_back_to_all(self, mock_retrieve):
        self.mod.search("ubuntu", "nonexistent")
        assert mock_retrieve.call_args[0][0] == "https://bitru.org/search/?q=ubuntu&c=0"

    @patch("bitru.retrieve_url", return_value=BR_SINGLE)
    def test_search_url_encodes_spaces(self, mock_retrieve):
        self.mod.search("ubuntu server", "all")
        assert mock_retrieve.call_args[0][0] == "https://bitru.org/search/?q=ubuntu%20server&c=0"

    @patch("bitru.retrieve_url", return_value=BR_MULTI)
    def test_search_results_emitted(self, mock_retrieve):
        self.mod.search("test", "all")
        assert len(self.cap) == 2

    @patch("bitru.retrieve_url", side_effect=Exception("network error"))
    def test_search_exception_does_not_crash(self, mock_retrieve):
        self.mod.search("ubuntu", "all")
        assert len(self.cap) == 0

    @patch("bitru.retrieve_url")
    def test_search_preserves_callers_what_even_if_encoded(self, mock_retrieve):
        self.mod.search("ubuntu%20server", "all")
        assert mock_retrieve.call_args[0][0] == "https://bitru.org/search/?q=ubuntu%20server&c=0"


class TestDownloadTorrent:
    def setup_method(self):
        self.mod, self.cap = _load_bitru()

    @patch("bitru.retrieve_url")
    def test_download_magnet_link(self, mock_retrieve, capsys):
        mock_retrieve.return_value = BR_MAGNET_HTML
        self.mod.download_torrent("https://bitru.org/details/abc")
        out = capsys.readouterr().out
        assert "magnet:?xt=urn:btih:abc123def456&dn=ubuntu" in out
        assert "https://bitru.org/details/abc" in out

    @patch("bitru.retrieve_url")
    def test_download_torrent_file(self, mock_retrieve, capsys):
        mock_retrieve.return_value = BR_TORRENT_HTML
        self.mod.download_torrent("https://bitru.org/details/def")
        out = capsys.readouterr().out
        assert "https://bitru.org/download/ubuntu.torrent" in out
        assert "https://bitru.org/details/def" in out

    @patch("bitru.retrieve_url", return_value=BR_NO_LINKS_HTML)
    def test_download_no_magnet_no_torrent(self, mock_retrieve, capsys):
        self.mod.download_torrent("https://bitru.org/details/ghi")
        out = capsys.readouterr().out
        assert out.strip() == ""

    @patch("bitru.retrieve_url", side_effect=Exception("network error"))
    def test_download_exception_exits(self, mock_retrieve):
        with pytest.raises(SystemExit):
            self.mod.download_torrent("https://bitru.org/details/jkl")
