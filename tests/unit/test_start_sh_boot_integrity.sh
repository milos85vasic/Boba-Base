#!/usr/bin/env bash
# test_start_sh_boot_integrity.sh — RED-first guard for the three boot-integrity
# defects that made `./start.sh` unable to bring the stack up and made
# admin/admin login impossible (§11.4.115 RED-on-the-broken-artifact).
#
# THE THREE DEFECT CLASSES THIS PINS (all measured 2026-09-01):
#
#   D1  ARITHMETIC BOOT-ABORT.
#       `((attempt++))` with attempt=0 evaluates to 0, which bash maps to
#       exit status 1. Under `set -euo pipefail` that TERMINATES start.sh.
#       Measured: `bash -c 'set -e; a=0; ((a++)); echo after'` never prints
#       "after" and exits 1. Three retry loops used this form
#       (wait_for_container, wait_for_jackett, ensure_webui_password), so a
#       service that was not healthy on its FIRST probe killed the whole boot
#       silently — the `print_warning ... return 0` fallbacks below each loop
#       were unreachable code. Everything downstream (Jackett API key
#       extraction, WebUI password setup, credential-store assertion, status
#       report) never ran.
#
#   D2  CREDENTIAL WRITER IS REPLACE-ONLY, NEVER INSERT.
#       _ensure_webui_credentials guarded both credential writes behind
#       `grep -q "^WebUI\\Username=" && sed ...`. On a config file that lacks
#       the key — which is the shape qBittorrent itself writes on a fresh
#       install — the sed never fires and the function still returns 0. The
#       credentials were therefore silently never written, and qBittorrent
#       5.x minted a random temporary password on every boot instead.
#
#   D3  SUCCESS DETECTED BY THE LITERAL BODY "Ok.".
#       Measured against the real image (qBittorrent v5.2.3, WebAPI 2.15.1):
#       a SUCCESSFUL login returns HTTP 204 with an EMPTY body and sets
#       cookie QBT_SID_<port>. It does NOT return `200 "Ok."` — that is the
#       qBittorrent 4.x signal. Every `[[ "$login_result" == "Ok." ]]` check
#       therefore reads a real success as a failure. The repo already knew
#       this at tests/unit/test_qbit_login_compat.py; the knowledge never
#       reached the shell scripts.
#
# POLARITY (§11.4.115 RED_MODE):
#   RED_MODE=1 -> assert the DEFECTS ARE PRESENT (reproduces the broken state)
#   RED_MODE=0 -> (default) assert the defects are FIXED — the regression guard
#
# Exit codes: 0 all assertions matched | 1 divergence | 2 harness error.

set -uo pipefail

RED_MODE="${RED_MODE:-0}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
START_SH="$REPO_ROOT/start.sh"

if [[ ! -f "$START_SH" ]]; then
    echo "HARNESS ERROR: start.sh not found at $START_SH" >&2
    exit 2
fi

PASS_COUNT=0
FAIL_COUNT=0
declare -a FAIL_DETAILS=()
assert_pass() { echo "PASS: $*"; PASS_COUNT=$((PASS_COUNT + 1)); }
assert_fail() { echo "FAIL: $*"; FAIL_COUNT=$((FAIL_COUNT + 1)); FAIL_DETAILS+=("$*"); }

TMPD="$(mktemp -d -t start_boot_integrity.XXXXXX)"
trap 'rm -rf "$TMPD"' EXIT

echo "=== test_start_sh_boot_integrity (RED_MODE=$RED_MODE) ==="
echo

# ---------------------------------------------------------------------------
# CONTROL NEEDLE (§11.4.201(7)(b)) — prove the instrument can SEE a defect of
# this exact shape before trusting any "clean" reading below. A grep that
# cannot find a known-present pattern would report every file clean.
# ---------------------------------------------------------------------------
NEEDLE="$TMPD/needle.sh"
printf '%s\n' 'x=0' '((x++))' > "$NEEDLE"
if grep -qE '\(\([a-zA-Z_][a-zA-Z0-9_]*\+\+\)\)' "$NEEDLE"; then
    echo "control needle: instrument CAN see the ((var++)) shape — readings below are meaningful"
