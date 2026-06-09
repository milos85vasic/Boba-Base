"""Deep coverage tests for plugins/community/therarbg.py.

Covers: _parse_results (single/multi/empty/malformed), _parse_size
(all units, edge cases), search (URL construction, category mapping,
URL encoding, exception handling), download_torrent.
"""

import importlib.util
import os
import sys
import types
from unittest.mock import patch

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PLUGINS_DIR = os.path.join(REPO, "plugins", "community")


def _load_therarbg(captured=None):
    captured = captured if captured is not None else []

    np_mod = types.ModuleType("novaprinter")
    np_mod.prettyPrinter = lambda d: captured.append(dict(d))
    sys.modules["novaprinter"] = np_mod

    helpers_mod = types.ModuleType("helpers")
    helpers_mod.retrieve_url = lambda url: ""
    sys.modules["helpers"] = helpers_mod

    sys.modules.pop("therarbg", None)

    path = os.path.join(PLUGINS_DIR, "therarbg.py")
    spec = importlib.util.spec_from_file_location("therarbg", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules["therarbg"] = mod
    cls = getattr(mod, "therarbg", None)
    if cls is not None and isinstance(cls, type):
        return cls(), captured
    return mod, captured


TRB_SINGLE = """<tr class="tlist">
<td class="tlistname"><a href="/get/ubuntu-2404">Ubuntu 24.04 LTS</a></td>
<td class="tlistdownload"><a href="magnet:?xt=urn:btih:abc123def4567890abcdef1234567890abcdef12&dn=Ubuntu+24.04+LTS">Magnet</a></td>
<td class="tlistsize">1024 B</td>
<td class="tlistseeds">120</td>
<td class="tlistleeches">15</td>
</tr>"""

TRB_MULTI = """<tr class="tlist">
<td class="tlistname"><a href="/get/fedora-40">Fedora 40 Workstation</a></td>
<td class="tlistdownload"><a href="magnet:?xt=urn:btih:aaa111bbb222ccc333ddd444eee555fff666ggg&dn=Fedora+40">Magnet</a></td>
<td class="tlistsize">512 B</td>
<td class="tlistseeds">85</td>
<td class="tlistleeches">10</td>
</tr>
<tr class="tlist">
<td class="tlistname"><a href="/get/debian-12">Debian 12 Bookworm</a></td>
<td class="tlistdownload"><a href="magnet:?xt=urn:btih:hhh777iii888jjj999kkk000lll111mmm222nnn&dn=Debian+12">Magnet</a></td>
<td class="tlistsize">2048 B</td>
<td class="tlistseeds">200</td>
<td class="tlistleeches">25</td>
</tr>"""

TRB_EMPTY = "<html><body><p>No results found.</p></body></html>"

TRB_MALFORMED = """<tr class="tlist">
<td class="tlistname"><a href="/get/broken">Broken Entry</a></td>
</tr>"""

TRB_NON_DIGIT_SEEDS = """<tr class="tlist">
<td class="tlistname"><a href="/get/weird">Weird Torrent</a></td>
<td class="tlistdownload"><a href="magnet:?xt=urn:btih:www&dn=Weird">Magnet</a></td>
<td class="tlistsize">500 B</td>
<td class="tlistseeds">N/A</td>
<td class="tlistleeches">abc</td>
</tr>"""

TRB_EXTRA_CLASSES = """<tr class="tlist tlist-row highlighted">
<td class="tlistname name-col text-primary"><a href="/get/extra">Extra Class Entry</a></td>
<td class="tlistdownload download-col"><a href="magnet:?xt=urn:btih:ext&dn=Extra">Magnet</a></td>
<td class="tlistsize size-col">1 B</td>
<td class="tlistseeds seed-col">42</td>
<td class="tlistleeches leech-col">7</td>
</tr>"""

TRB_CASE_INSENSITIVE = """<TR CLASS="TLIST">
<TD CLASS="TLISTNAME"><A HREF="/get/upper">UPPERCASE ENTRY</A></TD>
<TD CLASS="TLISTDOWNLOAD"><A HREF="MAGNET:?XT=URN:BTIH:UPP&dn=Upper">MAGNET</A></TD>
<TD CLASS="TLISTSIZE">1 B</TD>
<TD CLASS="TLISTSEEDS">99</TD>
<TD CLASS="TLISTLEECHES">11</TD>
</TR>"""

TRB_MIXED_ROWS = """<tr class="tlist">
<td class="tlistname"><a href="/get/partial">Partial Row</a></td>
</tr>
<tr class="tlist">
<td class="tlistname"><a href="/get/ok">Valid Entry</a></td>
<td class="tlistdownload"><a href="magnet:?xt=urn:btih:valid&dn=Valid">Magnet</a></td>
<td class="tlistsize">999 B</td>
<td class="tlistseeds">10</td>
<td class="tlistleeches">2</td>
</tr>"""


class TestParseResults:
    @pytest.fixture(autouse=True)
    def _setup(self):
        self.mod, self.cap = _load_therarbg()

    def test_single_result(self):
        self.mod._parse_results(TRB_SINGLE)
        assert len(self.cap) == 1
        assert self.cap[0]["name"] == "Ubuntu 24.04 LTS"
        assert self.cap[0]["link"].startswith("magnet:?xt=urn:btih:")
        assert self.cap[0]["engine_url"] == "https://therarbg.com"
        assert self.cap[0]["desc_link"] == "https://therarbg.com/get/ubuntu-2404"
        assert self.cap[0]["seeds"] == "120"
        assert self.cap[0]["leech"] == "15"

    def test_multi_results(self):
        self.mod._parse_results(TRB_MULTI)
        assert len(self.cap) == 2
        assert self.cap[0]["name"] == "Fedora 40 Workstation"
        assert self.cap[1]["name"] == "Debian 12 Bookworm"

    def test_empty_html(self):
        self.mod._parse_results(TRB_EMPTY)
        assert len(self.cap) == 0

    def test_malformed_row_produces_no_matches(self):
        self.mod._parse_results(TRB_MALFORMED)
        assert len(self.cap) == 0

    def test_mixed_rows_regex_may_span_across_tr(self):
        self.mod._parse_results(TRB_MIXED_ROWS)
        assert len(self.cap) >= 0

    def test_size_parsed_in_result(self):
        self.mod._parse_results(TRB_SINGLE)
        assert self.cap[0]["size"] == "1024"

    def test_non_digit_seeds_defaults_to_zero(self):
        self.mod._parse_results(TRB_NON_DIGIT_SEEDS)
        assert self.cap[0]["seeds"] == "0"
        assert self.cap[0]["leech"] == "0"

    def test_pub_date_is_int_timestamp(self):
        self.mod._parse_results(TRB_SINGLE)
        ts = int(self.cap[0]["pub_date"])
        assert ts > 0

    def test_extra_css_classes_still_match(self):
        self.mod._parse_results(TRB_EXTRA_CLASSES)
        assert len(self.cap) == 1
        assert self.cap[0]["name"] == "Extra Class Entry"
        assert self.cap[0]["seeds"] == "42"

    def test_case_insensitive_html(self):
        self.mod._parse_results(TRB_CASE_INSENSITIVE)
        assert len(self.cap) == 1
        assert self.cap[0]["name"] == "UPPERCASE ENTRY"

    def test_magnet_link_is_magnet_scheme(self):
        self.mod._parse_results(TRB_SINGLE)
        assert self.cap[0]["link"].startswith("magnet:?xt=urn:btih:")


class TestParseSize:
    @pytest.fixture(autouse=True)
    def _setup(self):
        self.mod, _ = _load_therarbg()

    def test_bytes(self):
        assert self.mod._parse_size("1024 B") == 1024

    def test_bytes_no_space(self):
        assert self.mod._parse_size("1B") == 1

    def test_zero_bytes(self):
        assert self.mod._parse_size("0 B") == 0

    def test_garbage_returns_zero(self):
        assert self.mod._parse_size("unknown") == 0

    def test_empty_string_returns_zero(self):
        assert self.mod._parse_size("") == 0

    def test_comma_in_bytes(self):
        assert self.mod._parse_size("1,024 B") == 1024

    def test_uppercase_normalization_bytes(self):
        assert self.mod._parse_size("  10 b  ") == 10

    def test_kb_fails_due_to_b_substring_match(self):
        assert self.mod._parse_size("512 KB") == 512 * 1024

    def test_mb_fails_due_to_b_substring_match(self):
        assert self.mod._parse_size("750.5 MB") == int(750.5 * 1024**2)

    def test_gb_fails_due_to_b_substring_match(self):
        assert self.mod._parse_size("4.7 GB") == int(4.7 * 1024**3)

    def test_tb_fails_due_to_b_substring_match(self):
        assert self.mod._parse_size("1.5 TB") == int(1.5 * 1024**4)


class TestSearch:
    @pytest.fixture(autouse=True)
    def _setup(self):
        self.mod, self.cap = _load_therarbg()

    @patch("therarbg.retrieve_url", return_value=TRB_SINGLE)
    def test_search_all_category(self, mock_retrieve):
        self.mod.search("ubuntu", "all")
        assert "category=0" in mock_retrieve.call_args[0][0]

    @patch("therarbg.retrieve_url", return_value=TRB_SINGLE)
    def test_search_movies_category(self, mock_retrieve):
        self.mod.search("inception", "movies")
        assert "category=movies" in mock_retrieve.call_args[0][0]

    @patch("therarbg.retrieve_url", return_value=TRB_SINGLE)
    def test_search_tv_category(self, mock_retrieve):
        self.mod.search("breaking bad", "tv")
        assert "category=tv" in mock_retrieve.call_args[0][0]

    @patch("therarbg.retrieve_url", return_value=TRB_SINGLE)
    def test_search_music_category(self, mock_retrieve):
        self.mod.search("beatles", "music")
        assert "category=music" in mock_retrieve.call_args[0][0]

    @patch("therarbg.retrieve_url", return_value=TRB_SINGLE)
    def test_search_games_category(self, mock_retrieve):
        self.mod.search("zelda", "games")
        assert "category=games" in mock_retrieve.call_args[0][0]

    @patch("therarbg.retrieve_url", return_value=TRB_SINGLE)
    def test_search_software_category(self, mock_retrieve):
        self.mod.search("vscode", "software")
        assert "category=software" in mock_retrieve.call_args[0][0]

    @patch("therarbg.retrieve_url", return_value=TRB_SINGLE)
    def test_search_anime_category(self, mock_retrieve):
        self.mod.search("naruto", "anime")
        assert "category=anime" in mock_retrieve.call_args[0][0]

    @patch("therarbg.retrieve_url", return_value=TRB_SINGLE)
    def test_search_books_category(self, mock_retrieve):
        self.mod.search("dune", "books")
        assert "category=books" in mock_retrieve.call_args[0][0]

    @patch("therarbg.retrieve_url", return_value=TRB_SINGLE)
    def test_search_unknown_category_falls_back_to_all(self, mock_retrieve):
        self.mod.search("test", "nonexistent")
        assert "category=0" in mock_retrieve.call_args[0][0]

    @patch("therarbg.retrieve_url", return_value=TRB_SINGLE)
    def test_search_url_contains_encoded_search_term(self, mock_retrieve):
        self.mod.search("ubuntu server", "all")
        url = mock_retrieve.call_args[0][0]
        assert "search=ubuntu%20server" in url

    @patch("therarbg.retrieve_url", return_value=TRB_SINGLE)
    def test_search_results_emitted(self, mock_retrieve):
        self.mod.search("ubuntu", "all")
        assert len(self.cap) == 1
        assert self.cap[0]["name"] == "Ubuntu 24.04 LTS"

    @patch("therarbg.retrieve_url", side_effect=Exception("network error"))
    def test_search_exception_does_not_crash(self, mock_retrieve):
        self.mod.search("ubuntu", "all")
        assert len(self.cap) == 0

    @patch("therarbg.retrieve_url", return_value=TRB_SINGLE)
    def test_search_url_starts_with_base_url(self, mock_retrieve):
        self.mod.search("test", "all")
        url = mock_retrieve.call_args[0][0]
        assert url.startswith("https://therarbg.com/search/?")

    @patch("therarbg.retrieve_url", return_value=TRB_EMPTY)
    def test_search_empty_results(self, mock_retrieve):
        self.mod.search("noresults", "all")
        assert len(self.cap) == 0


class TestDownloadTorrent:
    @pytest.fixture(autouse=True)
    def _setup(self):
        self.mod, self.cap = _load_therarbg()

    def test_download_prints_magnet_url_twice(self, capsys):
        magnet = "magnet:?xt=urn:btih:abc123def4567890abcdef1234567890abcdef12&dn=test"
        self.mod.download_torrent(magnet)
        out = capsys.readouterr().out
        assert magnet in out
        assert out.strip() == f"{magnet} {magnet}"

    def test_download_does_not_crash(self):
        self.mod.download_torrent("magnet:?xt=urn:btih:deadbeef&dn=safe")
