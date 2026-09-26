#!/usr/bin/env bash
# test_build_workable_items_from_source.sh — BOB-188 build-on-demand proof for
# scripts/pre_build/build_workable_items_from_source.sh (the binary resolver
# pre_build_verification.sh invariant 17 now uses).
#
# Operator decision recorded on BOB-188 (2026-08-26, §11.4.66): the gate must
# BUILD FROM SOURCE, or REFUSE HONESTLY when the Go toolchain is absent — never
# fall back to a stale binary sitting on disk. This test drives the resolver
# through its real invocation path in a scratch fixture that ALSO carries a
# stale executable at bin/workable-items and at the sibling ./workable-items —
# exactly the two files that won the old candidate loop.
#
# Oracle (§11.4.245, SPECIFIED + METAMORPHIC): the fixture's Go program prints
# a version string taken from its OWN source. The binary the resolver hands
# back must print the string CURRENTLY in the source (V1, then V2 after an
# edit), never the stale binaries' "STALE-SHIPPED"/"STALE-SIBLING" marker.
#
# Cases:
#   R1 golden-TRUE  stale bin/ + stale sibling present -> resolver output runs V1
#   R2 golden-TRUE  source edited to V2                -> resolver output runs V2
#   R3 golden-TRUE  Go toolchain absent from PATH      -> exit 3, REFUSED, no path
#   R4 golden-TRUE  source does not compile            -> exit 1, no path
#   R5 negative control: the OLD candidate-loop logic, replayed verbatim on the
#      same fixture, DOES pick the stale file — proves the fixture reproduces
#      the BOB-188 defect, so R1 passing is evidence, not an easy fixture.
#   M1 paired §1.1 mutation: a resolver copy that prefers bin/workable-items
#      when present -> R1's oracle catches it (prints STALE-SHIPPED).
#
# Usage: bash tests/pre_build/test_build_workable_items_from_source.sh
# Exit:  0 all cases behaved; 1 any case wrong; 3 precondition (no go) unmet.
# Constitution: §1.1, §11.4.30, §11.4.66, §11.4.107(10), §11.4.108,
#               §11.4.201(1)(6)(11), §11.4.224, §11.4.245.

set -uo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RESOLVER_REL="scripts/pre_build/build_workable_items_from_source.sh"
PASS=0; FAIL=0
ok()  { echo "  PASS  $1"; PASS=$((PASS+1)); }
bad() { echo "  FAIL  $1"; FAIL=$((FAIL+1)); }

if ! command -v go >/dev/null 2>&1; then
    echo "ABORT: go toolchain not on PATH — cannot exercise the build path (exit 3)"
    exit 3
fi

TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT   # §11.4.14 cleanup on every exit path

WI="${TMP}/wi"
mkdir -p "${WI}/cmd/workable-items" "${WI}/bin"
printf 'module fixture\n\ngo 1.21\n' > "${WI}/go.mod"
write_src() {
    printf 'package main\n\nimport "fmt"\n\nfunc main() { fmt.Println("%s") }\n' "$1" \
        > "${WI}/cmd/workable-items/main.go"
}
write_src "SRC-V1"
printf '#!/bin/sh\necho STALE-SHIPPED\n' > "${WI}/bin/workable-items"
printf '#!/bin/sh\necho STALE-SIBLING\n' > "${WI}/workable-items"
chmod +x "${WI}/bin/workable-items" "${WI}/workable-items"

RESOLVER="${PROJECT_ROOT}/${RESOLVER_REL}"
if [[ ! -f "${RESOLVER}" ]]; then
    bad "resolver ${RESOLVER_REL} does not exist (the BOB-188 build-on-demand path is absent)"
    echo "RESULT: ${PASS} passed, ${FAIL} failed"; exit 1
fi

run_resolver() {  # resolver-path [extra env...]
    local r="$1"; shift
    env TMPDIR="${TMP}" "$@" BOBA_WI_SRC_DIR="${WI}" bash "${r}" 2>"${TMP}/err"
}

