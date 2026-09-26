#!/usr/bin/env bash
# test_check_cm_script_docs_sync.sh — arms for CM-SCRIPT-DOCS-SYNC (§11.4.18,
# BOB-242): scripts/pre_build/check_cm_script_docs_sync.sh.
#
# Every arm runs in a throwaway git repository, so commit timestamps and the
# baseline are fully controlled and the real checkout is never touched.
#
# Arms:
#   G1 golden-GOOD  every script has a doc committed with/after it       -> exit 0
#   R1 golden-BAD   a new script with no docs/scripts/<name>.md          -> exit 1 NEW NODOC
#   R2 golden-BAD   script changed in a later commit, doc not            -> exit 1 NEW DOCBEHIND
#   R3 golden-BAD   script edited in the working tree, doc not           -> exit 1 NEW DOCBEHIND
#   R4 ratchet      a baseline row whose finding is gone                 -> exit 1 RETIRED
#   F1 golden-FALSE script + doc both edited in the working tree         -> exit 0
#   F2 golden-FALSE a pre-existing violation listed in the baseline      -> exit 0 BASELINED
#   F3 golden-FALSE a .sh outside scripts/ (tests/) is out of scope       -> exit 0
#   F4 collation    locale-sensitive baseline keys + one NEW row under a
#                   non-C caller locale -> exactly that NEW row, no warning
#   B1 fail-closed  zero scripts under scripts/ (blind)                  -> exit 2
#   B2 fail-closed  not a git repository                                 -> exit 2
#   M1 paired mutation: the doc-existence check neutered -> R1 catches it
#
# Usage: bash tests/pre_build/test_check_cm_script_docs_sync.sh
# Constitution: §1.1, §11.4.18, §11.4.107(10), §11.4.135(5), §11.4.201(1)(6), §11.4.224.

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
GATE="${REPO}/scripts/pre_build/check_cm_script_docs_sync.sh"
PASS=0; FAIL=0
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT   # §11.4.14 cleanup on every exit path

# commit with an explicit, increasing timestamp so ordering never depends on
# the wall clock resolution.
TS_FILE="${TMP}/.ts"; echo 1700000000 > "${TS_FILE}"   # file, not a variable: mk_repo runs in $(...)
gc() {  # <repo> <message>
    local TS; TS=$(( $(cat "${TS_FILE}") + 100 )); echo "${TS}" > "${TS_FILE}"
    GIT_AUTHOR_DATE="@${TS} +0000" GIT_COMMITTER_DATE="@${TS} +0000" \
        git -C "$1" -c user.email=t@t -c user.name=t commit -qm "$2"
}

mk_repo() {  # <name> : one script + its doc, committed together; empty baseline
    local r="${TMP}/$1"
    mkdir -p "${r}/scripts/pre_build" "${r}/docs/scripts"
    printf '#!/usr/bin/env bash\necho a\n' > "${r}/scripts/a.sh"
    printf '# a.sh\n\n**Revision:** 1\n**Last modified:** 2026-01-01T00:00:00Z\n' > "${r}/docs/scripts/a.md"
    printf '# baseline\n' > "${r}/scripts/pre_build/cm_script_docs_sync.baseline"
    git -C "${r}" init -q && git -C "${r}" add -A && gc "${r}" init
    echo "${r}"
}

