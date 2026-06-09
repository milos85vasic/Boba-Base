"""Deep coverage tests for plugins/rutracker.py.

Covers: HTML parsing (re_threads / re_torrent_data), search (URL construction,
category mapping, pagination, exception handling), download_torrent (valid
torrent, invalid data, empty data, HTML instead of torrent, URLError),
_build_magnet_link, _fetch_magnet_from_topic, _open_url (gzip, HTTP errors),
_check_mirrors, _get_env, _get_mirrors_from_env, Config, edge cases
(special characters, Cyrillic text, missing fields, no results).
"""

import gzip
import importlib.util
import os
import sys
import types
from http.cookiejar import Cookie
from io import BytesIO
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PLUGINS_DIR = os.path.join(REPO, "plugins")

# ─── HTML fixtures (matching rutracker.py regex patterns exactly) ─────────
#
# re_threads:  r'<tr id="trs-tr-\d+.*?</tr>'  (re.S)
# re_torrent_data (re.S):
#   a data-topic_id="ID".*?>TITLE<   <-- title MUST be on same line as >
#   data-ts_text="SIZE"
#   data-ts_text="SEEDS"
#   leechmed..>LEECH<
#   data-ts_text="PUB_DATE"
#
# KEY CONSTRAINT: the title text must appear AFTER the closing > of the
# <a> tag that contains data-topic_id, on the same line.  Otherwise
# re_torrent_data's non-greedy .*?> captures the > inside </a> and the
# title match fails.

SINGLE_ROW = (
    '<tr id="trs-tr-12345">'
    '<td><a data-topic_id="12345">The Beatles - Abbey Road</a></td>'
    '<td data-ts_text="314572800"></td>'
    '<td data-ts_text="25"></td>'
    '<td class="leechmed"><b>10</b></td>'
    '<td data-ts_text="1609459200"></td>'
    "</tr>"
)

MULTI_ROWS = (
    '<tr id="trs-tr-111">'
    '<td><a data-topic_id="111">Album One</a></td>'
    '<td data-ts_text="104857600"></td>'
    '<td data-ts_text="50"></td>'
    '<td class="leechmed"><b>5</b></td>'
    '<td data-ts_text="1609459200"></td>'
    "</tr>"
    '<tr id="trs-tr-222">'
    '<td><a data-topic_id="222">Album Two</a></td>'
    '<td data-ts_text="209715200"></td>'
    '<td data-ts_text="30"></td>'
    '<td class="leechmed"><b>8</b></td>'
    '<td data-ts_text="1612137600"></td>'
    "</tr>"
)

# Cyrillic + HTML entities
CYRILLIC_ROW = (
    '<tr id="trs-tr-999">'
    '<td><a data-topic_id="999">Музыка &amp; Звуки</a></td>'
    '<td data-ts_text="52428800"></td>'
    '<td data-ts_text="15"></td>'
    '<td class="leechmed"><b>3</b></td>'
    '<td data-ts_text="1640995200"></td>'
    "</tr>"
)

# Special characters in title
SPECIAL_ROW = (
    '<tr id="trs-tr-555">'
    '<td><a data-topic_id="555">C++ &amp; Python [2024] (HD)</a></td>'
    '<td data-ts_text="1048576"></td>'
    '<td data-ts_text="100"></td>'
    '<td class="leechmed"><b>20</b></td>'
    '<td data-ts_text="1704067200"></td>'
    "</tr>"
)

# Zero seeds / leech
ZERO_ROW = (
    '<tr id="trs-tr-777">'
    '<td><a data-topic_id="777">Dead Torrent</a></td>'
    '<td data-ts_text="1048576"></td>'
    '<td data-ts_text="0"></td>'
    '<td class="leechmed"><b>0</b></td>'
    '<td data-ts_text="1672531200"></td>'
    "</tr>"
)

# Negative seeds (some trackers report -1 for unknown)
NEGATIVE_ROW = (
    '<tr id="trs-tr-888">'
    '<td><a data-topic_id="888">Negative Seeds</a></td>'
    '<td data-ts_text="1048576"></td>'
    '<td data-ts_text="-1"></td>'
    '<td class="leechmed"><b>0</b></td>'
    '<td data-ts_text="1672531200"></td>'
    "</tr>"
)

# Malformed: missing data-topic_id
MALFORMED_NO_TOPIC_ID = (
    '<tr id="trs-tr-100">'
    "<td><a>NoTopicId</a></td>"
    '<td data-ts_text="1048576"></td>'
    '<td data-ts_text="10"></td>'
    '<td class="leechmed"><b>5</b></td>'
    '<td data-ts_text="1672531200"></td>'
    "</tr>"
)

# Malformed: missing size attribute
MALFORMED_NO_SIZE = (
    '<tr id="trs-tr-200">'
    '<td><a data-topic_id="200">NoSize</a></td>'
    '<td data-ts_text="10"></td>'
    '<td class="leechmed"><b>5</b></td>'
    '<td data-ts_text="1672531200"></td>'
    "</tr>"
)

