"""Deep coverage tests for plugins/community/linuxtracker.py.

Covers: LinuxSearchParser (HTML parsing, field extraction, edge cases),
search (URL construction, pagination, exception handling),
download_torrent (empty method).
"""

import importlib.util
import os
import sys
import types
from unittest.mock import patch

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PLUGINS_DIR = os.path.join(REPO, "plugins")


def _load_linuxtracker(captured=None):
    if captured is None:
        captured = []
    np_mod = types.ModuleType("novaprinter")
    np_mod.prettyPrinter = lambda d: captured.append(dict(d))
    sys.modules["novaprinter"] = np_mod

    helpers_mod = types.ModuleType("helpers")
    helpers_mod.retrieve_url = lambda url: ""
    sys.modules["helpers"] = helpers_mod

    sys.modules.pop("linuxtracker", None)

    path = os.path.join(PLUGINS_DIR, "community", "linuxtracker.py")
    spec = importlib.util.spec_from_file_location("linuxtracker", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules["linuxtracker"] = mod
    cls = getattr(mod, "linuxtracker", None)
    if cls is not None and isinstance(cls, type):
        return cls(), captured
    return mod, captured


# ─── HTML fixtures ──────────────────────────────────────────────────────────
#
# Parser flow for one result block:
#   1. <a href="...torrent-details..." title="...">  → creates hit, wait_for_data=True
#   2. NAME text (first data event, strong_count=0)  → captured as name
#   3. </strong>  → strong_count=1, wait_for_data=True
#   4. Category text (strong_count=1)                 → skipped
#   5. </strong>  → strong_count=2
#   6. text (strong_count=2)                          → skipped
#   7. </strong>  → strong_count=3
#   8. SIZE text (strong_count=3)                     → captured as size
#   9. </strong>  → strong_count=4
#  10. SEEDS text (strong_count=4)                    → captured as seeds
#  11. </strong>  → strong_count=5
#  12. LEECH text (strong_count=5)                    → captured as leech
#  13. </strong>  → strong_count=6
#  14. text (strong_count=6)                          → resets to 0
#  15. <a href="magnet:?...">                         → appends result, curr=None
#
# Critical: must use </strong> (not <strong/>), and name text must be the
# first data event after the torrent-details <a> tag.

LT_ONE_RESULT = (
    '<a href="index.php?page=torrent-details&amp;id=1" title="Ubuntu 24.04 LTS">'
    "Ubuntu 24.04 LTS"
    "<strong></strong>Category: Linux Distro<strong></strong>"
    "<strong></strong>1.2 GB<strong></strong>250<strong></strong>15<strong></strong>"
    '<a href="magnet:?xt=urn:btih:abc123&amp;dn=ubuntu">Magnet</a>'
    "</a>"
)

LT_TWO_RESULTS = (
    '<a href="index.php?page=torrent-details&amp;id=1" title="Ubuntu 24.04 LTS">'
    "Ubuntu 24.04 LTS"
    "<strong></strong>Category: Linux Distro<strong></strong>"
    "<strong></strong>1.2 GB<strong></strong>250<strong></strong>15<strong></strong>"
    '<a href="magnet:?xt=urn:btih:aaa111&amp;dn=ubuntu">Magnet</a>'
    "</a>"
    '<a href="index.php?page=torrent-details&amp;id=2" title="Fedora 40">'
    "Fedora 40 Workstation"
    "<strong></strong>Category: Linux Distro<strong></strong>"
    "<strong></strong>2.1 GB<strong></strong>180<strong></strong>22<strong></strong>"
    '<a href="magnet:?xt=urn:btih:bbb222&amp;dn=fedora">Magnet</a>'
    "</a>"
)

LT_EMPTY = '<html><body><p>No results found.</p></body></html>'

LT_NO_MAGNET = (
    '<a href="index.php?page=torrent-details&amp;id=1" title="Test Entry">'
    "Test Entry"
    "<strong></strong>Category: Misc<strong></strong>"
    "<strong></strong>500 MB<strong></strong>10<strong></strong>5<strong></strong>"
    "</a>"
)

LT_SIZE_WITH_COMMAS = (
    '<a href="index.php?page=torrent-details&amp;id=1" title="Big File">'
    "Big File"
    "<strong></strong>Category: Linux Distro<strong></strong>"
    "<strong></strong>1,024.5 MB<strong></strong>30<strong></strong>8<strong></strong>"
    '<a href="magnet:?xt=urn:btih:comma123&amp;dn=bigfile">Magnet</a>'
    "</a>"
)

LT_NON_SEEDS_TEXT = (
    '<a href="index.php?page=torrent-details&amp;id=1" title="Test">'
    "Test"
    "<strong></strong>Category: Test<strong></strong>"
    "<strong></strong>100 MB<strong></strong>not-a-number<strong></strong>also-not<strong></strong>"
    '<a href="magnet:?xt=urn:btih:nonum123&amp;dn=test">Magnet</a>'
    "</a>"
)

LT_SPECIAL_CHARS = (
    '<a href="index.php?page=torrent-details&amp;id=1" title="Arch &amp; Gentoo 2024">'
    "Arch &amp; Gentoo 2024"
    "<strong></strong>Category: Distro<strong></strong>"
    "<strong></strong>800 MB<strong></strong>999<strong></strong>1<strong></strong>"
    '<a href="magnet:?xt=urn:btih:special123&amp;dn=arch+gentoo">Magnet</a>'
    "</a>"
)

LT_EXTRA_STRONG_TAGS = (
    '<a href="index.php?page=torrent-details&amp;id=1" title="Extra Tags">'
    "Extra Tags"
    "<strong></strong>Category: Test<strong></strong>"
    "<strong></strong>100 MB<strong></strong>50<strong></strong>10<strong></strong>"
    "<strong></strong>Extra<strong></strong>Data<strong></strong>"
    '<a href="magnet:?xt=urn:btih:extra123&amp;dn=extra">Magnet</a>'
    "</a>"
)


class TestLinuxSearchParser:
    def test_single_result_fields(self):
        inst, cap = _load_linuxtracker()
        from linuxtracker import linuxtracker as cls

        parser = cls.LinuxSearchParser([], "http://linuxtracker.org")
        parser.feed(LT_ONE_RESULT)
        parser.close()
        assert len(parser.results) == 1
        r = parser.results[0]
        assert r["name"] == "Ubuntu 24.04 LTS"
        assert r["size"] == "1.2 GB"
        assert r["seeds"] == 250
        assert r["leech"] == 15
        assert "magnet:?xt=urn:btih:abc123" in r["link"]
        assert "torrent-details" in r["desc_link"]

    def test_two_results(self):
        inst, cap = _load_linuxtracker()
        from linuxtracker import linuxtracker as cls

        parser = cls.LinuxSearchParser([], "http://linuxtracker.org")
        parser.feed(LT_TWO_RESULTS)
        parser.close()
        assert len(parser.results) == 2
        assert parser.results[0]["name"] == "Ubuntu 24.04 LTS"
        assert parser.results[1]["name"] == "Fedora 40 Workstation"
        assert parser.results[1]["seeds"] == 180

    def test_empty_html(self):
        inst, cap = _load_linuxtracker()
        from linuxtracker import linuxtracker as cls

        parser = cls.LinuxSearchParser([], "http://linuxtracker.org")
        parser.feed(LT_EMPTY)
        parser.close()
        assert len(parser.results) == 0

    def test_no_magnet_no_result_appended(self):
        inst, cap = _load_linuxtracker()
        from linuxtracker import linuxtracker as cls

        parser = cls.LinuxSearchParser([], "http://linuxtracker.org")
        parser.feed(LT_NO_MAGNET)
        parser.close()
        assert len(parser.results) == 0

    def test_commas_stripped_from_size(self):
        inst, cap = _load_linuxtracker()
        from linuxtracker import linuxtracker as cls

        parser = cls.LinuxSearchParser([], "http://linuxtracker.org")
        parser.feed(LT_SIZE_WITH_COMMAS)
        parser.close()
        assert len(parser.results) == 1
        assert parser.results[0]["size"] == "1024.5 MB"

    def test_non_numeric_seeds_not_stored(self):
        inst, cap = _load_linuxtracker()
        from linuxtracker import linuxtracker as cls

        parser = cls.LinuxSearchParser([], "http://linuxtracker.org")
        parser.feed(LT_NON_SEEDS_TEXT)
        parser.close()
        assert len(parser.results) == 1
        r = parser.results[0]
        assert "seeds" not in r
        assert "leech" not in r

    def test_special_characters_preserved(self):
        inst, cap = _load_linuxtracker()
        from linuxtracker import linuxtracker as cls

        parser = cls.LinuxSearchParser([], "http://linuxtracker.org")
        parser.feed(LT_SPECIAL_CHARS)
        parser.close()
        assert len(parser.results) == 1
        assert "&" in parser.results[0]["name"]

    def test_extra_strong_tags_after_sixth_resets_and_still_captures_result(self):
        inst, cap = _load_linuxtracker()
        from linuxtracker import linuxtracker as cls

        parser = cls.LinuxSearchParser([], "http://linuxtracker.org")
        parser.feed(LT_EXTRA_STRONG_TAGS)
        parser.close()
        assert len(parser.results) == 1
        assert parser.results[0]["name"] == "Extra Tags"

    def test_engine_url_set_on_result(self):
        inst, cap = _load_linuxtracker()
        from linuxtracker import linuxtracker as cls

        parser = cls.LinuxSearchParser([], "http://linuxtracker.org")
        parser.feed(LT_ONE_RESULT)
        parser.close()
        assert parser.results[0]["engine_url"] == "http://linuxtracker.org"

    def test_desc_link_contains_engine_url_prefix(self):
        inst, cap = _load_linuxtracker()
        from linuxtracker import linuxtracker as cls

        parser = cls.LinuxSearchParser([], "http://linuxtracker.org")
        parser.feed(LT_ONE_RESULT)
        parser.close()
        assert parser.results[0]["desc_link"].startswith("http://linuxtracker.org/")

    def test_peers_link_sets_wait_for_data(self):
        inst, cap = _load_linuxtracker()
        from linuxtracker import linuxtracker as cls

        lt_with_peers = (
            '<a href="index.php?page=torrent-details&amp;id=1" title="Test">'
            "Test"
            "<strong></strong>"
            '<a href="peers.php?id=1">Peers</a>'
            "Category: Test<strong></strong>"
            "<strong></strong>100 MB<strong></strong>10<strong></strong>5<strong></strong>"
            '<a href="magnet:?xt=urn:btih:peers123&amp;dn=test">Magnet</a>'
            "</a>"
        )
        parser = cls.LinuxSearchParser([], "http://linuxtracker.org")
        parser.feed(lt_with_peers)
        parser.close()
        assert len(parser.results) == 1
        assert parser.results[0]["name"] == "Test"
        assert parser.results[0]["size"] == "100 MB"

    def test_multiline_html(self):
        inst, cap = _load_linuxtracker()
        from linuxtracker import linuxtracker as cls

        multiline = """<html><body>
<a href="index.php?page=torrent-details&amp;id=42" title="Debian 12">
Debian 12
<strong></strong>Category: Linux Distro
<strong></strong>
<strong></strong>3.5 GB
<strong></strong>400
<strong></strong>50
<strong></strong>
<a href="magnet:?xt=urn:btih:deca1234&amp;dn=debian12">Magnet</a>
</a>
</body></html>"""
        parser = cls.LinuxSearchParser([], "http://linuxtracker.org")
        parser.feed(multiline)
        parser.close()
        assert len(parser.results) == 1
        r = parser.results[0]
        assert r["name"] == "Debian 12"
        assert r["size"] == "3.5 GB"
        assert r["seeds"] == 400
        assert r["leech"] == 50


class TestSearch:
    def test_url_construction(self):
        inst, cap = _load_linuxtracker()
        with patch("linuxtracker.retrieve_url", return_value=LT_EMPTY) as mock:
            inst.search("ubuntu+linux", "all")
            called_url = mock.call_args[0][0]
            assert "search=ubuntu+linux" in called_url
            assert "page=torrents" in called_url
            assert "active=1" in called_url

    def test_search_emits_results_via_pretty_printer(self):
        inst, cap = _load_linuxtracker()
        with patch("linuxtracker.retrieve_url", return_value=LT_ONE_RESULT):
            inst.search("ubuntu", "all")
            assert len(cap) == 1
            assert cap[0]["name"] == "Ubuntu 24.04 LTS"

    def test_search_multiple_results(self):
        inst, cap = _load_linuxtracker()
        with patch("linuxtracker.retrieve_url", return_value=LT_TWO_RESULTS):
            inst.search("linux", "all")
            assert len(cap) == 2
            assert cap[0]["name"] == "Ubuntu 24.04 LTS"
            assert cap[1]["name"] == "Fedora 40 Workstation"

    def test_search_empty_results(self):
        inst, cap = _load_linuxtracker()
        with patch("linuxtracker.retrieve_url", return_value=LT_EMPTY):
            inst.search("nothing", "all")
            assert len(cap) == 0

    def test_search_category_all(self):
        inst, cap = _load_linuxtracker()
        with patch("linuxtracker.retrieve_url", return_value=LT_EMPTY) as mock:
            inst.search("test", "all")
            url = mock.call_args[0][0]
            assert "search=test" in url

    def test_search_category_software(self):
        inst, cap = _load_linuxtracker()
        with patch("linuxtracker.retrieve_url", return_value=LT_EMPTY) as mock:
            inst.search("ubuntu", "software")
            url = mock.call_args[0][0]
            assert "search=ubuntu" in url

    def test_search_exception_propagates(self):
        inst, cap = _load_linuxtracker()
        with patch("linuxtracker.retrieve_url", side_effect=Exception("network error")):
            with pytest.raises(Exception, match="network error"):
                inst.search("ubuntu", "all")

    def test_search_pagination_fetches_multiple_pages(self):
        inst, cap = _load_linuxtracker()

        def make_page(n_results, page_id):
            parts = []
            for i in range(n_results):
                idx = page_id * 100 + i
                parts.append(
                    f'<a href="index.php?page=torrent-details&amp;id={idx}" title="R{idx}">'
                    f"R{idx}"
                    "<strong></strong>Category: Test<strong></strong>"
                    f"<strong></strong>100 MB<strong></strong>{10 + i}<strong></strong>{5 + i}<strong></strong>"
                    f'<a href="magnet:?xt=urn:btih:{idx:032x}&amp;dn=r{idx}">Magnet</a>'
                    "</a>"
                )
            return "<html><body>" + "".join(parts) + "</body></html>"

        call_count = 0

        def side_effect(url):
            nonlocal call_count
            call_count += 1
            if "pages=1" in url:
                return make_page(16, 1)
            return make_page(2, 2)

        with patch("linuxtracker.retrieve_url", side_effect=side_effect):
            inst.search("linux", "all")
            assert call_count == 2
            assert len(cap) == 18

    def test_search_pagination_stops_when_fewer_than_15(self):
        inst, cap = _load_linuxtracker()
        with patch("linuxtracker.retrieve_url", return_value=LT_ONE_RESULT) as mock:
            inst.search("test", "all")
            assert mock.call_count == 1

    def test_search_page_param_increments(self):
        inst, cap = _load_linuxtracker()
        urls = []

        def side_effect(url):
            urls.append(url)
            if len(urls) == 1:
                return LT_EMPTY
            return LT_EMPTY

        with patch("linuxtracker.retrieve_url", side_effect=side_effect):
            inst.search("test", "all")
            assert "pages=1" in urls[0]

    def test_search_parser_closed_after_search(self):
        inst, cap = _load_linuxtracker()
        with patch("linuxtracker.retrieve_url", return_value=LT_ONE_RESULT):
            inst.search("test", "all")

    def test_search_called_with_correct_base_url(self):
        inst, cap = _load_linuxtracker()
        with patch("linuxtracker.retrieve_url", return_value=LT_EMPTY) as mock:
            inst.search("query", "all")
            url = mock.call_args[0][0]
            assert url.startswith(inst.url + "/")


class TestDownloadTorrent:
    def test_download_torrent_does_not_crash(self):
        inst, _ = _load_linuxtracker()
        inst.download_torrent("http://linuxtracker.org/index.php?page=torrent-details&id=1")

    def test_download_torrent_accepts_any_string(self):
        inst, _ = _load_linuxtracker()
        inst.download_torrent("")
        inst.download_torrent("not-a-url")
        inst.download_torrent("magnet:?xt=urn:btih:dummy")


class TestPluginMetadata:
    def test_url_attribute(self):
        inst, _ = _load_linuxtracker()
        assert inst.url == "http://linuxtracker.org"

    def test_name_attribute(self):
        inst, _ = _load_linuxtracker()
        assert inst.name == "Linux Tracker"

    def test_supported_categories(self):
        inst, _ = _load_linuxtracker()
        assert inst.supported_categories == {"all": 0, "software": 0}

    def test_supported_categories_keys(self):
        inst, _ = _load_linuxtracker()
        assert set(inst.supported_categories.keys()) == {"all", "software"}
