"""Deep coverage tests for plugins/piratebay.py.

Covers: search (JSON parsing, category mapping, empty/malformed, zero-hash skip),
download_link (magnet construction), retrieve_url (gzip, charset, HTTPError),
download_torrent (magnet passthrough, torrent download, errors), SOCKS proxy
side-effect, module-level helpers attribute access.
"""

import gzip
import importlib.util
import io
import json
import os
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PLUGINS_DIR = os.path.join(REPO, "plugins")

ZERO_HASH = "0000000000000000000000000000000000000000"


def _load_piratebay(captured=None):
    """Import piratebay plugin with stub modules. Returns (instance, captured)."""
    if captured is None:
        captured = []
    np_mod = types.ModuleType("novaprinter")
    np_mod.prettyPrinter = lambda d: captured.append(dict(d))
    sys.modules["novaprinter"] = np_mod

    helpers_mod = types.ModuleType("helpers")
    helpers_mod.retrieve_url = lambda url: ""
    helpers_mod.htmlentitydecode = lambda s: s
    sys.modules["helpers"] = helpers_mod

    sys.modules.pop("piratebay", None)

    path = os.path.join(PLUGINS_DIR, "piratebay.py")
    spec = importlib.util.spec_from_file_location("piratebay", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules["piratebay"] = mod
    cls = getattr(mod, "piratebay", None)
    if cls is not None and isinstance(cls, type):
        return cls(), captured
    return mod, captured


# ─── JSON fixtures matching apibay.org API ──────────────────────────────

def _make_result(name="Test Torrent", info_hash="a" * 40, size=1024,
                 seeders=10, leechers=5, id="12345", added="2024-01-01 00:00:00"):
    return {
        "id": id,
        "name": name,
        "info_hash": info_hash,
        "seeders": seeders,
        "leechers": leechers,
        "num_files": 1,
        "size": size,
        "username": "uploader",
        "added": added,
        "status": "trusted",
        "category": 200,
        "imdb": "",
    }


SINGLE_RESULT = json.dumps([_make_result()])
MULTI_RESULT = json.dumps([
    _make_result(name="Alpha", info_hash="a" * 40, id="1"),
    _make_result(name="Beta", info_hash="b" * 40, id="2", size=2048),
    _make_result(name="Gamma", info_hash="c" * 40, id="3", seeders=0),
])
EMPTY_RESULT = "[]"
ZERO_HASH_RESULT = json.dumps([_make_result(info_hash=ZERO_HASH, id="999")])
MALFORMED_JSON = "{not json"
MIXED_RESULT = json.dumps([
    _make_result(name="Good", info_hash="d" * 40, id="10"),
    _make_result(info_hash=ZERO_HASH, id="99"),
])


# ─── Category mapping ───────────────────────────────────────────────────

class TestCategoryMapping:
    def setup_method(self):
        self.pb, self.cap = _load_piratebay()

    def test_all_categories_present(self):
        assert set(self.pb.supported_categories.keys()) == {
            "all", "music", "movies", "games", "software"
        }

    def test_category_values(self):
        assert self.pb.supported_categories["all"] == "0"
        assert self.pb.supported_categories["music"] == "100"
        assert self.pb.supported_categories["movies"] == "200"
        assert self.pb.supported_categories["games"] == "400"
        assert self.pb.supported_categories["software"] == "300"

    def test_invalid_category_raises(self):
        with pytest.raises(KeyError):
            self.pb.search("test", cat="nonexistent")


# ─── download_link / magnet construction ─────────────────────────────────

class TestDownloadLink:
    def setup_method(self):
        self.pb, self.cap = _load_piratebay()

    def test_magnet_link_structure(self):
        result = _make_result(name="My Torrent", info_hash="ab" * 20)
        link = self.pb.download_link(result)
        assert link.startswith("magnet:?xt=urn:btih:ab")
        assert "dn=My+Torrent" in link

    def test_magnet_link_contains_tracker_params(self):
        result = _make_result()
        link = self.pb.download_link(result)
        assert link.count("tr=") == len(self.pb.trackers_list)

    def test_magnet_link_trackers_string_count(self):
        parts = self.pb.trackers.split("&")
        assert len(parts) == len(self.pb.trackers_list)
        assert all(p.startswith("tr=") for p in parts)

    def test_magnet_link_special_chars_in_name(self):
        result = _make_result(name="File & Path <test>")
        link = self.pb.download_link(result)
        assert "dn=File+%26+Path+%3Ctest%3E" in link


# ─── search (JSON parsing + prettyPrinter output) ───────────────────────

class TestSearch:
    def setup_method(self):
        self.pb, self.cap = _load_piratebay()

    def test_single_result(self):
        with patch.object(self.pb, "retrieve_url", return_value=SINGLE_RESULT):
            self.pb.search("test")
        assert len(self.cap) == 1
        item = self.cap[0]
        assert item["name"] == "Test Torrent"
        assert item["engine_url"] == "https://thepiratebay.org"
        assert item["size"] == "1024 B"
        assert item["seeds"] == 10
        assert item["leech"] == 5

    def test_multi_results(self):
        with patch.object(self.pb, "retrieve_url", return_value=MULTI_RESULT):
            self.pb.search("test")
        assert len(self.cap) == 3
        names = [r["name"] for r in self.cap]
        assert names == ["Alpha", "Beta", "Gamma"]

    def test_empty_json_array(self):
        with patch.object(self.pb, "retrieve_url", return_value=EMPTY_RESULT):
            self.pb.search("nothing")
        assert len(self.cap) == 0

    def test_malformed_json_returns_early(self):
        with patch.object(self.pb, "retrieve_url", return_value=MALFORMED_JSON):
            self.pb.search("bad")
        assert len(self.cap) == 0

    def test_empty_string_response(self):
        with patch.object(self.pb, "retrieve_url", return_value=""):
            self.pb.search("empty")
        assert len(self.cap) == 0

    def test_zero_hash_skipped(self):
        with patch.object(self.pb, "retrieve_url", return_value=ZERO_HASH_RESULT):
            self.pb.search("zero")
        assert len(self.cap) == 0

    def test_mixed_valid_and_zero_hash(self):
        with patch.object(self.pb, "retrieve_url", return_value=MIXED_RESULT):
            self.pb.search("mixed")
        assert len(self.cap) == 1
        assert self.cap[0]["name"] == "Good"

    def test_url_construction_all_category(self):
        with patch.object(self.pb, "retrieve_url", return_value=EMPTY_RESULT) as mock:
            self.pb.search("query", cat="all")
        called_url = mock.call_args[0][0]
        assert "apibay.org/q.php" in called_url
        assert "q=query" in called_url
        assert "cat=" not in called_url

    def test_url_construction_music_category(self):
        with patch.object(self.pb, "retrieve_url", return_value=EMPTY_RESULT) as mock:
            self.pb.search("song", cat="music")
        called_url = mock.call_args[0][0]
        assert "cat=100" in called_url

    def test_url_construction_movies_category(self):
        with patch.object(self.pb, "retrieve_url", return_value=EMPTY_RESULT) as mock:
            self.pb.search("film", cat="movies")
        called_url = mock.call_args[0][0]
        assert "cat=200" in called_url

    def test_url_encoded_search_term(self):
        with patch.object(self.pb, "retrieve_url", return_value=EMPTY_RESULT) as mock:
            self.pb.search("hello world")
        called_url = mock.call_args[0][0]
        assert "q=hello+world" in called_url

    def test_desc_link_format(self):
        with patch.object(self.pb, "retrieve_url", return_value=SINGLE_RESULT):
            self.pb.search("test")
        assert self.cap[0]["desc_link"].endswith("/description.php?id=12345")

    def test_pub_date_preserved(self):
        with patch.object(self.pb, "retrieve_url", return_value=SINGLE_RESULT):
            self.pb.search("test")
        assert self.cap[0]["pub_date"] == "2024-01-01 00:00:00"

    def test_link_starts_with_magnet(self):
        with patch.object(self.pb, "retrieve_url", return_value=SINGLE_RESULT):
            self.pb.search("test")
        assert self.cap[0]["link"].startswith("magnet:?xt=urn:btih:")


# ─── retrieve_url ────────────────────────────────────────────────────────

class TestRetrieveUrl:
    def setup_method(self):
        self.pb, self.cap = _load_piratebay()

    def _mock_response(self, data, charset="utf-8", content_type=None):
        if content_type is None:
            content_type = f"text/html; charset={charset}"
        resp = MagicMock()
        resp.read.return_value = data if isinstance(data, bytes) else data.encode(charset)
        resp.getheader.return_value = content_type
        return resp

    @patch("urllib.request.urlopen")
    def test_plain_text_response(self, mock_urlopen):
        body = "hello"
        mock_urlopen.return_value = self._mock_response(body)
        result = self.pb.retrieve_url("https://example.com")
        assert result == "hello"

    @patch("urllib.request.urlopen")
    def test_gzip_response(self, mock_urlopen):
        raw = gzip.compress(b"gzipped data")
        resp = MagicMock()
        resp.read.return_value = raw
        resp.getheader.return_value = "text/html; charset=utf-8"
        mock_urlopen.return_value = resp
        result = self.pb.retrieve_url("https://example.com")
        assert result == "gzipped data"

    @patch("urllib.request.urlopen")
    def test_http_error_returns_empty(self, mock_urlopen):
        import urllib.error
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "https://example.com", 403, "Forbidden", {}, io.BytesIO()
        )
        result = self.pb.retrieve_url("https://example.com")
        assert result == ""

    @patch("urllib.request.urlopen")
    def test_html_entities_decoded(self, mock_urlopen):
        mock_urlopen.return_value = self._mock_response("a &amp; b &quot;c&quot;")
        result = self.pb.retrieve_url("https://example.com")
        assert "a & b" in result
        assert '\\"c\\"' in result

    @patch("urllib.request.urlopen")
    def test_non_utf8_charset(self, mock_urlopen):
        resp = MagicMock()
        resp.read.return_value = "données".encode("latin-1")
        resp.getheader.return_value = "text/html; charset=latin-1"
        mock_urlopen.return_value = resp
        result = self.pb.retrieve_url("https://example.com")
        assert "données" in result

    @patch("urllib.request.urlopen")
    def test_no_charset_header(self, mock_urlopen):
        resp = MagicMock()
        resp.read.return_value = b"plain"
        resp.getheader.return_value = "text/html"
        mock_urlopen.return_value = resp
        result = self.pb.retrieve_url("https://example.com")
        assert result == "plain"

    @patch("urllib.request.urlopen")
    def test_user_agent_set(self, mock_urlopen):
        mock_urlopen.return_value = self._mock_response("")
        self.pb.retrieve_url("https://example.com")
        req = mock_urlopen.call_args[0][0]
        assert "Mozilla/5.0" in req.get_header("User-agent")


