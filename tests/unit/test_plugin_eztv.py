"""Deep coverage tests for plugins/eztv.py.

Covers: MyHtmlParser (HTML parsing, single/multi results, empty/malformed HTML),
search (URL construction for all categories, exception handling),
do_query (TypeError fallback, URLError), _parse_size, category mapping,
edge cases (missing fields, special characters, relative dates).
"""

import importlib.util
import os
import sys
import types
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PLUGINS_DIR = os.path.join(REPO, "plugins")


def _load_eztv(captured=None):
    """Import eztv plugin with stub modules. Returns (instance, captured)."""
    if captured is None:
        captured = []
    np_mod = types.ModuleType("novaprinter")
    np_mod.prettyPrinter = lambda d: captured.append(dict(d))
    sys.modules["novaprinter"] = np_mod

    helpers_mod = types.ModuleType("helpers")
    helpers_mod.retrieve_url = lambda url, **kwargs: ""
    sys.modules["helpers"] = helpers_mod

    sys.modules.pop("eztv", None)

    path = os.path.join(PLUGINS_DIR, "eztv.py")
    spec = importlib.util.spec_from_file_location("eztv", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules["eztv"] = mod
    cls = getattr(mod, "eztv", None)
    if cls is not None and isinstance(cls, type):
        return cls(), captured
    return mod, captured


# ─── HTML fixtures ─────────────────────────────────────────────────────
# The parser triggers on <tr class="forum_header_border" name="hover">
# and emits on </tr>.
# Then collects: <a class="magnet" href="...">, <a class="epinfo" title="..." href="...">,
# size text (ending KB/MB/GB), numeric seed text, and relative-date text.

EZTV_ROW = '''<tr class="forum_header_border" name="hover">
<td><a class="epinfo" href="/ep/12345" title="Show Name S01E01 (1080p)">Show Name S01E01 (1080p)</a></td>
<td><a class="magnet" href="magnet:?xt=urn:btih:abc123">Magnet</a></td>
<td>1.5 GB</td>
<td>42</td>
<td>3h 15m</td>
</tr>'''

EZTV_ROW_KB = '''<tr class="forum_header_border" name="hover">
<td><a class="epinfo" href="/ep/99999" title="Small File">Small File</a></td>
<td><a class="magnet" href="magnet:?xt=urn:btih:xyz789">Magnet</a></td>
<td>450 KB</td>
<td>10</td>
<td>5d 2h</td>
</tr>'''

EZTV_ROW_MB = '''<tr class="forum_header_border" name="hover">
<td><a class="epinfo" href="/ep/55555" title="Medium File">Medium File</a></td>
<td><a class="magnet" href="magnet:?xt=urn:btih:def456">Magnet</a></td>
<td>250 MB</td>
<td>5</td>
<td>2 weeks</td>
</tr>'''

EZTV_ROW_MONTHS = '''<tr class="forum_header_border" name="hover">
<td><a class="epinfo" href="/ep/11111" title="Old Show">Old Show</a></td>
<td><a class="magnet" href="magnet:?xt=urn:btih:old111">Magnet</a></td>
<td>3.2 GB</td>
<td>0</td>
<td>6 mo</td>
</tr>'''

EZTV_ROW_YEARS = '''<tr class="forum_header_border" name="hover">
<td><a class="epinfo" href="/ep/22222" title="Ancient Show">Ancient Show</a></td>
<td><a class="magnet" href="magnet:?xt=urn:btih:anc222">Magnet</a></td>
<td>700 MB</td>
<td>1</td>
<td>1 year</td>
</tr>'''

EZTV_ROW_NO_MAGNET = '''<tr class="forum_header_border" name="hover">
<td><a class="epinfo" href="/ep/33333" title="No Magnet">No Magnet</a></td>
<td>1.0 GB</td>
<td>3</td>
<td>1h 0m</td>
</tr>'''

EZTV_ROW_NO_SIZE = '''<tr class="forum_header_border" name="hover">
<td><a class="epinfo" href="/ep/44444" title="No Size">No Size</a></td>
<td><a class="magnet" href="magnet:?xt=urn:btih:nosz">Magnet</a></td>
<td>99</td>
<td>1h 0m</td>
</tr>'''

EZTV_ROW_NO_SEEDS = '''<tr class="forum_header_border" name="hover">
<td><a class="epinfo" href="/ep/66666" title="No Seeds">No Seeds</a></td>
<td><a class="magnet" href="magnet:?xt=urn:btih:noseed">Magnet</a></td>
<td>2.0 GB</td>
<td>1h 0m</td>
</tr>'''

EZTV_ROW_NO_DATE = '''<tr class="forum_header_border" name="hover">
<td><a class="epinfo" href="/ep/77777" title="No Date">No Date</a></td>
<td><a class="magnet" href="magnet:?xt=urn:btih:nodate">Magnet</a></td>
<td>1.0 GB</td>
<td>5</td>
</tr>'''

EZTV_ROW_SPECIAL_CHARS = '''<tr class="forum_header_border" name="hover">
<td><a class="epinfo" href="/ep/88888" title="Show &amp; Name: S01E01 [1080p] (v2)">Show &amp; Name: S01E01 [1080p] (v2)</a></td>
<td><a class="magnet" href="magnet:?xt=urn:btih:special123">Magnet</a></td>
<td>4.5 GB</td>
<td>7</td>
<td>12h 30m</td>
</tr>'''

EZTV_ROW_WEEKS_PLURAL = '''<tr class="forum_header_border" name="hover">
<td><a class="epinfo" href="/ep/99999" title="Plural Weeks">Plural Weeks</a></td>
<td><a class="magnet" href="magnet:?xt=urn:btih:wkplural">Magnet</a></td>
<td>1.0 GB</td>
<td>2</td>
<td>3 weeks</td>
</tr>'''

EZTV_ROW_WEEKS_SINGULAR = '''<tr class="forum_header_border" name="hover">
<td><a class="epinfo" href="/ep/10000" title="Singular Week">Singular Week</a></td>
<td><a class="magnet" href="magnet:?xt=urn:btih:wksing">Magnet</a></td>
<td>1.0 GB</td>
<td>2</td>
<td>1 week</td>
</tr>'''

EZTV_ROW_YEARS_PLURAL = '''<tr class="forum_header_border" name="hover">
<td><a class="epinfo" href="/ep/11111" title="Plural Years">Plural Years</a></td>
<td><a class="magnet" href="magnet:?xt=urn:btih:yrspl">Magnet</a></td>
<td>1.0 GB</td>
<td>2</td>
<td>3 years</td>
</tr>'''

EZTV_ROW_SIZE_COMMA = '''<tr class="forum_header_border" name="hover">
<td><a class="epinfo" href="/ep/12121" title="Comma Size">Comma Size</a></td>
<td><a class="magnet" href="magnet:?xt=urn:btih:comma1">Magnet</a></td>
<td>1,234 MB</td>
<td>8</td>
<td>2d 3h</td>
</tr>'''

EZTV_ROW_ZERO_SEEDS = '''<tr class="forum_header_border" name="hover">
<td><a class="epinfo" href="/ep/13131" title="Zero Seeds">Zero Seeds</a></td>
<td><a class="magnet" href="magnet:?xt=urn:btih:zero1">Magnet</a></td>
<td>1.0 GB</td>
<td>0</td>
<td>1h 0m</td>
</tr>'''

EZTV_ROW_TITLE_SPLIT = '''<tr class="forum_header_border" name="hover">
<td><a class="epinfo" href="/ep/14141" title="Show Title (1080p) Extra Info">Show Title (1080p) Extra Info</a></td>
<td><a class="magnet" href="magnet:?xt=urn:btih:split1">Magnet</a></td>
<td>2.0 GB</td>
<td>15</td>
<td>1h 0m</td>
</tr>'''

EZTV_MULTI_ROWS = EZTV_ROW + '\n' + EZTV_ROW_KB + '\n' + EZTV_ROW_MB

EZTV_FULL_PAGE = '''<html><body>
<table>
<tr><td>Header</td></tr>
''' + EZTV_MULTI_ROWS + '''
</table>
</body></html>'''


# ─── Parser tests ──────────────────────────────────────────────────────

class TestMyHtmlParser:

    def _parse(self, html, url='https://eztvx.to/'):
        plugin, captured = _load_eztv()
        parser = plugin.MyHtmlParser(url)
        parser.feed(html)
        parser.close()
        return captured

    def test_single_row_gv_size(self):
        results = self._parse(EZTV_ROW)
        assert len(results) == 1
        r = results[0]
        assert r['name'] == 'Show Name S01E01'
        assert r['link'] == 'magnet:?xt=urn:btih:abc123'
        assert r['size'] == '1.5 GB'
        assert r['seeds'] == 42
        assert r['engine_url'] == 'https://eztvx.to/'
        assert r['desc_link'] == 'https://eztvx.to//ep/12345'

    def test_single_row_kb_size(self):
        results = self._parse(EZTV_ROW_KB)
        assert len(results) == 1
        r = results[0]
        assert r['name'] == 'Small File'
        assert r['size'] == '450 KB'

    def test_single_row_mb_size(self):
        results = self._parse(EZTV_ROW_MB)
        assert len(results) == 1
        r = results[0]
        assert r['size'] == '250 MB'

    def test_date_hours_minutes(self):
        results = self._parse(EZTV_ROW)
        assert len(results) == 1
        r = results[0]
        assert isinstance(r['pub_date'], int)
        now = datetime.now()
        expected = now - timedelta(hours=3, minutes=15)
        diff = abs(datetime.fromtimestamp(r['pub_date']) - expected)
        assert diff < timedelta(seconds=2)

    def test_date_days_hours(self):
        results = self._parse(EZTV_ROW_KB)
        assert len(results) == 1
        r = results[0]
        now = datetime.now()
        expected = now - timedelta(days=5, hours=2)
        diff = abs(datetime.fromtimestamp(r['pub_date']) - expected)
        assert diff < timedelta(seconds=2)

    def test_date_weeks_singular(self):
        results = self._parse(EZTV_ROW_WEEKS_SINGULAR)
        assert len(results) == 1
        r = results[0]
        now = datetime.now()
        expected = now - timedelta(weeks=1)
        diff = abs(datetime.fromtimestamp(r['pub_date']) - expected)
        assert diff < timedelta(seconds=2)

    def test_date_weeks_plural(self):
        results = self._parse(EZTV_ROW_WEEKS_PLURAL)
        assert len(results) == 1
        r = results[0]
        now = datetime.now()
        expected = now - timedelta(weeks=3)
        diff = abs(datetime.fromtimestamp(r['pub_date']) - expected)
        assert diff < timedelta(seconds=2)

    def test_date_months(self):
        results = self._parse(EZTV_ROW_MONTHS)
        assert len(results) == 1
        r = results[0]
        now = datetime.now()
        expected = now - timedelta(days=6 * 30)
        diff = abs(datetime.fromtimestamp(r['pub_date']) - expected)
        assert diff < timedelta(seconds=2)

    def test_date_years_singular(self):
        results = self._parse(EZTV_ROW_YEARS)
        assert len(results) == 1
        r = results[0]
        now = datetime.now()
        expected = now - timedelta(days=365)
        diff = abs(datetime.fromtimestamp(r['pub_date']) - expected)
        assert diff < timedelta(seconds=2)

    def test_date_years_plural(self):
        results = self._parse(EZTV_ROW_YEARS_PLURAL)
        assert len(results) == 1
        r = results[0]
        now = datetime.now()
        expected = now - timedelta(days=3 * 365)
        diff = abs(datetime.fromtimestamp(r['pub_date']) - expected)
        assert diff < timedelta(seconds=2)

    def test_no_magnet_defaults(self):
        results = self._parse(EZTV_ROW_NO_MAGNET)
        assert len(results) == 1
        r = results[0]
        assert r.get('link') is None
        assert r['size'] == '1.0 GB'
        assert r['seeds'] == 3

    def test_no_size_defaults(self):
        results = self._parse(EZTV_ROW_NO_SIZE)
        assert len(results) == 1
        r = results[0]
        assert r['size'] == -1

    def test_no_seeds_defaults(self):
        results = self._parse(EZTV_ROW_NO_SEEDS)
        assert len(results) == 1
        r = results[0]
        assert r['seeds'] == -1

    def test_no_date_defaults(self):
        results = self._parse(EZTV_ROW_NO_DATE)
        assert len(results) == 1
        r = results[0]
        assert r['pub_date'] == -1

    def test_empty_html(self):
        results = self._parse('<html><body></body></html>')
        assert results == []

    def test_no_table_rows(self):
        results = self._parse('<table><tr><td>just text</td></tr></table>')
        assert results == []

    def test_special_characters_in_title(self):
        results = self._parse(EZTV_ROW_SPECIAL_CHARS)
        assert len(results) == 1
        r = results[0]
        assert r['name'] == 'Show & Name: S01E01 [1080p]'

    def test_comma_in_size_stripped(self):
        results = self._parse(EZTV_ROW_SIZE_COMMA)
        assert len(results) == 1
        r = results[0]
        assert r['size'] == '1234 MB'

    def test_zero_seeds(self):
        results = self._parse(EZTV_ROW_ZERO_SEEDS)
        assert len(results) == 1
        r = results[0]
        assert r['seeds'] == 0

    def test_title_split_at_paren(self):
        results = self._parse(EZTV_ROW_TITLE_SPLIT)
        assert len(results) == 1
        r = results[0]
        assert r['name'] == 'Show Title'

    def test_multiple_rows(self):
        results = self._parse(EZTV_MULTI_ROWS)
        assert len(results) == 3
        assert results[0]['name'] == 'Show Name S01E01'
        assert results[1]['name'] == 'Small File'
        assert results[2]['name'] == 'Medium File'

    def test_default_seeds_and_leech(self):
        results = self._parse(EZTV_ROW)
        assert results[0]['seeds'] == 42
        assert results[0]['leech'] == -1

    def test_custom_url(self):
        results = self._parse(EZTV_ROW, url='https://custom.example.com/')
        assert len(results) == 1
        assert results[0]['engine_url'] == 'https://custom.example.com/'
        assert results[0]['desc_link'] == 'https://custom.example.com//ep/12345'

    def test_non_row_a_tags_ignored(self):
        html = '<a href="/other">Not a row</a>'
        results = self._parse(html)
        assert results == []

    def test_mixed_content_before_row(self):
        html = '<p>Some intro text</p>' + EZTV_ROW
        results = self._parse(html)
        assert len(results) == 1

    def test_date_minutes_only_not_matched(self):
        """30m alone doesn't match any pattern — stays -1."""
        html = '''<tr class="forum_header_border" name="hover">
<td><a class="epinfo" href="/ep/99999" title="Minutes Only">Minutes Only</a></td>
<td><a class="magnet" href="magnet:?xt=urn:btih:min1">Magnet</a></td>
<td>1.0 GB</td>
<td>2</td>
<td>30m</td>
</tr>'''
        results = self._parse(html)
        assert len(results) == 1
        assert results[0]['pub_date'] == -1


# ─── do_query tests ────────────────────────────────────────────────────

class TestDoQuery:

    def _make_plugin(self, captured=None):
        if captured is None:
            captured = []
        plugin, captured = _load_eztv(captured)
        return plugin, captured

    def test_do_query_normal(self):
        plugin, _ = self._make_plugin()
        with patch("eztv.retrieve_url", return_value="<html>results</html>") as mock_ru:
            result = plugin.do_query("breaking bad")
            # self.url is 'https://eztvx.to/' so URL has double slash
            mock_ru.assert_called_once_with(
                "https://eztvx.to//search/breaking bad",
                request_data=b"layout=def_wlinks",
            )
            assert result == "<html>results</html>"

    def test_do_query_encoded_space(self):
        plugin, _ = self._make_plugin()
        with patch("eztv.retrieve_url", return_value="") as mock_ru:
            plugin.do_query("the%20matrix")
            mock_ru.assert_called_once_with(
                "https://eztvx.to//search/the-matrix",
                request_data=b"layout=def_wlinks",
            )

    def test_do_query_typeerror_fallback(self):
        plugin, _ = self._make_plugin()
        with patch("eztv.retrieve_url", side_effect=TypeError("no data arg")):
            mock_resp = MagicMock()
            mock_resp.read.return_value = b"<html>fallback</html>"
            with patch("eztv.urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
                result = plugin.do_query("test query")
                assert result == "<html>fallback</html>"
                mock_urlopen.assert_called_once()
                # §11.4.98/§11.4.69 regression guard: the fallback urlopen MUST
                # carry a bounded timeout so a wedged tracker can't hang the
                # plugin worker thread. Fails if `timeout=30` is dropped.
                assert mock_urlopen.call_args.kwargs.get("timeout") == 30

    def test_do_query_typeerror_urlopen_fallback_user_agent(self):
        plugin, _ = self._make_plugin()
        with patch("eztv.retrieve_url", side_effect=TypeError("old api")):
            mock_resp = MagicMock()
            mock_resp.read.return_value = b"ok"
            with patch("eztv.urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
                plugin.do_query("x")
                req = mock_urlopen.call_args[0][0]
                assert req.get_header("User-agent") == "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0"

    def test_do_query_typeerror_generic_exception(self):
        """Generic exceptions from urlopen propagate (only URLError is caught)."""
        plugin, _ = self._make_plugin()
        with patch("eztv.retrieve_url", side_effect=TypeError("old api")):
            with patch("eztv.urllib.request.urlopen", side_effect=Exception("simulated network error")):
                with pytest.raises(Exception, match="simulated network error"):
                    plugin.do_query("test")

    def test_do_query_typeerror_urllib_urlerror(self, capsys):
        import urllib.error
        plugin, _ = self._make_plugin()
        with patch("eztv.retrieve_url", side_effect=TypeError("old api")):
            with patch("eztv.urllib.request.urlopen", side_effect=urllib.error.URLError("connection refused")):
                result = plugin.do_query("test")
                assert result == ""
                captured = capsys.readouterr()
                assert "Connection error" in captured.err

    def test_do_query_empty_result(self):
        plugin, _ = self._make_plugin()
        with patch("eztv.retrieve_url", return_value=""):
            result = plugin.do_query("nothing here")
            assert result == ""

    def test_do_query_html_with_special_chars(self):
        plugin, _ = self._make_plugin()
        with patch("eztv.retrieve_url", return_value="<html>caf&eacute;</html>"):
            result = plugin.do_query("cafe")
            assert "caf&eacute;" in result


# ─── search tests ──────────────────────────────────────────────────────

class TestSearch:

    def _make_plugin(self, captured=None):
        if captured is None:
            captured = []
        plugin, captured = _load_eztv(captured)
        return plugin, captured

    def test_search_all_category(self):
        plugin, captured = self._make_plugin()
        with patch.object(plugin, "do_query", return_value=EZTV_ROW) as mock_dq:
            plugin.search("game of thrones", cat="all")
            mock_dq.assert_called_once_with("game of thrones")
            assert len(captured) == 1

    def test_search_tv_category(self):
        plugin, captured = self._make_plugin()
        with patch.object(plugin, "do_query", return_value=EZTV_ROW) as mock_dq:
            plugin.search("breaking bad", cat="tv")
            mock_dq.assert_called_once_with("breaking bad")
            assert len(captured) == 1

    def test_search_empty_html(self):
        plugin, captured = self._make_plugin()
        with patch.object(plugin, "do_query", return_value=""):
            plugin.search("nothing")
            assert captured == []

    def test_search_multiple_results(self):
        plugin, captured = self._make_plugin()
        with patch.object(plugin, "do_query", return_value=EZTV_MULTI_ROWS):
            plugin.search("multi")
            assert len(captured) == 3

    def test_search_no_results_html(self):
        plugin, captured = self._make_plugin()
        with patch.object(plugin, "do_query", return_value="<html><body>No results found</body></html>"):
            plugin.search("zzzzzzzzzzz")
            assert captured == []

    def test_search_passes_query_to_do_query(self):
        plugin, captured = self._make_plugin()
        with patch.object(plugin, "do_query", return_value="") as mock_dq:
            plugin.search("the%20office")
            mock_dq.assert_called_once_with("the%20office")

    def test_search_results_contain_engine_url(self):
        plugin, captured = self._make_plugin()
        with patch.object(plugin, "do_query", return_value=EZTV_ROW):
            plugin.search("test")
            assert captured[0]['engine_url'] == 'https://eztvx.to/'


# ─── Category mapping tests ───────────────────────────────────────────

class TestCategoryMapping:

    def test_supported_categories(self):
        plugin, _ = _load_eztv()
        assert plugin.supported_categories == {'all': 'all', 'tv': 'tv'}

    def test_class_name(self):
        plugin, _ = _load_eztv()
        assert plugin.name == 'EZTV'

    def test_class_url(self):
        plugin, _ = _load_eztv()
        assert plugin.url == 'https://eztvx.to/'


# ─── Edge case / integration tests ─────────────────────────────────────

class TestEdgeCases:

    def _parse(self, html, url='https://eztvx.to/'):
        plugin, captured = _load_eztv()
        parser = plugin.MyHtmlParser(url)
        parser.feed(html)
        parser.close()
        return captured

    def test_full_page_parse(self):
        results = self._parse(EZTV_FULL_PAGE)
        assert len(results) == 3

    def test_parser_state_resets_between_rows(self):
        html = EZTV_ROW + '\n' + EZTV_ROW_NO_MAGNET
        results = self._parse(html)
        assert len(results) == 2
        assert results[0].get('link') is not None
        assert results[1].get('link') is None

    def test_parser_preserves_leech_default(self):
        results = self._parse(EZTV_ROW)
        assert results[0]['leech'] == -1

    def test_size_with_commas_multiple(self):
        html = '''<tr class="forum_header_border" name="hover">
<td><a class="epinfo" href="/ep/1" title="Big">Big</a></td>
<td><a class="magnet" href="magnet:?xt=urn:btih:big1">Magnet</a></td>
<td>1,234,567 KB</td>
<td>10</td>
<td>1h 0m</td>
</tr>'''
        results = self._parse(html)
        assert results[0]['size'] == '1234567 KB'

    def test_multiple_size_units_in_page(self):
        html = EZTV_ROW + '\n' + EZTV_ROW_KB + '\n' + EZTV_ROW_MB
        results = self._parse(html)
        sizes = [r['size'] for r in results]
        assert '1.5 GB' in sizes
        assert '450 KB' in sizes
        assert '250 MB' in sizes

    def test_epinfo_href_concatenated(self):
        results = self._parse(EZTV_ROW)
        assert results[0]['desc_link'].endswith('/ep/12345')

    def test_magnet_href_preserved_exactly(self):
        results = self._parse(EZTV_ROW)
        assert results[0]['link'] == 'magnet:?xt=urn:btih:abc123'

    def test_non_numeric_data_in_row_ignored(self):
        html = '''<tr class="forum_header_border" name="hover">
<td><a class="epinfo" href="/ep/1" title="Show">Show</a></td>
<td><a class="magnet" href="magnet:?xt=urn:btih:test">Magnet</a></td>
<td>1.0 GB</td>
<td>5</td>
<td>N/A</td>
</tr>'''
        results = self._parse(html)
        assert len(results) == 1
        assert results[0]['pub_date'] == -1
        assert results[0]['seeds'] == 5

    def test_empty_epinfo_title(self):
        html = '''<tr class="forum_header_border" name="hover">
<td><a class="epinfo" href="/ep/1" title="">Empty Title</a></td>
<td><a class="magnet" href="magnet:?xt=urn:btih:empty">Magnet</a></td>
<td>1.0 GB</td>
<td>5</td>
<td>1h 0m</td>
</tr>'''
        results = self._parse(html)
        assert len(results) == 1
        assert results[0]['name'] == ''

    def test_title_with_space_before_paren(self):
        html = '''<tr class="forum_header_border" name="hover">
<td><a class="epinfo" href="/ep/1" title="Show Name (720p)">Show Name (720p)</a></td>
<td><a class="magnet" href="magnet:?xt=urn:btih:tst1">Magnet</a></td>
<td>800 MB</td>
<td>3</td>
<td>1h 0m</td>
</tr>'''
        results = self._parse(html)
        assert results[0]['name'] == 'Show Name'
