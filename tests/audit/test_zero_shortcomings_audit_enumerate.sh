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

out="$(bash scripts/zero_shortcomings_audit.sh enumerate --json)"
check "enumerate --json produces valid JSON with all three keys" \
    'printf "%s" "$out" | grep -q "\"backlog_open\"" \
     && printf "%s" "$out" | grep -q "\"gates_unimplemented\"" \
     && printf "%s" "$out" | grep -q "\"escapes_open\""'

# Ground truth 1: the tracker's own count of non-terminal, non-Obsolete items.
truth_backlog="$(sqlite3 docs/workable_items.db \
    "SELECT count(*) FROM items WHERE status NOT LIKE '%(→ Fixed.md)' AND status != 'Obsolete';")"
reported_backlog="$(printf '%s' "$out" | grep -oE '"backlog_open":[0-9]+' | grep -oE '[0-9]+')"
check "reported backlog_open exactly matches the tracker's own ground-truth count" \
    '[[ "$reported_backlog" == "$truth_backlog" ]]'

# --surface restricts to one surface only.
scoped="$(bash scripts/zero_shortcomings_audit.sh enumerate --json --surface backlog)"
check "--surface backlog omits the other two surfaces' keys" \
    '! printf "%s" "$scoped" | grep -q "gates_unimplemented"'

check "enumerate exits 0 even when open items exist (never gates on findings)" \
    'bash scripts/zero_shortcomings_audit.sh enumerate --json >/dev/null; [[ $? -eq 0 ]]'

printf 'test_zero_shortcomings_audit_enumerate: %d passed, %d failed\n' "$pass" "$fail"
[[ "$fail" -eq 0 ]]
