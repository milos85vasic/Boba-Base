#!/usr/bin/env bash
# Standing-check tests: healthy line, degraded markers (gate script missing,
# DB missing without creation), and credential redaction with a real payload.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."

SCRIPT="${AUDIT_SCRIPT_UNDER_TEST:-scripts/zero_shortcomings_audit.sh}"
pass=0; fail=0
check() {
    local desc="$1" cond="$2"
    if eval "$cond"; then printf '  PASS: %s\n' "$desc"; pass=$((pass + 1))
    else printf '  FAIL: %s\n' "$desc"; fail=$((fail + 1)); fi
}

T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
export AUDIT_STANDING_LOG_DIR="$T/logs"

# Fixture DB whose item titles carry a credential-shaped string.
DB="$T/w.db"
sqlite3 "$DB" "CREATE TABLE items(atm_id TEXT, status TEXT, severity TEXT, title TEXT, last_modified TEXT);
CREATE TABLE item_history(atm_id TEXT, event_type TEXT);
INSERT INTO items VALUES('X-1','Queued',NULL,'RUTRACKER_PASSWORD=hunter2-fixture-not-real','2026-01-01');"
STUB="$T/gate_ok.sh"
printf '#!/usr/bin/env bash\necho "LEDGER: unimplemented=3"\n' > "$STUB"

run() { # run <logdir-suffix> env... ; sets rc, out (stdout+stderr), log
    local d="$T/logs"; rm -rf "$d"
    rc=0
    out="$(env "$@" bash "$SCRIPT" standing-check 2>&1)" || rc=$?
    log="$(cat "$d"/*.log 2>/dev/null || true)"
}

# 1. healthy
run WORKABLE_ITEMS_DB_OVERRIDE="$DB" GATE_LEDGER_SCRIPT_OVERRIDE="$STUB"
check "healthy: exit 0" '[[ "$rc" -eq 0 ]]'
check "healthy: exactly one log line" '[[ "$(printf "%s\n" "$log" | grep -c .)" -eq 1 ]]'
check "healthy: mode=standing-check status=ok" 'grep -q "mode=standing-check status=ok" <<<"$log"'
check "healthy: counts present" 'grep -q "\"backlog_open\":1" <<<"$log" && grep -q "\"gates_unimplemented\":3" <<<"$log"'
check "credential fixture value never reaches log/stdout/stderr" \
    '! grep -q "hunter2-fixture-not-real" <<<"$log$out"'

# 2. degraded: gate script missing (I1)
run WORKABLE_ITEMS_DB_OVERRIDE="$DB" GATE_LEDGER_SCRIPT_OVERRIDE="$T/nonexistent.sh"
check "gate missing: still exit 0 (advisory)" '[[ "$rc" -eq 0 ]]'
check "gate missing: log marked status=degraded naming gates" \
    'grep -q "status=degraded" <<<"$log" && grep -q "failed=gates" <<<"$log"'
check "gate missing: WARN printed" 'grep -q "WARN" <<<"$out"'
check "gate missing: not marked ok" '! grep -q "status=ok" <<<"$log"'

# 3. degraded: DB missing, must not be created (I2)
MISSING="$T/does_not_exist.db"
run WORKABLE_ITEMS_DB_OVERRIDE="$MISSING" GATE_LEDGER_SCRIPT_OVERRIDE="$STUB"
check "db missing: still exit 0" '[[ "$rc" -eq 0 ]]'
check "db missing: status=degraded reason=db_missing" \
    'grep -q "status=degraded" <<<"$log" && grep -q "db_missing" <<<"$log"'
check "db missing: path was NOT created" '[[ ! -e "$MISSING" ]]'

printf 'test_zero_shortcomings_audit_standing_check: %d passed, %d failed\n' "$pass" "$fail"
[[ "$fail" -eq 0 ]]
