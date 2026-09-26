#!/usr/bin/env bash
# test_check_prebuild_invoked_executables_tracked.sh — RED/GREEN, golden-FALSE,
# fail-closed and paired §1.1 mutation arms for
# scripts/pre_build/check_prebuild_invoked_executables_tracked.sh
# (CM-PREBUILD-INVOKED-EXECUTABLES-TRACKED, BOB-231).
#
# Every arm runs in a throwaway git repository with a FAKE sweep script, so the
# real checkout is never touched and the fixture decides exactly what is tracked.
#
# Arms:
#   G1 golden-GOOD   every invoked gate tracked                      -> exit 0
#   R1 golden-BAD    an invoked gate exists but is untracked         -> exit 1, named
#   R2 golden-BAD    a helper the gate calls via ${SCRIPT_DIR} is
#                    untracked (level-2 enumeration)                 -> exit 1, named
#   R3 golden-BAD    a ${CONST_GATES_DIR} target untracked inside the
#                    nested constitution repo                        -> exit 1, named
#   R4 golden-BAD    a dynamic ${anchor} path: one glob match untracked -> exit 1, named
#   F1 golden-FALSE  an untracked path mentioned only in a COMMENT   -> exit 0
#   F2 golden-FALSE  an untracked tests/**/test_*.sh                 -> exit 0 + WARN (advisory)
#   B1 fail-closed   sweep with zero invocations (blind)             -> exit 2
#   B2 fail-closed   not a git repository                            -> exit 2
#   M1 paired mutation: the tracked-check neutered (always "tracked")
#                    -> R1's assertion catches it
#
# Usage: bash tests/pre_build/test_check_prebuild_invoked_executables_tracked.sh
# Exit:  0 every arm behaved; 1 otherwise.
# Constitution: §1.1, §11.4.107(10), §11.4.201(1)(6), §11.4.224, §11.4.245.

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
GATE="${REPO}/scripts/pre_build/check_prebuild_invoked_executables_tracked.sh"
PASS=0; FAIL=0
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT   # §11.4.14 cleanup on every exit path

g() { git -c user.email=t@t -c user.name=t "$@"; }

# mk_repo <name> : repo with a sweep invoking two gates (both tracked)
mk_repo() {
    local r="${TMP}/$1"
    mkdir -p "${r}/scripts/pre_build" "${r}/tests/unit"
    cat > "${r}/scripts/pre_build_verification.sh" <<'EOF'
#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
# prose only: ${PROJECT_ROOT}/scripts/pre_build/only_in_a_comment.sh
A="${PROJECT_ROOT}/scripts/pre_build/check_a.sh"
bash "${A}"
bash "${SCRIPT_DIR}/pre_build/check_b.sh"
EOF
    printf '#!/usr/bin/env bash\nexit 0\n' > "${r}/scripts/pre_build/check_a.sh"
    printf '#!/usr/bin/env bash\nexit 0\n' > "${r}/scripts/pre_build/check_b.sh"
    printf '#!/usr/bin/env bash\nexit 0\n' > "${r}/tests/unit/test_tracked.sh"
    g -C "${r}" init -q && g -C "${r}" add -A && g -C "${r}" commit -qm init
    echo "${r}"
}

arm() {  # <label> <want-rc> <must-contain-or-empty> <gate> <args...>
    local label="$1" want="$2" needle="$3" gate="$4"; shift 4
    local out rc
    out="$(bash "${gate}" "$@" 2>&1)"; rc=$?
    if [[ "${rc}" -eq "${want}" ]] && { [[ -z "${needle}" ]] || grep -qF -- "${needle}" <<<"${out}"; }; then
        echo "  PASS  ${label} (exit ${rc})"; PASS=$((PASS+1))
    else
        echo "  FAIL  ${label}: wanted exit ${want} + '${needle}', got exit ${rc}"
        sed 's/^/          /' <<<"${out}"; FAIL=$((FAIL+1))
    fi
}

echo "CM-PREBUILD-INVOKED-EXECUTABLES-TRACKED — arms"

r="$(mk_repo g1)"
arm "G1 golden-GOOD every invoked gate tracked" 0 "OK: all 2 executables" "${GATE}" "${r}"

r="$(mk_repo r1)"
printf '#!/usr/bin/env bash\n' > "${r}/scripts/pre_build/check_c.sh"
printf 'bash "${PROJECT_ROOT}/scripts/pre_build/check_c.sh"\n' >> "${r}/scripts/pre_build_verification.sh"
g -C "${r}" add scripts/pre_build_verification.sh && g -C "${r}" commit -qm sweep
arm "R1 golden-BAD untracked invoked gate is named" 1 "UNTRACKED INVOKED EXECUTABLE: scripts/pre_build/check_c.sh" "${GATE}" "${r}"
R1_REPO="${r}"

