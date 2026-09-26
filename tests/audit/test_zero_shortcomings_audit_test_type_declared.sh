#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."

pass=0
fail=0

check() {
    local desc="$1" cond="$2"
    if eval "$cond"; then
        printf '  PASS: %s\n' "$desc"
        pass=$((pass + 1))
    else
        printf '  FAIL: %s\n' "$desc"
        fail=$((fail + 1))
    fi
}

export AUDIT_QA_ROOT="tests/audit/fixtures/docs_qa_fixture"

# run_case <item> : sets rc and out (stdout+stderr) without tripping set -e.
run_case() {
    set +e
    out="$(bash scripts/zero_shortcomings_audit.sh verify-closure "$1" 2>&1)"
    rc=$?
    set -e
}

run_case BOB-FIXTURE-NO-TEST-TYPE
check "an evidence file with no declared test type is refused (FR-010)" '[[ "$rc" -eq 2 ]]'
check "the refusal message names the missing Test Type field" 'grep -q "declares no \*\*Test Type:\*\*" <<<"$out"'

run_case BOB-FIXTURE-MATCH
check "positive control: a fixture with a valid Test Type is not refused (rc 0)" '[[ "$rc" -eq 0 ]]'
check "positive control: its output carries no Test Type complaint" '! grep -qi "test type" <<<"$out"'

run_case BOB-FIXTURE-CASE-TEST-TYPE
check "a valid Test Type is accepted trimmed and case-insensitively ('  E2E  ')" '[[ "$rc" -eq 0 ]]'

run_case BOB-FIXTURE-BAD-TEST-TYPE
check "an unknown Test Type ('banana') is refused with exit 2" '[[ "$rc" -eq 2 ]]'
check "the refusal names the offending value and the allowed set" \
    'grep -q "banana" <<<"$out" && grep -q "unit|integration|e2e|security|stress|chaos|scaling|ui|challenge" <<<"$out"'

run_case BOB-FIXTURE-BLANK-TEST-TYPE
check "a whitespace-only Test Type is refused with exit 2" '[[ "$rc" -eq 2 ]]'
check "the whitespace-only refusal names the allowed set" \
    'grep -q "unit|integration|e2e|security|stress|chaos|scaling|ui|challenge" <<<"$out"'

unset AUDIT_QA_ROOT
printf 'test_zero_shortcomings_audit_test_type_declared: %d passed, %d failed\n' "$pass" "$fail"
[[ "$fail" -eq 0 ]]
