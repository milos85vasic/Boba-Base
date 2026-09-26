#!/usr/bin/env bash
# generate_markdown_exports.sh — Generate HTML + PDF + DOCX siblings for
# every in-scope .md file per constitution §11.4.65.
#
# DOCX export (BOB-011) is produced directly from the markdown via
# `pandoc -f markdown -t docx`; it shares the same file-discovery scope
# and the same staleness rule as HTML/PDF.
#
# Usage:
#   bash scripts/generate_markdown_exports.sh                # full in-scope sweep
#   bash scripts/generate_markdown_exports.sh FILE.md [...]   # only these files
#
# Inputs:
#   $@ (optional)  Explicit .md paths. When given, ONLY those files are
#                  converted and the root/docs/scripts discovery sweep is
#                  skipped entirely. Absent -> the historical full sweep.
#                  Added so a session touching 9 docs can resync exactly those
#                  9 twins without re-rendering ~350 unrelated exports (which
#                  would churn the CM-EXPORT-CHARSET-VALID ratchet baseline).
#   $BOBA_EXPORT_PYTHON (optional)  Interpreter to use for the python-markdown
#                  leg. Absent -> auto-resolved (see PY_MD below).
#   $SOURCE_DATE_EPOCH (optional)   When exported by the caller it pins every
#                  render's timestamp. Absent -> derived per file from the .md's
#                  last-commit time (constant 1785674948 for untracked files).
#
# Outputs:
#   <name>.html  always (pandoc --standalone, or python-markdown + charset head)
#   <name>.pdf   when the weasyprint CLI is on PATH
#   <name>.docx  when pandoc is on PATH (no pure-python fallback exists)
#
# Dependencies (all optional, each leg SKIPs honestly when absent — §11.4.3):
#   pandoc      -> HTML + DOCX.        weasyprint (CLI) -> PDF.
#   python3 with the `markdown` module -> HTML fallback when pandoc is absent.
#   Neither pandoc nor a markdown-capable interpreter -> hard error, no output.
#   NEVER emits a blank or placeholder file: a leg that cannot run writes nothing.
#
# Side-effects: writes .html/.pdf/.docx siblings next to each source .md.
# Idempotent: regenerates a twin only when it is STALE per
#             scripts/lib/export_staleness.sh — the same oracle the pre-build
#             gate uses (missing twin; locally-edited source newer than twin;
#             or, for committed files, the .md's last commit more recent than
#             the twin's). A pure mtime difference (touch, checkout order)
#             never regenerates. Plus the charset self-heal rule in convert_file.
#             Output is byte-stable: SOURCE_DATE_EPOCH is pinned per file.
#             Dependencies: git (for the oracle; outside a work tree -> mtime).
#
# Cross-references: docs/scripts/generate_markdown_exports.md (companion guide),
#   scripts/lib/export_staleness.sh (shared staleness oracle),
#   tests/unit/test_generate_markdown_exports_content_staleness.sh (BOB-249 guard),
#   scripts/pre_build/check_cm_export_charset_valid.sh (the gate over its output),
#   tests/unit/test_export_pdf_charset_integrity.sh (the paired §1.1 guard).
#
# Constitution: §11.4.65 Universal Markdown export mandate, §11.4.18 script docs

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HTML_GENERATED=0
HTML_MISSING=0
PDF_GENERATED=0
PDF_MISSING=0
DOCX_GENERATED=0
DOCX_MISSING=0

# PY_MD — an interpreter that can actually `import markdown`, resolved by
# TRYING THE IMPORT, never by assuming a path exists (§11.4.6 no-guessing).
# WHY MORE THAN system python3 (measured 2026-09-01): this host's /usr/bin/python3
# has no pip and is PEP-668 EXTERNALLY-MANAGED, so `markdown` cannot live there
# without root — but the repo's own .venv (the interpreter CLAUDE.md already
# prescribes for pytest) can hold it with no privilege at all. Probing only
# system python3 declared the whole HTML leg unavailable on a host that was
# fully capable of it — the §11.4.201(11) prerequisite-vs-artifact false
# negative. Order: explicit override, then repo venv, then system.
PY_MD=""
for _cand in "${BOBA_EXPORT_PYTHON:-}" "${PROJECT_ROOT}/.venv/bin/python" python3; do
    [[ -n "$_cand" ]] || continue
    if command -v "$_cand" &>/dev/null && "$_cand" -c "import markdown" &>/dev/null 2>&1; then
        PY_MD="$_cand"
        break
    fi
done

if command -v pandoc &>/dev/null; then
    CONVERTER="pandoc"
elif [[ -n "$PY_MD" ]]; then
    CONVERTER="python-markdown"
else
    echo "Error: neither pandoc nor python-markdown is available" >&2
    echo "  probed for \`import markdown\`: ${BOBA_EXPORT_PYTHON:+\$BOBA_EXPORT_PYTHON, }${PROJECT_ROOT}/.venv/bin/python, python3" >&2
    echo "  remedy (no root needed): uv pip install --python .venv/bin/python markdown" >&2
    exit 1
