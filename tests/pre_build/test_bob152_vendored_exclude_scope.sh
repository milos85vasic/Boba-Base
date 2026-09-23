#!/usr/bin/env bash
# test_bob152_vendored_exclude_scope.sh — BOB-152 §1.1 paired-mutation proof
# (§11.4.115 / §11.4.224 / §11.4.201(7)(b))
#
# PURPOSE
#   BOB-152 excludes `submodules/` (vendored-third-party code, §11.4.224(E))
#   from the scan scope of three constitution gates driven by
#   scripts/verify-all-constitution-rules.sh: CM-ORACLE-STRATEGY-NAMED-AND-
#   INDEPENDENT, CM-KILLPG-PGID-GUARD, and CM-TEST-MOCK-PID-EXPLICIT-INT
#   (env vars ORACLE_GUARD_EXCLUDE / KILLPG_GUARD_EXCLUDE /
#   MOCK_PID_GUARD_EXCLUDE, all three now sourced from the sweep's own
#   `_BOB152_VENDORED_EXCLUDE` variable). This proves the exclusion is
#   genuinely LOAD-BEARING, in BOTH directions, for all three gates: a
#   BYTE-IDENTICAL violation planted under `submodules/<fixture>/` is
#   excluded when the BOB-152 wiring is active, while the SAME violation
#   planted under `tests/<fixture>/` (first-party) is STILL CAUGHT.
#
# WHAT THIS ASSERTS (the oracle — §11.4.245)
#   Strategy: METAMORPHIC + INVARIANT, with explicit control needles.
#   Two byte-identical needles per gate are planted in a hermetic fixture
#   tree — one under a `submodules/` prefix (the PROBE, expected to
#   disappear once BOB-152's exclude is active), one under a `tests/`
#   prefix (the CONTROL, expected to be caught with or without the
#   exclude). Each gate is driven twice per needle pair: once with NO
#   exclude override (baseline — proves BOTH needles are genuinely
#   detectable, i.e. the instrument is not blind to either location) and
#   once with the REAL BOB-152 exclude value read from the sweep script
#   itself (never hand-typed here, per §11.4.251 — the test is bound to
#   the single source of truth, not a copy of it).
#
# INSTRUMENT VIABILITY (§11.4.201(7)(b) / §11.4.273)
#   The baseline (no-exclude) run is the control needle for every probe:
#   if a probe needle is NOT seen there, the harness/gate combination is
#   blind to that needle shape and the script ABORTS (exit 3) rather than
#   reporting a false PASS on the exclude behaviour.
#
# EXIT CODES
#   0  PASS  — for every gate: submodules-rooted needle excluded AND
#              tests-rooted needle still caught, with the baseline run
#              proving both were genuinely detectable pre-exclude.
#   1  FAIL  — the exclude did not behave as BOB-152 requires for at
#              least one gate.
#   3  ABORT — instrument blind / harness precondition unmet (NOT a
#              verdict on BOB-152 itself).
#
# SIDE EFFECTS: none outside its own mktemp -d, removed on exit.
# DEPENDENCIES: bash, find, grep, sed, mktemp, python3 (gates' AST arm).
set -uo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
SWEEP="${BOB152_SWEEP:-${PROJECT_ROOT}/scripts/verify-all-constitution-rules.sh}"
GATES_DIR="${BOB152_GATES_DIR:-${PROJECT_ROOT}/constitution/scripts/gates}"

abort() { echo "ABORT: $*" >&2; exit 3; }
overall_fail=0

echo "== BOB-152 vendored-exclude scope proof =="
echo "sweep: ${SWEEP}"
[[ -f "${SWEEP}" ]] || abort "sweep script absent: ${SWEEP}"

# --- 1. Extract the REAL exclude value from the sweep script itself --------
# Bound to the single source of truth (§11.4.251): never hand-typed here.
_base_line_count="$(grep -cE '^_BOB143_SWEEP_EXCLUDE=' "${SWEEP}" || true)"
[[ "${_base_line_count}" == "1" ]] || abort "expected exactly 1 _BOB143_SWEEP_EXCLUDE= assignment, found ${_base_line_count} (§11.4.201(6): 0 here would be a blind parse)"
BASE_EXCLUDE="$(sed -n 's/^_BOB143_SWEEP_EXCLUDE="\(.*\)"$/\1/p' "${SWEEP}")"
[[ -n "${BASE_EXCLUDE}" ]] || abort "_BOB143_SWEEP_EXCLUDE assignment matched but did not parse"

