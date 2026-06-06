#!/usr/bin/env bash
# pre_build_verification.sh — Pre-build gate verifying constitution inheritance
# is real and every invariant holds.
#
# Invoked by the build orchestrator before any build.
# Returns non-zero (BLOCKING) if any invariant fails.
#
# Invariants:
#   1. constitution/ directory exists
#   2. constitution/Constitution.md exists and contains the §11.4 anchor
#   3. constitution/CLAUDE.md contains anti-bluff covenant anchor
#   4. constitution/AGENTS.md contains anti-bluff covenant anchor
#   5. Parent CLAUDE.md references constitution submodule
#   6. Parent AGENTS.md references constitution submodule
#   7. Parent CONSTITUTION.md references Helix Universal Constitution
#   8. Parent CLAUDE.md contains §11.4 propagation anchor literal
#   9. Parent AGENTS.md contains §11.4 propagation anchor literal
#  10. Parent CONSTITUTION.md contains §11.4 propagation anchor literal
#  11. .claude/settings.json exists with PreToolUse guard hook (§11.4.109)
#  12. docs/AGENT_GUARDRAILS.md contains SUBAGENT CONSTITUTIONAL PREAMBLE heading
#  13. docs/AGENT_GUARDRAILS.md contains ORCHESTRATOR PRE-ACTION CHECKLIST heading
#  14. constitution/scripts/hooks/guard-forbidden-commands.sh exists (§11.4.109)
#  15. tests/hooks/test_guard_forbidden_commands.sh exists
#  16. CM-MARKDOWN-EXPORT-SYNC: every in-scope governance/tracker Markdown doc
#      has fresh .html AND .pdf siblings (mtime >= .md mtime) (§11.4.65)
#  (17). Optional: challenges/scripts/run_all_challenges.sh (if FULL_VALIDATION=1)
#
# Constitution: §1.1 (paired mutation), §11.4 (anti-bluff covenant), §11.4.125 (code-review gate), §11.4.109 (anti-forgetting enforcement), §11.4.65 (universal Markdown export)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# --- Code-Review Gate (x11.4.125) — run first, fail fast ---
echo "[pre-code-review] Running code-review gate..."
if ! bash "${SCRIPT_DIR}/pre_code_review.sh"; then
    echo "[pre-code-review] FAILED — pre-build verification aborted."
    exit 1
fi
echo "[pre-code-review] PASSED"
echo

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

echo "=== Constitution Inheritance Verification Gate ==="
echo

# --- Invariant 1: constitution directory ---
echo "[1/16] constitution/ directory exists"
if [[ -d "${PROJECT_ROOT}/constitution" ]]; then
    pass "constitution/ exists"
else
    fail "constitution/ directory not found"
fi

# --- Invariant 2: Constitution.md anchor ---
echo "[2/16] constitution/Constitution.md §11.4 anchor"
CONSTITUTION_ANCHOR='§11.4 End-user quality guarantee'
if [[ -f "${PROJECT_ROOT}/constitution/Constitution.md" ]] && \
   grep -qF "${CONSTITUTION_ANCHOR}" "${PROJECT_ROOT}/constitution/Constitution.md"; then
    pass "Constitution.md contains §11.4 anchor"
else
    fail "Constitution.md missing §11.4 anchor"
fi

# --- Invariant 3: CLAUDE.md anchor ---
echo "[3/16] constitution/CLAUDE.md anti-bluff covenant anchor"
CLAUDE_ANCHOR='MANDATORY ANTI-BLUFF COVENANT'
if [[ -f "${PROJECT_ROOT}/constitution/CLAUDE.md" ]] && \
   grep -qF "${CLAUDE_ANCHOR}" "${PROJECT_ROOT}/constitution/CLAUDE.md"; then
    pass "CLAUDE.md contains anti-bluff covenant anchor"
else
    fail "CLAUDE.md missing anti-bluff covenant anchor"
fi

# --- Invariant 4: AGENTS.md anchor ---
echo "[4/16] constitution/AGENTS.md anti-bluff covenant anchor"
AGENTS_ANCHOR='Anti-bluff covenant'
if [[ -f "${PROJECT_ROOT}/constitution/AGENTS.md" ]] && \
   grep -qF "${AGENTS_ANCHOR}" "${PROJECT_ROOT}/constitution/AGENTS.md"; then
    pass "AGENTS.md contains anti-bluff covenant anchor"
else
    fail "AGENTS.md missing anti-bluff covenant anchor"
fi

