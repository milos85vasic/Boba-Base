#!/usr/bin/env bash
# test_generate_markdown_exports_docs_chain_paths.sh
#
# Purpose: the generator decides which twins the docs_chain engine owns by
# reading the node `path:` values of .docs_chain/contexts/*.yaml. The earlier
# reader was a regex that stopped a value at the first space, so a QUOTED path
# containing a space (`path: "docs/a b/Status.html"`) was read as `docs/a`:
# the real node was treated as not owned, got provenance tags, and the engine's
# byte comparison (pre-build invariant 24) then failed for it. This test drives
# the generator (explicit-scope mode) in throwaway git repos and checks the
# ownership decision through its observable effect: an owned twin carries NO
# provenance tags, a free one does.
#
# Cases: double-quoted path with a space (flow map), single-quoted path with a
# doubled '' quote, a block-mapping plain scalar with a space and a trailing
# comment, a plain path (control), look-alikes that must NOT be read as a node
# path (`script_path:`, a `path:` inside a quoted description), an unterminated
# quote (loud NOTE, file treated as not owned), and -- when the engine binary
# and weasyprint exist -- the real `docs_chain verify` passing after a
# generator-only regeneration of the spaced-path node, with a control needle.
#
# Constitution: §11.4.106, §11.4.115 RED-first, §11.4.201, §11.4.273.

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${HERE}/../.." && pwd)"
GEN="${PROJECT_ROOT}/scripts/generate_markdown_exports.sh"
ENGINE="${PROJECT_ROOT}/constitution/submodules/docs_chain/docs_chain"

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
run_gen() { GOMAXPROCS=2 nice -n 19 bash "$GEN" "$@" > "$TMP/gen.out" 2> "$TMP/gen.err"; }
tagged() { grep -q 'x-export-source-sha256' "$1" 2>/dev/null; }
G() { git -C "$R" -c user.name=t -c user.email=t@t -c commit.gpgsign=false "$@"; }
mkdoc() { mkdir -p "$(dirname "$1")"; printf '# %s\n\nbody\n' "$(basename "$1" .md)" > "$1"; }

# ---------------------------------------------------------------- parse ----
R="$TMP/parse"; mkdir -p "$R/.docs_chain/contexts"; git -C "$R" init -q
cat > "$R/.docs_chain/contexts/spaced.yaml" <<'YAML'
context: spaced
description: "a description that mentions path: docs/free/Free.html on purpose"
nodes:
  dq_md:   { kind: status, path: "docs/a b/Status.md" }
  dq_html: { kind: html,   path: "docs/a b/Status.html" }
  sq_html: { kind: html,   path: 'docs/it''s/Q.html' }
  blk_html:
    kind: html
    path: docs/c d/B.html   # a trailing comment
  plain_html: { kind: html, path: docs/plain/P.html }
  lookalike: { kind: html, script_path: docs/look/L.html }
YAML
DQ="$R/docs/a b/Status.md"; SQ="$R/docs/it's/Q.md"; BLK="$R/docs/c d/B.md"
PLAIN="$R/docs/plain/P.md"; LOOK="$R/docs/look/L.md"; FREE="$R/docs/free/Free.md"
for f in "$DQ" "$SQ" "$BLK" "$PLAIN" "$LOOK" "$FREE"; do mkdoc "$f"; done
run_gen "$DQ" "$SQ" "$BLK" "$PLAIN" "$LOOK" "$FREE"
check_owned() { # desc md-path
    if [[ ! -f "${2%.md}.html" ]]; then fail "$1: no html twin was produced"
    elif tagged "${2%.md}.html"; then fail "$1: twin carries provenance tags, i.e. it was NOT treated as docs_chain-owned"
    else pass "$1: twin treated as docs_chain-owned (no provenance tags)"; fi
}
check_free() { # desc md-path
    if tagged "${2%.md}.html"; then pass "$1: twin carries provenance tags (not owned)"
    else fail "$1: twin has no provenance tags, i.e. it was wrongly treated as owned"; fi
}
check_owned "double-quoted flow-map path with a space" "$DQ"
check_owned "single-quoted path with a doubled '' quote" "$SQ"
check_owned "block-mapping plain scalar with a space and a trailing comment" "$BLK"
check_owned "control: plain unquoted path" "$PLAIN"
check_free  "look-alike key script_path: is not a node path" "$LOOK"
check_free  "a 'path:' inside a quoted description is not a node path" "$FREE"
if grep -q 'NOTE: docs_chain' "$TMP/gen.err"; then fail "a parsable context produced a docs_chain NOTE: $(tr '\n' ' ' < "$TMP/gen.err")"
else pass "a parsable context produces no docs_chain NOTE"; fi

