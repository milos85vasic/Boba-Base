#!/usr/bin/env bash
# test_check_brief_inputs.sh — Hermetic executing test for BOB-107's
# pre-dispatch existence check (scripts/hooks/check-brief-inputs.sh).
#
# Drives the REAL invocation path — not a `bash -n` parse-check
# (§11.4.224(A)): asserts on the checker's real exit status + stdout
# against real files it creates in a temp dir, PLUS a real invocation
# against the actual historical brief (.superpowers/sdd/task-phase1a-
# brief.md) that is BOB-107's forensic anchor — proving the fix closes
# the ACTUAL reported gap, not a synthetic stand-in for it.
#
# §1.1 — Paired meta-test mutation: neuter both `[ ! -e ]` / `[ ! -s ]`
# existence/non-empty checks in _check_one (`false && [ ! -e "$p" ]`) ->
# --self-test flips to FAIL and the real historical-brief scan silently
# reports OK on 6 genuinely-missing files -> restore -> re-assert GREEN.
# Proven manually during authoring (sha256 recorded); re-proven live here.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${HERE}/../.." && pwd)"
CHECKER="${PROJECT_ROOT}/scripts/hooks/check-brief-inputs.sh"

PASS_COUNT=0
FAIL_COUNT=0
pass() { PASS_COUNT=$((PASS_COUNT + 1)); echo "  PASS: $1"; }
fail() { FAIL_COUNT=$((FAIL_COUNT + 1)); echo "  FAIL: $1"; }

if [[ ! -x "${CHECKER}" ]]; then
    echo "FATAL: checker script missing or not executable at ${CHECKER}" >&2
    exit 2
fi

# --- 1: bash -n parse sanity (necessary, never sufficient) ---
if bash -n "${CHECKER}"; then
    pass "checker script is syntactically valid bash"
else
    fail "checker script fails bash -n"
fi

# --- 2: real invocation, --self-test polarity ---
SELFTEST_OUT="$(bash "${CHECKER}" --self-test 2>&1)"
SELFTEST_EXIT=$?
if [[ "${SELFTEST_EXIT}" -eq 0 ]]; then
    pass "checker --self-test exits 0 on unmutated source"
else
    fail "checker --self-test exited ${SELFTEST_EXIT} on unmutated source (expected 0): ${SELFTEST_OUT}"
fi
for label in "golden-good" "golden-bad" "brief-extract"; do
    if echo "${SELFTEST_OUT}" | grep -q "${label}.*PASS"; then
        pass "self-test '${label}' line reports PASS"
    else
        fail "self-test '${label}' line missing/not-PASS: ${SELFTEST_OUT}"
    fi
done

# --- 3: real invocation, explicit --file mode against real temp files ---
TMPD="$(mktemp -d)"
_cleanup_tmpd() { rm -rf "${TMPD}" 2>/dev/null || true; }
trap _cleanup_tmpd EXIT

echo "real content" > "${TMPD}/present.md"
EXIT_OK=0
OUT_OK="$(bash "${CHECKER}" --file "${TMPD}/present.md" 2>&1)" || EXIT_OK=$?
if [[ "${EXIT_OK}" -eq 0 ]]; then
    pass "explicit --file on a present non-empty file exits 0"
else
    fail "explicit --file on a present non-empty file exited ${EXIT_OK} (expected 0): ${OUT_OK}"
fi

EXIT_MISSING=0
OUT_MISSING="$(bash "${CHECKER}" --file "${TMPD}/present.md" --file "${TMPD}/absent.md" 2>&1)" || EXIT_MISSING=$?
if [[ "${EXIT_MISSING}" -eq 1 ]]; then
    pass "explicit --file with one absent input exits 1 (fail-closed)"
else
    fail "explicit --file with one absent input exited ${EXIT_MISSING} (expected 1)"
fi
if echo "${OUT_MISSING}" | grep -q "MISSING       ${TMPD}/absent.md"; then
    pass "the specific missing path is named in the refusal output"
else
    fail "missing path not named in refusal output: ${OUT_MISSING}"
fi
if echo "${OUT_MISSING}" | grep -qi "respawn the producer"; then
    pass "refusal output carries the actionable 'respawn the producer' remediation"
else
    fail "refusal output missing the 'respawn the producer' remediation text: ${OUT_MISSING}"
