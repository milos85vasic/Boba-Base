#!/usr/bin/env bash
# THE PRODUCER for the CM-EXPORT-CHARSET-VALID ratchet baseline (BOB-182).
#
# WHAT THIS IS, AND WHY IT IS A SEPARATE FILE (§11.4.249, §11.4.240).
#   A gate that writes its own threshold during a pre-build run becomes a PRODUCER
#   as well as a GATE — the producer=gate collapse §11.4.240(C) names as the one
#   that yields weakened thresholds. So the write capability lives HERE, in a
#   script that is EXPLICITLY INVOKED BY A HUMAN and is never on the pre-build
#   path. The gate cannot call this, and does not contain a line that could.
#
#   The two share ONE oracle (lib/cm_export_charset_scan.py) so the number this
#   script records and the number the gate later enforces cannot diverge. The
#   oracle knows nothing about thresholds; only its two consumers do.
#
# MONOTONE DECREASE IS ENFORCED HERE TOO (§11.4.135).
#   This script can only LOWER the baseline. Given a count at or above the stored
#   value it REFUSES and writes nothing — a regression is fixed in the corpus, it
#   is never accommodated by moving the bar. The ONLY way to raise the baseline is
#   to hand-edit the tracked file, which is a diff a reviewer sees (§11.4.142).
#   That asymmetry is the ratchet: cheap to tighten, deliberate to loosen.
#
#   HONEST SCOPE OF THAT DEFENCE (§11.4.6). The refusals below raise the cost of a
#   raise; they do not make one impossible, and claiming otherwise would overstate
#   them. Deleting the baseline file and re-running --adopt, or editing the number
#   by hand, both reach a higher bar. What stops that is not this script — it is
#   that every such route leaves a diff in a TRACKED file for a reviewer to see.
#   Which means the defence only exists once the baseline file is COMMITTED; while
#   it is untracked, none of these routes leaves a trace and the guarantee is void.
#
# ANTI-BLUFF (§11.4.6): this script reports what it MEASURED and what it WROTE. It
# never reports a tighten it did not perform, and on refusal it says why in terms
# of the two numbers it compared.
#
# USAGE
#   bash scripts/pre_build/tighten_cm_export_charset_baseline.sh [SCAN_ROOT]
#       Lower the baseline to the live count. Refuses unless it is strictly lower.
#   bash scripts/pre_build/tighten_cm_export_charset_baseline.sh --adopt [SCAN_ROOT]
#       Establish a baseline where none exists yet (first adoption only). Refuses
#       if one already exists — which blocks the careless raise, not the determined
#       one (delete-then-adopt still reaches a higher bar). The real defence is the
#       tracked diff; see HONEST SCOPE above.
#
# EXIT: 0 written · 1 refused / no baseline file to update · 2 usage
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${HERE}/../.." && pwd)"
cd "${PROJECT_ROOT}" || exit 1

