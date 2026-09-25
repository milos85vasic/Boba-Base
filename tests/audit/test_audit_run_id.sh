#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
source scripts/lib/audit_run_id.sh

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

id1="$(audit_run_id)"
check "run id matches YYYYMMDDTHHMMSSZ-pid<N> shape" \
    '[[ "$id1" =~ ^[0-9]{8}T[0-9]{6}Z-pid[0-9]+$ ]]'

id2="$(audit_run_id)"
check "the embedded pid is this shell's own PID" \
    '[[ "$id1" == *"-pid$$" ]] && [[ "$id2" == *"-pid$$" ]]'

printf 'test_audit_run_id: %d passed, %d failed\n' "$pass" "$fail"
[[ "$fail" -eq 0 ]]
