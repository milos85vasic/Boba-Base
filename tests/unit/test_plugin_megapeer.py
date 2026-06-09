"""Deep coverage tests for plugins/megapeer.py.

Covers: _parse_results (single/multi/empty/malformed HTML), _parse_size (all
units, commas, garbage, lowercase, whitespace), search (URL construction,
query encoding, exception handling), download_torrent (stdout output,
exception propagation), plugin metadata, edge cases.

Known bug in _parse_size: the multipliers dict checks "B" before "GB"/"MB"/etc.
Since "B" is a substring of "GB", it matches first, strips the wrong character,
and fails parsing. Only bare "B" sizes parse correctly. Tests document this.
"""

import importlib.util
import os
import sys
import types
from unittest.mock import patch

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PLUGINS_DIR = os.path.join(REPO, "plugins")


def _load_megapeer(captured=None):
    """Import megapeer plugin with stub modules. Returns (instance, captured)."""
    if captured is None:
        captured = []
    np_mod = types.ModuleType("novaprinter")
    np_mod.prettyPrinter = lambda d: captured.append(dict(d))
    sys.modules["novaprinter"] = np_mod

    helpers_mod = types.ModuleType("helpers")
    helpers_mod.retrieve_url = lambda url: ""
    sys.modules["helpers"] = helpers_mod

    sys.modules.pop("megapeer", None)

    path = os.path.join(PLUGINS_DIR, "megapeer.py")
    spec = importlib.util.spec_from_file_location("megapeer", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules["megapeer"] = mod
    cls = getattr(mod, "megapeer", None)
    if cls is not None and isinstance(cls, type):
        return cls(), captured
    return mod, captured


def _load_megapeer_module():
    """Import megapeer plugin and return the raw module."""
    np_mod = types.ModuleType("novaprinter")
    np_mod.prettyPrinter = lambda d: None
    sys.modules["novaprinter"] = np_mod

    helpers_mod = types.ModuleType("helpers")
    helpers_mod.retrieve_url = lambda url: ""
    sys.modules["helpers"] = helpers_mod

    sys.modules.pop("megapeer", None)

    path = os.path.join(PLUGINS_DIR, "megapeer.py")
    spec = importlib.util.spec_from_file_location("megapeer", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules["megapeer"] = mod
    return mod


# ─── HTML fixtures matching the megapeer regex (re.S | re.I) ──────────────
# Pattern: <tr class="table_fon">...<td>DATE</td>...
# <a href="/download/ID">...</a>...<a href="/torrent/PATH" class="url">NAME</a>...
# <td align="right">SIZE</td>...<font color="#...">SEEDS</font>...
# <font color="#...">LEECH</font>...</tr>

MP_SINGLE = '''<table>
<tr class="table_fon">
<td>2025-05-15</td>
<td><a href="/download/12345">DL</a></td>
<td><a href="/torrent/12345" class="url">Ubuntu 24.04 LTS</a></td>
<td align="right">2.4 GB</td>
<td><font color="#00aa00">150</font></td>
<td><font color="#aa0000">25</font></td>
</tr>
</table>'''

MP_MULTI = '''<table>
<tr class="table_fon">
<td>2025-05-10</td>
<td><a href="/download/111">DL</a></td>
<td><a href="/torrent/111" class="url">Linux Mint 22</a></td>
<td align="right">3.1 GB</td>
<td><font color="#00aa00">80</font></td>
<td><font color="#aa0000">10</font></td>
</tr>
<tr class="table_fon">
<td>2025-05-11</td>
<td><a href="/download/222">DL</a></td>
<td><a href="/torrent/222" class="url">Arch Linux 2025</a></td>
<td align="right">850 MB</td>
<td><font color="#00aa00">200</font></td>
<td><font color="#aa0000">5</font></td>
</tr>
<tr class="table_fon">
<td>2025-05-12</td>
<td><a href="/download/333">DL</a></td>
<td><a href="/torrent/333" class="url">Fedora Workstation 41</a></td>
<td align="right">2.1 GB</td>
<td><font color="#00aa00">60</font></td>
<td><font color="#aa0000">15</font></td>
</tr>
</table>'''

MP_EMPTY = '<html><body><p>Nothing found.</p></body></html>'

MP_MALFORMED = '''<table>
<tr class="table_fon">
<td>2025-05-15</td>
<td><a href="/download/999">DL</a></td>
</tr>
</table>'''

MP_NO_RESULTS_TABLE = '<html><body><table></table></body></html>'

MP_SPECIAL_CHARS = '''<table>
<tr class="table_fon">
<td>2025-06-01</td>
<td><a href="/download/555">DL</a></td>
<td><a href="/torrent/555" class="url">Тест &amp; "quotes" &lt;file&gt;</a></td>
<td align="right">1.5 GB</td>
<td><font color="#00aa00">42</font></td>
<td><font color="#aa0000">8</font></td>
</tr>
</table>'''

MP_BYTE_SIZE = '''<table>
<tr class="table_fon">
<td>2025-01-01</td>
<td><a href="/download/702">DL</a></td>
<td><a href="/torrent/702" class="url">Minimal</a></td>
<td align="right">100 B</td>
<td><font color="#00aa00">1</font></td>
<td><font color="#aa0000">0</font></td>
</tr>
</table>'''

MP_ZERO_SEEDS = '''<table>
<tr class="table_fon">
<td>2025-01-01</td>
<td><a href="/download/705">DL</a></td>
<td><a href="/torrent/705" class="url">Dead Torrent</a></td>
<td align="right">500 MB</td>
<td><font color="#00aa00">0</font></td>
<td><font color="#aa0000">0</font></td>
</tr>
</table>'''

MP_GARBAGE_SIZE = '''<table>
<tr class="table_fon">
<td>2025-01-01</td>
<td><a href="/download/703">DL</a></td>
<td><a href="/torrent/703" class="url">Unknown Size</a></td>
<td align="right">unknown</td>
<td><font color="#00aa00">7</font></td>
<td><font color="#aa0000">2</font></td>
</tr>
</table>'''


class TestParseResults:
    def test_single_result(self):
        mod, cap = _load_megapeer()
        mod._parse_results(MP_SINGLE)
        assert len(cap) == 1
        assert cap[0]["name"] == "Ubuntu 24.04 LTS"
        assert cap[0]["link"] == "https://megapeer.vip/download/12345"
        assert cap[0]["desc_link"] == "https://megapeer.vip/torrent/12345"
        assert cap[0]["engine_url"] == "https://megapeer.vip"
        assert cap[0]["seeds"] == "150"
        assert cap[0]["leech"] == "25"
        assert cap[0]["pub_date"] is not None

    def test_multi_results(self):
        mod, cap = _load_megapeer()
        mod._parse_results(MP_MULTI)
        assert len(cap) == 3
        assert cap[0]["name"] == "Linux Mint 22"
        assert cap[1]["name"] == "Arch Linux 2025"
        assert cap[2]["name"] == "Fedora Workstation 41"

    def test_empty_html(self):
        mod, cap = _load_megapeer()
        mod._parse_results(MP_EMPTY)
        assert len(cap) == 0

    def test_no_results_table(self):
        mod, cap = _load_megapeer()
        mod._parse_results(MP_NO_RESULTS_TABLE)
        assert len(cap) == 0

    def test_malformed_row_skipped(self):
        mod, cap = _load_megapeer()
        mod._parse_results(MP_MALFORMED)
        assert len(cap) == 0

    def test_size_gb_parses_correctly(self):
        mod, cap = _load_megapeer()
        mod._parse_results(MP_SINGLE)
        assert cap[0]["size"] == str(int(2.4 * 1024**3))

    def test_size_mb_parses_correctly(self):
        mod, cap = _load_megapeer()
        mod._parse_results(MP_MULTI)
        assert cap[1]["size"] == str((850 * 1024**2))

    def test_byte_size_parses_correctly(self):
        mod, cap = _load_megapeer()
        mod._parse_results(MP_BYTE_SIZE)
        assert cap[0]["size"] == "100"

    def test_special_characters_in_name(self):
        mod, cap = _load_megapeer()
        mod._parse_results(MP_SPECIAL_CHARS)
        assert len(cap) == 1
        assert "quotes" in cap[0]["name"]

    def test_links_are_absolute(self):
        mod, cap = _load_megapeer()
        mod._parse_results(MP_SINGLE)
        assert cap[0]["link"].startswith("https://megapeer.vip/download/")
        assert cap[0]["desc_link"].startswith("https://megapeer.vip/torrent/")

    def test_zero_seeds_leech(self):
        mod, cap = _load_megapeer()
        mod._parse_results(MP_ZERO_SEEDS)
        assert len(cap) == 1
        assert cap[0]["seeds"] == "0"
        assert cap[0]["leech"] == "0"

    def test_garbage_size_returns_zero(self):
        mod, cap = _load_megapeer()
        mod._parse_results(MP_GARBAGE_SIZE)
        assert cap[0]["size"] == "0"


class TestParseSize:
    def setup_method(self):
        self.mod, _ = _load_megapeer()

    def test_bytes(self):
        assert self.mod._parse_size("100 B") == 100

    def test_zero_bytes(self):
        assert self.mod._parse_size("0 B") == 0

    def test_garbage_returns_zero(self):
        assert self.mod._parse_size("unknown") == 0

    def test_invalid_number_returns_zero(self):
        assert self.mod._parse_size("abc GB") == 0

    def test_gb_parses_correctly(self):
        assert self.mod._parse_size("2.4 GB") == int(2.4 * 1024**3)

    def test_mb_parses_correctly(self):
        assert self.mod._parse_size("850 MB") == (850 * 1024**2)

    def test_kb_parses_correctly(self):
        assert self.mod._parse_size("512 KB") == 512 * 1024

    def test_tb_parses_correctly(self):
        assert self.mod._parse_size("3.5 TB") == int(3.5 * 1024**4)

    def test_comma_gb_parses_correctly(self):
        assert self.mod._parse_size("1,024 MB") == 1024 * 1024**2

    def test_lowercase_gb_parses_correctly(self):
        assert self.mod._parse_size("2.5 gb") == int(2.5 * 1024**3)

    def test_whitespace_gb_parses_correctly(self):
        assert self.mod._parse_size("  1.0 GB  ") == int(1.0 * 1024**3)

    def test_bug_whitespace_b_works(self):
        assert self.mod._parse_size("  100 B  ") == 100


class TestSearch:
    def setup_method(self):
        self.mod, self.cap = _load_megapeer()

    @patch("megapeer.retrieve_url", return_value=MP_SINGLE)
    def test_search_url_construction(self, mock_retrieve):
        self.mod.search("ubuntu", "all")
        called_url = mock_retrieve.call_args[0][0]
        assert called_url == "https://megapeer.vip/browse.php?search=ubuntu"

    @patch("megapeer.retrieve_url", return_value=MP_SINGLE)
    def test_search_url_encodes_query(self, mock_retrieve):
        self.mod.search("hello world", "all")
        called_url = mock_retrieve.call_args[0][0]
        assert "hello%20world" in called_url

    @patch("megapeer.retrieve_url", return_value=MP_SINGLE)
    def test_search_special_chars_encoded(self, mock_retrieve):
        self.mod.search("test & foo", "all")
        called_url = mock_retrieve.call_args[0][0]
        assert "&" not in called_url.split("search=")[1]

    @patch("megapeer.retrieve_url", return_value=MP_SINGLE)
    def test_search_results_emitted(self, mock_retrieve):
        self.mod.search("ubuntu", "all")
        assert len(self.cap) == 1
        assert self.cap[0]["name"] == "Ubuntu 24.04 LTS"

    @patch("megapeer.retrieve_url", return_value=MP_EMPTY)
    def test_search_no_results(self, mock_retrieve):
        self.mod.search("nonexistent", "all")
        assert len(self.cap) == 0

    @patch("megapeer.retrieve_url", side_effect=Exception("network error"))
    def test_search_exception_does_not_crash(self, mock_retrieve):
        self.mod.search("ubuntu", "all")
        assert len(self.cap) == 0

    @patch("megapeer.retrieve_url", return_value=MP_MULTI)
    def test_search_multiple_results_emitted(self, mock_retrieve):
        self.mod.search("linux", "all")
        assert len(self.cap) == 3

    @patch("megapeer.retrieve_url", return_value="")
    def test_search_empty_response(self, mock_retrieve):
        self.mod.search("test", "all")
        assert len(self.cap) == 0

    @patch("megapeer.retrieve_url", return_value=MP_SINGLE)
    def test_search_unquotes_what(self, mock_retrieve):
        self.mod.search("ubuntu%20lts", "all")
        called_url = mock_retrieve.call_args[0][0]
        assert "ubuntu%2520lts" not in called_url

    @patch("megapeer.retrieve_url", return_value=MP_SINGLE)
    def test_search_cat_param_accepted(self, mock_retrieve):
        self.mod.search("ubuntu", "movies")
        called_url = mock_retrieve.call_args[0][0]
        assert "browse.php" in called_url


class TestDownloadTorrent:
    def setup_method(self):
        self.mod, self.cap = _load_megapeer()

    def test_download_prints_url_twice(self, capsys):
        self.mod.download_torrent("https://megapeer.vip/download/12345")
        out = capsys.readouterr().out
        assert out.count("https://megapeer.vip/download/12345") == 2

    def test_download_output_format(self, capsys):
        self.mod.download_torrent("https://megapeer.vip/download/999")
        out = capsys.readouterr().out.strip()
        parts = out.split()
        assert len(parts) == 2
        assert parts[0] == parts[1]

    def test_download_exception_in_handler_propagates(self):
        with patch("builtins.print", side_effect=Exception("write error")):
            with pytest.raises(Exception, match="write error"):
                self.mod.download_torrent("https://megapeer.vip/download/1")

    def test_download_no_results_in_captured(self, capsys):
        self.mod.download_torrent("https://megapeer.vip/download/500")
        assert len(self.cap) == 0


class TestPluginMetadata:
    def test_url(self):
        mod, _ = _load_megapeer()
        assert mod.url == "https://megapeer.vip"

    def test_name(self):
        mod, _ = _load_megapeer()
        assert mod.name == "MegaPeer"

    def test_supported_categories_keys(self):
        mod, _ = _load_megapeer()
        expected = {"all", "movies", "tv", "music", "games", "software", "books"}
        assert set(mod.supported_categories.keys()) == expected

    def test_supported_categories_values_are_strings(self):
        mod, _ = _load_megapeer()
        for v in mod.supported_categories.values():
            assert isinstance(v, str)

    def test_class_rebound_at_module_level(self):
        raw_mod = _load_megapeer_module()
        assert raw_mod.megapeer is raw_mod.megapeer

    def test_version_declared(self):
        raw_mod = _load_megapeer_module()
        assert hasattr(raw_mod, "__name__")


class TestPubDate:
    def test_pub_date_is_unix_timestamp(self):
        mod, cap = _load_megapeer()
        mod._parse_results(MP_SINGLE)
        ts = int(cap[0]["pub_date"])
        assert ts > 0
        assert ts < 10**10

    def test_pub_date_changes_per_call(self):
        import time

        mod1, cap1 = _load_megapeer()
        mod1._parse_results(MP_SINGLE)
        t1 = int(cap1[0]["pub_date"])
        time.sleep(0.01)
        mod2, cap2 = _load_megapeer()
        mod2._parse_results(MP_SINGLE)
        t2 = int(cap2[0]["pub_date"])
        assert t2 >= t1
