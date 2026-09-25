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

# Task 4+4B combined review finding (Critical, 2026-09-25): a broken/crashing
# gate-ledger script must NEVER be reported identically to "genuinely zero
# unimplemented gates" -- exactly the §11.4.201(6) false-null class this tool
# exists to catch. Point the gate-ledger script at a genuinely non-existent
# path and confirm the counter fails LOUD rather than silently printing 0.
if fake_gates_out="$(GATE_LEDGER_SCRIPT_OVERRIDE=/nonexistent/gate_ledger.sh \
    bash scripts/zero_shortcomings_audit.sh enumerate --json --surface gates 2>/tmp/audit_gates_err)"; then
    fake_gates_rc=0
else
    fake_gates_rc=$?
fi
check "a broken gate-ledger script makes the counter fail loud, never silently report 0" \
    '[[ "$fake_gates_rc" -ne 0 ]] && [[ -s /tmp/audit_gates_err ]] && ! printf "%s" "$fake_gates_out" | grep -q "\"gates_unimplemented\":0"'
rm -f /tmp/audit_gates_err

# Task 4+4B combined review finding (Important, 2026-09-25): an unrecognized
# --surface value must fail with an actionable message, never a silent abort
# with zero explanatory output.
if bad_surface_out="$(bash scripts/zero_shortcomings_audit.sh enumerate --surface bogus 2>&1)"; then
    bad_surface_rc=0
else
    bad_surface_rc=$?
fi
check "an unrecognized --surface value fails with a printed error, not a silent abort" \
    '[[ "$bad_surface_rc" -ne 0 ]] && printf "%s" "$bad_surface_out" | grep -qi "surface"'

printf 'test_zero_shortcomings_audit_enumerate: %d passed, %d failed\n' "$pass" "$fail"
[[ "$fail" -eq 0 ]]
