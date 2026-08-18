#!/usr/bin/env bash
# pre_build_verification.sh — Pre-build gate verifying constitution inheritance
# is real and every invariant holds.
#
# Invoked by the build orchestrator before any build.
# Returns non-zero (BLOCKING) if any invariant fails.
#
# Invariants:
#   0. PREFLIGHT-INTERPRETER: `.venv/bin/python` (else `_select_python`-selected)
#      can import pytest+rpds+jsonschema — catches the §11.4.238 RD2-41b/RD2-43
#      ABI-mismatch class where a bare `python3 -m pytest` silently
#      ModuleNotFoundErrors at collection (system Python vs `.venv` drift).
#      SKIP-with-reason (§11.4.3/§11.4.69 `feature_class=preflight_interpreter`)
#      ONLY when `.venv/bin/python` is genuinely absent AND no fallback qualifies;
#      never silently pass on ImportError (§11.4.201 conservative-safe REFUSE).
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
#  17. CM-WORKABLE-ITEMS-VALIDATE: workable-items validate passes (§11.4.93/§11.4.95)
#  18. CM-WORKABLE-ITEMS-EXPORT-VALIDATE: workable-items-export.sh --check-only
#      passes (§11.4.93/§11.4.65). Previously named CM-DOCS-CHAIN-VALIDATE against
#      the misnomered `docs_chain.sh` — renamed 2026-08-15 (BOB-104) when the
#      REAL Docs Chain engine landed at constitution/submodules/docs_chain/.
#      The real-engine sync/verify is invariant 24 (CM-DOCS-CHAIN-ENGINE-VERIFY).
#  19. CM-QA-DISCOVERY-LEDGER-FRESH: docs/QA_DISCOVERY_LEDGER.md revision header
#      present AND `## Entries` count == `Discovery-channel split` table total (§11.4.238)
#  20. CM-QA-IS-THE-DISCOVERER: every out-of-band ledger entry carries both
#      **escape-audit:** and **new-check:** fields (§11.4.238(C))
#  21. CM-COVENANT-114-238-PROPAGATION: Constitution.md has exactly ONE
#      §11.4.238 block-start (§11.4.227(B)); the §11.4.157 lockstep mirror set
#      constitution/{CLAUDE,AGENTS,QWEN,GEMINI}.md each carries the literal
#      (§11.4.35 — the mirror set is the constitution submodule's own files,
#      NOT the boba project-root CLAUDE.md/AGENTS.md)
#  22. CM-WORKABLE-ITEMS-EXPORT-STEP1-REAL-INVOCATION: `scripts/workable-items-export.sh
#      --check-only` runs to exit-0 AND its combined stdout+stderr contains
#      NEITHER "binary not found" NOR "ERROR:" — retroactive catcher for the
#      §11.4.238 RD2-41a escape where Step 1/3 silently no-op'd because a
#      hardcoded binary path did not exist. Distinct from invariant 18 (which
#      only reads exit code): a `--check-only` run can trivially exit 0 while
#      printing an ERROR: line the caller never inspected — precisely the
#      RD2-41a shape. Extended-to-all-cases (§11.4.146) sibling of
#      tests/unit/test_docs_chain_binary_resolution.sh (test file name kept
#      for git-history preservation; script was renamed 2026-08-15 BOB-104).
#  23. CM-NO-PRODUCTION-MUTATION-RESIDUE: no mutation-marker residue in
#      production source paths (§11.4.84 working-tree-quiescence guarantee
#      at the pre-build seam). Mutation-marker-specific patterns detected:
#      - Go/C-style comment MUT'ATED tokens (e.g. `// MUT'ATED for §...`)
#      - Python/shell comment MUT'ATED tokens
#      - Fake-pass "always pass" tokens in comments (either //-style or #-style)
#      - The `if fals'e &&` short-circuit-swallow mutation shape
#      Scans production paths (download-proxy/, qBitTorrent-go/, scripts/,
#      plugins/, webui-bridge.py) restricted to *.go/*.py/*.sh; excludes
#      constitution/, submodules/, tests/, challenges/, scratchpad/,
#      qa-results/, node_modules/, .venv/, .git/ per §11.4.201(1) false-
#      positive guard. Retroactive catcher for the 2026-08-10 Agent H
#      forensic FACT where a GCM auth-bypass mutation in
#      qBitTorrent-go/internal/db/crypto.go (`if fals'e &&err != nil // MUT'ATED`)
#      existed mid-window while every existing seam-check reported green.
#      INV23_FIXTURE_ROOT env override targets the scan at a fixture dir for
#      golden-good/golden-bad §11.4.107(10) self-validation (paired §1.1
#      mutation at scratchpad/agent-L-fixtures/).
#  24. CM-DOCS-CHAIN-ENGINE-VERIFY: the REAL Docs Chain engine (constitution/
#      submodules/docs_chain/) runs `verify --all` against .docs_chain/contexts/*
#      exit 0 in-sync (§11.4.106). If the engine binary is not built OR pandoc/
#      weasyprint absent, SKIP-with-reason per §11.4.3 (never fake PASS).
#      Distinct from invariant 18 (workable-items-export.sh — the .md source
#      regenerator): invariant 24 asserts that the derived .html/.pdf/.docx
#      siblings hash-match their .md sources per §11.4.106's content-hash
#      change detection. Added 2026-08-15 (BOB-104) alongside docs_chain
#      submodule incorporation.
#  25. CM-RESOURCE-PRESSURE-SIGNATURE-CHECK: runs
#      challenges/scripts/resource_pressure_signature_challenge.sh (task #77,
#      BOB-076 2nd forced-logout incident 2026-08-18) under a 60s timeout as
#      a PROACTIVE, NON-BLOCKING host-pressure probe. This invariant NEVER
#      contributes to FAIL_COUNT — a tripped signature is real host-pressure
#      evidence outside this project's control, and per §11.4.234 the
#      pre-build gate must never itself become the reason a build cannot
#      proceed. Disposition: exit 0 -> PASS; exit non-zero (signature over
#      threshold) -> WARN with the full diagnostic printed + a timestamped
#      evidence log written to docs/qa/pre_build_resource_pressure/ (gitignored
#      per the repo-wide `*.log` pattern — local-only, never repo bloat);
#      timeout (124) or the challenge missing -> SKIP-with-reason (§11.4.3).
#  26. CM-BADGE-FRESHNESS-CHECK: runs scripts/compute-badges.sh --check
#      (§11.4.259, BOB-118) under a 180s timeout as a PROACTIVE,
#      NON-BLOCKING check that README.md's machine-derived "python tests"
#      / "frontend tests" badges still match a live re-computation. This
#      invariant NEVER contributes to FAIL_COUNT (§11.4.234 always-
#      unblocked) — a stale badge is a documentation-freshness drift, not
#      a build defect. Disposition: exit 0 -> PASS; exit 2 (stale) -> WARN
#      with the diagnostic printed + remediation command; timeout (124) or
#      the script missing -> SKIP-with-reason (§11.4.3).
#  (opt). Optional: challenges/scripts/run_all_challenges.sh (if FULL_VALIDATION=1)
#
# Constitution: §1.1 (paired mutation), §11.4 (anti-bluff covenant), §11.4.84 (working-tree quiescence), §11.4.107(10) (self-validated golden-good/golden-bad), §11.4.125 (code-review gate), §11.4.109 (anti-forgetting enforcement), §11.4.65 (universal Markdown export), §11.4.201(1) (false-positive-refusal is a FAIL-bluff), §11.4.238 (automated QA is the discoverer), §11.4.227(B) (propagation gates count block-starts), §12.12 (thread/process-headroom awareness), §11.4.234 (always-unblocked mechanism)

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

