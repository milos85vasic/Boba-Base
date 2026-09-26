#!/usr/bin/env bash
# SC-005 / FR-009: the standing check must RE-VERIFY closed items, not only
# count open ones. A deliberately reintroduced, previously fixed defect must be
# flagged by one normal standing-check run, without anyone re-triggering it.
#
# Every fixture is a mktemp temp DB (WORKABLE_ITEMS_DB_OVERRIDE) and a temp
# evidence tree (AUDIT_QA_ROOT); the "feature" whose defect is reintroduced is a
# state file the recorded command reads. The corruption-guard case runs a COPY
# of the audit inside a throwaway git repository, never against this project's
# tracked docs/qa.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
repo="$(pwd)"

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

T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
AUDIT="$repo/scripts/zero_shortcomings_audit.sh"
STUB="$T/gate_ok.sh"
printf '#!/usr/bin/env bash\necho "LEDGER: unimplemented=0"\n' > "$STUB"

new_db() { # path
    { sqlite3 "$repo/docs/workable_items.db" ".schema items" ".schema item_history"; } | sqlite3 "$1"
}
add_item() { # db id status last_modified [severity]
    sqlite3 "$1" "INSERT INTO items (atm_id,type,status,severity,title,description,last_modified)
        VALUES ('$2','Bug','$3',$( [[ -n "${5:-}" ]] && printf "'%s'" "$5" || printf NULL ),'t','d','$4');"
}
add_reopen() { # db id
    sqlite3 "$1" "INSERT INTO item_history (atm_id,event_type,on_date) VALUES ('$2','Reopened','2026-01-01');"
}
evidence() { # qa id command summary [test-type]
    mkdir -p "$1/$2"
    {
        printf '# %s\n\n' "$2"
        [[ -n "$3" ]] && printf '**Command:** `%s`\n' "$3"
        printf '**Result Summary:** %s\n**Evidence Layer:** runtime\n**Test Type:** %s\n' "$4" "${5:-unit}"
    } > "$1/$2/closure_evidence_20260926.md"
}

# --- scenario 1: a fixed defect, then the same defect reintroduced ---------
db="$T/w.db"; qa="$T/qa"; state="$T/feature_state"; marker="$T/open_item_ran"
new_db "$db"
printf 'fixed\n' > "$state"
add_item "$db" C-FIXED  'Fixed (→ Fixed.md)'     '2026-02-01 00:00:00' High
add_reopen "$db" C-FIXED; add_reopen "$db" C-FIXED
evidence "$qa" C-FIXED "cat $state" "fixed"
add_item "$db" C-OK     'Completed (→ Fixed.md)' '2026-03-01 00:00:00' Low
evidence "$qa" C-OK "echo ok" "ok"
add_item "$db" C-NOCMD  'Fixed (→ Fixed.md)'     '2026-09-01 00:00:00'
evidence "$qa" C-NOCMD "" "whatever"
add_item "$db" C-NOEVID 'Fixed (→ Fixed.md)'     '2026-09-02 00:00:00'
add_item "$db" C-OBS    'Obsolete'               '2026-09-03 00:00:00'
evidence "$qa" C-OBS "touch $marker.obsolete; echo x" "y"
add_item "$db" O-OPEN   'Queued'                 '2026-09-04 00:00:00'
evidence "$qa" O-OPEN "touch $marker; echo x" "y"

run_sc() { # args... -> rc, out, log
    local d="$T/logs"; rm -rf "$d"
    rc=0
    out="$(WORKABLE_ITEMS_DB_OVERRIDE="$db" GATE_LEDGER_SCRIPT_OVERRIDE="$STUB" \
        AUDIT_QA_ROOT="$qa" AUDIT_STANDING_LOG_DIR="$d" AUDIT_VERIFY_LOCK_FILE="$T/lock" \
        bash "$AUDIT" standing-check "$@" 2>&1)" || rc=$?
    log="$(cat "$d"/*.log 2>/dev/null || true)"
}
db_sum_before="$(sha256sum "$db" | cut -d' ' -f1)"

run_sc --reverify 5
printf '    healthy: %s\n' "$log"
check "healthy: exit 0" '[[ "$rc" -eq 0 ]]'
check "healthy: status=ok (every re-verified closure still reproduces)" 'grep -q "status=ok" <<<"$log"'
check "healthy: exactly the two closed items with a recorded command were re-verified" \
    'grep -q "reverify=checked:2,match:2,mismatch:0" <<<"$log"'
check "healthy: no mismatch named" '! grep -q "reverify_mismatch=" <<<"$log"'

printf 'broken\n' > "$state"          # the previously fixed defect is back
run_sc --reverify 5
printf '    reintroduced: %s\n' "$log"
check "reintroduced defect: still exit 0 (advisory, never blocks)" '[[ "$rc" -eq 0 ]]'
check "reintroduced defect: flagged as a mismatch naming the item" 'grep -q "reverify_mismatch=C-FIXED" <<<"$log"'
check "reintroduced defect: the run is marked status=degraded (never read as a PASS)" \
    'grep -q "status=degraded" <<<"$log" && grep -q "reverify_mismatch" <<<"$log"'
check "control: the still-healthy closed item is NOT flagged" '! grep -q "reverify_mismatch=[^ ]*C-OK" <<<"$log"'
check "WARN printed for the mismatch" 'grep -q "WARN" <<<"$out"'

run_sc
printf '    default run: %s\n' "$log"
check "SC-005: a DEFAULT standing-check (no flag) re-verifies and flags the reintroduced defect" \
    'grep -q "reverify_mismatch=C-FIXED" <<<"$log"'

