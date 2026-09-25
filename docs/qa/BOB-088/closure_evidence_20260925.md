# BOB-088 — Closure Evidence

**Date:** 2026-09-25 (discovered via BOB-238 investigation, independently
re-verified by the conductor)

**Status:** Completed (→ Fixed.md)

Already implemented at commit `7b45113c6b03524d9c799bdd68496ec202575e4c`
(2026-08-21): `scripts/testing/update_readme_doc_links.sh` (new generator,
259 lines) + `docs/scripts/update_readme_doc_links.md` (companion doc) +
`tests/unit/test_update_readme_doc_links_no_duplication.sh` (regression
test). Both new files' own in-source text explicitly cite "BOB-088 (the
tracked item this script closes)."

Re-verified independently by the conductor:
```
$ bash tests/unit/test_update_readme_doc_links_no_duplication.sh
  PASS: exactly one 'Issues' row after rewrite (no table duplication)
  PASS: stale Revision refreshed to the real live value (115)
  PASS: content after the table block ('### Next section') survived the rewrite
  PASS: end marker present exactly once
  PASS: second run is idempotent (no further changes)
RESULT: 5 passed, 0 failed
```

Full investigation citing the exact README.md diff (stale doc-link table
rows corrected, new GOVERNANCE_AUDIT_2026-08-08_ROUND2 row added):
`docs/qa/BOB-238/investigation_20260925.md`.

Classification: project-specific (§11.4.17) — doc-sync tooling, no
constitution change.
