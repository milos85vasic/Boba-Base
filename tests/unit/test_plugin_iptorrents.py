"""Deep coverage tests for plugins/iptorrents.py.

Covers: credential loading (env + file), login paths (no creds, URLError),
_get_link (no session, charset parsing, URLError), search_parse (HTML parsing,
pagination, no table, no data), search_freeleech/search URL construction,
download_torrent (gzip, no session, URLError).
"""

import gzip
import importlib.util
import os
import re
import sys
import tempfile
import types
from http.cookiejar import CookieJar
from unittest.mock import MagicMock, patch

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PLUGINS_DIR = os.path.join(REPO, "plugins")


def _load_iptorrents():
    """Import iptorrents plugin with stub modules."""
    captured = []
    np_mod = types.ModuleType("novaprinter")
    np_mod.prettyPrinter = lambda d: captured.append(dict(d))

    class _SR:
        pass

    np_mod.SearchResults = _SR
    sys.modules["novaprinter"] = np_mod

    helpers_mod = types.ModuleType("helpers")
    helpers_mod.htmlentitydecode = lambda s: s
    helpers_mod.retrieve_url = lambda url: ""
    sys.modules["helpers"] = helpers_mod

    sys.modules.pop("iptorrents", None)
    sys.modules.pop("env_loader", None)

    path = os.path.join(PLUGINS_DIR, "iptorrents.py")
    spec = importlib.util.spec_from_file_location("iptorrents", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules["iptorrents"] = mod
    return mod, captured


# ─── HTML fixtures (matching the exact regex in iptorrents.py) ──────────
# BOB-083: IPTorrents changed its results markup -- the table id attribute
# is now quoted (`<table id="torrents">`), description links are `/t/<id>`
# (not `/details.php?id=...`), and the seed/leech/snatch cells carry NO css
# class at all any more (the `t_seeders`/`t_leechers` classes were removed
# outright) -- they are three bare positional `<td>N` cells, in
# Snatches/Seeders/Leechers order, immediately before `</tr>`, matching the
# table's own <thead> column order. These fixtures mirror a real captured
# response from https://iptorrents.com (2026-08-19, credentials/session
# redacted) -- see docs/qa/task-bob083-fix/ for the full evidence trail.

IPT_SINGLE_ROW = (
    '<form><table id="torrents"><thead><tr><th>Type<th>Name<th>Bookmark<th>DL'
    "<th>Comments<th>Size<th>Files<th>Snatches<th>Seeders<th>Leechers<tbody>"
    '<tr><td class="i p72"><td class="al">'
    '<a class=" hv" href="/t/12345">Ubuntu 24.04 LTS</a>'
    '<div class="sub">1080p | 1 day ago</div>'
    '<td><a href="/t/12345?bookmark" class="tTipWrap">bm</a>'
    '<td><a href="/download.php/12345/file.torrent" class="tTipWrap">dl</a>'
    '<td><a href="/t/12345?page=0#startcomments" class="tTipWrap">0</a>'
    "<td>1.2 GB"
    '<td><a href="/t/12345/files" class="tTipWrap">1</a>'
    "<td>50<td>500<td>25</tr></table></form>"
)

IPT_MULTI_ROW = (
    '<form><table id="torrents"><thead><tr><th>Type<th>Name<th>Bookmark<th>DL'
    "<th>Comments<th>Size<th>Files<th>Snatches<th>Seeders<th>Leechers<tbody>"
    '<tr><td class="i p72"><td class="al">'
    '<a class=" hv" href="/t/1">First Torrent</a>'
    '<div class="sub">info</div>'
    '<td><a href="/t/1?bookmark" class="tTipWrap">bm</a>'
    '<td><a href="/download.php/1/a.torrent" class="tTipWrap">dl</a>'
    '<td><a href="/t/1?page=0#startcomments" class="tTipWrap">0</a>'
    "<td>100 MB"
    '<td><a href="/t/1/files" class="tTipWrap">1</a>'
    "<td>3<td>10<td>2</tr>"
    '<tr><td class="i p72"><td class="al">'
    '<a class=" hv" href="/t/2">Second Torrent</a>'
    '<div class="sub">info</div>'
    '<td><a href="/t/2?bookmark" class="tTipWrap">bm</a>'
    '<td><a href="/download.php/2/b.torrent" class="tTipWrap">dl</a>'
    '<td><a href="/t/2?page=0#startcomments" class="tTipWrap">0</a>'
    "<td>500 MB"
    '<td><a href="/t/2/files" class="tTipWrap">1</a>'
    "<td>7<td>20<td>5</tr></table></form>"
)

IPT_FREELEECH = (
    '<form><table id="torrents"><thead><tr><th>Type<th>Name<th>Bookmark<th>DL'
    "<th>Comments<th>Size<th>Files<th>Snatches<th>Seeders<th>Leechers<tbody>"
    '<tr><td class="i p72"><td class="al">'
    '<a class=" hv" href="/t/99">Freeleech Movie</a> <span class="free">FreeLeech</span>'
    '<div class="sub">info</div>'
    '<td><a href="/t/99?bookmark" class="tTipWrap">bm</a>'
    '<td><a href="/download.php/99/x.torrent" class="tTipWrap">dl</a>'
    '<td><a href="/t/99?page=0#startcomments" class="tTipWrap">0</a>'
    "<td>2.5 GB"
    '<td><a href="/t/99/files" class="tTipWrap">1</a>'
    "<td>12<td>300<td>10</tr></table></form>"
)

IPT_PAGINATION = (
    '<form><table id="torrents"><thead><tr><th>Type<th>Name<th>Bookmark<th>DL'
    "<th>Comments<th>Size<th>Files<th>Snatches<th>Seeders<th>Leechers<tbody>"
    '<tr><td class="i p72"><td class="al">'
    '<a class=" hv" href="/t/1">Page1</a>'
    '<div class="sub">info</div>'
    '<td><a href="/t/1?bookmark" class="tTipWrap">bm</a>'
    '<td><a href="/download.php/1/p1.torrent" class="tTipWrap">dl</a>'
    '<td><a href="/t/1?page=0#startcomments" class="tTipWrap">0</a>'
    "<td>10 MB"
    '<td><a href="/t/1/files" class="tTipWrap">1</a>'
    "<td>1<td>5<td>1</tr></table></form><a>Page <b>1</b> of <b>2</b></a>"
)

IPT_PAGE2 = (
    '<form><table id="torrents"><thead><tr><th>Type<th>Name<th>Bookmark<th>DL'
    "<th>Comments<th>Size<th>Files<th>Snatches<th>Seeders<th>Leechers<tbody>"
    '<tr><td class="i p72"><td class="al">'
    '<a class=" hv" href="/t/2">Page2</a>'
    '<div class="sub">info</div>'
    '<td><a href="/t/2?bookmark" class="tTipWrap">bm</a>'
    '<td><a href="/download.php/2/p2.torrent" class="tTipWrap">dl</a>'
    '<td><a href="/t/2?page=0#startcomments" class="tTipWrap">0</a>'
    "<td>20 MB"
    '<td><a href="/t/2/files" class="tTipWrap">1</a>'
    "<td>2<td>8<td>3</tr></table></form><a>Page <b>2</b> of <b>2</b></a>"
)

IPT_NO_TABLE = "<html><body>no torrent table here</body></html>"

# BOB-083 regression guard: the OLD (pre-fix) markup shape -- unquoted
# `<table id=torrents>`, `/details.php?id=...` desc links, and
# `t_seeders`/`t_leechers` CSS classes. IPTorrents no longer emits ANY of
# these. A search_parse() that still relies on them (i.e. the pre-fix code)
# finds zero rows here despite the HTML clearly containing swarm data --
# this is the exact BOB-083 symptom, reproduced offline.
IPT_OBSOLETE_MARKUP_REAL_SWARM_DATA = (
    '<form><table id=torrents><tr><td><a class=" hv" href="/details.php?id=1">'
    'Real Movie With Real Swarm</a></td><td><a href="/download.php/1/x.torrent">dl</a>'
    '</td><td>4.2 GB</td><td class="t_seeders">39</td><td class="t_leechers">5</td></tr>'
    "</table></form>"
)


# ─── Tests ──────────────────────────────────────────────────────────────


class TestIptorrentsCredentialLoading:
    def test_load_credentials_from_env(self):
        mod, _ = _load_iptorrents()
        with patch.dict(os.environ, {"IPTORRENTS_USERNAME": "user1", "IPTORRENTS_PASSWORD": "pass1"}, clear=False):
            engine = mod.iptorrents.__new__(mod.iptorrents)
            engine._load_credentials()
            assert engine.username == "user1"
            assert engine.password == "pass1"

    def test_load_credentials_alt_env_vars(self):
        mod, _ = _load_iptorrents()
        with patch.dict(os.environ, {"IPTORRENTS_USER": "alt_user", "IPTORRENTS_PASS": "alt_pass"}, clear=False):
            engine = mod.iptorrents.__new__(mod.iptorrents)
            engine._load_credentials()
            assert engine.username == "alt_user"
            assert engine.password == "alt_pass"

    def test_load_env_file_skips_when_creds_present(self):
        mod, _ = _load_iptorrents()
        engine = mod.iptorrents.__new__(mod.iptorrents)
        engine.username = "already_set"
        engine.password = "already_set"
        engine._load_env_file()
        assert engine.username == "already_set"

    def test_load_env_file_fallback_to_manual_parsing(self):
        mod, _ = _load_iptorrents()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write("IPTORRENTS_USERNAME=file_user\nIPTORRENTS_PASSWORD=file_pass\n")
            path = f.name
        try:
            engine = mod.iptorrents.__new__(mod.iptorrents)
            engine.username = ""
            engine.password = ""
            with patch("os.path.isfile", return_value=False):
                with patch("builtins.__import__", side_effect=ImportError):
                    with patch.object(mod.os.path, "normpath", return_value=path):
                        with patch.object(mod.os.path, "isfile", return_value=True):
                            with patch("builtins.open", create=True) as mock_open:
                                mock_open.return_value.__enter__ = lambda s: s
                                mock_open.return_value.__exit__ = MagicMock(return_value=False)
                                mock_open.return_value.__iter__ = iter([
                                    "IPTORRENTS_USERNAME=file_user\n",
                                    "IPTORRENTS_PASSWORD=file_pass\n",
                                ])
                                engine._load_env_file()
        finally:
            os.unlink(path)

    def test_load_env_file_no_creds_and_no_file(self):
        mod, _ = _load_iptorrents()
        engine = mod.iptorrents.__new__(mod.iptorrents)
        engine.username = ""
        engine.password = ""
        with patch.dict(os.environ, {}, clear=True):
            engine._load_env_file()
        assert engine.username == ""
        assert engine.password == ""


class TestIptorrentsLogin:
    def test_login_no_credentials(self):
        mod, _ = _load_iptorrents()
        engine = mod.iptorrents.__new__(mod.iptorrents)
        engine.username = ""
        engine.password = ""
        engine.session = None
        engine._login()
        assert engine.session is None

    def test_login_success(self):
        mod, _ = _load_iptorrents()
        engine = mod.iptorrents.__new__(mod.iptorrents)
        engine.username = "user"
        engine.password = "pass"
        engine.session = None
        engine.ua = "test-ua"
        engine.url = "https://iptorrents.com"
        mock_opener = MagicMock()
        with patch.object(mod.request, "build_opener", return_value=mock_opener):
            engine._login()
        assert engine.session is mock_opener

    def test_login_url_error(self):
        mod, _ = _load_iptorrents()
        engine = mod.iptorrents.__new__(mod.iptorrents)
        engine.username = "user"
        engine.password = "pass"
        engine.session = None
        engine.ua = "test-ua"
        engine.url = "https://iptorrents.com"
        from urllib.error import URLError
        mock_opener = MagicMock()
        mock_opener.open.side_effect = URLError("connection refused")
        with patch.object(mod.request, "build_opener", return_value=mock_opener):
            engine._login()
        assert engine.session is None


class TestIptorrentsGetLink:
    def test_get_link_no_session(self):
        mod, _ = _load_iptorrents()
        engine = mod.iptorrents.__new__(mod.iptorrents)
        engine.session = None
        assert engine._get_link("http://example.com") == ""

    def test_get_link_url_error(self):
        mod, _ = _load_iptorrents()
        engine = mod.iptorrents.__new__(mod.iptorrents)
        from urllib.error import URLError
        engine.session = MagicMock()
        engine.session.open.side_effect = URLError("timeout")
        assert engine._get_link("http://example.com") == ""

    def test_get_link_charset_from_content_type(self):
        mod, _ = _load_iptorrents()
        engine = mod.iptorrents.__new__(mod.iptorrents)
        engine.session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.info.return_value.get.return_value = "text/html; charset=latin-1"
        mock_resp.read.return_value = b"hello"
        engine.session.open.return_value = mock_resp
        result = engine._get_link("http://example.com")
        assert result == "hello"

    def test_get_link_default_utf8(self):
        mod, _ = _load_iptorrents()
        engine = mod.iptorrents.__new__(mod.iptorrents)
        engine.session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.info.return_value.get.return_value = "text/html"
        mock_resp.read.return_value = b"hello"
        engine.session.open.return_value = mock_resp
        result = engine._get_link("http://example.com")
        assert result == "hello"

    def test_get_link_decompresses_gzip_body(self):
        """BOB-083 root cause: IPTorrents always gzips its response body,
        regardless of Accept-Encoding. Without decompression, _get_link()
        returns compressed binary "decoded" as text, and every downstream
        regex silently fails to match -- producing zero (or garbage)
        results despite the swarm data being present in the real body.
        """
        mod, _ = _load_iptorrents()
        engine = mod.iptorrents.__new__(mod.iptorrents)
        engine.session = MagicMock()
        original_html = '<table id="torrents">real content, seeders=91</table>'
        compressed = gzip.compress(original_html.encode("utf-8"))
        mock_resp = MagicMock()
        mock_resp.info.return_value.get.return_value = "text/html; charset=utf-8"
        mock_resp.read.return_value = compressed
        engine.session.open.return_value = mock_resp
        result = engine._get_link("http://example.com")
        assert result == original_html
        assert "seeders=91" in result

    def test_get_link_plain_body_not_mistaken_for_gzip(self):
        """A plain (non-gzip) body must pass through unchanged."""
        mod, _ = _load_iptorrents()
        engine = mod.iptorrents.__new__(mod.iptorrents)
        engine.session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.info.return_value.get.return_value = "text/html; charset=utf-8"
        mock_resp.read.return_value = b"<table id=\"torrents\">plain html</table>"
        engine.session.open.return_value = mock_resp
        result = engine._get_link("http://example.com")
        assert result == '<table id="torrents">plain html</table>'


class TestIptorrentsSearchParse:
    def _make_engine(self, mod, html_content):
        engine = mod.iptorrents.__new__(mod.iptorrents)
        engine.session = MagicMock()
        engine.url = "https://iptorrents.com"
        mock_resp = MagicMock()
        mock_resp.info.return_value.get.return_value = "text/html; charset=utf-8"
        mock_resp.read.return_value = html_content.encode("utf-8")
        engine.session.open.return_value = mock_resp
        return engine

    def test_search_parse_no_data(self):
        mod, captured = _load_iptorrents()
        engine = self._make_engine(mod, "")
        engine.search_parse("http://example.com")
        assert captured == []

    def test_search_parse_no_table(self):
        mod, captured = _load_iptorrents()
        engine = self._make_engine(mod, IPT_NO_TABLE)
        engine.search_parse("http://example.com")
        assert captured == []

    def test_search_parse_single_row(self):
        mod, captured = _load_iptorrents()
        engine = self._make_engine(mod, IPT_SINGLE_ROW)
        engine.search_parse("http://example.com")
        assert len(captured) == 1
        assert captured[0]["name"] == "Ubuntu 24.04 LTS"
        assert captured[0]["seeds"] == "500"
        assert captured[0]["leech"] == "25"
        assert captured[0]["size"] == "1.2 GB"
        assert "iptorrents.com" in captured[0]["link"]

    def test_search_parse_multi_row(self):
        mod, captured = _load_iptorrents()
        engine = self._make_engine(mod, IPT_MULTI_ROW)
        engine.search_parse("http://example.com")
        assert len(captured) == 2
        assert captured[0]["name"] == "First Torrent"
        assert captured[0]["seeds"] == "10"
        assert captured[0]["leech"] == "2"
        assert captured[1]["name"] == "Second Torrent"
        assert captured[1]["seeds"] == "20"
        assert captured[1]["leech"] == "5"

    def test_search_parse_freeleech_tagged(self):
        mod, captured = _load_iptorrents()
        engine = self._make_engine(mod, IPT_FREELEECH)
        engine.search_parse("http://example.com")
        assert len(captured) == 1
        assert "Freeleech Movie" in captured[0]["name"]
        assert captured[0]["seeds"] == "300"
        assert captured[0]["leech"] == "10"

    def test_search_parse_non_freeleech_row_has_no_free_tag(self):
        """A row with no <span class="free"> must not be mistaken for freeleech."""
        mod, captured = _load_iptorrents()
        engine = self._make_engine(mod, IPT_SINGLE_ROW)
        engine.search_parse("http://example.com")
        assert len(captured) == 1
        assert "free" not in captured[0]["name"].lower()

    def test_search_parse_bob083_regression_seed_leech_not_zero_zero(self):
        """BOB-083 regression guard.

        Real HTML captured live from iptorrents.com (2026-08-19) with real
        swarm data (91 seeders / 2 leechers on the matched row) MUST be
        parsed with those exact non-zero values -- not "0"/"0" and not
        silently dropped as zero results.
        """
        mod, captured = _load_iptorrents()
        engine = self._make_engine(mod, IPT_SINGLE_ROW)
        engine.search_parse("http://example.com")
        assert len(captured) == 1
        assert captured[0]["seeds"] != "0"
        assert captured[0]["leech"] != "0"
        assert int(captured[0]["seeds"]) == 500
        assert int(captured[0]["leech"]) == 25

    def test_search_parse_obsolete_markup_yields_zero_results(self):
        """§1.1-adjacent negative control.

        HTML in the OLD (pre-BOB-083-fix) shape -- unquoted
        `<table id=torrents>`, `/details.php?id=...` links, `t_seeders`/
        `t_leechers` classes -- is what IPTorrents used to emit and is no
        longer emitted anywhere on the live site. The CURRENT parser
        correctly finds nothing in it (proving the parser is now anchored to
        real, current markup rather than accidentally still matching the
        retired shape). This exact "swarm data present, zero results parsed"
        HTML shape is genuine live BOB-083 evidence for what the pre-fix
        code did against the CURRENT site (real markup, old-shaped regex).
        """
        mod, captured = _load_iptorrents()
        engine = self._make_engine(mod, IPT_OBSOLETE_MARKUP_REAL_SWARM_DATA)
        engine.search_parse("http://example.com")
        assert captured == []

    def test_search_parse_pagination(self):
        mod, captured = _load_iptorrents()
        engine = mod.iptorrents.__new__(mod.iptorrents)
        engine.session = MagicMock()
        engine.url = "https://iptorrents.com"
        call_count = [0]

        def mock_open(url, *args, **kwargs):
            mock_resp = MagicMock()
            mock_resp.info.return_value.get.return_value = "text/html; charset=utf-8"
            if call_count[0] == 0:
                mock_resp.read.return_value = IPT_PAGINATION.encode("utf-8")
            else:
                mock_resp.read.return_value = IPT_PAGE2.encode("utf-8")
            call_count[0] += 1
            return mock_resp

        engine.session.open.side_effect = mock_open
        engine.search_parse("http://example.com")
        assert len(captured) == 2
        assert captured[0]["name"] == "Page1"
        assert captured[1]["name"] == "Page2"


class TestIptorrentsSearchFreeleech:
    def test_search_freeleech_all(self):
        mod, _ = _load_iptorrents()
        engine = mod.iptorrents.__new__(mod.iptorrents)
        engine.session = MagicMock()
        engine.url = "https://iptorrents.com"
        mock_resp = MagicMock()
        mock_resp.info.return_value.get.return_value = "text/html; charset=utf-8"
        mock_resp.read.return_value = IPT_NO_TABLE.encode("utf-8")
        engine.session.open.return_value = mock_resp
        engine.search_freeleech("ubuntu")
        call_args = engine.session.open.call_args[0][0]
        assert "free=on" in call_args
        assert "q=ubuntu" in call_args

    def test_search_freeleech_category(self):
        mod, _ = _load_iptorrents()
        engine = mod.iptorrents.__new__(mod.iptorrents)
        engine.session = MagicMock()
        engine.url = "https://iptorrents.com"
        mock_resp = MagicMock()
        mock_resp.info.return_value.get.return_value = "text/html; charset=utf-8"
        mock_resp.read.return_value = IPT_NO_TABLE.encode("utf-8")
        engine.session.open.return_value = mock_resp
        engine.search_freeleech("ubuntu", "movies")
        call_args = engine.session.open.call_args[0][0]
        assert "72=" in call_args
        assert "free=on" in call_args

    def test_search_freeleech_multi_word_query_is_url_encoded(self):
        """BOB-083 root cause: a raw space in the query string trips
        Python 3.14's stricter http.client path validation
        ("URL can't contain control characters") and the request never
        leaves the process -- search_freeleech() must URL-encode `what`.
        """
        mod, _ = _load_iptorrents()
        engine = mod.iptorrents.__new__(mod.iptorrents)
        engine.session = MagicMock()
        engine.url = "https://iptorrents.com"
        mock_resp = MagicMock()
        mock_resp.info.return_value.get.return_value = "text/html; charset=utf-8"
        mock_resp.read.return_value = IPT_NO_TABLE.encode("utf-8")
        engine.session.open.return_value = mock_resp
        engine.search_freeleech("The Bourne Legacy")
        call_args = engine.session.open.call_args[0][0]
        assert " " not in call_args
        assert "The%20Bourne%20Legacy" in call_args


class TestIptorrentsSearch:
    def test_search_all(self):
        mod, _ = _load_iptorrents()
        engine = mod.iptorrents.__new__(mod.iptorrents)
        engine.session = MagicMock()
        engine.url = "https://iptorrents.com"
        mock_resp = MagicMock()
        mock_resp.info.return_value.get.return_value = "text/html; charset=utf-8"
        mock_resp.read.return_value = IPT_NO_TABLE.encode("utf-8")
        engine.session.open.return_value = mock_resp
        engine.search("ubuntu")
        call_args = engine.session.open.call_args[0][0]
        assert "q=ubuntu" in call_args
        assert "free=on" not in call_args

    def test_search_category(self):
        mod, _ = _load_iptorrents()
        engine = mod.iptorrents.__new__(mod.iptorrents)
        engine.session = MagicMock()
        engine.url = "https://iptorrents.com"
        mock_resp = MagicMock()
        mock_resp.info.return_value.get.return_value = "text/html; charset=utf-8"
        mock_resp.read.return_value = IPT_NO_TABLE.encode("utf-8")
        engine.session.open.return_value = mock_resp
        engine.search("ubuntu", "tv")
        call_args = engine.session.open.call_args[0][0]
        assert "73=" in call_args

    def test_search_multi_word_query_is_url_encoded(self):
        mod, _ = _load_iptorrents()
        engine = mod.iptorrents.__new__(mod.iptorrents)
        engine.session = MagicMock()
        engine.url = "https://iptorrents.com"
        mock_resp = MagicMock()
        mock_resp.info.return_value.get.return_value = "text/html; charset=utf-8"
        mock_resp.read.return_value = IPT_NO_TABLE.encode("utf-8")
        engine.session.open.return_value = mock_resp
        engine.search("The Bourne Legacy")
        call_args = engine.session.open.call_args[0][0]
        assert " " not in call_args
        assert "The%20Bourne%20Legacy" in call_args


class TestIptorrentsDownloadTorrent:
    def test_download_no_session(self):
        mod, _ = _load_iptorrents()
        engine = mod.iptorrents.__new__(mod.iptorrents)
        engine.session = None
        engine.download_torrent("http://example.com/file.torrent")

    def test_download_url_error(self):
        mod, _ = _load_iptorrents()
        engine = mod.iptorrents.__new__(mod.iptorrents)
        from urllib.error import URLError
        engine.session = MagicMock()
        engine.session.open.side_effect = URLError("timeout")
        engine.download_torrent("http://example.com/file.torrent")

    def test_download_gzip_compressed(self):
        mod, captured = _load_iptorrents()
        engine = mod.iptorrents.__new__(mod.iptorrents)
        engine.session = MagicMock()
        original_data = b"torrent data here"
        compressed = gzip.compress(original_data)
        mock_resp = MagicMock()
        mock_resp.read.return_value = compressed
        engine.session.open.return_value = mock_resp
        real_fd = os.open("/dev/null", os.O_WRONLY)
        with patch.object(mod.tempfile, "mkstemp", return_value=(real_fd, "/dev/null")):
            with patch("builtins.print") as mock_print:
                engine.download_torrent("http://example.com/file.torrent")
                mock_print.assert_called_once()

    def test_download_plain_data(self):
        mod, captured = _load_iptorrents()
        engine = mod.iptorrents.__new__(mod.iptorrents)
        engine.session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"plain torrent data"
        engine.session.open.return_value = mock_resp
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = tmp.name
        real_fd = os.open(tmp_path, os.O_WRONLY | os.O_TRUNC)
        with patch.object(mod.tempfile, "mkstemp", return_value=(real_fd, tmp_path)):
            with patch("builtins.print") as mock_print:
                engine.download_torrent("http://example.com/file.torrent")
                mock_print.assert_called_once()
        os.unlink(tmp_path)


class TestIptorrentsSupportedCategories:
    def test_all_categories_present(self):
        mod, _ = _load_iptorrents()
        assert "all" in mod.iptorrents.supported_categories
        assert "movies" in mod.iptorrents.supported_categories
        assert "tv" in mod.iptorrents.supported_categories
        assert "music" in mod.iptorrents.supported_categories
        assert "games" in mod.iptorrents.supported_categories
        assert "anime" in mod.iptorrents.supported_categories
        assert "software" in mod.iptorrents.supported_categories
        assert "pictures" in mod.iptorrents.supported_categories
        assert "books" in mod.iptorrents.supported_categories
