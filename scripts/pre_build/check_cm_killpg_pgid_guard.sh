#!/usr/bin/env bash
# check_cm_killpg_pgid_guard.sh — CM-KILLPG-PGID-GUARD static pre-build gate
# (§11.4.263), consumed BY REFERENCE from the constitution submodule.
#
# Purpose:
#   Statically detect process-group signal calls (Python `os.killpg(...)` /
#   `os.kill(-pid, ...)`, the shell negated-target and process-group forms)
#   that are NOT preceded by a guard proving the target identifier is a real
#   process id greater than 1. The defect class this closes is the BOB-126
#   forensic anchor: signalling process group 1 is, under glibc, identical to
#   broadcasting the signal to every process the caller's UID owns — the root
#   cause of 7 forced logouts (BOB-116/120/123/124/125/126).
#
# WHY THIS FILE IS THIN (§11.4.177 / §11.4.74):
#   The DETECTION ENGINE is universal and lives in the constitution submodule
#   at `constitution/scripts/gates/cm_killpg_pgid_guard.sh`. §11.4.177 mandates
#   shared tooling be consumed BY REFERENCE, never copied — a copy diverges
#   silently. This file is therefore a DELEGATOR: it owns only boba's
#   consumer-side SCOPE DATA (§11.4.35 — which roots, which extensions, which
#   excludes, which guard-proximity window) and hands every scan to the shared
#   engine. It contains NO detection logic of its own, so it cannot drift from
#   the engine.
#
#   The coverage boba's former local copy carried and the shared engine lacked
#   was UPSTREAMED into that engine first (§11.4.74 extend-don't-reimplement),
#   so delegating loses nothing: the literal shell broadcast-kill
#   (`kill -9 -1`), the signal-name negated-pgid form (`kill -TERM -"$pgid"`),
#   and the numeric-literal-target rule (a hardcoded pid/pgid can never be
#   cleared by a nearby unrelated bounds check) all now live in the engine.
#
# Usage:
#   check_cm_killpg_pgid_guard.sh                 # default scope (below)
#   check_cm_killpg_pgid_guard.sh PATH...         # explicit file(s)/dir(s)
#   check_cm_killpg_pgid_guard.sh -v              # verbose (show guarded hits)
#   check_cm_killpg_pgid_guard.sh --help
#
# Inputs:   optional PATH arguments; no stdin; no env input.
# Outputs:  scope/verdict lines on stdout; findings + FAIL summary on stderr.
# Side-effects: none (read-only scan; no process is ever signalled).
# Dependencies: bash, find, grep, awk, and the constitution submodule gate.
#
# Scope DATA (consumer-owned, §11.4.35):
#   roots      : download-proxy/src, plugins, scripts
#   extensions : py sh
#   excludes   : tests submodules constitution __pycache__ node_modules .git
#   window     : 10 preceding lines for guard proximity
#
#   The extension filter applies to the DEFAULT roots. An EXPLICITLY passed
#   file is scanned whatever its extension — a deliberate, documented
#   widening (§11.4.6, never silent): the shared engine also understands Go,
#   Rust and C process-group signal forms, so pointing this gate at such a
#   file now yields real coverage instead of a silent no-op.
#
# Verdict:
#   0 — PASS  (no unguarded process-group signal call under scan)
#   1 — FAIL  (one or more unguarded calls; each reported on stderr)
#   2 — ERROR (usage error, missing engine, or a PATH that does not exist)
#
# Cross-refs: §11.4.1 §11.4.6 §11.4.35 §11.4.69 §11.4.74 §11.4.107(10)
#             §11.4.108 §11.4.115 §11.4.135 §11.4.177 §11.4.196(D) §11.4.201
#             §11.4.226 §11.4.238 §11.4.263 §12.12.

set -euo pipefail

SCRIPT_NAME="check_cm_killpg_pgid_guard"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
CONST_GATE="$REPO_ROOT/constitution/scripts/gates/cm_killpg_pgid_guard.sh"

