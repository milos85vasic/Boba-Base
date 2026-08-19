#!/usr/bin/env bash
# check_cm_killpg_pgid_guard.sh — CM-KILLPG-PGID-GUARD static pre-build gate.
#
# Purpose (BOB-126 follow-up, §11.4.238 discovery-channel-escape closure):
#   Statically detect calls that send a signal to a NEGATIVE pid or an
#   entire process GROUP (Python `os.killpg(pgid, sig)`, `os.kill(-pid,
#   sig)`; the bash `killpg` word / an explicit `kill -SIG` invocation)
#   that are NOT preceded, within the 10 lines above the call, by a
#   guard proving the target identifier is a real, positive process id:
#   `isinstance(<ident>, int)` AND `<ident> > 1` on that SAME identifier.
#
#   The defect class this closes: `os.killpg(1, SIGKILL)` is, under
#   glibc, IDENTICAL to `kill(-1, SIGKILL)` — a broadcast kill of every
#   process the caller's UID owns. A test double whose `.pid` attribute
#   is an un-configured mock object (`__int__` defaults to 1 on such
#   doubles) silently reaches that call, which is exactly the root
#   cause the operator's forensic writeup traced across 7 forced
#   logouts (BOB-116/120/123/124/125/126). The fix landed as a guard
#   requiring the id to be a real `int` greater than 1 immediately
#   before the dangerous call (search.py:1200-1240) — this gate makes
#   that shape a mechanically-enforced invariant instead of tribal
#   knowledge (§11.4.226 evidence-class-at-closure: a source-only fix
#   with no standing guard is exactly the class that silently reopens).
#
# Scope (default, no PATH arguments given):
#   download-proxy/src/, plugins/, scripts/  (relative to the repo root
#   this script resolves from its own location), walked recursively,
#   EXCLUDING any `tests/`, `submodules/`, `constitution/`, or
#   `__pycache__/` subdirectory at any depth. Only `*.py` and `*.sh`
#   files are considered. This gate script's OWN source file is always
#   excluded from its own scan — a structural self-exclusion, not a
#   wording trick, closing the §11.4.196(D)/§12.12 "instrument matches
#   its own carrier text" footgun class (this file necessarily quotes
#   the very patterns it greps for).
#
# Explicit-path mode:
#   `check_cm_killpg_pgid_guard.sh PATH...` scans exactly the given
#   file(s)/directory(ies) instead of the default scope (directories
#   are still walked with the same tests/submodules/constitution/
#   __pycache__ excludes). This is how the paired meta-test
#   (tests/pre_build/test_check_cm_killpg_pgid_guard.sh) exercises the
#   gate against hermetic golden-good/golden-bad fixtures without
#   touching the real tree.
#
# Detection patterns:
#   Python (*.py):  os\.killpg\(          os\.kill\(\s*-
#   Bash   (*.sh):  killpg\s              kill\s+-[1-9][0-9]*\b
#
#   The bash signal-kill pattern deliberately requires a NONZERO digit
#   (excludes `-0`). `kill -0 PID` delivers no signal at all (see
#   kill(2)) — it is the standard POSIX liveness PROBE idiom ("is this
#   process still alive?"), used unguarded twice in this repo today
#   (scripts/system-slice-watchdog/user1000-watchdog.sh,
#   scripts/tunnel-keepalive.sh) and structurally incapable of ever
#   becoming the BOB-126 broadcast-kill defect, since it never
#   delivers a real signal regardless of what pid/pgid it targets.
#   Flagging it would be a false-positive refusal on known-safe code
#   (§11.4.201 — a FAIL-bluff exactly as forbidden as a PASS-bluff);
#   this narrowing is a documented, evidence-based decision (§11.4.6),
#   not a silent omission.
#
#   A line that is ENTIRELY a comment (starts with `#`, after optional
#   leading whitespace) is never treated as a call site — comments that
#   quote the dangerous syntax while documenting the fix (search.py has
#   two such lines) are text, not code, and must not be flagged.
#
# Guard recognition:
#   For each real (non-comment) hit, the target identifier is extracted
#   from the call itself (the first argument to killpg(, or the name
#   after the leading `-` in kill(-, or the token following killpg /
#   the signal-kill call in bash). The identifier may be a simple bare
#   name OR a dotted-attribute chain (e.g. `self._pgid`) — both are
#   captured in full and matched literally (any `.` in the captured
#   identifier is regex-escaped before use, so it never behaves as an
#   "any character" wildcard). The 10 lines immediately preceding the
#   hit are then checked for BOTH, on that SAME identifier:
#     - isinstance(<ident>, int)
#     - <ident> > 1              (exactly `1`; `> 0`, `> 10`, ... do
#                                  NOT count — a pgid/pid of 1 is
#                                  precisely the broadcast-kill value)
#   present anywhere in that window (same line or different lines).
#
#   When the call's target does NOT start with an identifier character
#   (a literal or numeric target — e.g. the BOB-126 defect shape itself,
#   `os.killpg(1, ...)` / bash `kill -9 -1`), no identifier can be
#   extracted at all, and the call is ALWAYS treated as UNGUARDED. There
#   is NO non-identifier-scoped fallback scan. An earlier revision of
#   this gate fell back, in that case, to an unscoped "any
#   isinstance(..., int) plus any > 1 anywhere in the window" check —
#   which is a false-negative PASS-bluff (§11.4.201): a literal
#   broadcast-kill target sitting near ANY unrelated int-bounds guard
#   for a completely different variable (even inside a comment) was
#   misreported as guarded. Refusing to guess when no identifier can be
#   isolated is the conservative-safe default (§11.4.101/§11.4.201).
#   Note that a nested call expression such as `os.killpg(get_pgid(),
#   sig)` does NOT hit this identifier-less path: its target starts
#   with an identifier character, so the function name `get_pgid` is
#   captured and used (mis-scoped, but non-empty) as the identifier —
#   only a genuinely identifier-less (literal/numeric) target reaches
#   the always-unguarded path.
#
# Verdict:
#   GREEN (exit 0) — zero unguarded hits across every scanned file.
#   FAIL  (exit 1) — one or more unguarded hits; each reported as
#                     `<path>:<line>: <trimmed source> [identifier=...]`
#                     on stderr.
#   ERROR (exit 2) — usage/environment error (e.g. an explicit PATH
#                     argument does not exist).
#
# Cross-refs: §11.4.1 §11.4.6 §11.4.43 §11.4.69 §11.4.107(10) §11.4.108
#             §11.4.115 §11.4.135 §11.4.146(D3) §11.4.196(D) §11.4.201
#             §11.4.226 §11.4.238 §12.12.