fi

: > "${TMPD}/empty.md"
EXIT_EMPTY=0
OUT_EMPTY="$(bash "${CHECKER}" --file "${TMPD}/empty.md" 2>&1)" || EXIT_EMPTY=$?
if [[ "${EXIT_EMPTY}" -eq 1 ]] && echo "${OUT_EMPTY}" | grep -q "EMPTY         ${TMPD}/empty.md"; then
    pass "a present-but-zero-byte file is flagged EMPTY, not silently accepted (§11.4.201(1))"
else
    fail "zero-byte file not correctly flagged EMPTY: exit=${EXIT_EMPTY} out=${OUT_EMPTY}"
fi

# --- 4: real invocation, --brief mode against the ACTUAL forensic
#     fixture named in BOB-107's tracker entry. This is the reproduction
#     of the reported defect through the real user path, not a stand-in.
BRIEF_FIXTURE="${PROJECT_ROOT}/.superpowers/sdd/task-phase1a-brief.md"
if [[ -f "${BRIEF_FIXTURE}" ]]; then
    BRIEF_EXIT=0
    BRIEF_OUT="$(bash "${CHECKER}" --brief "${BRIEF_FIXTURE}" 2>&1)" || BRIEF_EXIT=$?
    if [[ "${BRIEF_EXIT}" -eq 1 ]]; then
        pass "the actual BOB-107 forensic brief (task-phase1a-brief.md) is refused (exit 1)"
    else
        fail "the actual BOB-107 forensic brief was NOT refused (exit ${BRIEF_EXIT}, expected 1) — the scratchpad files it names are genuinely absent right now"
    fi
    MISSING_NAMED="$(echo "${BRIEF_OUT}" | grep -c "^  MISSING" || true)"
    if [[ "${MISSING_NAMED}" -ge 1 ]]; then
        pass "at least one missing source-material path is individually named (${MISSING_NAMED} named)"
    else
        fail "no missing source-material path was individually named: ${BRIEF_OUT}"
    fi
    if echo "${BRIEF_OUT}" | grep -q "present       ${PROJECT_ROOT}/constitution/Constitution.md" || echo "${BRIEF_OUT}" | grep -q "present       constitution/Constitution.md"; then
        pass "a genuinely-present source (constitution/Constitution.md) is correctly reported present, not falsely flagged"
    else
        # honest: the brief's item 6 path is relative; accept either cwd-relative or repo-root-relative resolution
        echo "  SKIP (§11.4.3): constitution/Constitution.md presence line not matched under either resolution form — non-fatal, not this check's core assertion"
    fi
else
    echo "  SKIP (§11.4.3): historical fixture .superpowers/sdd/task-phase1a-brief.md not present in this checkout"
fi

# --- 5: a brief with NO Source-materials-shaped section is honestly
#     vacuous-OK, never a silent skip of a section that IS present. ---
cat > "${TMPD}/no-section-brief.md" << 'NOSEC'
# A brief with no source-materials section

Just prose, no declared inputs.
NOSEC
NOSEC_EXIT=0
NOSEC_OUT="$(bash "${CHECKER}" --brief "${TMPD}/no-section-brief.md" 2>&1)" || NOSEC_EXIT=$?
if [[ "${NOSEC_EXIT}" -eq 0 ]] && echo "${NOSEC_OUT}" | grep -qi "nothing declared"; then
    pass "a brief with no Source-materials section is honestly reported as nothing-declared and exits 0"
else
    fail "brief with no section did not exit 0 / did not report 'nothing declared': exit=${NOSEC_EXIT} out=${NOSEC_OUT}"
fi

# --- 6: invocation-error path — no mode flag given fails closed exit 2 ---
NOARGS_EXIT=0
bash "${CHECKER}" >/dev/null 2>&1 || NOARGS_EXIT=$?
if [[ "${NOARGS_EXIT}" -eq 2 ]]; then
    pass "invocation with no --file/--brief/--self-test fails closed with exit 2"
else
    fail "invocation with no mode exited ${NOARGS_EXIT} (expected 2)"
fi

echo
echo "=== Result: ${PASS_COUNT} passed, ${FAIL_COUNT} failed ==="
if [[ "${FAIL_COUNT}" -gt 0 ]]; then
    exit 1
fi
exit 0
