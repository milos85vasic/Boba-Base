#!/usr/bin/env bash
# CM-EXPORT-CHARSET-VALID — every generated .html export declares a charset.
#
# WHY THIS EXISTS (BOB-169 acceptance (d), §11.4.238 detection gap):
#   The export regime asserted PRESENCE and MTIME, never VALIDITY. So 301 of 334
#   generated exports were charset-less fragments — and the PDFs weasyprint
#   rendered from them carried 12,629 corrupted lines across 281 files — while
#   every gate stayed green. The defect was found by an agent reading a PDF, not
#   by the regime. §11.4.238: discovery out-of-band IS the coverage escape, and
#   closing only the defect without closing the gap is the violation.
#
# WHAT IT ASSERTS: two invariants, not one.
#   (1) THE CORPUS — the charset-less count does not EXCEED the ratchet baseline.
#   (2) THE RATCHET — the baseline is CURRENT. A count BELOW the baseline means
#       the corpus healed and the bar never followed it down, so the gate is
#       silently licensing a regression back to the old count. That staleness is
#       itself a finding and is refused, not merely mentioned in passing prose.
#
# ADOPTION MODEL — MONOTONE-DECREASE RATCHET (§11.4.135 pattern).
#   OPERATOR DECISION, recorded 2026-08-26 under §11.4.66/§11.4.224(E), verbatim:
#   "Keep the monotone ratchet." The count may only go DOWN, never up. An
#   immediate hard floor was offered and NOT chosen — 301 pre-existing violations
#   would have made the build unreachable, which §11.4.234 forbids. This is
#   consumer DATA per §11.4.35: the operator's stated choice, not an agent's
#   invented default, and it is not re-litigated here (§11.4.112(5)).
#
# §11.4.249 ROLE SEPARATION — WHAT THIS FILE IS, AND WHAT IT IS NOT (BOB-182).
#   The threshold is PERSISTED DATA in cm_export_charset_valid.baseline, which
#   this script READS and NEVER WRITES. It contains no write path to that file at
#   all — the separation is a CAPABILITY the source does not have, not an
#   instruction it is trusted to follow (§11.4.240(B)).
#     ORACLE   lib/cm_export_charset_scan.py — counts violations, knows nothing
#              about thresholds. Shared verbatim with the tightener, so producer
#              and gate can never disagree about the number they act on.
#     READER   lib/cm_export_charset_baseline_read.sh — the single validator of
#              what a baseline may be (symlink / non-regular / ambiguous line
#              count / unparseable / out-of-range all refuse). Also shared, and
#              READ-ONLY: sourcing it grants this gate no write capability. It
#              exists because the round-1 BLOCKING was one parse rule written
#              twice and fixed once.
#     GATE     this file — compares the oracle's count to the persisted baseline.
#     PRODUCER tighten_cm_export_charset_baseline.sh — a SEPARATE script, on a
#              SEPARATE invocation, never on the pre-build path. It alone writes
#              the baseline, and it can only LOWER it.
#     VERIFIER tests/pre_build/test_cm_export_charset_valid.sh — lives outside
#              this file, so a mutation that makes the gate always-pass cannot  guardrails:allow documents the §11.4.249 VERIFIER role — prose naming the marker, not residue
#              also silence its own audit.
#   HONEST BOUNDARY (§11.4.6): the oracle and the gate are adjacent, not remote —
#   this script invokes the scan directly. That is acceptable here for the precise
#   reason §11.4.249 names: the collapse it forbids is an oracle that CANNOT SAY
#   "cannot decide" and therefore defaults to ALLOW. Every cannot-decide branch
#   below fails CLOSED (§11.4.252): a blind enumeration, a detector that cannot be
#   shown to discriminate, and a missing or malformed baseline all REFUSE.
#
#   LOOSENING IS A TRACKED DIFF, NEVER AMBIENT. There is deliberately no env var
#   that injects a baseline value. Raising the bar requires editing a git-tracked
#   file, which a reviewer sees (§11.4.142); the previous BOBA_EXPORT_CHARSET_BASELINE
#   override let any caller pass a broken corpus leaving no reviewable trace
#   (measured 2026-08-26: BOBA_EXPORT_CHARSET_BASELINE=9999 turned a planted
#   violation into a PASS) — that channel is closed.
#
# EXIT: 0 pass · 1 regression / blind / fail-closed · 3 stale ratchet
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${HERE}/../.." && pwd)"
cd "${PROJECT_ROOT}" || exit 1

SCAN_ROOT="${1:-.}"
# The corpus and its baseline travel together: a fixture root carries its own.
BASELINE_FILE="${SCAN_ROOT}/scripts/pre_build/cm_export_charset_valid.baseline"
ORACLE="${HERE}/lib/cm_export_charset_scan.py"
BASELINE_READER="${HERE}/lib/cm_export_charset_baseline_read.sh"
TIGHTENER="scripts/pre_build/tighten_cm_export_charset_baseline.sh"

