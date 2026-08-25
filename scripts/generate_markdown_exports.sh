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
    # STALENESS IS NOT ONLY mtime (BOB-169 review, finding F7 + acceptance (c)).
    # A pre-BOB-169 export is a charset-less FRAGMENT that is mtime-FRESH, so an
    # mtime-only test leaves it in place forever — and if its .pdf is missing,
    # weasyprint re-bakes the mojibake from that stale fragment (reproduced by the
    # reviewer). Measured 2026-08-23: 303 such fragments, 302 of them mtime-fresh.
    # Treat "HTML exists but declares no charset" as STALE so the corpus self-heals
    # on the next run instead of requiring a manual sweep.
    if [[ ! -f "$html" || "$md" -nt "$html" ]] || ! grep -qiE '<meta[^>]+charset' "$html" 2>/dev/null; then
        mkdir -p "$(dirname "$html")"
        HTML_MISSING=$((HTML_MISSING + 1))

        if [[ "$CONVERTER" == "pandoc" ]]; then
            # --standalone is load-bearing, NOT cosmetic (BOB-169): without it pandoc
            # emits a BODY FRAGMENT with no <head>, so the file carries no
            # <meta charset="utf-8">. The bytes are correct UTF-8, but weasyprint
            # renders the PDF from this HTML and, with nothing declaring the
            # encoding, falls back to a non-UTF-8 default — baking mojibake into
            # the PDF's TEXT LAYER (§ -> "\u00c2\u00a7", em-dash -> "\u00e2\u20ac\u201d").
            # The python-markdown fallback below already writes the meta tag; this
            # leg was the only one missing it. Guarded by
            # tests/unit/test_export_pdf_charset_integrity.sh.
            pandoc -f markdown -t html5 --standalone -o "$html" "$md" --metadata title="$(basename "$md" .md)" 2>/dev/null
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
        # THE PDF IS DERIVED FROM THE HTML, so HTML freshness is part of PDF
        # staleness (BOB-169 review R2-F1 — BLOCKING). Keying only on "$md" healed
        # the HTML half and left the PDF corrupt: measured on the real-corpus shape
        # (fragment HTML + corrupt PDF, both mtime-fresh, .md older than both),
        # a run produced html charset=0 -> 1 while pdf mojibake stayed 1.
        # 288 real files were in exactly that shape. Worse than inert: invariant 50
        # measures HTML only, so after a bulk run the gate would report full
        # compliance while 288 corrupt PDFs remained with nothing measuring them —
        # a visible defect turned invisible, a §11.4 PASS-bluff at the metric layer.
        if [[ ! -f "$pdf" || "$md" -nt "$pdf" || "$html" -nt "$pdf" ]]; then
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
