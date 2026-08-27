#!/usr/bin/env bash
# test_ddos_sibling_retry_after_classification.sh — BOB-163.
#
# challenges/scripts/ddos_resilience_challenge.sh assertion (c) (CROSS-ENDPOINT
# ISOLATION) must treat a 429 carrying a WELL-FORMED Retry-After as a
# RESPONSIVE sibling, not a degraded one.
#
# THE DEFECT (measured live 2026-08-26, :7187/health):
#     HTTP/1.1 200 OK
#     server: uvicorn
#     x-ratelimit-limit: 120
#     x-ratelimit-remaining: 118
#     retry-after: 49
# :7187 now enforces a real limiter. A full challenge run sends ~250 requests
# to :7187, so the sibling probes fired while OTHER endpoints are under their
# heaviest tier land on an exhausted bucket and receive 429. Assertion (c)
# required `^2` and therefore read that 429 as "endpoint degraded" — a
# §11.4.1 FAIL-bluff: it condemns a service that is working correctly and
# protecting itself exactly as designed.
#
# OPERATOR DECISION (§11.4.66, recorded 2026-08-26): "Yes, if Retry-After is
# well-formed" — a 429 carrying a valid Retry-After IS evidence of a live
# service correctly protecting itself.
#
# REQUIRED BEHAVIOUR:
#   RESPONSIVE — any 2xx; OR a 429 whose Retry-After is well-formed (a
#                POSITIVE integer seconds value, or a valid HTTP-date that
#                actually PARSES — never merely "the header is non-empty").
#   DEGRADED   — connection failure, timeout, any 5xx, any other non-2xx, and
#                a 429 whose Retry-After is ABSENT or MALFORMED.
#
# §11.4.224/§11.4.43 RED-FIRST: against the pre-fix script `--self-validate`
# carries no sibling-responsiveness detector at all, so every assertion below
# finds nothing and this test FAILs. It GREENs only once the detector exists
# AND classifies all its golden fixtures correctly.
#
# §11.4.201(11) artifact-usability: this drives the REAL script through its
# REAL invocation path (`bash <script> --self-validate`) and asserts on its
# real stdout + real exit status. It never re-implements the classifier, never
# sources internals, and is never a `bash -n` parse check — a parse check
# proves nothing about behaviour (§11.4.224(A)).
#
# §11.4.249 producer != oracle: the fixtures the script self-validates against
# drive the SAME classifier the live assertion-(c) path mints verdicts from,
# so a mutation to the classifier breaks this test too. A copy of the parse
# inside this test would validate the copy, not the thing that ships.

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${HERE}/../.." && pwd)"
# DDOS_CHALLENGE_UNDER_TEST lets the §1.1 mutation harness point this suite at a
# COPY of the challenge, so a mutation is applied to the copy and the TRACKED
# file is never modified. Mutating the tracked file in place is what let an
# interrupted battery leave a live mutation marker in the working tree on
# 2026-08-26 — a §11.4.84 residue hazard that no amount of care removes, because
# the failure mode is the interruption, not the operator. Defaulting to the real
# path keeps the ordinary invocation (and every gate that runs it) unchanged.
SCRIPT="${DDOS_CHALLENGE_UNDER_TEST:-${PROJECT_ROOT}/challenges/scripts/ddos_resilience_challenge.sh}"

PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); echo "  PASS: $1"; }
fail() { FAIL=$((FAIL+1)); echo "  FAIL: $1"; }

finish() {
    echo "RESULT: $PASS passed, $FAIL failed"
    [ "$FAIL" -eq 0 ] || exit 1
    exit 0
}

echo "=== test_ddos_sibling_retry_after_classification (BOB-163) ==="

if [ ! -f "$SCRIPT" ]; then
    fail "challenges/scripts/ddos_resilience_challenge.sh not found at $SCRIPT"
    finish
fi

# The detector's fixtures are throwaway local python3 servers. Without python3
# the script SKIPs self-validation honestly, and so must this test — asserting
# a FAIL here would be exactly the §11.4.201(1) false-positive refusal the
# challenge itself forbids.
if ! command -v python3 >/dev/null 2>&1; then
    echo "SKIP: python3 not found (reason=tooling_absent) — the sibling fixtures cannot be spun up"
    finish
fi
if ! command -v curl >/dev/null 2>&1; then
    echo "SKIP: curl not found (reason=tooling_absent) — nothing can drive the fixtures"
    finish
fi

