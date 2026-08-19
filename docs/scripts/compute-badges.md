# scripts/compute-badges.sh — §11.4.259 machine-derived README badge regenerator

**Revision:** 1
**Last modified:** 2026-08-18T22:29:59Z
**Status:** active
**Item:** BOB-118 (§11.4.6 bluff audit — task-ad3205a9)

## Overview

`scripts/compute-badges.sh` regenerates the "python tests" and "frontend
tests" shields.io badges in `README.md`, plus the matching Contributing-
section bullets and a corroborating `## Test counts` table in
`docs/TESTING.md`, from REAL numbers produced by a live invocation of the
tools that actually count those tests — never a hand-typed or
carried-forward number. It is the fix for BOB-118 and the standing
mechanism that keeps the same class of bug from recurring.

## Why this exists — BOB-118

`docs/qa/task-ad3205a9-*` (a §11.4.6 no-guessing bluff audit) found that
README.md's badge row read `python tests-585 passing` and
`frontend tests-182 passing`, while a real `pytest --collect-only` over
`tests/` collected **5248** tests — roughly 9x more than the badge
claimed. The cited "authoritative source", `docs/TESTING.md`, contained
**zero** occurrences of either number anywhere in the file — the badge
could not be corroborated by any tracked document. This is exactly the
class of defect §11.4.259 exists to make structurally impossible: every
README badge MUST be machine-derived, never hand-picked.

## What it computes

| Badge / bullet | Real command | Notes |
|---|---|---|
| `python tests` badge (whole tree) | `pytest --collect-only -q tests/ --import-mode=importlib` | Parses pytest's own `N tests collected` summary line. |
| Contributing bullet "unit + e2e + contract" | sum of `pytest --collect-only -q tests/{unit,e2e,contract}/` | Scoped to match the bullet's own stated suite scope — never the whole-tree number under a narrower label. |
| `frontend tests` badge | `frontend/node_modules/.bin/vitest list --run` | Exact per-test-case count. Falls back to a labelled grep proxy over `it(`/`test(` declarations when `node_modules` is absent (never silently presented as exact). |
| `## Test counts` table in `docs/TESTING.md` | all of the above, plus `tests/integration/` | The corroborating source the badge audit found missing. |

Two badges (`challenges`, `pre-build invariants`) were verified fresh in a
prior session and are cross-checked (not rewritten) by this script — see
the counts printed to stdout on every run.

## Usage

```bash
# Compute + rewrite README.md and docs/TESTING.md in place
scripts/compute-badges.sh

# Compute only — print whether the badges are stale, write nothing.
# Exit 0 = in sync, exit 2 = stale (advisory; callers must not treat
# this as fatal per §11.4.234 always-unblocked).
scripts/compute-badges.sh --check

# Point at alternate files (used by the paired §1.1 mutation test)
scripts/compute-badges.sh --check --readme /tmp/fixture-README.md --testing-md /tmp/fixture-TESTING.md
```

## Wording: "collected" not "passing"

The regenerated badges say **"N collected"**, not "N passing". Running
the full 5248-test tree (many of which need live services, Docker/Podman,
or hardware) end-to-end is outside what a badge-refresh script can
honestly assert on every invocation. "Collected" is the claim this
script can always verify in seconds with zero infrastructure
dependencies: the test exists and pytest/vitest can find it. Asserting
"passing" without having actually run every one of those tests in the
same invocation would just be a differently-shaped version of the same
bluff BOB-118 reports.

## Edge cases (honest failure mode)

If the python interpreter cannot be resolved (mirrors `ci.sh`'s fallback
chain: `$PYTHON` → `.venv/bin/python` → `python3.13` → `python3.12` →
`python3`) or `pytest --collect-only` produces no parseable summary line,
the badge is emitted as `N/A (<reason>)` in shields.io's `lightgrey`
color — never a fabricated number (§11.4.6). Same discipline for the
frontend count when neither `vitest` nor any `*.spec.ts` file can be
found.

## Related scripts

- `scripts/pre_build_verification.sh` invariant `CM-BADGE-FRESHNESS-CHECK`
  calls `compute-badges.sh --check` as a non-blocking WARN (never FAIL,
  per §11.4.234) so a drifted badge surfaces on every pre-build sweep
  instead of silently aging for months.
- `docs/TESTING.md` — the corroborating authoritative source this script
  keeps in sync.

## Last verified

2026-08-18, this session: `--check` correctly reported the pre-fix
README as stale (`5248` vs the stale `585`, `371` vs the stale `182`),
then a clean run regenerated both files and a follow-up `--check`
reported in-sync. See `docs/qa/task-bob118-fix/` for the captured
before/after evidence.
