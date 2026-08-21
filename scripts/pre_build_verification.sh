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
#      - Fake-pass "alwa'ys pass" tokens in comments (//-style or #-style)
#      - The `if fals'e &&` short-circuit-swallow mutation shape
#      Delegates to scripts/pre_build/check_cm_no_production_mutation_residue.sh,
#      which discriminates residue from carriers STRUCTURALLY (§11.4.201(7)(a)):
#      it tracks docstring/block-comment/heredoc regions and masks string
#      literals, then looks for the marker in a REAL comment or the swallow
#      shape in REAL code — so a trailing marker on a live statement is caught
#      while a pattern held in a string or documented in a docstring is not.
#      See BOB-070 in that script's header for the control-needle measurement
#      that showed the previous line-anchored pattern missing 5 of 7 real
#      residue shapes. Retroactive catcher for the 2026-08-10 Agent H
#      forensic FACT where a GCM auth-bypass mutation in
#      qBitTorrent-go/internal/db/crypto.go (`if fals'e &&err != nil // MUT'ATED`)
#      existed mid-window while every existing seam-check reported green.
#      The gate accepts explicit PATH arguments so the paired §1.1 polarity
#      harness (challenges/fixtures/mutation_marker_scan/polarity_check.sh)
#      can drive the REAL detector over golden-good/golden-bad fixtures per
#      §11.4.107(10) — not a copy of its pattern.
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
#  27. CM-KILLPG-PGID-GUARD: runs scripts/pre_build/check_cm_killpg_pgid_guard.sh
#      (§11.4.263, BOB-126) — a static scan of production sources
#      (download-proxy/src/, plugins/, scripts/) that refuses any
#      os.killpg()/os.kill(-pid)/bash killpg/kill -SIG call whose target
#      is not proven, within the 10 lines above the call, to be a real
#      positive process id (isinstance(<ident>, int) and <ident> > 1 on
#      the SAME identifier). This is the mechanical enforcement of the
#      BOB-126 forensic root cause traced across 7 forced-logout
#      incidents (BOB-116/120/123/124/125/126): os.killpg(1, SIGKILL) is,
#      under glibc, IDENTICAL to kill(-1, SIGKILL) — a broadcast kill of
#      every process the caller's UID owns. BLOCKING (contributes to
#      FAIL_COUNT) — this is a real host-safety defect class, not a
#      documentation-freshness or resource-pressure signal.
#  28. CM-TEST-MOCK-PID-EXPLICIT-INT: runs
#      scripts/pre_build/check_cm_test_mock_pid_explicit_int.sh
#      (§11.4.263, BOB-126) — the TEST-side sibling of invariant 27:
#      statically scans tests/**/*.py for AsyncMock()/MagicMock()
#      subprocess-standin doubles (identified by an explicit
#      `.returncode = None` marker plus nearby .stdout.readline /
#      .stderr.read / .wait / .kill usage) that never explicitly set
#      `.pid = <int>` and never patch os.killpg — the exact shape whose
#      auto-generated `__int__`/`__index__` (defaulting to 1) can drive
#      the same broadcast-kill defect through a mocked test double.
#      BLOCKING (contributes to FAIL_COUNT).
#  29. CM-TEST-MOCK-PID-PATCHED-WHEN-REAL-PID: runs
#      scripts/pre_build/check_cm_test_mock_pid_patched_when_real_pid.sh
#      (§11.4.263, BOB-127, Task 8 syscall-audit rec #1) — the
#      adjacent-class sibling of invariant 28: satisfying invariant 28
#      (an explicit real int `.pid`) is necessary but NOT sufficient —
#      this invariant statically scans tests/**/*.py for the SAME
#      subprocess-standin doubles that DO set an explicit int-literal
#      `.pid = <int>` but never patch `os.killpg` specifically, so the
#      REAL syscall fires against a hardcoded, non-test-owned PID if it
#      happens to collide with a live process on the host (Linux PID
#      reuse). Found by Task 8 as 2 live hits in
#      test_public_tracker_subprocess_timeout.py, fixed at commit
#      8bedc5a. BLOCKING (contributes to FAIL_COUNT).
#  30. CM-BASH-UNIT-TESTS-EXECUTED: tests/unit/*.sh AND tests/pre_build/*.sh
#      (§1.1 meta-tests for the constitution-gate family, incl. the 30-check
#      gate 45 pair) are actually EXECUTED (§11.4.226) — ci.sh runs pytest,
#      which collects only test_*.py, so both whole suites were run by
#      NOTHING (tests/pre_build/'s gap was self-reported in commit 04742d7's
#      own message and never wired anywhere; closed here, tracked BOB-160).
#      Carries a NO-TRACE assertion over the
#      TRACKED corpus (main repo + constitution submodule, ~3.9k paths):
#      a marker file is stamped before the suite and every tracked path is
#      compared with bash's nanosecond-precise `-nt` afterwards, so a suite that
#      mutates a real tracked file and restores it with a plain `cp` (identical
#      content, NEW mtime — invisible to `git status`, and enough to make
#      invariant 16 report a false "export stale") is caught instead of
#      cascading into an unrelated invariant. Widened 2026-08-20 from a
#      hardcoded 3-file list; see the block's own comments for the measured
#      justification of its §11.4.224(E) submodule-scope exclusion, the
#      §11.4.201(7)(b) control needle, and the coverage-preservation assertion
#      that refuses to let the corpus silently shrink. BLOCKING.
#  --- Universal constitution gates (§11.4.35 consumer wiring) ---------------
#      Invariants 31-43 wire the inherited constitution/scripts/gates/ family.
#      Those gates are universal + project-agnostic and are consumed BY
#      REFERENCE (§11.4.28(B)/§11.4.177); each takes boba's scope as DATA.
#      A gate is wired here ONLY if it runs MEANINGFULLY against boba — PASS
#      on real evidence, FAIL on a real defect, or an honest SKIP-with-reason
#      (§11.4.3). Gates whose consumer DATA boba cannot yet supply are NOT
#      wired: wiring them would either refuse the build on a scope they were
#      never given (§11.4.201(1) FAIL-bluff) or paint green over an empty
#      manifest (a §11.4 PASS-bluff at the metric layer).
#  31. CM-COVENANT-PROPAGATION-BLOCK-INTEGRITY: the 17 CM-COVENANT-114-<N>-
#      PROPAGATION gates NOT bound in the family data pack, run against the
#      §11.4.157 lockstep mirror set constitution/{CLAUDE,AGENTS,QWEN,
#      GEMINI}.md — the SAME scope invariant 21 already declares canonical.
#      BLOCKING (all 17 green 2026-08-20).
#  32. CM-COVENANT-PROPAGATION-SUITE: the 30 data-pack-driven members of the
#      same family, via the inherited batch runner (§11.4.251 — the list
#      lives in the constitution's TSV, never duplicated here). ADVISORY:
#      27/30 green; §11.4.27/§11.4.255/§11.4.256 blocks are missing from the
#      mirror set — an UPSTREAM constitution gap boba cannot fix, and
#      §11.4.234 forbids letting it block boba's build.
#  33. CM-CLI-AGENT-PLUGINS-WIRED (§11.4.140 plugin/skill wiring). BLOCKING.
#  34. CM-MULTITRACK-ENGINE-IN-CONSTITUTION (§11.4.187). BLOCKING.
#  35. CM-SUBSYSTEM-SHORTCUTS (§11.4.140 sub-system shortcuts). BLOCKING.
#  36. CM-REPORTING-DIRECTIVES (§11.4.202 ISSUE/BUG/TASK). BLOCKING.
#  37. CM-FEATURE-DIRECTIVE (§11.4.213 FEATURE scheduling). BLOCKING.
#  38. CM-GATE-LEDGER-RATCHET (§11.4.227(A) named-gate ledger, monotone
#      decrease). BLOCKING. The single most expensive new gate (~102s).
#  39. CM-DANGEROUS-COMBINATION-FAIL-CLOSED (§11.4.252) over boba's
#      first-party source roots (download-proxy/src, plugins, scripts,
#      qBitTorrent-go, frontend/src) — an INCLUSION list, not an exclusion
#      fence. ADVISORY: 36 real hits on first run, a MIXED set of true
#      fail-opens and benign narrow-exception cleanup idioms; see the block
#      comment for why blocking an un-triaged mix would be a §11.4.201(1)
#      false refusal, and what promoting it to BLOCKING requires.
#  40. CM-ORACLE-STRATEGY-NAMED-AND-INDEPENDENT (§11.4.245) over tests/.
#      ADVISORY: 4475 unannotated test functions — a real whole-corpus gap
#      whose brownfield adoption path is an operator decision per
#      §11.4.224(E)/§11.4.66, never one this script may invent.
#  41. CM-OPENDESIGN-UI-SYSTEM (§11.4.162/§11.4.190) over frontend/ with
#      boba's real style-source globs as DATA. ADVISORY: 3/4 sub-checks fail
#      (hardcoded hex, no token artifact, no visual-regression suite) — a
#      genuine frontend design-system adoption gap.
#  42. CM-BUILD-ON-SOURCE-PROVEN-NOT-TEST-SIDE (§11.4.235(A)). BLOCKING;
#      SKIPs honestly today — needs a consumer marker config.
#  43. CM-VERSION-INCREMENT-ON-DEPLOY (§11.4.235(B)). BLOCKING; SKIPs
#      honestly today — needs a consumer deploy-ledger TSV.
#  44. CM-HEALTHCHECK-COVERS-SERVED-PORTS: every container healthcheck probes
#      EVERY port its service serves, cross-checked against the consumer
#      manifest config/served_ports.yaml (§11.4.35). Retroactive catcher for
#      BOB-138, where download-proxy reported healthy on 7186 while 7187 had
#      been dead ~2h. BLOCKING; FAILs (never SKIPs) on zero services checked
#      or missing python3+PyYAML — a blind instrument's quiet zero is not a
#      clean tree (§11.4.201(6)).
#  46. CM-PLUGIN-COUNT: runs scripts/pre_build/check_cm_plugin_count.sh
#      (BOB-149) — refuses any managed-plugin count stated in the governed
#      docs (CLAUDE.md, AGENTS.md, docs/features/Status.md) that disagrees
#      with the count DERIVED from install-plugin.sh's PLUGINS=() array.
#      "Managed plugins" resolved to FIVE individually-correct numbers
#      (curated 43 / bootstrap 12 / engines 43 / toplevel 36 / recursive 69)
#      and that ambiguity WAS the defect, so each metric is derived and
#      checked separately and a doc line must NAME which one it claims.
#      BLOCKING; see the block comment for why the count is load-bearing.
#  (opt). Optional: challenges/scripts/run_all_challenges.sh (if FULL_VALIDATION=1)
#
# Constitution: §1.1 (paired mutation), §11.4 (anti-bluff covenant), §11.4.84 (working-tree quiescence), §11.4.107(10) (self-validated golden-good/golden-bad), §11.4.125 (code-review gate), §11.4.109 (anti-forgetting enforcement), §11.4.65 (universal Markdown export), §11.4.201(1) (false-positive-refusal is a FAIL-bluff), §11.4.238 (automated QA is the discoverer), §11.4.227(B) (propagation gates count block-starts), §12.12 (thread/process-headroom awareness), §11.4.234 (always-unblocked mechanism), §11.4.263 (process-group signal-safety mandate), §11.4.35 (canonical-root inheritance — the constitution gates take boba's scope as consumer DATA), §11.4.28(B)/§11.4.177 (inherited BY REFERENCE, never copied), §11.4.227(A) (an anchor's done state is its SEAM landing), §11.4.227(B) (propagation gates count anchor BLOCK-STARTS), §11.4.251 (data-pack-driven family, no hand-maintained gate list), §11.4.234 (the mechanism is ALWAYS unblocked — advisory gates never block the build), §11.4.245 (oracle-strategy naming), §11.4.252 (fail-closed on dangerous combinations), §11.4.162/§11.4.190 (OpenDesign UI system)

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
echo "[1/49] constitution/ directory exists"
if [[ -d "${PROJECT_ROOT}/constitution" ]]; then
    pass "constitution/ exists"