OUT_FILE="$(mktemp)"
trap 'rm -f "$OUT_FILE"' EXIT

echo "--- driving: bash $SCRIPT --self-validate ---"
nice -n 19 bash "$SCRIPT" --self-validate > "$OUT_FILE" 2>&1
SV_RC=$?
echo "    exit status: $SV_RC"
echo "--- captured output ---"
sed 's/^/    | /' "$OUT_FILE"
echo "--- end output ---"

if grep -q "^SKIP: python3 not found" "$OUT_FILE"; then
    echo "SKIP: the script itself skipped self-validation (reason=tooling_absent)"
    finish
fi

# §11.4.201(7)(b) CONTROL NEEDLE: before trusting ANY zero-hit result below as
# a real absence, prove this grep can see through this same path at all. The
# needle is a string the pre-fix script already emits, so it is present in
# both the RED and the GREEN run. A blind instrument and a clean artifact
# return the identical quiet zero.
NEEDLE='detector 1: crash resistance'
if grep -qF -- "$NEEDLE" "$OUT_FILE"; then
    pass "control needle: grep can see '$NEEDLE' through this path — zero-hit results below are real absences"
else
    fail "CONTROL NEEDLE MISSING: grep cannot see '$NEEDLE' in the captured output; every zero below is uninterpretable (§11.4.201(7)(b)) — instrument is blind, not the artifact clean"
    finish
fi

# --- the detector must exist at all ---------------------------------------
if grep -qF -- 'detector 3: sibling responsiveness' "$OUT_FILE"; then
    pass "self-validate drives a sibling-responsiveness detector (assertion (c)'s oracle)"
else
    fail "self-validate carries NO sibling-responsiveness detector — assertion (c)'s oracle has never been observed to FAIL on a broken artifact, so it may mint no verdicts (§11.4.115(F))"
fi

# --- the five mandated cases, each driven through real HTTP ----------------
# Each expectation is matched STRUCTURALLY on the fixture's own result line
# (§11.4.201(7)(a)): the fixture label AND its resolved class, never a bare
# substring that a narrative sentence could carry.
expect_class() {
    # expect_class <fixture-label> <expected-class> <human description>
    local label="$1" want="$2" desc="$3"
    if grep -qE "fixture '${label}'.*-> class=${want}( |\$|[^a-z])" "$OUT_FILE"; then
        pass "$desc — fixture '${label}' classified '${want}'"
    else
        local got
        got="$(grep -oE "fixture '${label}'.*" "$OUT_FILE" | head -1)"
        fail "$desc — fixture '${label}' did NOT classify '${want}' (line: ${got:-<no such fixture line>})"
    fi
}

# case 1 — 2xx is responsive (the pre-existing, unchanged behaviour)
expect_class 'ok200'               responsive "2xx sibling stays RESPONSIVE"
# case 2 — 429 + well-formed Retry-After is responsive (THE OPERATOR DECISION)
expect_class 'r429_valid_seconds'  responsive "429 + positive integer Retry-After is RESPONSIVE (a live service protecting itself)"
expect_class 'r429_valid_httpdate' responsive "429 + valid HTTP-date Retry-After is RESPONSIVE"
# case 3 — 429 with NO Retry-After is degraded
expect_class 'r429_missing'        degraded   "429 with ABSENT Retry-After is DEGRADED"
# case 4 — 429 with malformed Retry-After is degraded (a real PARSE, not a
# non-empty check: these values are all non-empty and all invalid)
expect_class 'r429_garbage'        degraded   "429 with MALFORMED Retry-After is DEGRADED (non-empty is not well-formed)"
expect_class 'r429_zero'           degraded   "429 with Retry-After: 0 is DEGRADED (zero is not a POSITIVE integer)"
expect_class 'r429_neg'            degraded   "429 with a negative Retry-After is DEGRADED"
expect_class 'r429_baddate'        degraded   "429 with a structurally-shaped but IMPOSSIBLE HTTP-date is DEGRADED (it must actually parse)"
# case 5 — connection refused is degraded; 5xx is degraded
expect_class 'refused'             degraded   "connection-refused sibling is DEGRADED"
expect_class 'srv500'              degraded   "5xx sibling is DEGRADED"

