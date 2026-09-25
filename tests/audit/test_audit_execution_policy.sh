#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
source scripts/lib/audit_execution_policy.sh

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

check "AUDIT_MAX_PARALLEL_ITEMS is 3 per data-model.md" \
    '[[ "$AUDIT_MAX_PARALLEL_ITEMS" == "3" ]]'
check "AUDIT_NICE_LEVEL is 19 per Principle XIII" \
    '[[ "$AUDIT_NICE_LEVEL" == "19" ]]'
check "AUDIT_IONICE_CLASS is 3 (idle) per Principle XIII" \
    '[[ "$AUDIT_IONICE_CLASS" == "3" ]]'
check "AUDIT_RESOURCE_CEILING_PCT is 40 per Principle XIII" \
    '[[ "$AUDIT_RESOURCE_CEILING_PCT" == "40" ]]'

out="$(audit_dispatch_bounded echo hello)"
check "audit_dispatch_bounded runs the wrapped command" '[[ "$out" == "hello" ]]'

printf 'test_audit_execution_policy: %d passed, %d failed\n' "$pass" "$fail"
[[ "$fail" -eq 0 ]]