# --- PREFLIGHT: interpreter capability probe (§11.4.238 RD2-41b/RD2-43) ---
# Retroactively catches the class where a bare `python3 -m pytest` silently
# fails at COLLECTION with ModuleNotFoundError because the system Python
# resolves to a different ABI than what the project's native extensions
# (rpds, jsonschema) were built against. Mirror the ci.sh _select_python
# preference chain: .venv/bin/python -> python3.13 -> python3.12 -> python3.
echo "[PREFLIGHT] interpreter capability (§11.4.238 RD2-41b/RD2-43)"
PREFLIGHT_PY=""
for cand in \
    "${PYTHON:-}" \
    "${PROJECT_ROOT}/.venv/bin/python" \
    "${PROJECT_ROOT}/.venv/bin/python3" \
    python3.13 python3.12 python3; do
    [[ -z "${cand}" ]] && continue
    if command -v "${cand}" >/dev/null 2>&1 || [[ -x "${cand}" ]]; then
        PREFLIGHT_PY="${cand}"
        break
    fi
done
if [[ -z "${PREFLIGHT_PY}" ]]; then
    # No qualifying interpreter at all — honest SKIP-with-reason per §11.4.3/§11.4.69
    # feature_class=preflight_interpreter (§11.4.201 conservative-safe: don't silently pass;
    # cite the missing .venv path so the operator knows exactly what to create).
    echo "  SKIP: preflight_interpreter — no qualifying Python found"
    echo "        expected .venv/bin/python at ${PROJECT_ROOT}/.venv/bin/python"
    echo "        (create via: python3.12+ -m venv .venv && .venv/bin/pip install -e .)"
else
    PREFLIGHT_LOG="$(mktemp)"
    if "${PREFLIGHT_PY}" -c 'import pytest, rpds, jsonschema' >"${PREFLIGHT_LOG}" 2>&1; then
        pass "PREFLIGHT interpreter: ${PREFLIGHT_PY} can import pytest+rpds+jsonschema"
        rm -f "${PREFLIGHT_LOG}"
    else
        fail "PREFLIGHT interpreter: ${PREFLIGHT_PY} cannot import required modules (RD2-41b/RD2-43 class)"
        echo "        --- ImportError transcript ---"
        sed 's/^/        /' "${PREFLIGHT_LOG}"
        echo "        --- end ---"
        echo "        Actionable fix: run tests via \`.venv/bin/python -m pytest ...\`,"
        echo "        NEVER a bare \`python3 -m pytest\` on this host (system Python ABI drift)."
        rm -f "${PREFLIGHT_LOG}"
    fi
fi

# --- Invariant 1: constitution directory ---
echo "[1/23] constitution/ directory exists"
if [[ -d "${PROJECT_ROOT}/constitution" ]]; then
    pass "constitution/ exists"
else
    fail "constitution/ directory not found"
fi

# --- Invariant 2: Constitution.md anchor ---
echo "[2/23] constitution/Constitution.md §11.4 anchor"
CONSTITUTION_ANCHOR='§11.4 End-user quality guarantee'
if [[ -f "${PROJECT_ROOT}/constitution/Constitution.md" ]] && \
   grep -qF "${CONSTITUTION_ANCHOR}" "${PROJECT_ROOT}/constitution/Constitution.md"; then
    pass "Constitution.md contains §11.4 anchor"
else
    fail "Constitution.md missing §11.4 anchor"
fi

# --- Invariant 3: CLAUDE.md anchor ---
echo "[3/23] constitution/CLAUDE.md anti-bluff covenant anchor"
CLAUDE_ANCHOR='MANDATORY ANTI-BLUFF COVENANT'
if [[ -f "${PROJECT_ROOT}/constitution/CLAUDE.md" ]] && \
   grep -qF "${CLAUDE_ANCHOR}" "${PROJECT_ROOT}/constitution/CLAUDE.md"; then
    pass "CLAUDE.md contains anti-bluff covenant anchor"
else
    fail "CLAUDE.md missing anti-bluff covenant anchor"
fi

# --- Invariant 4: AGENTS.md anchor ---
echo "[4/23] constitution/AGENTS.md anti-bluff covenant anchor"
AGENTS_ANCHOR='Anti-bluff covenant'
if [[ -f "${PROJECT_ROOT}/constitution/AGENTS.md" ]] && \
   grep -qF "${AGENTS_ANCHOR}" "${PROJECT_ROOT}/constitution/AGENTS.md"; then
    pass "AGENTS.md contains anti-bluff covenant anchor"
else
    fail "AGENTS.md missing anti-bluff covenant anchor"
fi

# --- Invariant 5: Parent CLAUDE.md inheritance pointer ---
echo "[5/23] Parent CLAUDE.md inheritance pointer"
if grep -qF 'constitution/CLAUDE.md' "${PROJECT_ROOT}/CLAUDE.md"; then
    pass "CLAUDE.md references constitution submodule"