echo "[check_cm_export_charset_valid] CM-EXPORT-CHARSET-VALID"

if [[ ! -f "${ORACLE}" ]]; then
    echo "FAIL: CM-EXPORT-CHARSET-VALID — oracle missing at ${ORACLE}; nothing measured the corpus"
    exit 1
fi
if [[ ! -f "${BASELINE_READER}" ]]; then
    echo "FAIL: CM-EXPORT-CHARSET-VALID — baseline reader missing at ${BASELINE_READER}"
    exit 1
fi
# READ-ONLY by construction: the reader validates and returns a value, and has no
# write path — sourcing it grants this gate no capability it must lack (§11.4.249).
# shellcheck source=lib/cm_export_charset_baseline_read.sh
. "${BASELINE_READER}"

if ! read -r TOTAL BAD COMPLIANT SAMPLE < <(python3 "${ORACLE}" "${SCAN_ROOT}"); then
    echo "FAIL: CM-EXPORT-CHARSET-VALID — the oracle did not complete; the count is UNKNOWN, not zero"
    exit 1
fi

echo "  generated exports scanned ......... ${TOTAL}"
echo "  declaring a charset ............... ${COMPLIANT}"

# CONTROL NEEDLE (§11.4.201(7)(b)): a blind scan and a perfect corpus both report
# zero violations. Requiring a nonzero COMPLIANT count makes any zero a SEEN zero.
if [[ "${TOTAL}" -eq 0 ]]; then
    echo "FAIL: CM-EXPORT-CHARSET-VALID — zero generated exports found; the enumeration is BLIND, not a clean corpus"
    exit 1
fi
if [[ "${COMPLIANT}" -eq 0 ]]; then
    echo "FAIL: CM-EXPORT-CHARSET-VALID — not one export declares a charset; the detector cannot distinguish compliant from non-compliant"
    exit 1
fi

# FAIL CLOSED on an unverifiable threshold (§11.4.252). A gate that invents a
# baseline when it cannot read one is asserting a condition it never checked. Every
# refusal class — symlink, non-regular file, ambiguous line count, unparseable or
# out-of-range integer — is decided by the shared reader, so the gate and the
# tightener cannot drift apart on what a valid baseline is (the round-1 lesson:
# one rule written twice gets fixed once).
read_baseline "${BASELINE_FILE}"
BASELINE_RC=$?
if [[ "${BASELINE_RC}" -ne 0 ]]; then
    echo "  MISSING a charset ................. ${BAD}   (baseline UNUSABLE)"
    echo "FAIL: CM-EXPORT-CHARSET-VALID — ${BASELINE_ERROR}"
    if [[ "${BASELINE_RC}" -eq 2 ]]; then
        echo "        The threshold is an input to this gate's correctness and it is absent,"
        echo "        so the gate refuses rather than assume one."
        echo "        Establish it: bash ${TIGHTENER} --adopt"
    else
        echo "        An unusable threshold is an unresolvable signal, so the gate takes the"
        echo "        conservative-safe default and REFUSES (§11.4.201(4)/§11.4.252)."
    fi
    exit 1
fi
BASELINE="${BASELINE_VALUE}"

echo "  MISSING a charset ................. ${BAD}   (ratchet baseline ${BASELINE})"

if [[ "${BAD}" -gt "${BASELINE}" ]]; then
    echo "FAIL: CM-EXPORT-CHARSET-VALID — ${BAD} charset-less exports exceeds the ratchet baseline ${BASELINE} (e.g. ${SAMPLE})"
    echo "        A NEW charset-less export landed. The generators pass --standalone;"
    echo "        something bypassed them or a stale fragment was committed."
    echo "        The bar does not move up to meet a regression — fix the export."
    exit 1
fi

if [[ "${BAD}" -lt "${BASELINE}" ]]; then
    echo "FAIL: CM-EXPORT-CHARSET-VALID — STALE RATCHET: ${BAD} charset-less exports, below baseline ${BASELINE}"
    echo "        The corpus improved and the bar did not follow it down, so this gate is"
    echo "        currently licensing a regression from ${BAD} back to ${BASELINE} without complaint."
    echo "        That silent permission is the finding; the corpus itself is fine."
    echo "        Lock the progress in (§11.4.135 monotone decrease), then re-run:"
    echo "            bash ${TIGHTENER}"
    exit 3
fi

echo "PASS: CM-EXPORT-CHARSET-VALID — ${BAD} charset-less exports, at baseline (no regression, ratchet current)"
exit 0
