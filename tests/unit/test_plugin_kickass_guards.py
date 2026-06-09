"""Regression tests for kickass.py defensive guards (BOB-015).

kickass.py had three crash-prone patterns:
1. search(): retrieve_url() unguarded — crashes on network error; re.sub on None
2. __retrieve_download_link(): retrieve_url() unguarded — re.search on None
3. download_torrent(): retrieve_url() unguarded — re.search on None

All fixed with try/except + empty-response guards.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
PLUGINS = REPO / "plugins"


def _load_plugin():
    captured: list[dict] = []

    np_mod = types.ModuleType("novaprinter")
    np_mod.prettyPrinter = lambda d: captured.append(d)
    sys.modules["novaprinter"] = np_mod

    helpers_mod = types.ModuleType("helpers")
    helpers_mod.retrieve_url = lambda url: ""
    sys.modules["helpers"] = helpers_mod

    spec = importlib.util.spec_from_file_location("plugin_kickass", PLUGINS / "kickass.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, captured


class TestKickassSearchGuards:
    def test_search_empty_response_breaks_loop(self):
        mod, captured = _load_plugin()
        engine = mod.kickass()
        with patch.object(mod, "retrieve_url", return_value=""):
            engine.search("test query")
        assert captured == []

    def test_search_none_response_breaks_loop(self):
        mod, captured = _load_plugin()
        engine = mod.kickass()
        with patch.object(mod, "retrieve_url", return_value=None):
            engine.search("test query")
        assert captured == []

    def test_search_network_error_breaks_loop(self):
        mod, captured = _load_plugin()
        engine = mod.kickass()
        with patch.object(
            mod, "retrieve_url", side_effect=ConnectionError("network unreachable")
        ):
            engine.search("test query")
        assert captured == []

    def test_search_timeout_error_breaks_loop(self):
        mod, captured = _load_plugin()
        engine = mod.kickass()
        with patch.object(mod, "retrieve_url", side_effect=TimeoutError("timed out")):
            engine.search("test query")
        assert captured == []

    def test_search_malformed_html_does_not_crash(self):
        mod, captured = _load_plugin()
        engine = mod.kickass()
        with patch.object(
            mod,
            "retrieve_url",
            return_value="<html><body>not a torrent page</body></html>",
        ):
            engine.search("test query")
        assert captured == []


class TestKickassDownloadTorrentGuards:
    def test_download_torrent_empty_response_falls_back(self, capsys):
        mod, _ = _load_plugin()
        engine = mod.kickass()
        with patch.object(mod, "retrieve_url", return_value=""):
            engine.download_torrent("http://example.com/detail/123")
        out = capsys.readouterr().out
        assert "http://example.com/detail/123" in out
        assert engine.url in out

    def test_download_torrent_none_response_falls_back(self, capsys):
        mod, _ = _load_plugin()
        engine = mod.kickass()
        with patch.object(mod, "retrieve_url", return_value=None):
            engine.download_torrent("http://example.com/detail/456")
        out = capsys.readouterr().out
        assert "http://example.com/detail/456" in out

    def test_download_torrent_network_error_falls_back(self, capsys):
        mod, _ = _load_plugin()
        engine = mod.kickass()
        with patch.object(
            mod, "retrieve_url", side_effect=ConnectionError("refused")
        ):
            engine.download_torrent("http://example.com/detail/789")
        out = capsys.readouterr().out
        assert "http://example.com/detail/789" in out

    def test_download_torrent_magnet_passthrough(self, capsys):
        mod, _ = _load_plugin()
        engine = mod.kickass()
        engine.download_torrent("magnet:?xt=urn:btih:abc123")
        out = capsys.readouterr().out
        assert "magnet:?xt=urn:btih:abc123" in out


class TestKickassInternalDownloadLinkGuards:
    def test_retrieve_download_link_empty_response(self):
        mod, _ = _load_plugin()
        engine = mod.kickass()
        parser = engine.HTMLParser(engine.url)
        with patch.object(mod, "retrieve_url", return_value=""):
            result = parser._HTMLParser__retrieve_download_link("http://example.com/detail/1")
        assert result == "NotFound"

    def test_retrieve_download_link_none_response(self):
        mod, _ = _load_plugin()
        engine = mod.kickass()
        parser = engine.HTMLParser(engine.url)
        with patch.object(mod, "retrieve_url", return_value=None):
            result = parser._HTMLParser__retrieve_download_link("http://example.com/detail/2")
        assert result == "NotFound"

    def test_retrieve_download_link_network_error(self):
        mod, _ = _load_plugin()
        engine = mod.kickass()
        parser = engine.HTMLParser(engine.url)
        with patch.object(mod, "retrieve_url", side_effect=OSError("timeout")):
            result = parser._HTMLParser__retrieve_download_link("http://example.com/detail/3")
        assert result == "NotFound"

    def test_retrieve_download_link_magnet_found(self):
        mod, _ = _load_plugin()
        engine = mod.kickass()
        parser = engine.HTMLParser(engine.url)
        page = 'some html "magnet:?xt=urn:btih:abc123def456&dn=TestMovie" end'
        with patch.object(mod, "retrieve_url", return_value=page):
            result = parser._HTMLParser__retrieve_download_link("http://example.com/detail/4")
        assert result.startswith("magnet:")
