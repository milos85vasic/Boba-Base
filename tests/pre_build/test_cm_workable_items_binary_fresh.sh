#!/usr/bin/env bash
# test_cm_workable_items_binary_fresh.sh — paired §1.1 mutations for
# CM-WORKABLE-ITEMS-BINARY-FRESH (BOB-188).
#
# Every mutation runs in a TEMP FIXTURE TREE, never the real checkout: the gate
# derives PROJECT_ROOT from its own location, so copying it into a scratch tree
# gives full mutation freedom with zero §11.4.84 residue risk — which matters
# because this suite is expected to run while other agents hold the real tree.
#
# Cases (§11.4.201(10)/(7)(b) — the golden-FALSE ones are as load-bearing as the
# golden-TRUEs; a gate that cannot stay silent on a clean tree is a FAIL-bluff):
#   M1 golden-TRUE  source content changes        -> FAIL "STALE"
#   M2 golden-TRUE  fingerprint deleted           -> FAIL "NO source fingerprint"
#   M3 golden-TRUE  input scan blinded (0 inputs) -> FAIL "BLIND"
#   M4 golden-FALSE clean, fresh, fingerprinted   -> PASS   (false-positive guard)
#   M5 golden-FALSE mtime-only touch, same bytes  -> PASS   (content-hash, not mtime)
#   M6 golden-FALSE binary absent entirely        -> PASS   (honest artifact_not_yet_built)
#
# Usage: bash tests/pre_build/test_cm_workable_items_binary_fresh.sh
# Constitution: §1.1, §11.4.86, §11.4.107(10), §11.4.108, §11.4.201, §11.4.224.

set -uo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
GATE_REL="scripts/pre_build/check_cm_workable_items_binary_fresh.sh"
WI_REL="constitution/scripts/workable-items"
PASS=0; FAIL=0

TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT   # §11.4.14 cleanup on every exit path

# Build the fixture tree: the gate + a minimal but REAL workable-items layout.
mkdir -p "${TMP}/scripts/pre_build" "${TMP}/${WI_REL}/bin" "${TMP}/${WI_REL}/cmd/workable-items"
cp "${PROJECT_ROOT}/${GATE_REL}" "${TMP}/scripts/pre_build/"
printf 'package main\nfunc main() {}\n' > "${TMP}/${WI_REL}/cmd/workable-items/main.go"
printf 'module fixture\n\ngo 1.21\n' > "${TMP}/${WI_REL}/go.mod"
printf 'fixture-binary\n' > "${TMP}/${WI_REL}/bin/workable-items"
chmod +x "${TMP}/${WI_REL}/bin/workable-items"

record_fingerprint() {
    ( cd "${TMP}/${WI_REL}" || exit 1
      mapfile -t I < <(find . -name '*.go' -not -path './bin/*' -print | sort)
      [[ -f go.mod ]] && I+=("./go.mod")
      [[ -f go.sum ]] && I+=("./go.sum")
      printf '%s\n' "${I[@]}" | sort | xargs -r sha256sum | sha256sum | cut -d' ' -f1 \
        > bin/.source.sha256 )
}

run_gate() { bash "${TMP}/scripts/pre_build/$(basename "${GATE_REL}")" 2>&1; }

check() {  # name  expected_exit  expected_substring
    local name="$1" want_exit="$2" want_str="$3" out rc
    out="$(run_gate)"; rc=$?
    if [[ "${rc}" -eq "${want_exit}" ]] && grep -qF "${want_str}" <<<"${out}"; then
        echo "  PASS  ${name} (exit=${rc}, matched \"${want_str}\")"; PASS=$((PASS+1))
    else
        echo "  FAIL  ${name}: wanted exit=${want_exit} + \"${want_str}\", got exit=${rc}"
        sed 's/^/          /' <<<"${out}"; FAIL=$((FAIL+1))
    fi
}

echo "CM-WORKABLE-ITEMS-BINARY-FRESH — paired §1.1 mutations"

record_fingerprint
check "M4 golden-FALSE clean fresh tree stays silent" 0 "PASS: shipped workable-items binary matches"

touch "${TMP}/${WI_REL}/cmd/workable-items/main.go"
check "M5 golden-FALSE mtime-only touch does not fire" 0 "PASS: shipped workable-items binary matches"

printf 'package main\nfunc main() { _ = 1 }\n' > "${TMP}/${WI_REL}/cmd/workable-items/main.go"
check "M1 golden-TRUE source content change -> STALE" 1 "is STALE against its sources"

record_fingerprint   # back to fresh
check "M4b golden-FALSE re-record clears the staleness" 0 "PASS: shipped workable-items binary matches"

rm -f "${TMP}/${WI_REL}/bin/.source.sha256"
check "M2 golden-TRUE fingerprint deleted -> unprovable" 1 "carries NO source fingerprint"

record_fingerprint
# The sources must move OUTSIDE the scanned tree. Renaming them to a DOTTED
# sibling in place does NOT blind the scan -- `find .` descends into dotted
# directories, so `.cmd-hidden/workable-items/main.go` still matches `*.go`.
# The first draft of this mutation did exactly that and the gate correctly
# reported "inputs scanned: 1 / STALE" instead of BLIND: the instrument was
# wrong, not the thing measured (§11.4.201 -- the mutation is itself a
# measurement and gets no exemption from that rule).
mkdir -p "${TMP}/parked"
mv "${TMP}/${WI_REL}/cmd" "${TMP}/parked/cmd"
mv "${TMP}/${WI_REL}/go.mod" "${TMP}/parked/go.mod"
check "M3 golden-TRUE blinded scan -> BLIND not clean" 1 "the instrument is BLIND"
mv "${TMP}/parked/cmd" "${TMP}/${WI_REL}/cmd"
mv "${TMP}/parked/go.mod" "${TMP}/${WI_REL}/go.mod"

record_fingerprint
rm -f "${TMP}/${WI_REL}/bin/workable-items"
check "M6 golden-FALSE no binary -> honest skip" 0 "nothing shipped, nothing to be stale"

echo
echo "  ${PASS} passed, ${FAIL} failed"
[[ "${FAIL}" -eq 0 ]]
