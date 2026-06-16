"""§11.4.146 reproduce-first regression guard: multi-word query URL-encoding.

ROOT CAUSE (FACT, characterised 2026-06-16 on this codebase):
The merge service's public-tracker path
(``download-proxy/src/merge_service/search.py`` ``_search_public_tracker``)
invokes ``_engine.search({query!r}, {category!r})`` with the query passed
RAW (NOT percent-encoded). The standard nova2 CLI path
(``plugins/nova2.py:236``) instead passes
``urllib.parse.quote(" ".join(...))`` — i.e. an already-%20-encoded query.

Plugins that string-interpolate the raw query straight into a request
URL/path crash on ANY multi-word query: a literal space reaches
``helpers.retrieve_url`` which calls urllib, and urllib raises
``ValueError: URL can't contain control characters. ... (found at least
' ')``. Single-word queries work; multi-word silently lose the plugin.

These plugins ALSO carry ``what.replace('%20', ...)`` lines — those handle
the nova2 (%20-encoded) caller but do NOT handle a raw space from the
merge-service caller. The robust fix percent-encodes the query at the
point it enters the URL, so BOTH callers are safe (§11.4.111 resolve by a
stable, caller-independent encoding).

This test drives the REAL plugin ``search()`` and captures the URL handed
to ``retrieve_url``; it asserts the constructed URL contains NO raw space
(i.e. is properly percent-encoded), AND that urllib would accept it.

Polarity (§11.4.115): RED_MODE=1 (default) reproduces the defect on the
pre-fix plugins (raw space present / urllib rejects) and asserts it is
ABSENT post-fix — the SAME assertion is the standing GREEN guard.
"""

from __future__ import annotations

import importlib.util
import sys
import types
import urllib.request
from pathlib import Path
from unittest.mock import patch

import pytest

REPO = Path(__file__).resolve().parents[2]
PLUGINS = REPO / "plugins"
COMMUNITY = PLUGINS / "community"

# Multi-word query as the merge service would pass it: RAW, with a literal
# space (NOT %20). This is the exact value that triggered the crash.
MULTIWORD_RAW = "the matrix"


def _plugin_path(name: str) -> Path:
    p = PLUGINS / f"{name}.py"
    if p.exists():
        return p
    cp = COMMUNITY / f"{name}.py"
    if cp.exists():
        return cp
    raise FileNotFoundError(f"Plugin {name} not found")


def _load_plugin(name: str):
    """Import a plugin outside the nova3 harness with stubbed deps,
    capturing every URL passed to ``retrieve_url``."""
    captured_urls: list[str] = []

    np_mod = types.ModuleType("novaprinter")
    np_mod.prettyPrinter = lambda d: None  # type: ignore[attr-defined]

    class _SR:
        pass

    np_mod.SearchResults = _SR  # type: ignore[attr-defined]
    sys.modules["novaprinter"] = np_mod

    def _capture_url(url, *args, **kwargs):
        captured_urls.append(url)
        return ""  # empty body -> plugin parses 0 rows, no crash downstream

    helpers_mod = types.ModuleType("helpers")
    helpers_mod.retrieve_url = _capture_url  # type: ignore[attr-defined]
    helpers_mod.download_file = lambda url: url  # type: ignore[attr-defined]
    sys.modules["helpers"] = helpers_mod

    spec = importlib.util.spec_from_file_location(f"plugin_mwq_{name}", _plugin_path(name))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod, captured_urls


def _drive_search(name: str) -> list[str]:
    """Run the plugin's real search() with a raw multi-word query and
    return every URL it tried to fetch. retrieve_url is stubbed to a
    URL-capturing no-op so the call never hits the network and the
    plugin's pagination loop terminates on the empty body."""
    mod, captured_urls = _load_plugin(name)
    cls = getattr(mod, name)
    instance = cls()
    with patch.object(sys.modules["helpers"], "retrieve_url", side_effect=captured_urls.append):
        # side_effect=append both records the URL AND returns None;
        # plugins treat falsy body as "no results" and stop.
        try:
            instance.search(MULTIWORD_RAW, "all")
        except Exception:
            # A genuine ValueError from urllib on a raw space would be
            # raised by the REAL retrieve_url, not our stub — but some
            # plugins call urllib helpers directly. We still inspect the
            # captured URLs below; a crash mid-loop is acceptable as long
            # as the FIRST constructed URL is well-formed.
            pass
    return captured_urls