WINDOW=10
SCAN_EXT="py sh"
SCAN_EXCLUDE="tests submodules constitution __pycache__ node_modules .git"
DEFAULT_SCAN_ROOTS=("download-proxy/src" "plugins" "scripts")

VERBOSE=0
declare -a EXPLICIT_PATHS=()

print_help() { sed -n '2,52p' "${BASH_SOURCE[0]}"; }

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

# ------------------------------------------------------------------------
# Scan-target resolution (consumer-owned DATA only — no detection here)
# ------------------------------------------------------------------------
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
  local target="$1" name prune=() n
  if [[ -f "$target" ]]; then echo 1; return 0; fi
  for name in $SCAN_EXCLUDE; do prune+=(-o -name "$name"); done
  local -a exts=()
  local e first=1
  for e in $SCAN_EXT; do
    if [[ $first -eq 1 ]]; then first=0; else exts+=(-o); fi
    exts+=(-name "*.${e}")
  done
  n="$(find "$target" \( "${prune[@]:1}" \) -prune -o -type f \( "${exts[@]}" \) -print | wc -l)"
  echo "$n"
}

TOTAL_FILES=0
for t in "${SCAN_TARGETS[@]}"; do
  TOTAL_FILES=$(( TOTAL_FILES + $(count_files "$t") ))
done

echo "$SCRIPT_NAME — CM-KILLPG-PGID-GUARD static pre-build gate"
echo "  engine: constitution/scripts/gates/cm_killpg_pgid_guard.sh (by reference, §11.4.177)"
if [[ ${#EXPLICIT_PATHS[@]} -gt 0 ]]; then
  echo "  scope: explicit path(s): ${EXPLICIT_PATHS[*]}"
else
  echo "  scope: default (${DEFAULT_SCAN_ROOTS[*]}), repo-root: $REPO_ROOT"
fi
echo "  window: $WINDOW lines"
echo "  files scanned: $TOTAL_FILES"
echo

FINDINGS_FILE="$(mktemp)"
ENGINE_OUT="$(mktemp)"
trap 'rm -f "$FINDINGS_FILE" "$ENGINE_OUT"' EXIT
: > "$FINDINGS_FILE"

worst_rc=0
for target in "${SCAN_TARGETS[@]}"; do
  set +e
  if [[ $VERBOSE -eq 1 ]]; then
    KILLPG_GUARD_EXT="$SCAN_EXT" KILLPG_GUARD_EXCLUDE="$SCAN_EXCLUDE" \
      bash "$CONST_GATE" --root "$target" --window "$WINDOW" > "$ENGINE_OUT" 2>&1
  else
    KILLPG_GUARD_EXT="$SCAN_EXT" KILLPG_GUARD_EXCLUDE="$SCAN_EXCLUDE" \
      bash "$CONST_GATE" --root "$target" --window "$WINDOW" --quiet > "$ENGINE_OUT" 2>&1
  fi
  rc=$?
  set -e

  if [[ $rc -eq 2 ]]; then
    cat "$ENGINE_OUT" >&2
    exit 2
  fi
  [[ $VERBOSE -eq 1 ]] && grep -E 'PASS — guarded' "$ENGINE_OUT" || true
  if [[ $rc -ne 0 ]]; then
    worst_rc=1
    grep -E 'FAIL —' "$ENGINE_OUT" | grep -vE 'FAIL — [0-9]+ unguarded' >> "$FINDINGS_FILE" || true
  fi
done

if [[ $worst_rc -ne 0 ]]; then
  echo "=== FINDINGS ===" >&2
  cat "$FINDINGS_FILE" >&2
  echo >&2
  count="$(wc -l < "$FINDINGS_FILE" | tr -d ' ')"
  echo "FAIL: $count unguarded process-group signal hit(s) (CM-KILLPG-PGID-GUARD, BOB-126)" >&2
  exit 1
fi

echo "PASS: CM-KILLPG-PGID-GUARD clean across $TOTAL_FILES file(s)"
exit 0
