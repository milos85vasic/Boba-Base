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

# Regression tests for the Task 5C security-reviewer Critical finding
# (agent a3c502c254c1b2ffc): the cited keyword alternation
# (password|passwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token|
# client[_-]?secret) does not cover this project's own documented
# credential-variable surface (CLAUDE.md: BOBA_MASTER_KEY "Loss = total
# credential loss"; BOBA_API_TOKEN; per-tracker <TRACKER>_COOKIES "cookie
# values NEVER enter logs"). Each of these three must redact its value while
# keeping the variable name loggable, per Principle III.
master_key="BOBA_MASTER_KEY=master-key-fixture-value-not-real"
out_master_key="$(audit_redact_before_write "$master_key")"
check "BOBA_MASTER_KEY value is redacted (security review Critical-1)" \
    '! printf "%s" "$out_master_key" | grep -q "master-key-fixture-value-not-real"'
check "BOBA_MASTER_KEY variable name remains loggable" \
    'printf "%s" "$out_master_key" | grep -q "BOBA_MASTER_KEY"'

api_token="BOBA_API_TOKEN=api-token-fixture-value-not-real"
out_api_token="$(audit_redact_before_write "$api_token")"
check "BOBA_API_TOKEN value is redacted (security review Critical-1)" \
    '! printf "%s" "$out_api_token" | grep -q "api-token-fixture-value-not-real"'
check "BOBA_API_TOKEN variable name remains loggable" \
    'printf "%s" "$out_api_token" | grep -q "BOBA_API_TOKEN"'

cookies="NNMCLUB_COOKIES=cookie-fixture-value-not-real"
out_cookies="$(audit_redact_before_write "$cookies")"
check "tracker COOKIES value is redacted (security review Critical-1)" \
    '! printf "%s" "$out_cookies" | grep -q "cookie-fixture-value-not-real"'
check "tracker COOKIES variable name remains loggable" \
    'printf "%s" "$out_cookies" | grep -q "NNMCLUB_COOKIES"'

# Review finding I-4: shapes that previously leaked (each probe value is a
# fixture, never a real secret). Every case: the VALUE is gone, the NAME stays.
redact_case() { # desc input leaked-value name-that-must-remain
    local desc="$1" input="$2" leaked="$3" name="$4" out
    out="$(audit_redact_before_write "$input")"
    printf '    %s  =>  %s\n' "$input" "$out"
    check "I-4 $desc: value redacted" '! printf "%s" "$out" | grep -qF -- "$leaked"'
    check "I-4 $desc: name remains loggable" 'printf "%s" "$out" | grep -qF -- "$name"'
}
redact_case "JSON quoted key + space + quoted value" '{"api_key": "SEKRETJSON1"}' 'SEKRETJSON1' 'api_key'
redact_case "single-quoted multi-word value" "password='a SEKRET2'" 'SEKRET2' 'password'
redact_case "double-quoted multi-word value" 'RUTRACKER_PASSWORD="hello SEKRET3"' 'SEKRET3' 'RUTRACKER_PASSWORD'
redact_case "URL user:pass@host credentials" 'https://user:SEKRET4@host/x' 'SEKRET4' 'https://user:'
redact_case "token-only URL userinfo (GitHub PAT clone form)" 'git clone https://SEKRETPAT@github.com/org/repo.git' 'SEKRETPAT' 'github.com/org/repo.git'
redact_case "curl -u user:pass basic auth" 'curl -u admin:SEKRETCU https://host/x' 'SEKRETCU' 'admin'
redact_case "Authorization Bearer header" 'Authorization: Bearer SEKRET5' 'SEKRET5' 'Authorization'
redact_case "bare Bearer token" 'curl sent Bearer SEKRET5B to host' 'SEKRET5B' 'Bearer'
redact_case "cookie string runs to end of line" 'NNMCLUB_COOKIES=abc SEKRET6=1' 'SEKRET6' 'NNMCLUB_COOKIES'
redact_case "Cookie request header" 'Cookie: bb_session=SEKRET8; cf=SEKRET9' 'SEKRET9' 'Cookie'
redact_case "spaced separator" 'password = SEKRET7' 'SEKRET7' 'password'
redact_case "space-separated CLI flag" 'tool --api-key SEKRET10 --verbose' 'SEKRET10' '--api-key'

multi="$(audit_redact_before_write "$(printf 'line one ok\npassword=SEKRETML\nline three ok')")"
check "I-4 multi-line input: the credential line is redacted and other lines kept" \
    '! printf "%s" "$multi" | grep -q SEKRETML && printf "%s" "$multi" | grep -q "line three ok"'

# No over-redaction of the standing-check record (its JSON count keys and
# markers must stay byte-identical, or the pre-build stage would log garbage).
standing_line='20260926T000000Z-pid1 mode=standing-check status=ok {"backlog_open":41,"gates_unimplemented":7,"escapes_open":2}'
check "I-4 standing-check JSON count keys pass through byte-identical" \
    '[[ "$(audit_redact_before_write "$standing_line")" == "$standing_line" ]]'

# The recorded command's STDERR must pass through the redactor too.
stderr_out="$(AUDIT_QA_ROOT=tests/audit/fixtures/docs_qa_fixture bash scripts/zero_shortcomings_audit.sh verify-closure BOB-FIXTURE-STDERR-CREDENTIAL 2>&1)" || true
printf '    stderr-path output: %s\n' "$(printf '%s' "$stderr_out" | tr '\n' ' ')"
check "I-4 the recorded command's stderr credential value never reaches the terminal" \
    '! printf "%s" "$stderr_out" | grep -q "stderr-leak-fixture-not-real"'
check "I-4 the recorded command's stderr is still shown (name loggable, not swallowed)" \
    'printf "%s" "$stderr_out" | grep -q "BOBA_API_TOKEN"'

# Integration-level regression for the same review's Important finding:
# exercise the REAL cmd_verify_closure MISMATCH branch (not the standalone
# function above) so the wiring at the actual print_error call site is
# proven to redact both the recorded AND the fresh credential-shaped value,
# never just audit_redact_before_write in isolation.
export AUDIT_QA_ROOT="tests/audit/fixtures/docs_qa_fixture"
# `verify-closure` returning 1 on a genuine MISMATCH is the EXPECTED result
# here (this fixture is deliberately mismatched) -- not the exceptional case
# `set -e` guards against. The `|| true` is required so the command
# substitution's non-zero exit does not abort this test script before the
# assertions below (and the final summary line) ever run -- the same
# §11.4.201(12) set -e/pipefail class fixed repeatedly elsewhere in this
# audit feature's own test suite.
leak_path_out="$(bash scripts/zero_shortcomings_audit.sh verify-closure BOB-FIXTURE-MISMATCH-CREDENTIAL 2>&1)" || true
unset AUDIT_QA_ROOT
check "cmd_verify_closure's real MISMATCH print_error redacts the recorded credential value" \
    '! printf "%s" "$leak_path_out" | grep -q "hunter2-recorded-fixture-not-real"'
check "cmd_verify_closure's real MISMATCH print_error redacts the fresh credential value" \
    '! printf "%s" "$leak_path_out" | grep -q "live-token-fixture-not-real"'
check "cmd_verify_closure's real MISMATCH print_error keeps both variable names loggable" \
    'printf "%s" "$leak_path_out" | grep -q "RUTRACKER_PASSWORD" && printf "%s" "$leak_path_out" | grep -q "BOBA_API_TOKEN"'

printf 'test_zero_shortcomings_audit_redaction: %d passed, %d failed\n' "$pass" "$fail"
[[ "$fail" -eq 0 ]]