else
    fail "constitution/ directory not found"
fi

# --- Invariant 2: Constitution.md anchor ---
echo "[2/49] constitution/Constitution.md §11.4 anchor"
CONSTITUTION_ANCHOR='§11.4 End-user quality guarantee'
if [[ -f "${PROJECT_ROOT}/constitution/Constitution.md" ]] && \
   grep -qF "${CONSTITUTION_ANCHOR}" "${PROJECT_ROOT}/constitution/Constitution.md"; then
    pass "Constitution.md contains §11.4 anchor"
else
    fail "Constitution.md missing §11.4 anchor"
fi

# --- Invariant 3: CLAUDE.md anchor ---
echo "[3/49] constitution/CLAUDE.md anti-bluff covenant anchor"
CLAUDE_ANCHOR='MANDATORY ANTI-BLUFF COVENANT'
if [[ -f "${PROJECT_ROOT}/constitution/CLAUDE.md" ]] && \
   grep -qF "${CLAUDE_ANCHOR}" "${PROJECT_ROOT}/constitution/CLAUDE.md"; then
    pass "CLAUDE.md contains anti-bluff covenant anchor"
else
    fail "CLAUDE.md missing anti-bluff covenant anchor"
fi

# --- Invariant 4: AGENTS.md anchor ---
echo "[4/49] constitution/AGENTS.md anti-bluff covenant anchor"
AGENTS_ANCHOR='Anti-bluff covenant'
if [[ -f "${PROJECT_ROOT}/constitution/AGENTS.md" ]] && \
   grep -qF "${AGENTS_ANCHOR}" "${PROJECT_ROOT}/constitution/AGENTS.md"; then
    pass "AGENTS.md contains anti-bluff covenant anchor"
else
    fail "AGENTS.md missing anti-bluff covenant anchor"
fi

# --- Invariant 5: Parent CLAUDE.md inheritance pointer ---
echo "[5/49] Parent CLAUDE.md inheritance pointer"
if grep -qF 'constitution/CLAUDE.md' "${PROJECT_ROOT}/CLAUDE.md"; then
    pass "CLAUDE.md references constitution submodule"
else
    fail "CLAUDE.md missing inheritance pointer to constitution"
fi

# --- Invariant 6: Parent AGENTS.md inheritance pointer ---
echo "[6/49] Parent AGENTS.md inheritance pointer"
if grep -qF 'constitution/AGENTS.md' "${PROJECT_ROOT}/AGENTS.md"; then
    pass "AGENTS.md references constitution submodule"
else
    fail "AGENTS.md missing inheritance pointer to constitution"
fi

# --- Invariant 7: Parent CONSTITUTION.md inheritance pointer ---
echo "[7/49] Parent CONSTITUTION.md inheritance pointer"
if grep -qF 'Helix Universal Constitution' "${PROJECT_ROOT}/CONSTITUTION.md"; then
    pass "CONSTITUTION.md references Helix Universal Constitution"
else
    fail "CONSTITUTION.md missing inheritance pointer to Helix Constitution"
fi

# --- Invariant 8: Parent CLAUDE.md propagation anchor ---
echo "[8/49] Parent CLAUDE.md §11.4 propagation anchor"
if grep -qF '§11.4.10 (credentials handling)' "${PROJECT_ROOT}/CLAUDE.md"; then
    pass "CLAUDE.md contains §11.4 propagation anchor"
else
    fail "CLAUDE.md missing §11.4 propagation anchor"
fi

# --- Invariant 9: Parent AGENTS.md propagation anchor ---
echo "[9/49] Parent AGENTS.md §11.4 propagation anchor"
if grep -qF '§11.4.10' "${PROJECT_ROOT}/AGENTS.md"; then
    pass "AGENTS.md contains §11.4 propagation anchor"
else
    fail "AGENTS.md missing §11.4 propagation anchor"
fi

# --- Invariant 10: Parent CONSTITUTION.md propagation anchor ---
echo "[10/49] Parent CONSTITUTION.md §11.4 propagation anchor"
if grep -qF '§11.4.10' "${PROJECT_ROOT}/CONSTITUTION.md"; then
    pass "CONSTITUTION.md contains §11.4 propagation anchor"
else
    fail "CONSTITUTION.md missing §11.4 propagation anchor"
fi

# --- Invariant 11: .claude/settings.json with PreToolUse hook ---
echo "[11/49] .claude/settings.json with PreToolUse guard hook"
SETTINGS_FILE="${PROJECT_ROOT}/.claude/settings.json"
if [[ -f "${SETTINGS_FILE}" ]] && \
   grep -qF 'PreToolUse' "${SETTINGS_FILE}" && \
   grep -qF 'guard-forbidden-commands.sh' "${SETTINGS_FILE}"; then
    pass ".claude/settings.json has PreToolUse hook configured"
else
    fail ".claude/settings.json missing or missing PreToolUse hook"
fi

# --- Invariant 12: AGENT_GUARDRAILS.md SUBAGENT CONSTITUTIONAL PREAMBLE ---
echo "[12/49] docs/AGENT_GUARDRAILS.md SUBAGENT CONSTITUTIONAL PREAMBLE"
GUARDRAILS_FILE="${PROJECT_ROOT}/docs/AGENT_GUARDRAILS.md"
if [[ -f "${GUARDRAILS_FILE}" ]] && \
   grep -qF 'SUBAGENT CONSTITUTIONAL PREAMBLE' "${GUARDRAILS_FILE}"; then
    pass "AGENT_GUARDRAILS.md contains SUBAGENT CONSTITUTIONAL PREAMBLE"
else
    fail "AGENT_GUARDRAILS.md missing SUBAGENT CONSTITUTIONAL PREAMBLE"
fi

# --- Invariant 13: AGENT_GUARDRAILS.md ORCHESTRATOR PRE-ACTION CHECKLIST ---
echo "[13/49] docs/AGENT_GUARDRAILS.md ORCHESTRATOR PRE-ACTION CHECKLIST"
if [[ -f "${GUARDRAILS_FILE}" ]] && \
   grep -qF 'ORCHESTRATOR PRE-ACTION CHECKLIST' "${GUARDRAILS_FILE}"; then
    pass "AGENT_GUARDRAILS.md contains ORCHESTRATOR PRE-ACTION CHECKLIST"
else
    fail "AGENT_GUARDRAILS.md missing ORCHESTRATOR PRE-ACTION CHECKLIST"
fi

# --- Invariant 14: guard hook script at canonical path ---
echo "[14/49] constitution/scripts/hooks/guard-forbidden-commands.sh"
HOOK_SCRIPT="${PROJECT_ROOT}/constitution/scripts/hooks/guard-forbidden-commands.sh"
if [[ -f "${HOOK_SCRIPT}" ]] && [[ -x "${HOOK_SCRIPT}" ]]; then
    pass "Guard hook script exists and is executable"
else
    fail "Guard hook script missing or not executable"
fi

# --- Invariant 15: hermetic hook test exists ---
echo "[15/49] tests/hooks/test_guard_forbidden_commands.sh"
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
echo "[16/49] CM-MARKDOWN-EXPORT-SYNC: all-Markdown export freshness (§11.4.65)"

# §11.4.65 staleness oracle. NOT a plain mtime compare: git does not preserve
# mtimes and ".html" sorts before ".md", so on any fresh clone every export
# lands with an earlier mtime (measured: 65 and 68 false-stale pairs across two
# checkout-index extractions of the SAME commit; .pdf 0/141, proving it is
# alphabetical write order). The same mtime heuristic ALSO hides real staleness:
# once an export's mtime drifts ahead, generate_markdown_exports.sh skips it
# forever (measured: extract-tracker-cookies.md had IPTORRENTS 9x, its .html 0x).
# See scripts/lib/export_staleness.sh + tests/unit/test_export_staleness_oracle.sh
# shellcheck source=scripts/lib/export_staleness.sh
source "${PROJECT_ROOT}/scripts/lib/export_staleness.sh"

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
        elif export_is_stale "${md}" "${sib}" "${PROJECT_ROOT}"; then
            export_sync_violations+=("${rel%.md}.${ext} stale (source changed after export)")
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
echo "[17/49] CM-WORKABLE-ITEMS-VALIDATE: workable-items validate (§11.4.93/§11.4.95)"
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
echo "[18/49] CM-WORKABLE-ITEMS-EXPORT-VALIDATE: workable-items-export.sh --check-only (§11.4.93/§11.4.65)"
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
echo "[19/49] CM-QA-DISCOVERY-LEDGER-FRESH: ledger fresh + counts aligned (§11.4.238)"
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
echo "[20/49] CM-QA-IS-THE-DISCOVERER: every out-of-band entry carries required fields (§11.4.238(C))"
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
echo "[21/49] CM-COVENANT-114-238-PROPAGATION: §11.4.238 propagates (§11.4.227(B))"
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
echo "[22/49] CM-WORKABLE-ITEMS-EXPORT-STEP1-REAL-INVOCATION: export step 1 really invoked (§11.4.238 RD2-41a)"
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
# production sources still carry paired-§1.1 mutation residue.
#
# Retroactive catcher for the 2026-08-10 Agent H forensic FACT: a GCM
# auth-bypass mutation (`if fals'e &&err != nil // MUT'ATED for §11.4.115 RED`)
# lived in qBitTorrent-go/internal/db/crypto.go mid-window; the agent
# restored the file before returning, so a pure post-hoc diff check would
# report clean — but this gate would have refused the build had the
# restoration failed or the mutation window overlapped a build trigger.
#
# BOB-070 (RD2-41): the detection logic now lives in a dedicated gate
# script rather than inline here. Two reasons, both structural:
#   (a) the inline scan matched by LINE POSITION (marker had to start the
#       line), a positional proxy that a §11.4.201(7)(b) control needle
#       measured on 2026-08-20 as blind to 5 of 7 real residue shapes —
#       including the trailing-comment form Agent H's own residue took;
#   (b) the paired §1.1 polarity harness could only test a COPY of the
#       inline pattern, so pattern drift here left the harness green
#       (§11.4.249 producer=oracle collapse). A separate executable gate
#       lets the harness exercise the REAL detector.
# The gate is BLOCKING (contributes to FAIL_COUNT): a build carrying live
# mutation residue can ship an auth bypass.
echo "[23/49] CM-NO-PRODUCTION-MUTATION-RESIDUE: no mutation-marker residue in production sources (§11.4.84)"
MUTRES_GATE="${PROJECT_ROOT}/scripts/pre_build/check_cm_no_production_mutation_residue.sh"
if [[ ! -x "${MUTRES_GATE}" ]]; then
    fail "CM-NO-PRODUCTION-MUTATION-RESIDUE: gate script missing or not executable at scripts/pre_build/check_cm_no_production_mutation_residue.sh"
