#!/usr/bin/env bash
# check_cm_test_mock_pid_explicit_int.sh — CM-TEST-MOCK-PID-EXPLICIT-INT
# static pre-build gate.
#
# Purpose (BOB-126 follow-up, §11.4.238 discovery-channel-escape closure,
#   sibling of CM-KILLPG-PGID-GUARD which guards PRODUCTION code):
#   Statically detect TEST files that construct an `AsyncMock()` /
#   `MagicMock()` standing in for an `asyncio.subprocess.Process`
#   (identified by nearby `.stdout.readline`, `.stderr.read`, `.wait`,
#   `.kill` usage AND an explicit `.returncode = None` — see "Detection
#   design" below) but never explicitly set `.pid = <int>` on it and
#   never neutralise the destructive call by patching `os.killpg`.
#
#   The defect class this closes: an un-configured `unittest.mock`
#   object auto-generates every magic method, including `__int__` /
#   `__index__`, both defaulting to `1`. A test double standing in for
#   a real subprocess whose `.pid` attribute is left un-configured
#   therefore coerces to the integer `1` wherever production code reads
#   `int(proc.pid)` — and `os.killpg(os.getpgid(1), SIGKILL)` is,
#   under glibc, IDENTICAL to `kill(-1, SIGKILL)`: a broadcast kill of
#   every process the test-runner's UID owns. This is the exact root
#   cause the operator's forensic writeup traced across 7 forced
#   logouts (BOB-116/120/123/124/125/126); `download-proxy/src/
#   merge_service/search.py` now carries a production-side guard
#   (`isinstance(_pid, int) and _pid > 1`, mechanically enforced by the
#   sibling gate `scripts/pre_build/check_cm_killpg_pgid_guard.sh`), and
#   this gate makes the TEST-side half of the same hardening — never
#   relying on a mocked `.pid` that could coerce to `1` — a mechanically
#   enforced invariant instead of tribal knowledge, per §11.4.226
#   (evidence-class-at-closure: a fix proven only by one hardened test
#   is exactly the class that silently reopens the moment a DIFFERENT
#   test reuses the same unguarded mock shape) and per §11.4.240/§11.4.249
#   (a producer that also authors its own oracle is unverified — this
#   gate is the independent, structurally separate check).
#
# Detection design — WHY this gate requires an explicit
#   `<var>.returncode = None` marker (a narrowing beyond "any
#   subprocess-shaped mock", evidence-based per §11.4.6, NOT arbitrary):
#
#   Both call sites in search.py that can EVER reach `os.killpg` /
#   `os.getpgid` are lexically gated behind the SAME precondition:
#
#       if proc.returncode is None:
#           ...
#           _pid = proc.pid
#           if isinstance(_pid, int) and _pid > 1:
#               ...
#               os.killpg(_pgid, _signal.SIGKILL)
#
#   `proc.returncode is None` is the asyncio.subprocess convention for
#   "process still running" — it is the ONLY precondition under which
#   the cleanup/kill branch is reachable at all, with or without the
#   pid guard. A mock whose `.returncode` is left un-set (an
#   auto-generated `MagicMock` instance is not `is None`) or is
#   explicitly set to a real exit code (`0`, a positive int, or a
#   variable that defaults to one) can therefore NEVER reach the kill
#   branch — flagging such a mock for lacking `.pid = <int>` would be a
#   FALSE-POSITIVE refusal on code that is structurally incapable of
#   the BOB-126 defect (a §11.4.201 FAIL-bluff, forbidden exactly as a
#   PASS-bluff is). This was PROVEN by reading search.py directly
#   (§11.4.6 — not guessed) and cross-checked against every existing
#   `AsyncMock()`/`MagicMock()` subprocess-standin in `tests/**/*.py`
#   as of this gate's authoring date: three pre-existing, genuinely
#   safe helper factories (`_proc_mock()` in
#   tests/unit/merge_service/test_deadline_tunable.py and
#   tests/unit/merge_service/test_edge_case_challenges.py,
#   `_streaming_proc_mock()` in tests/unit/test_merge_trackers.py) set
#   `.returncode` to a completed-process value and have NO reachable
#   kill path — they must NOT be flagged, and are not, under this rule.
#   Honest gap (§11.4.6): a mock whose `.returncode` is assigned
#   *indirectly* (e.g. `mock.returncode = returncode` where a FUTURE
#   caller passes `returncode=None`) is invisible to this purely
#   lexical check — this gate proves the LITERAL shape is safe, not
#   every possible call-site permutation; the sibling production-side
#   gate (CM-KILLPG-PGID-GUARD) remains the primary, always-active
#   defense regardless of what any test constructs.
#
# Scope (default, no PATH arguments given):
#   tests/**/*.py (relative to the repo root this script resolves from
#   its own location), walked recursively, EXCLUDING any `__pycache__`
#   subdirectory at any depth. Deliberately the INVERSE scope from
#   CM-KILLPG-PGID-GUARD (which scans production code and excludes
#   tests/) — this gate exists specifically to cover the half of the
#   codebase that gate does not.
#
# Explicit-path mode:
#   `check_cm_test_mock_pid_explicit_int.sh PATH...` scans exactly the
#   given file(s)/directory(ies) instead of the default scope. This is
#   how the paired meta-test
#   (tests/pre_build/test_check_cm_test_mock_pid_explicit_int.sh)
#   exercises the gate against hermetic golden-good/golden-bad fixtures
#   without touching the real tree.
#
# Detection patterns (Python only, *.py):
#   1. A bare-variable assignment `<ident> = AsyncMock()` or
#      `<ident> = MagicMock()` on its own line (the process-standin
#      object itself — NOT a nested `<ident>.stdout = MagicMock()`
#      sub-stream assignment, which stands in for a pipe object that
#      has no `.pid` semantics of its own).
#   2. Within the 20 lines immediately AFTER that assignment (the
#      "forward window"), the SAME identifier carries BOTH:
#        a. an explicit `<ident>.returncode = None` assignment
#           (REQUIRED precondition — see "Detection design" above), AND
#        b. at least one process-lifecycle/streaming indicator:
#           `<ident>.stdout.readline`, `<ident>.stderr.read`,
#           `<ident>.wait`, `<ident>.kill`.
#   3. The SAME forward window does NOT contain
#      `<ident>.pid = <int-literal>` (a positive or negative integer
#      literal — `mock.pid = 12345` is the sanctioned hardening).
#   4. The mock is NOT exempted (see "Exemption" below).
#
# Exemption:
#   A hit is SKIPPED (not flagged) when a REAL (non-comment)
#   `patch(...)` / `patch.object(...)` call naming the string literal
#   `"killpg"` (or `'killpg'`) appears anywhere within 30 lines before
#   OR after the mock-assignment line. `os.killpg` is the ONLY
#   destructive operation in the search.py cleanup path — `os.getpgid`
#   is a read-only lookup that is itself gated behind the identical
#   `isinstance(_pid, int) and _pid > 1` guard before it can ever run
#   with a test-supplied pid (verified by reading search.py directly),
#   so a real `os.killpg` patch alone is sufficient to make the actual
#   syscall unreachable regardless of what `.pid` coerces to. A
#   patch mentioned only inside a comment (documenting a NEARBY test's
#   patches, e.g. "# patched getpgid" prose) is explicitly NOT counted
#   — matching a MENTION of the pattern as if it were the pattern is
#   exactly the carrier footgun §11.4.196(D)/§12.12/§11.4.201(6)-(7)
#   name; every candidate patch line is re-checked to exclude
#   comment-only lines before it counts.
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
#             §11.4.226 §11.4.238 §11.4.240 §11.4.249 §12.12.

