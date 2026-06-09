"""Deep coverage tests for plugins/community/torrentscsv.py.

Covers: search (JSON parsing, single/multi/empty/malformed/network-error),
download_link (magnet URI construction, missing infohash),
download_torrent (magnet handling, .torrent download, invalid data, network error),
class attributes, category mapping, prettyPrinter fields.
"""

import io
import importlib.util
import json
import os
import sys
import tempfile
import types
import urllib.request
from unittest.mock import MagicMock, patch

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PLUGINS_DIR = os.path.join(REPO, "plugins", "community")


def _load_torrentscsv(captured=None):
    if captured is None:
        captured = []

    np_mod = types.ModuleType("novaprinter")
    np_mod.prettyPrinter = lambda d: captured.append(dict(d))
    sys.modules["novaprinter"] = np_mod

    helpers_mod = types.ModuleType("helpers")
    helpers_mod.retrieve_url = lambda url: ""
    sys.modules["helpers"] = helpers_mod

    sys.modules.pop("torrentscsv", None)

    path = os.path.join(PLUGINS_DIR, "torrentscsv.py")
    spec = importlib.util.spec_from_file_location("torrentscsv", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules["torrentscsv"] = mod
    cls = getattr(mod, "torrentscsv", None)
    if cls is not None and isinstance(cls, type):
        return cls(), captured
    return mod, captured


SINGLE_RESPONSE = {
    "torrents": [
        {
            "name": "Ubuntu 24.04 LTS",
            "size_bytes": 5683289579,
            "seeders": 1250,
            "leechers": 340,
            "infohash": "abc123def4567890abc123def4567890abc123de",
            "created_unix": 1716249600,
        }
    ]
}

MULTI_RESPONSE = {
    "torrents": [
        {
            "name": "Fedora 40",
            "size_bytes": 2147483648,
            "seeders": 890,
            "leechers": 120,
            "infohash": "1111111111111111111111111111111111111111",
            "created_unix": 1716249601,
        },
        {
            "name": "Arch Linux",
            "size_bytes": 1073741824,
            "seeders": 567,
            "leechers": 45,
            "infohash": "2222222222222222222222222222222222222222",
            "created_unix": 1716249602,
        },
    ]
}

EMPTY_RESPONSE = {"torrents": []}

VALID_TORRENT_DATA = b"d8:announce42:udp://tracker.example.com:1337/announcee"


class TestClassAttributes:
    def setup_method(self):
        self.mod, self.cap = _load_torrentscsv()

    def test_url(self):
        assert self.mod.url == "https://torrents-csv.com"

    def test_name(self):
        assert self.mod.name == "torrents-csv"

    def test_supported_categories(self):
        assert self.mod.supported_categories == {"all": ""}

    def test_trackers_list_is_non_empty(self):
        assert len(self.mod.trackers_list) == 10
        assert all(t.startswith("udp://") for t in self.mod.trackers_list)

    def test_trackers_string_is_url_encoded(self):
        assert self.mod.trackers.startswith("tr=")
        assert "udp%3A%2F%2F" in self.mod.trackers
        for tracker in self.mod.trackers_list:
            from urllib.parse import urlencode

            assert urlencode({"tr": tracker}) in self.mod.trackers


class TestSearch:
    def setup_method(self):
        self.mod, self.cap = _load_torrentscsv()

    @patch("torrentscsv.retrieve_url", return_value=json.dumps(SINGLE_RESPONSE))
    def test_search_url_construction(self, mock_retrieve):
        self.mod.search("ubuntu")
        called_url = mock_retrieve.call_args[0][0]
        assert called_url.startswith("https://torrents-csv.com/service/search")
        assert "size=100" in called_url
        assert "q=ubuntu" in called_url

    @patch("torrentscsv.retrieve_url", return_value=json.dumps(SINGLE_RESPONSE))
    def test_search_single_result(self, mock_retrieve):
        self.mod.search("ubuntu")
        assert len(self.cap) == 1
        r = self.cap[0]
        assert r["name"] == "Ubuntu 24.04 LTS"
        assert r["size"] == "5683289579 B"
        assert r["seeds"] == 1250
        assert r["leech"] == 340
        assert r["engine_url"] == "https://torrents-csv.com"
        assert r["pub_date"] == 1716249600

    @patch("torrentscsv.retrieve_url", return_value=json.dumps(SINGLE_RESPONSE))
    def test_search_link_is_magnet(self, mock_retrieve):
        self.mod.search("ubuntu")
        assert self.cap[0]["link"].startswith("magnet:?xt=urn:btih:")
        assert "abc123def4567890abc123def4567890abc123de" in self.cap[0]["link"]
        assert "dn=Ubuntu+24.04+LTS" in self.cap[0]["link"]

    @patch("torrentscsv.retrieve_url", return_value=json.dumps(SINGLE_RESPONSE))
    def test_search_desc_link(self, mock_retrieve):
        self.mod.search("ubuntu")
        assert self.cap[0]["desc_link"] == "https://torrents-csv.com/#/search/torrent/ubuntu/1"

    @patch("torrentscsv.retrieve_url", return_value=json.dumps(MULTI_RESPONSE))
    def test_search_multi_results(self, mock_retrieve):
        self.mod.search("linux")
        assert len(self.cap) == 2
        assert self.cap[0]["name"] == "Fedora 40"
        assert self.cap[1]["name"] == "Arch Linux"

    @patch("torrentscsv.retrieve_url", return_value=json.dumps(EMPTY_RESPONSE))
    def test_search_empty_results(self, mock_retrieve):
        self.mod.search("nonexistent")
        assert len(self.cap) == 0

    @patch("torrentscsv.retrieve_url", return_value="not valid json {{{")
    def test_search_invalid_json_raises(self, mock_retrieve):
        with pytest.raises(json.JSONDecodeError):
            self.mod.search("ubuntu")

    @patch("torrentscsv.retrieve_url", return_value="{}")
    def test_search_missing_torrents_key_raises(self, mock_retrieve):
        with pytest.raises(KeyError):
            self.mod.search("ubuntu")

    @patch("torrentscsv.retrieve_url", side_effect=urllib.request.URLError("connection refused"))
    def test_search_network_error_propagates(self, mock_retrieve):
        with pytest.raises(urllib.request.URLError):
            self.mod.search("ubuntu")

    @patch("torrentscsv.retrieve_url", return_value=json.dumps({"torrents": [{"name": "test"}]}))
    def test_search_missing_infohash_keyerror(self, mock_retrieve):
        with pytest.raises(KeyError):
            self.mod.search("test")


class TestDownloadLink:
    def setup_method(self):
        self.mod, self.cap = _load_torrentscsv()

    def test_magnet_uri_structure(self):
        ihash = "deadbeef" * 5
        result = {"name": "Test File", "infohash": ihash}
        link = self.mod.download_link(result)
        assert link.startswith("magnet:?xt=urn:btih:" + ihash)
        assert "dn=Test+File" in link
        assert "tr=udp%3A%2F%2F" in link

    def test_magnet_uri_includes_all_trackers(self):
        result = {"name": "Multi Tracker", "infohash": "aaaa" * 10}
        link = self.mod.download_link(result)
        count = link.count("tr=")
        assert count == 10

    def test_missing_infohash_raises(self):
        result = {"name": "No Hash"}
        with pytest.raises(KeyError):
            self.mod.download_link(result)

    def test_missing_name_raises(self):
        result = {"infohash": "bbbb" * 10}
        with pytest.raises(KeyError):
            self.mod.download_link(result)

    def test_special_characters_in_name_encoded(self):
        result = {"name": "File & Stuff", "infohash": "cccc" * 10}
        link = self.mod.download_link(result)
        assert "dn=File+%26+Stuff" in link

    def test_spaces_become_plus(self):
        result = {"name": "My Favorite Movie 2024", "infohash": "dddd" * 10}
        link = self.mod.download_link(result)
        assert "dn=My+Favorite+Movie+2024" in link


class TestDownloadTorrent:
    def setup_method(self):
        self.mod, self.cap = _load_torrentscsv()

    def test_magnet_link_prints_url_twice(self, capsys):
        self.mod.download_torrent("magnet:?xt=urn:btih:abc123&dn=test")
        out = capsys.readouterr().out.strip()
        parts = out.split()
        assert len(parts) >= 2
        assert parts[0] == parts[1]
        assert parts[0].startswith("magnet:")

    def test_magnet_link_flushes_stdout(self, capsys, monkeypatch):
        flushed = []

        def fake_flush():
            flushed.append(True)

        monkeypatch.setattr(sys.stdout, "flush", fake_flush)
        self.mod.download_torrent("magnet:?xt=urn:btih:abc123&dn=test")
        assert len(flushed) >= 1

    def test_torrent_download_writes_temp_file(self, capsys, monkeypatch):
        response_obj = MagicMock()
        response_obj.read.return_value = VALID_TORRENT_DATA
        response_obj.__enter__ = MagicMock(return_value=response_obj)
        response_obj.__exit__ = MagicMock(return_value=False)

        def fake_urlopen(req, timeout=None):
            return response_obj

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

        self.mod.download_torrent("https://example.com/file.torrent")
        out = capsys.readouterr().out.strip()
        parts = out.split()
        assert len(parts) == 2
        assert parts[0].endswith(".torrent")
        assert parts[1] == "https://example.com/file.torrent"

    def test_torrent_download_user_agent_set(self, monkeypatch):
        captured_headers = {}

        response_obj = MagicMock()
        response_obj.read.return_value = VALID_TORRENT_DATA
        response_obj.__enter__ = MagicMock(return_value=response_obj)
        response_obj.__exit__ = MagicMock(return_value=False)

        def fake_urlopen(req, timeout=None):
            captured_headers["User-Agent"] = req.get_header("User-agent")
            return response_obj

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

        self.mod.download_torrent("https://example.com/file.torrent")
        assert captured_headers.get("User-Agent") == "Mozilla/5.0"

    def test_invalid_torrent_data_exits(self, monkeypatch):
        response_obj = MagicMock()
        response_obj.read.return_value = b"<html>not a torrent</html>"
        response_obj.__enter__ = MagicMock(return_value=response_obj)
        response_obj.__exit__ = MagicMock(return_value=False)

        def fake_urlopen(req, timeout=None):
            return response_obj

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

        with pytest.raises(SystemExit) as exc_info:
            self.mod.download_torrent("https://example.com/bad.torrent")
        assert exc_info.value.code == 1

    def test_invalid_torrent_data_stderr(self, capsys, monkeypatch):
        response_obj = MagicMock()
        response_obj.read.return_value = b"not-a-torrent"
        response_obj.__enter__ = MagicMock(return_value=response_obj)
        response_obj.__exit__ = MagicMock(return_value=False)

        monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: response_obj)

        try:
            self.mod.download_torrent("https://example.com/bad.torrent")
        except SystemExit:
            pass
        err = capsys.readouterr().err
        assert "Error: Not a valid torrent file" in err

    def test_network_error_exits(self, monkeypatch):
        def raise_error(req, timeout=None):
            raise urllib.request.URLError("connection refused")

        monkeypatch.setattr(urllib.request, "urlopen", raise_error)

        with pytest.raises(SystemExit) as exc_info:
            self.mod.download_torrent("https://example.com/file.torrent")
        assert exc_info.value.code == 1

    def test_network_error_prints_stderr(self, capsys, monkeypatch):
        def raise_error(req, timeout=None):
            raise urllib.request.URLError("connection refused")

        monkeypatch.setattr(urllib.request, "urlopen", raise_error)

        try:
            self.mod.download_torrent("https://example.com/file.torrent")
        except SystemExit:
            pass
        err = capsys.readouterr().err
        assert "Error downloading torrent" in err
        assert "connection refused" in err

    def test_generic_exception_exits(self, monkeypatch):
        def raise_error(req, timeout=None):
            raise ValueError("something went wrong")

        monkeypatch.setattr(urllib.request, "urlopen", raise_error)

        with pytest.raises(SystemExit) as exc_info:
            self.mod.download_torrent("https://example.com/file.torrent")
        assert exc_info.value.code == 1

    def test_torrent_temp_file_has_torrent_suffix(self, capsys, monkeypatch):
        response_obj = MagicMock()
        response_obj.read.return_value = VALID_TORRENT_DATA
        response_obj.__enter__ = MagicMock(return_value=response_obj)
        response_obj.__exit__ = MagicMock(return_value=False)

        monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: response_obj)

        self.mod.download_torrent("https://example.com/file.torrent")
        out = capsys.readouterr().out.strip()
        path_part = out.split()[0]
        assert path_part.endswith(".torrent")

    def test_search_url_raw_query(self):
        with patch("torrentscsv.retrieve_url", return_value=json.dumps(EMPTY_RESPONSE)) as mock_req:
            self.mod.search("test query & stuff")
            called_url = mock_req.call_args[0][0]
            assert "q=test query & stuff" in called_url

    def test_download_torrent_empty_magnet(self, capsys):
        self.mod.download_torrent("magnet:")
        out = capsys.readouterr().out.strip()
        parts = out.split()
        assert len(parts) >= 2
        assert parts[0] == "magnet:"
        assert parts[1] == "magnet:"
