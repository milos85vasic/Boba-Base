#!/usr/bin/env bash
# Purpose: prove the pre-build sweep runs the ADVISORY zero-shortcomings
# standing-check stage, labels it consistently with the sweep's total, and
# that the stage never contributes a FAIL to the sweep.
# Usage: bash tests/pre_build/test_check_cm_zero_shortcomings_standing.sh
# Env:   ZSC_SWEEP_OUT=<file> reuse a captured sweep output instead of re-running
#        (the sweep is long and heavy); ZSC_SWEEP_RC=<n> is its exit status and
#        is REQUIRED with ZSC_SWEEP_OUT (a defaulted rc would make the exit-status
#        assertion vacuous).
#        ZSC_UNIT_ONLY=1 runs only the cheap stage-level unit checks (no sweep).
# The stage itself is the function zsc_standing_stage in
# scripts/pre_build_verification.sh; its degraded/ok/mktemp-failure branches are
# unit-tested here by extracting that function and running it against a stub
# audit script -- never by running the full sweep.
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

# ---- Unit level: the stage function's branches, against a stub audit ----
unit_dir="$(mktemp -d)"
out_file="$(mktemp)"
trap 'rm -rf "$unit_dir" "$out_file"' EXIT
stage_src="$(sed -n '/^zsc_standing_stage() {/,/^}/p' scripts/pre_build_verification.sh)"
has_stage_fn() { [[ -n "$stage_src" ]]; }
check "unit: pre_build defines the zsc_standing_stage function" has_stage_fn

# run_stage <stub-body> -> prints "PASS_COUNT=<n>" after the stage output.
# Runs in a child bash with set -euo pipefail, exactly like the sweep.
run_stage() {
    local stub_body="$1" extra="${2:-}"
    mkdir -p "$unit_dir/proj/scripts"
    printf '#!/usr/bin/env bash\n%s\n' "$stub_body" > "$unit_dir/proj/scripts/zero_shortcomings_audit.sh"
    bash -c '
        set -euo pipefail
        PASS_COUNT=0
        pass() { PASS_COUNT=$((PASS_COUNT + 1)); echo "  PASS [$PASS_COUNT]: $1"; }
        fail() { echo "  FAIL [x]: $1"; exit 99; }
        PROJECT_ROOT="$1"; CONST_GATE_TIMEOUT=30
        eval "$2"
        eval "$3"
        zsc_standing_stage
        echo "PASS_COUNT=$PASS_COUNT"
    ' _ "$unit_dir/proj" "$stage_src" "$extra" 2>&1
}

if has_stage_fn; then
    ok_out="$(run_stage 'echo "[INFO] standing-check: r mode=standing-check status=ok {\"backlog_open\":1}"')" || true
    printf '    ok branch: %s\n' "$(tr '\n' ' ' <<<"$ok_out")"
    ok_counts() { grep -qx 'PASS_COUNT=1' <<<"$ok_out"; }
    check "unit: an ok standing-check increments PASS_COUNT (control)" ok_counts

    deg_out="$(run_stage 'echo "[INFO] standing-check: r mode=standing-check status=degraded reason=db_missing failed=backlog {}"')" || true
    printf '    degraded branch: %s\n' "$(tr '\n' ' ' <<<"$deg_out")"
    deg_no_pass() { grep -qx 'PASS_COUNT=0' <<<"$deg_out"; }
    check "unit: a degraded standing-check (exit 0) does NOT increment PASS_COUNT" deg_no_pass
    deg_warn() { grep -q 'WARN: CM-ZERO-SHORTCOMINGS-STANDING: .*degraded' <<<"$deg_out"; }
    check "unit: a degraded standing-check prints an explicit WARN line" deg_warn
    deg_no_fail() { ! grep -q 'FAIL \[' <<<"$deg_out"; }
    check "unit: a degraded standing-check never calls fail()" deg_no_fail

    nz_out="$(run_stage 'echo boom; exit 7')" || true
    nz_ok() { grep -qx 'PASS_COUNT=0' <<<"$nz_out" && grep -q 'WARN: CM-ZERO-SHORTCOMINGS-STANDING: .*exit 7' <<<"$nz_out"; }
    check "unit: a non-zero audit exit WARNs, is not counted, and does not abort" nz_ok

    mk_out="$(run_stage 'echo "status=ok"' 'mktemp() { return 1; }')" || true
    printf '    mktemp-failure branch: %s\n' "$(tr '\n' ' ' <<<"$mk_out")"
    mk_ok() { grep -qx 'PASS_COUNT=0' <<<"$mk_out" && grep -q 'WARN: CM-ZERO-SHORTCOMINGS-STANDING: .*temp' <<<"$mk_out"; }
    check "unit: a mktemp failure WARNs and does not abort the sweep under set -e" mk_ok
fi

# The exit-status predicate below must itself be able to fail (§11.4.273
# control needle): feed it synthetic inputs where the answer is known.
other_fail_in() { grep -aE 'FAIL \[[0-9]+\]:' "$1" | grep -qv 'CM-ZERO-SHORTCOMINGS'; }
exit_matches_in() { # file rc
    if other_fail_in "$1"; then [[ "$2" -eq 1 ]]; else [[ "$2" -eq 0 ]]; fi
}
printf '  FAIL [3]: CM-SOME-OTHER-GATE: broken\n' > "$unit_dir/syn_fail"
printf '  PASS [3]: CM-SOME-OTHER-GATE: fine\n' > "$unit_dir/syn_ok"
predicate_can_fail() {
    ! exit_matches_in "$unit_dir/syn_fail" 0 && ! exit_matches_in "$unit_dir/syn_ok" 1 \
        && exit_matches_in "$unit_dir/syn_fail" 1 && exit_matches_in "$unit_dir/syn_ok" 0
}
check "unit: the exit-status predicate rejects a wrong rc in both directions" predicate_can_fail

if [[ "${ZSC_UNIT_ONLY:-0}" == "1" ]]; then
    printf 'test_check_cm_zero_shortcomings_standing: %d passed, %d failed (unit only; sweep checks not run)\n' "$pass" "$fail"
    [[ "$fail" -eq 0 ]]
    exit $?
fi

# ---- Sweep level: consumes a captured sweep output (or runs the sweep) ----
rc=0
if [[ -n "${ZSC_SWEEP_OUT:-}" ]]; then
    if [[ ! -f "${ZSC_SWEEP_OUT}" || -z "${ZSC_SWEEP_RC:-}" ]]; then
        printf 'ERROR: ZSC_SWEEP_OUT needs an existing file AND ZSC_SWEEP_RC=<exit status>\n' >&2
        exit 2
    fi
    cp "$ZSC_SWEEP_OUT" "$out_file"; rc="${ZSC_SWEEP_RC}"
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
exit_matches_other_stages() { exit_matches_in "$out_file" "$rc"; }
check "sweep exit status is determined by the other stages only" exit_matches_other_stages

printf 'test_check_cm_zero_shortcomings_standing: %d passed, %d failed\n' "$pass" "$fail"
[[ "$fail" -eq 0 ]]
