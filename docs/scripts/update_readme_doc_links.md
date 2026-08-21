# `scripts/testing/update_readme_doc_links.sh` — README Tracked-Items table regenerator

**Revision:** 1
**Last modified:** 2026-08-21T19:45:00Z
**Purpose:** §11.4.57 machine-derived regenerator for README.md's
`### Tracked-Items + Status Documents` table.
**Last verified:** 2026-08-21

---

## Overview

`README.md` carries a `### Tracked-Items + Status Documents` table (bounded by
`<!-- doc-link-section:begin -->` / `<!-- doc-link-section:end -->` markers)
that is the mandated entry point (§11.4.57 / §11.4.212) for every tracker and
status document in this repository. Each row's `Last modified` and `Revision`
cells are supposed to be sourced verbatim from the document's own §11.4.44
revision header, and the `HTML` / `PDF` cells are supposed to reflect whether
those exports actually exist on disk.

Before this script existed, that table was hand-maintained, and it had
drifted: measured 2026-08-21 (BOB-088), 10 of its 18 rows carried a stale
`Revision`/`Last modified` pair (e.g. `docs/Issues.md` carried `**Revision:**
38` while the table still read `10`), two rows read `— (not yet exported)`
for HTML/PDF cells that had real exports on disk, and one MANDATED document
(`docs/GOVERNANCE_AUDIT_2026-08-08_ROUND2.md`, cited by name in BOB-088's own
body text) had no row at all.

## Usage

```bash
scripts/testing/update_readme_doc_links.sh            # rewrite README.md in place
scripts/testing/update_readme_doc_links.sh --check     # read-only; exit 0 = in sync, exit 2 = stale
scripts/testing/update_readme_doc_links.sh --check --readme <path>  # override target (tests)
```

Default mode rewrites `README.md` in place. `--check` mode is read-only and
prints a unified diff of the stale rows before exiting 2 — safe to wire into
a pre-commit or pre-build sweep.

**This script does not regenerate `README.html`/`.pdf`/`.docx`.** Run
`scripts/generate_markdown_exports.sh` afterward (§11.4.65/§11.4.12) so the
exports stay in sync with the source it just edited.

## Scope (deliberately narrow)

This generator owns only the closed-set "Tracked-Items" row class §11.4.57
names: `Issues`/`Fixed` + their `_Summary` companions, `CONTINUATION`,
`PORTING-FROM-LAVA`, `REMAINING_WORK_PLAN`, every
`docs/GOVERNANCE_AUDIT_*.md` (auto-discovered via `git ls-files`, so a third
round audit doc is picked up automatically), `COMPLETION_STATUS`,
`RELEASE_READINESS_20260616`, `QA_DISCOVERY_LEDGER`, and every
`docs/**/Status.md` + its `Status_Summary.md` (and `RELEASE_READINESS.md`
sibling, if present) pair, likewise auto-discovered.

§11.4.212's broader "every §11.4.65-scope doc must be reachable from README,
directly or transitively" obligation is a distinct, editorial-judgement-
bearing task (which subsection a guide/research doc/plan belongs under) and
is handled separately in README.md's other `###` subsections — this
generator does not attempt it, to avoid silently mis-categorizing a doc it
has no basis to categorize (§11.4.6).

## Internal behavior

1. Builds a manifest of `label|relative-path` pairs: a fixed list plus two
   auto-discovered classes (`docs/GOVERNANCE_AUDIT_*.md`,
   `docs/**/Status.md` pairs).
2. For each manifest entry, reads `**Revision:**` / `**Last modified:**`
   straight out of the file's own header (§11.4.44) — a document with no
   header emits `—` for both cells, never a fabricated value.
3. Checks `[[ -f ... ]]` for the `.html` and `.pdf` siblings on THIS run —
   never carried forward from the table's previous state.
4. Replaces only the table portion of the content between the
   `doc-link-section` markers; the hand-authored intro paragraph above the
   table, and anything after the table but before the end marker, are left
   untouched.

### A fixed defect worth knowing about (BOB-088, 2026-08-21)

The first version of the block-rewrite `awk` state machine dropped only the
old table's header line and its `|---` separator, then fell through to
printing every old data row unchanged — so applying the generator to a
genuinely stale table produced **two back-to-back copies** of the table
instead of replacing it. Caught by a RED-first regression test
(`tests/unit/test_update_readme_doc_links_no_duplication.sh`, run against the
pre-fix script and confirmed to fail 3/5 assertions before the fix, then pass
5/5 after) before it ever shipped in a commit.

## Testing

- `tests/unit/test_update_readme_doc_links_no_duplication.sh` — regression
  guard for the table-duplication defect above; drives the real script
  through its real invocation path against a fixture whose `Issues` row
  carries a deliberately stale `Revision`, and asserts (1) exactly one
  `Issues` row survives the rewrite, (2) the stale value was corrected to
  the real live value read off `docs/Issues.md`, (3) content after the table
  block is preserved, (4) the end marker is not duplicated, (5) a second run
  is idempotent.

## Dependencies

`bash` 4+, `git`, `sed`, `grep`, `awk`. No Python, no network access.

## Cross-references

- `README.md` — the file this script rewrites.
- CLAUDE.md / `constitution/CLAUDE.md` §11.4.57 — the mandate this script
  implements (README doc-link section + revision metadata).
- CLAUDE.md / `constitution/CLAUDE.md` §11.4.212 — README as the canonical
  documentation entry point (the broader obligation this script does NOT
  attempt; see "Scope" above).
- `scripts/generate_markdown_exports.sh` — must be run afterward to keep
  `README.html`/`.pdf`/`.docx` in sync.
- BOB-088 — the tracked workable item this script closes.
