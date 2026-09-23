#!/usr/bin/env bash
# check_cm_no_fail_open_skip.sh — CM-NO-FAIL-OPEN-SKIP static pre-build gate
# (BOB-161; constitution §11.4.69 names this gate as mandatory).
#
# Purpose:
#   FAIL the build when a test turns evidence the far side ANSWERED into a
#   SKIP — a skip conditioned on a response status, on an empty/absent body,
#   or inside an `except` that also catches answered HTTP errors. A skip is
#   PASS-counting in every summary a human reads, so such a test leaves a
#   real product failure green. Environment-derived skips (missing binary,
#   unset credentials, stack not running = connection refused) are the
#   legitimate §11.4.3 topology SKIP and are NOT findings.
#
# FORENSIC ANCHOR (BOB-092 -> BOB-161):
#   Two fail-opens of this class were removed from
#   tests/e2e/test_live_stack_evidence.py one at a time — an nnmclub
#   SKIP-on-404 and an iptorrents skip on "not authenticated" asserting
#   "transient outage" while the product had classified the failure as
#   rejected credentials. Both were found by an agent reading code, not by
#   the regime (§11.4.238 escape). The guards written then live in the file
#   they guard; this gate audits the CORPUS.
#
# DETECTION ENGINE:
#   scripts/pre_build/cm_no_fail_open_skip_analyzer.py (AST + intra-module
#   taint for Python, carrier-aware line scan for shell). This wrapper holds
#   no detection logic, so it cannot drift from the engine. The engine runs
#   an in-path CONTROL NEEDLE (golden-TRUE + golden-FALSE-with-carrier
#   canaries through the same functions) before trusting any zero
#   (§11.4.201(7)(b)).
#
# RATCHET:
#   Existing findings are recorded as a finding SET in
#   scripts/pre_build/cm_no_fail_open_skip.baseline (monotone-decreasing,
#   §11.4.135(5) / §11.4.224(E) brownfield default). Remediation is tracked
#   as BOB-192. The comparison is SET-based in both directions: NEW -> FAIL,
#   STALE row -> FAIL (remove it in the same change that fixes the finding).
#   Never add a row to silence a new finding.
#
# Usage:
#   check_cm_no_fail_open_skip.sh [--root DIR] [--baseline FILE] [--list]
#   check_cm_no_fail_open_skip.sh --help
#
# Inputs:   --root (default: repo root; must be a git work tree — tests/ is
#           enumerated with `git ls-files --cached --others --exclude-standard`
#           so a new, not-yet-staged test file is scanned too);
#           --baseline (default: scripts/pre_build/cm_no_fail_open_skip.baseline);
#           --list prints the current finding SET (for reviewing a tightening).
# Outputs:  one BASELINED/NEW/STALE line per key on stdout, then a one-line
#           verdict (the last line) naming the control-needle result.
# Side-effects: none (read-only static analysis).
# Dependencies: bash, git, python3 (standard library only).
#
# Verdict:
#   0 — PASS  finding SET equals the baseline SET.
#   1 — FAIL  NEW finding(s) and/or STALE baseline row(s).
#   2 — ERROR usage error, python3/engine missing, root not a git tree,
#       an unparseable test file (tree UNVERIFIED, not clean), the control
#       needle not seen, or zero skip sites (BLIND zero, §11.4.201(6)).
#
# Cross-references: §1.1 §11.4.3 §11.4.6 §11.4.69 §11.4.107(10) §11.4.135
#   §11.4.201 §11.4.224 §11.4.227(A) §11.4.238.
#   Self-test: tests/pre_build/test_check_cm_no_fail_open_skip.sh
#   User guide: docs/scripts/check_cm_no_fail_open_skip.md

set -euo pipefail

SCRIPT_NAME="check_cm_no_fail_open_skip"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ENGINE="$SCRIPT_DIR/cm_no_fail_open_skip_analyzer.py"

ROOT="$REPO_ROOT"
BASELINE="$SCRIPT_DIR/cm_no_fail_open_skip.baseline"
LIST=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help) sed -n '2,66p' "${BASH_SOURCE[0]}"; exit 0 ;;
    --root) ROOT="${2:?--root needs a value}"; shift 2 ;;
    --baseline) BASELINE="${2:?--baseline needs a value}"; shift 2 ;;
    --list) LIST=(--list); shift ;;
    *) echo "ERROR($SCRIPT_NAME): unknown argument: $1" >&2; exit 2 ;;
  esac
done

if [[ ! -f "$ENGINE" ]]; then
  echo "ERROR($SCRIPT_NAME): detection engine not found: $ENGINE" >&2
  exit 2
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR($SCRIPT_NAME): python3 not on PATH — refusing rather than reporting an unverified PASS (§11.4.201(4))." >&2
  exit 2
fi
if ! git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "ERROR($SCRIPT_NAME): $ROOT is not a git work tree — tests/ cannot be enumerated, so the tree is UNVERIFIED." >&2
  exit 2
fi

rc=0
python3 "$ENGINE" --root "$ROOT" --baseline "$BASELINE" "${LIST[@]}" || rc=$?
exit "$rc"