set -euo pipefail

SCRIPT_NAME="check_cm_killpg_pgid_guard"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SELF_PATH="$SCRIPT_DIR/$(basename "${BASH_SOURCE[0]}")"

WINDOW=10
DEFAULT_SCAN_ROOTS=("download-proxy/src" "plugins" "scripts")
EXCLUDE_DIR_NAMES=("tests" "submodules" "constitution" "__pycache__" "node_modules" ".git")

VERBOSE=0
declare -a EXPLICIT_PATHS=()

print_help() {
  sed -n '2,71p' "${BASH_SOURCE[0]}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      print_help
      exit 0
      ;;
    -v|--verbose)
      VERBOSE=1
      shift
      ;;
    --)
      shift
      while [[ $# -gt 0 ]]; do
        EXPLICIT_PATHS+=("$1")
        shift
      done
      ;;
    -*)
      echo "ERROR: unknown argument: $1" >&2
      exit 2
      ;;
    *)
      EXPLICIT_PATHS+=("$1")
      shift
      ;;
  esac
done

# ------------------------------------------------------------------------
# File collection
# ------------------------------------------------------------------------

# Emits a `find` pruning expression that skips every named directory
# (at any depth) before it emits the *.py / *.sh files under $1.
collect_files_under() {
  local root="$1"
  local -a prune=()
  local name
  for name in "${EXCLUDE_DIR_NAMES[@]}"; do
    prune+=(-o -name "$name")
  done
  # Drop the leading "-o" so the group starts with a bare -name test.
  find "$root" \( "${prune[@]:1}" \) -prune -o \
    -type f \( -name '*.py' -o -name '*.sh' \) -print
}

declare -a ALL_FILES=()

