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
# Exit codes: 0 done; 1 no HTML converter / a bad explicit argument; 2 the run
#   completed but >=1 HTML leg failed (each reported as an ERROR line on stderr;
#   PDF/DOCX leg failures stay non-fatal and are reported as WARN lines).
#
# Side-effects: writes .html/.pdf/.docx siblings next to each source .md.
#   Every leg renders into a private mktemp dir first; a render byte-identical
#   to the existing twin is NOT rewritten (only touched). Each .html carries two
#   provenance <meta> elements (source sha256 + dcterms.modified = the file's
#   SOURCE_DATE_EPOCH) so a newer source revision always yields committable bytes.
#   Exception: a twin that is a node of a .docs_chain/contexts/*.yaml context is
#   rendered byte-identically to the docs_chain engine (its argv, epoch
#   946684800, no provenance) so the engine's verify stays green. Installs are
#   atomic same-directory renames that keep the twin's mode.
#   An existing twin that fails a cheap STRUCTURAL validity check (html: charset
#   + </html>; pdf: %PDF- + %%EOF; docx: zip magic + word/document.xml) is
#   regenerated. Needs sha256sum, cmp, od; unzip optional.
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
#   tests/unit/test_generate_markdown_exports_review_followups.sh (M1/M3/M4 guard),
#   tests/unit/test_generate_markdown_exports_engine_parity.sh (I1/M-a/M-b guard),
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

# Scratch space for renders. Every leg renders into here first and only then
# installs the result (install_render). The render itself may live on a
# different filesystem (TMPDIR is tmpfs on some hosts) — install_render never
# moves it across filesystems (see there).
EXPORT_WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/md_exports.XXXXXX")"
INSTALL_STAGE=""
# The EXIT trap removes the render dir AND an in-flight install temp. INT/TERM
# are routed through `exit` so the EXIT trap also runs on Ctrl-C / kill (bash
# does not run EXIT traps on an untrapped fatal signal). SIGKILL cannot be
# trapped; its leftover is named "*.tmp", which the project .gitignore already
# ignores, and never matches a twin pattern (*.html / *.pdf / *.docx).
trap 'rm -rf "$EXPORT_WORKDIR"; [[ -n "$INSTALL_STAGE" ]] && rm -f "$INSTALL_STAGE"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
# Mode for a brand-new twin: the umask default a plain redirect would give
# (mktemp creates 0600, which must never leak into the repo).
NEW_TWIN_MODE="$(printf '%o' $(( 0666 & ~0$(umask) )))"
HTML_UNCHANGED=0
PDF_UNCHANGED=0
DOCX_UNCHANGED=0
HTML_FAILED=0
PDF_FAILED=0
DOCX_FAILED=0

# install_render <rendered_tmp> <twin>
#   -> 0 = new bytes installed, 1 = identical (not rewritten), 2 = install FAILED
#      (the previous twin, if any, is untouched and an ERROR line is printed).
# BOB-249 review M1: a render byte-identical to the existing twin is NOT
# rewritten. The twin is only re-stamped (touch), which records "verified
# against the current source" for the mtime half of the staleness oracle, so a
# dirty/untracked source is not re-rendered again on the next run. Nothing is
# claimed about git history: identical bytes cannot be committed, which is why
# the HTML carries a provenance record (see html_provenance_head below).
# BOB-249 review M-b: the render lives in EXPORT_WORKDIR, which can be another
# filesystem (tmpfs). `mv` across filesystems is NOT a rename — measured under
# strace: renameat2 -> EXDEV, then unlink(dest), then create + copy — so an
# interrupt or ENOSPC could leave the twin missing or partial, and the new file
# got the umask mode instead of the twin's. So the bytes are first copied to a
# temp file in the twin's OWN directory (same filesystem), given the existing
# twin's mode (or the umask default for a new twin), and only then renamed over
# the twin with `mv -f` — an atomic rename(2). Every failure path removes the
# temp and leaves the previous twin exactly as it was.
install_render() {
    local tmp="$1" dest="$2" dir base
    if [[ -f "$dest" ]] && cmp -s "$tmp" "$dest"; then
        rm -f "$tmp"
        touch "$dest"
        return 1
    fi
    dir="$(dirname "$dest")"; base="$(basename "$dest")"
    if INSTALL_STAGE="$(mktemp --suffix=.tmp "${dir}/.${base}.exporttmp.XXXXXX")" \
        && cat "$tmp" > "$INSTALL_STAGE" \
        && if [[ -e "$dest" ]]; then chmod --reference="$dest" "$INSTALL_STAGE"; else chmod "$NEW_TWIN_MODE" "$INSTALL_STAGE"; fi \
        && mv -f "$INSTALL_STAGE" "$dest"; then
        INSTALL_STAGE=""
        rm -f "$tmp"
        return 0
    fi
    [[ -n "$INSTALL_STAGE" ]] && rm -f "$INSTALL_STAGE"
    INSTALL_STAGE=""
    rm -f "$tmp"
    echo "ERROR: could not install ${dest} (write/rename in its directory failed); previous twin, if any, left in place" >&2
    return 2
}