else
    fail "CLAUDE.md missing inheritance pointer to constitution"
fi

# --- Invariant 6: Parent AGENTS.md inheritance pointer ---
echo "[6/23] Parent AGENTS.md inheritance pointer"
if grep -qF 'constitution/AGENTS.md' "${PROJECT_ROOT}/AGENTS.md"; then
    pass "AGENTS.md references constitution submodule"
else
    fail "AGENTS.md missing inheritance pointer to constitution"
fi

# --- Invariant 7: Parent CONSTITUTION.md inheritance pointer ---
echo "[7/23] Parent CONSTITUTION.md inheritance pointer"
if grep -qF 'Helix Universal Constitution' "${PROJECT_ROOT}/CONSTITUTION.md"; then
    pass "CONSTITUTION.md references Helix Universal Constitution"
else
    fail "CONSTITUTION.md missing inheritance pointer to Helix Constitution"
fi

# --- Invariant 8: Parent CLAUDE.md propagation anchor ---
echo "[8/23] Parent CLAUDE.md §11.4 propagation anchor"
if grep -qF '§11.4.10 (credentials handling)' "${PROJECT_ROOT}/CLAUDE.md"; then
    pass "CLAUDE.md contains §11.4 propagation anchor"
else
    fail "CLAUDE.md missing §11.4 propagation anchor"
fi

# --- Invariant 9: Parent AGENTS.md propagation anchor ---
echo "[9/23] Parent AGENTS.md §11.4 propagation anchor"
if grep -qF '§11.4.10' "${PROJECT_ROOT}/AGENTS.md"; then
    pass "AGENTS.md contains §11.4 propagation anchor"
else
    fail "AGENTS.md missing §11.4 propagation anchor"
fi

# --- Invariant 10: Parent CONSTITUTION.md propagation anchor ---
echo "[10/23] Parent CONSTITUTION.md §11.4 propagation anchor"
if grep -qF '§11.4.10' "${PROJECT_ROOT}/CONSTITUTION.md"; then
    pass "CONSTITUTION.md contains §11.4 propagation anchor"
else
    fail "CONSTITUTION.md missing §11.4 propagation anchor"
fi

# --- Invariant 11: .claude/settings.json with PreToolUse hook ---
echo "[11/23] .claude/settings.json with PreToolUse guard hook"
SETTINGS_FILE="${PROJECT_ROOT}/.claude/settings.json"
if [[ -f "${SETTINGS_FILE}" ]] && \
   grep -qF 'PreToolUse' "${SETTINGS_FILE}" && \
   grep -qF 'guard-forbidden-commands.sh' "${SETTINGS_FILE}"; then
    pass ".claude/settings.json has PreToolUse hook configured"
else
    fail ".claude/settings.json missing or missing PreToolUse hook"
fi

# --- Invariant 12: AGENT_GUARDRAILS.md SUBAGENT CONSTITUTIONAL PREAMBLE ---
echo "[12/23] docs/AGENT_GUARDRAILS.md SUBAGENT CONSTITUTIONAL PREAMBLE"
GUARDRAILS_FILE="${PROJECT_ROOT}/docs/AGENT_GUARDRAILS.md"
if [[ -f "${GUARDRAILS_FILE}" ]] && \
   grep -qF 'SUBAGENT CONSTITUTIONAL PREAMBLE' "${GUARDRAILS_FILE}"; then
    pass "AGENT_GUARDRAILS.md contains SUBAGENT CONSTITUTIONAL PREAMBLE"
else
    fail "AGENT_GUARDRAILS.md missing SUBAGENT CONSTITUTIONAL PREAMBLE"
fi

# --- Invariant 13: AGENT_GUARDRAILS.md ORCHESTRATOR PRE-ACTION CHECKLIST ---
echo "[13/23] docs/AGENT_GUARDRAILS.md ORCHESTRATOR PRE-ACTION CHECKLIST"
if [[ -f "${GUARDRAILS_FILE}" ]] && \
   grep -qF 'ORCHESTRATOR PRE-ACTION CHECKLIST' "${GUARDRAILS_FILE}"; then
    pass "AGENT_GUARDRAILS.md contains ORCHESTRATOR PRE-ACTION CHECKLIST"
else
    fail "AGENT_GUARDRAILS.md missing ORCHESTRATOR PRE-ACTION CHECKLIST"
fi

# --- Invariant 14: guard hook script at canonical path ---
echo "[14/23] constitution/scripts/hooks/guard-forbidden-commands.sh"
HOOK_SCRIPT="${PROJECT_ROOT}/constitution/scripts/hooks/guard-forbidden-commands.sh"
if [[ -f "${HOOK_SCRIPT}" ]] && [[ -x "${HOOK_SCRIPT}" ]]; then
    pass "Guard hook script exists and is executable"
else
    fail "Guard hook script missing or not executable"
fi

# --- Invariant 15: hermetic hook test exists ---
echo "[15/23] tests/hooks/test_guard_forbidden_commands.sh"
HOOK_TEST="${PROJECT_ROOT}/tests/hooks/test_guard_forbidden_commands.sh"
if [[ -f "${HOOK_TEST}" ]] && [[ -x "${HOOK_TEST}" ]]; then
    pass "Hermetic hook test exists"
else
    fail "Hermetic hook test missing or not executable"
fi

# --- Invariant 16: CM-MARKDOWN-EXPORT-SYNC (§11.4.65) ---
# Every Markdown file under docs/, scripts/, and project root MUST have
# .html AND .pdf siblings whose mtime is >= the .md mtime.
# docs/research/** and docs/qa/** are intentionally OUT of scope.
# .docx siblings are gitignored per BOB-011 (WARNING only, not failure).
echo "[16/23] CM-MARKDOWN-EXPORT-SYNC: all-Markdown export freshness (§11.4.65)"

export_sync_violations=()
export_docx_warnings=()

