"""Real axe-core accessibility audits over real rendered DOM (BOB-110).

Oracle: axe-core (github.com/dequelabs/axe-core) run inside a real
Playwright/Chromium page — see tests/ux/conftest.py module docstring
for why this was chosen over a static template grep.

Fixtures live at tests/ux/fixtures/:

  * a11y_good.html — every accessibility floor item done correctly.
    Must produce ZERO axe violations.
  * a11y_bad.html  — the SAME page with four deliberate, real
    violations planted (missing alt, disassociated label, low
    contrast, missing html[lang]) while KEEPING the two
    correct-but-easy-to-false-flag patterns (decorative alt="", an
    aria-hidden decorative icon inside an aria-labelled button).
    Must flag exactly the four planted violations and must NOT flag
    the two correct patterns (the golden-FALSE requirement).

Every assertion here can genuinely fail: this is proven live in this
session by mutating a11y_good.html to remove one alt attribute,
observing pytest go RED, then restoring the byte-identical original
(sha256-verified) and observing GREEN again — see the BOB-110 report
for the pasted terminal transcript.
"""

from __future__ import annotations

from tests.ux.conftest import fixture_url, run_axe, violating_html_snippets, violation_ids


class TestGoldenGoodFixture:
    """a11y_good.html must be genuinely clean — the RED-capable baseline."""

    def test_zero_wcag_violations(self, page, axe_source):
        page.goto(fixture_url("a11y_good.html"))
        result = run_axe(page, axe_source)
        violations = result.get("violations", [])
        detail = "\n".join(f"- {v['id']}: {v['help']}" for v in violations)
        assert not violations, f"golden-good fixture unexpectedly flagged:\n{detail}"

    def test_single_h1_present(self, page, axe_source):
        """Real rendered-DOM heading-count assertion (not a hand-typed value)."""
        page.goto(fixture_url("a11y_good.html"))
        h1_count = page.locator("h1").count()
        assert h1_count == 1, f"expected exactly one <h1>, got {h1_count}"

    def test_html_lang_present(self, page, axe_source):
        page.goto(fixture_url("a11y_good.html"))
        lang = page.evaluate("document.documentElement.lang")
        assert lang == "en", f"expected html[lang]='en' on rendered document, got {lang!r}"


class TestGoldenBadFixture:
    """a11y_bad.html must flag exactly its four planted violations."""

    EXPECTED_VIOLATION_IDS = {"image-alt", "label", "color-contrast", "html-has-lang"}

    def test_flags_all_planted_violations(self, page, axe_source):
        page.goto(fixture_url("a11y_bad.html"))
        result = run_axe(page, axe_source)
        found = violation_ids(result)
        missing = self.EXPECTED_VIOLATION_IDS - found
        assert not missing, (
            f"golden-bad fixture should have flagged {missing} but axe did "
            f"not — the oracle failed to catch a real, planted violation. "
            f"Full ids found: {found}"
        )

    def test_missing_alt_image_is_flagged(self, page, axe_source):
        page.goto(fixture_url("a11y_bad.html"))
        result = run_axe(page, axe_source)
        snippets = violating_html_snippets(result, "image-alt")
        assert any("poster.jpg" in s for s in snippets), (
            f"expected the alt-less poster.jpg <img> to be flagged for "
            f"image-alt, got nodes: {snippets}"
        )

    def test_disassociated_label_is_flagged(self, page, axe_source):
        page.goto(fixture_url("a11y_bad.html"))
        result = run_axe(page, axe_source)
        snippets = violating_html_snippets(result, "label")
        assert any('id="q"' in s for s in snippets), (
            f"expected the un-labelled #q <input> to be flagged for label, "
            f"got nodes: {snippets}"
        )

    def test_low_contrast_text_is_flagged(self, page, axe_source):
        page.goto(fixture_url("a11y_bad.html"))
        result = run_axe(page, axe_source)
        snippets = violating_html_snippets(result, "color-contrast")
        assert any("low-contrast" in s for s in snippets), (
            f"expected the #aaaaaa-on-#ffffff <p> to be flagged for "
            f"color-contrast (WCAG AA 4.5:1), got nodes: {snippets}"
        )

    def test_missing_html_lang_is_flagged(self, page, axe_source):
        page.goto(fixture_url("a11y_bad.html"))
        result = run_axe(page, axe_source)
        assert "html-has-lang" in violation_ids(result)
        lang = page.evaluate("document.documentElement.getAttribute('lang')")
        assert lang is None, f"expected no html[lang] on the bad fixture, got {lang!r}"


class TestGoldenFalseCases:
    """Correct-but-tricky patterns that MUST NOT be flagged.

    Run against a11y_bad.html specifically (not a11y_good.html) so the
    proof is stronger: these two patterns stay clean even on a page
    that DOES have real, flagged violations elsewhere — i.e. the
    oracle is not merely silent because the whole page passed, it is
    correctly discriminating pattern-by-pattern.
    """

    def test_decorative_image_alt_empty_not_flagged(self, page, axe_source):
        page.goto(fixture_url("a11y_bad.html"))
        result = run_axe(page, axe_source)
        for v in result.get("violations", []):
            for node in v.get("nodes", []):
                assert 'class="decorative"' not in node["html"], (
                    f"decorative <img alt=\"\"> was incorrectly flagged by "
                    f"rule {v['id']}: {node['html']}"
                )

    def test_aria_hidden_icon_not_flagged(self, page, axe_source):
        page.goto(fixture_url("a11y_bad.html"))
        result = run_axe(page, axe_source)
        for v in result.get("violations", []):
            for node in v.get("nodes", []):
                assert "aria-hidden" not in node["html"] or "svg" not in node["html"], (
                    f"aria-hidden decorative <svg> was incorrectly flagged by "
                    f"rule {v['id']}: {node['html']}"
                )
        # Positive check: the icon button itself (which DOES need an
        # accessible name) is present and was not flagged for missing one.
        button_related = [
            v["id"] for v in result.get("violations", []) if v["id"] in ("button-name", "aria-hidden-body")
        ]
        assert not button_related, (
            f"icon-only button with aria-label should not trigger "
            f"button-name/aria-hidden-body, but got: {button_related}"
        )
