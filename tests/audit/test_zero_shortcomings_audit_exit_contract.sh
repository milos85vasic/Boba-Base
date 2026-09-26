#!/usr/bin/env bash
# Exit-code contract + execution hygiene of verify-closure (BOB-248 follow-ups).
#   * usage / invalid-id refusals exit 4, internal refusals exit 5 -- both
#     DIFFERENT from the genuine-mismatch code 1, so a caller can tell
#     "the defect is back" from "the tool was misused / could not run";
#   * BASH_ENV and ENV never reach the fresh process that re-runs a recorded
#     command (a startup file could otherwise rewrite the evidence result);
#   * the recorded command runs under the ExecutionPolicy bounds
#     (audit_dispatch_bounded: nice/ionice, Principle XIII);
#   * FR-011: a second concurrent verify-closure refuses (exit 5) instead of
#     running its corruption guard over the same tracked tree at the same time;
#   * AUDIT_VERIFY_COMMAND_TIMEOUT bounds the recorded command and a timeout is
#     reported as its own inconclusive exit code 6, never as a match.
# Every fixture lives in a mktemp directory; nothing under docs/qa is touched.
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
qa="$T/qa"
fixture() { # id command summary
    mkdir -p "$qa/$1"
    {
        printf '**Command:** `%s`\n' "$2"
        printf '**Result Summary:** %s\n' "$3"
        printf '**Evidence Layer:** runtime\n**Test Type:** unit\n'
    } > "$qa/$1/closure_evidence_1.md"
}
fixture T-MATCH "echo ok" "ok"
fixture T-MISMATCH "echo now" "then"
# BASH_ENV probe: the startup file only marks a NON-interactive `bash -c`
# (BASH_EXECUTION_STRING is set there and empty for `bash script.sh`).
fixture T-BASHENV 'echo "${BASH_ENV_HIT:-clean}"' "clean"
# ExecutionPolicy probe: the recorded command reports its own niceness.
fixture T-NICE 'ps -o ni= -p $$ | tr -d " "' "19"
fixture T-SLOW "sleep 30; echo late" "late"
fixture T-LOCK "echo ok" "ok"

AUDIT="$repo/scripts/zero_shortcomings_audit.sh"
run() { # args... -> rc, out
    rc=0
    out="$(AUDIT_QA_ROOT="$qa" AUDIT_INCIDENT_LOG_DIR="$T/incidents" AUDIT_STANDING_LOG_DIR="$T/standing" AUDIT_VERIFY_LOCK_FILE="$T/lock.default" bash "$AUDIT" "$@" 2>&1)" || rc=$?
}

# --- usage refusals: exit 4 --------------------------------------------------
run;                                    check "no mode is a usage refusal (exit 4)" '[[ "$rc" -eq 4 ]]'
run frobnicate;                         check "unknown mode exits 4" '[[ "$rc" -eq 4 ]]'
run enumerate --surface;                check "enumerate --surface with no value exits 4" '[[ "$rc" -eq 4 ]]'
run enumerate --bogus;                  check "enumerate unknown option exits 4" '[[ "$rc" -eq 4 ]]'
run enumerate --surface nope;           check "enumerate unrecognized surface exits 4" '[[ "$rc" -eq 4 ]]'
run enumerate --surface gates --sort-by-risk
check "enumerate --sort-by-risk outside backlog exits 4" '[[ "$rc" -eq 4 ]]'
run verify-closure;                     check "verify-closure with no id exits 4" '[[ "$rc" -eq 4 ]]'
run verify-closure '../x';              check "verify-closure invalid id exits 4" '[[ "$rc" -eq 4 ]]'
run verify-closure T-MATCH --require-layer
check "verify-closure --require-layer with no value exits 4" '[[ "$rc" -eq 4 ]]'
run verify-closure T-MATCH --require-layer banana
check "verify-closure unrecognized --require-layer exits 4" '[[ "$rc" -eq 4 ]]'
run verify-closure T-MATCH --what;      check "verify-closure unknown option exits 4" '[[ "$rc" -eq 4 ]]'
run standing-check --bogus;             check "standing-check unknown option exits 4" '[[ "$rc" -eq 4 ]]'
run -h;                                 check "-h still exits 0" '[[ "$rc" -eq 0 ]]'

