"""§11.4.115 RED-first + §11.4.238 coverage-escape guard: the SIX engines that
commit ae387b2 ("UTF-8/Cyrillic query encoding — 14 plugins") MISSED.

WHY THIS FILE EXISTS (measured, 2026-09-02).
``ae387b2`` fixed 14 engines and ``test_plugin_unicode_query_encoding.py`` was
written to guard them. That guard enumerates a HARDCODED ``AFFECTED_PLUGINS``
list, so any engine outside the list is invisible to it — a discovery sweep
that stopped at 14 while the class was wider. Driving EVERY engine in
``install-plugin.sh``'s roster with a Cyrillic query found SIX more, each of
which crashed urllib on a Cyrillic search:

    engine          copy        pre-fix URL (measured)
    kickass         top+comm    .../search/Война%20и%20мир/0/
    ali213          community   ...search?kw=Война и мир&submit=
    bt4g            community   ...search?q=Война и мир&p=1
    eztv            top         ...//search/Война-и-мир
    limetorrents    top         .../search/all/Война-и-мир/seeds/1/
    solidtorrents   top         ...search?q=Война+и+мир&category=all...
    audiobookbay    community   .../page/1/?s=Война и мир&cat=...

audiobookbay was found only AFTER the fleet-wide guard grew a driver that pins
a healthy mirror: its ``find_healthy_url()`` short-circuits ``search()`` when no
mirror answers, so under a naive stub the search URL was never built and the
defect was invisible. That is the §11.4.201(6) false-null in miniature — an
un-driven engine and a clean engine both look like zero failures.

Every one hand-rolled a ``.replace(" ", <sep>)`` and left the non-ASCII
characters raw. urllib's ``putrequest`` ASCII-encodes the request line, so the
search dies with::

    'ascii' codec can't encode characters in position N: ordinal not in range(128)

This project's PRIMARY trackers are RuTracker / Kinozal / NNMClub / RuTor —
Cyrillic queries are the NORMAL case, not an edge case, and the operator's own
library contains "Король-лев 2: Гордость Симбы". A plugin that raises on a
Cyrillic search is broken for the main use case.

ANTI-BLUFF (§11.4/§11.4.1). Every assertion drives the REAL ``search()`` and
compares each Cyrillic token to the round-tripped URL BY EQUALITY. Asserting
only "no exception" or "len(urls) > 0" passes against mojibake and against a
query silently mangled into ASCII garbage — exactly the bluff this file exists
to prevent.

TWIN PARITY. kickass has a ``plugins/community/`` twin that is byte-identical
to the top-level copy (enforced by ``test_plugin_community_twin_parity.py``).
BOTH copies are driven here so a fix can never land on one side only.
"""

from __future__ import annotations

import http.client
import importlib.util
import io
import contextlib
import sys
import types
import urllib.parse
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO = Path(__file__).resolve().parents[2]
PLUGINS = REPO / "plugins"
COMMUNITY = PLUGINS / "community"

# Raw, as the merge service passes it: literal space AND non-ASCII characters.
CYRILLIC_RAW = "Война и мир"

# urllib's own predicate — a raw space is a disallowed URL pchar.
_DISALLOWED_URL_CHAR_RE = http.client._contains_disallowed_url_pchar_re  # noqa: SLF001


def _assert_url_ascii_and_urllib_safe(url: str, ctx: str) -> None:
    """The two cross-oracles urllib actually applies (§11.4.107).

    1. ASCII-only — ``putrequest`` does ``request.encode('ascii')``; a non-ASCII
       char raises ``UnicodeEncodeError: 'ascii' codec can't encode`` — the
       exact live-stack crash this file reproduces.
    2. No disallowed control char (a raw space among them).
    """
    try:
        url.encode("ascii")
    except UnicodeEncodeError as exc:
        pytest.fail(
            f"{ctx}: constructed URL is NOT ASCII — urllib would raise "
            f"\"'ascii' codec can't encode\" on this exact string.\n"
            f"  url: {url!r}\n  err: {exc}"
        )
    assert _DISALLOWED_URL_CHAR_RE.search(url) is None, (
        f"{ctx}: urllib would reject this URL (disallowed control char, "
        f"e.g. a raw space): {url!r}"
    )


def _assert_every_token_round_trips(url: str, ctx: str) -> None:
    """EQUALITY per Cyrillic token — the assertion that has teeth.

    Percent-decoding the URL must recover each original Cyrillic word EXACTLY.
    A test that only checked "no exception" would pass on a URL whose query had
    been stripped to ASCII, transliterated, or mojibake'd; this one cannot.
    """
    decoded = urllib.parse.unquote_plus(url)
    for word in CYRILLIC_RAW.split():
        assert word in decoded, (
            f"{ctx}: Cyrillic token {word!r} did NOT survive the URL "
            f"encode/decode round-trip — the query was mangled, not encoded.\n"
            f"  url    : {url!r}\n  decoded: {decoded!r}"
        )


