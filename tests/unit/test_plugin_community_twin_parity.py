"""§11.4.146 / §11.4.251 guard: plugins/community/<X>.py must not drift from plugins/<X>.py.

WHY THIS FILE EXISTS (measured gap, 2026-09-02).
``install-plugin.sh`` resolves ``plugins/<name>.py`` FIRST and only falls back
to ``plugins/community/<name>.py`` when the top-level file is absent
(install-plugin.sh, the ``plugin_file=`` resolution block). For every name that
exists in BOTH directories the top-level copy is therefore the LIVE engine and
the community copy is a dead twin that qBittorrent never loads.

That asymmetry is exactly what let the twins rot. Commit ae387b2
("UTF-8/Cyrillic query encoding — 14 plugins crashed on non-ASCII") touched 14
files, ALL under ``plugins/`` and ZERO under ``plugins/community/``. The
existing outbound guard ``test_plugin_unicode_query_encoding.py`` could not
catch it: its ``_plugin_path()`` helper resolves top-level first, mirroring
install-plugin.sh, so it drove the fixed copy every time and the stale twin
stayed green by never being executed at all.

Two measured, user-visible defects the drift preserved in the dead twins:

  * ``plugins/community/*.py`` (11 engines) still built URLs with RAW Cyrillic,
    the exact input that crashed the live stack with
    ``'ascii' codec can't encode characters``.
  * ``plugins/community/megapeer.py`` iterated
    ``{"B": 1, "KB": 1024, ...}`` with ``if unit in size_str``. "B" is a
    SUBSTRING of KB/MB/GB/TB and dict order put it first, so "1.5 GB" matched
    "B", ``.replace("B","")`` left ``"1.5 G"``, ``float()`` raised, and the
    handler returned 0 — EVERY realistically-sized result reported size 0.

ANTI-BLUFF (§11.4/§11.4.1). The size assertions compare against EXACT byte
counts and the query assertions compare the decoded URL against the EXPECTED
CYRILLIC STRING. A test asserting only "no exception" or "a URL was built"
passes against both defects above (mojibake raises nothing; a 0-byte size
raises nothing) and is precisely the bluff this file exists to prevent.

POLARITY (§11.4.115). Reverting any community twin to its pre-port content
makes the matching case FAIL: the byte-identity case on the diff, the encoding
cases on the raw non-ASCII URL, the megapeer case on ``0 != 1610612736``.
"""

from __future__ import annotations

import http.client
import importlib.util
import sys
import types
import urllib.parse
from pathlib import Path
import pytest

REPO = Path(__file__).resolve().parents[2]
PLUGINS = REPO / "plugins"
COMMUNITY = PLUGINS / "community"

# A real Cyrillic multi-word query, passed RAW (literal space + non-ASCII) the
# way the merge service passes it — the exact value-class that produced
# ``UnicodeEncodeError: 'ascii' codec can't encode`` on the live stack.
CYRILLIC_RAW = "Война и мир"

_DISALLOWED_URL_CHAR_RE = http.client._contains_disallowed_url_pchar_re  # noqa: SLF001


def _twin_names() -> list[str]:
    """Every engine that exists in BOTH plugins/ and plugins/community/."""
    return sorted(p.stem for p in COMMUNITY.glob("*.py") if (PLUGINS / p.name).exists())


TWINS = _twin_names()

# Twins whose live copy carries the ae387b2 Cyrillic percent-encoding fix, so
# the ported community copy must carry it too. ``snowfl`` is excluded from the
# search-driving cases for the same reason the original outbound suite excludes
# it (its search() bootstraps a token before building the query URL); its
# byte-identity is still asserted below.
CYRILLIC_FIXED_TWINS = [
    "glotorrents",
    "linuxtracker",
    "pirateiro",
    "rockbox",
    "tokyotoshokan",
    "torlock",
    "torrentdownload",
    "torrentproject",
    "torrentscsv",
    "yourbittorrent",
]


def _assert_url_ascii_and_urllib_safe(url: str, ctx: str = "") -> None:
    """urllib encodes the request line as ASCII (``putrequest`` ->
    ``request.encode('ascii')``); a non-ASCII char raises the exact live-stack
    UnicodeEncodeError. Cross-checked against urllib's own control-char
    predicate, which bites on a raw space."""
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


