#!/usr/bin/env bash
#
# check_md_export_twins_committable.sh — BOB-219 acceptance criterion (4).
#
# Purpose : For every TRACKED .md source in the constitution's §11.4.65
#           export scope (root/*.md, docs/**/*.md, scripts/**/*.md — the
#           exact scope `scripts/generate_markdown_exports.sh` sweeps), if
#           one of its mandated export twins (.html / .pdf / .docx) EXISTS
#           ON DISK, that twin MUST be committable (i.e. NOT silently
#           swallowed by a .gitignore rule).
#
#           This closes the BOB-219 defect class directly: a tracked
#           docs/guides/tracker-credentials.md whose .html/.pdf twins
#           existed on disk but were matched by the .gitignore *credentials*
#           deny-all glob with no rescue entry — invisible to `git status`,
#           so every clone of the repository silently shipped a guide with
#           no exports while the authoring host looked complete
#           (§11.4.201(6) FALSE-NULL: "swallowed" and "never generated" were
#           indistinguishable to the commit path).
#
#           This script does NOT require the twins to exist — generating
#           them is a separate concern (tracked as BOB-223 / the
#           CM-MARKDOWN-EXPORT-SYNC gate). It only asserts: if a twin is
#           PRESENT, it must be ADDABLE. A missing twin is silently skipped
#           (out of scope for this check — that is a presence gate, this is
#           a committability gate; conflating the two would make this
#           script fire on every .md whose exports simply have not been
#           regenerated yet, which is a different, already-owned invariant).
#
# Usage   : check_md_export_twins_committable.sh <repo-root>
#
#           <repo-root> is the path to ANY git repository to scan — the
#           paired RED/GREEN test at
#           tests/pre_build/test_check_md_export_twins_committable.sh
#           invokes it against disposable scratch fixtures, never only the
#           checkout it happens to ship in.
#
# Behaviour:
#   1. Enumerate every path `git -C <repo-root> ls-files -- '*.md'` reports
#      (TRACKED .md files only — an untracked .md's export twins are not
#      this defect class) that lies in §11.4.65 export scope: a top-level
#      *.md, or anything under docs/ or scripts/ ending in .md.
#   2. For each such .md, for each twin extension (html, pdf, docx — the
#      three formats §11.4.65/§11.4.153 mandate), compute the sibling path
#      by replacing the .md suffix with the twin extension.
#   3. If the sibling exists ON DISK, run
#      `git -C <repo-root> check-ignore -q -- <sibling>`. Exit 0 from
#      check-ignore means the sibling IS matched by a .gitignore rule
#      (ignored) — a violation. Print the .md source, the swallowed twin,
#      and the exact blocking `.gitignore:<line>` rule (via
#      `git check-ignore -v`), then continue scanning (report ALL
#      violations in one pass, not just the first).
#   4. A sibling that does not exist on disk is skipped silently (out of
#      scope per the header note above).
#
# Exit    : 0  every existing export twin of every tracked, in-scope .md is
#              committable (not gitignored)
#           1  >=1 existing twin IS silently swallowed by .gitignore
#              (printed: source .md, swallowed twin, blocking rule)
#           2  fail-closed: <repo-root> missing / not a git repo / no
#              positional argument / git unavailable — refuse rather than
#              silently succeed on unresolvable input (§11.4.252)
#
# Depends : bash, git.
# Refs    : BOB-219 (acceptance criterion 4); §11.4.65 (universal Markdown
#           export mandate — the scope this script enforces committability
#           for); §11.4.153 (four-format export set, of which this checks
#           html/pdf/docx — the three that ever get gitignore-swallowed;
#           .md itself is the tracked source); §11.4.10 (credentials never
#           reach git — this script only ever READS .gitignore state, it
#           never edits or bypasses any deny rule); §11.4.201(1) (a guard
#           that fires on a legitimately-absent twin would itself be a
#           false-positive refusal — closed by the "skip if absent" rule
#           in step 4); §11.4.201(6) (the false-null this closes);
#           §11.4.252 (fail-closed on an unresolvable precondition).
#           Sibling gate: scripts/pre_build/check_gitignore_swallow.sh
#           (BOB-212 — scoped to first-party SOURCE-CODE extensions only;
#           deliberately excludes html/pdf/docx export outputs, which is
#           exactly the gap this script fills).
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

# ---------------------------------------------------------- §11.4.65 scope --
# Mirrors scripts/generate_markdown_exports.sh's own discovery scope exactly
# (root/*.md + docs/**/*.md + scripts/**/*.md) so this gate never disagrees
# with the generator about what is "in scope".
in_scope() {  # $1 = repo-relative path
  local p="$1"
  case "$p" in
    */*)
      case "$p" in
        docs/*|scripts/*) return 0 ;;
        *) return 1 ;;
      esac
      ;;
    *.md)
      # top-level file (no '/'): always in scope
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

TWIN_EXTS=(html pdf docx)

violations=0
md_count=0

while IFS= read -r md_rel; do
  [ -n "$md_rel" ] || continue
  in_scope "$md_rel" || continue
  md_count=$((md_count + 1))

  base="${md_rel%.md}"
  for ext in "${TWIN_EXTS[@]}"; do
    twin_rel="${base}.${ext}"
    twin_abs="${REPO_ROOT}/${twin_rel}"
    [ -f "$twin_abs" ] || continue

    if git -C "$REPO_ROOT" check-ignore -q -- "$twin_rel" 2>/dev/null; then
      rule="$(git -C "$REPO_ROOT" check-ignore -v -- "$twin_rel" 2>/dev/null || true)"
      printf 'SWALLOWED EXPORT TWIN: %s\n' "$twin_rel" >&2
      printf '  source .md:    %s\n' "$md_rel" >&2
      printf '  blocking rule: %s\n' "${rule:-<unresolved>}" >&2
      violations=$((violations + 1))
    fi
  done
done < <(git -C "$REPO_ROOT" ls-files -- '*.md')

if [ "$violations" -gt 0 ]; then
  printf '\nFAIL: %d tracked §11.4.65-scope .md file(s) have an existing export twin silently swallowed by .gitignore (%d .md files scanned)\n' \
    "$violations" "$md_count" >&2
  exit 1
fi

printf 'OK: no tracked §11.4.65-scope .md export twin is silently swallowed by .gitignore (%d .md files scanned)\n' "$md_count"
exit 0
