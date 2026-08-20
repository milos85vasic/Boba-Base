#!/usr/bin/env bash
# export_staleness.sh — decide whether a generated export sibling (.html/.pdf)
# is STALE relative to its .md source, for CM-MARKDOWN-EXPORT-SYNC (§11.4.65).
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
#                                         every clone. §11.4.86 spirit, no
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
    # NOTE: the format MUST carry a placeholder. `--format='C'` (a bare
    # literal) makes git emit NOTHING AT ALL with --name-only — measured, the
    # map came back empty and every pair silently fell back to mtime, which
    # looked like a regression in the oracle. '%ct' is present only to make
    # the format valid; its VALUE is deliberately unused (two commits in the
    # same second share a timestamp and cannot be ordered by it).
    local p t
    while IFS=$'\t' read -r p t; do
        [[ -n "$p" ]] && _EXPORT_HIST_CT["$p"]="$t"
    done < <(
        cd "$root" 2>/dev/null && git log --format='C%ct' --name-only -- '*.md' '*.html' '*.pdf' 2>/dev/null \
        | awk '/^C[0-9]+$/{i++;next} NF&&!(($0) in s){s[$0]=i; print $0"\t"i}'
    )

    # working-tree-dirty set (one git status pass)
    while IFS= read -r line; do
        [[ -n "$line" ]] && _EXPORT_DIRTY["$line"]=1
    done < <( cd "$root" 2>/dev/null && git status --porcelain --untracked-files=all 2>/dev/null | awk '{print $NF}' )
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