else
    echo "HARNESS ERROR: control needle NOT seen — instrument is blind, refusing to report" >&2
    exit 2
fi
echo

# ---------------------------------------------------------------------------
# D1 — the arithmetic boot-abort, tested BEHAVIOURALLY through the real
#      functions (not by grepping the source: source-grep is the wrong
#      evidence class for a runtime abort, §11.4.226).
# ---------------------------------------------------------------------------
echo "--- D1: retry loops must not abort the boot under set -euo pipefail ---"

run_loop_probe() {
    # $1 = function name, $2... = stub definitions
    local fn="$1"; shift
    local out rc
    out="$TMPD/${fn}.out"
    # Deliberately reproduce start.sh's own shell options, then force the
    # not-ready path so the loop actually iterates.
    bash -c "
        set -euo pipefail
        source '$START_SH' >/dev/null 2>&1
        $*
        # M1 (review): this knob used to be dead — start.sh read nothing named
        # max_attempts_override, so the D1 probes ran the FULL 60s/30s
        # production budgets inside a "unit" test. start.sh now honours
        # BOBA_WAIT_MAX_ATTEMPTS, so the loop is exercised in ~1s.
        export BOBA_WAIT_MAX_ATTEMPTS=1
        $fn
    " > "$out" 2>&1
    rc=$?
    echo "$rc"
}

# wait_for_jackett with curl always failing -> must reach its warning, rc 0
RC_JACKETT="$(run_loop_probe wait_for_jackett 'curl() { return 1; }')"
if [[ "$RED_MODE" == "1" ]]; then
    if [[ "$RC_JACKETT" != "0" ]]; then
        assert_pass "D1(RED): wait_for_jackett aborts as expected (rc=$RC_JACKETT)"
    else
        assert_fail "D1(RED): expected abort, got rc=0 — defect already fixed?"
    fi
else
    if [[ "$RC_JACKETT" == "0" ]]; then
        assert_pass "D1: wait_for_jackett survives an unhealthy service (rc=0)"
    else
        assert_fail "D1: wait_for_jackett ABORTED the boot with rc=$RC_JACKETT (expected 0). Output: $(head -3 "$TMPD/wait_for_jackett.out" 2>/dev/null | tr '\n' ' ')"
    fi
fi

RC_CONTAINER="$(run_loop_probe wait_for_container 'CONTAINER_RUNTIME=false')"
if [[ "$RED_MODE" == "1" ]]; then
    if [[ "$RC_CONTAINER" != "0" ]]; then
        assert_pass "D1(RED): wait_for_container aborts as expected (rc=$RC_CONTAINER)"
    else
        assert_fail "D1(RED): expected abort, got rc=0"
    fi
else
    if [[ "$RC_CONTAINER" == "0" ]]; then
        assert_pass "D1: wait_for_container survives a missing container (rc=0)"
    else
        assert_fail "D1: wait_for_container ABORTED the boot with rc=$RC_CONTAINER (expected 0)"
    fi
fi

# Source-level backstop: the unsafe form must not reappear anywhere in start.sh
#
# CARRIER GUARD (§11.4.201(7)(a)) — added 2026-09-01 after this check was caught
# doing exactly what D4 below was already written to avoid. It grepped the RAW
# file, so a COMMENT merely MENTIONING `((attempt++))` matched as if it were
# live code. That is not hypothetical: another agent documenting the historical
# defect in start.sh tripped this check and had to reword a TRUTHFUL comment to
# get a clean run — a detector punishing accurate documentation of the very bug
# it guards, and the same class this file's D4 arm already fences off.
#
# Measured before the fix:
#   printf '# historical note: the old code used ((attempt++)) here\n' | grep -E ...
#   -> MATCHED (a comment read as code)
#
# The behavioural D1 probes above are unaffected — they execute the real
# functions, so no comment can influence them. Only this source backstop needed
# the code-only view.
START_CODE_D1="$TMPD/start_code_d1.sh"
sed 's/[[:space:]]*#.*$//' "$START_SH" > "$START_CODE_D1"
# Control needle on the code-only view: the arithmetic the fix INTRODUCED must
# still be visible after comment-stripping, or a "clean" reading below is a
# false null from a blinded reader (§11.4.201(7)(b)).
if ! grep -qE 'attempt=\$\(\(attempt \+ 1\)\)' "$START_CODE_D1"; then
    echo "HARNESS ERROR: code-only reader sees no retry arithmetic at all — refusing to report" >&2
    exit 2