else
    MUTRES_LOG="$(mktemp)"
    MUTRES_EXIT=0
    bash "${MUTRES_GATE}" >"${MUTRES_LOG}" 2>&1 || MUTRES_EXIT=$?
    if [[ "${MUTRES_EXIT}" -eq 0 ]]; then
        pass "CM-NO-PRODUCTION-MUTATION-RESIDUE:$(sed -n '1p' "${MUTRES_LOG}" | sed 's/^ *//')"
        # Audited waivers are never silent (§11.4.201(5), §11.4.224(E)).
        grep -F '~ WAIVED' "${MUTRES_LOG}" | sed 's/^/    /' || true
    else
        # exit 2 = the gate could not see (zero-file walk / bad path). That is
        # a §11.4.201(6) false-null, refused rather than reported clean.
        fail "CM-NO-PRODUCTION-MUTATION-RESIDUE: mutation-marker residue detected (exit ${MUTRES_EXIT})"
        echo "        --- gate output ---"
        sed 's/^/        /' "${MUTRES_LOG}"
        echo "        --- end ---"
    fi
    rm -f "${MUTRES_LOG}"
fi

# --- Invariant 24: CM-DOCS-CHAIN-ENGINE-VERIFY (§11.4.106 real engine) ---
# Assert the REAL Docs Chain engine (constitution/submodules/docs_chain/)
# reports every context in-sync — the derived .html/.pdf/.docx siblings
# hash-match their .md sources under content-hash change detection.
# Distinct from invariant 18 (workable-items-export.sh, which regenerates
# the .md SOURCES): invariant 24 gates the .md->export propagation the
# real engine mechanically enforces. SKIP-with-reason (§11.4.3) if the
# engine binary is not built OR transform tools absent (never fake PASS).
echo "[24/49] CM-DOCS-CHAIN-ENGINE-VERIFY: docs_chain engine verify --all (§11.4.106)"
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
echo "[25/49] CM-RESOURCE-PRESSURE-SIGNATURE-CHECK: proactive host-pressure probe (§12.12, task #77/BOB-076)"
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
echo "[26/49] CM-BADGE-FRESHNESS-CHECK: README badges match live counts (§11.4.259, BOB-118)"
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

# --- Invariant 27: CM-KILLPG-PGID-GUARD (§11.4.263, BOB-126) ---
# Statically refuses any production os.killpg()/os.kill(-pid)/bash killpg/
# kill -SIG call whose target is not proven, within the preceding 10
# lines, to be isinstance(<ident>, int) and <ident> > 1 on the SAME
# identifier — the exact broadcast-kill-of-UID shape traced across 7
# forced-logout incidents (BOB-116/120/123/124/125/126). BLOCKING
# (contributes to FAIL_COUNT): this closes a real host-safety defect
# class, not a documentation-freshness or resource-pressure signal.
echo "[27/49] CM-KILLPG-PGID-GUARD: no unguarded process-group kill calls (§11.4.263, BOB-126)"
KILLPG_GATE="${PROJECT_ROOT}/scripts/pre_build/check_cm_killpg_pgid_guard.sh"
if [[ ! -x "${KILLPG_GATE}" ]]; then
    fail "CM-KILLPG-PGID-GUARD: gate script missing or not executable at scripts/pre_build/check_cm_killpg_pgid_guard.sh"
else
    KILLPG_LOG="$(mktemp)"
    KILLPG_EXIT=0
    bash "${KILLPG_GATE}" >"${KILLPG_LOG}" 2>&1 || KILLPG_EXIT=$?
    if [[ "${KILLPG_EXIT}" -eq 0 ]]; then
        pass "CM-KILLPG-PGID-GUARD: $(tail -n1 "${KILLPG_LOG}")"
    else
        fail "CM-KILLPG-PGID-GUARD: unguarded killpg/kill-group call(s) detected (exit ${KILLPG_EXIT})"
        echo "        --- gate output ---"
        sed 's/^/        /' "${KILLPG_LOG}"
        echo "        --- end ---"
    fi
    rm -f "${KILLPG_LOG}"
fi

# --- Invariant 28: CM-TEST-MOCK-PID-EXPLICIT-INT (§11.4.263, BOB-126) ---
# TEST-side sibling of invariant 27: refuses any AsyncMock()/MagicMock()
# subprocess-standin mock under tests/**/*.py that is never given an
# explicit `.pid = <int>` and never patches os.killpg — the shape whose
# auto-generated `__int__`/`__index__` (defaulting to 1) reaches the same
# broadcast-kill defect through a mocked test double. BLOCKING
# (contributes to FAIL_COUNT).
echo "[28/49] CM-TEST-MOCK-PID-EXPLICIT-INT: no unguarded subprocess-mock pid in tests (§11.4.263, BOB-126)"
MOCK_PID_GATE="${PROJECT_ROOT}/scripts/pre_build/check_cm_test_mock_pid_explicit_int.sh"
if [[ ! -x "${MOCK_PID_GATE}" ]]; then
    fail "CM-TEST-MOCK-PID-EXPLICIT-INT: gate script missing or not executable at scripts/pre_build/check_cm_test_mock_pid_explicit_int.sh"
else
    MOCK_PID_LOG="$(mktemp)"
    MOCK_PID_EXIT=0
    bash "${MOCK_PID_GATE}" >"${MOCK_PID_LOG}" 2>&1 || MOCK_PID_EXIT=$?
    if [[ "${MOCK_PID_EXIT}" -eq 0 ]]; then
        pass "CM-TEST-MOCK-PID-EXPLICIT-INT: $(tail -n1 "${MOCK_PID_LOG}")"
    else
        fail "CM-TEST-MOCK-PID-EXPLICIT-INT: unguarded subprocess-mock pid hit(s) detected (exit ${MOCK_PID_EXIT})"
        echo "        --- gate output ---"
        sed 's/^/        /' "${MOCK_PID_LOG}"
        echo "        --- end ---"
    fi
    rm -f "${MOCK_PID_LOG}"
fi

# --- Invariant 29: CM-TEST-MOCK-PID-PATCHED-WHEN-REAL-PID (§11.4.263, BOB-127) ---
# Adjacent-class sibling of invariant 28: satisfying invariant 28 (an
# explicit real int `.pid`) is necessary but NOT sufficient — the
# production pid/pgid guard is satisfied by ANY real positive int, so a
# test that sets `.pid = <int>` but never patches os.killpg lets the
# REAL syscall fire against a hardcoded, non-test-owned PID (Linux PID
# reuse can make that PID a live, unrelated process). Task 8's syscall
# audit found this shape live in
# test_public_tracker_subprocess_timeout.py (2 hits, fixed at commit
# 8bedc5a). BLOCKING (contributes to FAIL_COUNT): a real, unmocked
# destructive syscall fired from a "unit" test is a genuine host-safety
# defect class, not a documentation-freshness or resource-pressure
# signal.
echo "[29/49] CM-TEST-MOCK-PID-PATCHED-WHEN-REAL-PID: no unpatched real-pid subprocess-mock in tests (§11.4.263, BOB-127)"
MOCK_PID_REAL_GATE="${PROJECT_ROOT}/scripts/pre_build/check_cm_test_mock_pid_patched_when_real_pid.sh"
if [[ ! -x "${MOCK_PID_REAL_GATE}" ]]; then
    fail "CM-TEST-MOCK-PID-PATCHED-WHEN-REAL-PID: gate script missing or not executable at scripts/pre_build/check_cm_test_mock_pid_patched_when_real_pid.sh"
else
    MOCK_PID_REAL_LOG="$(mktemp)"
    MOCK_PID_REAL_EXIT=0
    bash "${MOCK_PID_REAL_GATE}" >"${MOCK_PID_REAL_LOG}" 2>&1 || MOCK_PID_REAL_EXIT=$?
    if [[ "${MOCK_PID_REAL_EXIT}" -eq 0 ]]; then
        pass "CM-TEST-MOCK-PID-PATCHED-WHEN-REAL-PID: $(tail -n1 "${MOCK_PID_REAL_LOG}")"
    else
        fail "CM-TEST-MOCK-PID-PATCHED-WHEN-REAL-PID: unpatched real-pid subprocess-mock hit(s) detected (exit ${MOCK_PID_REAL_EXIT})"
        echo "        --- gate output ---"
        sed 's/^/        /' "${MOCK_PID_REAL_LOG}"
        echo "        --- end ---"
    fi
    rm -f "${MOCK_PID_REAL_LOG}"
fi

