#!/usr/bin/env bash
# test_compute_badges_carrier_match.sh — scripts/compute-badges.sh must rewrite
# ONLY real badge lines, never a PROSE line that merely MENTIONS `alt="tests"`.
#
# §11.4.201(7)(a) match-structure-not-substring. The pre-fix awk filter used
# bare `/alt="tests"/` / `/alt="vitest"/` patterns, which fire on ANY line
# containing that substring anywhere. README.md carries a prose paragraph that
# documents this very filter and therefore contains both literals — the script
# replaced that prose line with an <img> badge tag, destroying documentation
# content (observed live 2026-08-20, §11.4.238 out-of-band discovery).
#
# §11.4.43 RED-first: against the pre-fix script the carrier prose line is
# overwritten → this test FAILs. After anchoring the match to the real badge
# structure (an <img …> line carrying a shields.io src, inside the
# <p align="center"> badge block) it GREENs.
#
# Runs the REAL script through its REAL invocation path (§11.4.201(11)
# artifact-usability, never a re-implemented copy of the awk in the test).

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${HERE}/../.." && pwd)"
SCRIPT="${PROJECT_ROOT}/scripts/compute-badges.sh"

PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); echo "  PASS: $1"; }
fail() { FAIL=$((FAIL+1)); echo "  FAIL: $1"; }

finish() {
    echo "RESULT: $PASS passed, $FAIL failed"
    [ "$FAIL" -eq 0 ] || exit 1
    exit 0
}

if [ ! -x "$SCRIPT" ]; then
    fail "scripts/compute-badges.sh missing or not executable"
    finish
fi

TMPDIR_T="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_T"' EXIT
FIX_README="${TMPDIR_T}/README.md"
FIX_TESTING="${TMPDIR_T}/TESTING.md"

# The carrier line: prose that MENTIONS both literals. Kept on ONE line so a
# substring-matching filter replaces exactly this line (the observed defect).
CARRIER='      matches `alt="tests"` / `alt="vitest"` — it does not actually rewrite'

cat > "$FIX_README" <<EOF
# Fixture

<p align="center">
  <img alt="tests"          src="https://img.shields.io/badge/python%20tests-1%20collected-blue">
  <img alt="vitest"         src="https://img.shields.io/badge/frontend%20tests-1%20collected-blue">
  <img alt="plugins"        src="https://img.shields.io/badge/plugins-48-blue">
</p>

Provenance note: compute-badges.sh computes the count correctly but its
${CARRIER}
this badge line despite logging "(unchanged, cross-checked)".
EOF

cat > "$FIX_TESTING" <<'EOF'
# Fixture TESTING

## Test counts (machine-derived, §11.4.259)

| Suite | Directory | Real count | Method |
|---|---|---|---|
| Python (whole `tests/` tree) | `tests/` | **1** | `pytest --collect-only -q` |
EOF

if ! bash "$SCRIPT" --readme "$FIX_README" --testing-md "$FIX_TESTING" >/dev/null 2>&1; then
    fail "compute-badges.sh exited non-zero against the fixture"
    finish
fi

# ── Assertion 1 (the defect): the carrier prose line MUST survive verbatim ──
if grep -qF "$CARRIER" "$FIX_README"; then
    pass "carrier prose line mentioning alt=\"tests\"/alt=\"vitest\" left intact"
else
    fail "carrier prose line was OVERWRITTEN — substring match instead of structural match"
    echo "       expected to still find: $CARRIER" >&2
    echo "       --- resulting fixture ---" >&2
    sed -n '1,20p' "$FIX_README" >&2
fi

# ── Assertion 2 (no false negative): the REAL badge lines still get rewritten ──
# Guards against "fix" by simply disabling the rewrite (§11.4.201(1) — a gate
# that refuses everything is as broken as one that allows everything).
if grep -qE '^[[:space:]]*<img alt="tests"[[:space:]]+src="https://img\.shields\.io/badge/python%20tests-[0-9]+%20collected-blue">$' "$FIX_README"; then
    if grep -qF 'python%20tests-1%20collected-blue' "$FIX_README"; then
        fail "real python badge line was NOT refreshed (still the fixture placeholder)"
    else
        pass "real python badge line refreshed to a live count"
    fi
else
    fail "real python badge line missing/malformed after rewrite"
fi

if grep -qE '^[[:space:]]*<img alt="vitest"[[:space:]]+src="https://img\.shields\.io/badge/frontend%20tests-' "$FIX_README"; then
    pass "real vitest badge line present and well-formed after rewrite"
else
    fail "real vitest badge line missing/malformed after rewrite"
fi

# ── Assertion 3: unrelated badge lines in the block are untouched ──
if grep -qF '<img alt="plugins"        src="https://img.shields.io/badge/plugins-48-blue">' "$FIX_README"; then
    pass "unrelated badge line (plugins) untouched"
else
    fail "unrelated badge line (plugins) was modified"
fi

# ── Assertion 4: IDEMPOTENCE of the docs/TESTING.md section rewrite ──
# The regenerator strips the old '## Test counts' section but must also strip
# the blank line(s) that preceded it, otherwise the unconditional leading
# `echo ""` appends one MORE blank line on every run and they accumulate
# without bound. §11.4.50 deterministic consistency: N runs == 1 run.
blanks_before_heading() {
    awk '
        /^## Test counts \(machine-derived, §11\.4\.259\)/ { print blanks; found = 1; exit }
        /^[[:space:]]*$/ { blanks++; next }
        { blanks = 0 }
        END { if (!found) print "NO-HEADING" }
    ' "$1"
}

B1="$(blanks_before_heading "$FIX_TESTING")"
if [ "$B1" = "1" ]; then
    pass "TESTING.md: exactly 1 blank line before the generated heading (run 1)"
else
    fail "TESTING.md: expected 1 blank line before heading after run 1, got '$B1'"
fi

if ! bash "$SCRIPT" --readme "$FIX_README" --testing-md "$FIX_TESTING" >/dev/null 2>&1; then
    fail "compute-badges.sh exited non-zero on the second (idempotence) run"
else
    B2="$(blanks_before_heading "$FIX_TESTING")"
    if [ "$B2" = "$B1" ] && [ "$B2" = "1" ]; then
        pass "TESTING.md: blank-line count stable across runs (idempotent: $B1 -> $B2)"
    else
        fail "TESTING.md: blank lines ACCUMULATE across runs ($B1 -> $B2) — not idempotent"
    fi
fi

finish
