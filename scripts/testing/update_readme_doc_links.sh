#!/usr/bin/env bash
# scripts/testing/update_readme_doc_links.sh — §11.4.57 machine-derived
# README "Tracked-Items + Status Documents" table regenerator (BOB-088).
#
# Purpose: keep the README.md `### Tracked-Items + Status Documents` table
#   (bounded by the `<!-- doc-link-section:begin -->` /
#   `<!-- doc-link-section:end -->` markers §11.4.57 mandates) in sync with
#   the REAL `**Revision:**` / `**Last modified:**` header (§11.4.44) each
#   tracked document carries, and with whether its `.html` / `.pdf` siblings
#   actually exist on disk — never a hand-typed or carried-forward value.
#
# Forensic anchor (BOB-088, measured 2026-08-21): before this script existed
# the table was hand-maintained and had drifted on 10 of its 18 rows — e.g.
# `docs/Issues.md` carried **Revision:** 38 while the table still read 10,
# and `docs/PORTING-FROM-LAVA.md` had a real `.html`/`.pdf` on disk while the
# table still read "— (not yet exported)" for both — plus one MANDATED
# document (`docs/GOVERNANCE_AUDIT_2026-08-08_ROUND2.md`, cited by name in
# BOB-088's own body text) had NO row at all. Every value below is read from
# the tracked file itself in THIS invocation; a table cell is never
# hand-typed or assumed correct because it "looked right last time"
# (§11.4.6).
#
# Usage:
#   scripts/testing/update_readme_doc_links.sh            # rewrite in place
#   scripts/testing/update_readme_doc_links.sh --check     # read-only;
#                                                           # exit 0 = in
#                                                           # sync, exit 2 =
#                                                           # stale.
#   scripts/testing/update_readme_doc_links.sh --check --readme <path>
#                                                           # override the
#                                                           # target file
#                                                           # (used by tests).
#
# Scope (deliberately narrow — §11.4.212's broader "every reachable doc"
# obligation is a distinct, editorial-judgement-bearing task tracked
# separately; this generator owns only the closed-set "Tracked-Items" row
# class §11.4.57 names: Issues/Fixed + their Summaries, CONTINUATION,
# PORTING-FROM-LAVA, REMAINING_WORK_PLAN, every GOVERNANCE_AUDIT_*.md,
# COMPLETION_STATUS, RELEASE_READINESS_20260616, QA_DISCOVERY_LEDGER, and
# every `docs/**/Status.md` + its `Status_Summary.md` pair, auto-discovered
# so a NEW subsystem Status doc is picked up without hand-editing this
# script's manifest).
#
# Inputs: docs/*.md revision headers, `git ls-files docs/**/Status.md`.
# Outputs: README.md `### Tracked-Items + Status Documents` table (rewritten
#   in place, default mode only).
# Side-effects: none in --check mode. Rewrites README.md in default mode
#   (a git-tracked file — review the diff before commit). Does NOT
#   regenerate README.html/.pdf/.docx — run
#   scripts/generate_markdown_exports.sh afterward (§11.4.65/§11.4.12).
# Dependencies: bash 4+, git, sed, grep, awk.
# Cross-references: docs/scripts/update_readme_doc_links.md (§11.4.18
#   companion), CLAUDE.md / constitution/CLAUDE.md §11.4.57 (the mandate
#   this script implements), BOB-088 (the tracked item this script closes).
#
# Anti-bluff (§11.4.6): a document with no `**Revision:**` / `**Last
# modified:**` header emits `—` for both cells (never a fabricated value,
# matching the header note already printed above the table). A missing
# `.html`/`.pdf` sibling emits "— (not yet exported)"; a present one emits
# a real relative link — checked with a real `[[ -f ... ]]` on THIS run,
# never carried forward from a previous table state.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"

README="${ROOT_DIR}/README.md"
MODE="apply"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --check) MODE="check"; shift ;;
        --readme) README="$2"; shift 2 ;;
        -h|--help)
            sed -n '2,40p' "${BASH_SOURCE[0]}"
            exit 0
            ;;
        *) echo "update_readme_doc_links.sh: unknown argument: $1" >&2; exit 64 ;;
    esac
done

BEGIN_MARKER="<!-- doc-link-section:begin -->"
END_MARKER="<!-- doc-link-section:end -->"