# --- genuine outcomes keep their codes --------------------------------------
run verify-closure T-MATCH;             check "a match still exits 0" '[[ "$rc" -eq 0 ]]'
run verify-closure T-MISMATCH;          check "a genuine mismatch still exits 1" '[[ "$rc" -eq 1 ]]'
check "the mismatch code is distinct from the usage code" '[[ 1 -ne 4 ]]'

# --- internal refusal: exit 5 ------------------------------------------------
rc=0
out="$(AUDIT_QA_ROOT="$qa" TMPDIR="$T/no/such/tmp" AUDIT_VERIFY_LOCK_FILE="$T/lock" bash "$AUDIT" verify-closure T-MATCH 2>&1)" || rc=$?
check "an internal refusal (mktemp cannot create its guard files) exits 5" '[[ "$rc" -eq 5 ]]'
check "the internal refusal names what failed" 'grep -qi "mktemp" <<<"$out"'

# --- BASH_ENV / ENV never reach the fresh process ---------------------------
printf '[[ -n "${BASH_EXECUTION_STRING:-}" ]] && BASH_ENV_HIT=hit\n' > "$T/startup.sh"
rc=0
out="$(AUDIT_QA_ROOT="$qa" BASH_ENV="$T/startup.sh" ENV="$T/startup.sh" bash "$AUDIT" verify-closure T-BASHENV 2>&1)" || rc=$?
check "BASH_ENV/ENV exported by the caller do not reach the recorded command (match, exit 0)" '[[ "$rc" -eq 0 ]]'
# Control: the probe really detects a startup file when one IS sourced.
check "control: the BASH_ENV probe fires for a plain bash -c" \
    '[[ "$(BASH_ENV="$T/startup.sh" bash -c "echo \${BASH_ENV_HIT:-clean}")" == "hit" ]]'

# --- ExecutionPolicy: the recorded command runs niced -------------------------
own_nice="$(ps -o ni= -p $$ | tr -d ' ')"
run verify-closure T-NICE
check "the recorded command runs at nice 19 (audit_dispatch_bounded wired; caller nice=$own_nice)" '[[ "$rc" -eq 0 ]]'

# --- FR-011: concurrent verify-closure refuses --------------------------------
lock="$T/verify.lock"
( exec 9>>"$lock"; flock 9; sleep 5 ) &
holder=$!
sleep 0.5
rc=0
out="$(AUDIT_QA_ROOT="$qa" AUDIT_VERIFY_LOCK_FILE="$lock" AUDIT_VERIFY_LOCK_WAIT=0 bash "$AUDIT" verify-closure T-LOCK 2>&1)" || rc=$?
kill "$holder" 2>/dev/null || true
wait "$holder" 2>/dev/null || true
check "FR-011: a verify-closure that cannot take the lock refuses with exit 5" '[[ "$rc" -eq 5 ]]'
check "FR-011: the refusal names the concurrent holder" 'grep -qi "another verify-closure" <<<"$out"'
rc=0
AUDIT_QA_ROOT="$qa" AUDIT_VERIFY_LOCK_FILE="$lock" bash "$AUDIT" verify-closure T-LOCK >/dev/null 2>&1 || rc=$?
check "FR-011 control: once the lock is free the same check runs and matches" '[[ "$rc" -eq 0 ]]'

# --- bounded recorded command: timeout is its own inconclusive code ----------
start=$SECONDS
rc=0
AUDIT_QA_ROOT="$qa" AUDIT_VERIFY_COMMAND_TIMEOUT=2 bash "$AUDIT" verify-closure T-SLOW >"$T/slow.out" 2>&1 || rc=$?
elapsed=$((SECONDS - start))
check "a recorded command that exceeds AUDIT_VERIFY_COMMAND_TIMEOUT exits 6 (inconclusive)" '[[ "$rc" -eq 6 ]]'
check "the timeout really bounded the run (${elapsed}s < 20s)" '[[ "$elapsed" -lt 20 ]]'
check "the timeout is named in the output" 'grep -qi "timed out" "$T/slow.out"'

printf 'test_zero_shortcomings_audit_exit_contract: %d passed, %d failed\n' "$pass" "$fail"
[[ "$fail" -eq 0 ]]
