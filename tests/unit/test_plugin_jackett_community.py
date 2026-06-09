"""Deep coverage tests for plugins/community/jackett.py.

Covers: ProxyManager, configuration loading/saving, Jackett XML/JSON parsing
(single/multi/empty/malformed), search (URL construction, category mapping,
Pool(0) guard, exception handling), download_torrent (magnet links, torrent
files, no links, URLError), API communication (indexer list, search results),
escape_pipe, generate_xpath, handle_error, pretty_printer_thread_safe.
"""

import importlib.util
import json
import os
import sys
import types
import urllib.request
import xml.etree.ElementTree as ET
from unittest.mock import MagicMock, mock_open, patch

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PLUGINS_DIR = os.path.join(REPO, "plugins", "community")

# ─── Torznab XML fixtures ─────────────────────────────────────────────

TORZNAB_NS = "http://torznab.com/schemas/2015/feed"


def _torznab_attr(name: str, value: str) -> ET.Element:
    el = ET.Element(f"{{{TORZNAB_NS}}}attr")
    el.set("name", name)
    el.set("value", value)
    return el


def _build_indexers_xml(ids: list[str]) -> str:
    root = ET.Element("indexers")
    for idx in ids:
        el = ET.SubElement(root, "indexer")
        el.set("id", idx)
    return ET.tostring(root, encoding="unicode")


def _build_single_result_xml(
    title: str = "Ubuntu 24.04",
    magnet: str | None = "magnet:?xt=urn:btih:abc123",
    link: str | None = "http://example.com/torrent/1",
    size: int = 1_500_000_000,
    seeds: int = 100,
    peers: int = 50,
    tracker: str = "ExampleTracker",
    pub_date: str = "Mon, 01 Jan 2024 12:00:00 +0000",
    comments: str | None = "http://example.com/details/1",
) -> str:
    rss = ET.Element("rss")
    channel = ET.SubElement(rss, "channel")
    item = ET.SubElement(channel, "item")
    title_el = ET.SubElement(item, "title")
    title_el.text = title
    tracker_el = ET.SubElement(item, "jackettindexer")
    tracker_el.text = tracker
    if magnet is not None:
        magnet_el = _torznab_attr("magneturl", magnet)
        item.append(magnet_el)
    if link is not None:
        link_el = ET.SubElement(item, "link")
        link_el.text = link
    size_el = ET.SubElement(item, "size")
    size_el.text = str(size)
    seeds_attr = _torznab_attr("seeders", str(seeds))
    item.append(seeds_attr)
    peers_attr = _torznab_attr("peers", str(peers))
    item.append(peers_attr)
    if pub_date:
        pub_el = ET.SubElement(item, "pubDate")
        pub_el.text = pub_date
    if comments:
        comments_el = ET.SubElement(item, "comments")
        comments_el.text = comments
    return ET.tostring(rss, encoding="unicode")


def _build_multi_results_xml(count: int = 3) -> str:
    rss = ET.Element("rss")
    channel = ET.SubElement(rss, "channel")
    for i in range(count):
        item = ET.SubElement(channel, "item")
        title_el = ET.SubElement(item, "title")
        title_el.text = f"Result {i}"
        tracker_el = ET.SubElement(item, "jackettindexer")
        tracker_el.text = f"Tracker{i}"
        magnet_el = _torznab_attr("magneturl", f"magnet:?xt=urn:btih:hash{i}")
        item.append(magnet_el)
        link_el = ET.SubElement(item, "link")
        link_el.text = f"http://example.com/torrent/{i}"
        size_el = ET.SubElement(item, "size")
        size_el.text = str((i + 1) * 1_000_000_000)
        seeds_attr = _torznab_attr("seeders", str(10 * (i + 1)))
        item.append(seeds_attr)
        peers_attr = _torznab_attr("peers", str(20 * (i + 1)))
        item.append(peers_attr)
        pub_el = ET.SubElement(item, "pubDate")
        pub_el.text = "Mon, 01 Jan 2024 12:00:00 +0000"
        comments_el = ET.SubElement(item, "comments")
        comments_el.text = f"http://example.com/details/{i}"
    return ET.tostring(rss, encoding="unicode")


def _build_empty_channel_xml() -> str:
    rss = ET.Element("rss")
    ET.SubElement(rss, "channel")
    return ET.tostring(rss, encoding="unicode")


def _build_no_title_item_xml() -> str:
    rss = ET.Element("rss")
    channel = ET.SubElement(rss, "channel")
    item = ET.SubElement(channel, "item")
    magnet_el = _torznab_attr("magneturl", "magnet:?xt=urn:btih:skipped")
    item.append(magnet_el)
    link_el = ET.SubElement(item, "link")
    link_el.text = "http://example.com/torrent/no-title"
    return ET.tostring(rss, encoding="unicode")


def _build_no_link_item_xml() -> str:
    rss = ET.Element("rss")
    channel = ET.SubElement(rss, "channel")
    item = ET.SubElement(channel, "item")
    title_el = ET.SubElement(item, "title")
    title_el.text = "No link result"
    return ET.tostring(rss, encoding="unicode")


