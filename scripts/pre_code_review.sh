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
SKIP_COUNT=0
TOTAL_STEPS=4

pass() {
    PASS_COUNT=$((PASS_COUNT + 1))
    echo "  PASS [$PASS_COUNT]: $1"
}

fail() {
    FAIL_COUNT=$((FAIL_COUNT + 1))
    echo "  FAIL [$FAIL_COUNT]: $1"
}

skip() {
    SKIP_COUNT=$((SKIP_COUNT + 1))
    echo "  SKIP [$SKIP_COUNT]: $1"
}

# WARN = the check RAN and produced findings that are DELIBERATELY
# non-blocking (pre-existing issues). It is a real verdict — distinct from
# SKIP, where nothing was inspected at all. Keeping them separate is what
# stops "the analyzer is missing" from wearing "the analyzer found things"
# as a disguise, which is defect (b) described below.
WARN_COUNT=0
warn() {
    WARN_COUNT=$((WARN_COUNT + 1))
    echo "  WARN [$WARN_COUNT]: $1"
}

# --- Tool resolution (§11.4.201(11) artifact-usability) -------------------
#
# WHY THIS EXISTS — the gate was blind to its own tooling.
#   Measured 2026-09-01 on a clean tree at 60729c9: this gate invoked the
#   BARE names `ruff` and `mypy`. Neither is on PATH; both are installed at
#   .venv/bin/. Both invocations died with "command not found", and the
#   `if ... ; else` arms below reported that as "found pre-existing issues
#   (non-blocking)" — so the gate printed "=== Result: 2 passed, 0 failed
#   ===" and exit 0 having executed ZERO of its two analyzers. Meanwhile
#   `.venv/bin/ruff check .` reported "All checks passed!" — the gate could
#   not see its own clean result any more than it could have seen a dirty
#   one.
#
#   Two stacked defects, both in the §11.4.201 family:
#     (a) §11.4.201(11) ARTIFACT-USABILITY — the gate probed a PROXY (is
#         the name on PATH?) instead of the ARTIFACT through its real
#         invocation path (the resolved binary). The proxy failed in the
#         direction that matters: a working, installed analyzer read as
#         unusable.
#     (b) §11.4.201(6) FALSE-NULL — "tool absent" and "tool reports
#         findings" produced the IDENTICAL message and the IDENTICAL
#         non-blocking outcome. A blind instrument and a clean tree
#         returned the same quiet pass.
#
#   The irony is the point, and it is why this comment is long: this gate
#   exists to catch quality problems, and was itself the quality problem —
#   a check that had checked nothing, reporting PASSED. That is the exact
#   §11.4 PASS-bluff shape the gate is deployed to prevent, occurring
#   inside the preventer.
#
# Resolution order mirrors the established PREFLIGHT_PY idiom in
# scripts/pre_build_verification.sh (project venv first, then PATH), so a
# developer reading either script meets one convention, not two.
resolve_tool() {
    local tool="$1" override="$2" cand
    # 1. Explicit operator override (mirrors PREFLIGHT_PY's "${PYTHON:-}").
    if [[ -n "${override}" ]]; then
        if [[ -x "${override}" ]] || command -v "${override}" >/dev/null 2>&1; then
            printf '%s\n' "${override}"
            return 0
        fi
        return 1
    fi
    # 2. Project venv — the declared dev environment, checked as a real
    #    executable file, never as a name lookup.
    cand="${PROJECT_ROOT}/.venv/bin/${tool}"
    if [[ -x "${cand}" ]]; then
        printf '%s\n' "${cand}"
        return 0
    fi
    # 3. PATH fallback.
    if command -v "${tool}" >/dev/null 2>&1; then
        printf '%s\n' "${tool}"
        return 0
    fi
    return 1
}

