"""§11.4.146 reproduce-first regression guard: NON-ASCII (Cyrillic) query URL-encoding.

ROOT CAUSE (FACT, characterised 2026-06-16 on the live nezha stack):
The multi-word fix (see ``test_plugin_multiword_query_encoding.py``) only
``.replace(" ", ...)``-ed SPACES; it did NOT percent-encode non-ASCII (UTF-8)
characters. So a Cyrillic query such as "Война и мир" still reaches
``helpers.retrieve_url`` -> urllib with raw non-ASCII bytes in the URL string.
On the live stack the engine wrapper crashed with::

    {"__error__": "'ascii' codec can't encode characters in position N:
                   ordinal not in range(128)"}

i.e. urllib/http.client tried to ASCII-encode the URL and raised
``UnicodeEncodeError``. The robust fix percent-encodes the query with
``urllib.parse.quote(query, safe="")`` (for PATH segments: space -> %20 + UTF-8
percent-encoded) or ``urllib.parse.quote_plus(query)`` (for ``?key=`` QUERY
params: space -> + + UTF-8 percent-encoded), at the point the query enters the
URL — so the query is ASCII-safe regardless of the caller's encoding
(§11.4.111 resolve by a stable, caller-independent encoding).

This test drives the REAL plugin ``search()`` with a Cyrillic query and
captures the URL handed to ``retrieve_url``; it asserts the constructed URL is
ASCII-only (no non-ASCII byte), contains no raw space, is urllib-acceptable,
AND that the query round-trips (percent-decode -> original Cyrillic).

Polarity (§11.4.115): RED_MODE=1 (default) reproduces the defect on the pre-fix
plugins (non-ASCII char present / ascii-codec crash) and asserts it is ABSENT
post-fix — the SAME assertion is the standing GREEN guard.
"""

from __future__ import annotations

import http.client
import importlib.util
import sys
import types
import urllib.parse
from pathlib import Path
from unittest.mock import patch

import pytest

REPO = Path(__file__).resolve().parents[2]
PLUGINS = REPO / "plugins"
COMMUNITY = PLUGINS / "community"

# Cyrillic multi-word query as the merge service would pass it: RAW, with a
# literal space AND non-ASCII characters. This is the exact value-class that
# triggered the 'ascii' codec UnicodeEncodeError on the live nezha stack.
CYRILLIC_RAW = "Война и мир"

# The AUTHORITATIVE urllib oracle (§11.4.107 different-domain cross-check).
# http.client uses this regex in putrequest() to reject a URL; its pattern
# ([\x00-\x20\x7f]) bites on a raw space. We ALSO assert the URL is pure ASCII
# below, because a non-ASCII char does NOT match this regex but still crashes
# urllib at the ``url.encode('ascii')`` step (the actual nezha failure).
_DISALLOWED_URL_CHAR_RE = http.client._contains_disallowed_url_pchar_re  # noqa: SLF001


def _assert_url_ascii_and_urllib_safe(url: str, ctx: str = "") -> None:
    """Two cross-oracles, both required:

    1. ASCII-only — urllib/http.client encodes the request line as ASCII
       (``putrequest`` -> ``self._output(request.encode('ascii'))``); a
       non-ASCII char raises ``UnicodeEncodeError: 'ascii' codec can't
       encode`` — the EXACT live-stack crash. So the URL string must contain
       no non-ASCII char.
    2. No disallowed control char (raw space among them) — urllib's own
       predicate, reliable on py3.12 AND py3.13 alike.
    """
    try:
        url.encode("ascii")
    except UnicodeEncodeError as exc:  # pragma: no cover - asserted below
        pytest.fail(
            f"{ctx}constructed URL is NOT ASCII (urllib would raise "
            f"'ascii' codec can't encode): {url!r} ({exc})"
        )
    assert _DISALLOWED_URL_CHAR_RE.search(url) is None, (
        f"{ctx}urllib would reject the constructed URL "
        f"(disallowed control char present): {url!r}"
    )


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
        return ""  # empty body -> plugin parses 0 rows, terminates its loop

    helpers_mod = types.ModuleType("helpers")
    helpers_mod.retrieve_url = _capture_url  # type: ignore[attr-defined]
    helpers_mod.download_file = lambda url: url  # type: ignore[attr-defined]
    sys.modules["helpers"] = helpers_mod

    spec = importlib.util.spec_from_file_location(f"plugin_uq_{name}", _plugin_path(name))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod, captured_urls


def _drive_search_with(name: str, query: str) -> list[str]:
    """Run the plugin's real search() and return every URL it tried to fetch.
    retrieve_url is stubbed to a URL-capturing no-op so no network call is made
    and the pagination loop terminates on the empty body."""
    mod, captured_urls = _load_plugin(name)
    cls = getattr(mod, name)
    instance = cls()
    with patch.object(sys.modules["helpers"], "retrieve_url", side_effect=captured_urls.append):
        try:
            instance.search(query, "all")
        except Exception:
            # A genuine UnicodeEncodeError from the REAL retrieve_url would be
            # raised here on pre-fix code; we still inspect the captured URLs.
            pass
    return captured_urls


