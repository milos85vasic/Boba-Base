#!/usr/bin/env bash
#
# check_gitignore_swallow.sh — BOB-212 direction (b) swallow-guard.
#
# Purpose : Detect an UNTRACKED first-party SOURCE-CODE file that a
#           .gitignore rule silently ignores, and refuse LOUDLY — naming
#           both the swallowed file and the exact blocking rule (file:line)
#           — instead of the current silence (§11.4.201(6) false-null: "the
#           file was swallowed" and "the file was never authored" are today
#           indistinguishable to `git status`).
#
#           The item's own measurement (BOB-212) DISPROVED "narrow the
#           deny-all glob" — a corrected version of that narrowing still
#           leaked a real credential file (download-proxy/qbittorrent_creds.json)
#           because an extension-scoped deny cannot cover extensionless
#           secret files without collapsing back into a deny-all. This
#           script implements the surviving direction instead: the existing
#           .gitignore deny-all globs are left COMPLETELY UNCHANGED (this
#           script never edits, reads-to-modify, nor bypasses any of them);
#           only a LOUD refusal is added on top, scoped to first-party
#           source-code files so it can never fire on a legitimately
#           secret-shaped path (the §11.4.201(1) golden-FALSE obligation).
#
# Usage   : check_gitignore_swallow.sh <repo-root>
#
#           <repo-root> is the path to ANY git repository to scan — this
#           script assumes nothing about it being the checkout it happens to
#           ship in (the tracked RED test at
#           tests/security/test_gitignore_swallow_is_loud.sh invokes it
#           against a disposable scratch copy of this repo's own real
#           .gitignore, not the real checkout).
#
# Behaviour:
#   Enumerates every path `git ls-files --others --ignored --exclude-standard`
#   reports for <repo-root> (untracked AND ignored). For each such path that
#   is BOTH (a) under a first-party source root (not a submodule gitlink,
#   not vendored/third-party, not node_modules/__pycache__/build-output, not
#   a runtime-deployment-target directory — see the exclusion lists below)
#   AND (b) carries a recognised source-code file extension (see
#   SOURCE_EXTENSIONS below — deliberately excludes every extension/shape
#   this project treats as secret-bearing: .env, .pem, .key, .p12, .jks,
#   *creds*.json/yaml/yml, *_password*, *secrets*, cookies_*, etc. — a guard
#   that flags a legitimately-ignored secret file would be exactly as
#   forbidden as one that stays silent on a swallowed source file,
#   §11.4.201(1)), print a message naming the file's path (relative, exactly
#   as `git status`/`check-ignore` would print it) and the exact blocking
#   `.gitignore:<line>` rule (via `git check-ignore -v`), then exit non-zero.
#
# Exit    : 0  no first-party source file is silently swallowed
#           1  >=1 first-party source file IS silently swallowed (printed)
#           2  fail-closed: <repo-root> missing / not a git repo / no
#              positional argument / git unavailable — refuse rather than
#              silently succeed on unresolvable input (§11.4.252)
#
# Depends : bash, git.
# Refs    : BOB-212; §11.4.10 (credentials never reach git — untouched by
#           this script), §11.4.201(1) (false-positive/golden-FALSE guard),
#           §11.4.201(6) (false-null this closes), §11.4.252 (fail-closed on
#           an unresolvable dangerous-combination precondition).
# Doc     : docs/scripts/check_gitignore_swallow.md
#
set -euo pipefail

usage() {
  printf 'Usage: %s <repo-root>\n' "${0##*/}" >&2
}

# --------------------------------------------------------------- fail-closed
if [ "$#" -ne 1 ]; then
  usage
  printf 'ERROR: exactly one positional argument (a git repository root) is required\n' >&2
  exit 2
fi

REPO_ROOT="$1"

if ! command -v git >/dev/null 2>&1; then
  printf 'ERROR: git is not available on PATH — cannot scan\n' >&2
  exit 2
fi

if [ ! -d "$REPO_ROOT" ]; then
  printf 'ERROR: repo root does not exist or is not a directory: %s\n' "$REPO_ROOT" >&2
  exit 2
fi

if ! git -C "$REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  printf 'ERROR: not a git repository (git rev-parse failed): %s\n' "$REPO_ROOT" >&2
  exit 2
fi

# ------------------------------------------------- first-party root exclusion
# Any PATH COMPONENT matching one of these names excludes the whole path —
# submodule gitlinks, vendored/third-party trees, build output, caches, and
# every other regeneratable/non-authored class this project's own .gitignore
# already documents as such (see the real .gitignore's own comments).
EXCLUDED_DIR_NAMES=(
  submodules node_modules __pycache__ dist build out
  .venv venv vendor third_party .git .ruff_cache .mypy_cache
  .pytest_cache .hypothesis .benchmarks htmlcov .mutmut-cache
  prof mutants .vite .codegraph qa-results .evidence artifacts
  scratchpad .superpowers .docs_chain downloads incomplete volumes
  logs tmp releases bin coverage .worktrees worktrees
)

