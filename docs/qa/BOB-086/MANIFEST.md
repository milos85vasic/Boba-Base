# BOB-086 backfill evidence manifest

**Revision:** 1
**Last modified:** 2026-08-19T00:00:00Z

## Purpose

Captured-evidence artefact for the §11.4.146(D3) status-custody backfill
executed under BOB-086. The workable-items DB carried 56 items whose
status had reached a `Fixed`-family terminal state without any
corresponding `item_history` audit row — a silent status change class
that violates §11.4.148 (workable-item integrity) and §11.4.146(D3).

BOB-086 backfills one `item_history` row per silent item, honestly
labelled `AI-inferred from git-history pickaxe` per §11.4.6 (no
guessing — the original closure operator / exact timestamp are
unrecoverable, so the row records what IS knowable: the git commit
that added the item to `docs/Fixed.md`, and the commit's authored
date).

## Provenance

- Discovery: `sqlite3 docs/workable_items.db "SELECT DISTINCT atm_id
  FROM items WHERE current_location='Fixed' AND atm_id NOT IN
  (SELECT DISTINCT atm_id FROM item_history)"` → 56 rows.
- Closure-commit resolution: `git log --all --oneline -S "<atm_id>"
  -- docs/Fixed.md | tail -1` per item; fallback to `docs/` scope
  when the pickaxe on `Fixed.md` was empty (`f23879a` was the
  Fixed.md seed commit and predates several items' first mention).
- Date: `git log -1 --format=%cI <commit>` (committer date, ISO).

## Backfill schema (per row)

- `event_type` — derived from the item's current terminal status:
  - `Fixed (→ Fixed.md)` → `Fixed`
  - `Completed (→ Fixed.md)` → `Completed`
  - `Implemented (→ Fixed.md)` → `Implemented`
- `by` — `AI` (schema CHECK constrains to `AI`/`User`/NULL; the
  AI-inferred nature is recorded in `reason`).
- `on_date` — commit date (`YYYY-MM-DD`), UTC via `%cI`.
- `reason` — `historical-backfill-BOB-086 (AI-inferred from
  git-history pickaxe on docs/Fixed.md; original closure
  committer/timestamp: git <short-sha>)`.
- `evidence_path` — this per-item evidence file
  (`docs/qa/BOB-086/backfill_evidence/<atm_id>.md`).

## Honest boundary (§11.4.6)

- The backfill does NOT invent the original operator, exact
  closure timestamp, or original evidence artefacts (all
  unrecoverable). It records the git commit that materialised
  the closure as the best available anchor.
- The backfill does NOT retro-validate the closures. It restores
  the audit-trail invariant so future §11.4.146(D3) sweeps do not
  flag these items as silent.
- BOB-009 + BOB-010 additionally receive `items.commit_ref` +
  `items.closure_date` (commit `7d243cc`, 2026-06-08 — "chore:
  close BOB-009 and BOB-010 as completed, sync Markdown
  trackers") for cross-artefact traceability.

## Per-item files

See `backfill_evidence/<atm_id>.md` — one file per backfilled item,
each carrying its closure commit + authored date + status →
event-type mapping.
