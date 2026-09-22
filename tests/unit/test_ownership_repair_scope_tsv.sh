#!/usr/bin/env bash
# test_ownership_repair_scope_tsv.sh — BOB-202 RED, now GREEN as the standing
# guard for scripts/ownership_repair.sh's scope-entry reader.
#
# Feature      : 002-user-owned-downloads
# Under test   : scripts/ownership_repair.sh (the `while ... read` loop over
#                ownership_scope_entries() rows) + the new shared
#                scripts/lib/ownership.sh ownership_split_tsv() it now uses.
# Requirements : E1 scope schema (optional/preserve_mode/recursive booleans)
# Governance   : §11.4.115 (RED on the broken artifact), §11.4.201(1)
#                (golden-FALSE — a fully-specified row must still parse
#                identically), §11.4.251 (reuse the sibling's already-fixed
#                dialect, never invent a second one)
#
# ===========================================================================
# WHAT WAS WRONG, MEASURED (not assumed)
# ===========================================================================
# `while IFS=$'\t' read -r e_path e_kind e_opt e_pres e_rec` — TAB is an IFS
# *whitespace* character, so bash collapses a RUN of consecutive tabs into ONE
# delimiter even with IFS explicitly set to a single tab. `ownership_scope_
# entries()` (scripts/lib/ownership.sh) emits `str(e.get("kind", ""))`, so an
# entry that OMITS `kind` produces a row like `<path>\t\t1\t0\t1` — two tabs
# back to back. Reading that with `read` collapses the double-tab into a
# single delimiter, so `optional`'s value ("1") lands in `kind`'s slot and
# every field after it shifts one slot left, with `recursive` arriving EMPTY.
# CONSEQUENCE, driven end-to-end below: an entry declared `optional: true`
# that omits `kind` is silently treated as NON-optional — an absent path that
# should skip honestly instead hard-fails the whole run.
#
# THE FIX reuses scripts/ownership_precondition.sh's ALREADY-FIXED dialect for
# this exact row shape (`split_tsv()`, `readarray -d $'\t'`), promoted into
# the shared library as `ownership_split_tsv()` so this repair script and its
# sibling read the SAME scope rows through the SAME parser (§11.4.251) — not a
# second, independently-authored fix for the same bug class.
#
# ===========================================================================
# WHY THIS DRIVES THE REAL SCRIPT END-TO-END
# ===========================================================================
# The reader loop is inline in main(), not a separately callable function, so
# §11.4.201(11) means running the real script against a real scope file with
# a genuinely `kind`-omitting entry, observing its real stdout/exit code —
# not re-implementing the field-splitting here and asserting against the copy.
#
# §11.4.263: this suite signals no processes.

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${HERE}/../.." && pwd)"
REPAIR="${PROJECT_ROOT}/scripts/ownership_repair.sh"
LIB="${PROJECT_ROOT}/scripts/lib/ownership.sh"

PASS=0; FAIL=0; SKIP=0
pass() { PASS=$((PASS+1)); echo "  PASS: $1"; }
fail() { FAIL=$((FAIL+1)); echo "  FAIL: $1"; }
skip() { SKIP=$((SKIP+1)); echo "  SKIP: $1"; }
finish() {
    echo "RESULT: ${PASS} passed, ${FAIL} failed, ${SKIP} skipped"
    [[ "${FAIL}" -eq 0 ]] || exit 1
    exit 0
}

[[ -f "${REPAIR}" ]] || { fail "target missing: scripts/ownership_repair.sh"; finish; }
[[ -f "${LIB}" ]]    || { fail "target missing: scripts/lib/ownership.sh"; finish; }

WORK=""
cleanup() { local rc=$?; [[ -n "${WORK}" && -d "${WORK}" ]] && rm -rf "${WORK}"; exit "${rc}"; }
trap cleanup EXIT
WORK="$(mktemp -d "${TMPDIR:-/tmp}/bob202.XXXXXXXX")" || { fail "harness: mktemp -d failed"; finish; }

