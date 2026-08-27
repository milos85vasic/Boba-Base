#!/usr/bin/env bash
# test_bob205_danger_roots_scope.sh — BOB-205 RED (§11.4.115 / §11.4.224)
#
# PURPOSE
#   Prove the SCOPE hole in pre-build invariant 39
#   (CM-DANGEROUS-COMBINATION-FAIL-CLOSED, §11.4.252): the fail-open scanner
#   is driven per-root over a HAND-MAINTAINED `DANGER_ROOTS` array at
#   scripts/pre_build_verification.sh:1511, and `cmd/boba-ctl` — the container
#   orchestrator, a shell-exec + state-mutation surface — is not a member, so
#   the scanner is NEVER POINTED AT IT by any arm.
#
# WHAT THIS ASSERTS (the oracle — §11.4.245)
#   Strategy: METAMORPHIC + INVARIANT, with an explicit control needle.
#   Two BYTE-IDENTICAL fail-open needles are planted in a hermetic fixture
#   tree — one inside a root that IS in DANGER_ROOTS (the CONTROL), one inside
#   `cmd/boba-ctl` (the PROBE). The scanner is then driven exactly as
#   invariant 39 drives it. The metamorphic relation: identical input in two
#   locations must yield identical verdicts. Divergence is caused by SCOPE and
#   nothing else — the needles are byte-identical, so matcher strength,
#   language support and gate version are all held constant.
#   The oracle is INDEPENDENT of the code under test: the expected verdict
#   comes from the metamorphic relation, not from reading DANGER_ROOTS.
#
# INSTRUMENT VIABILITY (§11.4.201(7)(b))
#   The CONTROL needle proves the gate + this harness can see a needle of this
#   exact class through this exact path. If the control is NOT found, the
#   instrument is blind and this script ABORTS (exit 3) rather than reporting
#   a RED — a null from a blind instrument is not evidence.
#
# WHY THE NEEDLE IS PYTHON, NOT GO (the BOB-191 confound, avoided on purpose)
#   BOB-191 is a MATCHER hole: Go files inside a scanned root are structurally
#   unanalysable while being COUNTED as analysed. The gate routes only `*.py`
#   to its AST analyser; Go falls to a line-based text scanner that has no
#   `catch {}` / `except: pass` shape to match. A Go needle planted here could
#   therefore stay unseen EVEN AFTER `cmd/boba-ctl` is added to DANGER_ROOTS —
#   the RED would never flip, which is itself a §11.4.201(1) FAIL-bluff.
#   Python is the class the gate is PROVEN to see (the control needle proves
#   it on every run), so this test isolates SCOPE from MATCHER. Fixing
#   BOB-191 alone will NOT turn this test green; only widening the scope will.
#
# EXIT CODES
#   0  GREEN — cmd/boba-ctl is within the scanner's scope (post-fix)
#   1  RED   — planted fail-open inside cmd/boba-ctl is invisible (today)
#   3  ABORT — instrument blind / harness precondition unmet (NOT a verdict)
#
# SIDE EFFECTS: none outside its own mktemp -d, which it removes on exit.
# DEPENDENCIES: bash, find, grep, sed, mktemp, python3 (for the gate's AST arm)
set -uo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
DRIVER="${BOB205_DRIVER:-${PROJECT_ROOT}/scripts/pre_build_verification.sh}"
GATE="${BOB205_GATE:-${PROJECT_ROOT}/constitution/scripts/gates/cm_dangerous_combination_fail_closed.sh}"
PROBE_ROOT="${BOB205_PROBE_ROOT:-cmd/boba-ctl}"

abort() { echo "ABORT: $*" >&2; exit 3; }

echo "== BOB-205 scope RED =="
echo "driver: ${DRIVER}"
echo "gate:   ${GATE}"
[[ -f "${DRIVER}" ]] || abort "driver absent: ${DRIVER}"
[[ -f "${GATE}"   ]] || abort "gate absent: ${GATE}"
echo "gate sha256: $(sha256sum "${GATE}" | awk '{print $1}')"

# --- 1. Read DANGER_ROOTS from the REAL driver (single source of truth) -----
# Binding the test to the driver's own array is what makes it flip GREEN the
# moment the root is added, with zero edits to this file (§11.4.251).
_dr_lines="$(grep -cE '^[[:space:]]*DANGER_ROOTS=\(' "${DRIVER}" || true)"
[[ "${_dr_lines}" == "1" ]] || abort "expected exactly 1 DANGER_ROOTS= assignment in the driver, found ${_dr_lines} (§11.4.201(6): a 0 here would be a blind parse, not an empty list)"
_dr_raw="$(sed -n 's/^[[:space:]]*DANGER_ROOTS=(\(.*\))[[:space:]]*$/\1/p' "${DRIVER}")"
[[ -n "${_dr_raw}" ]] || abort "DANGER_ROOTS assignment matched but did not parse — the driver's array form changed"
# shellcheck disable=SC2206
DANGER_ROOTS=(${_dr_raw})
[[ "${#DANGER_ROOTS[@]}" -ge 1 ]] || abort "parsed an empty DANGER_ROOTS"
echo "DANGER_ROOTS (${#DANGER_ROOTS[@]}): ${DANGER_ROOTS[*]}"

# --- 2. Hermetic fixture tree ----------------------------------------------
FIX="$(mktemp -d)"; trap 'rm -rf "${FIX}"' EXIT