fi
UNSAFE_HITS="$(grep -nE '\(\([a-zA-Z_][a-zA-Z0-9_]*\+\+\)\)' "$START_CODE_D1" 2>/dev/null || true)"
if [[ "$RED_MODE" == "1" ]]; then
    if [[ -n "$UNSAFE_HITS" ]]; then
        assert_pass "D1(RED): unsafe ((var++)) present as expected"
    else
        assert_fail "D1(RED): no unsafe ((var++)) found"
    fi
else
    if [[ -z "$UNSAFE_HITS" ]]; then
        assert_pass "D1: no unsafe ((var++)) remains in start.sh"
    else
        assert_fail "D1: unsafe ((var++)) still present:"$'\n'"$UNSAFE_HITS"
    fi
fi

# NEGATIVE CONTROL (§11.4.201(1)) — a false-positive refusal is a FAIL-bluff of
# equal severity to missing the defect. Prove the code-only view does NOT flag a
# comment that legitimately discusses the historical `((attempt++))` form. This
# arm is what makes the carrier guard above load-bearing rather than decorative:
# revert the backstop to grep the raw file and this arm FAILs.
D1_CARRIER="$TMPD/d1_carrier.sh"
printf '%s\n' \
    '#!/usr/bin/env bash' \
    '# historical note: this loop used to be ((attempt++)), which returns exit' \
    '# status 1 when attempt is 0 and therefore killed the boot under set -e.' \
    'attempt=$((attempt + 1))' > "$D1_CARRIER"
D1_CARRIER_CODE="$TMPD/d1_carrier_code.sh"
sed 's/[[:space:]]*#.*$//' "$D1_CARRIER" > "$D1_CARRIER_CODE"
if grep -qE '\(\([a-zA-Z_][a-zA-Z0-9_]*\+\+\)\)' "$D1_CARRIER_CODE"; then
    assert_fail "D1(carrier): a COMMENT mentioning ((attempt++)) was flagged as live code — the detector punishes truthful documentation"
else
    assert_pass "D1(carrier): a comment mentioning ((attempt++)) is correctly NOT flagged"
fi
# And the same fixture WITHOUT comment-stripping must match, or the arm above
# proves nothing (it would pass against a detector that simply sees nothing).
if grep -qE '\(\([a-zA-Z_][a-zA-Z0-9_]*\+\+\)\)' "$D1_CARRIER"; then
    assert_pass "D1(carrier): the raw fixture DOES match — the carrier arm is meaningful, not vacuous"
else
    assert_fail "D1(carrier): raw fixture did not match either — the carrier arm is vacuous and proves nothing"
fi
echo

# ---------------------------------------------------------------------------
# D2 — credential writer must INSERT, not only replace.
#      Fixture is the EXACT shape qBittorrent 5.2.3 writes on a fresh install:
#      a [Preferences] section with WebUI keys but NO Username/Password.
# ---------------------------------------------------------------------------
echo "--- D2: credentials must be written into a config that lacks the keys ---"
FRESH="$TMPD/fresh_qBittorrent.conf"
cat > "$FRESH" <<'CONF'
[BitTorrent]
Session\DefaultSavePath=/downloads/

[Meta]
MigrationVersion=8

[Preferences]
Connection\PortRangeMin=6881
Downloads\SavePath=/downloads/
WebUI\Address=*
WebUI\Port=7185
WebUI\ServerDomains=*
CONF

