# `scripts/hooks/unattributed-commit-guard.sh` — unattributed-commit detector

**Revision:** 1
**Last modified:** 2026-08-21T19:55:00Z
**Purpose:** §11.4.84 / §11.4.238 guard that finds commits landing on this
repository with no attribution — no tracked-item id, no task, no PR reference.
**Last verified:** 2026-08-21

---

## Overview

A commit whose entire subject is `Auto-commit` (or `sync: …`) and whose body
carries no `BOB-NNN` / task / PR reference cannot be traced to the work that
motivated it. That is a §11.4.238 discovery problem rather than a style
complaint: when such a commit later turns out to have introduced a defect, there
is no item to reopen (§11.4.214) and no review to point at (§11.4.142).

This guard makes that population **mechanically visible** instead of something a
human notices while reading `git log`.

MEASURED on this repository, 2026-08-21: **21** bare `Auto-commit` subjects exist
across all refs, and **14** commits violate the rule in the default range
(`v1.0.0-rc..HEAD`) — 11 bare `Auto-commit` plus 2 `sync: …`, the latter class
missed entirely by the narrower grep that preceded this guard.

## Prerequisites

- A git working tree (the guard reads history only; it never writes).
- `git` on PATH. No network, no container runtime, no credentials.

## Usage

    bash scripts/hooks/unattributed-commit-guard.sh                # default range
    bash scripts/hooks/unattributed-commit-guard.sh --range A..B   # explicit range
    bash scripts/hooks/unattributed-commit-guard.sh --self-test    # §11.4.107(10)

Default range is "since the last tag reachable from HEAD".

Exit status: `0` clean, non-zero when violations are found (each named).

## Edge cases

- **A referenced `Auto-commit` is NOT a violation.** A commit may keep the bare
  subject provided its body cites an item; the guard's false-positive control
  needle covers exactly this case, so a legitimately-attributed commit is never
  flagged (§11.4.201(1) — a false refusal is as forbidden as a false pass).
- **Merge commits** inherit their subject from git and are not authored prose.
- **An empty range** (no commits since the last tag) is a clean `0`, not an error.

## Internal behaviour

The subject pattern set is CLOSED and explicit rather than heuristic: matching
"anything that looks low-effort" would produce exactly the false refusals
§11.4.201(1) forbids. A commit is a violation only when its subject matches the
closed set AND the FULL message carries no reference.

`--self-test` ships golden-good, golden-bad, and the false-positive control
needle, and is the §11.4.107(10) self-validation: a guard never observed FAILing
on a genuinely-broken input is unvalidated instrumentation (§11.4.115(F)).

**Paired §1.1 mutation (verified):** neutering the pattern match makes the
self-test FAIL and makes the real scan silently report OK against 21 known
violations — the exact bluff. Restored, the file is sha256-identical and the
scan again names the 14.

## Known gap — read this before trusting a green run

**This guard is not yet wired into any seam.** It runs when a human types it, so
it is not standing detection pressure (§11.4.226 — registration is not
coverage). Wiring it as-is would refuse every commit immediately, because the 14
pre-existing violations are real and cannot be fixed in the moment; that is a
§11.4.224(E) brownfield-adoption decision the operator owns, tracked as
**BOB-162** with the options enumerated. Until that answer is recorded, a clean
run of this guard means only "the range you asked about is clean".

## Related

- `tests/hooks/test_unattributed_commit_guard.sh` — 9 real-invocation assertions
- `docs/history/BOB-079-attributed-auto-commit-history.md` — the attribution record
  built FROM this guard's output (BOB-079)
- `scripts/hooks/check-brief-inputs.sh` — sibling dispatch-hygiene guard
