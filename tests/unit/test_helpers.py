"""
Tests for plugins/helpers.py — pure functions, no network.
"""

import os
import sys

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
