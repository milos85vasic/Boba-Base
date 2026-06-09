"""
Tests for plugins/helpers.py — pure functions, no network.
"""

import os
import sys
from typing import Any

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_PLUGINS_PATH = os.path.join(_REPO_ROOT, "plugins")
if _PLUGINS_PATH not in sys.path:
    sys.path.insert(0, _PLUGINS_PATH)

import helpers


class TestBuildMagnetLink:
    def test_basic_magnet(self):
        link = helpers.build_magnet_link("abcdef0123456789abcdef0123456789abcdef01", "test file")
        assert link.startswith("magnet:?xt=urn:btih:abcdef0123456789abcdef0123456789abcdef01")
        assert "dn=test%20file" in link
        assert "tr=" in link

    def test_magnet_with_custom_trackers(self):
        link = helpers.build_magnet_link("a" * 40, "test", trackers=["udp://tracker.test:80/announce"])
        assert "tr=" in link
        assert "tracker.test" in link

    def test_magnet_without_trackers_uses_default(self):
        link = helpers.build_magnet_link("b" * 40, "test", trackers=None)
        assert len(link) > 100
        assert "tr=udp%3A" in link
        assert "tr=" in link
        assert link.count("tr=") >= 9


class TestEnableSocksProxy:
    def test_disable_socks_restores_socket(self):
        import socket
        original = socket.socket
        helpers.enable_socks_proxy(False)
        assert socket.socket is original


class TestUserAgent:
    def test_user_agent_format(self):
        ua = helpers._getBrowserUserAgent()
        assert ua.startswith("Mozilla/5.0")
        assert "Firefox/" in ua
        assert "Gecko" in ua

    def test_user_agent_has_version_number(self):
        ua = helpers._getBrowserUserAgent()
        import re
        match = re.search(r"rv:(\d+)\.0", ua)
        assert match is not None
        assert int(match.group(1)) >= 125


class TestHtmlEntityDecode:
    def test_decode_html_entities(self):
        result = helpers.htmlentitydecode("&amp; &lt; &gt; &quot; &#39;")
        assert result == "& < > \" '"


# --- network-touching functions, exercised with a stubbed urlopen ---------

import gzip as _gzip  # noqa: E402
import io as _io  # noqa: E402
import urllib.error  # noqa: E402
import urllib.request  # noqa: E402

import pytest  # noqa: E402


class _FakeResp:
    def __init__(self, data: bytes, content_type: str = "text/html; charset=utf-8"):
        self._data = data
        self._ct = content_type

    def read(self) -> bytes:
        return self._data

    def getheader(self, name: str, default: str = "") -> str:
        return self._ct if name == "Content-Type" else default


def _gzipped(b: bytes) -> bytes:
    buf = _io.BytesIO()
    with _gzip.GzipFile(fileobj=buf, mode="wb") as g:
        g.write(b)
    return buf.getvalue()


class TestRetrieveUrl:
    def test_plain_html(self, monkeypatch):
        monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _FakeResp(b"<html>hi</html>"))
        assert "hi" in helpers.retrieve_url("http://x.test")

    def test_gzip_decoded(self, monkeypatch):
        monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _FakeResp(_gzipped(b"<b>gzbody</b>")))
        assert "gzbody" in helpers.retrieve_url("http://x.test")

    def test_charset_from_content_type(self, monkeypatch):
        body = "café".encode("latin-1")
        monkeypatch.setattr(
            urllib.request,
            "urlopen",
            lambda *a, **k: _FakeResp(body, content_type="text/html; charset=latin-1"),
        )
        assert "café" in helpers.retrieve_url("http://x.test")

    def test_url_error_returns_empty(self, monkeypatch):
        def _boom(*a, **k):
            raise urllib.error.URLError("down")

        monkeypatch.setattr(urllib.request, "urlopen", _boom)
        assert helpers.retrieve_url("http://x.test") == ""

    def test_unescape_toggle(self, monkeypatch):
        monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _FakeResp(b"a&amp;b"))
        assert helpers.retrieve_url("http://x.test", unescape_html_entities=True) == "a&b"
        assert helpers.retrieve_url("http://x.test", unescape_html_entities=False) == "a&amp;b"