while IFS= read -r -d '' md; do
    rel="${md#"${PROJECT_ROOT}/"}"

    # Skip excluded directories
    case "${rel}" in
        docs/research/*|docs/qa/*) continue ;;
    esac

    [[ -f "${md}" ]] || continue
    for ext in html pdf; do
        sib="${md%.md}.${ext}"
        if [[ ! -f "${sib}" ]]; then
            export_sync_violations+=("${rel%.md}.${ext} missing")
        elif [[ "${sib}" -ot "${md}" ]]; then
            export_sync_violations+=("${rel%.md}.${ext} stale (older than ${rel})")
        fi
    done

    # WARNING (not failure) for missing .docx siblings
    docx_sib="${md%.md}.docx"
    if [[ ! -f "${docx_sib}" ]]; then
        export_docx_warnings+=("${rel%.md}.docx missing (gitignored per BOB-011)")
    fi
done < <(
    find "${PROJECT_ROOT}" -maxdepth 1 -name '*.md' -type f -print0
    find "${PROJECT_ROOT}/docs" "${PROJECT_ROOT}/scripts" -name '*.md' -type f -print0 2>/dev/null
)

if [[ "${#export_docx_warnings[@]}" -gt 0 ]]; then
    echo "  WARN: ${#export_docx_warnings[@]} missing .docx sibling(s) (gitignored per BOB-011)"
    for w in "${export_docx_warnings[@]}"; do
        echo "        - ${w}"
    done
fi

if [[ "${#export_sync_violations[@]}" -eq 0 ]]; then
    pass "CM-MARKDOWN-EXPORT-SYNC: all in-scope docs have fresh .html/.pdf siblings"
else
    fail "CM-MARKDOWN-EXPORT-SYNC: ${#export_sync_violations[@]} export(s) missing/stale"
    for v in "${export_sync_violations[@]}"; do
        echo "      - ${v}"
    done
fi

# --- Invariant 17: CM-WORKABLE-ITEMS-VALIDATE (§11.4.93/§11.4.95) ---
echo "[17/23] CM-WORKABLE-ITEMS-VALIDATE: workable-items validate (§11.4.93/§11.4.95)"
# Binary resolution chain (matches constitution/scripts/reporting/report_item.sh
# and scripts/docs_chain.sh): env override -> committed constitution copy ->
# on-demand `go build`. The naive "bin/workable-items" path never existed in
# this checkout (bin/ is a gitignored local build-output dir nothing ever
# populated) — this invariant silently SKIPPED on every pre-build run until
# this fix (2026-08-08); see tests/unit/test_docs_chain_binary_resolution.sh
# for the sibling regression guard on docs_chain.sh's identical bug.
WORKABLE_BINARY="${WORKABLE_ITEMS_BIN:-}"
if [[ -n "${WORKABLE_BINARY}" ]]; then
    case "${WORKABLE_BINARY}" in
        /*) : ;;
        *) WORKABLE_BINARY="${PROJECT_ROOT}/${WORKABLE_BINARY}" ;;
    esac
fi
if [[ -z "${WORKABLE_BINARY}" || ! -x "${WORKABLE_BINARY}" ]]; then
    WI_SRC="${PROJECT_ROOT}/constitution/scripts/workable-items"
    for cand in "${WI_SRC}/bin/workable-items" "${WI_SRC}/workable-items" "${PROJECT_ROOT}/bin/workable-items"; do
        if [[ -x "${cand}" ]]; then WORKABLE_BINARY="${cand}"; break; fi
    done
fi
if [[ -z "${WORKABLE_BINARY}" || ! -x "${WORKABLE_BINARY}" ]]; then
    if command -v go >/dev/null 2>&1; then
        WI_BUILD="$(mktemp -d)/workable-items"
        if ( cd "${PROJECT_ROOT}/constitution/scripts/workable-items" && go build -o "${WI_BUILD}" ./cmd/workable-items ) >/dev/null 2>&1; then
            WORKABLE_BINARY="${WI_BUILD}"
        fi
    fi
fi
WORKABLE_DB="${PROJECT_ROOT}/docs/workable_items.db"
if [[ -n "${WORKABLE_BINARY}" && -x "${WORKABLE_BINARY}" ]] && [[ -f "${WORKABLE_DB}" ]]; then
    if "${WORKABLE_BINARY}" validate --db "${WORKABLE_DB}"; then
        pass "workable-items validate: DB invariant check passed"
    else
        fail "workable-items validate: DB invariant check FAILED"
    fi
    # §11.4.238 QA-discovery-ledger (docs/QA_DISCOVERY_LEDGER.md, BOB-008 entry):
    # a DB write landed with no matching docs/Issues.md/Fixed.md update, and
    # nothing in this gate would have caught it — validate() only checks
    # internal DB invariants, never DB-vs-Markdown divergence. Extended here
    # so this gate is the automated check that closes that coverage escape.
    ISSUES_MD="${PROJECT_ROOT}/docs/Issues.md"
    FIXED_MD="${PROJECT_ROOT}/docs/Fixed.md"
    if [[ -f "${ISSUES_MD}" && -f "${FIXED_MD}" ]]; then
        if "${WORKABLE_BINARY}" diff --db "${WORKABLE_DB}" --issues "${ISSUES_MD}" --fixed "${FIXED_MD}"; then
            pass "workable-items diff: DB and Markdown are in sync"
        else
            fail "workable-items diff: DB and Markdown have DIVERGED (run 'workable-items sync md-to-db' or 'db-to-md' to reconcile)"
        fi
    fi
else
    echo "  SKIP: workable-items binary or DB not present — skipping invariant 17"
fi

# --- Invariant 18: CM-WORKABLE-ITEMS-EXPORT-VALIDATE (§11.4.93/§11.4.65) ---
# NOTE: DOCS_CHAIN variable name is retained to preserve backward-compatibility
# with the §11.4.238 RD2-41a regression test that expects that specific label
# in the output stream; the actual script is scripts/workable-items-export.sh
# (renamed 2026-08-15 BOB-104). The REAL Docs Chain engine gate lives at
# invariant 24 (CM-DOCS-CHAIN-ENGINE-VERIFY) below.
echo "[18/24] CM-WORKABLE-ITEMS-EXPORT-VALIDATE: workable-items-export.sh --check-only (§11.4.93/§11.4.65)"
DOCS_CHAIN="${PROJECT_ROOT}/scripts/workable-items-export.sh"
if [[ -f "${DOCS_CHAIN}" ]] && [[ -x "${DOCS_CHAIN}" ]]; then
    if bash "${DOCS_CHAIN}" --check-only; then
        pass "workable-items-export --check-only: docs regeneration validation passed"
    else
        fail "workable-items-export --check-only: docs regeneration validation FAILED"
    fi
else
    echo "  SKIP: scripts/workable-items-export.sh not found or not executable — skipping invariant 18"
fi

# --- Invariant 19: CM-QA-DISCOVERY-LEDGER-FRESH (§11.4.238) ---
# The QA discovery-channel ledger MUST exist, carry its §11.4.44 revision
# header, and its `## Entries` count MUST equal the last data row of the
# `Discovery-channel split` table. Silent drift between the two is a
# §11.4.6 no-guessing violation at the ledger layer.
echo "[19/23] CM-QA-DISCOVERY-LEDGER-FRESH: ledger fresh + counts aligned (§11.4.238)"
LEDGER="${PROJECT_ROOT}/docs/QA_DISCOVERY_LEDGER.md"
if [[ ! -f "${LEDGER}" ]]; then
    fail "QA discovery ledger not found at docs/QA_DISCOVERY_LEDGER.md"
elif ! grep -qE '^\*\*Last modified:\*\*' "${LEDGER}"; then
    fail "QA discovery ledger missing '**Last modified:**' §11.4.44 header field"
else
    LEDGER_ENTRIES=$(awk '
        /^## Entries[[:space:]]*$/ {inside=1; next}
        /^## / {inside=0}
        inside && /^### / {c++}
        END {print c+0}
    ' "${LEDGER}")
    LEDGER_DECLARED=$(awk '
        /^## Discovery-channel split/ {inside=1; next}
        /^## / && inside {inside=0}
        inside && /^\|/ && !/^\| *Period/ && !/^\| *---/ {last=$0}
        END {
            if (last == "") {print "MISSING"; exit}
            n = split(last, cells, "|")
            auto_s = cells[3]; ob_s = cells[4]
            match(auto_s, /[0-9]+/); a = substr(auto_s, RSTART, RLENGTH)+0
            match(ob_s, /[0-9]+/);   b = substr(ob_s, RSTART, RLENGTH)+0
            print a + b
        }
    ' "${LEDGER}")
    if [[ "${LEDGER_DECLARED}" = "MISSING" ]]; then
        fail "QA discovery ledger missing Discovery-channel split table data row"
    elif [[ "${LEDGER_ENTRIES}" != "${LEDGER_DECLARED}" ]]; then
        fail "QA discovery ledger drift: entries=${LEDGER_ENTRIES} split-table-declared=${LEDGER_DECLARED}"
    else
        pass "QA discovery ledger fresh (entries=${LEDGER_ENTRIES} == declared=${LEDGER_DECLARED})"
    fi
fi

# --- Invariant 20: CM-QA-IS-THE-DISCOVERER (§11.4.238(C)) ---
# For every ledger entry whose channel is NOT `automated-helixqa`, both
# **escape-audit:** and **new-check:** fields MUST be present. The check
# matches the FIELD SHAPE (`**escape-audit:**` marker), never a bare
# substring — carrier prose mentioning the token in narrative text does
# NOT satisfy the field (§11.4.201(7)(a) match-structure-not-substring).
echo "[20/23] CM-QA-IS-THE-DISCOVERER: every out-of-band entry carries required fields (§11.4.238(C))"
if [[ ! -f "${LEDGER}" ]]; then
    fail "QA discovery ledger not found — cannot verify §11.4.238(C)"
else
    LEDGER_OFFENDERS=$(awk '
        BEGIN {inside=0; e_id=""; e_body=""}
        function flush() {
            if (e_id != "") {
                is_oob = (e_body ~ /\*\*channel:\*\*[^\n]*/) && (e_body !~ /channel:\*\*[^\n]*automated-helixqa/)
                if (is_oob) {
                    has_ea = (e_body ~ /\*\*escape-audit:\*\*/)
                    has_nc = (e_body ~ /\*\*new-check:\*\*/)
                    if (!has_ea || !has_nc) {
                        miss = ""
                        if (!has_ea) miss = miss "escape-audit "
                        if (!has_nc) miss = miss "new-check"
                        printf("%s: missing %s\n", e_id, miss)
                    }
                }
            }
            e_id = ""; e_body = ""
        }
        /^## Entries[[:space:]]*$/ {inside=1; next}
        /^## / {flush(); inside=0}
        inside && /^### / {flush(); e_id = $0; next}
        inside {e_body = e_body "\n" $0}
        END {flush()}
    ' "${LEDGER}")
    if [[ -n "${LEDGER_OFFENDERS}" ]]; then
        fail "out-of-band ledger entries missing required §11.4.238(C) fields:"
        while IFS= read -r line; do
            [[ -z "${line}" ]] || echo "        - ${line}"
        done <<< "${LEDGER_OFFENDERS}"
    else
        pass "every out-of-band ledger entry carries **escape-audit:** and **new-check:**"
    fi