# --- Invariant 30: CM-BASH-UNIT-TESTS-EXECUTED (§11.4.205/§11.4.226/§11.4.227) ---
# The tests/unit/*.sh bash suite was executed by NOTHING: ci.sh runs
# `pytest tests/unit/` (which collects only test_*.py), run-all-tests.sh only
# `bash -n` syntax-checks, and pre_build merely MENTIONED some of them in
# comments. "Registration is not coverage" (§11.4.226) — a guard nobody runs
# is prose, and §11.4.227 is explicit that prose does not bind, seams do.
# Executing them for the first time (2026-08-20) immediately emitted 3 latent
# FAILs, exactly the outcome §11.4.226 predicts for never-run standing guards.
#
# WIDENED (2026-08-21, independent-review finding, IMPORTANT-3): the SAME
# defect class existed for tests/pre_build/test_*.sh — the §1.1 paired-
# mutation meta-tests for the scripts/pre_build/check_cm_*.sh gate family
# (including this invariant's own gate-45 pair). Commit 04742d7's own
# message SAID SO: "STILL OPEN (reported, not fixed): tests/pre_build/ is
# executed by NOTHING" — recorded only in prose, with no tracked item and no
# runner, until now. The glob below covers both directories; a suite in
# EITHER one that is never executed is the identical false-null this
# invariant already exists to catch (§11.4.226).
#
# QUARANTINE (§11.4.248 + §11.4.135 monotone-decrease ratchet, §11.4.224(E)
# exclusion fence): the 3 known-failing suites are listed BY NAME so they are
# visible and tracked rather than silently dead. This list MUST only shrink.
# Removing a name without fixing its suite is a §11.4.227 metric-gaming move.
# TODO(BASH-TEST-QUARANTINE): fix and de-quarantine these three.
echo "[30/49] CM-BASH-UNIT-TESTS-EXECUTED: tests/unit/*.sh + tests/pre_build/*.sh + tests/hooks/*.sh actually run (§11.4.226)"
# STRUCTURAL EXCLUSIONS — permanent by design, NOT debt. These suites invoke
# scripts/pre_build_verification.sh itself to assert on another invariant's
# output; running them from INSIDE this invariant recurses infinitely (proven
# live 2026-08-20: rc=124 timeout). The BOBA_PREBUILD_NESTED sentinel below is
# the belt-and-braces guard; this list is the braces. They still run standalone.
# Membership is evidence-based: a suite belongs here IFF it EXECUTES the gate
# (`bash "$SCRIPT"`), not merely references it. Verified 2026-08-20 by grep +
# timing; an earlier revision of this list had exactly the wrong two entries.
BASH_TEST_SELF_RECURSIVE=(
    "test_export_sync_gate.sh"                    # bash "$GATE_SCRIPT" x3, ~299s
    "test_pre_build_workable_items_invariant.sh"  # bash "$SCRIPT", timed out at 300s
)
# QUARANTINE — real debt, MUST only shrink. Removing a name without fixing its
# suite is a §11.4.227 metric-gaming move.
# EMPTY as of 2026-08-20: all three original entries were resolved by ONE
# root-cause fix in test_pre_build_workable_items_diff_check.sh (dead
# session-scratchpad path + a plain `cp` restore that bumped docs/Issues.md's
# mtime and manufactured false export staleness for the other two). Keep this
# array — it is the ratchet; adding a name is allowed only as tracked debt.
BASH_TEST_QUARANTINE=()
BASH_TEST_RAN=0; BASH_TEST_FAILED=0; BASH_TEST_QUARANTINED=0
BASH_TEST_FAILURES=()
# --- NO-TRACE corpus snapshot (§11.4.84 working-tree quiescence) ---
# WHY: several suites mutate REAL tracked files to prove a gate has teeth, then
# restore them. A plain `cp` restore returns identical CONTENT but a NEW mtime,
# and CM-MARKDOWN-EXPORT-SYNC (invariant 16) compares MTIMES — so a restore can
# silently manufacture "<doc>.html stale" and fail an unrelated invariant
# (measured cascade 2026-08-20: docs/Issues.md 1787213360 -> 1787213787, zero
# content change). Restores must use `cp -p`; this seam CATCHES a regression
# instead of trusting the convention.
#
# WIDENED 2026-08-20 from a hardcoded 3-file list (docs/Issues.md, CLAUDE.md,
# constitution/Constitution.md) to the whole TRACKED corpus: a suite mutating
# any OTHER tracked file slipped straight through the old list.
#
# WHY NOT `git status --porcelain`: it detects CONTENT change, and this defect
# is mtime-only with byte-identical content. MEASURED 2026-08-20 in an isolated
# throwaway repo — after a plain-`cp` restore, `git status --porcelain -- f.md`
# printed 0 lines BEFORE and 0 lines AFTER. It is structurally BLIND to this
# class (§11.4.201(6) FALSE-NULL), so it cannot be the instrument here.
#
# WHY a marker file + bash `-nt` instead of `stat -c%Y`: `%Y` is WHOLE SECONDS.
# MEASURED 2026-08-20: a mutate+plain-`cp`-restore completing inside ONE
# wall-clock second (marker %Y=1787217026, victim %Y=1787217026 — identical —
# with %y differing at .733817268 vs .779816962) was CAUGHT by `-nt` and MISSED
# by the `%Y` comparison this block used before. Widening the corpus therefore
# also closed a same-second blind spot that the 3-file version had.
BASH_TEST_TRACE_CORPUS=()
BASH_TEST_TRACE_UNCOVERED=""
BASH_TEST_TRACE_MARKER=""
BASH_TEST_TRACE_DIR=""
BASH_TEST_TRACE_NEEDLE_OK=1
if [[ -z "${BOBA_PREBUILD_NESTED:-}" ]]; then
    # CORPUS SCOPE — main repo + the `constitution` submodule.
    # `git ls-files` at the top level does NOT descend into submodules, and
    # constitution/Constitution.md (one of the three paths the old list covered)
    # lives inside one — enumerated explicitly, or coverage would SHRINK while
    # appearing to widen.
    #
    # EXCLUSION (§11.4.224(E) fence — stated, justified, liftable, never silent):
    # the CONTENTS of submodules/{jackett,helixqa,challenges,containers} are out
    # of the per-commit corpus. The justification is MEASURED, not assumed
    # (§11.4.6) — 3 iterations each, idle host, 2026-08-20:
    #     main + constitution        3,958 files   0.50-0.66 s
    #     + all four submodules      62,069 files   9.4-13.8 s
    # i.e. ~20x the wall-clock to cover the 58,111 additional files of those
    # four trees, on a gate that runs at every commit (§11.4.234 keeps the
    # commit/push mechanism unblocked). Evidence the excluded region is not
    # where this defect lives: a full-tree `find -newer` across the ENTIRE
    # window of a real suite run (2026-08-20; 7 suites, 0 failures) reported
    # exactly TWO changed paths in the whole checkout —
    # .remember/logs/memory-2026-08-20.log and .pytest_cache/v/randomly_seed —
    # both UNTRACKED and gitignored, and NOTHING under submodules/ at all.
    # helixqa/challenges/containers are own-org (§11.4.28 first-party), so this
    # is tracked DEBT, not a permanent carve-out:
    # TODO(NO-TRACE-SUBMODULE-SCOPE): register the §11.4.197 work item for full
    # submodule-content coverage (cheaper enumeration, or a release-seam-only
    # full run). Setting BOBA_NOTRACE_FULL_SUBMODULES=1 includes them NOW; that
    # knob can only WIDEN the corpus, never narrow it, so it is not an escape
    # hatch (§11.4.224 no-escape-hatch discipline).
    #
    # NO gate-owned-write exclusion list is needed: measured above, the suite
    # writes ZERO tracked files. An unjustified exclusion is refused
    # (§11.4.224(E)); an empty exclusion list is the honest outcome here.
    # The membership index is filled in the SAME loops that build the corpus:
    # expanding a ~4k-element array again just to search it measured ~80ms per
    # extra pass, and the coverage-preservation check below needs three lookups.
    declare -A _nt_seen=()
    _nt_main=(); _nt_const=()
    mapfile -d '' -t _nt_main < <(git -C "${PROJECT_ROOT}" ls-files -z 2>/dev/null || true)
    for _p in ${_nt_main[@]+"${_nt_main[@]}"}; do
        BASH_TEST_TRACE_CORPUS+=("${PROJECT_ROOT}/${_p}")
        _nt_seen["${PROJECT_ROOT}/${_p}"]=1
    done
    if [[ -e "${PROJECT_ROOT}/constitution/.git" ]]; then
        mapfile -d '' -t _nt_const < <(git -C "${PROJECT_ROOT}/constitution" ls-files -z --recurse-submodules 2>/dev/null || true)
        for _p in ${_nt_const[@]+"${_nt_const[@]}"}; do
            BASH_TEST_TRACE_CORPUS+=("${PROJECT_ROOT}/constitution/${_p}")
            _nt_seen["${PROJECT_ROOT}/constitution/${_p}"]=1
        done
    fi
    if [[ -n "${BOBA_NOTRACE_FULL_SUBMODULES:-}" ]]; then
        while IFS= read -r _sm; do
            [[ -n "${_sm}" ]] || continue
            [[ "${_sm}" = "constitution" ]] && continue   # already enumerated above
            [[ -e "${PROJECT_ROOT}/${_sm}/.git" ]] || continue
            _nt_sub=()
            mapfile -d '' -t _nt_sub < <(git -C "${PROJECT_ROOT}/${_sm}" ls-files -z --recurse-submodules 2>/dev/null || true)
            for _p in ${_nt_sub[@]+"${_nt_sub[@]}"}; do
                BASH_TEST_TRACE_CORPUS+=("${PROJECT_ROOT}/${_sm}/${_p}")
                _nt_seen["${PROJECT_ROOT}/${_sm}/${_p}"]=1
            done
        done < <(git config -f "${PROJECT_ROOT}/.gitmodules" --get-regexp 'submodule\..*\.path' 2>/dev/null | awk '{print $2}')
    fi

    # COVERAGE-PRESERVATION assertion: the three paths the pre-widening list
    # covered MUST still be inside the corpus. An un-initialised constitution
    # submodule would otherwise SHRINK real coverage while the block reads as
    # wider — a quiet zero is not a clean result (§11.4.201(6)).
    for _lf in "${PROJECT_ROOT}/docs/Issues.md" "${PROJECT_ROOT}/CLAUDE.md" "${PROJECT_ROOT}/constitution/Constitution.md"; do
        [[ -f "${_lf}" ]] || continue   # genuinely absent on disk -> nothing to lose coverage of
        [[ -n "${_nt_seen[${_lf}]:-}" ]] || BASH_TEST_TRACE_UNCOVERED+="${_lf#"${PROJECT_ROOT}/"} "
    done

    # MARKER + CONTROL NEEDLE (§11.4.201(7)(b)): a "nothing moved" result is not
    # evidence until the instrument is PROVEN able to see a move through the
    # SAME path. The marker is created on the same filesystem as the corpus
    # (qa-results/ is gitignored — .gitignore:273) so no cross-filesystem
    # timestamp-granularity assumption is made; the needle then proves a file
    # written after the marker really does compare `-nt` on THIS filesystem.
    BASH_TEST_TRACE_DIR="${PROJECT_ROOT}/qa-results/.notrace"
    mkdir -p "${BASH_TEST_TRACE_DIR}" 2>/dev/null || BASH_TEST_TRACE_DIR="$(mktemp -d)"
    BASH_TEST_TRACE_MARKER="${BASH_TEST_TRACE_DIR}/marker"
    rm -f "${BASH_TEST_TRACE_MARKER}" "${BASH_TEST_TRACE_DIR}/needle"
    touch "${BASH_TEST_TRACE_MARKER}"
    touch "${BASH_TEST_TRACE_DIR}/needle"
    BASH_TEST_TRACE_NEEDLE_OK=0
    [[ "${BASH_TEST_TRACE_DIR}/needle" -nt "${BASH_TEST_TRACE_MARKER}" ]] && BASH_TEST_TRACE_NEEDLE_OK=1
    rm -f "${BASH_TEST_TRACE_DIR}/needle"
fi
if [[ -n "${BOBA_PREBUILD_NESTED:-}" ]]; then
    # Nested invocation (a test under this very invariant re-ran the gate).
    # Skipping here is what breaks the recursion — honest SKIP, never a PASS.
    echo "  SKIP: nested pre_build invocation (BOBA_PREBUILD_NESTED set) — recursion guard"
else
# tests/hooks/ ADDED 2026-08-21: the SAME orphan-guard class that stranded
# tests/pre_build/ recurred one directory over. Invariant 15 asserts a hooks
# test EXISTS, but existence is not execution — registration is not coverage
# (§11.4.226). MEASURED before the fix: this glob expanded to 27 suites, 0 of
# them under tests/hooks/, while 3 suites existed there (two authored minutes
# earlier for BOB-106/BOB-107, whose paired §1.1 mutations nothing would run).
for _bt in "${PROJECT_ROOT}"/tests/unit/test_*.sh "${PROJECT_ROOT}"/tests/pre_build/test_*.sh "${PROJECT_ROOT}"/tests/hooks/test_*.sh; do
    [[ -f "${_bt}" ]] || continue
    _btname="$(basename "${_bt}")"
    _skip=0
    # ${arr[@]+"${arr[@]}"} — safe expansion of a possibly-EMPTY array under
    # `set -u` (the quarantine is empty as of 2026-08-20).
    for _q in "${BASH_TEST_SELF_RECURSIVE[@]}" ${BASH_TEST_QUARANTINE[@]+"${BASH_TEST_QUARANTINE[@]}"}; do
        [[ "${_btname}" = "${_q}" ]] && { _skip=1; break; }
    done
    if [[ "${_skip}" -eq 1 ]]; then
        BASH_TEST_QUARANTINED=$((BASH_TEST_QUARANTINED + 1))
        continue
    fi
    BASH_TEST_RAN=$((BASH_TEST_RAN + 1))
    if ! BOBA_PREBUILD_NESTED=1 timeout 300 bash "${_bt}" >/dev/null 2>&1; then
        BASH_TEST_FAILED=$((BASH_TEST_FAILED + 1))
        BASH_TEST_FAILURES+=("${_btname}")
    fi
