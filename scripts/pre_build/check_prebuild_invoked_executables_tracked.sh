#!/usr/bin/env bash
# check_prebuild_invoked_executables_tracked.sh — CM-PREBUILD-INVOKED-EXECUTABLES-TRACKED (BOB-231)
#
# Purpose:
#   Every executable the pre-build sweep runs must itself be git-tracked. A gate
#   whose implementation file exists only on the authoring host is invisible to
#   every fresh clone: the clone either skips the gate or fails it for a reason
#   unrelated to the code under test, and there is no committed baseline to diff
#   round over round. BOB-227 measured 3 of 4 files of one gate untracked; this
#   check makes that whole class visible for every gate, present and future.
#
# How it enumerates (static, so it never has to run the sweep):
#   1. Every `${PROJECT_ROOT}/<path>`, `${SCRIPT_DIR}/<path>` and
#      `${CONST_GATES_DIR}/<path>` literal ending in .sh/.py/.bash on a
#      non-comment line of the sweep script. A `${var}` inside <path> becomes a
#      glob, and every match is checked.
#   2. One level down: inside each resolved script under scripts/, the same
#      literals with the bases `${SCRIPT_DIR}`/`$SCRIPT_DIR` (the script's own
#      directory) and `${REPO_ROOT}`/`${PROJECT_ROOT}` (the repository root) —
#      this catches helper analyzers and libraries a gate calls.
#   3. Every tests/**/test_*.sh — invariant 30 discovers and runs all of them.
#      These are reported as ADVISORY (a work-in-progress test on a developer
#      machine is normal; it must be tracked before it is relied on), never
#      counted as a blocking finding.
#   Paths under constitution/ are checked against the constitution submodule's
#   own index (git -C constitution ls-files), everything else against the main
#   repository's index.
#
# Usage:   bash scripts/pre_build/check_prebuild_invoked_executables_tracked.sh <repo-root> [<sweep-script>]
#          (<sweep-script> defaults to <repo-root>/scripts/pre_build_verification.sh)
# Outputs: one line per finding; last line is the verdict.
#          CM_TRACKED_VERBOSE=1 also lists every checked target.
# Exit:    0 every blocking invocation target is tracked (advisory WARNs allowed)
#          1 at least one invoked executable exists but is NOT tracked
#          2 harness error: bad arguments, not a git repo, sweep missing, or the
#            extraction resolved ZERO targets (a blind instrument, never "clean")
# Side-effects: none; reads only.
# Dependencies: bash, git, grep, sed, find, sort.
# Cross-references: docs/scripts/check_prebuild_invoked_executables_tracked.md,
#   tests/pre_build/test_check_prebuild_invoked_executables_tracked.sh.
#   Constitution: §11.4.30, §11.4.201(6), §11.4.205, §11.4.215, §11.4.227.

set -uo pipefail

usage() { echo "Usage: $0 <repo-root> [<sweep-script>]" >&2; }

if [[ $# -lt 1 || $# -gt 2 ]]; then usage; exit 2; fi
ROOT="$1"
if [[ ! -d "${ROOT}" ]] || ! git -C "${ROOT}" rev-parse --git-dir >/dev/null 2>&1; then
    echo "ERROR: ${ROOT} is not a git repository root" >&2; exit 2
fi
ROOT="$(cd "${ROOT}" && pwd)"
SWEEP="${2:-${ROOT}/scripts/pre_build_verification.sh}"
if [[ ! -f "${SWEEP}" ]]; then
    echo "ERROR: sweep script not found: ${SWEEP}" >&2; exit 2
fi

PATH_CHARS='[A-Za-z0-9_./*${}-]+'
EXT_RE='\.(sh|py|bash)'

# strip_comments <file> : drop whole-line comments (paths mentioned in prose are
# not invocations).
strip_comments() { grep -vE '^[[:space:]]*#' "$1" || true; }

declare -A TARGET_FROM=()   # repo-relative path -> "invoked from" label
declare -A ADVISORY=()      # repo-relative path -> 1

add_target() {  # <rel-pattern> <from-label>
    local pat="$1" from="$2" m
    pat="$(sed -E 's/\$\{[A-Za-z_][A-Za-z0-9_]*\}/*/g' <<<"${pat}")"
    pat="${pat#./}"
    if [[ "${pat}" == *'*'* ]]; then
        local found=0
        while IFS= read -r m; do
            [[ -n "${m}" ]] || continue
            found=1
            TARGET_FROM["${m#"${ROOT}/"}"]="${from}"
        done < <(compgen -G "${ROOT}/${pat}" || true)
        [[ "${found}" -eq 1 ]] || TARGET_FROM["${pat}"]="${from}"
    else
        TARGET_FROM["${pat}"]="${from}"
    fi
}

# Level 1: the sweep itself.
SWEEP_REL="${SWEEP#"${ROOT}/"}"
while IFS= read -r tok; do
    base="${tok%%\}*}"; base="${base#\$\{}"
    rel="${tok#*\}/}"
    case "${base}" in
        PROJECT_ROOT)    add_target "${rel}" "${SWEEP_REL}" ;;
        SCRIPT_DIR)      add_target "scripts/${rel}" "${SWEEP_REL}" ;;
        CONST_GATES_DIR) add_target "constitution/scripts/gates/${rel}" "${SWEEP_REL}" ;;
    esac
