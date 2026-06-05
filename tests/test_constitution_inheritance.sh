#!/usr/bin/env bash
# test_constitution_inheritance.sh — Comprehensive host-side test that
# asserts ALL constitution inheritance invariants, including the
# anti-bluff meta-test mutation.
#
# This test is the authoritative "is the constitution wired in?" check.
# It MUST be run before any release tag per §11.4.40.
#
# Constitution: §1.1, §11.4, §11.4.35

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

echo "=== Constitution Inheritance Test Suite ==="
echo

# =========================================================================
# SECTION 1 — Submodule existence
# =========================================================================
echo "--- Section 1: Submodule existence ---"

if [[ -d "${PROJECT_ROOT}/constitution/.git" ]] || [[ -f "${PROJECT_ROOT}/constitution/.git" ]]; then
    pass "constitution submodule is initialized (.git exists)"
else
    fail "constitution submodule not initialized"
fi

if [[ -f "${PROJECT_ROOT}/.gitmodules" ]] && \
   grep -q 'constitution' "${PROJECT_ROOT}/.gitmodules"; then
    pass ".gitmodules references constitution submodule"
else
    fail ".gitmodules missing constitution entry"
fi

# =========================================================================
# SECTION 2 — Core constitution files (all 6 required paths per Step 1)
# =========================================================================
echo "--- Section 2: Core constitution files ---"

REQUIRED_PATHS=(
    "constitution/Constitution.md"
    "constitution/CLAUDE.md"
    "constitution/AGENTS.md"
    "constitution/install_upstreams.sh"
    "constitution/find_constitution.sh"
    "constitution/meta_test_inheritance.sh"
)

for path in "${REQUIRED_PATHS[@]}"; do
    if [[ -f "${PROJECT_ROOT}/${path}" ]]; then
        pass "Required file exists: ${path}"
    else
        fail "Required file missing: ${path}"
    fi
done

# =========================================================================
# SECTION 3 — Upstreams directory
# =========================================================================
echo "--- Section 3: Upstreams ---"

if [[ -d "${PROJECT_ROOT}/constitution/upstreams" ]]; then
    pass "constitution/upstreams/ directory exists (lowercase, §11.4.29)"
else
    fail "constitution/upstreams/ directory missing"
fi

# Check we have at least 4 upstream files (GitHub, GitLab, GitFlic, GitVerse)
UPSTREAM_COUNT=$(ls "${PROJECT_ROOT}/constitution/upstreams/"*.sh 2>/dev/null | wc -l)
if [[ "${UPSTREAM_COUNT}" -ge 4 ]]; then
    pass "At least 4 upstream declarations found (found ${UPSTREAM_COUNT})"
else
    fail "Expected ≥4 upstream declarations, found ${UPSTREAM_COUNT}"
fi

# =========================================================================
# SECTION 4 — Anchor verification
# =========================================================================
echo "--- Section 4: Constitution anchors ---"

CONSTITUTION_ANCHOR='§11.4 End-user quality guarantee — forensic anchor'
if grep -qF "${CONSTITUTION_ANCHOR}" "${PROJECT_ROOT}/constitution/Constitution.md"; then
    pass "Constitution.md §11.4 anchor found"
else
    fail "Constitution.md §11.4 anchor missing"
fi

CLAUDE_ANCHOR='MANDATORY ANTI-BLUFF COVENANT'
if grep -qF "${CLAUDE_ANCHOR}" "${PROJECT_ROOT}/constitution/CLAUDE.md"; then
    pass "CLAUDE.md anti-bluff covenant anchor found"
else
    fail "CLAUDE.md anti-bluff covenant anchor missing"
fi

AGENTS_ANCHOR='Anti-bluff covenant'
if grep -qF "${AGENTS_ANCHOR}" "${PROJECT_ROOT}/constitution/AGENTS.md"; then
    pass "AGENTS.md anti-bluff covenant anchor found"
else
    fail "AGENTS.md anti-bluff covenant anchor missing"
fi

# =========================================================================
# SECTION 5 — Parent project inheritance pointers
# =========================================================================
echo "--- Section 5: Inheritance pointers ---"

if grep -qF 'INHERITED FROM constitution/CLAUDE.md' "${PROJECT_ROOT}/CLAUDE.md"; then
    pass "CLAUDE.md inheritance pointer present"
else
    fail "CLAUDE.md inheritance pointer missing"
fi

if grep -qF 'constitution/AGENTS.md' "${PROJECT_ROOT}/AGENTS.md"; then
    pass "AGENTS.md inheritance pointer present"
else
    fail "AGENTS.md inheritance pointer missing"
fi

if grep -qF 'Helix Universal Constitution' "${PROJECT_ROOT}/CONSTITUTION.md"; then
    pass "CONSTITUTION.md inheritance pointer present"
else
    fail "CONSTITUTION.md inheritance pointer missing"
fi

# =========================================================================
# SECTION 6 — Pre-build gate itself is wired
# =========================================================================
echo "--- Section 6: Pre-build gate ---"

