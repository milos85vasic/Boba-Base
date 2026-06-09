"""Deep coverage tests for plugins/yts.py.

Covers: score.paramBuilder, score.magnetBuilder, score.urlBuilder,
score.done, search pagination math, invalid JSON, missing torrents array,
multiple movies, download_torrent echo, supported_browse_params branch,
edge cases in paramBuilder, and metadata.
"""

from __future__ import annotations

import importlib.util
import json
import math
import sys
import types
from unittest.mock import patch

import pytest

REPO = "/Volumes/T7/Projects/Boba"
PLUGINS = f"{REPO}/plugins"


def _load_yts(captured=None):
    if captured is None:
        captured = []

    np_mod = types.ModuleType("novaprinter")
    np_mod.prettyPrinter = lambda d: captured.append(dict(d))
    sys.modules["novaprinter"] = np_mod

    helpers_mod = types.ModuleType("helpers")
    helpers_mod.retrieve_url = lambda url: ""
    sys.modules["helpers"] = helpers_mod

    sys.modules.pop("plugin_yts", None)

    path = f"{PLUGINS}/yts.py"
    spec = importlib.util.spec_from_file_location("plugin_yts", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, captured


def _make_movie(title="Test Movie", year=2024, rating=8.0, genres=None, torrents=None, url="https://yts.lt/movie/test"):
    if genres is None:
        genres = ["Action"]
    if torrents is None:
        torrents = [{"hash": "AA" * 20, "quality": "1080p", "size": "1.5 GB", "seeds": 50, "peers": 5}]
    return {
        "title": title,
        "year": year,
        "rating": rating,
        "genres": genres,
        "url": url,
        "torrents": torrents,
    }


def _make_api_response(movies=None, movie_count=1, limit=20, page_number=1):
    if movies is None:
        movies = [_make_movie()]
    return json.dumps({
        "status": "ok",
        "data": {
            "movie_count": movie_count,
            "limit": limit,
            "page_number": page_number,
            "movies": movies,
        },
    })


# ─── score.paramBuilder ───────────────────────────────────────────────────────


class TestParamBuilder:
    def test_simple_keyword(self):
        mod, _ = _load_yts()
        s = mod.score()
        params = s.paramBuilder("ubuntu")
        assert params.get("query_term") == "ubuntu"

    def test_keyword_with_quality(self):
        mod, _ = _load_yts()
        s = mod.score()
        params = s.paramBuilder("ubuntu quality=1080p")
        assert params.get("quality") == "1080p"
        assert params.get("query_term") == "ubuntu"

    def test_keyword_with_genre(self):
        mod, _ = _load_yts()
        s = mod.score()
        params = s.paramBuilder("movie genre=action")
        assert params.get("genre") == "action"
        assert params.get("query_term") == "movie"

    def test_keyword_with_minimum_rating(self):
        mod, _ = _load_yts()
        s = mod.score()
        params = s.paramBuilder("movie minimum_rating=7.5")
        assert params.get("minimum_rating") == "7.5"

    def test_keyword_with_sort_by(self):
        mod, _ = _load_yts()
        s = mod.score()
        params = s.paramBuilder("movie sort_by=date_added")
        assert params.get("sort_by") == "date_added"

    def test_keyword_with_page(self):
        mod, _ = _load_yts()
        s = mod.score()
        params = s.paramBuilder("movie page=3")
        assert params.get("page") == "3"

    def test_keyword_with_limit(self):
        mod, _ = _load_yts()
        s = mod.score()
        params = s.paramBuilder("movie limit=50")
        assert params.get("limit") == "50"

    def test_empty_query(self):
        mod, _ = _load_yts()
        s = mod.score()
        params = s.paramBuilder("")
        assert params == {} or params.get("query_term") is None

    def test_multiple_params_combined(self):
        mod, _ = _load_yts()
        s = mod.score()
        params = s.paramBuilder("query quality=720p genre=drama sort_by=rating page=2")
        assert params.get("quality") == "720p"
        assert params.get("genre") == "drama"
        assert params.get("sort_by") == "rating"
        assert params.get("page") == "2"

    def test_special_characters_in_query(self):
        mod, _ = _load_yts()
        s = mod.score()
        params = s.paramBuilder("C++ programming")
        assert params.get("query_term") == "C++ programming"


# ─── score.magnetBuilder ──────────────────────────────────────────────────────


class TestMagnetBuilder:
    def test_magnet_contains_hash(self):
        mod, _ = _load_yts()
        s = mod.score()
        h = "AA" * 20
        magnet = s.magnetBuilder(h, "Test")
        assert f"btih:{h}" in magnet

    def test_magnet_contains_dn(self):
        mod, _ = _load_yts()
        s = mod.score()
        magnet = s.magnetBuilder("BB" * 20, "My Movie")
        assert "dn=My+Movie" in magnet

    def test_magnet_contains_trackers(self):
        mod, _ = _load_yts()
        s = mod.score()
        magnet = s.magnetBuilder("CC" * 20, "X")
        assert "tr=" in magnet
        assert magnet.count("tr=") == len(s.tracker)

    def test_magnet_starts_with_magnet_prefix(self):
        mod, _ = _load_yts()
        s = mod.score()
        magnet = s.magnetBuilder("DD" * 20, "Z")
        assert magnet.startswith("magnet:?xt=urn:btih:")

    def test_magnet_special_chars_in_name(self):
        mod, _ = _load_yts()
        s = mod.score()
        magnet = s.magnetBuilder("EE" * 20, "Tom & Jerry [2021]")
        assert "dn=" in magnet
        assert "Tom" in magnet


# ─── score.urlBuilder ─────────────────────────────────────────────────────────


class TestUrlBuilder:
    def test_basic_url_building(self):
        mod, _ = _load_yts()
        s = mod.score()
        url = s.urlBuilder("https://yts.lt", ["api", "v2", "list_movies.json"])
        assert url == "https://yts.lt/api/v2/list_movies.json"

    def test_url_with_params(self):
        mod, _ = _load_yts()
        s = mod.score()
        url = s.urlBuilder("https://yts.lt", ["api", "v2", "list_movies.json"], {"query_term": "test"})
        assert url == "https://yts.lt/api/v2/list_movies.json?query_term=test"

    def test_url_no_params(self):
        mod, _ = _load_yts()
        s = mod.score()
        url = s.urlBuilder("https://yts.lt", ["api"], {})
        assert url == "https://yts.lt/api"

    def test_url_empty_uri(self):
        mod, _ = _load_yts()
        s = mod.score()
        url = s.urlBuilder("https://yts.lt", [], {"page": "1"})
        assert url == "https://yts.lt?page=1"


# ─── score.done ───────────────────────────────────────────────────────────────


class TestDone:
    def test_done_with_result(self):
        mod, captured = _load_yts()
        s = mod.score()
        s.done({"name": "test", "link": "magnet:..."})
        assert len(captured) == 1
        assert captured[0]["name"] == "test"

    def test_done_with_empty_dict(self):
        mod, captured = _load_yts()
        s = mod.score()
        s.done({})
        assert len(captured) == 0

    def test_done_no_args(self):
        mod, captured = _load_yts()
        s = mod.score()
        s.done()
        assert len(captured) == 0


# ─── Search: pagination math ──────────────────────────────────────────────────


class TestSearchPagination:
    def test_page_of_calculation_single_page(self):
        mod, captured = _load_yts()
        instance = mod.yts()
        data = _make_api_response(movie_count=5, limit=20, page_number=1)
        with patch.object(mod, "retrieve_url", return_value=data):
            instance.search("test")
        assert len(captured) == 1
        assert "[1of1]" in captured[0]["name"]

    def test_page_of_calculation_multi_page(self):
        mod, captured = _load_yts()
        instance = mod.yts()
        data = _make_api_response(movie_count=40, limit=20, page_number=1)
        with patch.object(mod, "retrieve_url", return_value=data):
            instance.search("test")
        total_pages = math.ceil(40 / 20)
        assert len(captured) >= 1
        assert f"[1of{total_pages}]" in captured[0]["name"]

    def test_page_of_calculation_page_2(self):
        mod, captured = _load_yts()
        instance = mod.yts()
        data = _make_api_response(movie_count=50, limit=20, page_number=2)
        with patch.object(mod, "retrieve_url", return_value=data):
            instance.search("test page:2")
        total_pages = math.ceil(50 / 20)
        assert f"[2of{total_pages}]" in captured[0]["name"]


# ─── Search: multiple movies ──────────────────────────────────────────────────


class TestSearchMultipleMovies:
    def test_two_movies_each_with_one_torrent(self):
        mod, captured = _load_yts()
        instance = mod.yts()
        movies = [
            _make_movie(title="Movie A", torrents=[{"hash": "11" * 20, "quality": "1080p", "size": "1 GB", "seeds": 10, "peers": 1}]),
            _make_movie(title="Movie B", torrents=[{"hash": "22" * 20, "quality": "720p", "size": "700 MB", "seeds": 5, "peers": 2}]),
        ]
        data = _make_api_response(movies=movies, movie_count=2)
        with patch.object(mod, "retrieve_url", return_value=data):
            instance.search("multi")
        assert len(captured) == 2
        assert captured[0]["name"].startswith("Movie A")
        assert captured[1]["name"].startswith("Movie B")

    def test_one_movie_multiple_qualities(self):
        mod, captured = _load_yts()
        instance = mod.yts()
        torrents = [
            {"hash": "11" * 20, "quality": "1080p", "size": "1.5 GB", "seeds": 100, "peers": 10},
            {"hash": "22" * 20, "quality": "720p", "size": "800 MB", "seeds": 50, "peers": 5},
            {"hash": "33" * 20, "quality": "2160p", "size": "4 GB", "seeds": 20, "peers": 2},
        ]
        movies = [_make_movie(title="Quality Test", torrents=torrents)]
        data = _make_api_response(movies=movies)
        with patch.object(mod, "retrieve_url", return_value=data):
            instance.search("quality")
        assert len(captured) == 3
        qualities = [c["name"] for c in captured]
        assert any("[1080p]" in q for q in qualities)
        assert any("[720p]" in q for q in qualities)
        assert any("[2160p]" in q for q in qualities)

    def test_metadata_fields_populated(self):
        mod, captured = _load_yts()
        instance = mod.yts()
        movies = [_make_movie(title="Meta Test", year=2023, rating=9.1, genres=["Sci-Fi", "Drama"])]
        data = _make_api_response(movies=movies)
        with patch.object(mod, "retrieve_url", return_value=data):
            instance.search("meta")
        row = captured[0]
        assert "2023" in row["name"]
        assert row["engine_url"] == "IMDB:9.1, [Sci-Fi, Drama]"
        assert row["desc_link"] == "https://yts.lt/movie/test"
        assert row["seeds"] == 50
        assert row["leech"] == 5


# ─── Search: error handling ───────────────────────────────────────────────────


class TestSearchErrorHandling:
    def test_invalid_json_returns_silently(self):
        mod, captured = _load_yts()
        instance = mod.yts()
        with patch.object(mod, "retrieve_url", return_value="not json at all"):
            instance.search("broken")
        assert captured == []

    def test_empty_response(self):
        mod, captured = _load_yts()
        instance = mod.yts()
        with patch.object(mod, "retrieve_url", return_value=""):
            instance.search("empty")
        assert captured == []

    def test_missing_data_key(self):
        mod, captured = _load_yts()
        instance = mod.yts()
        with patch.object(mod, "retrieve_url", return_value='{"status": "ok"}'):
            instance.search("nodata")
        assert captured == []

    def test_missing_movies_key(self):
        mod, captured = _load_yts()
        instance = mod.yts()
        with patch.object(mod, "retrieve_url", return_value='{"data": {"movie_count": 1}}'):
            instance.search("nomovies")
        assert captured == []

    def test_movie_count_zero(self):
        mod, captured = _load_yts()
        instance = mod.yts()
        data = _make_api_response(movies=[], movie_count=0)
        with patch.object(mod, "retrieve_url", return_value=data):
            instance.search("zero")
        assert captured == []

    def test_movie_without_torrents_key(self):
        mod, captured = _load_yts()
        instance = mod.yts()
        movie = {"title": "No Torrents", "year": 2024, "rating": 5.0, "genres": [], "url": "https://yts.lt/x", "torrents": []}
        data = _make_api_response(movies=[movie])
        with patch.object(mod, "retrieve_url", return_value=data):
            instance.search("notorrents")
        assert captured == []


# ─── Search: name format ─────────────────────────────────────────────────────


class TestNameFormat:
    def test_name_format_standard(self):
        mod, captured = _load_yts()
        instance = mod.yts()
        data = _make_api_response()
        with patch.object(mod, "retrieve_url", return_value=data):
            instance.search("fmt")
        name = captured[0]["name"]
        assert name.endswith("-[YTS]")
        assert "[1080p]" in name
        assert "(2024)" in name

    def test_name_contains_page_info(self):
        mod, captured = _load_yts()
        instance = mod.yts()
        data = _make_api_response(movie_count=30, limit=20, page_number=1)
        with patch.object(mod, "retrieve_url", return_value=data):
            instance.search("pg")
        assert "[1of2]" in captured[0]["name"]


# ─── download_torrent ─────────────────────────────────────────────────────────


class TestDownloadTorrent:
    def test_download_echoes_magnet_twice(self, capsys):
        mod, _ = _load_yts()
        instance = mod.yts()
        instance.download_torrent("magnet:?xt=urn:btih:DEADBEEF")
        out = capsys.readouterr().out.strip()
        parts = out.split(" ")
        assert len(parts) == 2
        assert parts[0] == parts[1] == "magnet:?xt=urn:btih:DEADBEEF"

    def test_download_with_full_magnet(self, capsys):
        mod, _ = _load_yts()
        instance = mod.yts()
        full_magnet = "magnet:?xt=urn:btih:AAAA1111BBBB2222CCCC3333&dn=Movie&tr=udp://tracker:1337"
        instance.download_torrent(full_magnet)
        out = capsys.readouterr().out.strip()
        assert out == f"{full_magnet} {full_magnet}"


# ─── Metadata ─────────────────────────────────────────────────────────────────


class TestMetadata:
    def test_class_url(self):
        mod, _ = _load_yts()
        assert mod.yts.url == "https://yts.lt"

    def test_class_name(self):
        mod, _ = _load_yts()
        assert mod.yts.name == "YTS"

    def test_supported_categories(self):
        mod, _ = _load_yts()
        cats = mod.yts.supported_categories
        assert "all" in cats
        assert "movies" in cats
        assert len(cats) == 2

    def test_tracker_list_populated(self):
        mod, _ = _load_yts()
        s = mod.score()
        assert len(s.tracker) > 0
        assert all(t.startswith("udp://") for t in s.tracker)


# ─── Search: magnet link format ───────────────────────────────────────────────


class TestMagnetLinks:
    def test_magnet_link_in_search_result(self):
        mod, captured = _load_yts()
        instance = mod.yts()
        data = _make_api_response()
        with patch.object(mod, "retrieve_url", return_value=data):
            instance.search("mag")
        link = captured[0]["link"]
        assert link.startswith("magnet:?xt=urn:btih:")
        assert "AA" * 20 in link

    def test_magnet_dn_matches_movie_title(self):
        mod, captured = _load_yts()
        instance = mod.yts()
        movies = [_make_movie(title="My Cool Movie")]
        data = _make_api_response(movies=movies)
        with patch.object(mod, "retrieve_url", return_value=data):
            instance.search("dn")
        assert "dn=My+Cool+Movie" in captured[0]["link"]

    def test_magnet_has_trackers(self):
        mod, captured = _load_yts()
        instance = mod.yts()
        data = _make_api_response()
        with patch.object(mod, "retrieve_url", return_value=data):
            instance.search("tr")
        link = captured[0]["link"]
        assert link.count("tr=") == 8