# TOOL-ABSENT is a BLOCKING FAIL, not a SKIP. Justification (§11.4.3 does
# permit an honest SKIP-with-reason for a genuinely absent environment, so
# this choice needs stating rather than assuming):
#   1. ruff and mypy are DECLARED dev dependencies of this project and ship
#      in .venv/. Their absence is not "this environment cannot perform the
#      check" (the §11.4.3 SKIP case, e.g. hardware not present) — it is
#      "the declared environment is not provisioned", a real, actionable,
#      operator-fixable condition.
#   2. The refusal is NOT a §11.4.201(1) false positive: the asserted
#      condition ("the analyzer did not execute") is REAL and resolved from
#      the authoritative source (the resolved path), and every candidate
#      path probed is printed on refusal so it is diagnosable in one step
#      (§11.4.201(5)).
#   3. A code-review gate that cannot see MUST refuse rather than bless
#      (§11.4.201(4) conservative-safe default).
# Escape hatch is EXPLICIT and RECORDED, never silent (§11.4.234(D) —
# the commit/push mechanism stays unblocked on an unprovisioned clone):
# PRE_CODE_REVIEW_ALLOW_MISSING_TOOLS=1 downgrades the refusal to a loud
# SKIP that is counted as a SKIP and NEVER as a PASS.
ALLOW_MISSING_TOOLS="${PRE_CODE_REVIEW_ALLOW_MISSING_TOOLS:-0}"

tool_absent() {
    local tool="$1" override="$2" upper
    upper="$(printf '%s' "${tool}" | tr '[:lower:]' '[:upper:]')"
    echo "    TOOL-ABSENT: '${tool}' did not resolve — this check DID NOT RUN."
    # Report the paths ACTUALLY probed, never a generic list (§11.4.6 /
    # §11.4.201(5): a refusal must print its resolved evidence, and an
    # override short-circuits the venv+PATH search so claiming those were
    # probed would be a fabricated diagnostic inside the honesty fix).
    if [[ -n "${override}" ]]; then
        echo "                 probed: ${override} (from \$${upper}) — not executable, not on PATH"
        echo "                 note: \$${upper} was set, so the .venv and PATH candidates were NOT tried"
    else
        echo "                 probed: ${PROJECT_ROOT}/.venv/bin/${tool} (not executable)"
        echo "                 probed: '${tool}' on PATH (command -v: not found)"
    fi
    echo "                 fix: python3.12+ -m venv .venv && .venv/bin/pip install ${tool}"
    echo "                 override: ${upper}=/path/to/${tool}"
    if [[ "${ALLOW_MISSING_TOOLS}" == "1" ]]; then
        skip "${tool} NOT RUN — tool absent (PRE_CODE_REVIEW_ALLOW_MISSING_TOOLS=1 override recorded)"
        return 0
    fi
    fail "${tool} NOT RUN — tool absent; a check that did not run is not a check that passed"
    return 1
}

echo "=== Code-Review Gate ==="
echo

# Check 4 owns NO mutation-marker patterns of its own — see the Check 4
# block below. The canonical detector is the single source of truth.
RESIDUE_GATE="${SCRIPT_DIR}/pre_build/check_cm_no_production_mutation_residue.sh"

RUFF_FAILED=0
MYPY_FAILED=0
BLOCKING_FAIL=0

# --- Check 1: ruff check ---
# THREE outcomes, never conflated (this is the whole point of the fix):
#   tool present + clean    -> PASS
#   tool present + findings -> WARNING, non-blocking (policy DELIBERATELY
#                              unchanged: these are pre-existing issues)
#   tool ABSENT             -> TOOL-ABSENT + blocking FAIL (see above)
echo "[1/4] ruff check on all Python files"
if RUFF_BIN="$(resolve_tool ruff "${RUFF:-}")"; then
    echo "    using: ${RUFF_BIN}"
    if (cd "$PROJECT_ROOT" && "${RUFF_BIN}" check .); then
        pass "ruff check passed (clean)"
    else
        warn "ruff RAN and found pre-existing issues (non-blocking)"
        RUFF_FAILED=1
    fi
