#!/usr/bin/env bash
# test_generate_markdown_exports_review_followups.sh — guards for the three
# open items two independent reviews left on the BOB-249 writer fix
# (scripts/generate_markdown_exports.sh).
#
# M1  A history-stale pair whose regeneration produced IDENTICAL bytes (a
#     whitespace-only .md commit) stayed stale FOREVER: nothing changed on disk,
#     so nothing could be committed, so the gate's history oracle kept reporting
#     the .html/.pdf stale and every run re-wrote them. Measured before the fix:
#     after `commit ws-only .md` + regenerate, `git status` showed only the .docx
#     (its SOURCE_DATE_EPOCH stamp moved) while .html and .pdf were byte-identical
#     and export_is_stale still said STALE for both.
#     Fix (writer scope only, oracle + gate untouched): every HTML twin records
#     its provenance — sha256 of the source bytes and the source revision time as
#     dcterms.modified, which weasyprint also maps into the PDF ModDate — so a
#     regeneration for a newer source revision always yields committable bytes;
#     and a render byte-identical to the existing twin is NOT rewritten (the twin
#     is only re-stamped, so the mtime oracle agrees it was verified).
# M3  A twin corrupted after generation ('garbage' bytes, newer mtime, or a
#     committed corruption) was never healed: neither writer nor gate checks
#     content. Fix: a cheap STRUCTURAL validity check (never a byte comparison) —
#     html: <meta charset> + closing </html>; pdf: %PDF- header + %%EOF trailer;
#     docx: zip magic + word/document.xml member.
# M4  html_regenerated=true was set BEFORE the HTML leg ran, and the leg ran
#     under `set -e` with stderr discarded: a failing HTML render aborted the
#     whole run silently (rc 3, zero diagnostics, the DOCX leg and every later
#     file never processed). Fix: the leg's failure is caught, reported on stderr
#     with the converter's own message, the PDF is NOT re-derived from the stale
#     HTML, the other legs and files continue, and the run exits 2 at the end.
#
# Anti-bluff (paired controls in this same file): the generator still
# regenerates on (a) a real content change, (b) a missing twin, (c) a
# charset-less HTML fragment; and valid untouched twins are NOT rewritten.
#
# Everything runs in throwaway git repos under mktemp; the generator is invoked
# in explicit-scope mode on sandbox files only. Legs needing weasyprint SKIP
# honestly when it is absent (§11.4.3) — a SKIP is never counted as a PASS.
#
# Constitution: §11.4.65, §11.4.115 RED-first, §11.4.201 real-condition guard,
# §11.4.246 reproducible builds, §11.4.273 needled measurement.

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${HERE}/../.." && pwd)"
GEN="${PROJECT_ROOT}/scripts/generate_markdown_exports.sh"
ORACLE="${PROJECT_ROOT}/scripts/lib/export_staleness.sh"

PASS=0; FAIL=0; SKIP=0
pass() { echo "PASS: $*"; PASS=$((PASS + 1)); }
fail() { echo "FAIL: $*"; FAIL=$((FAIL + 1)); }
skip() { echo "SKIP: $*"; SKIP=$((SKIP + 1)); }

[[ -f "$GEN" && -f "$ORACLE" ]] || { echo "FAIL: generator or oracle missing"; exit 1; }
command -v git >/dev/null || { echo "SKIP: git not available"; exit 0; }
command -v pandoc >/dev/null || { echo "SKIP: pandoc absent — every leg of this test needs it"; exit 0; }
HAS_WP=false; command -v weasyprint >/dev/null && weasyprint --version >/dev/null 2>&1 && HAS_WP=true
HAS_UNZIP=false; command -v unzip >/dev/null && HAS_UNZIP=true
# shellcheck source=scripts/lib/export_staleness.sh
source "$ORACLE"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mt()  { stat -c %Y.%y "$1" 2>/dev/null; }
sha() { sha256sum "$1" 2>/dev/null | cut -d' ' -f1; }
# gate_stale <md> <twin> <root>: the gate's own verdict, fresh maps every call.
gate_stale() { _EXPORT_MAPS_ROOT=""; export_is_stale "$1" "$2" "$3"; }

N=0
# new_repo -> sets R (repo), MD, B (twin base); committed with generated twins.
new_repo() {
    N=$((N + 1)); R="$TMP/r$N"; mkdir -p "$R/docs"
    git -C "$R" init -q
    MD="$R/docs/a.md"; B="${MD%.md}"
    printf '# Alpha\n\nBody text with § and Боба.\n' > "$MD"
    run_gen "$MD" || true
    G add -A && G commit -q -m init
}
G() { git -C "$R" -c user.name=t -c user.email=t@t -c commit.gpgsign=false "$@"; }
RC=0
run_gen() { GOMAXPROCS=2 nice -n 19 bash "$GEN" "$@" > "$TMP/gen.out" 2> "$TMP/gen.err"; RC=$?; return $RC; }
# No `producer | grep -q` under pipefail: an early grep exit SIGPIPEs the
# producer and a valid file would read as invalid (§11.4.201(12)).
valid_docx() { [[ "$(head -c 2 "$1" 2>/dev/null)" == "PK" ]] && { ! $HAS_UNZIP || grep -q 'word/document.xml' < <(unzip -l "$1" 2>/dev/null); }; }
valid_pdf()  { [[ "$(head -c 5 "$1" 2>/dev/null)" == "%PDF-" ]] && grep -qa '%%EOF' < <(tail -c 1024 "$1"); }
docx_has()   { grep -q "$2" < <(unzip -p "$1" word/document.xml 2>/dev/null); }