# run_case <label> <repair-script> <lib-script> <kind-line-or-empty>
#
# Builds a sandbox declaring ONE ABSENT, optional:true location. When
# <kind-line-or-empty> is non-empty it is inserted as the entry's `kind:` line
# (a fully-specified row, the golden-FALSE); when empty, `kind` is omitted
# entirely (the RED shape). Echoes RC:<exit-code> and whether the run reported
# the location as honestly skipped.
run_case() {
    local label="$1" repair_script="$2" lib_script="$3" kind_line="$4"
    local sb target scope state out rc

    sb="$(mktemp -d "${WORK}/${label}.XXXXXX")"
    mkdir -p "${sb}/scripts/lib" "${sb}/state" "${sb}/target"
    cp "${repair_script}" "${sb}/scripts/ownership_repair.sh"
    cp "${lib_script}" "${sb}/scripts/lib/ownership.sh"

    target="${sb}/target/nonexistent-optional"
    scope="${sb}/scope.yaml"
    {
        echo "schema_version: 1"
        echo "paths:"
        echo "  - path: ${target}"
        [[ -n "${kind_line}" ]] && echo "    ${kind_line}"
        echo "    optional: true"
        echo "    preserve_mode: false"
        echo "    recursive: true"
    } > "${scope}"

    state="${sb}/state"
    out="${sb}/run.out"
    CONTAINER_RUNTIME=podman OWNED_PATHS_FILE="${scope}" \
        bash "${sb}/scripts/ownership_repair.sh" --scope "${scope}" --state-dir "${state}" --force \
        > "${out}" 2>&1
    rc=$?

    if grep -qF "declared optional — skipped" "${out}"; then
        echo "RC:${rc}:SKIPPED-HONESTLY"
    elif grep -qF "not optional" "${out}"; then
        echo "RC:${rc}:TREATED-NON-OPTIONAL"
    else
        echo "RC:${rc}:OTHER"
        sed 's/^/        /' "${out}" >&2
    fi
}

echo "== BOB-202: scope reader — an omitted 'kind' must not shift later fields =="

# ===========================================================================
# CASE 1 (THE RED, now GREEN) — kind OMITTED, optional: true.
# ===========================================================================
R1="$(run_case shipped_no_kind "${REPAIR}" "${LIB}" "")"
case "${R1}" in
    RC:0:SKIPPED-HONESTLY)
        pass "shipped: an entry omitting 'kind' with optional:true is honestly skipped (rc 0) — 'optional' read from the right slot" ;;
    RC:1:TREATED-NON-OPTIONAL)
        fail "shipped: an entry omitting 'kind' with optional:true was treated as NON-optional and hard-failed — the field-shift defect is still present" ;;
    *)
        fail "shipped: unexpected result '${R1}' for the kind-omitted case" ;;
esac

# ===========================================================================
# CASE 2 (GOLDEN-FALSE, §11.4.201(1)) — kind PRESENT, optional: true. A fully
# specified row must parse identically to before the fix.
# ===========================================================================
R2="$(run_case shipped_with_kind "${REPAIR}" "${LIB}" "kind: downloads")"
case "${R2}" in
    RC:0:SKIPPED-HONESTLY)
        pass "golden-FALSE: a fully-specified row (kind present) still parses correctly — optional:true still skips honestly" ;;
    *)
        fail "golden-FALSE: a fully-specified row regressed — result '${R2}' (expected RC:0:SKIPPED-HONESTLY)" ;;
esac

# ===========================================================================
# CASE 3 (THE CONTROL, RED reproduced) — the SAME kind-omitted scope run
# against byte-identical copies of the PRE-FIX repair script + library
# (git HEAD, captured at run time) must reproduce the ORIGINAL collapse —
# proving Case 1 is discriminating, not a fixture artefact.
# ===========================================================================
PRE_REPAIR="${WORK}/ownership_repair_prefix.sh"
PRE_LIB="${WORK}/ownership_lib_prefix.sh"
if git -C "${PROJECT_ROOT}" show HEAD:scripts/ownership_repair.sh > "${PRE_REPAIR}" 2>/dev/null \
   && git -C "${PROJECT_ROOT}" show HEAD:scripts/lib/ownership.sh > "${PRE_LIB}" 2>/dev/null \
   && [[ -s "${PRE_REPAIR}" && -s "${PRE_LIB}" ]]; then
    if grep -qF "IFS=\$'\\t' read -r e_path e_kind e_opt e_pres e_rec" "${PRE_REPAIR}"; then
        R3="$(run_case control_prefix "${PRE_REPAIR}" "${PRE_LIB}" "")"
        case "${R3}" in
            RC:1:TREATED-NON-OPTIONAL)
                pass "control: the pre-fix reader reproduces the reported field-shift (treated non-optional, hard-fails) under this identical harness, proving Case 1 is discriminating" ;;
            RC:0:SKIPPED-HONESTLY)
                fail "control: the pre-fix reader ALSO skipped honestly under this harness — Case 1's PASS is not evidence of this fix" ;;
            *)
                fail "control: unexpected result '${R3}' for the pre-fix reader" ;;
        esac
    else
        skip "control: git HEAD's scripts/ownership_repair.sh no longer contains the pre-fix 'IFS=\$'\\t' read' form — HEAD has moved past the captured baseline, the shipped-case verdicts above stand on their own"
    fi
else
    skip "control: could not read the pre-fix scripts from git HEAD — not asserted"
fi

finish