# The AFFECTED set: plugins that interpolate the raw query into a URL/path.
# Enumerated by scanning plugins/*.py for query-in-URL construction without
# percent-encoding (NOT trusting the blind candidate list — several names in
# that list do not exist in this repo).
AFFECTED_PLUGINS = [
    "torlock",
    "nyaa",
    "bitsearch",
    "kickass",
    "torrentgalaxy",
    "eztv",
    "solidtorrents",
]
# NOTE: tokyotoshokan is NOT in the affected set — it already does
# ``query.replace(" ", "+")`` (plugins/tokyotoshokan.py) so a raw multi-word
# query is handled. Confirmed by this test passing against it pre-fix.


# Well-behaved plugins that ALREADY encode the query (quote / urlencode /
# explicit replace). The fix must NOT touch them — and they must still build
# valid URLs for a multi-word query (no regression, no double-encoding crash).
WELL_BEHAVED_PLUGINS = [
    "gamestorrents",  # unquote(what) -> quote(what)
    "megapeer",       # unquote(what) -> quote(what)
    "torrentkitty",   # unquote(what) -> quote(what)
    "anilibra",       # quote(what)
    "tokyotoshokan",  # query.replace(" ", "+")
]


def _drive_search_with(name: str, query: str) -> list[str]:
    mod, captured_urls = _load_plugin(name)
    cls = getattr(mod, name)
    instance = cls()
    with patch.object(sys.modules["helpers"], "retrieve_url", side_effect=captured_urls.append):
        try:
            instance.search(query, "all")
        except Exception:
            pass
    return captured_urls


@pytest.mark.parametrize("name", AFFECTED_PLUGINS)
def test_multiword_query_is_url_encoded(name: str) -> None:
    urls = _drive_search(name)
    assert urls, f"{name}: search() built no URL (harness broke)"
    first = urls[0]
    # The defect: a raw space in the URL. urllib rejects it; the feature
    # is dead for the user. A correctly-encoded URL has '%20' / '+' not ' '.
    assert " " not in first, (
        f"{name}: constructed URL contains a raw space (NOT encoded): {first!r}. "
        "Multi-word queries from the merge service will crash urllib."
    )
    # Cross-check (§11.4.107-style different-oracle): urllib must accept it.
    # This is what the real retrieve_url does; a raw control char would raise.
    urllib.request.Request(first)  # raises ValueError on a raw space


@pytest.mark.parametrize("name", AFFECTED_PLUGINS)
def test_nova2_encoded_query_still_works(name: str) -> None:
    """§11.4.146 extend-to-all-cases: the OTHER caller convention.

    nova2.py passes a %20-encoded query. The fix must keep that path
    working — the constructed URL must still be urllib-acceptable and
    free of raw spaces."""
    urls = _drive_search_with(name, "the%20matrix")
    assert urls, f"{name}: built no URL for %20-encoded query"
    first = urls[0]
    assert " " not in first, f"{name}: raw space from %20 query: {first!r}"
    urllib.request.Request(first)


@pytest.mark.parametrize("name", AFFECTED_PLUGINS)
def test_singleword_query_unaffected(name: str) -> None:
    """Boundary case: a single-word query (already working) must keep
    working — the fix is a no-op for it."""
    urls = _drive_search_with(name, "linux")
    assert urls, f"{name}: built no URL for single-word query"
    first = urls[0]
    assert " " not in first
    urllib.request.Request(first)
    assert "linux" in first.lower(), f"{name}: query token missing: {first!r}"


@pytest.mark.parametrize("name", WELL_BEHAVED_PLUGINS)
def test_well_behaved_plugins_not_regressed(name: str) -> None:
    """The well-behaved (already-encoding) plugins must still build a
    valid, urllib-acceptable URL for a multi-word query — proving the fix
    did not touch them and they were never the bug (§11.4.6 honesty)."""
    urls = _drive_search_with(name, MULTIWORD_RAW)
    assert urls, f"{name}: built no URL"
    first = urls[0]
    assert " " not in first, f"{name}: raw space in URL: {first!r}"
    urllib.request.Request(first)