# Malformed: missing leech class
MALFORMED_NO_LEECH = (
    '<tr id="trs-tr-300">'
    '<td><a data-topic_id="300">NoLeech</a></td>'
    '<td data-ts_text="1048576"></td>'
    '<td data-ts_text="10"></td>'
    '<td data-ts_text="1672531200"></td>'
    "</tr>"
)

# Full search page with pagination links
SEARCH_PAGE_WITH_RESULTS = (
    "<html><body>"
    '<table id="tor-tbl">'
    + SINGLE_ROW
    + """</table>
<a href="tracker.php?nm=test&amp;start=50">next</a>
<a href="tracker.php?nm=test&amp;start=100">next2</a>
</body></html>"""
)

# Search page with no results
SEARCH_PAGE_EMPTY = "<html><body><p>No results</p></body></html>"

# Topic page with magnet link
TOPIC_PAGE_MAGNET = (
    '<html><body><a href="magnet:?xt=urn:btih:aaaabbbbccccddddeeeeffffaaaabbbbccccdddd">Download</a></body></html>'
)

# Topic page without magnet link
TOPIC_PAGE_NO_MAGNET = "<html><body><p>No magnet here</p></body></html>"


# ─── Module loader ──────────────────────────────────────────────────────────


def _load_rutracker(captured=None):
    """Import rutracker plugin with stubs and mocked login.

    Returns (instance, captured_results_list).
    The instance has _open_url and __login mocked so no real HTTP happens.
    """
    if captured is None:
        captured = []

    # Stub novaprinter
    np_mod = types.ModuleType("novaprinter")
    np_mod.prettyPrinter = lambda d: captured.append(dict(d))
    sys.modules["novaprinter"] = np_mod

    # Stub env_loader so import doesn't fail
    env_mod = types.ModuleType("env_loader")
    env_mod.load_env_files = lambda *a, **kw: None
    sys.modules["env_loader"] = env_mod

    # Clean previous import
    sys.modules.pop("rutracker", None)

    path = os.path.join(PLUGINS_DIR, "rutracker.py")
    spec = importlib.util.spec_from_file_location("rutracker", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["rutracker"] = mod
    spec.loader.exec_module(mod)

    # Get the class (module-level alias: rutracker = RuTracker)
    cls = getattr(mod, "rutracker", None)
    if cls is None or not isinstance(cls, type):
        cls = getattr(mod, "RuTracker", None)
    if cls is None:
        raise ImportError("Could not find RuTracker class in rutracker.py")

    # Mock __login (name-mangled to _RuTracker__login) so __init__ succeeds
    # without real HTTP or cookie checks. Also mock _open_url for safety.
    with patch.object(cls, "_RuTracker__login", return_value=None), patch.object(cls, "_open_url", return_value=b""):
        instance = cls()

    # Add a fake bb_session cookie so any login-check in future calls passes
    cookie = Cookie(
        version=0,
        name="bb_session",
        value="fake_session_token",
        port=None,
        port_specified=False,
        domain=".rutracker.org",
        domain_specified=True,
        domain_initial_dot=True,
        path="/",
        path_specified=True,
        secure=False,
        expires=9999999999,
        discard=False,
        comment=None,
        comment_url=None,
        rest={},
        rfc2109=False,
    )
    instance.cj.set_cookie(cookie)

    return instance, captured


# ─── Test Classes ───────────────────────────────────────────────────────────


class TestConfig:
    def test_default_mirrors(self):
        """Config.mirrors has the three default rutracker mirrors."""
        from rutracker import Config

        c = Config()
        assert "https://rutracker.org" in c.mirrors
        assert "https://rutracker.net" in c.mirrors
        assert "https://rutracker.nl" in c.mirrors

    def test_env_mirrors_override(self):
        """_get_mirrors_from_env parses comma-separated env var."""
        from rutracker import _get_mirrors_from_env

        with patch.dict(os.environ, {"RUTRACKER_MIRRORS": "https://m1.example.com, https://m2.example.com"}):
            mirrors = _get_mirrors_from_env()
            assert mirrors == ["https://m1.example.com", "https://m2.example.com"]

    def test_get_env_with_default(self):
        """_get_env returns env var value or default."""
        from rutracker import _get_env

        assert _get_env("NONEXISTENT_VAR_XYZ_999", "fallback") == "fallback"
        with patch.dict(os.environ, {"TEST_RUTRACKER_VAR": "hello"}):
            assert _get_env("TEST_RUTRACKER_VAR") == "hello"

    def test_get_mirrors_from_env_empty(self):
        """_get_mirrors_from_env returns None when env var is empty."""
        from rutracker import _get_mirrors_from_env

        with patch.dict(os.environ, {"RUTRACKER_MIRRORS": ""}):
            assert _get_mirrors_from_env() is None

    def test_get_mirrors_from_env_whitespace(self):
        """Whitespace-only mirrors are filtered out."""
        from rutracker import _get_mirrors_from_env

        with patch.dict(os.environ, {"RUTRACKER_MIRRORS": " , , , "}):
            assert _get_mirrors_from_env() == []


class TestClassAttributes:
    def test_name(self):
        inst, _ = _load_rutracker()
        assert inst.name == "RuTracker"

    def test_encoding(self):
        inst, _ = _load_rutracker()
        assert inst.encoding == "cp1251"

    def test_supported_categories_complete(self):
        inst, _ = _load_rutracker()
        expected = {"all", "movies", "tv", "music", "games", "anime", "software", "books"}
        assert set(inst.supported_categories.keys()) == expected

    def test_url_properties(self):
        inst, _ = _load_rutracker()
        assert inst.forum_url == inst.url + "/forum/"
        assert inst.login_url == inst.forum_url + "login.php"

    def test_search_url(self):
        inst, _ = _load_rutracker()
        url = inst.search_url("nm=test")
        assert url == inst.forum_url + "tracker.php?nm=test"

    def test_download_url(self):
        inst, _ = _load_rutracker()
        url = inst.download_url("t=123")
        assert url == inst.forum_url + "dl.php?t=123"

    def test_topic_url(self):
        inst, _ = _load_rutracker()
        url = inst.topic_url("t=456")
        assert url == inst.forum_url + "viewtopic.php?t=456"

    def test_rutracker_trackers_list(self):
        import rutracker

        assert len(rutracker.RUTRACKER_TRACKERS) >= 10
        assert all("/ann" in t for t in rutracker.RUTRACKER_TRACKERS)


class TestRegexPatterns:
    def test_re_threads_matches_valid_row(self):
        inst, _ = _load_rutracker()
        assert inst.re_threads.search(SINGLE_ROW) is not None

    def test_re_threads_no_match_on_plain_html(self):
        inst, _ = _load_rutracker()
        assert inst.re_threads.search("<p>hello</p>") is None

    def test_re_torrent_data_extracts_all_fields(self):
        inst, _ = _load_rutracker()
        m = inst.re_torrent_data.search(SINGLE_ROW)
        assert m is not None
        assert m.group("id") == "12345"
        assert m.group("title") == "The Beatles - Abbey Road"
        assert m.group("size") == "314572800"
        assert m.group("seeds") == "25"
        assert m.group("leech") == "10"
        assert m.group("pub_date") == "1609459200"

    def test_re_torrent_data_no_match_on_malformed(self):
        inst, _ = _load_rutracker()
        assert inst.re_torrent_data.search(MALFORMED_NO_TOPIC_ID) is None

    def test_re_magnet_extracts_hash(self):
        inst, _ = _load_rutracker()
        m = inst.re_magnet.search(TOPIC_PAGE_MAGNET)
        assert m is not None
        assert m.group(1) == "aaaabbbbccccddddeeeeffffaaaabbbbccccdddd"

    def test_re_magnet_no_match(self):
        inst, _ = _load_rutracker()
        assert inst.re_magnet.search(TOPIC_PAGE_NO_MAGNET) is None


class TestParseSearchResults:
    """Test __execute_search HTML parsing via instance._open_url override."""

    def test_single_result(self):
        inst, cap = _load_rutracker()
        inst.results = {}
        with patch.object(inst, "_open_url", return_value=SINGLE_ROW.encode(inst.encoding)):
            inst._RuTracker__execute_search("http://fake/url")
        assert len(cap) == 1
        assert cap[0]["id"] == "12345"
        assert cap[0]["name"] == "The Beatles - Abbey Road"
        assert cap[0]["size"] == "314572800"
        assert cap[0]["seeds"] == "25"
        assert cap[0]["leech"] == "10"
        assert cap[0]["pub_date"] == "1609459200"

    def test_multi_results(self):
        inst, cap = _load_rutracker()
        inst.results = {}
        with patch.object(inst, "_open_url", return_value=MULTI_ROWS.encode(inst.encoding)):
            inst._RuTracker__execute_search("http://fake/url")
        assert len(cap) == 2
        assert cap[0]["id"] == "111"
        assert cap[0]["name"] == "Album One"
        assert cap[1]["id"] == "222"
        assert cap[1]["name"] == "Album Two"

    def test_empty_html_no_results(self):
        inst, cap = _load_rutracker()
        inst.results = {}
        with patch.object(inst, "_open_url", return_value=SEARCH_PAGE_EMPTY.encode(inst.encoding)):
            inst._RuTracker__execute_search("http://fake/url")
        assert len(cap) == 0

    def test_malformed_thread_skipped(self):
        inst, cap = _load_rutracker()
        inst.results = {}
        html = MALFORMED_NO_TOPIC_ID + MALFORMED_NO_SIZE + MALFORMED_NO_LEECH
        with patch.object(inst, "_open_url", return_value=html.encode(inst.encoding)):
            inst._RuTracker__execute_search("http://fake/url")
        assert len(cap) == 0

    def test_result_dict_keys(self):
        inst, cap = _load_rutracker()
        inst.results = {}
        with patch.object(inst, "_open_url", return_value=SINGLE_ROW.encode(inst.encoding)):
            inst._RuTracker__execute_search("http://fake/url")
        expected_keys = {"id", "link", "name", "size", "seeds", "leech", "engine_url", "desc_link", "pub_date"}
        assert set(cap[0].keys()) == expected_keys

    def test_result_engine_url(self):
        inst, cap = _load_rutracker()
        inst.results = {}
        with patch.object(inst, "_open_url", return_value=SINGLE_ROW.encode(inst.encoding)):
            inst._RuTracker__execute_search("http://fake/url")
        import rutracker

        assert cap[0]["engine_url"] == rutracker.DEFAULT_ENGINE_URL

    def test_result_desc_link_format(self):
        inst, cap = _load_rutracker()
        inst.results = {}
        with patch.object(inst, "_open_url", return_value=SINGLE_ROW.encode(inst.encoding)):
            inst._RuTracker__execute_search("http://fake/url")
        assert "viewtopic.php?t=12345" in cap[0]["desc_link"]

    def test_fetch_magnet_failure_falls_back_to_dl(self):
        inst, cap = _load_rutracker()
        inst.results = {}
        with patch.object(inst, "_open_url", return_value=SINGLE_ROW.encode(inst.encoding)):
            inst._RuTracker__execute_search("http://fake/url")
        # _open_url returns SINGLE_ROW for all URLs, so topic fetch returns
        # html without a magnet hash → fallback to dl.php URL
        assert "dl.php?t=12345" in cap[0]["link"]
        assert not cap[0]["link"].startswith("magnet:")

    def test_fetch_magnet_success_builds_magnet(self):
        inst, cap = _load_rutracker()
        inst.results = {}

        def fake_open(url, post_params=None, log_errors=True):
            if "viewtopic" in url:
                return TOPIC_PAGE_MAGNET.encode(inst.encoding)
            return SINGLE_ROW.encode(inst.encoding)

        with patch.object(inst, "_open_url", side_effect=fake_open):
            inst._RuTracker__execute_search("http://fake/url")
        assert cap[0]["link"].startswith("magnet:?xt=urn:btih:")
        assert "aaaabbbbccccddddeeeeffffaaaabbbbccccdddd" in cap[0]["link"]

    def test_duplicate_ids_deduplicated_in_dict(self):
        """Same topic_id appearing twice: second overwrites first in self.results."""
        inst, cap = _load_rutracker()
        inst.results = {}
        double = SINGLE_ROW + SINGLE_ROW
        with patch.object(inst, "_open_url", return_value=double.encode(inst.encoding)):
            inst._RuTracker__execute_search("http://fake/url")
        # Both are emitted via prettyPrinter, but results dict keeps one
        assert len(cap) == 2
        assert len(inst.results) == 1


class TestPagination:
    def test_first_page_returns_other_pages(self):
        inst, _ = _load_rutracker()
        inst.results = {}
        with patch.object(inst, "_open_url", return_value=SEARCH_PAGE_WITH_RESULTS.encode(inst.encoding)):
            pages = inst._RuTracker__execute_search("http://fake/url", is_first=True)
        assert len(pages) == 2
        assert "start=50" in pages[0]
        assert "start=100" in pages[1]

    def test_non_first_page_returns_empty(self):
        inst, _ = _load_rutracker()
        inst.results = {}
        with patch.object(inst, "_open_url", return_value=SEARCH_PAGE_WITH_RESULTS.encode(inst.encoding)):
            pages = inst._RuTracker__execute_search("http://fake/url", is_first=False)
        assert pages == []


class TestSearchURLConstruction:
    def test_search_all_category(self):
        inst, _ = _load_rutracker()
        with patch.object(inst, "_open_url", return_value=SEARCH_PAGE_EMPTY.encode(inst.encoding)) as mock_open:
            inst.search("test query", "all")
        called_url = mock_open.call_args_list[0][0][0]
        assert "tracker.php?" in called_url
        assert "nm=test+query" in called_url
        assert "f=" not in called_url

    def test_search_movies_category(self):
        inst, _ = _load_rutracker()
        with patch.object(inst, "_open_url", return_value=SEARCH_PAGE_EMPTY.encode(inst.encoding)) as mock_open:
            inst.search("test", "movies")
        called_url = mock_open.call_args_list[0][0][0]
        assert "f=7" in called_url
        assert "nm=test" in called_url

    def test_search_tv_category(self):
        inst, _ = _load_rutracker()
        with patch.object(inst, "_open_url", return_value=SEARCH_PAGE_EMPTY.encode(inst.encoding)) as mock_open:
            inst.search("show", "tv")
        called_url = mock_open.call_args_list[0][0][0]
        assert "f=9" in called_url

    def test_search_music_category(self):
        inst, _ = _load_rutracker()
        with patch.object(inst, "_open_url", return_value=SEARCH_PAGE_EMPTY.encode(inst.encoding)) as mock_open:
            inst.search("album", "music")
        called_url = mock_open.call_args_list[0][0][0]
        assert "f=2" in called_url

    def test_search_games_category(self):
        inst, _ = _load_rutracker()
        with patch.object(inst, "_open_url", return_value=SEARCH_PAGE_EMPTY.encode(inst.encoding)) as mock_open:
            inst.search("game", "games")
        called_url = mock_open.call_args_list[0][0][0]
        assert "f=8" in called_url

    def test_search_anime_category(self):
        inst, _ = _load_rutracker()
        with patch.object(inst, "_open_url", return_value=SEARCH_PAGE_EMPTY.encode(inst.encoding)) as mock_open:
            inst.search("naruto", "anime")
        called_url = mock_open.call_args_list[0][0][0]
        assert "f=33" in called_url

    def test_search_software_category(self):
        inst, _ = _load_rutracker()
        with patch.object(inst, "_open_url", return_value=SEARCH_PAGE_EMPTY.encode(inst.encoding)) as mock_open:
            inst.search("photoshop", "software")
        called_url = mock_open.call_args_list[0][0][0]
        assert "f=35" in called_url

    def test_search_books_category(self):
        inst, _ = _load_rutracker()
        with patch.object(inst, "_open_url", return_value=SEARCH_PAGE_EMPTY.encode(inst.encoding)) as mock_open:
            inst.search("python", "books")
        called_url = mock_open.call_args_list[0][0][0]
        assert "f=21" in called_url

    def test_search_unknown_category_defaults_to_minus1(self):
        inst, _ = _load_rutracker()
        with patch.object(inst, "_open_url", return_value=SEARCH_PAGE_EMPTY.encode(inst.encoding)) as mock_open:
            inst.search("test", "nonexistent")
        called_url = mock_open.call_args_list[0][0][0]
        assert "f=-1" in called_url

    def test_search_url_is_forum_based(self):
        inst, _ = _load_rutracker()
        with patch.object(inst, "_open_url", return_value=SEARCH_PAGE_EMPTY.encode(inst.encoding)) as mock_open:
            inst.search("test")
        called_url = mock_open.call_args_list[0][0][0]
        assert called_url.startswith(inst.url)
        assert "/forum/tracker.php?" in called_url


class TestSearchExceptionHandling:
    def test_search_network_error_returns_empty(self):
        inst, cap = _load_rutracker()
        with patch.object(inst, "_open_url", side_effect=URLError("connection refused")):
            inst.search("test")
        assert len(cap) == 0

    def test_search_http_error_returns_empty(self):
        inst, cap = _load_rutracker()
        with patch.object(
            inst, "_open_url", side_effect=HTTPError("http://fake", 503, "Service Unavailable", {}, BytesIO(b""))
        ):
            inst.search("test")
        assert len(cap) == 0

    def test_search_generic_exception_returns_empty(self):
        inst, cap = _load_rutracker()
        with patch.object(inst, "_open_url", side_effect=RuntimeError("boom")):
            inst.search("test")
        assert len(cap) == 0


class TestDownloadTorrent:
    def test_valid_torrent_data(self, capsys, tmp_path):
        """Download with data starting with 'd' (bencode dict) succeeds."""
        inst, _ = _load_rutracker()
        torrent_data = b"d8:announce41:http://tracker.example.com/announcee"
        mock_file = MagicMock()
        mock_file.fileno.return_value = 99
        with patch.object(inst, "_open_url", return_value=torrent_data):
            with patch("tempfile.mkstemp", return_value=(10, str(tmp_path / "test.torrent"))):
                with patch("os.fdopen") as mock_fdopen:
                    mock_fdopen.return_value.__enter__ = lambda s: mock_file
                    mock_fdopen.return_value.__exit__ = MagicMock(return_value=False)
                    with patch("os.fsync"), patch("os.chmod"):
                        inst.download_torrent("http://fake/dl.php?t=1")
        out = capsys.readouterr().out
        assert "http://fake/dl.php?t=1" in out

    def test_empty_data_raises(self):
        inst, _ = _load_rutracker()
        with patch.object(inst, "_open_url", return_value=b""):
            with pytest.raises(ValueError, match="No data received"):
                inst.download_torrent("http://fake/dl.php?t=1")

    def test_html_page_raises(self):
        inst, _ = _load_rutracker()
        html_data = b"<html><body>Login required</body></html>"
        with patch.object(inst, "_open_url", return_value=html_data):
            with pytest.raises(ValueError, match="not a valid torrent"):
                inst.download_torrent("http://fake/dl.php?t=1")

    def test_non_torrent_binary_raises(self):
        inst, _ = _load_rutracker()
        garbage = b"\x00\x01\x02\x03not_a_torrent"
        with patch.object(inst, "_open_url", return_value=garbage):
            with pytest.raises(ValueError, match="not a valid torrent"):
                inst.download_torrent("http://fake/dl.php?t=1")

    def test_url_error_propagates(self):
        inst, _ = _load_rutracker()
        with patch.object(inst, "_open_url", side_effect=URLError("timeout")):
            with pytest.raises(URLError):
                inst.download_torrent("http://fake/dl.php?t=1")

    def test_http_error_propagates(self):
        inst, _ = _load_rutracker()
        with patch.object(inst, "_open_url", side_effect=HTTPError("http://fake", 404, "Not Found", {}, BytesIO(b""))):
            with pytest.raises(HTTPError):
                inst.download_torrent("http://fake/dl.php?t=1")

    def test_torrent_written_to_temp_file(self, tmp_path):
        """Valid torrent data is written to a temp file via fdopen."""
        inst, _ = _load_rutracker()
        torrent_data = b"d8:announce41:http://tracker.example.com/announcee"
        written_bytes = []

        mock_file = MagicMock()
        mock_file.write.side_effect = lambda data: written_bytes.append(data)
        mock_file.fileno.return_value = 99

        with patch.object(inst, "_open_url", return_value=torrent_data):
            with patch("tempfile.mkstemp", return_value=(10, str(tmp_path / "out.torrent"))):
                with patch("os.fdopen") as mock_fdopen:
                    mock_fdopen.return_value.__enter__ = lambda s: mock_file
                    mock_fdopen.return_value.__exit__ = MagicMock(return_value=False)
                    with patch("os.fsync"), patch("os.chmod"):
                        inst.download_torrent("http://fake/dl.php?t=1")
        assert written_bytes == [torrent_data]

    def test_torrent_file_permissions_set(self, tmp_path):
        """os.chmod is called with 0o644 after writing."""
        inst, _ = _load_rutracker()
        torrent_data = b"d8:announce41:http://tracker.example.com/announcee"
        mock_file = MagicMock()
        mock_file.fileno.return_value = 99
        chmod_calls = []
        with patch.object(inst, "_open_url", return_value=torrent_data):
            with patch("tempfile.mkstemp", return_value=(10, str(tmp_path / "perms.torrent"))):
                with patch("os.fdopen") as mock_fdopen:
                    mock_fdopen.return_value.__enter__ = lambda s: mock_file
                    mock_fdopen.return_value.__exit__ = MagicMock(return_value=False)
                    with patch("os.fsync"), patch("os.chmod", side_effect=lambda p, m: chmod_calls.append((p, m))):
                        inst.download_torrent("http://fake/dl.php?t=1")
        assert chmod_calls == [(str(tmp_path / "perms.torrent"), 0o644)]


class TestBuildMagnetLink:
    def test_basic_magnet(self):
        inst, _ = _load_rutracker()
        link = inst._build_magnet_link("aabbccddee" * 4, "Test Name")
        assert link.startswith("magnet:?xt=urn:btih:")
        assert "aabbccddee" * 4 in link
        assert "dn=Test%20Name" in link
        assert "tr=" in link

    def test_trackers_included(self):
        import rutracker

        inst, _ = _load_rutracker()
        link = inst._build_magnet_link("aabbccddee" * 4, "Test")
        for tracker in rutracker.RUTRACKER_TRACKERS:
            from urllib.parse import quote

            assert quote(tracker, safe="/") in link

    def test_special_characters_encoded(self):
        inst, _ = _load_rutracker()
        link = inst._build_magnet_link("aabbccddee" * 4, "C++ & Python [2024]")
        assert "dn=C%2B%2B%20%26%20Python%20%5B2024%5D" in link

    def test_cyrillic_name_encoded(self):
        inst, _ = _load_rutracker()
        link = inst._build_magnet_link("aabbccddee" * 4, "Музыка")
        assert "dn=" in link
        assert "%D0%9C" in link


class TestFetchMagnetFromTopic:
    def test_magnet_found(self):
        inst, _ = _load_rutracker()
        with patch.object(inst, "_open_url", return_value=TOPIC_PAGE_MAGNET.encode(inst.encoding)):
            result = inst._fetch_magnet_from_topic("12345")
        assert result == "aaaabbbbccccddddeeeeffffaaaabbbbccccdddd"

    def test_no_magnet_returns_none(self):
        inst, _ = _load_rutracker()
        with patch.object(inst, "_open_url", return_value=TOPIC_PAGE_NO_MAGNET.encode(inst.encoding)):
            result = inst._fetch_magnet_from_topic("99999")
        assert result is None

    def test_network_error_returns_none(self):
        inst, _ = _load_rutracker()
        with patch.object(inst, "_open_url", side_effect=URLError("timeout")):
            result = inst._fetch_magnet_from_topic("12345")
        assert result is None

    def test_http_error_returns_none(self):
        inst, _ = _load_rutracker()
        with patch.object(inst, "_open_url", side_effect=HTTPError("http://fake", 404, "Not Found", {}, BytesIO(b""))):
            result = inst._fetch_magnet_from_topic("12345")
        assert result is None

    def test_topic_url_correctly_formatted(self):
        inst, _ = _load_rutracker()
        with patch.object(inst, "_open_url", return_value=TOPIC_PAGE_NO_MAGNET.encode(inst.encoding)) as mock_open:
            inst._fetch_magnet_from_topic("42")
        called_url = mock_open.call_args[0][0]
        assert "viewtopic.php?t=42" in called_url


class TestOpenUrl:
    def test_uncompressed_response(self):
        inst, _ = _load_rutracker()
        mock_response = MagicMock()
        mock_response.getcode.return_value = 200
        mock_response.info.return_value = {}
        mock_response.read.return_value = b"hello"
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        inst.opener = MagicMock()
        inst.opener.open.return_value = mock_response
        result = inst._open_url("http://example.com")
        assert result == b"hello"

    def test_gzip_compressed_response(self):
        inst, _ = _load_rutracker()
        original = b"compressed content here"
        compressed = gzip.compress(original)
        mock_response = MagicMock()
        mock_response.getcode.return_value = 200
        mock_response.info.return_value = {"Content-Encoding": "gzip"}
        mock_response.read.return_value = compressed
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        inst.opener = MagicMock()
        inst.opener.open.return_value = mock_response
        result = inst._open_url("http://example.com")
        assert result == original

    def test_non_200_raises_http_error(self):
        inst, _ = _load_rutracker()
        mock_response = MagicMock()
        mock_response.getcode.return_value = 500
        mock_response.info.return_value = {}
        mock_response.geturl.return_value = "http://example.com"
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        inst.opener = MagicMock()
        inst.opener.open.return_value = mock_response
        with pytest.raises(HTTPError):
            inst._open_url("http://example.com")

    def test_url_error_propagates(self):
        inst, _ = _load_rutracker()
        inst.opener = MagicMock()
        inst.opener.open.side_effect = URLError("DNS failure")
        with pytest.raises(URLError):
            inst._open_url("http://example.com")

    def test_log_errors_false_suppresses_logging(self):
        inst, _ = _load_rutracker()
        inst.opener = MagicMock()
        inst.opener.open.side_effect = URLError("fail")
        with pytest.raises(URLError):
            inst._open_url("http://example.com", log_errors=False)

    def test_post_params_encoded(self):
        inst, _ = _load_rutracker()
        mock_response = MagicMock()
        mock_response.getcode.return_value = 200
        mock_response.info.return_value = {}
        mock_response.read.return_value = b"ok"
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        inst.opener = MagicMock()
        inst.opener.open.return_value = mock_response
        inst._open_url("http://example.com", post_params={"key": "value"})
        call_args = inst.opener.open.call_args
        assert call_args[0][0] == "http://example.com"
        assert call_args[0][1] is not None


class TestCheckMirrors:
    def test_first_reachable_mirror_returned(self):
        inst, _ = _load_rutracker()
        mock_response = MagicMock()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        inst.opener = MagicMock()
        inst.opener.open.return_value = mock_response
        result = inst._check_mirrors(["https://m1.example.com", "https://m2.example.com"])
        assert result == "https://m1.example.com"

    def test_fallback_to_second_mirror(self):
        inst, _ = _load_rutracker()
        mock_response = MagicMock()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        inst.opener = MagicMock()
        inst.opener.open.side_effect = [URLError("fail"), mock_response]
        result = inst._check_mirrors(["https://m1.example.com", "https://m2.example.com"])
        assert result == "https://m2.example.com"

    def test_all_mirrors_fail_raises_runtime_error(self):
        inst, _ = _load_rutracker()
        inst.opener = MagicMock()
        inst.opener.open.side_effect = URLError("fail")
        with pytest.raises(RuntimeError):
            inst._check_mirrors(["https://m1.example.com", "https://m2.example.com"])


class TestEdgeCases:
    def test_cyrillic_text_parsed(self):
        inst, cap = _load_rutracker()
        inst.results = {}
        with patch.object(inst, "_open_url", return_value=CYRILLIC_ROW.encode(inst.encoding)):
            inst._RuTracker__execute_search("http://fake/url")
        assert len(cap) == 1
        assert cap[0]["id"] == "999"

    def test_special_characters_parsed(self):
        inst, cap = _load_rutracker()
        inst.results = {}
        with patch.object(inst, "_open_url", return_value=SPECIAL_ROW.encode(inst.encoding)):
            inst._RuTracker__execute_search("http://fake/url")
        assert len(cap) == 1
        assert cap[0]["id"] == "555"

    def test_zero_seeds_and_leech(self):
        inst, cap = _load_rutracker()
        inst.results = {}
        with patch.object(inst, "_open_url", return_value=ZERO_ROW.encode(inst.encoding)):
            inst._RuTracker__execute_search("http://fake/url")
        assert cap[0]["seeds"] == "0"
        assert cap[0]["leech"] == "0"

    def test_negative_seeds(self):
        inst, cap = _load_rutracker()
        inst.results = {}
        with patch.object(inst, "_open_url", return_value=NEGATIVE_ROW.encode(inst.encoding)):
            inst._RuTracker__execute_search("http://fake/url")
        assert cap[0]["seeds"] == "-1"

    def test_no_results_page(self):
        inst, cap = _load_rutracker()
        inst.results = {}
        with patch.object(inst, "_open_url", return_value=SEARCH_PAGE_EMPTY.encode(inst.encoding)):
            inst._RuTracker__execute_search("http://fake/url")
        assert len(cap) == 0
        assert len(inst.results) == 0

    def test_search_initializes_results_dict(self):
        inst, _ = _load_rutracker()
        inst.results = {"stale": "data"}
        with patch.object(inst, "_open_url", return_value=SEARCH_PAGE_EMPTY.encode(inst.encoding)):
            inst.search("test")
        assert inst.results == {}

    def test_topic_url_called_correctly_for_fetch(self):
        """_fetch_magnet_from_topic builds the URL with topic_id."""
        inst, _ = _load_rutracker()
        with patch.object(inst, "_open_url", return_value=TOPIC_PAGE_NO_MAGNET.encode(inst.encoding)) as mock_open:
            inst._fetch_magnet_from_topic("5678")
        called_url = mock_open.call_args[0][0]
        assert "viewtopic.php?t=5678" in called_url

    def test_results_accumulate_across_pages(self):
        """Multiple __execute_search calls accumulate into self.results."""
        inst, cap = _load_rutracker()
        inst.results = {}
        with patch.object(inst, "_open_url", return_value=SINGLE_ROW.encode(inst.encoding)):
            inst._RuTracker__execute_search("http://fake/page1")
            inst._RuTracker__execute_search("http://fake/page2")
        assert len(cap) == 2
        assert len(inst.results) == 1  # same topic_id → deduped in dict

    def test_search_pagination_fetches_all_pages(self):
        """search() fans out to all discovered pagination pages."""
        inst, cap = _load_rutracker()

        page1_html = (
            "<html><body>"
            '<table id="tor-tbl">'
            + SINGLE_ROW
            + """</table>
<a href="tracker.php?nm=test&amp;start=50">next</a>
</body></html>"""
        ).encode(inst.encoding)

        page2_html = (
            '<tr id="trs-tr-999">'
            '<td><a data-topic_id="999">Page Two Result</a></td>'
            '<td data-ts_text="1048576"></td>'
            '<td data-ts_text="5"></td>'
            '<td class="leechmed"><b>2</b></td>'
            '<td data-ts_text="1672531200"></td>'
            "</tr>"
        ).encode(inst.encoding)

        def fake_open(url, post_params=None, log_errors=True):
            if "start=50" in url:
                return page2_html
            return page1_html

        with patch.object(inst, "_open_url", side_effect=fake_open):
            inst.search("test")
        assert len(cap) == 2
        ids = {r["id"] for r in cap}
        assert "12345" in ids
        assert "999" in ids

    def test_download_url_fallback_when_no_magnet(self):
        """When _fetch_magnet_from_topic returns None, link is dl.php URL."""
        inst, cap = _load_rutracker()
        inst.results = {}
        with patch.object(inst, "_open_url", return_value=SINGLE_ROW.encode(inst.encoding)):
            inst._RuTracker__execute_search("http://fake/url")
        assert "dl.php?t=12345" in cap[0]["link"]

    def test_magnet_link_format_complete(self):
        """Magnet link contains all required components."""
        inst, cap = _load_rutracker()
        inst.results = {}

        def fake_open(url, post_params=None, log_errors=True):
            if "viewtopic" in url:
                return TOPIC_PAGE_MAGNET.encode(inst.encoding)
            return SINGLE_ROW.encode(inst.encoding)

        with patch.object(inst, "_open_url", side_effect=fake_open):
            inst._RuTracker__execute_search("http://fake/url")
        link = cap[0]["link"]
        assert link.startswith("magnet:?xt=urn:btih:")
        assert "&dn=" in link
        assert "&tr=" in link
        import rutracker

        assert link.count("&tr=") == len(rutracker.RUTRACKER_TRACKERS)