done
fi
if [[ -n "${BOBA_PREBUILD_NESTED:-}" ]]; then
    : # nested: neither pass nor fail counted, already reported as SKIP above
elif [[ "${BASH_TEST_RAN}" -eq 0 ]]; then
    # §11.4.201(6): a zero here is a FALSE-NULL (blind glob), never "all clean".
    fail "CM-BASH-UNIT-TESTS-EXECUTED: no tests/unit/test_*.sh, tests/pre_build/test_*.sh or tests/hooks/test_*.sh were executed — the glob is blind"
elif [[ "${BASH_TEST_FAILED}" -gt 0 ]]; then
    fail "CM-BASH-UNIT-TESTS-EXECUTED: ${BASH_TEST_FAILED}/${BASH_TEST_RAN} bash unit/pre_build test(s) FAILED"
    for _f in "${BASH_TEST_FAILURES[@]}"; do
        echo "        - ${_f}" >&2
    done
elif [[ "${#BASH_TEST_TRACE_CORPUS[@]}" -eq 0 ]]; then
    # §11.4.201(6): an empty corpus makes the scan return the SAME quiet zero a
    # genuinely clean tree returns. That is a FALSE-NULL, never a pass.
    fail "CM-BASH-UNIT-TESTS-EXECUTED: no-trace corpus is EMPTY — the tracked-file enumeration is blind, not a clean tree"
elif [[ -n "${BASH_TEST_TRACE_UNCOVERED}" ]]; then
    fail "CM-BASH-UNIT-TESTS-EXECUTED: no-trace corpus LOST coverage of: ${BASH_TEST_TRACE_UNCOVERED}"
    echo "        These paths were covered before the corpus widening; enumeration must not silently drop them." >&2
else
    # NO-TRACE assertion: any tracked file whose mtime moved while the suite ran
    # means a test wrote into the real tree — typically a plain `cp` restore
    # where `cp -p` was required.
    BASH_TEST_TRACE_VIOLATIONS=""
    BASH_TEST_TRACE_VIOLATION_N=0
    for _cf in ${BASH_TEST_TRACE_CORPUS[@]+"${BASH_TEST_TRACE_CORPUS[@]}"}; do
        [[ "${_cf}" -nt "${BASH_TEST_TRACE_MARKER}" ]] || continue
        # Regular files only. The submodule GITLINK entries `git ls-files` emits
        # are DIRECTORIES; a directory's mtime moves whenever any entry is
        # created inside it — including a gitignored temp file — which would be
        # a §11.4.201(1) false-positive refusal, not a real trace.
        [[ -f "${_cf}" ]] || continue
        BASH_TEST_TRACE_VIOLATION_N=$((BASH_TEST_TRACE_VIOLATION_N + 1))
        [[ "${BASH_TEST_TRACE_VIOLATION_N}" -le 20 ]] && BASH_TEST_TRACE_VIOLATIONS+="${_cf#"${PROJECT_ROOT}/"} "
    done
    if [[ "${BASH_TEST_TRACE_VIOLATION_N}" -gt 0 ]]; then
        # State the OBSERVATION, not an unproven cause (§11.4.6): this seam sees
        # the window, and cannot by itself distinguish a test's write from a
        # concurrent editor's. Both are real §11.4.84 quiescence violations at
        # the pre-build seam, and the two remedies differ — so name both.
        fail "CM-BASH-UNIT-TESTS-EXECUTED: ${BASH_TEST_TRACE_VIOLATION_N} tracked file(s) mtime-moved while the bash suite ran: ${BASH_TEST_TRACE_VIOLATIONS}"
        echo "        Either a suite restored with plain 'cp' where 'cp -p' is required (content AND" >&2
        echo "        mtime must be put back), or the tree was not quiescent — a concurrent editor" >&2
        echo "        wrote to it mid-run (§11.4.84). Re-run on a quiescent tree to tell them apart." >&2
    elif [[ "${BASH_TEST_TRACE_NEEDLE_OK}" -ne 1 ]]; then
        # The scan found nothing AND could not be proven able to see. Report the
        # blindness honestly instead of claiming a clean result (§11.4.6);
        # non-blocking per §11.4.234 — a coarse-granularity filesystem is a host
        # property, not a defect in this tree.
        pass "CM-BASH-UNIT-TESTS-EXECUTED: ${BASH_TEST_RAN} bash unit/pre_build test(s) green (${BASH_TEST_QUARANTINED} quarantined); no-trace DEGRADED — control needle unproven on this filesystem, result not trusted"
    else
        pass "CM-BASH-UNIT-TESTS-EXECUTED: ${BASH_TEST_RAN} bash unit/pre_build test(s) green (${BASH_TEST_QUARANTINED} quarantined), no-trace verified across ${#BASH_TEST_TRACE_CORPUS[@]} tracked paths (needle proven)"
    fi
fi
[[ -n "${BASH_TEST_TRACE_MARKER}" ]] && rm -f "${BASH_TEST_TRACE_MARKER}"
true   # keep the block's exit status clean for `set -e`

# ============================================================================
# UNIVERSAL CONSTITUTION GATES (§11.4.35 consumer wiring of the inherited
# constitution/scripts/gates/ family; §11.4.227(A) "an anchor's done state is
# its SEAM landing, not its TEXT landing")
# ============================================================================
# The constitution submodule ships ~78 universal, project-agnostic gate
# scripts. They are inherited BY REFERENCE (§11.4.28(B)/§11.4.177) — never
# copied — and each takes its project-specific scope as DATA (a --root, a
# --manifest, a --config), so the SAME gate serves every consuming project.
#
# WIRING DISCIPLINE (§11.4.201(1) false-positive-refusal is a FAIL-bluff, and
# a vacuous PASS is worse than no gate at all):
#   * A gate is wired here ONLY when it runs MEANINGFULLY against boba —
#     i.e. it PASSes on real evidence, FAILs on a real boba defect, or SKIPs
#     honestly with a stated reason (§11.4.3/§11.4.69).
#   * A gate whose consumer DATA boba cannot yet supply is NOT wired. Wiring
#     it would either refuse the build on a scope it was never given (a
#     §11.4.201(1) FAIL-bluff) or paint green over an empty manifest (a
#     §11.4 PASS-bluff at the metric layer). Those gates are enumerated,
#     with the exact data each needs, in docs/QA_DISCOVERY_LEDGER.md-adjacent
#     follow-up items rather than silently wired.
#   * SCOPE IS DATA. Several gates default to a scan root of ".." or "." —
#     correct for a single-repo consumer, wrong for boba, whose tree also
#     contains third-party vendored code under submodules/ (helixqa's
#     tools/opensource/** alone carries dozens of foreign CLAUDE.md/AGENTS.md
#     carriers and thousands of foreign test files). Every gate below is
#     therefore given boba's OWN first-party scope explicitly; a gate run at
#     the bare project root would report dozens of MISSING/FAIL lines about
#     code boba does not author (measured 2026-08-20: 57 false MISSING for
#     one propagation anchor alone).
#
# BLOCKING vs ADVISORY: a gate is BLOCKING when its failure would be a real
# defect in code boba owns. A gate whose subject lives upstream in the
# constitution submodule (which this repo consumes read-only and cannot fix)
# is ADVISORY — reported loudly, never the reason boba cannot build
# (§11.4.234 "the commit/push mechanism is ALWAYS unblocked"), matching the
# existing precedent of invariants 25 and 26.

CONST_GATES_DIR="${PROJECT_ROOT}/constitution/scripts/gates"
CONST_GATE_TIMEOUT="${CONST_GATE_TIMEOUT:-300}"

# run_const_gate <progress-label> <gate-name> <blocking|advisory> <script> [args...]
#
# Runs one inherited constitution gate and maps its exit code onto this
# script's pass/fail/skip vocabulary. Exit-code contract, uniform across the
# family and documented in every gate's own header:
#   0   -> PASS (or an honest SKIP, which the gate announces in its verdict)
#   1   -> the gate's invariant is violated
#   2   -> environment error OR the gate reporting itself BLIND (the
#          propagation engine returns 2 when its control needle fails). A
#          BLIND instrument's silence is NEVER evidence (§11.4.201(6)/(7)(b)),
#          so 2 is treated exactly as 1 — never as a pass.
#   124 -> exceeded the time budget; reported as an honest SKIP with the
#          budget named, never a silent pass.
run_const_gate() {
    local label="$1" gname="$2" mode="$3" script="$4"
    shift 4
    echo "[${label}] ${gname} -> constitution/scripts/gates/${script}"
    local gpath="${CONST_GATES_DIR}/${script}"
    if [[ ! -f "${gpath}" ]]; then
        # The constitution pointer predates this wiring. Honest SKIP for an
        # advisory gate; a BLOCKING gate whose script vanished is a real
        # regression of the inherited engine (§11.4.227(A) vanished-name rule).
        if [[ "${mode}" == "blocking" ]]; then
            fail "${gname}: gate script absent at constitution/scripts/gates/${script}"
        else
            echo "  SKIP: ${gname} — gate script absent at constitution/scripts/gates/${script} (§11.4.3 artifact_not_yet_built)"
        fi
        return 0
    fi
    local glog grc=0 verdict
    glog="$(mktemp)"
    timeout "${CONST_GATE_TIMEOUT}" bash "${gpath}" "$@" >"${glog}" 2>&1 || grc=$?
    verdict="$(grep -aE '^(✅|❌|⏭)|(PASS|FAIL|SKIP)' "${glog}" | tail -n1 || true)"
    [[ -n "${verdict}" ]] || verdict="$(tail -n1 "${glog}" || true)"
    case "${grc}" in
        0)
            # Discriminate an honest SKIP verdict from a PASS whose text merely
            # CONTAINS the token "SKIP" (the propagation family's
            # "7 POINTER-INHERITANCE-SKIP" summary is a PASS, not a skip) —
            # §11.4.201(7)(a) match structure, never substring.
            if printf '%s' "${verdict}" | grep -qE '^⏭|: SKIP'; then
                echo "  SKIP: ${gname} — ${verdict}"
            else
                pass "${gname}: ${verdict}"
            fi
            ;;
        124)
            echo "  SKIP: ${gname} — exceeded the ${CONST_GATE_TIMEOUT}s budget (§11.4.3; a timeout is never a silent pass)"
            ;;
        *)
            if [[ "${mode}" == "blocking" ]]; then
                fail "${gname}: exit ${grc} — ${verdict}"
                echo "        --- gate output (last 25 lines) ---"
                tail -n 25 "${glog}" | sed 's/^/        /'
                echo "        --- end ---"
            else
                echo "  WARN: ${gname} — exit ${grc} (ADVISORY, non-blocking per §11.4.234; see this invariant's block comment for why it is advisory)"
                echo "        --- gate output (last 15 lines) ---"
                tail -n 15 "${glog}" | sed 's/^/        /'
                echo "        --- end ---"
            fi
            ;;
    esac
    rm -f "${glog}"
    return 0
}

