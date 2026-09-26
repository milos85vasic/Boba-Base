#!/usr/bin/env bash
# test_gate_debt_register_markers.sh — §1.1 paired-mutation guard for the
# BOB-223 GATE-DEBT REGISTER block in scripts/pre_build_verification.sh
# (§11.4.227(A) registered-deferral discipline).
#
# BOB-223 named two constitutionally-named gates with no implementation
# anywhere in this pre-build sweep: CM-SCRIPT-DOCS-SYNC (§11.4.18) and
# CM-DOC-REVISION-HEADER-PRESENT (§11.4.44). Per §11.4.227(A) a named gate
# must be either IMPLEMENTED or covered by a REGISTERED DEFERRAL pointing
# at a tracked workable item — silent absence is exactly what §11.4.227
# forbids. BOB-242 (2026-09-26) IMPLEMENTED both as invariants 61/62, so
# the DEFERRED lines were removed; this test now proves each name is
# EITHER implemented OR deferred — never silently absent — and that the
# check genuinely has teeth: each mutation below corrupts a SCRATCH COPY (never the live,
# possibly-concurrently-read repo file — §11.4.84 working-tree quiescence:
# scripts/pre_build_verification.sh is a shared choke-point actively read
# by other concurrent invocations during multi-track development, so this
# test NEVER writes to it in place) and asserts the check FAILS against
# that copy, then re-confirms the REAL, untouched source is still GREEN.
#
# This is a fast, hermetic, source-grep-based test — it does NOT run the
# full ~58-invariant sweep (that would cost minutes per assertion for a
# check whose only job is "does this exact wording exist in the source").
# Runtime confirmation that the block actually EXECUTES (not merely exists
# as dead source text) is covered by the full-sweep run this item's own
# closure evidence captures, and by every future full sweep (the block
# runs unconditionally, right before the final Result tally).
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${HERE}/../.." && pwd)"
GATE_SOURCE="${PROJECT_ROOT}/scripts/pre_build_verification.sh"

PASS_COUNT=0
FAIL_COUNT=0
pass() { PASS_COUNT=$((PASS_COUNT + 1)); echo "  PASS: $1"; }
fail() { FAIL_COUNT=$((FAIL_COUNT + 1)); echo "  FAIL: $1"; }

if [[ ! -f "${GATE_SOURCE}" ]]; then
    fail "pre-flight: ${GATE_SOURCE} not found"
    echo "RESULT: ${PASS_COUNT} passed, ${FAIL_COUNT} failed"
    exit 1
fi

# Scratch working copy — ALL mutation + inspection happens here. The real
# repo file is only ever READ (once, to seed the scratch copy), never
# written, so a concurrently-running `bash scripts/pre_build_verification.sh`
# elsewhere on the host is never exposed to a torn/partial write.
SCRATCH="$(mktemp)"
cp "${GATE_SOURCE}" "${SCRATCH}"
cleanup() { rm -f "${SCRATCH}"; }
trap cleanup EXIT

# accounted_for <file> <gate-name> <gate-script-rel> <anchor>
# A named gate is accounted for when it is EITHER registered as a deferral
# (the exact DEFERRED line) OR implemented: the sweep prints its invariant
# label, invokes its gate script by path, and that script exists. BOB-242
# moved both gates from the first state to the second on 2026-09-26.
accounted_for() {
    local f="$1" name="$2" script="$3" anchor="$4"
    if grep -qF "DEFERRED: ${name} (${anchor}) — see BOB-223" "${f}"; then return 0; fi
    grep -qE "^echo \"\[[0-9]+/[0-9]+\] ${name}:" "${f}" \
        && grep -qF "\${PROJECT_ROOT}/${script}" "${f}" \
        && [[ -f "${PROJECT_ROOT}/${script}" ]]
}
markers_present() {  # $1 = file to check
    accounted_for "$1" CM-SCRIPT-DOCS-SYNC scripts/pre_build/check_cm_script_docs_sync.sh '§11.4.18' \
        && accounted_for "$1" CM-DOC-REVISION-HEADER-PRESENT scripts/pre_build/check_cm_doc_revision_header_present.sh '§11.4.44' \
        && grep -qF 'GATE-DEBT REGISTER' "$1" \
        && bash -n "$1"
}

# === Part (a): the REAL, live source accounts for both gates ===
if markers_present "${GATE_SOURCE}"; then
    pass "real source: both named gates are accounted for (implemented or deferred), register present, syntax-clean"
else
    fail "real source: a named gate is neither implemented nor registered as a deferral — silent gate debt"
fi

# === MUTATION 1 (scratch copy): drop the CM-SCRIPT-DOCS-SYNC invariant label ===
cp "${GATE_SOURCE}" "${SCRATCH}"
sed -i -E '/^echo "\[[0-9]+\/[0-9]+\] CM-SCRIPT-DOCS-SYNC:/d' "${SCRATCH}"
if ! markers_present "${SCRATCH}"; then
    pass "mutation 1 (scratch copy): removing the CM-SCRIPT-DOCS-SYNC invariant makes the check FAIL (teeth proven)"
else
    fail "mutation 1 (scratch copy): check still passes with CM-SCRIPT-DOCS-SYNC neither implemented nor deferred — no teeth"
fi

# === MUTATION 2 (scratch copy): unwire the CM-DOC-REVISION-HEADER-PRESENT gate script ===
cp "${GATE_SOURCE}" "${SCRATCH}"
sed -i 's|scripts/pre_build/check_cm_doc_revision_header_present.sh|scripts/pre_build/UNWIRED.sh|g' "${SCRATCH}"
if ! markers_present "${SCRATCH}"; then
    pass "mutation 2 (scratch copy): unwiring the CM-DOC-REVISION-HEADER-PRESENT gate script makes the check FAIL (teeth proven)"
else
    fail "mutation 2 (scratch copy): check still passes with the header gate unwired — no teeth"
fi

# === MUTATION 3 (scratch copy): remove the register block heading ===
grep -vF 'GATE-DEBT REGISTER' "${GATE_SOURCE}" > "${SCRATCH}"
if ! markers_present "${SCRATCH}"; then
    pass "mutation 3 (scratch copy): removing the GATE-DEBT REGISTER makes the check FAIL (teeth proven)"
else
    fail "mutation 3 (scratch copy): check still passes without the register — no teeth"
fi

# === NEGATIVE CONTROL: a deferral line alone still counts as accounted for ===
cp "${GATE_SOURCE}" "${SCRATCH}"
sed -i -E '/^echo "\[[0-9]+\/[0-9]+\] CM-SCRIPT-DOCS-SYNC:/d' "${SCRATCH}"
printf 'echo "  DEFERRED: CM-SCRIPT-DOCS-SYNC (§11.4.18) — see BOB-223"\n' >> "${SCRATCH}"
if markers_present "${SCRATCH}"; then
    pass "negative control: an unimplemented gate WITH its DEFERRED line is accepted (the register path still works)"
else
    fail "negative control: a correctly registered deferral is refused — the check would be a false-positive refusal"
fi

# === Final: the REAL source was never written to — re-confirm GREEN ===
if markers_present "${GATE_SOURCE}"; then
    pass "real source: still GREEN and byte-for-byte unmodified by this test (never written in place)"
else
    fail "real source: no longer GREEN — this test must never have mutated it in place"
fi

echo "RESULT: ${PASS_COUNT} passed, ${FAIL_COUNT} failed"
[[ "${FAIL_COUNT}" -eq 0 ]]
