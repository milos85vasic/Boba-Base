# Phase 0 Research: Zero-Shortcomings Evidence-Backed Audit & Closure

No `NEEDS CLARIFICATION` markers remain in the Technical Context — the one genuine
ambiguity in the feature (audit scope boundary) was already resolved in `spec.md` via
Q1 (Option A, operator-confirmed). This document instead records the concrete technical
decisions the plan depends on, each grounded in direct investigation of this repository
rather than assumed, per this project's own §11.4.6 no-guessing discipline.

## 1. Enumerating surface 1 — the open workable-items backlog

- **Decision**: Enumerate via the existing `constitution/scripts/workable-items` CLI
  (`validate` / `diff` subcommands and direct read-only `sqlite3` queries against
  `docs/workable_items.db`), never by re-parsing `docs/Issues.md`/`docs/Fixed.md`.
- **Rationale**: The SQLite DB is the established single source of truth
  (§11.4.93/§11.4.95); the Markdown files are DERIVED from it. Confirmed live this
  session: `workable-items validate --db docs/workable_items.db` correctly reports "OK —
  240 items, all invariants satisfied" against the current tracker state, and the CLI
  already exposes every field this feature needs (`status`, `type`, `reopens_count`,
  `current_location`).
- **Alternatives considered**: Re-parsing the Markdown trackers directly — rejected,
  since it would duplicate parsing logic the tracker CLI already owns and risks drifting
  from the DB the moment either side changes independently (exactly the class of defect
  §11.4.93 exists to prevent).

## 2. Enumerating surface 2 — the governance-gate ledger

- **Decision**: Enumerate via the existing, already-wired
  `constitution/scripts/gates/cm_gate_ledger_ratchet.sh` (which itself consumes
  `gate_ledger.sh` + the checked-in `gate_ledger_baseline.txt` /
  `gate_ledger_deferrals.tsv` / `gate_ledger_removals.tsv`), never a new gate-name scan.
- **Rationale**: Confirmed live this session — this mechanism is ALREADY implemented and
  ALREADY wired as `scripts/pre_build_verification.sh` invariant 38, and is what produced
  the exact "414 unimplemented against baseline 403" figure BOB-237 tracks. Building a
  second scanner would be a byte-identical fork of already-correct, already-tested logic.
- **Alternatives considered**: Re-implementing a `CM-*` name grep directly in the new
  orchestrator — rejected outright; this project's own inherited constitution
  (§11.4.251, byte-identical-fork prohibition) explicitly forbids maintaining two
  parallel implementations of the same check.

## 3. Enumerating surface 3 — the coverage-escape discovery ledger

- **Decision**: Build one new parser, `scripts/lib/audit_ledger_parser.sh`, that reads
  `docs/QA_DISCOVERY_LEDGER.md`'s existing "## Entries" section, splits it on `### `
  headings (one per entry), and reports any entry whose body lacks a `**new-check:**`
  field as an open coverage-escape.
- **Rationale**: Confirmed live this session — the ledger already has a stable,
  well-documented schema (`id` / `date` / `channel` / `summary` / `escape-audit` /
  `new-check`, explicitly stated in its own "## Schema" section, Revision 17, last
  amended 2026-08-25) and real historical entries following it consistently. No existing
  automated reader exists for it — this is the one genuinely new enumeration surface.
- **Alternatives considered**: Converting the ledger to YAML/JSON for easier parsing —
  rejected as out of scope and needlessly invasive to an established, actively-edited,
  17-revision human document with real historical content; a plain-text schema parser is
  sufficient and non-destructive.

## 4. Making closure evidence independently reproducible (FR-004/006/013)

- **Decision**: Every closure evidence artifact records the exact command invoked, its
  captured stdout/stderr, its exit code, and a timestamp. Independent re-verification
  re-runs the SAME command from a fresh shell and compares the SEMANTIC result (exit
  code and any pass/fail counts the command itself reports) — never a byte-for-byte diff
  of the full captured text.
- **Rationale**: This is the exact pattern this session already proved out manually
  across every closed item (BOB-196, BOB-187, BOB-159, BOB-175 — each independently
  re-run and its pass/fail counts cross-checked before acceptance). Byte-for-byte
  comparison would false-positive on legitimately non-deterministic output (timestamps,
  PIDs, wall-clock durations) — exactly the false-positive-refusal class this project's
  inherited constitution (§11.4.201(1)) treats as equally severe to the gap being
  closed.
