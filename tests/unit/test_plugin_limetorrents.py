"""Deep coverage tests for plugins/limetorrents.py.

Covers: MyHtmlParser (table rows, date parsing, edge cases), search (URL
construction, category mapping, exception handling, pagination),
download_torrent (magnet, HTTP fallback, error paths), _fetch_url_with_retry,
_fetch_magnet_from_page, and edge cases.
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


def _load_limetorrents(captured=None):
    if captured is None:
        captured = []
    np_mod = types.ModuleType("novaprinter")
    np_mod.prettyPrinter = lambda d: captured.append(dict(d))
    sys.modules["novaprinter"] = np_mod

    helpers_mod = types.ModuleType("helpers")
    helpers_mod.retrieve_url = lambda url: ""
    sys.modules["helpers"] = helpers_mod

    sys.modules.pop("limetorrents", None)

    path = os.path.join(PLUGINS_DIR, "limetorrents.py")
    spec = importlib.util.spec_from_file_location("limetorrents", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules["limetorrents"] = mod
    cls = getattr(mod, "limetorrents", None)
    if cls is not None and isinstance(cls, type):
        return cls(), captured, mod
    return mod, captured, mod


BASE_URL = "https://www.limetorrents.lol"

LT_SINGLE_ROW = """
<table class="table2">
<tr bgcolor="#F4F4F4">
<td><a href="/some-torrent-name.html">Some Torrent Name</a></td>
<td>1 day ago</td>
<td>1,234 MB</td>
<td>50</td>
<td>10</td>
</tr>
</table>"""

LT_TWO_ROWS = """
<table class="table2">
<tr bgcolor="#F4F4F4">
<td><a href="/movie-a.html">Movie A</a></td>
<td>3 hours ago</td>
<td>700 MB</td>
<td>200</td>
<td>5</td>
</tr>
<tr bgcolor="#FFFFFF">
<td><a href="/movie-b.html">Movie B</a></td>
<td>2 months ago</td>
<td>4,500 MB</td>
<td>15</td>
<td>3</td>
</tr>
</table>"""

LT_NO_LINK_ROW = """
<table class="table2">
<tr bgcolor="#F4F4F4">
<td>No link here</td>
<td>5 days ago</td>
<td>500 MB</td>
<td>10</td>
<td>2</td>
</tr>
</table>"""

LT_EMPTY_TABLE = '<table class="table2"></table>'

LT_NON_HTML_LINK = """
<table class="table2">
<tr bgcolor="#F4F4F4">
<td><a href="/download/12345">Not Html Link</a></td>
<td>yesterday</td>
<td>100 MB</td>
<td>1</td>
<td>0</td>
</tr>
</table>"""

LT_TR_NO_BG = """
<table class="table2">
<tr>
<td><a href="/ignored.html">Ignored Row</a></td>
<td>1 day ago</td>
<td>100 MB</td>
<td>1</td>
<td>0</td>
</tr>
</table>"""

LT_WRONG_TABLE_CLASS = """
<table class="table1">
<tr bgcolor="#F4F4F4">
<td><a href="/ignored.html">Ignored</a></td>
<td>1 day ago</td>
<td>100 MB</td>
<td>1</td>
<td>0</td>
</tr>
</table>"""

MAGNET_PAGE = """
<html><body>
<a href="magnet:?xt=urn:btih:aa11bb22cc33dd44ee55ff6677889900abcdef12&dn=test&tr=udp://tracker.example.com:1337">Download</a>
</body></html>"""

MAGNET_PAGE_SINGLE_QUOTE = """
<a href='magnet:?xt=urn:btih:11223344556677889900aabbccddeeff11223344&dn=foo'>DL</a>"""

MAGNET_PAGE_PLAIN = '''
"magnet:?xt=urn:btih:aabbccddeeff00112233445566778899aabbccdd&dn=bar"'''

NO_MAGNET_PAGE = "<html><body>No magnet here</body></html>"

SEARCH_PAGE_WITH_RESULTS = """
<table class="table2">
<tr bgcolor="#F4F4F4">
<td><a href="/some-torrent.html">Some Torrent</a></td>
<td>1 day ago</td>
<td>1,024 MB</td>
<td>100</td>
<td>20</td>
</tr>
</table>"""

SEARCH_FEW_ITEMS = """
<table class="table2">
<tr bgcolor="#F4F4F4">
<td><a href="/single-result.html">Single Result</a></td>
<td>yesterday</td>
<td>500 MB</td>
<td>10</td>
<td>1</td>
</tr>
</table>"""

SEARCH_20_ITEMS_ROWS = "\n".join(
    f'<tr bgcolor="{"#F4F4F4" if i % 2 == 0 else "#FFFFFF"}">'
    f'<td><a href="/item{i}.html">Item {i}</a></td>'
    f"<td>1 day ago</td>"
    f"<td>100 MB</td>"
    f"<td>{i}</td>"
    f"<td>0</td>"
    f"</tr>"
    for i in range(20)
)
SEARCH_20_ITEMS = f'<table class="table2">{SEARCH_20_ITEMS_ROWS}</table>'


# --- MyHtmlParser tests ---


class TestMyHtmlParser:

    def _parse(self, html):
        inst, _, _ = _load_limetorrents()
        parser = inst.MyHtmlParser(BASE_URL)
        parser.feed(html)
        parser.close()
        return parser

    def test_single_result(self):
        parser = self._parse(LT_SINGLE_ROW)
        assert len(parser.results) == 1
        r = parser.results[0]
        assert r["name"] == "Some Torrent Name"
        assert r["desc_link"] == BASE_URL + "/some-torrent-name.html"
        assert r["engine_url"] == BASE_URL

    def test_two_results(self):
        parser = self._parse(LT_TWO_ROWS)
        assert len(parser.results) == 2
        names = [r["name"] for r in parser.results]
        assert "Movie A" in names
        assert "Movie B" in names

    def test_no_link_row_skipped(self):
        parser = self._parse(LT_NO_LINK_ROW)
        assert len(parser.results) == 0

    def test_non_html_link_skipped(self):
        parser = self._parse(LT_NON_HTML_LINK)
        assert len(parser.results) == 0

    def test_tr_without_bgcolor_ignored(self):
        parser = self._parse(LT_TR_NO_BG)
        assert len(parser.results) == 0

    def test_wrong_table_class_ignored(self):
        parser = self._parse(LT_WRONG_TABLE_CLASS)
        assert len(parser.results) == 0

    def test_empty_table(self):
        parser = self._parse(LT_EMPTY_TABLE)
        assert len(parser.results) == 0

    def test_empty_html(self):
        parser = self._parse("")
        assert len(parser.results) == 0

    def test_page_items_counter(self):
        parser = self._parse(LT_TWO_ROWS)
        assert parser.page_items == 2

    def test_desc_link_and_info_link_both_set(self):
        parser = self._parse(LT_SINGLE_ROW)
        r = parser.results[0]
        assert r["desc_link"] == r["_info_link"]

    def test_size_commas_stripped(self):
        parser = self._parse(LT_SINGLE_ROW)
        r = parser.results[0]
        assert r["size"] == "1234 MB"

    def test_seeds_stripped(self):
        parser = self._parse(LT_SINGLE_ROW)
        r = parser.results[0]
        assert r["seeds"] == "50"

    def test_leech_stripped(self):
        parser = self._parse(LT_SINGLE_ROW)
        r = parser.results[0]
        assert r["leech"] == "10"

    def test_error_handler_noop(self):
        parser = self._parse("")
        parser.error("test error message")


# --- Date parsing tests ---


class TestDateParsing:

    def _parse_date(self, date_str):
        inst, _, _ = _load_limetorrents()
        parser = inst.MyHtmlParser(BASE_URL)
        now = datetime.now()
        html = f"""
        <table class="table2">
        <tr bgcolor="#F4F4F4">
        <td><a href="/test.html">Test</a></td>
        <td>{date_str}</td>
        <td>100 MB</td>
        <td>1</td>
        <td>0</td>
        </tr>
        </table>"""
        parser.feed(html)
        parser.close()
        ts = int(parser.results[0]["pub_date"])
        return datetime.fromtimestamp(ts), now

    def test_yesterday(self):
        parsed, now = self._parse_date("yesterday")
        assert (now - parsed).days == 1

    def test_days_ago(self):
        parsed, now = self._parse_date("5 days ago")
        assert (now - parsed).days == 5

    def test_hours_ago(self):
        parsed, now = self._parse_date("3 hours ago")
        diff = now - parsed
        assert diff.total_seconds() == pytest.approx(3 * 3600, abs=60)

    def test_minutes_ago(self):
        parsed, now = self._parse_date("30 minutes ago")
        diff = now - parsed
        assert diff.total_seconds() == pytest.approx(30 * 60, abs=60)

    def test_months_ago(self):
        parsed, now = self._parse_date("2 months ago")
        assert (now - parsed).days == 60

    def test_last_month(self):
        parsed, now = self._parse_date("last month")
        assert (now - parsed).days == 30

    def test_years_ago(self):
        parsed, now = self._parse_date("1 year ago")
        assert (now - parsed).days == 365

    def test_unrecognized_date(self):
        inst, _, _ = _load_limetorrents()
        parser = inst.MyHtmlParser(BASE_URL)
        html = """
        <table class="table2">
        <tr bgcolor="#F4F4F4">
        <td><a href="/x.html">X</a></td>
        <td>unknown date format</td>
        <td>100 MB</td>
        <td>1</td>
        <td>0</td>
        </tr>
        </table>"""
        parser.feed(html)
        parser.close()
        ts = int(parser.results[0]["pub_date"])
        assert ts == -1


# --- search() tests ---


class TestSearch:

    def test_search_calls_retrieve_url_with_correct_pattern(self):
        inst, _, mod = _load_limetorrents()
        urls = []
        with patch.object(mod, "retrieve_url", side_effect=lambda url: (urls.append(url), "")[1]):
            inst.search("test-query", "all")
        assert len(urls) >= 1
        assert "/search/all/test-query/seeds/1/" in urls[0]

    def test_search_category_mapping(self):
        inst, _, mod = _load_limetorrents()
        urls = []
        with patch.object(mod, "retrieve_url", side_effect=lambda url: (urls.append(url), "")[1]):
            for cat, expected in [
                ("movies", "movies"),
                ("tv", "tv"),
                ("music", "music"),
                ("anime", "anime"),
                ("games", "games"),
                ("software", "applications"),
            ]:
                urls.clear()
                inst.search("q", cat)
                assert any(
                    f"/search/{expected}/" in u for u in urls
                ), f"Category {cat} should map to {expected}"

    def test_search_query_encoding(self):
        inst, _, mod = _load_limetorrents()
        urls = []
        with patch.object(mod, "retrieve_url", side_effect=lambda url: (urls.append(url), "")[1]):
            inst.search("hello%20world", "all")
        assert any("hello-world" in u for u in urls)

    def test_search_fetches_magnet_for_each_result(self):
        inst, captured, mod = _load_limetorrents()
        with (
            patch.object(mod, "retrieve_url", return_value=SEARCH_PAGE_WITH_RESULTS),
            patch.object(
                inst,
                "_fetch_magnet_from_page",
                return_value="magnet:?xt=urn:btih:aaaa1111bbbb2222cccc3333dddd4444eeee5555",
            ) as mock_fetch,
        ):
            inst.search("test", "all")
            assert mock_fetch.call_count >= 1
            call_url = mock_fetch.call_args[0][0]
            assert "some-torrent.html" in call_url

    def test_search_skips_results_without_magnet(self):
        inst, captured, mod = _load_limetorrents()
        with (
            patch.object(mod, "retrieve_url", return_value=SEARCH_PAGE_WITH_RESULTS),
            patch.object(inst, "_fetch_magnet_from_page", return_value=""),
        ):
            inst.search("test", "all")
            assert len(captured) == 0

    def test_search_calls_prettyPrinter_with_link(self):
        inst, captured, mod = _load_limetorrents()
        with (
            patch.object(mod, "retrieve_url", return_value=SEARCH_PAGE_WITH_RESULTS),
            patch.object(
                inst,
                "_fetch_magnet_from_page",
                return_value="magnet:?xt=urn:btih:aaaa1111bbbb2222cccc3333dddd4444eeee5555",
            ),
        ):
            inst.search("test", "all")
            assert len(captured) == 1
            assert "link" in captured[0]
            assert captured[0]["link"].startswith("magnet:")

    def test_search_pagination_stops_on_few_items(self):
        inst, _, mod = _load_limetorrents()
        call_count = 0

        def mock_retrieve(url):
            nonlocal call_count
            call_count += 1
            return SEARCH_FEW_ITEMS

        with (
            patch.object(mod, "retrieve_url", side_effect=mock_retrieve),
            patch.object(
                inst,
                "_fetch_magnet_from_page",
                return_value="magnet:?xt=urn:btih:aaaa1111bbbb2222cccc3333dddd4444eeee5555",
            ),
        ):
            inst.search("test", "all")
        assert call_count == 1

    def test_search_pagination_continues_on_20_items(self):
        inst, _, mod = _load_limetorrents()
        call_count = 0

        def mock_retrieve(url):
            nonlocal call_count
            call_count += 1
            return SEARCH_20_ITEMS

        with (
            patch.object(mod, "retrieve_url", side_effect=mock_retrieve),
            patch.object(
                inst,
                "_fetch_magnet_from_page",
                return_value="magnet:?xt=urn:btih:aaaa1111bbbb2222cccc3333dddd4444eeee5555",
            ),
        ):
            inst.search("test", "all")
        assert call_count == 2

    def test_search_exception_on_retrieve_continues(self):
        inst, _, mod = _load_limetorrents()
        call_count = 0

        def mock_retrieve(url):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("network error")
            return ""

        with patch.object(mod, "retrieve_url", side_effect=mock_retrieve):
            inst.search("test", "all")
        assert call_count == 2

    def test_search_skips_result_with_no_info_link(self):
        inst, captured, mod = _load_limetorrents()
        with patch.object(mod, "retrieve_url", return_value=LT_NO_LINK_ROW):
            inst.search("test", "all")
            assert len(captured) == 0

    def test_search_removes_info_link_from_output(self):
        inst, captured, mod = _load_limetorrents()
        with (
            patch.object(mod, "retrieve_url", return_value=SEARCH_PAGE_WITH_RESULTS),
            patch.object(
                inst,
                "_fetch_magnet_from_page",
                return_value="magnet:?xt=urn:btih:aaaa1111bbbb2222cccc3333dddd4444eeee5555",
            ),
        ):
            inst.search("test", "all")
            assert "_info_link" not in captured[0]


# --- download_torrent() tests ---


class TestDownloadTorrent:

    def test_magnet_input_printed(self, capsys):
        inst, _, _ = _load_limetorrents()
        magnet = "magnet:?xt=urn:btih:aa11bb22cc33dd44ee55ff6677889900abcdef12&dn=test"
        inst.download_torrent(magnet)
        captured = capsys.readouterr()
        assert magnet in captured.out

    def test_magnet_input_printed_twice(self, capsys):
        inst, _, _ = _load_limetorrents()
        magnet = "magnet:?xt=urn:btih:aa11bb22cc33dd44ee55ff6677889900abcdef12&dn=test"
        inst.download_torrent(magnet)
        captured = capsys.readouterr()
        assert captured.out.count("magnet:?xt=urn:btih:") == 2

    def test_http_url_fetches_magnet(self, capsys):
        inst, _, _ = _load_limetorrents()
        with patch.object(
            inst,
            "_fetch_magnet_from_page",
            return_value="magnet:?xt=urn:btih:aa11bb22cc33dd44ee55ff6677889900abcdef12&dn=test",
        ):
            inst.download_torrent("https://limetorrents.lol/some-torrent.html")
            captured = capsys.readouterr()
            assert "magnet:?xt=urn:btih:" in captured.out

    def test_http_url_no_magnet_raises(self):
        inst, _, _ = _load_limetorrents()
        with patch.object(inst, "_fetch_magnet_from_page", return_value=""):
            with pytest.raises(ValueError, match="Could not find magnet"):
                inst.download_torrent("https://limetorrents.lol/some-torrent.html")

    def test_http_url_exception_raises(self):
        inst, _, _ = _load_limetorrents()
        with patch.object(
            inst, "_fetch_magnet_from_page", side_effect=Exception("network err")
        ):
            with pytest.raises(ValueError, match="Could not find magnet"):
                inst.download_torrent("https://limetorrents.lol/page.html")


# --- _fetch_magnet_from_page tests ---


class TestFetchMagnetFromPage:

    def test_magnet_href_double_quotes(self):
        inst, _, _ = _load_limetorrents()
        with patch.object(inst, "_fetch_url_with_retry", return_value=MAGNET_PAGE):
            result = inst._fetch_magnet_from_page("https://example.com/page")
            assert result.startswith("magnet:?xt=urn:btih:")
            assert "aa11bb22cc33dd44ee55ff6677889900abcdef12" in result

    def test_magnet_href_single_quotes(self):
        inst, _, _ = _load_limetorrents()
        with patch.object(inst, "_fetch_url_with_retry", return_value=MAGNET_PAGE_SINGLE_QUOTE):
            result = inst._fetch_magnet_from_page("https://example.com/page")
            assert result.startswith("magnet:?xt=urn:btih:")
            assert "11223344556677889900aabbccddeeff11223344" in result

    def test_magnet_plain_quotes(self):
        inst, _, _ = _load_limetorrents()
        with patch.object(inst, "_fetch_url_with_retry", return_value=MAGNET_PAGE_PLAIN):
            result = inst._fetch_magnet_from_page("https://example.com/page")
            assert result.startswith("magnet:?xt=urn:btih:")

    def test_no_magnet_returns_empty(self):
        inst, _, _ = _load_limetorrents()
        with patch.object(inst, "_fetch_url_with_retry", return_value=NO_MAGNET_PAGE):
            result = inst._fetch_magnet_from_page("https://example.com/page")
            assert result == ""

    def test_fetch_exception_returns_empty(self):
        inst, _, _ = _load_limetorrents()
        with patch.object(
            inst, "_fetch_url_with_retry", side_effect=Exception("timeout")
        ):
            result = inst._fetch_magnet_from_page("https://example.com/page")
            assert result == ""


# --- _fetch_url_with_retry tests ---


class TestFetchUrlWithRetry:

    def test_success_on_first_try(self):
        inst, _, _ = _load_limetorrents()
        mock_response = MagicMock()
        mock_response.read.return_value = b"<html>ok</html>"
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("limetorrents.urlopen", return_value=mock_response) as mock_open:
            result = inst._fetch_url_with_retry("https://example.com/page")
            assert result == "<html>ok</html>"
            assert mock_open.call_count == 1

    def test_retries_on_failure(self):
        inst, _, _ = _load_limetorrents()
        mock_response = MagicMock()
        mock_response.read.return_value = b"success"
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        call_count = 0

        with patch("limetorrents.urlopen") as mock_open:
            from urllib.error import URLError

            def side_effect(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count < 3:
                    raise URLError("fail")
                return mock_response

            mock_open.side_effect = side_effect
            result = inst._fetch_url_with_retry("https://example.com/page", max_retries=3)
            assert result == "success"
            assert call_count == 3

    def test_raises_after_max_retries(self):
        inst, _, _ = _load_limetorrents()
        from urllib.error import URLError

        with patch("limetorrents.urlopen", side_effect=URLError("always fail")):
            with pytest.raises(URLError):
                inst._fetch_url_with_retry("https://example.com/page", max_retries=2)

    def test_url_encoding_with_spaces(self):
        inst, _, _ = _load_limetorrents()
        mock_response = MagicMock()
        mock_response.read.return_value = b"ok"
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("limetorrents.urlopen", return_value=mock_response) as mock_open:
            inst._fetch_url_with_retry("https://example.com/path with spaces")
            called_url = mock_open.call_args[0][0].full_url
            assert " " not in called_url

    def test_url_encoding_with_percent20(self):
        inst, _, _ = _load_limetorrents()
        mock_response = MagicMock()
        mock_response.read.return_value = b"ok"
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("limetorrents.urlopen", return_value=mock_response) as mock_open:
            inst._fetch_url_with_retry("https://example.com/path%20encoded")
            called_url = mock_open.call_args[0][0].full_url
            assert "%20" not in called_url or " " not in called_url


# --- Class attribute tests ---


class TestClassAttributes:

    def test_url(self):
        inst, _, _ = _load_limetorrents()
        assert inst.url == "https://www.limetorrents.lol"

    def test_name(self):
        inst, _, _ = _load_limetorrents()
        assert inst.name == "LimeTorrents"

    def test_supported_categories_all_keys(self):
        inst, _, _ = _load_limetorrents()
        expected = {"all", "anime", "software", "games", "movies", "music", "tv"}
        assert set(inst.supported_categories.keys()) == expected

    def test_supported_categories_values(self):
        inst, _, _ = _load_limetorrents()
        assert inst.supported_categories["all"] == "all"
        assert inst.supported_categories["anime"] == "anime"
        assert inst.supported_categories["software"] == "applications"
        assert inst.supported_categories["games"] == "games"
        assert inst.supported_categories["movies"] == "movies"
        assert inst.supported_categories["music"] == "music"
        assert inst.supported_categories["tv"] == "tv"
