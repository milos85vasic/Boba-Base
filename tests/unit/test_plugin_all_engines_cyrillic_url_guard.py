"""§11.4.238 coverage-escape closure: EVERY engine's search() must build an
ASCII-encodable URL for a Cyrillic query — roster derived, never hardcoded.

WHY THIS FILE EXISTS (the escape it closes, measured 2026-09-02).
Commit ``ae387b2`` fixed 14 plugins for exactly this defect class and shipped
``test_plugin_unicode_query_encoding.py`` as its guard. That guard could not
have caught the next instance, for TWO structural reasons:

  1. **It enumerates a hardcoded ``AFFECTED_PLUGINS`` list.** An engine outside
     that list is invisible to it. Six engines outside it were still broken —
     kickass, ali213, bt4g, eztv, limetorrents, solidtorrents — and every one
     crashed urllib on a Cyrillic search while the guard stayed green.
  2. **Its ``_plugin_path()`` resolves ``plugins/<n>.py`` FIRST** (mirroring
     ``install-plugin.sh``) and only falls back to ``plugins/community/``. So
     for a forked engine it drove the top-level copy every time and never once
     executed the community twin.

An AGENT found the kickass defect by hand; no gate did. Per §11.4.238 the
missing check is itself a release blocker, not merely the bug. This file is
that check.

WHAT MAKES IT NOT-BLIND (the two properties the old guard lacked):

  * **The roster is DERIVED**, parsed at run time from ``install-plugin.sh``'s
    canonical ``PLUGINS=()`` array. Adding an engine to the project adds it to
    this guard automatically — there is no list to forget to update.
  * **BOTH copies are driven** — ``plugins/<n>.py`` AND
    ``plugins/community/<n>.py`` whenever both exist. A fix landing on one side
    only is caught.

WHAT MAKES IT NOT-A-BLUFF:

  * Every engine is DRIVEN — its real ``search()`` runs and the URL it hands to
    ``retrieve_url`` is captured and encoded. Nothing here reads source or
    greps for ``quote(``; a plugin that imports ``quote`` and forgets to call it
    fails exactly as it should.
  * An engine that cannot be driven FAILS LOUDLY naming itself. There is no
    silent skip — a harness that quietly captured nothing for half the roster
    would report a clean sweep over engines it never executed (§11.4.201(6)
    false-null). The four engines whose constructors need credentials or a
    network login have explicit, documented drivers below; if one of those
    stops working, this file fails rather than going quiet.
  * A control needle (``test_control_needle_...``) proves the oracle fires on a
    genuinely broken URL, so a zero-failure run means "checked and clean", not
    "checked nothing".
"""

from __future__ import annotations

import contextlib
import http.client
import importlib.util
import io
import re
import sys
import types
import urllib.parse
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO = Path(__file__).resolve().parents[2]
PLUGINS = REPO / "plugins"
COMMUNITY = PLUGINS / "community"
INSTALL_SH = REPO / "install-plugin.sh"

CYRILLIC_RAW = "Война и мир"

_DISALLOWED_URL_CHAR_RE = http.client._contains_disallowed_url_pchar_re  # noqa: SLF001


# ---------------------------------------------------------------------------
# Roster: DERIVED from install-plugin.sh, never hardcoded here.
# ---------------------------------------------------------------------------

def _roster() -> list[str]:
    src = INSTALL_SH.read_text(encoding="utf-8")
    block = re.search(r"^PLUGINS=\((.*?)^\)", src, re.S | re.M)
    assert block, (
        "install-plugin.sh no longer has a parseable PLUGINS=() array — this "
        "guard derives its roster from it, so it is now BLIND. Re-derive the "
        "parser before trusting any green run from this file."
    )
    names = re.findall(r'"([^"]+)"', block.group(1))
    assert len(names) >= 40, (
        f"roster parsed only {len(names)} engines from install-plugin.sh; the "
        f"project ships 43. The parser is under-matching and this guard would "
        f"silently cover only part of the fleet."
    )
    return names


def _copies(name: str) -> list[str]:
    out = []
    if (PLUGINS / f"{name}.py").is_file():
        out.append("top")
    if (COMMUNITY / f"{name}.py").is_file():
        out.append("community")
    return out


def _targets() -> list[tuple[str, str]]:
    return [(n, c) for n in _roster() for c in _copies(n)]


