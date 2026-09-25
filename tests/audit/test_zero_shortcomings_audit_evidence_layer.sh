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
bash scripts/zero_shortcomings_audit.sh verify-closure BOB-FIXTURE-LAYER-OK
ok_rc=$?
bash scripts/zero_shortcomings_audit.sh verify-closure BOB-FIXTURE-LAYER-TOOWEAK
weak_rc=$?
set -e
unset AUDIT_QA_ROOT

check "runtime-layer evidence for a runtime-required item passes" '[[ "$ok_rc" -eq 0 ]]'
check "source-layer evidence is refused with a distinct exit code, not a plain mismatch" \
    '[[ "$weak_rc" -eq 2 ]]'

printf 'test_zero_shortcomings_audit_evidence_layer: %d passed, %d failed\n' "$pass" "$fail"
[[ "$fail" -eq 0 ]]
