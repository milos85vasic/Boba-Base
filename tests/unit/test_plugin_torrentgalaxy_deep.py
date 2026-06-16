"""Deep coverage tests for plugins/torrentgalaxy.py.

Covers: category mapping, pagination (multi-page), special characters in
titles, HTML with missing fields, regex edge cases, search URL construction,
download_torrent with various link patterns, error handling.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import patch

import pytest

# Resolve the repo root dynamically (§11.4.111/§11.4.29) — a hardcoded
# "/Volumes/T7/Projects/Boba" failed on the case-sensitive T7 volume (real
# repo is lowercase "boba"), making every test here FileNotFoundError.
REPO = Path(__file__).resolve().parents[2]
PLUGINS = f"{REPO}/plugins"


def _load_torrentgalaxy(captured=None):
    if captured is None:
        captured = []

    np_mod = types.ModuleType("novaprinter")
    np_mod.prettyPrinter = lambda d: captured.append(dict(d))
    sys.modules["novaprinter"] = np_mod

    helpers_mod = types.ModuleType("helpers")
    helpers_mod.retrieve_url = lambda url: ""
    helpers_mod.download_file = lambda url: url
    sys.modules["helpers"] = helpers_mod

    sys.modules.pop("plugin_torrentgalaxy", None)

    path = f"{PLUGINS}/torrentgalaxy.py"
    spec = importlib.util.spec_from_file_location("plugin_torrentgalaxy", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, captured


TGX_ROW_TEMPLATE = (
    '<div class="tgxtablerow txlight">'
    "<b>{title}</b>"
    '<a href="{href}">link</a>'
    "<span>{size}</span>"
    '<span class="badge badge-secondary txlight" style="border-radius:4px;">'
    'cat</span><span style="color:green">x</span>'
    "<span>{seeds}</span>"
    "<span>{leech}</span>"
    "</table>\n</div>"
)


def _tgx_page(rows: str) -> str:
    return f"<html><body>{rows}</body></html>"


def _row(title="Test", href="/post/test", size="1 GB", seeds="10", leech="5"):
    return TGX_ROW_TEMPLATE.format(
        title=title, href=href, size=size, seeds=seeds, leech=leech
    )


# ─── Category mapping ────────────────────────────────────────────────────────


class TestCategoryMapping:
    def test_all_category_produces_no_cat_filter(self):
        mod, captured = _load_torrentgalaxy()
        instance = mod.torrentgalaxy()
        page1 = _tgx_page(_row(title="Result1"))
        call_count = 0

        def fake_retrieve(url):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return page1
            return _tgx_page("")

        with (
            patch.object(mod, "retrieve_url", side_effect=fake_retrieve),
            patch.object(mod, "sleep", lambda _s: None),
        ):
            instance.search("query", cat="all")

        assert len(captured) == 1
        assert captured[0]["name"] == "Result1"

    def test_movies_category_includes_category_filter(self):
        mod, captured = _load_torrentgalaxy()
        instance = mod.torrentgalaxy()
        urls_seen = []

        def fake_retrieve(url):
            urls_seen.append(url)
            return _tgx_page("")

        with (
            patch.object(mod, "retrieve_url", side_effect=fake_retrieve),
            patch.object(mod, "sleep", lambda _s: None),
        ):
            instance.search("query", cat="movies")

        assert len(urls_seen) == 1
        assert ":category:Movies" in urls_seen[0]

    def test_tv_category_in_url(self):
        mod, captured = _load_torrentgalaxy()
        instance = mod.torrentgalaxy()
        urls_seen = []

        def fake_retrieve(url):
            urls_seen.append(url)
            return _tgx_page("")

        with (
            patch.object(mod, "retrieve_url", side_effect=fake_retrieve),
            patch.object(mod, "sleep", lambda _s: None),
        ):
            instance.search("test", cat="tv")

        assert ":category:TV" in urls_seen[0]

    def test_music_category_in_url(self):
        mod, captured = _load_torrentgalaxy()
        instance = mod.torrentgalaxy()
        urls_seen = []

        def fake_retrieve(url):
            urls_seen.append(url)
            return _tgx_page("")

        with (
            patch.object(mod, "retrieve_url", side_effect=fake_retrieve),
            patch.object(mod, "sleep", lambda _s: None),
        ):
            instance.search("test", cat="music")

        assert ":category:Music" in urls_seen[0]

    def test_anime_category_in_url(self):
        mod, captured = _load_torrentgalaxy()
        instance = mod.torrentgalaxy()
        urls_seen = []

        def fake_retrieve(url):
            urls_seen.append(url)
            return _tgx_page("")

        with (
            patch.object(mod, "retrieve_url", side_effect=fake_retrieve),
            patch.object(mod, "sleep", lambda _s: None),
        ):
            instance.search("test", cat="anime")

        assert ":category:Anime" in urls_seen[0]

    def test_software_category_in_url(self):
        mod, captured = _load_torrentgalaxy()
        instance = mod.torrentgalaxy()
        urls_seen = []

        def fake_retrieve(url):
            urls_seen.append(url)
            return _tgx_page("")

        with (
            patch.object(mod, "retrieve_url", side_effect=fake_retrieve),
            patch.object(mod, "sleep", lambda _s: None),
        ):
            instance.search("test", cat="software")

        assert ":category:Apps" in urls_seen[0]

    def test_books_category_in_url(self):
        mod, captured = _load_torrentgalaxy()
        instance = mod.torrentgalaxy()
        urls_seen = []

        def fake_retrieve(url):
            urls_seen.append(url)
            return _tgx_page("")

        with (
            patch.object(mod, "retrieve_url", side_effect=fake_retrieve),
            patch.object(mod, "sleep", lambda _s: None),
        ):
            instance.search("test", cat="books")

        assert ":category:Books" in urls_seen[0]

    def test_games_category_in_url(self):
        mod, captured = _load_torrentgalaxy()
        instance = mod.torrentgalaxy()
        urls_seen = []

        def fake_retrieve(url):
            urls_seen.append(url)
            return _tgx_page("")

        with (
            patch.object(mod, "retrieve_url", side_effect=fake_retrieve),
            patch.object(mod, "sleep", lambda _s: None),
        ):
            instance.search("test", cat="games")

        assert ":category:Games" in urls_seen[0]


# ─── Pagination ───────────────────────────────────────────────────────────────


class TestPagination:
    def test_multiple_pages(self):
        mod, captured = _load_torrentgalaxy()
        instance = mod.torrentgalaxy()
        pages = [
            _tgx_page(_row(title="Page1-Item1") + _row(title="Page1-Item2")),
            _tgx_page(_row(title="Page2-Item1")),
            _tgx_page(""),
        ]

        def fake_retrieve(url):
            return pages.pop(0) if pages else _tgx_page("")

        with (
            patch.object(mod, "retrieve_url", side_effect=fake_retrieve),
            patch.object(mod, "sleep", lambda _s: None),
        ):
            instance.search("multi")

        assert len(captured) == 3
        assert captured[0]["name"] == "Page1-Item1"
        assert captured[1]["name"] == "Page1-Item2"
        assert captured[2]["name"] == "Page2-Item1"

    def test_page_urls_increment(self):
        mod, captured = _load_torrentgalaxy()
        instance = mod.torrentgalaxy()
        urls_seen = []
        call_count = [0]

        def fake_retrieve(url):
            urls_seen.append(url)
            call_count[0] += 1
            if call_count[0] <= 2:
                return _tgx_page(_row(title="x"))
            return _tgx_page("")

        with (
            patch.object(mod, "retrieve_url", side_effect=fake_retrieve),
            patch.object(mod, "sleep", lambda _s: None),
        ):
            instance.search("test")

        assert len(urls_seen) >= 2
        assert "?page=1" in urls_seen[0]
        assert "?page=2" in urls_seen[1]

    def test_sleep_called_between_pages(self):
        mod, captured = _load_torrentgalaxy()
        instance = mod.torrentgalaxy()
        sleep_calls = []
        call_count = [0]

        def fake_retrieve(url):
            call_count[0] += 1
            if call_count[0] <= 2:
                return _tgx_page(_row(title="x"))
            return _tgx_page("")

        def fake_sleep(s):
            sleep_calls.append(s)

        with (
            patch.object(mod, "retrieve_url", side_effect=fake_retrieve),
            patch.object(mod, "sleep", fake_sleep),
        ):
            instance.search("test")

        assert len(sleep_calls) >= 1
        assert all(s == 3 for s in sleep_calls)


# ─── Special characters and regex edge cases ──────────────────────────────────


class TestRegexEdgeCases:
    def test_title_with_html_entities(self):
        mod, captured = _load_torrentgalaxy()
        parser = mod.torrentgalaxy.HTMLParser("https://torrentgalaxy.one/")
        parser.feed(_tgx_page(_row(title="Tom &amp; Jerry 2021", href="/post/tj")))
        assert len(captured) == 1
        assert captured[0]["name"] == "Tom &amp; Jerry 2021"

    def test_title_with_special_chars(self):
        mod, captured = _load_torrentgalaxy()
        parser = mod.torrentgalaxy.HTMLParser("https://torrentgalaxy.one/")
        parser.feed(
            _tgx_page(_row(title="C++ Programming [2024] (1080p)", href="/post/cp"))
        )
        assert len(captured) == 1
        assert captured[0]["name"] == "C++ Programming [2024] (1080p)"

    def test_size_with_commas(self):
        mod, captured = _load_torrentgalaxy()
        parser = mod.torrentgalaxy.HTMLParser("https://torrentgalaxy.one/")
        parser.feed(_tgx_page(_row(title="Large", size="1,234.56 GB", href="/post/l")))
        assert len(captured) == 1
        assert captured[0]["size"] == "1,234.56 GB"

    def test_size_in_kb(self):
        mod, captured = _load_torrentgalaxy()
        parser = mod.torrentgalaxy.HTMLParser("https://torrentgalaxy.one/")
        parser.feed(_tgx_page(_row(title="Tiny", size="512 KB", href="/post/t")))
        assert len(captured) == 1
        assert captured[0]["size"] == "512 KB"

    def test_size_in_tb(self):
        mod, captured = _load_torrentgalaxy()
        parser = mod.torrentgalaxy.HTMLParser("https://torrentgalaxy.one/")
        parser.feed(_tgx_page(_row(title="Huge", size="2.5 TB", href="/post/h")))
        assert len(captured) == 1
        assert captured[0]["size"] == "2.5 TB"

    def test_zero_seeds_zero_leech(self):
        mod, captured = _load_torrentgalaxy()
        parser = mod.torrentgalaxy.HTMLParser("https://torrentgalaxy.one/")
        parser.feed(_tgx_page(_row(title="Dead", seeds="0", leech="0", href="/post/d")))
        assert len(captured) == 1
        assert captured[0]["seeds"] == "0"
        assert captured[0]["leech"] == "0"

    def test_large_seed_count(self):
        mod, captured = _load_torrentgalaxy()
        parser = mod.torrentgalaxy.HTMLParser("https://torrentgalaxy.one/")
        parser.feed(
            _tgx_page(_row(title="Popular", seeds="99,999", leech="1,234", href="/post/p"))
        )
        assert len(captured) == 1
        assert captured[0]["seeds"] == "99,999"
        assert captured[0]["leech"] == "1,234"

    def test_multiple_rows_parsed(self):
        mod, captured = _load_torrentgalaxy()
        parser = mod.torrentgalaxy.HTMLParser("https://torrentgalaxy.one/")
        rows = _row(title="A", href="/post/a") + _row(title="B", href="/post/b")
        parser.feed(_tgx_page(rows))
        assert len(captured) == 2
        assert captured[0]["name"] == "A"
        assert captured[1]["name"] == "B"

    def test_no_torrents_sets_flag(self):
        mod, captured = _load_torrentgalaxy()
        parser = mod.torrentgalaxy.HTMLParser("https://torrentgalaxy.one/")
        parser.feed(_tgx_page("<p>nothing here</p>"))
        assert parser.noTorrents is True
        assert len(captured) == 0

    def test_no_torrents_reset_on_subsequent_feed(self):
        mod, captured = _load_torrentgalaxy()
        parser = mod.torrentgalaxy.HTMLParser("https://torrentgalaxy.one/")
        parser.feed(_tgx_page("<p>empty</p>"))
        assert parser.noTorrents is True
        parser.feed(_tgx_page(_row(title="Found", href="/post/f")))
        assert parser.noTorrents is False
        assert len(captured) == 1


# ─── URL construction ─────────────────────────────────────────────────────────


class TestURLConstruction:
    def test_search_url_contains_keyword(self):
        mod, captured = _load_torrentgalaxy()
        instance = mod.torrentgalaxy()
        urls_seen = []

        def fake_retrieve(url):
            urls_seen.append(url)
            return _tgx_page("")

        with (
            patch.object(mod, "retrieve_url", side_effect=fake_retrieve),
            patch.object(mod, "sleep", lambda _s: None),
        ):
            instance.search("ubuntu")

        assert "keywords:ubuntu" in urls_seen[0]

    def test_search_url_starts_with_base_url(self):
        mod, captured = _load_torrentgalaxy()
        instance = mod.torrentgalaxy()
        urls_seen = []

        def fake_retrieve(url):
            urls_seen.append(url)
            return _tgx_page("")

        with (
            patch.object(mod, "retrieve_url", side_effect=fake_retrieve),
            patch.object(mod, "sleep", lambda _s: None),
        ):
            instance.search("test")

        assert urls_seen[0].startswith("https://torrentgalaxy.one/")

    def test_url_encoded_query(self):
        mod, captured = _load_torrentgalaxy()
        instance = mod.torrentgalaxy()
        urls_seen = []

        def fake_retrieve(url):
            urls_seen.append(url)
            return _tgx_page("")

        with (
            patch.object(mod, "retrieve_url", side_effect=fake_retrieve),
            patch.object(mod, "sleep", lambda _s: None),
        ):
            instance.search("hello world")

        # Reconciled per §11.4.120: a raw space in the query is now encoded
        # to %20 so the URL is valid for urllib (a raw space crashed the
        # merge-service caller). The keyword still appears, %20-joined.
        assert "keywords:hello%20world" in urls_seen[0]
        assert " " not in urls_seen[0]


# ─── download_torrent ─────────────────────────────────────────────────────────


class TestDownloadTorrent:
    def test_download_with_itorrents_link_no_query(self):
        mod, _ = _load_torrentgalaxy()
        instance = mod.torrentgalaxy()
        detail_page = '<a href="https://itorrents.org/torrent/ABC.torrent">dl</a>'
        with patch.object(mod, "retrieve_url", return_value=detail_page):
            with pytest.raises(Exception, match="Download link not found"):
                instance.download_torrent("https://torrentgalaxy.one/post/x")

    def test_download_itorrents_with_query_params(self):
        mod, _ = _load_torrentgalaxy()
        instance = mod.torrentgalaxy()
        detail_page = '<a href="https://itorrents.org/torrent/ABC.torrent?token=xyz&name=test">dl</a>'
        with (
            patch.object(mod, "retrieve_url", return_value=detail_page),
            patch.object(mod, "download_file", side_effect=lambda u: f"FILE:{u}"),
        ):
            out = instance.download_torrent("https://torrentgalaxy.one/post/x")
        import io
        import contextlib

        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            with (
                patch.object(mod, "retrieve_url", return_value=detail_page),
                patch.object(mod, "download_file", side_effect=lambda u: f"FILE:{u}"),
            ):
                instance.download_torrent("https://torrentgalaxy.one/post/x")
        output = f.getvalue().strip()
        assert output == "FILE:https://itorrents.org/torrent/ABC.torrent"

    def test_download_non_itorrents_link_fails(self):
        mod, _ = _load_torrentgalaxy()
        instance = mod.torrentgalaxy()
        detail_page = '<a href="https://example.com/torrent/ABC.torrent?foo=bar">dl</a>'
        with patch.object(mod, "retrieve_url", return_value=detail_page):
            with pytest.raises(Exception, match="Download link not found"):
                instance.download_torrent("https://torrentgalaxy.one/post/x")

    def test_download_no_href_at_all(self):
        mod, _ = _load_torrentgalaxy()
        instance = mod.torrentgalaxy()
        with patch.object(mod, "retrieve_url", return_value="<html><body>text only</body></html>"):
            with pytest.raises(Exception, match="Download link not found"):
                instance.download_torrent("https://torrentgalaxy.one/post/x")

    def test_download_whitespace_collapsed_before_search(self):
        mod, _ = _load_torrentgalaxy()
        instance = mod.torrentgalaxy()
        detail_page = (
            '<a\n  href="https://itorrents.org/torrent/DEF.torrent?tok=abc"\n>dl</a>'
        )
        import io
        import contextlib

        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            with (
                patch.object(mod, "retrieve_url", return_value=detail_page),
                patch.object(mod, "download_file", side_effect=lambda u: f"FILE:{u}"),
            ):
                instance.download_torrent("https://torrentgalaxy.one/post/y")
        output = f.getvalue().strip()
        assert output == "FILE:https://itorrents.org/torrent/DEF.torrent"


# ─── Timestamp ────────────────────────────────────────────────────────────────


class TestTimestamp:
    def test_pub_date_is_always_minus_one(self):
        mod, captured = _load_torrentgalaxy()
        parser = mod.torrentgalaxy.HTMLParser("https://torrentgalaxy.one/")
        parser.feed(_tgx_page(_row(title="X", href="/post/x")))
        assert captured[0]["pub_date"] == -1


# ─── Metadata ─────────────────────────────────────────────────────────────────


class TestMetadata:
    def test_class_url(self):
        mod, _ = _load_torrentgalaxy()
        assert mod.torrentgalaxy.url == "https://torrentgalaxy.one/"

    def test_class_name(self):
        mod, _ = _load_torrentgalaxy()
        assert mod.torrentgalaxy.name == "TorrentGalaxy"

    def test_supported_categories_keys(self):
        mod, _ = _load_torrentgalaxy()
        expected = {"all", "movies", "tv", "music", "games", "anime", "software", "books"}
        assert set(mod.torrentgalaxy.supported_categories.keys()) == expected

    def test_engine_url_in_parsed_row(self):
        mod, captured = _load_torrentgalaxy()
        parser = mod.torrentgalaxy.HTMLParser("https://torrentgalaxy.one/")
        parser.feed(_tgx_page(_row(title="Y", href="/post/y")))
        assert captured[0]["engine_url"] == "https://torrentgalaxy.one/"

    def test_desc_link_matches_link(self):
        mod, captured = _load_torrentgalaxy()
        parser = mod.torrentgalaxy.HTMLParser("https://torrentgalaxy.one/")
        parser.feed(_tgx_page(_row(title="Z", href="/post/z")))
        assert captured[0]["link"] == captured[0]["desc_link"]
        assert "post/z" in captured[0]["link"]
