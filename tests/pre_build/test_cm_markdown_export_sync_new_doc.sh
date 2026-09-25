#!/usr/bin/env bash
# test_cm_markdown_export_sync_new_doc.sh — BOB-223 regression guard for the
# CM-MARKDOWN-EXPORT-SYNC (invariant 16) new-doc-creation-moment false
# positive.
#
# THE DEFECT (BOB-223): writing a §11.4.18-mandated companion doc at
# docs/scripts/<name>.md immediately trips invariant 16's hard BLOCKING
# fail, because its .html/.pdf twins do not exist yet — punishing exactly
# the compliance §11.4.18 requires, while an author who never writes the
# doc at all sails through this gate for free (CM-SCRIPT-DOCS-SYNC, the
# gate that WOULD catch the missing doc, is itself unimplemented — see the
# GATE-DEBT REGISTER near the end of scripts/pre_build_verification.sh).
#
# THE FIX: a missing twin for a .md that is NOT YET IN GIT HEAD (no
# committed prior state to have regressed from) is downgraded from a
# BLOCKING fail to a non-blocking WARN carrying an actionable remediation
# command. A missing OR stale twin for a .md that IS already in HEAD is
# UNCHANGED — still hard-blocking, exactly as before BOB-223 (proven by the
# pre-existing tests/unit/test_export_sync_gate.sh, unmodified by this
# item, plus this test's own ARM 2 below).
#
# WHY THIS DRIVES THE REAL GATE (§11.4.249 producer != oracle != gate): this
# harness EXECUTES the real scripts/pre_build_verification.sh and inspects
# its CM-MARKDOWN-EXPORT-SYNC invariant line + overall verdict. It does not
# reimplement invariant 16's own scan/scope logic.
#
# Fixture handling: a single throwaway, genuinely-UNTRACKED
# docs/scripts/__bob223_fixture_new_doc__.md (never committed, never
# staged — this test never runs `git add`) is created for ARM 1 and always
# removed via an EXIT trap, so the tree is quiescent (§11.4.84) both before
# and after this test runs regardless of pass/fail/interrupt.
#
# Cases:
#   1. NEW-DOC (the BOB-223 case)   — a genuinely untracked .md with NO
#                                      .html/.pdf twins at all -> gate
#                                      still reports CM-MARKDOWN-EXPORT-SYNC
#                                      PASS overall (the fixture contributes
#                                      a WARN, never a FAIL) + prints the
#                                      exact fixture path under the new
#                                      "newly-introduced doc(s)" WARN block
#                                      with an actionable remediation
#                                      command.
#   2. STALE-BUT-PRESENT (mutation) — same untracked .md, but its .html
#                                      sibling now EXISTS with an older
#                                      mtime after a real content edit
#                                      (git-dirty) -> the SAME fixture MUST
#                                      still hard-FAIL, proving the fix
#                                      narrows ONLY the missing-AND-new-to-
#                                      git case and does not touch the
#                                      staleness-detection path at all,
#                                      for ANY doc, new or old.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${HERE}/../.." && pwd)"
GATE_SCRIPT="${PROJECT_ROOT}/scripts/pre_build_verification.sh"

# PID-suffixed fixture name: this dispatch's own concurrent multi-track
# environment was observed running multiple simultaneous invocations of
# this very test file, and a fixed fixture name would race across them
# (one instance's cleanup deleting another's in-flight fixture). $$ makes
# concurrent self-invocation safe.
FIXTURE_REL="docs/scripts/__bob223_fixture_new_doc_$$__.md"
FIXTURE_MD="${PROJECT_ROOT}/${FIXTURE_REL}"
FIXTURE_HTML="${FIXTURE_MD%.md}.html"
FIXTURE_PDF="${FIXTURE_MD%.md}.pdf"

PASS_COUNT=0
FAIL_COUNT=0
pass() { PASS_COUNT=$((PASS_COUNT + 1)); echo "  PASS: $1"; }
fail() { FAIL_COUNT=$((FAIL_COUNT + 1)); echo "  FAIL: $1"; }

cleanup() {
    rm -f "${FIXTURE_MD}" "${FIXTURE_HTML}" "${FIXTURE_PDF}"
}
trap cleanup EXIT

# --- Pre-flight: fixture must not already exist, and must be genuinely
#     absent from HEAD (a real reproduction of "just created, uncommitted") ---
cleanup
if git -C "${PROJECT_ROOT}" cat-file -e "HEAD:${FIXTURE_REL}" 2>/dev/null; then
    fail "pre-flight: ${FIXTURE_REL} unexpectedly exists at HEAD — cannot reproduce the new-doc case"
    echo "RESULT: ${PASS_COUNT} passed, ${FAIL_COUNT} failed"
    exit 1
