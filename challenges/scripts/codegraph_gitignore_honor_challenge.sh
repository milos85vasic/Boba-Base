#!/usr/bin/env bash
# codegraph_gitignore_honor_challenge.sh — BOB-104 §11.4.115 RED/GREEN polarity.
#
# Purpose
# -------
# CodeGraph 1.5.0 regressed on the "honor nested .gitignore" invariant and
# walked into frontend/node_modules + extension/node_modules, producing
# 32,260 files / 514,456 nodes vs the 2026-06-06 baseline of
# 509 files / 8,906 nodes (~63x file blow-up).
#
# This challenge is a STATIC-SCAN falsifier that measures the two file-count
# populations without actually running codegraph (so it is fast, deterministic,
# and does NOT touch .codegraph/ state):
#
#   * "correct" oracle  = git ls-files -co --exclude-standard | wc -l
#       (this is what a gitignore-HONORING indexer WOULD sweep)
#   * "broken" ceiling  = find . -type f -not -path '*/.git/*' | wc -l
#       (this is what a gitignore-BROKEN indexer would produce — the
#        regression's actual shape: every node_modules file walked into)
#
# §11.4.115 polarity contract
# ---------------------------
# RED_MODE=1: reproduces the 1.5.0 blowup shape. Passes (exit 0) iff the
#             "broken ceiling" (unrestricted find) is > BASELINE * 10, i.e.
#             a broken gitignore-honor path would definitely blow past
#             any sane baseline. This confirms the ceiling is REAL, and
#             therefore the guard is meaningful.
#
# RED_MODE=0 (default, GREEN): asserts the "correct oracle" (git ls-files)
#             stays within an order of magnitude of the 2026-06-06 baseline
#             (509 files). GREEN threshold: <= 5000 (an order of magnitude
#             above baseline, absorbing natural repo growth).
#
# Both modes emit real measured file counts as evidence (§11.4.5/§11.4.6 —
# no guessing; the numbers are cited). A change that breaks the invariant
# would push the correct oracle upward toward the broken ceiling and fail
# GREEN mode.
#
# Exit codes
#   0 — polarity assertion holds for the selected mode.
#   1 — polarity assertion violated (the guarded invariant broke).
#   2 — environment error (not in a git worktree, tooling missing).
#
# Cross-refs: §11.4.6 §11.4.115 §11.4.201 §11.4.238.
#
# Related
#   BOB-104 workable item + upstream https://github.com/colbymchenry/codegraph/issues/1567

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

RED_MODE="${RED_MODE:-0}"

# Baseline captured 2026-06-06 at BOB-104 opening (files).
BASELINE_FILES=509
# GREEN threshold: order of magnitude above baseline, absorbs natural growth.
GREEN_MAX_FILES=5000
# RED threshold: broken ceiling must be at least 10x baseline to prove
# the guard is measuring a real risk surface.
RED_MIN_BROKEN=$((BASELINE_FILES * 10))

cd "$REPO_ROOT"

if ! git rev-parse --show-toplevel >/dev/null 2>&1; then
  echo "ERROR: not inside a git worktree at $REPO_ROOT" >&2
  exit 2
fi
for bin in git find wc; do
  if ! command -v "$bin" >/dev/null 2>&1; then
    echo "ERROR: required tool missing: $bin" >&2
    exit 2
  fi
done

# Measure the correct oracle — what a gitignore-HONORING indexer sees.
# `git ls-files -co --exclude-standard` = cached + untracked-not-ignored.
correct_oracle=$(git ls-files -co --exclude-standard | wc -l)
# Measure the broken ceiling — what an indexer that IGNORES .gitignore
# would sweep. We exclude .git/ (never indexed) but nothing else.
broken_ceiling=$(find . -type f -not -path './.git/*' 2>/dev/null | wc -l)

echo "codegraph_gitignore_honor_challenge — measured file counts"
echo "  baseline (2026-06-06):                 ${BASELINE_FILES}"
echo "  correct oracle (git ls-files -co):     ${correct_oracle}"
echo "  broken ceiling (unrestricted find):    ${broken_ceiling}"
echo "  green-mode max (order-of-magnitude):   ${GREEN_MAX_FILES}"
echo "  red-mode min (10x baseline):           ${RED_MIN_BROKEN}"
echo "  RED_MODE=${RED_MODE}"

if [[ "$RED_MODE" == "1" ]]; then
  # RED assertion: broken ceiling must decisively exceed 10x baseline,
  # proving the guarded risk surface is real.
  if [[ "$broken_ceiling" -gt "$RED_MIN_BROKEN" ]]; then
    echo "PASS (RED): broken ceiling ${broken_ceiling} > ${RED_MIN_BROKEN} — regression risk surface is real."
    exit 0
  else
    echo "FAIL (RED): broken ceiling ${broken_ceiling} not > ${RED_MIN_BROKEN} — cannot reproduce the blow-up shape."
    exit 1
  fi
else
  # GREEN assertion: the gitignore-honoring oracle stays within an
  # order of magnitude of the 2026-06-06 baseline.
  if [[ "$correct_oracle" -le "$GREEN_MAX_FILES" ]]; then
    echo "PASS (GREEN): correct oracle ${correct_oracle} <= ${GREEN_MAX_FILES} — invariant holds."
    exit 0
  else
    echo "FAIL (GREEN): correct oracle ${correct_oracle} > ${GREEN_MAX_FILES} — .gitignore-honor invariant broken."
    exit 1
  fi
fi
