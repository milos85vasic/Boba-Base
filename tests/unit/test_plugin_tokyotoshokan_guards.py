"""Regression guards for the tokyotoshokan plugin crash on degenerate input.

BOB-015 sub-task: ``plugins/tokyotoshokan.py`` crashes ungracefully when the
upstream/proxy hands back a degenerate response body. The ``search()`` and
``handle_more_pages()`` paths both do::

    data = retrieve_url(...)
    match = torrent_list.search(data)   # re.search(None) -> TypeError

so a ``None`` response body (a real failure mode on network / SSL errors,
where the underlying fetch returns ``None`` rather than a string) raises an
unhandled ``TypeError: expected string or bytes-like object`` BEFORE the
``if not match`` guard can run.

Empty string / whitespace / malformed HTML are accepted by ``re.search`` and
fall through the existing ``if not match: return`` guard cleanly, so those
inputs are asserted as already-safe (they must NOT crash and must yield 0
rows) rather than claimed as crashes.
"""

from __future__ import annotations

import os
import sys
import types

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_PLUGINS_PATH = os.path.join(_REPO_ROOT, "plugins")
if _PLUGINS_PATH not in sys.path:
    sys.path.insert(0, _PLUGINS_PATH)

import pytest


_NAMES = {
    "retrieve_url": lambda url, **kw: "",
    "download_file": lambda url: url,
}


class _HelpersModule(types.ModuleType):
    def __getattr__(self, name):
        if name in _NAMES:
            return _NAMES[name]
        raise AttributeError(name)


def _install_helpers() -> None:
    sys.modules["helpers"] = _HelpersModule("helpers")
    np_mod = types.ModuleType("novaprinter")
    np_mod.prettyPrinter = lambda d: None  # type: ignore[attr-defined]
    sys.modules["novaprinter"] = np_mod


_install_helpers()


@pytest.fixture(autouse=True)
def _ensure_helpers():
    _install_helpers()
    yield
    _install_helpers()


def _make_plugin(monkeypatch, response):
    import tokyotoshokan

    plugin = tokyotoshokan.tokyotoshokan()
    monkeypatch.setattr("tokyotoshokan.retrieve_url", lambda url, **kw: response)
    results: list[dict] = []
    monkeypatch.setattr("tokyotoshokan.prettyPrinter", lambda r: results.append(r))
    return plugin, results


class TestTokyotoshokanGuard:
    def test_none_response_body_does_not_crash(self, monkeypatch):
        """retrieve_url returning None (network/SSL failure) must NOT crash."""
        plugin, results = _make_plugin(monkeypatch, None)
        plugin.search("test")
        assert results == []

    def test_empty_response_returns_no_torrents(self, monkeypatch):
        plugin, results = _make_plugin(monkeypatch, "")
        plugin.search("test")
        assert results == []

    def test_whitespace_response_returns_no_torrents(self, monkeypatch):
        plugin, results = _make_plugin(monkeypatch, "   \n\t  ")
        plugin.search("test")
        assert results == []

    def test_malformed_truncated_html_returns_no_torrents(self, monkeypatch):
        plugin, results = _make_plugin(
            monkeypatch,
            '<html><body><table class="listing"><tr><td>truncated',
        )
        plugin.search("test")
        assert results == []

    def test_wellformed_html_yields_parsed_row(self, monkeypatch):
        """Positive control: a well-formed listing MUST yield a parsed row.

        The four negative tests above prove the ``if not data:`` /
        ``if not match:`` guards don't crash on degenerate input — but on
        their own they would also pass against a guard that over-suppresses
        (e.g. ``return`` unconditionally). This test feeds one minimal,
        well-formed torrent row through the real ``search()`` path and asserts
        ``prettyPrinter`` is called with a non-degenerate result, proving the
        guards do NOT suppress valid results.

        Fixture shape mirrors what ``tokyotoshokan``'s parser actually needs to
        accumulate the 7 keys it requires before flushing a row at ``</tr>``:
        a ``<tr>`` whose ``class`` makes ``"category"``.find() truthy, a magnet
        ``<a>`` (link), an ``application/x-bittorrent`` ``<a>`` (name), a
        ``details`` ``<a>`` (desc_link), a ``desc-bot`` cell with a
        ``Size: <val> `` token, and a ``stats`` cell with two ``<span>``
        children (seeds, leech).
        """
        wellformed = (
            '<html><body><table class="listing">'
            '<tr class="c category">'
            '<td class="desc-top">'
            '<a href="magnet:?xt=urn:btih:DEADBEEF">magnet</a>'
            '<a type="application/x-bittorrent" href="http://x/file.torrent">'
            "Cool Linux Anime 1080p</a>"
            '<a href="details.php?id=1">details</a>'
            "</td>"
            '<td class="desc-bot">Authorized: Yes Size: 1.4GB Date: today</td>'
            '<td class="stats">S: <span>42</span> L: <span>7</span></td>'
            "</tr>"
            "</table></body></html>"
        )

        import tokyotoshokan

        plugin = tokyotoshokan.tokyotoshokan()
        # Serve the listing only for the first search request; return ""
        # for the paginated follow-up fetches so paging stops gracefully.
        def _retrieve(url, **kw):
            if "search.php?terms=" in url and "lastid" not in url:
                return wellformed
            return ""

        results: list[dict] = []
        monkeypatch.setattr("tokyotoshokan.retrieve_url", _retrieve)
        monkeypatch.setattr("tokyotoshokan.prettyPrinter", results.append)

        plugin.search("linux")

        assert len(results) >= 1, "guard over-suppressed a valid listing"
        row = results[0]
        assert row.get("link"), "parsed row has empty link"
        assert row.get("name"), "parsed row has empty name"
        assert row["link"].startswith("magnet:")
        assert row["name"] == "Cool Linux Anime 1080p"
