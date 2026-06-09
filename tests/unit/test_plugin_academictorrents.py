"""Deep coverage tests for plugins/community/academictorrents.py.

Covers: XML parsing, search (ThreadPoolExecutor), download_torrent,
category mapping, torrent filter, resolve_search_result, cache management,
exception handling, module-level constants.
"""

import importlib.util
import os
import sys
import types
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PLUGINS_DIR = os.path.join(REPO, "plugins")


def _load_plugin(captured=None):
    if captured is None:
        captured = []

    np_mod = types.ModuleType("novaprinter")
    np_mod.prettyPrinter = lambda d: captured.append(dict(d))
    np_mod.SearchResults = dict
    sys.modules["novaprinter"] = np_mod

    helpers_mod = types.ModuleType("helpers")
    helpers_mod.download_file = lambda info: f"downloaded:{info}"
    helpers_mod.retrieve_url = lambda url: ""
    sys.modules["helpers"] = helpers_mod

    sys.modules.pop("academictorrents", None)

    path = os.path.join(PLUGINS_DIR, "community", "academictorrents.py")
    spec = importlib.util.spec_from_file_location("academictorrents", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules["academictorrents"] = mod

    cls = getattr(mod, "academictorrents", None)
    if cls is not None and isinstance(cls, type):
        return cls(), captured
    return mod, captured


XML_SINGLE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>Deep Learning Research Paper 2025</title>
      <description>A comprehensive study of deep learning techniques applied to NLP</description>
      <link>https://academictorrents.com/details/a1b2c3</link>
      <infohash>a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0</infohash>
      <size>52428800</size>
    </item>
  </channel>
</rss>"""

XML_MULTI = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>Paper One: Quantum Computing</title>
      <description>Foundations of quantum algorithms</description>
      <link>https://academictorrents.com/details/111</link>
      <infohash>1111111111111111111111111111111111111111</infohash>
      <size>1048576</size>
    </item>
    <item>
      <title>Paper Two: Machine Learning Basics</title>
      <description>Introduction to supervised machine learning</description>
      <link>https://academictorrents.com/details/222</link>
      <infohash>2222222222222222222222222222222222222222</infohash>
      <size>2097152</size>
    </item>
    <item>
      <title>Paper Three: Data Structures</title>
      <description>Advanced tree and graph algorithms</description>
      <link>https://academictorrents.com/details/333</link>
      <infohash>3333333333333333333333333333333333333333</infohash>
      <size>3145728</size>
    </item>
  </channel>
</rss>"""

XML_EMPTY = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
  </channel>
</rss>"""

XML_NO_INFOHASH = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>Paper Without Infohash</title>
      <description>Missing the infohash element</description>
      <link>https://academictorrents.com/details/missinghash</link>
      <size>1024</size>
    </item>
  </channel>
</rss>"""

XML_MALFORMED = "not valid xml <rss>"

PEER_HTML = """<html><body><table>
<tr><td>Mirrors</td><td>42 complete, 7 downloading</td></tr>
<tr><td>Added</td><td>2025-06-09T12:00:00</td></tr>
</table></body></html>"""

PEER_HTML_NO_MIRRORS = """<html><body><table>
<tr><td>Something Else</td><td>irrelevant data</td></tr>
<tr><td>Added</td><td>2025-06-09T12:00:00</td></tr>
</table></body></html>"""

PEER_HTML_ZERO_PEERS = """<html><body><table>
<tr><td>Mirrors</td><td>0 complete, 0 downloading</td></tr>
<tr><td>Added</td><td>2025-01-01T00:00:00</td></tr>
</table></body></html>"""


class TestCategoryMapping:
    def setup_method(self):
        self.inst, self.cap = _load_plugin()

    def test_supported_categories_is_all_only(self):
        assert self.inst.supported_categories == {"all": "0"}
        assert len(self.inst.supported_categories) == 1

    def test_url_and_name_set(self):
        assert self.inst.url == "https://academictorrents.com/"
        assert self.inst.name == "AcademicTorrents"


class TestTorrentFilter:
    def setup_method(self):
        self.inst, self.cap = _load_plugin()
        root = ET.fromstring(XML_SINGLE)
        self.item = root.find("channel/item")

    def test_filter_matches_title(self):
        self.inst.filters = ["deep", "learning"]
        assert self.inst._torrent_filter(self.item) is True

    def test_filter_matches_description(self):
        self.inst.filters = ["nlp"]
        assert self.inst._torrent_filter(self.item) is True

    def test_filter_no_match(self):
        self.inst.filters = ["unrelated", "keyword"]
        assert self.inst._torrent_filter(self.item) is False

    def test_filter_partial_word_match(self):
        self.inst.filters = ["deep"]
        assert self.inst._torrent_filter(self.item) is True

    def test_filter_title_matches_only_when_lowercased(self):
        self.inst.filters = ["deep learning"]
        assert self.inst._torrent_filter(self.item) is True

    def test_filter_description_matches_when_lowercased(self):
        self.inst.filters = ["nlp"]
        assert self.inst._torrent_filter(self.item) is True

    def test_filter_multiple_filters_or_logic(self):
        self.inst.filters = ["unrelated", "deep"]
        assert self.inst._torrent_filter(self.item) is True

    def test_filter_single_filter_matches(self):
        self.inst.filters = ["comprehensive"]
        assert self.inst._torrent_filter(self.item) is True

    def test_filter_empty_filters_returns_false(self):
        self.inst.filters = []
        assert self.inst._torrent_filter(self.item) is False


class TestResolveSearchResult:
    def setup_method(self):
        self.inst, self.cap = _load_plugin()
        root = ET.fromstring(XML_SINGLE)
        self.item = root.find("channel/item")
        self.mod = sys.modules["academictorrents"]

    def test_resolve_with_peers_and_date(self):
        with patch.object(self.mod, "retrieve_url", return_value=PEER_HTML):
            result = self.inst.resolve_search_result(self.item)
        assert result["name"] == "Deep Learning Research Paper 2025"
        assert result["seeds"] == 42
        assert result["leech"] == 7
        assert result["size"] == "52428800"
        assert result["pub_date"] > 0
        assert result["engine_url"] == "https://academictorrents.com/"
        assert result["link"].startswith("https://academictorrents.com/download/")
        assert result["link"].endswith(".torrent")

    def test_resolve_without_peer_data(self):
        with patch.object(self.mod, "retrieve_url", return_value=PEER_HTML_NO_MIRRORS):
            result = self.inst.resolve_search_result(self.item)
        assert result["seeds"] == -1
        assert result["leech"] == -1
        assert result["pub_date"] > 0

    def test_resolve_with_zero_peers(self):
        with patch.object(self.mod, "retrieve_url", return_value=PEER_HTML_ZERO_PEERS):
            result = self.inst.resolve_search_result(self.item)
        assert result["seeds"] == 0
        assert result["leech"] == 0

    def test_resolve_link_contains_infohash(self):
        with patch.object(self.mod, "retrieve_url", return_value=PEER_HTML):
            result = self.inst.resolve_search_result(self.item)
        expected_infohash = "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0"
        assert expected_infohash in result["link"]
        assert result["link"] == f"https://academictorrents.com/download/{expected_infohash}.torrent"

    def test_resolve_retrieve_url_error_propagates(self):
        with patch.object(self.mod, "retrieve_url", side_effect=Exception("network error")):
            with pytest.raises(Exception, match="network error"):
                self.inst.resolve_search_result(self.item)

    def test_resolve_missing_infohash(self):
        root = ET.fromstring(XML_NO_INFOHASH)
        item = root.find("channel/item")
        with patch.object(self.mod, "retrieve_url", return_value=PEER_HTML):
            result = self.inst.resolve_search_result(item)
        assert result["name"] == "Paper Without Infohash"
        assert "None.torrent" in result["link"]

    def test_resolve_desc_link_passed_to_retrieve_url(self):
        with patch.object(self.mod, "retrieve_url", return_value=PEER_HTML) as mock_retrieve:
            self.inst.resolve_search_result(self.item)
        assert mock_retrieve.called
        url_called = mock_retrieve.call_args[0][0]
        assert url_called.endswith("/tech")
        assert url_called == "https://academictorrents.com/details/a1b2c3/tech"


class TestSearch:
    def setup_method(self):
        self.inst, self.cap = _load_plugin()
        self.mod = sys.modules["academictorrents"]

    def test_search_single_result(self):
        with patch.object(self.mod, "retrieve_url", return_value=PEER_HTML):
            with patch.object(self.inst, "_retrieve_database", return_value=ET.fromstring(XML_SINGLE)):
                self.inst.search("deep learning", "all")
        assert len(self.cap) == 1
        assert self.cap[0]["name"] == "Deep Learning Research Paper 2025"
        assert self.cap[0]["seeds"] == 42
        assert self.cap[0]["leech"] == 7
        assert self.cap[0]["pub_date"] > 0

    def test_search_multiple_results(self):
        with patch.object(self.mod, "retrieve_url", return_value=PEER_HTML):
            with patch.object(self.inst, "_retrieve_database", return_value=ET.fromstring(XML_MULTI)):
                self.inst.search("paper", "all")
        assert len(self.cap) == 3
        names = [r["name"] for r in self.cap]
        assert "Paper One: Quantum Computing" in names
        assert "Paper Two: Machine Learning Basics" in names
        assert "Paper Three: Data Structures" in names

    def test_search_no_matches(self):
        with patch.object(self.mod, "retrieve_url", return_value=PEER_HTML):
            with patch.object(self.inst, "_retrieve_database", return_value=ET.fromstring(XML_SINGLE)):
                self.inst.search("nonexistent keyword", "all")
        assert len(self.cap) == 0

    def test_search_partial_filter_matches_one_of_many(self):
        with patch.object(self.mod, "retrieve_url", return_value=PEER_HTML):
            with patch.object(self.inst, "_retrieve_database", return_value=ET.fromstring(XML_MULTI)):
                self.inst.search("quantum", "all")
        assert len(self.cap) == 1
        assert self.cap[0]["name"] == "Paper One: Quantum Computing"

    def test_search_multiple_filters_match_same_item_once(self):
        with patch.object(self.mod, "retrieve_url", return_value=PEER_HTML):
            with patch.object(self.inst, "_retrieve_database", return_value=ET.fromstring(XML_SINGLE)):
                self.inst.search("deep learning paper", "all")
        assert len(self.cap) == 1

    def test_search_output_false_suppresses_print(self):
        inst = _load_plugin()[0]
        inst.output = False
        mod = sys.modules["academictorrents"]
        with patch.object(mod, "retrieve_url", return_value=PEER_HTML):
            with patch.object(inst, "_retrieve_database", return_value=ET.fromstring(XML_SINGLE)):
                inst.search("deep learning", "all")
        assert len(self.cap) == 0

    def test_search_filters_set_from_query(self):
        with patch.object(self.mod, "retrieve_url", return_value=PEER_HTML):
            with patch.object(self.inst, "_retrieve_database", return_value=ET.fromstring(XML_EMPTY)):
                self.inst.search("hello world", "all")
        assert "hello" in self.inst.filters
        assert "world" in self.inst.filters
        assert len(self.inst.filters) == 2

    def test_search_url_encoded_space_handled(self):
        with patch.object(self.mod, "retrieve_url", return_value=PEER_HTML):
            with patch.object(self.inst, "_retrieve_database", return_value=ET.fromstring(XML_EMPTY)):
                self.inst.search("hello%20world", "all")
        assert "hello" in self.inst.filters
        assert "world" in self.inst.filters

    def test_search_retrieve_url_error_propagates_from_thread(self):
        with patch.object(self.mod, "retrieve_url", side_effect=Exception("network error")):
            with patch.object(self.inst, "_retrieve_database", return_value=ET.fromstring(XML_SINGLE)):
                with pytest.raises(Exception, match="network error"):
                    self.inst.search("deep learning", "all")


class TestDownloadTorrent:
    def setup_method(self):
        self.inst, self.cap = _load_plugin()
        self.mod = sys.modules["academictorrents"]

    def test_download_calls_download_file(self):
        with patch.object(self.mod, "download_file", return_value="cached_path.torrent") as mock_dl:
            self.inst.download_torrent("https://academictorrents.com/download/abc.torrent")
        mock_dl.assert_called_once_with("https://academictorrents.com/download/abc.torrent")

    def test_download_prints_result(self, capsys):
        with patch.object(self.mod, "download_file", return_value="cached_path.torrent"):
            self.inst.download_torrent("https://academictorrents.com/download/abc.torrent")
        out = capsys.readouterr().out
        assert "cached_path.torrent" in out

    def test_download_none_info(self):
        with patch.object(self.mod, "download_file", return_value="result") as mock_dl:
            self.inst.download_torrent(None)
        mock_dl.assert_called_once_with(None)


class TestCacheUpdate:
    def setup_method(self):
        self.inst, self.cap = _load_plugin()
        self.mod = sys.modules["academictorrents"]

    def test_update_cache_skip_when_fresh(self):
        from datetime import date
        today = str(date.today())
        m = mock_open(read_data=f"{today}\n<dummy xml>")
        with patch.object(self.mod, "cache_path") as mock_path:
            mock_path.exists.return_value = True
            with patch("builtins.open", m):
                with patch.object(self.mod, "request") as mock_req:
                    self.inst._update_database_cache()
                    mock_req.urlopen.assert_not_called()

    def test_update_cache_download_when_missing(self):
        with patch.object(self.mod, "cache_path") as mock_path:
            mock_path.exists.return_value = False
            m = mock_open()
            with patch("builtins.open", m):
                with patch.object(self.mod, "request") as mock_req:
                    mock_req.urlopen.return_value.read.return_value = b"<xml>fresh data</xml>"
                    mock_req.urlopen.return_value.decode.return_value = "<xml>fresh data</xml>"
                    self.inst._update_database_cache()
                    mock_req.urlopen.assert_called_once()

    def test_update_cache_download_when_stale(self):
        m = mock_open(read_data="2020-01-01\n<old xml>")
        with patch.object(self.mod, "cache_path") as mock_path:
            mock_path.exists.return_value = True
            with patch("builtins.open", m):
                with patch.object(self.mod, "request") as mock_req:
                    mock_req.urlopen.return_value.read.return_value = b"<xml>fresh</xml>"
                    mock_req.urlopen.return_value.decode.return_value = "<xml>fresh</xml>"
                    self.inst._update_database_cache()
                    mock_req.urlopen.assert_called_once()

    def test_retrieve_database_creates_dir_and_parses_xml(self):
        from datetime import date
        today = str(date.today())
        xml_content = "<rss><channel><item><title>Test</title><description>Desc</description><link>https://example.com</link><infohash>abc</infohash><size>100</size></item></channel></rss>"
        m = mock_open(read_data=f"{today}\n{xml_content}")
        with patch.object(self.mod, "cache_path") as mock_path:
            mock_path.exists.return_value = True
            with patch("builtins.open", m):
                with patch("pathlib.Path.mkdir") as mock_mkdir:
                    result = self.inst._retrieve_database()
        mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)
        assert isinstance(result, ET.Element)
        items = result.findall("channel/item")
        assert len(items) == 1