# --- the DECISION must be wired, not merely the classifier ------------------
# Measured 2026-08-26: an adversarial mutation that left the classifier fully
# intact and unwired ONLY the live assertion-(c) loop survived a
# classifier-only version of this test 14/14 green. A validated oracle that
# the live verdict never consults is the §11.4.196(F) configured-but-not-in-use
# bluff. These two assertions drive the shared decision function's BOTH
# polarities, so the live path and the self-test share one seam.
if grep -qE "decision 'all-responsive': rc=0" "$OUT_FILE"; then
    pass "decision function returns 'isolation held' on a 2xx + two well-formed-429 sample (the §11.4.1 FAIL-bluff is gone)"
else
    got="$(grep -oE "decision 'all-responsive'.*" "$OUT_FILE" | head -1)"
    fail "decision function did not report isolation held on an all-responsive sample (line: ${got:-<no decision line — the live decision is not exercised by any fixture>})"
fi
if grep -qE "decision 'one-degraded': rc=1" "$OUT_FILE"; then
    pass "decision function returns 'isolation broken' when the sample contains a malformed-429 and a refused connection"
else
    got="$(grep -oE "decision 'one-degraded'.*" "$OUT_FILE" | head -1)"
    fail "decision function did not flag a sample containing two degraded siblings (line: ${got:-<no decision line — the live decision is not exercised by any fixture>})"
fi

# --- F4: an EMPTY probe log must NOT read as "isolation held" ---------------
# The false-null shape (§11.4.201(6)): a probe that produced NO lines and a run
# in which every sibling was healthy return the identical quiet "no degraded
# sibling found". Zero observations is not evidence of health; the decision
# seam must fail closed and say why.
if grep -qE "decision 'empty-log': rc=1" "$OUT_FILE"; then
    pass "decision function FAILS CLOSED on an empty probe log (zero observations is not evidence of isolation)"
else
    got="$(grep -oE "decision 'empty-log'.*" "$OUT_FILE" | head -1)"
    fail "decision function did not fail closed on an empty probe log (line: ${got:-<no empty-log fixture — the false-null polarity is unguarded>})"
fi

# --- MINOR-1: fail-closed must key on PARSED OBSERVATIONS, not file size ----
# A zero-BYTE check is the narrowest possible reading of the §11.4.201(6)
# false-null. A log that is non-empty but yields FEWER PARSED OBSERVATIONS than
# probes launched is the same lie wearing a different shape:
#   * a blank-line / whitespace-only log is 1+ bytes and parses to nothing;
#   * a complete DEGRADED observation whose trailing newline was lost is
#     SILENTLY DROPPED by `while read` (it returns non-zero on an unterminated
#     final line), so the one sibling that WAS degraded vanishes and the run
#     reads "isolation held";
#   * a partial log (one probe subshell died before appending) reads "proven"
#     on half the evidence, because nothing compares observations to probes.
# Each must fail CLOSED against an expected-count contract.
for case in blank-line whitespace-only torn-degraded torn-mixed partial; do
    if grep -qE "decision '${case}': rc=1" "$OUT_FILE"; then
        pass "MINOR-1: '${case}' fails closed (parsed observations < probes launched)"
    else
        got="$(grep -oE "decision '${case}'.*" "$OUT_FILE" | head -1)"
        fail "MINOR-1: '${case}' did not fail closed (line: ${got:-<no such fixture — this shape of the false-null is unguarded>})"
    fi
done
# ...and the contract must NOT fire when the evidence really is complete
# (§11.4.201(1): a false-positive refusal is as forbidden as a false pass).
if grep -qE "decision 'complete-2of2': rc=0" "$OUT_FILE"; then
    pass "MINOR-1: a COMPLETE 2-of-2 all-responsive log still reads isolation held (no false-positive refusal)"
else
    got="$(grep -oE "decision 'complete-2of2'.*" "$OUT_FILE" | head -1)"
    fail "MINOR-1: the expected-count contract refuses a complete log (line: ${got:-<no such fixture>})"
fi

# --- the detector must not have flagged itself ------------------------------
if grep -qF -- '[SELF-VAL BAD]' "$OUT_FILE"; then
    echo "    offending self-validation lines:"
    grep -F -- '[SELF-VAL BAD]' "$OUT_FILE" | sed 's/^/      /'
    fail "self-validation reported at least one dishonest detector — the classifier failed its own golden fixtures"
else
    pass "no [SELF-VAL BAD] lines — every detector distinguished its golden-good from its golden-bad fixture"
fi

