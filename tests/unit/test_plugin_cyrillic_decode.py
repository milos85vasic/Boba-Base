"""§11.4.146 reproduce-first guard: INBOUND cp1251 -> Cyrillic TITLE decode.

WHY THIS FILE EXISTS (measured gap, 2026-09-01).
``test_plugin_unicode_query_encoding.py`` covers the OUTBOUND half — the query
leaving us, percent-encoded, ASCII-safe (commit ae387b2, 14 plugins). Nothing
covered the INBOUND half: tracker bytes arriving in cp1251 and being decoded
back into a Cyrillic title. The existing kinozal/nnmclub suites DO feed
cp1251-encoded fixture bytes, but every title they assert is pure ASCII
("Test Movie 2024", "First Torrent", "Ubuntu 24.04 LTS") — so a decode
regression that turns Cyrillic into mojibake (wrong codec, double-decode,
latin-1 fallback) leaves every one of those assertions GREEN while the operator
sees garbage in the WebUI.

This project searches RuTracker / Kinozal / NNMClub / RuTor — Russian-language
trackers — so a mojibake title is not a cosmetic defect: it breaks the displayed
name, cross-tracker dedup matching, and any name-keyed lookup downstream.

ANTI-BLUFF (§11.4/§11.4.1). Every assertion below compares the decoded title to
the EXPECTED CYRILLIC STRING BY EQUALITY. A test asserting only "no exception"
or "len(results) == 1" passes against mojibake and is exactly the bluff this
file exists to prevent — mojibake raises nothing, it just decodes wrong.

The title used is a real entry from the operator's live library.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO = Path(__file__).resolve().parents[2]
PLUGINS_DIR = REPO / "plugins"

# A REAL title from the operator's live library. Every character is
# cp1251-encodable, so a correct pipeline round-trips it exactly.
CYRILLIC_TITLE = "Король-лев 2: Гордость Симбы"
CYRILLIC_TITLE_2 = "Война и мир (4К, полная версия)"  # noqa: RUF001


def _assert_no_mojibake(actual: str, expected: str, ctx: str) -> None:
    """Equality plus a named diagnostic for the classic wrong-codec signatures."""
    if actual == expected:
        return
    # Name the failure mode rather than dumping an opaque !=.
    mode = "unknown-divergence"
    if expected.encode("cp1251").decode("latin-1", "replace") == actual:
        mode = "MOJIBAKE: cp1251 bytes decoded as latin-1"
    elif expected.encode("cp1251").decode("utf-8", "replace") == actual:
        mode = "MOJIBAKE: cp1251 bytes decoded as utf-8"
    elif "�" in actual or "?" * 3 in actual:
        mode = "LOSSY: replacement/'?' characters present"
    elif not any("Ѐ" <= ch <= "ӿ" for ch in actual):
        mode = "CYRILLIC LOST: no Cyrillic codepoint survived"
    raise AssertionError(
        f"{ctx}: decoded title does not match expected Cyrillic text.\n"
        f"  expected: {expected!r}\n"
        f"  actual  : {actual!r}\n"
        f"  mode    : {mode}"
    )


# ===========================================================================
# kinozal — full search() -> _request(cp1251 bytes) -> searching() -> draw()
# ===========================================================================

KZ_JSON = (
    '{"username":"u","password":"p","magnet":true,"proxy":false,'
    '"proxies":{"http":"","https":""},"ua":"test"}'
)


def _load_kinozal(captured=None):
    if captured is None:
        captured = []

    np_mod = types.ModuleType("novaprinter")
    np_mod.prettyPrinter = lambda d: captured.append(dict(d))
    sys.modules["novaprinter"] = np_mod

    helpers_mod = types.ModuleType("helpers")
    helpers_mod.retrieve_url = lambda url: ""
    sys.modules["helpers"] = helpers_mod

    socks_mod = types.ModuleType("socks")
    socks_mod.PROXY_TYPE_SOCKS5 = 2
    socks_mod.set_default_proxy = lambda *a, **kw: None
    socks_mod.socksocket = MagicMock()
    sys.modules["socks"] = socks_mod

    sys.modules.pop("kinozal", None)
    path = os.path.join(PLUGINS_DIR, "kinozal.py")
    spec = importlib.util.spec_from_file_location("kinozal", path)
    mod = importlib.util.module_from_spec(spec)
    with patch.object(Path, "read_text", return_value=KZ_JSON), \
         patch.object(Path, "write_text"), \
         patch.object(Path, "write_bytes"), \
         patch("logging.basicConfig"):
        spec.loader.exec_module(mod)
    sys.modules["kinozal"] = mod
    inst = mod.kinozal()
    captured.clear()
    return inst, captured


def _kz_row(topic: str, title: str) -> str:
    """One RE_TORRENTS-shaped row. Sizes/dates use the site's real Cyrillic units."""
    return (
        f'<td class="nam"><a href="/showtopic.php?topic={topic}" class="r0">{title}</a></td>\n'
        "<td class='s'>2024</td>\n"
        "<td><span class='s'>10.5 ГБ</span></td>\n"
        "<td><span class='sl_s'>55</span></td>\n"
        "<td><span class='sl_p'>12</span></td>\n"
        "<td class='s'>09.06.2025 в 14:30</td>\n"
        "</tr>\n<tr>\n"
    )


