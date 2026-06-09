"""Deep coverage tests for plugins/community/btsow.py.

Covers: _parse_results (data-list cards, single/multi, malformed), _parse_size
(all units, edge cases), search (URL construction, category mapping),
download_torrent (magnet output), exception handling.
"""

import importlib.util
import os
import sys
import types
from unittest.mock import patch

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PLUGINS_DIR = os.path.join(REPO, "plugins", "community")


def _load_btsow(captured=None):
    if captured is None:
        captured = []
    np_mod = types.ModuleType("novaprinter")
    np_mod.prettyPrinter = lambda d: captured.append(dict(d))
    sys.modules["novaprinter"] = np_mod

    helpers_mod = types.ModuleType("helpers")
    helpers_mod.retrieve_url = lambda url: ""
    sys.modules["helpers"] = helpers_mod

    sys.modules.pop("btsow", None)

    path = os.path.join(PLUGINS_DIR, "btsow.py")
    spec = importlib.util.spec_from_file_location("btsow", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules["btsow"] = mod
    cls = getattr(mod, "btsow", None)
    if cls is not None and isinstance(cls, type):
        return cls(), captured
    return mod, captured


BT_SINGLE = '''<div class="row data-list">
<a href="/magnet/abcdef12345678901234567890abcdef12345678">
<div class="name">Ubuntu 24.04 LTS</div>
<div class="size">1024 B</div>
<div class="date">2025-01-15</div>
</a>
</div>'''

BT_MULTI = '''<div class="row data-list">
<a href="/magnet/1111111111111111111111111111111111111111">
<div class="name">Debian 12</div>
<div class="size">1024 B</div>
<div class="date">2025-02-01</div>
</a>
</div>
<div class="row data-list">
<a href="/magnet/2222222222222222222222222222222222222222">
<div class="name">Fedora 40</div>
<div class="size">2048 B</div>
<div class="date">2025-03-10</div>
</a>
</div>'''

BT_EMPTY = '<html><body><p>No results found.</p></body></html>'

BT_MALFORMED = '''<div class="row data-list">
<a href="/magnet/badhash">
<div class="name">Bad Hash Entry</div>
</a>
</div>'''

BT_NON_DATA_LIST = '''<div class="row other-class">
<a href="/magnet/3333333333333333333333333333333333333333">
<div class="name">Should Not Match</div>
<div class="size">1.0 B</div>
<div class="date">2025-01-01</div>
</a>
</div>'''

BT_NO_HASH = '''<div class="row data-list">
<a href="/magnet/no-hash-here">
<div class="name">No Hash File</div>
<div class="size">1 B</div>
<div class="date">2025-01-01</div>
</a>
</div>'''

BT_UPPERCASE_HASH = '''<div class="row data-list">
<a href="/magnet/AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA">
<div class="name">Upper Hash</div>
<div class="size">1 B</div>
<div class="date">2025-01-01</div>
</a>
</div>'''

BT_MIXED_ATTRIBUTES = '''<div class="something data-list extra" data-foo="bar">
<a class="link" href="/magnet/9999999999999999999999999999999999999999">
<div class="something name other">Arch Linux</div>
<div class="size  value">100 B</div>
<div class="date  field">2025-01-01</div>
</a>
</div>'''

BT_MISSING_SIZE = '''<div class="row data-list">
<a href="/magnet/aaaaaaaa1111111111222222222233333333334444">
<div class="name">Missing Size File</div>
<div class="date">2025-01-01</div>
</a>
</div>'''

BT_EXTRA_WHITESPACE = '''<div class="row data-list">
<a href="/magnet/bbbbbbbb2222222222333333333344444444445555">
<div class="name">
  Fedora  41
</div>
<div class="size">
  500 B
</div>
<div class="date">
  2025-06-01
</div>
</a>
</div>'''


class TestParseResults:
    def test_single_result(self):
        mod, cap = _load_btsow()
        mod._parse_results(BT_SINGLE)
        assert len(cap) == 1
        assert cap[0]["name"] == "Ubuntu 24.04 LTS"
        assert cap[0]["engine_url"] == "https://btsow.motorcycles"
        assert cap[0]["seeds"] == "0"
        assert cap[0]["leech"] == "0"
        assert cap[0]["size"] == "1024"
        assert cap[0]["desc_link"] == "https://btsow.motorcycles/magnet/abcdef12345678901234567890abcdef12345678"
        assert cap[0]["link"].startswith("magnet:?xt=urn:btih:")

    def test_multi_results(self):
        mod, cap = _load_btsow()
        mod._parse_results(BT_MULTI)
        assert len(cap) == 2
        assert cap[0]["name"] == "Debian 12"
        assert cap[1]["name"] == "Fedora 40"

    def test_empty_html(self):
        mod, cap = _load_btsow()
        mod._parse_results(BT_EMPTY)
        assert len(cap) == 0

    def test_malformed_skipped_no_error(self):
        mod, cap = _load_btsow()
        mod._parse_results(BT_MALFORMED)
        assert len(cap) == 0

    def test_non_data_list_ignored(self):
        mod, cap = _load_btsow()
        mod._parse_results(BT_NON_DATA_LIST)
        assert len(cap) == 0

    def test_magnet_link_constructed_from_hash(self):
        mod, cap = _load_btsow()
        mod._parse_results(BT_SINGLE)
        magnet = cap[0]["link"]
        assert magnet == "magnet:?xt=urn:btih:ABCDEF12345678901234567890ABCDEF12345678&dn=Ubuntu%2024.04%20LTS"

    def test_no_hash_falls_back_to_url_magnet_path(self):
        mod, cap = _load_btsow()
        mod._parse_results(BT_NO_HASH)
        assert len(cap) == 1
        assert cap[0]["link"] == "https://btsow.motorcycles/magnet/no-hash-here"

    def test_uppercase_hash_preserved_in_magnet(self):
        mod, cap = _load_btsow()
        mod._parse_results(BT_UPPERCASE_HASH)
        assert cap[0]["link"] == "magnet:?xt=urn:btih:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA&dn=Upper%20Hash"

    def test_pub_date_present(self):
        mod, cap = _load_btsow()
        mod._parse_results(BT_SINGLE)
        assert "pub_date" in cap[0]
        assert int(cap[0]["pub_date"]) > 0

    def test_mixed_html_attributes(self):
        mod, cap = _load_btsow()
        mod._parse_results(BT_MIXED_ATTRIBUTES)
        assert len(cap) == 1
        assert cap[0]["name"] == "Arch Linux"
        assert cap[0]["size"] == "100"

    def test_extra_whitespace_in_fields(self):
        mod, cap = _load_btsow()
        mod._parse_results(BT_EXTRA_WHITESPACE)
        assert len(cap) == 1
        assert cap[0]["name"] == "Fedora  41"
        assert cap[0]["size"] == "500"


class TestParseSize:
    def setup_method(self):
        self.mod, _ = _load_btsow()

    def test_bytes(self):
        assert self.mod._parse_size("1024 B") == 1024

    def test_kilobytes(self):
        assert self.mod._parse_size("512 KB") == 512 * 1024

    def test_megabytes(self):
        assert self.mod._parse_size("750.5 MB") == int(750.5 * 1024**2)

    def test_gigabytes(self):
        assert self.mod._parse_size("4.7 GB") == int(4.7 * 1024**3)

    def test_terabytes(self):
        assert self.mod._parse_size("1.5 TB") == int(1.5 * 1024**4)

    def test_comma_in_number(self):
        assert self.mod._parse_size("1,024 B") == 1024

    def test_uppercase_normalization(self):
        assert self.mod._parse_size("  10.0 b  ") == 10

    def test_lowercase_units(self):
        assert self.mod._parse_size("1.0 b") == 1

    def test_no_unit_returns_zero(self):
        assert self.mod._parse_size("12345") == 0

    def test_garbage_returns_zero(self):
        assert self.mod._parse_size("unknown") == 0

    def test_spaces_within_size(self):
        assert self.mod._parse_size("  1.0  B  ") == 1

    def test_decimal_bytes(self):
        assert self.mod._parse_size("1.5 B") == int(1.5 * 1)


class TestSearch:
    def setup_method(self):
        self.mod, self.cap = _load_btsow()

    @patch("btsow.retrieve_url", return_value=BT_SINGLE)
    def test_search_all_category(self, mock_retrieve):
        self.mod.search("ubuntu", "all")
        called_url = mock_retrieve.call_args[0][0]
        assert called_url == "https://btsow.motorcycles/search/ubuntu"

    @patch("btsow.retrieve_url", return_value=BT_SINGLE)
    def test_search_url_encoding(self, mock_retrieve):
        self.mod.search("ubuntu server", "all")
        called_url = mock_retrieve.call_args[0][0]
        assert called_url == "https://btsow.motorcycles/search/ubuntu%20server"

    @patch("btsow.retrieve_url", return_value=BT_SINGLE)
    def test_search_results_emitted(self, mock_retrieve):
        self.mod.search("ubuntu", "all")
        assert len(self.cap) == 1
        assert self.cap[0]["name"] == "Ubuntu 24.04 LTS"

    @patch("btsow.retrieve_url", side_effect=Exception("network error"))
    def test_search_exception_does_not_crash(self, mock_retrieve, capsys):
        self.mod.search("ubuntu", "all")
        assert len(self.cap) == 0
        captured = capsys.readouterr()
        assert "Search error" in captured.err

    @patch("btsow.retrieve_url", return_value=BT_EMPTY)
    def test_search_empty_results(self, mock_retrieve):
        self.mod.search("nonexistent", "all")
        assert len(self.cap) == 0

    @patch("btsow.retrieve_url", return_value=BT_MULTI)
    def test_search_multi_results(self, mock_retrieve):
        self.mod.search("linux", "all")
        assert len(self.cap) == 2


class TestDownloadTorrent:
    def setup_method(self):
        self.mod, self.cap = _load_btsow()

    def test_download_outputs_url_and_magnet(self, capsys):
        self.mod.download_torrent("magnet:?xt=urn:btih:abc123")
        out = capsys.readouterr().out
        assert out.strip() == "magnet:?xt=urn:btih:abc123 magnet:?xt=urn:btih:abc123"

    def test_download_outputs_path_as_both_args(self, capsys):
        self.mod.download_torrent("/magnet/hashhere")
        out = capsys.readouterr().out
        assert out.strip() == "/magnet/hashhere /magnet/hashhere"