# twin_valid <html|pdf|docx> <path> -> 0 = structurally valid.
# BOB-249 review M3: staleness is a question about HISTORY, not about CONTENT,
# so a twin corrupted after generation (garbage bytes with a newer mtime, or a
# committed corruption) was judged "fresh" forever by writer and gate alike.
# This is a CHEAP STRUCTURAL check, deliberately not a byte comparison with a
# fresh render (that would re-render the whole corpus every run):
#   html  <meta ... charset> element (the BOB-169 rule) + a closing </html>
#   pdf   %PDF- header + %%EOF in the trailer
#   docx  zip local-header magic + a word/document.xml member (unzip optional)
# Pipelines feeding `grep -q` are avoided on purpose: grep -q exits at the first
# match, the producer then dies of SIGPIPE, and under `pipefail` a VALID twin
# would read as invalid and be regenerated every run (§11.4.201(12)).
HAS_UNZIP=false
command -v unzip &>/dev/null && HAS_UNZIP=true
twin_valid() {
    local kind="$1" f="$2" head tail_bytes
    [[ -s "$f" ]] || return 1
    case "$kind" in
        html)
            grep -qiE '<meta[^>]+charset' "$f" && grep -qi '</html>' "$f"
            ;;
        pdf)
            head="$(head -c 5 "$f" | tr -d '\0')"
            [[ "$head" == "%PDF-" ]] || return 1
            tail_bytes="$(tail -c 1024 "$f" | tr -d '\0')"
            [[ "$tail_bytes" == *"%%EOF"* ]]
            ;;
        docx)
            head="$(head -c 4 "$f" | od -An -tx1 | tr -d ' \n')"
            [[ "$head" == "504b0304" ]] || return 1
            $HAS_UNZIP || return 0
            grep -q 'word/document\.xml' < <(unzip -l "$f" 2>/dev/null)
            ;;
        *) return 1 ;;
    esac
}

# html_provenance_head <abs_md> -> <meta> lines recording what the HTML was
# built from. BOB-249 review M1: without this, a whitespace-only .md commit
# regenerates byte-IDENTICAL .html/.pdf, so nothing can be committed and the
# gate's history oracle calls the pair stale forever. The sha256 is the source
# CONTENT the twin was built from; dcterms.modified is the source REVISION time
# (the same per-file SOURCE_DATE_EPOCH already stamped into the .docx), and
# weasyprint maps it into the PDF's ModDate, so the PDF moves with it. Both are
# pure functions of (content, history): byte-stable, never wall-clock.
html_provenance_head() {
    local md="$1" src_sha iso
    src_sha="$(sha256sum "$md" | cut -d' ' -f1)"
    printf '<meta name="x-export-source-sha256" content="%s">\n' "$src_sha"
    if iso="$(date -u -d "@${SOURCE_DATE_EPOCH}" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null)"; then
        printf '<meta name="dcterms.modified" content="%s">\n' "$iso"
    fi
}

# insert_provenance <head_file> <in_html> <out_html>
# BOB-249 review M-a: the provenance lines used to be passed as `pandoc -H`,
# and -H does NOT append — measured: a document's own YAML `header-includes`
# is present without -H and GONE with it. So pandoc now runs with no -H and the
# lines are inserted afterwards, immediately before the FIRST `</head>`. The
# first occurrence is always the head's own closing tag: the <head> precedes the
# <body>, and pandoc escapes `</head>` in title/metadata text, so a literal
# `</head>` in raw body HTML comes later and is never touched. LC_ALL=C keeps
# awk byte-exact on UTF-8 input. Each line gets pandoc's two-space head
# indentation, so the bytes equal what `-H` produced for a document without
# its own header-includes. Fails (non-zero) if no `</head>` is found.
insert_provenance() {
    LC_ALL=C awk -v hf="$1" '
        BEGIN { while ((getline l < hf) > 0) h = h "  " l "\n" }
        !done {
            i = index($0, "</head>")
            if (i) {
                if (i > 1) print substr($0, 1, i - 1)
                printf "%s", h
                print substr($0, i)
                done = 1
                next
            }
        }
        { print }
        END { exit(done ? 0 : 1) }' "$2" > "$3"
}

