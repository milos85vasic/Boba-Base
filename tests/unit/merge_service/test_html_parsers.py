"""
Unit tests for HTML parsing functions in the merge service.

Tests _parse_rutracker_html, _parse_kinozal_html, and _parse_nnmclub_html
with sample HTML fragments and edge cases.
"""

import importlib.util
import os
import sys

import pytest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_SRC_PATH = os.path.join(_REPO_ROOT, "download-proxy", "src")
_MS_PATH = os.path.join(_SRC_PATH, "merge_service")

if "merge_service.search" not in sys.modules:
    _search_spec = importlib.util.spec_from_file_location(
        "merge_service.search",
        os.path.join(_MS_PATH, "search.py"),
        submodule_search_locations=[_MS_PATH],
    )
    _search_mod = importlib.util.module_from_spec(_search_spec)
    sys.modules.setdefault("merge_service", type(sys)("merge_service"))
    sys.modules["merge_service"].__path__ = [_MS_PATH]
    sys.modules["merge_service.search"] = _search_mod
    _search_spec.loader.exec_module(_search_mod)

SearchOrchestrator = sys.modules["merge_service.search"].SearchOrchestrator


@pytest.fixture
def orchestrator():
    return SearchOrchestrator()


RUTRACKER_SAMPLE_HTML = """
<tr id="trs-tr-12345" class="row1">
<td><a data-topic_id="12345" class="tLink">Интерстеллар / Interstellar</a></td>
<td data-ts_text="15728640000"></td>
<td data-ts_text="89"></td>
<td class="leechmed">15</td>
<td data-ts_text="1609459200"></td>
</tr>
"""

RUTRACKER_MULTI_HTML = """
<tr id="trs-tr-111" class="row1">
<td><a data-topic_id="111" class="tLink">Movie A 1080p</a></td>
<td data-ts_text="2147483648"></td>
<td data-ts_text="200"></td>
<td class="leechmed">30</td>
<td data-ts_text="1609459200"></td>
</tr>
<tr id="trs-tr-222" class="row2">
<td><a data-topic_id="222" class="tLink">Movie B 720p</a></td>
<td data-ts_text="1073741824"></td>
<td data-ts_text="50"></td>
<td class="leechmed">10</td>
<td data-ts_text="1609459300"></td>
</tr>
"""

KINOZAL_SAMPLE_HTML = """
<td class="nam"><a href="/details.php?id=67890" class="r0">Интерстеллар / Interstellar (2014) BDRip</a></td><td class=s'>&nbsp;</td><td class=s'>1.46 ГБ</td><td class=sl_s'>42</td><td class=sl_p'>5</td><td class=s'>01.01.2025 10:00</td>
"""

KINOZAL_MULTI_HTML = """
<td class="nam"><a href="/details.php?id=100" class="r1">Film X (2023) WEB-DL</a></td><td class=s'>&nbsp;</td><td class=s'>3.2 ГБ</td><td class=sl_s'>100</td><td class=sl_p'>8</td><td class=s'>02.02.2025</td>
<td class="nam"><a href="/details.php?id=200" class="r2">Film Y (2022) BDRip</a></td><td class=s'>&nbsp;</td><td class=s'>700 МБ</td><td class=sl_s'>25</td><td class=sl_p'>3</td><td class=s'>03.03.2025</td>
"""

NNMCLUB_SAMPLE_HTML = """
<a class="topictitle" href="viewtopic.php?t=54321"><b>Interstellar 2014 BDRip</b></a></span>
<td><a href="dl.php?id=54321">download</a></td>
<td><u>1572864000</u></td>
<td><b>30</b></td>
<td><b>4</b></td>
<td><u>1609459200</u></td>
"""

NNMCLUB_MULTI_HTML = """
<a class="topictitle" href="viewtopic.php?t=100"><b>Show A S01 1080p</b></a></span>
<td><a href="dl.php?id=100">download</a></td>
<td><u>5368709120</u></td>
<td><b>80</b></td>
<td><b>12</b></td>
<td><u>1609459200</u></td>
<a class="topictitle" href="viewtopic.php?t=200"><b>Show B S02 720p</b></a></span>
<td><a href="dl.php?id=200">download</a></td>
<td><u>2147483648</u></td>
<td><b>45</b></td>
<td><b>7</b></td>
<td><u>1609459300</u></td>
"""