# --- Invariant 31: CM-COVENANT-PROPAGATION-BLOCK-INTEGRITY (§11.4.227(B)) ---
# The 17 CM-COVENANT-114-<N>-PROPAGATION gates that are NOT bound in the
# family's data pack (covenant_propagation_anchors.tsv) and therefore are not
# reachable through covenant_propagation_suite.sh. Each asserts §11.4.227(B)
# anchor-block integrity for its anchor across the §11.4.157 lockstep mirror
# set: exactly ONE block-start per anchor per carrier, byte-identical across
# the carriers that carry it, block-STARTS counted (never bare literals — a
# mid-body citation is a CARRIER, §11.4.201(7)(a)), and a BLIND control-needle
# result refused rather than trusted.
#
# SCOPE IS DATA (§11.4.35): the mirror set is constitution/{CLAUDE,AGENTS,
# QWEN,GEMINI}.md — the SAME scope boba's own invariant 21 already declares
# canonical, and explicitly NOT the boba project-root CLAUDE.md/AGENTS.md
# (which is a §11.4.35 POINTER-INHERITANCE consumer the engine skips
# honestly). Running these at the bare project root instead produces dozens
# of false MISSING lines against third-party vendored carriers under
# submodules/helixqa/tools/opensource/** and .worktrees/** — measured
# 2026-08-20: 57 false MISSING for anchor 11.4.199 alone. BLOCKING: all 17
# are green today at this scope, so a future red is a real regression of the
# governance corpus boba inherits.
echo "[31/49] CM-COVENANT-PROPAGATION-BLOCK-INTEGRITY: 17 pack-unbound anchors (§11.4.227(B))"
PROP_UNBOUND=(162 167 176 187 191 196 199 200 201 202 207 213 230 231 232 233 235)
PROP_OK=0; PROP_BAD=(); PROP_MISSING=0
for _anchor in "${PROP_UNBOUND[@]}"; do
    _pg="${CONST_GATES_DIR}/cm_covenant_114_${_anchor}_propagation.sh"
    if [[ ! -f "${_pg}" ]]; then
        PROP_MISSING=$((PROP_MISSING + 1))
        continue
    fi
    _prc=0
    timeout 120 bash "${_pg}" --root "${PROJECT_ROOT}/constitution" >/dev/null 2>&1 || _prc=$?
    if [[ "${_prc}" -eq 0 ]]; then
        PROP_OK=$((PROP_OK + 1))
    else
        PROP_BAD+=("11.4.${_anchor}(exit ${_prc})")
    fi
done
if [[ "${#PROP_BAD[@]}" -eq 0 ]] && [[ "${PROP_MISSING}" -eq 0 ]]; then
    pass "CM-COVENANT-PROPAGATION-BLOCK-INTEGRITY: ${PROP_OK}/${#PROP_UNBOUND[@]} anchors single-block-PRESENT + lockstep-identical across the constitution mirror set"
elif [[ "${#PROP_BAD[@]}" -eq 0 ]]; then
    # Scripts absent = the constitution pointer predates this wiring. Honest
    # SKIP-with-reason (§11.4.3/§11.4.69 artifact_not_yet_built), never a
    # silent pass and never a false refusal (§11.4.201(1)).
    echo "  SKIP: CM-COVENANT-PROPAGATION-BLOCK-INTEGRITY — ${PROP_MISSING}/${#PROP_UNBOUND[@]} wrapper(s) absent from this constitution pointer (${PROP_OK} of the present ones passed)"
else
    fail "CM-COVENANT-PROPAGATION-BLOCK-INTEGRITY: ${#PROP_BAD[@]} anchor(s) failed block-integrity: ${PROP_BAD[*]}"
fi

# --- Invariant 32: CM-COVENANT-PROPAGATION-SUITE (§11.4.227(B), ADVISORY) ---
# The data-pack-driven half of the same family, run in ONE shot through the
# inherited batch runner rather than hand-listing 30 script names here
# (§11.4.251 role-as-data-pack — the list lives in the constitution's TSV,
# not duplicated in this consumer).
#
# ADVISORY, not blocking: measured 2026-08-20, 27/30 are green and 3 are red
# for reasons that live UPSTREAM in the constitution submodule, which this
# repo consumes read-only and cannot fix —
#   CM-COVENANT-114-27-PROPAGATION   1 PRESENT / 3 MISSING
#   CM-COVENANT-114-255-PROPAGATION  0 PRESENT / 4 MISSING
#   CM-COVENANT-114-256-PROPAGATION  0 PRESENT / 4 MISSING
# §11.4.255/§11.4.256 are the anchors re-minted out of the known
# §11.4.140/§11.4.141 collision; their blocks have not landed in the mirror
# set. Blocking boba's build on an upstream governance gap would violate
# §11.4.234 (the mechanism is ALWAYS unblocked) while fixing nothing, so the
# suite reports loudly on every run and the 3 reds are tracked as owed
# upstream work. Promote to BLOCKING the moment the 3 land.
echo "[32/49] CM-COVENANT-PROPAGATION-SUITE: 30 pack-driven anchors (§11.4.227(B), ADVISORY)"
PROP_SUITE="${CONST_GATES_DIR}/covenant_propagation_suite.sh"
if [[ ! -f "${PROP_SUITE}" ]]; then
    echo "  SKIP: CM-COVENANT-PROPAGATION-SUITE — batch runner absent at constitution/scripts/gates/covenant_propagation_suite.sh (§11.4.3)"
else
    SUITE_LOG="$(mktemp)"
    SUITE_RC=0
    timeout "${CONST_GATE_TIMEOUT}" bash "${PROP_SUITE}" gates --root "${PROJECT_ROOT}/constitution" >"${SUITE_LOG}" 2>&1 || SUITE_RC=$?
    SUITE_SUMMARY="$(grep -a '^suite(gates):' "${SUITE_LOG}" | tail -n1 || true)"
    [[ -n "${SUITE_SUMMARY}" ]] || SUITE_SUMMARY="$(tail -n1 "${SUITE_LOG}" || true)"
    if [[ "${SUITE_RC}" -eq 0 ]]; then
        pass "CM-COVENANT-PROPAGATION-SUITE: ${SUITE_SUMMARY}"
    elif [[ "${SUITE_RC}" -eq 124 ]]; then
        echo "  SKIP: CM-COVENANT-PROPAGATION-SUITE — exceeded the ${CONST_GATE_TIMEOUT}s budget (§11.4.3)"
    else
        echo "  WARN: CM-COVENANT-PROPAGATION-SUITE — ${SUITE_SUMMARY} (ADVISORY, non-blocking per §11.4.234; subject is upstream in the constitution submodule)"
        grep -aE '^CM-COVENANT.*[[:space:]]+[1-9][0-9]*[[:space:]]' "${SUITE_LOG}" | sed 's/^/        /' | sed -n '1,10p'
    fi
    rm -f "${SUITE_LOG}"
fi

# --- Invariants 33-38: constitution-engine integrity gates (BLOCKING) ---
# Each asserts that a mechanism boba INHERITS BY REFERENCE (§11.4.28(B)/
# §11.4.177) is genuinely intact — not merely present. All six are green
# today, so a red is a real regression of the engine boba depends on. Their
# scope is the constitution submodule and every one of them resolves it from
# its own script location, so NO --root is passed (passing boba's project
# root would point them at a tree that does not contain their inputs and
# manufacture a §11.4.201(1) false refusal).
run_const_gate "33/49" "CM-CLI-AGENT-PLUGINS-WIRED"             blocking cm_cli_agent_plugins_wired.sh
run_const_gate "34/49" "CM-MULTITRACK-ENGINE-IN-CONSTITUTION"   blocking cm_multitrack_engine_in_constitution.sh
run_const_gate "35/49" "CM-SUBSYSTEM-SHORTCUTS"                 blocking cm_subsystem_shortcuts.sh
run_const_gate "36/49" "CM-REPORTING-DIRECTIVES"                blocking cm_reporting_directives.sh
run_const_gate "37/49" "CM-FEATURE-DIRECTIVE"                   blocking cm_feature_directive.sh
run_const_gate "38/49" "CM-GATE-LEDGER-RATCHET"                 blocking cm_gate_ledger_ratchet.sh

# --- Invariant 39: CM-DANGEROUS-COMBINATION-FAIL-CLOSED (§11.4.252, ADVISORY) ---
# Refuses fail-open shapes (swallowed exceptions, credentials defaulting to a
# literal) on code paths combining >= 2 dangerous capabilities.
#
# SCOPE IS DATA (§11.4.35): the gate's default scan root is ".." — for boba
# that would sweep submodules/helixqa/tools/opensource/** and every other
# vendored third-party tree. boba's first-party production source roots are
# enumerated here from CLAUDE.md's own Architecture section; each is scanned
# separately so the scope is an INCLUSION list (auditable) rather than an
# exclusion list (a §11.4.224(E) fence boba has not declared).
#
# ADVISORY, not blocking: the first run (2026-08-20) surfaced 36 real hits —
# 4 under download-proxy/src/ and 32 under plugins/. They are a genuine
# §11.4.252 backlog, but they are a MIXED set: some are real broad
# `except Exception: pass` fail-opens (e.g. plugins/env_loader.py:30, which
# swallows every error while populating os.environ from .env), while others
# are narrow, correct cleanup idioms the gate cannot yet distinguish
# (`except asyncio.CancelledError: pass` after task.cancel();
# `except OSError: pass` around an fsync inside a block that re-raises) and
# which §11.4.252 itself exempts as graceful degradation rather than a
# >=2-capability dangerous combination. Blocking the build on an un-triaged
# mix would be a §11.4.201(1) false-positive refusal; every hit is instead
# printed on every run so none of it is silenced. Promote to BLOCKING once
# each hit is triaged (fix the real fail-opens; declare the benign ones under
# a §11.4.224(E)-style checked-in fence, or land the upstream refinement).
echo "[39/49] CM-DANGEROUS-COMBINATION-FAIL-CLOSED: fail-open scan over first-party source (§11.4.252, ADVISORY)"
DANGER_GATE="${CONST_GATES_DIR}/cm_dangerous_combination_fail_closed.sh"
if [[ ! -f "${DANGER_GATE}" ]]; then
    echo "  SKIP: CM-DANGEROUS-COMBINATION-FAIL-CLOSED — gate script absent (§11.4.3)"
