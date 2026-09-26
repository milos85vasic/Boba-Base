#!/usr/bin/env bash
# test_generate_markdown_exports_content_staleness.sh — writer/gate staleness
# agreement + byte-stable regeneration guard for scripts/generate_markdown_exports.sh.
#
# THE DEFECT (measured 2026-09-26): the WRITER decided staleness with plain
# mtime (`$md -nt $twin`) while the GATE (CM-MARKDOWN-EXPORT-SYNC, invariant 16)
# uses the content-history ordinal oracle in scripts/lib/export_staleness.sh.
# A fresh `git checkout` writes files in path order (x.docx, x.html BEFORE x.md),
# so on a scratch clone 226 of 455 .md files were strictly newer than their own
# .docx and 34 than their .html — and the writer rewrote every one of them with
# ZERO content change. Because pandoc stamps the wall-clock time into
# docx docProps/core.xml, each rewrite was also a byte-different .docx, so a
# pure checkout produced a dirty tree of meaningless churn.
#
# ASSERTIONS (all in a throwaway git repo under mktemp; the real docs tree is
# never touched — the generator is invoked in explicit-scope mode on sandbox
# files only):
#   T1  touch-only (the checkout-order shape): .md mtime newer than every twin,
#       content unchanged and committed -> ZERO twins rewritten (bytes AND mtime
#       unchanged).                                              [RED before fix]
#   T2  real content edit of the .md -> all three twins rewritten and the new
#       text present in the html and in the docx body.           [anti-bluff half]
#   T3  missing twin -> regenerated.                             [anti-bluff half]
#   T4  charset-less HTML fragment that is mtime-FRESH and committed -> HTML is
#       rewritten with a charset AND the PDF derived from it is rewritten too.
#   T5  determinism: regenerating the same content twice (1.1 s apart) yields a
#       byte-identical .docx (and .pdf).                         [RED before fix]
#
# Each leg needing pandoc / weasyprint SKIPs honestly when the tool is absent
# (§11.4.3) — it never counts as a PASS.
#
# Constitution: §11.4.65 export sync, §11.4.115 RED-first, §11.4.201 guard
# asserts the real condition, §11.4.246 reproducible builds, §11.4.273 needled
# measurement (T2/T3 are the positive controls that prove T1's zero is real).

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${HERE}/../.." && pwd)"
GEN="${PROJECT_ROOT}/scripts/generate_markdown_exports.sh"

PASS=0; FAIL=0; SKIP=0
pass() { echo "PASS: $*"; PASS=$((PASS + 1)); }
fail() { echo "FAIL: $*"; FAIL=$((FAIL + 1)); }
skip() { echo "SKIP: $*"; SKIP=$((SKIP + 1)); }

[[ -f "$GEN" ]] || { echo "FAIL: generator missing: $GEN"; exit 1; }
command -v git >/dev/null || { echo "SKIP: git not available"; exit 0; }
HAS_PANDOC=false; command -v pandoc >/dev/null && HAS_PANDOC=true
HAS_WP=false; command -v weasyprint >/dev/null && weasyprint --version >/dev/null 2>&1 && HAS_WP=true
if ! $HAS_PANDOC; then echo "SKIP: pandoc absent — every leg of this test needs it"; exit 0; fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
R="$TMP/repo"
mkdir -p "$R/docs"
G() { git -C "$R" -c user.name=t -c user.email=t@t -c commit.gpgsign=false "$@"; }
G init -q
run_gen() { GOMAXPROCS=2 nice -n 19 bash "$GEN" "$@" > "$TMP/gen.log" 2>&1; }
mt() { stat -c %Y.%y "$1" 2>/dev/null; }
sha() { sha256sum "$1" 2>/dev/null | cut -d' ' -f1; }

MD="$R/docs/a.md"; B="${MD%.md}"
printf '# Alpha\n\nBody text with § and Боба.\n' > "$MD"
run_gen "$MD"
[[ -f "$B.html" && -f "$B.docx" ]] || { cat "$TMP/gen.log"; echo "FAIL: setup could not produce twins"; exit 1; }
G add -A && G commit -q -m init

# ---- T1: touch-only (checkout write order) must rewrite nothing -------------
touch -d '2020-01-01 00:00:00' "$B".html "$B".docx; [[ -f "$B.pdf" ]] && touch -d '2020-01-01 00:00:00' "$B.pdf"
touch "$MD"
declare -A before_sha before_mt
for e in html pdf docx; do [[ -f "$B.$e" ]] || continue; before_sha[$e]="$(sha "$B.$e")"; before_mt[$e]="$(mt "$B.$e")"; done
sleep 1.1
run_gen "$MD"
t1_bad=""
for e in "${!before_sha[@]}"; do
    [[ "$(mt "$B.$e")" == "${before_mt[$e]}" ]] || t1_bad+=" .$e(rewritten)"
    [[ "$(sha "$B.$e")" == "${before_sha[$e]}" ]] || t1_bad+=" .$e(bytes-changed)"