# ---------------------------------------------------------------------------
# Harness: import an engine with nova3 deps stubbed, capture every URL fetched.
# ---------------------------------------------------------------------------

def _plugin_path(name: str, copy: str) -> Path:
    return (PLUGINS if copy == "top" else COMMUNITY) / f"{name}.py"


def _cap_any(captured: list[str]):
    """A retrieve_url replacement tolerant of every calling convention."""

    def _inner(url, *args, **kwargs):
        captured.append(url)
        return ""

    return _inner


def _load(name: str, copy: str, capture: list[str]):
    np_mod = types.ModuleType("novaprinter")
    np_mod.prettyPrinter = lambda d: None  # type: ignore[attr-defined]

    class _SR:
        pass

    np_mod.SearchResults = _SR  # type: ignore[attr-defined]
    sys.modules["novaprinter"] = np_mod

    def _cap(url, *args, **kwargs):
        capture.append(url)
        return ""  # empty body -> parser finds nothing -> pagination loop ends

    helpers_mod = types.ModuleType("helpers")
    helpers_mod.retrieve_url = _cap  # type: ignore[attr-defined]
    helpers_mod.download_file = lambda u: u  # type: ignore[attr-defined]
    helpers_mod.htmlentitydecode = lambda s: s  # type: ignore[attr-defined]
    sys.modules["helpers"] = helpers_mod

    socks_mod = types.ModuleType("socks")
    socks_mod.PROXY_TYPE_SOCKS5 = 2  # type: ignore[attr-defined]
    socks_mod.set_default_proxy = lambda *a, **kw: None  # type: ignore[attr-defined]
    socks_mod.socksocket = MagicMock()  # type: ignore[attr-defined]
    sys.modules["socks"] = socks_mod

    modname = f"cyrpath_{copy}_{name}"
    sys.modules.pop(modname, None)
    sys.modules.pop(name, None)
    spec = importlib.util.spec_from_file_location(modname, _plugin_path(name, copy))
    mod = importlib.util.module_from_spec(spec)
    with patch("logging.basicConfig"), patch.object(Path, "write_text"), patch.object(
        Path, "write_bytes"
    ):
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
    sys.modules[name] = mod
    return mod


def drive_search(name: str, copy: str, query: str) -> list[str]:
    """Run the engine's REAL ``search()``; return every URL it tried to fetch.

    stdout/stderr are captured because nova3 engines print their results to
    stdout — leaking that into pytest's report would obscure the assertion.
    """
    captured: list[str] = []
    mod = _load(name, copy, captured)
    cls = getattr(mod, name)
    inst = cls()
    sink = io.StringIO()
    with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        stack = contextlib.ExitStack()
        with stack:
            # Engines that did `from helpers import retrieve_url` hold their own
            # binding; patch the module attribute too so nothing escapes.
            # The replacement MUST accept the extra kwargs some engines pass
            # (eztv sends `request_data=` for its POST). A 1-arg stub raises
            # TypeError there, eztv's `except TypeError` swallows it and falls
            # back to raw urllib — and the URL is never captured, so the test
            # would fail as "built no URL" for a HARNESS reason, not a product
            # defect (§11.4.1 FAIL-bluff).
            if hasattr(mod, "retrieve_url"):
                stack.enter_context(
                    patch.object(mod, "retrieve_url", side_effect=_cap_any(captured))
                )
            # eztv posts via urllib directly when retrieve_url lacks request_data.
            stack.enter_context(
                patch(
                    "urllib.request.urlopen",
                    side_effect=AssertionError(
                        f"{name}/{copy}: escaped to a REAL network call"
                    ),
                )
            )
            # audiobookbay probes mirrors first and returns early when none
            # answers the stub, so the search URL is never built. Pin one.
            if hasattr(inst, "find_healthy_url"):
                stack.enter_context(
                    patch.object(inst, "find_healthy_url", return_value=cls.url)
                )
            try:
                inst.search(query, "all")
            except Exception:
                # Pre-fix code raises UnicodeEncodeError from the real urllib;
                # the URL it tried to build is already captured, which is what
                # the assertions inspect.
                pass
    return captured


# ---------------------------------------------------------------------------
# The six engines the ae387b2 sweep missed, each with the copies that exist.
# ---------------------------------------------------------------------------

