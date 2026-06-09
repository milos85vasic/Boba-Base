"""Deep coverage tests for plugins/community/snowfl.py.

Covers: Parser (token retrieval, query generation, feed/prettyPrinter),
search (URL construction, category mapping, exception handling),
download_torrent (magnet links, torrent pages, no links, URLError),
category mapping, edge cases (special chars, random strings, URL encoding).
"""

import importlib.util
import json
import os
import re
import sys
import time
import types
import urllib.parse
from unittest.mock import MagicMock, patch

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PLUGINS_DIR = os.path.join(REPO, "plugins")


def _load_snowfl(retrieve_url_return=None):
    """Import snowfl plugin with stub modules.

    Returns (instance, mod, captured) where captured is the list of dicts
    passed to prettyPrinter. After loading, patch ``mod.retrieve_url`` to
    control network responses per-test.
    """
    captured = []
    np_mod = types.ModuleType("novaprinter")
    np_mod.prettyPrinter = lambda d: captured.append(dict(d))
    sys.modules["novaprinter"] = np_mod

    helpers_mod = types.ModuleType("helpers")
    helpers_mod.retrieve_url = lambda url: ""
    sys.modules["helpers"] = helpers_mod

    sys.modules.pop("snowfl", None)

    path = os.path.join(PLUGINS_DIR, "community", "snowfl.py")
    spec = importlib.util.spec_from_file_location("snowfl", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules["snowfl"] = mod

    cls = getattr(mod, "snowfl", None)
    assert cls is not None and isinstance(cls, type)
    return cls(), mod, captured


# ─── Fixtures ──────────────────────────────────────────────────────────────

INDEX_HTML = '''<html><head>
<script src="b.min.js?v=abc123def"></script>
</head><body></body></html>'''

INDEX_HTML_NO_SCRIPT = '<html><head></head><body></body></html>'
INDEX_HTML_MULTIPLE_SCRIPTS = '''<html><head>
<script src="other.js"></script>
<script src="b.min.js?v=xyz789"></script>
</head></html>'''

SCRIPT_JS = '''var token="mytoken123";$((function(){var e,t,n,r,o,a,i='''
SCRIPT_JS_NO_TOKEN = 'var x=1;$(function(){var e,t,n,r,o,a,i='

SAMPLE_COLLECTION = [
    {
        "magnet": "magnet:?xt=urn:btih:abc123&dn=Test+Movie",
        "name": "Test.Movie.2024.1080p",
        "size": "1500000000",
        "seeder": "120",
        "leecher": "30",
        "url": "https://snowfl.com/torrent/abc123",
    },
    {
        "url": "https://snowfl.com/torrent/def456",
        "name": "Another.Show.S01E01",
        "size": "800000000",
        "seeder": "50",
        "leecher": "10",
    },
]

SAMPLE_JSON = json.dumps(SAMPLE_COLLECTION)


# ─── Helpers ───────────────────────────────────────────────────────────────


def _make_parser(mod, helpers_returns):
    """Build a Parser with controlled retrieve_url returns."""
    mod.retrieve_url = MagicMock(side_effect=helpers_returns)
    return mod.snowfl.Parser("https://snowfl.com/")


# ─── Parser: token retrieval ───────────────────────────────────────────────


class TestParserTokenRetrieval:
    def test_token_extracted_from_script(self):
        inst, mod, captured = _load_snowfl()
        parser = _make_parser(mod, [INDEX_HTML, SCRIPT_JS])
        assert parser.token == "mytoken123"

    def test_token_uses_correct_urls(self):
        inst, mod, captured = _load_snowfl()
        mod.retrieve_url = MagicMock(side_effect=[INDEX_HTML, SCRIPT_JS])
        mod.snowfl.Parser("https://snowfl.com/")
        calls = mod.retrieve_url.call_args_list
        assert calls[0][0][0] == "https://snowfl.com/index.html"
        assert "b.min.js" in calls[1][0][0]

    def test_token_picks_first_script_match(self):
        inst, mod, captured = _load_snowfl()
        parser = _make_parser(mod, [INDEX_HTML_MULTIPLE_SCRIPTS, SCRIPT_JS])
        assert parser.token == "mytoken123"

    def test_token_retrieval_no_script_raises(self):
        inst, mod, captured = _load_snowfl()
        mod.retrieve_url = MagicMock(return_value=INDEX_HTML_NO_SCRIPT)
        with pytest.raises(IndexError):
            mod.snowfl.Parser("https://snowfl.com/")

    def test_token_retrieval_no_token_in_script_raises(self):
        inst, mod, captured = _load_snowfl()
        mod.retrieve_url = MagicMock(
            side_effect=[INDEX_HTML, SCRIPT_JS_NO_TOKEN]
        )
        with pytest.raises(IndexError):
            mod.snowfl.Parser("https://snowfl.com/")


# ─── Parser: feed / prettyPrinter ─────────────────────────────────────────


class TestParserFeed:
    def test_feed_magnet_link(self):
        inst, mod, captured = _load_snowfl()
        parser = _make_parser(mod, [INDEX_HTML, SCRIPT_JS])
        parser.feed([SAMPLE_COLLECTION[0]])
        assert len(captured) == 1
        assert captured[0]["link"] == "magnet:?xt=urn:btih:abc123&dn=Test+Movie"
        assert captured[0]["name"] == "Test.Movie.2024.1080p"
        assert captured[0]["engine_url"] == "https://snowfl.com/"

    def test_feed_non_magnet_url_encoded(self):
        inst, mod, captured = _load_snowfl()
        parser = _make_parser(mod, [INDEX_HTML, SCRIPT_JS])
        parser.feed([SAMPLE_COLLECTION[1]])
        assert len(captured) == 1
        assert "def456" in captured[0]["link"]
        assert urllib.parse.quote("https://snowfl.com/torrent/def456") == captured[0]["link"]

    def test_feed_multiple_results(self):
        inst, mod, captured = _load_snowfl()
        parser = _make_parser(mod, [INDEX_HTML, SCRIPT_JS])
        parser.feed(SAMPLE_COLLECTION)
        assert len(captured) == 2
        assert captured[0]["seeds"] == "120"
        assert captured[1]["seeds"] == "50"

    def test_feed_empty_collection(self):
        inst, mod, captured = _load_snowfl()
        parser = _make_parser(mod, [INDEX_HTML, SCRIPT_JS])
        parser.feed([])
        assert len(captured) == 0

    def test_feed_preserves_all_fields(self):
        inst, mod, captured = _load_snowfl()
        parser = _make_parser(mod, [INDEX_HTML, SCRIPT_JS])
        parser.feed([SAMPLE_COLLECTION[0]])
        d = captured[0]
        assert d["size"] == "1500000000"
        assert d["leech"] == "30"
        assert d["desc_link"] == "https://snowfl.com/torrent/abc123"


# ─── Parser: generateQuery ─────────────────────────────────────────────────


class TestParserGenerateQuery:
    def test_query_format(self):
        inst, mod, captured = _load_snowfl()
        parser = _make_parser(mod, [INDEX_HTML, SCRIPT_JS])
        q = parser.generateQuery("test+query")
        assert "https://snowfl.com/" in q
        assert "mytoken123" in q
        assert "test+query" in q
        assert "/0/SEED/NONE/1?_=" in q

    def test_query_timestamp_is_millis(self):
        inst, mod, captured = _load_snowfl()
        parser = _make_parser(mod, [INDEX_HTML, SCRIPT_JS])
        before = int(time.time() * 1000)
        q = parser.generateQuery("x")
        after = int(time.time() * 1000)
        ts = int(q.split("_=")[1])
        assert before <= ts <= after

    def test_query_random_str_alphanumeric_lowercase(self):
        inst, mod, captured = _load_snowfl()
        parser = _make_parser(mod, [INDEX_HTML, SCRIPT_JS])
        q = parser.generateQuery("x")
        # Format: {url}/{token}/{what}/{random_str}/0/SEED/NONE/1?_={ts}
        m = re.search(r"/([a-z0-9]{8})/0/SEED/NONE/1\?_=", q)
        assert m is not None
        random_part = m.group(1)
        assert len(random_part) == 8
        assert all(c in "abcdefghijklmnopqrstuvwxyz0123456789" for c in random_part)

    def test_query_special_characters_preserved(self):
        inst, mod, captured = _load_snowfl()
        parser = _make_parser(mod, [INDEX_HTML, SCRIPT_JS])
        q = parser.generateQuery("hello+world&foo=bar")
        assert "hello+world&foo=bar" in q


# ─── download_torrent tests ────────────────────────────────────────────────


class TestDownloadTorrent:
    def test_magnet_link_printed_directly(self, capsys):
        inst, mod, captured = _load_snowfl()
        magnet = "magnet:?xt=urn:btih:abc123&dn=Movie"
        inst.download_torrent(magnet)
        out = capsys.readouterr().out.strip()
        assert out == f"{magnet} {magnet}"

    def test_magnet_with_extra_params(self, capsys):
        inst, mod, captured = _load_snowfl()
        magnet = "magnet:?xt=urn:btih:abc123&dn=Movie&tr=http://tracker"
        inst.download_torrent(magnet)
        out = capsys.readouterr().out.strip()
        assert out == f"{magnet} {magnet}"

    def test_non_magnet_extracts_from_page(self, capsys):
        inst, mod, captured = _load_snowfl()
        page_html = '"magnet:?xt=urn:btih:def456&dn=Show"'
        mod.retrieve_url = MagicMock(return_value=page_html)
        inst.download_torrent("https://snowfl.com/torrent/def456")
        out = capsys.readouterr().out.strip()
        assert "magnet:?xt=urn:btih:def456" in out
        assert "https://snowfl.com/torrent/def456" in out

    def test_non_magnet_in_json_payload(self, capsys):
        inst, mod, captured = _load_snowfl()
        page_html = '{"download":"magnet:?xt=urn:btih:aaa111&dn=Test"}'
        mod.retrieve_url = MagicMock(return_value=page_html)
        inst.download_torrent("https://snowfl.com/t/1")
        out = capsys.readouterr().out.strip()
        assert "magnet:?xt=urn:btih:aaa111" in out

    def test_no_magnet_on_page_raises(self):
        inst, mod, captured = _load_snowfl()
        mod.retrieve_url = MagicMock(return_value="<html>no magnet here</html>")
        with pytest.raises(Exception, match="bug report"):
            inst.download_torrent("https://snowfl.com/torrent/xyz")

    def test_empty_page_raises(self):
        inst, mod, captured = _load_snowfl()
        mod.retrieve_url = MagicMock(return_value="")
        with pytest.raises(Exception, match="bug report"):
            inst.download_torrent("https://snowfl.com/torrent/empty")

    def test_url_is_unquoted_before_fetch(self):
        inst, mod, captured = _load_snowfl()
        mod.retrieve_url = MagicMock(return_value="")
        encoded_url = "https%3A%2F%2Fsnowfl.com%2Ftorrent%2F123"
        try:
            inst.download_torrent(encoded_url)
        except Exception:
            pass
        called_url = mod.retrieve_url.call_args[0][0]
        assert "snowfl.com/torrent/123" in called_url


# ─── search tests ──────────────────────────────────────────────────────────


class TestSearch:
    def test_search_calls_feeds_json_results(self):
        inst, mod, captured = _load_snowfl()
        mod.retrieve_url = MagicMock(
            side_effect=[INDEX_HTML, SCRIPT_JS, SAMPLE_JSON]
        )
        inst.search("test+movie")
        assert len(captured) == 2

    def test_search_url_contains_token_and_query(self):
        inst, mod, captured = _load_snowfl()
        mod.retrieve_url = MagicMock(
            side_effect=[INDEX_HTML, SCRIPT_JS, SAMPLE_JSON]
        )
        inst.search("my+query")
        third_call = mod.retrieve_url.call_args_list[2][0][0]
        assert "mytoken123" in third_call
        assert "my+query" in third_call

    def test_search_empty_results(self):
        inst, mod, captured = _load_snowfl()
        mod.retrieve_url = MagicMock(
            side_effect=[INDEX_HTML, SCRIPT_JS, "[]"]
        )
        inst.search("nothing")
        assert len(captured) == 0

    def test_search_invalid_json_raises(self):
        inst, mod, captured = _load_snowfl()
        mod.retrieve_url = MagicMock(
            side_effect=[INDEX_HTML, SCRIPT_JS, "NOT JSON"]
        )
        with pytest.raises((json.JSONDecodeError, ValueError)):
            inst.search("broken")

    def test_search_retrieve_url_failure_propagates(self):
        inst, mod, captured = _load_snowfl()
        # First call is to index.html for token — make that fail
        mod.retrieve_url = MagicMock(side_effect=Exception("Network error"))
        with pytest.raises(Exception, match="Network error"):
            inst.search("anything")


# ─── Class attribute tests ─────────────────────────────────────────────────


class TestClassAttributes:
    def test_url(self):
        inst, _, _ = _load_snowfl()
        assert inst.url == "https://snowfl.com/"

    def test_name(self):
        inst, _, _ = _load_snowfl()
        assert inst.name == "Snowfl"

    def test_supported_categories(self):
        inst, _, _ = _load_snowfl()
        assert inst.supported_categories == {"all": "0"}

    def test_version_in_source(self):
        path = os.path.join(PLUGINS_DIR, "community", "snowfl.py")
        with open(path) as f:
            content = f.read()
        assert re.search(r"#\s*VERSION:\s*1\.3", content)
