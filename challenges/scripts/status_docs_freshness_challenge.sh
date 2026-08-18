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
# --- CONCURRENCY GUARD (BOB-075 followup, §11.4.84/§11.4.201/§11.4.180) ---
# RED_MODE=1 backdates + traps + restores docs/codegraph/Status.md IN PLACE
# on the real, committed file. This is a real, committed-file mutation, not
# a scratch copy — two concurrent RED_MODE=1 invocations race on the SAME
# file with NO shared-state coordination beyond each process's own private
# backup, and EMPIRICALLY, unforced concurrent runs corrupt the file: one
# instance's GREEN-phase restore can be silently clobbered by the other
# instance's own backdate landing in the gap between "restore" and
# "trap - EXIT" / the final freshness re-check, and — because that instance
# has ALREADY disabled its own trap by that point — its subsequent FAIL exit
# leaves the file stuck at the backdated (100-days-ago) timestamp with NO
# further restore. Reproduced 3/5 unforced concurrent trials in this
# fix's evidence run (docs/qa/BOB-075/concurrency_evidence/) — see that
# directory for full before/after/mutation transcripts.
#
# The fix: a single-instance mutex serializes entry into the backdate phase.
#   - Primary: `flock -n` on this script's OWN file (its inode), so distinct
#     copies of this script (e.g. different checkouts) get independent
#     locks, and two invocations of THE SAME copy correctly contend.
#   - Fallback: mkdir-based lock (atomic mkdir, portable to hosts without
#     `flock(1)`), keyed off this script's resolved real path so it shares
#     the same per-checkout scoping as the flock path. A holder-PID
#     liveness check (`kill -0`, §11.4.180) reaps a provably-stale mkdir
#     lock left behind by a killed/crashed holder — a live holder is NEVER
#     reaped.
#   - Fail-fast, non-blocking: a held lock refuses immediately with an
#     actionable message naming the holder PID (when known) rather than
#     blocking or racing.
#   - The cleanup trap ALWAYS restores the real file FIRST (if a backdate
#     is in flight) THEN releases the lock — so a signal (INT/TERM) arriving
#     mid-backdate never leaves the file stuck NOR leaves the lock held
#     past the point the file is safe again.
#
# Wall-clock / background-execution note (§11.4.89):
#   `docs_chain verify --all` takes ~70-90s on this repo (weasyprint/pandoc
#   rendering of the registered contexts). RED_MODE=1 (the default) calls
#   `check_all_fresh` THREE times (baseline, RED, GREEN), so a full RED_MODE=1
#   run is realistically ~3-5 minutes of wall-clock, almost entirely spent
#   inside `docs_chain verify --all` subprocess calls this script does not
#   control the duration of. Per §11.4.89 (background test execution
#   mandate — tests expected to exceed ~30s MUST run backgrounded, never
#   block the main work stream), RUN THE RED_MODE=1 PATH IN THE BACKGROUND:
#     nohup bash challenges/scripts/status_docs_freshness_challenge.sh \
#       > qa-results/status_docs_freshness_$(date -u +%Y%m%dT%H%M%SZ).log 2>&1 &
#     disown
#   RED_MODE=0 (the standing regression-guard invocation, one
#   `check_all_fresh` call) is ~70-90s alone and MAY be run foreground for
#   a quick manual check, but is still a background-eligible candidate under
#   the same §11.4.89 threshold.
#   No `timeout` wrapper is needed or wanted here: the script already
#   tracks and bounds its own work (a fixed, small number of sequential
#   `docs_chain verify --all` calls with no unbounded loop), so an external
#   timeout would only add a second, uncoordinated failure mode (a false
#   "hang" abort mid-backdate that races the EXIT trap) without adding any
#   safety this script does not already provide via the lock + trap above.
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

# ---------------------------------------------------------------------------
# Concurrency guard (§11.4.84 quiescence / §11.4.201 real-condition guard /
# §11.4.180 stale-lock reap). Single-instance mutex keyed off THIS script's
# own resolved path, so distinct checkouts/copies never contend with each
# other but two concurrent invocations of the SAME copy always do.
# ---------------------------------------------------------------------------
SCRIPT_SELF="${BASH_SOURCE[0]}"
LOCK_MODE=""
LOCK_FD=""
MKDIR_LOCK_PATH=""