# --- F1: the HAVE_DATE_PARSE honest-skip must be honest at the ARTIFACT ------
# retry_after_wellformed documents a deliberate portability branch: where the
# host date(1) cannot parse (-d refused — the BSD/busybox shape), the semantic
# parse is skipped and the STRUCTURAL match stands alone. On such a host a
# correctly-SHAPED but impossible date ("Sun, 32 Nov 1994 25:99:99 GMT") is
# indistinguishable from a real one and classifies RESPONSIVE — by design.
#
# But the r429_baddate fixture asserted `degraded` UNCONDITIONALLY, so the two
# halves of the same mechanism contradicted each other: the detector was
# accused of misclassifying ("[SELF-VAL BAD] ... classified 'r429_baddate' as
# 'responsive', expected 'degraded'") when it had behaved exactly as specified.
# Because self-validation runs on EVERY live invocation, that turned an
# INSTRUMENT property into a whole-challenge exit 1 against a healthy product —
# the §11.4.201(1) false-positive refusal this challenge exists to forbid.
#
# The refusal itself is correct (an unexercised arm is unvalidated
# instrumentation); what must change is that the refusal NAMES ITS RESOLVED
# CAUSE (§11.4.201(4)(5)), exactly as the refused-port arm already does, instead
# of blaming the detector.
echo ""
echo "--- F1: re-running --self-validate under a date(1) that refuses -d ---"
REAL_DATE="$(command -v date 2>/dev/null || true)"
if [ -z "$REAL_DATE" ]; then
    echo "  SKIP: cannot resolve a real date(1) to shim (reason=tooling_absent)"
else
    SHIM_DIR="$(mktemp -d)"
    trap 'rm -f "$OUT_FILE"; rm -rf "$SHIM_DIR"' EXIT
    cat > "$SHIM_DIR/date" <<SHIMEOF
#!/usr/bin/env bash
# Masks ONLY \`date -d\` (the BSD/busybox shape); every other form passes
# through to the real binary, so \`date +%s.%N\` used elsewhere still works.
if [ "\${1:-}" = "-d" ]; then
    echo "date: invalid option -- 'd'" >&2
    exit 1
fi
exec "$REAL_DATE" "\$@"
SHIMEOF
    chmod +x "$SHIM_DIR/date"
    # prove the shim actually masks -d before drawing any conclusion from it
    if PATH="$SHIM_DIR:$PATH" date -d "Sun, 06 Nov 1994 08:49:37 GMT" +%s >/dev/null 2>&1; then
        fail "SHIM INEFFECTIVE: date -d still parses under the shim — the F1 arm proves nothing this run"
    elif ! PATH="$SHIM_DIR:$PATH" date +%s >/dev/null 2>&1; then
        fail "SHIM OVER-BROAD: the shim broke plain date(1) too — the F1 arm proves nothing this run"
    else
        pass "shim verified: date -d refused, plain date(1) still works (the arm is genuinely exercised)"
        MASK_OUT="$SHIM_DIR/masked.out"
        PATH="$SHIM_DIR:$PATH" nice -n 19 bash "$SCRIPT" --self-validate > "$MASK_OUT" 2>&1
        MASK_RC=$?
        echo "    masked-date exit status: $MASK_RC"
        grep -E "r429_baddate|r429_valid_httpdate" "$MASK_OUT" | sed 's/^/    | /'

        if grep -qF -- "detector 3: sibling responsiveness" "$MASK_OUT"; then
            pass "control needle (masked run): detector 3 ran — zero-hit results below are real absences"
        else
            fail "CONTROL NEEDLE MISSING in masked run — every zero below is uninterpretable (§11.4.201(7)(b))"
        fi

        if grep -qE "fixture 'r429_baddate': NOT EXERCISED \(reason=no_date_parser_on_host\)" "$MASK_OUT"; then
            pass "F1: the shaped-impossible-date arm reports NOT EXERCISED naming its resolved cause (no_date_parser_on_host)"
        else
            fail "F1: no honest NOT EXERCISED line for r429_baddate — the refusal does not name its resolved cause (§11.4.201(4)(5))"
        fi

        if grep -qE "\[SELF-VAL BAD\] sibling detector classified 'r429_baddate'" "$MASK_OUT"; then
            fail "F1: the detector is ACCUSED of misclassifying r429_baddate on a host where it behaved exactly as specified — a §11.4.201(1) false-positive refusal blaming the product for an instrument property"
        else
            pass "F1: the detector is NOT accused of misclassifying on a host whose date(1) cannot parse"
        fi

        # The well-formed HTTP-date arm must still be exercised and still pass:
        # structural matching alone is sufficient for a REAL date, so masking
        # date -d must not disturb it.
        if grep -qE "fixture 'r429_valid_httpdate'.*-> class=responsive" "$MASK_OUT"; then
            pass "F1: a genuinely valid HTTP-date still classifies responsive without a date(1) parser"
        else
            fail "F1: masking date -d broke the valid-HTTP-date arm — the structural fallback is not sufficient as documented"
        fi
    fi
