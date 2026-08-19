#!/usr/bin/env bash
# anchor_block_integrity_challenge.sh — §11.4.107(10) self-validated
# harness for scripts/anchor_block_integrity_check.sh (BOB-105).
#
# Runs the checker against 5 fixtures with KNOWN outcomes:
#   golden-good              → checker exits 0
#   negative-control         → checker exits 0
#   golden-bad-duplicated    → checker exits 1 (DUPLICATE-OR-COLLISION)
#   golden-bad-diverged      → checker exits 1 (LOCKSTEP-DIVERGENCE)
#   golden-bad-collision     → checker exits 1 (DUPLICATE-OR-COLLISION)
#
# A checker that PASSes a golden-bad fixture, or FAILs a golden-good /
# negative-control fixture, is itself the bluff (§11.4.107(10)).
#
# §11.4.115 RED-first: this harness is authored BEFORE the checker is
# trusted; the golden-bad fixtures reproduce the defect class on the
# pre-check state, then GREEN on the post-check state (rc=1 with the
# right finding class).
#
# Exit codes:
#   0 — every fixture matched its expected outcome (checker is honest).
#   1 — one or more fixtures diverged (checker is bluffing).
#   2 — harness or environment error.
#
# Cross-refs: §11.4.4 §11.4.107(10) §11.4.115 §11.4.201 §11.4.227(B).

set -euo pipefail

HARNESS_NAME="anchor_block_integrity_challenge"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

CHECKER="$REPO_ROOT/scripts/anchor_block_integrity_check.sh"
FIX_ROOT="$REPO_ROOT/challenges/fixtures/anchor_block_integrity"

if [[ ! -x "$CHECKER" ]]; then
  echo "ERROR: checker not executable at $CHECKER" >&2
  exit 2
fi
if [[ ! -d "$FIX_ROOT" ]]; then
  echo "ERROR: fixtures dir missing at $FIX_ROOT" >&2
  exit 2
fi

# Fixture spec:  name  expected_rc  expected_finding_grep (empty = any)
FIXTURES=(
  "golden-good|0|"
  "negative-control|0|"
  "golden-bad-duplicated|1|DUPLICATE-OR-COLLISION"
  "golden-bad-diverged|1|LOCKSTEP-DIVERGENCE"
  "golden-bad-collision|1|DUPLICATE-OR-COLLISION"
)

fails=0
for spec in "${FIXTURES[@]}"; do
  IFS='|' read -r name want_rc want_grep <<<"$spec"
  cfg="$FIX_ROOT/$name/anchor_block_integrity_check.conf"
  if [[ ! -f "$cfg" ]]; then
    echo "FAIL: $name — missing config $cfg"
    fails=$((fails+1))
    continue
  fi
  out="$(mktemp)"
  err="$(mktemp)"
  set +e
  "$CHECKER" --config "$cfg" >"$out" 2>"$err"
  got_rc=$?
  set -e

  ok=1
  if [[ "$got_rc" -ne "$want_rc" ]]; then
    ok=0
    echo "FAIL: $name — expected rc=$want_rc got rc=$got_rc"
    echo "  --- stdout ---"; sed 's/^/    /' "$out"
    echo "  --- stderr ---"; sed 's/^/    /' "$err"
  fi

  if [[ -n "$want_grep" ]]; then
    if ! grep -q "$want_grep" "$err"; then
      ok=0
      echo "FAIL: $name — expected finding class '$want_grep' not present on stderr"
      echo "  --- stderr ---"; sed 's/^/    /' "$err"
    fi
  fi

  if [[ $ok -eq 1 ]]; then
    echo "PASS: $name (rc=$got_rc${want_grep:+, finding=$want_grep})"
  else
    fails=$((fails+1))
  fi
  rm -f "$out" "$err"
done

echo
if [[ $fails -ne 0 ]]; then
  echo "$HARNESS_NAME: FAIL — $fails fixture(s) diverged from expected outcome"
  exit 1
fi
echo "$HARNESS_NAME: PASS — checker honest across all ${#FIXTURES[@]} fixtures (§11.4.107(10))"
exit 0
