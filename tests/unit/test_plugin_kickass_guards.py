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

    def test_search_whitespace_body_breaks_loop(self):
        # BOB-015 characterization: whitespace-only body is non-empty but
        # matches no torrent rows -> no results, loop terminates, no crash.
        mod, captured = _load_plugin()
        engine = mod.kickass()
        with patch.object(mod, "retrieve_url", return_value="   \n\t  "):
            engine.search("test query")
        assert captured == []

    def test_search_http_error_shaped_body_breaks_loop(self):
        # BOB-015 characterization: an HTTP-error-shaped body must not crash
        # and must yield no torrents.
        mod, captured = _load_plugin()
        engine = mod.kickass()
        with patch.object(mod, "retrieve_url", return_value="500 Internal Server Error"):
            engine.search("test query")
        assert captured == []

    def test_search_truncated_html_does_not_crash(self):
        # BOB-015 characterization: an unterminated <tr> tag must not crash.
        mod, captured = _load_plugin()
        engine = mod.kickass()
        with patch.object(
            mod, "retrieve_url", return_value='<html><body><tr class="odd"><td>'
        ):
            engine.search("test query")
        assert captured == []


class TestKickassSearchPageCap:
    # A single torrent row that satisfies the HTMLParser.__findTorrents regex
    # so that parser.noTorrents NEVER trips. An index-ignoring / interstitial
    # server that re-serves this body for every page index would otherwise
    # make search() loop forever (compounded by the per-row sleep(1)).
    _ROW = (
        '<tr class="odd">'
        '<div class="torrentname">'
        '<a href="detail/abc" class="cellMainLink">Some Torrent</a>'
        '</div>'
        '<td>1.5 GB</td>'
        '<td class="green center">42</td>'
        '<td class="red lasttd center">7</td>'
        '</tr>'
    )

    def _make_fake_retrieve(self, hard_limit: int):
        """Return (fake, counter_holder).

        The fake ALWAYS serves a matching torrent row for search pages
        (noTorrents never trips) and a magnet for the detail-link fetch.
        It counts SEARCH-page fetches; exceeding hard_limit raises
        AssertionError, which on the unbounded pre-fix code trips because
        the loop never terminates.
        """
        counter = {"search": 0}

        def fake(url: str) -> str:
            if "detail/abc" in url:
                # detail-link fetch: return a body with a magnet
                return '<a href="magnet:?xt=urn:btih:deadbeef">dl</a>'
            counter["search"] += 1
            if counter["search"] > hard_limit:
                raise AssertionError(
                    f"search() exceeded {hard_limit} search-page fetches "
                    f"-> unbounded loop (no page cap)"
                )
            return self._ROW

        return fake, counter

    def test_search_caps_pages_on_index_ignoring_server(self):
        # RED on pre-fix code: `while True:` with no page cap loops forever
        # against a server that re-serves matching rows for every index, so
        # the fake's hard-limit assertion trips. GREEN after MAX_PAGES bounds
        # the loop: search() returns after <= MAX_PAGES (50) search fetches.
        mod, _captured = _load_plugin()
        engine = mod.kickass()
        hard_limit = 200
        fake, counter = self._make_fake_retrieve(hard_limit)
        with patch.object(mod, "retrieve_url", side_effect=fake), patch.object(
            mod, "sleep", lambda _seconds: None
        ):
            engine.search("test query")
        # post-fix: bounded by MAX_PAGES (counter is incremented before the
        # cap check, so it lands at MAX_PAGES + 1 fetches at most).
        assert counter["search"] <= 51, (
            f"search() made {counter['search']} search-page fetches; "
            f"expected <= 51 (MAX_PAGES=50 + 1)"
        )


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

    def test_download_torrent_none_url_does_not_crash(self, capsys):
        # BOB-015 RED: download_torrent(None) called `None.startswith(...)`
        # before any guard -> unhandled AttributeError. A degenerate (None)
        # url must be handled gracefully, never raise.
        mod, _ = _load_plugin()
        engine = mod.kickass()
        engine.download_torrent(None)  # must NOT raise
        out = capsys.readouterr().out
        # graceful fallback emits the engine url so qBittorrent gets the
        # expected `<x> <engine_url>` shape rather than a traceback
        assert engine.url in out

    def test_download_torrent_empty_url_does_not_crash(self, capsys):
        mod, _ = _load_plugin()
        engine = mod.kickass()
        with patch.object(mod, "retrieve_url", return_value=""):
            engine.download_torrent("")  # must NOT raise
        out = capsys.readouterr().out
        assert engine.url in out

    def test_download_torrent_http_error_body_falls_back(self, capsys):
        # GENUINE regex-fallback (else-branch) coverage: retrieve_url returns a
        # NON-EMPTY body that contains NO magnet link, so the magnet regex at
        # kickass.py download_torrent() must NOT match and the code must fall
        # back to the `<url> <engine_url>` shape. This drives the else branch
        # (it would be skipped entirely if the body were empty, which is what
        # the old shadowed-patch version silently did).
        mod, _ = _load_plugin()
        engine = mod.kickass()
        body = "<html><body>500 Internal Server Error, no magnet here</body></html>"
        with patch.object(mod, "retrieve_url", return_value=body):
            engine.download_torrent("http://example.com/detail/err")
        out = capsys.readouterr().out
        # else branch emits exactly "<url> <engine_url>"
        assert out.strip() == "http://example.com/detail/err " + engine.url
        # the non-empty error body must NEVER be echoed verbatim
        assert "Internal Server Error" not in out

    def test_download_torrent_magnet_in_body_extracted(self, capsys):
        # POSITIVE CONTROL: retrieve_url returns a body that DOES contain a
        # magnet:?... link. The regex-match branch (kickass.py
        # download_torrent ~L94-96) must extract and print the MAGNET, not the
        # detail url. This proves the patch actually reaches the regex and the
        # match branch is genuinely exercised.
        mod, _ = _load_plugin()
        engine = mod.kickass()
        magnet = "magnet:?xt=urn:btih:abc123def456&dn=TestMovie"
        body = f'<html><a href="{magnet}">dl</a></html>'
        with patch.object(mod, "retrieve_url", return_value=body):
            engine.download_torrent("http://example.com/detail/ok")
        out = capsys.readouterr().out
        # match branch emits "<magnet> <engine_url>" — the magnet, not the url
        assert out.strip() == magnet + " " + engine.url
        assert "http://example.com/detail/ok" not in out


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

    def test_retrieve_download_link_http_error_page(self):
        # BOB-015 characterization: HTTP-error-shaped detail page has no
        # magnet -> NotFound, no crash.
        mod, _ = _load_plugin()
        engine = mod.kickass()
        parser = engine.HTMLParser(engine.url)
        with patch.object(mod, "retrieve_url", return_value="500 Internal Server Error"):
            result = parser._HTMLParser__retrieve_download_link("http://example.com/detail/e")
        assert result == "NotFound"

    def test_retrieve_download_link_truncated_magnet(self):
        # BOB-015 characterization: an unterminated magnet (no closing quote)
        # does not match the magnet regex -> NotFound, no crash.
        mod, _ = _load_plugin()
        engine = mod.kickass()
        parser = engine.HTMLParser(engine.url)
        with patch.object(mod, "retrieve_url", return_value='href="magnet:?xt=urn:btih:abc'):
            result = parser._HTMLParser__retrieve_download_link("http://example.com/detail/t")
        assert result == "NotFound"

    def test_retrieve_download_link_magnet_found(self):
        mod, _ = _load_plugin()
        engine = mod.kickass()
        parser = engine.HTMLParser(engine.url)
        page = 'some html "magnet:?xt=urn:btih:abc123def456&dn=TestMovie" end'
        with patch.object(mod, "retrieve_url", return_value=page):
            result = parser._HTMLParser__retrieve_download_link("http://example.com/detail/4")
        assert result.startswith("magnet:")