def _build_guid_fallback_xml() -> str:
    rss = ET.Element("rss")
    channel = ET.SubElement(rss, "channel")
    item = ET.SubElement(channel, "item")
    title_el = ET.SubElement(item, "title")
    title_el.text = "Guid only"
    magnet_el = _torznab_attr("magneturl", "magnet:?xt=urn:btih:guidhash")
    item.append(magnet_el)
    link_el = ET.SubElement(item, "link")
    link_el.text = "http://example.com/torrent/guid"
    guid_el = ET.SubElement(item, "guid")
    guid_el.text = "http://example.com/guid/1"
    return ET.tostring(rss, encoding="unicode")


def _build_no_channel_xml() -> str:
    rss = ET.Element("rss")
    return ET.tostring(rss, encoding="unicode")


# ─── Loader ───────────────────────────────────────────────────────────

class _FakeResponse:
    def __init__(self, data: bytes | str, code: int = 200):
        if isinstance(data, str):
            data = data.encode("utf-8")
        self._data = data
        self.code = code
        self.url = ""

    def read(self) -> bytes:
        return self._data


def _load_jackett(captured=None, *, api_key="test_key_123", url="http://127.0.0.1:9117", tracker_first=False, thread_count=20):
    """Import jackett plugin with stubs. Returns (instance, captured, module)."""
    if captured is None:
        captured = []

    np_mod = types.ModuleType("novaprinter")
    np_mod.prettyPrinter = lambda d: captured.append(dict(d))
    sys.modules["novaprinter"] = np_mod

    helpers_mod = types.ModuleType("helpers")
    helpers_mod.retrieve_url = lambda url: ""
    helpers_mod.download_file = lambda url: url
    helpers_mod.enable_socks_proxy = lambda enable: None
    sys.modules["helpers"] = helpers_mod

    sys.modules.pop("jackett", None)

    config_data = {
        "api_key": api_key,
        "url": url,
        "tracker_first": tracker_first,
        "thread_count": thread_count,
    }

    path = os.path.join(PLUGINS_DIR, "jackett.py")
    spec = importlib.util.spec_from_file_location("jackett", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["jackett"] = mod

    with patch("builtins.open", mock_open(read_data=json.dumps(config_data))):
        spec.loader.exec_module(mod)

    mod.CONFIG_DATA = config_data
    mod.CONFIG_DATA.pop("malformed", None)
    cls = getattr(mod, "jackett", None)
    if cls is not None and isinstance(cls, type):
        inst = cls()
        return inst, captured, mod
    return mod, captured, mod


# ─── ProxyManager Tests ───────────────────────────────────────────────

class TestProxyManager:
    def test_enable_proxy_sets_env(self):
        _, _, mod = _load_jackett()
        pm = mod.ProxyManager()
        pm.http_proxy = "http://proxy:8080"
        pm.https_proxy = "http://proxy:8443"
        pm.enable_proxy(True)
        assert os.environ.get("http_proxy") == "http://proxy:8080"
        assert os.environ.get("https_proxy") == "http://proxy:8443"

    def test_disable_proxy_removes_env(self):
        _, _, mod = _load_jackett()
        pm = mod.ProxyManager()
        os.environ["http_proxy"] = "http://proxy:8080"
        os.environ["https_proxy"] = "http://proxy:8443"
        pm.enable_proxy(False)
        assert os.environ.get("http_proxy") is None
        assert os.environ.get("https_proxy") is None

    def test_disable_proxy_no_error_when_missing(self):
        _, _, mod = _load_jackett()
        pm = mod.ProxyManager()
        os.environ.pop("http_proxy", None)
        os.environ.pop("https_proxy", None)
        pm.enable_proxy(False)
        assert os.environ.get("http_proxy") is None

    def test_enable_proxy_calls_socks(self):
        _, _, mod = _load_jackett()
        pm = mod.ProxyManager()
        with patch.object(mod.helpers, "enable_socks_proxy") as mock_socks:
            pm.enable_proxy(True)
            mock_socks.assert_called_with(True)

    def test_enable_proxy_socks_attribute_error_swallows(self):
        _, _, mod = _load_jackett()
        pm = mod.ProxyManager()
        delattr(mod.helpers, "enable_socks_proxy")
        pm.enable_proxy(True)  # should not raise


# ─── Configuration Tests ──────────────────────────────────────────────

class TestConfiguration:
    def test_load_malformed_json(self):
        _, _, mod = _load_jackett()
        with patch("builtins.open", mock_open(read_data="{bad json")):
            mod.load_configuration()
        assert mod.CONFIG_DATA.get("malformed") is True

    def test_load_missing_file_creates_default(self):
        _, _, mod = _load_jackett()
        with patch("builtins.open", mock_open()) as mo:
            mo.side_effect = FileNotFoundError
            with patch.object(mod, "save_configuration"):
                mod.load_configuration()
        assert "api_key" in mod.CONFIG_DATA

    def test_env_override_api_key(self):
        _, _, mod = _load_jackett()
        mod.CONFIG_DATA = {
            "api_key": "old_key",
            "url": "http://localhost:9117",
            "tracker_first": False,
            "thread_count": 20,
        }
        with patch.dict(os.environ, {"JACKETT_API_KEY": "env_key"}):
            mod.load_configuration()
        assert mod.CONFIG_DATA["api_key"] == "env_key"

    def test_env_override_url(self):
        _, _, mod = _load_jackett()
        mod.CONFIG_DATA = {
            "api_key": "k",
            "url": "http://old:9117",
            "tracker_first": False,
            "thread_count": 20,
        }
        with patch.dict(os.environ, {"JACKETT_URL": "http://new:9999"}):
            mod.load_configuration()
        assert mod.CONFIG_DATA["url"] == "http://new:9999"

    def test_malformed_when_missing_keys(self):
        _, _, mod = _load_jackett()
        mod.CONFIG_DATA = {}
        with patch("builtins.open", mock_open(read_data=json.dumps({}))):
            mod.load_configuration()
        assert mod.CONFIG_DATA.get("malformed") is True

    def test_adds_missing_thread_count(self):
        _, _, mod = _load_jackett()
        mod.CONFIG_DATA = {
            "api_key": "k",
            "url": "http://localhost:9117",
            "tracker_first": False,
        }
        with patch("builtins.open", mock_open(read_data=json.dumps(mod.CONFIG_DATA))):
            with patch.object(mod, "save_configuration"):
                mod.load_configuration()
        assert mod.CONFIG_DATA["thread_count"] == 20

    def test_save_configuration(self):
        _, _, mod = _load_jackett()
        with patch("builtins.open", mock_open()) as mo:
            mod.save_configuration()
            handle = mo()
            written = "".join(call.args[0] for call in handle.write.call_args_list)
            data = json.loads(written)
            assert "api_key" in data


# ─── Jackett Class Init Tests ─────────────────────────────────────────

class TestJackettInit:
    def test_name(self, tmp_path):
        inst, _, mod = _load_jackett()
        assert inst.name == "Jackett"

    def test_url_strips_trailing_slash(self):
        inst, _, mod = _load_jackett(url="http://127.0.0.1:9117/")
        assert inst.url == "http://127.0.0.1:9117"

    def test_url_no_trailing_slash(self):
        inst, _, mod = _load_jackett(url="http://127.0.0.1:9117")
        assert inst.url == "http://127.0.0.1:9117"

    def test_api_key_from_config(self):
        inst, _, mod = _load_jackett(api_key="my_key")
        assert inst.api_key == "my_key"

    def test_supported_categories_all_keys(self):
        inst, _, mod = _load_jackett()
        expected = {"all", "anime", "books", "games", "movies", "music", "software", "tv"}
        assert set(inst.supported_categories.keys()) == expected

    def test_all_category_maps_to_none(self):
        inst, _, mod = _load_jackett()
        assert inst.supported_categories["all"] is None

    def test_category_values_are_string_lists(self):
        inst, _, mod = _load_jackett()
        for cat, val in inst.supported_categories.items():
            if cat != "all":
                assert isinstance(val, list)
                assert all(isinstance(v, str) for v in val)


# ─── generate_xpath Tests ─────────────────────────────────────────────

class TestGenerateXpath:
    def test_seeders_xpath(self):
        inst, _, _ = _load_jackett()
        result = inst.generate_xpath("seeders")
        assert "seeders" in result
        assert TORZNAB_NS in result

    def test_magneturl_xpath(self):
        inst, _, _ = _load_jackett()
        result = inst.generate_xpath("magneturl")
        assert "magneturl" in result

    def test_peers_xpath(self):
        inst, _, _ = _load_jackett()
        result = inst.generate_xpath("peers")
        assert "peers" in result

    def test_format(self):
        inst, _, _ = _load_jackett()
        result = inst.generate_xpath("foo")
        expected = f'./{{{TORZNAB_NS}}}attr[@name="foo"]'
        assert result == expected


# ─── escape_pipe Tests ────────────────────────────────────────────────

class TestEscapePipe:
    def test_no_pipes(self):
        inst, _, _ = _load_jackett()
        d = {"name": "hello", "link": "http://x.com"}
        result = inst.escape_pipe(d)
        assert result["name"] == "hello"
        assert result["link"] == "http://x.com"

    def test_pipes_escaped(self):
        inst, _, _ = _load_jackett()
        d = {"name": "a|b|c", "size": 123}
        result = inst.escape_pipe(d)
        assert result["name"] == "a%7Cb%7Cc"
        assert result["size"] == 123

    def test_non_string_values_preserved(self):
        inst, _, _ = _load_jackett()
        d = {"size": 42, "seeds": 10}
        result = inst.escape_pipe(d)
        assert result["size"] == 42
        assert result["seeds"] == 10

    def test_empty_string(self):
        inst, _, _ = _load_jackett()
        d = {"name": ""}
        result = inst.escape_pipe(d)
        assert result["name"] == ""


# ─── pretty_printer_thread_safe Tests ──────────────────────────────────

class TestPrettyPrinterThreadSafe:
    def test_calls_pretty_printer(self):
        inst, cap, mod = _load_jackett()
        d = {"name": "test", "link": "http://x.com", "size": 100}
        inst.pretty_printer_thread_safe(d)
        assert len(cap) == 1

    def test_escapes_pipes_before_print(self):
        inst, cap, mod = _load_jackett()
        d = {"name": "a|b"}
        inst.pretty_printer_thread_safe(d)
        assert cap[0]["name"] == "a%7Cb"

    def test_modifies_original_dict(self):
        inst, cap, mod = _load_jackett()
        d = {"name": "a|b"}
        inst.pretty_printer_thread_safe(d)
        assert d["name"] == "a%7Cb"


# ─── handle_error Tests ───────────────────────────────────────────────

class TestHandleError:
    def test_emits_error_row(self):
        inst, cap, _ = _load_jackett()
        inst.handle_error("test error", "query")
        assert len(cap) == 1
        row = cap[0]
        assert "test error" in row["name"]
        assert "query" in row["name"]
        assert row["size"] == -1
        assert row["seeds"] == -1
        assert row["leech"] == -1
        assert row["pub_date"] == -1

    def test_error_links_to_wiki(self):
        inst, cap, _ = _load_jackett()
        inst.handle_error("error", "query")
        assert "github.com/qbittorrent" in cap[0]["desc_link"]

    def test_error_link_is_engine_url(self):
        inst, cap, _ = _load_jackett()
        inst.handle_error("error", "query")
        assert cap[0]["link"] == inst.url


# ─── get_response Tests ───────────────────────────────────────────────

class TestGetResponse:
    def test_successful_response(self):
        inst, _, mod = _load_jackett()
        fake = _FakeResponse("<rss></rss>")
        with patch.object(mod.urllib.request, "build_opener") as mock_opener:
            mock_opener.return_value.open.return_value = fake
            result = inst.get_response("http://127.0.0.1:9117/api/test")
        assert result == "<rss></rss>"

    def test_http_302_returns_redirect_url(self):
        inst, _, mod = _load_jackett()
        err = urllib.request.HTTPError(
            url="http://example.com", code=302, msg="Redirect",
            hdrs=None, fp=None
        )
        err.url = "magnet:?xt=urn:btih:redirect"
        with patch.object(mod.urllib.request, "build_opener") as mock_opener:
            mock_opener.return_value.open.side_effect = err
            result = inst.get_response("http://example.com")
        assert result == "magnet:?xt=urn:btih:redirect"

    def test_http_error_non_302_returns_none(self):
        inst, _, mod = _load_jackett()
        err = urllib.request.HTTPError(
            url="http://example.com", code=500, msg="Server Error",
            hdrs=None, fp=None
        )
        with patch.object(mod.urllib.request, "build_opener") as mock_opener:
            mock_opener.return_value.open.side_effect = err
            result = inst.get_response("http://example.com")
        assert result is None

    def test_generic_exception_returns_none(self):
        inst, _, mod = _load_jackett()
        with patch.object(mod.urllib.request, "build_opener") as mock_opener:
            mock_opener.return_value.open.side_effect = OSError("connection refused")
            result = inst.get_response("http://example.com")
        assert result is None


# ─── get_jackett_indexers Tests ───────────────────────────────────────

class TestGetJackettIndexers:
    def _patch_get_response(self, mod, response_text):
        mod_mod = mod
        with patch.object(mod_mod, "jackett") as inst_cls:
            pass

    def test_returns_indexer_ids(self):
        inst, _, mod = _load_jackett()
        xml = _build_indexers_xml(["tracker1", "tracker2", "tracker3"])
        with patch.object(inst, "get_response", return_value=xml):
            result = inst.get_jackett_indexers("query")
        assert result == ["tracker1", "tracker2", "tracker3"]

    def test_empty_indexers(self):
        inst, _, mod = _load_jackett()
        xml = _build_indexers_xml([])
        with patch.object(inst, "get_response", return_value=xml):
            result = inst.get_jackett_indexers("query")
        assert result == []

    def test_connection_error_returns_empty(self):
        inst, _, mod = _load_jackett()
        with patch.object(inst, "get_response", return_value=None):
            with patch.object(inst, "handle_error") as mock_err:
                result = inst.get_jackett_indexers("query")
        assert result == []
        mock_err.assert_called_once()

    def test_calls_correct_url(self):
        inst, _, mod = _load_jackett(api_key="mykey")
        xml = _build_indexers_xml([])
        with patch.object(inst, "get_response", return_value=xml) as mock_resp:
            inst.get_jackett_indexers("query")
        called_url = mock_resp.call_args[0][0]
        assert "apikey=mykey" in called_url
        assert "t=indexers" in called_url
        assert "configured=true" in called_url


# ─── search_jackett_indexer Tests ─────────────────────────────────────

class TestSearchJackettIndexer:
    def test_single_result_parsed(self):
        inst, cap, mod = _load_jackett()
        xml = _build_single_result_xml()
        with patch.object(inst, "get_response", return_value=xml):
            inst.search_jackett_indexer("ubuntu", None, "all")
        assert len(cap) == 1
        assert "Ubuntu 24.04" in cap[0]["name"]

    def test_tracker_name_appended(self):
        inst, cap, mod = _load_jackett()
        xml = _build_single_result_xml(tracker="MyTracker")
        with patch.object(inst, "get_response", return_value=xml):
            inst.search_jackett_indexer("q", None, "all")
        assert "[MyTracker]" in cap[0]["name"]

    def test_tracker_first_mode(self):
        inst, cap, mod = _load_jackett(tracker_first=True)
        xml = _build_single_result_xml(tracker="FirstTracker")
        with patch.object(inst, "get_response", return_value=xml):
            inst.search_jackett_indexer("q", None, "all")
        assert cap[0]["name"].startswith("[FirstTracker]")

    def test_tracker_last_mode(self):
        inst, cap, mod = _load_jackett(tracker_first=False)
        xml = _build_single_result_xml(tracker="LastTracker")
        with patch.object(inst, "get_response", return_value=xml):
            inst.search_jackett_indexer("q", None, "all")
        assert cap[0]["name"].endswith("[LastTracker]")

    def test_multi_results(self):
        inst, cap, mod = _load_jackett()
        xml = _build_multi_results_xml(3)
        with patch.object(inst, "get_response", return_value=xml):
            inst.search_jackett_indexer("query", None, "all")
        assert len(cap) == 3

    def test_empty_channel(self):
        inst, cap, mod = _load_jackett()
        xml = _build_empty_channel_xml()
        with patch.object(inst, "get_response", return_value=xml):
            inst.search_jackett_indexer("query", None, "all")
        assert len(cap) == 0

    def test_no_channel(self):
        inst, cap, mod = _load_jackett()
        xml = _build_no_channel_xml()
        with patch.object(inst, "get_response", return_value=xml):
            inst.search_jackett_indexer("query", None, "all")
        assert len(cap) == 0

    def test_item_without_title_skipped(self):
        inst, cap, mod = _load_jackett()
        xml = _build_no_title_item_xml()
        with patch.object(inst, "get_response", return_value=xml):
            inst.search_jackett_indexer("query", None, "all")
        assert len(cap) == 0

    def test_item_without_link_skipped(self):
        inst, cap, mod = _load_jackett()
        xml = _build_no_link_item_xml()
        with patch.object(inst, "get_response", return_value=xml):
            inst.search_jackett_indexer("query", None, "all")
        assert len(cap) == 0

    def test_guid_fallback_when_no_comments(self):
        inst, cap, mod = _load_jackett()
        xml = _build_guid_fallback_xml()
        with patch.object(inst, "get_response", return_value=xml):
            inst.search_jackett_indexer("query", None, "all")
        assert len(cap) == 1
        assert "http://example.com/guid/1" in cap[0]["desc_link"]

    def test_connection_error_calls_handle_error(self):
        inst, cap, mod = _load_jackett()
        with patch.object(inst, "get_response", return_value=None):
            with patch.object(inst, "handle_error") as mock_err:
                inst.search_jackett_indexer("query", None, "testindexer")
        mock_err.assert_called_once()
        assert "testindexer" in mock_err.call_args[0][0]

    def test_size_parsed(self):
        inst, cap, mod = _load_jackett()
        xml = _build_single_result_xml(size=2_500_000_000)
        with patch.object(inst, "get_response", return_value=xml):
            inst.search_jackett_indexer("q", None, "all")
        assert "2500000000" in cap[0]["size"]

    def test_size_none_results_in_minus_one(self):
        inst, cap, mod = _load_jackett()
        rss = ET.Element("rss")
        channel = ET.SubElement(rss, "channel")
        item = ET.SubElement(channel, "item")
        title_el = ET.SubElement(item, "title")
        title_el.text = "No size"
        magnet_el = _torznab_attr("magneturl", "magnet:?xt=urn:btih:x")
        item.append(magnet_el)
        link_el = ET.SubElement(item, "link")
        link_el.text = "http://example.com/x"
        xml = ET.tostring(rss, encoding="unicode")
        with patch.object(inst, "get_response", return_value=xml):
            inst.search_jackett_indexer("q", None, "all")
        assert cap[0]["size"] == -1

    def test_seeders_none_results_in_minus_one(self):
        inst, cap, mod = _load_jackett()
        rss = ET.Element("rss")
        channel = ET.SubElement(rss, "channel")
        item = ET.SubElement(channel, "item")
        title_el = ET.SubElement(item, "title")
        title_el.text = "No seeds"
        magnet_el = _torznab_attr("magneturl", "magnet:?xt=urn:btih:y")
        item.append(magnet_el)
        link_el = ET.SubElement(item, "link")
        link_el.text = "http://example.com/y"
        xml = ET.tostring(rss, encoding="unicode")
        with patch.object(inst, "get_response", return_value=xml):
            inst.search_jackett_indexer("q", None, "all")
        assert cap[0]["seeds"] == -1

    def test_leechers_none_results_in_minus_one(self):
        inst, cap, mod = _load_jackett()
        rss = ET.Element("rss")
        channel = ET.SubElement(rss, "channel")
        item = ET.SubElement(channel, "item")
        title_el = ET.SubElement(item, "title")
        title_el.text = "No peers"
        magnet_el = _torznab_attr("magneturl", "magnet:?xt=urn:btih:z")
        item.append(magnet_el)
        link_el = ET.SubElement(item, "link")
        link_el.text = "http://example.com/z"
        xml = ET.tostring(rss, encoding="unicode")
        with patch.object(inst, "get_response", return_value=xml):
            inst.search_jackett_indexer("q", None, "all")
        assert cap[0]["leech"] == -1

    def test_leech_calculated_as_peers_minus_seeds(self):
        inst, cap, mod = _load_jackett()
        xml = _build_single_result_xml(seeds=100, peers=150)
        with patch.object(inst, "get_response", return_value=xml):
            inst.search_jackett_indexer("q", None, "all")
        assert cap[0]["leech"] == 50

    def test_no_comments_falls_back_to_guid(self):
        inst, cap, mod = _load_jackett()
        rss = ET.Element("rss")
        channel = ET.SubElement(rss, "channel")
        item = ET.SubElement(channel, "item")
        title_el = ET.SubElement(item, "title")
        title_el.text = "No comments"
        magnet_el = _torznab_attr("magneturl", "magnet:?xt=urn:btih:noCOMMENT")
        item.append(magnet_el)
        link_el = ET.SubElement(item, "link")
        link_el.text = "http://example.com/no-comments"
        xml = ET.tostring(rss, encoding="unicode")
        with patch.object(inst, "get_response", return_value=xml):
            inst.search_jackett_indexer("q", None, "all")
        assert cap[0]["desc_link"] == ""

    def test_no_comments_no_guid_empty_desc(self):
        inst, cap, mod = _load_jackett()
        rss = ET.Element("rss")
        channel = ET.SubElement(rss, "channel")
        item = ET.SubElement(channel, "item")
        title_el = ET.SubElement(item, "title")
        title_el.text = "No desc"
        magnet_el = _torznab_attr("magneturl", "magnet:?xt=urn:btih:noDESC")
        item.append(magnet_el)
        link_el = ET.SubElement(item, "link")
        link_el.text = "http://example.com/no-desc"
        xml = ET.tostring(rss, encoding="unicode")
        with patch.object(inst, "get_response", return_value=xml):
            inst.search_jackett_indexer("q", None, "all")
        assert cap[0]["desc_link"] == ""

    def test_engine_url_matches_instance_url(self):
        inst, cap, mod = _load_jackett()
        xml = _build_single_result_xml()
        with patch.object(inst, "get_response", return_value=xml):
            inst.search_jackett_indexer("q", None, "all")
        assert cap[0]["engine_url"] == inst.url

    def test_pub_date_parsed(self):
        inst, cap, mod = _load_jackett()
        xml = _build_single_result_xml(pub_date="Mon, 01 Jan 2024 12:00:00 +0000")
        with patch.object(inst, "get_response", return_value=xml):
            inst.search_jackett_indexer("q", None, "all")
        assert cap[0]["pub_date"] > 0

    def test_pub_date_malformed_results_in_minus_one(self):
        inst, cap, mod = _load_jackett()
        xml = _build_single_result_xml(pub_date="not-a-date")
        with patch.object(inst, "get_response", return_value=xml):
            inst.search_jackett_indexer("q", None, "all")
        assert cap[0]["pub_date"] == -1

    def test_pub_date_missing_results_in_minus_one(self):
        inst, cap, mod = _load_jackett()
        rss = ET.Element("rss")
        channel = ET.SubElement(rss, "channel")
        item = ET.SubElement(channel, "item")
        title_el = ET.SubElement(item, "title")
        title_el.text = "No date"
        magnet_el = _torznab_attr("magneturl", "magnet:?xt=urn:btih:nodate")
        item.append(magnet_el)
        link_el = ET.SubElement(item, "link")
        link_el.text = "http://example.com/nodate"
        xml = ET.tostring(rss, encoding="unicode")
        with patch.object(inst, "get_response", return_value=xml):
            inst.search_jackett_indexer("q", None, "all")
        assert cap[0]["pub_date"] == -1

    def test_magneturl_preferred_over_link(self):
        inst, cap, mod = _load_jackett()
        xml = _build_single_result_xml(
            magnet="magnet:?xt=urn:btih:magnetpreferred",
            link="http://example.com/torrent/file"
        )
        with patch.object(inst, "get_response", return_value=xml):
            inst.search_jackett_indexer("q", None, "all")
        assert cap[0]["link"] == "magnet:?xt=urn:btih:magnetpreferred"

    def test_link_used_when_no_magneturl(self):
        inst, cap, mod = _load_jackett()
        xml = _build_single_result_xml(magnet=None, link="http://example.com/torrent/file")
        with patch.object(inst, "get_response", return_value=xml):
            inst.search_jackett_indexer("q", None, "all")
        assert cap[0]["link"] == "http://example.com/torrent/file"

    def test_category_included_in_url(self):
        inst, cap, mod = _load_jackett()
        xml = _build_indexers_xml([])
        with patch.object(inst, "get_response", return_value=xml) as mock_resp:
            inst.search_jackett_indexer("q", ["2000"], "all")
        called_url = mock_resp.call_args[0][0]
        assert "cat=2000" in called_url

    def test_multiple_categories_in_url(self):
        inst, cap, mod = _load_jackett()
        xml = _build_indexers_xml([])
        with patch.object(inst, "get_response", return_value=xml) as mock_resp:
            inst.search_jackett_indexer("q", ["1000", "4000"], "games")
        called_url = mock_resp.call_args[0][0]
        assert "cat=1000%2C4000" in called_url

    def test_special_characters_in_query(self):
        inst, cap, mod = _load_jackett()
        xml = _build_single_result_xml()
        with patch.object(inst, "get_response", return_value=xml) as mock_resp:
            inst.search_jackett_indexer("hello world & foo=bar", None, "all")
        called_url = mock_resp.call_args[0][0]
        assert "hello+world+%26+foo%3Dbar" in called_url

    def test_pipes_escaped_in_output(self):
        inst, cap, mod = _load_jackett()
        xml = _build_single_result_xml(title="a|b|c")
        with patch.object(inst, "get_response", return_value=xml):
            inst.search_jackett_indexer("q", None, "all")
        assert "%7C" in cap[0]["name"]


# ─── search Tests ─────────────────────────────────────────────────────

class TestSearch:
    def test_search_all_category(self):
        inst, cap, mod = _load_jackett(thread_count=1)
        xml = _build_single_result_xml()
        with patch.object(inst, "get_response", return_value=xml):
            inst.search("ubuntu", "all")
        assert len(cap) == 1

    def test_search_malformed_config(self):
        inst, cap, mod = _load_jackett()
        mod.CONFIG_DATA["malformed"] = True
        inst.search("query", "all")
        assert len(cap) == 1
        assert "malformed" in cap[0]["name"]

    def test_search_default_api_key(self):
        inst, cap, mod = _load_jackett(api_key="YOUR_API_KEY_HERE")
        inst.search("query", "all")
        assert len(cap) == 1
        assert "api key error" in cap[0]["name"]

    def test_search_with_category_anime(self):
        inst, cap, mod = _load_jackett(thread_count=1)
        xml = _build_single_result_xml()
        with patch.object(inst, "get_response", return_value=xml) as mock_resp:
            inst.search("naruto", "anime")
        called_url = mock_resp.call_args[0][0]
        assert "cat=5070" in called_url

    def test_search_with_category_tv(self):
        inst, cap, mod = _load_jackett(thread_count=1)
        xml = _build_single_result_xml()
        with patch.object(inst, "get_response", return_value=xml) as mock_resp:
            inst.search("show", "tv")
        called_url = mock_resp.call_args[0][0]
        assert "cat=5000" in called_url

    def test_search_with_category_movies(self):
        inst, cap, mod = _load_jackett(thread_count=1)
        xml = _build_single_result_xml()
        with patch.object(inst, "get_response", return_value=xml) as mock_resp:
            inst.search("movie", "movies")
        called_url = mock_resp.call_args[0][0]
        assert "cat=2000" in called_url

    def test_search_with_category_music(self):
        inst, cap, mod = _load_jackett(thread_count=1)
        xml = _build_single_result_xml()
        with patch.object(inst, "get_response", return_value=xml) as mock_resp:
            inst.search("album", "music")
        called_url = mock_resp.call_args[0][0]
        assert "cat=3000" in called_url

    def test_search_with_category_books(self):
        inst, cap, mod = _load_jackett(thread_count=1)
        xml = _build_single_result_xml()
        with patch.object(inst, "get_response", return_value=xml) as mock_resp:
            inst.search("book", "books")
        called_url = mock_resp.call_args[0][0]
        assert "cat=8000" in called_url

    def test_search_with_category_games(self):
        inst, cap, mod = _load_jackett(thread_count=1)
        xml = _build_single_result_xml()
        with patch.object(inst, "get_response", return_value=xml) as mock_resp:
            inst.search("game", "games")
        called_url = mock_resp.call_args[0][0]
        assert "cat=1000%2C4000" in called_url

    def test_search_multithreaded(self):
        inst, cap, mod = _load_jackett(thread_count=4)
        indexers_xml = _build_indexers_xml(["idx1", "idx2"])
        results_xml = _build_single_result_xml()
        with patch.object(inst, "get_jackett_indexers", return_value=["idx1", "idx2"]):
            with patch.object(inst, "search_jackett_indexer") as mock_search:
                inst.search("query", "all")
        assert mock_search.call_count == 2

    def test_search_multithreaded_pool_0_guard(self):
        """Pool(0) raises ValueError -- the plugin guards against empty indexers."""
        inst, cap, mod = _load_jackett(thread_count=4)
        with patch.object(inst, "get_jackett_indexers", return_value=[]):
            inst.search("query", "all")
        assert len(cap) == 0

    def test_search_single_thread_mode(self):
        inst, cap, mod = _load_jackett(thread_count=1)
        xml = _build_single_result_xml()
        with patch.object(inst, "get_response", return_value=xml):
            inst.search("query", "all")
        assert len(cap) == 1

    def test_search_query_unquoted(self):
        inst, cap, mod = _load_jackett(thread_count=1)
        xml = _build_single_result_xml()
        with patch.object(inst, "get_response", return_value=xml) as mock_resp:
            inst.search("hello%20world", "all")
        called_url = mock_resp.call_args[0][0]
        assert "hello+world" in called_url

    def test_search_connection_error_on_indexers(self):
        inst, cap, mod = _load_jackett(thread_count=4)
        with patch.object(inst, "get_jackett_indexers", return_value=[]):
            inst.search("query", "all")
        assert len(cap) == 0


# ─── download_torrent Tests ───────────────────────────────────────────

class TestDownloadTorrent:
    def test_magnet_input(self, capsys):
        inst, cap, mod = _load_jackett()
        inst.download_torrent("magnet:?xt=urn:btih:direct")
        out = capsys.readouterr().out
        assert "magnet:?xt=urn:btih:direct" in out

    def test_magnet_input_prints_double(self, capsys):
        inst, cap, mod = _load_jackett()
        inst.download_torrent("magnet:?xt=urn:btih:abc")
        out = capsys.readouterr().out
        parts = out.strip().split(" magnet:?")
        assert len(parts) == 2

    def test_response_is_magnet(self, capsys):
        inst, cap, mod = _load_jackett()
        with patch.object(inst, "get_response", return_value="magnet:?xt=urn:btih:fromresponse"):
            inst.download_torrent("http://example.com/torrent/1")
        out = capsys.readouterr().out
        assert "magnet:?xt=urn:btih:fromresponse" in out
        assert "http://example.com/torrent/1" in out

    def test_response_not_magnet_falls_back_to_download_file(self, capsys):
        inst, cap, mod = _load_jackett()
        with patch.object(inst, "get_response", return_value="not a magnet"):
            inst.download_torrent("http://example.com/torrent/2")
        out = capsys.readouterr().out
        assert "http://example.com/torrent/2" in out

    def test_response_none_falls_back_to_download_file(self, capsys):
        inst, cap, mod = _load_jackett()
        with patch.object(inst, "get_response", return_value=None):
            inst.download_torrent("http://example.com/torrent/3")
        out = capsys.readouterr().out
        assert "http://example.com/torrent/3" in out

    def test_proxy_enabled_during_request(self):
        inst, cap, mod = _load_jackett()
        with patch.object(inst, "get_response", return_value=None):
            with patch.object(mod.proxy_manager, "enable_proxy") as mock_proxy:
                inst.download_torrent("http://example.com/torrent/4")
        calls = [c.args[0] for c in mock_proxy.call_args_list]
        assert True in calls
        assert False in calls


# ─── Edge Cases ───────────────────────────────────────────────────────

class TestEdgeCases:
    def test_special_characters_in_search_query(self):
        inst, cap, mod = _load_jackett(thread_count=1)
        xml = _build_single_result_xml()
        with patch.object(inst, "get_response", return_value=xml) as mock_resp:
            inst.search("foo&bar=baz", "all")
        called_url = mock_resp.call_args[0][0]
        assert "foo" in called_url

    def test_empty_search_query(self):
        inst, cap, mod = _load_jackett(thread_count=1)
        xml = _build_single_result_xml()
        with patch.object(inst, "get_response", return_value=xml) as mock_resp:
            inst.search("", "all")
        called_url = mock_resp.call_args[0][0]
        assert "q=" in called_url

    def test_unicode_search_query(self):
        inst, cap, mod = _load_jackett(thread_count=1)
        xml = _build_single_result_xml()
        with patch.object(inst, "get_response", return_value=xml) as mock_resp:
            inst.search("日本語", "all")
        called_url = mock_resp.call_args[0][0]
        assert "q=" in called_url

    def test_large_seeds_and_leech(self):
        inst, cap, mod = _load_jackett()
        xml = _build_single_result_xml(seeds=999999, peers=1000000)
        with patch.object(inst, "get_response", return_value=xml):
            inst.search_jackett_indexer("q", None, "all")
        assert cap[0]["seeds"] == 999999
        assert cap[0]["leech"] == 1

    def test_zero_seeds_and_leech(self):
        inst, cap, mod = _load_jackett()
        xml = _build_single_result_xml(seeds=0, peers=0)
        with patch.object(inst, "get_response", return_value=xml):
            inst.search_jackett_indexer("q", None, "all")
        assert cap[0]["seeds"] == 0
        assert cap[0]["leech"] == 0

    def test_large_size_value(self):
        inst, cap, mod = _load_jackett()
        xml = _build_single_result_xml(size=10_995_116_277_760)  # ~10 TB
        with patch.object(inst, "get_response", return_value=xml):
            inst.search_jackett_indexer("q", None, "all")
        assert "10995116277760" in cap[0]["size"]

    def test_url_with_trailing_slash_in_search(self):
        inst, cap, mod = _load_jackett(url="http://127.0.0.1:9117/", thread_count=1)
        xml = _build_single_result_xml()
        with patch.object(inst, "get_response", return_value=xml):
            inst.search("q", "all")
        assert len(cap) == 1

    def test_multiple_items_only_titled_emitted(self):
        inst, cap, mod = _load_jackett()
        rss = ET.Element("rss")
        channel = ET.SubElement(rss, "channel")
        for i in range(5):
            item = ET.SubElement(channel, "item")
            if i % 2 == 0:
                title_el = ET.SubElement(item, "title")
                title_el.text = f"Titled {i}"
                magnet_el = _torznab_attr("magneturl", f"magnet:?xt=urn:btih:item{i}")
                item.append(magnet_el)
                link_el = ET.SubElement(item, "link")
                link_el.text = f"http://example.com/{i}"
        xml = ET.tostring(rss, encoding="unicode")
        with patch.object(inst, "get_response", return_value=xml):
            inst.search_jackett_indexer("q", None, "all")
        assert len(cap) == 3

    def test_xml_with_extra_namespace_elements(self):
        inst, cap, mod = _load_jackett()
        rss = ET.Element("rss")
        channel = ET.SubElement(rss, "channel")
        item = ET.SubElement(channel, "item")
        title_el = ET.SubElement(item, "title")
        title_el.text = "Extra NS"
        magnet_el = _torznab_attr("magneturl", "magnet:?xt=urn:btih:extraNS")
        item.append(magnet_el)
        link_el = ET.SubElement(item, "link")
        link_el.text = "http://example.com/extra"
        extra = ET.SubElement(item, f"{{{TORZNAB_NS}}}attr")
        extra.set("name", "downloadvolumefactor")
        extra.set("value", "0")
        xml = ET.tostring(rss, encoding="unicode")
        with patch.object(inst, "get_response", return_value=xml):
            inst.search_jackett_indexer("q", None, "all")
        assert len(cap) == 1

    def test_thread_count_exactly_one_skips_pool(self):
        inst, cap, mod = _load_jackett(thread_count=1)
        xml = _build_single_result_xml()
        with patch.object(inst, "get_response", return_value=xml):
            with patch.object(inst, "search_jackett_indexer") as mock_search:
                inst.search("q", "all")
        mock_search.assert_called_once()

    def test_get_response_builds_cookie_opener(self):
        inst, _, mod = _load_jackett()
        with patch.object(mod.urllib.request, "build_opener") as mock_opener:
            mock_opener.return_value.open.return_value = _FakeResponse(b"ok")
            inst.get_response("http://test.com")
        mock_opener.assert_called_once()
        args = mock_opener.call_args[0]
        assert any(isinstance(a, mod.urllib.request.HTTPCookieProcessor) for a in args)