fi

# PROBE THE ARTIFACT THROUGH ITS REAL INVOCATION PATH, not a prerequisite
# (§11.4.201(11)). This previously ALSO required `python3 -c "from weasyprint
# import HTML"` to succeed — but the code below never imports weasyprint, it
# execs the `weasyprint` CLI. A CLI installed into its own isolated environment
# (uv tool install, pipx, a venv on PATH) is fully working and yet invisible to
# a system-interpreter import probe, so the gate answered "no PDF support" on a
# host that renders PDFs correctly — the false-negative half of §11.4.201, and
# the exact shape §11.4.201(11) names. `weasyprint --version` exercises the real
# entry point, so it cannot claim a capability the render path does not have.
HAS_WEASYPRINT=false
if command -v weasyprint &>/dev/null && weasyprint --version &>/dev/null 2>&1; then
    HAS_WEASYPRINT=true
fi

# DOCX export requires pandoc (no pure-python fallback).
HAS_PANDOC_DOCX=false
if command -v pandoc &>/dev/null; then
    HAS_PANDOC_DOCX=true
fi

# STALENESS ORACLE — the SAME one the gate uses (BOB-249).
# The writer used to decide staleness with plain mtime (`$md -nt $twin`) while
# CM-MARKDOWN-EXPORT-SYNC (invariant 16) uses the content-history ordinal oracle
# below. A fresh checkout writes x.docx and x.html BEFORE x.md (path order), so
# measured on a scratch clone 226 of 455 .md files were strictly newer than their
# .docx and 34 than their .html: the writer rewrote them all with zero content
# change. Sharing the oracle makes writer and gate agree on what "stale" means:
# a clean (committed) source is judged by git history, a locally-edited or
# untracked one by mtime, a missing twin is always stale.
# The lib is resolved next to THIS script. When absent (a test copying only this
# file into a sandbox) or when a file is not inside a git work tree, we fall back
# to plain mtime — the oracle's own documented "unresolvable" rule — and say so
# on stderr, never silently (§11.4.201(6)).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HAS_ORACLE=false
if [[ -f "${SCRIPT_DIR}/lib/export_staleness.sh" ]]; then
    # shellcheck source=scripts/lib/export_staleness.sh
    source "${SCRIPT_DIR}/lib/export_staleness.sh"
    HAS_ORACLE=true
else
    echo "WARN: ${SCRIPT_DIR}/lib/export_staleness.sh not found — staleness falls back to plain mtime" >&2
fi

# Deterministic timestamp for generated exports (BOB-249). pandoc stamps the
# wall-clock time into docx docProps/core.xml, so every regeneration was a
# byte-different .docx even with zero content change. SOURCE_DATE_EPOCH is the
# reproducible-builds knob pandoc honours (the same one
# constitution/scripts/render/render-governance-twins.sh pins). We derive it PER
# FILE from the .md's last-commit time, so the stamp is a property of the source
# history, identical in every FULL-history clone (in a shallow clone
# `git log -1 -- <md>` returns the boundary commit's time, so the stamp differs;
# measured 1790428767 full vs 1790428777 shallow). Untracked (never-committed) sources get a
# fixed, content-independent constant: 1785674948 = 2026-08-02T12:49:08Z, the
# value the governance renderer uses. An explicitly exported SOURCE_DATE_EPOCH
# from the caller wins (standard reproducible-builds convention).
# Limit (documented, not hidden): a twin generated while its .md is dirty carries
# the PREVIOUS commit's time; once that .md is committed a forced regeneration
# carries the new commit's time — deterministic per (content, history) pair, not
# per content alone. The staleness oracle does not force such regenerations.
# weasyprint 69.0 PDFs are already byte-stable (measured); the export is applied
# to it anyway at no cost.
DEFAULT_SOURCE_DATE_EPOCH=1785674948
CALLER_SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-}"

declare -A _ROOT_OF_DIR=()
# repo_root_of <abs_dir> -> physical git toplevel, or "" when not in a work tree.
repo_root_of() {
    local d="$1"
    if [[ -z "${_ROOT_OF_DIR[$d]+x}" ]]; then
        _ROOT_OF_DIR[$d]="$(git -C "$d" rev-parse --show-toplevel 2>/dev/null || true)"
    fi
    printf '%s' "${_ROOT_OF_DIR[$d]}"
}

# is_stale <source> <twin> <root> — 0 = stale. Oracle when available + rooted,
# else plain mtime (missing twin is always stale).
is_stale() {
    local src="$1" twin="$2" root="$3"
    [[ -f "$twin" ]] || return 0
    if $HAS_ORACLE && [[ -n "$root" ]]; then
        export_is_stale "$src" "$twin" "$root"
        return $?
    fi
    [[ "$src" -nt "$twin" ]]
}

