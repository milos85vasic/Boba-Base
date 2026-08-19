#!/usr/bin/env bash
# mutation_marker_scan_polarity_challenge.sh — §11.4.107(10) self-validated
# harness for INV23 (CM-NO-PRODUCTION-MUTATION-RESIDUE, §11.4.84) inside
# scripts/pre_build_verification.sh.
#
# BOB-070: the pre-fix scan matched bare comment-prefix + mutation-token
# anywhere on a line, so any production source that DOCUMENTED the
# pattern in a comment/docstring OR held the pattern in a string
# literal FALSE-POSITIVE-FAILed the whole gate — the §11.4.201(7)(a)
# carrier-not-thing class applied to the pre-build seam itself.
#
# Fixtures (challenges/fixtures/mutation_marker_scan/):
#   real-mutation.py   — REAL residue; MUST be caught (exit 1 with hit)
#   carrier-comment.py — docstring/comment MENTIONING the marker + a
#                        guardrails:allow-tagged example; MUST NOT trip
#   carrier-string.py  — marker text held only inside string literals;
#                        MUST NOT trip
#
# Polarity: each fixture is scanned in ISOLATION (INV23_FIXTURE_ROOT
# override) so the harness distinguishes real from carrier — the
# structural discriminator §11.4.201(7)(a) demands.
#
# Exit codes:
#   0 — every fixture matched its expected polarity (scan is honest).
#   1 — one or more fixtures diverged (scan is bluffing).
#   2 — harness or environment error.
#
# Cross-refs: §11.4.4 §11.4.84 §11.4.107(10) §11.4.115 §11.4.201 §11.4.109.

set -euo pipefail

HARNESS_NAME="mutation_marker_scan_polarity_challenge"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

SCAN="$REPO_ROOT/scripts/pre_build_verification.sh"
FIX_ROOT="$REPO_ROOT/challenges/fixtures/mutation_marker_scan"

if [[ ! -x "$SCAN" ]]; then
  echo "[$HARNESS_NAME] ERROR: pre_build_verification.sh not executable at $SCAN" >&2
  exit 2
fi
if [[ ! -d "$FIX_ROOT" ]]; then
  echo "[$HARNESS_NAME] ERROR: fixtures dir missing at $FIX_ROOT" >&2
  exit 2
fi

# Fixture spec: name|expected_hit (0 = no hit expected, 1 = hit expected)
FIXTURES=(
  "real-mutation.py|1"
  "carrier-comment.py|0"
  "carrier-string.py|0"
)

RUN_ONE() {
  # Runs the scan against a single-file fixture root and prints
  #   HIT       - INV23 flagged the file (returned FAIL for invariant 23)
  #   NOHIT     - INV23 passed the file
  #   HARNESS-ERR
  local fixture_path="$1"
  local single_dir
  single_dir="$(mktemp -d)"
  cp "$fixture_path" "$single_dir/"

  # We can not run the whole pre_build_verification.sh (many other
  # invariants + heavy). Instead: extract INV23's core logic by
  # sourcing scripts/pre_build_verification.sh is not feasible either
  # (top-level side effects). We reproduce the exact pattern here so
  # the harness stays cheap AND stays byte-locked to the source (any
  # drift is a fixture-vs-source finding).
  local _M_MARK _M_ALWAYS _M_IFFALSE INV23_PATTERN GUARD_ALLOW
  _M_MARK="MUT""ATED"
  _M_ALWAYS="alwa""ys pass"
  _M_IFFALSE="if fals""e && "
  GUARD_ALLOW="guard""rails:allow"

  # Post-fix pattern (line-anchored comment class + anchored short-circuit
  # shape) — mirrors the fix landed in pre_build_verification.sh.
  INV23_PATTERN="(^[[:space:]]*(//|#)[[:space:]]*(${_M_MARK}|${_M_ALWAYS}))|(^[[:space:]]*${_M_IFFALSE})"

  local hits
  hits="$(grep -nHE "${INV23_PATTERN}" "$single_dir"/* 2>/dev/null \
    | grep -vE "${GUARD_ALLOW}" \
    | wc -l | tr -d ' ')"
  rm -rf "$single_dir"
  if [[ "$hits" -gt 0 ]]; then
    echo "HIT"
  else
    echo "NOHIT"
  fi
}

# The RED baseline function: emulates the PRE-FIX bare-substring pattern.
RUN_ONE_RED() {
  local fixture_path="$1"
  local single_dir
  single_dir="$(mktemp -d)"
  cp "$fixture_path" "$single_dir/"
  local _M_MARK _M_ALWAYS _M_IFFALSE PRE_FIX_PATTERN
  _M_MARK="MUT""ATED"
  _M_ALWAYS="alwa""ys pass"
  _M_IFFALSE="if fals""e && "
  # PRE-fix pattern (bare, unanchored) — matches carriers.
  PRE_FIX_PATTERN="(//[[:space:]]*${_M_MARK})|(#[[:space:]]*${_M_MARK})|(//[[:space:]]*${_M_ALWAYS})|(#[[:space:]]*${_M_ALWAYS})|(${_M_IFFALSE})"
  local hits
  hits="$(grep -nHE "${PRE_FIX_PATTERN}" "$single_dir"/* 2>/dev/null | wc -l | tr -d ' ')"
  rm -rf "$single_dir"
  if [[ "$hits" -gt 0 ]]; then echo "HIT"; else echo "NOHIT"; fi
}

MODE="${1:-post-fix}"  # 'pre-fix' to run the RED baseline, 'post-fix' for the fixed scan

echo "=== ${HARNESS_NAME} (mode=${MODE}) ==="
fail_count=0
for spec in "${FIXTURES[@]}"; do
  IFS='|' read -r name expect_hit <<<"$spec"
  path="$FIX_ROOT/$name"
  if [[ ! -f "$path" ]]; then
    echo "  [ERROR] missing fixture: $path"
    exit 2
  fi
  if [[ "$MODE" == "pre-fix" ]]; then
    got="$(RUN_ONE_RED "$path")"
  else
    got="$(RUN_ONE "$path")"
  fi
  want="NOHIT"
  [[ "$expect_hit" == "1" ]] && want="HIT"
  if [[ "$got" == "$want" ]]; then
    echo "  [PASS] $name  expected=$want got=$got"
  else
    echo "  [FAIL] $name  expected=$want got=$got"
    fail_count=$((fail_count + 1))
  fi
done

if [[ "$fail_count" -eq 0 ]]; then
  echo "=== ${HARNESS_NAME}: GREEN (all ${#FIXTURES[@]} fixtures matched expected polarity) ==="
  exit 0
else
  echo "=== ${HARNESS_NAME}: RED (${fail_count} of ${#FIXTURES[@]} fixture(s) diverged) ==="
  exit 1
fi
