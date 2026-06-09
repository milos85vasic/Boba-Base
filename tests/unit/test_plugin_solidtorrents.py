"""Deep coverage tests for plugins/solidtorrents.py.

Covers: TorrentInfoParser (single/multi/empty/malformed results, date parsing,
seeders/leechers, size), search (URL construction, category mapping, pagination,
exception handling), request (URL building), edge cases.
"""

import importlib.util
import os
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PLUGINS_DIR = os.path.join(REPO, "plugins")


def _load_solidtorrents(captured=None, retrieve_return=""):
    """Import solidtorrents plugin with stub modules. Returns (instance, captured)."""
    if captured is None:
        captured = []
    np_mod = types.ModuleType("novaprinter")
    np_mod.prettyPrinter = lambda d: captured.append(dict(d))
    sys.modules["novaprinter"] = np_mod

    helpers_mod = types.ModuleType("helpers")
    helpers_mod.retrieve_url = lambda url: retrieve_return
    sys.modules["helpers"] = helpers_mod

    sys.modules.pop("solidtorrents", None)

    path = os.path.join(PLUGINS_DIR, "solidtorrents.py")
    spec = importlib.util.spec_from_file_location("solidtorrents", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules["solidtorrents"] = mod
    cls = getattr(mod, "solidtorrents", None)
    if cls is not None and isinstance(cls, type):
        return cls(), captured
    return mod, captured


# ---------------------------------------------------------------------------
# HTML fixtures matching the TorrentInfoParser state machine
# ---------------------------------------------------------------------------
# Column counting: the <div class="stats"> itself counts as column 0
# (column starts at -1, incremented on every <div> inside stats).
# Structure needed inside .stats:
#   col 0: the stats div itself
#   col 1: dummy div
#   col 2: size div (plain text) → parseSize
#   col 3: div with <font> → parseSeeders
#   col 4: div with <font> → parseLeechers
#   col 5: date div → parseDate

SINGLE_RESULT = '''<div class="search-result">
  <h5 class="title"><a href="/torrent/12345/my-torrent-name">My Torrent Name</a></h5>
  <div class="stats">
    <div></div>
    <div>1.5 GB</div>
    <div><font>120</font></div>
    <div><font>30</font></div>
    <div>Jun 15, 2025</div>
  </div>
  <a class="dl-magnet" href="magnet:?xt=urn:btih:abc123def">Magnet</a>
</div>'''

MULTI_RESULT = '''<div class="search-result">
  <h5 class="title"><a href="/torrent/111/alpha">Alpha Torrent</a></h5>
  <div class="stats">
    <div></div>
    <div>2.3 GB</div>
    <div><font>200</font></div>
    <div><font>10</font></div>
    <div>Jan 01, 2024</div>
  </div>
  <a class="dl-magnet" href="magnet:?xt=urn:btih:aaa111">M</a>
</div>
<div class="search-result">
  <h5 class="title"><a href="/torrent/222/beta">Beta Torrent</a></h5>
  <div class="stats">
    <div></div>
    <div>850 MB</div>
    <div><font>55</font></div>
    <div><font>44</font></div>
    <div>Dec 25, 2023</div>
  </div>
  <a class="dl-magnet" href="magnet:?xt=urn:btih:bbb222">M</a>
</div>'''

EMPTY_HTML = '<html><body>No results found.</body></html>'

MALFORMED_HTML = '<div class="search-result"><h5 class="title">no link</h5></div>'

# Result with no magnet link — should not emit via prettyPrinter
NO_MAGNET_RESULT = '''<div class="search-result">
  <h5 class="title"><a href="/torrent/999/ghost">Ghost Torrent</a></h5>
  <div class="stats">
    <div></div>
    <div>500 MB</div>
    <div><font>10</font></div>
    <div><font>5</font></div>
    <div>Mar 10, 2025</div>
  </div>
</div>'''

# Date with invalid month
BAD_DATE_RESULT = '''<div class="search-result">
  <h5 class="title"><a href="/torrent/555/x">BadDate</a></h5>
  <div class="stats">
    <div></div>
    <div>1 GB</div>
    <div><font>1</font></div>
    <div><font>2</font></div>
    <div>Foo 99, 2025</div>
  </div>
  <a class="dl-magnet" href="magnet:?xt=urn:btih:bad1">M</a>
</div>'''

# Date with extra whitespace
WHITESPACE_DATE_RESULT = '''<div class="search-result">
  <h5 class="title"><a href="/torrent/666/ws">WSD</a></h5>
  <div class="stats">
    <div></div>
    <div>1 GB</div>
    <div><font>1</font></div>
    <div><font>2</font></div>
    <div>Jul 4, 2025</div>
  </div>
  <a class="dl-magnet" href="magnet:?xt=urn:btih:ws1">M</a>
</div>'''

# 15 results to test pagination threshold (parser.totalResults < 15)
FIFTEEN_RESULTS = ''.join(f'''<div class="search-result">
  <h5 class="title"><a href="/torrent/{i}/t{i}">Torrent {i}</a></h5>
  <div class="stats">
    <div></div>
    <div>{i} GB</div>
    <div><font>{i}</font></div>
    <div><font>{i}</font></div>
    <div>Jan 01, 2025</div>
  </div>
  <a class="dl-magnet" href="magnet:?xt=urn:btih:{i:04x}">M</a>
</div>''' for i in range(1, 16))

# Exactly 14 results (should stop after page 1)
FOURTEEN_RESULTS = ''.join(f'''<div class="search-result">
  <h5 class="title"><a href="/torrent/{i}/t{i}">Torrent {i}</a></h5>
  <div class="stats">
    <div></div>
    <div>{i} GB</div>
    <div><font>{i}</font></div>
    <div><font>{i}</font></div>
    <div>Jan 01, 2025</div>
  </div>
  <a class="dl-magnet" href="magnet:?xt=urn:btih:{i:04x}">M</a>
</div>''' for i in range(1, 15))


# ---------------------------------------------------------------------------
# TorrentInfoParser tests
# ---------------------------------------------------------------------------

class TestTorrentInfoParser:

    def test_single_result(self):
        inst, captured = _load_solidtorrents()
        parser = inst.TorrentInfoParser(inst.url)
        parser.feed(SINGLE_RESULT)
        parser.close()
        assert parser.totalResults == 1
        assert len(captured) == 1
        r = captured[0]
        assert r['name'] == 'My Torrent Name'
        assert r['size'] == '1.5 GB'
        assert r['seeds'] == '120'
        assert r['leech'] == '30'
        assert 'magnet:?xt=urn:btih:abc123def' in r['link']
        assert r['desc_link'] == inst.url + '/torrent/12345/my-torrent-name'
        assert r['engine_url'] == inst.url

    def test_multi_result(self):
        inst, captured = _load_solidtorrents()
        parser = inst.TorrentInfoParser(inst.url)
        parser.feed(MULTI_RESULT)
        parser.close()
        assert parser.totalResults == 2
        assert len(captured) == 2
        assert captured[0]['name'] == 'Alpha Torrent'
        assert captured[1]['name'] == 'Beta Torrent'

    def test_empty_html(self):
        inst, captured = _load_solidtorrents()
        parser = inst.TorrentInfoParser(inst.url)
        parser.feed(EMPTY_HTML)
        parser.close()
        assert parser.totalResults == 0
        assert len(captured) == 0

    def test_malformed_no_link(self):
        inst, captured = _load_solidtorrents()
        parser = inst.TorrentInfoParser(inst.url)
        parser.feed(MALFORMED_HTML)
        parser.close()
        assert parser.totalResults == 0
        assert len(captured) == 0

    def test_no_magnet_not_emitted(self):
        inst, captured = _load_solidtorrents()
        parser = inst.TorrentInfoParser(inst.url)
        parser.feed(NO_MAGNET_RESULT)
        parser.close()
        assert parser.totalResults == 0
        assert len(captured) == 0

    def test_bad_date_sets_pub_date_minus_1(self):
        inst, captured = _load_solidtorrents()
        parser = inst.TorrentInfoParser(inst.url)
        parser.feed(BAD_DATE_RESULT)
        parser.close()
        assert parser.totalResults == 1
        assert captured[0]['pub_date'] == -1

    def test_valid_date_parsed_correctly(self):
        inst, captured = _load_solidtorrents()
        parser = inst.TorrentInfoParser(inst.url)
        parser.feed(SINGLE_RESULT)
        parser.close()
        assert captured[0]['pub_date'] > 0

    def test_whitespace_in_date(self):
        inst, captured = _load_solidtorrents()
        parser = inst.TorrentInfoParser(inst.url)
        parser.feed(WHITESPACE_DATE_RESULT)
        parser.close()
        assert parser.totalResults == 1
        assert captured[0]['pub_date'] > 0

    def test_empty_torrent_info_defaults(self):
        inst, _ = _load_solidtorrents()
        parser = inst.TorrentInfoParser(inst.url)
        info = parser.empty_torrent_info()
        assert info['link'] == ''
        assert info['name'] == ''
        assert info['size'] == '-1'
        assert info['seeds'] == '-1'
        assert info['leech'] == '-1'
        assert info['engine_url'] == inst.url
        assert info['desc_link'] == ''
        assert info['pub_date'] == -1

    def test_fifteen_results_count(self):
        inst, captured = _load_solidtorrents()
        parser = inst.TorrentInfoParser(inst.url)
        parser.feed(FIFTEEN_RESULTS)
        parser.close()
        assert parser.totalResults == 15
        assert len(captured) == 15

    def test_stats_column_counting(self):
        """Verify seeders/leechers parsed from correct columns."""
        inst, captured = _load_solidtorrents()
        parser = inst.TorrentInfoParser(inst.url)
        parser.feed(SINGLE_RESULT)
        parser.close()
        assert captured[0]['seeds'] == '120'
        assert captured[0]['leech'] == '30'

    def test_result_resets_after_magnet(self):
        """After a magnet link is found, torrentReady resets and torrent_info is cleared."""
        inst, _ = _load_solidtorrents()
        parser = inst.TorrentInfoParser(inst.url)
        parser.feed(SINGLE_RESULT)
        assert parser.torrentReady is False
        assert parser.foundResult is False

    def test_desc_link_concatenated_with_base_url(self):
        inst, captured = _load_solidtorrents()
        parser = inst.TorrentInfoParser(inst.url)
        parser.feed(SINGLE_RESULT)
        parser.close()
        assert captured[0]['desc_link'].startswith(inst.url)

    def test_date_with_comma(self):
        """Date format 'Jun 15, 2025' should be parsed."""
        inst, captured = _load_solidtorrents()
        parser = inst.TorrentInfoParser(inst.url)
        parser.feed(SINGLE_RESULT)
        parser.close()
        assert captured[0]['pub_date'] > 0


# ---------------------------------------------------------------------------
# search() tests
# ---------------------------------------------------------------------------

class TestSearch:

    def test_search_calls_retrieve_url_with_correct_url(self):
        inst, _ = _load_solidtorrents()
        with patch.object(inst, 'request', return_value=EMPTY_HTML) as mock_req:
            inst.search('ubuntu', 'all')
            mock_req.assert_called_once_with('ubuntu', 'all', 1)

    def test_search_category_mapping(self):
        inst, _ = _load_solidtorrents()
        assert inst.supported_categories['all'] == 'all'
        assert inst.supported_categories['music'] == 'Audio'
        assert inst.supported_categories['books'] == 'eBook'

    def test_search_music_category(self):
        inst, _ = _load_solidtorrents()
        with patch.object(inst, 'request', return_value=EMPTY_HTML) as mock_req:
            inst.search('beatles', 'music')
            mock_req.assert_called_once_with('beatles', 'Audio', 1)

    def test_search_books_category(self):
        inst, _ = _load_solidtorrents()
        with patch.object(inst, 'request', return_value=EMPTY_HTML) as mock_req:
            inst.search('dune', 'books')
            mock_req.assert_called_once_with('dune', 'eBook', 1)

    def test_search_stops_on_fewer_than_15_results(self):
        """With 14 results on page 1, search should NOT fetch page 2."""
        inst, _ = _load_solidtorrents()
        with patch.object(inst, 'request', return_value=FOURTEEN_RESULTS) as mock_req:
            inst.search('test', 'all')
            assert mock_req.call_count == 1

    def test_search_fetches_multiple_pages_when_needed(self):
        """With 15 results on page 1, search should fetch page 2."""
        inst, _ = _load_solidtorrents()
        with patch.object(inst, 'request', return_value=FIFTEEN_RESULTS) as mock_req:
            inst.search('popular', 'all')
            assert mock_req.call_count >= 2

    def test_search_pagination_up_to_4_pages(self):
        """Search should never request more than 4 pages."""
        inst, _ = _load_solidtorrents()
        with patch.object(inst, 'request', return_value=FIFTEEN_RESULTS) as mock_req:
            inst.search('popular', 'all')
            assert mock_req.call_count == 4

    def test_search_feeds_results_to_pretty_printer(self):
        inst, captured = _load_solidtorrents()
        with patch.object(inst, 'request', return_value=SINGLE_RESULT):
            inst.search('test', 'all')
            assert len(captured) == 1
            assert captured[0]['name'] == 'My Torrent Name'

    def test_search_invalid_category_raises_key_error(self):
        inst, _ = _load_solidtorrents()
        with pytest.raises(KeyError):
            inst.search('test', 'nonexistent')

    def test_search_empty_query(self):
        inst, captured = _load_solidtorrents()
        with patch.object(inst, 'request', return_value=EMPTY_HTML):
            inst.search('', 'all')
            assert len(captured) == 0

    def test_search_request_exception_propagates(self):
        inst, _ = _load_solidtorrents()
        with patch.object(inst, 'request', side_effect=Exception("network")):
            with pytest.raises(Exception, match="network"):
                inst.search('test', 'all')


# ---------------------------------------------------------------------------
# request() tests
# ---------------------------------------------------------------------------

class TestRequest:

    def test_request_url_construction(self):
        inst, _ = _load_solidtorrents()
        with patch("solidtorrents.retrieve_url", return_value="") as mock_ret:
            sys.modules["solidtorrents"].retrieve_url = mock_ret
            result = inst.request("hello world", "all", 1)
            called_url = mock_ret.call_args[0][0]
            assert "search?q=hello world" in called_url
            assert "category=all" in called_url
            assert "page=1" in called_url

    def test_request_page_number(self):
        inst, _ = _load_solidtorrents()
        with patch("solidtorrents.retrieve_url", return_value="") as mock_ret:
            sys.modules["solidtorrents"].retrieve_url = mock_ret
            inst.request("q", "Audio", 3)
            called_url = mock_ret.call_args[0][0]
            assert "page=3" in called_url

    def test_request_base_url(self):
        inst, _ = _load_solidtorrents()
        with patch("solidtorrents.retrieve_url", return_value="") as mock_ret:
            sys.modules["solidtorrents"].retrieve_url = mock_ret
            inst.request("x", "all")
            called_url = mock_ret.call_args[0][0]
            assert called_url.startswith(inst.url)

    def test_request_sort_parameters(self):
        inst, _ = _load_solidtorrents()
        with patch("solidtorrents.retrieve_url", return_value="") as mock_ret:
            sys.modules["solidtorrents"].retrieve_url = mock_ret
            inst.request("q", "all")
            called_url = mock_ret.call_args[0][0]
            assert "sort=seeders" in called_url
            assert "sort=desc" in called_url

    def test_request_returns_retrieve_url_result(self):
        inst, _ = _load_solidtorrents()
        with patch("solidtorrents.retrieve_url", return_value="<html>data</html>") as mock_ret:
            sys.modules["solidtorrents"].retrieve_url = mock_ret
            result = inst.request("q", "all")
            assert result == "<html>data</html>"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:

    def test_plugin_class_attributes(self):
        inst, _ = _load_solidtorrents()
        assert inst.url == 'https://solidtorrents.to'
        assert inst.name == 'Solid Torrents'

    def test_date_all_months(self):
        """Each month name should produce a valid timestamp."""
        inst, captured = _load_solidtorrents()
        months = ['jan', 'feb', 'mar', 'apr', 'may', 'jun',
                  'jul', 'aug', 'sep', 'oct', 'nov', 'dec']
        for i, m in enumerate(months):
            html = f'''<div class="search-result">
              <h5 class="title"><a href="/torrent/{i}/m{m}">Month {m}</a></h5>
              <div class="stats">
                <div></div>
                <div>1 GB</div>
                <div><font>1</font></div>
                <div><font>1</font></div>
                <div>{m.title()} 15, 2025</div>
              </div>
              <a class="dl-magnet" href="magnet:?xt=urn:btih:{m}01">M</a>
            </div>'''
            captured.clear()
            parser = inst.TorrentInfoParser(inst.url)
            parser.feed(html)
            parser.close()
            assert parser.totalResults == 1, f"Failed for month {m}"
            assert captured[0]['pub_date'] > 0, f"Bad date for month {m}"

    def test_multiple_search_result_divs(self):
        """Two search-result divs in a single HTML block."""
        inst, captured = _load_solidtorrents()
        html = SINGLE_RESULT + SINGLE_RESULT
        parser = inst.TorrentInfoParser(inst.url)
        parser.feed(html)
        parser.close()
        assert parser.totalResults == 2
        assert len(captured) == 2

    def test_search_emits_results_across_pages(self):
        """Verify results from multiple pages accumulate in captured."""
        inst, captured = _load_solidtorrents()
        page1 = SINGLE_RESULT
        page2 = NO_MAGNET_RESULT  # has search-result but no magnet
        with patch.object(inst, 'request', side_effect=[page1, page2]) as mock_req:
            inst.search('test', 'all')
            # page1 has 1 result with magnet, page2 has 0 magnets
            assert len(captured) == 1

    def test_search_default_category(self):
        """search(cat='all') should use 'all' category."""
        inst, _ = _load_solidtorrents()
        with patch.object(inst, 'request', return_value=EMPTY_HTML) as mock_req:
            inst.search('test')
            mock_req.assert_called_once_with('test', 'all', 1)

    def test_date_with_lowercase_input(self):
        """Date parser lowercases input, so 'JAN' should work."""
        inst, captured = _load_solidtorrents()
        html = '''<div class="search-result">
          <h5 class="title"><a href="/torrent/1/lc">LC Date</a></h5>
          <div class="stats">
            <div></div>
            <div>1 GB</div>
            <div><font>1</font></div>
            <div><font>1</font></div>
            <div>JAN 5, 2025</div>
          </div>
          <a class="dl-magnet" href="magnet:?xt=urn:btih:lc01">M</a>
        </div>'''
        parser = inst.TorrentInfoParser(inst.url)
        parser.feed(html)
        parser.close()
        assert parser.totalResults == 1
        assert captured[0]['pub_date'] > 0

    def test_nested_search_result_content(self):
        """Parser ignores unrelated tags inside search-result."""
        inst, captured = _load_solidtorrents()
        html = '''<div class="search-result">
          <span>irrelevant</span>
          <h5 class="title"><a href="/torrent/1/nested">Nested Name</a></h5>
          <p>some paragraph</p>
          <div class="stats">
            <div></div>
            <div>7 GB</div>
            <div><font>99</font></div>
            <div><font>11</font></div>
            <div>Feb 28, 2025</div>
          </div>
          <a class="dl-magnet" href="magnet:?xt=urn:btih:nest01">M</a>
        </div>'''
        parser = inst.TorrentInfoParser(inst.url)
        parser.feed(html)
        parser.close()
        assert parser.totalResults == 1
        assert captured[0]['name'] == 'Nested Name'
        assert captured[0]['size'] == '7 GB'
