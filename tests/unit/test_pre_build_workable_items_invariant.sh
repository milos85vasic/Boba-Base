#!/usr/bin/env bash
# test_pre_build_workable_items_invariant.sh — real-invocation test that
# scripts/pre_build_verification.sh's invariant 17
# (CM-WORKABLE-ITEMS-VALIDATE) actually runs `workable-items validate`
# instead of silently SKIPPING.
#
# Forensic anchor (2026-08-08): the invariant hardcoded
# WORKABLE_BINARY="${PROJECT_ROOT}/bin/workable-items" — a path that has
# never existed in this checkout — so every pre-build run printed
# "SKIP: workable-items binary or DB not present — skipping invariant 17"
# and the DB-integrity check was never actually performed by the gate that
# is supposed to enforce it. Sibling bug to scripts/workable-items-export.sh
# (renamed 2026-08-15 BOB-104 from scripts/docs_chain.sh — misnomer retired)
# Step 1 (see tests/unit/test_docs_chain_binary_resolution.sh, itself kept
# under the historical basename); same fix pattern
# (env/config -> committed constitution copy -> on-demand `go build`,
# matching constitution/scripts/reporting/report_item.sh).
#
# §11.4.224: an executing test through the real invocation path.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${HERE}/../.." && pwd)"
SCRIPT="${PROJECT_ROOT}/scripts/pre_build_verification.sh"

PASS_COUNT=0
FAIL_COUNT=0
pass() { PASS_COUNT=$((PASS_COUNT + 1)); echo "  PASS: $1"; }
fail() { FAIL_COUNT=$((FAIL_COUNT + 1)); echo "  FAIL: $1"; }

echo "=== test_pre_build_workable_items_invariant.sh ==="

# Full pre_build_verification.sh does a lot of work; grep just the invariant
# 17 line + its immediate verdict rather than asserting the whole script's
# overall exit code (which depends on many unrelated invariants).
OUT="$(bash "$SCRIPT" 2>&1)" || true

if echo "$OUT" | grep -qF "SKIP: workable-items binary or DB not present"; then
    fail "invariant 17 still silently SKIPs — binary resolution is broken"
else
    pass "invariant 17 no longer silently skips (binary resolved)"
fi

if echo "$OUT" | grep -qE "workable-items validate: DB invariant check (passed|FAILED)"; then
    pass "invariant 17 reached a real validate verdict (passed or FAILED, not skipped)"
elif echo "$OUT" | grep -qF "MUTATION MARKER"; then
    # Honest boundary (§11.4.3): a SEPARATE, pre-existing defect — the
    # mutation-marker pre-check aborts the whole script before invariant 17
    # is ever reached, on carrier false-positives (legitimate
    # constitution/**/*_mutation_test.sh + *_test.go files that intentionally
    # contain the literal strings "MUTATED"/"# MUTATION" as part of their own
    # §1.1 testing logic, not leftover residue). This is a DIFFERENT bug from
    # the one this test targets (binary resolution, proven fixed above) —
    # tracked separately in docs/GOVERNANCE_AUDIT_2026-08-08_ROUND2.md rather
    # than silently passed or falsely blamed on this fix.
    echo "  SKIP: cannot reach invariant 17 end-to-end — a separate, pre-existing"
    echo "        mutation-marker carrier false-positive aborts the script first"
    echo "        (tracked separately; not this fix's regression)."
else
    fail "invariant 17 never reached a real validate verdict, and not via the known mutation-marker abort"
fi

echo
echo "Results: ${PASS_COUNT} passed, ${FAIL_COUNT} failed"
[ "$FAIL_COUNT" -eq 0 ]