if [[ -x "${PROJECT_ROOT}/scripts/pre_build_verification.sh" ]]; then
    pass "scripts/pre_build_verification.sh is executable"
else
    fail "scripts/pre_build_verification.sh not found or not executable"
fi

# Run the gate and capture its output
echo "  Running pre_build_verification.sh..."
GATE_OUTPUT=$("${PROJECT_ROOT}/scripts/pre_build_verification.sh" 2>&1) && GATE_RC=$? || GATE_RC=$?
if [[ "${GATE_RC}" -eq 0 ]]; then
    pass "pre_build_verification.sh returns 0 (all invariants hold)"
else
    fail "pre_build_verification.sh returned ${GATE_RC}"
    echo "  Gate output:"
    echo "${GATE_OUTPUT}" | sed 's/^/    /'
fi

# =========================================================================
# SECTION 7 — Anti-bluff meta-test mutation (§1.1)
# =========================================================================
echo "--- Section 7: Anti-bluff meta-test mutation (§1.1) ---"

# Mutation 1: Strip §11.4 anchor from Constitution.md → gate must FAIL
echo "  Mutation 1: Strip §11.4 anchor from Constitution.md"
MUTATION_TARGET="${PROJECT_ROOT}/constitution/Constitution.md"
MUTATION_ANCHOR='§11.4 End-user quality guarantee — forensic anchor'
MUTATION_BACKUP=$(mktemp)
cp "${MUTATION_TARGET}" "${MUTATION_BACKUP}"

# Perform the mutation
sed -i '' "s/${MUTATION_ANCHOR}/MUTATED_OUT/g" "${MUTATION_TARGET}" 2>/dev/null || \
sed -i "s/${MUTATION_ANCHOR}/MUTATED_OUT/g" "${MUTATION_TARGET}"

# Run the gate — it MUST FAIL
set +e
"${PROJECT_ROOT}/scripts/pre_build_verification.sh" > /dev/null 2>&1
MUTATION_RC=$?
set -e

# Restore
cp "${MUTATION_BACKUP}" "${MUTATION_TARGET}"
rm -f "${MUTATION_BACKUP}"

if [[ "${MUTATION_RC}" -ne 0 ]]; then
    pass "Mutation §11.4: gate correctly FAILed (rc=${MUTATION_RC})"
else
    fail "Mutation §11.4: gate returned 0 — BLUFF GATE!"
    echo "  The gate did not detect that §11.4 anchor was removed."
fi

# Mutation 2: Remove inheritance pointer from CLAUDE.md → gate must FAIL
echo "  Mutation 2: Strip inheritance pointer from CLAUDE.md"
CLAUDE_INHERITANCE_HEADER='## INHERITED FROM constitution/CLAUDE.md'
CLAUDE_BACKUP=$(mktemp)
cp "${PROJECT_ROOT}/CLAUDE.md" "${CLAUDE_BACKUP}"

# Remove the inheritance block
grep -vF "${CLAUDE_INHERITANCE_HEADER}" "${PROJECT_ROOT}/CLAUDE.md" > "${CLAUDE_BACKUP}.stripped"
# Also remove the following lines that are part of the inheritance block
grep -vF 'constitution/CLAUDE.md' "${CLAUDE_BACKUP}.stripped" > "${PROJECT_ROOT}/CLAUDE.md"

set +e
"${PROJECT_ROOT}/scripts/pre_build_verification.sh" > /dev/null 2>&1
MUTATION2_RC=$?
set -e

# Restore
cp "${CLAUDE_BACKUP}" "${PROJECT_ROOT}/CLAUDE.md"
rm -f "${CLAUDE_BACKUP}" "${CLAUDE_BACKUP}.stripped"

if [[ "${MUTATION2_RC}" -ne 0 ]]; then
    pass "Mutation CLAUDE.md: gate correctly FAILed (rc=${MUTATION2_RC})"
else
    fail "Mutation CLAUDE.md: gate returned 0 — BLUFF GATE!"
fi

# =========================================================================
# SECTION 8 — Submodule upstream configuration
# =========================================================================
echo "--- Section 8: Submodule upstream remotes ---"

cd "${PROJECT_ROOT}/constitution"
REMOTE_COUNT=$(git remote | wc -l | tr -d ' ')
echo "  Constitution submodule has ${REMOTE_COUNT} remote(s)"

# Check origin has push URLs configured (multi-upstream fan-out)
PUSH_URL_COUNT=$(git remote get-url --push --all origin 2>/dev/null | wc -l | tr -d ' ')
if [[ "${PUSH_URL_COUNT}" -ge 4 ]]; then
    pass "origin has ${PUSH_URL_COUNT} push URLs (multi-upstream fan-out)"
else
    fail "origin has only ${PUSH_URL_COUNT} push URLs (expected ≥4)"
fi
cd "${PROJECT_ROOT}"

# =========================================================================
# Final result
# =========================================================================
echo
echo "=== Result: ${PASS_COUNT} passed, ${FAIL_COUNT} failed ==="

if [[ "${FAIL_COUNT}" -gt 0 ]]; then
    exit 1
fi
exit 0