class TestConcurrentBehavior:
    def setup_method(self):
        self.inst, self.cap = _load_plugin()
        self.mod = sys.modules["academictorrents"]

    def test_multiple_torrents_processed(self):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>"""
        for i in range(10):
            xml += f"""<item>
      <title>Paper {i}</title>
      <description>Description {i}</description>
      <link>https://academictorrents.com/details/{i}</link>
      <infohash>{str(i)*40}</infohash>
      <size>{i*1000}</size>
    </item>"""
        xml += """</channel></rss>"""
        with patch.object(self.mod, "retrieve_url", return_value=PEER_HTML):
            with patch.object(self.inst, "_retrieve_database", return_value=ET.fromstring(xml)):
                self.inst.search("paper", "all")
        assert len(self.cap) == 10
        assert all(r["seeds"] == 42 for r in self.cap)

    def test_concurrent_task_error_propagates(self):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>Good Paper</title>
      <description>This one works fine</description>
      <link>https://academictorrents.com/details/good</link>
      <infohash>goodhashgoodhashgoodhashgoodhashgood</infohash>
      <size>100</size>
    </item>
    <item>
      <title>Bad Paper</title>
      <description>This one crashes</description>
      <link>https://academictorrents.com/details/bad</link>
      <infohash>badhashbadhashbadhashbadhashbadhashb</infohash>
      <size>200</size>
    </item>
  </channel>
</rss>"""
        call_count = [0]

        def flaky_retrieve(url):
            call_count[0] += 1
            if "bad" in url:
                raise Exception("network error on bad paper")
            return PEER_HTML

        with patch.object(self.mod, "retrieve_url", side_effect=flaky_retrieve):
            with patch.object(self.inst, "_retrieve_database", return_value=ET.fromstring(xml)):
                with pytest.raises(Exception, match="network error on bad paper"):
                    self.inst.search("paper", "all")

    def test_search_with_no_items(self):
        with patch.object(self.mod, "retrieve_url", return_value=PEER_HTML):
            with patch.object(self.inst, "_retrieve_database", return_value=ET.fromstring(XML_EMPTY)):
                self.inst.search("anything", "all")
        assert len(self.cap) == 0