fi

# --- MINOR-2: the control needle needs a NEGATIVE control -------------------
# HAVE_DATE_PARSE ran only an accept-valid probe, so a parser that accepts
# EVERYTHING — including the impossible date — was indistinguishable from a
# correct one. Fail-closed still held (the classifier trusted the liar,
# r429_baddate flipped to responsive, self-validation went red and the
# challenge refused to mint live verdicts) so no live bluff was possible; but
# the refusal ACCUSED THE DETECTOR when the resolved cause was the INSTRUMENT
# — the identical misattribution F1 fixed, for the opposite parser shape.
# §11.4.201(7)(b): a needle that only proves "can see a valid date" does not
# prove "can reject an invalid one".
echo ""
echo "--- MINOR-2: re-running --self-validate under a date(1) that ACCEPTS anything ---"
if [ -z "${REAL_DATE:-}" ]; then
    echo "  SKIP: no real date(1) resolved earlier (reason=tooling_absent)"
else
    LIE_DIR="$(mktemp -d)"
    trap 'rm -f "$OUT_FILE"; rm -rf "${SHIM_DIR:-}" "$LIE_DIR"' EXIT
    cat > "$LIE_DIR/date" <<LIEEOF
#!/usr/bin/env bash
# A LYING parser: every \`date -d\` succeeds with a plausible epoch, including
# for dates that do not exist. Every other form passes through untouched.
if [ "\${1:-}" = "-d" ]; then
    echo "784111777"
    exit 0
fi
exec "$REAL_DATE" "\$@"
LIEEOF
    chmod +x "$LIE_DIR/date"
    # prove the shim really lies before drawing any conclusion from it
    if ! PATH="$LIE_DIR:$PATH" date -d "Sun, 32 Nov 1994 25:99:99 GMT" +%s >/dev/null 2>&1; then
        fail "LYING SHIM INEFFECTIVE: the impossible date is still rejected — the MINOR-2 arm proves nothing this run"
    elif ! PATH="$LIE_DIR:$PATH" date +%s >/dev/null 2>&1; then
        fail "LYING SHIM OVER-BROAD: plain date(1) broke — the MINOR-2 arm proves nothing this run"
    else
        pass "lying shim verified: date -d accepts an impossible date, plain date(1) still works"
        LIE_OUT="$LIE_DIR/lie.out"
        PATH="$LIE_DIR:$PATH" nice -n 19 bash "$SCRIPT" --self-validate > "$LIE_OUT" 2>&1
        echo "    lying-date exit status: $?"
        grep -E "r429_baddate" "$LIE_OUT" | sed 's/^/    | /'

        if grep -qF -- "detector 3: sibling responsiveness" "$LIE_OUT"; then
            pass "control needle (lying run): detector 3 ran — zero-hit results below are real absences"
        else
            fail "CONTROL NEEDLE MISSING in lying run — every zero below is uninterpretable (§11.4.201(7)(b))"
        fi

        if grep -qE "fixture 'r429_baddate': NOT EXERCISED \(reason=unreliable_date_parser_on_host\)" "$LIE_OUT"; then
            pass "MINOR-2: a parser that accepts an impossible date is detected and NAMED (unreliable_date_parser_on_host)"
        else
            fail "MINOR-2: the lying parser was not detected — the needle has no negative control, so the semantic parse is trusted blind"
        fi

        if grep -qE "\[SELF-VAL BAD\] sibling detector classified 'r429_baddate'" "$LIE_OUT"; then
            fail "MINOR-2: the detector is ACCUSED of misclassifying when the resolved cause is a LYING date(1) — the same misattribution F1 fixed, opposite parser shape"
        else
            pass "MINOR-2: the detector is NOT accused when the instrument is the liar"
        fi
    fi
fi

# --- exit status is part of the contract ------------------------------------
if [ "$SV_RC" -eq 0 ]; then
    pass "self-validate exited 0"
else
    fail "self-validate exited $SV_RC (expected 0) — the challenge refuses to mint live verdicts from unvalidated instrumentation"
fi

finish