_vendored_line_count="$(grep -cE '^_BOB152_VENDORED_EXCLUDE=' "${SWEEP}" || true)"
[[ "${_vendored_line_count}" == "1" ]] || abort "expected exactly 1 _BOB152_VENDORED_EXCLUDE= assignment, found ${_vendored_line_count}"
_vendored_raw="$(sed -n 's/^_BOB152_VENDORED_EXCLUDE="\(.*\)"$/\1/p' "${SWEEP}")"
[[ "${_vendored_raw}" == '${_BOB143_SWEEP_EXCLUDE} submodules' ]] || abort "_BOB152_VENDORED_EXCLUDE is no longer wired as '\${_BOB143_SWEEP_EXCLUDE} submodules' (got: ${_vendored_raw}) — the two exclude lists have diverged from their intended base+submodules relationship"
BOB152_EXCLUDE="${BASE_EXCLUDE} submodules"
echo "BASE_EXCLUDE (from sweep):     ${BASE_EXCLUDE}"
echo "BOB152_EXCLUDE (base+submodules, as the sweep wires it): ${BOB152_EXCLUDE}"

# Confirm the three affected gates' exports are actually wired to the
# BOB-152 variable (not left pointing at the narrower BOB-143 one).
for _v in MOCK_PID_GUARD_EXCLUDE ORACLE_GUARD_EXCLUDE KILLPG_GUARD_EXCLUDE; do
    _expected_line='export '"${_v}"'="${'"${_v}"':-$_BOB152_VENDORED_EXCLUDE}"'
    grep -qF -- "${_expected_line}" "${SWEEP}" \
        || abort "${_v} export in the sweep is not wired to \$_BOB152_VENDORED_EXCLUDE (expected literal line: ${_expected_line}) — BOB-152 wiring regressed"
done
echo "wiring confirmed: MOCK_PID_GUARD_EXCLUDE / ORACLE_GUARD_EXCLUDE / KILLPG_GUARD_EXCLUDE all read \$_BOB152_VENDORED_EXCLUDE"

# DANGEROUS_COMBO_EXCLUDE MUST NOT have gained "submodules" (out of BOB-152
# scope, per the sweep script's own SCOPE comment) — a regression guard for
# the "don't touch cm_dangerous_combination_fail_closed.sh" constraint.
_dc_line="$(grep -E '^export DANGEROUS_COMBO_EXCLUDE=' "${SWEEP}" || true)"
[[ -n "${_dc_line}" ]] || abort "DANGEROUS_COMBO_EXCLUDE export line not found in the sweep"
if printf '%s' "${_dc_line}" | grep -qE '_BOB152_VENDORED_EXCLUDE'; then
    abort "DANGEROUS_COMBO_EXCLUDE has been rewired to _BOB152_VENDORED_EXCLUDE — this is explicitly out of BOB-152 scope (concurrent-work collision risk)"
fi
echo "confirmed OUT OF SCOPE preserved: DANGEROUS_COMBO_EXCLUDE is still bound to \$_BOB143_SWEEP_EXCLUDE, not \$_BOB152_VENDORED_EXCLUDE"

# --- 2. Hermetic fixture tree ------------------------------------------------
FIX="$(mktemp -d)"; trap 'rm -rf "${FIX}"' EXIT

write_killpg_needle() {
    mkdir -p "$(dirname "$1")"
    cat > "$1" <<'PYEOF'
import os


def sweep_the_group(target_pid):
    os.killpg(target_pid, 9)
PYEOF
}

write_oracle_needle() {
    mkdir -p "$(dirname "$1")"
    cat > "$1" <<'PYEOF'
def test_bob152_probe_has_no_oracle_annotation():
    assert True
PYEOF
}

write_mock_pid_needle() {
    mkdir -p "$(dirname "$1")"
    cat > "$1" <<'PYEOF'
from unittest.mock import AsyncMock


def test_bob152_mock_pid_unset():
    proc = AsyncMock()
    observed_pid = proc.pid
    assert observed_pid is not None
PYEOF
}

run_gate() {
    # run_gate <gate-basename> <env-var-name> <exclude-value-or-empty> <root> [extra-args...]
    local _gate="$1" _envvar="$2" _exclude="$3" _root="$4"; shift 4
    if [[ -n "${_exclude}" ]]; then
        env "${_envvar}=${_exclude}" bash "${GATES_DIR}/${_gate}" --root "${_root}" --quiet "$@" 2>&1
    else
        env -u "${_envvar}" bash "${GATES_DIR}/${_gate}" --root "${_root}" --quiet "$@" 2>&1
    fi
}

