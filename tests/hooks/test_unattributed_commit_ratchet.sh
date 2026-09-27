#!/usr/bin/env bash
# test_unattributed_commit_ratchet.sh — executing test for the one-time
# ratchet adoption of scripts/hooks/unattributed-commit-guard.sh (BOB-162,
# operator decision: option (b), monotone-decrease ratchet).
#
# Purpose:
#   Prove, in disposable mktemp git repositories only (the real history is
#   read, never written), that the guard's --baseline mode
#     (a) passes a history whose only unattributed commits are the exact
#         grandfathered SHAs in the baseline,
#     (b) FAILS a NEW unattributed commit on top — including one that reuses
#         a grandfathered subject line word for word,
#     (c) refuses the two ways of hiding (b) by editing the baseline: adding
#         the new SHA without raising SEEDED_COUNT, and adding it while also
#         raising SEEDED_COUNT (the row is newer than SEED_CUTOFF_EPOCH),
#     (d) FAILS a RETIRED row (a baselined SHA inside the scanned range that
#         is no longer a violation), so the set can only be edited downward
#         in step with reality,
#     (e) fails closed (exit 2) on a baseline without its seed header,
#   and that the paired §1.1 mutation — blanking the NEW-set computation in a
#   copy of the guard — makes (b) pass wrongly, so the check is load-bearing.
#   Finally the REAL repository is scanned the way pre-build invariant 63
#   scans it, and must pass against the checked-in baseline.
#
# Usage:   bash tests/hooks/test_unattributed_commit_ratchet.sh
# Exit:    0 all assertions passed; 1 any failed; 2 harness error.
# Side-effects: creates and removes mktemp directories only.
# Cross-references: scripts/hooks/unattributed-commit-guard.sh,
#   scripts/pre_build/cm_unattributed_commit.baseline,
#   docs/scripts/unattributed-commit-guard.md, scripts/pre_build_verification.sh
#   invariant 63. Constitution: §11.4.135(5), §11.4.224(E), §11.4.201(1),
#   §11.4.115, §1.1.

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${HERE}/../.." && pwd)"
GUARD="${PROJECT_ROOT}/scripts/hooks/unattributed-commit-guard.sh"
REAL_BASELINE="${PROJECT_ROOT}/scripts/pre_build/cm_unattributed_commit.baseline"

PASS_COUNT=0; FAIL_COUNT=0
pass() { PASS_COUNT=$((PASS_COUNT + 1)); echo "  PASS: $1"; }
fail() { FAIL_COUNT=$((FAIL_COUNT + 1)); echo "  FAIL: $1"; }

[[ -f "${GUARD}" ]] || { echo "FATAL: guard missing at ${GUARD}" >&2; exit 2; }

SCRATCH="$(mktemp -d)"
trap 'rm -rf "${SCRATCH}"' EXIT
REPO="${SCRATCH}/repo"

# Commit with a fixed committer/author date so the cutoff arithmetic is exact.
_commit() {  # <iso-date> <message...>
    local d="$1"; shift
    GIT_AUTHOR_DATE="$d" GIT_COMMITTER_DATE="$d" git -C "${REPO}" commit -q --allow-empty "$@"
}
_run() {  # <guard-path> <baseline> -> sets RC and OUT
    RC=0
    OUT="$(cd "${REPO}" && bash "$1" --range HEAD --baseline "$2" 2>&1)" || RC=$?
}

git init -q -b main "${REPO}"
git -C "${REPO}" config user.email "test@example.invalid"
git -C "${REPO}" config user.name "test"
_commit "2026-01-01T00:00:00Z" -m "root: seed"
_commit "2026-01-02T00:00:00Z" -m "Auto-commit";                 G1="$(git -C "${REPO}" rev-parse HEAD)"
_commit "2026-01-03T00:00:00Z" -m "feat: real change (ATM-500)"; ATTR="$(git -C "${REPO}" rev-parse HEAD)"
_commit "2026-01-04T00:00:00Z" -m "Auto-commit";                 G2="$(git -C "${REPO}" rev-parse HEAD)"
_commit "2026-01-05T00:00:00Z" -m "sync: nightly mirror";        G3="$(git -C "${REPO}" rev-parse HEAD)"
_commit "2026-01-06T00:00:00Z" -m "Auto-commit 1767657600000";   G4="$(git -C "${REPO}" rev-parse HEAD)"
CUTOFF="$(date -u -d '2026-02-01T00:00:00Z' +%s)"

_write_baseline() {  # <file> <seeded-count> <sha...>
    local f="$1" n="$2"; shift 2
    {
        echo "# fixture baseline"
        echo "# SEED_CUTOFF_EPOCH: ${CUTOFF}"
        echo "# SEEDED_COUNT: ${n}"
        local s; for s in "$@"; do echo "${s} fixture"; done
    } > "$f"
}
B="${SCRATCH}/base.txt"
_write_baseline "$B" 4 "$G1" "$G2" "$G3" "$G4"

echo "[a] grandfathered history only"
_run "${GUARD}" "$B"
if [[ "${RC}" -eq 0 ]]; then pass "(a) 4 grandfathered commits, exit 0"; else fail "(a) expected exit 0, got ${RC}: ${OUT}"; fi
if grep -q "4 baselined" <<<"${OUT}"; then pass "(a) reports 4 baselined"; else fail "(a) baselined count not reported: ${OUT}"; fi

