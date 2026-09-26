#!/usr/bin/env bash
# Purpose: prove the pre-build sweep runs the ADVISORY zero-shortcomings
# standing-check stage, labels it consistently with the sweep's total, and
# that the stage never contributes a FAIL to the sweep.
# Usage: bash tests/pre_build/test_check_cm_zero_shortcomings_standing.sh
# Env:   ZSC_SWEEP_OUT=<file> reuse a captured sweep output instead of re-running
#        (the sweep is long and heavy); ZSC_SWEEP_RC=<n> is its exit status.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."

pass=0
fail=0
check() {
    local desc="$1"; shift
    if "$@"; then
        printf '  PASS: %s\n' "$desc"; pass=$((pass + 1))
    else
        printf '  FAIL: %s\n' "$desc"; fail=$((fail + 1))
    fi
}

out_file="$(mktemp)"
trap 'rm -f "$out_file"' EXIT
rc=0
if [[ -n "${ZSC_SWEEP_OUT:-}" && -f "${ZSC_SWEEP_OUT}" ]]; then
    cp "$ZSC_SWEEP_OUT" "$out_file"; rc="${ZSC_SWEEP_RC:-0}"
else
    nice -n 19 ionice -c 3 bash scripts/pre_build_verification.sh >"$out_file" 2>&1 || rc=$?
fi

# Control needle (§11.4.273): the label grep must see a known-present stage.
needle='CM-MD-EXPORT-TWINS-COMMITTABLE'
has_needle() { grep -aq "^\[[0-9]*/[0-9]*\] ${needle}" "$out_file"; }
check "control needle: instrument sees a known existing stage label" has_needle

stage_line() { grep -a '^\[[0-9]*/[0-9]*\] CM-ZERO-SHORTCOMINGS-STANDING' "$out_file"; }
check "the sweep prints exactly one CM-ZERO-SHORTCOMINGS-STANDING stage" \
    test "$(stage_line | wc -l)" -eq 1

# The stage's own label must be N/N with the sweep's highest denominator.
total_ok() {
    local l n d max
    l="$(stage_line | head -1)"
    n="$(sed -E 's/^\[([0-9]+)\/([0-9]+)\].*/\1/' <<<"$l")"
    d="$(sed -E 's/^\[([0-9]+)\/([0-9]+)\].*/\2/' <<<"$l")"
    max="$(grep -aoE '^\[[0-9]+/[0-9]+\]' "$out_file" | sed -E 's/.*\/([0-9]+)\]/\1/' | sort -n | tail -1)"
    [[ -n "$n" && "$n" == "$d" && "$d" == "$max" ]]
}
check "stage label is [N/N] and N equals the sweep's highest total" total_ok

# Strong, non-vacuous advisory assertions: no FAIL line names this stage and
# the stage printed a PASS or a WARN result line (something real ran).
no_fail_line() { ! grep -aE 'FAIL \[[0-9]+\]: CM-ZERO-SHORTCOMINGS' "$out_file"; }
check "no FAIL line is emitted for the stage" no_fail_line
result_line() { grep -aE '(PASS \[[0-9]+\]|WARN): CM-ZERO-SHORTCOMINGS-STANDING' "$out_file"; }
check "the stage emitted a PASS or WARN result line" result_line

# Advisory: the stage must not change the sweep's exit status. The sweep exit
# must equal what its OTHER stages alone imply (1 iff some non-stage FAIL line).
other_fail() { grep -aE 'FAIL \[[0-9]+\]:' "$out_file" | grep -qv 'CM-ZERO-SHORTCOMINGS'; }
exit_matches_other_stages() {
    if other_fail; then [[ "$rc" -eq 1 ]]; else [[ "$rc" -eq 0 ]]; fi
}
check "sweep exit status is determined by the other stages only" exit_matches_other_stages

printf 'test_check_cm_zero_shortcomings_standing: %d passed, %d failed\n' "$pass" "$fail"
[[ "$fail" -eq 0 ]]
