#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
source scripts/zero_shortcomings_audit.sh 2>/dev/null || true

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

# A fake, credential-SHAPED value (never a real secret -- this is a fixture).
plain="3 passed, 0 failed"
out_plain="$(audit_redact_before_write "$plain")"
check "ordinary, non-credential text passes through unchanged" \
    '[[ "$out_plain" == "$plain" ]]'

leaky="RUTRACKER_PASSWORD=hunter2-fixture-value-not-real"
out_leaky="$(audit_redact_before_write "$leaky")"
check "a credential-shaped VALUE is redacted" \
    '! printf "%s" "$out_leaky" | grep -q "hunter2-fixture-value-not-real"'
check "the credential's VARIABLE NAME remains loggable (Principle III: names loggable, values are not)" \
    'printf "%s" "$out_leaky" | grep -q "RUTRACKER_PASSWORD"'
check "the redaction marker is present in place of the value" \
    'printf "%s" "$out_leaky" | grep -q "redacted-per"'

printf 'test_zero_shortcomings_audit_redaction: %d passed, %d failed\n' "$pass" "$fail"
[[ "$fail" -eq 0 ]]