check_pair() {
    # check_pair <label> <gate-basename> <env-var> <needle-writer> <needle-relpath-basename> [extra-args...]
    local _label="$1" _gate="$2" _envvar="$3" _writer="$4" _needle_name="$5"; shift 5
    local _extra_args=("$@")
    local _subroot="${FIX}/${_label}"
    rm -rf "${_subroot}"; mkdir -p "${_subroot}"

    local _probe="${_subroot}/submodules/bob152_probe/${_needle_name}"
    local _control="${_subroot}/tests/bob152_control/${_needle_name}"
    "${_writer}" "${_probe}"
    "${_writer}" "${_control}"

    local _probe_sum _control_sum
    _probe_sum="$(sha256sum "${_probe}" | awk '{print $1}')"
    _control_sum="$(sha256sum "${_control}" | awk '{print $1}')"
    [[ "${_probe_sum}" == "${_control_sum}" ]] || abort "[${_label}] probe and control needles differ — metamorphic relation void"

    echo
    echo "---- ${_label} (${_gate}) ----"

    # Baseline: NO exclude override at all — both needles must be seen.
    local _baseline
    _baseline="$(run_gate "${_gate}" "${_envvar}" "" "${_subroot}" "${_extra_args[@]}")"
    local _base_probe_hits _base_control_hits
    _base_probe_hits="$(printf '%s\n' "${_baseline}" | grep -cF "${_probe}" || true)"
    _base_control_hits="$(printf '%s\n' "${_baseline}" | grep -cF "${_control}" || true)"
    if [[ "${_base_probe_hits:-0}" -eq 0 || "${_base_control_hits:-0}" -eq 0 ]]; then
        echo "${_baseline}"
        abort "[${_label}] baseline (no exclude) did not see BOTH needles (probe=${_base_probe_hits:-0} control=${_base_control_hits:-0}) — instrument blind, cannot trust the exclude verdict (§11.4.201(7)(b))"
    fi
    echo "baseline (no exclude): probe seen (${_base_probe_hits} hit(s)), control seen (${_base_control_hits} hit(s)) — instrument PROVEN seeing both locations"

    # BOB-152 exclude active — probe (submodules/) MUST disappear, control (tests/) MUST remain.
    local _excluded
    _excluded="$(run_gate "${_gate}" "${_envvar}" "${BOB152_EXCLUDE}" "${_subroot}" "${_extra_args[@]}")"
    local _exc_probe_hits _exc_control_hits
    _exc_probe_hits="$(printf '%s\n' "${_excluded}" | grep -cF "${_probe}" || true)"
    _exc_control_hits="$(printf '%s\n' "${_excluded}" | grep -cF "${_control}" || true)"

    if [[ "${_exc_probe_hits:-0}" -eq 0 && "${_exc_control_hits:-0}" -ge 1 ]]; then
        echo "PASS: with BOB-152 exclude active, submodules/-rooted probe EXCLUDED (0 hits), tests/-rooted control STILL CAUGHT (${_exc_control_hits} hit(s))."
        return 0
    fi
    echo "${_excluded}"
    echo "FAIL: with BOB-152 exclude active, probe hits=${_exc_probe_hits:-0} (want 0) control hits=${_exc_control_hits:-0} (want >=1)."
    return 1
}

_failed_labels=""

check_pair "killpg" "cm_killpg_pgid_guard.sh" "KILLPG_GUARD_EXCLUDE" write_killpg_needle "bob152_needle.py" \
    || { overall_fail=1; _failed_labels="${_failed_labels} killpg"; }

check_pair "oracle" "cm_oracle_strategy_named_and_independent.sh" "ORACLE_GUARD_EXCLUDE" write_oracle_needle "bob152_needle_test.py" --glob '*test*.py' \
    || { overall_fail=1; _failed_labels="${_failed_labels} oracle"; }

check_pair "mock_pid" "cm_test_mock_pid_explicit_int.sh" "MOCK_PID_GUARD_EXCLUDE" write_mock_pid_needle "bob152_needle_test.py" \
    || { overall_fail=1; _failed_labels="${_failed_labels} mock_pid"; }

echo
if [[ "${overall_fail}" -eq 0 ]]; then
    echo "VERDICT: PASS — BOB-152 exclude is load-bearing (submodules/ excluded, tests/ still caught) for all 3 affected gates."
    exit 0
fi
echo "VERDICT: FAIL — BOB-152 exclude misbehaved for:${_failed_labels}"
exit 1
