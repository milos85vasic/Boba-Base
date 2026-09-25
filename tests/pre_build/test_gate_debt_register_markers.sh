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
# forbids. This test proves the deferral marker text is present and
# correctly worded in the real source, and that the check genuinely has
# teeth: each mutation below corrupts a SCRATCH COPY (never the live,
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

markers_present() {  # $1 = file to check
    grep -qF 'DEFERRED: CM-SCRIPT-DOCS-SYNC (§11.4.18) — see BOB-223' "$1" \
        && grep -qF 'DEFERRED: CM-DOC-REVISION-HEADER-PRESENT (§11.4.44) — see BOB-223' "$1" \
        && grep -qF 'GATE-DEBT REGISTER' "$1" \
        && bash -n "$1"
}

# === Part (a): the REAL, live source has both markers, correctly worded ===
if markers_present "${GATE_SOURCE}"; then
    pass "real source: both DEFERRED markers present, correctly worded, script syntax-clean"
else
    fail "real source: expected both DEFERRED markers present — register missing or corrupted"
fi

# === Part (b): MUTATION 1 (on the SCRATCH copy only) — corrupt the
#     CM-SCRIPT-DOCS-SYNC marker ===
cp "${GATE_SOURCE}" "${SCRATCH}"
sed -i 's/DEFERRED: CM-SCRIPT-DOCS-SYNC (§11.4.18) — see BOB-223/DEFERRED: CM-SCRIPT-DOCS-SYNC CORRUPTED/' "${SCRATCH}"
if ! markers_present "${SCRATCH}"; then
    pass "mutation 1 (scratch copy): corrupting the CM-SCRIPT-DOCS-SYNC marker line makes the check FAIL (teeth proven)"
else
    fail "mutation 1 (scratch copy): check still reports markers present after corruption — no teeth"
fi

# === Part (c): MUTATION 2 (on the SCRATCH copy only) — corrupt the
#     CM-DOC-REVISION-HEADER-PRESENT marker ===
cp "${GATE_SOURCE}" "${SCRATCH}"
sed -i 's/DEFERRED: CM-DOC-REVISION-HEADER-PRESENT (§11.4.44) — see BOB-223/DEFERRED: CM-DOC-REVISION-HEADER-PRESENT CORRUPTED/' "${SCRATCH}"
if ! markers_present "${SCRATCH}"; then
    pass "mutation 2 (scratch copy): corrupting the CM-DOC-REVISION-HEADER-PRESENT marker line makes the check FAIL (teeth proven)"
else
    fail "mutation 2 (scratch copy): check still reports markers present after corruption — no teeth"
fi

# === Part (d): MUTATION 3 (on the SCRATCH copy only) — remove BOTH
#     marker lines entirely ===
grep -vF 'DEFERRED:' "${GATE_SOURCE}" > "${SCRATCH}"
if ! markers_present "${SCRATCH}"; then
    pass "mutation 3 (scratch copy): removing both DEFERRED lines entirely makes the check FAIL (teeth proven)"
else
    fail "mutation 3 (scratch copy): check still reports markers present after removal — no teeth"
fi

# === Final: the REAL source was never written to — re-confirm GREEN ===
if markers_present "${GATE_SOURCE}"; then
    pass "real source: still GREEN and byte-for-byte unmodified by this test (never written in place)"
else
    fail "real source: no longer GREEN — this test must never have mutated it in place"
fi

echo "RESULT: ${PASS_COUNT} passed, ${FAIL_COUNT} failed"
[[ "${FAIL_COUNT}" -eq 0 ]]
