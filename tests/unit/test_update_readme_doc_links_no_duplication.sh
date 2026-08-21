#!/usr/bin/env bash
# test_update_readme_doc_links_no_duplication.sh — regression guard for a
# real, measured defect (BOB-088, 2026-08-21):
# scripts/testing/update_readme_doc_links.sh's block-rewrite awk state
# machine dropped ONLY the old table's header + `|---` separator line and
# fell through to printing every OLD data row unchanged, so applying the
# generator to a genuinely-stale README.md produced TWO back-to-back copies
# of the Tracked-Items table between the `<!-- doc-link-section:begin -->`
# / `<!-- doc-link-section:end -->` markers instead of replacing the old one.
#
# §11.4.115 RED-baseline-on-the-broken-artifact + polarity-switch: this test
# drives the REAL script (§11.4.201(11) artifact-usability — never a
# reimplemented copy of its awk) through its REAL invocation path against a
# fixture whose "Document" table already carries a stale value the generator
# WILL rewrite, so the apply-mode rewrite branch (not the "already in sync"
# no-op shortcut) is genuinely exercised. It then asserts (1) the row count
# in the rewritten table matches the manifest exactly once (no duplication),
# (2) the stale value was corrected, (3) a second run is idempotent.
#
# Usage:   bash tests/unit/test_update_readme_doc_links_no_duplication.sh
# Side-effects: none on the real repo — operates entirely on a temp fixture
#   README + a temp copy of docs/Issues.md via a fixture-local git checkout
#   is NOT needed because the script resolves ALL its manifest paths off the
#   REAL ${ROOT_DIR}, so this test targets --readme at a temp file while
#   letting the manifest resolve against the real (git-tracked) docs/ tree —
#   this is the same pattern scripts/compute-badges.sh's own carrier-match
#   test uses (--readme overrides ONLY the target file, never the doc
#   sources the counts/rows are computed from).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${HERE}/../.." && pwd)"
SCRIPT="${PROJECT_ROOT}/scripts/testing/update_readme_doc_links.sh"

PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); echo "  PASS: $1"; }
fail() { FAIL=$((FAIL+1)); echo "  FAIL: $1"; }
finish() {
    echo "RESULT: $PASS passed, $FAIL failed"
    [ "$FAIL" -eq 0 ] || exit 1
    exit 0
}

if [ ! -x "$SCRIPT" ]; then
    fail "scripts/testing/update_readme_doc_links.sh missing or not executable"
    finish
fi

TMPDIR_T="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_T"' EXIT
FIX_README="${TMPDIR_T}/README.md"

# Real Revision of docs/Issues.md right now (the script reads this off the
# REAL file — the fixture only overrides the TARGET, not the source).
REAL_REV="$(grep -m1 -oE '\*\*Revision:\*\*[[:space:]]*[0-9]+' "${PROJECT_ROOT}/docs/Issues.md" | grep -oE '[0-9]+$')"
if [[ -z "${REAL_REV}" ]]; then
    fail "could not read a live Revision off docs/Issues.md — cannot construct a deterministic fixture"
    finish
fi
STALE_REV=$((REAL_REV + 1000))

cat > "$FIX_README" <<EOF
# Fixture

## Documentation

### Tracked-Items + Status Documents

<!-- doc-link-section:begin -->
Fixture intro paragraph.

| Document | Last modified | Revision | Markdown | HTML | PDF |
|---|---|---|---|---|---|
| Issues | 2000-01-01T00:00:00Z | ${STALE_REV} | [Markdown](docs/Issues.md) | [HTML](docs/Issues.html) | [PDF](docs/Issues.pdf) |
<!-- doc-link-section:end -->

### Next section
EOF

if ! bash "$SCRIPT" --readme "$FIX_README" >/dev/null 2>&1; then
    fail "update_readme_doc_links.sh exited non-zero against the fixture"
    finish
fi

# ── Assertion 1 (the defect): exactly ONE "Issues" data row after rewrite ──
issues_count="$(grep -cE '^\| Issues \|' "$FIX_README" || true)"
if [[ "${issues_count}" -eq 1 ]]; then
    pass "exactly one 'Issues' row after rewrite (no table duplication)"
else
    fail "table was duplicated — found ${issues_count} 'Issues' rows (expected 1)"
    echo "       --- resulting fixture block ---" >&2
    sed -n '/doc-link-section:begin/,/doc-link-section:end/p' "$FIX_README" >&2
fi

# ── Assertion 2: the stale Revision was actually corrected ──
if grep -qE "^\| Issues \| .* \| ${STALE_REV} \|" "$FIX_README"; then
    fail "stale Revision ${STALE_REV} was NOT corrected"
else
    if grep -qE "^\| Issues \| .* \| ${REAL_REV} \|" "$FIX_README"; then
        pass "stale Revision refreshed to the real live value (${REAL_REV})"
    else
        fail "Issues row present but Revision matches neither stale nor real value"
    fi
fi

# ── Assertion 3: content AFTER the table (the next markdown section) survived ──
if grep -qF "### Next section" "$FIX_README"; then
    pass "content after the table block ('### Next section') survived the rewrite"
else
    fail "content after the table block was lost"
fi

# ── Assertion 4: end marker still present exactly once ──
end_marker_count="$(grep -cF '<!-- doc-link-section:end -->' "$FIX_README" || true)"
if [[ "${end_marker_count}" -eq 1 ]]; then
    pass "end marker present exactly once"
else
    fail "end marker count is ${end_marker_count} (expected 1)"
fi

# ── Assertion 5: idempotence — a second run changes nothing further ──
cp "$FIX_README" "${FIX_README}.after_run1"
if ! bash "$SCRIPT" --readme "$FIX_README" >/dev/null 2>&1; then
    fail "update_readme_doc_links.sh exited non-zero on the second (idempotence) run"
else
    if diff -q "${FIX_README}.after_run1" "$FIX_README" >/dev/null 2>&1; then
        pass "second run is idempotent (no further changes)"
    else
        fail "second run changed the fixture further (not idempotent)"
    fi
fi

finish
