#!/bin/bash
# verify_resource_pressure_polarity.sh — §11.4.115(F) aggregate polarity
# verifier for resource_pressure_signature_challenge.sh.
#
# Purpose: replace the threshold-mutation "polarity verified" claim the
# §11.4.209 independent review correctly rejected
# (.superpowers/sdd/task-review-457cca4-a7e55f9-report.md, IMPORTANT-1) —
# `SIG1_MAX_PROC_RSS_GB=0` tripping on every process (docs/qa/BOB-076/
# challenge_polarity_forced_fail.log) proves the comparison operator
# works, NOT that the detector catches the actual pathological state.
# §11.4.115(F): "a guard never observed FAILing on the genuinely-broken
# artifact is unvalidated instrumentation and mints no verdicts."
#
# This runner executes all FIVE per-signature RED fixtures under
# challenges/fixtures/resource_pressure/ against the REAL, UN-MUTATED
# challenge script and its DEFAULT thresholds. Each fixture creates (or,
# for SIG-4, safely dependency-injects — see that fixture's own header for
# the host-safety rationale) the genuine pathological precondition the
# corresponding SIG-N detector is supposed to catch, then asserts the
# challenge exits 1 naming that SIG-N.
#
# Usage:
#   bash challenges/scripts/verify_resource_pressure_polarity.sh
#
# Exit:
#   0 = every executed fixture confirmed RED — the challenge genuinely
#       detects the real pathological state for every signature that could
#       be safely and honestly fixtured on this host
#   1 = one or more fixtures failed to reproduce RED (detector under-detects)
#   2 = one or more fixtures had to SKIP (§11.4.3) — reported honestly, not
#       counted as a pass; the run still exits non-zero so a SKIP can never
#       be silently mistaken for a clean bill of health
#
# Anti-bluff (§11.4.6): a SKIPped signature is NEVER reported as verified.
# Per-fixture full transcripts are written to $EVIDENCE_DIR (default
# docs/qa/task-78/) as captured evidence.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
FIXTURE_DIR="$REPO_ROOT/challenges/fixtures/resource_pressure"
EVIDENCE_DIR="${EVIDENCE_DIR:-$REPO_ROOT/docs/qa/task-78}"

mkdir -p "$EVIDENCE_DIR"

FIXTURES=(
  "SIG-1:sig1_real_rss_fixture.sh:sig1_real_fixture_output.txt"
  "SIG-2:sig2_real_thread_fixture.sh:sig2_real_fixture_output.txt"
  "SIG-3:sig3_real_eagain_fixture.sh:sig3_real_fixture_output.txt"
  "SIG-4:sig4_seeded_psi_fixture.sh:sig4_real_fixture_output.txt"
  "SIG-5:sig5_real_pathological_regex_fixture.sh:sig5_real_fixture_output.txt"
)

RESULT_SIGS=()
RESULT_TEXTS=()
PASS_COUNT=0
FAIL_COUNT=0
SKIP_COUNT=0

for entry in "${FIXTURES[@]}"; do
  SIG="${entry%%:*}"
  REST="${entry#*:}"
  FIXTURE_FILE="${REST%%:*}"
  OUT_NAME="${REST#*:}"
  FIXTURE_PATH="$FIXTURE_DIR/$FIXTURE_FILE"
  OUT_FILE="$EVIDENCE_DIR/$OUT_NAME"

  echo "############################################################"
  echo "# $SIG — $FIXTURE_FILE"
  echo "############################################################"

  if [ ! -r "$FIXTURE_PATH" ]; then
    {
      echo "SKIP: fixture script missing at $FIXTURE_PATH"
    } | tee "$OUT_FILE"
    RESULT_SIGS+=("$SIG")
    RESULT_TEXTS+=("SKIP (missing fixture)")
    SKIP_COUNT=$((SKIP_COUNT + 1))
    echo
    continue
  fi

  bash "$FIXTURE_PATH" > "$OUT_FILE" 2>&1
  RC=$?
  cat "$OUT_FILE"
  echo

  RESULT_SIGS+=("$SIG")
  case "$RC" in
    0)
      RESULT_TEXTS+=("RED CONFIRMED")
      PASS_COUNT=$((PASS_COUNT + 1))
      ;;
    2)
      RESULT_TEXTS+=("SKIP (§11.4.3 — see $OUT_FILE)")
      SKIP_COUNT=$((SKIP_COUNT + 1))
      ;;
    *)
      RESULT_TEXTS+=("RED NOT REPRODUCED (detector under-detects — see $OUT_FILE)")
      FAIL_COUNT=$((FAIL_COUNT + 1))
      ;;
  esac
done

echo "############################################################"
echo "# §11.4.115(F) polarity summary"
echo "############################################################"
i=0
while [ "$i" -lt "${#RESULT_SIGS[@]}" ]; do
  printf "  %-6s %s\n" "${RESULT_SIGS[$i]}" "${RESULT_TEXTS[$i]}"
  i=$((i + 1))
done
echo
echo "RED confirmed: $PASS_COUNT / ${#FIXTURES[@]}   FAIL: $FAIL_COUNT   SKIP: $SKIP_COUNT"

if [ "$FAIL_COUNT" -gt 0 ]; then
  echo "VERDICT: FAIL — one or more detectors did not fire on a genuine pathological artifact"
  exit 1
elif [ "$SKIP_COUNT" -gt 0 ]; then
  echo "VERDICT: PARTIAL — $SKIP_COUNT signature(s) honestly SKIPPED (§11.4.3), NOT claimed verified"
  exit 2
else
  echo "VERDICT: PASS — all ${#FIXTURES[@]} signature detectors genuinely fire on their real pathological artifact"
  exit 0
fi
