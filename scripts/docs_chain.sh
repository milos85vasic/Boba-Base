#!/usr/bin/env bash
# docs_chain.sh — Regenerate all docs from the workable-items DB, produce
# HTML/PDF/DOCX siblings, and stub any missing domain-summary pages.
#
# Usage:
#   bash scripts/docs_chain.sh                     # Full regeneration
#   bash scripts/docs_chain.sh --check-only         # Validate without modifying
#
# Constitution: §11.4.106 (Phase 4+ docs_chain),
#               §11.4.93 (workable-items SSOT),
#               §11.4.65 (universal Markdown export)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

CHECK_ONLY=false
for arg in "$@"; do
    case "$arg" in
        --check-only) CHECK_ONLY=true ;;
        --help|-h)
            echo "Usage: bash scripts/docs_chain.sh [--check-only]"
            echo
            echo "  (no flag)    Full regeneration: export from DB, generate HTML/PDF/DOCX, stub summaries."
            echo "  --check-only Validate without modifying any files."
            exit 0
            ;;
    esac
done

ERRORS=0

# ---------------------------------------------------------------------------
# Step 1: workable-items export (regenerates Issues.md, Fixed.md, Summaries)
# ---------------------------------------------------------------------------
echo "[docs-chain] Step 1/3: workable-items export"

