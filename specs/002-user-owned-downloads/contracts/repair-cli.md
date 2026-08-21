# Contract: Ownership Repair

**Feature**: 002-user-owned-downloads
**Implements**: FR-004, FR-004a–g, FR-005, FR-006, FR-015
**Artifact**: `scripts/ownership_repair.sh`

## Purpose

Bring pre-existing content under the operator's ownership. Runs automatically on first
start (operator decision) and can also be invoked explicitly.

## Invocation

```bash
scripts/ownership_repair.sh                       # normal run; no-op if marker valid
scripts/ownership_repair.sh --force               # ignore the marker and re-walk
scripts/ownership_repair.sh --dry-run             # report what would change; change nothing
scripts/ownership_repair.sh --scope <path>        # override the declared scope file
```

## Exit codes

| Code | Meaning |
|---|---|
| `0` | every in-scope item is operator-owned (either repaired now, or already correct) |
| `1` | at least one item could not be repaired — reported individually |
| `2` | could not run (scope missing/unparseable) |

## Behavioural contract

- **Blocking (FR-004d)**: when invoked from startup it completes before any
  download-writing service accepts work. No background mode.
- **Unbounded (FR-004f)**: no self-imposed time limit. It runs to completion.
- **Resumable (FR-004a)**: the marker is written **only** after a fully successful pass.
  Interrupted ⇒ marker absent ⇒ next start resumes. Stopping the system mid-repair is
  therefore safe, and is the operator's escape hatch from a long run.
- **Idempotent (FR-004c)**: a second run with a valid marker is a no-op; with `--force`
  it re-walks and changes nothing already correct.
- **Scope-fenced (FR-005)**: touches only declared locations. Anything outside is not
  merely skipped — it must be impossible to reach.
- **Records before mutating (FR-004b)**: each change is written to the change record
  *before* the change is applied, so a crash still leaves a trail of what was touched.
- **Never relaxes permissions (FR-015)**: entries marked `preserve_mode` keep their bits.
  `config/boba.db` MUST remain no more permissive than mode 600. Bringing a credential
  store under the operator's ownership while widening who can read it would trade a
  usability defect for a security one.
- **Honest failure (FR-006)**: items it could not repair are listed individually. It MUST
  NOT report success for items it did not change, and MUST NOT exit `0` with failures
  outstanding.
- **Host-safe**: runs under `nice -n 19` / `ionice -c 3`; the tree may be large and the
  host runs mission-critical work (Principle XIII).

## Progress (FR-004e)

While blocking it MUST emit progress reflecting **real work completed** — items processed
against items discovered. A spinner or fixed-step estimate does not satisfy this: the
requirement exists so a long run on a large library is distinguishable from a hang.

## Both directions (§11.4.201(1))

- **golden-bad**: a tree seeded with non-operator-owned items → items repaired, exit `0`,
  change record non-empty
- **golden-good**: an already-correct tree → exit `0`, change record **empty**, nothing
  mutated
- **negative control**: a path outside the declared scope, seeded wrongly-owned → left
  untouched
- **interrupt case**: kill mid-run → marker absent → next run resumes and completes
- **preserve-mode case**: a `preserve_mode` entry keeps its exact bits after repair

## Explicitly out of scope

Concurrent-modification handling between the repair and an active download: impossible by
construction, because the repair blocks every download-writing service (FR-004g). Recorded
so a later reader sees it was decided, not overlooked.
