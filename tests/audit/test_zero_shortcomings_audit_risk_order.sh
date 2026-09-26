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

# NOTE: docs/workable_items.db has no reopens_count column on items (measured
# 2026-09-26); the count is derived from item_history 'Reopened' events, the
# tracker's own source of truth for reopens (Constitution 11.4.55).
out="$(bash scripts/zero_shortcomings_audit.sh enumerate --surface backlog --sort-by-risk || true)"
truth_top="$(sqlite3 docs/workable_items.db \
    "SELECT i.atm_id FROM items i WHERE i.status NOT LIKE '%(→ Fixed.md)' AND i.status != 'Obsolete'
     ORDER BY (SELECT count(*) FROM item_history h WHERE h.atm_id=i.atm_id AND h.event_type='Reopened') DESC,
              i.last_modified DESC, i.atm_id LIMIT 1;")"
reported_top="$(printf '%s\n' "$out" | head -1)"
n_out="$(printf '%s\n' "$out" | grep -c . || true)"
n_truth="$(sqlite3 docs/workable_items.db \
    "SELECT count(*) FROM items WHERE status NOT LIKE '%(→ Fixed.md)' AND status != 'Obsolete';")"

check "the first-listed item under --sort-by-risk matches the tracker's own highest-risk item" \
    '[[ -n "$truth_top" && "$reported_top" == "$truth_top" ]]'
check "every open backlog item is listed exactly once" '[[ "$n_out" -eq "$n_truth" ]]'
plain="$(bash scripts/zero_shortcomings_audit.sh enumerate --surface gates --sort-by-risk 2>&1 || true)"
check "--sort-by-risk leaves non-backlog surfaces unchanged (no id list)" \
    '! printf "%s" "$plain" | grep -q "^BOB-\|^ATM-"'

printf 'test_zero_shortcomings_audit_risk_order: %d passed, %d failed\n' "$pass" "$fail"
[[ "$fail" -eq 0 ]]