# Binary resolution chain (matches constitution/scripts/reporting/report_item.sh):
# env override -> committed constitution copy -> on-demand `go build`. The
# naive "bin/workable-items" path never existed in this checkout (bin/ is a
# gitignored local build-output dir nothing ever populated) — see
# tests/unit/test_docs_chain_binary_resolution.sh for the regression guard.
WORKABLE_BIN="${WORKABLE_ITEMS_BIN:-}"
if [[ -n "${WORKABLE_BIN}" ]]; then
    case "${WORKABLE_BIN}" in
        /*) : ;;
        *) WORKABLE_BIN="${PROJECT_ROOT}/${WORKABLE_BIN}" ;;
    esac
fi
if [[ -z "${WORKABLE_BIN}" || ! -x "${WORKABLE_BIN}" ]]; then
    WI_SRC="${PROJECT_ROOT}/constitution/scripts/workable-items"
    for cand in "${WI_SRC}/bin/workable-items" "${WI_SRC}/workable-items" "${PROJECT_ROOT}/bin/workable-items"; do
        if [[ -x "${cand}" ]]; then WORKABLE_BIN="${cand}"; break; fi
    done
fi
if [[ -z "${WORKABLE_BIN}" || ! -x "${WORKABLE_BIN}" ]]; then
    if command -v go >/dev/null 2>&1; then
        WI_BUILD="$(mktemp -d)/workable-items"
        if ( cd "${PROJECT_ROOT}/constitution/scripts/workable-items" && go build -o "${WI_BUILD}" ./cmd/workable-items ) >/dev/null 2>&1; then
            WORKABLE_BIN="${WI_BUILD}"
        fi
    fi
fi
WORKABLE_DB="${PROJECT_ROOT}/docs/workable_items.db"

if [[ -z "${WORKABLE_BIN}" || ! -x "${WORKABLE_BIN}" ]]; then
    echo "  ERROR: workable-items binary not found (set WORKABLE_ITEMS_BIN, or ensure constitution/scripts/workable-items is present, or install go)" >&2
    ERRORS=$((ERRORS + 1))
elif [[ ! -f "${WORKABLE_DB}" ]]; then
    echo "  ERROR: workable-items DB not found at ${WORKABLE_DB}" >&2
    ERRORS=$((ERRORS + 1))
else
    if $CHECK_ONLY; then
        # --check-only: validate export would work by running validate
        echo "  (check-only) Running workable-items validate..."
        if ! "${WORKABLE_BIN}" validate --db "${WORKABLE_DB}"; then
            echo "  ERROR: workable-items validate failed" >&2
            ERRORS=$((ERRORS + 1))
        fi

        # Check that export output files exist (if not, they'd be generated)
        MISSING_OUT=0
        for f in Issues.md Fixed.md Issues_Summary.md Fixed_Summary.md; do
            if [[ ! -f "${PROJECT_ROOT}/docs/${f}" ]]; then
                echo "  (check-only) Would generate: docs/${f}"
                MISSING_OUT=$((MISSING_OUT + 1))
            fi
        done
        if [[ "$MISSING_OUT" -gt 0 ]]; then
            echo "  (check-only) ${MISSING_OUT} export file(s) missing — would be regenerated."
        else
            echo "  (check-only) All export files present."
        fi
    else
        # Full regeneration
        echo "  Running: ${WORKABLE_BIN} export --db ${WORKABLE_DB} --out-dir ${PROJECT_ROOT}/docs"
        # export writes to the current directory by default; use --out-dir
        # but also pass --out-issues/--out-fixed for explicit paths
        "${WORKABLE_BIN}" export \
            --db "${WORKABLE_DB}" \
            --out-dir "${PROJECT_ROOT}/docs" \
            --out-issues "${PROJECT_ROOT}/docs/Issues.md" \
            --out-fixed "${PROJECT_ROOT}/docs/Fixed.md"
    fi
fi

# ---------------------------------------------------------------------------
# Step 2: Stub missing domain-summary pages
# ---------------------------------------------------------------------------
echo "[docs-chain] Step 2/3: domain summary pages"

# Directories under docs/ that represent 'domains' — exclude subdirs that
# are explicitly out of scope (research, qa, incidents, assets, issues/*,
# and hidden dirs).
stubbed=0

stub_summary() {
    local domain_dir="$1"
    local domain_name="$2"
    local summary_path="${PROJECT_ROOT}/docs/${domain_name}_Summary.md"

    if [[ -f "$summary_path" ]]; then
        return 0
    fi

    if $CHECK_ONLY; then
        echo "  (check-only) Would stub: docs/${domain_name}_Summary.md"
        stubbed=$((stubbed + 1))
        return 0
    fi

    echo "  Stubbing: docs/${domain_name}_Summary.md"
    cat > "$summary_path" <<-SUMMARYEOF
# ${domain_name} Summary

> Auto-generated by docs_chain.sh — §11.4.106 procedure docs stub.

This directory contains documentation for the **${domain_name}** domain.

## Contents

$(find "${domain_dir}" -maxdepth 1 -name '*.md' -type f 2>/dev/null | sort | while read -r f; do
    base="$(basename "$f" .md)"
    rel="${f#"${PROJECT_ROOT}/"}"
    echo "- [${base}](${rel})"
done)

## Status

<!-- Status and per-domain summary details to be filled per §11.4.106 -->
- Domain: ${domain_name}
- Docs count: $(find "${domain_dir}" -name '*.md' -type f 2>/dev/null | wc -l | tr -d ' ')
- Last reviewed: $(date +%Y-%m-%d)

---
*This stub was created by \`scripts/docs_chain.sh\`. Replace with actual domain documentation as part of §11.4.106 Phase 4+.*
SUMMARYEOF
    stubbed=$((stubbed + 1))
}

# Map directory names to domain names
declare -A DOMAIN_MAP
DOMAIN_MAP["api"]="API"
DOMAIN_MAP["architecture"]="Architecture"
DOMAIN_MAP["codegraph"]="CodeGraph"
DOMAIN_MAP["demos"]="Demos"
DOMAIN_MAP["migration"]="Migration"
DOMAIN_MAP["scripts"]="Scripts"
DOMAIN_MAP["superpowers"]="Superpowers"

for dir in "${!DOMAIN_MAP[@]}"; do
    full_path="${PROJECT_ROOT}/docs/${dir}"
    if [[ -d "$full_path" ]]; then
        stub_summary "$full_path" "${DOMAIN_MAP[$dir]}"
    fi
done

if $CHECK_ONLY; then
    if [[ "$stubbed" -gt 0 ]]; then
        echo "  (check-only) ${stubbed} summary page(s) would be stubbed."
    else
        echo "  (check-only) All domain summary pages already present."
    fi
else
    echo "  Stubbed ${stubbed} missing summary page(s)."
fi

# ---------------------------------------------------------------------------
# Step 3: Generate HTML/PDF/DOCX siblings for all in-scope markdown files
# ---------------------------------------------------------------------------
echo "[docs-chain] Step 3/3: markdown HTML/PDF/DOCX export"

if $CHECK_ONLY; then
    echo "  (check-only) Would run: generate_markdown_exports.sh"
else
    if [[ -f "${SCRIPT_DIR}/generate_markdown_exports.sh" ]]; then
        bash "${SCRIPT_DIR}/generate_markdown_exports.sh"
    else
        echo "  ERROR: generate_markdown_exports.sh not found" >&2
        ERRORS=$((ERRORS + 1))
    fi
fi

# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------
echo
if [[ "$ERRORS" -gt 0 ]]; then
    echo "[docs-chain] FAILED with ${ERRORS} error(s)."
    exit 1
else
    echo "[docs-chain] Complete."
    exit 0
fi
