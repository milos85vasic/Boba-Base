#!/usr/bin/env bash
# test_compute_badges_frontend_timeout_bound.sh — BOB-224 regression guard.
#
# BOB-224 (CRITICAL): tests/unit/test_compute_badges_carrier_match.sh HANGED
# to the FULL 300s outer timeout (rc=124) rather than completing or failing.
#
# ROOT CAUSE (captured evidence, not guessed — §11.4.102/§11.4.6):
# scripts/compute-badges.sh's count_frontend_tests() ran the frontend suite
# via:
#     out="$(cd "${frontend}" && timeout 120 "${vitest_bin}" list --run 2>&1)"
# `timeout N <cmd>` with NO `-k`/`--kill-after` sends ONLY SIGTERM at the
# deadline and then WAITS for the child to actually exit — per `timeout
# --help` itself: "It may be necessary to use the KILL signal, since this
# signal can't be caught." vitest's CLI installs its own cooperative
# `process.once("SIGTERM", onExit)` handler (vitest/dist/chunks/
# cli-api.*.js) whose JS callback can only run once Node's event loop is
# free. `vitest list --run` spends its opening phase in synchronous,
# CPU-heavy work (esbuild-transforming every *.spec.ts file); under host
# CPU/memory pressure that phase can starve the event loop well past the
# nominal 120s budget, so the "timeout" never actually terminates anything —
# the whole call chain blocks until SOME outer wrapper (a 300s test-runner
# timeout) finally SIGKILLs the entire tree. Confirmed in isolation: a Node
# script that installs a SIGTERM handler and then busy-loops synchronously
# runs to the END of its busy loop under `timeout 3 node script.js` with no
# `-k` — the 3-second budget goes completely unenforced (see Assertion 1
# below, which reproduces exactly this on THIS host/toolchain).
#
# THE FIX: `timeout -k 10 120 ...` — SIGKILL cannot be caught, blocked, or
# delayed by JS/event-loop state, so it terminates the process at the OS
# level regardless of what it is doing. This is a genuine hard bound, not a
# cooperative one, and it does NOT raise the 120s budget or skip anything.
#
# §11.4.201(7)(a)/§11.4.6: "the failure IS the duration" — this guard asserts
# completion WITHIN A BOUND, never a functional/output assertion, so a
# regression that removes the kill-escalation is caught by TIMING, not by a
# value mismatch. Assertion 2 exercises the exact fixed invocation SHAPE
# (`timeout -k <grace> <budget> <cmd>`) against the same busy-looping-but-
# SIGTERM-catching stub and proves it terminates within budget+grace+margin.
# Assertion 3 is a structural check that the actual fix landed in
# scripts/compute-badges.sh's real invocation line (§11.4.146(D3)-style:
# proves the guard covers the REAL file, not only a reimplemented copy).
#
# Deliberately does NOT invoke the real frontend/node_modules/.bin/vitest —
# its actual runtime is host-load-dependent and not reliably controllable
# from a test (that unreliability is exactly what caused BOB-224 to be
# intermittent). Instead this reproduces the general mechanism class
# directly and verifiably, then checks the real fix is wired to it.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${HERE}/../.." && pwd)"
COMPUTE_BADGES="${PROJECT_ROOT}/scripts/compute-badges.sh"

PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); echo "  PASS: $1"; }
fail() { FAIL=$((FAIL+1)); echo "  FAIL: $1"; }

finish() {
    echo "RESULT: $PASS passed, $FAIL failed"
    [ "$FAIL" -eq 0 ] || exit 1
    exit 0
}

TMPDIR_T="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_T"' EXIT

# A minimal stand-in for vitest's own documented behaviour: install a
# SIGTERM handler (so the signal CAN be received) but spend BUDGET_MS
# synchronously busy-looping first (so the handler's callback cannot run
# until that loop returns control to the event loop) — the exact shape
# vitest's cli-api.js SIGTERM handling + esbuild's synchronous transform
# phase produce under host load.
STUB="${TMPDIR_T}/sigterm_busy_stub.js"
cat > "$STUB" <<'JS'
const budgetMs = parseInt(process.argv[2] || "3000", 10);
process.once('SIGTERM', () => { process.exit(1); });
const start = Date.now();
while (Date.now() - start < budgetMs) { /* synchronous, non-yielding */ }
process.exit(0);
JS

if ! command -v node >/dev/null 2>&1; then
    fail "node not found on PATH — cannot exercise the timeout-enforcement mechanism"
    finish
