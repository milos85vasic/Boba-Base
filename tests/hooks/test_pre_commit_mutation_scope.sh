#!/usr/bin/env bash
# test_pre_commit_mutation_scope.sh — Hermetic executing test for BOB-245's
# scope-restriction fix to scripts/git_hooks/pre-commit (the §11.4.75
# mutation-marker guard).
#
# ROOT CAUSE (BOB-245): the hook naively grepped EVERY staged file for the
# literal "MUTATED" marker (and two siblings) with zero ability to
# distinguish a genuine leftover mutation-test artifact in shipped
# production code from legitimate PROSE in docs/QA-evidence files, or
# legitimate COMMENTS in test sources, correctly and intentionally
# describing this project's own MANDATORY §1.1 paired-mutation-testing
# methodology. Confirmed real false positives that blocked an otherwise-
# clean commit this session:
#   docs/qa/BOB-187/closure_evidence_20260925.md (+ .html twin)
#   docs/qa/BOB-196/closure_evidence_20260925.md (+ .html twin)
#   tests/unit/test_ownership_precondition.sh
#
# FIX: the hook now restricts its scan to first-party PRODUCTION source
# roots (download-proxy, qBitTorrent-go, scripts, plugins,
# webui-bridge.py) of a scannable type (*.sh|*.bash|*.py|*.go), and
# explicitly excludes tests/, docs/, qa-results/, scratchpad/,
# constitution/, submodules/, challenges/, mutants/ and vendored/build-
# output directories — the same technique as the sibling gate
# scripts/pre_build/check_cm_no_production_mutation_residue.sh.
#
# This test drives the REAL invocation path (§11.4.224(A) — not a
# `bash -n` parse-check alone) against a hermetic throwaway git repo under
# mktemp -d, never against the real project repo.
#
# §1.1 — Paired meta-test mutation: comment out the
# `_pc_is_production_path "$file" || continue` scope-gate line in
# scripts/git_hooks/pre-commit (restoring the pre-fix unscoped behaviour)
# -> Test 1 below (the RED-then-GREEN false-positive case) FAILs because
# the hook again blocks the non-production fixture -> restore the line ->
# re-assert GREEN. Proven manually during authoring.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${HERE}/../.." && pwd)"
HOOK_SOURCE="${PROJECT_ROOT}/scripts/git_hooks/pre-commit"

PASS_COUNT=0
FAIL_COUNT=0
pass() { PASS_COUNT=$((PASS_COUNT + 1)); echo "  PASS: $1"; }
fail() { FAIL_COUNT=$((FAIL_COUNT + 1)); echo "  FAIL: $1"; }

if [[ ! -f "${HOOK_SOURCE}" ]]; then
    echo "FATAL: hook source missing at ${HOOK_SOURCE}" >&2
    exit 2
fi

# --- 0: bash -n parse sanity (necessary, never sufficient per §11.4.224(A)) ---
if bash -n "${HOOK_SOURCE}"; then
    pass "hook source is syntactically valid bash"
else
    fail "hook source fails bash -n"
fi

# --- Hermetic throwaway git repo under mktemp -d ---
TMPREPO="$(mktemp -d)"
_cleanup_tmprepo() { rm -rf "${TMPREPO}" 2>/dev/null || true; }
trap _cleanup_tmprepo EXIT

git -C "${TMPREPO}" init -q -b main
git -C "${TMPREPO}" config user.email "test@example.invalid"
git -C "${TMPREPO}" config user.name "test"
mkdir -p "${TMPREPO}/docs/qa/FIXTURE" "${TMPREPO}/tests/unit" "${TMPREPO}/scripts"
git -C "${TMPREPO}" commit -q --allow-empty -m "root: seed"

# Build the two marker-substring tokens indirectly so THIS test file never
# literally contains them either (same self-avoidance discipline as the
# hook and the sibling gate it mirrors).
T_MUT="MUT""ATED"
T_UNMUT="UN""${T_MUT}"

# --- Test 1: RED-then-GREEN — legitimate prose under a NON-production
#     path (docs/) containing the literal marker MUST now PASS (exit 0).
#     This is the fix under test. ---
FIXTURE_DOC="${TMPREPO}/docs/qa/FIXTURE/closure_evidence.md"
{
    echo "# Fixture closure evidence"
    echo ""
    echo "GREEN on the ${T_UNMUT} sandbox copy, RED on the ${T_MUT} sandbox copy,"
    echo "confirming the fix reproduces the reported defect and restores it."
} > "${FIXTURE_DOC}"

# Sanity: confirm the fixture genuinely contains the raw marker literal
# (i.e. this test is exercising a real hit, not an empty file).
if grep -qF "${T_MUT}" "${FIXTURE_DOC}"; then
    pass "fixture doc genuinely contains the literal marker (test is non-trivial)"
