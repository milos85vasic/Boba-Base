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

# Re-source guard (review finding, Task 1+2 combined review 2026-09-25):
# multiple sibling scripts/lib/*.sh files may each independently source this
# shared dependency; without a guard, a second `source` in the same shell
# aborts the WHOLE process with a "readonly variable" error, regardless of
# set -e. Run the double-source attempt in a child shell so a pre-fix crash
# here is captured as a check result, not an abort of this test script.
if double_source_result="$(bash -c 'set -euo pipefail; cd "'"$(pwd)"'"; source scripts/lib/audit_execution_policy.sh; source scripts/lib/audit_execution_policy.sh; echo OK' 2>&1)"; then
    double_source_exit=0
else
    double_source_exit=$?
fi
check "sourcing the file twice in one shell does not abort (re-source guard)" \
    '[[ "$double_source_exit" -eq 0 ]] && [[ "$double_source_result" == "OK" ]]'

printf 'test_audit_execution_policy: %d passed, %d failed\n' "$pass" "$fail"
[[ "$fail" -eq 0 ]]
