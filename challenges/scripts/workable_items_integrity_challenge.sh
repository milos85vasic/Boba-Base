#!/usr/bin/env bash
# workable_items_integrity_challenge.sh — §11.4.93 SSoT integrity + §11.4.106(F)
# DB<->Markdown drift regression guard (BOB-072/BOB-073).
#
# EXPECT: `workable-items validate --db docs/workable_items.db` reports either
# ZERO violations, OR exactly ONE known-tracked/OPERATOR-BLOCKED violation
# (BOB-010 history id=64) that `correct-history-evidence` structurally CANNOT
# fix (its own docstring scopes it to closure events {Fixed|Implemented|
# Completed|Obsolete}; history id=64 is an `Updated` event — the tool's own
# prior self-documenting correction-audit row, not a closure claim). This
# challenge does NOT silently swallow that finding — it asserts the violation
# list is EXACTLY that one known line, so any DIFFERENT or ADDITIONAL
# violation still FAILS the challenge (§11.4.201 conservative-safe: a wider
# validate output than the tracked exemption is a genuine regression, not
# noise). `workable-items diff` between the DB and docs/Issues.md +
# docs/Fixed.md MUST report zero drift, unconditionally (diff carries no
# exemption).
#
# §11.4.115 RED/GREEN polarity:
#   RED_MODE=1 — reproduces the BOB-072/073 defect on a THROWAWAY temp copy of
#     the pre-fix DB (docs/qa/BOB-072-073/backup/workable_items.db.pre-fix,
#     §9.2 backup taken before the fix landed) — EXPECT validate to report
#     MORE than the one tracked exemption line (14 violations pre-fix) AND/OR
#     diff to report non-zero drift (9 differences pre-fix) — proving the
#     defect this guard exists to catch is REAL and OBSERVABLE.
#   RED_MODE=0 (default) — GREEN regression guard against the LIVE
#     docs/workable_items.db + docs/Issues.md + docs/Fixed.md: validate's
#     violation list must be empty or exactly the one tracked exemption line,
#     AND diff must report zero drift.
#
# CONST-XII anti-bluff (§11.4.6/§11.4.107(10)): never operates on the live DB
# in RED_MODE=1 — the pre-fix backup is read-only input to a temp copy this
# script owns and deletes on exit (trap). GREEN mode never mutates anything —
# both `validate` and `diff` are read-only subcommands.
#
# BOB-072 (RD2-03 SSoT integrity) + BOB-073 (RD2-04 DB<->MD drift).
# Pass: PASS message(s) + exit 0
# Fail: FAIL: <reason> + exit 1
# Skip: SKIP: <reason> + exit 0 (§11.4.3 — topology/tooling genuinely absent)

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BIN="${PROJECT_ROOT}/constitution/scripts/workable-items/bin/workable-items"
LIVE_DB="${PROJECT_ROOT}/docs/workable_items.db"
LIVE_ISSUES="${PROJECT_ROOT}/docs/Issues.md"
LIVE_FIXED="${PROJECT_ROOT}/docs/Fixed.md"
PRE_FIX_DB="${PROJECT_ROOT}/docs/qa/BOB-072-073/backup/workable_items.db.pre-fix"
RED_MODE="${RED_MODE:-0}"

# The one tracked, tool-scope-exhausted exemption (see docs/qa/BOB-072-073/
# validate_after.log + task-bob072-073-report.md for the full exhaustion
# trail: attempted `correct-history-evidence --atm-id BOB-010 --history-id 64`
# — real refusal captured, event_type=Updated is outside the tool's
# closure-events-only scope by design).
EXEMPT_LINE='  - BOB-010: closure evidence_path does not resolve (well-formed path, but nothing exists there) — history id=64, event=Updated, on=2026-08-10: "scripts/docs_chain.sh" (§11.4.5/§11.4.69/§11.4.123/§11.4.226 — a closure'"'"'s captured proof must be producible on demand)'

if [[ ! -x "${BIN}" ]]; then
    echo "SKIP: workable-items binary not built at ${BIN}"
    echo "      §11.4.3 honest-skip: tool artifact absent, not a false PASS"
    exit 0
fi