fi

run_gate() {
    set +e
    GATE_OUT="$(bash "${GATE_SCRIPT}" 2>&1)"
    GATE_RC=$?
    set -e
}
export_sync_passed() { echo "${GATE_OUT}" | grep -qE 'PASS \[[0-9]+\]: CM-MARKDOWN-EXPORT-SYNC'; }
export_sync_failed() { echo "${GATE_OUT}" | grep -qE 'FAIL \[[0-9]+\]: CM-MARKDOWN-EXPORT-SYNC'; }
fixture_in_new_doc_warn() { echo "${GATE_OUT}" | grep -qF "__bob223_fixture_new_doc_$$__.html missing (doc not yet in git history"; }
fixture_in_violations() { echo "${GATE_OUT}" | grep -qF "__bob223_fixture_new_doc_$$__.html"; }

# === ARM 1: new, untracked doc, NO twins at all -> WARN, not FAIL ===
cat > "${FIXTURE_MD}" << 'EOF'
# __bob223_fixture_new_doc__

**Revision:** 1
**Last modified:** 2026-09-25T00:00:00Z

Throwaway BOB-223 regression-guard fixture. Never committed.
EOF

run_gate
# NOTE: GATE_RC (the aggregate sweep exit code) is deliberately NOT asserted
# here — this repo runs ~58 invariants and an UNRELATED pre-existing gate
# finding elsewhere in the sweep would make GATE_RC non-zero regardless of
# this fix. This test's scope is CM-MARKDOWN-EXPORT-SYNC specifically,
# asserted by name via export_sync_passed/fixture_in_new_doc_warn above.
if export_sync_passed && fixture_in_new_doc_warn; then
    pass "new untracked doc with no twins: CM-MARKDOWN-EXPORT-SYNC passes overall + fixture surfaces as a non-blocking WARN with remediation guidance"
else
    fail "new untracked doc with no twins: expected CM-MARKDOWN-EXPORT-SYNC PASS + fixture in the new-doc WARN block"
    echo "----- gate output (CM-MARKDOWN-EXPORT-SYNC + surrounding WARN block) -----"
    echo "${GATE_OUT}" | grep -A6 'CM-MARKDOWN-EXPORT-SYNC\|newly-introduced doc' || true
    echo "----------------------------------------------------------------------"
fi

# === ARM 2: MUTATION — same untracked doc, but its .html sibling now
#     EXISTS and is genuinely STALE (a real content edit to the .md makes
#     it git-dirty, and the .html sibling's mtime is older) -> MUST still
#     hard-FAIL. Proves the fix does not touch the staleness-detection
#     path at all — only the "missing sibling for a doc absent from HEAD"
#     case is downgraded. ===
echo "extra content line so the .md content genuinely differs" >> "${FIXTURE_MD}"
touch -t 201001010000.00 "${FIXTURE_MD}"
cat > "${FIXTURE_HTML}" << 'EOF'
<html><body>stale placeholder, predates the source edit above</body></html>
EOF
touch -t 200001010000.00 "${FIXTURE_HTML}"

run_gate
if export_sync_failed && fixture_in_violations; then
    pass "mutation: a STALE-but-PRESENT sibling for the SAME untracked doc still makes CM-MARKDOWN-EXPORT-SYNC FAIL (staleness detection unweakened, teeth proven)"
else
    fail "mutation: expected CM-MARKDOWN-EXPORT-SYNC FAIL for the stale-but-present sibling — the fix may have over-broadly suppressed detection"
    echo "----- gate output (CM-MARKDOWN-EXPORT-SYNC + surrounding block) -----"
    echo "${GATE_OUT}" | grep -A6 'CM-MARKDOWN-EXPORT-SYNC' || true
    echo "----------------------------------------------------------------------"
fi

# === Cleanup + verify the tree is quiescent again (fixture fully removed) ===
cleanup
if [[ ! -e "${FIXTURE_MD}" && ! -e "${FIXTURE_HTML}" && ! -e "${FIXTURE_PDF}" ]]; then
    pass "cleanup: fixture fully removed, tree quiescent again (§11.4.84)"
else
    fail "cleanup: fixture artefact(s) still present after cleanup"
fi

echo "RESULT: ${PASS_COUNT} passed, ${FAIL_COUNT} failed"
[[ "${FAIL_COUNT}" -eq 0 ]]
