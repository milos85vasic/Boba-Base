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
bash scripts/zero_shortcomings_audit.sh verify-closure BOB-FIXTURE-MATCH
match_rc=$?
set -e
check "a genuinely matching closure exits 0" '[[ "$match_rc" -eq 0 ]]'

set +e
bash scripts/zero_shortcomings_audit.sh verify-closure BOB-FIXTURE-MISMATCH
mismatch_rc=$?
set -e
check "a mismatched closure exits 1 (Review Focus item 3: semantic mismatch is real)" \
    '[[ "$mismatch_rc" -eq 1 ]]'

set +e
bash scripts/zero_shortcomings_audit.sh verify-closure BOB-FIXTURE-NONEXISTENT
missing_rc=$?
set -e
check "an item with no recorded evidence exits 2 (itself a finding)" \
    '[[ "$missing_rc" -eq 2 ]]'

# Regression test for the third, latent set -e/pipefail instance the Task 5
# implementer flagged (§11.4.201(12)): an evidence file with no **Command:**
# field must fail LOUD with the documented exit-2 contract, never a bare,
# unexplained exit 1 from set -e aborting before the -z check runs.
set +e
no_command_out="$(bash scripts/zero_shortcomings_audit.sh verify-closure BOB-FIXTURE-NO-COMMAND 2>&1)"
no_command_rc=$?
set -e
check "a closure with no **Command:** field exits 2 with a named reason, not a bare exit 1" \
    '[[ "$no_command_rc" -eq 2 ]] && printf "%s" "$no_command_out" | grep -qi "no \*\*Command:\*\* field"'

unset AUDIT_QA_ROOT
printf 'test_zero_shortcomings_audit_verify_closure: %d passed, %d failed\n' "$pass" "$fail"
[[ "$fail" -eq 0 ]]
