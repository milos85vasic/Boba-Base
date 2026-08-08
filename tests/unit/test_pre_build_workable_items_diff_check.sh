#!/usr/bin/env bash
# test_pre_build_workable_items_diff_check.sh — real-invocation test that
# invariant 17 (CM-WORKABLE-ITEMS-VALIDATE) ALSO fails the pre-build gate on
# a DB<->Markdown divergence (`workable-items diff`), not just on internal
# validate() violations.
#
# Forensic anchor (§11.4.238 QA-discovery-ledger, docs/QA_DISCOVERY_LEDGER.md,
# BOB-008 entry, 2026-08-08): a `docs/workable_items.db` write landed
# (commit 54e313f) with no matching `docs/Issues.md` update — a real DB<->MD
# divergence — and NOTHING in the standing pre-build gate would have caught
# it, because invariant 17 only ran `validate` (internal DB invariants),
# never `diff` (DB-vs-Markdown divergence). This test proves the gate now
# runs both.
#
# §11.4.224: real invocation, mutation-proven (a deliberately-desynced copy
# of docs/Issues.md MUST make invariant 17 FAIL; the real, synced tree MUST
# pass) — never a bash -n parse-check alone.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${HERE}/../.." && pwd)"
SCRIPT="${PROJECT_ROOT}/scripts/pre_build_verification.sh"

PASS_COUNT=0
FAIL_COUNT=0
pass() { PASS_COUNT=$((PASS_COUNT + 1)); echo "  PASS: $1"; }
fail() { FAIL_COUNT=$((FAIL_COUNT + 1)); echo "  FAIL: $1"; }

echo "=== test_pre_build_workable_items_diff_check.sh ==="

run_invariant_17() {
    # Isolate invariant 17's own logic without needing the whole 18-invariant
    # script to complete (a separate, tracked, pre-existing defect — an
    # unrelated mutation-marker false-positive — aborts the full script
    # before invariant 17; see RD2-41 in docs/GOVERNANCE_AUDIT_2026-08-08_ROUND2.md).
    # Extract and run just the invariant-17 block in a subshell.
    awk '/# --- Invariant 17:/{flag=1} flag{print} /# --- Invariant 18:/{exit}' "$SCRIPT" \
        > /tmp/.private/milosvasic/claude-1000/-run-media-milosvasic-DATA4TB-Projects-boba/aa7d8260-6b66-4009-9682-135f4fd74829/scratchpad/inv17_extract.sh
    (
        PROJECT_ROOT="$PROJECT_ROOT"
        pass() { echo "PASS_MARKER: $1"; }
        fail() { echo "FAIL_MARKER: $1"; }
        # shellcheck disable=SC1091
        source /tmp/.private/milosvasic/claude-1000/-run-media-milosvasic-DATA4TB-Projects-boba/aa7d8260-6b66-4009-9682-135f4fd74829/scratchpad/inv17_extract.sh
    )
}

# --- Test 1: on the real (currently-synced) tree, invariant 17's diff check
#     specifically must report NO divergence. NOTE: `workable-items validate`
#     currently reports 2 pre-existing, already-tracked violations
#     (BOB-009/BOB-010's evidence_path gap — see docs/QA_DISCOVERY_LEDGER.md),
#     so invariant 17's OVERALL exit may legitimately be non-zero for that
#     separate, honest, already-documented reason. This test asserts only
#     that the DIFF-specific check ran and found no divergence — it does not
#     assert overall pass, which would be a false claim about an unrelated,
#     already-open item.
OUT1="$(run_invariant_17 2>&1)" || true
if echo "$OUT1" | grep -qi "divergence\|out of sync\|not in sync"; then
    fail "invariant 17's diff check reports the CURRENT tree as divergent — unexpected, investigate: $OUT1"
else
    pass "invariant 17's diff check reports the current tree as in sync (no false divergence)"
fi

# --- Test 2 (mutation): desync docs/Issues.md -> invariant 17 must FAIL ---
ISSUES_MD="${PROJECT_ROOT}/docs/Issues.md"
BACKUP="$(mktemp)"
cp "$ISSUES_MD" "$BACKUP"
trap 'cp "$BACKUP" "$ISSUES_MD"; rm -f "$BACKUP"' EXIT

printf '\n<!-- test-mutation: desynced from DB on purpose -->\n' >> "$ISSUES_MD"

OUT2="$(run_invariant_17 2>&1)" || true
# Must be a DIFF-specific failure, not just a re-detection of the separate,
# pre-existing validate() issue (which would fail identically whether or not
# a diff check exists at all — that would be a tautology, not a real proof).
if echo "$OUT2" | grep -qi "divergence\|out of sync\|not in sync\|differs\|diff:"; then
    pass "invariant 17 correctly reports DIVERGENCE when docs/Issues.md is desynced from the DB"
else
    fail "invariant 17 did NOT report a diff-specific divergence for a deliberately desynced docs/Issues.md — diff check missing or broken"
    echo "$OUT2"
fi

cp "$BACKUP" "$ISSUES_MD"
rm -f "$BACKUP"
trap - EXIT

echo
echo "Results: ${PASS_COUNT} passed, ${FAIL_COUNT} failed"
[ "$FAIL_COUNT" -eq 0 ]