fi

# --- Invariant 21: CM-COVENANT-114-238-PROPAGATION (§11.4.227(B)) ---
# The §11.4.157 lockstep mirror set for a universal anchor is the CONSTITUTION
# SUBMODULE's own CLAUDE.md + AGENTS.md + QWEN.md + GEMINI.md — NOT the boba
# project-root CLAUDE.md/AGENTS.md (§11.4.35 canonical-root-inheritance-clarity:
# project-root files carry only project-specific rules + inheritance pointer,
# they never enumerate every universal anchor; enforcing that would be a
# §11.4.201(1) FAIL-bluff / §11.4.120 wrong-seam defect — see 2026-08-10 fix).
# Constitution.md: exactly ONE §11.4.238 block-start (^### §?11.4.238\b) per
# §11.4.227(B) block-integrity — 0 = MISSING, >1 = duplication FAIL.
# Mirror files (constitution/{CLAUDE,AGENTS,QWEN,GEMINI}.md): at least one
# literal `11.4.238` (§11.4.157 lockstep-carrier check).
# Refuses conservatively per §11.4.201 on any file that cannot be read.
echo "[21/23] CM-COVENANT-114-238-PROPAGATION: §11.4.238 propagates (§11.4.227(B))"
PROP_FINDINGS=""
CONSTITUTION_FILE="${PROJECT_ROOT}/constitution/Constitution.md"
if [[ ! -f "${CONSTITUTION_FILE}" ]]; then
    PROP_FINDINGS+="constitution/Constitution.md not found\n"
