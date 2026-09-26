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
set +e
bash scripts/zero_shortcomings_audit.sh verify-closure BOB-FIXTURE-NO-TEST-TYPE
rc=$?
set -e
unset AUDIT_QA_ROOT

check "an evidence file with no declared test type is refused (FR-010)" '[[ "$rc" -eq 2 ]]'

printf 'test_zero_shortcomings_audit_test_type_declared: %d passed, %d failed\n' "$pass" "$fail"
[[ "$fail" -eq 0 ]]