done
if [[ -z "$t1_bad" ]]; then pass "T1 touch-only: 0 of ${#before_sha[@]} twins rewritten"
else fail "T1 touch-only rewrote twins with no content change:$t1_bad"; fi

# ---- T2: real content edit must regenerate all twins ------------------------
printf '\nNEEDLE-T2-CONTENT-EDIT\n' >> "$MD"
for e in html pdf docx; do [[ -f "$B.$e" ]] && before_mt[$e]="$(mt "$B.$e")"; done
sleep 1.1
run_gen "$MD"
t2_bad=""
for e in html docx; do [[ "$(mt "$B.$e")" != "${before_mt[$e]}" ]] || t2_bad+=" .$e(not-rewritten)"; done
grep -q 'NEEDLE-T2-CONTENT-EDIT' "$B.html" || t2_bad+=" html-missing-needle"
unzip -p "$B.docx" word/document.xml 2>/dev/null | grep -q 'NEEDLE-T2-CONTENT-EDIT' || t2_bad+=" docx-missing-needle"
if $HAS_WP; then [[ "$(mt "$B.pdf")" != "${before_mt[pdf]:-x}" ]] || t2_bad+=" .pdf(not-rewritten)"; fi
if [[ -z "$t2_bad" ]]; then pass "T2 content edit: twins regenerated with the new content"
else fail "T2 content edit did not regenerate:$t2_bad"; fi
G add -A && G commit -q -m edit

# ---- T3: missing twin must be regenerated -----------------------------------
rm -f "$B.docx"
run_gen "$MD"
if [[ -s "$B.docx" ]] && unzip -tq "$B.docx" >/dev/null 2>&1; then pass "T3 missing .docx regenerated"
else fail "T3 missing .docx NOT regenerated"; fi
G add -A && G commit -q -m restore --allow-empty

# ---- T4: charset-less fragment (mtime-fresh, committed) self-heals ---------
# Real BOB-169 corpus shape: fragment HTML + corrupt PDF committed TOGETHER, so
# the history oracle alone sees html and pdf as same-commit (in sync). Only the
# writer's "HTML was regenerated in this run" rule can re-derive the PDF.
printf '<p>fragment without a head</p>\n' > "$B.html"
$HAS_WP && printf 'corrupt-pdf-baked-from-fragment\n' > "$B.pdf"
touch -d '2020-01-01 00:00:00' "$MD"; touch "$B.html"; $HAS_WP && touch "$B.pdf"
G add -A && G commit -q -m fragment
sleep 1.1
run_gen "$MD"
if grep -qiE '<meta[^>]+charset' "$B.html"; then pass "T4 charset fragment rewritten with a charset"
else fail "T4 charset fragment NOT healed"; fi
if $HAS_WP; then
    if [[ "$(head -c 4 "$B.pdf")" == "%PDF" ]]; then pass "T4 PDF re-derived from the healed HTML"
    else fail "T4 PDF NOT re-derived after its HTML was regenerated (still the committed corrupt one)"; fi
else skip "T4 PDF leg (weasyprint absent)"; fi
G add -A && G commit -q -m healed --allow-empty

# ---- T5: byte-stable regeneration -------------------------------------------
rm -f "$B.docx"; run_gen "$MD"; d1="$(sha "$B.docx")"
sleep 1.1
rm -f "$B.docx"; run_gen "$MD"; d2="$(sha "$B.docx")"
if [[ -n "$d1" && "$d1" == "$d2" ]]; then pass "T5 .docx byte-identical across two regenerations ($d1)"
else fail "T5 .docx differs across regenerations of identical content ($d1 vs $d2)"; fi
if $HAS_WP; then
    rm -f "$B.pdf"; run_gen "$MD"; p1="$(sha "$B.pdf")"
    sleep 1.1
    rm -f "$B.pdf"; run_gen "$MD"; p2="$(sha "$B.pdf")"
    if [[ -n "$p1" && "$p1" == "$p2" ]]; then pass "T5 .pdf byte-identical across two regenerations"
    else fail "T5 .pdf differs across regenerations ($p1 vs $p2)"; fi
else skip "T5 PDF leg (weasyprint absent)"; fi

echo "RESULT: ${PASS} passed, ${FAIL} failed, ${SKIP} skipped"
(( FAIL == 0 )) || exit 1
exit 0
