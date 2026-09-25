#!/usr/bin/env bash
# test_bob143_worktrees_exclude_scope.sh — BOB-143 §1.1 paired-mutation proof
# (§11.4.115 / §11.4.224(E) / §11.4.201(1)/(6)/(7)(b) / §11.4.251)
#
# PURPOSE
#   BOB-143: `.worktrees/` holds ORPHANED `git worktree` scratch checkouts
#   (the originally-measured ci-split-workflows/ + completion-initiative-
#   phase-0/, 46M total) whose `.git` pointer targets a gitdir that no longer
#   exists, so git cannot resolve their HEAD/branch/status. §11.4.122/
#   §11.4.124/§11.4.101 forbid deleting unprovable-provenance work
#   autonomously, so BOB-143's own text names the cheaper mitigation:
#   option (b), a checked-in §11.4.224(E)-fenced exclusion-list entry. This
#   test proves that entry — config/covenant_propagation_exclusions.tsv,
#   read by constitution/scripts/gates/lib/covenant_propagation_engine.sh —
#   is genuinely load-bearing, in BOTH directions, for BOTH code paths that
#   read it (the single-gate engine directly, AND
#   covenant_propagation_suite.sh's own separate carrier-precompute `find`,
#   which is the code path scripts/verify-all-constitution-rules.sh — boba's
#   §11.4.32 sweep, the exact instrument BOB-143 measured — actually drives).
#
#   It also REGRESSION-GUARDS the other half of BOB-143 that measurement
#   already showed fixed (commit c0ea01c, `_BOB143_SWEEP_EXCLUDE` in
#   scripts/verify-all-constitution-rules.sh): the CM-TEST-MOCK-PID-EXPLICIT-
#   INT / CM-ORACLE-STRATEGY-NAMED-AND-INDEPENDENT / CM-KILLPG-PGID-GUARD /
#   CM-DANGEROUS-COMBINATION-FAIL-CLOSED exclude exports must still name
#   `.worktrees`. TDD (§11.4.43/§11.4.115/§11.4.224): this meta-test is
#   authored AFTER config/covenant_propagation_exclusions.tsv (the fix) but
#   its baseline (no-exclusions) run was observed RED first (both the probe
#   and the control needle reported MISSING, exactly BOB-143's measured
#   shape) — see docs/qa/BOB-143/closure_evidence_20260925.md for the
#   captured RED transcript that predates this file landing.
#
# WHAT THIS ASSERTS (the oracle — §11.4.245)
#   Strategy: METAMORPHIC + INVARIANT, with explicit control needles, mirroring
#   tests/pre_build/test_bob152_vendored_exclude_scope.sh (the proven shape
#   for this exact exclude-scope class). Two carrier files — a PROBE under a
#   `.worktrees/` prefix (dot-leading, the exact name the exclusion targets)
#   and a CONTROL under a sibling `worktrees/` prefix (NO leading dot — a
#   deliberately similar but genuinely different name) — both deliberately
#   MISSING the anchor block under test, so BOTH are real, detectable
#   MISSING findings absent any exclusion. A real, root-level carrier
#   carrying a CORRECT block for the same anchor sits alongside them so the
#   fixture is never a zero-carrier BLIND run (§11.4.201(6)).
#
# INSTRUMENT VIABILITY (§11.4.201(7)(b) / §11.4.273)
#   The baseline (no-exclusions-file) run is the control needle for every
#   probe: if the PROBE is not seen there, the harness/engine combination is
#   blind to `.worktrees`-rooted carriers and any later "excluded" verdict is
#   not evidence of the fix — it would just be blindness. The script ABORTS
#   (exit 3) rather than reporting a false PASS on the exclude behaviour.
#
# EXIT CODES
#   0  PASS  — for every code path checked: .worktrees/-rooted probe excluded
#              AND worktrees/-rooted (no-dot) control still caught, with the
#              baseline proving both were genuinely detectable pre-exclude,
#              AND the MOCK_PID/ORACLE/KILLPG/DANGEROUS_COMBO wiring still
#              names .worktrees.
#   1  FAIL  — the exclude did not behave as BOB-143 requires somewhere.
#   3  ABORT — instrument blind / harness precondition unmet (NOT a verdict
#              on BOB-143 itself).
#
# SIDE EFFECTS: none outside its own mktemp -d, removed on exit. Never
# touches the real .worktrees/ (if present) or config/covenant_propagation_
# exclusions.tsv — it only READS the latter.
# DEPENDENCIES: bash, find, grep, sed, mktemp, the constitution submodule's
# covenant_propagation_engine.sh + covenant_propagation_suite.sh.
set -uo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
GATES_DIR="${BOB143_GATES_DIR:-${PROJECT_ROOT}/constitution/scripts/gates}"
SUITE="${GATES_DIR}/covenant_propagation_suite.sh"
SWEEP="${BOB143_SWEEP:-${PROJECT_ROOT}/scripts/verify-all-constitution-rules.sh}"
EXCL_FILE="${PROJECT_ROOT}/config/covenant_propagation_exclusions.tsv"

