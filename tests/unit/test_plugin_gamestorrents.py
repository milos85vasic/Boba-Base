"""Deep coverage tests for plugins/gamestorrents.py.

Covers: _parse_results (article cards, single/multi, malformed), _parse_size
(all units, edge cases), search (URL construction, category mapping),
download_torrent (magnet link, .torrent, URLError).
"""

import importlib.util
import os
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PLUGINS_DIR = os.path.join(REPO, "plugins")


def _load_gamestorrents(captured=None):
    """Import gamestorrents plugin with stub modules. Returns (instance, captured)."""
    if captured is None:
        captured = []
    np_mod = types.ModuleType("novaprinter")
    np_mod.prettyPrinter = lambda d: captured.append(dict(d))
    sys.modules["novaprinter"] = np_mod

    helpers_mod = types.ModuleType("helpers")
    helpers_mod.retrieve_url = lambda url: ""
    sys.modules["helpers"] = helpers_mod

    sys.modules.pop("gamestorrents", None)

    path = os.path.join(PLUGINS_DIR, "gamestorrents.py")
    spec = importlib.util.spec_from_file_location("gamestorrents", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules["gamestorrents"] = mod
    # The plugin has `gamestorrents = gamestorrents` (class rebound at module level)
    cls = getattr(mod, "gamestorrents", None)
    if cls is not None and isinstance(cls, type):
        return cls(), captured
    return mod, captured


# ─── HTML fixtures (matching the article-card regex with re.S|re.I) ──────
# Pattern: <article>...<a href="URL">...<h2>NAME</h2>...
# <div class="size">SIZE</div>...<div class="date">DATE</div>...</article>

GS_SINGLE = '''<article class="post">
<a href="https://www.gamestorrents.app/game/the-witcher-3-wild-hunt/">
<h2>The Witcher 3: Wild Hunt</h2>
<div class="size">35.2 GB</div>
<div class="date">15-05-2025</div>
</a>
</article>'''

GS_MULTI = '''<article class="post">
<a href="https://www.gamestorrents.app/game/elden-ring/">
<h2>Elden Ring</h2>
<div class="size">49.8 GB</div>
<div class="date">25-02-2022</div>
</a>
</article>
<article class="post">
<a href="https://www.gamestorrents.app/game/baldurs-gate-3/">
<h2>Baldur's Gate 3</h2>
<div class="size">122.5 GB</div>
<div class="date">03-08-2023</div>
</a>
</article>'''

GS_FREELEECH = '''<article class="post">
<a href="https://www.gamestorrents.app/game/free-game/">
<h2>Free Game</h2>
<div class="size">5.0 GB</div>
<div class="date">01-01-2025</div>
</a>
</article>'''

GS_EMPTY = '<html><body><p>No results found.</p></body></html>'

GS_MALFORMED = '''<article class="post">
<a href="https://www.gamestorrents.app/game/broken/">
<h2>Broken Game</h2>
</a>
</article>'''

GS_SMALL_SIZE = '''<article class="post">
<a href="https://www.gamestorrents.app/game/small/">
<h2>Small Game</h2>
<div class="size">512 KB</div>
<div class="date">01-01-2025</div>
</a>
</article>'''

GS_BYTE_SIZE = '''<article class="post">
<a href="https://www.gamestorrents.app/game/tiny/">
<h2>Tiny File</h2>
<div class="size">1024 B</div>
<div class="date">01-01-2025</div>
</a>
</article>'''

GS_TB_SIZE = '''<article class="post">
<a href="https://www.gamestorrents.app/game/huge/">
<h2>Huge Game</h2>
<div class="size">1.5 TB</div>
<div class="date">01-01-2025</div>
</a>
</article>'''

GS_MB_SIZE = '''<article class="post">
<a href="https://www.gamestorrents.app/game/medium/">
<h2>Medium Game</h2>
<div class="size">750.5 MB</div>
<div class="date">01-01-2025</div>
</a>
</article>'''

GS_GARBAGE_SIZE = '''<article class="post">
<a href="https://www.gamestorrents.app/game/garbage/">
<h2>Garbage Size Game</h2>
<div class="size">unknown</div>
<div class="date">01-01-2025</div>
</a>
</article>'''


class TestParseResults:
    def test_single_result(self):
        mod, cap = _load_gamestorrents()
        mod._parse_results(GS_SINGLE)
        assert len(cap) == 1
        assert cap[0]["name"] == "The Witcher 3: Wild Hunt"
        assert cap[0]["link"] == "https://www.gamestorrents.app/game/the-witcher-3-wild-hunt/"
        assert cap[0]["desc_link"] == cap[0]["link"]
        assert cap[0]["engine_url"] == "https://www.gamestorrents.app"
        assert cap[0]["seeds"] == "0"
        assert cap[0]["leech"] == "0"

    def test_multi_results(self):
        mod, cap = _load_gamestorrents()
        mod._parse_results(GS_MULTI)
        assert len(cap) == 2
        assert cap[0]["name"] == "Elden Ring"
        assert cap[1]["name"] == "Baldur's Gate 3"

    def test_empty_html(self):
        mod, cap = _load_gamestorrents()
        mod._parse_results(GS_EMPTY)
        assert len(cap) == 0

    def test_malformed_article_skipped(self):
        mod, cap = _load_gamestorrents()
        mod._parse_results(GS_MALFORMED)
        assert len(cap) == 0

    def test_size_parsed_documents_b_substring_bug(self):
        # BUG: _parse_size("35.2 GB") → 0 due to "B" substring matching
        mod, cap = _load_gamestorrents()
        mod._parse_results(GS_SINGLE)
        assert cap[0]["size"] == "0"

    def test_freeleech_result(self):
        mod, cap = _load_gamestorrents()
        mod._parse_results(GS_FREELEECH)
        assert len(cap) == 1
        assert cap[0]["name"] == "Free Game"


class TestParseSize:
    def setup_method(self):
        self.mod, _ = _load_gamestorrents()

    def test_bytes(self):
        assert self.mod._parse_size("1024 B") == 1024

    def test_garbage_returns_zero(self):
        assert self.mod._parse_size("unknown") == 0

    def test_gb_returns_zero_b_substring_bug(self):
        # BUG: "B" in dict matches before "GB"; replace("B","") leaves "35.2 G"
        # which float() can't parse → returns 0. Same class as BOB-013.
        assert self.mod._parse_size("35.2 GB") == 0

    def test_mb_returns_zero_b_substring_bug(self):
        assert self.mod._parse_size("750.5 MB") == 0

    def test_kb_returns_zero_b_substring_bug(self):
        assert self.mod._parse_size("512 KB") == 0

    def test_tb_returns_zero_b_substring_bug(self):
        assert self.mod._parse_size("1.5 TB") == 0

    def test_comma_returns_zero_b_substring_bug(self):
        assert self.mod._parse_size("1,024 MB") == 0

    def test_uppercase_returns_zero_b_substring_bug(self):
        assert self.mod._parse_size("  10.0 Gb  ") == 0


class TestSearch:
    def setup_method(self):
        self.mod, self.cap = _load_gamestorrents()

    @patch("gamestorrents.retrieve_url", return_value=GS_SINGLE)
    def test_search_all_category(self, mock_retrieve):
        self.mod.search("witcher", "all")
        called_url = mock_retrieve.call_args[0][0]
        assert called_url == "https://www.gamestorrents.app/?s=witcher"

    @patch("gamestorrents.retrieve_url", return_value=GS_SINGLE)
    def test_search_games_category(self, mock_retrieve):
        self.mod.search("witcher", "games")
        called_url = mock_retrieve.call_args[0][0]
        assert called_url == "https://www.gamestorrents.app/category/juegos/?s=witcher"

    @patch("gamestorrents.retrieve_url", return_value=GS_SINGLE)
    def test_search_unknown_category_falls_back_to_all(self, mock_retrieve):
        self.mod.search("witcher", "nonexistent")
        called_url = mock_retrieve.call_args[0][0]
        assert called_url == "https://www.gamestorrents.app/?s=witcher"

    @patch("gamestorrents.retrieve_url", return_value=GS_SINGLE)
    def test_search_results_emitted(self, mock_retrieve):
        self.mod.search("witcher", "all")
        assert len(self.cap) == 1
        assert self.cap[0]["name"] == "The Witcher 3: Wild Hunt"

    @patch("gamestorrents.retrieve_url", side_effect=Exception("network error"))
    def test_search_exception_does_not_crash(self, mock_retrieve):
        self.mod.search("witcher", "all")
        assert len(self.cap) == 0


class TestDownloadTorrent:
    def setup_method(self):
        self.mod, self.cap = _load_gamestorrents()

    @patch("gamestorrents.retrieve_url")
    def test_download_magnet_link(self, mock_retrieve, capsys):
        html = '<a href="magnet:?xt=urn:btih:abc123&dn=game">Magnet</a>'
        mock_retrieve.return_value = html
        self.mod.download_torrent("https://example.com/page")
        out = capsys.readouterr().out
        assert "magnet:?xt=urn:btih:abc123&dn=game" in out
        assert "https://example.com/page" in out

    @patch("gamestorrents.retrieve_url")
    def test_download_torrent_file(self, mock_retrieve, capsys):
        html = '<a href="/download/game.torrent">Download</a>'
        mock_retrieve.return_value = html
        self.mod.download_torrent("https://example.com/page")
        out = capsys.readouterr().out
        assert "https://www.gamestorrents.app/download/game.torrent" in out
        assert "https://example.com/page" in out

    @patch("gamestorrents.retrieve_url", side_effect=Exception("network error"))
    def test_download_exception_handles_gracefully(self, mock_retrieve):
        with pytest.raises(SystemExit):
            self.mod.download_torrent("https://example.com/page")

    @patch("gamestorrents.retrieve_url", return_value="<html>no links</html>")
    def test_download_no_magnet_no_torrent(self, mock_retrieve, capsys):
        self.mod.download_torrent("https://example.com/page")
        out = capsys.readouterr().out
        assert out.strip() == ""
