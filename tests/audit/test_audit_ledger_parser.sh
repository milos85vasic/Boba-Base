#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
source scripts/lib/audit_ledger_parser.sh

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

good_count="$(audit_ledger_count_open_escapes tests/audit/fixtures/ledger_golden_good.md)"
check "golden-good ledger (all entries closed or automated) reports 0 open" \
    '[[ "$good_count" -eq 0 ]]'

bad_count="$(audit_ledger_count_open_escapes tests/audit/fixtures/ledger_golden_bad_missing_new_check.md)"
check "golden-bad ledger (one entry with no new-check) reports 1 open" \
    '[[ "$bad_count" -eq 1 ]]'

malformed_count="$(audit_ledger_count_malformed tests/audit/fixtures/ledger_malformed_escape_audit.md)"
check "an out-of-band entry with no escape-audit field is reported malformed" \
    '[[ "$malformed_count" -eq 1 ]]'

# Review Focus item 1: a missing/unreadable ledger MUST fail loudly, never
# silently report a clean 0 — the exact false-null class §11.4.201(6) forbids.
set +e
audit_ledger_count_open_escapes /nonexistent/ledger.md >/tmp/audit_parser_missing_out 2>/tmp/audit_parser_missing_err
missing_rc=$?
set -e
check "a missing ledger file exits non-zero rather than printing 0" \
    '[[ "$missing_rc" -ne 0 ]]'
check "a missing ledger file prints an actionable error on stderr" \
    '[[ -s /tmp/audit_parser_missing_err ]]'
rm -f /tmp/audit_parser_missing_out /tmp/audit_parser_missing_err

printf 'test_audit_ledger_parser: %d passed, %d failed\n' "$pass" "$fail"
[[ "$fail" -eq 0 ]]
