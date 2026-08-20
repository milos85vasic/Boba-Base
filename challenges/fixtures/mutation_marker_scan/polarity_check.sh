#!/usr/bin/env bash
# polarity_check.sh — paired §1.1 / §11.4.107(10) self-validation harness for
# CM-NO-PRODUCTION-MUTATION-RESIDUE (scripts/pre_build/check_cm_no_production_mutation_residue.sh).
#
# WHY THIS DRIVES THE REAL GATE
#   The previous harness (challenges/scripts/mutation_marker_scan_polarity_challenge.sh)
#   re-declared the gate's grep pattern inside itself and tested THAT copy.
#   Its own comments admit it: "we reproduce the exact pattern here". That is
#   a §11.4.249 producer=oracle collapse — the harness cannot see the gate
#   drifting, because it never runs the gate. This harness executes the real
#   gate script with explicit-path arguments and reads its exit code, so a
#   change to the detector is immediately visible here.
#
# BOTH POLARITIES ARE REQUIRED (§1.1)
#   A gate proven only on residue is a false-positive machine; a gate proven
#   only on carriers is a false-negative machine. BOB-070 produced one of
#   each in sequence, which is why every fixture below is asserted in both
#   directions:
#     real-*     residue      -> gate MUST exit 1 (fires)
#     waiver-*   abused escape-> gate MUST exit 1 (fires, class C5)
#     carrier-*  documentation-> gate MUST exit 0 (stays clean)
#
# CONTROL NEEDLE (§11.4.201(7)(b))
#   A "carrier stayed clean" result is a NULL, and a blind instrument returns
#   the same quiet zero as an honest one. So before trusting any NOHIT the
#   harness plants a known-detectable needle through the SAME invocation path
#   and requires it to be seen. If the needle is missed the harness exits 2
#   (cannot see) rather than reporting the carriers clean.
#
# Exit codes: 0 all polarities correct | 1 divergence | 2 harness/blind error.
#
# Cross-refs: §1.1 §11.4.84 §11.4.107(10) §11.4.115 §11.4.201(7) §11.4.224(E) §11.4.249
set -uo pipefail

HARNESS="polarity_check"
FIX_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${FIX_DIR}/../../.." && pwd)"
GATE="${REPO_ROOT}/scripts/pre_build/check_cm_no_production_mutation_residue.sh"

[[ -x "${GATE}" ]] || { echo "[${HARNESS}] ERROR: gate not executable at ${GATE}" >&2; exit 2; }

# fixture|expected  (FIRE = gate exits 1, CLEAN = gate exits 0)
FIXTURES=(
    "real-mutation.py|FIRE"
    "real-trailing.py|FIRE"
    "real-trailing.go|FIRE"
    "real-swallow-midline.go|FIRE"
    "real-fakepass-trailing.sh|FIRE"
    "real-annotation.py|FIRE"
    "waiver-abuse-no-reason.py|FIRE"
    "waiver-abuse-on-code-line.py|FIRE"
    "carrier-comment.py|CLEAN"
    "carrier-string.py|CLEAN"
    "carrier-waived.py|CLEAN"
    "carrier-heredoc.sh|CLEAN"
    "carrier-block-comment.go|CLEAN"
)

run_gate() {  # -> FIRE | CLEAN | ERR
    local target="$1" rc=0
    bash "${GATE}" "${target}" >/dev/null 2>&1 || rc=$?
    case "${rc}" in 0) echo CLEAN ;; 1) echo FIRE ;; *) echo "ERR${rc}" ;; esac
}

# ── control needle: prove the invocation path can see, before trusting a NULL
needle_dir="$(mktemp -d)"
trap 'rm -rf "${needle_dir}"' EXIT
printf 'def n():\n    return 1  # %s for RED\n' "MUT""ATED" >"${needle_dir}/needle.py"
needle_verdict="$(run_gate "${needle_dir}/needle.py")"
if [[ "${needle_verdict}" != "FIRE" ]]; then
    echo "[${HARNESS}] BLIND: control needle returned ${needle_verdict}, expected FIRE." >&2
    echo "[${HARNESS}] Every CLEAN below would be a false-null — refusing to report." >&2
    exit 2
fi
echo "=== ${HARNESS} ==="
echo "  [needle] control needle SEEN through the real gate — NULLs below are meaningful"

fails=0
for spec in "${FIXTURES[@]}"; do
    IFS='|' read -r name want <<<"${spec}"
    path="${FIX_DIR}/${name}"
    [[ -f "${path}" ]] || { echo "  [ERROR] missing fixture: ${path}"; exit 2; }
    got="$(run_gate "${path}")"
    if [[ "${got}" == "${want}" ]]; then
        printf '  [PASS] %-30s expected=%-5s got=%s\n' "${name}" "${want}" "${got}"
    else
        printf '  [FAIL] %-30s expected=%-5s got=%s\n' "${name}" "${want}" "${got}"
        fails=$((fails + 1))
    fi
done

if [[ "${fails}" -eq 0 ]]; then
    echo "=== ${HARNESS}: GREEN (${#FIXTURES[@]}/${#FIXTURES[@]} fixtures matched, needle seen) ==="
    exit 0
fi
echo "=== ${HARNESS}: RED (${fails}/${#FIXTURES[@]} fixture(s) diverged) ==="
exit 1
