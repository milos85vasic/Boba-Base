#!/usr/bin/env bash
# status_docs_freshness_challenge.sh — Layer 4 §11.4.44/§11.4.86 doc-staleness
# gate for docs/features/Status.md + docs/codegraph/Status.md.
#
# BOB-075 (GOVERNANCE_AUDIT_2026-08-08_ROUND2.md RD2-08): both docs' Revision
# headers were found ~2 months stale — worse, `docs/features/Status.md` had
# a REAL content edit (ea86ce1) land without its header being bumped at all,
# proving header staleness is a genuine, silent §11.4.44 defect class, not
# cosmetic. This gate makes that defect class mechanically detectable.
#
# EXPECT (RED_MODE=0 — the standing regression guard):
#   1. `docs_chain verify --all` reports every registered context in-sync
#      (both `features-status` and `codegraph-status` contexts) — the
#      derived .html/.pdf/.docx siblings match their .md source.
#   2. Each of docs/features/Status.md and docs/codegraph/Status.md carries
#      a parseable `**Last modified:** <ISO8601>` header whose age is
#      <= FRESHNESS_SLA_DAYS (60 — chosen because it is tighter than the
#      73-day-old drift the RD2-08 audit actually caught on
#      docs/codegraph/Status.md; a real 73-day-stale doc MUST fail this
#      gate, and 60 gives a working margin for genuinely quiet periods
#      without being a no-op SLA).
#
# EXPECT (RED_MODE=1, default — §11.4.115 polarity proof both directions):
#   step 1 baseline (as above)                          -> EXPECT PASS
#   step 2 backdate docs/codegraph/Status.md's header
#          to 100 days ago (> SLA)                      -> EXPECT FAIL
#          naming that file + its real age
#   step 3 restore the original header                  -> EXPECT PASS
#
# Anti-bluff (§11.4.6/§11.4.107(10)): step 2 proves the age-check is
# genuinely falsifiable — a gate that PASSes a doc it just backdated past
# the SLA is itself a bluff gate.
#
# Pass: PASS message + exit 0
# Fail: FAIL: <reason> + exit 1
# Skip: SKIP: <reason> + exit 0 (§11.4.3 — engine/tooling genuinely absent)

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENGINE="${PROJECT_ROOT}/constitution/submodules/docs_chain/docs_chain"
RED_MODE="${RED_MODE:-1}"
FRESHNESS_SLA_DAYS="${FRESHNESS_SLA_DAYS:-60}"

FEATURES_STATUS="${PROJECT_ROOT}/docs/features/Status.md"
CODEGRAPH_STATUS="${PROJECT_ROOT}/docs/codegraph/Status.md"

now_epoch() { date -u +%s; }

# extract_last_modified <file> — prints the ISO8601 value of the file's
# `**Last modified:** ...` header line, or empty on no match.
extract_last_modified() {
    grep -m1 -E '^\*\*Last modified:\*\*' "$1" | sed -E 's/^\*\*Last modified:\*\*[[:space:]]*//'
}

# age_days_of <iso8601> — prints the age in whole days of the given
# ISO8601 UTC timestamp relative to now. Empty/unparseable -> prints
# a huge sentinel age so callers treat it as maximally stale (§11.4.201 —
# conservative-safe default on an unresolvable signal, never a silent PASS).
age_days_of() {
    local ts="$1" epoch
    epoch="$(date -u -d "${ts}" +%s 2>/dev/null || true)"
    if [[ -z "${epoch}" ]]; then
        echo 999999
        return
    fi
    echo $(( ( $(now_epoch) - epoch ) / 86400 ))
}

