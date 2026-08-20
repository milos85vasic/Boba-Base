#!/usr/bin/env bash
# check_cm_test_mock_pid_explicit_int.sh — CM-TEST-MOCK-PID-EXPLICIT-INT
# static pre-build gate (§11.4.263 clause C), consumed BY REFERENCE from the
# constitution submodule.
#
# Purpose:
#   Statically detect TEST code that builds a `Mock()` / `MagicMock()` /
#   `AsyncMock()` standing in for a process/subprocess without explicitly
#   setting `.pid` to an integer. An unconfigured mock attribute coerces to
#   the integer 1 through `MagicMock.__int__()`, so production code reading
#   `proc.pid` receives 1 — and signalling process group 1 is the BOB-126
#   broadcast-kill that caused 7 forced logouts.
#
# WHY THIS FILE IS THIN (§11.4.177 / §11.4.74):
#   The DETECTION ENGINE is universal and lives in the constitution submodule
#   at `constitution/scripts/gates/cm_test_mock_pid_explicit_int.sh`.
#   §11.4.177 mandates shared tooling be consumed BY REFERENCE, never copied
#   — a copy diverges silently. This file is a DELEGATOR: it owns only boba's
#   consumer-side SCOPE DATA (§11.4.35 — which root, which glob, which
#   excludes) and hands every scan to the shared engine. No detection logic
#   lives here, so it cannot drift from the engine.
#
#   Coverage boba's former local copy carried and the shared engine lacked was
#   UPSTREAMED into that engine first (§11.4.74): the SUBPROCESS-SHAPE rule
#   that fires on the literal BOB-126 fixture — a stand-in with
#   `.returncode = None` plus a process-lifecycle attribute and no explicit
#   int `.pid` — even when the test file never mentions `.pid` at all
#   (production reads it). The engine additionally catches shapes the local
#   copy missed (any mock whose `.pid` is read) and avoids a false positive
#   the local copy had (it only recognised the `patch.object(os, "killpg")`
#   exemption form, not `patch("os.killpg")`).
#
# Usage:
#   check_cm_test_mock_pid_explicit_int.sh              # default scope
#   check_cm_test_mock_pid_explicit_int.sh PATH...      # explicit file(s)/dir(s)
#   check_cm_test_mock_pid_explicit_int.sh --help
#
# Inputs:   optional PATH arguments; no stdin; no env input.
# Outputs:  scope/verdict lines on stdout; findings + FAIL summary on stderr.
# Side-effects: none (read-only scan; no mock is ever instantiated).
# Dependencies: bash, find, awk, and the constitution submodule gate.
#
# Scope DATA (consumer-owned, §11.4.35):
#   root     : tests
#   glob     : *.py
#   excludes : __pycache__ .git
#
#   The glob applies to the DEFAULT root. An EXPLICITLY passed file is
#   scanned whatever its extension — a deliberate, documented widening
#   (§11.4.6, never silent); a non-Python file simply yields no matches.
#
# Verdict:
#   0 — PASS  (no risky process-stand-in mock under scan)
#   1 — FAIL  (one or more; each reported on stderr)
#   2 — ERROR (usage error, missing engine, or a PATH that does not exist)
#
# Cross-refs: §11.4.1 §11.4.6 §11.4.35 §11.4.69 §11.4.74 §11.4.107(10)
#             §11.4.108 §11.4.115 §11.4.135 §11.4.177 §11.4.201 §11.4.226
#             §11.4.238 §11.4.240 §11.4.249 §11.4.263 §12.12.

set -euo pipefail

SCRIPT_NAME="check_cm_test_mock_pid_explicit_int"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
CONST_GATE="$REPO_ROOT/constitution/scripts/gates/cm_test_mock_pid_explicit_int.sh"

SCAN_GLOB="*.py"
SCAN_EXCLUDE="__pycache__ .git"
DEFAULT_SCAN_ROOTS=("tests")

VERBOSE=0
declare -a EXPLICIT_PATHS=()

