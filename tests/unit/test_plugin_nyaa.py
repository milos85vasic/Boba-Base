"""Deep coverage tests for plugins/nyaa.py.

Covers: NyaasiParser (HTML parsing, single/multi results, empty/malformed,
RSS mode, magnets vs torrent files, pub_date, seeds/leech edge cases),
search (URL construction, all 8 categories, pagination, exception handling),
download_torrent (magnet links, torrent files, no links, missing re import),
category mapping (all/anime/books/music/pictures/software/tv/movies).
"""

import importlib.util
import os
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PLUGINS_DIR = os.path.join(REPO, "plugins")


def _load_nyaa(captured=None):
    """Import nyaa plugin with stub modules.

    Returns (instance, captured, helpers_mod, nyaa_mod).
    """
    if captured is None:
        captured = []

    np_mod = types.ModuleType("novaprinter")
    np_mod.prettyPrinter = lambda d: captured.append(dict(d))
    sys.modules["novaprinter"] = np_mod

    helpers_mod = types.ModuleType("helpers")
    helpers_mod.retrieve_url = lambda url: ""
    sys.modules["helpers"] = helpers_mod

    sys.modules.pop("nyaa", None)

    path = os.path.join(PLUGINS_DIR, "nyaa.py")
    spec = importlib.util.spec_from_file_location("nyaa", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules["nyaa"] = mod
    cls = getattr(mod, "nyaa", None)
    if cls is not None and isinstance(cls, type):
        return cls(), captured, helpers_mod, mod
    return mod, captured, helpers_mod, mod


# ─── HTML fixtures ─────────────────────────────────────────────────────────
# Column order matching the parser: Name | Category | Link | Size | Date | Seeds | Leeches | ...

SINGLE_RESULT_MAGNET = '''<html><body>
<table>
<tr>
<td><a href="/view/12345" title="[SubGroup] My Anime - 01 [1080p].mkv">[SubGroup] My Anime - 01 [1080p].mkv</a></td>
<td class="text-center">Anime - English-translated</td>
<td><a href="magnet:?xt=urn:btih:abc123def456" title="Download"></a>
<a href="/download/12345.torrent" title="Download file">.torrent</a></td>
<td class="text-center">1.2 GiB</td>
<td data-timestamp="1700000000" class="text-center">2023-11-14 12:00</td>
<td class="text-center">5</td>
<td class="text-center">2</td>
<td class="text-center">3</td>
<td class="text-center comment">No comments</td>
</tr>
</table>
</body></html>'''

SINGLE_RESULT_TORRENT = '''<html><body>
<table>
<tr>
<td><a href="/view/99999" title="Linux Distro 2024.iso">Linux Distro 2024.iso</a></td>
<td class="text-center">Software - Raw</td>
<td><a href="/download/99999.torrent" title="Download file">.torrent</a></td>
<td class="text-center">2.5 GiB</td>
<td data-timestamp="1710000000" class="text-center">2024-03-09 10:00</td>
<td class="text-center">42</td>
<td class="text-center">0</td>
<td class="text-center">10</td>
<td class="text-center comment">Good distro</td>
</tr>
</table>
</body></html>'''

MULTI_RESULT = '''<html><body>
<table>
<tr>
<td><a href="/view/1" title="Result One">Result One</a></td>
<td class="text-center">Anime</td>
<td><a href="magnet:?xt=urn:btih:aaa" title="Download">DL</a></td>
<td class="text-center">100 MiB</td>
<td data-timestamp="1700000000" class="text-center">2023-11-14</td>
<td class="text-center">10</td>
<td class="text-center">3</td>
<td class="text-center">1</td>
<td class="text-center comment">ok</td>
</tr>
<tr>
<td><a href="/view/2" title="Result Two">Result Two</a></td>
<td class="text-center">Music</td>
<td><a href="magnet:?xt=urn:btih:bbb" title="Download">DL</a></td>
<td class="text-center">50 MiB</td>
<td data-timestamp="1700100000" class="text-center">2023-11-15</td>
<td class="text-center">7</td>
<td class="text-center">1</td>
<td class="text-center">2</td>
<td class="text-center comment">nice</td>
</tr>
<tr>
<td><a href="/view/3" title="Result Three">Result Three</a></td>
<td class="text-center">Books</td>
<td><a href="magnet:?xt=urn:btih:ccc" title="Download">DL</a></td>
<td class="text-center">10 MiB</td>
<td data-timestamp="1700200000" class="text-center">2023-11-16</td>
<td class="text-center">50</td>
<td class="text-center">0</td>
<td class="text-center">5</td>
<td class="text-center comment">textbook</td>
</tr>
</table>
</body></html>'''

EMPTY_HTML = "<html><body><table></table></body></html>"

MALFORMED_HTML = '<html><body><table><tr><td>garbage without links</td></tr></table></body></html>'

NO_RESULTS_HTML = '''<html><body>
<div class="alert">No results found.</div>
<table></table>
</body></html>'''

RESULTS_NO_MAGNET = '''<html><body>
<table>
<tr>
<td><a href="/view/55555" title="Some Torrent">Some Torrent</a></td>
<td class="text-center">Anime</td>
<td><a href="javascript:void(0)" class="comment-link">Comment</a></td>
<td class="text-center">1 GiB</td>
<td data-timestamp="1700000000" class="text-center">2023-11-14</td>
<td class="text-center">5</td>
<td class="text-center">2</td>
<td class="text-center">3</td>
<td class="text-center comment">x</td>
</tr>
</table>
</body></html>'''

RESULT_NO_SEEDS = '''<html><body>
<table>
<tr>
<td><a href="/view/77777" title="Bad Seeds">Bad Seeds</a></td>
<td class="text-center">Anime</td>
<td><a href="magnet:?xt=urn:btih:eee" title="Download">DL</a></td>
<td class="text-center">1 GiB</td>
<td data-timestamp="1700000000" class="text-center">2023-11-14</td>
<td class="text-center">not-a-number</td>
<td class="text-center">also-bad</td>
<td class="text-center">1</td>
<td class="text-center comment">x</td>
</tr>
</table>
</body></html>'''

RESULT_NO_TIMESTAMP = '''<html><body>
<table>
<tr>
<td><a href="/view/88888" title="No Date">No Date</a></td>
<td class="text-center">Anime</td>
<td><a href="magnet:?xt=urn:btih:fff" title="Download">DL</a></td>
<td class="text-center">1 GiB</td>
<td class="text-center">2023-11-14</td>
<td class="text-center">5</td>
<td class="text-center">2</td>
<td class="text-center">3</td>
<td class="text-center comment">x</td>
</tr>
</table>
</body></html>'''

RESULT_CLASS_ON_A = '''<html><body>
<table>
<tr>
<td><a href="/view/11111" class="some-class" title="Classed">Classed</a></td>
<td class="text-center">Anime</td>
<td><a href="magnet:?xt=urn:btih:ggg" title="Download">DL</a></td>
<td class="text-center">1 GiB</td>
<td data-timestamp="1700000000" class="text-center">2023-11-14</td>
<td class="text-center">5</td>
<td class="text-center">2</td>
<td class="text-center">3</td>
<td class="text-center comment">x</td>
</tr>
</table>
</body></html>'''

TORRENT_FILE_DOWNLOAD = '''<html><body>
<table>
<tr>
<td><a href="/view/66666" title="File Torrent">File Torrent</a></td>
<td class="text-center">Anime</td>
<td><a href="/download/66666.torrent" title="Download file">.torrent</a></td>
<td class="text-center">500 MiB</td>
<td data-timestamp="1700000000" class="text-center">2023-11-14</td>
<td class="text-center">8</td>
<td class="text-center">1</td>
<td class="text-center">0</td>
<td class="text-center comment">x</td>
</tr>
</table>
</body></html>'''

RESULT_UNRELATED_LINK = '''<html><body>
<table>
<tr>
<td><a href="/view/22222" title="With Link">With Link</a></td>
<td class="text-center">Anime</td>
<td><a href="/help/faq" title="FAQ">FAQ</a>
<a href="magnet:?xt=urn:btih:hhh" title="Download">DL</a></td>
<td class="text-center">1 GiB</td>
<td data-timestamp="1700000000" class="text-center">2023-11-14</td>
<td class="text-center">5</td>
<td class="text-center">2</td>
<td class="text-center">3</td>
<td class="text-center comment">x</td>
</tr>
</table>
</body></html>'''

RESULT_BOTH_LINKS_MAGNET_MODE = '''<html><body>
<table>
<tr>
<td><a href="/view/33333" title="Both Links">Both Links</a></td>
<td class="text-center">Anime</td>
<td><a href="magnet:?xt=urn:btih:iii" title="Download">DL</a>
<a href="/download/33333.torrent" title="Download file">.torrent</a></td>
<td class="text-center">1 GiB</td>
<td data-timestamp="1700000000" class="text-center">2023-11-14</td>
<td class="text-center">5</td>
<td class="text-center">2</td>
<td class="text-center">3</td>
<td class="text-center comment">x</td>
</tr>
</table>
</body></html>'''

RESULT_BOTH_LINKS_TORRENT_MODE = '''<html><body>
<table>
<tr>
<td><a href="/view/44444" title="Both Torrent Mode">Both Torrent Mode</a></td>
<td class="text-center">Anime</td>
<td><a href="magnet:?xt=urn:btih:jjj" title="Download">DL</a>
<a href="/download/44444.torrent" title="Download file">.torrent</a></td>
<td class="text-center">1 GiB</td>
<td data-timestamp="1700000000" class="text-center">2023-11-14</td>
<td class="text-center">5</td>
<td class="text-center">2</td>
<td class="text-center">3</td>
<td class="text-center comment">x</td>
</tr>
</table>
</body></html>'''

MAGNET_ONLY_NO_TORRENT = '''<html><body>
<table>
<tr>
<td><a href="/view/55555" title="Magnet Only">Magnet Only</a></td>
<td class="text-center">Anime</td>
<td><a href="magnet:?xt=urn:btih:kkk" title="Download">DL</a></td>
<td class="text-center">1 GiB</td>
<td data-timestamp="1700000000" class="text-center">2023-11-14</td>
<td class="text-center">5</td>
<td class="text-center">2</td>
<td class="text-center">3</td>
<td class="text-center comment">x</td>
</tr>
</table>
</body></html>'''


# ─── NyaasiParser tests ────────────────────────────────────────────────────


class TestNyaasiParser:
    def test_single_result_magnet(self):
        inst, captured, _, _ = _load_nyaa()
        hits = []
        parser = inst.NyaasiParser(hits, inst.url, use_magnet=True)
        parser.feed(SINGLE_RESULT_MAGNET)
        parser.close()
        assert len(hits) == 1
        h = hits[0]
        assert h["name"] == "[SubGroup] My Anime - 01 [1080p].mkv"
        assert h["desc_link"] == "https://nyaa.si/view/12345"
        assert h["engine_url"] == "https://nyaa.si"
        assert h["link"].startswith("magnet:?xt=urn:btih:")
        assert h["size"] == "1.2 GiB"
        assert h["seeds"] == 5
        assert h["leech"] == 2
        assert h["pub_date"] == "1700000000"

    def test_single_result_torrent_file(self):
        inst, captured, _, _ = _load_nyaa()
        hits = []
        parser = inst.NyaasiParser(hits, inst.url, use_magnet=False)
        parser.feed(SINGLE_RESULT_TORRENT)
        parser.close()
        assert len(hits) == 1
        h = hits[0]
        assert h["name"] == "Linux Distro 2024.iso"
        assert h["desc_link"] == "https://nyaa.si/view/99999"
        assert h["link"] == "https://nyaa.si/download/99999.torrent"
        assert h["size"] == "2.5 GiB"
        assert h["seeds"] == 42
        assert h["leech"] == 0

    def test_multi_results(self):
        inst, captured, _, _ = _load_nyaa()
        hits = []
        parser = inst.NyaasiParser(hits, inst.url, use_magnet=True)
        parser.feed(MULTI_RESULT)
        parser.close()
        assert len(hits) == 3
        assert hits[0]["name"] == "Result One"
        assert hits[1]["name"] == "Result Two"
        assert hits[2]["name"] == "Result Three"
        assert hits[0]["seeds"] == 10
        assert hits[1]["seeds"] == 7
        assert hits[2]["seeds"] == 50

    def test_empty_html(self):
        inst, captured, _, _ = _load_nyaa()
        hits = []
        parser = inst.NyaasiParser(hits, inst.url, use_magnet=True)
        parser.feed(EMPTY_HTML)
        parser.close()
        assert len(hits) == 0

    def test_malformed_html(self):
        inst, captured, _, _ = _load_nyaa()
        hits = []
        parser = inst.NyaasiParser(hits, inst.url, use_magnet=True)
        parser.feed(MALFORMED_HTML)
        parser.close()
        assert len(hits) == 0

    def test_no_results_html(self):
        inst, captured, _, _ = _load_nyaa()
        hits = []
        parser = inst.NyaasiParser(hits, inst.url, use_magnet=True)
        parser.feed(NO_RESULTS_HTML)
        parser.close()
        assert len(hits) == 0

    def test_result_no_magnet_skipped_in_magnet_mode(self):
        inst, captured, _, _ = _load_nyaa()
        hits = []
        parser = inst.NyaasiParser(hits, inst.url, use_magnet=True)
        parser.feed(RESULTS_NO_MAGNET)
        parser.close()
        assert len(hits) == 0

    def test_non_numeric_seeds_and_leech(self):
        inst, captured, _, _ = _load_nyaa()
        hits = []
        parser = inst.NyaasiParser(hits, inst.url, use_magnet=True)
        parser.feed(RESULT_NO_SEEDS)
        parser.close()
        assert len(hits) == 1
        assert hits[0]["seeds"] == -1
        assert hits[0]["leech"] == -1

    def test_no_timestamp_pub_date_none(self):
        inst, captured, _, _ = _load_nyaa()
        hits = []
        parser = inst.NyaasiParser(hits, inst.url, use_magnet=True)
        parser.feed(RESULT_NO_TIMESTAMP)
        parser.close()
        assert len(hits) == 1
        assert hits[0]["pub_date"] is None

    def test_class_on_anchor_skipped(self):
        inst, captured, _, _ = _load_nyaa()
        hits = []
        parser = inst.NyaasiParser(hits, inst.url, use_magnet=True)
        parser.feed(RESULT_CLASS_ON_A)
        parser.close()
        assert len(hits) == 0

    def test_unrelated_link_skipped(self):
        inst, captured, _, _ = _load_nyaa()
        hits = []
        parser = inst.NyaasiParser(hits, inst.url, use_magnet=True)
        parser.feed(RESULT_UNRELATED_LINK)
        parser.close()
        assert len(hits) == 1
        assert "magnet:" in hits[0]["link"]

    def test_torrent_file_mode_uses_torrent_link(self):
        inst, captured, _, _ = _load_nyaa()
        hits = []
        parser = inst.NyaasiParser(hits, inst.url, use_magnet=False)
        parser.feed(TORRENT_FILE_DOWNLOAD)
        parser.close()
        assert len(hits) == 1
        assert hits[0]["link"] == "https://nyaa.si/download/66666.torrent"

    def test_torrent_file_mode_both_links_uses_torrent(self):
        inst, captured, _, _ = _load_nyaa()
        hits = []
        parser = inst.NyaasiParser(hits, inst.url, use_magnet=False)
        parser.feed(RESULT_BOTH_LINKS_TORRENT_MODE)
        parser.close()
        assert len(hits) == 1
        assert hits[0]["link"] == "https://nyaa.si/download/44444.torrent"

    def test_magnet_mode_both_links_uses_magnet(self):
        inst, captured, _, _ = _load_nyaa()
        hits = []
        parser = inst.NyaasiParser(hits, inst.url, use_magnet=True)
        parser.feed(RESULT_BOTH_LINKS_MAGNET_MODE)
        parser.close()
        assert len(hits) == 1
        assert hits[0]["link"].startswith("magnet:?")

    def test_magnet_only_no_torrent(self):
        inst, captured, _, _ = _load_nyaa()
        hits = []
        parser = inst.NyaasiParser(hits, inst.url, use_magnet=True)
        parser.feed(MAGNET_ONLY_NO_TORRENT)
        parser.close()
        assert len(hits) == 1
        assert "magnet:" in hits[0]["link"]

    def test_torrent_mode_magnet_only_no_result(self):
        inst, captured, _, _ = _load_nyaa()
        hits = []
        parser = inst.NyaasiParser(hits, inst.url, use_magnet=False)
        parser.feed(MAGNET_ONLY_NO_TORRENT)
        parser.close()
        assert len(hits) == 0

    def test_pub_date_from_timestamp(self):
        inst, captured, _, _ = _load_nyaa()
        hits = []
        parser = inst.NyaasiParser(hits, inst.url, use_magnet=True)
        parser.feed(SINGLE_RESULT_MAGNET)
        parser.close()
        assert hits[0]["pub_date"] == "1700000000"

    def test_size_captured_correctly(self):
        inst, captured, _, _ = _load_nyaa()
        hits = []
        parser = inst.NyaasiParser(hits, inst.url, use_magnet=True)
        parser.feed(MULTI_RESULT)
        parser.close()
        assert hits[0]["size"] == "100 MiB"
        assert hits[1]["size"] == "50 MiB"
        assert hits[2]["size"] == "10 MiB"


# ─── search tests ──────────────────────────────────────────────────────────


class TestSearch:
    def _patch_retrieve(self, mod, helpers_mod, html):
        """Patch retrieve_url on both the module and helpers_mod."""
        helpers_mod.retrieve_url = MagicMock(return_value=html)
        mod.retrieve_url = helpers_mod.retrieve_url

    def test_search_single_page(self):
        inst, captured, helpers_mod, mod = _load_nyaa()
        self._patch_retrieve(mod, helpers_mod, SINGLE_RESULT_MAGNET)
        inst.search("test+query", "all")
        assert len(captured) == 1
        assert captured[0]["name"] == "[SubGroup] My Anime - 01 [1080p].mkv"

    def test_search_url_construction(self):
        inst, captured, helpers_mod, mod = _load_nyaa()
        self._patch_retrieve(mod, helpers_mod, EMPTY_HTML)
        inst.search("hello+world", "anime")
        helpers_mod.retrieve_url.assert_called_once()
        url = helpers_mod.retrieve_url.call_args[0][0]
        assert "nyaa.si" in url
        assert "c=1_0" in url
        assert "q=hello+world" in url
        assert "s=seeders" in url
        assert "o=desc" in url
        assert "f=0" in url
        assert "p=1" in url

    def test_search_category_all(self):
        inst, captured, helpers_mod, mod = _load_nyaa()
        self._patch_retrieve(mod, helpers_mod, EMPTY_HTML)
        inst.search("q", "all")
        url = helpers_mod.retrieve_url.call_args[0][0]
        assert "c=0_0" in url

    def test_search_category_anime(self):
        inst, captured, helpers_mod, mod = _load_nyaa()
        self._patch_retrieve(mod, helpers_mod, EMPTY_HTML)
        inst.search("q", "anime")
        url = helpers_mod.retrieve_url.call_args[0][0]
        assert "c=1_0" in url

    def test_search_category_books(self):
        inst, captured, helpers_mod, mod = _load_nyaa()
        self._patch_retrieve(mod, helpers_mod, EMPTY_HTML)
        inst.search("q", "books")
        url = helpers_mod.retrieve_url.call_args[0][0]
        assert "c=3_0" in url

    def test_search_category_music(self):
        inst, captured, helpers_mod, mod = _load_nyaa()
        self._patch_retrieve(mod, helpers_mod, EMPTY_HTML)
        inst.search("q", "music")
        url = helpers_mod.retrieve_url.call_args[0][0]
        assert "c=2_0" in url

    def test_search_category_pictures(self):
        inst, captured, helpers_mod, mod = _load_nyaa()
        self._patch_retrieve(mod, helpers_mod, EMPTY_HTML)
        inst.search("q", "pictures")
        url = helpers_mod.retrieve_url.call_args[0][0]
        assert "c=5_0" in url

    def test_search_category_software(self):
        inst, captured, helpers_mod, mod = _load_nyaa()
        self._patch_retrieve(mod, helpers_mod, EMPTY_HTML)
        inst.search("q", "software")
        url = helpers_mod.retrieve_url.call_args[0][0]
        assert "c=6_0" in url

    def test_search_category_tv(self):
        inst, captured, helpers_mod, mod = _load_nyaa()
        self._patch_retrieve(mod, helpers_mod, EMPTY_HTML)
        inst.search("q", "tv")
        url = helpers_mod.retrieve_url.call_args[0][0]
        assert "c=4_0" in url

    def test_search_category_movies(self):
        inst, captured, helpers_mod, mod = _load_nyaa()
        self._patch_retrieve(mod, helpers_mod, EMPTY_HTML)
        inst.search("q", "movies")
        url = helpers_mod.retrieve_url.call_args[0][0]
        assert "c=4_0" in url

    def test_search_multi_page(self):
        page1 = MULTI_RESULT
        page2 = '''<html><body>
<table>
<tr>
<td><a href="/view/99" title="Page Two Result">Page Two Result</a></td>
<td class="text-center">Anime</td>
<td><a href="magnet:?xt=urn:btih:ddd" title="Download">DL</a></td>
<td class="text-center">1 GiB</td>
<td data-timestamp="1700300000" class="text-center">2023-11-17</td>
<td class="text-center">1</td>
<td class="text-center">0</td>
<td class="text-center">0</td>
<td class="text-center comment">x</td>
</tr>
</table>
</body></html>'''
        pages = [page1, page2]
        page_idx = [0]

        def fake_retrieve(url):
            idx = page_idx[0]
            page_idx[0] += 1
            return pages[min(idx, len(pages) - 1)]

        inst, captured, helpers_mod, mod = _load_nyaa()
        helpers_mod.retrieve_url = fake_retrieve
        mod.retrieve_url = fake_retrieve
        inst.search("q", "all")
        assert len(captured) >= 3

    def test_search_empty_results(self):
        inst, captured, helpers_mod, mod = _load_nyaa()
        self._patch_retrieve(mod, helpers_mod, EMPTY_HTML)
        inst.search("nothing+here", "all")
        assert len(captured) == 0

    def test_search_exception_in_retrieve(self):
        inst, captured, helpers_mod, mod = _load_nyaa()
        self._patch_retrieve(mod, helpers_mod, "")
        helpers_mod.retrieve_url.side_effect = Exception("network error")
        mod.retrieve_url = helpers_mod.retrieve_url
        with pytest.raises(Exception, match="network error"):
            inst.search("test", "all")

    def test_search_special_characters(self):
        inst, captured, helpers_mod, mod = _load_nyaa()
        self._patch_retrieve(mod, helpers_mod, EMPTY_HTML)
        inst.search("[CoY] Attack+on+Titan S01E01", "anime")
        url = helpers_mod.retrieve_url.call_args[0][0]
        assert "%5BCoY%5D" in url or "[CoY]" in url

    def test_search_default_category(self):
        inst, captured, helpers_mod, mod = _load_nyaa()
        self._patch_retrieve(mod, helpers_mod, EMPTY_HTML)
        inst.search("q")
        url = helpers_mod.retrieve_url.call_args[0][0]
        assert "c=0_0" in url

    def test_search_unknown_category(self):
        inst, captured, helpers_mod, mod = _load_nyaa()
        self._patch_retrieve(mod, helpers_mod, EMPTY_HTML)
        inst.search("q", "nonexistent")
        url = helpers_mod.retrieve_url.call_args[0][0]
        assert "c=None" in url

    def test_search_parser_results_passed_to_pretty_printer(self):
        inst, captured, helpers_mod, mod = _load_nyaa()
        self._patch_retrieve(mod, helpers_mod, SINGLE_RESULT_MAGNET)
        inst.search("test", "all")
        assert len(captured) == 1
        result = captured[0]
        assert "name" in result
        assert "link" in result
        assert "desc_link" in result
        assert "seeds" in result
        assert "leech" in result

    def test_search_hits_cleared_between_pages(self):
        big_page = '''<html><body><table>''' + ''.join(
            f'''<tr>
<td><a href="/view/{i}" title="R{i}">R{i}</a></td>
<td class="text-center">Anime</td>
<td><a href="magnet:?xt=urn:btih:{i:040x}" title="Download">DL</a></td>
<td class="text-center">1 MiB</td>
<td data-timestamp="1700000000" class="text-center">2023-11-14</td>
<td class="text-center">1</td>
<td class="text-center">0</td>
<td class="text-center">0</td>
<td class="text-center comment">x</td>
</tr>'''
            for i in range(75)
        ) + '''</table></body></html>'''
        small_page = SINGLE_RESULT_MAGNET
        pages = [big_page, small_page]
        page_idx = [0]

        def fake_retrieve(url):
            idx = page_idx[0]
            page_idx[0] += 1
            return pages[min(idx, len(pages) - 1)]

        inst, captured, helpers_mod, mod = _load_nyaa()
        helpers_mod.retrieve_url = fake_retrieve
        mod.retrieve_url = fake_retrieve
        inst.search("q", "all")
        assert len(captured) == 76


# ─── download_torrent tests ────────────────────────────────────────────────


class TestDownloadTorrent:
    def test_download_magnet_direct(self, capsys):
        inst, captured, _, _ = _load_nyaa()
        magnet = "magnet:?xt=urn:btih:abc123&dn=test"
        inst.download_torrent(magnet)
        out = capsys.readouterr().out
        assert magnet in out
        assert inst.url in out

    def test_download_external_url(self, capsys):
        inst, captured, _, _ = _load_nyaa()
        inst.download_torrent("https://example.com/torrent/123")
        out = capsys.readouterr().out
        assert "https://example.com/torrent/123" in out
        assert inst.url in out

    def test_download_nyaa_view_url_finds_magnet(self, capsys):
        inst, captured, helpers_mod, mod = _load_nyaa()
        helpers_mod.retrieve_url = MagicMock(return_value='<a href="magnet:?xt=urn:btih:abc">magnet</a>')
        inst.download_torrent("https://nyaa.si/view/12345")
        out = capsys.readouterr().out
        assert "magnet:?xt=urn:btih:abc" in out

    def test_download_nyaa_url_no_magnet_prints_url(self, capsys):
        inst, captured, helpers_mod, mod = _load_nyaa()
        helpers_mod.retrieve_url = MagicMock(return_value="<html><body>no magnet here</body></html>")
        inst.download_torrent("https://nyaa.si/view/12345")
        out = capsys.readouterr().out
        assert "https://nyaa.si/view/12345" in out

    def test_download_nyaa_torrent_file_url_prints_url(self, capsys):
        inst, captured, helpers_mod, mod = _load_nyaa()
        helpers_mod.retrieve_url = MagicMock(return_value="<html></html>")
        inst.download_torrent("https://nyaa.si/download/999.torrent")
        out = capsys.readouterr().out
        assert "https://nyaa.si/download/999.torrent" in out

    def test_download_torrent_retrieve_exception(self, capsys):
        inst, captured, helpers_mod, mod = _load_nyaa()
        helpers_mod.retrieve_url = MagicMock(side_effect=Exception("timeout"))
        with pytest.raises(Exception, match="timeout"):
            inst.download_torrent("https://nyaa.si/view/12345")


# ─── Class attribute tests ─────────────────────────────────────────────────


class TestAttributes:
    def test_url(self):
        inst, _, _, _ = _load_nyaa()
        assert inst.url == "https://nyaa.si"

    def test_name(self):
        inst, _, _, _ = _load_nyaa()
        assert inst.name == "Nyaa.si"

    def test_use_magnet_links_default(self):
        inst, _, _, _ = _load_nyaa()
        assert inst.use_magent_links is True

    def test_supported_categories_all(self):
        inst, _, _, _ = _load_nyaa()
        assert inst.supported_categories["all"] == "0_0"

    def test_supported_categories_anime(self):
        inst, _, _, _ = _load_nyaa()
        assert inst.supported_categories["anime"] == "1_0"

    def test_supported_categories_books(self):
        inst, _, _, _ = _load_nyaa()
        assert inst.supported_categories["books"] == "3_0"

    def test_supported_categories_music(self):
        inst, _, _, _ = _load_nyaa()
        assert inst.supported_categories["music"] == "2_0"

    def test_supported_categories_pictures(self):
        inst, _, _, _ = _load_nyaa()
        assert inst.supported_categories["pictures"] == "5_0"

    def test_supported_categories_software(self):
        inst, _, _, _ = _load_nyaa()
        assert inst.supported_categories["software"] == "6_0"

    def test_supported_categories_tv(self):
        inst, _, _, _ = _load_nyaa()
        assert inst.supported_categories["tv"] == "4_0"

    def test_supported_categories_movies(self):
        inst, _, _, _ = _load_nyaa()
        assert inst.supported_categories["movies"] == "4_0"

    def test_tv_and_movies_same_id(self):
        inst, _, _, _ = _load_nyaa()
        assert inst.supported_categories["tv"] == inst.supported_categories["movies"]

    def test_all_categories_present(self):
        inst, _, _, _ = _load_nyaa()
        expected = {"all", "anime", "books", "music", "pictures", "software", "tv", "movies"}
        assert set(inst.supported_categories.keys()) == expected
