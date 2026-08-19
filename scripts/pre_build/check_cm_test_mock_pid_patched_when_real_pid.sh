#!/usr/bin/env bash
# check_cm_test_mock_pid_patched_when_real_pid.sh —
# CM-TEST-MOCK-PID-PATCHED-WHEN-REAL-PID static pre-build gate.
#
# Purpose (BOB-127 follow-up, Task 8 syscall-audit recommendation #1,
#   §11.4.238 discovery-channel-escape closure — adjacent-class sibling
#   of CM-TEST-MOCK-PID-EXPLICIT-INT / CM-KILLPG-PGID-GUARD):
#   Statically detect TEST files that construct a subprocess-shaped
#   `AsyncMock()` / `MagicMock()` (identified with the SAME detection
#   shape as CM-TEST-MOCK-PID-EXPLICIT-INT: an explicit
#   `.returncode = None` marker plus a nearby process-lifecycle
#   indicator — see "Detection design" below), set an EXPLICIT
#   integer-literal `.pid = <int>` on it (the sanctioned CM-TEST-MOCK-
#   PID-EXPLICIT-INT hardening pattern), but never neutralise the
#   dangerous syscall by patching `os.killpg` specifically.
#
#   The defect class this closes: satisfying the CM-TEST-MOCK-PID-
#   EXPLICIT-INT gate (an explicit real `int > 1` pid) is NECESSARY but
#   NOT SUFFICIENT — the production code's `isinstance(_pid, int) and
#   _pid > 1` guard is satisfied by ANY real positive int, so the code
#   proceeds past the guard and calls the REAL `os.getpgid(<pid>)` and,
#   if that resolves, the REAL `os.killpg(<pgid>, SIGKILL)` against
#   whatever process/process-group happens to own that literal,
#   hardcoded, non-test-owned PID on the host actually running the
#   test. `os.killpg(1, ...)` (pgid resolves to 1) is astronomically
#   unlikely from a real, non-`MagicMock`-derived pid, so this is not
#   the CATASTROPHIC broadcast-kill class CM-KILLPG-PGID-GUARD /
#   CM-TEST-MOCK-PID-EXPLICIT-INT close — but PID reuse on Linux
#   (`pid_max` 32768 by default, lower on many container/desktop
#   configs) means a hardcoded literal PID CAN legitimately belong to a
#   live, unrelated process at test-run time, especially on a
#   long-running dev host with many processes — exactly the operator's
#   environment where the BOB-126 incidents happened. If that
#   collision occurs, an unpatched test fires a real `SIGKILL` at a
#   real, unrelated process group: collateral damage from a "unit"
#   test.
#
#   This was found by Task 8's syscall audit
#   (`.superpowers/sdd/task-8-syscall-audit.md`, DANGEROUS findings #1
#   and #2) as two live hits in
#   `tests/unit/merge_service/test_public_tracker_subprocess_timeout.py`
#   (`proc.pid = 12345` / `proc.pid = 1111`, neither patching
#   `os.killpg`/`os.getpgid`) and fixed at commit 8bedc5a by copying the
#   already-correct pattern from the third test in the same file
#   (`test_process_group_kill_called_on_deadline`, `proc.pid = 9999`,
#   which DOES patch both `_search.os.getpgid` and `_search.os.killpg`).
#   This gate makes that "explicit pid ⇒ ALSO patch os.killpg" pairing
#   a mechanically-enforced invariant instead of tribal knowledge, per
#   §11.4.226 (evidence-class-at-closure) and §11.4.240/§11.4.249 (an
#   independent, structurally separate check, never the fix's own
#   author-supplied oracle).
#
# Detection design (shares its precondition with CM-TEST-MOCK-PID-
#   EXPLICIT-INT — see that gate's own header for the full evidence
#   trail proving `.returncode = None` is the correct, non-guessed
#   reachability precondition for search.py's kill branch):
#
#   1. A bare-variable assignment `<ident> = AsyncMock()` or
#      `<ident> = MagicMock()` on its own line (the process-standin
#      object itself).
#   2. Within the 20 lines immediately AFTER that assignment (the
#      "forward window"), the SAME identifier carries ALL of:
#        a. an explicit `<ident>.returncode = None` assignment
#           (REQUIRED precondition — a mock whose `.returncode` is
#           left unset or set to a real exit code can never reach the
#           kill branch at all — see CM-TEST-MOCK-PID-EXPLICIT-INT's
#           header for the proof), AND
#        b. at least one process-lifecycle/streaming indicator:
#           `<ident>.stdout.readline`, `<ident>.stderr.read`,
#           `<ident>.wait`, `<ident>.kill`, AND
#        c. an explicit `<ident>.pid = <int-literal>` assignment (a
#           positive or negative integer literal — THIS is what
#           distinguishes this gate's scope from CM-TEST-MOCK-PID-
#           EXPLICIT-INT: a mock with NO pid-literal at all is that
#           sibling gate's job, not this one, and is silently skipped
#           here).
#   3. The identifier does NOT carry a real (non-comment) patch of
#      `os.killpg` SPECIFICALLY within 30 lines before OR after the
#      mock-assignment line (see "os.killpg-targeting exemption"
#      below) — narrower than CM-TEST-MOCK-PID-EXPLICIT-INT's
#      exemption, which accepts a patch of ANY module's attribute
#      literally named "killpg". That looser match is safe for THAT
#      gate's threat model (mock coerces to 1 — any real patch of
#      *something* called "killpg" nearby is corroborating evidence a
#      human deliberately neutralised the call), but is NOT safe here:
#      this gate's whole point is verifying the syscall the code
#      ACTUALLY reaches (`os.killpg`, imported as `os` inside
#      `merge_service.search`, i.e. `<qualifier>.os.killpg` /
#      `os.killpg`) is neutralised — a patch of some unrelated
#      `some_other_module.killpg` attribute does nothing to stop the
#      real `os.killpg` call and MUST NOT exempt a hit (§11.4.201
#      false-positive/false-negative-refusal discipline: an exemption
#      regex broad enough to accept an irrelevant patch is itself a
#      §11.4 PASS-bluff at the gate layer).
#
# os.killpg-targeting exemption (the narrowing that distinguishes this
#   gate from CM-TEST-MOCK-PID-EXPLICIT-INT's looser sibling check):
#   A hit is SKIPPED (not flagged) when a REAL (non-comment) line
#   within 30 lines before OR after the mock-assignment line matches
#   ONE of:
#     - `patch("<optional-dotted-prefix.>os.killpg")` /
#       `patch('<optional-dotted-prefix.>os.killpg')` — the
#       string-literal patch-target form, where the last two dotted
#       segments of the target string are exactly `os.killpg` (so
#       `patch("os.killpg")` and `patch("merge_service.os.killpg")`
#       both count, but `patch("some_other_module.killpg")` does
#       NOT — there is no `os.` immediately before `killpg`).
#     - `patch.object(<optional-dotted-prefix.>os, "killpg")` /
#       `patch.object(<optional-dotted-prefix.>os, 'killpg')` — the
#       object-form patch, where the FIRST argument is either the bare
#       name `os` or a dotted attribute chain ENDING in `.os` (the
#       real-tree pattern this gate was written against:
#       `patch.object(_search.os, "killpg")`), and the second argument
#       is the string literal `killpg`.
#   Both forms require the literal token `os` immediately before
#   `.killpg` (string form) or as the exact final dotted segment
#   before the `,` (object form) — a target ending in some OTHER
#   identifier that merely happens to contain the substring "os" (e.g.
#   `chaos.killpg`) does NOT match, because the regex anchors `os` at
#   a `.`-or-start-of-token boundary, never a bare substring match.
#   A patch mentioned only inside a comment is explicitly NOT counted
#   — matching a MENTION of the pattern as if it were the pattern is
#   the carrier footgun §11.4.196(D)/§12.12/§11.4.201(6)-(7) name;
#   every candidate line is re-checked to exclude comment-only lines
#   before it counts.
#
# Scope (default, no PATH arguments given):
#   tests/**/*.py (relative to the repo root this script resolves from
#   its own location), walked recursively, EXCLUDING
#   `tests/pre_build/` (this gate's own meta-test lives there and
#   authors hermetic fixtures that are deliberately dangerous-shaped;
#   flagging them would be a false positive on the harness itself —
#   §11.4.201), `.venv/`, and any `__pycache__` subdirectory at any
#   depth.
#
# Explicit-path mode:
#   `check_cm_test_mock_pid_patched_when_real_pid.sh PATH...` scans
#   exactly the given file(s)/directory(ies) instead of the default
#   scope. This is how the paired meta-test
#   (tests/pre_build/test_check_cm_test_mock_pid_patched_when_real_pid.sh)
#   exercises the gate against hermetic golden-good/golden-bad
#   fixtures without touching the real tree.
#
# Verdict:
#   GREEN (exit 0) — zero unpatched real-pid-mock hits across every
#                     scanned file.
#   FAIL  (exit 1) — one or more unpatched hits; each reported as
#                     `<path>:<line>: <trimmed source> [identifier=...]`
#                     on stderr.
#   ERROR (exit 2) — usage/environment error (e.g. an explicit PATH
#                     argument does not exist).
#
# Side-effects: none. Read-only; creates one mktemp findings file for
#   its own run and removes it on exit via `trap ... EXIT`.
#
# Dependencies: bash ([[ ]], <<< here-strings, process substitution),
#   grep -E, sed -E, find, wc — all standard on the project's
#   supported hosts. No Python, no network access, no repository write
#   access.
#
# Cross-refs: §11.4.1 §11.4.6 §11.4.43 §11.4.69 §11.4.107(10) §11.4.108
#             §11.4.115 §11.4.135 §11.4.146(D3) §11.4.196(D) §11.4.201
#             §11.4.226 §11.4.238 §11.4.240 §11.4.249 §11.4.263 §12.12.