arm() {  # <label> <want-rc> <needle-or-empty> <gate> <args...>
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

echo "CM-SCRIPT-DOCS-SYNC — arms"

r="$(mk_repo g1)"
arm "G1 golden-GOOD script and doc committed together" 0 "OK:" "${GATE}" "${r}"

r="$(mk_repo r1)"
printf '#!/usr/bin/env bash\n' > "${r}/scripts/b.sh"; git -C "${r}" add -A; gc "${r}" b
arm "R1 golden-BAD script without a companion doc is a NEW finding" 1 "NEW NODOC:scripts/b.sh" "${GATE}" "${r}"
R1_REPO="${r}"

r="$(mk_repo r2)"
printf 'echo changed\n' >> "${r}/scripts/a.sh"; git -C "${r}" add -A; gc "${r}" change-a
arm "R2 golden-BAD script committed after its doc is a NEW finding" 1 "NEW DOCBEHIND:scripts/a.sh" "${GATE}" "${r}"

r="$(mk_repo r3)"
printf 'echo dirty\n' >> "${r}/scripts/a.sh"
arm "R3 golden-BAD script edited in the working tree without its doc" 1 "NEW DOCBEHIND:scripts/a.sh" "${GATE}" "${r}"

r="$(mk_repo r4)"
printf 'NODOC:scripts/gone.sh\n' >> "${r}/scripts/pre_build/cm_script_docs_sync.baseline"
arm "R4 ratchet: a baseline row with no matching finding must be deleted" 1 "RETIRED NODOC:scripts/gone.sh" "${GATE}" "${r}"

r="$(mk_repo f1)"
printf 'echo dirty\n' >> "${r}/scripts/a.sh"; printf '\nmore\n' >> "${r}/docs/scripts/a.md"
arm "F1 golden-FALSE script and doc edited together in the working tree" 0 "OK:" "${GATE}" "${r}"

r="$(mk_repo f2)"
printf '#!/usr/bin/env bash\n' > "${r}/scripts/old.sh"
printf 'NODOC:scripts/old.sh\n' >> "${r}/scripts/pre_build/cm_script_docs_sync.baseline"
git -C "${r}" add -A; gc "${r}" old
arm "F2 golden-FALSE a violation already in the baseline snapshot passes" 0 "BASELINED NODOC:scripts/old.sh" "${GATE}" "${r}"

r="$(mk_repo f3)"
mkdir -p "${r}/tests"; printf '#!/usr/bin/env bash\n' > "${r}/tests/test_x.sh"; git -C "${r}" add -A; gc "${r}" t
arm "F3 golden-FALSE a script outside scripts/ is out of scope" 0 "OK:" "${GATE}" "${r}"

# F4: collation. Baseline rows whose order differs between the C and en_US
# locales (the real pair that tripped it: run_all_challenges vs run-tests),
# plus one unpairable NEW finding — comm only checks order when a line is
# unpairable, which is exactly when a mis-merge would misclassify rows.
# Observed live 2026-09-26 before LC_ALL=C was pinned: "comm: file 1 is not in
# sorted order" (comm then runs on undefined input order).
r="$(mk_repo f4)"
for n in run_all_x run-t a-z a_b; do printf '#!/usr/bin/env bash\n' > "${r}/scripts/${n}.sh"; printf 'NODOC:scripts/%s.sh\n' "${n}" >> "${r}/scripts/pre_build/cm_script_docs_sync.baseline"; done
printf '#!/usr/bin/env bash\n' > "${r}/scripts/z_new.sh"
git -C "${r}" add -A; gc "${r}" f4
out="$(LC_ALL=en_US.UTF-8 bash "${GATE}" "${r}" 2>&1)"; rc=$?
if [[ "${rc}" -eq 1 ]] && [[ "$(grep -c '^NEW ' <<<"${out}")" -eq 1 ]] && grep -q '^NEW NODOC:scripts/z_new.sh' <<<"${out}" \
   && ! grep -q '^RETIRED ' <<<"${out}" && ! grep -q "not in sorted order" <<<"${out}"; then
    echo "  PASS  F4 locale-sensitive baseline under a non-C caller locale: exactly the one NEW row, no RETIRED, no order warning (exit 1)"; PASS=$((PASS+1))
else
    echo "  FAIL  F4 locale-sensitive keys misdiffed: exit ${rc}"; sed 's/^/          /' <<<"${out}"; FAIL=$((FAIL+1))
fi

r="${TMP}/b1"; mkdir -p "${r}/docs"; printf 'x\n' > "${r}/docs/x.md"
git -C "${r}" init -q && git -C "${r}" add -A && gc "${r}" init
arm "B1 fail-closed: zero scripts enumerated is BLIND, never clean" 2 "BLIND" "${GATE}" "${r}"

mkdir -p "${TMP}/notgit"
arm "B2 fail-closed: not a git repository" 2 "not a git repository" "${GATE}" "${TMP}/notgit"

MUT="${TMP}/mutated_gate.sh"
sed 's/if \[\[ ! -f "\${ROOT}\/\${doc}" \]\]; then/if false; then/' "${GATE}" > "${MUT}"
if ! grep -qF "NEW NODOC:scripts/b.sh" <<<"$(bash "${GATE}" "${R1_REPO}" 2>&1)"; then
    echo "  FAIL  M1 precondition: the unmutated gate does not report R1, so the mutation proves nothing"; FAIL=$((FAIL+1))
elif cmp -s "${MUT}" "${GATE}"; then
    echo "  FAIL  M1 mutation sed did not change the gate copy"; FAIL=$((FAIL+1))
else
    out="$(bash "${MUT}" "${R1_REPO}" 2>&1)"; rc=$?
    if ! grep -qF "NEW NODOC:scripts/b.sh" <<<"${out}"; then
        echo "  PASS  M1 mutated gate (doc-existence check neutered) no longer reports R1 — R1's assertion catches it"; PASS=$((PASS+1))
    else
        echo "  FAIL  M1 mutated gate still reports NODOC — the mutation is not load-bearing"; FAIL=$((FAIL+1))
    fi
fi

echo "RESULT: ${PASS} passed, ${FAIL} failed"
[[ "${FAIL}" -eq 0 ]]
