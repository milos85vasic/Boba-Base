#!/usr/bin/env bash
# test_compute_badges_all_badges_updated.sh — every machine-derived README badge
# must actually match its live count after compute-badges.sh runs (§11.4.259,
# §11.4.6, §11.4.201).
#
# FORENSIC ANCHOR (measured 2026-08-20). compute-badges.sh printed, on every run:
#
#     challenges:     38 (unchanged, cross-checked, matches existing badge)
#     pre-build invariants: 44 (unchanged, cross-checked, matches existing badge)
#
# while README.md carried `challenges-31` and `pre--build%20invariants-30`. That
# parenthetical is a HARDCODED STRING: the script never compared those two badges
# to anything and never updated them. It asserted a cross-check it did not
# perform — a §11.4 bluff at the badge layer, in the same file where BOB-118
# already found untraceable badge numbers once before.
#
# The python and frontend badges ARE genuinely computed, compared and rewritten,
# so a test that only checked those two would pass while the lie persisted.
# This test therefore covers EVERY machine-derived badge.
#
# Usage:   bash tests/unit/test_compute_badges_all_badges_updated.sh
# Outputs: PASS/FAIL per badge on stdout; non-zero exit on any mismatch.
# Side-effects: none — read-only. Never invokes compute-badges.sh (which mutates
#   tracked files); it asserts the COMMITTED state is already consistent, which is
#   the property that matters at commit time.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
README="${ROOT}/README.md"
FAILED=0

badge_value() {
    # $1 = the badge's alt= name. Structural match (§11.4.201(7)(a)): the line
    # must BE an <img> whose src is a shields.io badge, never any line that
    # merely mentions the alt text — the carrier trap this file's sibling test
    # (test_compute_badges_carrier_match.sh) exists to prevent.
    grep -E "^[[:space:]]*<img[[:space:]]+alt=\"$1\"[[:space:]]+src=\"https://img\.shields\.io/badge/" "${README}" \
        | head -1 | grep -oE 'badge/[^"]*' | sed 's|badge/||'
}

check() {
    local name="$1" live="$2" badge_raw="$3"
    # Badge label shape: <label>-<value>-<color>; the value is the 2nd-to-last
    # dash-delimited field once %20 is decoded.
    local got
    got="$(printf '%s' "${badge_raw}" | sed 's/%20/ /g' | awk -F- '{print $(NF-1)}')"
    if [[ "${got}" == "${live}" ]]; then
        echo "  PASS ${name}: badge=${got} == live=${live}"
    else
        echo "  FAIL ${name}: badge=${got} but live count is ${live}"
        echo "       raw badge: ${badge_raw}"
        FAILED=1
    fi
}

# --- live counts, derived the same way compute-badges.sh derives them --------
LIVE_PB="$(grep -oE '\[[0-9]+/[0-9]+\]' "${ROOT}/scripts/pre_build_verification.sh" \
           | sed 's|.*/||; s|\]||' | sort -n | tail -1)"
LIVE_CH="$(find "${ROOT}/challenges/scripts" -maxdepth 1 -name '*.sh' 2>/dev/null | wc -l | tr -d ' ')"

# §11.4.201(6): a blind derivation must not be read as agreement. If either live
# count came back empty the instrument saw nothing and the test says so.
if [[ -z "${LIVE_PB}" || "${LIVE_CH}" == "0" ]]; then
    echo "FAIL: could not derive live counts (pb='${LIVE_PB}' ch='${LIVE_CH}') — blind instrument, not a clean tree"
    exit 1
fi

echo "test_compute_badges_all_badges_updated: live pb=${LIVE_PB} ch=${LIVE_CH}"
check "pre-build"  "${LIVE_PB}" "$(badge_value 'pre-build')"
check "challenges" "${LIVE_CH}" "$(badge_value 'challenges')"

if [[ "${FAILED}" -ne 0 ]]; then
    echo "test_compute_badges_all_badges_updated: FAIL — at least one badge does not match its live count"
    echo "  compute-badges.sh must UPDATE every badge it reports on, and may only"
    echo "  claim 'matches existing badge' after really comparing (§11.4.6)."
    exit 1
fi
echo "test_compute_badges_all_badges_updated: PASS — every machine-derived badge matches its live count"
