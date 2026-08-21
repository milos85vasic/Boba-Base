"""Real keyboard-navigation coverage (BOB-110).

Drives REAL `Tab` key presses via Playwright (`page.keyboard.press`,
which Chromium treats as genuine keyboard input — this is what makes
`:focus-visible` actually engage, unlike a synthetic `.focus()` call)
and asserts on the REAL post-press `document.activeElement` id plus
its REAL computed CSS (outline / box-shadow). No hand-typed
expectation about `tabindex` source values is ever asserted directly
— only what the browser's real focus/render pipeline produces.

Fixtures live at tests/ux/fixtures/:

  * keyboard_good.html — six real interactive controls in document
    order, all keyboard-reachable, all with a visible focus style.
  * keyboard_bad.html  — the SAME layout with two planted violations:
    one control removed from the Tab order via tabindex="-1" (visible
    + mouse-clickable, but keyboard-unreachable), and one control
    whose :focus outline/box-shadow is explicitly suppressed with no
    replacement (keyboard-reachable but the focus is invisible).
"""

from __future__ import annotations

from tests.ux.conftest import fixture_url

# document order in both fixtures.
GOOD_TAB_ORDER = ["skip", "nav1", "nav2", "btn1", "inp1", "btn2"]


def _tab_sequence(page, presses: int) -> list[str]:
    """Press Tab ``presses`` times from a neutral start, returning the id
    of ``document.activeElement`` after each press (empty string if the
    focused element has no id, e.g. still <body>)."""
    page.evaluate("document.body.focus()")
    ids: list[str] = []
    for _ in range(presses):
        page.keyboard.press("Tab")
        active_id = page.evaluate("document.activeElement && document.activeElement.id || ''")
        ids.append(active_id)
    return ids


def _focus_is_visible(page, element_id: str) -> bool:
    """True iff the currently-focused element (asserted to be
    ``element_id``) has a real, non-none visible focus indicator."""
    active_id = page.evaluate("document.activeElement && document.activeElement.id || ''")
    assert active_id == element_id, f"expected #{element_id} focused, got #{active_id!r}"
    style = page.evaluate(
        """() => {
            const s = getComputedStyle(document.activeElement);
            return { outlineStyle: s.outlineStyle, outlineWidth: s.outlineWidth, boxShadow: s.boxShadow };
        }"""
    )
    has_outline = style["outlineStyle"] not in ("none", "") and style["outlineWidth"] not in ("0px", "")
    has_box_shadow = style["boxShadow"] not in ("none", "")
    return has_outline or has_box_shadow


class TestGoldenGoodKeyboardNav:
    def test_tab_order_reaches_every_control_in_document_order(self, page):
        page.goto(fixture_url("keyboard_good.html"))
        ids = _tab_sequence(page, len(GOOD_TAB_ORDER))
        assert ids == GOOD_TAB_ORDER, (
            f"expected real Tab-key traversal to reach {GOOD_TAB_ORDER} in "
            f"order, got {ids}"
        )

    def test_each_control_gets_a_visible_focus_indicator(self, page):
        page.goto(fixture_url("keyboard_good.html"))
        page.evaluate("document.body.focus()")
        for expected_id in GOOD_TAB_ORDER:
            page.keyboard.press("Tab")
            assert _focus_is_visible(page, expected_id), (
                f"#{expected_id} received keyboard focus but has no visible "
                f"focus indicator (real computed outline/box-shadow check)"
            )


class TestGoldenBadKeyboardNav:
    def test_tabindex_negative_one_button_is_unreachable(self, page):
        """RED-capable: btn2 has tabindex="-1" — a keyboard-only user can
        never Tab to it, even though it is visible and mouse-clickable."""
        page.goto(fixture_url("keyboard_bad.html"))
        # Tab past every other control (skip, nav1, nav2, btn1, inp1) plus
        # a couple of extra presses — btn2 must never appear.
        ids = _tab_sequence(page, 8)
        assert "btn2" not in ids, (
            f"btn2 (tabindex=-1) was reached by keyboard Tab traversal "
            f"({ids}) — the fixture is supposed to demonstrate the "
            f"unreachable-control failure, so this indicates the oracle "
            f"itself is broken, not that the app is fine"
        )
        # Confirm the button IS really present and visible (so "not
        # reached" means keyboard-unreachable, not "doesn't exist").
        assert page.locator("#btn2").is_visible()

    def test_missing_focus_indicator_is_detected(self, page):
        """RED-capable: #inp1's :focus style is suppressed with no
        replacement — focus lands there but is invisible to a sighted
        keyboard user."""
        page.goto(fixture_url("keyboard_bad.html"))
        page.evaluate("document.body.focus()")
        for _ in range(5):  # skip, nav1, nav2, btn1, inp1
            page.keyboard.press("Tab")
        visible = _focus_is_visible(page, "inp1")
        assert not visible, (
            "expected the golden-bad fixture's #inp1 to have NO visible "
            "focus indicator (that is the planted violation) — got a "
            "visible one, meaning this check cannot actually detect the "
            "failure it claims to detect"
        )