run_sc --reverify 1
check "risk order: --reverify 1 checks only the most-reopened closed item" \
    'grep -q "reverify=checked:1,match:0,mismatch:1" <<<"$log" && grep -q "reverify_mismatch=C-FIXED" <<<"$log"'

run_sc --reverify 0
check "--reverify 0 disables re-verification and says so" 'grep -q "reverify=off" <<<"$log" && grep -q "status=ok" <<<"$log"'

check "the tracker DB was never mutated (no reopen in standing mode)" \
    '[[ "$(sha256sum "$db" | cut -d" " -f1)" == "$db_sum_before" ]]'
check "open items are never re-run by the standing check" '[[ ! -e "$marker" ]]'
check "obsolete items are never re-run by the standing check" '[[ ! -e "$marker.obsolete" ]]'
check "the credential-free log stays one line per run" '[[ "$(printf "%s\n" "$log" | grep -c .)" -eq 1 ]]'

for bad in "" "x" "-1"; do
    rc=0; WORKABLE_ITEMS_DB_OVERRIDE="$db" GATE_LEDGER_SCRIPT_OVERRIDE="$STUB" AUDIT_STANDING_LOG_DIR="$T/logs" \
        bash "$AUDIT" standing-check --reverify $bad >/dev/null 2>&1 || rc=$?
    check "--reverify '${bad}' is a usage refusal (exit 4)" '[[ "$rc" -eq 4 ]]'
done

# --- scenario 2: bounded runtime (per-item timeout + total budget) ---------
db2="$T/w2.db"; qa2="$T/qa2"
new_db "$db2"
add_item "$db2" S-HANG 'Fixed (→ Fixed.md)' '2026-09-01 00:00:00'
evidence "$qa2" S-HANG "sleep 60; echo late" "late"
add_item "$db2" S-SLOW 'Fixed (→ Fixed.md)' '2026-08-01 00:00:00'
evidence "$qa2" S-SLOW "sleep 3; echo slow" "slow"
add_item "$db2" S-LAST 'Fixed (→ Fixed.md)' '2026-07-01 00:00:00'
evidence "$qa2" S-LAST "echo last" "last"
start=$SECONDS
rc=0; d="$T/logs2"
WORKABLE_ITEMS_DB_OVERRIDE="$db2" GATE_LEDGER_SCRIPT_OVERRIDE="$STUB" AUDIT_QA_ROOT="$qa2" \
    AUDIT_STANDING_LOG_DIR="$d" AUDIT_VERIFY_LOCK_FILE="$T/lock" \
    AUDIT_REVERIFY_ITEM_TIMEOUT=2 AUDIT_REVERIFY_BUDGET=4 \
    bash "$AUDIT" standing-check --reverify 3 >/dev/null 2>&1 || rc=$?
elapsed=$((SECONDS - start)); log2="$(cat "$d"/*.log 2>/dev/null || true)"
printf '    bounded (%ss): %s\n' "$elapsed" "$log2"
check "bounded: exit 0" '[[ "$rc" -eq 0 ]]'
check "bounded: a hanging recorded command is cut off and reported as a timeout, not a match" \
    'grep -q "reverify_timeout=S-HANG" <<<"$log2"'
check "bounded: the total budget stops further items and says which were skipped" \
    'grep -q "reverify_skipped_budget=" <<<"$log2" && grep -q "S-LAST" <<<"$log2"'
check "bounded: the whole run stayed well under the pre-build stage timeout (${elapsed}s < 30s)" '[[ "$elapsed" -lt 30 ]]'
check "bounded: an inconclusive run is status=degraded, never ok" 'grep -q "status=degraded" <<<"$log2"'

# --- scenario 3: the corruption guard still protects other evidence --------
sb="$T/sandbox"
mkdir -p "$sb/scripts/lib" "$sb/docs/qa/BOB-OTHER" "$sb/docs/qa/C-CORRUPT"
cp "$AUDIT" "$sb/scripts/"
cp "$repo"/scripts/lib/audit_*.sh "$sb/scripts/lib/"
evidence "$sb/docs/qa" C-CORRUPT "echo corrupt > docs/qa/BOB-OTHER/closure_evidence_1.md; echo same" "same"
(
    cd "$sb"
    git init -q .
    git config user.email t@t.invalid; git config user.name t
    echo "other original" > docs/qa/BOB-OTHER/closure_evidence_1.md
    git add -A && git commit -q -m seed
)
db3="$T/w3.db"; new_db "$db3"
add_item "$db3" C-CORRUPT 'Fixed (→ Fixed.md)' '2026-09-01 00:00:00'
rc=0; d="$T/logs3"
(cd "$sb" && WORKABLE_ITEMS_DB_OVERRIDE="$db3" GATE_LEDGER_SCRIPT_OVERRIDE="$STUB" \
    AUDIT_STANDING_LOG_DIR="$d" AUDIT_VERIFY_LOCK_FILE="$T/lock" \
    bash scripts/zero_shortcomings_audit.sh standing-check --reverify 1 >/dev/null 2>&1) || rc=$?
check "corruption guard: the other item's tracked evidence was restored" \
    '[[ "$(cat "$sb/docs/qa/BOB-OTHER/closure_evidence_1.md")" == "other original" ]]'
check "corruption guard: the incident is logged beside the standing log, not in the sandbox docs/qa" \
    'grep -rq "docs/qa/BOB-OTHER/closure_evidence_1.md" "$d" && [[ ! -d "$sb/docs/qa/zero_shortcomings_audit" ]]'
check "this test left the real repo's docs/qa untouched" '[[ -z "$(git -C "$repo" status --porcelain -- docs/qa)" ]]'

printf 'test_zero_shortcomings_audit_standing_reverify: %d passed, %d failed\n' "$pass" "$fail"
[[ "$fail" -eq 0 ]]