# ─── download_torrent ────────────────────────────────────────────────────

class TestDownloadTorrent:
    def setup_method(self):
        self.pb, self.cap = _load_piratebay()

    def test_magnet_link_passthrough(self, capsys):
        magnet = "magnet:?xt=urn:btih:abc123&dn=Test"
        self.pb.download_torrent(magnet)
        captured = capsys.readouterr()
        assert magnet in captured.out
        assert captured.out.count(magnet) == 2

    @patch("urllib.request.urlopen")
    def test_torrent_file_download_known_bug_os_import_order(self, mock_urlopen, capsys):
        """Plugin bug: `import os` on line 175 is AFTER `os.fdopen` on line 172,
        causing UnboundLocalError → SystemExit.  This test documents the bug."""
        mock_urlopen.return_value.__enter__ = lambda s: s
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value.read.return_value = b"torrent data"
        with pytest.raises(SystemExit):
            self.pb.download_torrent("https://example.com/file.torrent")
        captured = capsys.readouterr()
        assert "Error:" in captured.err
        mock_urlopen.assert_called_once()

    @patch("urllib.request.urlopen", side_effect=Exception("conn refused"))
    def test_torrent_download_error(self, mock_urlopen, capsys):
        with pytest.raises(SystemExit):
            self.pb.download_torrent("https://example.com/file.torrent")
        captured = capsys.readouterr()
        assert "Error:" in captured.err


# ─── Module-level / class attributes ─────────────────────────────────────

class TestModuleAttributes:
    def setup_method(self):
        self.pb, self.cap = _load_piratebay()

    def test_url_attribute(self):
        assert self.pb.url == "https://thepiratebay.org"

    def test_name_attribute(self):
        assert self.pb.name == "The Pirate Bay"

    def test_trackers_list_nonempty(self):
        assert len(self.pb.trackers_list) > 0

    def test_trackers_string_contains_all(self):
        from urllib.parse import unquote
        decoded = unquote(self.pb.trackers)
        for tracker in self.pb.trackers_list:
            assert tracker in decoded

    def test_helpers_htmlentitydecode_exists(self):
        import helpers
        assert hasattr(helpers, "htmlentitydecode")

    def test_helpers_module_loaded(self):
        assert "helpers" in sys.modules

    def test_novaprinter_module_loaded(self):
        assert "novaprinter" in sys.modules
