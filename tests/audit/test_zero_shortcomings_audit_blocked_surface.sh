#!/usr/bin/env bash
# FR-007 / SC-006: `enumerate --surface blocked` must name each Operator-blocked
# item's specific unblock condition, and must SURFACE (never silently drop) an
# Operator-blocked item that has no details row or a blank condition.
# Tested against a HAND-BUILT temp DB with a HAND-WRITTEN expected output, so a
# header line alone can never satisfy it (the previous grep for
# "unblock|condition" matched the "(id|unblock_condition)" header and passed
# with zero data rows).
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

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
db="$tmp/w.db"
{
    sqlite3 docs/workable_items.db ".schema items" ".schema operator_block_details"
} | sqlite3 "$db"

add_item() { # id status
    sqlite3 "$db" "INSERT INTO items (atm_id,type,status,title,description)
        VALUES ('$1','Bug','$2','t','d');"
}
add_block() { # id condition
    sqlite3 "$db" "INSERT INTO operator_block_details (atm_id,what,why_exhausted_alternatives,unblock_condition)
        VALUES ('$1','w','y','$2');"
}

add_item T-VALID   'Operator-blocked'; add_block T-VALID 'Operator supplies the fixture cookie'
add_item T-NODETAIL 'Operator-blocked'                      # no details row at all
add_item T-BLANK   'Operator-blocked'; add_block T-BLANK '   '  # whitespace-only condition
add_item T-NOTBLOCKED 'Queued'; add_block T-NOTBLOCKED 'irrelevant, not blocked'

set +e
out="$(WORKABLE_ITEMS_DB_OVERRIDE="$db" bash scripts/zero_shortcomings_audit.sh enumerate --surface blocked 2>"$tmp/err")"
rc=$?
set -e
# Data lines only: drop the colored [INFO] header line.
data="$(printf '%s\n' "$out" | grep -v '\[INFO\]' || true)"
expected="T-BLANK|MISSING-UNBLOCK-CONDITION
T-NODETAIL|MISSING-UNBLOCK-CONDITION
T-VALID|Operator supplies the fixture cookie"   # hand-written ground truth
printf '  got:\n%s\n' "$data"

check "blocked surface output is exactly the hand-written expected rows" \
    '[[ "$data" == "$expected" ]]'
check "an Operator-blocked item with NO details row is surfaced, not dropped" \
    'printf "%s\n" "$data" | grep -qx "T-NODETAIL|MISSING-UNBLOCK-CONDITION"'
check "a blank unblock condition is surfaced as a defect, not accepted" \
    'printf "%s\n" "$data" | grep -qx "T-BLANK|MISSING-UNBLOCK-CONDITION"'
check "a non-blocked item never appears" \
    '! printf "%s\n" "$data" | grep -q "T-NOTBLOCKED"'
check "enumerate still exits 0 (findings are reported, not gated)" '[[ "$rc" -eq 0 ]]'
check "the defect count is announced on stderr" \
    'grep -q "2 Operator-blocked item(s) lack an unblock condition" "$tmp/err"'
check "enumerate --surface blocked never prints a bare number with nothing else (SC-006)" \
    '! printf "%s" "$data" | grep -qE "^[0-9]+$"'

# m1: a missing DB must fail loud and must NOT be created by sqlite3.
missing="$tmp/does-not-exist.db"
for surf in blocked backlog; do
    set +e
    WORKABLE_ITEMS_DB_OVERRIDE="$missing" bash scripts/zero_shortcomings_audit.sh enumerate --surface "$surf" >"$tmp/m1.out" 2>&1
    m1rc=$?
    set -e
    check "m1: --surface $surf against a missing DB exits non-zero" '[[ "$m1rc" -ne 0 ]]'
    check "m1: --surface $surf against a missing DB does NOT create the DB file" '[[ ! -e "$missing" ]]'
    check "m1: --surface $surf names the missing DB in its error" 'grep -q "does-not-exist.db" "$tmp/m1.out"'
done

printf 'test_zero_shortcomings_audit_blocked_surface: %d passed, %d failed\n' "$pass" "$fail"
[[ "$fail" -eq 0 ]]