r="$(mk_repo r2)"
printf 'python3 "${SCRIPT_DIR}/helper_analyzer.py"\n' >> "${r}/scripts/pre_build/check_a.sh"
printf 'print(1)\n' > "${r}/scripts/pre_build/helper_analyzer.py"
g -C "${r}" add scripts/pre_build/check_a.sh && g -C "${r}" commit -qm helper-ref
arm "R2 golden-BAD untracked helper called by a gate is named" 1 "UNTRACKED INVOKED EXECUTABLE: scripts/pre_build/helper_analyzer.py" "${GATE}" "${r}"

r="$(mk_repo r3)"
mkdir -p "${r}/constitution/scripts/gates"
printf '#!/usr/bin/env bash\n' > "${r}/constitution/scripts/gates/cm_tracked.sh"
printf '#!/usr/bin/env bash\n' > "${r}/constitution/scripts/gates/cm_untracked.sh"
g -C "${r}/constitution" init -q && g -C "${r}/constitution" add scripts/gates/cm_tracked.sh && g -C "${r}/constitution" commit -qm c
printf 'CONST_GATES_DIR="${PROJECT_ROOT}/constitution/scripts/gates"\nbash "${CONST_GATES_DIR}/cm_tracked.sh"\nbash "${CONST_GATES_DIR}/cm_untracked.sh"\n' >> "${r}/scripts/pre_build_verification.sh"
arm "R3 golden-BAD untracked constitution gate is named (checked in the submodule's own index)" 1 "UNTRACKED INVOKED EXECUTABLE: constitution/scripts/gates/cm_untracked.sh" "${GATE}" "${r}"
arm "R3b the tracked constitution gate beside it is not reported" 1 "" "${GATE}" "${r}"
if bash "${GATE}" "${r}" 2>&1 | grep -qF "cm_tracked.sh"; then
    echo "  FAIL  R3c tracked constitution gate wrongly reported"; FAIL=$((FAIL+1))
else
    echo "  PASS  R3c tracked constitution gate not reported"; PASS=$((PASS+1))
fi

r="$(mk_repo r4)"
mkdir -p "${r}/scripts/gates"
printf '#!/usr/bin/env bash\n' > "${r}/scripts/gates/cov_1_p.sh"
g -C "${r}" add scripts/gates/cov_1_p.sh && g -C "${r}" commit -qm cov1
printf '#!/usr/bin/env bash\n' > "${r}/scripts/gates/cov_2_p.sh"
printf 'for _anchor in 1 2; do bash "${PROJECT_ROOT}/scripts/gates/cov_${_anchor}_p.sh"; done\n' >> "${r}/scripts/pre_build_verification.sh"
arm "R4 golden-BAD dynamic \${anchor} path: the untracked glob match is named" 1 "UNTRACKED INVOKED EXECUTABLE: scripts/gates/cov_2_p.sh" "${GATE}" "${r}"

r="$(mk_repo f1)"
printf '#!/usr/bin/env bash\n' > "${r}/scripts/pre_build/only_in_a_comment.sh"
arm "F1 golden-FALSE untracked path mentioned only in a comment is not an invocation" 0 "OK:" "${GATE}" "${r}"

r="$(mk_repo f2)"
printf '#!/usr/bin/env bash\n' > "${r}/tests/unit/test_wip.sh"
arm "F2 golden-FALSE untracked test suite is advisory: exit 0 with a WARN naming it" 0 "WARN (advisory): untracked test suite that invariant 30 would run: tests/unit/test_wip.sh" "${GATE}" "${r}"

r="$(mk_repo b1)"
printf '#!/usr/bin/env bash\necho nothing\n' > "${r}/scripts/pre_build_verification.sh"
arm "B1 fail-closed: a sweep resolving zero targets is BLIND, never clean" 2 "BLIND" "${GATE}" "${r}"

mkdir -p "${TMP}/notgit"
arm "B2 fail-closed: not a git repository" 2 "not a git repository" "${GATE}" "${TMP}/notgit"

# M1 paired mutation: neuter the tracked check.
MUT="${TMP}/mutated_gate.sh"
sed 's/ls-files --error-unmatch -- /ls-files -- /g' "${GATE}" > "${MUT}"
if [[ ! -f "${GATE}" ]] || ! grep -qF "UNTRACKED INVOKED EXECUTABLE" <<<"$(bash "${GATE}" "${R1_REPO}" 2>&1)"; then
    echo "  FAIL  M1 precondition: the unmutated gate does not report R1, so the mutation proves nothing"; FAIL=$((FAIL+1))
elif cmp -s "${MUT}" "${GATE}"; then
    echo "  FAIL  M1 mutation sed did not change the gate copy"; FAIL=$((FAIL+1))
else
    out="$(bash "${MUT}" "${R1_REPO}" 2>&1)"; rc=$?
    if [[ "${rc}" -eq 0 ]]; then
        echo "  PASS  M1 mutated gate (tracked-check neutered) passes the R1 fixture — R1's exit-1 assertion would catch it"; PASS=$((PASS+1))
    else
        echo "  FAIL  M1 mutated gate still exits ${rc} on R1 — the mutation is not load-bearing"; FAIL=$((FAIL+1))
    fi
fi

echo "RESULT: ${PASS} passed, ${FAIL} failed"
[[ "${FAIL}" -eq 0 ]]