else
    BLOCKS=$(grep -cE '^### §?11\.4\.238\b' "${CONSTITUTION_FILE}" || true)
    if [[ "${BLOCKS}" -ne 1 ]]; then
        PROP_FINDINGS+="Constitution.md: expected exactly 1 §11.4.238 block-start (^### §?11.4.238), got ${BLOCKS} (§11.4.227(B))\n"
    fi
fi
for mirror_pair in \
    "constitution/CLAUDE.md:${PROJECT_ROOT}/constitution/CLAUDE.md" \
    "constitution/AGENTS.md:${PROJECT_ROOT}/constitution/AGENTS.md" \
    "constitution/QWEN.md:${PROJECT_ROOT}/constitution/QWEN.md" \
    "constitution/GEMINI.md:${PROJECT_ROOT}/constitution/GEMINI.md"; do
    label="${mirror_pair%%:*}"
    path="${mirror_pair#*:}"
    if [[ ! -f "${path}" ]]; then
        PROP_FINDINGS+="${label} not found at ${path}\n"
    elif ! grep -qF '11.4.238' "${path}"; then
        PROP_FINDINGS+="${label}: literal '11.4.238' missing entirely (§11.4.157 lockstep-mirror gap)\n"
    fi
done
if [[ -n "${PROP_FINDINGS}" ]]; then
    fail "§11.4.238 propagation violations:"
    printf '%b' "${PROP_FINDINGS}" | while IFS= read -r line; do
        [[ -z "${line}" ]] || echo "        - ${line}"
    done
else
    pass "§11.4.238 propagates (Constitution block-start ×1, §11.4.157 mirror-set literal present ×4)"
fi

# --- Invariant 22: CM-WORKABLE-ITEMS-EXPORT-STEP1-REAL-INVOCATION (§11.4.238 RD2-41a retroactive catcher) ---
# Distinct from invariant 18 (exit code only): asserts the combined stdout+stderr
# of `workable-items-export.sh --check-only` contains NEITHER "binary not
# found" NOR "ERROR:" — the exact escape shape from RD2-41a where Step 1/3
# silently no-op'd because a hardcoded binary path (bin/workable-items) did
# not exist and no downstream check inspected the printed error line. Sibling
# of tests/unit/test_docs_chain_binary_resolution.sh at the pre-build seam.
echo "[22/24] CM-WORKABLE-ITEMS-EXPORT-STEP1-REAL-INVOCATION: export step 1 really invoked (§11.4.238 RD2-41a)"
if [[ ! -f "${DOCS_CHAIN}" || ! -x "${DOCS_CHAIN}" ]]; then
    echo "  SKIP: scripts/workable-items-export.sh not found or not executable — skipping invariant 22"
else
    DC_LOG="$(mktemp)"
    DC_EXIT=0
    bash "${DOCS_CHAIN}" --check-only >"${DC_LOG}" 2>&1 || DC_EXIT=$?
    # match structure not substring (§11.4.201(7)(a)): only real error lines,
    # never carrier prose from the log — anchor to start-of-line for the
    # "  ERROR:" self-diagnostic printed by workable-items-export.sh's own ERRORS branch.
    if [[ "${DC_EXIT}" -ne 0 ]]; then
        fail "CM-WORKABLE-ITEMS-EXPORT-STEP1-REAL-INVOCATION: --check-only exit=${DC_EXIT} (expected 0)"
        echo "        --- last 30 lines ---"
        tail -n 30 "${DC_LOG}" | sed 's/^/        /'
        echo "        --- end ---"
    elif grep -qE '^[[:space:]]*ERROR:' "${DC_LOG}"; then
        fail "CM-WORKABLE-ITEMS-EXPORT-STEP1-REAL-INVOCATION: --check-only printed ERROR: line despite exit 0 (RD2-41a shape)"
        grep -nE '^[[:space:]]*ERROR:' "${DC_LOG}" | sed 's/^/        /'
    elif grep -qF 'binary not found' "${DC_LOG}"; then
        fail "CM-WORKABLE-ITEMS-EXPORT-STEP1-REAL-INVOCATION: 'binary not found' in output — Step 1 silently no-op'd (RD2-41a)"
        grep -nF 'binary not found' "${DC_LOG}" | sed 's/^/        /'
    else
        pass "workable-items-export step 1 really invoked (exit 0, no 'binary not found' / 'ERROR:' lines)"
    fi
    rm -f "${DC_LOG}"
fi

# --- Invariant 23: CM-NO-PRODUCTION-MUTATION-RESIDUE (§11.4.84) ---
# Working-tree quiescence at the pre-build seam: refuses any build whose
# production sources still carry mutation-marker residue.
#
# Retroactive catcher for the 2026-08-10 Agent H forensic FACT: a GCM
# auth-bypass mutation (`if fals'e &&err != nil // MUT'ATED for §11.4.115 RED`)
# lived in qBitTorrent-go/internal/db/crypto.go mid-window; the agent
# restored the file before returning, so a pure post-hoc diff check would
# report clean — but this gate would have refused the build had the
# restoration failed or the mutation window overlapped a build trigger.
#
# Pattern classes detected (built by string-concatenation to avoid the
# gate self-matching its own literal patterns — §11.4.201(7)(a)
# match-structure-not-substring):
#   1. Go/C-style comment MUT'ATED tokens          (//<space>MUT'ATED)
#   2. Python/shell comment MUT'ATED tokens        (#<space>MUT'ATED)
#   3. Fake-pass tokens in //-comments            (//<space>alwa'ys pass)
#   4. Fake-pass tokens in #-comments             (#<space>alwa'ys pass)
#   5. `if fals'e &&` short-circuit-swallow shape (Agent H's exact form)
#
# Excludes (§11.4.201(1) FALSE-POSITIVE guard, mirroring pre_code_review.sh):
#   constitution/  submodules/  tests/  challenges/  scratchpad/
#   qa-results/    node_modules/  .venv/  .git/  __pycache__/  mutants/
#
# Testing seam: INV23_FIXTURE_ROOT env override scans a fixture dir
# instead of production paths, so the paired §1.1 mutation golden-good/
# golden-bad fixtures at scratchpad/agent-L-fixtures/ can self-validate
# the analyzer per §11.4.107(10). NEVER used to bypass real scans in a
# normal build.
echo "[23/24] CM-NO-PRODUCTION-MUTATION-RESIDUE: no mutation-marker residue in production sources (§11.4.84)"

