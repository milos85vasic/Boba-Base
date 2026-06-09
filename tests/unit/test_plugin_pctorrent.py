"""Deep coverage tests for plugins/community/pctorrent.py.

Covers: _parse_results (article cards, single/multi, malformed), _parse_size
(all units, edge cases), search (URL construction, category mapping),
download_torrent (magnet link, .torrent, exception), case-insensitive regex.
"""

import importlib.util
import os
import sys
import time
import types
from unittest.mock import MagicMock, patch

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PLUGINS_DIR = os.path.join(REPO, "plugins", "community")


def _load_pctorrent(captured=None):
    if captured is None:
        captured = []
    np_mod = types.ModuleType("novaprinter")
    np_mod.prettyPrinter = lambda d: captured.append(dict(d))
    sys.modules["novaprinter"] = np_mod

    helpers_mod = types.ModuleType("helpers")
    helpers_mod.retrieve_url = lambda url: ""
    sys.modules["helpers"] = helpers_mod

    sys.modules.pop("pctorrent", None)

    path = os.path.join(PLUGINS_DIR, "pctorrent.py")
    spec = importlib.util.spec_from_file_location("pctorrent", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules["pctorrent"] = mod
    cls = getattr(mod, "pctorrent", None)
    if cls is not None and isinstance(cls, type):
        return cls(), captured
    return mod, captured


PC_SINGLE = '''<article class="post item">
<a href="https://pctorrent.ru/igry/123-witcher.html">The Witcher 3: Wild Hunt</a>
<div class="block size">35.2 GB</div>
<div class="block date">15.05.2025</div>
</article>'''

PC_MULTI = '''<article class="post item">
<a href="https://pctorrent.ru/igry/123-elden.html">Elden Ring</a>
<div class="block size">49.8 GB</div>
<div class="block date">25.02.2022</div>
</article>
<article class="post item">
<a href="https://pctorrent.ru/igry/456-bg3.html">Baldur's Gate 3</a>
<div class="block size">122.5 GB</div>
<div class="block date">03.08.2023</div>
</article>'''

PC_EMPTY = '<html><body><p>No results found.</p></body></html>'

PC_MALFORMED = '''<article class="post item">
<a href="https://pctorrent.ru/broken.html">Broken Game</a>
</article>'''

PC_SMALL_SIZE = '''<article class="post item">
<a href="https://pctorrent.ru/small.html">Small Game</a>
<div class="block size">512 KB</div>
<div class="block date">01.01.2025</div>
</article>'''

PC_BYTE_SIZE = '''<article class="post item">
<a href="https://pctorrent.ru/tiny.html">Tiny File</a>
<div class="block size">1024 B</div>
<div class="block date">01.01.2025</div>
</article>'''

PC_TB_SIZE = '''<article class="post item">
<a href="https://pctorrent.ru/huge.html">Huge Game</a>
<div class="block size">1.5 TB</div>
<div class="block date">01.01.2025</div>
</article>'''

PC_MB_SIZE = '''<article class="post item">
<a href="https://pctorrent.ru/medium.html">Medium Game</a>
<div class="block size">750.5 MB</div>
<div class="block date">01.01.2025</div>
</article>'''

PC_GARBAGE_SIZE = '''<article class="post item">
<a href="https://pctorrent.ru/garbage.html">Garbage Game</a>
<div class="block size">unknown</div>
<div class="block date">01.01.2025</div>
</article>'''

PC_UPPERCASE_TAGS = '''<ARTICLE class="post item">
<A href="https://pctorrent.ru/case.html">Case Test</A>
<DIV class="block size">10 GB</DIV>
<DIV class="block date">01.01.2025</DIV>
</ARTICLE>'''


class TestParseResults:
    def test_single_result(self):
        mod, cap = _load_pctorrent()
        mod._parse_results(PC_SINGLE)
        assert len(cap) == 1
        assert cap[0]["name"] == "The Witcher 3: Wild Hunt"
        assert cap[0]["link"] == "https://pctorrent.ru/igry/123-witcher.html"
        assert cap[0]["desc_link"] == cap[0]["link"]
        assert cap[0]["engine_url"] == "https://pctorrent.ru"
        assert cap[0]["seeds"] == "0"
        assert cap[0]["leech"] == "0"

    def test_multi_results(self):
        mod, cap = _load_pctorrent()
        mod._parse_results(PC_MULTI)
        assert len(cap) == 2
        assert cap[0]["name"] == "Elden Ring"
        assert cap[1]["name"] == "Baldur's Gate 3"

    def test_empty_html(self):
        mod, cap = _load_pctorrent()
        mod._parse_results(PC_EMPTY)
        assert len(cap) == 0

    def test_malformed_article_skipped(self):
        mod, cap = _load_pctorrent()
        mod._parse_results(PC_MALFORMED)
        assert len(cap) == 0

    def test_size_parsed_correctly(self):
        mod, cap = _load_pctorrent()
        mod._parse_results(PC_SINGLE)
        assert cap[0]["size"] == str(int(35.2 * 1024**3))

    def test_pub_date_is_recent(self):
        mod, cap = _load_pctorrent()
        before = int(time.time())
        mod._parse_results(PC_SINGLE)
        after = int(time.time())
        pub_date = int(cap[0]["pub_date"])
        assert before <= pub_date <= after

    def test_regex_case_insensitive(self):
        mod, cap = _load_pctorrent()
        mod._parse_results(PC_UPPERCASE_TAGS)
        assert len(cap) == 1
        assert cap[0]["name"] == "Case Test"
        assert cap[0]["size"] == str(10 * 1024**3)

    def test_garbage_size_emits_zero_bytes(self):
        mod, cap = _load_pctorrent()
        mod._parse_results(PC_GARBAGE_SIZE)
        assert len(cap) == 1
        assert cap[0]["size"] == "0"


class TestParseSize:
    def setup_method(self):
        self.mod, _ = _load_pctorrent()

    def test_bytes(self):
        assert self.mod._parse_size("1024 B") == 1024

    def test_kilobytes(self):
        assert self.mod._parse_size("512 KB") == 512 * 1024

    def test_megabytes(self):
        assert self.mod._parse_size("750.5 MB") == int(750.5 * 1024**2)

    def test_gigabytes(self):
        assert self.mod._parse_size("35.2 GB") == int(35.2 * 1024**3)

    def test_terabytes(self):
        assert self.mod._parse_size("1.5 TB") == int(1.5 * 1024**4)

    def test_garbage_returns_zero(self):
        assert self.mod._parse_size("unknown") == 0

    def test_empty_string_returns_zero(self):
        assert self.mod._parse_size("") == 0

    def test_comma_in_number(self):
        assert self.mod._parse_size("1,024 MB") == 1024 * 1024**2

    def test_whitespace_and_case_normalization(self):
        assert self.mod._parse_size("  10.0 Gb  ") == int(10.0 * 1024**3)

    def test_zero_gigabytes(self):
        assert self.mod._parse_size("0 GB") == 0


class TestSearch:
    def setup_method(self):
        self.mod, self.cap = _load_pctorrent()

    @patch("pctorrent.retrieve_url", return_value=PC_SINGLE)
    def test_search_all_category(self, mock_retrieve):
        self.mod.search("witcher", "all")
        called_url = mock_retrieve.call_args[0][0]
        assert called_url == "https://pctorrent.ru/?do=search&subaction=search&story=witcher"

    @patch("pctorrent.retrieve_url", return_value=PC_SINGLE)
    def test_search_games_category(self, mock_retrieve):
        self.mod.search("witcher", "games")
        called_url = mock_retrieve.call_args[0][0]
        assert called_url == "https://pctorrent.ru/igry/?do=search&subaction=search&story=witcher"

    @patch("pctorrent.retrieve_url", return_value=PC_SINGLE)
    def test_search_unknown_category_falls_back_to_all(self, mock_retrieve):
        self.mod.search("witcher", "nonexistent")
        called_url = mock_retrieve.call_args[0][0]
        assert called_url == "https://pctorrent.ru/?do=search&subaction=search&story=witcher"

    @patch("pctorrent.retrieve_url", return_value=PC_SINGLE)
    def test_search_results_emitted(self, mock_retrieve):
        self.mod.search("witcher", "all")
        assert len(self.cap) == 1
        assert self.cap[0]["name"] == "The Witcher 3: Wild Hunt"

    @patch("pctorrent.retrieve_url", side_effect=Exception("network error"))
    def test_search_exception_does_not_crash(self, mock_retrieve):
        self.mod.search("witcher", "all")
        assert len(self.cap) == 0

    @patch("pctorrent.retrieve_url", return_value=PC_SINGLE)
    def test_search_urlencodes_special_characters(self, mock_retrieve):
        self.mod.search("the witcher 3", "all")
        called_url = mock_retrieve.call_args[0][0]
        assert "the%20witcher%203" in called_url


class TestDownloadTorrent:
    def setup_method(self):
        self.mod, self.cap = _load_pctorrent()

    @patch("pctorrent.retrieve_url")
    def test_download_magnet_link(self, mock_retrieve, capsys):
        html = '<a href="magnet:?xt=urn:btih:abc123&dn=game">Magnet</a>'
        mock_retrieve.return_value = html
        self.mod.download_torrent("https://example.com/page")
        out = capsys.readouterr().out
        assert "magnet:?xt=urn:btih:abc123&dn=game" in out
        assert "https://example.com/page" in out

    @patch("pctorrent.retrieve_url")
    def test_download_torrent_file(self, mock_retrieve, capsys):
        html = '<a href="/engine/download.php?id=123">Download</a>'
        mock_retrieve.return_value = html
        self.mod.download_torrent("https://example.com/page")
        out = capsys.readouterr().out
        assert "https://pctorrent.ru/engine/download.php?id=123" in out
        assert "https://example.com/page" in out

    @patch("pctorrent.retrieve_url", side_effect=Exception("network error"))
    def test_download_exception_handles_gracefully(self, mock_retrieve):
        with pytest.raises(SystemExit):
            self.mod.download_torrent("https://example.com/page")

    @patch("pctorrent.retrieve_url", return_value="<html>no links</html>")
    def test_download_no_magnet_no_torrent(self, mock_retrieve, capsys):
        self.mod.download_torrent("https://example.com/page")
        out = capsys.readouterr().out
        assert out.strip() == ""

    @patch("pctorrent.retrieve_url")
    def test_download_magnet_priority_over_torrent(self, mock_retrieve, capsys):
        html = '<a href="magnet:?xt=urn:btih:abc123">Magnet</a><a href="/engine/download.php?id=456">Torrent</a>'
        mock_retrieve.return_value = html
        self.mod.download_torrent("https://example.com/page")
        out = capsys.readouterr().out
        assert "magnet:?xt=urn:btih:abc123" in out
        assert "engine/download.php" not in out

    @patch("pctorrent.retrieve_url")
    def test_download_stderr_on_exception(self, mock_retrieve, capsys):
        mock_retrieve.side_effect = Exception("connection refused")
        with pytest.raises(SystemExit):
            self.mod.download_torrent("https://example.com/page")
        err = capsys.readouterr().err
        assert "Download error" in err
        assert "connection refused" in err