fi
if ! command -v timeout >/dev/null 2>&1; then
    fail "timeout not found on PATH — cannot exercise the timeout-enforcement mechanism"
    finish
fi

# ── Assertion 1 (RED — proves the vulnerability class is REAL on this host) ──
# `timeout <budget> <stub busy-looping for LOOP_MS>` with NO -k, where
# LOOP_MS > budget. If `timeout` enforced a hard bound this would return
# at ~budget; the pre-fix shape used in compute-badges.sh instead lets the
# process run to the end of its synchronous work.
BUDGET_S=2
LOOP_MS=6000
START_NS="$(date +%s%N)"
timeout "${BUDGET_S}" node "$STUB" "$LOOP_MS" >/dev/null 2>&1
END_NS="$(date +%s%N)"
ELAPSED_MS=$(( (END_NS - START_NS) / 1000000 ))
# Genuine hard bound would land near BUDGET_S*1000 (a couple hundred ms of
# slack for process startup). Observing the process run substantially past
# its budget PROVES bare `timeout` (no -k) does not enforce one here.
if [ "$ELAPSED_MS" -gt $((BUDGET_S * 1000 + 1000)) ]; then
    pass "vulnerability class reproduced: bare 'timeout ${BUDGET_S}s' (no -k) let a SIGTERM-catching busy loop run for ${ELAPSED_MS}ms (budget was ${BUDGET_S}000ms) — confirms BOB-224's wedge is real on this host/toolchain"
else
    fail "expected bare 'timeout' (no -k) to overrun its budget on a busy-looping SIGTERM-catcher (observed ${ELAPSED_MS}ms vs ${BUDGET_S}000ms budget) — the vulnerability precondition did not reproduce, cannot certify the fix against it"
fi

# ── Assertion 2 (GREEN — proves the FIX shape genuinely bounds execution) ──
# The exact invocation shape landed in scripts/compute-badges.sh:
# `timeout -k <grace> <budget> <cmd>`. SIGKILL must terminate the process
# even though it is busy-looping and cannot service SIGTERM promptly.
GRACE_S=2
START_NS="$(date +%s%N)"
timeout -k "${GRACE_S}" "${BUDGET_S}" node "$STUB" "$LOOP_MS" >/dev/null 2>&1
RC=$?
END_NS="$(date +%s%N)"
ELAPSED_MS=$(( (END_NS - START_NS) / 1000000 ))
MAX_ALLOWED_MS=$(( (BUDGET_S + GRACE_S) * 1000 + 1500 ))
if [ "$ELAPSED_MS" -le "$MAX_ALLOWED_MS" ]; then
    pass "fix shape enforces a hard bound: 'timeout -k ${GRACE_S} ${BUDGET_S}' killed the same busy-looping SIGTERM-catcher within ${ELAPSED_MS}ms (allowed <= ${MAX_ALLOWED_MS}ms; loop alone would have taken ${LOOP_MS}ms)"
else
    fail "fix shape did NOT bound execution: 'timeout -k ${GRACE_S} ${BUDGET_S}' took ${ELAPSED_MS}ms (allowed <= ${MAX_ALLOWED_MS}ms) — the wedge is NOT closed"
fi
if [ "$RC" -eq 124 ] || [ "$RC" -eq 137 ]; then
    pass "timeout -k reported a timeout/kill exit status (rc=$RC) rather than a clean process exit"
else
    fail "expected rc 124 (timed out) or 137 (killed) from the -k escalation path, got rc=$RC"
fi

# ── Assertion 3 (structural — the REAL fix is wired into the REAL script) ──
# §11.4.201(11): don't just prove the mechanism in the abstract — prove
# scripts/compute-badges.sh's actual vitest invocation carries the fix.
if [ ! -f "$COMPUTE_BADGES" ]; then
    fail "scripts/compute-badges.sh not found"
elif grep -qE 'timeout[[:space:]]+-k[[:space:]]+[0-9]+[[:space:]]+120[[:space:]]+"\$\{vitest_bin\}"[[:space:]]+list[[:space:]]+--run' "$COMPUTE_BADGES"; then
    pass "scripts/compute-badges.sh's vitest invocation carries a -k/--kill-after hard-bound escalation"
else
    fail "scripts/compute-badges.sh's 'timeout 120 \${vitest_bin} list --run' invocation is missing a -k/--kill-after escalation — BOB-224's wedge is unfixed in the real script"
fi

finish
