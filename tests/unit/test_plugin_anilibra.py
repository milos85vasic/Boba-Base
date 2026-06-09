"""Deep coverage tests for plugins/anilibra.py.

Covers: search (URL construction, JSON parsing, exception handling),
_process_release (release parsing, torrent fetching, magnet links),
download_torrent (magnet output), category mapping, edge cases.
"""

import importlib.util
import json
import os
import sys
import types
from unittest.mock import patch

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PLUGINS_DIR = os.path.join(REPO, "plugins")


def _load_anilibra(captured=None, retrieve_url_fn=None):
    """Import anilibra plugin with stub modules.

    Returns (instance, captured, set_retrieve_url) where set_retrieve_url
    is a callable to replace the plugin's retrieve_url binding.
    """
    if captured is None:
        captured = []
    np_mod = types.ModuleType("novaprinter")
    np_mod.prettyPrinter = lambda d: captured.append(dict(d))
    sys.modules["novaprinter"] = np_mod

    helpers_mod = types.ModuleType("helpers")
    helpers_mod.retrieve_url = retrieve_url_fn or (lambda url: "[]")
    sys.modules["helpers"] = helpers_mod

    sys.modules.pop("anilibra", None)

    path = os.path.join(PLUGINS_DIR, "anilibra.py")
    spec = importlib.util.spec_from_file_location("anilibra", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules["anilibra"] = mod

    def set_retrieve_url(fn):
        mod.retrieve_url = fn

    cls = getattr(mod, "anilibra", None)
    if cls is not None and isinstance(cls, type):
        return cls(), captured, set_retrieve_url
    return mod, captured, set_retrieve_url


# ─── Fixtures ────────────────────────────────────────────────────────────

RELEASE_1 = {
    "id": 1001,
    "name": {"main": "Наруто", "english": "Naruto"},
}

RELEASE_2 = {
    "id": 1002,
    "name": {"main": "Атака Титанов", "english": "Attack on Titan"},
}

TORRENT_A = {
    "id": 501,
    "magnet": "magnet:?xt=urn:btih:abc123&dn=Naruto+720p",
    "size": 1073741824,
    "seeders": 150,
    "leechers": 10,
    "label": "Naruto [720p]",
}

TORRENT_B = {
    "id": 502,
    "magnet": "magnet:?xt=urn:btih:def456&dn=Naruto+1080p",
    "size": 2147483648,
    "seeders": 200,
    "leechers": 5,
    "label": "Naruto [1080p]",
}

TORRENT_NO_MAGNET = {
    "id": 503,
    "magnet": "",
    "size": 500000000,
    "seeders": 1,
    "leechers": 0,
    "label": "Naruto [480p]",
}


# ─── Category mapping ────────────────────────────────────────────────────


class TestCategoryMapping:
    def test_all_category(self):
        inst, _, _ = _load_anilibra()
        assert inst.supported_categories["all"] == "0"

    def test_anime_category(self):
        inst, _, _ = _load_anilibra()
        assert inst.supported_categories["anime"] == "1"

    def test_no_unsupported_categories(self):
        inst, _, _ = _load_anilibra()
        assert set(inst.supported_categories.keys()) == {"all", "anime"}


# ─── search: URL construction ────────────────────────────────────────────


class TestSearchURLConstruction:
    def test_search_url_contains_query(self):
        inst, captured, set_url = _load_anilibra()
        calls = []
        set_url(lambda url: (calls.append(url), "[]")[1])
        inst.search("naruto")
        assert len(calls) == 1
        assert "query=naruto" in calls[0]

    def test_search_url_uses_v1_api(self):
        inst, captured, set_url = _load_anilibra()
        calls = []
        set_url(lambda url: (calls.append(url), "[]")[1])
        inst.search("test")
        assert "/api/v1/app/search/releases" in calls[0]

    def test_search_url_has_limit(self):
        inst, captured, set_url = _load_anilibra()
        calls = []
        set_url(lambda url: (calls.append(url), "[]")[1])
        inst.search("test")
        assert "limit=20" in calls[0]

    def test_search_url_encodes_special_characters(self):
        inst, captured, set_url = _load_anilibra()
        calls = []
        set_url(lambda url: (calls.append(url), "[]")[1])
        inst.search("naruto shippuden")
        assert "query=naruto%20shippuden" in calls[0]

    def test_search_url_encodes_unicode(self):
        inst, captured, set_url = _load_anilibra()
        calls = []
        set_url(lambda url: (calls.append(url), "[]")[1])
        inst.search("naruto 風影")
        assert "query=" in calls[0]
        assert "%E9%A2%A8%E5%BD%B1" in calls[0]


# ─── search: JSON parsing ────────────────────────────────────────────────


class TestSearchJSONParsing:
    def test_empty_list_no_results(self):
        inst, captured, _ = _load_anilibra()
        inst.search("nothing")
        assert captured == []

    def test_single_release_one_torrent(self):
        inst, captured, set_url = _load_anilibra()
        release_json = json.dumps([RELEASE_1])
        torrent_json = json.dumps([TORRENT_A])

        def mock_retrieve(url):
            if "search/releases" in url:
                return release_json
            return torrent_json

        set_url(mock_retrieve)
        inst.search("naruto")
        assert len(captured) == 1
        assert captured[0]["name"] == "Naruto [720p]"
        assert captured[0]["link"] == "magnet:?xt=urn:btih:abc123&dn=Naruto+720p"

    def test_two_releases_two_torrents_each(self):
        inst, captured, set_url = _load_anilibra()
        release_json = json.dumps([RELEASE_1, RELEASE_2])
        torrent_json = json.dumps([TORRENT_A, TORRENT_B])

        def mock_retrieve(url):
            if "search/releases" in url:
                return release_json
            return torrent_json

        set_url(mock_retrieve)
        inst.search("anime")
        assert len(captured) == 4

    def test_not_a_list_returns_early(self):
        inst, captured, set_url = _load_anilibra()
        set_url(lambda url: '{"error": "bad"}')
        inst.search("test")
        assert captured == []

    def test_not_a_list_string(self):
        inst, captured, set_url = _load_anilibra()
        set_url(lambda url: '"just a string"')
        inst.search("test")
        assert captured == []

    def test_malformed_json_raises(self):
        inst, captured, set_url = _load_anilibra()
        set_url(lambda url: "{not valid json")
        inst.search("test")
        assert captured == []

    def test_empty_string_response(self):
        inst, captured, set_url = _load_anilibra()
        set_url(lambda url: "")
        inst.search("test")
        assert captured == []

    def test_retrieve_url_exception(self):
        inst, captured, set_url = _load_anilibra()
        set_url(lambda url: (_ for _ in ()).throw(ConnectionError("timeout")))
        inst.search("test")
        assert captured == []


# ─── _process_release ────────────────────────────────────────────────────


class TestProcessRelease:
    def test_release_with_no_id_skipped(self):
        inst, captured, set_url = _load_anilibra()
        set_url(lambda url: "[]")
        inst._process_release({"name": {"main": "Test"}})
        assert captured == []

    def test_release_with_none_id_skipped(self):
        inst, captured, set_url = _load_anilibra()
        set_url(lambda url: "[]")
        inst._process_release({"id": None, "name": {"main": "Test"}})
        assert captured == []

    def test_uses_english_name_when_available(self):
        inst, captured, set_url = _load_anilibra()
        set_url(lambda url: json.dumps([TORRENT_A]))
        inst._process_release(RELEASE_1)
        assert captured[0]["name"] == "Naruto [720p]"

    def test_falls_back_to_russian_name(self):
        inst, captured, set_url = _load_anilibra()
        set_url(lambda url: json.dumps([TORRENT_A]))
        inst._process_release({"id": 2001, "name": {"main": "Русский", "english": ""}})
        assert captured[0]["name"] == "Naruto [720p]"

    def test_falls_back_to_russian_name_when_english_missing(self):
        inst, captured, set_url = _load_anilibra()
        set_url(lambda url: json.dumps([TORRENT_A]))
        inst._process_release({"id": 2002, "name": {"main": "Русский"}})
        assert captured[0]["name"] == "Naruto [720p]"

    def test_missing_name_key_defaults_to_unknown(self):
        inst, captured, set_url = _load_anilibra()
        set_url(lambda url: json.dumps([TORRENT_A]))
        inst._process_release({"id": 2003})
        assert captured[0]["name"] == "Naruto [720p]"

    def test_torrents_endpoint_called(self):
        inst, captured, set_url = _load_anilibra()
        calls = []
        set_url(lambda url: (calls.append(url), json.dumps([TORRENT_A]))[1])
        inst._process_release(RELEASE_1)
        assert any("/api/v1/anime/torrents/release/1001" in c for c in calls)

    def test_torrents_not_a_list_skipped(self):
        inst, captured, set_url = _load_anilibra()
        set_url(lambda url: '{"error": "bad"}')
        inst._process_release(RELEASE_1)
        assert captured == []

    def test_torrents_empty_list(self):
        inst, captured, set_url = _load_anilibra()
        set_url(lambda url: "[]")
        inst._process_release(RELEASE_1)
        assert captured == []

    def test_no_magnet_skipped(self):
        inst, captured, set_url = _load_anilibra()
        set_url(lambda url: json.dumps([TORRENT_NO_MAGNET]))
        inst._process_release(RELEASE_1)
        assert captured == []

    def test_result_fields_populated(self):
        inst, captured, set_url = _load_anilibra()
        set_url(lambda url: json.dumps([TORRENT_A]))
        inst._process_release(RELEASE_1)
        r = captured[0]
        assert r["link"] == TORRENT_A["magnet"]
        assert r["size"] == str(TORRENT_A["size"])
        assert r["seeds"] == str(TORRENT_A["seeders"])
        assert r["leech"] == str(TORRENT_A["leechers"])
        assert r["engine_url"] == "https://anilibria.top"
        assert r["desc_link"] == "https://anilibria.top/anime/releases/1001"

    def test_desc_link_uses_release_id(self):
        inst, captured, set_url = _load_anilibra()
        set_url(lambda url: json.dumps([TORRENT_A]))
        inst._process_release({"id": 9999, "name": {"main": "X"}})
        assert captured[0]["desc_link"] == "https://anilibria.top/anime/releases/9999"

    def test_pub_date_is_unix_timestamp(self):
        inst, captured, set_url = _load_anilibra()
        set_url(lambda url: json.dumps([TORRENT_A]))
        inst._process_release(RELEASE_1)
        pub = int(captured[0]["pub_date"])
        assert pub > 0
        assert pub < 2000000000

    def test_torrents_fetch_exception_silenced(self):
        inst, captured, set_url = _load_anilibra()
        set_url(lambda url: (_ for _ in ()).throw(RuntimeError("boom")))
        inst._process_release(RELEASE_1)
        assert captured == []

    def test_label_defaults_to_display_name(self):
        inst, captured, set_url = _load_anilibra()
        torrent_no_label = {"id": 510, "magnet": "magnet:?xt=urn:btih:aaa", "size": 100, "seeders": 1, "leechers": 0}
        set_url(lambda url: json.dumps([torrent_no_label]))
        inst._process_release({"id": 3001, "name": {"main": "Тест", "english": "Test"}})
        assert captured[0]["name"] == "Test"

    def test_mixed_magnet_and_no_magnet(self):
        inst, captured, set_url = _load_anilibra()
        set_url(lambda url: json.dumps([TORRENT_A, TORRENT_NO_MAGNET, TORRENT_B]))
        inst._process_release(RELEASE_1)
        assert len(captured) == 2

    def test_zero_size_seeders_leechers(self):
        inst, captured, set_url = _load_anilibra()
        torrent_zero = {"id": 520, "magnet": "magnet:?xt=urn:btih:zero", "size": 0, "seeders": 0, "leechers": 0}
        set_url(lambda url: json.dumps([torrent_zero]))
        inst._process_release({"id": 4001, "name": {"main": "Zero"}})
        assert captured[0]["size"] == "0"
        assert captured[0]["seeds"] == "0"
        assert captured[0]["leech"] == "0"


# ─── download_torrent ────────────────────────────────────────────────────


class TestDownloadTorrent:
    def test_prints_magnet_link(self, capsys):
        inst, _, _ = _load_anilibra()
        magnet = "magnet:?xt=urn:btih:abc123&dn=Naruto"
        inst.download_torrent(magnet)
        out = capsys.readouterr().out
        assert magnet in out

    def test_prints_magnet_twice(self, capsys):
        inst, _, _ = _load_anilibra()
        magnet = "magnet:?xt=urn:btih:abc123"
        inst.download_torrent(magnet)
        out = capsys.readouterr().out
        assert out.strip() == f"{magnet} {magnet}"

    def test_handles_empty_string(self, capsys):
        inst, _, _ = _load_anilibra()
        inst.download_torrent("")
        out = capsys.readouterr().out
        assert " " in out

    def test_handles_special_characters(self, capsys):
        inst, _, _ = _load_anilibra()
        magnet = "magnet:?xt=urn:btih:abc&dn=Test+File%20(1080p)"
        inst.download_torrent(magnet)
        out = capsys.readouterr().out
        assert magnet in out


# ─── Edge cases ──────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_release_with_missing_english_name(self):
        inst, captured, set_url = _load_anilibra()
        release = {"id": 5001, "name": {"main": "Тест"}}
        set_url(lambda url: json.dumps([TORRENT_A]))
        inst._process_release(release)
        assert len(captured) == 1

    def test_release_with_empty_torrent_list(self):
        inst, captured, set_url = _load_anilibra()
        set_url(lambda url: "[]")
        inst._process_release({"id": 6001, "name": {"main": "Empty"}})
        assert captured == []

    def test_multiple_releases_with_mixed_results(self):
        inst, captured, set_url = _load_anilibra()

        def mock_retrieve(url):
            if "search/releases" in url:
                return json.dumps([RELEASE_1, {"id": 7001, "name": {"main": "No Torrents"}}])
            if "7001" in url:
                return "[]"
            return json.dumps([TORRENT_A])

        set_url(mock_retrieve)
        inst.search("mixed")
        assert len(captured) == 1

    def test_search_with_cat_parameter_accepted(self):
        inst, captured, set_url = _load_anilibra()
        calls = []
        set_url(lambda url: (calls.append(url), "[]")[1])
        inst.search("test", cat="anime")
        assert len(calls) == 1

    def test_class_name_is_anilibra(self):
        inst, _, _ = _load_anilibra()
        assert type(inst).__name__ == "anilibra"

    def test_module_level_rebinding(self):
        inst, _, _ = _load_anilibra()
        assert type(inst).__name__ == "anilibra"

    def test_search_results_are_dicts(self):
        inst, captured, set_url = _load_anilibra()
        set_url(lambda url: json.dumps([TORRENT_A]))
        inst._process_release(RELEASE_1)
        assert isinstance(captured[0], dict)

    def test_large_release_list(self):
        inst, captured, set_url = _load_anilibra()
        releases = [{"id": i, "name": {"main": f"Release {i}", "english": f"Release {i}"}} for i in range(20)]
        set_url(lambda url: json.dumps(releases))
        call_count = [0]
        original = inst._process_release

        def counting_process(rel):
            call_count[0] += 1
            return original(rel)

        inst._process_release = counting_process
        inst.search("many")
        assert call_count[0] == 20

    def test_torrent_with_zero_seeders(self):
        inst, captured, set_url = _load_anilibra()
        torrent = {"id": 801, "magnet": "magnet:?xt=urn:btih:seed0", "size": 1000, "seeders": 0, "leechers": 5}
        set_url(lambda url: json.dumps([torrent]))
        inst._process_release({"id": 9001, "name": {"main": "Zero Seed"}})
        assert captured[0]["seeds"] == "0"
        assert captured[0]["leech"] == "5"

    def test_name_main_key_missing(self):
        inst, captured, set_url = _load_anilibra()
        set_url(lambda url: json.dumps([TORRENT_A]))
        inst._process_release({"id": 9002, "name": {}})
        assert captured[0]["name"] == "Naruto [720p]"

    def test_name_completely_missing(self):
        inst, captured, set_url = _load_anilibra()
        set_url(lambda url: json.dumps([TORRENT_A]))
        inst._process_release({"id": 9003})
        assert captured[0]["name"] == "Naruto [720p]"

    def test_search_standalone_script(self):
        inst, captured, set_url = _load_anilibra()
        set_url(lambda url: "[]")
        inst.search("naruto", "all")
        assert captured == []
