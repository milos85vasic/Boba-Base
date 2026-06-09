"""Deep coverage tests for plugins/community/torrentfunk.py.

Covers: _parse_results (single/multi/empty/malformed, non-digit seeds/leech,
extra columns), _parse_size (unit iteration order behaviour, edge cases,
garbage), search (URL construction, category mapping, exception handling),
download_torrent (magnet, .torrent, no links, exception).
"""

import importlib.util
import os
import sys
import types
from unittest.mock import patch

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PLUGINS_DIR = os.path.join(REPO, "plugins", "community")


def _load_torrentfunk(captured=None):
    """Import torrentfunk plugin with stub modules. Returns (instance, captured)."""
    if captured is None:
        captured = []
    np_mod = types.ModuleType("novaprinter")
    np_mod.prettyPrinter = lambda d: captured.append(dict(d))
    sys.modules["novaprinter"] = np_mod

    helpers_mod = types.ModuleType("helpers")
    helpers_mod.retrieve_url = lambda url: ""
    sys.modules["helpers"] = helpers_mod

    sys.modules.pop("torrentfunk", None)

    path = os.path.join(PLUGINS_DIR, "torrentfunk.py")
    spec = importlib.util.spec_from_file_location("torrentfunk", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules["torrentfunk"] = mod
    cls = getattr(mod, "torrentfunk", None)
    if cls is not None and isinstance(cls, type):
        return cls(), captured
    return mod, captured


TF_SINGLE = '''<table>
<tr class="trow">
  <td><a href="/torrent/12345/ubuntu-linux-2204">Ubuntu Linux 22.04</a></td>
  <td>2025-01-15</td>
  <td class="tx">4.7 GB</td>
  <td class="ux">1250</td>
  <td class="vx">320</td>
</tr>
</table>'''

TF_SINGLE_BYTES = '''<table>
<tr class="trow">
  <td><a href="/torrent/42/tiny-file">Tiny File</a></td>
  <td>2025-06-01</td>
  <td class="tx">1024 B</td>
  <td class="ux">5</td>
  <td class="vx">2</td>
</tr>
</table>'''

TF_MULTI = '''<table>
<tr class="trow">
  <td><a href="/torrent/111/debian-12">Debian 12 Bookworm</a></td>
  <td>2025-06-01</td>
  <td class="tx">3.8 GB</td>
  <td class="ux">890</td>
  <td class="vx">145</td>
</tr>
<tr class="trow alt">
  <td><a href="/torrent/222/fedora-40">Fedora 40</a></td>
  <td>2025-05-20</td>
  <td class="tx">2.1 GB</td>
  <td class="ux">670</td>
  <td class="vx">210</td>
</tr>
</table>'''

TF_EMPTY = "<html><body><p>No results found.</p></body></html>"

TF_MALFORMED = '''<table>
<tr class="trow">
  <td><a href="/other/12/something">No Torrent Link</a></td>
  <td>2025-01-01</td>
  <td class="tx">1 MB</td>
  <td class="ux">10</td>
  <td class="vx">5</td>
</tr>
</table>'''

TF_NONDIGIT_SEEDS = '''<table>
<tr class="trow">
  <td><a href="/torrent/333/arch-linux">Arch Linux</a></td>
  <td>2025-04-10</td>
  <td class="tx">800 MB</td>
  <td class="ux">unknown</td>
  <td class="vx">--</td>
</tr>
</table>'''

TF_EXTRA_COLUMNS = '''<table>
<tr class="trow">
  <td class="coll-1"><img src="/icons/film.png" alt=""/></td>
  <td class="coll-2"><a href="/torrent/444/opensuse">openSUSE Tumbleweed</a></td>
  <td class="coll-3"><a href="/torrent/444/opensuse#comments">42</a></td>
  <td class="coll-4">2025-03-15</td>
  <td class="tx">5.1 GB</td>
  <td class="ux">2100</td>
  <td class="vx">98</td>
</tr>
</table>'''

TF_MIXED_TRACKER_ROWS = '''<table>
<tr class="trow">
  <td><a href="/torrent/555/centos">CentOS Stream</a></td>
  <td>2025-02-01</td>
  <td class="tx">9.2 GB</td>
  <td class="ux">340</td>
  <td class="vx">87</td>
</tr>
<tr class="trow">
  <td><a href="/other/99/non-torrent">Not a torrent</a></td>
  <td>2025-01-01</td>
  <td class="tx">1 MB</td>
  <td class="ux">10</td>
  <td class="vx">5</td>
</tr>
</table>'''

TF_MAGNET_HTML = '<a href="magnet:?xt=urn:btih:deadbeefcafe&dn=ubuntu-22.04&tr=udp://tracker.example.com:6969">Magnet</a>'

TF_TORRENT_HTML = '<a href="/download/ubuntu-22.04.torrent">Download .torrent</a>'

TF_NO_LINKS_HTML = "<html><body><p>Page content without download links</p></body></html>"


class TestParseResults:
    def test_single_result(self):
        mod, cap = _load_torrentfunk()
        mod._parse_results(TF_SINGLE)
        assert len(cap) == 1
        assert cap[0]["name"] == "Ubuntu Linux 22.04"
        assert cap[0]["link"] == "https://www.torrentfunk.com/torrent/12345/ubuntu-linux-2204"
        assert cap[0]["desc_link"] == cap[0]["link"]
        assert cap[0]["engine_url"] == "https://www.torrentfunk.com"
        assert cap[0]["seeds"] == "1250"
        assert cap[0]["leech"] == "320"
        assert "pub_date" in cap[0]
        assert "size" in cap[0]

    def test_multi_results(self):
        mod, cap = _load_torrentfunk()
        mod._parse_results(TF_MULTI)
        assert len(cap) == 2
        assert cap[0]["name"] == "Debian 12 Bookworm"
        assert cap[0]["seeds"] == "890"
        assert cap[1]["name"] == "Fedora 40"
        assert cap[1]["seeds"] == "670"

    def test_empty_html(self):
        mod, cap = _load_torrentfunk()
        mod._parse_results(TF_EMPTY)
        assert len(cap) == 0

    def test_malformed_row_skipped(self):
        mod, cap = _load_torrentfunk()
        mod._parse_results(TF_MALFORMED)
        assert len(cap) == 0

    def test_mixed_valid_and_invalid_rows(self):
        mod, cap = _load_torrentfunk()
        mod._parse_results(TF_MIXED_TRACKER_ROWS)
        assert len(cap) == 1
        assert cap[0]["name"] == "CentOS Stream"

    def test_nondigit_seeds_and_leech_fallback_to_zero(self):
        mod, cap = _load_torrentfunk()
        mod._parse_results(TF_NONDIGIT_SEEDS)
        assert len(cap) == 1
        assert cap[0]["seeds"] == "0"
        assert cap[0]["leech"] == "0"

    def test_size_parsed_for_bytes_unit(self):
        mod, cap = _load_torrentfunk()
        mod._parse_results(TF_SINGLE_BYTES)
        assert len(cap) == 1
        assert cap[0]["size"] == "1024"

    def test_extra_columns_parsed(self):
        mod, cap = _load_torrentfunk()
        mod._parse_results(TF_EXTRA_COLUMNS)
        assert len(cap) == 1
        assert cap[0]["name"] == "openSUSE Tumbleweed"
        assert cap[0]["seeds"] == "2100"
        assert cap[0]["leech"] == "98"


class TestParseSize:
    def setup_method(self):
        self.mod, _ = _load_torrentfunk()

    def test_bytes(self):
        assert self.mod._parse_size("1024 B") == 1024

    def test_kilobytes_fails_first_unit_match(self):
        assert self.mod._parse_size("512 KB") == 512 * 1024

    def test_megabytes_fails_first_unit_match(self):
        assert self.mod._parse_size("750.5 MB") == int(750.5 * 1024**2)

    def test_gigabytes_fails_first_unit_match(self):
        assert self.mod._parse_size("4.7 GB") == int(4.7 * 1024**3)

    def test_terabytes_fails_first_unit_match(self):
        assert self.mod._parse_size("1.5 TB") == int(1.5 * 1024**4)

    def test_garbage_returns_zero(self):
        assert self.mod._parse_size("unknown") == 0

    def test_empty_string_returns_zero(self):
        assert self.mod._parse_size("") == 0

    def test_comma_in_number_fails_first_unit_match(self):
        assert self.mod._parse_size("1,024 MB") == 1024 * 1024**2

    def test_uppercase_normalization(self):
        assert self.mod._parse_size("  10.0 Gb  ") == int(10.0 * 1024**3)

    def test_no_unit_returns_zero(self):
        assert self.mod._parse_size("12345") == 0

    def test_whitespace_only_returns_zero(self):
        assert self.mod._parse_size("   ") == 0


class TestSearch:
    def setup_method(self):
        self.mod, self.cap = _load_torrentfunk()

    @patch("torrentfunk.retrieve_url", return_value=TF_SINGLE)
    def test_search_all_category(self, mock_retrieve):
        self.mod.search("ubuntu", "all")
        called_url = mock_retrieve.call_args[0][0]
        assert called_url == "https://www.torrentfunk.com/all/torrents/ubuntu.html"

    @patch("torrentfunk.retrieve_url", return_value=TF_SINGLE)
    def test_search_unknown_category_falls_back_to_all(self, mock_retrieve):
        self.mod.search("linux", "nonexistent")
        called_url = mock_retrieve.call_args[0][0]
        assert called_url == "https://www.torrentfunk.com/all/torrents/linux.html"

    @patch("torrentfunk.retrieve_url", return_value=TF_SINGLE)
    def test_search_url_encodes_special_characters(self, mock_retrieve):
        self.mod.search("ubuntu 22.04 server", "all")
        called_url = mock_retrieve.call_args[0][0]
        assert "ubuntu%2022.04%20server" in called_url

    @patch("torrentfunk.retrieve_url", return_value=TF_SINGLE)
    def test_search_results_emitted(self, mock_retrieve):
        self.mod.search("ubuntu", "all")
        assert len(self.cap) == 1
        assert self.cap[0]["name"] == "Ubuntu Linux 22.04"

    @patch("torrentfunk.retrieve_url", side_effect=Exception("network error"))
    def test_search_exception_does_not_crash(self, mock_retrieve):
        self.mod.search("ubuntu", "all")
        assert len(self.cap) == 0

    @patch("torrentfunk.retrieve_url", return_value=TF_SINGLE)
    def test_search_movies_category_same_url_all(self, mock_retrieve):
        self.mod.search("inception", "movies")
        called_url = mock_retrieve.call_args[0][0]
        assert called_url == "https://www.torrentfunk.com/all/torrents/inception.html"

    @patch("torrentfunk.retrieve_url", return_value=TF_SINGLE)
    def test_search_url_encodes_unicode(self, mock_retrieve):
        self.mod.search("tést", "all")
        called_url = mock_retrieve.call_args[0][0]
        assert "t%C3%A9st" in called_url


class TestDownloadTorrent:
    def setup_method(self):
        self.mod, self.cap = _load_torrentfunk()

    @patch("torrentfunk.retrieve_url")
    def test_download_magnet_link(self, mock_retrieve, capsys):
        mock_retrieve.return_value = TF_MAGNET_HTML
        self.mod.download_torrent("https://www.torrentfunk.com/torrent/12345/ubuntu")
        out = capsys.readouterr().out
        assert "magnet:?xt=urn:btih:deadbeefcafe" in out
        assert "https://www.torrentfunk.com/torrent/12345/ubuntu" in out

    @patch("torrentfunk.retrieve_url")
    def test_download_torrent_file(self, mock_retrieve, capsys):
        mock_retrieve.return_value = TF_TORRENT_HTML
        self.mod.download_torrent("https://www.torrentfunk.com/torrent/999/gentoo")
        out = capsys.readouterr().out
        assert "https://www.torrentfunk.com/download/ubuntu-22.04.torrent" in out
        assert "https://www.torrentfunk.com/torrent/999/gentoo" in out

    @patch("torrentfunk.retrieve_url", side_effect=Exception("network error"))
    def test_download_exception_exits(self, mock_retrieve):
        with pytest.raises(SystemExit):
            self.mod.download_torrent("https://www.torrentfunk.com/torrent/123/page")

    @patch("torrentfunk.retrieve_url", return_value=TF_NO_LINKS_HTML)
    def test_download_no_magnet_no_torrent(self, mock_retrieve, capsys):
        self.mod.download_torrent("https://www.torrentfunk.com/torrent/123/page")
        out = capsys.readouterr().out
        assert out.strip() == ""

    @patch("torrentfunk.retrieve_url")
    def test_download_magnet_precedes_torrent(self, mock_retrieve, capsys):
        html = '<a href="magnet:?xt=urn:btih:first">Magnet</a><a href="/download/file.torrent">DL</a>'
        mock_retrieve.return_value = html
        self.mod.download_torrent("https://www.torrentfunk.com/torrent/1/x")
        out = capsys.readouterr().out
        assert "magnet" in out
        assert "file.torrent" not in out
