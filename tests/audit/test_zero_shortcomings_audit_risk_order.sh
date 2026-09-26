#!/usr/bin/env bash
# FR-012 risk-ordered backlog listing, tested against a HAND-BUILT DB and a
# HAND-WRITTEN expected order (never a copy of the implementation's SQL).
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

# Same items/item_history schema as the real tracker DB.
{
    sqlite3 docs/workable_items.db ".schema items" ".schema item_history"
} | sqlite3 "$db"

add_item() { # id status last_modified
    sqlite3 "$db" "INSERT INTO items (atm_id,type,status,title,description,last_modified)
        VALUES ('$1','Bug','$2','t','d','$3');"
}
add_reopen() { # id
    sqlite3 "$db" "INSERT INTO item_history (atm_id,event_type,on_date) VALUES ('$1','Reopened','2026-01-01');"
}

# Open items. OLD2 is the OLDEST but has 2 reopens: must rank first.
add_item T-OLD2  'Queued'      '2026-01-01 00:00:00'
add_reopen T-OLD2; add_reopen T-OLD2
# Tie on reopens (1 each): newer last_modified first.
add_item T-TIE1  'In progress' '2026-03-01 00:00:00'; add_reopen T-TIE1
add_item T-TIE2  'Queued'      '2026-05-01 00:00:00'; add_reopen T-TIE2
# Zero reopens, NEWEST: ranks after every reopened item.
add_item T-NEW0  'Queued'      '2026-09-01 00:00:00'
# Two with zero reopens and identical last_modified: atm_id ascending.
add_item T-EQB   'Queued'      '2026-06-01 00:00:00'
add_item T-EQA   'Queued'      '2026-06-01 00:00:00'
# Closed/obsolete items with many reopens must be excluded.
add_item T-CLOSED 'Fixed (→ Fixed.md)' '2026-09-02 00:00:00'; add_reopen T-CLOSED; add_reopen T-CLOSED; add_reopen T-CLOSED
add_item T-OBS   'Obsolete'    '2026-09-03 00:00:00'; add_reopen T-OBS

export WORKABLE_ITEMS_DB_OVERRIDE="$db"
expected="T-OLD2 T-TIE2 T-TIE1 T-NEW0 T-EQA T-EQB"   # hand-written ground truth

out="$(bash scripts/zero_shortcomings_audit.sh enumerate --surface backlog --sort-by-risk)"
got="$(printf '%s\n' "$out" | tr '\n' ' ' | sed 's/ $//')"
printf '  got: %s\n' "$got"

check "order is reopens DESC, then last_modified DESC, then atm_id (hand-written expected)" \
    '[[ "$got" == "$expected" ]]'
check "an older item with 2 reopens outranks a newer item with 0 (not a last_modified-only sort)" \
    '[[ "$(printf "%s\n" "$out" | head -1)" == "T-OLD2" ]]'
check "closed and obsolete items are excluded even with reopens" \
    '! grep -q "T-CLOSED\|T-OBS" <<<"$out"'

set +e
gerr="$(bash scripts/zero_shortcomings_audit.sh enumerate --surface gates --sort-by-risk 2>&1 >/dev/null)"; grc=$?
aerr="$(bash scripts/zero_shortcomings_audit.sh enumerate --sort-by-risk 2>&1 >/dev/null)"; arc=$?
set -e
check "--sort-by-risk with --surface gates exits non-zero with an error naming the option" \
    '[[ "$grc" -ne 0 ]] && grep -q -- "--sort-by-risk" <<<"$gerr"'
check "--sort-by-risk with the default (all) surface also exits non-zero" '[[ "$arc" -ne 0 ]]'

json="$(bash scripts/zero_shortcomings_audit.sh enumerate --surface backlog --sort-by-risk --json)"
check "--json on backlog emits a JSON array in the same risk order" \
    '[[ "$json" == "[\"T-OLD2\",\"T-TIE2\",\"T-TIE1\",\"T-NEW0\",\"T-EQA\",\"T-EQB\"]" ]]'

unset WORKABLE_ITEMS_DB_OVERRIDE
printf 'test_zero_shortcomings_audit_risk_order: %d passed, %d failed\n' "$pass" "$fail"
[[ "$fail" -eq 0 ]]
