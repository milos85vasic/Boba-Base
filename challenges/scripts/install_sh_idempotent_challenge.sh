#!/bin/bash
# install_sh_idempotent_challenge.sh — proves scripts/install.sh is
# idempotent (safe to re-run) AND leaves the stack healthy after
# each invocation. Uses skip flags to keep the run bounded (~60-90s)
# even in the busy state; the full-build path is exercised separately
# by a manual `bash scripts/install.sh` from the operator.
#
# What this proves:
#   1. install.sh exists + is executable + parses (bash -n)
#   2. Two consecutive runs both exit 0 (idempotent)
#   3. After each run, boba-svc health returns 0 (all endpoints green)
#
# SKIPs (§11.4.3):
#   - Non-Linux
#   - install.sh missing
#
# Exit: 0 = all PASS, 1 = FAIL, 2 = invocation error.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

if [[ "$(uname -s)" != "Linux" ]]; then
    echo "=== install_sh_idempotent_challenge ==="
    echo "SKIP: Linux-only (uname=$(uname -s))"
    exit 0
fi
if [ ! -x scripts/install.sh ]; then
    echo "=== install_sh_idempotent_challenge ==="
    echo "SKIP: scripts/install.sh missing or not executable"
    exit 0
fi

echo "=== install_sh_idempotent_challenge ==="

PASS_COUNT=0
FAIL_COUNT=0
declare -a FAIL_DETAILS=()

assert_pass() { echo "PASS: $*"; PASS_COUNT=$((PASS_COUNT + 1)); }
assert_fail() { echo "FAIL: $*"; FAIL_COUNT=$((FAIL_COUNT + 1)); FAIL_DETAILS+=("$*"); }

# ─── Check 1: syntax ──────────────────────────────────────────────
if bash -n scripts/install.sh 2>/dev/null; then
    assert_pass "scripts/install.sh syntax clean (bash -n)"
else
    assert_fail "scripts/install.sh syntax error — bash -n exited non-zero"
    # If parsing fails, further runs are pointless.
    echo "Total: PASS=$PASS_COUNT FAIL=$FAIL_COUNT"
    exit 1
fi

# ─── Check 2: first bounded run (skip pull+build, exercises install
#             + start + health path) ───────────────────────────────
LOG1="$(mktemp -t install-run-1.XXXXXX)"
if BOBA_INSTALL_SKIP_PULL=1 BOBA_INSTALL_SKIP_BUILD=1 timeout 240 \
   bash scripts/install.sh >"$LOG1" 2>&1; then
    assert_pass "install.sh run #1 exit=0 (skip-pull, skip-build)"
else
    rc=$?
    assert_fail "install.sh run #1 exit=$rc — see $LOG1 for details (last 20 lines below)"
    tail -20 "$LOG1" | sed 's/^/    /'
fi

# ─── Check 3: after run #1, health reports all green ──────────────
if bash scripts/boba-svc.sh health >/dev/null 2>&1; then
    assert_pass "post-run-#1 health probe all GREEN"
else
    assert_fail "post-run-#1 health probe reported FAILs"
    bash scripts/boba-svc.sh health 2>&1 | sed 's/^/    /'
fi

# ─── Check 4: second bounded run (idempotency) ────────────────────
LOG2="$(mktemp -t install-run-2.XXXXXX)"
if BOBA_INSTALL_SKIP_PULL=1 BOBA_INSTALL_SKIP_BUILD=1 timeout 240 \
   bash scripts/install.sh >"$LOG2" 2>&1; then
    assert_pass "install.sh run #2 exit=0 — idempotent"
else
    rc=$?
    assert_fail "install.sh run #2 exit=$rc — non-idempotent (see $LOG2)"
    tail -20 "$LOG2" | sed 's/^/    /'
fi

# ─── Check 5: post-run-#2 health still green ──────────────────────
if bash scripts/boba-svc.sh health >/dev/null 2>&1; then
    assert_pass "post-run-#2 health probe all GREEN (stack survived re-install)"
else
    assert_fail "post-run-#2 health probe reported FAILs"
    bash scripts/boba-svc.sh health 2>&1 | sed 's/^/    /'
fi

# Tidy logs on success
[ "$FAIL_COUNT" -eq 0 ] && rm -f "$LOG1" "$LOG2"

echo "─────────────────────────────────────────────────────────────────"
echo "Total: PASS=$PASS_COUNT FAIL=$FAIL_COUNT"
if [ "$FAIL_COUNT" -gt 0 ]; then
    for line in "${FAIL_DETAILS[@]}"; do echo "  - $line"; done
    exit 1
fi
exit 0
