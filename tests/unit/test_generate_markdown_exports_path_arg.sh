#!/usr/bin/env bash
# test_generate_markdown_exports_path_arg.sh — BOB-181 regression guard.
#
# BOB-181: scripts/generate_markdown_exports.sh accepted no arguments; a
# caller passing `bash scripts/generate_markdown_exports.sh docs/qa/X.md`
# got the WHOLE-TREE sweep with the path argument silently discarded — a
# false affordance (§11.4.201: an interface must mean what it claims).
# Live incident (measured 2026-08-23): a conductor asked for one file,
# stale/defective exports landed in a SIBLING work-stream's directory.
#
# This test asserts: an explicit .md path argument SCOPES the run to
# exactly that file — decoy .md files at every sweep location (project
# root, docs/, scripts/) must NOT be touched — while the no-argument
# invocation's historical full-sweep behaviour stays UNCHANGED.
#
# MECHANISM (hermetic, isolated temp trees only — never the live repo):
#   Each case builds a throwaway tree shaped like PROJECT_ROOT (the
#   subject script placed at <root>/scripts/generate_markdown_exports.sh,
#   because PROJECT_ROOT is derived from BASH_SOURCE, so the script must
#   physically live at that relative location to resolve correctly) with
#   a decoy .md at each of the three sweep locations plus one "target.md"
#   named as the explicit argument. Blast-radius assertions use
#   `find <dir> -newer <marker>`, per the item's documented SECOND-ORDER
#   LESSON: `git status --porcelain` is blind to untracked directories
#   (a conductor's own verification attempt collapsed one to a single
#   summary line the grep could not match inside) — `find` sees inside.
#
# TWO SUBJECTS, ONE ASSERTION SET (§11.4.115 RED_MODE polarity switch):
#   `current`    (default) — copies the REAL, live
#                 scripts/generate_markdown_exports.sh at run time, so
#                 this mode is the standing regression guard: it tracks
#                 whatever the real script currently does and must always
#                 pass while the fix holds.
#   `historical` — uses an embedded, verbatim copy of the script exactly
#                 as it existed at commit d61abdf (the immediate parent
#                 of the commit that introduced argument handling) — the
#                 true pre-fix defect, not a re-typed approximation.
#                 Embedded (rather than `git show`-fetched) so the guard
#                 is hermetic and needs no git history at run time.
#                 Asserting the SAME "scoped correctly" expectation
#                 against this subject is expected to FAIL — that failure
#                 IS the RED reproduction.
#
# Usage:
#   bash tests/unit/test_generate_markdown_exports_path_arg.sh             # GREEN: current script (standing guard)
#   bash tests/unit/test_generate_markdown_exports_path_arg.sh historical  # RED: pre-fix script (reproduction)
#
# Constitution: §11.4.115 RED-baseline-on-the-broken-artifact, §11.4.135
# permanent regression guard, §11.4.201 false-affordance / real-condition
# guard honesty, §11.4.273 control-needle-proven measurement.

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${HERE}/../.." && pwd)"
REAL_SCRIPT="${PROJECT_ROOT}/scripts/generate_markdown_exports.sh"

SUBJECT="${1:-current}"

PASS_COUNT=0
FAIL_COUNT=0
pass() { PASS_COUNT=$((PASS_COUNT + 1)); echo "  PASS: $1"; }
fail() { FAIL_COUNT=$((FAIL_COUNT + 1)); echo "  FAIL: $1"; }

TMPBASE="$(mktemp -d)"
cleanup() { rm -rf "${TMPBASE}"; }
trap cleanup EXIT

# --- Embedded historical pre-fix fixture (verbatim git blob at commit
# d61abdff92e6d18dc12edd1f78ddb05722023d98 — the "fix(BOB-169)" commit that
# immediately PRECEDES the commit that added argument handling). It has no
# `$@`/`$1` reference anywhere: an argument is a no-op, the script always
# runs the three unconditional sweeps below. Quoted heredoc delimiter so
# nothing inside is expanded by THIS script.
write_historical_fixture() {
    local dest="$1"
    cat > "${dest}" <<'PREFIX_FIXTURE_EOF'
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
            # the PDF's TEXT LAYER (§ -> "Â§", em-dash -> "â€”").
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
PREFIX_FIXTURE_EOF
    chmod +x "${dest}"
}

# --- Builds one throwaway tree shaped like PROJECT_ROOT: a decoy .md at
# each of the three sweep locations, plus the ONE file the test will name
# as the explicit argument.
build_tree() {
    local root="$1"
    mkdir -p "${root}/docs" "${root}/scripts"
    printf '# root decoy\n'    > "${root}/root_decoy.md"
    printf '# docs decoy\n'    > "${root}/docs/decoy.md"
    printf '# docs target\n'   > "${root}/docs/target.md"
    printf '# scripts decoy\n' > "${root}/scripts/decoy.md"
}

# --- Places the given script SOURCE at <root>/scripts/generate_markdown_exports.sh
# (this exact relative location matters: PROJECT_ROOT is derived from the
# script's own BASH_SOURCE) and invokes it with the given args from inside
# the tree. Leaves stdout+stderr in RUN_OUT and the exit code in RUN_RC.
RUN_OUT=""
RUN_RC=0
run_case() {
    local root="$1" script_src="$2"; shift 2
    cp "${script_src}" "${root}/scripts/generate_markdown_exports.sh"
    chmod +x "${root}/scripts/generate_markdown_exports.sh"
    set +e
    RUN_OUT="$(cd "${root}" && bash "${root}/scripts/generate_markdown_exports.sh" "$@" 2>&1)"
    RUN_RC=$?
    set -e
    set +e
}

