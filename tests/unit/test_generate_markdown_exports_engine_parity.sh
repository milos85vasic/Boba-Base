#!/usr/bin/env bash
# test_generate_markdown_exports_engine_parity.sh — guards for the three items an
# independent review left on the BOB-249 writer hardening
# (scripts/generate_markdown_exports.sh).
#
# I1  Docs Chain parity. The html provenance <meta> lines made the generator's
#     html differ byte-for-byte from the docs_chain engine's builtin
#     `pandoc-html` output (constitution/submodules/docs_chain/internal/adapter/
#     derived.go: `--standalone --from=markdown --to=html --metadata title=<base>`,
#     SOURCE_DATE_EPOCH pinned to 946684800). The engine's `verify` recomputes
#     every derived node and compares bytes, so editing an engine-owned doc and
#     running the generator before `docs_chain sync` failed invariant 24
#     (CM-DOCS-CHAIN-ENGINE-VERIFY). Reproduced before the fix on a sandbox copy
#     of docs/features: `verify` -> STALE [status_summary_docx status_summary_html
#     status_summary_pdf] (the docx and pdf legs also deviated: no pinned title /
#     a different SOURCE_DATE_EPOCH / weasyprint base-url). Fix: a twin that is a
#     NODE of a .docs_chain/contexts/*.yaml context is rendered exactly as the
#     engine renders it; every other twin keeps the provenance tags.
# M-a `pandoc -H` SUPPRESSES a document's own YAML header-includes (measured by
#     the reviewer). Fix: the provenance lines are inserted after pandoc runs,
#     immediately before the FIRST </head>, and -H is gone.
# M-b install_render rendered on TMPDIR (tmpfs) and `mv`ed into the repo: a
#     cross-device mv is copy+unlink, not a rename, so an interrupt could leave a
#     missing/partial twin, and the destination's mode was replaced by umask.
#     Fix: a temp file in the destination's OWN directory (same filesystem),
#     mode copied from the existing twin, atomic `mv -f`, temp removed on every
#     failure path, and an install failure is reported, never counted as
#     "byte-identical".
#
# Everything runs in throwaway git repos under mktemp; the generator is invoked
# in explicit-scope mode on sandbox files only. weasyprint/engine legs SKIP
# honestly when their tool is absent (§11.4.3) — a SKIP is never a PASS.
#
# Constitution: §11.4.65, §11.4.106, §11.4.115 RED-first, §11.4.201, §11.4.273.

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${HERE}/../.." && pwd)"
GEN="${PROJECT_ROOT}/scripts/generate_markdown_exports.sh"
ENGINE="${PROJECT_ROOT}/constitution/submodules/docs_chain/docs_chain"
ENGINE_EPOCH=946684800

PASS=0; FAIL=0; SKIP=0
pass() { echo "PASS: $*"; PASS=$((PASS + 1)); }
fail() { echo "FAIL: $*"; FAIL=$((FAIL + 1)); }
skip() { echo "SKIP: $*"; SKIP=$((SKIP + 1)); }

[[ -f "$GEN" ]] || { echo "FAIL: generator missing"; exit 1; }
command -v git >/dev/null || { echo "SKIP: git not available"; exit 0; }
command -v pandoc >/dev/null || { echo "SKIP: pandoc absent — every leg of this test needs it"; exit 0; }
HAS_WP=false; command -v weasyprint >/dev/null && weasyprint --version >/dev/null 2>&1 && HAS_WP=true

TMP="$(mktemp -d)"
trap 'chmod -R u+w "$TMP" 2>/dev/null; rm -rf "$TMP"' EXIT
sha() { sha256sum "$1" 2>/dev/null | cut -d' ' -f1; }
RC=0
run_gen() { GOMAXPROCS=2 nice -n 19 bash "$GEN" "$@" > "$TMP/gen.out" 2> "$TMP/gen.err"; RC=$?; return $RC; }
G() { git -C "$R" -c user.name=t -c user.email=t@t -c commit.gpgsign=false "$@"; }
strays() { find "$1" -name '*exporttmp*' 2>/dev/null | wc -l | tr -d ' '; }

# ---------------------------------------------------------------- I1 --------
R="$TMP/i1"; mkdir -p "$R/docs/own" "$R/.docs_chain/contexts"; git -C "$R" init -q
cat > "$R/.docs_chain/contexts/own.yaml" <<'YAML'
# test context mirroring .docs_chain/contexts/features-status.yaml
context: own-status
description: sandbox
nodes:
  own_md:   { kind: status, path: docs/own/Status.md }
  own_html: { kind: html,   path: docs/own/Status.html }
  own_pdf:  { kind: pdf,    path: docs/own/Status.pdf }
  own_docx: { kind: docx,   path: docs/own/Status.docx }
