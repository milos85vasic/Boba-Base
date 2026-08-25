#!/usr/bin/env bash
# check_cm_workable_items_binary_fresh.sh — CM-WORKABLE-ITEMS-BINARY-FRESH (BOB-188)
#
# Purpose: the workable-items Go binary is SHIPPED (git-tracked at
# constitution/scripts/workable-items/bin/) so consumers that inherit the
# constitution by reference can run it without a Go toolchain. That makes it a
# distribution artifact, and a distribution artifact can go STALE against the
# source it was built from — which is exactly what BOB-188 was.
#
# WHY THIS GATE EXISTS (the forensic, so nobody deletes it as ceremony):
#   pre_build_verification.sh invariant 17 resolves the binary through a
#   candidate loop whose FIRST entry is bin/workable-items. That file is TRACKED
#   and executable, so it WINS over the freshly-built untracked sibling. On
#   2026-08-25 the tracked binary was six days older than its own source and did
#   not contain the guards that source had gained:
#
#     string                                      source  tracked-bin  current-bin
#     "refusing to set terminal status"              1         0            1
#     "Issues-location item has TERMINAL status"     1         0            1
#     NEEDLE "workable-items" (strings(1) sees)      -        34           34
#
#   The needle is load-bearing: 34 hits in BOTH binaries prove strings(1) reads
#   both equally, so those zeros are REAL ABSENCES and not a blind instrument
#   (§11.4.201(7)(b)). A check whose message string is absent from the binary
#   cannot fire — the gate meant to catch ten un-migrated terminal-status rows
#   was running a binary structurally incapable of seeing them.
#
# Usage:   bash scripts/pre_build/check_cm_workable_items_binary_fresh.sh
# Inputs:  constitution/scripts/workable-items/{**/*.go,go.mod,go.sum}
# Outputs: exit 0 = binary matches its sources (or honestly absent);
#          exit 1 = STALE, or the input scan went BLIND.
# Side-effects: none. Reads only.
#
# Constitution: §11.4.108 (SOURCE->ARTIFACT layer — this gate IS layer 2 for a
# tracked artifact), §11.4.201(6)(7)(b) (a zero is not evidence until a needle
# proves the instrument sees), §11.4.86 (content fingerprint, never mtime),
# §11.4.30 (the §11.4.30 build-artifact question this raises is OPERATOR-owned
# and recorded in BOB-188 — this gate does not pre-empt it, it makes the
# staleness impossible while the decision is pending).

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WI_DIR="${PROJECT_ROOT}/constitution/scripts/workable-items"
BIN="${WI_DIR}/bin/workable-items"
FINGERPRINT="${WI_DIR}/bin/.source.sha256"

if [[ ! -d "${WI_DIR}" ]]; then
    echo "SKIP: ${WI_DIR} not present (constitution submodule not checked out)"
    exit 0
fi

# Content fingerprint of every build input, sorted for determinism (§11.4.86 —
# content hash, NEVER mtime: a touch must not clear staleness, and a revert must).
mapfile -t INPUTS < <(cd "${WI_DIR}" && find . -name '*.go' -not -path './bin/*' -print | sort)
for extra in go.mod go.sum; do
    [[ -f "${WI_DIR}/${extra}" ]] && INPUTS+=("./${extra}")
done

# §11.4.201(6) BLIND-OR-EMPTY guard: zero inputs is NEVER "clean". A find that
# returns nothing and a source tree with no Go in it are the same quiet zero,
# and only one of them is honest.
if (( ${#INPUTS[@]} == 0 )); then
    echo "FAIL: source scan found 0 build inputs under ${WI_DIR} — the instrument is BLIND, not the tree clean"
    exit 1
fi

LIVE="$(cd "${WI_DIR}" && printf '%s\n' "${INPUTS[@]}" | sort | xargs -r sha256sum | sha256sum | cut -d' ' -f1)"

if [[ ! -f "${BIN}" ]]; then
    echo "SKIP: ${BIN} not present — nothing shipped, nothing to be stale (§11.4.69 artifact_not_yet_built)"
    exit 0
fi

if [[ ! -f "${FINGERPRINT}" ]]; then
    echo "FAIL: ${BIN} is shipped but carries NO source fingerprint at ${FINGERPRINT}"
    echo "      An unfingerprinted shipped binary cannot be proven fresh, and BOB-188 is what that costs."
    echo "      Remediation: rebuild + record — see docs/scripts/check_cm_workable_items_binary_fresh.md"
    exit 1
fi

RECORDED="$(tr -d '[:space:]' < "${FINGERPRINT}")"

if [[ "${LIVE}" != "${RECORDED}" ]]; then
    echo "FAIL: shipped workable-items binary is STALE against its sources"
    echo "      recorded (at build time): ${RECORDED}"
    echo "      live     (sources now)  : ${LIVE}"
    echo "      inputs scanned          : ${#INPUTS[@]}"
    echo "      A stale TRACKED binary wins the invariant-17 candidate loop on every"
    echo "      fresh clone, so the gate runs code that predates its own guards."
    echo "      Remediation: cd ${WI_DIR} && go build -o bin/workable-items ./cmd/workable-items"
    echo "                   then re-record the fingerprint (see the companion doc)."
    exit 1
fi

echo "PASS: shipped workable-items binary matches its ${#INPUTS[@]} build inputs (${LIVE:0:12})"
exit 0