else
    fail "fixture doc setup failed to embed the literal marker — test would be vacuous"
fi

( cd "${TMPREPO}" && git add "docs/qa/FIXTURE/closure_evidence.md" )
DOC_EXIT=0
DOC_OUT="$(cd "${TMPREPO}" && bash "${HOOK_SOURCE}" 2>&1)" || DOC_EXIT=$?
if [[ "${DOC_EXIT}" -eq 0 ]]; then
    pass "staged docs/ file containing the literal marker in legitimate prose: hook now exits 0 (RED-then-GREEN: this is the fix)"
else
    fail "staged docs/ file containing the literal marker in legitimate prose: hook exited ${DOC_EXIT} (expected 0) — output: ${DOC_OUT}"
fi
( cd "${TMPREPO}" && git restore --staged "docs/qa/FIXTURE/closure_evidence.md" )

# --- Test 1b: same false-positive class under tests/ (comments in a test
#     source describing the paired-mutation methodology) also PASSes. ---
FIXTURE_TEST="${TMPREPO}/tests/unit/test_fixture.sh"
{
    echo "#!/usr/bin/env bash"
    echo "# GREEN on the ${T_UNMUT} sandbox copy"
    echo "# RED on the ${T_MUT} sandbox copy, a FRESH escape target"
    echo "exit 0"
} > "${FIXTURE_TEST}"
( cd "${TMPREPO}" && git add "tests/unit/test_fixture.sh" )
TEST_EXIT=0
TEST_OUT="$(cd "${TMPREPO}" && bash "${HOOK_SOURCE}" 2>&1)" || TEST_EXIT=$?
if [[ "${TEST_EXIT}" -eq 0 ]]; then
    pass "staged tests/ file with legitimate mutation-methodology comments: hook exits 0"
else
    fail "staged tests/ file with legitimate mutation-methodology comments: hook exited ${TEST_EXIT} (expected 0) — output: ${TEST_OUT}"
fi
( cd "${TMPREPO}" && git restore --staged "tests/unit/test_fixture.sh" )

# --- Test 2: NEGATIVE CONTROL — a genuine mutation-residue-shaped marker
#     staged under a PRODUCTION path (scripts/) MUST STILL FAIL (exit 1).
#     Proves the fix is a genuine scope-narrowing, not a disable. ---
FIXTURE_PROD="${TMPREPO}/scripts/fixture_prod.sh"
{
    echo "#!/usr/bin/env bash"
    echo "# ${T_MUT} for §1.1 RED — leftover residue, should never ship"
    echo "echo hello"
} > "${FIXTURE_PROD}"
( cd "${TMPREPO}" && git add "scripts/fixture_prod.sh" )
PROD_EXIT=0
PROD_OUT="$(cd "${TMPREPO}" && bash "${HOOK_SOURCE}" 2>&1)" || PROD_EXIT=$?
if [[ "${PROD_EXIT}" -eq 1 ]]; then
    pass "staged scripts/ file with a genuine residue-shaped marker: hook STILL exits 1 (negative control — real detection preserved)"
else
    fail "staged scripts/ file with a genuine residue-shaped marker: hook exited ${PROD_EXIT} (expected 1) — output: ${PROD_OUT}"
fi
if echo "${PROD_OUT}" | grep -q "fixture_prod.sh"; then
    pass "refusal output names the offending production file"
else
    fail "refusal output did not name the offending production file: ${PROD_OUT}"
fi
( cd "${TMPREPO}" && git restore --staged "scripts/fixture_prod.sh" )

# --- Test 3: a clean commit with no markers anywhere exits 0. ---
CLEAN_FILE="${TMPREPO}/scripts/fixture_clean.sh"
{
    echo "#!/usr/bin/env bash"
    echo "echo 'nothing to see here'"
} > "${CLEAN_FILE}"
( cd "${TMPREPO}" && git add "scripts/fixture_clean.sh" )
CLEAN_EXIT=0
CLEAN_OUT="$(cd "${TMPREPO}" && bash "${HOOK_SOURCE}" 2>&1)" || CLEAN_EXIT=$?
if [[ "${CLEAN_EXIT}" -eq 0 ]]; then
    pass "staged clean file with no markers: hook exits 0"
else
    fail "staged clean file with no markers: hook exited ${CLEAN_EXIT} (expected 0) — output: ${CLEAN_OUT}"
fi
( cd "${TMPREPO}" && git restore --staged "scripts/fixture_clean.sh" )

echo
echo "=== Result: ${PASS_COUNT} passed, ${FAIL_COUNT} failed ==="
if [[ "${FAIL_COUNT}" -gt 0 ]]; then
    exit 1
fi
exit 0