# validate_is_clean_or_exempt <db-path> -> 0 if PASS-shape, 1 if FAIL-shape.
# Prints the classification reason on stdout either way (never silent).
validate_is_clean_or_exempt() {
    local db="$1" out exit_code violation_lines
    out="$(mktemp)"
    exit_code=0
    "${BIN}" validate --db "${db}" >"${out}" 2>&1 || exit_code=$?
    if [[ "${exit_code}" -eq 0 ]]; then
        echo "  validate: 0 violations (clean)"
        rm -f "${out}"
        return 0
    fi
    violation_lines="$(grep -c '^  - ' "${out}" || true)"
    if [[ "${violation_lines}" -eq 1 ]] && grep -qxF "${EXEMPT_LINE}" "${out}"; then
        echo "  validate: 1 violation — exactly the tracked BOB-010/history-id=64 exemption (acceptable)"
        rm -f "${out}"
        return 0
    fi
    echo "  validate: ${violation_lines} violation(s), NOT the clean/exempt shape:"
    sed 's/^/    /' "${out}"
    rm -f "${out}"
    return 1
}

# diff_is_clean <db-path> <issues-path> <fixed-path> -> 0 if in-sync, 1 else.
diff_is_clean() {
    local db="$1" issues="$2" fixed="$3" out exit_code
    out="$(mktemp)"
    exit_code=0
    "${BIN}" diff --db "${db}" --issues "${issues}" --fixed "${fixed}" >"${out}" 2>&1 || exit_code=$?
    if [[ "${exit_code}" -eq 0 ]]; then
        echo "  diff: in sync"
        rm -f "${out}"
        return 0
    fi
    echo "  diff: NOT in sync:"
    sed 's/^/    /' "${out}"
    rm -f "${out}"
    return 1
}

if [[ "${RED_MODE}" == "1" ]]; then
    echo "[RED_MODE=1] Reproducing the BOB-072/073 defect against the pre-fix DB snapshot"
    if [[ ! -f "${PRE_FIX_DB}" ]]; then
        echo "SKIP: pre-fix backup ${PRE_FIX_DB} absent — RED reproduction needs the §9.2 snapshot"
        echo "      (this is a one-time historical fixture; GREEN mode does not depend on it)"
        exit 0
    fi
    TMP_DIR="$(mktemp -d)"
    trap 'rm -rf "${TMP_DIR}"' EXIT
    TMP_DB="${TMP_DIR}/workable_items.pre-fix.db"
    cp "${PRE_FIX_DB}" "${TMP_DB}"

    RED_BAD=0
    echo "[1/2] validate on pre-fix snapshot (EXPECT the defect: violations beyond the tracked exemption)"
    if validate_is_clean_or_exempt "${TMP_DB}"; then
        echo "  UNEXPECTED: pre-fix snapshot validated clean/exempt — RED did not reproduce"
    else
        echo "  CONFIRMED: pre-fix snapshot carries real, non-exempt violations (the defect this guard catches)"
        RED_BAD=1
    fi

    echo "[2/2] diff on pre-fix snapshot vs the CURRENT (fixed) docs/Issues.md + docs/Fixed.md (EXPECT drift)"
    if diff_is_clean "${TMP_DB}" "${LIVE_ISSUES}" "${LIVE_FIXED}"; then
        echo "  UNEXPECTED: pre-fix snapshot diffed clean against current MD — RED did not reproduce"
    else
        echo "  CONFIRMED: pre-fix snapshot drifts against the current (fixed) Markdown (the defect this guard catches)"
        RED_BAD=1
    fi

    if [[ "${RED_BAD}" -eq 1 ]]; then
        echo "PASS (RED_MODE=1): defect reproduced on the pre-fix snapshot — this guard is not a tautology"
        exit 0
    fi
    echo "FAIL (RED_MODE=1): pre-fix snapshot did not reproduce the defect — guard is a bluff or the snapshot is stale"
    exit 1
fi

# ---------------------------------------------------------------------------
# RED_MODE=0 (default): GREEN regression guard against the LIVE tracker.
# ---------------------------------------------------------------------------
echo "[GREEN] validate + diff against the live docs/workable_items.db + docs/Issues.md + docs/Fixed.md"

GREEN_OK=1
echo "[1/2] validate (EXPECT clean or the single tracked BOB-010/history-id=64 exemption)"
if ! validate_is_clean_or_exempt "${LIVE_DB}"; then
    GREEN_OK=0
fi

echo "[2/2] diff (EXPECT zero drift, unconditionally)"
if ! diff_is_clean "${LIVE_DB}" "${LIVE_ISSUES}" "${LIVE_FIXED}"; then
    GREEN_OK=0
fi

if [[ "${GREEN_OK}" -eq 1 ]]; then
    echo "PASS: workable_items.db SSoT integrity + Issues.md/Fixed.md drift both hold (BOB-072/BOB-073)"
    exit 0
fi
echo "FAIL: workable_items.db SSoT integrity or DB<->Markdown drift regressed — see output above"
exit 1