# --- SECOND-ORDER LESSON instrument: which export files were touched
# during this run, found via `find -newer <marker>` (never
# `git status --porcelain`, which is blind to untracked directories).
touched_exports() {
    local root="$1" marker="$2"
    find "${root}" -newer "${marker}" \( -name '*.html' -o -name '*.pdf' -o -name '*.docx' \) 2>/dev/null
}

decoy_touched() {
    # $1 = the `touched_exports` output (already captured)
    printf '%s\n' "$1" | grep -qE '(root_decoy|/docs/decoy|/scripts/decoy)\.(html|pdf|docx)$'
}

target_touched() {
    printf '%s\n' "$1" | grep -qE '/docs/target\.(html|pdf|docx)$'
}

# Resolve which script content this run is testing.
case "${SUBJECT}" in
    current)
        [[ -f "${REAL_SCRIPT}" ]] || { echo "FATAL: real script not found: ${REAL_SCRIPT}" >&2; exit 2; }
        SUBJECT_SCRIPT="${TMPBASE}/subject_current.sh"
        cp "${REAL_SCRIPT}" "${SUBJECT_SCRIPT}"
        SUBJECT_LABEL="current (real repo script)"
        ;;
    historical)
        SUBJECT_SCRIPT="${TMPBASE}/subject_historical.sh"
        write_historical_fixture "${SUBJECT_SCRIPT}"
        SUBJECT_LABEL="historical (pre-BOB-181-fix, commit d61abdf)"
        ;;
    *)
        echo "FATAL: unknown SUBJECT '${SUBJECT}' (expected 'current' or 'historical')" >&2
        exit 2
        ;;
esac

echo "=== test_generate_markdown_exports_path_arg.sh — subject: ${SUBJECT_LABEL} ==="

# === Check 1: explicit path argument must SCOPE the run ===
# (the BOB-181 assertion itself — decoys at all three sweep locations must
# stay untouched, and the named target must genuinely be converted, so a
# vacuous "nothing ran at all" can never masquerade as a scoped pass.)
CASE1_ROOT="${TMPBASE}/case1"
build_tree "${CASE1_ROOT}"
CASE1_MARKER="${TMPBASE}/case1.marker"
touch "${CASE1_MARKER}"
sleep 1  # ensure marker predates any file the run creates (1s mtime granularity)
run_case "${CASE1_ROOT}" "${SUBJECT_SCRIPT}" "${CASE1_ROOT}/docs/target.md"
CASE1_TOUCHED="$(touched_exports "${CASE1_ROOT}" "${CASE1_MARKER}")"

if target_touched "${CASE1_TOUCHED}"; then
    pass "explicit-arg run: named target.md WAS converted (sanity — the run is not vacuous)"
else
    fail "explicit-arg run: named target.md was NOT converted (rc=${RUN_RC}) — run is vacuous, cannot judge scoping"
    echo "----- run output -----"; echo "${RUN_OUT}"; echo "-----------------------"
fi

if decoy_touched "${CASE1_TOUCHED}"; then
    fail "explicit-arg run: a decoy OUTSIDE the requested scope was touched — argument was silently discarded (BOB-181)"
    echo "  touched exports:"; printf '%s\n' "${CASE1_TOUCHED}" | sed 's/^/    /'
    echo "----- run output -----"; echo "${RUN_OUT}"; echo "-----------------------"
else
    pass "explicit-arg run: no decoy outside the requested scope was touched — run is correctly scoped"
fi

# === Check 2: no-argument default must be UNCHANGED (full sweep) ===
# Positive control (§11.4.273): proves `touched_exports`/`decoy_touched`
# genuinely detect "touched" (not a blind instrument that always reports
# clean) by confirming a full sweep DOES touch every file, in both subjects.
CASE2_ROOT="${TMPBASE}/case2"
build_tree "${CASE2_ROOT}"
CASE2_MARKER="${TMPBASE}/case2.marker"
touch "${CASE2_MARKER}"
sleep 1
run_case "${CASE2_ROOT}" "${SUBJECT_SCRIPT}"
CASE2_TOUCHED="$(touched_exports "${CASE2_ROOT}" "${CASE2_MARKER}")"

if target_touched "${CASE2_TOUCHED}" && decoy_touched "${CASE2_TOUCHED}"; then
    pass "no-argument run: full-tree sweep behaviour is UNCHANGED (target + decoys all converted)"
else
    fail "no-argument run: full-tree sweep did NOT touch everything as expected (rc=${RUN_RC}) — default invocation contract broken"
    echo "  touched exports:"; printf '%s\n' "${CASE2_TOUCHED}" | sed 's/^/    /'
    echo "----- run output -----"; echo "${RUN_OUT}"; echo "-----------------------"
fi

echo "RESULT: ${PASS_COUNT} passed, ${FAIL_COUNT} failed"
[[ "${FAIL_COUNT}" -eq 0 ]]
