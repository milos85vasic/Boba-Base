# CLI Contract: `scripts/zero_shortcomings_audit.sh`

This is the interface contract other project tooling (`scripts/pre_build_verification.sh`,
`scripts/commit-push-all.sh`, and any operator or subagent invoking the audit directly)
depends on. Following this project's existing conventions (Principle VII), the script
uses the shared color-print helpers and implements `-h/--help`.

## Invocation

```text
scripts/zero_shortcomings_audit.sh <mode> [options]
```

## Modes

### `enumerate`

Read-only. Enumerates all three surfaces and prints a summary report. Exits `0`
regardless of findings (findings are reported, not gated) unless the enumeration itself
fails to run (for example, `docs/workable_items.db` is unreadable) — that failure exits
non-zero, per §11.4.201's guard-honesty discipline (a failed measurement must never read
as a clean zero).

```text
scripts/zero_shortcomings_audit.sh enumerate [--json] [--surface backlog|gates|escapes]
```

- `--json`: emit the `AuditRunRecord`'s `surface_counts` and per-item lists as JSON
  instead of the human-readable report, for consumption by
  `scripts/pre_build_verification.sh`'s new invariant.
- `--surface <name>`: restrict enumeration to one surface (for targeted investigation);
  omitting it enumerates all three.

**Exit codes**: `0` = enumeration completed (findings, if any, are in the report body,
never in the exit code alone — an enumeration completing with 40 open items still exits
`0`, since `enumerate` mode never gates); `1` = enumeration itself failed to run against
one or more surfaces (a tooling failure, distinct from "found open items").

### `verify-closure <item-id>`

Independently re-runs one item's recorded `ClosureEvidenceArtifact.command` and compares
`exit_code` + `result_summary` against the stored values (FR-004/006/013).

```text
scripts/zero_shortcomings_audit.sh verify-closure <item-id> [--reopen-on-mismatch]
```

- `--reopen-on-mismatch`: if the re-run's result does not match the recorded evidence,
  automatically call the tracker CLI to reopen the item (FR-013). Without this flag, a
  mismatch is reported but the item is left as-is (dry-run mode, for investigation).

**Exit codes**: `0` = re-run matched the recorded evidence; `1` = re-run did not match
(a genuine mismatch was found) OR a usage/invalid-id/internal refusal occurred before the
command ran (e.g. invalid `item-id`, missing option value, could not snapshot evidence) —
callers MUST read the printed message to tell these apart; `2` = the item has no recorded
evidence to verify against, the evidence layer is too weak, the `**Test Type:**` is
missing/invalid, or no `**Command:**` is recorded (itself a finding — a closed item with
no evidence is a bluff by definition); `3` = mismatch found and `--reopen-on-mismatch` was
given but the tracker reopen itself FAILED (explicit error, never swallowed).
Known contract debt: usage/internal refusals share exit `1` with a genuine mismatch.

### `standing-check`

The FR-009 recurring mode, invoked as a new stage inside
`scripts/pre_build_verification.sh`. Always equivalent to `enumerate --json`, but
additionally appends an `AuditRunRecord` with `mode = standing-check` to
`docs/qa/zero_shortcomings_audit/<run-id>.log`. Never performs closure work itself
(per data-model.md's `AuditRunRecord` validation rule).

```text
scripts/zero_shortcomings_audit.sh standing-check
```

**Exit codes**: initially always `0` (advisory, per plan.md's Human Checkpoint 4 —
promotable to blocking only after a burn-in period confirms zero false positives); once
promoted, exits non-zero only on a genuinely new finding not present in the previous
recorded run (a *regression* in the zero-shortcomings state), never on the pre-existing,
already-tracked backlog count alone — a gate that blocks every commit on the mere
existence of the already-known 41-item backlog would make the commit mechanism
unusable, which Principle VI's "always-unblocked" design explicitly forbids.

## Global options

- `-h`, `--help`: usage and examples, per Principle VII.
- `--dry-run`: for any mode that would mutate state (currently only
  `verify-closure --reopen-on-mismatch`), print what would happen without doing it.

## What this contract explicitly does NOT cover

- This tool never itself implements a fix for an enumerated item — closure work (writing
  the actual fix + its RED/GREEN tests + its evidence artifact) happens through the
  project's existing per-domain tooling (pytest, `go test`, `ng test`, the
  `workable-items` CLI for tracker updates); this tool's job is enumeration, evidence
  re-verification, corruption-guarding, and standing-check wiring — never the fix
  itself.
