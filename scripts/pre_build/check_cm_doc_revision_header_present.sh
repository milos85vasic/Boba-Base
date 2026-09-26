#!/usr/bin/env bash
# check_cm_doc_revision_header_present.sh — CM-DOC-REVISION-HEADER-PRESENT (§11.4.44, BOB-242)
#
# Purpose:
#   §11.4.44 requires every tracked document in scope to carry, directly below
#   its H1 title, a **Revision:** N line (a positive integer) and a
#   **Last modified:** line in ISO 8601 UTC. The gate was named in the
#   constitution but had no general implementation (registered as gate debt by
#   BOB-223). This implements it for the scope BOB-242 names: the §11.4.18
#   script guides under docs/scripts/.
#
# Scope: every docs/scripts/*.md git tracks, plus untracked ones that are not
#   ignored (a new guide must arrive with its header). Wider §11.4.44 scope
#   (docs/guides, docs/research, …) is not claimed here.
#
# Rule: within the first HEADER_LINES (15) lines —
#   **Revision:** <positive integer>
#   **Last modified:** YYYY-MM-DDTHH:MM[:SS]Z
#
# Adoption: measured 2026-09-26, 1 of 45 guides failed (an offset timestamp,
#   corrected in the same change), so this lands as a hard floor with no
#   baseline.
#
# Usage:   bash scripts/pre_build/check_cm_doc_revision_header_present.sh <repo-root>
# Exit:    0 every guide carries a valid header
#          1 at least one guide is missing or has a malformed header (each named)
#          2 harness error: bad arguments, not a git repo, or ZERO guides
#            enumerated (a blind walk is never reported as clean)
# Side-effects: none; reads only.
# Dependencies: bash, git, head, grep.
# Cross-references: docs/scripts/check_cm_doc_revision_header_present.md,
#   tests/pre_build/test_check_cm_doc_revision_header_present.sh.
#   Constitution: §11.4.44, §11.4.201(6), §11.4.227(A).

set -uo pipefail

if [[ $# -ne 1 ]]; then echo "Usage: $0 <repo-root>" >&2; exit 2; fi
ROOT="$1"
if [[ ! -d "${ROOT}" ]] || ! git -C "${ROOT}" rev-parse --git-dir >/dev/null 2>&1; then
    echo "ERROR: ${ROOT} is not a git repository root" >&2; exit 2
fi
ROOT="$(cd "${ROOT}" && pwd)"

HEADER_LINES=15
REV_RE='^\*\*Revision:\*\*[[:space:]]+[1-9][0-9]*[[:space:]]*$'
MOD_RE='^\*\*Last modified:\*\*[[:space:]]+[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}(:[0-9]{2})?Z[[:space:]]*$'

mapfile -t DOCS < <(git -C "${ROOT}" ls-files --cached --others --exclude-standard -- 'docs/scripts/*.md' | sort -u)
if [[ "${#DOCS[@]}" -eq 0 ]]; then
    echo "ERROR: enumerated ZERO guides under docs/scripts/ — the walk is BLIND, not the tree clean (§11.4.201(6))" >&2
    exit 2
fi

BAD=0; SEEN=0
for d in "${DOCS[@]}"; do
    [[ -f "${ROOT}/${d}" ]] || continue   # deleted in the working tree
    SEEN=$((SEEN+1))
    head_txt="$(head -n "${HEADER_LINES}" "${ROOT}/${d}")"
    if ! grep -qE "${REV_RE}" <<<"${head_txt}"; then
        echo "${d}: missing or malformed **Revision:** (need a positive integer within the first ${HEADER_LINES} lines)"
        BAD=$((BAD+1))
    fi
    if ! grep -qE "${MOD_RE}" <<<"${head_txt}"; then
        echo "${d}: missing or malformed **Last modified:** (need ISO 8601 UTC, e.g. 2026-09-26T12:00:00Z, within the first ${HEADER_LINES} lines)"
        BAD=$((BAD+1))
    fi
done

if [[ "${BAD}" -gt 0 ]]; then
    echo "FAIL: ${BAD} header problem(s) across ${SEEN} guide(s) under docs/scripts/ (§11.4.44)"
    exit 1
fi
echo "OK: all ${SEEN} guides under docs/scripts/ carry a §11.4.44 revision header"
exit 0
