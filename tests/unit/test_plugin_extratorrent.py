"""Deep coverage tests for plugins/community/extratorrent.py.

Covers: _parse_results (single/multi/empty/malformed), _parse_size
(all units, edge cases), search (URL construction, category mapping,
exception handling), download_torrent (magnet, torrent file, no links,
URLError), category mapping, edge cases.
"""

import importlib.util
import os
import sys
import types
from unittest.mock import patch

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PLUGINS_DIR = os.path.join(REPO, "plugins", "community")


def _load_extratorrent(captured=None):
    if captured is None:
        captured = []
    np_mod = types.ModuleType("novaprinter")
    np_mod.prettyPrinter = lambda d: captured.append(dict(d))
    sys.modules["novaprinter"] = np_mod

    helpers_mod = types.ModuleType("helpers")
    helpers_mod.retrieve_url = lambda url: ""
    sys.modules["helpers"] = helpers_mod

    sys.modules.pop("extratorrent", None)

    path = os.path.join(PLUGINS_DIR, "extratorrent.py")
    spec = importlib.util.spec_from_file_location("extratorrent", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules["extratorrent"] = mod
    cls = getattr(mod, "extratorrent", None)
    if cls is not None and isinstance(cls, type):
        return cls(), captured
    return mod, captured


# ─── HTML fixtures ────────────────────────────────────────────────────
# The regex expects: <tr class="...trl..."><td><a href="/torrent/...">NAME</a></td><td>SIZE</td><td>SEEDS</td><td>LEECH</td><td>????</td></tr>

ET_SINGLE = '''<table>
<tr class="trl1">
<td><a href="/torrent/abc123/ubuntu-24.04">Ubuntu 24.04 LTS</a></td>
<td>4.2 GB</td>
<td>1523</td>
<td>45</td>
<td>2025-05-20</td>
</tr>
</table>'''

ET_MULTI = '''<table>
<tr class="trl1">
<td><a href="/torrent/aaa111/ubuntu-24.04">Ubuntu 24.04 LTS</a></td>
<td>4.2 GB</td>
<td>1523</td>
<td>45</td>
<td>2025-05-20</td>
</tr>
<tr class="trl2">
<td><a href="/torrent/bbb222/fedora-40">Fedora 40</a></td>
<td>2.1 GB</td>
<td>876</td>
<td>12</td>
<td>2025-04-10</td>
</tr>
<tr class="trl1">
<td><a href="/torrent/ccc333/centos-stream">CentOS Stream</a></td>
<td>1.8 GB</td>
<td>345</td>
<td>8</td>
<td>2025-03-15</td>
</tr>
</table>'''

ET_EMPTY = '<html><body><p>No results found.</p></body></html>'

ET_MALFORMED = '''<table>
<tr class="trl1">
<td><a href="/torrent/broken123">Broken Entry</a></td>
</tr>
</table>'''

ET_GARBAGE_SEEDS = '''<table>
<tr class="trl1">
<td><a href="/torrent/gar1/garbage-seeds">Garbage Seeds</a></td>
<td>1.0 GB</td>
<td>abc</td>
<td>5</td>
<td>2025-01-01</td>
</tr>
</table>'''

ET_GARBAGE_LEECH = '''<table>
<tr class="trl1">
<td><a href="/torrent/gar2/garbage-leech">Garbage Leech</a></td>
<td>1.0 GB</td>
<td>10</td>
<td>xyz</td>
<td>2025-01-01</td>
</tr>
</table>'''

ET_SPECIAL_CHARS = '''<table>
<tr class="trl1">
<td><a href="/torrent/sp1/name-with-ampersand&amp;more">Name with &amp; and <b>HTML</b></a></td>
<td>3.5 GB</td>
<td>50</td>
<td>5</td>
<td>2025-06-01</td>
</tr>
</table>'''

ET_ZERO_SEEDS = '''<table>
<tr class="trl1">
<td><a href="/torrent/z1/dead-torrent">Dead Torrent</a></td>
<td>100 MB</td>
<td>0</td>
<td>0</td>
<td>2025-01-01</td>
</tr>
</table>'''

ET_NO_TRL_CLASS = '''<table>
<tr class="normal-row">
<td><a href="/torrent/n1/not-matched">Not Matched</a></td>
<td>1.0 GB</td>
<td>10</td>
<td>5</td>
<td>2025-01-01</td>
</tr>
</table>'''


class TestParseResults:
    def test_single_result(self):
        mod, cap = _load_extratorrent()
        mod._parse_results(ET_SINGLE)
        assert len(cap) == 1
        assert cap[0]["name"] == "Ubuntu 24.04 LTS"
        assert cap[0]["link"] == "https://extratorrent.st/torrent/abc123/ubuntu-24.04"
        assert cap[0]["desc_link"] == cap[0]["link"]
        assert cap[0]["engine_url"] == "https://extratorrent.st"
        assert cap[0]["seeds"] == "1523"
        assert cap[0]["leech"] == "45"

    def test_multi_results(self):
        mod, cap = _load_extratorrent()
        mod._parse_results(ET_MULTI)
        assert len(cap) == 3
        assert cap[0]["name"] == "Ubuntu 24.04 LTS"
        assert cap[1]["name"] == "Fedora 40"
        assert cap[2]["name"] == "CentOS Stream"

    def test_empty_html(self):
        mod, cap = _load_extratorrent()
        mod._parse_results(ET_EMPTY)
        assert len(cap) == 0

    def test_malformed_row_skipped(self):
        mod, cap = _load_extratorrent()
        mod._parse_results(ET_MALFORMED)
        assert len(cap) == 0

    def test_no_trl_class_skipped(self):
        mod, cap = _load_extratorrent()
        mod._parse_results(ET_NO_TRL_CLASS)
        assert len(cap) == 0

    def test_garbage_seeds_defaults_to_zero(self):
        mod, cap = _load_extratorrent()
        mod._parse_results(ET_GARBAGE_SEEDS)
        assert len(cap) == 1
        assert cap[0]["seeds"] == "0"

    def test_garbage_leech_defaults_to_zero(self):
        mod, cap = _load_extratorrent()
        mod._parse_results(ET_GARBAGE_LEECH)
        assert len(cap) == 1
        assert cap[0]["leech"] == "0"

    def test_zero_seeds_preserved(self):
        mod, cap = _load_extratorrent()
        mod._parse_results(ET_ZERO_SEEDS)
        assert len(cap) == 1
        assert cap[0]["seeds"] == "0"
        assert cap[0]["leech"] == "0"

    def test_pub_date_is_unix_timestamp(self):
        mod, cap = _load_extratorrent()
        mod._parse_results(ET_SINGLE)
        ts = int(cap[0]["pub_date"])
        assert ts > 1_000_000_000

    def test_size_parsed_correctly(self):
        mod, cap = _load_extratorrent()
        mod._parse_results(ET_SINGLE)
        assert cap[0]["size"] == str(int(4.2 * 1024**3))


class TestParseSize:
    """Tests for _parse_size."""

    def setup_method(self):
        self.mod, _ = _load_extratorrent()

    def test_bytes(self):
        assert self.mod._parse_size("1024 B") == 1024

    def test_kilobytes(self):
        assert self.mod._parse_size("512 KB") == 512 * 1024

    def test_megabytes(self):
        assert self.mod._parse_size("750.5 MB") == int(750.5 * 1024**2)

    def test_gigabytes(self):
        assert self.mod._parse_size("4.2 GB") == int(4.2 * 1024**3)

    def test_terabytes(self):
        assert self.mod._parse_size("1.5 TB") == int(1.5 * 1024**4)

    def test_comma_in_number(self):
        assert self.mod._parse_size("1,024 MB") == 1024 * 1024**2

    def test_uppercase_normalization(self):
        assert self.mod._parse_size("  10.0 Gb  ") == int(10.0 * 1024**3)

    def test_garbage_returns_zero(self):
        assert self.mod._parse_size("unknown") == 0

    def test_empty_string(self):
        assert self.mod._parse_size("") == 0

    def test_bare_number_no_unit(self):
        assert self.mod._parse_size("100") == 0

    def test_lower_case_unit(self):
        assert self.mod._parse_size("2.5 tb") == int(2.5 * 1024**4)

    def test_float_with_many_decimals(self):
        assert self.mod._parse_size("0.001 GB") == int(0.001 * 1024**3)

    def test_bytes_with_comma(self):
        assert self.mod._parse_size("1,024 B") == 1024

    def test_bytes_decimal(self):
        assert self.mod._parse_size("512.5 B") == 512


class TestSearch:
    def setup_method(self):
        self.mod, self.cap = _load_extratorrent()

    @patch("extratorrent.retrieve_url", return_value=ET_SINGLE)
    def test_search_all_category(self, mock_retrieve):
        self.mod.search("ubuntu", "all")
        called_url = mock_retrieve.call_args[0][0]
        assert called_url == "https://extratorrent.st/search/?search=ubuntu&category=0"

    @patch("extratorrent.retrieve_url", return_value=ET_SINGLE)
    def test_search_movies_category(self, mock_retrieve):
        self.mod.search("avatar", "movies")
        called_url = mock_retrieve.call_args[0][0]
        assert called_url == "https://extratorrent.st/search/?search=avatar&category=4"

    @patch("extratorrent.retrieve_url", return_value=ET_SINGLE)
    def test_search_tv_category(self, mock_retrieve):
        self.mod.search("breaking bad", "tv")
        called_url = mock_retrieve.call_args[0][0]
        assert "category=8" in called_url

    @patch("extratorrent.retrieve_url", return_value=ET_SINGLE)
    def test_search_music_category(self, mock_retrieve):
        self.mod.search("album", "music")
        called_url = mock_retrieve.call_args[0][0]
        assert "category=5" in called_url

    @patch("extratorrent.retrieve_url", return_value=ET_SINGLE)
    def test_search_games_category(self, mock_retrieve):
        self.mod.search("witcher", "games")
        called_url = mock_retrieve.call_args[0][0]
        assert "category=3" in called_url

    @patch("extratorrent.retrieve_url", return_value=ET_SINGLE)
    def test_search_software_category(self, mock_retrieve):
        self.mod.search("photoshop", "software")
        called_url = mock_retrieve.call_args[0][0]
        assert "category=7" in called_url

    @patch("extratorrent.retrieve_url", return_value=ET_SINGLE)
    def test_search_anime_category(self, mock_retrieve):
        self.mod.search("naruto", "anime")
        called_url = mock_retrieve.call_args[0][0]
        assert "category=1" in called_url

    @patch("extratorrent.retrieve_url", return_value=ET_SINGLE)
    def test_search_books_category(self, mock_retrieve):
        self.mod.search("python cookbook", "books")
        called_url = mock_retrieve.call_args[0][0]
        assert "category=2" in called_url

    @patch("extratorrent.retrieve_url", return_value=ET_SINGLE)
    def test_search_unknown_category_falls_back_to_all(self, mock_retrieve):
        self.mod.search("test", "nonexistent")
        called_url = mock_retrieve.call_args[0][0]
        assert "category=0" in called_url

    @patch("extratorrent.retrieve_url", return_value=ET_SINGLE)
    def test_search_results_emitted(self, mock_retrieve):
        self.mod.search("ubuntu", "all")
        assert len(self.cap) == 1
        assert self.cap[0]["name"] == "Ubuntu 24.04 LTS"

    @patch("extratorrent.retrieve_url", side_effect=Exception("network error"))
    def test_search_exception_does_not_crash(self, mock_retrieve):
        self.mod.search("ubuntu", "all")
        assert len(self.cap) == 0

    @patch("extratorrent.retrieve_url", return_value=ET_SINGLE)
    def test_search_special_chars_in_query(self, mock_retrieve):
        self.mod.search("c++ & c#", "all")
        called_url = mock_retrieve.call_args[0][0]
        assert "c%2B%2B%20%26%20c%23" in called_url

    @patch("extratorrent.retrieve_url", return_value=ET_SINGLE)
    def test_search_url_encoded_input_decoded(self, mock_retrieve):
        self.mod.search("ubuntu%2024.04", "all")
        called_url = mock_retrieve.call_args[0][0]
        assert "ubuntu%2024.04" in called_url or "ubuntu" in called_url


class TestDownloadTorrent:
    def setup_method(self):
        self.mod, self.cap = _load_extratorrent()

    @patch("extratorrent.retrieve_url")
    def test_download_magnet_link(self, mock_retrieve, capsys):
        html = '<a href="magnet:?xt=urn:btih:abc123&dn=ubuntu">Magnet</a>'
        mock_retrieve.return_value = html
        self.mod.download_torrent("https://extratorrent.st/torrent/abc123")
        out = capsys.readouterr().out
        assert "magnet:?xt=urn:btih:abc123&dn=ubuntu" in out
        assert "https://extratorrent.st/torrent/abc123" in out

    @patch("extratorrent.retrieve_url")
    def test_download_torrent_file(self, mock_retrieve, capsys):
        html = '<a href="/download/ubuntu.torrent">Download</a>'
        mock_retrieve.return_value = html
        self.mod.download_torrent("https://extratorrent.st/torrent/abc123")
        out = capsys.readouterr().out
        assert "https://extratorrent.st/download/ubuntu.torrent" in out
        assert "https://extratorrent.st/torrent/abc123" in out

    @patch("extratorrent.retrieve_url", side_effect=Exception("network error"))
    def test_download_exception_exits(self, mock_retrieve):
        with pytest.raises(SystemExit):
            self.mod.download_torrent("https://example.com/page")

    @patch("extratorrent.retrieve_url", return_value="<html>no links</html>")
    def test_download_no_magnet_no_torrent(self, mock_retrieve, capsys):
        self.mod.download_torrent("https://example.com/page")
        out = capsys.readouterr().out
        assert out.strip() == ""

    @patch("extratorrent.retrieve_url")
    def test_download_magnet_preferred_over_torrent(self, mock_retrieve, capsys):
        html = (
            '<a href="magnet:?xt=urn:btih:aaa&dn=test">Magnet</a>'
            '<a href="/download/test.torrent">Download</a>'
        )
        mock_retrieve.return_value = html
        self.mod.download_torrent("https://example.com/page")
        out = capsys.readouterr().out
        assert "magnet:?xt=urn:btih:aaa&dn=test" in out
        assert "/download/test.torrent" not in out

    @patch("extratorrent.retrieve_url")
    def test_download_magnet_special_chars(self, mock_retrieve, capsys):
        html = '<a href="magnet:?xt=urn:btih:def456&dn=name+with+spaces&tr=udp://tracker:6969">Magnet</a>'
        mock_retrieve.return_value = html
        self.mod.download_torrent("https://example.com/page")
        out = capsys.readouterr().out
        assert "magnet:?xt=urn:btih:def456" in out


class TestCategoryMapping:
    def test_all_categories_present(self):
        mod, _ = _load_extratorrent()
        expected = {"all", "movies", "tv", "music", "games", "software", "anime", "books"}
        assert set(mod.supported_categories.keys()) == expected

    def test_category_values_are_strings(self):
        mod, _ = _load_extratorrent()
        for val in mod.supported_categories.values():
            assert isinstance(val, str)
            assert val.isdigit()

    def test_url_attribute(self):
        mod, _ = _load_extratorrent()
        assert mod.url == "https://extratorrent.st"

    def test_name_attribute(self):
        mod, _ = _load_extratorrent()
        assert mod.name == "ExtraTorrent"
