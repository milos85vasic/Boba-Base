#!/usr/bin/env bash
# test_docs_chain_binary_resolution.sh — real-invocation test that
# scripts/docs_chain.sh's Step 1/3 (workable-items export) actually resolves
# and runs the workable-items binary, instead of silently erroring.
#
# Forensic anchor (2026-08-08): docs_chain.sh hardcoded
# WORKABLE_BIN="${PROJECT_ROOT}/bin/workable-items" — a path that has never
# existed in this checkout (bin/ is gitignored, meant as a local build-output
# dir, and nothing built it there). Every run of docs_chain.sh printed
# "ERROR: workable-items binary not found" on Step 1/3 and exited non-zero,
# while Steps 2/3 (HTML/PDF/DOCX export) kept "succeeding" against whatever
# Issues.md/Fixed.md already contained — masking that the DB-export step was
# never actually happening. constitution/scripts/reporting/report_item.sh
# already solves this correctly (env/config -> committed constitution copy ->
# on-demand `go build`); this test proves docs_chain.sh follows the same
# resolution chain for real, via the script's real invocation path.
#
# §11.4.224: an executing test through the real invocation path, never a
# `bash -n` parse-check alone.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${HERE}/../.." && pwd)"
# RENAMED 2026-08-15 (BOB-104): scripts/docs_chain.sh -> scripts/workable-items-export.sh
# (misnomer retired when the REAL Docs Chain engine landed at constitution/submodules/docs_chain/).
# This test file's basename is preserved for git-history + forensic anchor traceability.
SCRIPT="${PROJECT_ROOT}/scripts/workable-items-export.sh"

PASS_COUNT=0
FAIL_COUNT=0
pass() { PASS_COUNT=$((PASS_COUNT + 1)); echo "  PASS: $1"; }
fail() { FAIL_COUNT=$((FAIL_COUNT + 1)); echo "  FAIL: $1"; }

echo "=== test_docs_chain_binary_resolution.sh ==="

# --- Test 1: --check-only resolves + runs the real binary, no "binary not found" ---
OUT="$(bash "$SCRIPT" --check-only 2>&1)" || true
if echo "$OUT" | grep -q "workable-items binary not found"; then
    fail "Step 1/3 still reports 'binary not found' — resolution is broken"
    echo "$OUT" | sed -n '1,8p'
else
    pass "Step 1/3 resolved a real workable-items binary (no 'binary not found')"
fi

# --- Test 2: the resolved binary is the REAL one — check-only's own validate
#     sub-step must actually run (proves it's not just skipping past a guard) ---
if echo "$OUT" | grep -q "Running workable-items validate"; then
    pass "Step 1/3 (check-only) reached the real 'workable-items validate' call"
else
    fail "Step 1/3 (check-only) never reached the validate call — still short-circuiting"
fi

echo
echo "Results: ${PASS_COUNT} passed, ${FAIL_COUNT} failed"
[ "$FAIL_COUNT" -eq 0 ]
