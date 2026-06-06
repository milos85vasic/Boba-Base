#!/usr/bin/env bash
# test_docx_export.sh — Hermetic test for the DOCX branch of
# generate_markdown_exports.sh (BOB-011, §11.4.65 universal export).
#
# §11.4.43 / §11.4.115 RED-first: against the pre-fix script (HTML+PDF only,
# no DOCX branch) no .docx sibling is ever produced, so the
# "docx generated" + "valid zip" + "idempotent" assertions FAIL. After the
# DOCX branch lands they GREEN.
#
# Anti-bluff (§11.4): asserts a user-observable artifact — the .docx exists,
# is non-empty, and begins with the ZIP local-file-header magic PK\x03\x04
# (a DOCX is an OOXML zip). A no-op stub that only touches an empty file
# would fail the magic-byte + non-empty checks.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${HERE}/../.." && pwd)"
SCRIPT="${PROJECT_ROOT}/scripts/generate_markdown_exports.sh"

PASS_COUNT=0
FAIL_COUNT=0
pass() { PASS_COUNT=$((PASS_COUNT + 1)); echo "  PASS: $1"; }
fail() { FAIL_COUNT=$((FAIL_COUNT + 1)); echo "  FAIL: $1"; }

if ! command -v pandoc &>/dev/null; then
    echo "  SKIP: pandoc not installed — DOCX export requires pandoc (SKIP-OK: BOB-011)"
    echo "RESULT: ${PASS_COUNT} passed, ${FAIL_COUNT} failed (skipped)"
    exit 0
fi

[[ -f "$SCRIPT" ]] || { fail "export script missing: $SCRIPT"; echo "RESULT: ${PASS_COUNT} passed, ${FAIL_COUNT} failed"; exit 1; }

# Sandbox a fake PROJECT_ROOT so we never touch tracked files. The script
# resolves PROJECT_ROOT as the parent of its own scripts/ dir, so we copy
# the script into <sandbox>/scripts/ and place a .md at <sandbox>/.
SANDBOX="$(mktemp -d)"
cleanup() { rm -rf "$SANDBOX"; }
trap cleanup EXIT

mkdir -p "$SANDBOX/scripts"
cp "$SCRIPT" "$SANDBOX/scripts/generate_markdown_exports.sh"
MD="$SANDBOX/sample.md"
printf '# Sample BOB-011 Heading\n\nThis is **bold** export content.\n\n- one\n- two\n' > "$MD"

DOCX="$SANDBOX/sample.docx"

# Run the script (it walks the sandbox root for *.md).
bash "$SANDBOX/scripts/generate_markdown_exports.sh" >/dev/null 2>&1 || true

# (1) The DOCX sibling was produced.
[[ -f "$DOCX" ]] \
    && pass "DOCX sibling produced ($DOCX)" \
    || fail "DOCX sibling NOT produced — DOCX branch missing?"

# (2) It is non-empty.
if [[ -f "$DOCX" && -s "$DOCX" ]]; then
    pass "DOCX is non-empty ($(wc -c < "$DOCX" | tr -d ' ') bytes)"
else
    fail "DOCX is empty or absent"
fi

# (3) It is a valid zip — first 4 bytes are the ZIP magic PK\x03\x04 (0x504b0304).
if [[ -f "$DOCX" ]]; then
    magic="$(head -c 4 "$DOCX" | od -An -tx1 | tr -d ' \n')"
    if [[ "$magic" == "504b0304" ]]; then
        pass "DOCX has valid ZIP magic (PK\\x03\\x04)"
    else
        fail "DOCX magic bytes are '$magic', expected 504b0304"
    fi
fi

# (4) Idempotency — second run with no .md change must NOT regenerate the docx
#     (mtime unchanged).
if [[ -f "$DOCX" ]]; then
    before="$(stat -f %m "$DOCX" 2>/dev/null || stat -c %Y "$DOCX")"
    sleep 1
    bash "$SANDBOX/scripts/generate_markdown_exports.sh" >/dev/null 2>&1 || true
    after="$(stat -f %m "$DOCX" 2>/dev/null || stat -c %Y "$DOCX")"
    [[ "$before" == "$after" ]] \
        && pass "DOCX not regenerated when .md unchanged (idempotent)" \
        || fail "DOCX regenerated though .md unchanged (mtime $before -> $after)"
fi

echo "RESULT: ${PASS_COUNT} passed, ${FAIL_COUNT} failed"
[[ "$FAIL_COUNT" -eq 0 ]]
