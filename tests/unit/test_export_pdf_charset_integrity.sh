#!/usr/bin/env bash
# BOB-169 — the exported PDF must carry the source's non-ASCII intact.
#
# ROOT CAUSE this guards (PRE-FIX STATE — the flag is present now; this describes
# what the guard exists to prevent RETURNING):
# scripts/generate_markdown_exports.sh rendered HTML via
# `pandoc -f markdown -t html5` WITHOUT --standalone, so pandoc emitted a BODY
# FRAGMENT with no <head> and no <meta charset>. weasyprint then renders the PDF
# from that charset-less HTML and falls back to a non-UTF-8 default, baking
# mojibake into the PDF's TEXT LAYER (§ -> "Â§", em-dash -> "â€”"). The
# python-markdown fallback in the same function writes <meta charset="utf-8">
# and is correct; the direct markdown->docx path never reads the HTML and is
# also clean. Only the pandoc HTML leg — and the PDF rendered from it — is bad.
#
# Real invocation path, not a parse check (§11.4.224(A)): a COPY of the real
# generator runs against a temp tree. PROJECT_ROOT derives from BASH_SOURCE
# (generate_markdown_exports.sh:17), so a copy at <temp>/scripts/ scans <temp>
# and cannot touch the repo's ~600 real exports.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${HERE}/../.." && pwd)"
GEN="${PROJECT_ROOT}/scripts/generate_markdown_exports.sh"

PASS=0; FAIL=0
ok()   { echo "  PASS: $1"; PASS=$((PASS + 1)); }
bad()  { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }
skip() { echo "  SKIP(§11.4.3): $1"; }

[[ -f "$GEN" ]] || { echo "FAIL: generator missing: scripts/generate_markdown_exports.sh"; exit 1; }

# Honest SKIP when the toolchain is absent — an unmeasurable claim is not a PASS.
for tool in pandoc weasyprint pdftotext; do
  command -v "$tool" >/dev/null 2>&1 || { skip "$tool absent — PDF charset integrity is unmeasurable here"; echo "RESULT: 0 passed, 0 failed (skipped)"; exit 0; }
done

FIX="$(mktemp -d)"; trap 'rm -rf "$FIX"' EXIT

usable_tree() { [[ -n "${1:-}" && -f "${1}/scripts/generate_markdown_exports.sh" ]]; }

mkdir -p "${FIX}/scripts" "${FIX}/docs"
cp "$GEN" "${FIX}/scripts/generate_markdown_exports.sh"
a="$(sha256sum "$GEN" | cut -d' ' -f1)"
b="$(sha256sum "${FIX}/scripts/generate_markdown_exports.sh" | cut -d' ' -f1)"
[[ "$a" == "$b" ]] || { echo "ANTI-REPLICA CHECK FAILED — fixture diverged from the real generator" >&2; exit 1; }

# Every character below is one the defect corrupts.
cat > "${FIX}/docs/charset_fixture.md" <<'MD'
# Charset fixture

Section §11.4.169 — an em-dash, a right arrow →, and "smart quotes".
MD

if ! usable_tree "$FIX"; then
  echo "  FAIL: fixture setup failed for root='${FIX:-}' — generator NOT executed"
  echo "RESULT: 0 passed, 1 failed"; exit 1
fi

GOMAXPROCS=2 nice -n 19 ionice -c 3 bash "${FIX}/scripts/generate_markdown_exports.sh" >/dev/null 2>&1

H="${FIX}/docs/charset_fixture.html"
P="${FIX}/docs/charset_fixture.pdf"

if [[ -f "$H" ]]; then
  # MATCH STRUCTURE, NOT SUBSTRING (§11.4.201(7)(a)). A bare `grep -qi charset`
  # FALSE-PASSED here during authoring: it matched this fixture's own heading slug
  # "charset-fixture". A document is not self-describing because it says the word.
  # Only a <meta ... charset...> element is a declaration.
  if grep -qiE '<meta[^>]+charset' "$H"; then
    ok "exported HTML carries a <meta charset> declaration"
  else
    CARRIER="$(grep -ci 'charset' "$H" || true)"
    bad "exported HTML has NO <meta charset> element (bare-substring carriers present: ${CARRIER}) — weasyprint must guess (BOB-169 root cause)"
  fi
else
  bad "no HTML produced"
fi

if [[ -f "$P" ]]; then
  TXT="$(pdftotext "$P" - 2>/dev/null)"
  MOJ="$(printf '%s' "$TXT" | grep -cE 'Â|â€|â†|ï¿½' || true)"
  # CONTROL NEEDLE (§11.4.201(7)(b)): a blind extraction returns zero mojibake and
  # zero real characters alike. Requiring the real characters present makes the
  # zero a SEEN zero — an empty text layer can no longer pass this test.
  REAL="$(printf '%s' "$TXT" | grep -cE '§|—' || true)"
  if [[ "$REAL" -eq 0 ]]; then
    bad "PDF text layer carries NEITHER mojibake NOR the source's non-ASCII — extraction blind, result proves nothing"
  elif [[ "$MOJ" -gt 0 ]]; then
    bad "PDF text layer carries mojibake on ${MOJ} line(s) — source non-ASCII corrupted"
  else
    ok "PDF text layer preserves the source's non-ASCII (needle: ${REAL} line(s) intact, 0 mojibake)"
  fi
else
  bad "no PDF produced"
fi

echo "RESULT: ${PASS} passed, ${FAIL} failed"
[[ "$FAIL" -eq 0 ]]