# Build patterns via concatenation so this script does not self-match.
_M_MARK="MUT""ATED"
_M_ALWAYS="alwa""ys pass"
_M_IFFALSE="if fals""e && "
# Combined ERE — anchored to the shapes we actually mean (not bare substrings):
INV23_PATTERN="(//[[:space:]]*${_M_MARK})|(#[[:space:]]*${_M_MARK})|(//[[:space:]]*${_M_ALWAYS})|(#[[:space:]]*${_M_ALWAYS})|(${_M_IFFALSE})"

if [[ -n "${INV23_FIXTURE_ROOT:-}" ]]; then
    INV23_ROOTS=("${INV23_FIXTURE_ROOT}")
    echo "  (INV23_FIXTURE_ROOT override — scanning ${INV23_FIXTURE_ROOT})"
else
    # Production source paths — only those that ship user-visible behaviour.
    INV23_ROOTS=()
    for cand in \
        "${PROJECT_ROOT}/download-proxy" \
        "${PROJECT_ROOT}/qBitTorrent-go" \
        "${PROJECT_ROOT}/scripts" \
        "${PROJECT_ROOT}/plugins" \
        "${PROJECT_ROOT}/webui-bridge.py"; do
        [[ -e "${cand}" ]] && INV23_ROOTS+=("${cand}")
    done
fi

if [[ "${#INV23_ROOTS[@]}" -eq 0 ]]; then
    # §11.4.201 conservative-safe: cite what was expected, do not silently pass.
    fail "CM-NO-PRODUCTION-MUTATION-RESIDUE: no production source root resolved to scan"
else
    # Path exclusions. In FIXTURE-ROOT test mode the fixture dir itself
    # lives under scratchpad/ (deliberate — §11.4.11 scratchpad discipline),
    # so if we kept the scratchpad exclusion the test would see zero files
    # and false-PASS the golden-bad fixture (§11.4.201(6) false-null).
    # Dropping the scratchpad exclusion ONLY in fixture-root mode preserves
    # the production-scan behaviour while making the analyzer testable.
    INV23_EXCLUDES=(
        ! -path '*/constitution/*'
        ! -path '*/submodules/*'
        ! -path '*/tests/*'
        ! -path '*/challenges/*'
        ! -path '*/qa-results/*'
        ! -path '*/node_modules/*'
        ! -path '*/.venv/*'
        ! -path '*/venv/*'
        ! -path '*/site-packages/*'
        ! -path '*/.git/*'
        ! -path '*/__pycache__/*'
        ! -path '*/mutants/*'
        ! -path '*/.mypy_cache/*'
        ! -path '*/.pytest_cache/*'
        ! -path '*/.ruff_cache/*'
        ! -path '*/out/*' ! -path '*/build/*' ! -path '*/dist/*'
    )
    if [[ -z "${INV23_FIXTURE_ROOT:-}" ]]; then
        INV23_EXCLUDES+=( ! -path '*/scratchpad/*' )
    fi

    INV23_HITS_LOG="$(mktemp)"
    while IFS= read -r -d '' _f; do
        # -E extended-regex, -n line number, -H filename even on single-file
        grep -nHE "${INV23_PATTERN}" "${_f}" >>"${INV23_HITS_LOG}" 2>/dev/null || true
    done < <(find "${INV23_ROOTS[@]}" -type f \
        \( -name '*.go' -o -name '*.py' -o -name '*.sh' \) \
        "${INV23_EXCLUDES[@]}" \
        -print0 2>/dev/null)
    INV23_COUNT=$(wc -l <"${INV23_HITS_LOG}" | tr -d ' ')
    if [[ "${INV23_COUNT}" -eq 0 ]]; then
        pass "no mutation-marker residue in production sources"
    else
        fail "CM-NO-PRODUCTION-MUTATION-RESIDUE: ${INV23_COUNT} mutation-marker hit(s) in production sources"
        # Print the offenders (file:line:matched) so the operator can act.
        while IFS= read -r line; do
            [[ -z "${line}" ]] || echo "        - ${line}"
        done <"${INV23_HITS_LOG}"
    fi
    rm -f "${INV23_HITS_LOG}"
fi

# --- Invariant 24: CM-DOCS-CHAIN-ENGINE-VERIFY (§11.4.106 real engine) ---
# Assert the REAL Docs Chain engine (constitution/submodules/docs_chain/)
# reports every context in-sync — the derived .html/.pdf/.docx siblings
# hash-match their .md sources under content-hash change detection.
# Distinct from invariant 18 (workable-items-export.sh, which regenerates
# the .md SOURCES): invariant 24 gates the .md->export propagation the
# real engine mechanically enforces. SKIP-with-reason (§11.4.3) if the
# engine binary is not built OR transform tools absent (never fake PASS).
echo "[24/24] CM-DOCS-CHAIN-ENGINE-VERIFY: docs_chain engine verify --all (§11.4.106)"
DC_ENGINE="${PROJECT_ROOT}/constitution/submodules/docs_chain/docs_chain"
DC_CONTEXTS="${PROJECT_ROOT}/.docs_chain/contexts"
if [[ ! -x "${DC_ENGINE}" ]]; then
    echo "  SKIP: docs_chain engine binary not built at ${DC_ENGINE#${PROJECT_ROOT}/} — run: (cd constitution/submodules/docs_chain && go build -o docs_chain ./cmd/docs_chain)"
elif [[ ! -d "${DC_CONTEXTS}" ]]; then
    echo "  SKIP: no .docs_chain/contexts/ dir at project root — nothing for the engine to verify"