if [[ ${#EXPLICIT_PATHS[@]} -gt 0 ]]; then
  for p in "${EXPLICIT_PATHS[@]}"; do
    if [[ -f "$p" ]]; then
      case "$p" in
        *.py|*.sh) ALL_FILES+=("$p") ;;
        *) : ;; # not a scanned extension — silently out of scope
      esac
    elif [[ -d "$p" ]]; then
      while IFS= read -r f; do
        ALL_FILES+=("$f")
      done < <(collect_files_under "$p")
    else
      echo "ERROR: PATH does not exist: $p" >&2
      exit 2
    fi
  done
else
  for root in "${DEFAULT_SCAN_ROOTS[@]}"; do
    full="$REPO_ROOT/$root"
    if [[ ! -d "$full" ]]; then
      continue
    fi
    while IFS= read -r f; do
      ALL_FILES+=("$f")
    done < <(collect_files_under "$full")
  done
fi

# Structural self-exclusion (§11.4.196(D)/§12.12 carrier-match guard):
# this gate's own source necessarily quotes the patterns it detects.
declare -a SCAN_FILES=()
for f in "${ALL_FILES[@]}"; do
  abs_f="$(cd "$(dirname "$f")" && pwd)/$(basename "$f")"
  if [[ "$abs_f" == "$SELF_PATH" ]]; then
    continue
  fi
  SCAN_FILES+=("$f")
done

# ------------------------------------------------------------------------
# Detection + guard-recognition
# ------------------------------------------------------------------------

FINDINGS_FILE="$(mktemp)"
: > "$FINDINGS_FILE"
trap 'rm -f "$FINDINGS_FILE"' EXIT

report_fail() {
  echo "FAIL: $*" >> "$FINDINGS_FILE"
}

# extract_ident <kind> <line-content>
#   kind: py_killpg | py_kill_neg | sh_killpg | sh_kill_sig
#   Prints the extracted identifier, or nothing if it could not be
#   isolated as a [A-Za-z_][A-Za-z0-9_.]* token (a bare name OR a
#   dotted-attribute chain such as `self._pgid` — Important-2 fix: an
#   earlier revision stopped at the first `.`, mis-extracting `self`
#   as the identifier and falsely flagging correctly-guarded
#   attribute-stored pid/pgid calls as unguarded). Nothing is printed
#   for a literal/numeric target (e.g. `1`), since it does not start
#   with an identifier character — that is intentional; see the
#   "Guard recognition" header comment above for how the caller treats
#   an empty extraction.
extract_ident() {
  local kind="$1" content="$2"
  case "$kind" in
    py_killpg)
      printf '%s\n' "$content" | sed -nE \
        's/.*os\.killpg\([[:space:]]*([A-Za-z_][A-Za-z0-9_.]*).*/\1/p'
      ;;
    py_kill_neg)
      printf '%s\n' "$content" | sed -nE \
        's/.*os\.kill\([[:space:]]*-[[:space:]]*([A-Za-z_][A-Za-z0-9_.]*).*/\1/p'
      ;;
    sh_killpg)
      printf '%s\n' "$content" | sed -nE \
        's/.*killpg[[:space:]]+\$?\{?([A-Za-z_][A-Za-z0-9_.]*).*/\1/p'
      ;;
    sh_kill_sig)
      printf '%s\n' "$content" | sed -nE \
        's/.*kill[[:space:]]+-[1-9][0-9]*[[:space:]]+-?\$?\{?"?([A-Za-z_][A-Za-z0-9_.]*).*/\1/p'
      ;;
  esac
}

