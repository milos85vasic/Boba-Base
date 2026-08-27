#!/usr/bin/env bash
# test_ownership_gid_agreement.sh — BOB-207 RED, now GREEN as a standing guard.
#
# §11.4.115 POLARITY: this file was authored as the RED that reproduced the
# defect (probe says ok / repair says broken on the same location). The fix
# landed — ownership_repair.sh's walk now selects on uid, matching the probe —
# so the SAME source now passes and serves as the permanent regression guard
# (§11.4.135). It is green because the defect is fixed, not because it stopped
# asserting: reverting the one-line predicate restores the original failure
# verbatim (evidence: docs/qa/BOB-207/runs/mutation_revert_predicate.txt), and
# it also kills the complementary wrong definition (a walk selecting on gid
# alone), which the repair suite does not detect.
#
# Feature      : 002-user-owned-downloads
# Under test   : scripts/lib/ownership.sh   probe_location()   (the PRECONDITION)
#                scripts/ownership_repair.sh                   (the REPAIR)
# Requirements : FR-001, FR-002, FR-003, FR-010, FR-010b
# Governance   : §11.4.115 (RED on the broken artifact), §11.4.201(1)
#                (golden-FALSE / no false-positive refusal), §11.4.250
#                (a tower of disagreeing halves signals a primitive defect),
#                §11.4.14 (cleanup on every exit path via trap).
#
# ===========================================================================
# WHAT THIS ASSERTS, AND WHY IT IS NOT "probe_location must call stat -c %g"
# ===========================================================================
# BOB-207 was filed as "the probe is gid-blind". That is a true observation,
# but it is an IMPLEMENTATION fact, and a test written against it would (a) be
# satisfied by any cosmetic change that reads %g without acting on it, and
# (b) hard-wire ONE of the two legitimate repairs — forcing the probe to widen
# even if the correct resolution is for the repair to narrow.
#
# The DEFECT, stated at the layer the user experiences it, is that the two
# halves of this feature DISAGREE ABOUT WHICH PROPERTY THEY MEAN:
#
#   probe_location()          treats a location as correct on uid alone
#   ownership_repair.sh       treats an item as needing repair on uid OR gid
#
# So the precondition can certify a location that the repair — running over
# that same location, from the same declared scope, in the same process tree —
# reports as broken. One of them is wrong, and until they agree, whichever one
# the operator happens to read is not a fact about the system.
#
# THE INVARIANT UNDER TEST (implementation-agnostic, user-observable):
#
#   For any location L, probe_location(L) returns `ok`
#   IF AND ONLY IF
#   ownership_repair.sh --dry-run reports zero items needing repair for L.
#
# This FAILS today on a gid-mismatched location, and PASSES under EITHER
# legitimate fix:
#   * widen the probe   -> probe refuses, repair selects   -> both say broken
#   * narrow the repair -> probe says ok, repair selects 0 -> both say correct
# It cannot be satisfied by reading %g and ignoring it, and it cannot be
# satisfied by making either side always-refuse (case GF-1 forbids that).
#
# ===========================================================================
# THE FIXTURE, AND WHY IT IS A gid MISMATCH RATHER THAN THE PRODUCTION uid ONE
# ===========================================================================
# The production defect is a uid mismatch (rootless-podman subuid 100999 vs the
# operator's 1000). A unit test runs UNPRIVILEGED and MUST NOT use sudo, and a
# foreign host uid is not constructible unprivileged — measured and recorded in
# tests/unit/test_ownership_repair.sh:19-45, not re-derived here.
#
# A gid mismatch IS constructible unprivileged, with two ordinary commands, on
# an ordinary filesystem: chgrp a directory to a SUPPLEMENTARY group the
# operator already belongs to, and set its setgid bit. Files created inside
# then inherit that group. Both commands are permitted to the directory's owner
# for a group they are a member of — no privilege, no mount, no loopback.
#
# §11.4.115(G) PRECONDITION PROVENANCE: **observed**, not constructed. This is
# not a hand-built precondition standing in for a defect traced elsewhere — the
# disagreement it exposes is between two shipped code paths, and the fixture
# only supplies a location on which they are made to answer the same question.
#
# HOST REQUIREMENTS. The operator must belong to at least one supplementary
# group, and the filesystem under TMPDIR must honour setgid inheritance. Both
# are checked and reported as an honest SKIP-with-reason (§11.4.3) rather than
# silently passing, because a suite that cannot build its fixture has proven
# nothing and must not report that it has.
#
# §11.4.263: this suite signals no processes — no kill/pkill/killpg anywhere.

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${HERE}/../.." && pwd)"
# The two targets default to the SHIPPED paths. The overrides exist so a
# candidate fix can be validated against this suite BEFORE it is applied to the
# working tree (§11.4.115: a RED must be shown to go GREEN under the fix, and
# on a dirty tree the only honest way to show that is to run the fix from a
# copy). They are never set by any gate or runner — an unset environment gives
# the shipped code, so this cannot become a way to test something else and
# report it as the product.
LIB="${BOB207_LIB_UNDER_TEST:-${PROJECT_ROOT}/scripts/lib/ownership.sh}"
REPAIR="${BOB207_REPAIR_UNDER_TEST:-${PROJECT_ROOT}/scripts/ownership_repair.sh}"
if [[ -n "${BOB207_LIB_UNDER_TEST:-}${BOB207_REPAIR_UNDER_TEST:-}" ]]; then
    echo "  NOTE: running against OVERRIDDEN targets (candidate-fix validation), not the shipped tree:"
    echo "        lib    = ${LIB}"
    echo "        repair = ${REPAIR}"
