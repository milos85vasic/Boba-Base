#!/usr/bin/env bash
# m2: an option that needs a value, given without one, prints a clear usage
# error and exits 4 (never a bash "unbound variable" abort).
# m3: verify-closure rejects an item id that is not ^[A-Za-z0-9._-]+$ or that
# contains `..` BEFORE the id is used in any path.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."

pass=0
fail=0
check() {
    local desc="$1" cond="$2"
    if eval "$cond"; then
        printf '  PASS: %s\n' "$desc"; pass=$((pass + 1))
    else
        printf '  FAIL: %s\n' "$desc"; fail=$((fail + 1))
    fi
}
run() { # args... -> sets rc, out
    rc=0
    out="$(AUDIT_QA_ROOT=tests/audit/fixtures/docs_qa_fixture bash scripts/zero_shortcomings_audit.sh "$@" 2>&1)" || rc=$?
}

run enumerate --surface
check "m2 enumerate --surface with no value exits 4 (usage refusal)" '[[ "$rc" -eq 4 ]]'
check "m2 enumerate --surface with no value names the missing value" 'printf "%s" "$out" | grep -q -- "--surface requires a value"'
check "m2 enumerate --surface with no value is not an unbound-variable abort" '! printf "%s" "$out" | grep -q "unbound variable"'

run verify-closure BOB-FIXTURE-MATCH --require-layer
check "m2 verify-closure --require-layer with no value exits 4 (usage refusal)" '[[ "$rc" -eq 4 ]]'
check "m2 verify-closure --require-layer with no value names the missing value" 'printf "%s" "$out" | grep -q -- "--require-layer requires a value"'
check "m2 --require-layer with no value is not an unbound-variable abort" '! printf "%s" "$out" | grep -q "unbound variable"'

for bad in '../BOB-FIXTURE-MATCH' 'BOB/FIXTURE' '..' 'BOB..X' 'BOB FIXTURE' 'BOB;rm' '-rf'; do
    run verify-closure "$bad"
    check "m3 item id '$bad' is rejected with exit 4 (usage refusal)" '[[ "$rc" -eq 4 ]]'
    check "m3 item id '$bad' is rejected by name" 'printf "%s" "$out" | grep -q "invalid item id"'
done
run verify-closure BOB-FIXTURE-MATCH
check "m3 a valid item id is still accepted (the guard is not over-broad)" '[[ "$rc" -eq 0 ]]'
run verify-closure BOB-FIXTURE-MATCH --require-layer banana
check "an unrecognized --require-layer value is rejected (exit 4)" '[[ "$rc" -eq 4 ]] && printf "%s" "$out" | grep -q "require-layer"'

printf 'test_zero_shortcomings_audit_cli_validation: %d passed, %d failed\n' "$pass" "$fail"
[[ "$fail" -eq 0 ]]