bash -c "
    set -uo pipefail
    source '$START_SH' >/dev/null 2>&1
    _ensure_webui_credentials '$FRESH'
" > "$TMPD/cred.out" 2>&1
CRED_RC=$?

HAS_USER=0; HAS_PASS=0
grep -q '^WebUI\\Username=admin$' "$FRESH" && HAS_USER=1
grep -q '^WebUI\\Password_PBKDF2=@ByteArray(' "$FRESH" && HAS_PASS=1

if [[ "$RED_MODE" == "1" ]]; then
    if [[ "$HAS_USER" == "0" && "$HAS_PASS" == "0" ]]; then
        assert_pass "D2(RED): credentials silently not written, as expected (rc=$CRED_RC)"
    else
        assert_fail "D2(RED): credentials WERE written (user=$HAS_USER pass=$HAS_PASS)"
    fi
else
    if [[ "$HAS_USER" == "1" ]]; then
        assert_pass "D2: WebUI\\Username=admin inserted into a config lacking it"
    else
        assert_fail "D2: WebUI\\Username was NOT inserted (rc=$CRED_RC). This is the defect that made admin/admin impossible."
    fi
    if [[ "$HAS_PASS" == "1" ]]; then
        assert_pass "D2: WebUI\\Password_PBKDF2 inserted into a config lacking it"
    else
        assert_fail "D2: WebUI\\Password_PBKDF2 was NOT inserted (rc=$CRED_RC)"
    fi
fi

# NEGATIVE CONTROL (§11.4.201(1)) — an ALREADY-correct config must be left
# valid, not corrupted or duplicated. A guard that mangles good input is a
# false-positive engine.
ALREADY="$TMPD/already_qBittorrent.conf"
cat > "$ALREADY" <<'CONF'
[Preferences]
WebUI\Address=*
WebUI\Username=admin
WebUI\Password_PBKDF2=@ByteArray(PLACEHOLDER==:PLACEHOLDER==)
WebUI\Port=7185
CONF
bash -c "set -uo pipefail; source '$START_SH' >/dev/null 2>&1; _ensure_webui_credentials '$ALREADY'" >/dev/null 2>&1
DUP_USER="$(grep -c '^WebUI\\Username=' "$ALREADY" || true)"
if [[ "$DUP_USER" == "1" ]]; then
    assert_pass "D2(neg-control): an already-correct config keeps exactly one Username line"
else
    assert_fail "D2(neg-control): Username line count is $DUP_USER, expected 1 (writer duplicates keys)"
fi
echo

# ---------------------------------------------------------------------------
# D3 — login success must not be decided by the literal body "Ok." alone.
#      Measured truth: qBittorrent 5.2.3 returns 204 + empty body + QBT_SID.
# ---------------------------------------------------------------------------
echo "--- D3: login success detection must handle 204 + empty body ---"
OK_ONLY_HITS="$(grep -nE '\[\[ *"\$login_result" *[=!]= *"Ok\." *\]\]' "$START_SH" 2>/dev/null || true)"
if [[ "$RED_MODE" == "1" ]]; then
    if [[ -n "$OK_ONLY_HITS" ]]; then
        assert_pass "D3(RED): body==\"Ok.\" success detection present, as expected"
    else
        assert_fail "D3(RED): no \"Ok.\"-only check found"
    fi
else
    if [[ -z "$OK_ONLY_HITS" ]]; then
        assert_pass "D3: no bare body==\"Ok.\" success check remains"
    else
        assert_fail "D3: login success still decided by body==\"Ok.\" — a 204 success reads as failure:"$'\n'"$OK_ONLY_HITS"
    fi
    # The fixed code must actually consult the HTTP status or the cookie.
    if grep -qE 'QBT_SID|http_code|%\{http_code\}' "$START_SH"; then
        assert_pass "D3: start.sh consults HTTP status and/or the QBT_SID cookie"
    else
        assert_fail "D3: start.sh consults neither HTTP status nor QBT_SID cookie"
    fi
