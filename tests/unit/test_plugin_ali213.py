"""Deep coverage tests for plugins/community/ali213.py.

Covers: search (URL construction, result parsing, threading, empty results),
handle_gamepage (full multi-step flow, missing data at each step, retry logic),
download_torrent (magnet input, magnet in page, .torrent fallback),
plugin attributes (regex patterns, constants, category mapping),
threading behaviour, exception resilience.
"""

import importlib.util
import os
import sys
import threading
import types
from unittest.mock import call, patch

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PLUGINS_DIR = os.path.join(REPO, "plugins")


def _load_ali213(captured=None):
    if captured is None:
        captured = []
    np_mod = types.ModuleType("novaprinter")
    np_mod.prettyPrinter = lambda d: captured.append(dict(d))
    sys.modules["novaprinter"] = np_mod

    helpers_mod = types.ModuleType("helpers")
    helpers_mod.retrieve_url = lambda url: ""
    sys.modules["helpers"] = helpers_mod

    sys.modules.pop("ali213", None)

    path = os.path.join(PLUGINS_DIR, "community", "ali213.py")
    spec = importlib.util.spec_from_file_location("ali213", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules["ali213"] = mod
    return mod.ali213(), captured


# ─── HTML fixtures ───────────────────────────────────────────────────────

AS_SEARCH_EMPTY = '<html><body>No search results found.</body></html>'

AS_SEARCH_SINGLE = """<html><body>
<p class="downAddress"><a href="http://down.ali213.net/pcgame/the-witcher-3.html" target="_blank"><em>35.2G</em>
</body></html>"""

AS_SEARCH_MULTI = """<html><body>
<p class="downAddress"><a href="http://down.ali213.net/pcgame/elden-ring.html" target="_blank"><em>49.8G</em>
<p class="downAddress"><a href="http://down.ali213.net/pcgame/baldurs-gate-3.html" target="_blank"><em>122G</em>
<p class="downAddress"><a href="http://down.ali213.net/pcgame/cyberpunk.html" target="_blank"><em>75.2G</em>
<p class="downAddress"><a href="http://down.ali213.net/pcgame/red-dead.html" target="_blank"><em>120G</em>
<p class="downAddress"><a href="http://down.ali213.net/pcgame/starcraft.html" target="_blank"><em>32GB</em>
<p class="downAddress"><a href="http://down.ali213.net/pcgame/diablo.html" target="_blank"><em>45.5G</em>
</body></html>"""

AS_GAME_PAGE = '<html><body>var downUrl ="/abc123key"</body></html>'

AS_GAME_PAGE_NO_DOWNURL = '<html><body>No download URL here.</body></html>'

AS_SOFT50_PAGE = """<html><body>
<a class="result_js" href="http://btfile.soft5566.com/y/some-game" target="_blank">Download</a>
</body></html>"""

AS_SOFT50_PAGE_NO_RESULT_JS = '<html><body>No result here.</body></html>'

AS_BTFILE_PAGE = """<html><body>
<a id="btbtn" href="http://btfile.soft5566.com/y/thewitcher3.torrent" target="_blank">Download Torrent</a>
</body></html>"""

AS_BTFILE_PAGE_NO_BTBUTTON = '<html><body>No btbtn here.</body></html>'


# ─── FakeThread helpers ──────────────────────────────────────────────────

class _FakeThread:
    """Records creation args and allows call assertions without real threads."""

    instances = []

    def __init__(self, target=None, args=None):
        self.target = target
        self.args = args
        self._joined = False
        _FakeThread.instances.append(self)

    def start(self):
        pass

    def join(self):
        self._joined = True

    @classmethod
    def reset(cls):
        cls.instances.clear()


def _patch_helpers_retrieve_url(mock_fn):
    """Patch helpers.retrieve_url so download_torrent's local import sees it."""
    return patch.object(sys.modules["helpers"], "retrieve_url", mock_fn)


# ─── Plugin attributes ────────────────────────────────────────────────────


class TestPluginAttributes:
    def test_basic_attributes(self):
        inst, cap = _load_ali213()
        assert inst.url == "http://down.ali213.net/"
        assert inst.name == "ali213"
        assert inst.games_to_parse == 5
        assert inst.first_dl_site == "http://www.soft50.com/"
        assert inst.final_dl_site == "http://btfile.soft5566.com/y/"

    def test_supported_categories(self):
        inst, cap = _load_ali213()
        assert inst.supported_categories == {"all": True, "games": True, "software": True}


# ─── Search ────────────────────────────────────────────────────────────────


class TestSearch:
    def setup_method(self):
        _FakeThread.reset()
        self.inst, self.cap = _load_ali213()

    @patch("ali213.retrieve_url", return_value=AS_SEARCH_SINGLE)
    @patch("ali213.time.sleep")
    def test_search_url_construction(self, mock_sleep, mock_retrieve):
        self.inst.search("witcher")
        mock_retrieve.assert_any_call(
            "http://down.ali213.net/search?kw=witcher&submit="
        )

    @patch("ali213.retrieve_url", return_value=AS_SEARCH_SINGLE)
    @patch("ali213.time.sleep")
    def test_search_first_call_is_query_url(self, mock_sleep, mock_retrieve):
        self.inst.search("ark survival")
        first_call = mock_retrieve.mock_calls[0]
        assert first_call == call("http://down.ali213.net/search?kw=ark survival&submit=")

    @patch("ali213.retrieve_url")
    @patch("ali213.time.sleep")
    def test_search_single_result_full_flow(self, mock_sleep, mock_retrieve):
        mock_retrieve.side_effect = [
            AS_SEARCH_SINGLE,
            AS_GAME_PAGE,
            AS_SOFT50_PAGE,
            AS_BTFILE_PAGE,
        ]
        self.inst.search("witcher")
        assert len(self.cap) == 1
        r = self.cap[0]
        assert r["size"] == "35.2G"
        assert r["link"] == "http://btfile.soft5566.com/y/thewitcher3.torrent"
        assert r["desc_link"] == "http://btfile.soft5566.com/y/some-game"
        assert r["engine_url"] == "http://down.ali213.net/"
        assert r["seeds"] == -1
        assert r["leech"] == -1
        assert "thewitcher3.torrent" in r["name"]

    @patch("ali213.retrieve_url", return_value=AS_SEARCH_MULTI)
    @patch("ali213.time.sleep")
    def test_search_spawns_threads_per_result(self, mock_sleep, mock_retrieve):
        with patch("ali213.threading.Thread", _FakeThread):
            self.inst.search("game")
        assert len(_FakeThread.instances) == 5

    @patch("ali213.retrieve_url", return_value=AS_SEARCH_MULTI)
    @patch("ali213.time.sleep")
    def test_search_joins_all_threads(self, mock_sleep, mock_retrieve):
        with patch("ali213.threading.Thread", _FakeThread):
            self.inst.search("game")
        assert all(t._joined for t in _FakeThread.instances)
        assert len(_FakeThread.instances) == 5

    @patch("ali213.retrieve_url", return_value=AS_SEARCH_MULTI)
    @patch("ali213.time.sleep")
    def test_search_results_less_than_games_to_parse(self, mock_sleep, mock_retrieve):
        self.inst.games_to_parse = 20
        with patch("ali213.threading.Thread", _FakeThread):
            self.inst.search("game")
        assert self.inst.games_to_parse == 6

    @patch("ali213.retrieve_url", return_value=AS_SEARCH_MULTI)
    @patch("ali213.time.sleep")
    def test_search_thread_args_match_regex_groups(self, mock_sleep, mock_retrieve):
        with patch("ali213.threading.Thread", _FakeThread):
            self.inst.search("game")
        assert _FakeThread.instances[0].args[0] == ("elden-ring.html", "49.8G")
        assert _FakeThread.instances[1].args[0] == ("baldurs-gate-3.html", "122G")

    @patch("ali213.retrieve_url", return_value=AS_SEARCH_EMPTY)
    def test_search_empty_results(self, mock_retrieve):
        self.inst.search("nonexistent_game_xyz")
        assert len(self.cap) == 0

    @patch("ali213.retrieve_url", side_effect=Exception("network down"))
    @patch("ali213.time.sleep")
    def test_search_exception_propagates(self, mock_sleep, mock_retrieve):
        with pytest.raises(Exception, match="network down"):
            self.inst.search("anything")


# ─── HandleGamepage ────────────────────────────────────────────────────────


class TestHandleGamepage:
    def setup_method(self):
        self.inst, self.cap = _load_ali213()

    @patch("ali213.retrieve_url")
    @patch("ali213.time.sleep")
    def test_full_flow_emits_result(self, mock_sleep, mock_retrieve):
        mock_retrieve.side_effect = [
            AS_GAME_PAGE,
            AS_SOFT50_PAGE,
            AS_BTFILE_PAGE,
        ]
        self.inst.handle_gamepage(("the-witcher-3.html", "35.2G"))
        assert len(self.cap) == 1
        r = self.cap[0]
        assert r["size"] == "35.2G"
        assert r["link"] == "http://btfile.soft5566.com/y/thewitcher3.torrent"
        assert r["desc_link"] == "http://btfile.soft5566.com/y/some-game"
        assert r["engine_url"] == "http://down.ali213.net/"
        assert r["seeds"] == -1
        assert r["leech"] == -1
        assert "thewitcher3.torrent" in r["name"]

    @patch("ali213.retrieve_url")
    @patch("ali213.time.sleep")
    def test_gamepage_url_constructed_correctly(self, mock_sleep, mock_retrieve):
        mock_retrieve.side_effect = [
            AS_GAME_PAGE,
            AS_SOFT50_PAGE,
            AS_BTFILE_PAGE,
        ]
        self.inst.handle_gamepage(("elden-ring.html", "49.8G"))
        mock_retrieve.assert_any_call("http://down.ali213.net/pcgame/elden-ring.html")

    @patch("ali213.retrieve_url")
    @patch("ali213.time.sleep")
    def test_soft50_url_constructed_correctly(self, mock_sleep, mock_retrieve):
        mock_retrieve.side_effect = [
            AS_GAME_PAGE,
            AS_SOFT50_PAGE,
            AS_BTFILE_PAGE,
        ]
        self.inst.handle_gamepage(("elden-ring.html", "49.8G"))
        mock_retrieve.assert_any_call("http://www.soft50.com/abc123key")

    @patch("ali213.retrieve_url", return_value=AS_GAME_PAGE_NO_DOWNURL)
    @patch("ali213.time.sleep")
    def test_no_downurl_skips_silently(self, mock_sleep, mock_retrieve):
        self.inst.handle_gamepage(("the-witcher-3.html", "35.2G"))
        assert len(self.cap) == 0

    @patch("ali213.retrieve_url")
    @patch("ali213.time.sleep")
    def test_no_result_js_skips_silently(self, mock_sleep, mock_retrieve):
        mock_retrieve.side_effect = [
            AS_GAME_PAGE,
            AS_SOFT50_PAGE_NO_RESULT_JS,
        ]
        self.inst.handle_gamepage(("the-witcher-3.html", "35.2G"))
        assert len(self.cap) == 0

    @patch("ali213.retrieve_url")
    @patch("ali213.time.sleep")
    def test_no_btbtn_skips_silently(self, mock_sleep, mock_retrieve):
        mock_retrieve.side_effect = [
            AS_GAME_PAGE,
            AS_SOFT50_PAGE,
            AS_BTFILE_PAGE_NO_BTBUTTON,
        ]
        self.inst.handle_gamepage(("the-witcher-3.html", "35.2G"))
        assert len(self.cap) == 0

    @patch("ali213.retrieve_url")
    @patch("ali213.time.sleep")
    def test_retry_logic_on_empty_soft50_response(self, mock_sleep, mock_retrieve):
        mock_retrieve.side_effect = [
            AS_GAME_PAGE,
            "",
            "",
            "",
            AS_SOFT50_PAGE,
            AS_BTFILE_PAGE,
        ]
        self.inst.handle_gamepage(("the-witcher-3.html", "35.2G"))
        assert mock_sleep.call_count == 4
        assert len(self.cap) == 1

    @patch("ali213.retrieve_url")
    @patch("ali213.time.sleep")
    def test_retry_exhaustion_returns_silently(self, mock_sleep, mock_retrieve):
        mock_retrieve.side_effect = [
            AS_GAME_PAGE,
        ] + [""] * 21
        self.inst.handle_gamepage(("the-witcher-3.html", "35.2G"))
        assert mock_sleep.call_count == 20
        assert len(self.cap) == 0

    @patch("ali213.retrieve_url")
    @patch("ali213.time.sleep")
    def test_max_retries_does_not_exceed_twenty(self, mock_sleep, mock_retrieve):
        mock_retrieve.side_effect = [
            AS_GAME_PAGE,
        ] + [""] * 25
        self.inst.handle_gamepage(("the-witcher-3.html", "35.2G"))
        assert mock_sleep.call_count == 20


# ─── DownloadTorrent ───────────────────────────────────────────────────────


class TestDownloadTorrent:
    def setup_method(self):
        self.inst, self.cap = _load_ali213()

    def test_magnet_input_printed_directly(self, capsys):
        magnet = "magnet:?xt=urn:btih:abc123&dn=game"
        self.inst.download_torrent(magnet)
        out = capsys.readouterr().out
        assert magnet in out
        assert self.inst.url in out

    def test_magnet_in_page_extracted_and_printed(self, capsys):
        mock = sys.modules["helpers"].retrieve_url
        try:
            sys.modules["helpers"].retrieve_url = (
                lambda url: '<a href="magnet:?xt=urn:btih:deadbeef&dn=mygame">Download</a>'
            )
            self.inst.download_torrent("http://btfile.soft5566.com/y/some.torrent")
        finally:
            sys.modules["helpers"].retrieve_url = mock
        out = capsys.readouterr().out
        assert "magnet:?xt=urn:btih:deadbeef&dn=mygame" in out
        assert self.inst.url in out

    def test_no_magnet_prints_original_url(self, capsys):
        mock = sys.modules["helpers"].retrieve_url
        try:
            sys.modules["helpers"].retrieve_url = (
                lambda url: "<html><body>No magnet here.</body></html>"
            )
            original = "http://btfile.soft5566.com/y/some.torrent"
            self.inst.download_torrent(original)
        finally:
            sys.modules["helpers"].retrieve_url = mock
        out = capsys.readouterr().out
        assert original in out
        assert self.inst.url in out

    def test_multiple_magnets_uses_first(self, capsys):
        mock = sys.modules["helpers"].retrieve_url
        try:
            sys.modules["helpers"].retrieve_url = (
                lambda url: (
                    '<a href="magnet:?xt=urn:btih:first">First</a>'
                    '<a href="magnet:?xt=urn:btih:second">Second</a>'
                )
            )
            self.inst.download_torrent("http://btfile.soft5566.com/y/some.torrent")
        finally:
            sys.modules["helpers"].retrieve_url = mock
        out = capsys.readouterr().out
        assert "magnet:?xt=urn:btih:first" in out
        assert "second" not in out

    def test_magnet_regex_requires_question_mark(self, capsys):
        mock = sys.modules["helpers"].retrieve_url
        try:
            sys.modules["helpers"].retrieve_url = (
                lambda url: '<a href="magnet:xt=urn:btih:noquestion">No Question</a>'
            )
            original = "http://btfile.soft5566.com/y/some.torrent"
            self.inst.download_torrent(original)
        finally:
            sys.modules["helpers"].retrieve_url = mock
        out = capsys.readouterr().out
        assert original in out
        assert "magnet:xt=urn:btih:noquestion" not in out