# The needle: a swallowed-exception (shape A1) on a path that combines
# ENV/CREDENTIAL MUTATION with SHELL-EXEC — a §11.4.252 dangerous combination
# of >= 2 capabilities, modelled on the real plugins/env_loader.py:30 hit that
# invariant 39 already reports.
write_needle() {
    mkdir -p "$(dirname "$1")"
    cat > "$1" <<'PYEOF'
import os
import subprocess


def load_credentials(path):
    try:
        for line in open(path):
            key, _, value = line.partition("=")
            os.environ[key.strip()] = value.strip()
    except Exception:
        pass
    subprocess.run(["/bin/true"], check=False)
PYEOF
}

NEEDLE_BASENAME="bob205_faillopen_needle.py"
for _r in "${DANGER_ROOTS[@]}"; do
    mkdir -p "${FIX}/${_r}"
    write_needle "${FIX}/${_r}/${NEEDLE_BASENAME}"       # CONTROL needles
done
mkdir -p "${FIX}/${PROBE_ROOT}"
write_needle "${FIX}/${PROBE_ROOT}/${NEEDLE_BASENAME}"   # PROBE needle
# Byte-identity of control vs probe is load-bearing: it holds matcher, language
# and gate version constant so SCOPE is the only free variable.
_ctl_sum="$(sha256sum "${FIX}/${DANGER_ROOTS[0]}/${NEEDLE_BASENAME}" | awk '{print $1}')"
_prb_sum="$(sha256sum "${FIX}/${PROBE_ROOT}/${NEEDLE_BASENAME}"      | awk '{print $1}')"
[[ "${_ctl_sum}" == "${_prb_sum}" ]] || abort "control and probe needles differ (${_ctl_sum} vs ${_prb_sum}) — the metamorphic relation is void"
echo "needle sha256 (control == probe): ${_ctl_sum}"

# --- 3. Drive the scanner EXACTLY as invariant 39 does ----------------------
# Same loop, same --root/--quiet CLI, same structural finding-line matcher
# (a finding NAMES A LOCATION; the summary line never does — driver:1529).
FINDINGS="${FIX}/.findings"; : > "${FINDINGS}"
SCANNED=0
for _r in "${DANGER_ROOTS[@]}"; do
    [[ -d "${FIX}/${_r}" ]] || continue
    SCANNED=$((SCANNED + 1))
    bash "${GATE}" --root "${FIX}/${_r}" --quiet 2>&1 \
        | grep -aE '^❌.* at .*:[0-9]+' >> "${FINDINGS}" || true
done
echo "roots scanned by the driver's own list: ${SCANNED}"

_ctl_hits="$(grep -cF "/${DANGER_ROOTS[0]}/${NEEDLE_BASENAME}" "${FINDINGS}" || true)"
_prb_hits="$(grep -cF "/${PROBE_ROOT}/${NEEDLE_BASENAME}"      "${FINDINGS}" || true)"

# --- 4. Instrument viability BEFORE any verdict (§11.4.201(7)(b)) ----------
if [[ "${_ctl_hits:-0}" -eq 0 ]]; then
    echo "---- raw findings ----"; cat "${FINDINGS}"; echo "----------------------"
    abort "CONTROL NEEDLE NOT SEEN in ${DANGER_ROOTS[0]} — the gate or this harness is blind to this needle class; the probe's zero says NOTHING (§11.4.201(7)(b))"
fi
echo "CONTROL needle (${DANGER_ROOTS[0]}/): ${_ctl_hits} hit(s) — instrument PROVEN seeing"
echo "PROBE   needle (${PROBE_ROOT}/): ${_prb_hits} hit(s)"

# --- 5. Verdicts ------------------------------------------------------------
echo
echo "-- PRIMARY oracle (metamorphic: byte-identical needles => identical verdicts) --"
if [[ "${_prb_hits:-0}" -ge 1 ]]; then
    PRIMARY=PASS
    echo "PASS: the planted fail-open inside ${PROBE_ROOT}/ WAS seen by the §11.4.252 scanner as invariant 39 drives it."
else
    PRIMARY=FAIL
    echo "FAIL: a fail-open that IS reported when it sits in ${DANGER_ROOTS[0]}/ is INVISIBLE when it sits in ${PROBE_ROOT}/."
    echo "      Cause: ${PROBE_ROOT} is not a member of DANGER_ROOTS, so the scanner is never pointed at it."
    echo "      Driver: ${DRIVER}:$(grep -nE '^[[:space:]]*DANGER_ROOTS=\(' "${DRIVER}" | cut -d: -f1)"
fi

echo
echo "-- SECONDARY oracle (structural; WEAKER — pins list CONTENT, not SCANNING) --"
SECONDARY=FAIL
for _r in "${DANGER_ROOTS[@]}"; do [[ "${_r}" == "${PROBE_ROOT}" ]] && SECONDARY=PASS; done
if [[ "${SECONDARY}" == PASS ]]; then
    echo "PASS: DANGER_ROOTS contains ${PROBE_ROOT}."
else
    echo "FAIL: DANGER_ROOTS does not contain ${PROBE_ROOT}. (Weaker: a list entry is not proof of a scan.)"
fi

echo
if [[ "${PRIMARY}" == PASS ]]; then
    echo "VERDICT: GREEN (primary=${PRIMARY} secondary=${SECONDARY})"
    exit 0
fi
echo "VERDICT: RED (primary=${PRIMARY} secondary=${SECONDARY}) — BOB-205 scope hole reproduced"
exit 1