class TestParseRutrackerHtml:
    def test_single_result(self, orchestrator):
        results = orchestrator._parse_rutracker_html(RUTRACKER_SAMPLE_HTML, "https://rutracker.org")
        assert len(results) == 1
        r = results[0]
        assert "Interstellar" in r.name
        assert r.seeds == 89
        assert r.leechers == 15
        assert r.tracker == "rutracker"
        assert "12345" in r.link
        assert "12345" in r.desc_link

    def test_multiple_results(self, orchestrator):
        results = orchestrator._parse_rutracker_html(RUTRACKER_MULTI_HTML, "https://rutracker.org")
        assert len(results) == 2
        assert results[0].name == "Movie A 1080p"
        assert results[0].seeds == 200
        assert results[1].name == "Movie B 720p"
        assert results[1].seeds == 50

    def test_empty_html_returns_empty(self, orchestrator):
        results = orchestrator._parse_rutracker_html("", "https://rutracker.org")
        assert results == []

    def test_malformed_html_returns_empty(self, orchestrator):
        results = orchestrator._parse_rutracker_html(
            "<html><body>no torrents here</body></html>", "https://rutracker.org"
        )
        assert results == []

    def test_link_contains_base_url(self, orchestrator):
        results = orchestrator._parse_rutracker_html(RUTRACKER_SAMPLE_HTML, "https://rutracker.org")
        assert results[0].link.startswith("https://rutracker.org/forum/dl.php")
        assert results[0].desc_link.startswith("https://rutracker.org/forum/viewtopic.php")

    def test_size_formatted(self, orchestrator):
        results = orchestrator._parse_rutracker_html(RUTRACKER_SAMPLE_HTML, "https://rutracker.org")
        size = results[0].size
        assert size != "0 B"
        assert float(size.split()[0]) > 0

    def test_negative_seeds_treated_as_zero(self, orchestrator):
        html = """
        <tr id="trs-tr-999" class="row1">
        <td><a data-topic_id="999" class="tLink">Dead Torrent</a></td>
        <td data-ts_text="1000"></td>
        <td data-ts_text="-5"></td>
        <td class="leechmed">0</td>
        <td data-ts_text="1609459200"></td>
        </tr>
        """
        results = orchestrator._parse_rutracker_html(html, "https://rutracker.org")
        assert len(results) == 1
        assert results[0].seeds == 0


class TestParseKinozalHtml:
    def test_single_result(self, orchestrator):
        results = orchestrator._parse_kinozal_html(KINOZAL_SAMPLE_HTML, "https://kinozal.tv")
        assert len(results) == 1
        r = results[0]
        assert "Interstellar" in r.name
        assert r.seeds == 42
        assert r.leechers == 5
        assert r.tracker == "kinozal"

    def test_cyrillic_size_translated(self, orchestrator):
        results = orchestrator._parse_kinozal_html(KINOZAL_SAMPLE_HTML, "https://kinozal.tv")
        size = results[0].size
        assert "G" in size or "GB" in size

    def test_multiple_results(self, orchestrator):
        results = orchestrator._parse_kinozal_html(KINOZAL_MULTI_HTML, "https://kinozal.tv")
        assert len(results) == 2
        assert "Film X" in results[0].name
        assert results[0].seeds == 100
        assert "Film Y" in results[1].name
        assert results[1].seeds == 25

    def test_empty_html_returns_empty(self, orchestrator):
        results = orchestrator._parse_kinozal_html("", "https://kinozal.tv")
        assert results == []

    def test_malformed_html_returns_empty(self, orchestrator):
        results = orchestrator._parse_kinozal_html("<html><body>nothing</body></html>", "https://kinozal.tv")
        assert results == []

    def test_link_uses_dl_subdomain(self, orchestrator):
        results = orchestrator._parse_kinozal_html(KINOZAL_SAMPLE_HTML, "https://kinozal.tv")
        assert "dl." in results[0].link
        assert "67890" in results[0].link

    def test_desc_link(self, orchestrator):
        results = orchestrator._parse_kinozal_html(KINOZAL_SAMPLE_HTML, "https://kinozal.tv")
        assert "details.php?id=67890" in results[0].desc_link
        assert results[0].desc_link.startswith("https://kinozal.tv")