# ---- M1: whitespace-only commit must converge, not stay stale forever -------
new_repo
sleep 1.1
printf '# Alpha\n\nBody text with § and Боба.\n\n\n' > "$MD"   # whitespace only
G commit -q -am ws-only
run_gen "$MD"
G add -A && G commit -q -m regen --allow-empty
m1_bad=""
legs="html docx"; $HAS_WP && legs="html pdf docx"
for e in $legs; do gate_stale "$MD" "$B.$e" "$R" && m1_bad+=" .$e"; done
if [[ -z "$m1_bad" ]]; then pass "M1 whitespace-only commit: after one regenerate+commit the gate oracle calls every twin fresh"
else fail "M1 whitespace-only commit: still STALE per the gate after regenerate+commit:$m1_bad"; fi
# ...and a second run touches nothing (no every-run rewrite).
declare -A m1_mt=() m1_sha=()
for e in $legs; do m1_mt[$e]="$(mt "$B.$e")"; m1_sha[$e]="$(sha "$B.$e")"; done
sleep 1.1; run_gen "$MD"
m1b_bad=""
for e in $legs; do
    [[ "$(mt "$B.$e")" == "${m1_mt[$e]}" && "$(sha "$B.$e")" == "${m1_sha[$e]}" ]] || m1b_bad+=" .$e"
done
if [[ -z "$m1b_bad" ]]; then pass "M1 converged pair: a further run rewrites nothing"
else fail "M1 converged pair rewritten again on the next run:$m1b_bad"; fi
# provenance is really recorded (positive control that the mechanism is the reason)
if grep -q "name=\"x-export-source-sha256\" content=\"$(sha "$MD")\"" "$B.html"; then pass "M1 html records the source sha256 it was built from"
else fail "M1 html lacks the source-sha256 provenance meta"; fi

# ---- M1c: identical re-render is not rewritten, and is recognised as fresh --
# An untracked source (mtime-judged) that is merely touched renders to the exact
# same bytes: the twin must keep its bytes, and the NEXT run must not re-render.
N=$((N + 1)); R="$TMP/r$N"; mkdir -p "$R/docs"; git -C "$R" init -q
MD="$R/docs/a.md"; B="${MD%.md}"; printf '# Untracked\n\nx\n' > "$MD"
run_gen "$MD"; h0="$(sha "$B.html")"
sleep 1.1; touch "$MD"; run_gen "$MD"; h1="$(sha "$B.html")"; t1="$(mt "$B.html")"
sleep 1.1; run_gen "$MD"; t2="$(mt "$B.html")"
if [[ "$h0" == "$h1" && "$t1" == "$t2" ]]; then pass "M1c identical re-render kept its bytes and was fresh on the next run"
else fail "M1c identical re-render: bytes $h0 -> $h1, next run mtime $t1 -> $t2"; fi

# ---- M3: corrupted twins are healed, valid ones are not touched -------------
new_repo
sleep 1.1
# The HTML is left intact in this step, so no html->pdf dependency can mask the
# pdf result (each corrupted twin is the NEWEST file of its pair).
printf 'garbage\n' > "$B.docx"
$HAS_WP && printf 'garbage\n' > "$B.pdf"
run_gen "$MD"
if valid_docx "$B.docx"; then pass "M3 working-tree-corrupted .docx healed"; else fail "M3 corrupted .docx NOT healed (newer mtime hid it)"; fi
if $HAS_WP; then
    if valid_pdf "$B.pdf"; then pass "M3 working-tree-corrupted .pdf healed"; else fail "M3 corrupted .pdf NOT healed"; fi
