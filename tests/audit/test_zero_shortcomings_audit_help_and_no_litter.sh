#!/usr/bin/env bash
# Purpose: (a) --help documents every enumerate/verify-closure option;
# (b) the pre-build stage and standing-check do not litter docs/qa.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
SCRIPT=scripts/zero_shortcomings_audit.sh
pass=0; fail=0
check() { if eval "$2"; then printf '  PASS: %s\n' "$1"; pass=$((pass+1)); else printf '  FAIL: %s\n' "$1"; fail=$((fail+1)); fi; }

help_out="$(bash "$SCRIPT" --help 2>&1)"
check "control: help shows a known option (--json)" 'grep -q -- "--json" <<<"$help_out"'
for opt in --sort-by-risk --require-layer "blocked"; do
    check "help mentions $opt" 'grep -q -- "$opt" <<<"$help_out"'
done

# Stage code must redirect the log dir to a temp dir and clean it up.
# The stage is the function zsc_standing_stage (its runtime branches are
# unit-tested in tests/pre_build/test_check_cm_zero_shortcomings_standing.sh).
stage="$(sed -n '/^zsc_standing_stage() {/,/^}/p' scripts/pre_build_verification.sh)"
check "control: stage extraction is non-empty" '[[ -n "$stage" ]]'
check "stage exports AUDIT_STANDING_LOG_DIR from mktemp -d" 'grep -q "AUDIT_STANDING_LOG_DIR=\"\${logdir}\"" <<<"$stage" && grep -q "logdir=\"\$(mktemp -d" <<<"$stage"'
check "stage removes the temp dir" 'grep -q "rm -rf \"\${log}\" \"\${logdir}\"" <<<"$stage"'

# Functional: with the override, nothing lands under the repo docs/qa dir.
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
real=docs/qa/zero_shortcomings_audit
# Count with find guarded by `|| true`: `ls` of a directory that does not
# exist exits 2, which under set -o pipefail aborted this whole test before its
# summary line (a FAIL-bluff from the instrument, not from the product).
count_real() { { find "$real" -mindepth 1 -maxdepth 1 2>/dev/null || true; } | wc -l; }
before="$(count_real)"
# --reverify 0: closed-item re-verification would re-run real recorded
# commands (minutes); where it writes its incident log is covered by
# tests/audit/test_zero_shortcomings_audit_standing_reverify.sh scenario 3.
AUDIT_STANDING_LOG_DIR="$T" bash "$SCRIPT" standing-check --reverify 0 >/dev/null 2>&1 || true
after="$(count_real)"
check "override dir received the log" '[[ "$(ls "$T" | wc -l)" -ge 1 ]]'
check "repo docs/qa/zero_shortcomings_audit unchanged" '[[ "$before" -eq "$after" ]]'

printf 'test_zero_shortcomings_audit_help_and_no_litter: %d passed, %d failed\n' "$pass" "$fail"
[[ "$fail" -eq 0 ]]
