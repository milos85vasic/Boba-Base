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

# --- FR-010 (BOB-248): a closure must declare EVERY test type its command
# mechanically exercises. Decidable only from test-path tokens the project
# itself uses to classify tests (tests/<type>/ and challenges/); anything else
# is reported as an honest limit, never guessed. Temp fixtures only.
T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
fx() { # id test-type command
    mkdir -p "$T/$1"
    printf '**Command:** `%s`\n**Result Summary:** ok\n**Evidence Layer:** runtime\n**Test Type:** %s\n' \
        "$3" "$2" > "$T/$1/closure_evidence_1.md"
}
fx T-UNIT-AS-INTEG 'integration'       ': tests/unit/a.sh; echo ok'
fx T-TWO-DECLARED  'unit, integration'  ': tests/unit/a.sh tests/integration/b.sh; echo ok'
fx T-TWO-ONE-MISS  'unit'               ': tests/unit/a.sh tests/integration/b.sh; echo ok'
fx T-UNDECIDABLE   'unit'               'echo ok'
fx T-LIST-BAD      'unit, banana'       'echo ok'
fx T-CHALLENGE     'challenge'          ': challenges/scripts/x.sh; echo ok'
fx T-NOT-A-TYPE    'unit'               ': tests/unitx/a.sh tests/audit/b.sh; echo ok'
fx T-EMPTY-LIST    ' , '                'echo ok'
vc() { set +e; out="$(AUDIT_QA_ROOT="$T" AUDIT_VERIFY_LOCK_FILE="$T/lock" bash scripts/zero_shortcomings_audit.sh verify-closure "$1" 2>&1)"; rc=$?; set -e; }

vc T-UNIT-AS-INTEG
check "FR-010: a command running tests/unit/ but declaring only integration is refused (exit 2)" '[[ "$rc" -eq 2 ]]'
check "FR-010: the refusal names the undeclared type" 'grep -q "exercises undeclared test type(s): unit" <<<"$out"'
vc T-TWO-DECLARED
check "FR-010: a command exercising two types that declares both is accepted (exit 0)" '[[ "$rc" -eq 0 ]]'
vc T-TWO-ONE-MISS
check "FR-010: declaring only one of two exercised types is refused, naming the other" \
    '[[ "$rc" -eq 2 ]] && grep -q "undeclared test type(s): integration" <<<"$out"'
vc T-UNDECIDABLE
check "FR-010 honest limit: an undecidable command is accepted as declared (exit 0)" '[[ "$rc" -eq 0 ]]'
check "FR-010 honest limit: it SAYS coverage is not mechanically decidable" 'grep -q "not mechanically decidable" <<<"$out"'
vc T-LIST-BAD
check "FR-010: one invalid member in a declared list is refused (exit 2) and named" \
    '[[ "$rc" -eq 2 ]] && grep -q "banana" <<<"$out"'
vc T-CHALLENGE
check "FR-010: a challenges/ path is decided as challenge and accepted when declared" \
    '[[ "$rc" -eq 0 ]] && ! grep -q "not mechanically decidable" <<<"$out"'
vc T-NOT-A-TYPE
check "FR-010 control: tests/unitx/ and tests/audit/ are not mistaken for a type (undecidable, exit 0)" \
    '[[ "$rc" -eq 0 ]] && grep -q "not mechanically decidable" <<<"$out"'
vc T-EMPTY-LIST
check "FR-010: a declared list with no members is refused (exit 2)" '[[ "$rc" -eq 2 ]]'

printf 'test_zero_shortcomings_audit_test_type_declared: %d passed, %d failed\n' "$pass" "$fail"
[[ "$fail" -eq 0 ]]