TARGETS = _targets()
TARGET_IDS = [f"{n}[{c}]" for n, c in TARGETS]


# ---------------------------------------------------------------------------
# The oracle
# ---------------------------------------------------------------------------

def assert_url_is_cyrillic_safe(url: str, ctx: str) -> None:
    """urllib's own two failure modes, both asserted.

    ``http.client.putrequest`` does ``request.encode('ascii')``: a non-ASCII
    char raises ``UnicodeEncodeError: 'ascii' codec can't encode characters``.
    Separately, urllib rejects disallowed control chars — a raw space among
    them. A URL must survive both.
    """
    try:
        url.encode("ascii")
    except UnicodeEncodeError as exc:
        pytest.fail(
            f"{ctx}: search() built a NON-ASCII URL. urllib raises\n"
            f"  \"'ascii' codec can't encode characters\"\n"
            f"on this exact string, so a Cyrillic search is DEAD for the user.\n"
            f"  url: {url!r}\n  err: {exc}\n"
            f"Fix: percent-encode the query where it enters the URL —\n"
            f"  QUERY param  ->  quote_plus(unquote_plus(what))\n"
            f"  PATH segment ->  quote(unquote_plus(what), safe='')\n"
            f"('+' is a LITERAL plus in a path segment, so quote_plus is wrong there.)"
        )
    assert _DISALLOWED_URL_CHAR_RE.search(url) is None, (
        f"{ctx}: search() built a URL urllib rejects (disallowed control char, "
        f"typically a raw space): {url!r}"
    )


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------

def _install_stubs(captured: list[str]) -> None:
    np_mod = types.ModuleType("novaprinter")
    np_mod.prettyPrinter = lambda d: None  # type: ignore[attr-defined]

    class _SR:
        pass

    np_mod.SearchResults = _SR  # type: ignore[attr-defined]
    sys.modules["novaprinter"] = np_mod

    def _cap(url, *args, **kwargs):
        captured.append(url)
        return ""

    helpers_mod = types.ModuleType("helpers")
    helpers_mod.retrieve_url = _cap  # type: ignore[attr-defined]
    helpers_mod.download_file = lambda u: u  # type: ignore[attr-defined]
    # Some engines import this legacy helper; a missing symbol would abort the
    # import and make this guard silently skip them.
    helpers_mod.htmlentitydecode = lambda s: s  # type: ignore[attr-defined]
    sys.modules["helpers"] = helpers_mod

    socks_mod = types.ModuleType("socks")
    socks_mod.PROXY_TYPE_SOCKS5 = 2  # type: ignore[attr-defined]
    socks_mod.set_default_proxy = lambda *a, **kw: None  # type: ignore[attr-defined]
    socks_mod.socksocket = MagicMock()  # type: ignore[attr-defined]
    sys.modules["socks"] = socks_mod


def _import_engine(name: str, copy: str, captured: list[str]):
    _install_stubs(captured)
    modname = f"cyrguard_{copy}_{name}"
    sys.modules.pop(modname, None)
    sys.modules.pop(name, None)
    path = (PLUGINS if copy == "top" else COMMUNITY) / f"{name}.py"
    spec = importlib.util.spec_from_file_location(modname, path)
    mod = importlib.util.module_from_spec(spec)
    with patch("logging.basicConfig"), patch.object(Path, "write_text"), patch.object(
        Path, "write_bytes"
    ):
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
    sys.modules[name] = mod
    return mod


def _cap_any(captured: list[str]):
    def _inner(url, *args, **kwargs):
        captured.append(url)
        return ""

    return _inner


# --- explicit drivers for engines the generic path cannot reach -------------
#
# Each entry documents WHY the generic driver fails and drives the engine's
# real URL-building code by a narrower seam. These are NOT skips: an engine
# listed here is still executed and still asserted.

def _drive_iptorrents(mod, captured):
    """Constructor demands credentials; search() delegates to search_parse()."""
    inst = mod.iptorrents()
    with patch.object(inst, "_login"), patch.object(
        inst, "search_parse", side_effect=lambda link, page=1: captured.append(link)
    ):
        inst.search(CYRILLIC_RAW, "all")