edges:
  - { type: derive-from, from: own_md,   to: own_html, transform: md2html }
  - { type: derive-from, from: own_html, to: own_pdf,  transform: html2pdf }
  - { type: derive-from, from: own_md,   to: own_docx, transform: md2docx }
transforms:
  md2html:  { builtin: pandoc-html }
  html2pdf: { builtin: weasyprint-pdf }
  md2docx:  { builtin: pandoc-docx }
YAML
OWN="$R/docs/own/Status.md"; FREE="$R/docs/free.md"
printf '# Status\n\n| a | b |\n|---|---|\n| § | Боба |\n\n[link](#status)\n' > "$OWN"
printf '# Free\n\nnot owned\n' > "$FREE"
run_gen "$OWN" "$FREE"; G add -A; G commit -q -m init

# independent references, built exactly as derived.go builds them
REF="$TMP/ref"; mkdir -p "$REF"
cp "$OWN" "$REF/staged-input-name.md"   # the engine stages to a random temp name
SOURCE_DATE_EPOCH=$ENGINE_EPOCH pandoc --standalone --from=markdown --to=html \
    --metadata title=Status -o "$REF/Status.html" "$REF/staged-input-name.md"
SOURCE_DATE_EPOCH=$ENGINE_EPOCH pandoc --from=markdown --to=docx \
    --metadata title=Status -o "$REF/Status.docx" "$REF/staged-input-name.md"
if cmp -s "$REF/Status.html" "${OWN%.md}.html"; then pass "I1 owned html == engine pandoc-html output byte for byte"
else fail "I1 owned html differs from the engine's pandoc-html output"; fi
if grep -q 'x-export-source-sha256\|dcterms.modified' "${OWN%.md}.html"; then fail "I1 owned html still carries provenance tags"
else pass "I1 owned html carries no provenance tags"; fi
if cmp -s "$REF/Status.docx" "${OWN%.md}.docx"; then pass "I1 owned docx == engine pandoc-docx output byte for byte"
else fail "I1 owned docx differs from the engine's pandoc-docx output"; fi
if $HAS_WP; then
    SOURCE_DATE_EPOCH=$ENGINE_EPOCH weasyprint --base-url "$(cd "$R/docs/own" && pwd -P)/Status.pdf" \
        "$REF/Status.html" "$REF/Status.pdf" 2>/dev/null
    if cmp -s "$REF/Status.pdf" "${OWN%.md}.pdf"; then pass "I1 owned pdf == engine weasyprint-pdf output byte for byte"
    else fail "I1 owned pdf differs from the engine's weasyprint-pdf output"; fi
else skip "I1 owned pdf parity (weasyprint absent)"; fi
if grep -q "name=\"x-export-source-sha256\" content=\"$(sha "$FREE")\"" "${FREE%.md}.html"; then
    pass "I1 non-owned html still carries the provenance tags"
else fail "I1 non-owned html lost its provenance tags"; fi

# the real engine: edit the owned source, run ONLY the generator, verify must pass
if [[ -x "$ENGINE" ]] && $HAS_WP; then
    sleep 1.1; printf '\n- edited after init NEEDLE-I1\n' >> "$OWN"
    run_gen "$OWN"
    grep -q NEEDLE-I1 "${OWN%.md}.html" || fail "I1 precondition: generator did not regenerate the edited owned doc"
    if "$ENGINE" verify --all --root "$R" > "$TMP/v.out" 2>&1; then pass "I1 real docs_chain verify passes after generator-only regeneration ($(tr '\n' ' ' < "$TMP/v.out"))"
    else fail "I1 real docs_chain verify FAILS after generator-only regeneration: $(tr '\n' ' ' < "$TMP/v.out")"; fi
    # control needle: verify can SEE drift on this very sandbox
    cp "${OWN%.md}.html" "$TMP/keep.html"; printf '<!-- drift -->\n' >> "${OWN%.md}.html"
    if "$ENGINE" verify --all --root "$R" > "$TMP/v2.out" 2>&1; then fail "I1 control: verify did not detect a hand-drifted html — instrument blind"
    else pass "I1 control: verify detects a drifted html ($(tr '\n' ' ' < "$TMP/v2.out"))"; fi
    cp "$TMP/keep.html" "${OWN%.md}.html"