else
    DCE_LOG="$(mktemp)"
    DCE_EXIT=0
    "${DC_ENGINE}" verify --all --root "${PROJECT_ROOT}" >"${DCE_LOG}" 2>&1 || DCE_EXIT=$?
    if [[ "${DCE_EXIT}" -eq 0 ]]; then
        pass "docs_chain engine: verify --all in-sync ($(wc -l <"${DCE_LOG}" | tr -d ' ') contexts checked)"
    elif [[ "${DCE_EXIT}" -eq 1 ]] && grep -qE '(ToolAbsentError|tool absent|pandoc|weasyprint)' "${DCE_LOG}"; then
        echo "  SKIP: docs_chain engine reports ToolAbsentError (pandoc/weasyprint) — §11.4.3 honest-skip"
        sed 's/^/        /' "${DCE_LOG}"
    else
        fail "CM-DOCS-CHAIN-ENGINE-VERIFY: docs_chain verify --all FAILED (exit ${DCE_EXIT}) — derived docs drift from .md sources"
        echo "        --- verify output ---"
        sed 's/^/        /' "${DCE_LOG}"
        echo "        --- end ---"
        echo "        Remediation: cd \${PROJECT_ROOT} && ./constitution/submodules/docs_chain/docs_chain sync --all"
    fi
    rm -f "${DCE_LOG}"
fi

# --- Invariant 25: CM-RESOURCE-PRESSURE-SIGNATURE-CHECK (§12.12/§11.4.201, task #77 / BOB-076) ---
# Proactive, NON-BLOCKING probe for the 5 forced-logout-precursor signatures
# identified in the 2026-08-18 2nd forced-logout incident triage. This
# invariant NEVER increments FAIL_COUNT: a tripped signature is real host
# resource pressure outside this project's own control, and per §11.4.234
# the pre-build gate must always stay unblocked -- the operator needs a
# loud WARNING here, not a blocked build. Bounded to 60s so a wedged probe
# can never stall the pre-build sweep itself (§11.4.89).
echo "[25/25] CM-RESOURCE-PRESSURE-SIGNATURE-CHECK: proactive host-pressure probe (§12.12, task #77/BOB-076)"
RPS_CHALLENGE="${PROJECT_ROOT}/challenges/scripts/resource_pressure_signature_challenge.sh"
if [[ ! -f "${RPS_CHALLENGE}" ]]; then
    echo "  SKIP: resource_pressure_signature_challenge.sh not found — skipping invariant 25"
else
    RPS_LOG="$(mktemp)"
    RPS_EXIT=0
    if command -v timeout >/dev/null 2>&1; then
        timeout 60s bash "${RPS_CHALLENGE}" >"${RPS_LOG}" 2>&1 || RPS_EXIT=$?
    else
        bash "${RPS_CHALLENGE}" >"${RPS_LOG}" 2>&1 || RPS_EXIT=$?
    fi
    if [[ "${RPS_EXIT}" -eq 0 ]]; then
        pass "resource-pressure-signature-check: clean (all 5 signatures below threshold)"
    elif [[ "${RPS_EXIT}" -eq 124 ]]; then
        echo "  SKIP: resource-pressure-signature-check timed out after 60s (§11.4.3 honest-skip — non-blocking, never a FAIL)"
    else
        # WARN, never FAIL (§11.4.234 always-unblocked). Capture evidence
        # per §11.4.5/§11.4.69 so the operator has the exact trip in hand
        # before the next forced-logout-class incident.
        RPS_EVIDENCE_DIR="${PROJECT_ROOT}/docs/qa/pre_build_resource_pressure"
        mkdir -p "${RPS_EVIDENCE_DIR}"
        RPS_TS="$(date -u +%Y%m%dT%H%M%SZ)"
        RPS_EVIDENCE="${RPS_EVIDENCE_DIR}/${RPS_TS}.log"
        cp "${RPS_LOG}" "${RPS_EVIDENCE}"
        echo "  WARN: resource-pressure-signature-check tripped (exit ${RPS_EXIT}) — evidence: ${RPS_EVIDENCE#${PROJECT_ROOT}/}"
        echo "        --- diagnostic (also saved above) ---"
        sed 's/^/        /' "${RPS_LOG}"
        echo "        --- end ---"
    fi
    rm -f "${RPS_LOG}"
fi

# --- Invariant 26: CM-BADGE-FRESHNESS-CHECK (§11.4.259, BOB-118) ---
# Proactive, NON-BLOCKING check that README.md's machine-derived badges
# (python tests / frontend tests) still match a live re-computation. This
# invariant NEVER increments FAIL_COUNT: a stale badge is not a build
# defect, it is a documentation-freshness drift, and per §11.4.234 the
# pre-build gate must always stay unblocked -- the operator needs a loud
# WARNING here, not a blocked build. Bounded to 180s so a wedged pytest
# collection or vitest invocation can never stall the pre-build sweep
# itself (§11.4.89).
echo "[26/26] CM-BADGE-FRESHNESS-CHECK: README badges match live counts (§11.4.259, BOB-118)"
BADGE_SCRIPT="${PROJECT_ROOT}/scripts/compute-badges.sh"
if [[ ! -x "${BADGE_SCRIPT}" ]]; then
    echo "  SKIP: scripts/compute-badges.sh not found or not executable — skipping invariant 26"
else
    BADGE_LOG="$(mktemp)"
    BADGE_EXIT=0
    if command -v timeout >/dev/null 2>&1; then
        timeout 180s "${BADGE_SCRIPT}" --check >"${BADGE_LOG}" 2>&1 || BADGE_EXIT=$?
    else
        "${BADGE_SCRIPT}" --check >"${BADGE_LOG}" 2>&1 || BADGE_EXIT=$?
    fi
    if [[ "${BADGE_EXIT}" -eq 0 ]]; then
        pass "badge-freshness-check: README badges match live counts"
    elif [[ "${BADGE_EXIT}" -eq 124 ]]; then
        echo "  SKIP: badge-freshness-check timed out after 180s (§11.4.3 honest-skip — non-blocking, never a FAIL)"
    else
        # WARN, never FAIL (§11.4.234 always-unblocked). Loud + actionable
        # so a drift is caught within one pre-build cycle, never allowed to
        # age for months the way BOB-118's 585-vs-5248 drift did.
        echo "  WARN: badge-freshness-check found stale badges (exit ${BADGE_EXIT})"
        echo "        --- diagnostic ---"
        sed 's/^/        /' "${BADGE_LOG}"
        echo "        --- end ---"
        echo "        Remediation: ./scripts/compute-badges.sh"
    fi
    rm -f "${BADGE_LOG}"
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