# --- Invariant 5: Parent CLAUDE.md inheritance pointer ---
echo "[5/16] Parent CLAUDE.md inheritance pointer"
if grep -qF 'constitution/CLAUDE.md' "${PROJECT_ROOT}/CLAUDE.md"; then
    pass "CLAUDE.md references constitution submodule"
else
    fail "CLAUDE.md missing inheritance pointer to constitution"
fi

# --- Invariant 6: Parent AGENTS.md inheritance pointer ---
echo "[6/16] Parent AGENTS.md inheritance pointer"
if grep -qF 'constitution/AGENTS.md' "${PROJECT_ROOT}/AGENTS.md"; then
    pass "AGENTS.md references constitution submodule"
else
    fail "AGENTS.md missing inheritance pointer to constitution"
fi

# --- Invariant 7: Parent CONSTITUTION.md inheritance pointer ---
echo "[7/16] Parent CONSTITUTION.md inheritance pointer"
if grep -qF 'Helix Universal Constitution' "${PROJECT_ROOT}/CONSTITUTION.md"; then
    pass "CONSTITUTION.md references Helix Universal Constitution"
else
    fail "CONSTITUTION.md missing inheritance pointer to Helix Constitution"
fi

# --- Invariant 8: Parent CLAUDE.md propagation anchor ---
echo "[8/16] Parent CLAUDE.md §11.4 propagation anchor"
if grep -qF '§11.4.10 (credentials handling)' "${PROJECT_ROOT}/CLAUDE.md"; then
    pass "CLAUDE.md contains §11.4 propagation anchor"
else
    fail "CLAUDE.md missing §11.4 propagation anchor"
fi

# --- Invariant 9: Parent AGENTS.md propagation anchor ---
echo "[9/16] Parent AGENTS.md §11.4 propagation anchor"
if grep -qF '§11.4.10' "${PROJECT_ROOT}/AGENTS.md"; then
    pass "AGENTS.md contains §11.4 propagation anchor"
else
    fail "AGENTS.md missing §11.4 propagation anchor"
fi

# --- Invariant 10: Parent CONSTITUTION.md propagation anchor ---
echo "[10/16] Parent CONSTITUTION.md §11.4 propagation anchor"
if grep -qF '§11.4.10' "${PROJECT_ROOT}/CONSTITUTION.md"; then
    pass "CONSTITUTION.md contains §11.4 propagation anchor"
else
    fail "CONSTITUTION.md missing §11.4 propagation anchor"
fi

# --- Invariant 11: .claude/settings.json with PreToolUse hook ---
echo "[11/16] .claude/settings.json with PreToolUse guard hook"
SETTINGS_FILE="${PROJECT_ROOT}/.claude/settings.json"
if [[ -f "${SETTINGS_FILE}" ]] && \
   grep -qF 'PreToolUse' "${SETTINGS_FILE}" && \
   grep -qF 'guard-forbidden-commands.sh' "${SETTINGS_FILE}"; then
    pass ".claude/settings.json has PreToolUse hook configured"
else
    fail ".claude/settings.json missing or missing PreToolUse hook"
fi

# --- Invariant 12: AGENT_GUARDRAILS.md SUBAGENT CONSTITUTIONAL PREAMBLE ---
echo "[12/16] docs/AGENT_GUARDRAILS.md SUBAGENT CONSTITUTIONAL PREAMBLE"
GUARDRAILS_FILE="${PROJECT_ROOT}/docs/AGENT_GUARDRAILS.md"
if [[ -f "${GUARDRAILS_FILE}" ]] && \
   grep -qF 'SUBAGENT CONSTITUTIONAL PREAMBLE' "${GUARDRAILS_FILE}"; then
    pass "AGENT_GUARDRAILS.md contains SUBAGENT CONSTITUTIONAL PREAMBLE"
else
    fail "AGENT_GUARDRAILS.md missing SUBAGENT CONSTITUTIONAL PREAMBLE"
fi

# --- Invariant 13: AGENT_GUARDRAILS.md ORCHESTRATOR PRE-ACTION CHECKLIST ---
echo "[13/16] docs/AGENT_GUARDRAILS.md ORCHESTRATOR PRE-ACTION CHECKLIST"
if [[ -f "${GUARDRAILS_FILE}" ]] && \
   grep -qF 'ORCHESTRATOR PRE-ACTION CHECKLIST' "${GUARDRAILS_FILE}"; then
    pass "AGENT_GUARDRAILS.md contains ORCHESTRATOR PRE-ACTION CHECKLIST"
else
    fail "AGENT_GUARDRAILS.md missing ORCHESTRATOR PRE-ACTION CHECKLIST"
fi

