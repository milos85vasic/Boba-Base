"""
Mock HTML fixture tests for private tracker plugins: rutracker, kinozal, nnmclub.

Each test exercises the plugin's HTML parsing logic with realistic mock
HTML that mirrors the actual tracker page structure.  These are unit tests
(isolated, no network) that validate the parsers produce correct
SearchResult objects from real-world-like HTML.

Per §11.4.132 risk-ordered validation: private tracker plugins are
historically most-problematic (credential failures, HTML changes).
Tests run early in the suite.
"""

from __future__ import annotations

import importlib.util
import os
import sys

import pytest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_SRC_PATH = os.path.join(_REPO_ROOT, "download-proxy", "src")
_MS_PATH = os.path.join(_SRC_PATH, "merge_service")

if _SRC_PATH not in sys.path:
    sys.path.insert(0, _SRC_PATH)

sys.modules.setdefault("merge_service", type(sys)("merge_service"))
sys.modules["merge_service"].__path__ = [_MS_PATH]


def _import_search_module():
    spec = importlib.util.spec_from_file_location("merge_service.search", os.path.join(_MS_PATH, "search.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["merge_service.search"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def search_mod():
    return _import_search_module()


# ==========================================================================
# RuTracker HTML fixtures
# ==========================================================================


RUTRACKER_SINGLE_ROW = """
<html>
<body>
<table class="forumline">
<tbody>
<tr id="trs-tr-100" class="hl-tr">
<td class="topictitle">
<a data-topic_id="100" href="/forum/viewtopic.php?t=100"
   class="torTopic med tLeft">Ubuntu 24.04 LTS Desktop amd64</a>
</td>
<td data-ts_text="4831838208"></td>
<td data-ts_text="125"></td>
<td class="leechmed"><a href="#">15</a></td>
<td data-ts_text="1717000000"></td>
</tr>
</tbody>
</table>
</body>
</html>
"""

RUTRACKER_MULTI_ROW = """
<html>
<body>
<table class="forumline">
<tbody>
<tr id="trs-tr-101" class="hl-tr">
<td class="topictitle">
<a data-topic_id="101" href="/forum/viewtopic.php?t=101"
   class="torTopic med tLeft">Debian 12 Bookworm Netinstall</a>
</td>
<td data-ts_text="671088640"></td>
<td data-ts_text="87"></td>
<td class="leechmed"><a href="#">5</a></td>
<td data-ts_text="1716900000"></td>
</tr>
<tr id="trs-tr-102" class="hl-tr">
<td class="topictitle">
<a data-topic_id="102" href="/forum/viewtopic.php?t=102"
   class="torTopic med tLeft">Fedora Workstation 40</a>
</td>
<td data-ts_text="2147483648"></td>
<td data-ts_text="200"></td>
<td class="leechmed"><a href="#">30</a></td>
<td data-ts_text="1716800000"></td>
</tr>
<tr id="trs-tr-103" class="hl-tr">
<td class="topictitle">
<a data-topic_id="103" href="/forum/viewtopic.php?t=103"
   class="torTopic med tLeft">Arch Linux 2024.06.01</a>
</td>
<td data-ts_text="8589934592"></td>
<td data-ts_text="55"></td>
<td class="leechmed"><a href="#">8</a></td>
<td data-ts_text="1716700000"></td>
</tr>
</tbody>
</table>
</body>
</html>
"""

RUTRACKER_HTML_ENTITIES = """
<html>
<body>
<table class="forumline">
<tbody>
<tr id="trs-tr-200" class="hl-tr">
<td class="topictitle">
<a data-topic_id="200" href="/forum/viewtopic.php?t=200"
   class="torTopic med tLeft">Movie &amp; Friends: The Sequel</a>
</td>
<td data-ts_text="7340032000"></td>
<td data-ts_text="42"></td>
<td class="leechmed"><a href="#">7</a></td>
<td data-ts_text="1716600000"></td>
</tr>
</tbody>
</table>
</body>
</html>
"""

RUTRACKER_NEGATIVE_SEEDS = """
<html>
<body>
<table class="forumline">
<tbody>
<tr id="trs-tr-300" class="hl-tr">
<td class="topictitle">
<a data-topic_id="300" href="/forum/viewtopic.php?t=300"
   class="torTopic med tLeft">Old Torrent</a>
</td>
<td data-ts_text="1073741824"></td>
<td data-ts_text="-3"></td>
<td class="leechmed"><a href="#">0</a></td>
<td data-ts_text="1600000000"></td>
</tr>
</tbody>
</table>
</body>
</html>
"""

RUTRACKER_EMPTY_TABLE = """
<html>
<body>
<table class="forumline">
<tbody>
</tbody>
</table>
</body>
</html>
"""


class TestRutrackerHtmlFixtures:
    def test_single_row(self, search_mod):
        results = search_mod.SearchOrchestrator()._parse_rutracker_html(
            RUTRACKER_SINGLE_ROW, "https://rutracker.org"
        )
        assert len(results) == 1
        r = results[0]
        assert r.name == "Ubuntu 24.04 LTS Desktop amd64"
        assert r.seeds == 125
        assert r.leechers == 15
        assert r.tracker == "rutracker"
        assert r.engine_url == "https://rutracker.org"
        assert "100" in r.link
        assert "100" in r.desc_link
        assert r.size  # non-empty

    def test_multi_row(self, search_mod):
        results = search_mod.SearchOrchestrator()._parse_rutracker_html(
            RUTRACKER_MULTI_ROW, "https://rutracker.org"
        )
        assert len(results) == 3
        assert results[0].name == "Debian 12 Bookworm Netinstall"
        assert results[0].seeds == 87
        assert results[1].name == "Fedora Workstation 40"
        assert results[1].seeds == 200
        assert results[2].name == "Arch Linux 2024.06.01"
        assert results[2].seeds == 55

    def test_html_entities(self, search_mod):
        results = search_mod.SearchOrchestrator()._parse_rutracker_html(
            RUTRACKER_HTML_ENTITIES, "https://rutracker.org"
        )
        assert len(results) == 1
        assert results[0].name == "Movie & Friends: The Sequel"

    def test_negative_seeds_clamped(self, search_mod):
        results = search_mod.SearchOrchestrator()._parse_rutracker_html(
            RUTRACKER_NEGATIVE_SEEDS, "https://rutracker.org"
        )
        assert len(results) == 1
        assert results[0].seeds == 0

    def test_empty_table(self, search_mod):
        results = search_mod.SearchOrchestrator()._parse_rutracker_html(
            RUTRACKER_EMPTY_TABLE, "https://rutracker.org"
        )
        assert results == []

    def test_completely_empty_html(self, search_mod):
        results = search_mod.SearchOrchestrator()._parse_rutracker_html("", "https://rutracker.org")
        assert results == []


# ==========================================================================
# Kinozal HTML fixtures
# ==========================================================================


KINOZAL_SINGLE_ROW = """
<table>
<tr>
<td class="nam"><a href="/details.php?id=500" class="r0">Inception 2010 BDRip 1080p</a></td>
<td class=s'>&nbsp;</td>
<td class=s'>7.5 ГБ</td>
<td class=sl_s'>340</td>
<td class=sl_p'>12</td>
<td class=s'>2024-01-15</td>
</tr>
</table>
"""

KINOZAL_MULTI_ROW = """
<table>
<tr>
<td class="nam"><a href="/details.php?id=501" class="r0">The Matrix 1999 BDRip 720p</a></td>
<td class=s'>&nbsp;</td>
<td class=s'>4.2 GB</td>
<td class=sl_s'>520</td>
<td class=sl_p'>25</td>
<td class=s'>2024-02-10</td>
</tr>
<tr>
<td class="nam"><a href="/details.php?id=502" class="r1">Interstellar 2014 WEB-DL 2160p</a></td>
<td class=s'>&nbsp;</td>
<td class=s'>15.8 ГБ</td>
<td class=sl_s'>180</td>
<td class=sl_p'>8</td>
<td class=s'>2024-03-05</td>
</tr>
</table>
"""

KINOZAL_HTML_ENTITIES = """
<table>
<tr>
<td class="nam"><a href="/details.php?id=503" class="r0">Harry Potter &amp; the Goblet of Fire</a></td>
<td class=s'>&nbsp;</td>
<td class=s'>8.1 GB</td>
<td class=sl_s'>275</td>
<td class=sl_p'>10</td>
<td class=s'>2024-01-20</td>
</tr>
</table>
"""

KINOZAL_CYRILLIC_SIZE = """
<table>
<tr>
<td class="nam"><a href="/details.php?id=504" class="r0">Linux Distro Pack</a></td>
<td class=s'>&nbsp;</td>
<td class=s'>2.3 ТБ</td>
<td class=sl_s'>15</td>
<td class=sl_p'>2</td>
<td class=s'>2024-04-01</td>
</tr>
</table>
"""

KINOZAL_EMPTY = """
<table>
</table>
"""


class TestKinozalHtmlFixtures:
    def test_single_row(self, search_mod):
        results = search_mod.SearchOrchestrator()._parse_kinozal_html(
            KINOZAL_SINGLE_ROW, "https://kinozal.tv"
        )
        assert len(results) == 1
        r = results[0]
        assert r.name == "Inception 2010 BDRip 1080p"
        assert r.seeds == 340
        assert r.leechers == 12
        assert r.tracker == "kinozal"
        assert r.engine_url == "https://kinozal.tv"
        assert "500" in r.link
        assert "500" in r.desc_link
        assert "ГБ" in r.size or "GB" in r.size

    def test_multi_row(self, search_mod):
        results = search_mod.SearchOrchestrator()._parse_kinozal_html(
            KINOZAL_MULTI_ROW, "https://kinozal.tv"
        )
        assert len(results) == 2
        assert results[0].name == "The Matrix 1999 BDRip 720p"
        assert results[0].seeds == 520
        assert results[1].name == "Interstellar 2014 WEB-DL 2160p"
        assert results[1].seeds == 180

    def test_html_entities(self, search_mod):
        results = search_mod.SearchOrchestrator()._parse_kinozal_html(
            KINOZAL_HTML_ENTITIES, "https://kinozal.tv"
        )
        assert len(results) == 1
        assert results[0].name == "Harry Potter & the Goblet of Fire"

    def test_cyrillic_size_translated(self, search_mod):
        results = search_mod.SearchOrchestrator()._parse_kinozal_html(
            KINOZAL_CYRILLIC_SIZE, "https://kinozal.tv"
        )
        assert len(results) == 1
        # Cyrillic ТБ should be translated to TB
        assert "TB" in results[0].size

    def test_dl_subdomain_in_link(self, search_mod):
        results = search_mod.SearchOrchestrator()._parse_kinozal_html(
            KINOZAL_SINGLE_ROW, "https://kinozal.tv"
        )
        assert len(results) == 1
        assert "dl.kinozal.tv" in results[0].link

    def test_empty_table(self, search_mod):
        results = search_mod.SearchOrchestrator()._parse_kinozal_html(
            KINOZAL_EMPTY, "https://kinozal.tv"
        )
        assert results == []

    def test_completely_empty_html(self, search_mod):
        results = search_mod.SearchOrchestrator()._parse_kinozal_html("", "https://kinozal.tv")
        assert results == []


# ==========================================================================
# NNMClub HTML fixtures
# ==========================================================================


NNMCLUB_SINGLE_ROW = """
<html>
<body>
<table class="topiclist">
<tr>
<td>
<a class="topictitle" href="viewtopic.php?t=600"><b>Ubuntu 24.04 Server ISO</b></a>
</td>
<td><a href="dlink.php?id=600">download</a></td>
<td><u>1073741824</u></td>
<td><b>95</b></td>
<td><b>8</b></td>
<td><u>1717000000</u></td>
</tr>
</table>
</body>
</html>
"""

NNMCLUB_MULTI_ROW = """
<html>
<body>
<table class="topiclist">
<tr>
<td>
<a class="topictitle" href="viewtopic.php?t=601"><b>Fedora Workstation 40</b></a>
</td>
<td><a href="dlink.php?id=601">download</a></td>
<td><u>2147483648</u></td>
<td><b>60</b></td>
<td><b>3</b></td>
<td><u>1716900000</u></td>
</tr>
<tr>
<td>
<a class="topictitle" href="viewtopic.php?t=602"><b>Debian 12 Netinstall</b></a>
</td>
<td><a href="dlink.php?id=602">download</a></td>
<td><u>671088640</u></td>
<td><b>140</b></td>
<td><b>12</b></td>
<td><u>1716800000</u></td>
</tr>
<tr>
<td>
<a class="topictitle" href="viewtopic.php?t=603"><b>Arch Linux 2024.06</b></a>
</td>
<td><a href="dlink.php?id=603">download</a></td>
<td><u>4294967296</u></td>
<td><b>35</b></td>
<td><b>5</b></td>
<td><u>1716700000</u></td>
</tr>
</table>
</body>
</html>
"""

NNMCLUB_HTML_ENTITIES = """
<html>
<body>
<table class="topiclist">
<tr>
<td>
<a class="topictitle" href="viewtopic.php?t=604"><b>Tom &amp; Jerry Collection</b></a>
</td>
<td><a href="dlink.php?id=604">download</a></td>
<td><u>5368709120</u></td>
<td><b>200</b></td>
<td><b>15</b></td>
<td><u>1716600000</u></td>
</tr>
</table>
</body>
</html>
"""

NNMCLUB_EMPTY = """
<html>
<body>
<table class="topiclist">
</table>
</body>
</html>
"""


class TestNnmclubHtmlFixtures:
    def test_single_row(self, search_mod):
        results = search_mod.SearchOrchestrator()._parse_nnmclub_html(
            NNMCLUB_SINGLE_ROW, "https://nnmclub.to"
        )
        assert len(results) == 1
        r = results[0]
        assert r.name == "Ubuntu 24.04 Server ISO"
        assert r.seeds == 95
        assert r.leechers == 8
        assert r.tracker == "nnmclub"
        assert r.engine_url == "https://nnmclub.to"
        assert "600" in r.link
        assert "600" in r.desc_link

    def test_multi_row(self, search_mod):
        results = search_mod.SearchOrchestrator()._parse_nnmclub_html(
            NNMCLUB_MULTI_ROW, "https://nnmclub.to"
        )
        assert len(results) == 3
        assert results[0].name == "Fedora Workstation 40"
        assert results[0].seeds == 60
        assert results[1].name == "Debian 12 Netinstall"
        assert results[1].seeds == 140
        assert results[2].name == "Arch Linux 2024.06"
        assert results[2].seeds == 35

    def test_html_entities(self, search_mod):
        results = search_mod.SearchOrchestrator()._parse_nnmclub_html(
            NNMCLUB_HTML_ENTITIES, "https://nnmclub.to"
        )
        assert len(results) == 1
        assert results[0].name == "Tom & Jerry Collection"

    def test_empty_table(self, search_mod):
        results = search_mod.SearchOrchestrator()._parse_nnmclub_html(
            NNMCLUB_EMPTY, "https://nnmclub.to"
        )
        assert results == []

    def test_completely_empty_html(self, search_mod):
        results = search_mod.SearchOrchestrator()._parse_nnmclub_html("", "https://nnmclub.to")
        assert results == []


# ==========================================================================
# IPTorrents HTML fixtures
# ==========================================================================


IPTORRENTS_SINGLE_ROW = """
<table id="torrents">
<tr><th>Name</th><th>Size</th><th>Seeders</th><th>Leechers</th></tr>
<tr>
<td><a class=" hv" href="/t/700">Ubuntu 24.04 LTS Desktop</a></td>
<td><a href="/download.php/700/ubuntu.torrent">dl</a></td>
<td>4.7 GB</td>
<td>320</td>
<td>18</td>
</tr>
</table>
"""

IPTORRENTS_MULTI_ROW = """
<table id="torrents">
<tr><th>Name</th><th>Size</th><th>Seeders</th><th>Leechers</th></tr>
<tr>
<td><a class=" hv" href="/t/701">Debian 12 Bookworm</a></td>
<td><a href="/download.php/701/debian.torrent">dl</a></td>
<td>640 MB</td>
<td>180</td>
<td>5</td>
</tr>
<tr>
<td><a class=" hv" href="/t/702">Fedora 40 Workstation</a></td>
<td><a href="/download.php/702/fedora.torrent">dl</a></td>
<td>2.1 GB</td>
<td>95</td>
<td>8</td>
</tr>
</table>
"""

IPTORRENTS_FREELEECH = """
<table id="torrents">
<tr><th>Name</th><th>Size</th><th>Seeders</th><th>Leechers</th></tr>
<tr>
<td><a class=" hv" href="/t/703">Free Torrent Download</a></td>
<td><a href="/download.php/703/free.torrent">dl</a></td>
<td>1.5 GB</td>
<td>500</td>
<td>25</td>
<td class="free">free</td>
</tr>
</table>
"""

IPTORRENTS_FREELEECH_ALREADY_TAGGED = """
<table id="torrents">
<tr><th>Name</th><th>Size</th><th>Seeders</th><th>Leechers</th></tr>
<tr>
<td><a class=" hv" href="/t/704">Already Tagged [free]</a></td>
<td><a href="/download.php/704/already.torrent">dl</a></td>
<td>800 MB</td>
<td>42</td>
<td>3</td>
<td class="free">free</td>
</tr>
</table>
"""

IPTORRENTS_NO_TABLE = """
<html><body><p>No torrents found</p></body></html>
"""

IPTORRENTS_NO_SIZE = """
<table id="torrents">
<tr><th>Name</th></tr>
<tr>
<td><a class=" hv" href="/t/705">No Size Info</a></td>
<td><a href="/download.php/705/nosize.torrent">dl</a></td>
<td>unknown</td>
<td>10</td>
<td>1</td>
</tr>
</table>
"""


class TestIptorrentsHtmlFixtures:
    def test_single_row(self, search_mod):
        results = search_mod.SearchOrchestrator()._parse_iptorrents_html(
            IPTORRENTS_SINGLE_ROW, "https://iptorrents.com"
        )
        assert len(results) == 1
        r = results[0]
        assert r.name == "Ubuntu 24.04 LTS Desktop"
        assert r.seeds == 320
        assert r.leechers == 18
        assert r.tracker == "iptorrents"
        assert r.engine_url == "https://iptorrents.com"
        assert r.freeleech is False
        assert "700" in r.link
        assert "700" in r.desc_link

    def test_multi_row(self, search_mod):
        results = search_mod.SearchOrchestrator()._parse_iptorrents_html(
            IPTORRENTS_MULTI_ROW, "https://iptorrents.com"
        )
        assert len(results) == 2
        assert results[0].name == "Debian 12 Bookworm"
        assert results[0].seeds == 180
        assert results[1].name == "Fedora 40 Workstation"
        assert results[1].seeds == 95

    def test_freeleech_detected(self, search_mod):
        results = search_mod.SearchOrchestrator()._parse_iptorrents_html(
            IPTORRENTS_FREELEECH, "https://iptorrents.com"
        )
        assert len(results) == 1
        assert results[0].freeleech is True
        assert "[free]" in results[0].name

    def test_freeleech_not_duplicated(self, search_mod):
        results = search_mod.SearchOrchestrator()._parse_iptorrents_html(
            IPTORRENTS_FREELEECH_ALREADY_TAGGED, "https://iptorrents.com"
        )
        assert len(results) == 1
        assert results[0].freeleech is True
        assert results[0].name.count("[free]") == 1

    def test_no_table(self, search_mod):
        results = search_mod.SearchOrchestrator()._parse_iptorrents_html(
            IPTORRENTS_NO_TABLE, "https://iptorrents.com"
        )
        assert results == []

    def test_no_size(self, search_mod):
        results = search_mod.SearchOrchestrator()._parse_iptorrents_html(
            IPTORRENTS_NO_SIZE, "https://iptorrents.com"
        )
        assert len(results) == 1
        assert results[0].size == "0 B"

    def test_empty_html(self, search_mod):
        results = search_mod.SearchOrchestrator()._parse_iptorrents_html(
            "", "https://iptorrents.com"
        )
        assert results == []