# is_guarded <window-text> <ident-or-empty>
#   Returns 0 (guarded) iff the window contains BOTH
#   isinstance(<ident>, int) AND <ident> > 1 (literal 1, never a longer
#   number) on the SAME identifier. Uses grep -q so it is safe as an
#   `if` condition under `set -e`.
#
#   CRITICAL (§11.4.201 false-negative fix): when no identifier could
#   be extracted from the call (empty $2 — a literal/numeric target,
#   e.g. `os.killpg(1, ...)`, which is the BOB-126 defect shape
#   itself), this function returns 1 (unguarded) IMMEDIATELY. There is
#   NO non-identifier-scoped fallback scan of the window. A prior
#   revision fell back to an unscoped "any isinstance(..., int) + any
#   > 1 anywhere in the window" match in this case, which reported a
#   literal broadcast-kill target as "guarded" whenever ANY unrelated
#   int-bounds guard for a totally different variable happened to sit
#   in the preceding 10 lines (even inside a comment) — a
#   false-negative PASS on the exact defect class this gate exists to
#   catch. Refusing to guess on an identifier-less target is the
#   conservative-safe default per §11.4.101/§11.4.201.
is_guarded() {
  local window="$1" ident="$2"
  [[ -n "$ident" ]] || return 1
  local ident_re isinstance_re gt1_re
  # Escape any literal `.` in a dotted-attribute identifier (e.g.
  # `self._pgid`) so it matches itself, not "any character", inside
  # the ERE patterns below.
  ident_re="${ident//./\\.}"
  isinstance_re="isinstance\\([[:space:]]*${ident_re}[[:space:]]*,[[:space:]]*int[[:space:]]*\\)"
  gt1_re="${ident_re}[[:space:]]*>[[:space:]]*1([^0-9]|\$)"
  grep -qE "$isinstance_re" <<<"$window" && grep -qE "$gt1_re" <<<"$window"
}

is_comment_only_line() {
  local content="$1"
  [[ "$content" =~ ^[[:space:]]*# ]]
}

# process_hits <file> <pattern> <kind> <label>
process_hits() {
  local file="$1" pattern="$2" kind="$3" label="$4"
  local hits
  hits="$(grep -nE "$pattern" "$file" 2>/dev/null || true)"
  [[ -n "$hits" ]] || return 0

  while IFS= read -r hitline; do
    [[ -n "$hitline" ]] || continue
    local lineno content
    lineno="${hitline%%:*}"
    content="${hitline#*:}"

    if is_comment_only_line "$content"; then
      continue
    fi

    local ident
    ident="$(extract_ident "$kind" "$content")"

    local wstart wend window
    if (( lineno <= 1 )); then
      window=""
    else
      wend=$(( lineno - 1 ))
      if (( lineno > WINDOW + 1 )); then
        wstart=$(( lineno - WINDOW ))
      else
        wstart=1
      fi
      window="$(sed -n "${wstart},${wend}p" "$file")"
    fi

    if is_guarded "$window" "$ident"; then
      if [[ $VERBOSE -eq 1 ]]; then
        echo "  guarded: $file:$lineno [identifier=${ident:-none}]"
      fi
      continue
    fi

    local trimmed
    trimmed="$(printf '%s' "$content" | sed -E 's/^[[:space:]]+//')"
    report_fail "$file:$lineno: unguarded $label — $trimmed [identifier=${ident:-none}]"
  done <<<"$hits"
}

echo "$SCRIPT_NAME — CM-KILLPG-PGID-GUARD static pre-build gate"
if [[ ${#EXPLICIT_PATHS[@]} -gt 0 ]]; then
  echo "  scope: explicit path(s): ${EXPLICIT_PATHS[*]}"
else
  echo "  scope: default (${DEFAULT_SCAN_ROOTS[*]}), repo-root: $REPO_ROOT"
fi
echo "  window: $WINDOW lines"
echo "  files scanned: ${#SCAN_FILES[@]}"
echo

for file in "${SCAN_FILES[@]}"; do
  case "$file" in
    *.py)
      process_hits "$file" 'os\.killpg\(' py_killpg "os.killpg( call"
      process_hits "$file" 'os\.kill\(\s*-' py_kill_neg "os.kill(-pid, ...) call"
      ;;
    *.sh)
      process_hits "$file" 'killpg\s' sh_killpg "killpg call"
      process_hits "$file" 'kill\s+-[1-9][0-9]*\b' sh_kill_sig "kill -SIG call"
      ;;
  esac
done

if [[ -s "$FINDINGS_FILE" ]]; then
  echo "=== FINDINGS ===" >&2
  cat "$FINDINGS_FILE" >&2
  echo >&2
  count="$(wc -l < "$FINDINGS_FILE" | tr -d ' ')"
  echo "FAIL: $count unguarded killpg/kill-group hit(s) (CM-KILLPG-PGID-GUARD, BOB-126)" >&2
  exit 1
fi

echo "PASS: CM-KILLPG-PGID-GUARD clean across ${#SCAN_FILES[@]} file(s)"
exit 0
