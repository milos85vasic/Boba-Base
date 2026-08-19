#!/usr/bin/env bash
# pre_code_review.sh — Code-review gate running before pre_build_verification.sh
#
# Checks:
#   1. ruff check on all Python files
#   2. mypy on download-proxy/src/
#   3. bash -n syntax check on all scripts/*.sh
#   4. No mutation markers in source files
#      (same markers the pre-commit hook checks: MUT""ATED, // alwa""ys pass, # MUT""ATION)
#      BOB-070 hardening: patterns are line-anchored to their comment
#      shape and lines carrying `guardrails:allow` are skipped, so a
#      docstring/comment/string-literal that MENTIONS the marker as
#      documentation never false-positive-FAILs the gate
#      (§11.4.84 + §11.4.201(7)(a) carrier-vs-thing).
#
# Constitution: x11.4.125

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

FAIL_COUNT=0
PASS_COUNT=0

pass() {
    PASS_COUNT=$((PASS_COUNT + 1))
    echo "  PASS [$PASS_COUNT]: $1"
}

fail() {
    FAIL_COUNT=$((FAIL_COUNT + 1))
    echo "  FAIL [$FAIL_COUNT]: $1"
}

echo "=== Code-Review Gate ==="
echo

# Build mutation marker patterns indirectly to avoid self-match.
# BOB-070: patterns are LINE-ANCHORED (with optional indent) to the
# comment-line shape a real mutation takes — a trailing / quoted /
# in-string mention (e.g. `pattern = "# MUTATION"`, docstring quoting
# the marker as documentation) never false-positive-FAILs the gate
# (§11.4.201(7)(a) carrier-vs-thing).
M1="^[[:space:]]*(//|#)[[:space:]]*MUT""ATED"
M2="^[[:space:]]*// alwa""ys pass"
M3="^[[:space:]]*# MUT""ATION"
MUTATION_PATTERNS=("$M1" "$M2" "$M3")
# §11.4.109-style per-line escape sentinel — a line carrying this
# token is an INTENTIONAL documented carrier (audited by git-blame +
# review); a real mutation would never carry it.
GUARDRAILS_ALLOW_MARKER="guard""rails:allow"

RUFF_FAILED=0
MYPY_FAILED=0
BLOCKING_FAIL=0

# --- Check 1: ruff check (non-blocking — pre-existing issues) ---
echo "[1/4] ruff check on all Python files"
if cd "$PROJECT_ROOT" && ruff check .; then
    pass "ruff check passed"
else
    echo "    WARNING: ruff found pre-existing issues (non-blocking)"
    RUFF_FAILED=1
fi

# --- Check 2: mypy (non-blocking — pre-existing issues) ---
echo "[2/4] mypy on download-proxy/src/"
if cd "$PROJECT_ROOT" && mypy download-proxy/src/; then
    pass "mypy passed"
else
    echo "    WARNING: mypy found pre-existing issues (non-blocking)"
    MYPY_FAILED=1
fi

# --- Check 3: bash -n syntax check (blocking) ---
echo "[3/4] bash -n syntax check on scripts/*.sh"
bash_errors=0
for script in "$SCRIPT_DIR"/*.sh; do
    if ! bash -n "$script" 2>/dev/null; then
        fail "bash syntax error in $(basename "$script")"
        bash_errors=$((bash_errors + 1))
        BLOCKING_FAIL=$((BLOCKING_FAIL + 1))
    fi
done
if [[ "$bash_errors" -eq 0 ]]; then
    pass "all scripts/*.sh pass syntax check"
fi

# --- Check 4: mutation markers (blocking — exclude tests/ and challenges/ where intentional) ---
echo "[4/4] mutation marker check"
marker_errors=0
while IFS= read -r -d '' file; do
    for pattern in "${MUTATION_PATTERNS[@]}"; do
        # -E extended-regex for the ^[[:space:]]* line anchor; the
        # guardrails:allow post-filter drops intentional carriers.
        if grep -nE "$pattern" "$file" 2>/dev/null \
             | grep -vE "$GUARDRAILS_ALLOW_MARKER" \
             | grep -q .; then
            echo "    MUTATION MARKER '$pattern' in $file"
            marker_errors=$((marker_errors + 1))
        fi
    done
done < <(find "$PROJECT_ROOT" -type f \( -name "*.py" -o -name "*.ts" -o -name "*.js" -o -name "*.go" -o -name "*.sh" \) \
    ! -path "*/.venv/*" ! -path "*/venv/*" ! -path "*/site-packages/*" \
    ! -path "*/node_modules/*" ! -path "*/.git/*" ! -path "*/submodules/*" \
    ! -path "*/constitution/*" \
    ! -path "*/out/*" ! -path "*/build/*" ! -path "*/dist/*" \
    ! -path "*/__pycache__/*" ! -path "*/mutants/*" \
    ! -path "*/.mypy_cache/*" ! -path "*/.pytest_cache/*" ! -path "*/.ruff_cache/*" \
    ! -path "*/tests/*" ! -path "*/challenges/*" \
    ! -path "*/scratchpad/*" ! -path "*/qa-results/*" -print0 2>/dev/null)

if [[ "$marker_errors" -eq 0 ]]; then
    pass "no mutation markers found"
else
    fail "$marker_errors mutation marker(s) detected"
    BLOCKING_FAIL=$((BLOCKING_FAIL + marker_errors))
fi

echo
echo "=== Result: ${PASS_COUNT} passed, ${FAIL_COUNT} failed ==="

if [[ "${BLOCKING_FAIL}" -gt 0 ]]; then
    exit 1
fi
exit 0