else
    DANGER_ROOTS=(download-proxy/src plugins scripts qBitTorrent-go frontend/src)
    DANGER_HITS=0; DANGER_SCANNED=0; DANGER_DETAIL=()
    for _dr in "${DANGER_ROOTS[@]}"; do
        [[ -d "${PROJECT_ROOT}/${_dr}" ]] || continue
        DANGER_SCANNED=$((DANGER_SCANNED + 1))
        _dlog="$(mktemp)"; _drc=0
        timeout "${CONST_GATE_TIMEOUT}" bash "${DANGER_GATE}" --root "${PROJECT_ROOT}/${_dr}" --quiet >"${_dlog}" 2>&1 || _drc=$?
        if [[ "${_drc}" -ne 0 ]]; then
            # A COUNT IS A LEAD; THE LINES ARE THE FINDINGS (§11.4.194(6)(b)).
            # This previously counted every line starting with the failure
            # marker — including the gate's OWN SUMMARY line, which also starts
            # with it ("FAIL — 26 fail-open anti-pattern hit(s) found"). Each
            # failing root therefore contributed exactly ONE phantom hit, and
            # the reported total read 38 when the truth was 36.
            #
            # A finding line NAMES A LOCATION (" at <path>:<line>"); the summary
            # never does. Matching that structure, rather than the marker glyph,
            # is the §11.4.201(9) field-identity fix: a summary is not a finding.
            _dn="$(grep -acE '^❌.* at .*:[0-9]+' "${_dlog}" || true)"
            DANGER_HITS=$((DANGER_HITS + ${_dn:-0}))
            DANGER_DETAIL+=("${_dr}:${_dn:-?}")
            grep -aE '^❌.* at .*:[0-9]+' "${_dlog}" | sed 's/^/        /' | sed -n '1,6p'
        fi
        rm -f "${_dlog}"
    done
    if [[ "${DANGER_HITS}" -eq 0 ]]; then
        pass "CM-DANGEROUS-COMBINATION-FAIL-CLOSED: no fail-open anti-pattern across ${DANGER_SCANNED} first-party source root(s)"
    else
        echo "  WARN: CM-DANGEROUS-COMBINATION-FAIL-CLOSED — ${DANGER_HITS} fail-open hit(s) across ${DANGER_DETAIL[*]} (ADVISORY, non-blocking per §11.4.234; un-triaged §11.4.252 backlog, see the block comment)"
    fi
fi

# --- Invariant 40: CM-ORACLE-STRATEGY-NAMED-AND-INDEPENDENT (§11.4.245, ADVISORY) ---
# Every test function must NAME its oracle strategy from the §11.4.245 closed
# set, so "the test agrees with the code" cannot masquerade as coverage.
#
# SCOPE IS DATA (§11.4.35): scoped to boba's own tests/ tree — the gate's
# default root ("..") would sweep every vendored third-party test suite in
# submodules/.
#
# ADVISORY, not blocking: the first run (2026-08-20) reported 4475 boba test
# functions with no oracle annotation. That is a real, whole-corpus §11.4.245
# gap — but retro-fitting 4475 annotations is a BROWNFIELD ADOPTION question,
# and §11.4.224(E) is explicit that the adoption ratchet for a pre-existing
# corpus is an OPERATOR decision (§11.4.66), never one an agent invents.
# Turning this blocking today would make the build unreachable, which
# §11.4.234 forbids. The count is printed on every run so the gap cannot be
# forgotten; promote to BLOCKING once the operator picks an adoption path
# (immediate floor / monotone-decrease ratchet / changed-tests-only).
run_const_gate "40/49" "CM-ORACLE-STRATEGY-NAMED-AND-INDEPENDENT" advisory \
    cm_oracle_strategy_named_and_independent.sh --root "${PROJECT_ROOT}/tests" --quiet

# --- Invariant 41: CM-OPENDESIGN-UI-SYSTEM (§11.4.162/§11.4.190, ADVISORY) ---
# SCOPE IS DATA (§11.4.35): boba's UI surface is the Angular app under
# frontend/. The gate's default theme/token globs do not match boba's layout,
# so at the bare project root it SKIPs with "no UI surface detected" — an
# honest skip, but a blind one. The globs below are boba's real style
# sources, verified present: frontend/src/styles.scss and
# frontend/src/app/**/*.scss.
#
# ADVISORY, not blocking: given that scope the gate reports 3 of 4 sub-checks
# failing (hardcoded hex in theme sources, no design-token artifact, no
# visual-regression tests). That is a genuine §11.4.162/§11.4.190 adoption
# gap in boba's frontend, not a build defect, and closing it is design work
# (an OpenDesign token file + visual-regression suite) rather than something
# the pre-build seam can demand today.
echo "[41/49] CM-OPENDESIGN-UI-SYSTEM: Angular frontend design-system audit (§11.4.162, ADVISORY)"
OD_GATE="${CONST_GATES_DIR}/cm_opendesign_ui_system.sh"
if [[ ! -d "${PROJECT_ROOT}/frontend" ]]; then
    echo "  SKIP: CM-OPENDESIGN-UI-SYSTEM — no frontend/ UI surface in this checkout (§11.4.3)"
elif [[ ! -f "${OD_GATE}" ]]; then
    echo "  SKIP: CM-OPENDESIGN-UI-SYSTEM — gate script absent (§11.4.3)"
else
    OD_LOG="$(mktemp)"; OD_RC=0
    # The scope globs are consumer DATA (§11.4.35) and must reach the gate's
    # OWN environment, so they are handed over with `env` rather than as a
    # prefix on a shell-function call (whose assignment scoping is a bash
    # quirk, not a contract).
    env OD_THEME_GLOBS="src/styles.scss src/app/*.scss src/app/**/*.scss" \
        OD_TOKEN_GLOBS="src/tokens/* design-tokens.json tokens.css" \
        timeout "${CONST_GATE_TIMEOUT}" bash "${OD_GATE}" --root "${PROJECT_ROOT}/frontend" \
        >"${OD_LOG}" 2>&1 || OD_RC=$?
    OD_VERDICT="$(grep -aE '^(✅|❌|⏭)' "${OD_LOG}" | tail -n1 || true)"
    if [[ "${OD_RC}" -eq 0 ]]; then
        if printf '%s' "${OD_VERDICT}" | grep -qE '^⏭|: SKIP'; then
            echo "  SKIP: CM-OPENDESIGN-UI-SYSTEM — ${OD_VERDICT}"
        else
            pass "CM-OPENDESIGN-UI-SYSTEM: ${OD_VERDICT}"
        fi
    elif [[ "${OD_RC}" -eq 124 ]]; then
        echo "  SKIP: CM-OPENDESIGN-UI-SYSTEM — exceeded the ${CONST_GATE_TIMEOUT}s budget (§11.4.3)"
    else
        echo "  WARN: CM-OPENDESIGN-UI-SYSTEM — exit ${OD_RC} (ADVISORY, non-blocking per §11.4.234; §11.4.162/§11.4.190 frontend adoption gap)"
        grep -aE '^(✅|❌)' "${OD_LOG}" | sed 's/^/        /' | sed -n '1,8p'
    fi
    rm -f "${OD_LOG}"
fi

# --- Invariants 42-43: consumer-config gates (BLOCKING, honest SKIP today) ---
# Both are wired BLOCKING and both currently SKIP-with-reason
# (feature_disabled_by_config, §11.4.3/§11.4.69) because boba has not yet
# declared their consumer marker/ledger config. An honest SKIP is a valid
# wired state (§11.4.3); what they must never do is pass silently, and they
# do not — each names the exact config it is missing. They become live the
# moment boba lands the config:
#   42 CM-BUILD-ON-SOURCE-PROVEN-NOT-TEST-SIDE (§11.4.235(A)) needs a marker
#      config binding source_review_go / build_launched /
#      test_instrumentation_blocking to real marker paths.
#   43 CM-VERSION-INCREMENT-ON-DEPLOY (§11.4.235(B)) needs an append-only
#      deploy ledger TSV of <version_id><TAB><artifact_fingerprint> rows.
run_const_gate "42/49" "CM-BUILD-ON-SOURCE-PROVEN-NOT-TEST-SIDE" blocking cm_build_on_source_proven_not_test_side.sh
run_const_gate "43/49" "CM-VERSION-INCREMENT-ON-DEPLOY"          blocking cm_version_increment_on_deploy.sh

# --- Invariant 44: CM-HEALTHCHECK-COVERS-SERVED-PORTS (§11.4.201/§11.4.254) ---
# Every container healthcheck must probe EVERY port its service actually
# serves. Retroactive catcher for BOB-138: `download-proxy` serves BOTH 7186
# (proxy) and 7187 (merge service) from ONE process, but its healthcheck
# probed only 7186 — so the container reported "Up 4 hours (healthy)" while
# the merge service had been dead ~2h (7186 -> HTTP 200 in 0.096s, 7187 ->
# HTTP 000 after 6s). A healthcheck that cannot observe the failure it exists
# to catch is a §11.4.201(6) FALSE-NULL wearing a green badge.
#
# SCOPE IS DATA (§11.4.35): config/served_ports.yaml declares the per-service
# served-port set the gate cross-checks against docker-compose.yml.
#
# BLOCKING: this is a real availability-integrity defect class in code boba
# owns (§11.4.239 critical-invariant work class — availability of the primary
# user-facing capability), not a documentation-freshness signal. Verified
# live 2026-08-20: exit 0, 5 services, download-proxy correctly resolved to
# [7186, 7187]. The gate deliberately FAILs — never SKIPs — when it checked
# ZERO services or when python3+PyYAML is unavailable, because a quiet zero
# from a blind instrument is not a clean tree (§11.4.201(6)/(7)(b)).
echo "[44/49] CM-HEALTHCHECK-COVERS-SERVED-PORTS: healthchecks probe every served port (§11.4.254, BOB-138)"
HC_GATE="${PROJECT_ROOT}/scripts/pre_build/check_cm_healthcheck_covers_served_ports.sh"
if [[ ! -f "${HC_GATE}" ]]; then
    fail "CM-HEALTHCHECK-COVERS-SERVED-PORTS: gate script missing at scripts/pre_build/check_cm_healthcheck_covers_served_ports.sh"
else
    HC_LOG="$(mktemp)"; HC_RC=0
    timeout "${CONST_GATE_TIMEOUT}" bash "${HC_GATE}" >"${HC_LOG}" 2>&1 || HC_RC=$?
    if [[ "${HC_RC}" -eq 0 ]]; then
        pass "CM-HEALTHCHECK-COVERS-SERVED-PORTS: $(tail -n1 "${HC_LOG}" || true)"
    elif [[ "${HC_RC}" -eq 124 ]]; then
        fail "CM-HEALTHCHECK-COVERS-SERVED-PORTS: exceeded the ${CONST_GATE_TIMEOUT}s budget (a timeout is not a pass)"
    else
        fail "CM-HEALTHCHECK-COVERS-SERVED-PORTS: exit ${HC_RC} — a served port is unprobed by its healthcheck"
        echo "        --- gate output ---"
        sed 's/^/        /' "${HC_LOG}"
        echo "        --- end ---"
    fi
    rm -f "${HC_LOG}"
fi

# --- Invariant 33: CM-OWNERSHIP-INVARIANTS (§11.4.201, FR-011 of feature 002) ---
# Refuses a tree where the operator-owned-writes fix has been weakened or
# reverted. Under ROOTLESS podman container uid N maps to host 100000+N-1, so a
# linuxserver service running its app at PUID=1000 writes files at host uid
# 100999 — an identity the operator does not have, which is the defect that
# forced a manual chown after every download. Container uid 0 maps to the HOST
# OPERATOR and grants no host privilege, so PUID=0 is the fix.
#
# THE INVARIANT NUMBER IS THE PART THAT ROTS. This block previously
# explained why slot 45 was free under a denominator of 44 — a statement
# that was already false by the time it was committed, because the same
# commit renumbered the file to /46. See the two-syntax census note at the
# CM-PLUGIN-COUNT block for why counting labels here is easy to get wrong.
# BLOCKING.
echo "[45/49] CM-OWNERSHIP-INVARIANTS: operator-owned writes not reverted (§11.4.201, FR-011)"
OWNINV_GATE="${PROJECT_ROOT}/scripts/pre_build/check_cm_ownership_invariants.sh"
if [[ ! -x "${OWNINV_GATE}" ]]; then
    fail "CM-OWNERSHIP-INVARIANTS: gate script missing or not executable at scripts/pre_build/check_cm_ownership_invariants.sh"