# ---------------------------------------------------------------------------
# §11.4.6 no-guessing: the fixed part of the manifest — every doc §11.4.57
# names explicitly by class, in the order the table has historically shown
# them. Discovered Status.md/Status_Summary.md pairs (below) are appended
# after this fixed block, sorted, so a new subsystem's docs land
# deterministically rather than at an arbitrary insertion point.
# ---------------------------------------------------------------------------
FIXED_DOCS=(
    "Issues|docs/Issues.md"
    "Issues_Summary|docs/Issues_Summary.md"
    "Fixed|docs/Fixed.md"
    "Fixed_Summary|docs/Fixed_Summary.md"
    "CONTINUATION|docs/CONTINUATION.md"
    "PORTING-FROM-LAVA|docs/PORTING-FROM-LAVA.md"
    "REMAINING_WORK_PLAN|docs/REMAINING_WORK_PLAN.md"
    "COMPLETION_STATUS|docs/COMPLETION_STATUS.md"
    "RELEASE_READINESS_20260616|docs/RELEASE_READINESS_20260616.md"
    "QA_DISCOVERY_LEDGER|docs/QA_DISCOVERY_LEDGER.md"
)

# Every docs/GOVERNANCE_AUDIT_*.md — auto-discovered (not hand-listed) so a
# THIRD round audit doc is picked up automatically; this is precisely the
# class BOB-088 found a missing row in (GOVERNANCE_AUDIT_2026-08-08_ROUND2).
GA_DOCS=()
while IFS= read -r f; do
    [[ -z "${f}" ]] && continue
    name="$(basename "${f}" .md)"
    GA_DOCS+=("${name}|${f}")
done < <(cd "${ROOT_DIR}" && git ls-files 'docs/GOVERNANCE_AUDIT_*.md' 2>/dev/null | sort)

# Every docs/**/Status.md + its sibling Status_Summary.md, auto-discovered.
STATUS_DOCS=()
while IFS= read -r status_file; do
    [[ -z "${status_file}" ]] && continue
    dir="$(dirname "${status_file}")"
    label_dir="${dir#docs/}"
    STATUS_DOCS+=("${label_dir}/Status|${status_file}")
    summary_file="${dir}/Status_Summary.md"
    if [[ -f "${ROOT_DIR}/${summary_file}" ]]; then
        STATUS_DOCS+=("${label_dir}/Status_Summary|${summary_file}")
    fi
    # A release-readiness sibling in the same subsystem directory, if present
    # (matches the existing browser_extension/RELEASE_READINESS row).
    rr_file="${dir}/RELEASE_READINESS.md"
    if [[ -f "${ROOT_DIR}/${rr_file}" ]]; then
        STATUS_DOCS+=("${label_dir}/RELEASE_READINESS|${rr_file}")
    fi
done < <(cd "${ROOT_DIR}" && git ls-files 'docs/**/Status.md' 2>/dev/null | sort)

MANIFEST=("${FIXED_DOCS[@]}" "${GA_DOCS[@]}" "${STATUS_DOCS[@]}")

# ---------------------------------------------------------------------------
# Build one table row from a "<label>|<relative-path>" manifest entry, read
# freshly from disk on THIS invocation (§11.4.6).
# ---------------------------------------------------------------------------
build_row() {
    local label="$1" relpath="$2"
    local abspath="${ROOT_DIR}/${relpath}"
    if [[ ! -f "${abspath}" ]]; then
        echo "update_readme_doc_links.sh: WARNING — manifest entry '${label}' -> ${relpath} not found, skipping" >&2
        return 1
    fi
    local rev lastmod
    rev="$(grep -m1 -oE '\*\*Revision:\*\*[[:space:]]*[0-9]+' "${abspath}" | grep -oE '[0-9]+$' || true)"
    lastmod="$(grep -m1 -oE '\*\*Last modified:\*\*[[:space:]]*[0-9TZ:.+-]+' "${abspath}" | sed 's/.*\*\*Last modified:\*\*[[:space:]]*//' || true)"
    [[ -z "${rev}" ]] && rev="—"
    [[ -z "${lastmod}" ]] && lastmod="—"

    local base_noext="${relpath%.md}"
    local html_rel="${base_noext}.html"
    local pdf_rel="${base_noext}.pdf"
    local html_cell pdf_cell
    if [[ -f "${ROOT_DIR}/${html_rel}" ]]; then
        html_cell="[HTML](${html_rel})"
    else
        html_cell="— (not yet exported)"
    fi
    if [[ -f "${ROOT_DIR}/${pdf_rel}" ]]; then
        pdf_cell="[PDF](${pdf_rel})"
    else
        pdf_cell="— (not yet exported)"
    fi

    printf '| %s | %s | %s | [Markdown](%s) | %s | %s |\n' \
        "${label}" "${lastmod}" "${rev}" "${relpath}" "${html_cell}" "${pdf_cell}"
}

