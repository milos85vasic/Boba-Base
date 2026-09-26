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
stage="$(sed -n '/^echo "\[59\/59\]/,/^rm -rf /p' scripts/pre_build_verification.sh)"
check "control: stage extraction is non-empty" '[[ -n "$stage" ]]'
check "stage exports AUDIT_STANDING_LOG_DIR from mktemp -d" 'grep -q "AUDIT_STANDING_LOG_DIR=.*ZSC_LOGDIR" <<<"$stage" && grep -q "ZSC_LOGDIR=\"\$(mktemp -d)\"" <<<"$stage"'
check "stage removes the temp dir" 'grep -q "^rm -rf .*ZSC_LOGDIR" <<<"$stage"'

# Functional: with the override, nothing lands under the repo docs/qa dir.
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
real=docs/qa/zero_shortcomings_audit
before="$(ls "$real" 2>/dev/null | wc -l)"
AUDIT_STANDING_LOG_DIR="$T" bash "$SCRIPT" standing-check >/dev/null 2>&1 || true
after="$(ls "$real" 2>/dev/null | wc -l)"
check "override dir received the log" '[[ "$(ls "$T" | wc -l)" -ge 1 ]]'
check "repo docs/qa/zero_shortcomings_audit unchanged" '[[ "$before" -eq "$after" ]]'

printf 'test_zero_shortcomings_audit_help_and_no_litter: %d passed, %d failed\n' "$pass" "$fail"
[[ "$fail" -eq 0 ]]