abort() { echo "ABORT: $*" >&2; exit 3; }
overall_fail=0

echo "== BOB-143 .worktrees/ exclude scope proof =="
echo "gates dir: ${GATES_DIR}"
echo "exclusions file: ${EXCL_FILE}"
[[ -f "${SUITE}" ]] || abort "covenant_propagation_suite.sh absent: ${SUITE}"
[[ -f "${EXCL_FILE}" ]] || abort "the fix (config/covenant_propagation_exclusions.tsv) is absent — nothing to prove"

# --- 1. The checked-in exclusion row must be well-formed, bound to the -----
#        single source of truth (§11.4.251), never hand-typed here.
_worktrees_rows="$(awk -F'\t' '/^#/{next} $1=="*/.worktrees"{print}' "${EXCL_FILE}")"
_worktrees_row_count="$(printf '%s\n' "${_worktrees_rows}" | grep -c . || true)"
[[ "${_worktrees_row_count}" == "1" ]] || abort "expected exactly 1 '*/.worktrees' row in ${EXCL_FILE}, found ${_worktrees_row_count}"
_wt_glob="$(printf '%s' "${_worktrees_rows}" | cut -f1)"
_wt_class="$(printf '%s' "${_worktrees_rows}" | cut -f2)"
_wt_just="$(printf '%s' "${_worktrees_rows}" | cut -f3)"
[[ "${_wt_glob}" == "*/.worktrees" ]] || abort "glob is not '*/.worktrees' (got: ${_wt_glob})"
case "${_wt_class}" in
    vendored-third-party|generated-code|non-shipping-fixtures|filename-collision) ;;
    *) abort "class '${_wt_class}' is outside the engine's closed set" ;;
esac
[[ -n "${_wt_just}" ]] || abort "the .worktrees row carries no justification"
echo "row confirmed: ${_wt_glob}	${_wt_class}	<justification, ${#_wt_just} chars>"

# --- 2. Regression-guard the ALREADY-FIXED half (commit c0ea01c): the ------
#        sweep's own MOCK_PID/ORACLE/KILLPG/DANGEROUS_COMBO excludes must
#        still name .worktrees. Bound to the sweep script itself, never
#        hand-copied (§11.4.251).
if [[ -f "${SWEEP}" ]]; then
    _base_line_count="$(grep -cE '^_BOB143_SWEEP_EXCLUDE=' "${SWEEP}" || true)"
    [[ "${_base_line_count}" == "1" ]] || abort "expected exactly 1 _BOB143_SWEEP_EXCLUDE= assignment in ${SWEEP}, found ${_base_line_count}"
    _base_exclude="$(sed -n 's/^_BOB143_SWEEP_EXCLUDE="\(.*\)"$/\1/p' "${SWEEP}")"
    case " ${_base_exclude} " in
        *" .worktrees "*) : ;;
        *) abort "_BOB143_SWEEP_EXCLUDE no longer names .worktrees (got: ${_base_exclude}) — the already-measured-fixed half of BOB-143 regressed" ;;
    esac
    echo "sweep wiring confirmed: _BOB143_SWEEP_EXCLUDE still names .worktrees (feeds MOCK_PID/ORACLE/KILLPG/DANGEROUS_COMBO_EXCLUDE)"
else
    echo "NOTE: sweep script not found at ${SWEEP} — skipping the already-fixed-half regression guard (not this test's fix to make)"
fi

# --- 3. Hermetic fixture builder ---------------------------------------------
FIX="$(mktemp -d)"; trap 'rm -rf "${FIX}"' EXIT