set -euo pipefail

SCRIPT_NAME="check_cm_test_mock_pid_explicit_int"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

FWD_WINDOW=20
KILLPG_WINDOW=30
DEFAULT_SCAN_ROOTS=("tests")
EXCLUDE_DIR_NAMES=("__pycache__" ".git")

VERBOSE=0
declare -a EXPLICIT_PATHS=()

print_help() {
  sed -n '2,110p' "${BASH_SOURCE[0]}"
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

# real_killpg_patch_in_window <file> <center-line> <radius>
#   Returns 0 iff a NON-comment line within [center-radius, center+radius]
#   contains a `patch(...)` / `patch.object(...)` call naming the
#   string literal "killpg" (single or double quoted).
real_killpg_patch_in_window() {
  local file="$1" center="$2" radius="$3"
  local wstart wend
  wstart=$(( center - radius ))
  if (( wstart < 1 )); then wstart=1; fi
  wend=$(( center + radius ))
  local total_lines
  total_lines="$(wc -l < "$file" | tr -d ' ')"
  if (( wend > total_lines )); then wend="$total_lines"; fi

  local content
  local -r killpg_patch_re="patch(\\.object)?\\([^)]*[\"']killpg[\"']"
  while IFS= read -r content; do
    if is_comment_only_line "$content"; then
      continue
    fi
    if [[ "$content" =~ $killpg_patch_re ]]; then
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

    # (2a) REQUIRED precondition: <ident>.returncode = None within window.
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

    # (3) explicit .pid = <int> guard already present.
    local pid_re
    pid_re="${ident}\\.pid[[:space:]]*=[[:space:]]*-?[0-9]+"
    if grep -qE "$pid_re" <<<"$window"; then
      if [[ $VERBOSE -eq 1 ]]; then
        echo "  guarded (pid=int): $file:$lineno [identifier=$ident]"
      fi
      continue
    fi

    # (4) killpg-patch exemption.
    if real_killpg_patch_in_window "$file" "$lineno" "$KILLPG_WINDOW"; then
      if [[ $VERBOSE -eq 1 ]]; then
        echo "  exempt (killpg-patched nearby): $file:$lineno [identifier=$ident]"
      fi
      continue
    fi

    local trimmed
    trimmed="$(printf '%s' "$content" | sed -E 's/^[[:space:]]+//')"
    report_fail "$file:$lineno: unguarded subprocess-mock — $trimmed [identifier=$ident] (no \`${ident}.pid = <int>\` and no \`os.killpg\` patch within $KILLPG_WINDOW lines)"
  done <<<"$hits"
}

echo "$SCRIPT_NAME — CM-TEST-MOCK-PID-EXPLICIT-INT static pre-build gate"
if [[ ${#EXPLICIT_PATHS[@]} -gt 0 ]]; then
  echo "  scope: explicit path(s): ${EXPLICIT_PATHS[*]}"
else
  echo "  scope: default (${DEFAULT_SCAN_ROOTS[*]}), repo-root: $REPO_ROOT"
fi
echo "  forward window: $FWD_WINDOW lines; killpg-exemption window: ±$KILLPG_WINDOW lines"
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
  echo "FAIL: $count unguarded test-subprocess-mock pid hit(s) (CM-TEST-MOCK-PID-EXPLICIT-INT, BOB-126)" >&2
  exit 1
fi

echo "PASS: CM-TEST-MOCK-PID-EXPLICIT-INT clean across ${#SCAN_FILES[@]} file(s)"
exit 0