class TestParseNnmclubHtml:
    def test_single_result(self, orchestrator):
        results = orchestrator._parse_nnmclub_html(NNMCLUB_SAMPLE_HTML, "https://nnmclub.to")
        assert len(results) == 1
        r = results[0]
        assert "Interstellar" in r.name
        assert r.seeds == 30
        assert r.leechers == 4
        assert r.tracker == "nnmclub"

    def test_multiple_results(self, orchestrator):
        results = orchestrator._parse_nnmclub_html(NNMCLUB_MULTI_HTML, "https://nnmclub.to")
        assert len(results) == 2
        assert "Show A" in results[0].name
        assert results[0].seeds == 80
        assert "Show B" in results[1].name
        assert results[1].seeds == 45

    def test_empty_html_returns_empty(self, orchestrator):
        results = orchestrator._parse_nnmclub_html("", "https://nnmclub.to")
        assert results == []

    def test_malformed_html_returns_empty(self, orchestrator):
        results = orchestrator._parse_nnmclub_html("<html>nope</html>", "https://nnmclub.to")
        assert results == []

    def test_link_contains_base_url(self, orchestrator):
        results = orchestrator._parse_nnmclub_html(NNMCLUB_SAMPLE_HTML, "https://nnmclub.to")
        assert results[0].link.startswith("https://nnmclub.to/forum/")
        assert results[0].desc_link.startswith("https://nnmclub.to/forum/")

    def test_size_is_raw_value(self, orchestrator):
        results = orchestrator._parse_nnmclub_html(NNMCLUB_SAMPLE_HTML, "https://nnmclub.to")
        assert results[0].size == "1572864000"


class TestParseEdgeCases:
    def test_all_parsers_handle_none_gracefully(self, orchestrator):
        for parser in [
            orchestrator._parse_rutracker_html,
            orchestrator._parse_kinozal_html,
            orchestrator._parse_nnmclub_html,
        ]:
            results = parser("", "https://example.com")
            assert isinstance(results, list)
            assert len(results) == 0

    def test_rutracker_partial_row_skipped(self, orchestrator):
        html = '<tr id="trs-tr-999" class="row1"><td>no data here</td></tr>'
        results = orchestrator._parse_rutracker_html(html, "https://rutracker.org")
        assert results == []

    def test_kinozal_incomplete_entry_skipped(self, orchestrator):
        html = '<td class="nam"><a href="/details.php?id=1">Name Only</a></td>'
        results = orchestrator._parse_kinozal_html(html, "https://kinozal.tv")
        assert results == []


IPTORRENTS_SAMPLE_HTML = """<form><table id="torrents">
<thead><tr><th>Type<th>Name<th>DL<th>Size<th>Files<th>S<th>L<th>C</tr></thead>
<tr><td class="i p72"><a href="?72"><img src="https://example.com/movies.png" alt="Movies"></a></td><td class="al"><a class=" hv" href="/t/12345">Ubuntu Server 24.04 LTS</a><div class="sub">1 day ago</div></td><td><a href="/download.php/12345/Ubuntu.Server.torrent"><i class="fa fa-download"></i></a></td><td>4.5 GB</td><td><a href="/t/12345/files">2</a></td><td>335</td><td>16</td><td>0</td></tr>
<tr><td class="i p72"><a href="?72"><img src="https://example.com/movies.png" alt="Movies"></a></td><td class="al"><a class=" hv" href="/t/67890">Ubuntu Desktop 22.04</a><div class="sub">3 days ago</div></td><td><a href="/download.php/67890/Ubuntu.Desktop.torrent"><i class="fa fa-download"></i></a></td><td>3.2 GB</td><td><a href="/t/67890/files">1</a></td><td>200</td><td>30</td><td>5</td></tr>
</table></form>
"""