ADOPT=0
if [[ "${1:-}" == "--adopt" ]]; then ADOPT=1; shift; fi
if [[ $# -gt 1 ]]; then
    echo "usage: $(basename "$0") [--adopt] [SCAN_ROOT]" >&2
    exit 2
fi
SCAN_ROOT="${1:-.}"
BASELINE_FILE="${SCAN_ROOT}/scripts/pre_build/cm_export_charset_valid.baseline"
ORACLE="${HERE}/lib/cm_export_charset_scan.py"
BASELINE_READER="${HERE}/lib/cm_export_charset_baseline_read.sh"

echo "[tighten_cm_export_charset_baseline] CM-EXPORT-CHARSET-VALID ratchet"

if [[ ! -f "${ORACLE}" ]]; then
    echo "REFUSED: oracle missing at ${ORACLE}; nothing measured the corpus"
    exit 1
fi
if [[ ! -f "${BASELINE_READER}" ]]; then
    echo "REFUSED: baseline reader missing at ${BASELINE_READER}"
    exit 1
fi
# shellcheck source=lib/cm_export_charset_baseline_read.sh
. "${BASELINE_READER}"
if ! read -r TOTAL BAD COMPLIANT _SAMPLE < <(python3 "${ORACLE}" "${SCAN_ROOT}"); then
    echo "REFUSED: the oracle did not complete; the count is UNKNOWN, not zero"
    exit 1
fi

# The same control needle the gate uses (§11.4.201(7)(b)). Tightening to a zero a
# BLIND scan produced would lock in a threshold nothing ever measured.
if [[ "${TOTAL}" -eq 0 ]]; then
    echo "REFUSED: zero generated exports found; the enumeration is BLIND, not a clean corpus"
    exit 1
fi
if [[ "${COMPLIANT}" -eq 0 ]]; then
    echo "REFUSED: not one export declares a charset; the detector cannot be shown to discriminate"
    exit 1
fi

echo "  generated exports scanned ......... ${TOTAL}"
echo "  MISSING a charset (live count) .... ${BAD}"

read_baseline "${BASELINE_FILE}"
BASELINE_RC=$?

if [[ "${BASELINE_RC}" -eq 2 ]]; then
    # Genuinely absent — the only state --adopt is for.
    if [[ "${ADOPT}" -ne 1 ]]; then
        echo "REFUSED: ${BASELINE_ERROR}"
        echo "         This mode LOWERS an existing ratchet; it does not establish one."
        echo "         First adoption is a deliberate act: re-run with --adopt."
        exit 1
    fi
elif [[ "${BASELINE_RC}" -ne 0 ]]; then
    # Present but unusable. Refusing to write THROUGH it is the point: a symlink
    # would be silently replaced by a regular file (destroying whatever the
    # operator meant by it), and a corrupt or ambiguous file would be overwritten
    # by a value this script never managed to compare against.
    echo "REFUSED: ${BASELINE_ERROR}"
    echo "         Refusing to overwrite a threshold this script cannot first read."
    exit 1
else
    if [[ "${ADOPT}" -eq 1 ]]; then
        echo "REFUSED: a baseline already exists at ${BASELINE_FILE}"
        echo "         --adopt is for first adoption only. Allowing it to overwrite an"
        echo "         existing ratchet would be a raise wearing an adoption's clothes."
        exit 1
    fi
    CURRENT="${BASELINE_VALUE}"
    echo "  stored ratchet baseline ........... ${CURRENT}"
    if [[ "${BAD}" -gt "${CURRENT}" ]]; then
        echo "REFUSED: live count ${BAD} would RAISE the baseline above ${CURRENT}."
        echo "         The ratchet is MONOTONE DECREASE (§11.4.135). A regression is fixed"
        echo "         in the corpus; the bar is never moved up to meet it. Nothing written."
        exit 1
    fi
    if [[ "${BAD}" -eq "${CURRENT}" ]]; then
        echo "NO-OP: live count ${BAD} already equals the baseline; the ratchet is current."
        exit 0
    fi
fi

STAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
FROM="${CURRENT:-<first adoption>}"
TMP="${BASELINE_FILE}.tmp.$$"
{
    echo "# CM-EXPORT-CHARSET-VALID — ratchet baseline (§11.4.135 monotone decrease)."
    echo "#"
    echo "# This file is DATA (§11.4.35), not code: it carries the operator's recorded"
    echo "# brownfield adoption answer of 2026-08-26 — \"keep the monotone ratchet\" —"
    echo "# as a number the gate enforces."
    echo "#"
    echo "# WRITTEN ONLY BY scripts/pre_build/tighten_cm_export_charset_baseline.sh,"
    echo "# which can only LOWER this value. The gate READS this file and has no write"
    echo "# path to it at all (§11.4.249 producer≠gate, §11.4.240(B) capability)."
    echo "#"
    echo "# RAISING it requires editing this file by hand — deliberately harder than"
    echo "# tightening, and visible to a reviewer as a diff (§11.4.142)."
    echo "baseline=${BAD}"
    echo "tightened_from=${FROM}"
    echo "tightened_at=${STAMP}"
    echo "exports_scanned=${TOTAL}"
} > "${TMP}" && mv -f "${TMP}" "${BASELINE_FILE}"
RC=$?
rm -f "${TMP}" 2>/dev/null
if [[ "${RC}" -ne 0 ]]; then
    echo "REFUSED: could not write ${BASELINE_FILE}"
    exit 1
fi
# Verify the write landed where it was aimed (§11.4.200 read-back-after-write): a
# zero exit from the writer proves bytes moved, never that they arrived at the
# intended path.
read_baseline "${BASELINE_FILE}"
if [[ $? -ne 0 || "${BASELINE_VALUE}" != "${BAD}" ]]; then
    echo "REFUSED: post-write read-back of ${BASELINE_FILE} does not show baseline=${BAD}"
    echo "         The write reported success but the file does not carry the value."
    exit 1
fi

if [[ "${ADOPT}" -eq 1 ]]; then
    echo "ADOPTED: ratchet baseline established at ${BAD} (${TOTAL} exports scanned)"
else
    echo "TIGHTENED: ratchet baseline lowered ${CURRENT} -> ${BAD}; the progress is locked in"
fi
echo "          Commit ${BASELINE_FILE} — an untracked ratchet binds nothing (§11.4.215)."
exit 0