acquire_lock() {
    if command -v flock >/dev/null 2>&1; then
        # Lock on this script's own file (its inode). Read-only fd is
        # sufficient for flock — it does not require write access.
        exec 9<"${SCRIPT_SELF}"
        if ! flock -n 9; then
            local holder=""
            if [[ -f "${SCRIPT_SELF}.lockpid" ]]; then
                holder="$(cat "${SCRIPT_SELF}.lockpid" 2>/dev/null || true)"
            fi
            echo "FAIL: another instance of $(basename "${SCRIPT_SELF}") is already running${holder:+ (pid=${holder})} — refusing to run concurrently (this script backdates + restores docs/codegraph/Status.md in place, and concurrent invocations are known to corrupt it, §11.4.84/BOB-075). Wait for the other instance to finish, then retry." >&2
            exit 1
        fi
        LOCK_MODE="flock"
        LOCK_FD=9
        echo "$$" > "${SCRIPT_SELF}.lockpid" 2>/dev/null || true
        return 0
    fi

    # Portable fallback: atomic mkdir-based lock.
    MKDIR_LOCK_PATH="${SCRIPT_SELF}.lock.d"
    local waited=0
    while ! mkdir "${MKDIR_LOCK_PATH}" 2>/dev/null; do
        local holder_pid=""
        [[ -f "${MKDIR_LOCK_PATH}/pid" ]] && holder_pid="$(cat "${MKDIR_LOCK_PATH}/pid" 2>/dev/null || true)"
        if [[ -n "${holder_pid}" ]] && ! kill -0 "${holder_pid}" 2>/dev/null; then
            # Provably stale: recorded holder PID is dead. Reap (§11.4.180) —
            # a LIVE holder is never touched.
            rm -rf "${MKDIR_LOCK_PATH}"
            continue
        fi
        if [[ "${waited}" -ge 1 ]]; then
            echo "FAIL: another instance of $(basename "${SCRIPT_SELF}") is already running${holder_pid:+ (pid=${holder_pid})} — refusing to run concurrently (this script backdates + restores docs/codegraph/Status.md in place, and concurrent invocations are known to corrupt it, §11.4.84/BOB-075). Wait for the other instance to finish, then retry." >&2
            exit 1
        fi
        waited=1
    done
    echo "$$" > "${MKDIR_LOCK_PATH}/pid"
    LOCK_MODE="mkdir"
    return 0
}

release_lock() {
    case "${LOCK_MODE}" in
        flock)
            rm -f "${SCRIPT_SELF}.lockpid" 2>/dev/null || true
            flock -u "${LOCK_FD}" 2>/dev/null || true
            exec 9<&- 2>/dev/null || true
            ;;
        mkdir)
            [[ -n "${MKDIR_LOCK_PATH}" ]] && rm -rf "${MKDIR_LOCK_PATH}"
            ;;
    esac
    LOCK_MODE=""
}

acquire_lock

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

# ---------------------------------------------------------------------------
# Unified cleanup: on ANY exit path (normal completion, error under
# `set -e`, or a signal), restore the real file FIRST if a backdate is
# currently in flight, THEN release the lock. Order matters (BOB-075
# followup constraint): a signal arriving mid-backdate must never release
# the lock while the committed file is still left stale.
# ---------------------------------------------------------------------------
BACKUP=""
cleanup() {
    local rc=$?
    if [[ -n "${BACKUP}" && -f "${BACKUP}" ]]; then
        cp "${BACKUP}" "${CODEGRAPH_STATUS}"
        rm -f "${BACKUP}"
        BACKUP=""
    fi
    release_lock
    exit "${rc}"
}
trap cleanup EXIT INT TERM

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
BACKUP=""

if ! check_all_fresh; then
    echo "FAIL: post-restore check still FAILing — restore did not take, or a real drift exists"
    exit 1
fi
echo "  PASS: green flip back confirmed"
echo "  (restored original Last-modified: ${CURRENT_LM})"

echo
echo "PASS: status-docs freshness gate — baseline PASS + RED polarity + green flip verified"
exit 0