print_help() { sed -n '2,53p' "${BASH_SOURCE[0]}"; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help) print_help; exit 0 ;;
    -v|--verbose) VERBOSE=1; shift ;;
    --) shift; while [[ $# -gt 0 ]]; do EXPLICIT_PATHS+=("$1"); shift; done ;;
    -*) echo "ERROR: unknown argument: $1" >&2; exit 2 ;;
    *) EXPLICIT_PATHS+=("$1"); shift ;;
  esac
done

if [[ ! -f "$CONST_GATE" ]]; then
  echo "ERROR: shared gate engine missing: $CONST_GATE" >&2
  echo "       (§11.4.177 — this gate is consumed by reference; run" >&2
  echo "        'git submodule update --init constitution' to restore it)" >&2
  exit 2
fi

declare -a SCAN_TARGETS=()
if [[ ${#EXPLICIT_PATHS[@]} -gt 0 ]]; then
  for p in "${EXPLICIT_PATHS[@]}"; do
    if [[ -e "$p" ]]; then
      SCAN_TARGETS+=("$p")
    else
      echo "ERROR: PATH does not exist: $p" >&2
      exit 2
    fi
  done
else
  for root in "${DEFAULT_SCAN_ROOTS[@]}"; do
    [[ -d "$REPO_ROOT/$root" ]] && SCAN_TARGETS+=("$REPO_ROOT/$root")
  done
fi

# Honest file count for the scope report (§11.4.6 — never a fabricated number).
count_files() {
  local target="$1" name prune=()
  if [[ -f "$target" ]]; then echo 1; return 0; fi
  for name in $SCAN_EXCLUDE; do prune+=(-o -name "$name"); done
  find "$target" \( "${prune[@]:1}" \) -prune -o -type f -name "$SCAN_GLOB" -print | wc -l
}

TOTAL_FILES=0
for t in "${SCAN_TARGETS[@]}"; do
  TOTAL_FILES=$(( TOTAL_FILES + $(count_files "$t") ))
done

echo "$SCRIPT_NAME — CM-TEST-MOCK-PID-EXPLICIT-INT static pre-build gate"
echo "  engine: constitution/scripts/gates/cm_test_mock_pid_explicit_int.sh (by reference, §11.4.177)"
if [[ ${#EXPLICIT_PATHS[@]} -gt 0 ]]; then
  echo "  scope: explicit path(s): ${EXPLICIT_PATHS[*]}"
else
  echo "  scope: default (${DEFAULT_SCAN_ROOTS[*]}), repo-root: $REPO_ROOT"
fi
echo "  files scanned: $TOTAL_FILES"
if [[ $VERBOSE -eq 1 ]]; then
  echo "  note: the shared engine reports violations only; it has no"
  echo "        per-skip diagnostic stream, so -v adds no extra detail here."
fi
echo

FINDINGS_FILE="$(mktemp)"
ENGINE_OUT="$(mktemp)"
trap 'rm -f "$FINDINGS_FILE" "$ENGINE_OUT"' EXIT
: > "$FINDINGS_FILE"

worst_rc=0
for target in "${SCAN_TARGETS[@]}"; do
  set +e
  MOCK_PID_GUARD_GLOB="$SCAN_GLOB" MOCK_PID_GUARD_EXCLUDE="$SCAN_EXCLUDE" \
    bash "$CONST_GATE" --root "$target" --quiet > "$ENGINE_OUT" 2>&1
  rc=$?
  set -e
  if [[ $rc -eq 2 ]]; then
    cat "$ENGINE_OUT" >&2
    exit 2
  fi
  if [[ $rc -ne 0 ]]; then
    worst_rc=1
    grep -E 'FAIL —' "$ENGINE_OUT" | grep -vE 'FAIL — [0-9]+ mock' >> "$FINDINGS_FILE" || true
  fi
done

if [[ $worst_rc -ne 0 ]]; then
  echo "=== FINDINGS ===" >&2
  cat "$FINDINGS_FILE" >&2
  echo >&2
  count="$(wc -l < "$FINDINGS_FILE" | tr -d ' ')"
  echo "FAIL: $count unguarded test process-mock pid hit(s) (CM-TEST-MOCK-PID-EXPLICIT-INT, BOB-126)" >&2
  exit 1
fi

echo "PASS: CM-TEST-MOCK-PID-EXPLICIT-INT clean across $TOTAL_FILES file(s)"
exit 0