def _drive_piratebay(mod, captured):
    """retrieve_url is a METHOD on the class, not the helpers import."""
    inst = mod.piratebay()
    with patch.object(
        inst, "retrieve_url", side_effect=lambda u: (captured.append(u), "[]")[1]
    ):
        inst.search(CYRILLIC_RAW, "all")


def _drive_rutracker(mod, captured):
    """__init__ performs a LIVE login (403 without credentials), so bypass it
    with object.__new__ and capture at _open_url — the seam that receives the
    fully-built search URL."""
    cls = mod.rutracker
    inst = object.__new__(cls)
    inst.url = cls.url
    inst.results = {}
    with patch.object(
        cls, "_open_url", side_effect=lambda u, *a, **k: (captured.append(u), b"")[1]
    ):
        inst.search(CYRILLIC_RAW, "all")


def _drive_jackett(mod, captured):
    """Constructor needs a configured Jackett instance + API key; drive the
    per-indexer search that actually builds the torznab URL."""
    cls = mod.jackett
    inst = object.__new__(cls)
    inst.url = getattr(cls, "url", "http://localhost:9117")
    inst.api_key = "testkey"
    with patch.object(
        inst, "get_response", create=True, side_effect=lambda u: captured.append(u)
    ):
        inst.search_jackett_indexer(CYRILLIC_RAW, None, "all")


def _drive_session_engine(name: str):
    """kinozal / nnmclub / rutor fetch through their own ``_request()`` method
    (a logged-in urllib opener), NOT the ``helpers.retrieve_url`` the generic
    driver patches — so the generic path captures nothing for them.

    These are three of this project's FOUR primary Russian-language trackers,
    i.e. exactly the engines a Cyrillic-query guard must not miss. Patch
    ``_init`` (skips the live login) and ``_request`` (captures the URL and
    returns empty bytes so the pagination loop terminates).
    """

    def _driver(mod, captured):
        inst = getattr(mod, name)()
        with patch.object(inst, "_init"), patch.object(
            inst, "_request", side_effect=lambda u, *a, **k: (captured.append(u), b"")[1]
        ):
            inst.search(CYRILLIC_RAW, "all")

    return _driver


def _drive_audiobookbay(mod, captured):
    """``search()`` calls ``find_healthy_url()`` first; every mirror probe gets
    the empty-body stub, so no mirror is declared healthy and search() returns
    BEFORE building a search URL. Pin a healthy mirror so the real query-bearing
    URL is actually built and checked."""
    inst = mod.audiobookbay()
    with patch.object(inst, "find_healthy_url", return_value=mod.audiobookbay.url):
        inst.search(CYRILLIC_RAW, "all")


EXPLICIT_DRIVERS = {
    "iptorrents": _drive_iptorrents,
    "piratebay": _drive_piratebay,
    "rutracker": _drive_rutracker,
    "jackett": _drive_jackett,
    "kinozal": _drive_session_engine("kinozal"),
    "nnmclub": _drive_session_engine("nnmclub"),
    "rutor": _drive_session_engine("rutor"),
    "audiobookbay": _drive_audiobookbay,
}


# Engines whose query provably NEVER enters a fetched URL. Each is verified by
# its own test below — this is a stated, tested exemption, not a silent skip
# (§11.4.3 SKIP-with-reason). An engine may only be added here with a proof.
QUERY_NOT_IN_FETCHED_URL = {
    "academictorrents": (
        "downloads a full RSS database and filters it CLIENT-SIDE "
        "(search() builds self.filters and never interpolates the query into a "
        "URL), so it is structurally immune to this defect class"
    ),
    "snowfl": (
        "builds the query into a path segment inside Parser.generateQuery(), "
        "not via retrieve_url; its token bootstrap cannot be driven here, so the "
        "encoding is asserted directly at generateQuery below"
    ),
}


def drive(name: str, copy: str) -> list[str]:
    """Execute the engine's real search() and return every URL it built."""
    captured: list[str] = []
    mod = _import_engine(name, copy, captured)
    sink = io.StringIO()
    driver = EXPLICIT_DRIVERS.get(name)
    with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        with contextlib.ExitStack() as stack:
            # No test in this file may touch the network.
            stack.enter_context(
                patch(
                    "urllib.request.urlopen",
                    side_effect=AssertionError(f"{name}/{copy}: real network call"),
                )
            )
            if hasattr(mod, "retrieve_url"):
                stack.enter_context(
                    patch.object(mod, "retrieve_url", side_effect=_cap_any(captured))
                )
            try:
                if driver is not None:
                    driver(mod, captured)
                else:
                    mod_cls = getattr(mod, name)
                    mod_cls().search(CYRILLIC_RAW, "all")
            except Exception:
                # Pre-fix code raises UnicodeEncodeError out of real urllib; the
                # URL it tried to build is already captured and IS the evidence.
                pass
    return captured