class TestKinozalCyrillicTitleDecode:
    """kinozal decodes cp1251 tracker bytes into the exact Cyrillic title."""

    def test_search_decodes_cyrillic_title_exactly(self):
        inst, cap = _load_kinozal()
        page = "</span>Найдено 2 раздач" + _kz_row("12345", CYRILLIC_TITLE) + _kz_row(
            "67890", CYRILLIC_TITLE_2
        )
        # The tracker speaks cp1251 on the wire — feed REAL cp1251 bytes.
        raw = page.encode("cp1251")
        assert raw.decode("cp1251").encode("ascii", "ignore") != raw, (
            "fixture must actually contain non-ASCII bytes, else this proves nothing"
        )
        with patch.object(inst, "_init"), patch.object(inst, "_request", return_value=raw):
            inst.search("король лев", "all")

        assert len(cap) == 2, f"expected 2 parsed rows, got {len(cap)}: {cap}"
        _assert_no_mojibake(cap[0]["name"], CYRILLIC_TITLE, "kinozal row 0")
        _assert_no_mojibake(cap[1]["name"], CYRILLIC_TITLE_2, "kinozal row 1")

    def test_cyrillic_title_survives_the_size_unit_translation(self):
        """draw() str.maketrans-es Cyrillic size units (Г->G, Б->B ...).

        That table must apply to the SIZE only. 'Гордость' starts with 'Г' — if
        the translation ever leaked onto the name, the title would silently
        become 'Gордость'. Assert the name is untouched and the size IS mapped.
        """
        inst, cap = _load_kinozal()
        page = "</span>Найдено 1 раздач" + _kz_row("111", CYRILLIC_TITLE)
        with patch.object(inst, "_init"), patch.object(
            inst, "_request", return_value=page.encode("cp1251")
        ):
            inst.search("король лев", "all")
        assert len(cap) == 1
        _assert_no_mojibake(cap[0]["name"], CYRILLIC_TITLE, "kinozal size-translate")
        assert "Гордость" in cap[0]["name"], "size-unit translation leaked onto the title"
        assert cap[0]["size"] == "10.5 GB", f"size units not normalised: {cap[0]['size']!r}"


# ===========================================================================
# nnmclub — full search() -> _request(cp1251 bytes) -> searching() -> draw()
# ===========================================================================

