#!/usr/bin/env bash
# FR-013: `verify-closure --reopen-on-mismatch` reopens EXACTLY the mismatched
# item in the tracker, and a reopen that fails is REPORTED (distinct exit 3 +
# explicit error), never swallowed. Runs only against a TEMP COPY of the
# tracker DB (WORKABLE_ITEMS_DB_OVERRIDE); the real DB's bytes are asserted
# unchanged.
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

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
real_sum_before="$(sha256sum docs/workable_items.db | cut -d' ' -f1)"
db="$tmp/w.db"
cp docs/workable_items.db "$db"

target="$(sqlite3 "$db" "SELECT atm_id FROM items WHERE status LIKE '%(→ Fixed.md)' ORDER BY atm_id LIMIT 1;")"
check "precondition: the temp DB holds a closed item to reopen" '[[ -n "$target" ]]'
reopened_before="$(sqlite3 "$db" "SELECT count(*) FROM item_history WHERE event_type='Reopened';")"
status_snapshot_before="$(sqlite3 "$db" "SELECT atm_id||'|'||status FROM items WHERE atm_id != '$target' ORDER BY atm_id;" | sha256sum)"

qa="$tmp/qa"
mk_evidence() { # id
    mkdir -p "$qa/$1"
    cat > "$qa/$1/closure_evidence_1.md" <<MD
**Command:** \`echo '2 passed, 0 failed'\`
**Result Summary:** 9 passed, 0 failed
**Evidence Layer:** runtime
**Test Type:** unit
MD
}
mk_evidence "$target"

rc=0
out="$(AUDIT_QA_ROOT="$qa" WORKABLE_ITEMS_DB_OVERRIDE="$db" bash scripts/zero_shortcomings_audit.sh verify-closure "$target" --reopen-on-mismatch 2>&1)" || rc=$?
printf '    reopen output: %s\n' "$(printf '%s' "$out" | tr '\n' ' ')"
check "a mismatch with --reopen-on-mismatch exits 1 (mismatch found, reopen succeeded)" '[[ "$rc" -eq 1 ]]'
check "the mismatched item is now Reopened in the temp DB" \
    '[[ "$(sqlite3 "$db" "SELECT status FROM items WHERE atm_id='"'"'$target'"'"' LIMIT 1;")" == "Reopened" ]]'
check "exactly ONE new Reopened history event was written" \
    '[[ "$(sqlite3 "$db" "SELECT count(*) FROM item_history WHERE event_type='"'"'Reopened'"'"';")" -eq $((reopened_before + 1)) ]]'
check "no OTHER item's status changed" \
    '[[ "$(sqlite3 "$db" "SELECT atm_id||'"'"'|'"'"'||status FROM items WHERE atm_id != '"'"'$target'"'"' ORDER BY atm_id;" | sha256sum)" == "$status_snapshot_before" ]]'

# A reopen that FAILS (the item is not in the tracker) must be reported.
ghost="BOB-GHOST-NOT-IN-DB"
mk_evidence "$ghost"
rc2=0
out2="$(AUDIT_QA_ROOT="$qa" WORKABLE_ITEMS_DB_OVERRIDE="$db" bash scripts/zero_shortcomings_audit.sh verify-closure "$ghost" --reopen-on-mismatch 2>&1)" || rc2=$?
printf '    failing-reopen output: %s\n' "$(printf '%s' "$out2" | tr '\n' ' ')"
check "a FAILED reopen exits 3 (distinct from a plain mismatch), not swallowed" '[[ "$rc2" -eq 3 ]]'
check "a FAILED reopen prints an explicit error naming the item" \
    'printf "%s" "$out2" | grep -q "reopen FAILED for $ghost"'

# Without the flag, a mismatch never touches the tracker.
mk_evidence "$target"
before_noflag="$(sqlite3 "$db" "SELECT count(*) FROM item_history;")"
AUDIT_QA_ROOT="$qa" WORKABLE_ITEMS_DB_OVERRIDE="$db" bash scripts/zero_shortcomings_audit.sh verify-closure "$target" >/dev/null 2>&1 || true
check "without --reopen-on-mismatch the tracker is untouched" \
    '[[ "$(sqlite3 "$db" "SELECT count(*) FROM item_history;")" -eq "$before_noflag" ]]'

check "the REAL tracker DB is byte-identical after the test" \
    '[[ "$(sha256sum docs/workable_items.db | cut -d" " -f1)" == "$real_sum_before" ]]'

printf 'test_zero_shortcomings_audit_reopen_on_mismatch: %d passed, %d failed\n' "$pass" "$fail"
[[ "$fail" -eq 0 ]]
