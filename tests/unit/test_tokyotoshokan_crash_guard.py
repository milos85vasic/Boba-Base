"""BOB-015 regression guard: tokyotoshokan plugins must not crash on
empty / garbage upstream responses.

Both ``plugins/tokyotoshokan.py`` and ``plugins/community/tokyotoshokan.py``
contained ``data = torrent_list.search(data).group(0)`` calls that raise
``AttributeError: 'NoneType' object has no attribute 'group'`` when the
upstream site returns an empty body (network / SSL failure) or HTML whose
``<table class="listing">`` block is missing.

The first page in ``plugins/tokyotoshokan.py`` already had a guard, but the
paged-fetch loop in ``handle_more_pages`` did not. The community copy had no
guard on any of its three call sites.

Each test feeds a first page that DOES contain a listing table plus a
pagination link (so the ``handle_more_pages`` loop is entered), then returns
an empty body for the subsequent paged fetch — the exact condition that used
to crash. After the guard, ``search()`` must complete without raising and
simply emit whatever rows the first page held (zero, here, since the fixture
has no complete result rows).
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PLUGINS = REPO / "plugins"


def _load_plugin_from(path: Path, modname: str):
    """Import a plugin file at an explicit path, capturing prettyPrinter rows."""
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

    spec = importlib.util.spec_from_file_location(modname, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod, captured


# First page: a listing table that contains a pagination link matching
# `\?lastid=[0-9]+&page=[0-9]+&terms=<query>`. This makes handle_more_pages
# enter its loop and then call retrieve_url for the paged URL.
_FIRST_PAGE = (
    '<table class="listing">'
    '<a href="?lastid=42&page=2&terms=ubuntu">next</a>'
    "</table>"
)


def _make_retriever(*responses: str, default: str = ""):
    """Return a retrieve_url that yields each response in order, then `default`.

    The tokyotoshokan crash lives in ``handle_more_pages``' paged-fetch loop
    (``data = torrent_list.search(data).group(0)``). Reaching it on the MAIN
    plugin requires: call 1 = first page (search()), call 2 = a paged page that
    still has a listing table + pagination link (so the loop body runs), then
    call 3 = the empty/garbage body that used to crash inside the loop.
    """
    seq = list(responses)
    idx = {"i": 0}

    def retrieve(_url):
        i = idx["i"]
        idx["i"] = i + 1
        return seq[i] if i < len(seq) else default

    return retrieve


def _run_search_with(mod, captured, retriever):
    # Patch the module-level retrieve_url the plugin imported at load time.
    mod.retrieve_url = retriever
    # page_count is a module global the plugin mutates; reset between runs.
    if hasattr(mod, "page_count"):
        mod.page_count = 1
    instance = mod.tokyotoshokan()
    instance.search("ubuntu")
    return captured


def test_main_tokyotoshokan_empty_paged_response_does_not_crash() -> None:
    mod, captured = _load_plugin_from(PLUGINS / "tokyotoshokan.py", "plugin_tts_main")
    # call1 = first page, call2 = paged page with table+link (loop entered),
    # call3+ = empty body that used to crash at the in-loop .group(0).
    retriever = _make_retriever(_FIRST_PAGE, _FIRST_PAGE, "")
    rows = _run_search_with(mod, captured, retriever)
    # Must not raise; first page held no complete result rows -> zero results.
    assert rows == []


def test_main_tokyotoshokan_garbage_paged_response_does_not_crash() -> None:
    mod, captured = _load_plugin_from(PLUGINS / "tokyotoshokan.py", "plugin_tts_main2")
    retriever = _make_retriever(
        _FIRST_PAGE, _FIRST_PAGE, "<html>garbage no listing table</html>"
    )
    rows = _run_search_with(mod, captured, retriever)
    assert rows == []


def test_community_tokyotoshokan_empty_first_response_does_not_crash() -> None:
    # Community copy has NO first-page guard, so even an empty first body
    # used to crash at `torrent_list.search(data).group(0)`.
    mod, captured = _load_plugin_from(
        PLUGINS / "community" / "tokyotoshokan.py", "plugin_tts_comm"
    )
    retriever = _make_retriever("", default="")
    rows = _run_search_with(mod, captured, retriever)
    assert rows == []


def test_community_tokyotoshokan_empty_paged_response_does_not_crash() -> None:
    mod, captured = _load_plugin_from(
        PLUGINS / "community" / "tokyotoshokan.py", "plugin_tts_comm2"
    )
    # First page has table+link so handle_more_pages enters its loop;
    # the in-loop paged fetch returns empty -> crash site at line 117.
    retriever = _make_retriever(_FIRST_PAGE, _FIRST_PAGE, "")
    rows = _run_search_with(mod, captured, retriever)
    assert rows == []
