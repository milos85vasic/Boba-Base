# check_cm_script_docs_sync.sh

**Revision:** 1
**Last modified:** 2026-09-26T14:00:00Z

## Overview

Gate `CM-SCRIPT-DOCS-SYNC` (pre-build invariant 61, BOB-242). Enforces the
§11.4.18 script documentation mandate: every shell script under `scripts/` has a
guide at `docs/scripts/<name>.md`, and the guide is not older than the script.

## Why this exists

The constitution named this gate but nothing implemented it. BOB-223 registered
it as gate debt after finding that writing a mandated guide could trip another
gate while never writing one cost nothing. This is the implementation.

## Prerequisites

`bash`, `git`, `grep`, `sort`, `comm`. The argument must be a git repository root.

## Usage

```bash
bash scripts/pre_build/check_cm_script_docs_sync.sh .            # gate verdict
bash scripts/pre_build/check_cm_script_docs_sync.sh . --list     # print the current finding set
CM_SDS_VERBOSE=1 bash scripts/pre_build/check_cm_script_docs_sync.sh .   # list every baselined row
```

## What counts as a finding

| Key | Meaning |
|-----|---------|
| `NODOC:<path>` | no `docs/scripts/<name>.md` (name = basename without extension) |
| `DOCBEHIND:<path>` | the script changed after its guide |

"Changed" is the last commit touching the file. A file with uncommitted edits,
or an untracked file, counts as changed now: editing a script without its guide
is caught before the commit, and editing both together is not a finding.

## Ratchet baseline

`scripts/pre_build/cm_script_docs_sync.baseline` holds the finding set that
existed when the gate landed (seeded 2026-09-26: 52 `NODOC` + 11 `DOCBEHIND` =
63 rows). It is compared as a set:

- a finding not in the baseline is **NEW** and fails the gate;
- a baseline row with no matching finding is **RETIRED** and fails the gate —
  delete the row in the same change that writes or updates the guide;
- rows in both are reported as baselined and do not fail.

The ratchet is the repository's established default for set-based gates. An
operator may instead choose a hard floor or changed-files-only enforcement
(§11.4.66); that decision is not made here.

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | no NEW finding and no RETIRED row |
| 1 | NEW finding(s) and/or RETIRED row(s) |
| 2 | harness error: bad arguments, not a git repo, or zero scripts enumerated |

## Edge cases

- The gate pins `LC_ALL=C`: `sort` and `comm` must agree on collation, and
  under `en_US.UTF-8` they did not (`run_all_challenges` vs `run-tests`), so
  `comm` warned and ran on input it considered unsorted.

- Two scripts with the same basename in different directories share one guide.
- A script deleted in the working tree is skipped.
- Scripts outside `scripts/` (for example `tests/`) are out of scope.

## Related scripts

- `tests/pre_build/test_check_cm_script_docs_sync.sh` — 12 arms: golden good and
  bad, ratchet, golden-false, a collation regression, fail-closed, paired mutation.
- `scripts/pre_build/check_cm_doc_revision_header_present.sh` — the §11.4.44
  header check on the same guides.

## Last verified

2026-09-26 — real tree after seeding: gate reports no NEW finding from committed state (one NEW finding came from a concurrent stream's uncommitted edit of scripts/zero_shortcomings_audit.sh, correctly flagged); test suite 12 passed, 0 failed.