# ------------------------------------------------------- loud fallback -----
R="$TMP/loud"; mkdir -p "$R/.docs_chain/contexts"; git -C "$R" init -q
cat > "$R/.docs_chain/contexts/broken.yaml" <<'YAML'
nodes:
  x_html: { kind: html, path: "docs/x/X.html }
YAML
X="$R/docs/x/X.md"; mkdoc "$X"
run_gen "$X"
if tagged "${X%.md}.html"; then pass "unterminated quote: twin treated as not owned (tags kept)"
else fail "unterminated quote: twin wrongly treated as owned"; fi
if grep -q 'broken.yaml' "$TMP/gen.err" && grep -qi 'unterminated' "$TMP/gen.err"; then
    pass "unterminated quote: a loud NOTE names the file and the reason"
else fail "unterminated quote: no NOTE naming the file and the unterminated quote: $(tr '\n' ' ' < "$TMP/gen.err")"; fi

# ------------------------------------------------------- real engine -------
if [[ -x "$ENGINE" ]] && $HAS_WP; then
    R="$TMP/engine"; mkdir -p "$R/.docs_chain/contexts"; git -C "$R" init -q
    cat > "$R/.docs_chain/contexts/spaced.yaml" <<'YAML'
context: spaced-status
description: sandbox with a spaced, quoted node path
nodes:
  s_md:   { kind: status, path: "docs/a b/Status.md" }
  s_html: { kind: html,   path: "docs/a b/Status.html" }
  s_pdf:  { kind: pdf,    path: "docs/a b/Status.pdf" }
  s_docx: { kind: docx,   path: "docs/a b/Status.docx" }
edges:
  - { type: derive-from, from: s_md,   to: s_html, transform: md2html }
  - { type: derive-from, from: s_html, to: s_pdf,  transform: html2pdf }
  - { type: derive-from, from: s_md,   to: s_docx, transform: md2docx }
transforms:
  md2html:  { builtin: pandoc-html }
  html2pdf: { builtin: weasyprint-pdf }
  md2docx:  { builtin: pandoc-docx }
YAML
    S="$R/docs/a b/Status.md"; mkdoc "$S"
    run_gen "$S"; G add -A; G commit -q -m init
    sleep 1.1; printf '\n- edited NEEDLE-SPACED\n' >> "$S"
    run_gen "$S"
    grep -q NEEDLE-SPACED "${S%.md}.html" || fail "engine precondition: the generator did not regenerate the edited doc"
    if "$ENGINE" verify --all --root "$R" > "$TMP/v.out" 2>&1; then
        pass "real docs_chain verify passes after a generator-only regeneration of a spaced-path node"
    else fail "real docs_chain verify FAILS for the spaced-path node: $(tr '\n' ' ' < "$TMP/v.out")"; fi
    cp "${S%.md}.html" "$TMP/keep.html"; printf '<!-- drift -->\n' >> "${S%.md}.html"
    if "$ENGINE" verify --all --root "$R" > "$TMP/v2.out" 2>&1; then fail "control: verify did not see a drifted html — instrument blind"
    else pass "control: verify detects a drifted html on the same sandbox"; fi
    cp "$TMP/keep.html" "${S%.md}.html"
else skip "real-engine verify (engine binary not built or weasyprint absent)"; fi

echo "test_generate_markdown_exports_docs_chain_paths: ${PASS} passed, ${FAIL} failed, ${SKIP} skipped"
[[ "$FAIL" -eq 0 ]]
