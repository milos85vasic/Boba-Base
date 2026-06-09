"""Deep coverage tests for plugins/community/xfsub.py.

Covers: _parse_results (table rows, single/multi, malformed, non-numeric seeds/leech),
_parse_size (all units, edge cases, comma, whitespace), search (URL construction,
category mapping, exception handling), download_torrent (magnet link, .torrent,
no links, URLError -> sys.exit).
"""

import importlib.util
import os
import sys
import types
from unittest.mock import patch

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PLUGINS_DIR = os.path.join(REPO, "plugins", "community")


def _load_xfsub(captured=None):
    """Import xfsub plugin with stub modules. Returns (instance, captured)."""
    if captured is None:
        captured = []
    np_mod = types.ModuleType("novaprinter")
    np_mod.prettyPrinter = lambda d: captured.append(dict(d))
    sys.modules["novaprinter"] = np_mod

    helpers_mod = types.ModuleType("helpers")
    helpers_mod.retrieve_url = lambda url: ""
    sys.modules["helpers"] = helpers_mod

    sys.modules.pop("xfsub", None)

    path = os.path.join(PLUGINS_DIR, "xfsub.py")
    spec = importlib.util.spec_from_file_location("xfsub", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules["xfsub"] = mod
    cls = getattr(mod, "xfsub", None)
    if cls is not None and isinstance(cls, type):
        return cls(), captured
    return mod, captured


# ─── HTML fixtures matching the <tr> regex with re.S|re.I ────────────────
# Pattern: <tr>...<a href="/torrent/...">NAME</a>...<td>SIZE</td>
# <td>SEEDS</td><td>LEECH</td><td>DATE</td></tr>

XF_SINGLE = '''<html><body><table>
<tr><td><a href="/torrent/12345/naruto-shippuden">Naruto Shippuden</a></td>
<td>1.5 GB</td><td>120</td><td>45</td><td>2025-06-01</td></tr>
</table></body></html>'''

XF_MULTI = '''<html><body><table>
<tr><td><a href="/torrent/1/one-piece">One Piece</a></td>
<td>2.0 GB</td><td>200</td><td>30</td><td>2025-01-01</td></tr>
<tr><td><a href="/torrent/2/bleach">Bleach</a></td>
<td>750 MB</td><td>85</td><td>12</td><td>2024-12-15</td></tr>
<tr><td><a href="/torrent/3/aot">Attack on Titan</a></td>
<td>3.2 GB</td><td>310</td><td>67</td><td>2025-06-08</td></tr>
</table></body></html>'''

XF_EMPTY = '<html><body><p>No results found.</p></body></html>'

XF_MALFORMED = '''<html><body><table>
<tr><td>Missing anchor</td><td>1 GB</td><td>5</td><td>2</td><td>2025-01-01</td></tr>
</table></body></html>'''

XF_NON_NUMERIC_SEEDS = '''<html><body><table>
<tr><td><a href="/torrent/99/generic">Generic Anime</a></td>
<td>500 MB</td><td>N/A</td><td>-</td><td>2025-01-01</td></tr>
</table></body></html>'''

XF_SMALL_SIZE = '''<html><body><table>
<tr><td><a href="/torrent/42/small">Small Sub</a></td>
<td>512 KB</td><td>10</td><td>2</td><td>2025-06-01</td></tr>
</table></body></html>'''

XF_BYTE_SIZE = '''<html><body><table>
<tr><td><a href="/torrent/43/tiny">Tiny Sub</a></td>
<td>1024 B</td><td>1</td><td>0</td><td>2025-06-01</td></tr>
</table></body></html>'''

XF_TB_SIZE = '''<html><body><table>
<tr><td><a href="/torrent/44/huge">Huge Sub</a></td>
<td>1.5 TB</td><td>50</td><td>20</td><td>2025-06-01</td></tr>
</table></body></html>'''

XF_WHITESPACE_DIRTY = '''<html><body><table>
<tr>
<td>  <a href="/torrent/77/extra">  Extra Spaced Title  </a>  </td>
<td>   4.5 GB   </td><td>  33  </td><td>  7  </td><td>  2025-01-15  </td>
</tr></table></body></html>'''

XF_MAGNET_HTML = '''<html><body>
<p>Some page content</p>
<a href="magnet:?xt=urn:btih:deadbeef&dn=xfsub-test">Magnet</a>
</body></html>'''

XF_TORRENT_HTML = '''<html><body>
<p>Download page</p>
<a href="/download/torrent/12345.torrent">Download</a>
</body></html>'''

XF_NO_LINKS_HTML = '<html><body><p>No download links available.</p></body></html>'

XF_COMMA_SIZE = '''<html><body><table>
<tr><td><a href="/torrent/55/comma">Comma Size</a></td>
<td>1,024 MB</td><td>20</td><td>5</td><td>2025-06-01</td></tr>
</table></body></html>'''


class TestParseResults:
    def setup_method(self):
        self.mod, self.cap = _load_xfsub()

    def test_single_result(self):
        self.mod._parse_results(XF_SINGLE)
        assert len(self.cap) == 1
        r = self.cap[0]
        assert r["name"] == "Naruto Shippuden"
        assert r["link"] == "https://www.xfsub.com/torrent/12345/naruto-shippuden"
        assert r["desc_link"] == r["link"]
        assert r["engine_url"] == "https://www.xfsub.com"
        assert r["seeds"] == "120"
        assert r["leech"] == "45"

    def test_multi_results(self):
        self.mod._parse_results(XF_MULTI)
        assert len(self.cap) == 3
        assert self.cap[0]["name"] == "One Piece"
        assert self.cap[1]["name"] == "Bleach"
        assert self.cap[2]["name"] == "Attack on Titan"

    def test_empty_html(self):
        self.mod._parse_results(XF_EMPTY)
        assert len(self.cap) == 0

    def test_malformed_row_skipped(self):
        self.mod._parse_results(XF_MALFORMED)
        assert len(self.cap) == 0

    def test_non_numeric_seeds_leech_default_to_zero(self):
        self.mod._parse_results(XF_NON_NUMERIC_SEEDS)
        assert len(self.cap) == 1
        assert self.cap[0]["seeds"] == "0"
        assert self.cap[0]["leech"] == "0"

    def test_size_parsed_correctly_b(self):
        self.mod._parse_results(XF_BYTE_SIZE)
        assert self.cap[0]["size"] == "1024"

    def test_gb_size_parses(self):
        self.mod._parse_results(XF_SINGLE)
        assert self.cap[0]["size"] == str(int(1.5 * 1024**3))

    def test_whitespace_stripped(self):
        self.mod._parse_results(XF_WHITESPACE_DIRTY)
        assert len(self.cap) == 1
        assert self.cap[0]["name"] == "Extra Spaced Title"
        assert self.cap[0]["seeds"] == "33"


class TestParseSize:
    def setup_method(self):
        self.mod, _ = _load_xfsub()

    def test_bytes(self):
        assert self.mod._parse_size("1024 B") == 1024

    def test_all_units_parse(self):
        assert self.mod._parse_size("512 KB") == 512 * 1024
        assert self.mod._parse_size("750 MB") == int(750 * 1024**2)
        assert self.mod._parse_size("1.5 GB") == int(1.5 * 1024**3)
        assert self.mod._parse_size("1.5 TB") == int(1.5 * 1024**4)
        assert self.mod._parse_size("1,024 MB") == 1024 * 1024**2
        assert self.mod._parse_size("  10.0 Gb  ") == int(10.0 * 1024**3)

    def test_garbage_returns_zero(self):
        assert self.mod._parse_size("unknown") == 0

    def test_empty_string_returns_zero(self):
        assert self.mod._parse_size("") == 0


class TestSearch:
    def setup_method(self):
        self.mod, self.cap = _load_xfsub()

    @patch("xfsub.retrieve_url", return_value=XF_SINGLE)
    def test_search_all_category_url(self, mock_retrieve):
        self.mod.search("naruto", "all")
        called_url = mock_retrieve.call_args[0][0]
        assert called_url == "https://www.xfsub.com/search/?keyword=naruto"

    @patch("xfsub.retrieve_url", return_value=XF_SINGLE)
    def test_search_anime_category_url(self, mock_retrieve):
        self.mod.search("naruto", "anime")
        called_url = mock_retrieve.call_args[0][0]
        assert called_url == "https://www.xfsub.com/search/?keyword=naruto"

    @patch("xfsub.retrieve_url", return_value=XF_SINGLE)
    def test_search_special_characters_url_encoded(self, mock_retrieve):
        self.mod.search("naruto shippuden", "all")
        called_url = mock_retrieve.call_args[0][0]
        assert "naruto%20shippuden" in called_url

    @patch("xfsub.retrieve_url", return_value=XF_SINGLE)
    def test_search_results_emitted(self, mock_retrieve):
        self.mod.search("naruto", "all")
        assert len(self.cap) == 1
        assert self.cap[0]["name"] == "Naruto Shippuden"

    @patch("xfsub.retrieve_url", side_effect=Exception("network error"))
    def test_search_exception_does_not_crash(self, mock_retrieve):
        self.mod.search("naruto", "all")
        assert len(self.cap) == 0

    def test_class_metadata(self):
        assert self.mod.url == "https://www.xfsub.com"
        assert self.mod.name == "Xfsub"
        assert self.mod.supported_categories == {"all": "0", "anime": "1"}


class TestDownloadTorrent:
    def setup_method(self):
        self.mod, _ = _load_xfsub()

    @patch("xfsub.retrieve_url")
    def test_download_magnet_link(self, mock_retrieve, capsys):
        mock_retrieve.return_value = XF_MAGNET_HTML
        self.mod.download_torrent("https://www.xfsub.com/torrent/12345")
        out = capsys.readouterr().out
        assert "magnet:?xt=urn:btih:deadbeef&dn=xfsub-test" in out
        assert "https://www.xfsub.com/torrent/12345" in out

    @patch("xfsub.retrieve_url")
    def test_download_torrent_file(self, mock_retrieve, capsys):
        mock_retrieve.return_value = XF_TORRENT_HTML
        self.mod.download_torrent("https://www.xfsub.com/torrent/12345")
        out = capsys.readouterr().out
        assert "https://www.xfsub.com/download/torrent/12345.torrent" in out
        assert "https://www.xfsub.com/torrent/12345" in out

    @patch("xfsub.retrieve_url", side_effect=Exception("network error"))
    def test_download_exception_exits_with_code_1(self, mock_retrieve):
        with pytest.raises(SystemExit) as exc_info:
            self.mod.download_torrent("https://www.xfsub.com/torrent/12345")
        assert exc_info.value.code == 1

    @patch("xfsub.retrieve_url", return_value=XF_NO_LINKS_HTML)
    def test_download_no_magnet_no_torrent_prints_nothing(self, mock_retrieve, capsys):
        self.mod.download_torrent("https://www.xfsub.com/torrent/12345")
        out = capsys.readouterr().out
        assert out.strip() == ""

    @patch("xfsub.retrieve_url")
    def test_download_prefers_magnet_over_torrent(self, mock_retrieve, capsys):
        html = '''<html><body>
        <a href="magnet:?xt=urn:btih:first">Magnet First</a>
        <a href="/download/second.torrent">Download</a>
        </body></html>'''
        mock_retrieve.return_value = html
        self.mod.download_torrent("https://www.xfsub.com/torrent/99")
        out = capsys.readouterr().out
        assert "magnet:?xt=urn:btih:first" in out
        assert "/download/second.torrent" not in out

    @patch("xfsub.retrieve_url")
    def test_download_falls_back_to_torrent_when_no_magnet(self, mock_retrieve, capsys):
        mock_retrieve.return_value = XF_TORRENT_HTML
        self.mod.download_torrent("https://www.xfsub.com/torrent/12345")
        out = capsys.readouterr().out
        assert "https://www.xfsub.com/download/torrent/12345.torrent" in out


def test_module_alias():
    mod, _ = _load_xfsub()
    loaded = sys.modules["xfsub"]
    cls = getattr(loaded, "xfsub", None)
    assert cls is not None
    assert isinstance(cls, type)
    assert cls.__name__ == "xfsub"