# Explicit excluded ROOT-RELATIVE path prefixes — cases a bare directory-name
# denylist cannot express: own-org submodule gitlinks that are NOT under
# submodules/ (constitution/, superspec/ — see .gitmodules), and repo-
# specific duplicate/runtime-deployment-target trees this project's own
# .gitignore already documents as such (config/download-proxy/src/ is an
# explicitly-documented DUPLICATE source tree; config/qBittorrent/ and
# config/jackett/ are runtime deployment/config targets, not authored
# source — the real first-party sources are download-proxy/src/, plugins/,
# and the jackett submodule respectively).
EXCLUDED_PATH_PREFIXES=(
  "constitution/"
  "superspec/"
  "config/qBittorrent/"
  "config/download-proxy/src/"
  "config/jackett/"
)

# ----------------------------------------------- recognised source extensions
# Deliberately excludes EVERY extension/shape this project's own .gitignore
# treats as secret-bearing (.env, .pem, .key, .p12, .pfx, .jks) and every
# data/markup extension that is either ambiguous with generated doc twins
# (.html/.pdf/.docx are export outputs under docs/, tracked when legitimate
# and never source) or commonly secret-bearing by convention in this repo
# (.json — this project's own *creds*.json / aws_credentials.json shapes are
# JSON; JSON is data, not source code, so it is excluded rather than trying
# to sub-pattern-match "safe" JSON from "secret" JSON).
SOURCE_EXTENSIONS=(
  go py ts tsx js jsx mjs cjs sh rs java kt c cc cpp h hpp ps1 sql
)

is_excluded_dir() {
  local path="$1" seg
  local IFS='/'
  # shellcheck disable=SC2206
  local -a parts=($path)
  for seg in "${parts[@]}"; do
    local ex
    for ex in "${EXCLUDED_DIR_NAMES[@]}"; do
      if [ "$seg" = "$ex" ]; then
        return 0
      fi
    done
  done
  return 1
}

is_excluded_prefix() {
  local path="$1" p
  for p in "${EXCLUDED_PATH_PREFIXES[@]}"; do
    case "$path" in
      "$p"*) return 0 ;;
    esac
  done
  return 1
}

has_source_extension() {
  local path="$1" base ext e
  base="${path##*/}"
  case "$base" in
    *.*) ext="${base##*.}" ;;
    *) return 1 ;;
  esac
  for e in "${SOURCE_EXTENSIONS[@]}"; do
    if [ "$ext" = "$e" ]; then
      return 0
    fi
  done
  return 1
}

# --------------------------------------------------------------------- scan
findings=0
findings_output=""

# Untracked AND ignored files, NUL-delimited (paths may contain spaces).
# `--exclude-standard` honours .gitignore (incl. any nested .gitignore) plus
# global/info excludes, exactly what a real `git add .` / `git status` would
# respect.
while IFS= read -r -d '' rel; do
  [ -z "$rel" ] && continue

  if is_excluded_dir "$rel"; then
    continue
  fi
  if is_excluded_prefix "$rel"; then
    continue
  fi
  if ! has_source_extension "$rel"; then
    continue
  fi

  # Recover the exact blocking rule (file:line:pattern) for this path. Use
  # --no-index so this also works against a scratch tree with no commits.
  rule_line="$(git -C "$REPO_ROOT" check-ignore -v --no-index -- "$rel" 2>/dev/null || true)"
  if [ -z "$rule_line" ]; then
    # Enumerated as ignored by ls-files but check-ignore disagrees (should
    # not happen) — skip rather than fabricate a rule citation (§11.4.6).
    continue
  fi

  findings=$((findings + 1))
  findings_output="${findings_output}SWALLOWED (first-party source, silently ignored): ${rel}
  blocked by: ${rule_line}
"
done < <(git -C "$REPO_ROOT" ls-files --others --ignored --exclude-standard -z)

# -------------------------------------------------------------------- verdict
if [ "$findings" -gt 0 ]; then
  printf 'BOB-212 swallow-guard: REFUSED — %d first-party source file(s) are silently swallowed by .gitignore.\n' "$findings"
  printf '%s' "$findings_output"
  printf 'Remedy: either rename/relocate the file so no .gitignore rule matches it, or add an explicit "!" negation for it in .gitignore (see the rule cited above), then re-run this guard.\n'
  exit 1
fi

printf 'BOB-212 swallow-guard: OK — no first-party source files are silently swallowed by .gitignore.\n'
exit 0