# build_fixture <subroot> — a real correct carrier at root (so discovery is
# never zero-carrier §11.4.201(6)) plus a PROBE under .worktrees/ and a
# CONTROL under worktrees/ (no dot), both deliberately missing anchor 230's
# block. Anchor 11.4.230 chosen only because its wrapper exists and is
# stable; the engine is identical for every anchor (§11.4.251 — one code
# copy), so this is a representative, not an exhaustive, proof.
build_fixture() {
    local _root="$1"
    rm -rf "${_root}"
    mkdir -p "${_root}/.worktrees/bob143_probe" "${_root}/worktrees/bob143_control"
    printf '%s\n' \
        '**§11.4.230 — Parallelized-pipeline methodology: real correct block for the fixture root carrier.**' \
        > "${_root}/CLAUDE.md"
    printf 'Stale orphaned .git-worktree checkout copy. No anchor block here on purpose (BOB-143 probe).\n' \
        > "${_root}/.worktrees/bob143_probe/CLAUDE.md"
    printf 'A sibling, similarly-named but NOT excluded directory. No anchor block here on purpose (BOB-143 control).\n' \
        > "${_root}/worktrees/bob143_control/CLAUDE.md"
}

PROBE_REL=".worktrees/bob143_probe/CLAUDE.md"
CONTROL_REL="worktrees/bob143_control/CLAUDE.md"

# check_gate_direct <label> — drives cm_covenant_114_230_propagation.sh
# directly against the fixture: once with COVENANT_PROPAGATION_EXCLUSIONS
# pointed at an EMPTY file (baseline — proves both needles are genuinely
# detectable with no exclusion active at all), then once with it pointed at
# the REAL checked-in fix.
check_gate_direct() {
    local _label="direct-engine"
    local _root="${FIX}/${_label}"
    build_fixture "${_root}"
    echo
    echo "---- ${_label}: cm_covenant_114_230_propagation.sh ----"

    local _empty_excl="${FIX}/empty_exclusions.tsv"
    : > "${_empty_excl}"

    local _baseline
    _baseline="$(COVENANT_PROPAGATION_EXCLUSIONS="${_empty_excl}" bash "${GATES_DIR}/cm_covenant_114_230_propagation.sh" --root "${_root}" --quiet 2>&1)"
    local _base_probe _base_control
    _base_probe="$(printf '%s\n' "${_baseline}" | grep -cF "${PROBE_REL}" || true)"
    _base_control="$(printf '%s\n' "${_baseline}" | grep -cF "${CONTROL_REL}" || true)"
    if [[ "${_base_probe:-0}" -eq 0 || "${_base_control:-0}" -eq 0 ]]; then
        echo "${_baseline}"
        abort "[${_label}] baseline (no exclusion) did not see BOTH needles (probe=${_base_probe:-0} control=${_base_control:-0}) — instrument blind"
    fi
    echo "baseline (empty exclusions file): probe seen (${_base_probe} hit(s)), control seen (${_base_control} hit(s)) — instrument PROVEN seeing both locations"

    local _fixed
    _fixed="$(COVENANT_PROPAGATION_EXCLUSIONS="${EXCL_FILE}" bash "${GATES_DIR}/cm_covenant_114_230_propagation.sh" --root "${_root}" --quiet 2>&1)"
    local _fx_probe _fx_control _fx_excl_line
    _fx_probe="$(printf '%s\n' "${_fixed}" | grep -cF "${PROBE_REL}" || true)"
    _fx_control="$(printf '%s\n' "${_fixed}" | grep -cF "${CONTROL_REL}" || true)"
    _fx_excl_line="$(printf '%s\n' "${_fixed}" | grep -cE '⊘ EXCLUDED  \*/\.worktrees  \[filename-collision\]' || true)"

    if [[ "${_fx_probe:-0}" -eq 0 && "${_fx_control:-0}" -ge 1 && "${_fx_excl_line:-0}" -ge 1 ]]; then
        echo "PASS: with the real BOB-143 exclusion active, .worktrees/-rooted probe EXCLUDED (0 hits, and the ⊘ EXCLUDED line was printed), worktrees/-rooted control STILL CAUGHT (${_fx_control} hit(s))."
        return 0
    fi
    echo "${_fixed}"
    echo "FAIL: with the real exclusion active, probe hits=${_fx_probe:-0} (want 0) control hits=${_fx_control:-0} (want >=1) exclusion-line hits=${_fx_excl_line:-0} (want >=1)."
    return 1
}