def _load_nnmclub(captured=None):
    if captured is None:
        captured = []

    np_mod = types.ModuleType("novaprinter")
    np_mod.prettyPrinter = lambda d: captured.append(dict(d))
    sys.modules["novaprinter"] = np_mod

    helpers_mod = types.ModuleType("helpers")
    helpers_mod.retrieve_url = lambda url: ""
    sys.modules["helpers"] = helpers_mod

    sys.modules.pop("nnmclub", None)
    with patch("logging.basicConfig"), patch("pathlib.Path.write_text"), patch(
        "pathlib.Path.write_bytes"
    ):
        path = os.path.join(PLUGINS_DIR, "nnmclub.py")
        spec = importlib.util.spec_from_file_location("nnmclub", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        sys.modules["nnmclub"] = mod
    inst = mod.nnmclub()
    captured.clear()
    return inst, mod, captured


def _nnm_row(topic: str, title: str) -> str:
    return (
        f'<a class="topictitle" href="viewtopic.php?t={topic}"><b>{title}</b></a>'
        f' <a href="dl.php?t={topic}">d{topic}</a> '
        "<u>1548578624</u> <b>50</b> <b>12</b> <u>1700000000</u>"
    )


class TestNnmclubCyrillicTitleDecode:
    """nnmclub decodes cp1251 tracker bytes into the exact Cyrillic title.

    nnmclub decodes with ``.decode("cp1251", "ignore")`` — the ``ignore`` errors
    mode makes a wrong-codec regression SILENT (bad bytes are dropped, nothing
    raises), which is precisely why an equality assertion is required here.
    """

    def test_search_decodes_cyrillic_title_exactly(self):
        inst, mod, cap = _load_nnmclub()
        page = (
            f"Выход [ {mod.config.username} ]"
            + 'TP_VER">Torrents: 2 '
            + _nnm_row("12345", CYRILLIC_TITLE)
            + _nnm_row("67890", CYRILLIC_TITLE_2)
        )
        with patch.object(inst, "_init"), \
             patch.object(inst, "_fetch_magnet_from_topic", return_value=""), \
             patch.object(inst, "_request", return_value=page.encode("cp1251")):
            inst.search("король лев", "all")

        names = [r["name"] for r in cap]
        assert len(cap) == 2, f"expected 2 parsed rows, got {len(cap)}: {names}"
        _assert_no_mojibake(cap[0]["name"], CYRILLIC_TITLE, "nnmclub row 0")
        _assert_no_mojibake(cap[1]["name"], CYRILLIC_TITLE_2, "nnmclub row 1")

    def test_ignore_errors_mode_does_not_hide_a_wrong_codec(self):
        """Control needle: prove the assertion above can actually FAIL.

        Feed the SAME page as UTF-8 bytes while the plugin decodes cp1251. No
        exception is raised (errors='ignore'), the row still parses — and the
        title comes back as mojibake. If this test ever stops failing to match,
        the equality assertion above has lost its teeth.
        """
        inst, mod, cap = _load_nnmclub()
        page = (
            f"Выход [ {mod.config.username} ]"
            + 'TP_VER">Torrents: 1 '
            + _nnm_row("12345", CYRILLIC_TITLE)
        )
        with patch.object(inst, "_init"), \
             patch.object(inst, "_fetch_magnet_from_topic", return_value=""), \
             patch.object(inst, "_request", return_value=page.encode("utf-8")):
            inst.search("король лев", "all")
        assert len(cap) == 1, "row should still parse — mojibake raises nothing"
        assert cap[0]["name"] != CYRILLIC_TITLE, (
            "a utf-8 page decoded as cp1251 MUST NOT yield the correct title; "
            "if it does, this control needle is blind"
        )


# ===========================================================================
# B9 drift guard — the Cyrillic fix must live on the copy that is INSTALLED
# ===========================================================================

# The 14 plugins fixed by ae387b2 ("UTF-8/Cyrillic query encoding"), with the
# encoding call each one must carry. 11 of these have a plugins/community/ twin;
# install-plugin.sh resolves plugins/<n>.py FIRST and only falls back to
# plugins/community/<n>.py, so the fix must be on the TOP-LEVEL copy to reach
# the operator. A fix landing on the community twin instead is invisible.
CYRILLIC_FIXED = {
    "bitsearch": "quote_plus",
    "glotorrents": "quote_plus",
    "linuxtracker": "quote_plus",
    "nyaa": "quote_plus",
    "pirateiro": "quote_plus",
    "rockbox": "quote_plus",
    "torrentdownload": "quote_plus",
    "torrentscsv": "quote_plus",
    "torrentproject": "quote_plus",
    "tokyotoshokan": "quote_plus",
    "torrentgalaxy": "quote",
    "snowfl": "quote",
    "torlock": "quote",
    "yourbittorrent": "quote",
}


def _resolve_installed(name: str) -> Path:
    """Mirror install-plugin.sh: plugins/<n>.py wins, community/ is fallback."""
    top = PLUGINS_DIR / f"{name}.py"
    return top if top.is_file() else PLUGINS_DIR / "community" / f"{name}.py"


class TestCyrillicFixIsOnTheInstalledCopy:
    """The forked twins must never let an encoding fix land on the dead copy."""

    @pytest.mark.parametrize(("name", "call"), sorted(CYRILLIC_FIXED.items()))
    def test_installed_copy_carries_the_encoding_fix(self, name, call):
        live = _resolve_installed(name)
        assert live.is_file(), f"{name}: no plugin file resolved at all"
        src = live.read_text(encoding="utf-8")
        assert call in src, (
            f"{name}: the copy install-plugin.sh actually installs ({live.relative_to(REPO)}) "
            f"does NOT contain {call}() — the Cyrillic query fix is missing from the LIVE "
            f"copy. If it was applied to a twin under plugins/community/, it never reaches "
            f"the operator (install-plugin.sh prefers plugins/*.py)."
        )

    def test_resolution_order_is_toplevel_first(self):
        """Pin the resolution order this whole guard depends on."""
        script = (REPO / "install-plugin.sh").read_text(encoding="utf-8")
        primary = script.index('plugin_file="plugins/${plugin}.py"')
        fallback = script.index('plugin_file="plugins/community/${plugin}.py"')
        assert primary < fallback, (
            "install-plugin.sh no longer prefers plugins/*.py over plugins/community/*.py — "
            "every LIVE/DEAD determination in this file is invalidated; re-derive it."
        )


# ===========================================================================
# A8 — bare `except:` narrowing in the two community-LIVE size parsers
# ===========================================================================
# bitru and btsow have NO plugins/<name>.py twin, so install-plugin.sh installs
# plugins/community/<name>.py — these are LIVE engines on the operator's stack.
# Their _parse_size() used a bare `except:`, which also swallows
# KeyboardInterrupt and SystemExit (both derive from BaseException, not
# Exception): a Ctrl-C landing inside that loop was silently converted into a
# bogus "size 0" / a continued loop instead of terminating the process.

BARE_EXCEPT_FIXED = ("bitru", "btsow")


def _load_community_engine(name: str):
    """Load plugins/community/<name>.py with novaprinter/helpers stubbed."""
    captured: list[dict] = []

    np_mod = types.ModuleType("novaprinter")
    np_mod.prettyPrinter = lambda d: captured.append(dict(d))
    sys.modules["novaprinter"] = np_mod

    helpers_mod = types.ModuleType("helpers")
    helpers_mod.retrieve_url = lambda url: ""
    sys.modules["helpers"] = helpers_mod

    sys.modules.pop(name, None)
    path = PLUGINS_DIR / "community" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules[name] = mod
    return getattr(mod, name)(), captured


class TestParseSizeDoesNotSwallowBaseException:
    """A bare `except:` in _parse_size() also caught Ctrl-C — it must not."""

    @pytest.mark.parametrize("name", BARE_EXCEPT_FIXED)
    def test_keyboard_interrupt_propagates(self, name):
        inst, _ = _load_community_engine(name)

        class _Boom(str):
            """A size token whose float() conversion raises KeyboardInterrupt.

            .upper()/.strip()/.replace() behave normally so the value reaches the
            float() inside the try: block, exactly where the bare except sat.
            """

            # upper()/strip() must return SELF, else the plain str they would
            # normally return drops the subclass before float() is ever reached
            # and the needle never fires (a blind instrument, §11.4.201(7)(b)).
            def upper(self):  # noqa: D102
                return self

            def strip(self, *a, **kw):  # noqa: D102
                return self

            def replace(self, *a, **kw):  # noqa: D102
                raise KeyboardInterrupt("operator pressed Ctrl-C")

        with pytest.raises(KeyboardInterrupt):
            inst._parse_size(_Boom("10 GB"))

    @pytest.mark.parametrize("name", BARE_EXCEPT_FIXED)
    def test_unparseable_size_still_degrades_to_zero(self, name):
        """False-positive guard (§11.4.201): the ORDINARY path must still work.

        Narrowing the handler must not turn a merely-unparseable size into a
        crash — a garbage size token still yields 0, and a good one still parses.
        """
        inst, _ = _load_community_engine(name)
        assert inst._parse_size("not-a-number GB") == 0
        assert inst._parse_size("10 GB") == 10 * 1024**3
        assert inst._parse_size("") == 0

    @pytest.mark.parametrize("name", BARE_EXCEPT_FIXED)
    def test_row_parse_failure_is_reported_not_swallowed(self, name, capsys):
        """A per-row failure must reach stderr, never vanish.

        stdout is the nova3 result stream and MUST stay clean; the diagnostic
        belongs on stderr. Previously this handler was a bare `continue`, so a
        site-layout change produced a silently short result set.
        """
        inst, cap = _load_community_engine(name)
        with patch.object(inst, "_parse_size", side_effect=RuntimeError("layout changed")):
            inst._parse_results(_ROW_HTML[name])
        err = capsys.readouterr().err
        assert "layout changed" in err, (
            f"{name}: per-row parse failure was swallowed silently — stderr was {err!r}"
        )
        assert cap == [], "a failed row must not be emitted as a result"


# Minimal HTML matching each engine's _parse_results regex — one well-formed row,
# so the ONLY failure is the injected one.
_ROW_HTML = {
    "bitru": (
        '<div class="torrent-item">'
        '<a href="/details/1">Тест</a>'
        '<span class="size">1 GB</span>'
        '<span class="seed">5</span>'
        '<span class="leech">1</span>'
        "</div>"
    ),
    "btsow": (
        '<div class="data-list">'
        '<a href="/magnet/aabbccddeeff00112233445566778899aabbccdd"></a>'
        '<div class="name">Тест</div>'
        '<div class="size">1 GB</div>'
        '<div class="date">2025-01-01</div>'
        "</div>"
    ),
}