- **Alternatives considered**: Byte-identical output hashing — rejected for the reason
  above; trusting the closing agent's self-report without independent re-run — rejected
  outright, since that is precisely the "bluff" this entire feature exists to eliminate.

## 5. Detecting and guarding against evidence-corruption side effects (FR-008)

- **Decision**: Before running any item's verification command, snapshot the mtime and
  content hash of every git-tracked file OUTSIDE that item's own `docs/qa/<id>/`
  directory. After the command completes, diff against the snapshot. Any tracked file
  that changed and is itself a closure-evidence artifact for a DIFFERENT item is
  automatically restored (`git checkout --`) and the incident is recorded in the run
  log rather than silently absorbed.
- **Rationale**: This is a direct, formalized generalization of a REAL incident this
  session already hit and manually resolved: a diagnostic `pytest tests/scaling/` run
  (intended as read-only investigation) had a live side effect of overwriting
  `docs/qa/BOB-109/*.json` with fresh, transient-connection-refused evidence, staged in
  git. It was caught only because the conductor happened to run `git status` before a
  destructive command and investigated the diff before reverting it (per this project's
  own git-safety discipline). This feature makes that catch automatic and mandatory for
  every future closure, rather than dependent on an operator or agent noticing by hand.
- **Alternatives considered**: Running every item's verification inside a fully isolated
  git worktree or container — rejected as a heavier first-pass solution than needed; the
  git-diff-snapshot approach is cheap, has already been proven sufficient by the real
  incident it is modeled on, and does not require standing up new isolation
  infrastructure this project does not otherwise use for routine test runs.

## 6. Standing/recurring mechanism placement (FR-009)

- **Decision**: Add one new, initially-advisory (non-blocking) invariant to the existing
  `scripts/pre_build_verification.sh` gate suite, which already runs as an explicit
  stage of every `scripts/commit-push-all.sh` invocation.
- **Rationale**: Principle VI is an absolute "NO CI/CD PIPELINES" hard stop (no GitHub
  Actions, no `.gitlab-ci.yml`, no scheduled pipeline of any kind) — this rules out a
  cron job or hosted scheduler as the recurring trigger. The project's own constitution
  additionally states "Boba ships NO blocking git hooks" as a deliberate §11.4.234
  always-unblocked-commit design choice, ruling out a new git hook. The existing manual
  gate suite already satisfies FR-009's "recurring cadence without manual re-scoping"
  requirement, since it runs on every commit without anyone needing to remember to
  invoke it separately.
- **Alternatives considered**: A systemd timer — rejected as introducing a new
  host-level automation surface this project does not otherwise use, and one that could
  itself become a Principle XIII host-safety concern if misconfigured to run
  unboundedly; a dedicated standalone "run me periodically" script the operator must
  remember to invoke — rejected as reintroducing exactly the "manual re-scoping"
  failure mode FR-009 exists to close.

## 7. Risk-ordering closure work within a bounded session (FR-012)

- **Decision**: Sort enumerated items for closure by the tracker's own existing
  `reopens_count` (descending) then `last_modified` (most recent first) fields.
- **Rationale**: These fields already exist in the workable-items schema and are already
  the basis for this project's own inherited risk-ordering discipline
  (§11.4.132/§11.4.189 — most-reopened items get the deepest scrutiny first). No new
  instrumentation or scoring model is needed.
- **Alternatives considered**: A fresh bespoke severity-scoring formula — rejected as
  unneeded complexity given the existing fields already serve this exact purpose and are
  already populated for every tracked item.

## 8. Concurrency and collision avoidance across parallel closures (FR-011)

- **Decision**: Reuse the project's already-proven combination of (a) `scripts/
  commit-push-all.sh --scope <path>` for commit-time isolation and (b) explicit,
  disjoint file-scope declarations when dispatching parallel closure work to
  subagents.
- **Rationale**: This exact mechanism was used successfully this session across six
  concurrently-dispatched closure efforts (BOB-187, BOB-159, BOB-196, BOB-223, BOB-097,
  BOB-175) with zero file collisions, by explicitly scoping each dispatch's allowed
  files and holding back any item whose scope would overlap an in-flight one (as this
  plan does explicitly for BOB-231/BOB-240 pending BOB-223/BOB-175's own completion).
  Nothing new needs to be built; this plan's execution strategy simply documents and
  continues the proven discipline.
- **Alternatives considered**: A formal file-lock daemon or database-backed claim
  registry — rejected as over-engineering relative to the project's current scale, where
  the manual-discipline approach has already been exercised successfully and no
  collision has yet occurred under it.
