#!/usr/bin/env bash
# pre_build_verification.sh — Pre-build gate verifying constitution inheritance
# is real and every invariant holds.
#
# Invoked by the build orchestrator before any build.
# Returns non-zero (BLOCKING) if any invariant fails.
#
# Invariants:
#   1. constitution/ directory exists
#   2. constitution/Constitution.md exists and contains the §11.4 anchor
#   3. constitution/CLAUDE.md exists and contains the Anti-Bluff covenant anchor
#   4. constitution/AGENTS.md exists and contains the Anti-bluff covenant anchor
#   5. Parent CLAUDE.md references constitution submodule
#   6. Parent AGENTS.md references constitution submodule
#   7. Parent CONSTITUTION.md references Helix Universal Constitution
#
# Constitution: §1.1 (paired mutation), §11.4 (anti-bluff covenant)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

FAIL_COUNT=0
PASS_COUNT=0

pass() {
    PASS_COUNT=$((PASS_COUNT + 1))
    echo "  PASS [$PASS_COUNT]: $1"
}

fail() {
    FAIL_COUNT=$((FAIL_COUNT + 1))
    echo "  FAIL [$FAIL_COUNT]: $1"
}

echo "=== Constitution Inheritance Verification Gate ==="
echo

# --- Invariant 1: constitution directory ---
echo "[1/7] constitution/ directory exists"
if [[ -d "${PROJECT_ROOT}/constitution" ]]; then
    pass "constitution/ exists"
else
    fail "constitution/ directory not found"
fi

# --- Invariant 2: Constitution.md anchor ---
echo "[2/7] constitution/Constitution.md §11.4 anchor"
CONSTITUTION_ANCHOR='§11.4 End-user quality guarantee'
if [[ -f "${PROJECT_ROOT}/constitution/Constitution.md" ]] && \
   grep -qF "${CONSTITUTION_ANCHOR}" "${PROJECT_ROOT}/constitution/Constitution.md"; then
    pass "Constitution.md contains §11.4 anchor"
else
    fail "Constitution.md missing §11.4 anchor"
fi

# --- Invariant 3: CLAUDE.md anchor ---
echo "[3/7] constitution/CLAUDE.md anti-bluff covenant anchor"
CLAUDE_ANCHOR='MANDATORY ANTI-BLUFF COVENANT'
if [[ -f "${PROJECT_ROOT}/constitution/CLAUDE.md" ]] && \
   grep -qF "${CLAUDE_ANCHOR}" "${PROJECT_ROOT}/constitution/CLAUDE.md"; then
    pass "CLAUDE.md contains anti-bluff covenant anchor"
else
    fail "CLAUDE.md missing anti-bluff covenant anchor"
fi

# --- Invariant 4: AGENTS.md anchor ---
echo "[4/7] constitution/AGENTS.md anti-bluff covenant anchor"
AGENTS_ANCHOR='Anti-bluff covenant'
if [[ -f "${PROJECT_ROOT}/constitution/AGENTS.md" ]] && \
   grep -qF "${AGENTS_ANCHOR}" "${PROJECT_ROOT}/constitution/AGENTS.md"; then
    pass "AGENTS.md contains anti-bluff covenant anchor"
else
    fail "AGENTS.md missing anti-bluff covenant anchor"
fi

# --- Invariant 5: Parent CLAUDE.md inheritance pointer ---
echo "[5/7] Parent CLAUDE.md inheritance pointer"
if grep -qF 'constitution/CLAUDE.md' "${PROJECT_ROOT}/CLAUDE.md"; then
    pass "CLAUDE.md references constitution submodule"
else
    fail "CLAUDE.md missing inheritance pointer to constitution"
fi

# --- Invariant 6: Parent AGENTS.md inheritance pointer ---
echo "[6/7] Parent AGENTS.md inheritance pointer"
if grep -qF 'constitution/AGENTS.md' "${PROJECT_ROOT}/AGENTS.md"; then
    pass "AGENTS.md references constitution submodule"
else
    fail "AGENTS.md missing inheritance pointer to constitution"
fi

# --- Invariant 7: Parent CONSTITUTION.md inheritance pointer ---
echo "[7/7] Parent CONSTITUTION.md inheritance pointer"
if grep -qF 'Helix Universal Constitution' "${PROJECT_ROOT}/CONSTITUTION.md"; then
    pass "CONSTITUTION.md references Helix Universal Constitution"
else
    fail "CONSTITUTION.md missing inheritance pointer to Helix Constitution"
fi

echo
echo "=== Result: ${PASS_COUNT} passed, ${FAIL_COUNT} failed ==="

if [[ "${FAIL_COUNT}" -gt 0 ]]; then
    exit 1
fi
exit 0