else
    OWNINV_LOG="$(mktemp)"
    OWNINV_EXIT=0
    bash "${OWNINV_GATE}" >"${OWNINV_LOG}" 2>&1 || OWNINV_EXIT=$?
    if [[ "${OWNINV_EXIT}" -eq 0 ]]; then
        pass "CM-OWNERSHIP-INVARIANTS: $(tail -n1 "${OWNINV_LOG}")"
    else
        fail "CM-OWNERSHIP-INVARIANTS: ownership invariant violated (exit ${OWNINV_EXIT})"
        echo "        --- gate output ---"
        sed 's/^/        /' "${OWNINV_LOG}"
        echo "        --- end ---"
    fi
    rm -f "${OWNINV_LOG}"
fi

# --- Invariant 46: CM-PLUGIN-COUNT (BOB-149) ---
# Refuses a tree where a documented managed-plugin count disagrees with the
# count derived from the authoritative source (install-plugin.sh's PLUGINS=()
# array). BOB-149: the count had drifted three ways — 43 in the constitution,
# 42 in CLAUDE.md, 48 in the README badge — and nothing in the repository
# equalled 48 at all (it was an April-2026 count of plugins/*.py FILES,
# relabelled "plugin engines" and never updated after a community/ reorg).
#
# WHY THE COUNT IS LOAD-BEARING (a number is not worth a gate merely because
# it is written down — this one is depended on in three places):
#   - constitution Principle II enumerates the roster BY NAME and asserts its
#     size, so a drifted count contradicts governance;
#   - §11.4.86 requires the derived docs to re-sync whenever that PLUGINS=()
#     array changes — a rule with no mechanical enforcement is exactly the
#     §11.4.227 prose-not-seam gap this invariant closes;
#   - release checklist step 3 ("every managed plugin (43 entries per
#     Principle II) MUST be installed") gates a RELEASE on the number.
# CLAUDE.md is additionally what agents read as project instruction, so a
# wrong number there is the one most likely to propagate into new work.
#
# SLOT 46 — and the story of how three agents got this wrong in a row, kept
# here because it is the most useful comment in this file.
#
# THIS FILE LABELS ITS INVARIANTS IN TWO SYNTAXES:
#     echo "[N/NN] CM-FOO: ..."          <- the obvious one
#     run_const_gate "N/NN" "CM-BAR"     <- easy to miss entirely
#
# A `grep -oE '\[[0-9]+/NN\]'` sees only the first. Doing that reported ~37
# labels and a comfortable set of "free" numbers at 33-38/40/42/43. All of it
# was wrong: run_const_gate holds exactly those numbers, the union covered
# 1..44 with NO free slot, and slot 33 was already claimed TWICE.
#
# THE INSTRUMENT HAD BEEN CONTROL-NEEDLED, which is why this is worth writing
# down. A synthetic label was injected, the count moved, it was removed, the
# check passed. But the needle was an ECHO-FORM label, so it certified only
# that the query could see the ECHO FORM. A control needle certifies the QUERY
# CLASS it shares load-bearing features with — never "the file". Three
# independent agents hit this same false-null before it was caught.
#
# The file is now renumbered across BOTH forms: 46 labels, 46 distinct,
# contiguous 1..46, zero duplicates, and the denominator finally tells the
# truth. If you add an invariant, take 47 and bump every denominator in BOTH
# syntaxes — and COUNT BOTH FORMS before you believe any slot is free.
# BLOCKING.
echo "[46/49] CM-PLUGIN-COUNT: documented plugin counts match their derivation (BOB-149)"
PLUGINCNT_GATE="${PROJECT_ROOT}/scripts/pre_build/check_cm_plugin_count.sh"
if [[ ! -x "${PLUGINCNT_GATE}" ]]; then
    fail "CM-PLUGIN-COUNT: gate script missing or not executable at scripts/pre_build/check_cm_plugin_count.sh"
else
    PLUGINCNT_LOG="$(mktemp)"
    PLUGINCNT_EXIT=0
    bash "${PLUGINCNT_GATE}" >"${PLUGINCNT_LOG}" 2>&1 || PLUGINCNT_EXIT=$?
    if [[ "${PLUGINCNT_EXIT}" -eq 0 ]]; then
        pass "CM-PLUGIN-COUNT: $(tail -n1 "${PLUGINCNT_LOG}")"
    else
        fail "CM-PLUGIN-COUNT: documented plugin count(s) diverge from the derivation (exit ${PLUGINCNT_EXIT})"
        echo "        --- gate output ---"
        sed 's/^/        /' "${PLUGINCNT_LOG}"
        echo "        --- end ---"
    fi
    rm -f "${PLUGINCNT_LOG}"
fi


# --- Invariant 47: CM-GO-TOOLCHAIN-MATCHES-BUILDER (BOB-153) ---
# The Go profile could not build AT ALL: qBitTorrent-go/go.mod declared
# `go 1.26.2` while the Dockerfile built `FROM golang:1.23-alpine`. Both values
# entered in the SAME commit (4002c57, 2026-04-22) — never a drift, born
# divergent, and for four months nothing compared them.
#
# The gate asserts builder >= directive, NOT string equality. Equality would
# refuse a NEWER builder, which is a §11.4.201(1) false-positive refusal.
# BLOCKING.
echo "[47/49] CM-GO-TOOLCHAIN-MATCHES-BUILDER: Dockerfile builder satisfies go.mod (BOB-153)"
GOTC_GATE="${PROJECT_ROOT}/scripts/pre_build/check_cm_go_toolchain_matches_builder.sh"
if [[ ! -x "${GOTC_GATE}" ]]; then
    fail "CM-GO-TOOLCHAIN-MATCHES-BUILDER: gate script missing or not executable"
else
    GOTC_LOG="$(mktemp)"; GOTC_EXIT=0
    bash "${GOTC_GATE}" >"${GOTC_LOG}" 2>&1 || GOTC_EXIT=$?
    if [[ "${GOTC_EXIT}" -eq 0 ]]; then
        pass "CM-GO-TOOLCHAIN-MATCHES-BUILDER: $(tail -n1 "${GOTC_LOG}")"
    else
        fail "CM-GO-TOOLCHAIN-MATCHES-BUILDER: builder cannot satisfy the go directive (exit ${GOTC_EXIT})"
        echo "        --- gate output ---"; sed 's/^/        /' "${GOTC_LOG}"; echo "        --- end ---"
    fi
    rm -f "${GOTC_LOG}"
fi

# --- Invariant 48: CM-RUNTIME-DEPS-PARITY (BOB-154) ---
# The test stack and production were not the same stack: the venv ran CPython
# 3.14.6 while the container runs 3.12.13, plus 7 package divergences. The
# container pip-installs on EVERY start from unpinned floors, so the set was a
# function of the install date and was REGENERATED differently on each restart.
#
# Honest SKIP when the stack is down (§11.4.3) — a stopped stack is a legitimate
# state, not evidence of drift. The skip is DISCRIMINATED from a pass below,
# because reporting a skip as a pass is the false-null this gate exists to
# prevent. BLOCKING otherwise.
echo "[48/49] CM-RUNTIME-DEPS-PARITY: test stack and production run the same deps (BOB-154)"
DEPSPARITY_GATE="${PROJECT_ROOT}/scripts/pre_build/check_cm_runtime_deps_parity.sh"
if [[ ! -x "${DEPSPARITY_GATE}" ]]; then
    fail "CM-RUNTIME-DEPS-PARITY: gate script missing or not executable"
else
    DEPSPARITY_LOG="$(mktemp)"; DEPSPARITY_EXIT=0
    bash "${DEPSPARITY_GATE}" >"${DEPSPARITY_LOG}" 2>&1 || DEPSPARITY_EXIT=$?
    DEPSPARITY_VERDICT="$(tail -n1 "${DEPSPARITY_LOG}")"
    if [[ "${DEPSPARITY_EXIT}" -eq 0 ]]; then
        if printf '%s' "${DEPSPARITY_VERDICT}" | grep -q '^SKIP('; then
            echo "  SKIP: CM-RUNTIME-DEPS-PARITY — ${DEPSPARITY_VERDICT}"
        else
            pass "CM-RUNTIME-DEPS-PARITY: ${DEPSPARITY_VERDICT}"
        fi
    else
        fail "CM-RUNTIME-DEPS-PARITY: the test stack and production are not the same stack (exit ${DEPSPARITY_EXIT})"
        echo "        --- gate output ---"; sed 's/^/        /' "${DEPSPARITY_LOG}"; echo "        --- end ---"
    fi
    rm -f "${DEPSPARITY_LOG}"
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

# ---------------------------------------------------------------------------
echo "[49/49] CM-CLOSURE-SEAM-BINDS: done-but-open rows found mechanically (§11.4.226)"
# WHY THIS IS WIRED HERE (BOB-136 acceptance (c)).
#
# The gate itself has existed and worked for some time, but NOTHING invoked it:
# a repo-wide grep found exactly one wired caller, and that caller runs the
# gate's --message COMMIT-SEAM mode, which is monotone by design and
# structurally CANNOT see a past merged commit. So the sweep half — the half
# acceptance (c) actually specifies, "done-but-open rows are found mechanically
# rather than by a human noticing" — ran only when a human typed it.
#
# That is §11.4.196(F) configured-is-not-in-use and §11.4.227 seam-landing-not-
# text-landing: a guard with no execution seam is not standing detection
# pressure (§11.4.226), however correct its logic.
#
# WHY IT IS SAFE TO WIRE NOW, stated as a measured fact rather than a hope: the
# row's own body gave the blocker as "would break the build immediately on the
# pre-existing backlog". That blocker is FALSIFIED — the backlog is 0. Measured
# live this session: "CHECK A closure seam .......... PASS (0 stale rows, 0 untracked ids)".
# The one row it previously reported (BOB-120) was a §11.4.201(1) FALSE POSITIVE
# on a gerund carrier, fixed at the detector rather than by exempting the row.
if [[ -x "${PROJECT_ROOT}/scripts/pre_build/check_cm_closure_seam_binds.sh" ]]; then
    if bash "${PROJECT_ROOT}/scripts/pre_build/check_cm_closure_seam_binds.sh"; then
        pass "CM-CLOSURE-SEAM-BINDS: no stale rows, no flagless-diff callers"
    else
        fail "CM-CLOSURE-SEAM-BINDS: a done-claiming commit references a non-terminal row (or a flagless diff caller exists)"
    fi
else
    # §11.4.3 honest SKIP — never a silent pass.
    echo "  SKIP: scripts/pre_build/check_cm_closure_seam_binds.sh absent or not executable"
fi

echo
echo "=== Result: ${PASS_COUNT} passed, ${FAIL_COUNT} failed ==="

if [[ "${FAIL_COUNT}" -gt 0 ]]; then
    exit 1
fi
exit 0
