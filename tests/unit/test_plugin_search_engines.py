"""Offline anti-bluff parsing tests for four qBittorrent search-engine plugins.

Covered plugins: ``yts``, ``torlock``, ``torrentkitty``, ``torrentgalaxy``.

Each plugin is a qBittorrent nova3 engine class that does
``from novaprinter import prettyPrinter`` / ``from helpers import
retrieve_url``. We install lightweight stub modules in ``sys.modules``
BEFORE importing the plugin (mirroring tests/unit/test_plugin_crash_guards.py)
and capture every ``prettyPrinter`` call so we can assert the parsed
result dict fields (name, size, seeds, link, ...).

These tests are offline: ``helpers.retrieve_url`` is stubbed with canned
HTML / JSON fixtures. Each test asserts the real parsed output — a no-op
or wrong parser would emit no rows (or wrong fields) and the test fails.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
PLUGINS = REPO / "plugins"


def _load_plugin(name: str):
    """Import a plugin file standalone, returning (module, captured_rows)."""
    captured: list[dict] = []

    np_mod = types.ModuleType("novaprinter")
    np_mod.prettyPrinter = lambda d: captured.append(dict(d))  # type: ignore[attr-defined]

    class _SR:
        pass

    np_mod.SearchResults = _SR  # type: ignore[attr-defined]
    sys.modules["novaprinter"] = np_mod

    helpers_mod = types.ModuleType("helpers")
    helpers_mod.retrieve_url = lambda url: ""  # type: ignore[attr-defined]
    helpers_mod.download_file = lambda url: url  # type: ignore[attr-defined]
    sys.modules["helpers"] = helpers_mod

    path = PLUGINS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"plugin_{name}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod, captured


# ---------------------------------------------------------------------------
# yts (JSON API)
# ---------------------------------------------------------------------------

_YTS_JSON = """
{
  "status": "ok",
  "data": {
    "movie_count": 1,
    "limit": 20,
    "page_number": 1,
    "movies": [
      {
        "title": "Big Buck Bunny",
        "year": 2008,
        "rating": 7.5,
        "genres": ["Animation", "Comedy"],
        "url": "https://yts.lt/movie/big-buck-bunny",
        "torrents": [
          {"hash": "ABCDEF0123456789ABCDEF0123456789ABCDEF01",
           "quality": "1080p", "size": "823 MB", "seeds": 120, "peers": 7},
          {"hash": "1111111122222222333333334444444455555555",
           "quality": "720p", "size": "512 MB", "seeds": 80, "peers": 4}
        ]
      }
    ]
  }
}
"""


def test_yts_parses_json_api_into_two_torrents() -> None:
    mod, captured = _load_plugin("yts")
    instance = mod.yts()
    with patch.object(mod, "retrieve_url", return_value=_YTS_JSON):
        instance.search("big buck bunny")

    assert len(captured) == 2, "two torrent qualities must yield two rows"

    first = captured[0]
    # Name format: "{title} ({year}) [{quality}]-[{page}of{N}]-[YTS]"
    assert first["name"] == "Big Buck Bunny (2008) [1080p]-[1of1]-[YTS]"
    assert first["size"] == "823 MB"
    assert first["seeds"] == 120
    assert first["leech"] == 7
    assert first["desc_link"] == "https://yts.lt/movie/big-buck-bunny"
    # Magnet built from the torrent hash.
    assert first["link"].startswith("magnet:?xt=urn:btih:ABCDEF0123456789ABCDEF0123456789ABCDEF01")
    assert "dn=Big+Buck+Bunny" in first["link"]
    assert "IMDB:7.5" in first["engine_url"]
    assert "Animation, Comedy" in first["engine_url"]

    second = captured[1]
    assert second["name"] == "Big Buck Bunny (2008) [720p]-[1of1]-[YTS]"
    assert second["seeds"] == 80


def test_yts_empty_movie_count_emits_no_rows() -> None:
    mod, captured = _load_plugin("yts")
    instance = mod.yts()
    empty = '{"data": {"movie_count": 0, "limit": 20, "page_number": 1, "movies": []}}'
    with patch.object(mod, "retrieve_url", return_value=empty):
        instance.search("nonexistent-film-xyz")
    assert captured == []


def test_yts_download_torrent_echoes_magnet(capsys) -> None:
    mod, _ = _load_plugin("yts")
    instance = mod.yts()
    instance.download_torrent("magnet:?xt=urn:btih:DEADBEEF")
    out = capsys.readouterr().out.strip()
    assert out == "magnet:?xt=urn:btih:DEADBEEF magnet:?xt=urn:btih:DEADBEEF"


def test_yts_metadata() -> None:
    mod, _ = _load_plugin("yts")
    assert mod.yts.url == "https://yts.lt"
    assert mod.yts.name == "YTS"
    assert "movies" in mod.yts.supported_categories


# ---------------------------------------------------------------------------
# torlock (HTMLParser)
# ---------------------------------------------------------------------------

# Single results page; <article> wraps result <tr> rows. The plugin's
# search() loops pages 1..4 and stops when a page yields <20 items, so a
# single small fixture (returned for every page) breaks the loop after
# page 1.
_TORLOCK_HTML = """
<html><body>
<article>
<table>
<tr>
  <a href="/torrent/123456/ubuntu-22-04-iso.html">Ubuntu 22.04 Desktop ISO</a>
  <td class="td">Today</td>
  <td class="ts">3.5 GB</td>
  <td class="tul">543</td>
  <td class="tdl">21</td>