# --- Invariant 14: guard hook script at canonical path ---
echo "[14/16] constitution/scripts/hooks/guard-forbidden-commands.sh"
HOOK_SCRIPT="${PROJECT_ROOT}/constitution/scripts/hooks/guard-forbidden-commands.sh"
if [[ -f "${HOOK_SCRIPT}" ]] && [[ -x "${HOOK_SCRIPT}" ]]; then
    pass "Guard hook script exists and is executable"
else
    fail "Guard hook script missing or not executable"
fi

# --- Invariant 15: hermetic hook test exists ---
echo "[15/16] tests/hooks/test_guard_forbidden_commands.sh"
HOOK_TEST="${PROJECT_ROOT}/tests/hooks/test_guard_forbidden_commands.sh"
if [[ -f "${HOOK_TEST}" ]] && [[ -x "${HOOK_TEST}" ]]; then
    pass "Hermetic hook test exists"
else
    fail "Hermetic hook test missing or not executable"
fi

# --- Invariant 16: CM-MARKDOWN-EXPORT-SYNC (§11.4.65) ---
# Every in-scope governance/tracker Markdown doc MUST have .html AND .pdf
# siblings whose mtime is >= the .md mtime (stale exports are a §11.4.65
# violation regardless of whether the .md itself is correct).
#
# Scope is the explicit established governance/tracker set that, by project
# convention, IS supposed to carry exports: root governance docs
# (README/CLAUDE/AGENTS/CONSTITUTION) + the docs/ trackers + any
# docs/**/Status*.md. docs/research/** and any doc that legitimately has no
# exports are intentionally OUT of scope.
echo "[16/16] CM-MARKDOWN-EXPORT-SYNC: in-scope Markdown export freshness (§11.4.65)"
EXPORT_SYNC_SCOPE=(
    "README.md"
    "CLAUDE.md"
    "AGENTS.md"
    "CONSTITUTION.md"
    "docs/Issues.md"
    "docs/Issues_Summary.md"
    "docs/Fixed.md"
    "docs/Fixed_Summary.md"
    "docs/CONTINUATION.md"
)
# Auto-discover any Status docs (none today, but enforce when they appear).
while IFS= read -r status_md; do
    [[ -n "${status_md}" ]] && EXPORT_SYNC_SCOPE+=("${status_md#"${PROJECT_ROOT}/"}")
done < <(find "${PROJECT_ROOT}/docs" -type f -name 'Status*.md' 2>/dev/null | sort)

export_sync_violations=()
for rel_md in "${EXPORT_SYNC_SCOPE[@]}"; do
    md="${PROJECT_ROOT}/${rel_md}"
    # An in-scope doc that does not exist is not a violation here (other
    # invariants own existence); only enforce export freshness when the .md
    # is present.
    [[ -f "${md}" ]] || continue
    for ext in html pdf; do
        sib="${md%.md}.${ext}"
        if [[ ! -f "${sib}" ]]; then
            export_sync_violations+=("${rel_md%.md}.${ext} missing")
        elif [[ "${sib}" -ot "${md}" ]]; then
            export_sync_violations+=("${rel_md%.md}.${ext} stale (older than ${rel_md})")
        fi
    done
done

if [[ "${#export_sync_violations[@]}" -eq 0 ]]; then
    pass "CM-MARKDOWN-EXPORT-SYNC: all in-scope docs have fresh .html/.pdf siblings"
else
    fail "CM-MARKDOWN-EXPORT-SYNC: ${#export_sync_violations[@]} export(s) missing/stale"
    for v in "${export_sync_violations[@]}"; do
        echo "      - ${v}"
    done
fi

# --- Optional: Run challenge aggregator when FULL_VALIDATION=1 ---
if [[ -n "${FULL_VALIDATION:-}" ]] && [[ "${FULL_VALIDATION}" = "1" ]]; then
    echo
    echo "--- FULL_VALIDATION: Running challenge aggregator ---"
    CHALLENGES="${PROJECT_ROOT}/challenges/scripts/run_all_challenges.sh"
    if [[ -f "${CHALLENGES}" ]] && [[ -x "${CHALLENGES}" ]]; then
        if bash "${CHALLENGES}"; then
            pass "Challenge aggregator: all challenges passed"
        else
            fail "Challenge aggregator: one or more challenges failed"
        fi
    else
        echo "  SKIP: run_all_challenges.sh not found or not executable"
    fi
fi

echo
echo "=== Result: ${PASS_COUNT} passed, ${FAIL_COUNT} failed ==="

if [[ "${FAIL_COUNT}" -gt 0 ]]; then
    exit 1
fi
exit 0