IPTORRENTS_FREELEECH_HTML = """<form><table id="torrents">
<thead><tr><th>Type<th>Name<th>DL<th>Size<th>Files<th>S<th>L<th>C</tr></thead>
<tr><td class="i p72"><a href="?72"><img src="https://example.com/movies.png" alt="Movies"></a></td><td class="al"><a class=" hv" href="/t/11111">Free Movie 2024 4K</a><div class="sub">2 hours ago</div><span class="free">FreeLeech</span></td><td><a href="/download.php/11111/Free.Movie.torrent"><i class="fa fa-download"></i></a></td><td>88.9 MB</td><td>3</td><td>100</td><td>50</td><td>10</td></tr>
</table></form>
"""


class TestParseIptorrentsHtml:
    def test_single_result(self, orchestrator):
        # BOB-122 (2026-08-19): the live IPTorrents markup carries three
        # trailing numeric <td> cells in column order Snatches/Seeders/
        # Leechers. The IPTORRENTS_SAMPLE_HTML fixture has trailing cells
        # `<td>335</td><td>16</td><td>0</td>` = snatches=335, seeders=16,
        # leechers=0. Previously this test asserted seeds==335 which was
        # a pre-BOB-122 wrong-column interpretation.
        results = orchestrator._parse_iptorrents_html(IPTORRENTS_SAMPLE_HTML, "https://iptorrents.com")
        assert len(results) == 2
        r = results[0]
        assert "Ubuntu Server" in r.name
        assert r.seeds == 16
        assert r.leechers == 0  # BOB-122: last trailing <td>0</td> = leechers
        assert r.tracker == "iptorrents"
        assert r.freeleech is False

    def test_multiple_results(self, orchestrator):
        # BOB-122: seeds is the SECOND of the last three numeric <td> per
        # live-site column order (Snatches / Seeders / Leechers). Fixture
        # row 2 has trailing cells `<td>200</td><td>30</td><td>5</td>` =
        # snatches=200 / seeders=30 / leechers=5.
        results = orchestrator._parse_iptorrents_html(IPTORRENTS_SAMPLE_HTML, "https://iptorrents.com")
        assert len(results) == 2
        assert "Ubuntu Server" in results[0].name
        assert results[0].seeds == 16
        assert "Ubuntu Desktop" in results[1].name
        assert results[1].seeds == 30
        assert results[1].leechers == 5

    def test_freeleech_detected(self, orchestrator):
        results = orchestrator._parse_iptorrents_html(IPTORRENTS_FREELEECH_HTML, "https://iptorrents.com")
        assert len(results) == 1
        assert results[0].freeleech is True
        assert "Free Movie" in results[0].name

    def test_empty_html_returns_empty(self, orchestrator):
        results = orchestrator._parse_iptorrents_html("", "https://iptorrents.com")
        assert results == []

    def test_malformed_html_returns_empty(self, orchestrator):
        results = orchestrator._parse_iptorrents_html("<html><body>nothing</body></html>", "https://iptorrents.com")
        assert results == []

    def test_link_contains_base_url(self, orchestrator):
        results = orchestrator._parse_iptorrents_html(IPTORRENTS_SAMPLE_HTML, "https://iptorrents.com")
        assert results[0].link.startswith("https://iptorrents.com/download.php/")
        assert results[0].desc_link.startswith("https://iptorrents.com/t/")

    def test_size_parsed(self, orchestrator):
        results = orchestrator._parse_iptorrents_html(IPTORRENTS_SAMPLE_HTML, "https://iptorrents.com")
        assert "GB" in results[0].size or "4.5" in results[0].size

    def test_header_row_skipped(self, orchestrator):
        html = '<table id="torrents"><tr><th>Type<th>Name</tr></table>'
        results = orchestrator._parse_iptorrents_html(html, "https://iptorrents.com")
        assert results == []