def _load_community_plugin(name: str) -> tuple[types.ModuleType, list[str]]:
    """Import plugins/community/<name>.py EXPLICITLY (never the top-level
    twin), outside the nova3 harness, with stubbed deps.

    The URL-capturing ``retrieve_url`` is installed into the ``helpers`` stub
    BEFORE ``exec_module``. That ordering is load-bearing: these plugins do
    ``from helpers import retrieve_url`` at import time, binding the function
    object into their OWN module namespace, so patching ``helpers.retrieve_url``
    AFTER the import would leave the plugin calling the un-patched original and
    the capture list would come back empty — a silent false PASS on every
    "did the URL get encoded" assertion (§11.4.201(6) false-null).
    """
    path = COMMUNITY / f"{name}.py"
    assert path.exists(), f"community twin missing: {path}"

    captured: list[str] = []

    np_mod = types.ModuleType("novaprinter")
    np_mod.prettyPrinter = lambda d: None  # type: ignore[attr-defined]

    class _SR:
        pass

    np_mod.SearchResults = _SR  # type: ignore[attr-defined]
    sys.modules["novaprinter"] = np_mod

    def _capture(url, *args, **kwargs):
        captured.append(url)
        return ""  # empty body -> plugin parses 0 rows and ends its page loop

    helpers_mod = types.ModuleType("helpers")
    helpers_mod.retrieve_url = _capture  # type: ignore[attr-defined]
    helpers_mod.download_file = lambda url: url  # type: ignore[attr-defined]
    sys.modules["helpers"] = helpers_mod

    spec = importlib.util.spec_from_file_location(f"community_twin_{name}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod, captured


def _drive_community_search(name: str, query: str) -> list[str]:
    """Run the COMMUNITY twin's real search() and return every URL it tried to
    fetch. No network call is made and the empty body terminates the loop."""
    mod, captured = _load_community_plugin(name)
    instance = getattr(mod, name)()
    try:
        instance.search(query, "all")
    except Exception:
        # Pre-port code raises UnicodeEncodeError from the REAL retrieve_url
        # while building the URL; the captured list still holds it, and the
        # assertions below inspect it.
        pass
    return captured


# --------------------------------------------------------------------------
# 1. Structural parity — the guard whose absence let ae387b2 skip the twins.
# --------------------------------------------------------------------------


def test_twin_set_is_non_empty() -> None:
    """Control needle (§11.4.201(7)(b)): if the discovery glob silently matched
    nothing, every parametrized case below would vacuously pass."""
    assert len(TWINS) >= 15, f"twin discovery returned only {len(TWINS)}: {TWINS}"


@pytest.mark.parametrize("name", TWINS)
def test_community_twin_is_byte_identical_to_live(name: str) -> None:
    """install-plugin.sh loads plugins/<name>.py and never the community twin,
    so a fix landing only on the live copy is invisible until someone deletes
    the live file. Byte-identity is the invariant that makes that drift a
    build-time failure instead of a silent one."""
    live = (PLUGINS / f"{name}.py").read_bytes()
    twin = (COMMUNITY / f"{name}.py").read_bytes()
    assert live == twin, (
        f"{name}: plugins/community/{name}.py has DRIFTED from the live "
        f"plugins/{name}.py ({len(live)} vs {len(twin)} bytes). A fix landed on "
        f"one copy only — port it across (do not delete either file)."
    )


# --------------------------------------------------------------------------
# 2. Cyrillic query encoding, driven through the COMMUNITY twin's real path.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", CYRILLIC_FIXED_TWINS)
def test_community_twin_cyrillic_query_is_url_encoded(name: str) -> None:
    """RED-on-broken (§11.4.115): the pre-port twin interpolated raw Cyrillic
    into the URL and urllib's ASCII encode raised; post-port it is
    percent-encoded and ASCII-safe."""
    urls = _drive_community_search(name, CYRILLIC_RAW)
    assert urls, f"{name}: community search() built no URL (harness broke)"
    first = urls[0]
    assert " " not in first, (
        f"{name}: community twin URL contains a raw space (NOT encoded): {first!r}"
    )
    _assert_url_ascii_and_urllib_safe(first, f"community/{name}: ")


@pytest.mark.parametrize("name", CYRILLIC_FIXED_TWINS)
def test_community_twin_cyrillic_query_round_trips(name: str) -> None:
    """The encoding must be REVERSIBLE and LOSSLESS: percent-decoding the URL
    recovers the ORIGINAL Cyrillic tokens by equality. This is what separates a
    real fix from one that dropped, transliterated, or mojibake'd the query —
    none of which raise."""
    urls = _drive_community_search(name, CYRILLIC_RAW)
    assert urls, f"{name}: community twin built no URL"
    first = urls[0]
    # unquote_plus decodes BOTH %XX and '+', covering the query-param ('+') and
    # path ('%20') conventions in one shot.
    decoded = urllib.parse.unquote_plus(first)
    # torlock / yourbittorrent join words with '-', so the whole phrase will not
    # appear; each Cyrillic WORD must survive the round-trip exactly.
    for word in CYRILLIC_RAW.split():
        assert word in decoded, (
            f"community/{name}: Cyrillic token {word!r} did not survive the URL "
            f"round-trip: url={first!r} decoded={decoded!r}"
        )


@pytest.mark.parametrize("name", CYRILLIC_FIXED_TWINS)
def test_community_twin_no_double_encode_of_nova2_query(name: str) -> None:
    """nova2 hands the plugin an ALREADY percent-encoded query. The ported fix
    unquotes first, so the value is encoded exactly once and still decodes back
    to the original Cyrillic — a double-encode would leave %25D0-style garbage
    that no longer round-trips."""
    pre_encoded = urllib.parse.quote(CYRILLIC_RAW)
    urls = _drive_community_search(name, pre_encoded)
    assert urls, f"{name}: community twin built no URL for pre-encoded query"
    first = urls[0]
    assert " " not in first, f"community/{name}: raw space from pre-encoded query: {first!r}"
    _assert_url_ascii_and_urllib_safe(first, f"community/{name}: ")
    decoded = urllib.parse.unquote_plus(first)
    for word in CYRILLIC_RAW.split():
        assert word in decoded, (
            f"community/{name}: Cyrillic token {word!r} lost (double-encode?): "
            f"url={first!r} decoded={decoded!r}"
        )


# --------------------------------------------------------------------------
# 3. The size-parse defect the drift preserved — asserted on exact byte counts.
# --------------------------------------------------------------------------

# ("1.5 GB" is the canonical case: "B" is a substring of "GB", so the pre-port
# ordering matched "B" first and the result collapsed to 0.)
SIZE_CASES = [
    ("1.5 GB", 1610612736),
    ("2 TB", 2199023255552),
    ("512 MB", 536870912),
    ("700 KB", 716800),
]


@pytest.mark.parametrize("engine", ["megapeer", "torrentkitty"])
@pytest.mark.parametrize(("raw", "expected"), SIZE_CASES)
def test_community_twin_parses_size_to_exact_bytes(engine: str, raw: str, expected: int) -> None:
    """Exact-value assertion (§11.4/§11.4.1). The pre-port community twins
    returned 0 for every one of these — a silent, non-raising, user-visible
    defect (every result showed as 0 bytes in the WebUI). Asserting "> 0" or
    "no exception" would NOT have caught it; asserting the exact byte count
    does."""
    mod, _ = _load_community_plugin(engine)
    instance = getattr(mod, engine)()
    got = instance._parse_size(raw)  # noqa: SLF001
    assert got == expected, (
        f"community/{engine}._parse_size({raw!r}) = {got}, expected {expected}. "
        f"A 0 here is the substring-ordering defect: 'B' matched inside "
        f"'GB'/'MB'/'KB'/'TB' before the longer unit did."
    )


@pytest.mark.parametrize("engine", ["megapeer", "torrentkitty"])
def test_community_twin_size_parse_matches_live_twin(engine: str) -> None:
    """Cross-oracle (§11.4.107): the community twin and the live engine must
    agree on every case, so neither copy can regress independently."""
    twin_mod, _ = _load_community_plugin(engine)
    twin = getattr(twin_mod, engine)()

    spec = importlib.util.spec_from_file_location(f"live_{engine}", PLUGINS / f"{engine}.py")
    live_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(live_mod)  # type: ignore[union-attr]
    live = getattr(live_mod, engine)()

    for raw, _expected in SIZE_CASES:
        assert twin._parse_size(raw) == live._parse_size(raw), (  # noqa: SLF001
            f"{engine}: community twin and live engine disagree on {raw!r}"
        )