set -euo pipefail

SCRIPT_NAME="check_cm_test_mock_pid_patched_when_real_pid"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

FWD_WINDOW=20
KILLPG_WINDOW=30
DEFAULT_SCAN_ROOTS=("tests")
EXCLUDE_DIR_NAMES=("__pycache__" ".git" ".venv" "pre_build")

VERBOSE=0
declare -a EXPLICIT_PATHS=()

print_help() {
  sed -n '2,150p' "${BASH_SOURCE[0]}"
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

collect_files_under() {
  local root="$1"
  local -a prune=()
  local name
  for name in "${EXCLUDE_DIR_NAMES[@]}"; do
    prune+=(-o -name "$name")
  done
  find "$root" \( "${prune[@]:1}" \) -prune -o \
    -type f -name '*.py' -print
}

declare -a SCAN_FILES=()

if [[ ${#EXPLICIT_PATHS[@]} -gt 0 ]]; then
  for p in "${EXPLICIT_PATHS[@]}"; do
    if [[ -f "$p" ]]; then
      case "$p" in
        *.py) SCAN_FILES+=("$p") ;;
        *) : ;; # not a scanned extension — silently out of scope
      esac
    elif [[ -d "$p" ]]; then
      while IFS= read -r f; do
        SCAN_FILES+=("$f")
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
      SCAN_FILES+=("$f")
    done < <(collect_files_under "$full")
  done
fi

# ------------------------------------------------------------------------
# Detection
# ------------------------------------------------------------------------

FINDINGS_FILE="$(mktemp)"
: > "$FINDINGS_FILE"
trap 'rm -f "$FINDINGS_FILE"' EXIT

report_fail() {
  echo "FAIL: $*" >> "$FINDINGS_FILE"
}

is_comment_only_line() {
  local content="$1"
  [[ "$content" =~ ^[[:space:]]*# ]]
}

# os_killpg_patch_in_window <file> <center-line> <radius>
#   Returns 0 iff a NON-comment line within [center-radius, center+radius]
#   real-patches `os.killpg` SPECIFICALLY (see "os.killpg-targeting
#   exemption" in the header comment above) — string-literal form
#   `patch("<...>os.killpg")` OR object form
#   `patch.object(<...>os, "killpg")`.
os_killpg_patch_in_window() {
  local file="$1" center="$2" radius="$3"
  local wstart wend
  wstart=$(( center - radius ))
  if (( wstart < 1 )); then wstart=1; fi
  wend=$(( center + radius ))
  local total_lines
  total_lines="$(wc -l < "$file" | tr -d ' ')"
  if (( wend > total_lines )); then wend="$total_lines"; fi

  local content
  # String-literal form: patch("...os.killpg") / patch('...os.killpg').
  # The dotted-prefix group is OPTIONAL and, if present, is itself a
  # sequence of `<ident>.` segments — so the LITERAL substring
  # immediately before "killpg" inside the quotes is always "os.".
  local -r str_form_re="patch\\([[:space:]]*[\"']([A-Za-z_][A-Za-z0-9_]*\\.)*os\\.killpg[\"']"
  # Object form: patch.object(...os, "killpg") / patch.object(...os, 'killpg').
  # The dotted-prefix group is likewise optional; the token immediately
  # before the comma is always exactly "os".
  local -r obj_form_re="patch\\.object\\([[:space:]]*([A-Za-z_][A-Za-z0-9_]*\\.)*os[[:space:]]*,[[:space:]]*[\"']killpg[\"']"

  while IFS= read -r content; do
    if is_comment_only_line "$content"; then
      continue
    fi
    if [[ "$content" =~ $str_form_re ]] || [[ "$content" =~ $obj_form_re ]]; then
      return 0
    fi
  done < <(sed -n "${wstart},${wend}p" "$file")

  return 1
}

process_file() {
  local file="$1"
  local total_lines
  total_lines="$(wc -l < "$file" | tr -d ' ')"

  local hits
  hits="$(grep -nE '^[[:space:]]*[A-Za-z_][A-Za-z0-9_]*[[:space:]]*=[[:space:]]*(Async|Magic)Mock\(\)[[:space:]]*$' "$file" 2>/dev/null || true)"
  [[ -n "$hits" ]] || return 0

  while IFS= read -r hitline; do
    [[ -n "$hitline" ]] || continue
    local lineno content ident
    lineno="${hitline%%:*}"
    content="${hitline#*:}"

    ident="$(printf '%s\n' "$content" | sed -nE 's/^[[:space:]]*([A-Za-z_][A-Za-z0-9_]*)[[:space:]]*=.*/\1/p')"
    [[ -n "$ident" ]] || continue

    local wstart wend window
    wstart=$(( lineno + 1 ))
    wend=$(( lineno + FWD_WINDOW ))
    if (( wend > total_lines )); then wend="$total_lines"; fi
    if (( wstart > wend )); then
      window=""
    else
      window="$(sed -n "${wstart},${wend}p" "$file")"
    fi

    # (2a) REQUIRED precondition: <ident>.returncode = None within window
    # — a mock whose .returncode never reaches "still running" can never
    # reach the kill branch at all (see CM-TEST-MOCK-PID-EXPLICIT-INT's
    # header for the full evidence trail proving this precondition).
    local returncode_none_re
    returncode_none_re="${ident}\\.returncode[[:space:]]*=[[:space:]]*None\\b"
    if ! grep -qE "$returncode_none_re" <<<"$window"; then
      if [[ $VERBOSE -eq 1 ]]; then
        echo "  skip (no returncode=None): $file:$lineno [identifier=$ident]"
      fi
      continue
    fi

    # (2b) at least one process-lifecycle/streaming indicator.
    local lifecycle_re
    lifecycle_re="${ident}\\.stdout\\.readline|${ident}\\.stderr\\.read|${ident}\\.wait\\b|${ident}\\.kill\\b"
    if ! grep -qE "$lifecycle_re" <<<"$window"; then
      if [[ $VERBOSE -eq 1 ]]; then
        echo "  skip (no lifecycle indicator): $file:$lineno [identifier=$ident]"
      fi
      continue
    fi

    # (2c) THE SCOPE-DEFINING PRECONDITION for THIS gate (distinct from
    # CM-TEST-MOCK-PID-EXPLICIT-INT, which flags the ABSENCE of this
    # assignment): an explicit `<ident>.pid = <int-literal>` MUST be
    # present, or this mock is entirely out of scope here — a mock with
    # no pid-literal at all is CM-TEST-MOCK-PID-EXPLICIT-INT's job, not
    # this gate's, and is silently skipped (never double-flagged).
    local pid_re
    pid_re="${ident}\\.pid[[:space:]]*=[[:space:]]*-?[0-9]+"
    if ! grep -qE "$pid_re" <<<"$window"; then
      if [[ $VERBOSE -eq 1 ]]; then
        echo "  skip (no pid-literal — CM-TEST-MOCK-PID-EXPLICIT-INT's scope): $file:$lineno [identifier=$ident]"
      fi
      continue
    fi

    # (3) os.killpg-targeting exemption.
    if os_killpg_patch_in_window "$file" "$lineno" "$KILLPG_WINDOW"; then
      if [[ $VERBOSE -eq 1 ]]; then
        echo "  exempt (os.killpg-patched nearby): $file:$lineno [identifier=$ident]"
      fi
      continue
    fi

    local trimmed
    trimmed="$(printf '%s' "$content" | sed -E 's/^[[:space:]]+//')"
    report_fail "$file:$lineno: real-pid subprocess-mock with NO os.killpg-targeting patch — $trimmed [identifier=$ident] (has \`${ident}.pid = <int>\` but no \`os.killpg\`-targeting patch within $KILLPG_WINDOW lines; see test_process_group_kill_called_on_deadline in tests/unit/merge_service/test_public_tracker_subprocess_timeout.py for the sanctioned fix pattern)"
  done <<<"$hits"
}

echo "$SCRIPT_NAME — CM-TEST-MOCK-PID-PATCHED-WHEN-REAL-PID static pre-build gate"
if [[ ${#EXPLICIT_PATHS[@]} -gt 0 ]]; then
  echo "  scope: explicit path(s): ${EXPLICIT_PATHS[*]}"
else
  echo "  scope: default (${DEFAULT_SCAN_ROOTS[*]}, excluding tests/pre_build/), repo-root: $REPO_ROOT"
fi
echo "  forward window: $FWD_WINDOW lines; os.killpg-exemption window: ±$KILLPG_WINDOW lines"
echo "  files scanned: ${#SCAN_FILES[@]}"
echo

for file in "${SCAN_FILES[@]}"; do
  process_file "$file"
done

if [[ -s "$FINDINGS_FILE" ]]; then
  echo "=== FINDINGS ===" >&2
  cat "$FINDINGS_FILE" >&2
  echo >&2
  count="$(wc -l < "$FINDINGS_FILE" | tr -d ' ')"
  echo "FAIL: $count unpatched real-pid test-subprocess-mock hit(s) (CM-TEST-MOCK-PID-PATCHED-WHEN-REAL-PID, BOB-127)" >&2
  exit 1
fi

echo "PASS: CM-TEST-MOCK-PID-PATCHED-WHEN-REAL-PID clean across ${#SCAN_FILES[@]} file(s)"
exit 0
