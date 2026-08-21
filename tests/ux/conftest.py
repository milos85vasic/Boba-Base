"""tests/ux — UX-class (accessibility / usability) coverage (BOB-110).

docs/testing/test_type_matrix.md's §11.4.27 test-type audit found UI
FUNCTIONAL coverage (Vitest unit tests + Playwright e2e under
frontend/e2e/ and tests/e2e/) but nothing framed around
usability/accessibility/UX outcomes specifically — no test asserted on
WCAG rules, keyboard reachability, or screen-reader labeling. This
package closes that gap.

Oracle chosen (§11.4.170 — value-equality assertions are FORBIDDEN as
the proof a UI is correct): a REAL axe-core accessibility audit run
against a REAL, JS-hydrated, Playwright-rendered DOM. This is the
strongest oracle available:

  * axe-core (github.com/dequelabs/axe-core, vendored via
    frontend/node_modules/axe-core after `npm install --save-dev
    axe-core`) implements the actual WCAG 2.x success-criteria checks
    (color-contrast computed from real rendered styles, image-alt,
    label, aria-hidden handling, html-has-lang, ...) — not a
    hand-rolled approximation.
  * The DOM axe scans is produced by a real Chromium instance
    (Playwright, headless) executing the real page's JS — for the
    live dashboard that means the real compiled Angular bundle, not a
    static template grep. A `curl`/BeautifulSoup-only approach was
    rejected: the merge-service dashboard root ships
    `<app-root></app-root>` with an empty body until Angular
    hydrates it (verified: `curl -s http://localhost:7187/ | grep
    app-root` shows the unhydrated shell), so any oracle that does not
    execute JS would be auditing a page nobody ever sees.
  * Static template-only checks (grepping .component.html source) were
    considered and rejected as the primary oracle: they cannot see
    computed contrast, ARIA state Angular sets at runtime, or real
    keyboard focus order, and a grep-based check that only counts
    `alt=` occurrences is exactly the kind of oracle-agrees-with-code
    bluff §11.4.245 forbids (it would pass a page that never renders).

Keyboard-navigation coverage additionally drives REAL `Tab` key
presses (Playwright `page.keyboard.press("Tab")`, which Chromium
treats as genuine keyboard input and therefore does trigger
`:focus-visible`) and asserts on the REAL post-press
`document.activeElement` id and its REAL computed style — never a
static assertion about `tabindex` values in source.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Browser, Page, sync_playwright

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
AXE_SOURCE_PATH = REPO_ROOT / "frontend" / "node_modules" / "axe-core" / "axe.min.js"


def _axe_source() -> str:
    if not AXE_SOURCE_PATH.is_file():
        pytest.skip(
            f"axe-core runtime not installed at {AXE_SOURCE_PATH} — run "
            "`cd frontend && npm install --save-dev axe-core` to close this "
            "gap (§11.4.3 honest topology SKIP, BOB-110). The rest of the "
            "UX suite that does not need axe (keyboard-nav-only checks) "
            "still runs."
        )
    return AXE_SOURCE_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def axe_source() -> str:
    return _axe_source()


@pytest.fixture(scope="session")
def browser():
    try:
        pw = sync_playwright().start()
        br = pw.chromium.launch(headless=True)
    except Exception as exc:  # pragma: no cover - environment guard
        pytest.skip(
            f"Playwright/Chromium unavailable ({type(exc).__name__}: {exc}) — "
            "honest §11.4.3 SKIP (BOB-110). Run `cd frontend && "
            "npx playwright install chromium` (or the repo-root equivalent) "
            "to close this gap."
        )
        return  # unreachable, pytest.skip raises
    yield br
    br.close()
    pw.stop()


@pytest.fixture
def page(browser: Browser):
    pg = browser.new_page()
    yield pg
    pg.close()


def fixture_url(name: str) -> str:
    """file:// URL for a fixture under tests/ux/fixtures/."""
    path = FIXTURES_DIR / name
    assert path.is_file(), f"missing UX fixture: {path}"
    return path.resolve().as_uri()


def run_axe(page: Page, axe_source: str, *, tags: tuple[str, ...] = ("wcag2a", "wcag2aa")) -> dict[str, Any]:
    """Inject real axe-core into ``page`` and run a real scan of its DOM.

    Returns the raw ``axe.run()`` result (``violations`` / ``passes`` /
    ``incomplete`` / ``inapplicable``). This executes IN the real
    browser against the REAL rendered document — not a reimplementation
    of WCAG rules in Python — so a scan can genuinely disagree with
    whatever the page author believed was correct.
    """
    page.add_script_tag(content=axe_source)
    result = page.evaluate(
        "(tags) => axe.run(document, { runOnly: { type: 'tag', values: tags } })",
        list(tags),
    )
    assert isinstance(result, dict) and "violations" in result, (
        f"axe.run() returned an unexpected shape: {result!r} — the oracle "
        "itself did not run correctly, this is not a real scan result."
    )
    return result


def violation_ids(axe_result: dict[str, Any]) -> set[str]:
    return {v["id"] for v in axe_result.get("violations", [])}


def violating_html_snippets(axe_result: dict[str, Any], rule_id: str) -> list[str]:
    """The raw offending ``node.html`` strings axe captured for one rule."""
    for v in axe_result.get("violations", []):
        if v["id"] == rule_id:
            return [n["html"] for n in v.get("nodes", [])]
    return []
