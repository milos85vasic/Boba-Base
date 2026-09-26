#!/usr/bin/env bash
# check_cm_script_docs_sync.sh — CM-SCRIPT-DOCS-SYNC (§11.4.18, BOB-242)
#
# Purpose:
#   §11.4.18 requires every shell script to have an external guide at
#   docs/scripts/<name>.md, updated in the SAME commit as the script ("no
#   documentation can be out of sync with its codebase"). The gate was named in
#   the constitution but had no implementation (registered as gate debt by
#   BOB-223). This is the implementation.
#
# Scope: every *.sh / *.bash under scripts/ that git tracks, plus untracked
#   files there that are not ignored (a new script must arrive with its guide).
#   <name> is the file's basename without its extension.
#
# Findings (one key each):
#   NODOC:<path>      no docs/scripts/<name>.md exists
#   DOCBEHIND:<path>  the script changed after its guide did. "Changed" is the
#                     last commit that touched the file; a file with uncommitted
#                     edits (or untracked) counts as changed NOW, so editing a
#                     script in the working tree without its guide is caught
#                     before the commit, and editing both together is not.
#
# Brownfield adoption — MONOTONE-DECREASING RATCHET (§11.4.135(5) / §11.4.224(E)):
#   scripts/pre_build/cm_script_docs_sync.baseline holds the finding SET that
#   existed when this gate landed (seeded 2026-09-26 from --list). Compared by
#   SET, never count:
#     NEW finding (not in the baseline)        -> FAIL  (never add a row to hide one)
#     RETIRED row (baseline key no longer found) -> FAIL (delete the row in the
#                                                   same change that fixes it)
#     BASELINED (in both)                      -> reported, not a failure
#   The ratchet was chosen by the implementing agent as the repository's
#   established brownfield default for set-based gates (same shape as
#   cm_no_fail_open_skip.baseline). It is recorded here as DATA and is open to
#   an operator decision (§11.4.66) to switch to a hard floor or
#   changed-files-only.
#
# Usage:   bash scripts/pre_build/check_cm_script_docs_sync.sh <repo-root> [--list]
#          --list prints the current finding SET (to review a tightening) and exits 0.
# Exit:    0 no NEW finding and no RETIRED row
#          1 NEW finding(s) and/or RETIRED baseline row(s)
#          2 harness error: bad arguments, not a git repo, or ZERO scripts
#            enumerated (a blind walk is never reported as clean)
# Side-effects: none; reads only. The baseline is only ever edited by hand.
# Dependencies: bash, git, grep, sort, comm.
# Cross-references: docs/scripts/check_cm_script_docs_sync.md,
#   tests/pre_build/test_check_cm_script_docs_sync.sh.
#   Constitution: §11.4.18, §11.4.135(5), §11.4.201(6), §11.4.224(E), §11.4.227(A).

set -uo pipefail
export LC_ALL=C   # sort and comm must agree on collation (a mismatch silently corrupts the set diff)

usage() { echo "Usage: $0 <repo-root> [--list]" >&2; }
LIST=0
ROOT=""
for a in "$@"; do
    case "${a}" in
        --list) LIST=1 ;;
        -*) usage; exit 2 ;;
        *) [[ -z "${ROOT}" ]] || { usage; exit 2; }; ROOT="${a}" ;;
    esac
done
[[ -n "${ROOT}" ]] || { usage; exit 2; }
if [[ ! -d "${ROOT}" ]] || ! git -C "${ROOT}" rev-parse --git-dir >/dev/null 2>&1; then
    echo "ERROR: ${ROOT} is not a git repository root" >&2; exit 2
fi
ROOT="$(cd "${ROOT}" && pwd)"
BASELINE="${ROOT}/scripts/pre_build/cm_script_docs_sync.baseline"
NOW="$(date +%s)"

# Files with uncommitted changes or untracked: their effective change time is NOW.
declare -A DIRTY=()
while IFS= read -r -d '' entry; do
    DIRTY["${entry:3}"]=1
done < <(git -C "${ROOT}" status --porcelain=v1 -z --untracked-files=all -- scripts docs/scripts 2>/dev/null)

changed_at() {  # <repo-relative path>
    if [[ -n "${DIRTY[$1]+x}" ]]; then echo "${NOW}"; return; fi
    local t; t="$(git -C "${ROOT}" log -1 --format=%ct -- "$1" 2>/dev/null)"
    echo "${t:-0}"
}

mapfile -t SCRIPTS < <(git -C "${ROOT}" ls-files --cached --others --exclude-standard -- 'scripts/*.sh' 'scripts/*.bash' | sort -u)
if [[ "${#SCRIPTS[@]}" -eq 0 ]]; then
    echo "ERROR: enumerated ZERO scripts under scripts/ — the walk is BLIND, not the tree clean (§11.4.201(6))" >&2
    exit 2
fi

FINDINGS="$(mktemp)"; trap 'rm -f "${FINDINGS}" "${FINDINGS}.b"' EXIT
for f in "${SCRIPTS[@]}"; do
    [[ -f "${ROOT}/${f}" ]] || continue   # deleted in the working tree
    name="$(basename "${f}")"; name="${name%.*}"
    doc="docs/scripts/${name}.md"
    if [[ ! -f "${ROOT}/${doc}" ]]; then
        echo "NODOC:${f}" >> "${FINDINGS}"
    elif (( $(changed_at "${f}") > $(changed_at "${doc}") )); then
        echo "DOCBEHIND:${f}" >> "${FINDINGS}"
    fi
done
sort -u -o "${FINDINGS}" "${FINDINGS}"

if [[ "${LIST}" -eq 1 ]]; then
    cat "${FINDINGS}"
    exit 0
fi

if [[ -f "${BASELINE}" ]]; then
    grep -vE '^[[:space:]]*(#|$)' "${BASELINE}" | sort -u > "${FINDINGS}.b"
else
    : > "${FINDINGS}.b"
fi

NEW=0; RETIRED=0; KEPT=0
while IFS= read -r k; do echo "NEW ${k}"; NEW=$((NEW+1)); done < <(comm -23 "${FINDINGS}" "${FINDINGS}.b")
while IFS= read -r k; do echo "RETIRED ${k}  (no longer a finding — delete this row from the baseline)"; RETIRED=$((RETIRED+1)); done < <(comm -13 "${FINDINGS}" "${FINDINGS}.b")
while IFS= read -r k; do [[ "${CM_SDS_VERBOSE:-0}" == 1 ]] && echo "BASELINED ${k}"; KEPT=$((KEPT+1)); done < <(comm -12 "${FINDINGS}" "${FINDINGS}.b")
[[ "${KEPT}" -gt 0 && "${CM_SDS_VERBOSE:-0}" != 1 ]] && comm -12 "${FINDINGS}" "${FINDINGS}.b" | sed -n '1,3p' | sed 's/^/BASELINED /'

if [[ "${NEW}" -gt 0 || "${RETIRED}" -gt 0 ]]; then
    echo "FAIL: ${NEW} NEW script-doc finding(s), ${RETIRED} RETIRED baseline row(s) (${#SCRIPTS[@]} scripts scanned, ${KEPT} baselined)"
    echo "      fix: write/update docs/scripts/<name>.md in the same change as the script (§11.4.18);"
    echo "      for a RETIRED row, delete it from scripts/pre_build/cm_script_docs_sync.baseline"
    exit 1
fi
echo "OK: no new script-doc drift (${#SCRIPTS[@]} scripts scanned, ${KEPT} baselined finding(s) remaining)"
exit 0