</tr>
<tr>
  <a href="/torrent/789012/debian-12-netinst.html">Debian 12 netinst</a>
  <td class="td">5/14/2024</td>
  <td class="ts">700 MB</td>
  <td class="tul">88</td>
  <td class="tdl">3</td>
</tr>
</table>
</article>
</body></html>
"""


def test_torlock_parses_two_rows_with_full_fields() -> None:
    mod, captured = _load_plugin("torlock")
    instance = mod.torlock()
    with patch.object(mod, "retrieve_url", return_value=_TORLOCK_HTML):
        instance.search("ubuntu")

    assert len(captured) == 2, "article fixture has two non-bad result rows"

    first = captured[0]
    assert first["name"] == "Ubuntu 22.04 Desktop ISO"
    assert first["size"] == "3.5 GB"
    assert first["seeds"] == "543"
    assert first["leech"] == "21"
    assert first["desc_link"] == "https://torlock2.com/torrent/123456/ubuntu-22-04-iso.html"
    # .torrent link is built from the numeric id segment of the desc path.
    assert first["link"] == "https://torlock2.com/tor/123456.torrent"
    assert first["engine_url"] == "https://torlock2.com"
    # "Today" -> a valid (non -1) midnight epoch.
    assert isinstance(first["pub_date"], int) and first["pub_date"] > 0

    second = captured[1]
    assert second["name"] == "Debian 12 netinst"
    assert second["link"] == "https://torlock2.com/tor/789012.torrent"
    assert second["seeds"] == "88"


def test_torlock_skips_nofollow_malicious_links() -> None:
    mod, captured = _load_plugin("torlock")
    instance = mod.torlock()
    bad_html = (
        "<article><table><tr>"
        '<a href="/torrent/999/bad.html" rel="nofollow">Malicious</a>'
        '<td class="ts">1 GB</td><td class="tul">1</td><td class="tdl">0</td>'
        "<td class=\"td\">Today</td>"
        "</tr></table></article>"
    )
    with patch.object(mod, "retrieve_url", return_value=bad_html):
        instance.search("bad")
    assert captured == [], "rel=nofollow rows must be dropped"


def test_torlock_empty_html_yields_no_rows() -> None:
    mod, captured = _load_plugin("torlock")
    instance = mod.torlock()
    with patch.object(mod, "retrieve_url", return_value="<html></html>"):
        instance.search("anything")
    assert captured == []


def test_torlock_download_torrent(capsys) -> None:
    mod, _ = _load_plugin("torlock")
    instance = mod.torlock()
    # helpers.download_file stub echoes its argument.
    with patch.object(mod, "download_file", side_effect=lambda u: f"FILE:{u}"):
        instance.download_torrent("https://torlock2.com/tor/1.torrent")
    out = capsys.readouterr().out.strip()
    assert out == "FILE:https://torlock2.com/tor/1.torrent"


# ---------------------------------------------------------------------------
# torrentkitty (regex over <tr> table)
# ---------------------------------------------------------------------------

_TK_HTML = """
<table>
<tr>
  <td class="name">Ubuntu 24.04 LTS</td>
  <td class="size">4.2 GB</td>
  <td class="date">2024-04-25</td>
  <td class="action"><a href="magnet:?xt=urn:btih:AAAA1111&dn=ubuntu">Magnet</a></td>