done < <(strip_comments "${SWEEP}" | grep -oE "\\\$\\{(PROJECT_ROOT|SCRIPT_DIR|CONST_GATES_DIR)\\}/${PATH_CHARS}${EXT_RE}\\b" | sort -u)

# Level 2: helpers referenced by the resolved scripts under scripts/.
for rel in "${!TARGET_FROM[@]}"; do
    [[ "${rel}" == scripts/* && -f "${ROOT}/${rel}" ]] || continue
    dir="$(dirname "${rel}")"
    while IFS= read -r tok; do
        base="$(sed -E 's/^\$\{?([A-Z_]+)\}?\/.*/\1/' <<<"${tok}")"
        sub="$(sed -E 's/^\$\{?[A-Z_]+\}?\///' <<<"${tok}")"
        case "${base}" in
            SCRIPT_DIR)             add_target "${dir}/${sub}" "${rel}" ;;
            REPO_ROOT|PROJECT_ROOT) add_target "${sub}" "${rel}" ;;
        esac
    done < <(strip_comments "${ROOT}/${rel}" | grep -oE "\\\$\\{?(SCRIPT_DIR|REPO_ROOT|PROJECT_ROOT)\\}?/${PATH_CHARS}${EXT_RE}\\b" | sort -u)
done

# Level 3: the bash test suites invariant 30 discovers and runs.
if [[ -d "${ROOT}/tests" ]]; then
    while IFS= read -r -d '' t; do
        ADVISORY["${t#"${ROOT}/"}"]=1
    done < <(find "${ROOT}/tests" -type f -name 'test_*.sh' -print0)
fi

if [[ "${#TARGET_FROM[@]}" -eq 0 ]]; then
    echo "ERROR: resolved ZERO invocation targets from ${SWEEP_REL} — the extraction is BLIND, not the sweep clean (§11.4.201(6))" >&2
    exit 2
fi

is_tracked() {  # <repo-relative path>
    local rel="$1"
    if [[ "${rel}" == constitution/* && -e "${ROOT}/constitution/.git" ]]; then
        git -C "${ROOT}/constitution" ls-files --error-unmatch -- "${rel#constitution/}" >/dev/null 2>&1
    else
        git -C "${ROOT}" ls-files --error-unmatch -- "${rel}" >/dev/null 2>&1
    fi
}

UNTRACKED=0; ABSENT=0; CHECKED=0; WARNED=0
while IFS= read -r rel; do
    if [[ ! -e "${ROOT}/${rel}" ]]; then
        ABSENT=$((ABSENT+1))
        echo "  info: referenced but absent on disk (not a tracking finding): ${rel} (from ${TARGET_FROM[${rel}]})"
        continue
    fi
    CHECKED=$((CHECKED+1))
    [[ "${CM_TRACKED_VERBOSE:-0}" == 1 ]] && echo "  checked: ${rel} (from ${TARGET_FROM[${rel}]})"
    if ! is_tracked "${rel}"; then
        UNTRACKED=$((UNTRACKED+1))
        echo "UNTRACKED INVOKED EXECUTABLE: ${rel}"
        echo "  invoked from: ${TARGET_FROM[${rel}]}"
    fi
done < <(printf '%s\n' "${!TARGET_FROM[@]}" | sort)

for rel in $(printf '%s\n' "${!ADVISORY[@]}" | sort); do
    [[ -z "${TARGET_FROM[${rel}]+x}" ]] || continue
    if ! is_tracked "${rel}"; then
        WARNED=$((WARNED+1))
        echo "  WARN (advisory): untracked test suite that invariant 30 would run: ${rel}"
    fi
done

if [[ "${UNTRACKED}" -gt 0 ]]; then
    echo "FAIL: ${UNTRACKED} executable(s) invoked by the pre-build sweep are not git-tracked (${CHECKED} checked, ${ABSENT} absent, ${WARNED} advisory)"
    exit 1
fi
echo "OK: all ${CHECKED} executables invoked by the pre-build sweep are git-tracked (${ABSENT} referenced-but-absent, ${WARNED} advisory untracked test suite(s))"
exit 0