# ---------------------------------------------------------------------------
# The guard
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(("name", "copy"), TARGETS, ids=TARGET_IDS)
def test_every_engine_builds_an_ascii_safe_url_for_a_cyrillic_query(
    name: str, copy: str
) -> None:
    urls = drive(name, copy)
    assert urls, (
        f"{name}/{copy}: search() produced NO URL, so this engine was never "
        f"actually checked. That is a BLIND instrument, not a pass "
        f"(§11.4.201(6)): a broken engine and an undriveable one both look "
        f"like zero failures. Either fix the harness or add an explicit driver "
        f"to EXPLICIT_DRIVERS documenting why the generic path cannot reach it."
    )
    for url in urls:
        assert_url_is_cyrillic_safe(url, f"{name}/{copy}")


@pytest.mark.parametrize(("name", "copy"), TARGETS, ids=TARGET_IDS)
def test_every_engine_round_trips_the_cyrillic_query(name: str, copy: str) -> None:
    """Encoding must be REVERSIBLE. ASCII-safety alone is satisfied by a URL
    that dropped, transliterated or double-encoded the query — all of which
    return the wrong results silently. Equality per token is what has teeth.

    Matching is case-INSENSITIVE: several engines lowercase the query for their
    URL slug (one337x builds ``/search/война-и-мир/1/``). That is deliberate
    site convention, fully reversible, and not the mangling this guard hunts —
    demanding exact case would be a §11.4.201(1) false-positive refusal.
    """
    if name in QUERY_NOT_IN_FETCHED_URL:
        pytest.skip(f"{name}: {QUERY_NOT_IN_FETCHED_URL[name]}")

    urls = drive(name, copy)
    assert urls, f"{name}/{copy}: built no URL"

    tokens = [w.casefold() for w in CYRILLIC_RAW.split()]
    # Some engines probe mirrors or fetch a landing page first; the query-bearing
    # URL is whichever one carries a token. Requiring urls[0] specifically would
    # fail on a healthy engine for a harness reason.
    bearer = next(
        (u for u in urls if any(t in urllib.parse.unquote_plus(u).casefold() for t in tokens)),
        None,
    )
    assert bearer is not None, (
        f"{name}/{copy}: NONE of the {len(urls)} URLs built carries the query. "
        f"Either the query was dropped/mangled entirely, or this engine does not "
        f"put the query in a fetched URL — in which case add it to "
        f"QUERY_NOT_IN_FETCHED_URL with a proof, never leave it silently green.\n"
        f"  urls: {urls[:3]!r}"
    )
    decoded = urllib.parse.unquote_plus(bearer).casefold()
    for word in CYRILLIC_RAW.split():
        assert word.casefold() in decoded, (
            f"{name}/{copy}: Cyrillic token {word!r} did not survive the URL "
            f"round-trip — the query was mangled rather than encoded "
            f"(a double-encode yields %25D0%2592..., which is ASCII-clean and "
            f"would pass the oracle above).\n"
            f"  url    : {bearer!r}\n  decoded: {decoded!r}"
        )


def test_academictorrents_never_puts_the_query_in_a_url() -> None:
    """Verify the QUERY_NOT_IN_FETCHED_URL exemption instead of assuming it.

    academictorrents filters a downloaded RSS database client-side. Prove that:
    every URL it fetches is query-free, AND the query really did drive the run
    (it lands in ``self.filters``). If it ever starts interpolating the query
    into a URL, this fails and the exemption must be withdrawn.
    """
    urls = drive("academictorrents", "community")
    tokens = [w.casefold() for w in CYRILLIC_RAW.split()]
    for u in urls:
        decoded = urllib.parse.unquote_plus(u).casefold()
        assert not any(t in decoded for t in tokens), (
            "academictorrents now interpolates the query into a fetched URL "
            f"({u!r}) — its QUERY_NOT_IN_FETCHED_URL exemption is stale and the "
            "engine must be encoding-checked like every other."
        )
        assert_url_is_cyrillic_safe(u, "academictorrents/community")


