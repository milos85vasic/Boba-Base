# challenges/scripts/codegraph_gitignore_honor_challenge.sh — BOB-104 §11.4.115 RED/GREEN regression guard

**Revision:** 1
**Last modified:** 2026-08-19T00:00:00Z
**Status:** active
**Item:** BOB-104 (CodeGraph 1.5.0 nested-.gitignore honor regression)

## Overview

`challenges/scripts/codegraph_gitignore_honor_challenge.sh` is a
falsifiable §11.4.115 RED/GREEN polarity guard covering the CodeGraph
1.5.0 regression that walked into `frontend/node_modules` +
`extension/node_modules` (both nested-`.gitignore`-excluded), producing
32,260 files / 514,456 nodes vs the 2026-06-06 baseline of
509 files / 8,906 nodes — a ~63x file blow-up. Upstream issue
https://github.com/colbymchenry/codegraph/issues/1567; draft PR #1568.
Boba's closure obligation is a real, mechanical regression guard on the
invariant "a gitignore-honoring indexer must NOT sweep node_modules".

## Design (static-scan approach)

The challenge is a **static file-count comparison**, not a live codegraph
re-index. Rationale (§11.4.6, weighed against options):

* it does **not** touch `.codegraph/` state;
* it runs in seconds, not minutes;
* it is deterministic and needs no codegraph binary present;
* it is falsifiable — the RED and GREEN thresholds are numeric.

Two populations are measured:

| population        | command                                      | meaning                                              |
| ----------------- | -------------------------------------------- | ---------------------------------------------------- |
| correct oracle    | `git ls-files -co --exclude-standard \| wc -l` | what a gitignore-HONORING indexer would sweep        |
| broken ceiling    | `find . -type f -not -path './.git/*' \| wc -l` | what a gitignore-BROKEN indexer would sweep         |

The 2026-06-06 baseline (BOB-104 opening measurement) is **509 files**.

## Polarity contract (§11.4.115)

| mode              | assertion                                     | passes when                                       |
| ----------------- | --------------------------------------------- | ------------------------------------------------- |
| `RED_MODE=1`      | broken ceiling > BASELINE * 10 (>= 5090)      | the risk surface is real (a broken path would    |
|                   |                                               | definitely blow past any sane baseline)           |
| `RED_MODE=0` (GREEN, default) | correct oracle <= 5000            | invariant holds — indexer would not blow up      |

`GREEN_MAX_FILES = 5000` sits an order of magnitude above the 2026-06-06
baseline, absorbing normal repo growth without becoming decoration.
`RED_MIN_BROKEN = 5090` (10 * baseline) proves the guarded risk surface
still exists on this checkout (if someone deleted every node_modules the
RED assertion would fail honestly — the ceiling would collapse).

## Usage

```bash
# GREEN mode (default) — asserts the invariant holds:
bash challenges/scripts/codegraph_gitignore_honor_challenge.sh

# RED mode — asserts the risk surface is real:
RED_MODE=1 bash challenges/scripts/codegraph_gitignore_honor_challenge.sh
```

Every run prints the measured baseline / correct-oracle / broken-ceiling
/ thresholds as evidence (§11.4.6 numbers, not claims).

## Exit codes

| code | meaning                                                   |
| ---- | --------------------------------------------------------- |
| 0    | polarity assertion holds for the selected mode.           |
| 1    | polarity assertion violated (guarded invariant broke).    |
| 2    | environment error (not a git worktree, tooling missing).  |

## Verification observed 2026-08-19

* GREEN: correct oracle = 2080, threshold 5000 -> exit 0 PASS.
* RED: broken ceiling = 129978, threshold 5090 -> exit 0 PASS.

The correct oracle sits well below GREEN_MAX_FILES; the broken ceiling
towers ~63x above it — the exact shape the 1.5.0 regression produced.

## Cross-references

* §11.4.6 no-guessing (measured numbers cited)
* §11.4.115 RED-first polarity contract
* §11.4.201 guards assert the real condition (self-falsifiable)
* §11.4.238 automated QA discovers, not confirms
* Upstream: https://github.com/colbymchenry/codegraph/issues/1567, PR #1568
