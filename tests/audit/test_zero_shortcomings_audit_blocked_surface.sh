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

out="$(bash scripts/zero_shortcomings_audit.sh enumerate --surface blocked)"
check "enumerate --surface blocked names at least one real unblock condition, not a bare count" \
    'printf "%s" "$out" | grep -qiE "unblock|condition"'
check "enumerate --surface blocked never prints a bare number with nothing else (SC-006)" \
    '! printf "%s" "$out" | grep -qE "^[0-9]+$"'

printf 'test_zero_shortcomings_audit_blocked_surface: %d passed, %d failed\n' "$pass" "$fail"
[[ "$fail" -eq 0 ]]