# source_epoch <abs_md> <root> -> SOURCE_DATE_EPOCH value for this file.
source_epoch() {
    local md="$1" root="$2" ct=""
    if [[ -n "$CALLER_SOURCE_DATE_EPOCH" ]]; then printf '%s' "$CALLER_SOURCE_DATE_EPOCH"; return; fi
    if [[ -n "$root" ]]; then
        ct="$(git -C "$root" -c core.quotePath=false log -1 --format=%ct -- "${md#"${root}/"}" 2>/dev/null || true)"
    fi
    printf '%s' "${ct:-$DEFAULT_SOURCE_DATE_EPOCH}"
}

convert_file() {
    # Absolute, physical path: the oracle keys on "<root>/<rel>" and git's
    # toplevel is physical, so a relative or symlinked argument must be
    # normalised first or every lookup would miss (and fall back to mtime).
    local md
    md="$(cd "$(dirname "$1")" && pwd -P)/$(basename "$1")"
    local html="${md%.md}.html"
    local pdf="${md%.md}.pdf"
    local docx="${md%.md}.docx"
    local root html_regenerated=false
    root="$(repo_root_of "$(dirname "$md")")"
    export SOURCE_DATE_EPOCH
    SOURCE_DATE_EPOCH="$(source_epoch "$md" "$root")"

    # Generate HTML
    # STALENESS IS NOT ONLY mtime (BOB-169 review, finding F7 + acceptance (c)).
    # A pre-BOB-169 export is a charset-less FRAGMENT that is mtime-FRESH, so an
    # mtime-only test leaves it in place forever — and if its .pdf is missing,
    # weasyprint re-bakes the mojibake from that stale fragment (reproduced by the
    # reviewer). Measured 2026-08-23: 303 such fragments, 302 of them mtime-fresh.
    # Treat "HTML exists but declares no charset" as STALE so the corpus self-heals
    # on the next run instead of requiring a manual sweep.
    if is_stale "$md" "$html" "$root" || ! grep -qiE '<meta[^>]+charset' "$html" 2>/dev/null; then
        html_regenerated=true
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
            # Encoding is PINNED on both legs (§11.4.6): the corpus carries
            # Cyrillic ("Боба") and §, and open() would otherwise inherit the
            # ambient locale — a C/POSIX locale silently mangles the read and
            # the charset meta tag below would then be advertising a lie.
            "$PY_MD" -c "
import markdown, sys
md = open(sys.argv[1], encoding='utf-8').read()
html = markdown.markdown(md, extensions=['tables', 'fenced_code'])
title = sys.argv[3] if len(sys.argv) > 3 else 'Document'
out = f'<!DOCTYPE html><html><head><meta charset=\"utf-8\"><title>{title}</title></head><body>{html}</body></html>'
open(sys.argv[2], 'w', encoding='utf-8').write(out)
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
        # html_regenerated is checked explicitly: the oracle caches the
        # working-tree dirty set once per run, so an HTML rewritten moments ago
        # in THIS run still reads "clean" to it — without this flag a healed
        # charset fragment would leave its corrupt PDF in place (guarded by T4 of
        # tests/unit/test_generate_markdown_exports_content_staleness.sh).
        if $html_regenerated || is_stale "$md" "$pdf" "$root" || is_stale "$html" "$pdf" "$root"; then
            mkdir -p "$(dirname "$pdf")"
            PDF_MISSING=$((PDF_MISSING + 1))
            weasyprint "$html" "$pdf" 2>/dev/null && PDF_GENERATED=$((PDF_GENERATED + 1)) || true
        fi
    fi

    # Generate DOCX directly from the markdown via pandoc if available.
    if $HAS_PANDOC_DOCX; then
        if is_stale "$md" "$docx" "$root"; then
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

if (( $# > 0 )); then
    # EXPLICIT SCOPE. Every argument must be a real, readable .md file; an
    # unresolvable one is a hard error, never a silent skip, so a typo'd path
    # cannot masquerade as "nothing to do" (§11.4.201(6): a quiet zero from a
    # blind instrument reads exactly like a clean corpus).
    echo "Scope: ${#} explicitly named file(s)"
    for md in "$@"; do
        if [[ ! -f "$md" ]]; then
            echo "Error: not a file: $md" >&2
            exit 1
        fi
        if [[ "$md" != *.md ]]; then
            echo "Error: not a .md source: $md" >&2
            exit 1
        fi
        convert_file "$md"
    done
else
    echo "Scope: full sweep (root + docs/ + scripts/)"

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
fi

echo "Generated $HTML_GENERATED of $HTML_MISSING missing HTML files"
$HAS_WEASYPRINT && echo "Generated $PDF_GENERATED of $PDF_MISSING missing PDF files"
$HAS_PANDOC_DOCX && echo "Generated $DOCX_GENERATED of $DOCX_MISSING missing DOCX files"
echo "Done."
exit 0
