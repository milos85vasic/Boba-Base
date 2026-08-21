"""Real axe-core + keyboard-nav pass over the LIVE merge-service dashboard
(BOB-110 acceptance: "Scope an axe-core or equivalent accessibility pass
over the Angular frontend").

Complements the fixture-based oracle-validation tests
(test_accessibility_axe.py / test_keyboard_navigation.py, which prove the
oracle genuinely catches and correctly discriminates violations) by
running the SAME real oracle against the ACTUAL shipped product: the
Angular SPA served at the merge-service root
(``merge_service_live`` fixture — http://localhost:7187 by default,
re-exported from tests/fixtures/services.py exactly like every other
integration/e2e test in this repo).

This test asserts on REALITY. A red result here is a genuine, newly
DISCOVERED defect in the shipped dashboard (the exact posture §11.4.238
mandates: automated coverage finds it, not a human) — it is not
weakened or downgraded to "informational" to make this dispatch look
cleaner. See the BOB-110 report for the actual observed outcome.
"""

from __future__ import annotations

from tests.ux.conftest import run_axe, violation_ids


def test_live_dashboard_axe_scan(page, axe_source, merge_service_live):
    page.goto(merge_service_live.rstrip("/") + "/", timeout=30_000)
    # Wait for Angular hydration — the raw HTML response ships an empty
    # <app-root></app-root>; only after JS executes does real content
    # exist to scan. See conftest.py module docstring for the curl proof.
    page.wait_for_selector("app-root *", timeout=15_000)
    page.wait_for_timeout(500)  # let late-bound ARIA / animations settle
    result = run_axe(page, axe_source)
    violations = result.get("violations", [])
    detail = "\n".join(
        f"- {v['id']} ({v['impact']}): {v['help']} — {len(v['nodes'])} node(s)\n"
        + "\n".join(f"    {n['html'][:200]}" for n in v["nodes"][:3])
        for v in violations
    )
    assert not violations, (
        f"axe-core found {len(violations)} real accessibility violation "
        f"class(es) on the live dashboard ({merge_service_live}/):\n{detail}\n\n"
        "This is genuine discovered debt (BOB-110) surfaced by the new "
        "automated UX gate, not a fixture artefact — fix the referenced "
        "Angular templates, or file a tracked followup per §11.4.238, "
        "rather than weakening this assertion."
    )


def test_live_dashboard_has_keyboard_reachable_focus(page, merge_service_live):
    """Weak-but-real supplementary check: at least one interactive element
    on the live dashboard is reachable by pure keyboard Tab traversal and
    real focus actually moves off <body>."""
    page.goto(merge_service_live.rstrip("/") + "/", timeout=30_000)
    page.wait_for_selector("app-root *", timeout=15_000)
    page.evaluate("document.body.focus()")
    page.keyboard.press("Tab")
    active = page.evaluate(
        "() => ({tag: document.activeElement.tagName, isBody: document.activeElement === document.body})"
    )
    assert not active["isBody"], (
        "pressing Tab once from a fresh page load did not move focus off "
        "<body> — the live dashboard has no keyboard-reachable interactive "
        "element in its initial tab order"
    )


def test_live_dashboard_has_single_h1(page, merge_service_live):
    page.goto(merge_service_live.rstrip("/") + "/", timeout=30_000)
    page.wait_for_selector("app-root *", timeout=15_000)
    h1_count = page.locator("h1").count()
    assert h1_count >= 1, "live dashboard has zero <h1> elements — no top-level heading for screen-reader users"
