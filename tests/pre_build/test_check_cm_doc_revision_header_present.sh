#!/usr/bin/env bash
# test_check_cm_doc_revision_header_present.sh — arms for
# CM-DOC-REVISION-HEADER-PRESENT (§11.4.44, BOB-242):
# scripts/pre_build/check_cm_doc_revision_header_present.sh.
#
# Arms (each in a throwaway git repository):
#   G1 golden-GOOD   Revision + UTC Last modified in the header           -> exit 0
#   R1 golden-BAD    Revision line missing                                -> exit 1, named
#   R2 golden-BAD    Last modified missing                                -> exit 1, named
#   R3 golden-BAD    Last modified not ISO 8601 UTC (offset, no Z)        -> exit 1, named
#   R4 golden-BAD    Revision not a positive integer                      -> exit 1, named
#   R5 golden-BAD    header present only far below the title (line 40)    -> exit 1, named
#   R6 golden-BAD    an UNTRACKED new guide without a header              -> exit 1, named
#   F1 golden-FALSE  a guide outside docs/scripts/ without a header       -> exit 0
#   F2 golden-FALSE  seconds omitted (YYYY-MM-DDTHH:MMZ) is still ISO UTC  -> exit 0
#   B1 fail-closed   zero guides enumerated (blind)                       -> exit 2
#   B2 fail-closed   not a git repository                                 -> exit 2
#   M1 paired mutation: the Revision check neutered -> R1 catches it
#
# Usage: bash tests/pre_build/test_check_cm_doc_revision_header_present.sh
# Constitution: §1.1, §11.4.44, §11.4.107(10), §11.4.201(1)(6), §11.4.224.

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
GATE="${REPO}/scripts/pre_build/check_cm_doc_revision_header_present.sh"
PASS=0; FAIL=0
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT   # §11.4.14 cleanup on every exit path

GOOD_HDR='**Revision:** 3
**Last modified:** 2026-09-26T12:00:00Z'

mk_repo() {  # <name> <header-text-for-x.md> [line-offset]
    local r="${TMP}/$1" hdr="$2" pad="${3:-0}" i
    mkdir -p "${r}/docs/scripts"
    {
        echo "# x.sh"; echo
        for ((i = 0; i < pad; i++)); do echo "filler"; done
        printf '%s\n' "${hdr}"
        echo; echo "body"
    } > "${r}/docs/scripts/x.md"
    printf '# y.sh\n\n%s\n' "${GOOD_HDR}" > "${r}/docs/scripts/y.md"
    git -C "${r}" init -q && git -C "${r}" add -A && git -C "${r}" -c user.email=t@t -c user.name=t commit -qm init
    echo "${r}"
}

arm() {  # <label> <want-rc> <needle-or-empty> <gate> <args...>
    local label="$1" want="$2" needle="$3" gate="$4"; shift 4
    local out rc
    out="$(bash "${gate}" "$@" 2>&1)"; rc=$?
    if [[ "${rc}" -eq "${want}" ]] && { [[ -z "${needle}" ]] || grep -qF -- "${needle}" <<<"${out}"; }; then
        echo "  PASS  ${label} (exit ${rc})"; PASS=$((PASS+1))
    else
        echo "  FAIL  ${label}: wanted exit ${want} + '${needle}', got exit ${rc}"
        sed 's/^/          /' <<<"${out}"; FAIL=$((FAIL+1))
    fi
}

echo "CM-DOC-REVISION-HEADER-PRESENT — arms"

arm "G1 golden-GOOD full header" 0 "OK: all 2" "${GATE}" "$(mk_repo g1 "${GOOD_HDR}")"
R1_REPO="$(mk_repo r1 '**Last modified:** 2026-09-26T12:00:00Z')"
arm "R1 golden-BAD Revision missing" 1 "docs/scripts/x.md: missing or malformed **Revision:**" "${GATE}" "${R1_REPO}"
arm "R2 golden-BAD Last modified missing" 1 "docs/scripts/x.md: missing or malformed **Last modified:**" "${GATE}" "$(mk_repo r2 '**Revision:** 1')"
arm "R3 golden-BAD Last modified with an offset instead of UTC Z" 1 "docs/scripts/x.md: missing or malformed **Last modified:**" "${GATE}" \
    "$(mk_repo r3 $'**Revision:** 1\n**Last modified:** 2026-06-14T16:40:00+0300')"
arm "R4 golden-BAD Revision not a positive integer" 1 "docs/scripts/x.md: missing or malformed **Revision:**" "${GATE}" \
    "$(mk_repo r4 $'**Revision:** v2\n**Last modified:** 2026-09-26T12:00:00Z')"
arm "R5 golden-BAD header buried at line 40, not below the title" 1 "docs/scripts/x.md" "${GATE}" "$(mk_repo r5 "${GOOD_HDR}" 38)"
r="$(mk_repo r6 "${GOOD_HDR}")"; printf '# new.sh\n\nno header\n' > "${r}/docs/scripts/new.md"
arm "R6 golden-BAD an untracked new guide is checked too" 1 "docs/scripts/new.md" "${GATE}" "${r}"
r="$(mk_repo f1 "${GOOD_HDR}")"; mkdir -p "${r}/docs/guides"; printf '# g\n\nno header\n' > "${r}/docs/guides/g.md"
arm "F1 golden-FALSE a doc outside docs/scripts/ is out of scope" 0 "OK:" "${GATE}" "${r}"
arm "F2 golden-FALSE seconds omitted is still ISO 8601 UTC" 0 "OK:" "${GATE}" \
    "$(mk_repo f2 $'**Revision:** 12\n**Last modified:** 2026-09-26T12:00Z')"
r="${TMP}/b1"; mkdir -p "${r}/docs"; printf 'x\n' > "${r}/docs/x.md"
git -C "${r}" init -q && git -C "${r}" add -A && git -C "${r}" -c user.email=t@t -c user.name=t commit -qm init
arm "B1 fail-closed: zero guides enumerated is BLIND" 2 "BLIND" "${GATE}" "${r}"
mkdir -p "${TMP}/notgit"
arm "B2 fail-closed: not a git repository" 2 "not a git repository" "${GATE}" "${TMP}/notgit"

MUT="${TMP}/mutated_gate.sh"
sed 's/^REV_RE=.*/REV_RE=".*"/' "${GATE}" > "${MUT}"
if ! grep -qF "missing or malformed **Revision:**" <<<"$(bash "${GATE}" "${R1_REPO}" 2>&1)"; then
    echo "  FAIL  M1 precondition: the unmutated gate does not report R1"; FAIL=$((FAIL+1))
elif cmp -s "${MUT}" "${GATE}"; then
    echo "  FAIL  M1 mutation sed did not change the gate copy"; FAIL=$((FAIL+1))
elif grep -qF "missing or malformed **Revision:**" <<<"$(bash "${MUT}" "${R1_REPO}" 2>&1)"; then
    echo "  FAIL  M1 mutated gate still reports the missing Revision — mutation not load-bearing"; FAIL=$((FAIL+1))
else
    echo "  PASS  M1 mutated gate (Revision check neutered) misses R1 — R1's assertion catches it"; PASS=$((PASS+1))
fi

echo "RESULT: ${PASS} passed, ${FAIL} failed"
[[ "${FAIL}" -eq 0 ]]