# (engine, copy) pairs. kickass is forked into a byte-identical community twin;
# ali213/bt4g are community-ONLY (no top-level file, so community IS the copy
# install-plugin.sh installs); eztv/limetorrents/solidtorrents are top-only.
MISSED_BY_AE387B2 = [
    ("kickass", "top"),
    ("kickass", "community"),
    ("ali213", "community"),
    ("bt4g", "community"),
    ("eztv", "top"),
    ("limetorrents", "top"),
    ("solidtorrents", "top"),
    ("audiobookbay", "community"),
]

_IDS = [f"{n}[{c}]" for n, c in MISSED_BY_AE387B2]


@pytest.mark.parametrize(("name", "copy"), MISSED_BY_AE387B2, ids=_IDS)
def test_cyrillic_query_produces_an_ascii_safe_url(name: str, copy: str) -> None:
    """RED on pre-fix code: the raw Cyrillic reaches the URL and urllib dies."""
    urls = drive_search(name, copy, CYRILLIC_RAW)
    assert urls, f"{name}/{copy}: search() built no URL at all — harness is blind"
    _assert_url_ascii_and_urllib_safe(urls[0], f"{name}/{copy}")


@pytest.mark.parametrize(("name", "copy"), MISSED_BY_AE387B2, ids=_IDS)
def test_cyrillic_query_round_trips_by_equality(name: str, copy: str) -> None:
    """The encoding must be REVERSIBLE — proves the query was encoded, not
    dropped, stripped, transliterated, or mojibake'd."""
    urls = drive_search(name, copy, CYRILLIC_RAW)
    assert urls, f"{name}/{copy}: built no URL"
    _assert_every_token_round_trips(urls[0], f"{name}/{copy}")


@pytest.mark.parametrize(("name", "copy"), MISSED_BY_AE387B2, ids=_IDS)
def test_nova2_pre_encoded_query_is_not_double_encoded(name: str, copy: str) -> None:
    """The nova2 caller passes an ALREADY %20-encoded query.

    The fix must decode-then-encode exactly once. A naive ``quote()`` over a
    pre-encoded string turns ``%D0%92`` into ``%25D0%2592`` — still ASCII, so
    the ASCII oracle above stays GREEN while the query is silently corrupted.
    Only the round-trip equality catches that, which is why it is asserted here
    on the pre-encoded path too.
    """
    urls = drive_search(name, copy, urllib.parse.quote(CYRILLIC_RAW))
    assert urls, f"{name}/{copy}: built no URL for the pre-encoded query"
    first = urls[0]
    _assert_url_ascii_and_urllib_safe(first, f"{name}/{copy} (pre-encoded)")
    _assert_every_token_round_trips(first, f"{name}/{copy} (pre-encoded)")


@pytest.mark.parametrize(("name", "copy"), MISSED_BY_AE387B2, ids=_IDS)
def test_ascii_query_still_works(name: str, copy: str) -> None:
    """§11.4.201(1) false-positive guard.

    Encoding must not break the ordinary ASCII path — a fix that made every
    Cyrillic query safe by mangling every query would satisfy the tests above.
    """
    urls = drive_search(name, copy, "ubuntu server")
    assert urls, f"{name}/{copy}: built no URL for a plain ASCII query"
    first = urls[0]
    _assert_url_ascii_and_urllib_safe(first, f"{name}/{copy} (ascii)")
    decoded = urllib.parse.unquote_plus(first)
    for word in ("ubuntu", "server"):
        assert word in decoded, (
            f"{name}/{copy}: plain ASCII token {word!r} lost: "
            f"url={first!r} decoded={decoded!r}"
        )


def test_control_needle_the_harness_can_actually_see_a_bad_url() -> None:
    """§11.4.201(7)(b): prove the oracles FAIL on a genuinely broken URL.

    Without this, a harness that silently captured nothing — or oracles that
    accept anything — would report every engine SAFE. Feed both oracles the
    exact pre-fix kickass URL measured on 2026-09-02 and require each to fire.
    """
    broken = "https://kickasstorrents.to/search/Война%20и%20мир/0/"  # noqa: RUF001
    # pytest.fail() raises Failed, which subclasses BaseException and NOT
    # Exception, so the non-ASCII branch escapes a bare `Exception`. Naming
    # the exact pair keeps both branches covered while staying narrow enough
    # that a NameError in the needle can no longer read as a pass (B017).
    with pytest.raises((AssertionError, pytest.fail.Exception)):
        _assert_url_ascii_and_urllib_safe(broken, "needle")

    raw_space = "https://example.test/search/war and peace/"
    with pytest.raises(AssertionError):
        _assert_url_ascii_and_urllib_safe(raw_space, "needle")

    # A URL that dropped the query entirely is ASCII-clean but must still fail
    # the round-trip oracle.
    stripped = "https://example.test/search//0/"
    with pytest.raises(AssertionError):
        _assert_every_token_round_trips(stripped, "needle")