TABLE_HEADER='| Document | Last modified | Revision | Markdown | HTML | PDF |
|---|---|---|---|---|---|'

ROWS=""
for entry in "${MANIFEST[@]}"; do
    label="${entry%%|*}"
    relpath="${entry#*|}"
    if row="$(build_row "${label}" "${relpath}")"; then
        ROWS+="${row}"$'\n'
    fi
done

NEW_TABLE="${TABLE_HEADER}
${ROWS%$'\n'}"

if [[ ! -f "${README}" ]]; then
    echo "update_readme_doc_links.sh: ${README} not found" >&2
    exit 1
fi

if ! grep -qF "${BEGIN_MARKER}" "${README}" || ! grep -qF "${END_MARKER}" "${README}"; then
    echo "update_readme_doc_links.sh: ${BEGIN_MARKER} / ${END_MARKER} markers not found in ${README}" >&2
    echo "  (§11.4.57 requires the Tracked-Items table to live between these exact markers)" >&2
    exit 1
fi

CURRENT_BLOCK="$(awk -v b="${BEGIN_MARKER}" -v e="${END_MARKER}" '
    $0 == b { inblk = 1; next }
    $0 == e { inblk = 0; next }
    inblk { print }
' "${README}")"

# The current block carries one leading blank line + the intro paragraph +
# a blank line + the table; only the TABLE portion is machine-derived, so
# only that portion is diffed/replaced — the prose above stays hand-authored.
CURRENT_TABLE="$(printf '%s\n' "${CURRENT_BLOCK}" | awk '/^\| Document \|/{f=1} f{print}')"

if [[ "${MODE}" == "check" ]]; then
    if [[ "${CURRENT_TABLE}" == "${NEW_TABLE}" ]]; then
        echo "update_readme_doc_links.sh --check: Tracked-Items table is in sync with live doc headers"
        exit 0
    fi
    echo "update_readme_doc_links.sh --check: Tracked-Items table is STALE — run 'scripts/testing/update_readme_doc_links.sh' to refresh"
    diff <(printf '%s\n' "${CURRENT_TABLE}") <(printf '%s\n' "${NEW_TABLE}") || true
    exit 2
fi

if [[ "${CURRENT_TABLE}" == "${NEW_TABLE}" ]]; then
    echo "update_readme_doc_links.sh: Tracked-Items table already in sync — nothing to do"
    exit 0
fi

TMP_README="$(mktemp)"
trap 'rm -f "${TMP_README}"' EXIT

# §11.4.6 anti-bluff / correctness note: this state machine has THREE states
# inside the block — "prose" (print verbatim until the table header line),
# "drop-old-table" (the header line triggers printing NEW_TABLE once, then
# EVERY subsequent `|`-prefixed line — separator AND every old data row —
# is dropped, never just the header+separator), and "prose-after" (any
# non-`|` line reached after the old table, printed verbatim). A prior
# version of this rule only dropped the header + `|---` separator line and
# fell through to printing every old data row unchanged, corrupting
# README.md into TWO back-to-back copies of the table (caught + fixed
# 2026-08-21, BOB-088) — regression test:
# tests/unit/test_update_readme_doc_links_no_duplication.sh
awk -v b="${BEGIN_MARKER}" -v e="${END_MARKER}" -v newtable="${NEW_TABLE}" '
    $0 == b { print; state = "prose"; next }
    $0 == e { print; state = ""; next }
    state == "prose" {
        if (/^\| Document \|/) { print newtable; state = "drop-old-table"; next }
        print
        next
    }
    state == "drop-old-table" {
        if (/^\|/) { next }
        state = "prose-after"
        print
        next
    }
    state == "prose-after" { print; next }
    { print }
' "${README}" > "${TMP_README}"

mv "${TMP_README}" "${README}"
trap - EXIT

echo "update_readme_doc_links.sh: README.md Tracked-Items table refreshed (${#MANIFEST[@]} manifest entries)"