fi

PASS=0; FAIL=0; SKIP=0
pass() { PASS=$((PASS+1)); echo "  PASS: $1"; }
fail() { FAIL=$((FAIL+1)); echo "  FAIL: $1"; }
skip() { SKIP=$((SKIP+1)); echo "  SKIP: $1"; }
finish() {
    echo "RESULT: $PASS passed, $FAIL failed, $SKIP skipped"
    [ "$FAIL" -eq 0 ] || exit 1
    exit 0
}

echo "== BOB-207: precondition/repair agreement on the ownership property =="

# ── target prechecks: name what is missing, never guess ────────────────────
[[ -f "$LIB" ]]    || { fail "target missing: scripts/lib/ownership.sh";    echo "       looked for: $LIB" >&2;    finish; }
[[ -f "$REPAIR" ]] || { fail "target missing: scripts/ownership_repair.sh"; echo "       looked for: $REPAIR" >&2; finish; }

# shellcheck source=/dev/null
source "$LIB"

OP_UID="$(id -u)"; OP_GID="$(id -g)"

# ── §11.4.14 cleanup on EVERY exit path, including interrupts ──────────────
WORK=""
cleanup() { local rc=$?; [[ -n "$WORK" && -d "$WORK" ]] && rm -rf "$WORK"; exit "$rc"; }
trap cleanup EXIT INT TERM HUP

WORK="$(mktemp -d "${TMPDIR:-/tmp}/bob207.XXXXXXXX")" || { fail "harness: mktemp -d failed"; finish; }

# ── fixture feasibility, checked not assumed (§11.4.3 honest SKIP) ─────────
ALT_GID=""
for g in $(id -G); do [[ "$g" != "$OP_GID" ]] && { ALT_GID="$g"; break; }; done
if [[ -z "$ALT_GID" ]]; then
    skip "fixture: operator belongs to no supplementary group — a gid mismatch is not constructible here"
    finish
fi
ALT_NAME="$(getent group "$ALT_GID" 2>/dev/null | cut -d: -f1)"; ALT_NAME="${ALT_NAME:-<numeric>}"

# ── the two verdict readers, each returning ONE word ───────────────────────
# probe verdict: whatever probe_location() echoes ("ok" | "wrong-owner:N" | ...)
probe_verdict() {
    local v
    if v="$(probe_location "$1" 2>/dev/null)"; then :; fi
    printf '%s' "${v:-<no-verdict>}"
}

# repair verdict: "clean" when --dry-run selects zero items under L, else
# "selects:<n>". Reads the repair's own decision through its real CLI — never a
# re-implementation of its find predicate, which would test this harness's copy
# of the rule instead of the rule (§11.4.201(11): probe the artifact through its
# real invocation path).
repair_verdict() {
    local root="$1" scope="$2" state="$3" out n
    out="$(OWNERSHIP_REPAIR_RENICED=1 nice -n 19 bash "$REPAIR" --dry-run --force \
             --scope "$scope" --state-dir "$state" 2>&1)" || true
    n="$(printf '%s\n' "$out" | grep -c 'would chown')"
    [[ "$n" -eq 0 ]] && { printf 'clean'; return; }
    printf 'selects:%s' "$n"
}

write_scope() {  # write_scope <scope-file> <root>
    cat > "$1" <<YAML
schema_version: 1
paths:
  - path: $2
    kind: downloads
    optional: false
    preserve_mode: false
    recursive: true
YAML
}

# ===========================================================================
# NEEDLE — prove probe_location() CAN refuse before trusting any `ok` it emits.
# A probe stuck at `ok` would make every case below pass for the wrong reason
# (§11.4.201(7)(b): a null is not evidence until the instrument is shown to see).
# ===========================================================================
NV="$(probe_verdict "${WORK}/definitely-absent")"
if [[ "$NV" == "ok" ]]; then
    fail "needle: probe_location returned ok for a path that does not exist — the probe cannot refuse, so no ok below is evidence"
    finish
fi
pass "needle: probe_location refuses an absent path (verdict '${NV}') — it is capable of saying no"