# Docs Chain ownership (BOB-249 review I1). A twin that is a NODE of a
# .docs_chain/contexts/*.yaml context is owned by the docs_chain engine, whose
# `verify` (pre-build invariant 24, CM-DOCS-CHAIN-ENGINE-VERIFY) recomputes it
# with its builtin transform and compares BYTES. Such a twin is therefore
# rendered exactly as constitution/submodules/docs_chain/internal/adapter/
# derived.go renders it — same argv, SOURCE_DATE_EPOCH pinned to the engine's
# reproducibleEpoch, no provenance tags — so running this generator before
# `docs_chain sync` can never make invariant 24 fail. Every other twin keeps
# the provenance tags. Ownership is read from the node `path:` values; a
# context file declaring none (unparsable, or a schema this reader does not
# understand) earns a one-line NOTE and its files are treated as NOT owned; a
# project with no .docs_chain/ directory is simply not a docs_chain project.
DOCS_CHAIN_EPOCH=946684800   # derived.go: reproducibleEpoch (2000-01-01T00:00:00Z)
declare -A _ENGINE_NODE=() _ENGINE_ROOT_LOADED=()
load_engine_nodes() {
    local root="$1" dir f p n
    [[ -n "$root" && -z "${_ENGINE_ROOT_LOADED[$root]+x}" ]] || return 0
    _ENGINE_ROOT_LOADED[$root]=1
    [[ -d "${root}/.docs_chain" ]] || return 0
    dir="${root}/.docs_chain/contexts"
    if [[ ! -d "$dir" ]]; then
        echo "NOTE: ${root}/.docs_chain has no contexts/ directory — no twin treated as docs_chain-owned" >&2
        return 0
    fi
    for f in "$dir"/*.yaml "$dir"/*.yml; do
        [[ -f "$f" ]] || continue
        n=0
        while IFS= read -r p; do
            p="${p%\"}"; p="${p#\"}"; p="${p%\'}"; p="${p#\'}"; p="${p#./}"
            [[ -n "$p" ]] || continue
            [[ "$p" == /* ]] || p="${root}/${p}"
            _ENGINE_NODE["$p"]=1
            n=$((n + 1))
        done < <(grep -v '^[[:space:]]*#' "$f" 2>/dev/null \
                 | grep -oE '(^|[{,[:space:]])path:[[:space:]]*[^,}[:space:]#]+' \
                 | sed -E 's/^.*path:[[:space:]]*//' || true)
        (( n > 0 )) || echo "NOTE: docs_chain context ${f} declares no node path (unparsable?) — its files are treated as not engine-owned" >&2
    done
}
# engine_owned <abs_twin> <root> -> 0 when the twin is a docs_chain node.
engine_owned() {
    load_engine_nodes "$2"
    [[ -n "${_ENGINE_NODE[$1]+x}" ]]
}