else
    tool_absent ruff "${RUFF:-}" || BLOCKING_FAIL=$((BLOCKING_FAIL + 1))
fi

# --- Check 2: mypy --- (same three-outcome contract as Check 1)
echo "[2/4] mypy on download-proxy/src/"
if MYPY_BIN="$(resolve_tool mypy "${MYPY:-}")"; then
    echo "    using: ${MYPY_BIN}"
    if (cd "$PROJECT_ROOT" && "${MYPY_BIN}" download-proxy/src/); then
        pass "mypy passed (clean)"
    else
        warn "mypy RAN and found pre-existing issues (non-blocking)"
        MYPY_FAILED=1
    fi
else
    tool_absent mypy "${MYPY:-}" || BLOCKING_FAIL=$((BLOCKING_FAIL + 1))
fi

# --- Check 3: bash -n syntax check (blocking) ---
echo "[3/4] bash -n syntax check on scripts/*.sh"
# Corpus honesty (§11.4.201(6)): this loop was audited for the same
# false-null shape as Checks 1-2 and does NOT have it — measured 2026-09-01
# against an empty directory, the unglobbed literal `*.sh` reaches `bash -n`,
# which errors, so an empty corpus already produced a FAIL, never a false
# pass. What it lacked was an HONEST MESSAGE: it reported "syntax error in
# *.sh". The scanned-count below states the corpus size on every run and
# refuses explicitly on zero, so "checked nothing" can never be read off as
# "checked everything, all clean".
bash_errors=0
bash_scanned=0
for script in "$SCRIPT_DIR"/*.sh; do
    [[ -e "$script" ]] || continue   # unglobbed literal => corpus is empty
    bash_scanned=$((bash_scanned + 1))
    if ! bash -n "$script" 2>/dev/null; then
        fail "bash syntax error in $(basename "$script")"
        bash_errors=$((bash_errors + 1))
        BLOCKING_FAIL=$((BLOCKING_FAIL + 1))
    fi
done
echo "    scanned ${bash_scanned} script(s)"
if [[ "$bash_scanned" -eq 0 ]]; then
    fail "bash -n corpus EMPTY (${SCRIPT_DIR}/*.sh matched nothing) — check DID NOT RUN"
    BLOCKING_FAIL=$((BLOCKING_FAIL + 1))
elif [[ "$bash_errors" -eq 0 ]]; then
    pass "all ${bash_scanned} scripts/*.sh pass syntax check"
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
# Summary honesty (§11.4.201(6)): the pre-fix line read "2 passed, 0 failed"
# for a run in which 2 of 4 steps never executed — the counters described
# only the steps that HAD run, so silence about the other two read as
# success. SKIPs are now surfaced, and any step that produced no verdict at
# all is named explicitly rather than quietly vanishing from the arithmetic.
ACCOUNTED=$((PASS_COUNT + WARN_COUNT + FAIL_COUNT + SKIP_COUNT))
echo "=== Result: ${PASS_COUNT} passed, ${WARN_COUNT} warned (ran, non-blocking findings)," \
     "${FAIL_COUNT} failed, ${SKIP_COUNT} skipped" \
     "— ${ACCOUNTED} verdicts over ${TOTAL_STEPS} steps ==="
if [[ "${ACCOUNTED}" -lt "${TOTAL_STEPS}" ]]; then
    echo "    WARNING: $(( TOTAL_STEPS - ACCOUNTED )) step(s) produced NO verdict —" \
         "this summary does NOT certify them."
fi
if [[ "${SKIP_COUNT}" -gt 0 ]]; then
    echo "    NOTE: ${SKIP_COUNT} check(s) were SKIPPED, not passed. This gate did" \
         "not inspect what they cover."
fi

if [[ "${BLOCKING_FAIL}" -gt 0 ]]; then
    exit 1
fi
exit 0