else skip "M3 pdf leg (weasyprint absent)"; fi
G add -A && G commit -q -m healed --allow-empty
sleep 1.1
head -c 200 "$B.html" > "$TMP/trunc" && cat "$TMP/trunc" > "$B.html"   # charset kept, body cut
grep -qiE '<meta[^>]+charset' "$B.html" || echo "NOTE: truncation removed the charset — case degenerates to the fragment rule"
run_gen "$MD"
if grep -q '</html>' "$B.html"; then pass "M3 truncated .html (charset intact) healed"; else fail "M3 truncated .html NOT healed"; fi
G add -A && G commit -q -m healed-html --allow-empty
# committed corruption (history says the twin is newer than the source)
printf 'garbage2\n' > "$B.docx"; G commit -q -am corrupt-committed >/dev/null
run_gen "$MD"
if valid_docx "$B.docx"; then pass "M3 committed-corrupt .docx healed"; else fail "M3 committed-corrupt .docx NOT healed"; fi
G add -A && G commit -q -m healed2 --allow-empty
# control: valid, untouched twins are NOT rewritten
declare -A c_mt=() c_sha=()
for e in html pdf docx; do [[ -f "$B.$e" ]] || continue; c_mt[$e]="$(mt "$B.$e")"; c_sha[$e]="$(sha "$B.$e")"; done
sleep 1.1; run_gen "$MD"
c_bad=""
for e in "${!c_mt[@]}"; do [[ "$(mt "$B.$e")" == "${c_mt[$e]}" && "$(sha "$B.$e")" == "${c_sha[$e]}" ]] || c_bad+=" .$e"; done
if [[ -z "$c_bad" && ${#c_mt[@]} -ge 2 ]]; then pass "M3 control: ${#c_mt[@]} valid untouched twins not rewritten"
else fail "M3 control: valid twins spuriously rewritten:$c_bad"; fi

# ---- M4: a failing HTML leg is loud, never feeds the PDF, never kills the run
new_repo
MD2="$R/docs/b.md"; printf '# Beta\n\nb\n' > "$MD2"; run_gen "$MD2" || true
G add -A && G commit -q -m b
mkdir -p "$TMP/shim"; REAL_PANDOC="$(command -v pandoc)"
cat > "$TMP/shim/pandoc" <<SH
#!/usr/bin/env bash
# fail the HTML leg for docs/a.md only; everything else goes to the real pandoc
html=0; a=0
for x in "\$@"; do [[ "\$x" == html5 ]] && html=1; [[ "\$x" == */docs/a.md ]] && a=1; done
if (( html && a )); then echo "SHIM-HTML-FAILURE forced by test" >&2; exit 3; fi
exec "${REAL_PANDOC}" "\$@"
SH
chmod +x "$TMP/shim/pandoc"
sleep 1.1
printf '\nNEEDLE-M4\n' >> "$MD"; printf '\nNEEDLE-M4-B\n' >> "$MD2"
p0="$(sha "$B.pdf")"; h0="$(sha "$B.html")"
PATH="$TMP/shim:$PATH" run_gen "$MD" "$MD2"
if (( RC == 2 )); then pass "M4 run completes and exits 2 when an HTML leg fails"; else fail "M4 exit status $RC (want 2: run completed, a leg failed)"; fi
if grep -q 'SHIM-HTML-FAILURE' "$TMP/gen.err" && grep -qi 'html' "$TMP/gen.err"; then pass "M4 failure is reported on stderr with the converter's message"
else fail "M4 failure not surfaced on stderr: $(tr '\n' '|' < "$TMP/gen.err")"; fi
[[ "$(sha "$B.html")" == "$h0" ]] && pass "M4 stale HTML left untouched (no partial write)" || fail "M4 HTML changed despite a failed leg"
if $HAS_WP; then
    [[ "$(sha "$B.pdf")" == "$p0" ]] && pass "M4 PDF NOT re-derived from the stale HTML" || fail "M4 PDF re-rendered from the stale HTML"
else skip "M4 pdf leg (weasyprint absent)"; fi
if docx_has "$B.docx" NEEDLE-M4; then pass "M4 DOCX leg of the same file still ran"
else fail "M4 DOCX leg did not run after the HTML leg failed"; fi
if grep -q NEEDLE-M4-B "${MD2%.md}.html" 2>/dev/null; then pass "M4 the next file in the run was still processed"
else fail "M4 the run stopped at the failing file — later files never processed"; fi

# ---- Anti-bluff: still regenerates on (a) content change, (b) missing twin,
#      (c) charset-less fragment ---------------------------------------------
new_repo
sleep 1.1; printf '\nNEEDLE-A\n' >> "$MD"; run_gen "$MD"
grep -q NEEDLE-A "$B.html" && docx_has "$B.docx" NEEDLE-A \
    && pass "(a) content change regenerates html+docx" || fail "(a) content change NOT regenerated"
G add -A && G commit -q -m a
rm -f "$B.html"; run_gen "$MD"
[[ -f "$B.html" ]] && grep -q NEEDLE-A "$B.html" && pass "(b) missing twin regenerated" || fail "(b) missing twin NOT regenerated"
G add -A && G commit -q -m b --allow-empty
printf '<p>fragment</p>\n' > "$B.html"; G commit -q -am frag
run_gen "$MD"
grep -qiE '<meta[^>]+charset' "$B.html" && pass "(c) charset-less fragment healed" || fail "(c) charset fragment NOT healed"

echo "RESULT: ${PASS} passed, ${FAIL} failed, ${SKIP} skipped"
(( FAIL == 0 )) || exit 1
exit 0
