#!/usr/bin/env bash
# export_staleness.sh — decide whether a generated export sibling (.html/.pdf/.docx)
# is STALE relative to its .md source, for CM-MARKDOWN-EXPORT-SYNC (§11.4.65)
# AND for the writer, scripts/generate_markdown_exports.sh (BOB-249: writer and
# gate must share one definition of "stale").
#
# WHY NOT PLAIN MTIME (measured 2026-08-20, this repo):
#   Git does NOT preserve mtimes, and on checkout ".html" sorts BEFORE ".md",
#   so every export lands with an EARLIER mtime than its source. Two
#   `git checkout-index` extractions of the SAME commit reported 65 and 68
#   stale pairs; split by extension, .html was 65/141 and 68/141 while .pdf
#   was 0/141 — a deterministic alphabetical write-order artifact. So a plain
#   mtime oracle REFUSES a provably clean tree on any fresh clone
#   (§11.4.201(1) false-positive FAIL-bluff, §11.4.50 non-reproducible).
#   It also fails the OTHER way: once an export's mtime drifts AHEAD of its
#   source, generate_markdown_exports.sh skips regenerating it forever and the
#   gate reports "fresh" while the content rots. Measured live:
#   docs/scripts/extract-tracker-cookies.md contained IPTORRENTS 9x while its
#   committed .html contained it 0x (.html last committed 2026-06-16, .md
#   2026-08-18). Self-perpetuating — it never heals.
#
# THE ORACLE:
#   * sibling missing                  -> STALE (content-independent)
#   * source DIRTY vs HEAD             -> mtime comparison. A local edit makes
#                                         mtime the only, and a meaningful,
#                                         signal.
#   * source CLEAN (matches HEAD)      -> GIT HISTORY. mtimes here are just
#                                         checkout artifacts. We compare the
#                                         ORDINAL of each path's last-touching
#                                         commit in the `git log` walk (0 =
#                                         most recent), NOT commit timestamps:
#                                         two commits made in the same second
#                                         have identical timestamps and cannot
#                                         be ordered by them (reproduced in a
#                                         fixture). Ordinals order correctly
#                                         regardless, and are identical in
#                                         every FULL-history clone (a shallow
#                                         clone truncates the walk). §11.4.86 spirit, no
#                                         mtime anywhere.
#   * anything unresolvable            -> fall back to mtime, never silently
#                                         "fresh" (§11.4.201(6): a blind zero
#                                         is not a clean result).
#
# API:  export_is_stale <md_path> <sibling_path> <repo_root>
#       returns 0 = STALE, 1 = fresh
# Unit tests: tests/unit/test_export_staleness_oracle.sh

declare -gA _EXPORT_HIST_CT=()
declare -gA _EXPORT_DIRTY=()
_EXPORT_MAPS_ROOT=""