# ===========================================================================
# CASE 1 (THE RED) — a location whose files land with the operator's uid but a
# DIFFERENT gid. Both halves are asked about the same directory.
# ===========================================================================
R1="${WORK}/case1"; L1="${R1}/library"; mkdir -p "$L1" "${WORK}/state1"
if ! chgrp "$ALT_GID" "$L1" 2>/dev/null; then
    skip "case 1: chgrp to supplementary group ${ALT_NAME}(${ALT_GID}) refused — fixture not constructible"
    finish
fi
if ! chmod g+s "$L1" 2>/dev/null; then
    skip "case 1: chmod g+s refused — fixture not constructible"
    finish
fi
: > "${L1}/download.bin"
INH_GID="$(stat -c '%g' "${L1}/download.bin")"
if [[ "$INH_GID" == "$OP_GID" ]]; then
    skip "case 1: filesystem under ${TMPDIR:-/tmp} did not honour setgid inheritance (file gid stayed ${INH_GID}) — fixture not constructible"
    finish
fi

# The fixture is ASSERTED before it is used: a case whose premise silently did
# not hold would otherwise report a green that means nothing.
FILE_UID="$(stat -c '%u' "${L1}/download.bin")"
if [[ "$FILE_UID" != "$OP_UID" ]]; then
    fail "case 1 fixture: file uid is ${FILE_UID}, expected the operator's ${OP_UID} — the premise 'uid right, gid wrong' does not hold"
    finish
fi
echo "  fixture: ${L1} -> files land uid=${FILE_UID} gid=${INH_GID}; operator is ${OP_UID}:${OP_GID} (gid MISMATCH via ${ALT_NAME})"

write_scope "${WORK}/scope1.yaml" "$R1"
P1="$(probe_verdict "$L1")"
D1="$(repair_verdict "$R1" "${WORK}/scope1.yaml" "${WORK}/state1")"
echo "  precondition says : ${P1}"
echo "  repair says       : ${D1}"

if [[ "$P1" == "ok" && "$D1" != "clean" ]]; then
    fail "gid-mismatched location: the PRECONDITION certifies it ('${P1}') while the REPAIR reports it broken ('${D1}') — the two halves disagree about which property 'correct ownership' means (BOB-207, §11.4.250)"
elif [[ "$P1" != "ok" && "$D1" == "clean" ]]; then
    fail "gid-mismatched location: the PRECONDITION refuses it ('${P1}') while the REPAIR finds nothing to repair ('${D1}') — the halves disagree in the opposite direction; a startup refusal the repair cannot clear is an unclearable block"
else
    pass "gid-mismatched location: precondition ('${P1}') and repair ('${D1}') agree"
fi

# ===========================================================================
# CASE GF-1 (GOLDEN-FALSE, §11.4.201(1)) — a location with the operator's uid
# AND gid must be accepted by BOTH halves. This must hold TODAY and after
# whichever fix lands. Without it, "make the probe always refuse" or "make the
# repair select everything" would turn Case 1 green while breaking the product.
# ===========================================================================
R2="${WORK}/case2"; L2="${R2}/library"; mkdir -p "$L2" "${WORK}/state2"
: > "${L2}/download.bin"
G2_UID="$(stat -c '%u' "${L2}/download.bin")"; G2_GID="$(stat -c '%g' "${L2}/download.bin")"
if [[ "$G2_UID" != "$OP_UID" || "$G2_GID" != "$OP_GID" ]]; then
    fail "case GF-1 fixture: file is ${G2_UID}:${G2_GID}, expected ${OP_UID}:${OP_GID} — the healthy premise does not hold"
    finish
fi
echo "  fixture: ${L2} -> files land uid=${G2_UID} gid=${G2_GID} (fully correct)"

write_scope "${WORK}/scope2.yaml" "$R2"
P2="$(probe_verdict "$L2")"
D2="$(repair_verdict "$R2" "${WORK}/scope2.yaml" "${WORK}/state2")"
echo "  precondition says : ${P2}"
echo "  repair says       : ${D2}"

if [[ "$P2" == "ok" ]]; then
    pass "golden-FALSE: a fully-correct location is still accepted by the precondition"
else
    fail "golden-FALSE: the precondition REFUSED a location owned ${OP_UID}:${OP_GID} ('${P2}') — a false-positive refusal is a FAIL-bluff of equal severity to a false pass (§11.4.201(1))"
fi
if [[ "$D2" == "clean" ]]; then
    pass "golden-FALSE: a fully-correct location gives the repair nothing to do"
else
    fail "golden-FALSE: the repair wants to change a location already owned ${OP_UID}:${OP_GID} ('${D2}')"
fi
if [[ "$P2" == "ok" && "$D2" == "clean" ]]; then
    pass "golden-FALSE: precondition and repair agree on a correct location"
fi

finish