else skip "I1 real-engine verify (engine binary not built at ${ENGINE#"$PROJECT_ROOT"/} or weasyprint absent)"; fi

# unparsable context -> not owned, one-line note, tags kept
R="$TMP/i1b"; mkdir -p "$R/docs" "$R/.docs_chain/contexts"; git -C "$R" init -q
printf 'this: [is not: a context\n' > "$R/.docs_chain/contexts/broken.yaml"
MD="$R/docs/x.md"; printf '# X\n\nx\n' > "$MD"
run_gen "$MD"
if grep -q 'x-export-source-sha256' "${MD%.md}.html" && [[ "$(grep -c 'docs_chain' "$TMP/gen.err")" == 1 ]]; then
    pass "I1 unparsable context: file treated as not owned, exactly one note on stderr"
else fail "I1 unparsable context handling: tags=$(grep -c x-export-source "${MD%.md}.html") notes=$(grep -c docs_chain "$TMP/gen.err")"; fi

# ---------------------------------------------------------------- M-a -------
R="$TMP/ma"; mkdir -p "$R/docs"; git -C "$R" init -q
MD="$R/docs/hi.md"
cat > "$MD" <<'MD'
---
header-includes: |
  <meta name="x-user-header" content="kept">
---
# Header includes

Body.
MD
run_gen "$MD"
H="${MD%.md}.html"
if grep -q 'name="x-user-header"' "$H" && grep -q 'x-export-source-sha256' "$H"; then pass "M-a YAML header-includes survive alongside the provenance tags"
else fail "M-a header-includes=$(grep -c x-user-header "$H") provenance=$(grep -c x-export-source "$H")"; fi
MD2="$R/docs/body.md"
printf '# Body head\n\n<!-- a literal </head> inside the body -->\n\nText `</head>` too.\n' > "$MD2"
run_gen "$MD2"
H2="${MD2%.md}.html"
pandoc -f markdown -t html5 --standalone --metadata title=body -o "$TMP/bare.html" "$MD2"
first_head="$(grep -n '</head>' "$H2" | head -1 | cut -d: -f1)"
meta_line="$(grep -n 'x-export-source-sha256' "$H2" | cut -d: -f1)"
if [[ "$(grep -c 'x-export-source-sha256' "$H2")" == 1 && -n "$meta_line" && "$meta_line" -lt "$first_head" ]]; then
    pass "M-a provenance inserted once, inside <head> (line $meta_line < first </head> at $first_head)"
else fail "M-a provenance placement: count=$(grep -c x-export-source "$H2") line=$meta_line first</head>=$first_head"; fi
if cmp -s "$TMP/bare.html" <(grep -v 'name="x-export-source-sha256"\|name="dcterms.modified"' "$H2"); then
    pass "M-a html == bare pandoc output apart from exactly the two provenance lines"
else fail "M-a html differs from bare pandoc output beyond the two provenance lines"; fi
grep -q 'a literal </head> inside the body' "$H2" && pass "M-a body text containing </head> untouched" \
    || fail "M-a body text containing </head> was altered"
# comment lines are carriers that MENTION -H (they explain why it is gone); only
# executable lines count (§11.4.273). Control needle: the same filter still sees
# a live pandoc invocation line.
code="$(grep -v '^[[:space:]]*#' "$GEN")"
if grep -qE -- '(^|[[:space:]])-H[[:space:]]' <<<"$code"; then fail "M-a generator still passes pandoc -H"
elif ! grep -qE 'pandoc -f markdown -t html5 --standalone' <<<"$code"; then fail "M-a control: filtered source no longer shows the pandoc html5 call — instrument blind"
else pass "M-a generator no longer passes pandoc -H (control needle sees the pandoc call)"; fi

# ---------------------------------------------------------------- M-b -------
R="$TMP/mb"; mkdir -p "$R/docs"; git -C "$R" init -q
MD="$R/docs/m.md"; B="${MD%.md}"
printf '# M\n\nm\n' > "$MD"; run_gen "$MD"; G add -A; G commit -q -m init
# (1) the install is a same-directory rename
mkdir -p "$TMP/mvlog"; REAL_MV="$(command -v mv)"
cat > "$TMP/mvlog/mv" <<SH
#!/usr/bin/env bash
printf '%s\n' "\$@" >> "$TMP/mv.args"
exec "$REAL_MV" "\$@"
SH
chmod +x "$TMP/mvlog/mv"
sleep 1.1; printf '\nNEEDLE-MB1\n' >> "$MD"; chmod 640 "$B.html"
: > "$TMP/mv.args"
PATH="$TMP/mvlog:$PATH" run_gen "$MD"
src_arg="$(grep -v '^-' "$TMP/mv.args" | sed -n 1p)"
if [[ -n "$src_arg" && "$(dirname "$src_arg")" == "$(cd "$R/docs" && pwd -P)" ]]; then
    pass "M-b install renames from the twin's own directory (same filesystem)"
