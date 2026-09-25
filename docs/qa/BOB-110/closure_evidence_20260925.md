# BOB-110 — Closure Evidence

**Date:** 2026-09-25 (discovered via BOB-238 investigation, independently
re-verified by the conductor)

**Status:** Completed (→ Fixed.md)

Already implemented at commit `7b45113c6b03524d9c799bdd68496ec202575e4c`
(2026-08-21): a full `tests/ux/` suite (axe-core against real
Playwright-rendered DOM, real keyboard Tab-traversal, real
`:focus-visible` computed-style checks) + `docs/testing/ux_accessibility.md`
mapping coverage directly against this item's three named criteria (WCAG
checks, keyboard-nav coverage, screen-reader labeling).

Re-verified independently by the conductor:
```
$ ls tests/ux/
__init__.py  conftest.py  test_accessibility_axe.py  test_keyboard_navigation.py
```

The suite's first live run correctly found a REAL defect (21 WCAG AA
color-contrast violations) and did not silence it — that finding was
spun into its own item, BOB-164, which is independently already closed:
```
$ sqlite3 docs/workable_items.db "SELECT atm_id, status FROM items WHERE atm_id='BOB-164';"
BOB-164|Fixed (→ Fixed.md)
```

Full investigation: `docs/qa/BOB-238/investigation_20260925.md`.

Classification: project-specific (§11.4.17) — no constitution change.