fi
echo

# ---------------------------------------------------------------------------
# D4 — AUTHENTICATION MUST NOT BE BYPASSED.
#      Regression guard for a security defect introduced and caught during the
#      2026-09-01 login repair: enforcing the template's
#        WebUI\LocalHostAuth=false + WebUI\AuthSubnetWhitelistEnabled=true
#      (whitelist = loopback + ALL RFC1918) does not relax the brute-force ban,
#      it DISABLES AUTHENTICATION for every listed subnet. With network_mode:
#      host and WebUI\Address=*, that leaves the WebUI unauthenticated across
#      the whole LAN.
#      MEASURED with the bypass ON : wrong password -> HTTP 204 (accepted).
#      MEASURED with the bypass OFF: wrong password -> HTTP 401, and an
#      unauthenticated API call -> Forbidden.
# ---------------------------------------------------------------------------
echo "--- D4: start.sh must not disable WebUI authentication ---"
# CARRIER GUARD (§11.4.201(7)(a)): strip comments before matching. The first
# version of this check grepped the raw file, so an ACCURATE comment describing
# the removed bypass made the test report a violation — a detector that
# punishes truthful documentation of the defect it guards.
START_CODE_D4="$TMPD/start_code_d4.sh"
sed 's/[[:space:]]*#.*$//' "$START_SH" > "$START_CODE_D4"
if ! grep -qE '_enforce_config_line .*LocalHostAuth' "$START_CODE_D4"; then
    echo "HARNESS ERROR: code-only reader sees no LocalHostAuth call — refusing to report" >&2
    exit 2
fi
BYPASS_HITS="$(grep -nE '_enforce_config_line[^#]*LocalHostAuth[^#]*"false"|_enforce_config_line[^#]*AuthSubnetWhitelistEnabled[^#]*"true"' "$START_CODE_D4" 2>/dev/null || true)"
if [[ "$RED_MODE" == "1" ]]; then
    if [[ -n "$BYPASS_HITS" ]]; then
        assert_pass "D4(RED): auth-bypass settings present, as expected"
    else
        assert_fail "D4(RED): no auth-bypass settings found"
    fi
else
    if [[ -z "$BYPASS_HITS" ]]; then
        assert_pass "D4: start.sh does not disable localhost auth or enable the subnet-auth whitelist"
    else
        assert_fail "D4: start.sh still DISABLES WebUI authentication:"$'\n'"$BYPASS_HITS"
    fi
    # It must still relax the LOCKOUT (that was the legitimate need).
    if grep -q 'MaxAuthenticationFailCount' "$START_SH"; then
        assert_pass "D4: brute-force lockout is still relaxed via MaxAuthenticationFailCount (the check is kept, the lockout is loosened)"
    else
        assert_fail "D4: MaxAuthenticationFailCount no longer enforced — test-suite login probes may trip an IP ban"
    fi
    # NEGATIVE CONTROL (§11.4.201(1)): start.sh's own comment DOES contain the
    # literal `LocalHostAuth=false` (it documents the removed bypass). That
    # carrier must NOT be reported as a violation.
    if grep -q 'WebUI\\LocalHostAuth=false' "$START_SH" && [[ -z "$BYPASS_HITS" ]]; then
        assert_pass "D4(carrier): the literal appears in a comment and is correctly NOT flagged"
    elif ! grep -q 'WebUI\\LocalHostAuth=false' "$START_SH"; then
        assert_pass "D4(carrier): no carrier present to test (vacuous, not a failure)"
    else
        assert_fail "D4(carrier): a comment mention of the bypass was flagged as real code"
    fi
fi
echo

# ---------------------------------------------------------------------------
echo "=== summary: PASS=$PASS_COUNT FAIL=$FAIL_COUNT ==="
if [[ "$FAIL_COUNT" -gt 0 ]]; then
    echo "--- failures ---"
    for d in "${FAIL_DETAILS[@]}"; do echo "  * $d"; done
    exit 1
fi
exit 0
