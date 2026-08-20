#!/usr/bin/env bash
# pre_code_review.sh — Code-review gate running before pre_build_verification.sh
#
# Checks:
#   1. ruff check on all Python files
#   2. mypy on download-proxy/src/
#   3. bash -n syntax check on all scripts/*.sh
#   4. No mutation residue in production sources — DELEGATED to the
#      canonical CM-NO-PRODUCTION-MUTATION-RESIDUE detector at
#      scripts/pre_build/check_cm_no_production_mutation_residue.sh
#      (see the Check 4 block below for why it is delegated, not
#      re-implemented).
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

# Check 4 owns NO mutation-marker patterns of its own — see the Check 4
# block below. The canonical detector is the single source of truth.
RESIDUE_GATE="${SCRIPT_DIR}/pre_build/check_cm_no_production_mutation_residue.sh"

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

# --- Check 4: production mutation residue (blocking) — DELEGATED ---
#
# WHY DELEGATED, NOT RE-IMPLEMENTED (§11.4.240 / §11.4.249)
#   This check used to carry its own copy of the marker patterns. That
#   copy was LINE-ANCHORED (`^[[:space:]]*` + comment introducer), which
#   is a POSITIONAL proxy, not a structural discriminator
#   (§11.4.201(7)(a)). It therefore could not see the single most common
#   real residue shape — a marker in a TRAILING comment on a live
#   statement:
#       return True  <trailing comment carrying the marker>
#       return nil   <trailing comment carrying the marker>
#   Measured on 2026-08-20 against this very script with a
#   §11.4.201(7)(b) control needle: an own-line marker FIRED, while both
#   trailing shapes above passed through and the gate printed "no
#   mutation markers found" with exit 0. The same positional proxy had
#   already been removed from the pre-build seam; this was the second
#   site carrying it, so the codebase held two detectors that disagreed.
#
#   A third private copy of the logic would just be a third thing to
#   drift. The canonical structural detector — which tracks docstring /
#   block-comment / heredoc regions, masks string-literal interiors, and
#   so separates a CARRIER from RESIDUE by grammar rather than by column
#   — already exists and is proven on both polarities by
#   challenges/fixtures/mutation_marker_scan/polarity_check.sh (13
#   fixtures + control needle). This check now runs THAT, and owns no
#   patterns, no exclusion list and no waiver logic of its own.
#
#   Scope note, stated rather than hidden (§11.4.6 / §11.4.234(C)): the
#   canonical detector is invoked in its DEFAULT mode, so the corpus it
#   walks is its own declared production-source scope. It parses
#   .go/.py/.sh/.bash. The retired local copy also globbed .ts/.js, so
#   own-line residue in frontend TypeScript is no longer covered here.
#   That coverage is NOT silently dropped: it is printed on every run
#   below and is owed as a §11.4.197 follow-up to extend the canonical
#   detector (adding a language needs a comment-introducer + string/
#   template-literal model in the detector, which is that script's to
#   own — re-adding a blind line-anchored .ts scan here would recreate
#   exactly the defect this change removes).
echo "[4/4] production mutation residue check (delegated to canonical detector)"
if [[ ! -x "$RESIDUE_GATE" ]]; then
    # §11.4.201: an absent detector is not a clean tree. Refuse.
    fail "canonical residue detector missing or not executable: $RESIDUE_GATE"
    BLOCKING_FAIL=$((BLOCKING_FAIL + 1))
else
    residue_rc=0
    "$RESIDUE_GATE" || residue_rc=$?
    case "$residue_rc" in
        0)
            pass "no production mutation residue (canonical detector)"
            ;;
        1)
            fail "production mutation residue detected (see hits above)"
            BLOCKING_FAIL=$((BLOCKING_FAIL + 1))
            ;;
        *)
            # exit 2 = the detector could not see (zero-file walk, awk
            # fatal). A blind instrument and a clean tree return the same
            # quiet zero, so this is a FAIL, never a pass (§11.4.201(6)).
            fail "canonical residue detector errored (exit $residue_rc) — result not trustworthy"
            BLOCKING_FAIL=$((BLOCKING_FAIL + 1))
            ;;
    esac
    echo "    NOTE: canonical detector parses .go/.py/.sh/.bash; frontend .ts/.js"
    echo "          are outside its corpus — owed §11.4.197 follow-up, not a silent gap."
fi

echo
echo "=== Result: ${PASS_COUNT} passed, ${FAIL_COUNT} failed ==="

if [[ "${BLOCKING_FAIL}" -gt 0 ]]; then
    exit 1
fi
exit 0
