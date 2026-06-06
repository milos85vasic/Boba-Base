#!/usr/bin/env bash
# generate_markdown_exports.sh — Generate HTML + PDF + DOCX siblings for
# every in-scope .md file per constitution §11.4.65.
#
# DOCX export (BOB-011) is produced directly from the markdown via
# `pandoc -f markdown -t docx`; it shares the same file-discovery scope
# and the same "only regenerate when .md is newer than the sibling"
# idempotency rule as HTML/PDF.
#
# Usage: bash scripts/generate_markdown_exports.sh
# Idempotent: only regenerates when .md is newer than its sibling.
#
# Constitution: §11.4.65 Universal Markdown export mandate

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HTML_GENERATED=0
HTML_MISSING=0
PDF_GENERATED=0
PDF_MISSING=0
DOCX_GENERATED=0
DOCX_MISSING=0

if command -v pandoc &>/dev/null; then
    CONVERTER="pandoc"
elif python3 -c "import markdown" &>/dev/null 2>&1; then
    CONVERTER="python-markdown"
else
    echo "Error: neither pandoc nor python-markdown is available" >&2
    exit 1
fi

HAS_WEASYPRINT=false
if command -v weasyprint &>/dev/null && python3 -c "from weasyprint import HTML" &>/dev/null 2>&1; then
    HAS_WEASYPRINT=true
fi

# DOCX export requires pandoc (no pure-python fallback).
HAS_PANDOC_DOCX=false
if command -v pandoc &>/dev/null; then
    HAS_PANDOC_DOCX=true
fi

convert_file() {
    local md="$1"
    local html="${md%.md}.html"
    local pdf="${md%.md}.pdf"
    local docx="${md%.md}.docx"

    # Generate HTML
    if [[ ! -f "$html" || "$md" -nt "$html" ]]; then
        mkdir -p "$(dirname "$html")"
        HTML_MISSING=$((HTML_MISSING + 1))

        if [[ "$CONVERTER" == "pandoc" ]]; then
            pandoc -f markdown -t html5 -o "$html" "$md" --metadata title="$(basename "$md" .md)" 2>/dev/null
        else
            python3 -c "
import markdown, sys
md = open(sys.argv[1]).read()
html = markdown.markdown(md)
title = sys.argv[3] if len(sys.argv) > 3 else 'Document'
out = f'<!DOCTYPE html><html><head><meta charset=\"utf-8\"><title>{title}</title></head><body>{html}</body></html>'
open(sys.argv[2], 'w').write(out)
" "$md" "$html" "$(basename "$md" .md)"
        fi
        HTML_GENERATED=$((HTML_GENERATED + 1))
    fi

    # Generate PDF from HTML if weasyprint is available
    if $HAS_WEASYPRINT; then
        if [[ ! -f "$pdf" || "$md" -nt "$pdf" ]]; then
            mkdir -p "$(dirname "$pdf")"
            PDF_MISSING=$((PDF_MISSING + 1))
            weasyprint "$html" "$pdf" 2>/dev/null && PDF_GENERATED=$((PDF_GENERATED + 1)) || true
        fi
    fi

    # Generate DOCX directly from the markdown via pandoc if available.
    if $HAS_PANDOC_DOCX; then
        if [[ ! -f "$docx" || "$md" -nt "$docx" ]]; then
            mkdir -p "$(dirname "$docx")"
            DOCX_MISSING=$((DOCX_MISSING + 1))
            pandoc -f markdown -t docx -o "$docx" "$md" 2>/dev/null && DOCX_GENERATED=$((DOCX_GENERATED + 1)) || true
        fi
    fi
}

echo "=== Generating Markdown HTML + PDF exports ==="
echo "Converter: $CONVERTER"
$HAS_WEASYPRINT && echo "PDF support: weasyprint available" || echo "PDF support: not available"
$HAS_PANDOC_DOCX && echo "DOCX support: pandoc available" || echo "DOCX support: not available"

# Project root .md files
for md in "$PROJECT_ROOT"/*.md; do
    [[ -f "$md" ]] || continue
    convert_file "$md"
done

# docs/ recursively
while IFS= read -r -d '' md; do
    convert_file "$md"
done < <(find "$PROJECT_ROOT/docs" -name '*.md' -type f -print0 2>/dev/null)

# scripts/ recursively
while IFS= read -r -d '' md; do
    convert_file "$md"
done < <(find "$PROJECT_ROOT/scripts" -name '*.md' -type f -print0 2>/dev/null)

echo "Generated $HTML_GENERATED of $HTML_MISSING missing HTML files"
$HAS_WEASYPRINT && echo "Generated $PDF_GENERATED of $PDF_MISSING missing PDF files"
$HAS_PANDOC_DOCX && echo "Generated $DOCX_GENERATED of $DOCX_MISSING missing DOCX files"
echo "Done."
exit 0