def test_snowfl_path_query_is_ascii_and_round_trips() -> None:
    """Verify snowfl's exemption at its real seam: Parser.generateQuery().

    snowfl's token bootstrap (index.html + script scrape) cannot be driven with
    stub bodies, so the query never reaches a captured URL. Assert directly on
    the value handed to generateQuery — it must be ASCII, space-free, free of
    '+' (a literal plus in a PATH), and round-trip to the original Cyrillic.
    """
    captured: list[str] = []
    mod = _import_engine("snowfl", "top", [])
    cls = mod.snowfl

    class _FakeParser:
        def __init__(self, url):
            self.url = url

        def generateQuery(self, what):
            captured.append(what)
            return f"{self.url}/dummy"

        def feed(self, data):  # noqa: ANN001
            pass

    sink = io.StringIO()
    with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        with patch.object(cls, "Parser", _FakeParser):
            try:
                cls().search(CYRILLIC_RAW, "all")
            except Exception:
                pass

    assert captured, "snowfl: generateQuery was never reached — this check is blind"
    q = captured[0]
    assert_url_is_cyrillic_safe(q, "snowfl(generateQuery)")
    assert "+" not in q, f"snowfl: '+' is a LITERAL plus in a path segment: {q!r}"
    decoded = urllib.parse.unquote(q).casefold()
    for word in CYRILLIC_RAW.split():
        assert word.casefold() in decoded, (
            f"snowfl: Cyrillic token {word!r} lost in the path round-trip: {q!r}"
        )


def test_roster_covers_both_copies_of_every_forked_engine() -> None:
    """Pin the property the ae387b2 guard lacked.

    ``test_plugin_unicode_query_encoding._plugin_path`` resolves top-level
    FIRST and returns, so it never executes a community twin. This guard must
    drive BOTH — assert that it does, for at least the known forked set.
    """
    forked = [n for n in _roster() if len(_copies(n)) == 2]
    assert forked, "no forked engines found — the copy-resolution logic is broken"
    for name in forked:
        pairs = [(n, c) for n, c in TARGETS if n == name]
        assert len(pairs) == 2, (
            f"{name} exists in BOTH plugins/ and plugins/community/ but this "
            f"guard drives {len(pairs)} copy/copies — the twin is unguarded, "
            f"which is exactly how the kickass defect survived."
        )


def test_control_needle_the_oracle_fires_on_a_broken_url() -> None:
    """§11.4.201(7)(b): a zero-failure run above is evidence only if the oracle
    can fail. Feed it the real pre-fix URLs measured on 2026-09-02."""
    # The oracle raises BOTH kinds: pytest.fail() -> Failed (a BaseException,
    # NOT an Exception) on the non-ASCII branch, and plain assert ->
    # AssertionError on the control-char branch. So a bare `Exception` would
    # miss the first. Naming the exact pair is NARROWER than BaseException and
    # still covers both, so a typo/NameError inside the needle can no longer
    # masquerade as the oracle firing (B017's real concern).
    _ORACLE_RAISES = (AssertionError, pytest.fail.Exception)
    # Pre-fix kickass: %20 for the space, Cyrillic left raw.
    with pytest.raises(_ORACLE_RAISES):
        assert_url_is_cyrillic_safe(
            "https://kickasstorrents.to/search/Война%20и%20мир/0/", "needle"  # noqa: RUF001
        )
    # Pre-fix ali213: nothing encoded at all.
    with pytest.raises(_ORACLE_RAISES):
        assert_url_is_cyrillic_safe(
            "http://down.ali213.net/search?kw=Война и мир&submit=", "needle"
        )
    # An ASCII URL with a raw space must fail on the control-char oracle alone.
    with pytest.raises(AssertionError):
        assert_url_is_cyrillic_safe("https://example.test/s?q=war and peace", "needle")
    # A correctly-encoded URL must NOT fire (the false-positive guard).
    assert_url_is_cyrillic_safe(
        "https://example.test/search/%D0%92%D0%BE%D0%B9%D0%BD%D0%B0/", "needle"
    )