# leg_error <leg> <md> <rc> <stderr_file> — loud, never silent (BOB-249 review M4).
leg_error() {
    echo "ERROR: ${1} export failed for ${2} (exit ${3}):" >&2
    sed 's/^/    /' "$4" >&2 2>/dev/null || true
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
    local root rc irc html_regenerated=false html_failed=false
    local tmp err="${EXPORT_WORKDIR}/err" title
    local own_html=false own_pdf=false own_docx=false
    root="$(repo_root_of "$(dirname "$md")")"
    title="$(basename "$md" .md)"
    engine_owned "$html" "$root" && own_html=true
    engine_owned "$pdf" "$root" && own_pdf=true
    engine_owned "$docx" "$root" && own_docx=true
    export SOURCE_DATE_EPOCH
    SOURCE_DATE_EPOCH="$(source_epoch "$md" "$root")"

    # Generate HTML
    # STALENESS IS NOT ONLY mtime (BOB-169 review, finding F7 + acceptance (c)).
    # A pre-BOB-169 export is a charset-less FRAGMENT that is mtime-FRESH, so an
    # mtime-only test leaves it in place forever — and if its .pdf is missing,
    # weasyprint re-bakes the mojibake from that stale fragment (reproduced by the
    # reviewer). Measured 2026-08-23: 303 such fragments, 302 of them mtime-fresh.
    # Treat "HTML exists but declares no charset" as STALE so the corpus self-heals
    # on the next run instead of requiring a manual sweep. twin_valid carries
    # that rule plus the M3 truncation check.
    if is_stale "$md" "$html" "$root" || ! twin_valid html "$html"; then
        mkdir -p "$(dirname "$html")"
        HTML_MISSING=$((HTML_MISSING + 1))
        tmp="${EXPORT_WORKDIR}/twin.html"
        # A docs_chain-owned twin carries NO provenance (engine byte parity, I1).
        if $own_html; then : > "${EXPORT_WORKDIR}/head.html"
        else html_provenance_head "$md" > "${EXPORT_WORKDIR}/head.html"; fi

        # BOB-249 review M4: the converter used to run bare under `set -e` with
        # stderr discarded, so one failing render aborted the WHOLE run with no
        # diagnostic (exit 3, the DOCX leg and every later file never
        # processed), and html_regenerated was already true before the attempt.
        # Now the failure is caught, reported, counted (exit 2 at the end), the
        # stale HTML is left as it was, and the PDF is not re-derived from it.
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
            # The provenance lines are inserted AFTER pandoc (insert_provenance):
            # `-H` is NOT used because it suppresses a document's own YAML
            # header-includes (BOB-249 review M-a, measured).
            if $own_html; then
                # Exactly the engine's pandoc-html argv + epoch (derived.go).
                if SOURCE_DATE_EPOCH="$DOCS_CHAIN_EPOCH" pandoc --standalone --from=markdown --to=html \
                    --metadata "title=${title}" -o "$tmp" "$md" 2>"$err"; then rc=0; else rc=$?; fi
            elif pandoc -f markdown -t html5 --standalone -o "${tmp}.raw" "$md" \
                    --metadata title="$title" 2>"$err"; then
                if insert_provenance "${EXPORT_WORKDIR}/head.html" "${tmp}.raw" "$tmp" 2>>"$err"; then rc=0
                else rc=$?; echo "pandoc output has no </head> to receive the provenance lines" >> "$err"; fi
                rm -f "${tmp}.raw"
            else
                rc=$?
            fi
        else
            # Encoding is PINNED on both legs (§11.4.6): the corpus carries
            # Cyrillic ("Боба") and §, and open() would otherwise inherit the
            # ambient locale — a C/POSIX locale silently mangles the read and
            # the charset meta tag below would then be advertising a lie.
            if "$PY_MD" -c "
import markdown, sys
md = open(sys.argv[1], encoding='utf-8').read()
html = markdown.markdown(md, extensions=['tables', 'fenced_code'])
title = sys.argv[3] if len(sys.argv) > 3 else 'Document'
head = open(sys.argv[4], encoding='utf-8').read() if len(sys.argv) > 4 else ''
out = f'<!DOCTYPE html><html><head><meta charset=\"utf-8\"><title>{title}</title>{head}</head><body>{html}</body></html>'
open(sys.argv[2], 'w', encoding='utf-8').write(out)
" "$md" "$tmp" "$(basename "$md" .md)" "${EXPORT_WORKDIR}/head.html" 2>"$err"; then rc=0; else rc=$?; fi
        fi
        if (( rc == 0 )) && twin_valid html "$tmp"; then
            irc=0; install_render "$tmp" "$html" || irc=$?
            case "$irc" in
                0) HTML_GENERATED=$((HTML_GENERATED + 1)); html_regenerated=true ;;
                1) HTML_GENERATED=$((HTML_GENERATED + 1)); HTML_UNCHANGED=$((HTML_UNCHANGED + 1)) ;;
                *) html_failed=true; HTML_FAILED=$((HTML_FAILED + 1)) ;;
            esac
        else
            (( rc != 0 )) || echo "converter exited 0 but produced no structurally valid HTML" >> "$err"
            rm -f "$tmp"
            html_failed=true
            HTML_FAILED=$((HTML_FAILED + 1))
            leg_error HTML "$md" "$rc" "$err"
        fi
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
        # It is set only when new HTML bytes were really installed (M4).
        if $html_failed; then
            echo "WARN: PDF of ${md} not re-derived — its HTML leg failed, and a PDF baked from the stale HTML would look fresh" >&2
        elif $html_regenerated || is_stale "$md" "$pdf" "$root" || is_stale "$html" "$pdf" "$root" \
                || ! twin_valid pdf "$pdf"; then
            mkdir -p "$(dirname "$pdf")"
            PDF_MISSING=$((PDF_MISSING + 1))
            tmp="${EXPORT_WORKDIR}/twin.pdf"
            # A docs_chain-owned PDF is rendered with the engine's argv: epoch
            # pinned and --base-url pinned to the LIVE pdf path (derived.go).
            if $own_pdf; then
                if SOURCE_DATE_EPOCH="$DOCS_CHAIN_EPOCH" weasyprint --base-url "$pdf" "$html" "$tmp" 2>"$err"; then rc=0; else rc=$?; fi
            else
                if weasyprint "$html" "$tmp" 2>"$err"; then rc=0; else rc=$?; fi
            fi
            if (( rc == 0 )) && twin_valid pdf "$tmp"; then
                irc=0; install_render "$tmp" "$pdf" || irc=$?
                case "$irc" in
                    0) PDF_GENERATED=$((PDF_GENERATED + 1)) ;;
                    1) PDF_GENERATED=$((PDF_GENERATED + 1)); PDF_UNCHANGED=$((PDF_UNCHANGED + 1)) ;;
                    *) PDF_FAILED=$((PDF_FAILED + 1)) ;;
                esac
            else
                # Exit status unchanged for this leg (a missing PDF was always a
                # counted, non-fatal outcome); the failure is now at least visible.
                rm -f "$tmp"
                PDF_FAILED=$((PDF_FAILED + 1))
                echo "WARN: PDF export failed for ${md}; previous twin (if any) left in place" >&2
            fi
        fi
    fi

    # Generate DOCX directly from the markdown via pandoc if available.
    if $HAS_PANDOC_DOCX; then
        if is_stale "$md" "$docx" "$root" || ! twin_valid docx "$docx"; then
            mkdir -p "$(dirname "$docx")"
            DOCX_MISSING=$((DOCX_MISSING + 1))
            tmp="${EXPORT_WORKDIR}/twin.docx"
            if $own_docx; then
                # Exactly the engine's pandoc-docx argv + epoch (derived.go).
                if SOURCE_DATE_EPOCH="$DOCS_CHAIN_EPOCH" pandoc --from=markdown --to=docx \
                    --metadata "title=${title}" -o "$tmp" "$md" 2>"$err"; then rc=0; else rc=$?; fi
            else
                if pandoc -f markdown -t docx -o "$tmp" "$md" 2>"$err"; then rc=0; else rc=$?; fi
            fi
            if (( rc == 0 )) && twin_valid docx "$tmp"; then
                irc=0; install_render "$tmp" "$docx" || irc=$?
                case "$irc" in
                    0) DOCX_GENERATED=$((DOCX_GENERATED + 1)) ;;
                    1) DOCX_GENERATED=$((DOCX_GENERATED + 1)); DOCX_UNCHANGED=$((DOCX_UNCHANGED + 1)) ;;
                    *) DOCX_FAILED=$((DOCX_FAILED + 1)) ;;
                esac
            else
                rm -f "$tmp"
                DOCX_FAILED=$((DOCX_FAILED + 1))
                echo "WARN: DOCX export failed for ${md}; previous twin (if any) left in place" >&2
            fi
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

echo "Generated $HTML_GENERATED of $HTML_MISSING missing HTML files ($HTML_UNCHANGED byte-identical, not rewritten; $HTML_FAILED failed)"
$HAS_WEASYPRINT && echo "Generated $PDF_GENERATED of $PDF_MISSING missing PDF files ($PDF_UNCHANGED byte-identical, not rewritten; $PDF_FAILED failed)"
$HAS_PANDOC_DOCX && echo "Generated $DOCX_GENERATED of $DOCX_MISSING missing DOCX files ($DOCX_UNCHANGED byte-identical, not rewritten; $DOCX_FAILED failed)"
# An HTML-leg failure is the one fatal outcome (BOB-249 review M4): every other
# file and leg was still processed, then the run reports it with exit 2. PDF and
# DOCX failures keep their historical non-fatal status (warned above).
if (( HTML_FAILED > 0 )); then
    echo "Done with ${HTML_FAILED} HTML export failure(s) — see ERROR lines above." >&2
    exit 2
fi
echo "Done."
exit 0