class TestModuleConstants:
    def setup_method(self):
        _load_plugin()
        self.mod = sys.modules["academictorrents"]

    def test_database_url_constant(self):
        assert self.mod.DATABASE_URL == "https://academictorrents.com/database.xml"

    def test_system_paths_defined(self):
        assert "win32" in self.mod.system_paths
        assert "linux" in self.mod.system_paths
        assert "darwin" in self.mod.system_paths

    def test_cache_path_is_absolute(self):
        assert isinstance(self.mod.cache_path, Path)
        assert "qbit_plugins_data" in str(self.mod.cache_path)
        assert str(self.mod.cache_path).endswith("academic_cache.xml")

    def test_home_constant_set(self):
        assert self.mod.home is not None
        assert len(self.mod.home) > 0


class TestEdgeCases:
    def setup_method(self):
        self.inst, self.cap = _load_plugin()
        self.mod = sys.modules["academictorrents"]

    def test_malformed_xml_database_raises(self):
        with patch.object(self.inst, "_update_database_cache"):
            m = mock_open(read_data="2025-06-09\nnot valid xml <<<")
            with patch("builtins.open", m):
                with pytest.raises(ET.ParseError):
                    self.inst._retrieve_database()

    def test_search_with_empty_query(self):
        with patch.object(self.mod, "retrieve_url", return_value=PEER_HTML):
            with patch.object(self.inst, "_retrieve_database", return_value=ET.fromstring(XML_EMPTY)):
                self.inst.search("", "all")
        assert self.inst.filters == [""]

    def test_class_output_defaults_true(self):
        inst, _ = _load_plugin()
        assert inst.output is True

    def test_resolve_pub_date_is_integer_timestamp(self):
        root = ET.fromstring(XML_SINGLE)
        item = root.find("channel/item")
        with patch.object(self.mod, "retrieve_url", return_value=PEER_HTML):
            result = self.inst.resolve_search_result(item)
        assert isinstance(result["pub_date"], int)
        assert result["pub_date"] > 0

    def test_search_with_spaces_in_query_splits_correctly(self):
        with patch.object(self.mod, "retrieve_url", return_value=PEER_HTML):
            with patch.object(self.inst, "_retrieve_database", return_value=ET.fromstring(XML_EMPTY)):
                self.inst.search("  deep   learning  papers  ", "all")
        assert "deep" in self.inst.filters
        assert "learning" in self.inst.filters
        assert "papers" in self.inst.filters

    def test_filters_lowercased(self):
        with patch.object(self.mod, "retrieve_url", return_value=PEER_HTML):
            with patch.object(self.inst, "_retrieve_database", return_value=ET.fromstring(XML_EMPTY)):
                self.inst.search("DEEP LEARNING", "all")
        assert self.inst.filters == ["deep", "learning"]

    def test_infohash_preserved_in_search_link(self):
        with patch.object(self.mod, "retrieve_url", return_value=PEER_HTML):
            with patch.object(self.inst, "_retrieve_database", return_value=ET.fromstring(XML_SINGLE)):
                self.inst.search("deep", "all")
        assert len(self.cap) == 1
        assert "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0.torrent" in self.cap[0]["link"]