echo "[a2] the same history WITHOUT a baseline still fails (the ratchet is opt-in per seam)"
RC=0; OUT="$(cd "${REPO}" && bash "${GUARD}" --range HEAD 2>&1)" || RC=$?
if [[ "${RC}" -eq 1 ]]; then pass "(a2) no --baseline: exit 1"; else fail "(a2) expected exit 1, got ${RC}"; fi

echo "[b] a NEW unattributed commit reusing a grandfathered subject"
_commit "2026-03-01T00:00:00Z" -m "Auto-commit"; NEW1="$(git -C "${REPO}" rev-parse HEAD)"
_run "${GUARD}" "$B"
if [[ "${RC}" -eq 1 ]]; then pass "(b) new bare commit on top: exit 1"; else fail "(b) expected exit 1, got ${RC}: ${OUT}"; fi
if grep -q "NEW ${NEW1}" <<<"${OUT}"; then pass "(b) the new SHA is named as NEW"; else fail "(b) new SHA not named: ${OUT}"; fi
if grep -q "NEW ${G1}" <<<"${OUT}"; then fail "(b) a grandfathered SHA was reported NEW"; else pass "(b) grandfathered SHAs are not reported NEW"; fi

echo "[c1] hiding attempt: add the new SHA to the baseline, count unchanged"
B2="${SCRATCH}/base2.txt"; _write_baseline "$B2" 4 "$G1" "$G2" "$G3" "$G4" "$NEW1"
_run "${GUARD}" "$B2"
if [[ "${RC}" -eq 1 ]] && grep -q "exceeds SEEDED_COUNT" <<<"${OUT}"; then pass "(c1) baseline grown past SEEDED_COUNT: exit 1"; else fail "(c1) expected exit 1 naming SEEDED_COUNT, got ${RC}: ${OUT}"; fi

echo "[c2] hiding attempt: add the new SHA AND raise SEEDED_COUNT"
B3="${SCRATCH}/base3.txt"; _write_baseline "$B3" 5 "$G1" "$G2" "$G3" "$G4" "$NEW1"
_run "${GUARD}" "$B3"
if [[ "${RC}" -eq 1 ]] && grep -q "newer than SEED_CUTOFF_EPOCH" <<<"${OUT}"; then pass "(c2) row newer than the seed cutoff: exit 1"; else fail "(c2) expected exit 1 naming SEED_CUTOFF_EPOCH, got ${RC}: ${OUT}"; fi

echo "[d] a RETIRED row (in range, pre-cutoff, but not a violation)"
git -C "${REPO}" reset -q --hard "${G4}"   # scratch repo only: drop NEW1 again
B4="${SCRATCH}/base4.txt"; _write_baseline "$B4" 5 "$G1" "$G2" "$G3" "$G4" "$ATTR"
_run "${GUARD}" "$B4"
if [[ "${RC}" -eq 1 ]] && grep -q "RETIRED ${ATTR}" <<<"${OUT}"; then pass "(d) retired row: exit 1, named"; else fail "(d) expected exit 1 naming RETIRED, got ${RC}: ${OUT}"; fi

echo "[e] baseline without its seed header fails closed"
B5="${SCRATCH}/base5.txt"; printf '%s x\n' "$G1" "$G2" "$G3" "$G4" > "$B5"
_run "${GUARD}" "$B5"
if [[ "${RC}" -eq 2 ]]; then pass "(e) headerless baseline: exit 2"; else fail "(e) expected exit 2, got ${RC}: ${OUT}"; fi

echo "[m] paired §1.1 mutation: blank the NEW-set computation"
MUT="${SCRATCH}/guard_mutated.sh"
sed 's/^\( *\)NEW_SHAS="\$(comm -23 .*# RATCHET-NEW-SET$/\1NEW_SHAS=""  # MUTATED/' "${GUARD}" > "${MUT}"
if grep -q '# MUTATED' "${MUT}"; then
    _commit "2026-03-01T00:00:00Z" -m "Auto-commit"
    _run "${GUARD}" "$B";   ORIG_RC="${RC}"
    _run "${MUT}" "$B";     MUT_RC="${RC}"
    if [[ "${ORIG_RC}" -eq 1 && "${MUT_RC}" -eq 0 ]]; then
        pass "(m) unmutated guard refuses the new commit (1); mutated guard wrongly passes it (0) — the NEW check is load-bearing"
    else
        fail "(m) expected original=1 mutated=0, got original=${ORIG_RC} mutated=${MUT_RC}"
    fi
else
    fail "(m) mutation did not apply — the RATCHET-NEW-SET marker line is missing from the guard"
fi

echo "[r] the real repository, scanned exactly as pre-build invariant 63 scans it"
if [[ -f "${REAL_BASELINE}" ]]; then
    RC=0; OUT="$(cd "${PROJECT_ROOT}" && bash "${GUARD}" --range HEAD --baseline "${REAL_BASELINE}" 2>&1)" || RC=$?
    if [[ "${RC}" -eq 0 ]]; then pass "(r) real HEAD history vs checked-in baseline: exit 0 — $(tail -n1 <<<"${OUT}")"; else fail "(r) real scan exited ${RC}: ${OUT}"; fi
else
    fail "(r) checked-in baseline missing at ${REAL_BASELINE}"
fi

echo
echo "=== Result: ${PASS_COUNT} passed, ${FAIL_COUNT} failed ==="
[[ "${FAIL_COUNT}" -eq 0 ]]