# check_suite_path <label> — drives the SAME fixture through
# covenant_propagation_suite.sh gates --root <fixture>, the code path
# scripts/verify-all-constitution-rules.sh (boba's real §11.4.32 sweep, the
# instrument BOB-143 measured against) actually invokes. The suite
# pre-computes its own carrier list with a SEPARATE find command
# (covenant_propagation_suite.sh's own carrier-set-reuse block) that reads
# the SAME exclusions file — a genuinely distinct implementation that could
# silently diverge from the single-gate engine's own discovery, so it is
# proven independently rather than assumed identical.
#
# NOTE ON SIGNAL: the suite's own stdout is a ONE-LINE-PER-GATE summary
# table (covenant_propagation_suite.sh:100-113) — it deliberately does not
# forward each gate's per-file ✅/❌ lines, only the aggregate stats
# "<N> single-block-PRESENT, <N> POINTER-INHERITANCE-SKIP, <N> MISSING/
# DUPLICATED, <N> DIVERGENT". So this check reads the MISSING/DUPLICATED
# COUNT on the CM-COVENANT-114-230-PROPAGATION row rather than grepping for
# a per-file path (proven empirically: with the fixture's 1 real root
# carrier + probe + control, baseline reads "2 MISSING/DUPLICATED"; with
# the probe excluded it reads "1 MISSING/DUPLICATED" — down by exactly the
# probe, the control's own MISSING survives).
_anchor230_missing_count() {
    # $1 = suite stdout
    printf '%s\n' "$1" | grep -E '^CM-COVENANT-114-230-PROPAGATION[[:space:]]' \
        | sed -E 's/.*[[:space:]]([0-9]+) MISSING\/DUPLICATED.*/\1/'
}

check_suite_path() {
    local _label="suite-path"
    local _root="${FIX}/${_label}"
    build_fixture "${_root}"
    echo
    echo "---- ${_label}: covenant_propagation_suite.sh gates (production invocation shape) ----"

    local _empty_excl="${FIX}/empty_exclusions_suite.tsv"
    : > "${_empty_excl}"

    local _baseline _base_missing
    _baseline="$(COVENANT_PROPAGATION_EXCLUSIONS="${_empty_excl}" bash "${SUITE}" gates --root "${_root}" 2>&1)"
    _base_missing="$(_anchor230_missing_count "${_baseline}")"
    if [[ -z "${_base_missing}" ]]; then
        echo "${_baseline}" | tail -40
        abort "[${_label}] anchor 230's row was not found in the suite's baseline output — instrument blind (or the row format changed)"
    fi
    if [[ "${_base_missing}" -ne 2 ]]; then
        echo "${_baseline}" | tail -40
        abort "[${_label}] baseline (no exclusion) reported ${_base_missing} MISSING/DUPLICATED for anchor 230, expected exactly 2 (the .worktrees/ probe AND the worktrees/ control) — instrument is not seeing both needles, so an 'excluded' verdict below would not be evidence"
    fi
    echo "baseline (empty exclusions file): anchor 230 row reports 2 MISSING/DUPLICATED (probe + control) — instrument PROVEN seeing both locations"

    local _fixed _fx_missing
    _fixed="$(COVENANT_PROPAGATION_EXCLUSIONS="${EXCL_FILE}" bash "${SUITE}" gates --root "${_root}" 2>&1)"
    _fx_missing="$(_anchor230_missing_count "${_fixed}")"

    if [[ -n "${_fx_missing}" && "${_fx_missing}" -eq 1 ]]; then
        echo "PASS: via the suite path, with the real BOB-143 exclusion active anchor 230's row reports exactly 1 MISSING/DUPLICATED (the worktrees/ control only — the .worktrees/ probe's MISSING dropped out, i.e. was excluded from discovery)."
        return 0
    fi
    echo "${_fixed}" | tail -40
    echo "FAIL: via the suite path, with the real exclusion active anchor 230's row reports MISSING/DUPLICATED='${_fx_missing:-<row not found>}' (want exactly 1)."
    return 1
}

_failed_labels=""

check_gate_direct || { overall_fail=1; _failed_labels="${_failed_labels} direct-engine"; }
check_suite_path  || { overall_fail=1; _failed_labels="${_failed_labels} suite-path"; }

echo
if [[ "${overall_fail}" -eq 0 ]]; then
    echo "VERDICT: PASS — BOB-143's .worktrees/ exclusion is load-bearing (excluded) while worktrees/ (no dot) is still caught, on both the direct-engine and the production suite invocation paths; the already-fixed MOCK_PID/ORACLE/KILLPG/DANGEROUS_COMBO wiring still names .worktrees."
    exit 0
fi
echo "VERDICT: FAIL — BOB-143 .worktrees/ exclusion misbehaved for:${_failed_labels}"
exit 1
