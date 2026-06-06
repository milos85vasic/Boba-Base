#!/usr/bin/env bash
# test_export_sync_gate.sh — Hermetic paired-mutation test for the
# CM-MARKDOWN-EXPORT-SYNC gate (invariant 16 of pre_build_verification.sh),
# enforcing §11.4.65 (universal Markdown export sync).
#
# §1.1 paired mutation: the gate must PASS on the clean tree, and FAIL when an
# in-scope governance/tracker doc's .html sibling is backdated (touch -t to an
# older mtime than the .md). The mutation proves the gate has teeth; the
# original mtime is always restored via a trap, even on early exit.
#
# This test drives the REAL pre_build_verification.sh and inspects the
# CM-MARKDOWN-EXPORT-SYNC invariant line + the overall verdict — it does not
# re-implement the gate logic, so it cannot bluff by agreeing with a stub.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${HERE}/../.." && pwd)"
GATE_SCRIPT="${PROJECT_ROOT}/scripts/pre_build_verification.sh"

PASS_COUNT=0
FAIL_COUNT=0
pass() { PASS_COUNT=$((PASS_COUNT + 1)); echo "  PASS: $1"; }
fail() { FAIL_COUNT=$((FAIL_COUNT + 1)); echo "  FAIL: $1"; }

# The in-scope doc we mutate. Its .html sibling must exist in the clean tree.
MUTATION_MD="${PROJECT_ROOT}/docs/CONTINUATION.md"
MUTATION_SIBLING="${MUTATION_MD%.md}.html"

# Run the gate and capture combined output. Returns gate exit code in
# GATE_RC and the output in GATE_OUT. We do NOT `set -e`-abort on its failure.
GATE_OUT=""
GATE_RC=0
run_gate() {
    set +e
    GATE_OUT="$(bash "${GATE_SCRIPT}" 2>&1)"
    GATE_RC=$?
    set -e
}

# Extract the CM-MARKDOWN-EXPORT-SYNC invariant outcome (PASS/FAIL) from output.
# Looks at the pass()/fail() result line for invariant 16.
export_sync_passed() {
    echo "${GATE_OUT}" | grep -qE 'PASS \[[0-9]+\]: CM-MARKDOWN-EXPORT-SYNC'
}
export_sync_failed() {
    echo "${GATE_OUT}" | grep -qE 'FAIL \[[0-9]+\]: CM-MARKDOWN-EXPORT-SYNC'
}

# --- Pre-flight: the file we mutate must exist with an .html sibling ---
if [[ ! -f "${MUTATION_MD}" ]] || [[ ! -f "${MUTATION_SIBLING}" ]]; then
    fail "pre-flight: ${MUTATION_MD} or its .html sibling not found"
    echo "RESULT: ${PASS_COUNT} passed, ${FAIL_COUNT} failed"
    exit 1
fi

# Record the original mtime so the trap can restore it precisely.
ORIG_MTIME="$(date -r "${MUTATION_SIBLING}" '+%Y%m%d%H%M.%S' 2>/dev/null || true)"
restore_sibling() {
    if [[ -n "${ORIG_MTIME}" ]]; then
        touch -t "${ORIG_MTIME}" "${MUTATION_SIBLING}" 2>/dev/null || true
    else
        # Fallback: make sibling newer than the .md so the clean tree is valid.
        touch "${MUTATION_SIBLING}" 2>/dev/null || true
    fi
}
trap restore_sibling EXIT

# === Part (a): clean tree → gate PASSES ===
run_gate
if export_sync_passed && [[ "${GATE_RC}" -eq 0 ]]; then
    pass "clean tree: CM-MARKDOWN-EXPORT-SYNC passes and gate exits 0"
else
    fail "clean tree: expected CM-MARKDOWN-EXPORT-SYNC PASS + exit 0 (rc=${GATE_RC})"
    echo "----- gate output -----"
    echo "${GATE_OUT}"
    echo "-----------------------"
fi

# === Part (b): MUTATION — backdate the .html sibling → gate FAILS ===
# Set the sibling's mtime to well before the .md mtime.
touch -t 200001010000.00 "${MUTATION_SIBLING}"

run_gate
if export_sync_failed && [[ "${GATE_RC}" -ne 0 ]]; then
    pass "mutation: backdated .html sibling makes CM-MARKDOWN-EXPORT-SYNC FAIL + gate exits non-zero (teeth proven)"
else
    fail "mutation: expected CM-MARKDOWN-EXPORT-SYNC FAIL + non-zero exit (rc=${GATE_RC}) — gate has no teeth"
    echo "----- gate output -----"
    echo "${GATE_OUT}"
    echo "-----------------------"
fi

# === Restore + verify the clean tree is GREEN again ===
restore_sibling
run_gate
if export_sync_passed && [[ "${GATE_RC}" -eq 0 ]]; then
    pass "restore: tree is GREEN again after restoring the .html sibling mtime"
else
    fail "restore: tree did not return to GREEN (rc=${GATE_RC})"
fi

echo "RESULT: ${PASS_COUNT} passed, ${FAIL_COUNT} failed"
[[ "${FAIL_COUNT}" -eq 0 ]]
