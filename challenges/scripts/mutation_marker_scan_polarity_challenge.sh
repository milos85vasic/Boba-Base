#!/usr/bin/env bash
# mutation_marker_scan_polarity_challenge.sh — challenge-runner entry point for
# the CM-NO-PRODUCTION-MUTATION-RESIDUE polarity harness (§11.4.84).
#
# ── Why this file is now a DELEGATOR ────────────────────────────────────
#   The previous version of this challenge re-declared the gate's own
#   detection pattern inside itself — its own comment said so verbatim:
#   "We reproduce the exact pattern here so the harness stays cheap AND
#   stays byte-locked to the source". It was not byte-locked to anything.
#   It built a private copy of the regex and then tested THAT copy, so its
#   verdict described the copy, never the gate. That is a §11.4.249
#   producer=oracle collapse: the thing under test and the thing deciding
#   the verdict were the same artifact.
#
#   The consequence was measured, not theorised. While this challenge
#   reported GREEN on every run, the real gate drifted into being blind to
#   5 of 7 real residue shapes (trailing-comment residue, mid-line
#   short-circuit swallow, unfenced waiver bypass — see the forensic table
#   in scripts/pre_build/check_cm_no_production_mutation_residue.sh). A
#   green light that cannot go red is not an oracle, it is decoration.
#
# ── DELEGATE, not RETIRE, and why ───────────────────────────────────────
#   The real harness lives at
#     challenges/fixtures/mutation_marker_scan/polarity_check.sh
#   and it executes the REAL gate script for all 13 fixtures, with a
#   §11.4.201(7)(b) control needle that refuses to report any fixture
#   CLEAN until a known-detectable residue has been SEEN through the same
#   invocation path.
#
#   Deleting this file outright would have silently dropped that harness
#   out of the suite: challenges/scripts/run_all_challenges.sh discovers
#   its work by globbing "$HERE"/*_challenge.sh, and the harness lives
#   under challenges/fixtures/, which that glob never reaches. Retiring
#   the challenge would therefore have removed the last thing that runs
#   the harness — a §11.4.234(C) "gate lost on disconnect". So this file
#   is kept at the discovered path and reduced to a delegator that owns no
#   detection logic of its own. There is exactly ONE detector (the gate)
#   and exactly ONE oracle (the harness); this file is neither.
#
#   It deliberately declares no marker tokens and no patterns. A file that
#   holds no copy of the thing under test cannot drift away from it.
#
# Exit codes (passed through verbatim from the harness):
#   0 — every fixture matched its expected polarity, needle seen.
#   1 — one or more fixtures diverged (the gate is bluffing).
#   2 — harness/environment error, including "control needle not seen",
#       which is a §11.4.201(6) blind-instrument refusal and never a pass.
#
# Cross-refs: §1.1 §11.4.84 §11.4.107(10) §11.4.115 §11.4.201(7)
#             §11.4.234(C) §11.4.240 §11.4.249
set -uo pipefail

CHALLENGE_NAME="mutation_marker_scan_polarity_challenge"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
HARNESS="${REPO_ROOT}/challenges/fixtures/mutation_marker_scan/polarity_check.sh"

if [[ ! -f "${HARNESS}" ]]; then
    echo "[${CHALLENGE_NAME}] ERROR: polarity harness missing at ${HARNESS}" >&2
    echo "[${CHALLENGE_NAME}] Refusing to report a verdict — an absent oracle is not a pass." >&2
    exit 2
fi

echo "=== ${CHALLENGE_NAME} ==="
echo "  delegating to the real-gate harness: ${HARNESS#"${REPO_ROOT}/"}"
echo "  (this challenge owns no detection logic — §11.4.249 producer != oracle)"
echo

bash "${HARNESS}"
rc=$?

echo
case "${rc}" in
    0) echo "=== ${CHALLENGE_NAME}: PASS (harness GREEN — real gate honest on both polarities) ===" ;;
    1) echo "=== ${CHALLENGE_NAME}: FAIL (harness RED — real gate diverged on a fixture) ===" ;;
    *) echo "=== ${CHALLENGE_NAME}: ERROR (harness exit ${rc} — verdict not trustworthy) ===" ;;
esac
exit "${rc}"