else fail "M-b install source is '$src_arg' — not in the twin's directory (cross-device mv)"; fi
if [[ "$(stat -c %a "$B.html")" == 640 ]] && grep -q NEEDLE-MB1 "$B.html"; then pass "M-b regenerated twin keeps its previous mode 640"
else fail "M-b mode after regeneration $(stat -c %a "$B.html") (want 640), needle=$(grep -c NEEDLE-MB1 "$B.html")"; fi
[[ "$(strays "$R")" == 0 ]] && pass "M-b no temp files left after a successful run" || fail "M-b $(strays "$R") temp file(s) left after success"
# new twin gets the umask default, not mktemp's 0600
MDN="$R/docs/new.md"; printf '# N\n\nn\n' > "$MDN"; run_gen "$MDN"
want="$(printf '%o' $(( 0666 & ~0$(umask) )))"
[[ "$(stat -c %a "${MDN%.md}.html")" == "$want" ]] && pass "M-b a brand-new twin gets the umask default ($want)" \
    || fail "M-b brand-new twin mode $(stat -c %a "${MDN%.md}.html") (want $want)"
# (2) a failing install leaves the twin intact, cleans up, and is LOUD
mkdir -p "$TMP/mvfail"
printf '#!/usr/bin/env bash\necho "SHIM-MV-FAILURE" >&2\nexit 1\n' > "$TMP/mvfail/mv"; chmod +x "$TMP/mvfail/mv"
sleep 1.1; printf '\nNEEDLE-MB2\n' >> "$MD"
h0="$(sha "$B.html")"; d0="$(sha "$B.docx")"
PATH="$TMP/mvfail:$PATH" run_gen "$MD"
[[ "$(sha "$B.html")" == "$h0" && "$(sha "$B.docx")" == "$d0" ]] && pass "M-b failing install leaves the previous twins intact" \
    || fail "M-b failing install changed a twin"
[[ "$(strays "$R")" == 0 ]] && pass "M-b no temp files left after a failing install" || fail "M-b $(strays "$R") temp file(s) left after a failing install"
if (( RC != 0 )) && grep -qi 'install' "$TMP/gen.err"; then pass "M-b failing install reported (exit $RC, stderr names the install)"
else fail "M-b failing install silent: exit $RC, stderr=$(tr '\n' '|' < "$TMP/gen.err")"; fi
if grep -q '0 failed' "$TMP/gen.out" && grep -q 'byte-identical' "$TMP/gen.out" && ! grep -q '[1-9][0-9]* failed' "$TMP/gen.out"; then
    fail "M-b failing install counted as success/byte-identical in the summary"
else pass "M-b summary does not count the failed install as success"; fi
# (3) read-only destination directory: twin intact, loud, nothing left behind
sleep 1.1; printf '\nNEEDLE-MB3\n' >> "$MD"; h0="$(sha "$B.html")"
chmod 555 "$R/docs"; run_gen "$MD"; chmod 755 "$R/docs"
[[ "$(sha "$B.html")" == "$h0" && "$(strays "$R")" == 0 && $RC -ne 0 ]] && pass "M-b read-only directory: twin intact, no temp, exit $RC" \
    || fail "M-b read-only directory: sha-same=$([[ "$(sha "$B.html")" == "$h0" ]] && echo y || echo n) strays=$(strays "$R") rc=$RC"
# (4) a leftover temp from a killed run is ignored by git
printf 'x' > "$R/docs/.m.html.exporttmp.AbC123.tmp"
cp "$PROJECT_ROOT/.gitignore" "$R/.gitignore"
if git -C "$R" check-ignore -q "docs/.m.html.exporttmp.AbC123.tmp"; then pass "M-b a stray temp name is git-ignored by the project .gitignore"
else fail "M-b a stray temp would show up untracked in git status"; fi
rm -f "$R/docs/.m.html.exporttmp.AbC123.tmp"

echo "RESULT: ${PASS} passed, ${FAIL} failed, ${SKIP} skipped"
(( FAIL == 0 )) || exit 1
exit 0