_export_build_maps() {
    local root="$1"
    [[ "${_EXPORT_MAPS_ROOT}" == "${root}" ]] && return 0
    _EXPORT_MAPS_ROOT="${root}"
    _EXPORT_HIST_CT=(); _EXPORT_DIRTY=()

    # ordinal of each path's last-touching commit (0 = most recent).
    # One git log pass; `git log` is newest-first, so the FIRST time a path
    # appears is its most recent change.
    # '*.docx' is in the pathspec (BOB-249): without it a .docx had no history
    # entry and fell back to mtime, so every docx twin was "stale" after a fresh
    # checkout. Adding a pattern only inserts more commits into the walk; the
    # relative order of any two commits (and same-commit equality) is unchanged.
    # --full-history (M6): git's default walk SIMPLIFIES merge history, so which of a
    # branch's commits are visited depends on the pathspec (adding '*.docx' flipped
    # the html/pdf verdict of a merge that took only docx from a branch: measured 3
    # divergences in 120 fuzzed merge histories, 0 with --full-history). --full-history
    # visits every commit that touches a listed path, so a verdict is a function of the
    # twins alone. Residual: a merge that DISCARDS a branch's md/html/pdf changes reads
    # STALE (safe direction: one regen). -m / --first-parent read it fresh but report
    # false-FRESH for "regen, then edit md" on a merged branch, so they are not used.
    # NUL-DELIMITED (-z), parsed in pure bash (no awk): without -z git C-quotes
    # any path containing a tab, newline, double-quote or backslash even with
    # core.quotePath=false, so such a clean file never matched its history key and
    # silently fell back to mtime. awk is deliberately NOT used: RS="\0" is a
    # gawk/mawk extension and busybox awk truncates at the first NUL (measured).
    # Record layout of `git log -z --format='%x01C%ct' --name-only`:
    #   \x01C<ct> NUL  ("\n"<path1>) NUL <path2> NUL ...  \x01C<ct> NUL ...
    # i.e. each commit is a header record followed by its paths; git prefixes the
    # FIRST path of a commit with one "\n" (strip exactly one). Empty/merge
    # commits emit a header only. The '%ct' value is deliberately unused (two
    # commits in the same second cannot be ordered by it); the format needs a
    # placeholder or git emits nothing with --name-only (measured). A header is
    # a record that is exactly \x01C<digits>; a real path cannot be mistaken for
    # one short of a filename that is itself \x01C<digits>.
    local rec i=-1 first=0
    while IFS= read -r -d '' rec; do
        if [[ "$rec" =~ ^$'\x01'C[0-9]+$ ]]; then
            i=$((i+1)); first=1; continue
        fi
        (( first )) && { rec="${rec#$'\n'}"; first=0; }
        [[ -n "$rec" && -z "${_EXPORT_HIST_CT[$rec]+x}" ]] && _EXPORT_HIST_CT["$rec"]="$i"
    done < <(
        cd "$root" 2>/dev/null && git log -z --full-history --format='%x01C%ct' --name-only -- '*.md' '*.html' '*.pdf' '*.docx' 2>/dev/null
    )

    # working-tree-dirty set (one git status pass).
    # `-z` is load-bearing (BOB-249 review I1): plain --porcelain C-quotes any
    # path with a space or non-ASCII byte. -z output is NUL-delimited, unquoted:
    # `XY <path>\0`, and for a rename/copy `XY <to>\0<from>\0` (the second
    # record is a bare path with NO XY prefix, so it must be consumed here, never
    # parsed as an entry: an original path starting with R or C would otherwise be
    # read as a further rename/copy and swallow the next real entry). Both paths
    # are marked dirty. Pure bash for the same portability reason as above.
    local xy orig
    while IFS= read -r -d '' rec; do
        xy="${rec:0:2}"
        [[ -n "${rec:3}" ]] && _EXPORT_DIRTY["${rec:3}"]=1
        if [[ "$xy" == *[RC]* ]]; then
            IFS= read -r -d '' orig && [[ -n "$orig" ]] && _EXPORT_DIRTY["$orig"]=1
        fi
    done < <(
        cd "$root" 2>/dev/null && git status --porcelain -z --untracked-files=all 2>/dev/null
    )
}

export_is_stale() {
    local md="$1" sib="$2" root="$3"
    [[ -f "$sib" ]] || return 0        # missing == stale

    _export_build_maps "$root"

    local rel_md="${md#"${root}/"}" rel_sib="${sib#"${root}/"}"

    # A locally-modified (or untracked) source: mtime IS the meaningful signal.
    if [[ -n "${_EXPORT_DIRTY[$rel_md]:-}" || -n "${_EXPORT_DIRTY[$rel_sib]:-}" ]]; then
        [[ "$sib" -ot "$md" ]] && return 0
        return 1
    fi

    # Clean source: mtimes are checkout artifacts. Ask git history instead.
    local md_i="${_EXPORT_HIST_CT[$rel_md]:-}" sib_i="${_EXPORT_HIST_CT[$rel_sib]:-}"
    if [[ -n "$md_i" && -n "$sib_i" ]]; then
        # Lower ordinal == more recent commit. Source touched more recently
        # than its export => the export was never regenerated for that change.
        (( md_i < sib_i )) && return 0
        return 1
    fi

    # Unresolvable (not in history yet): fall back to mtime rather than
    # silently claiming fresh (§11.4.201(6)).
    [[ "$sib" -ot "$md" ]] && return 0
    return 1
}