class TestDownloadFile:
    def test_writes_payload_and_returns_path(self, monkeypatch):
        monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _FakeResp(b"TORRENTBYTES"))
        result = helpers.download_file("http://x.test/f.torrent")
        path, url = result.split(" ", 1)
        assert url == "http://x.test/f.torrent"
        try:
            with open(path, "rb") as fh:
                assert fh.read() == b"TORRENTBYTES"
        finally:
            os.remove(path)

    def test_gzip_payload_decoded(self, monkeypatch):
        monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _FakeResp(_gzipped(b"GZTORRENT")))
        path = helpers.download_file("http://x.test/f").split(" ", 1)[0]
        try:
            with open(path, "rb") as fh:
                assert fh.read() == b"GZTORRENT"
        finally:
            os.remove(path)

    def test_referer_header_added(self, monkeypatch):
        captured = {}

        def _capture(request, *a, **k):
            captured["referer"] = request.get_header("Referer")
            return _FakeResp(b"x")

        monkeypatch.setattr(urllib.request, "urlopen", _capture)
        helpers.download_file("http://x.test/f", referer="http://ref.test")
        assert captured["referer"] == "http://ref.test"


# --- regression guards: urlopen MUST be called with a bounded timeout --------
# §11.4.98 / §11.4.69: unbounded urlopen blocks the plugin worker thread on a
# slow host. These guards fail against pre-fix code (urlopen without timeout).


class TestUrlopenTimeoutGuard:
    def test_retrieve_url_passes_timeout(self, monkeypatch):
        captured: dict[str, Any] = {}

        def _spy(*args: Any, **kwargs: Any) -> _FakeResp:
            captured["kwargs"] = kwargs
            return _FakeResp(b"<html>ok</html>")

        monkeypatch.setattr(urllib.request, "urlopen", _spy)
        helpers.retrieve_url("http://x.test")
        assert captured["kwargs"].get("timeout") == 30

    def test_download_file_passes_timeout(self, monkeypatch):
        captured: dict[str, Any] = {}

        def _spy(*args: Any, **kwargs: Any) -> _FakeResp:
            captured["kwargs"] = kwargs
            return _FakeResp(b"TORRENTBYTES")

        monkeypatch.setattr(urllib.request, "urlopen", _spy)
        path = helpers.download_file("http://x.test/f.torrent").split(" ", 1)[0]
        try:
            assert captured["kwargs"].get("timeout") == 30
        finally:
            os.remove(path)


class TestFetchMagnetFromPage:
    _MAGNET = "magnet:?xt=urn:btih:" + "a" * 40

    def test_found(self, monkeypatch):
        monkeypatch.setattr(helpers, "retrieve_url", lambda url: f"<a href='{self._MAGNET}'>dl</a>")
        assert helpers.fetch_magnet_from_page("http://x.test") == self._MAGNET

    def test_not_found(self, monkeypatch):
        monkeypatch.setattr(helpers, "retrieve_url", lambda url: "<html>no magnet here</html>")
        assert helpers.fetch_magnet_from_page("http://x.test") == ""

    def test_exception_returns_empty(self, monkeypatch):
        def _boom(url):
            raise RuntimeError("net down")

        monkeypatch.setattr(helpers, "retrieve_url", _boom)
        assert helpers.fetch_magnet_from_page("http://x.test") == ""


class TestEnableSocksProxyBranches:
    @pytest.fixture(autouse=True)
    def _restore_socket(self):
        import socket

        original = socket.socket
        yield
        socket.socket = original

    def test_enable_no_env_is_noop(self, monkeypatch):
        import socket

        monkeypatch.delenv("qbt_socks_proxy", raising=False)
        before = socket.socket
        helpers.enable_socks_proxy(True)
        assert socket.socket is before

    def test_enable_socks5(self, monkeypatch):
        import socket

        calls = {}
        monkeypatch.setenv("qbt_socks_proxy", "socks5://user:pass@proxy.test:1080")
        monkeypatch.setattr(helpers.socks, "setdefaultproxy", lambda *a, **k: calls.setdefault("args", a))
        helpers.enable_socks_proxy(True)
        assert calls["args"][0] == helpers.socks.PROXY_TYPE_SOCKS5
        assert socket.socket is helpers.socks.socksocket

    def test_enable_socks4(self, monkeypatch):
        import socket

        calls = {}
        monkeypatch.setenv("qbt_socks_proxy", "socks4://proxy.test:1080")
        monkeypatch.setattr(helpers.socks, "setdefaultproxy", lambda *a, **k: calls.setdefault("args", a))
        helpers.enable_socks_proxy(True)
        assert calls["args"][0] == helpers.socks.PROXY_TYPE_SOCKS4
        assert socket.socket is helpers.socks.socksocket