# check_all_fresh — runs the full GREEN-state assertion set. Prints its own
# PASS/FAIL lines; returns 0 on all-green, 1 on any finding.
check_all_fresh() {
    local ok=0

    if [[ -x "${ENGINE}" && -d "${PROJECT_ROOT}/.docs_chain/contexts" ]]; then
        local verify_log verify_exit=0
        verify_log="$(mktemp)"
        "${ENGINE}" verify --all --root "${PROJECT_ROOT}" >"${verify_log}" 2>&1 || verify_exit=$?
        if [[ "${verify_exit}" -ne 0 ]]; then
            echo "  FAIL: docs_chain verify --all reported drift (exit ${verify_exit})"
            sed 's/^/         /' "${verify_log}"
            ok=1
        else
            echo "  PASS: docs_chain verify --all — $(wc -l <"${verify_log}" | tr -d ' ') context(s) in-sync"
        fi
        rm -f "${verify_log}"
    else
        echo "  SKIP: docs_chain engine or .docs_chain/contexts/ absent — export-sync check skipped (§11.4.3)"
    fi

    local f
    for f in "${FEATURES_STATUS}" "${CODEGRAPH_STATUS}"; do
        local rel="${f#${PROJECT_ROOT}/}"
        if [[ ! -f "${f}" ]]; then
            echo "  FAIL: ${rel} does not exist"
            ok=1
            continue
        fi
        local lm age
        lm="$(extract_last_modified "${f}")"
        if [[ -z "${lm}" ]]; then
            echo "  FAIL: ${rel} has no parseable '**Last modified:**' header"
            ok=1
            continue
        fi
        age="$(age_days_of "${lm}")"
        if [[ "${age}" -gt "${FRESHNESS_SLA_DAYS}" ]]; then
            echo "  FAIL: ${rel} Last-modified=${lm} is ${age}d old (SLA ${FRESHNESS_SLA_DAYS}d)"
            ok=1
        else
            echo "  PASS: ${rel} Last-modified=${lm} is ${age}d old (<= SLA ${FRESHNESS_SLA_DAYS}d)"
        fi
    done

    return "${ok}"
}

echo "[1/1] Baseline: docs_chain in-sync + both Status docs within ${FRESHNESS_SLA_DAYS}d SLA (EXPECT PASS)"
if ! check_all_fresh; then
    echo "FAIL: baseline freshness check did not pass — see findings above"
    exit 1
fi
echo "  BASELINE PASS"

if [[ "${RED_MODE}" == "0" ]]; then
    echo
    echo "PASS: status-docs freshness gate (RED_MODE=0 — regression guard only)"
    exit 0
fi

# ---------------------------------------------------------------------------
# RED polarity (§11.4.115): backdate one doc's header past the SLA and
# EXPECT the very next check to FAIL naming it.
# ---------------------------------------------------------------------------
echo
echo "[RED] Backdating $(basename "${CODEGRAPH_STATUS}")'s Last-modified by 100d (EXPECT FAIL)"

BACKUP="$(mktemp)"
cp "${CODEGRAPH_STATUS}" "${BACKUP}"
trap 'cp "${BACKUP}" "${CODEGRAPH_STATUS}"; rm -f "${BACKUP}"' EXIT

STALE_TS="$(date -u -d '100 days ago' +%Y-%m-%dT%H:%M:%SZ)"
CURRENT_LM="$(extract_last_modified "${CODEGRAPH_STATUS}")"
sed -i "s/^\*\*Last modified:\*\*.*/\*\*Last modified:\*\* ${STALE_TS}/" "${CODEGRAPH_STATUS}"

RED_LOG="$(mktemp)"
RED_RC=0
check_all_fresh >"${RED_LOG}" 2>&1 || RED_RC=$?
if [[ "${RED_RC}" -eq 0 ]]; then
    echo "FAIL: backdating past the SLA did NOT trip the gate — the freshness check is a bluff"
    sed 's/^/       /' "${RED_LOG}"
    rm -f "${RED_LOG}"
    exit 1
fi
if ! grep -q "codegraph/Status.md.*is [0-9]* d old\|codegraph/Status.md Last-modified=${STALE_TS}" "${RED_LOG}"; then
    # Looser structural check: the FAIL line must name the codegraph Status doc.
    if ! grep -q "docs/codegraph/Status.md" "${RED_LOG}"; then
        echo "FAIL: gate FAILed (rc=${RED_RC}) but did not name docs/codegraph/Status.md — wrong-node bluff"
        sed 's/^/       /' "${RED_LOG}"
        rm -f "${RED_LOG}"
        exit 1
    fi
fi
echo "  PASS: RED detected (exit ${RED_RC}, docs/codegraph/Status.md named as stale)"
sed 's/^/         /' "${RED_LOG}"
rm -f "${RED_LOG}"

echo
echo "[GREEN] Restoring original header (EXPECT PASS)"
cp "${BACKUP}" "${CODEGRAPH_STATUS}"
rm -f "${BACKUP}"
trap - EXIT

if ! check_all_fresh; then
    echo "FAIL: post-restore check still FAILing — restore did not take, or a real drift exists"
    exit 1
fi
echo "  PASS: green flip back confirmed"
echo "  (restored original Last-modified: ${CURRENT_LM})"

echo
echo "PASS: status-docs freshness gate — baseline PASS + RED polarity + green flip verified"
exit 0
