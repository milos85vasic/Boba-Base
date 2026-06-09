import json
import os
import sys
import types

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_PLUGINS_PATH = os.path.join(_REPO_ROOT, "plugins")
if _PLUGINS_PATH not in sys.path:
    sys.path.insert(0, _PLUGINS_PATH)

import pytest


_NAMES = {
    "htmlentitydecode": lambda s: s,
    "unescape": lambda s: s,
    "retrieve_url": lambda url, **kw: "",
    "get_torrent_socks_proxy": None,
}


class _HelpersModule(types.ModuleType):
    def __getattr__(self, name):
        if name in _NAMES:
            return _NAMES[name]
        raise AttributeError(name)


def _install_helpers():
    sys.modules["helpers"] = _HelpersModule("helpers")


_install_helpers()


@pytest.fixture(autouse=True)
def _ensure_helpers():
    _install_helpers()
    yield
    _install_helpers()


class TestPiratebayJsonGuard:
    def test_empty_response_returns_early(self, monkeypatch):
        from piratebay import piratebay as PiratebayPlugin

        plugin = PiratebayPlugin()
        monkeypatch.setattr(plugin, "retrieve_url", lambda url: "")
        results = []
        monkeypatch.setattr("piratebay.prettyPrinter", lambda r: results.append(r))
        plugin.search("test")
        assert results == []

    def test_invalid_json_returns_early(self, monkeypatch):
        from piratebay import piratebay as PiratebayPlugin

        plugin = PiratebayPlugin()
        monkeypatch.setattr(plugin, "retrieve_url", lambda url: "not json <<<>>>")
        results = []
        monkeypatch.setattr("piratebay.prettyPrinter", lambda r: results.append(r))
        plugin.search("test")
        assert results == []

    def test_valid_json_no_results(self, monkeypatch):
        from piratebay import piratebay as PiratebayPlugin

        plugin = PiratebayPlugin()
        monkeypatch.setattr(plugin, "retrieve_url", lambda url: "[]")
        results = []
        monkeypatch.setattr("piratebay.prettyPrinter", lambda r: results.append(r))
        plugin.search("test")
        assert results == []

    def test_valid_json_with_results(self, monkeypatch):
        from piratebay import piratebay as PiratebayPlugin

        plugin = PiratebayPlugin()
        response = json.dumps([
            {
                "id": "1",
                "name": "Test Torrent",
                "info_hash": "a" * 40,
                "seeders": "100",
                "leechers": "50",
                "num_files": "1",
                "size": "1000000",
                "username": "uploader",
                "added": "2024-01-01",
                "status": "trusted",
                "category": "200",
                "imdb": "",
            }
        ])
        monkeypatch.setattr(plugin, "retrieve_url", lambda url: response)
        results = []
        monkeypatch.setattr("piratebay.prettyPrinter", lambda r: results.append(r))
        plugin.search("test")
        assert len(results) == 1
        assert results[0]["name"] == "Test Torrent"


class TestKickassGuard:
    def test_empty_html_returns_no_torrents(self, monkeypatch):
        from kickass import kickass as KickassPlugin

        monkeypatch.setattr("kickass.retrieve_url", lambda url: "")
        plugin = KickassPlugin()
        results = []
        monkeypatch.setattr("kickass.prettyPrinter", lambda r: results.append(r))
        plugin.search("test")
        assert results == []

    def test_malformed_html_returns_no_torrents(self, monkeypatch):
        from kickass import kickass as KickassPlugin

        monkeypatch.setattr("kickass.retrieve_url", lambda url: "<html><body>Service Unavailable</body></html>")
        plugin = KickassPlugin()
        results = []
        monkeypatch.setattr("kickass.prettyPrinter", lambda r: results.append(r))
        plugin.search("test")
        assert results == []


class TestEztvGuard:
    def test_empty_html_returns_no_torrents(self, monkeypatch):
        from eztv import eztv as EztvPlugin

        monkeypatch.setattr("eztv.retrieve_url", lambda url, **kw: "")
        plugin = EztvPlugin()
        results = []
        monkeypatch.setattr("eztv.prettyPrinter", lambda r: results.append(r))
        plugin.search("test")
        assert results == []


class TestNyaaGuard:
    def test_empty_html_returns_no_torrents(self, monkeypatch):
        from nyaa import nyaa as NyaaPlugin

        monkeypatch.setattr("nyaa.retrieve_url", lambda url: "")
        plugin = NyaaPlugin()
        results = []
        monkeypatch.setattr("nyaa.prettyPrinter", lambda r: results.append(r))
        plugin.search("test")
        assert results == []


class TestLimetorrentsGuard:
    def test_empty_html_returns_no_torrents(self, monkeypatch):
        from limetorrents import limetorrents as LimePlugin

        monkeypatch.setattr("limetorrents.retrieve_url", lambda url: "")
        plugin = LimePlugin()
        results = []
        monkeypatch.setattr("limetorrents.prettyPrinter", lambda r: results.append(r))
        plugin.search("test")
        assert results == []
