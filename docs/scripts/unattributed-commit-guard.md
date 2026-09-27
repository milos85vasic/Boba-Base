# `scripts/hooks/unattributed-commit-guard.sh` — unattributed-commit detector

**Revision:** 2
**Last modified:** 2026-09-27T15:30:00Z
**Purpose:** §11.4.84 / §11.4.238 guard that finds commits landing on this
repository with no attribution — no tracked-item id, no task, no PR reference.
**Last verified:** 2026-09-27

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

RE-MEASURED 2026-09-27 (HEAD 30221da): **26** violating commits are reachable
from HEAD (23 bare `Auto-commit`, 1 `Auto-commit <epoch-ms>`, 2 `sync: …`), and
a scan of `--all` refs finds the same 26. The default range is now
`1.3.0..HEAD` and holds **0** — the "14" above was a property of the range, not
of the repository, which is why the standing gate scans all of HEAD instead.

## Prerequisites

- A git working tree (the guard reads history only; it never writes).
- `git` on PATH. No network, no container runtime, no credentials.

## Usage

    bash scripts/hooks/unattributed-commit-guard.sh                # default range
    bash scripts/hooks/unattributed-commit-guard.sh --range A..B   # explicit range
    bash scripts/hooks/unattributed-commit-guard.sh --self-test    # §11.4.107(10)
    bash scripts/hooks/unattributed-commit-guard.sh --range HEAD \
        --baseline scripts/pre_build/cm_unattributed_commit.baseline  # ratchet (pre-build 63)

Default range is "since the last tag reachable from HEAD".

Exit status: `0` clean, `1` violations found (each named), `2` the result
could not be determined (bad range, unreadable or header-less baseline).

### Ratchet mode (`--baseline FILE`)

Adopted per the operator's BOB-162 decision, option (b): a **one-time
monotone-decrease ratchet**. The baseline file lists the grandfathered commits
**by exact 40-hex SHA** (first field of each non-comment line) and carries two
header lines:

    # SEED_CUTOFF_EPOCH: <committer time of the newest grandfathered commit>
    # SEEDED_COUNT: <number of rows at seeding>

Why SHA and not a count: a count lets a new violation replace a retired one
(one in, one out) and cannot tell a new `Auto-commit` from an old one with the
same subject. A SHA can never match a commit that did not exist at seeding.

In this mode the run FAILs (`1`) on any of:

| Output line | Meaning |
|---|---|
| `NEW <sha> <subject>` | a violating commit that is not in the baseline |
| `RETIRED <sha>` | a baselined commit inside the range that is no longer a violation — delete the row |
| `INTEGRITY … exceeds SEEDED_COUNT` | the baseline was grown — the set may only shrink |
| `INTEGRITY … newer than SEED_CUTOFF_EPOCH` | a row names a commit made after the seed — it cannot be grandfathered |
| `INTEGRITY duplicate SHA row(s)` | the same SHA is listed twice |

A missing header or a row that is not a full SHA is exit `2` (unverifiable,
never a pass). Baselined commits outside the range are ignored, so the same file
works for any range.

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

**Ratchet mutation (re-run by the test on every execution):** replacing the
line marked `# RATCHET-NEW-SET` with an empty set makes a new unattributed
commit on top of the grandfathered history pass with exit 0; the unmutated
guard refuses it with exit 1.

## Wiring

Pre-build invariant 63 (`CM-UNATTRIBUTED-COMMIT-RATCHET`) in
`scripts/pre_build_verification.sh` runs the ratchet mode over all of HEAD
against `scripts/pre_build/cm_unattributed_commit.baseline` (seeded with the 26
commits above). It is BLOCKING.

The seam is the pre-build sweep, not the pre-push hook: the commits this guard
exists for are produced and pushed from another host or session, so a push hook
on this host never sees them; they become visible here the moment they are in
HEAD.

Honest limits: the SEED_CUTOFF_EPOCH check trusts committer timestamps, so a
producer that backdates its commits below the cutoff could be added to the
baseline without tripping it (the SEEDED_COUNT check still refuses the extra
row, and the change is visible in review). History is never rewritten to shrink
the set (§11.4.113), so the 26 remain unless the closed pattern set changes.

## Related

- `tests/hooks/test_unattributed_commit_guard.sh` — 9 real-invocation assertions
- `tests/hooks/test_unattributed_commit_ratchet.sh` — 12 assertions for the
  ratchet mode in mktemp repos, the paired mutation, and the real-repo scan
- `scripts/pre_build/cm_unattributed_commit.baseline` — the grandfathered set
- `docs/history/BOB-079-attributed-auto-commit-history.md` — the attribution record
  built FROM this guard's output (BOB-079)
- `scripts/hooks/check-brief-inputs.sh` — sibling dispatch-hygiene guard