# The AFFECTED set: the 15 plugins that interpolate the raw query into a
# URL/path WITHOUT percent-encoding non-ASCII chars. tokyotoshokan + yts were
# NOT in the earlier multi-word set; both are included here.
AFFECTED_PLUGINS = [
    "bitsearch",
    "glotorrents",
    "linuxtracker",
    "nyaa",
    "pirateiro",
    "rockbox",
    # snowfl is covered by the dedicated test below (token bootstrap).
    "tokyotoshokan",
    "torlock",
    "torrentdownload",
    "torrentgalaxy",
    "torrentproject",
    "torrentscsv",
    "yourbittorrent",
    "yts",
]


@pytest.mark.parametrize("name", AFFECTED_PLUGINS)
def test_cyrillic_query_is_url_encoded(name: str) -> None:
    """RED-on-broken (§11.4.115): a Cyrillic query must not reach the URL as
    raw non-ASCII bytes. Pre-fix the URL carries the literal Cyrillic (or a raw
    space) and urllib's ASCII encode crashes; post-fix it is percent-encoded."""
    urls = _drive_search_with(name, CYRILLIC_RAW)
    assert urls, f"{name}: search() built no URL (harness broke)"
    first = urls[0]
    # The defect: non-ASCII chars (or a raw space) in the URL string.
    assert " " not in first, (
        f"{name}: constructed URL contains a raw space (NOT encoded): {first!r}."
    )
    _assert_url_ascii_and_urllib_safe(first, f"{name}: ")


@pytest.mark.parametrize("name", AFFECTED_PLUGINS)
def test_cyrillic_query_round_trips(name: str) -> None:
    """§11.4.146 extend: the encoding must be REVERSIBLE — percent-decoding
    the URL recovers the original Cyrillic query (proves the fix encoded the
    real query, not dropped/mangled it). We decode the whole URL and assert the
    original tokens are present."""
    urls = _drive_search_with(name, CYRILLIC_RAW)
    assert urls, f"{name}: built no URL"
    first = urls[0]
    # unquote_plus decodes BOTH %XX and '+', covering query-param ('+') and
    # path ('%20') conventions in one shot.
    decoded = urllib.parse.unquote_plus(first)
    # Some plugins replace space with '-' (torlock, yourbittorrent); for those
    # the spaces become '-' so the joined phrase won't match, but the
    # individual Cyrillic WORDS must survive the encode/decode round-trip.
    for word in CYRILLIC_RAW.split():
        assert word in decoded, (
            f"{name}: Cyrillic token {word!r} lost in URL round-trip: "
            f"url={first!r} decoded={decoded!r}"
        )


@pytest.mark.parametrize("name", AFFECTED_PLUGINS)
def test_nova2_percent_encoded_cyrillic_still_works(name: str) -> None:
    """§11.4.146 extend-to-all-cases: the nova2 caller passes an ALREADY
    percent-encoded query. The fix must not double-encode it into garbage —
    the URL stays ASCII-safe and the Cyrillic still round-trips."""
    pre_encoded = urllib.parse.quote(CYRILLIC_RAW)  # %D0%92...%20... style
    urls = _drive_search_with(name, pre_encoded)
    assert urls, f"{name}: built no URL for pre-encoded query"
    first = urls[0]
    assert " " not in first, f"{name}: raw space from pre-encoded query: {first!r}"
    _assert_url_ascii_and_urllib_safe(first, f"{name}: ")
    decoded = urllib.parse.unquote_plus(first)
    for word in CYRILLIC_RAW.split():
        assert word in decoded, (
            f"{name}: Cyrillic token {word!r} lost (double-encode?): "
            f"url={first!r} decoded={decoded!r}"
        )


def test_snowfl_cyrillic_path_encoded() -> None:
    """snowfl builds the query into a URL PATH segment via
    ``Parser.generateQuery``; its token bootstrap (index.html + script) can't
    be driven under the simple stub, so verify the fix directly: the value
    reaching generateQuery for a Cyrillic query must be ASCII-only,
    %20-encoded (not '+', literal in a path), and round-trip back to the
    original Cyrillic."""
    mod, _ = _load_plugin("snowfl")
    cls = mod.snowfl
    inst = cls()
    captured: list[str] = []

    class _FakeParser:
        def __init__(self, url):
            self.url = url

        def generateQuery(self, what):
            captured.append(what)
            return f"{self.url}/dummy"

        def feed(self, data):  # noqa: ANN001
            pass

    with patch.object(cls, "Parser", _FakeParser):
        try:
            inst.search(CYRILLIC_RAW, "all")
        except Exception:
            pass
    assert captured, "snowfl: generateQuery was never reached"
    q = captured[0]
    # ASCII-only: a raw Cyrillic char in a path crashes urllib's ascii encode.
    try:
        q.encode("ascii")
    except UnicodeEncodeError as exc:  # pragma: no cover
        pytest.fail(f"snowfl: non-ASCII reached the path query: {q!r} ({exc})")
    assert " " not in q, f"snowfl: raw space in path query: {q!r}"
    assert "+" not in q, f"snowfl: '+' is literal in a path: {q!r}"
    decoded = urllib.parse.unquote(q)
    for word in CYRILLIC_RAW.split():
        assert word in decoded, f"snowfl: Cyrillic token {word!r} lost: {q!r}"