echo "BOB-188 build-on-demand resolver — cases"

# R5 negative control FIRST: the old loop, verbatim, must pick the stale file.
old_pick=""
for cand in "${WI}/bin/workable-items" "${WI}/workable-items"; do
    if [[ -x "${cand}" ]]; then old_pick="${cand}"; break; fi
done
if [[ "$("${old_pick}")" == "STALE-SHIPPED" ]]; then
    ok "R5 negative control: the old candidate loop picks the stale shipped binary on this fixture"
else
    bad "R5 fixture does not reproduce BOB-188 (old loop printed '$("${old_pick}")')"
fi

# R1
out="$(run_resolver "${RESOLVER}")"; rc=$?
if [[ "${rc}" -eq 0 && -x "${out}" && "$("${out}")" == "SRC-V1" ]]; then
    ok "R1 resolver builds from source and ignores the stale binaries (prints SRC-V1)"
else
    bad "R1 rc=${rc} path='${out}' ran='$([[ -x "${out}" ]] && "${out}")' err=$(tr '\n' ' ' <"${TMP}/err")"
fi

# R2
write_src "SRC-V2"
out="$(run_resolver "${RESOLVER}")"; rc=$?
if [[ "${rc}" -eq 0 && -x "${out}" && "$("${out}")" == "SRC-V2" ]]; then
    ok "R2 a source edit is reflected immediately (prints SRC-V2) — staleness is structurally impossible"
else
    bad "R2 rc=${rc} path='${out}' ran='$([[ -x "${out}" ]] && "${out}")'"
fi

# R3 — PATH stripped of go. Keep the coreutils the resolver needs.
NOGO="${TMP}/nogo-bin"; mkdir -p "${NOGO}"
for t in bash env sha256sum find sort xargs cut mktemp dirname cat tr rm mv chmod printf basename; do
    p="$(command -v "${t}" 2>/dev/null)" && ln -sf "${p}" "${NOGO}/${t}"
done
out="$(run_resolver "${RESOLVER}" PATH="${NOGO}")"; rc=$?
if [[ "${rc}" -eq 3 && -z "${out}" ]] && grep -q "REFUSED" "${TMP}/err"; then
    ok "R3 Go absent -> exit 3 REFUSED, no binary path emitted (never a stale fallback)"
else
    bad "R3 rc=${rc} out='${out}' err=$(tr '\n' ' ' <"${TMP}/err")"
fi

# R4
printf 'package main\nfunc main() { this is not go }\n' > "${WI}/cmd/workable-items/main.go"
out="$(run_resolver "${RESOLVER}")"; rc=$?
if [[ "${rc}" -eq 1 && -z "${out}" ]]; then
    ok "R4 broken source -> exit 1, no binary path (a failed build is never replaced by a stale one)"
else
    bad "R4 rc=${rc} out='${out}'"
fi
write_src "SRC-V1"

# M1 paired mutation: prefer bin/workable-items when present.
MUT="${TMP}/mutated_resolver.sh"
{
    echo '#!/usr/bin/env bash'
    echo 'if [[ -x "${BOBA_WI_SRC_DIR}/bin/workable-items" ]]; then echo "${BOBA_WI_SRC_DIR}/bin/workable-items"; exit 0; fi'
    tail -n +2 "${RESOLVER}"
} > "${MUT}"
out="$(run_resolver "${MUT}")"; rc=$?
if [[ -x "${out}" && "$("${out}")" == "STALE-SHIPPED" ]]; then
    ok "M1 mutation (prefer shipped binary) is caught by the R1 oracle — the test has teeth"
else
    bad "M1 mutated resolver did not reproduce the stale pick (rc=${rc} out='${out}') — oracle toothless"
fi

echo "RESULT: ${PASS} passed, ${FAIL} failed"
[[ "${FAIL}" -eq 0 ]]