</tr>
<tr>
  <td class="name">Fedora Workstation 40</td>
  <td class="size">2,048 MB</td>
  <td class="date">2024-04-23</td>
  <td class="action"><a href="magnet:?xt=urn:btih:BBBB2222&dn=fedora">Magnet</a></td>
</tr>
</table>
"""


def test_torrentkitty_parses_rows_and_converts_size() -> None:
    mod, captured = _load_plugin("torrentkitty")
    instance = mod.torrentkitty()
    with patch.object(mod, "retrieve_url", return_value=_TK_HTML):
        instance.search("ubuntu")

    assert len(captured) == 2

    first = captured[0]
    assert first["name"] == "Ubuntu 24.04 LTS"
    assert first["link"] == "magnet:?xt=urn:btih:AAAA1111&dn=ubuntu"
    assert first["desc_link"] == "magnet:?xt=urn:btih:AAAA1111&dn=ubuntu"
    assert first["engine_url"] == "https://www.torrentkitty.tv"
    assert first["seeds"] == "0"
    # _parse_size now correctly converts suffix units (the "B"-substring bug
    # that reported 0 for every GB/MB size is fixed). 4.2 GB -> bytes.
    assert first["size"] == str(int(4.2 * 1024**3))

    second = captured[1]
    assert second["name"] == "Fedora Workstation 40"
    assert second["size"] == str(2048 * 1024**2)  # "2,048 MB" -> bytes
    assert second["link"] == "magnet:?xt=urn:btih:BBBB2222&dn=fedora"


def test_torrentkitty_parse_size_all_units() -> None:
    """_parse_size converts every unit by its suffix (regression guard for the
    fixed "B"-substring bug that collapsed all KB/MB/GB/TB sizes to 0)."""
    mod, _ = _load_plugin("torrentkitty")
    instance = mod.torrentkitty()
    assert instance._parse_size("800 B") == 800
    assert instance._parse_size("garbage") == 0
    assert instance._parse_size("1 KB") == 1024
    assert instance._parse_size("2 MB") == 2 * 1024**2
    assert instance._parse_size("1.5 GB") == int(1.5 * 1024**3)
    assert instance._parse_size("1 TB") == 1024**4
    assert instance._parse_size("2,048 MB") == 2048 * 1024**2


def test_torrentkitty_no_results_no_rows() -> None:
    mod, captured = _load_plugin("torrentkitty")
    instance = mod.torrentkitty()
    with patch.object(mod, "retrieve_url", return_value="<table></table>"):
        instance.search("nothing-here")
    assert captured == []


def test_torrentkitty_search_swallows_network_error() -> None:
    mod, captured = _load_plugin("torrentkitty")
    instance = mod.torrentkitty()

    def boom(_url):
        raise OSError("connection refused")

    with patch.object(mod, "retrieve_url", side_effect=boom):
        instance.search("x")  # must not raise
    assert captured == []


def test_torrentkitty_download_torrent(capsys) -> None:
    mod, _ = _load_plugin("torrentkitty")
    instance = mod.torrentkitty()
    instance.download_torrent("magnet:?xt=urn:btih:ZZZZ")
    out = capsys.readouterr().out.strip()
    assert out == "magnet:?xt=urn:btih:ZZZZ magnet:?xt=urn:btih:ZZZZ"


# ---------------------------------------------------------------------------
# torrentgalaxy (regex over tgxtablerow; search() loops with sleep)
# ---------------------------------------------------------------------------

_TGX_ROW = (
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


def test_torrentgalaxy_parses_row_fields() -> None:
    mod, captured = _load_plugin("torrentgalaxy")
    instance = mod.torrentgalaxy()
    page = _tgx_page(
        _TGX_ROW.format(
            title="Sintel 2010 1080p",
            href="/post/sintel-2010",
            size="1.20 GB",
            seeds="312",
            leech="15",
        )
    )

    # search() loops pages with sleep(3); patch sleep to 0 and return an
    # empty page on the 2nd request so the while-loop terminates fast.
    responses = [page, _tgx_page("")]

    def fake_retrieve(_url):
        return responses.pop(0) if responses else _tgx_page("")

    with (
        patch.object(mod, "retrieve_url", side_effect=fake_retrieve),
        patch.object(mod, "sleep", lambda _s: None),
    ):
        instance.search("sintel")

    assert len(captured) == 1, "single row on page 1 must produce one result"
    row = captured[0]
    assert row["name"] == "Sintel 2010 1080p"
    assert row["size"] == "1.20 GB"
    assert row["seeds"] == "312"
    assert row["leech"] == "15"
    # generic_url = url[:-1] + href  (url has trailing slash)
    assert row["link"] == "https://torrentgalaxy.one/post/sintel-2010"
    assert row["desc_link"] == "https://torrentgalaxy.one/post/sintel-2010"
    assert row["engine_url"] == "https://torrentgalaxy.one/"
    assert row["pub_date"] == -1


def test_torrentgalaxy_no_torrents_breaks_loop() -> None:
    mod, captured = _load_plugin("torrentgalaxy")
    instance = mod.torrentgalaxy()
    with (
        patch.object(mod, "retrieve_url", return_value=_tgx_page("")),
        patch.object(mod, "sleep", lambda _s: None),
    ):
        instance.search("nothing")
    assert captured == []


def test_torrentgalaxy_htmlparser_feed_directly() -> None:
    mod, captured = _load_plugin("torrentgalaxy")
    parser = mod.torrentgalaxy.HTMLParser("https://torrentgalaxy.one/")
    parser.feed(
        _TGX_ROW.format(
            title="Tears of Steel",
            href="/post/tos",
            size="900 MB",
            seeds="42",
            leech="1",
        )
    )
    assert parser.noTorrents is False
    assert len(captured) == 1
    assert captured[0]["name"] == "Tears of Steel"
    assert captured[0]["link"] == "https://torrentgalaxy.one/post/tos"


def test_torrentgalaxy_download_torrent_resolves_itorrents(capsys) -> None:
    mod, _ = _load_plugin("torrentgalaxy")
    instance = mod.torrentgalaxy()
    detail_page = '<a href="https://itorrents.org/torrent/ABC.torrent?foo=bar">dl</a>'
    with (
        patch.object(mod, "retrieve_url", return_value=detail_page),
        patch.object(mod, "download_file", side_effect=lambda u: f"FILE:{u}"),
    ):
        instance.download_torrent("https://torrentgalaxy.one/post/x")
    out = capsys.readouterr().out.strip()
    assert out.startswith("FILE:https://itorrents.org/torrent/ABC.torrent")


def test_torrentgalaxy_download_torrent_missing_link_raises() -> None:
    import pytest

    mod, _ = _load_plugin("torrentgalaxy")
    instance = mod.torrentgalaxy()
    with patch.object(mod, "retrieve_url", return_value="<html>no link</html>"):
        with pytest.raises(Exception, match="Download link not found"):
            instance.download_torrent("https://torrentgalaxy.one/post/x")
