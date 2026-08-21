#!/usr/bin/env bash
# test_ownership_repair.sh — unit contract suite for scripts/ownership_repair.sh
# (feature 002-user-owned-downloads, T007).
#
# Contract under test : specs/002-user-owned-downloads/contracts/repair-cli.md
# Data model          : specs/002-user-owned-downloads/data-model.md (E1/E2/E3)
# Requirements        : FR-004, FR-004a/b/c, FR-005, FR-006, FR-015
#
# ============================================================================
# §11.4.43 / §11.4.224(A) RED-FIRST — READ THIS BEFORE "FIXING" A FAILURE
# ============================================================================
# `scripts/ownership_repair.sh` DOES NOT EXIST YET. This suite is authored
# BEFORE it (T007 precedes T019/T020/T022) and therefore FAILS on purpose. The
# RED must be for the RIGHT reason — the missing artifact — and the precheck
# below says so explicitly so a missing script is never confused with a defect
# in this harness. Once T019 lands, every case below must go GREEN unmodified.
#
# ============================================================================
# THE FIXTURE CONSTRAINT, MEASURED — WHY THESE CASES USE A **gid** MISMATCH
# ============================================================================
# The observed production defect is a **uid** mismatch: the download tree's new
# files land at uid 100999 (the rootless-podman subuid mapping) while the
# operator is uid 1000, so the operator cannot rename, move or delete their own
# downloads and cannot read config/boba.db.
#
# A unit test runs UNPRIVILEGED and MUST NOT use sudo. Reproducing a foreign
# **uid** on disk was probed three ways on this host (2026-08-21, §11.4.6 —
# measured, not assumed):
#
#   1. plain `chown 1001 f`                       -> EPERM "Operation not permitted"
#   2. `unshare -Ur` then `chown 1:1 f`           -> EINVAL "Invalid argument"
#                                                    (only uid 0 is mapped)
#   3. `unshare -U --map-users=100000,0,65536`
#      (the real subuid range, /etc/subuid says
#       milosvasic:100000:65536) then `chown`     -> EPERM; the file reads
#                                                    65534:65534 inside the ns
#                                                    and 1000:1000 on the host
#
# So a real host-uid mismatch is NOT constructible in an unprivileged hermetic
# sandbox — and, symmetrically, an unprivileged process could not chown it BACK
# either, so even a perfect implementation could not turn such a fixture green
# here. That half of the defect belongs to the integration layer and is
# DECLARED AS A GAP at the end of this file rather than faked (§11.4.6,
# §11.4.115(G): a constructed precondition that does not trace to the real
# defect mints at most defensive hardening, never a defect-closing test).
#
# What IS honestly constructible, and IS the same defect class: a **gid**
# mismatch. Measured on this host: `chgrp 10 f` succeeds (the operator is a
# member of `wheel`), producing a real on-disk `1000:10` — an item that is NOT
# operator-owned — and the repair can genuinely put it back to `1000:1000`
# unprivileged. This is not a proxy for the defect: `scripts/lib/ownership.sh`
# models the operator identity as uid AND gid (`ownership_operator_uid` /
# `ownership_operator_gid`), and data-model E3 records `previous_gid`/`new_gid`
# as first-class fields. A gid-wrong item is squarely inside the set the repair
# must fix, and it exercises the full RED->GREEN mutation path end to end.
#
# ============================================================================
# HOW THE MARKER AND CHANGE RECORD ARE LOCATED (they are deliberately
# unspecified by the contract — T021 decides location and serialisation)
# ============================================================================
# This suite must not depend on a decision that has not been made, and must not
# invent one. So it does NOT hardcode any path. Instead:
#
#   * The script is executed from a SANDBOX project root (a byte-identical copy
#     of the artifact under a mktemp tree). `scripts/lib/ownership.sh` resolves
#     the project root from its OWN path, so wherever the implementation
#     chooses to write its marker and change record relative to the project
#     root, it lands INSIDE the sandbox and is discoverable.
#
#   * MARKER detection is structural, not path-based: data-model E2 mandates a
#     `scope_fingerprint` field, so the marker is detected as "some artifact in
#     the sandbox contains the current scope fingerprint" (a full sha256 — no
#     plausible false match). This is format-agnostic (yaml/json/plain all
#     work) and location-agnostic.
#
#   * The marker-ABSENT assertion in the interrupt case is a NULL, and
#     §11.4.201(7)(b) forbids trusting a null until the instrument is proven
#     able to see through the same path. The golden-bad case runs FIRST and
#     must find a marker; that positive detection is the CONTROL NEEDLE, and it
#     arms MARKER_DETECTOR_PROVEN. If the needle never fired, the interrupt
#     case refuses to report "absent" and fails honestly instead.
#
#   * CHANGE RECORD detection: an artifact (outside the fixture tree and
#     outside the copied scripts) that mentions a SPECIFIC repaired item path.
#     Specific item paths are used, never the declared root — the root appears
#     in the scope file, which would be a §11.4.201(7)(a) carrier match.
#
# ============================================================================
# §11.4.263 PROCESS-GROUP SIGNAL SAFETY (case 5 kills a process)
# ============================================================================
# This host has a documented seven-incident forced-logout history caused by
# `killpg(1, SIGKILL)` degenerating into `kill(-1, SIGKILL)`. This suite
# therefore NEVER uses pkill/killall, NEVER signals a process group, and
# NEVER signals a pid it did not capture itself. Every signal goes through
# `signal_pid_safely`, which validates the pid is an integer > 1 AND confirms
# via /proc/<pid>/cmdline that it is really the sandbox script (§11.4.196(D)
# real-identity resolution, not a substring guess).
#
# §11.4.14: every fixture is a mktemp tree reaped by a trap on every exit path.
# The real download tree and the real config/owned_paths.yaml are never read
# and never touched.

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${HERE}/../.." && pwd)"
SCRIPT="${PROJECT_ROOT}/scripts/ownership_repair.sh"
LIB="${PROJECT_ROOT}/scripts/lib/ownership.sh"

PASS=0; FAIL=0; SKIP=0
pass() { PASS=$((PASS+1)); echo "  PASS: $1"; }
fail() { FAIL=$((FAIL+1)); echo "  FAIL: $1"; }
skip() { SKIP=$((SKIP+1)); echo "  SKIP: $1"; }
finish() {
    echo "RESULT: ${PASS} passed, ${FAIL} failed, ${SKIP} skipped"
    [ "${FAIL}" -eq 0 ] || exit 1
    exit 0
}

OP_UID="$(id -u)"
OP_GID="$(id -g)"

# Reaped on EXIT/INT/TERM. Populated as sandboxes are created.
RUN_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/boba_ownership_repair.XXXXXXXX")"
BG_PID=""
cleanup_all() {
    # A backgrounded repair must never outlive the suite (§11.4.14).
    if [[ -n "${BG_PID}" ]] && [[ "${BG_PID}" =~ ^[0-9]+$ ]] && (( BG_PID > 1 )); then
        kill -KILL "${BG_PID}" 2>/dev/null || true
    fi
    [[ -n "${RUN_ROOT:-}" && "${RUN_ROOT}" == *boba_ownership_repair.* ]] && rm -rf "${RUN_ROOT}"
    return 0
}
trap cleanup_all EXIT INT TERM

echo "test_ownership_repair.sh — contract cases:"
echo "  1 golden-bad      : wrongly-owned tree repaired, exit 0, change record NON-EMPTY"
echo "  2 preserve_mode   : credential-store entry keeps its EXACT bits (FR-015)"
echo "  3 negative control: path OUTSIDE declared scope left untouched (FR-005)"
echo "  4 golden-good     : correct tree -> exit 0, change record EMPTY, nothing mutated"
echo "  5 interrupt/resume: kill mid-run -> marker ABSENT -> re-run completes (FR-004a)"
echo "  6 scope re-arm    : scope change invalidates the marker (data-model E2)"
echo "  7 honest failure  : unrepairable item reported, does NOT exit 0 (FR-006)"
echo

# ---------------------------------------------------------------------------
# Prechecks. A missing artifact is the EXPECTED RED, not a harness defect.
# ---------------------------------------------------------------------------
if [[ ! -f "${LIB}" ]]; then
    fail "scripts/lib/ownership.sh missing — this suite depends on the shared helper"
    finish
fi

if [[ ! -f "${SCRIPT}" ]]; then
    echo "  ---------------------------------------------------------------"
    echo "  EXPECTED RED (§11.4.43 / §11.4.224(A) test-first):"
    echo "  scripts/ownership_repair.sh does not exist yet. This suite was"
    echo "  written BEFORE it, on purpose. This is NOT a harness defect — the"
    echo "  harness itself is exercised end to end the moment the artifact"
    echo "  appears (T019). Nothing below ran, so nothing below is claimed."
    echo "  ---------------------------------------------------------------"
    fail "MISSING ARTIFACT: scripts/ownership_repair.sh (contract: contracts/repair-cli.md)"
    finish
fi

if [[ ! -x "${SCRIPT}" ]]; then
    fail "scripts/ownership_repair.sh exists but is not executable"
    finish
fi

# python3 with PyYAML is a hard dependency of ownership.sh's scope parser. Its
# absence is an honest SKIP, never a silent pass (§11.4.3 / §11.4.201(6)).
if ! python3 -c 'import yaml' >/dev/null 2>&1; then
    skip "python3 with PyYAML unavailable — scripts/lib/ownership.sh cannot parse a scope (topology_unsupported)"
    finish
fi

# A secondary group is what makes a real not-operator-owned fixture possible
# unprivileged. PROBED, never assumed — membership in `id -G` does not by
# itself prove chgrp will succeed on this filesystem.
WRONG_GID=""
_probe_dir="${RUN_ROOT}/gidprobe"; mkdir -p "${_probe_dir}"; : > "${_probe_dir}/f"
for _g in $(id -G); do
    [[ "${_g}" == "${OP_GID}" ]] && continue
    if chgrp "${_g}" "${_probe_dir}/f" 2>/dev/null; then
        if [[ "$(stat -c '%g' "${_probe_dir}/f")" == "${_g}" ]]; then WRONG_GID="${_g}"; break; fi
    fi
done
rm -rf "${_probe_dir}"
if [[ -z "${WRONG_GID}" ]]; then
    skip "no secondary group this account can chgrp to — a real not-operator-owned fixture cannot be built unprivileged (hardware_not_present-class topology gap; see the DECLARED GAPS note at the end of this file)"
    finish
fi
echo "  fixture identity: operator ${OP_UID}:${OP_GID}; wrong-owner fixtures seeded as ${OP_UID}:${WRONG_GID}"
echo

# ---------------------------------------------------------------------------
# Harness helpers
# ---------------------------------------------------------------------------

# sb_new — build an isolated project root holding a BYTE-IDENTICAL copy of the
# artifact. sha256-verified: a divergent copy would mean the suite is not
# testing the artifact (§11.4.6 / §11.4.201(11) probe the artifact itself).
sb_new() {
    local sb
    sb="$(mktemp -d "${RUN_ROOT}/sb.XXXXXXXX")"
    mkdir -p "${sb}/scripts/lib" "${sb}/config" "${sb}/fixture"
    cp -p "${SCRIPT}" "${sb}/scripts/ownership_repair.sh"
    cp -p "${LIB}"    "${sb}/scripts/lib/ownership.sh"
    chmod +x "${sb}/scripts/ownership_repair.sh"
    local a b
    a="$(sha256sum "${SCRIPT}" | cut -d' ' -f1)"
    b="$(sha256sum "${sb}/scripts/ownership_repair.sh" | cut -d' ' -f1)"
    if [[ "${a}" != "${b}" ]]; then
        echo "sb_new: sandbox copy is NOT byte-identical to the artifact" >&2
        return 1
    fi
    printf '%s\n' "${sb}"
}

# sb_scope — write the sandbox scope file from TAB-separated entry specs on
# stdin: <abs-path>\t<kind>\t<optional>\t<preserve_mode>\t<recursive>
sb_scope() {
    local sb="$1" f p kind opt pres rec
    f="${sb}/config/owned_paths.yaml"
    { echo "schema_version: 1"; echo "paths:"; } > "${f}"
    while IFS=$'\t' read -r p kind opt pres rec; do
        [[ -n "${p}" ]] || continue
        {
            printf '  - path: "%s"\n' "${p}"
            printf '    kind: %s\n' "${kind}"
            printf '    optional: %s\n' "${opt}"
            printf '    preserve_mode: %s\n' "${pres}"
            printf '    recursive: %s\n' "${rec}"
        } >> "${f}"
    done
}

# seed_tree <dir> <count> <gid> — a real tree of real files at a real gid.
seed_tree() {
    local dir="$1" count="$2" gid="$3" i
    mkdir -p "${dir}/sub/deeper"
    for (( i = 0; i < count; i++ )); do
        printf 'item %d\n' "${i}" > "${dir}/item_$(printf '%05d' "${i}").bin"
    done
    printf 'nested\n' > "${dir}/sub/nested.bin"
    printf 'deep\n'   > "${dir}/sub/deeper/deep.bin"
    if [[ "${gid}" != "${OP_GID}" ]]; then
        chgrp -R "${gid}" "${dir}"
    fi
}

# manifest <dir> — relative path + uid + gid + mode, sorted. "Nothing mutated"
# is asserted against this, so it is a direct observation, not an inference.
manifest() { find "$1" -printf '%P %U %G %m\n' 2>/dev/null | LC_ALL=C sort; }

# wrong_owned_count <dir> — items NOT owned by the operator (uid AND gid).
wrong_owned_count() {
    find "$1" \( ! -uid "${OP_UID}" -o ! -gid "${OP_GID}" \) -printf '.' 2>/dev/null | wc -c
}

# artifact_files <sb> — every file the run could have written, EXCLUDING the
# fixture tree (that is the subject, not the record) and the copied scripts.
# config/ is deliberately NOT pruned: the change record may legitimately land
# there, and pruning it would make an "empty record" reading a FALSE-NULL.
# The scope file itself is skipped by exact path — it is a known carrier.
artifact_files() {
    local sb="$1"
    find "${sb}" \( -path "${sb}/fixture" -o -path "${sb}/scripts" \) -prune -o \
        -type f ! -path "${sb}/config/owned_paths.yaml" -print 2>/dev/null
}

# artifact_mentions <sb> <literal> — artifacts containing a literal string.
artifact_mentions() {
    local sb="$1" needle="$2" f
    while IFS= read -r f; do
        grep -qF -- "${needle}" "${f}" 2>/dev/null && printf '%s\n' "${f}"
    done < <(artifact_files "${sb}")
    return 0
}

# sb_fingerprint <sb> — the current scope fingerprint, computed by the SAME
# helper the implementation uses. Run in a subshell so the sourced library
# never leaks into this suite's shell.
sb_fingerprint() {
    local sb="$1"
    (
        OWNED_PATHS_FILE="${sb}/config/owned_paths.yaml"
        export OWNED_PATHS_FILE
        # shellcheck disable=SC1090
        source "${sb}/scripts/lib/ownership.sh"
        ownership_scope_fingerprint
    )
}

MARKER_DETECTOR_PROVEN=0
# marker_present <sb> — data-model E2 mandates a scope_fingerprint field, so a
# marker is detected structurally by that sha256 rather than by a hardcoded
# path or format.
marker_present() {
    local sb="$1" fp
    fp="$(sb_fingerprint "${sb}")" || return 2
    [[ -n "${fp}" ]] || return 2
    [[ -n "$(artifact_mentions "${sb}" "${fp}")" ]]
}

# run_repair <sb> [args…] — the REAL invocation path. The scope is supplied
# both ways (flag AND env) so whichever the implementation honours, the real
# config/owned_paths.yaml stays unreachable. Output lands in RUN_OUT/RUN_RC.
RUN_OUT=""; RUN_RC=0
run_repair() {
    local sb="$1"; shift
    RUN_OUT="$(
        cd "${sb}" && OWNED_PATHS_FILE="${sb}/config/owned_paths.yaml" \
            bash "${sb}/scripts/ownership_repair.sh" \
                --scope "${sb}/config/owned_paths.yaml" "$@" 2>&1
    )"
    RUN_RC=$?
    return 0
}

# signal_pid_safely <pid> <SIG> — §11.4.263. Refuses pid <= 1, refuses a
# non-integer, and refuses a pid whose REAL /proc cmdline is not the sandbox
# script. Never signals a process group, never uses pkill.
signal_pid_safely() {
    local pid="$1" sig="$2" want="$3" cmdline
    [[ "${pid}" =~ ^[0-9]+$ ]] || { echo "signal refused: pid '${pid}' is not an integer" >&2; return 1; }
    (( pid > 1 )) || { echo "signal refused: pid ${pid} <= 1 (§11.4.263)" >&2; return 1; }
    [[ -r "/proc/${pid}/cmdline" ]] || return 1
    cmdline="$(tr '\0' ' ' < "/proc/${pid}/cmdline" 2>/dev/null)" || return 1
    case "${cmdline}" in
        *"${want}"*) : ;;
        *) echo "signal refused: pid ${pid} cmdline does not match ${want}" >&2; return 1 ;;
    esac
    kill "-${sig}" "${pid}"
}

# ===========================================================================
# CASE 1 (+2, +3) — golden-bad, preserve_mode, negative control.
# One sandbox, one run: the negative control must be proven against the SAME
# invocation that did the repairing, otherwise it proves nothing about reach.
# ===========================================================================
echo "Case 1/2/3: golden-bad repair, preserve_mode, out-of-scope negative control"
SB1="$(sb_new)" || { fail "could not build sandbox"; finish; }
IN1="${SB1}/fixture/in_scope"
OUT1="${SB1}/fixture/out_of_scope"
CRED1="${IN1}/creds/boba.db"

seed_tree "${IN1}" 12 "${WRONG_GID}"
seed_tree "${OUT1}" 6 "${WRONG_GID}"
mkdir -p "${IN1}/creds"
printf 'pretend-encrypted-credential-store\n' > "${CRED1}"
chgrp "${WRONG_GID}" "${CRED1}"
chmod 600 "${CRED1}"

printf '%s\tdownloads\tfalse\tfalse\ttrue\n%s\tcredential-store\ttrue\ttrue\tfalse\n' \
    "${IN1}" "${CRED1}" | sb_scope "${SB1}"

OUT1_BEFORE="$(manifest "${OUT1}")"
IN1_WRONG_BEFORE="$(wrong_owned_count "${IN1}")"
run_repair "${SB1}"

# -- 1a: exit 0 -------------------------------------------------------------
if [[ "${RUN_RC}" -eq 0 ]]; then
    pass "golden-bad: exit 0 after repairing a wrongly-owned tree"
else
    fail "golden-bad: exit ${RUN_RC}, contract requires 0 when every in-scope item is operator-owned"
fi

# -- 1b: the tree is ACTUALLY operator-owned now (user-observable outcome) ---
IN1_WRONG_AFTER="$(wrong_owned_count "${IN1}")"
if [[ "${IN1_WRONG_BEFORE}" -gt 0 && "${IN1_WRONG_AFTER}" -eq 0 ]]; then
    pass "golden-bad: all ${IN1_WRONG_BEFORE} not-operator-owned items are now ${OP_UID}:${OP_GID}"
elif [[ "${IN1_WRONG_BEFORE}" -eq 0 ]]; then
    fail "golden-bad: fixture seeded 0 wrongly-owned items — the fixture is blind, not the script"
else
    fail "golden-bad: ${IN1_WRONG_AFTER}/${IN1_WRONG_BEFORE} items still not operator-owned after repair"
fi

# -- 1c: change record NON-EMPTY (E3) ---------------------------------------
_probe_item="${IN1}/item_00000.bin"
if [[ -n "$(artifact_mentions "${SB1}" "${_probe_item}")" ]]; then
    pass "golden-bad: change record is non-empty (a repaired item path is recorded)"
else
    fail "golden-bad: no artifact records the repaired path ${_probe_item} — E3 change record missing or empty"
fi

# -- 1d: marker written on success; ARMS the control needle (§11.4.201(7)(b)) -
marker_present "${SB1}"; _mp=$?
if [[ "${_mp}" -eq 0 ]]; then
    MARKER_DETECTOR_PROVEN=1
    pass "golden-bad: repair marker written after a successful pass and carries the scope fingerprint (E2)"
elif [[ "${_mp}" -eq 2 ]]; then
    fail "golden-bad: could not compute the scope fingerprint — the marker detector is BLIND (not evidence of absence)"
else
    fail "golden-bad: no artifact carries the scope fingerprint — marker absent, or it omits the mandated scope_fingerprint field (E2)"
fi

# -- 2: preserve_mode keeps EXACT bits (FR-015) -----------------------------
if [[ -f "${CRED1}" ]]; then
    _cred_mode="$(stat -c '%a' "${CRED1}")"
    _cred_gid="$(stat -c '%g' "${CRED1}")"
    if [[ "${_cred_mode}" == "600" ]]; then
        pass "preserve_mode: credential store kept mode 600 exactly"
    else
        fail "preserve_mode: credential store mode is ${_cred_mode}, was 600 — FR-015 forbids relaxing access while changing ownership"
    fi
    if [[ "${_cred_gid}" == "${OP_GID}" ]]; then
        pass "preserve_mode: credential store ownership WAS repaired (preserve_mode guards bits, not ownership)"
    else
        fail "preserve_mode: credential store still gid ${_cred_gid} — preserve_mode must not stop the ownership repair itself"
    fi
else
    fail "preserve_mode: fixture credential store vanished during the run"
fi

# -- 3: NEGATIVE CONTROL — out-of-scope tree untouched (FR-005) -------------
OUT1_AFTER="$(manifest "${OUT1}")"
if [[ "${OUT1_BEFORE}" == "${OUT1_AFTER}" ]]; then
    pass "negative control: out-of-scope tree byte-identical in owner/mode after the run (FR-005 scope fence holds)"
else
    fail "negative control: the repair reached OUTSIDE the declared scope — FR-005 violation"
    diff <(printf '%s\n' "${OUT1_BEFORE}") <(printf '%s\n' "${OUT1_AFTER}") | head -8 | sed 's/^/        /'
fi
if [[ -z "$(artifact_mentions "${SB1}" "${OUT1}/item_00000.bin")" ]]; then
    pass "negative control: no out-of-scope path appears in the change record"
else
    fail "negative control: an out-of-scope path was recorded as touched"
fi
echo

# ===========================================================================
# CASE 4 — golden-good: an already-correct tree.
# ===========================================================================
echo "Case 4: golden-good — already-correct tree"
SB2="$(sb_new)" || { fail "could not build sandbox"; finish; }
IN2="${SB2}/fixture/in_scope"
seed_tree "${IN2}" 10 "${OP_GID}"
printf '%s\tdownloads\tfalse\tfalse\ttrue\n' "${IN2}" | sb_scope "${SB2}"

IN2_BEFORE="$(manifest "${IN2}")"
if [[ "$(wrong_owned_count "${IN2}")" -ne 0 ]]; then
    fail "golden-good: fixture is not actually correct to begin with — the case would be vacuous"
else
    run_repair "${SB2}"
    IN2_AFTER="$(manifest "${IN2}")"

    if [[ "${RUN_RC}" -eq 0 ]]; then
        pass "golden-good: exit 0 on an already-correct tree"
    else
        fail "golden-good: exit ${RUN_RC} on an already-correct tree (§11.4.201(1) false-positive refusal)"
    fi

    if [[ "${IN2_BEFORE}" == "${IN2_AFTER}" ]]; then
        pass "golden-good: nothing mutated (owner and mode identical for every item)"
    else
        fail "golden-good: the repair mutated an already-correct tree"
        diff <(printf '%s\n' "${IN2_BEFORE}") <(printf '%s\n' "${IN2_AFTER}") | head -8 | sed 's/^/        /'
    fi

    _gg_recorded=""
    for _i in 00000 00003 00009; do
        if [[ -n "$(artifact_mentions "${SB2}" "${IN2}/item_${_i}.bin")" ]]; then
            _gg_recorded="${IN2}/item_${_i}.bin"; break
        fi
    done
    if [[ -z "${_gg_recorded}" ]]; then
        pass "golden-good: change record is EMPTY (no item recorded as changed)"
    else
        fail "golden-good: change record contains ${_gg_recorded} but nothing was changed — E3 is one entry per ALTERED item"
    fi

    # A no-change pass is still a FULLY SUCCESSFUL pass, so E2 requires a
    # marker — and FR-004c's "second run with a valid marker is a no-op" has
    # no precondition without one. This is also the assertion that gives this
    # case teeth: every other golden-good check passes on a do-nothing script.
    if marker_present "${SB2}"; then
        pass "golden-good: marker written after a successful no-change pass (E2 / FR-004c precondition)"
    else
        fail "golden-good: no marker after a successful pass — a later run has nothing to short-circuit on (E2)"
    fi
fi
echo

# ===========================================================================
# CASE 5 — interrupt -> resume. THE LOAD-BEARING CASE.
#
# data-model E2: the marker is written ONLY after a fully successful pass. If
# it were written at start, one crash would permanently mark the repair done
# and silently skip the remainder — the run-once optimisation would defeat the
# repair it optimises. This case is what makes that concrete.
# ===========================================================================
echo "Case 5: interrupt -> resume (marker written only on success)"
_c5_done=0
for _c5_size in 3000 9000; do
    [[ "${_c5_done}" -eq 1 ]] && break
    SB3="$(sb_new)" || { fail "could not build sandbox"; break; }
    IN3="${SB3}/fixture/in_scope"
    seed_tree "${IN3}" "${_c5_size}" "${WRONG_GID}"
    printf '%s\tdownloads\tfalse\tfalse\ttrue\n' "${IN3}" | sb_scope "${SB3}"
    _c5_total="$(wrong_owned_count "${IN3}")"

    (
        cd "${SB3}" && OWNED_PATHS_FILE="${SB3}/config/owned_paths.yaml" \
            bash "${SB3}/scripts/ownership_repair.sh" \
                --scope "${SB3}/config/owned_paths.yaml" >/dev/null 2>&1
    ) &
    BG_PID=$!

    # Poll for genuine PARTIAL progress — evidence-driven, not timing-driven,
    # so the interrupt lands in a real mid-run state rather than a guessed one.
    _c5_partial=0
    for _try in $(seq 1 800); do
        _remaining="$(wrong_owned_count "${IN3}")"
        if [[ "${_remaining}" -lt "${_c5_total}" && "${_remaining}" -gt 0 ]]; then
            _c5_partial=1; break
        fi
        kill -0 "${BG_PID}" 2>/dev/null || break
        sleep 0.01
    done

    if [[ "${_c5_partial}" -eq 1 ]]; then
        signal_pid_safely "${BG_PID}" TERM "${SB3}/scripts/ownership_repair.sh" || true
        for _try in $(seq 1 200); do
            kill -0 "${BG_PID}" 2>/dev/null || break
            sleep 0.01
        done
        if kill -0 "${BG_PID}" 2>/dev/null; then
            signal_pid_safely "${BG_PID}" KILL "${SB3}/scripts/ownership_repair.sh" || true
        fi
        wait "${BG_PID}" 2>/dev/null
        BG_PID=""

        # 5a: marker MUST be absent. This null is only trusted because the
        # same detector fired in case 1 (§11.4.201(7)(b) control needle).
        if [[ "${MARKER_DETECTOR_PROVEN}" -ne 1 ]]; then
            fail "interrupt: refusing to report 'marker absent' — the detector never fired a positive in case 1, so its null is BLIND, not evidence"
        elif marker_present "${SB3}"; then
            fail "interrupt: a repair marker EXISTS after an interrupted run — it was written at start, so one crash permanently skips the remainder (data-model E2 violation, FR-004a)"
        else
            pass "interrupt: no marker after an interrupted run (marker is written only on success)"
        fi

        # 5b: the next run resumes and completes.
        run_repair "${SB3}"
        if [[ "${RUN_RC}" -eq 0 ]]; then
            pass "resume: the follow-up run exits 0"
        else
            fail "resume: the follow-up run exited ${RUN_RC}"
        fi
        if [[ "$(wrong_owned_count "${IN3}")" -eq 0 ]]; then
            pass "resume: every remaining item was repaired (the interrupted remainder was NOT skipped)"
        else
            fail "resume: $(wrong_owned_count "${IN3}") items remain not-operator-owned — the resume skipped the remainder"
        fi
        if marker_present "${SB3}"; then
            pass "resume: marker written once the pass genuinely completed"
        else
            fail "resume: no marker after a completed run"
        fi
        _c5_done=1
    else
        if [[ -n "${BG_PID}" ]] && kill -0 "${BG_PID}" 2>/dev/null; then
            signal_pid_safely "${BG_PID}" KILL "${SB3}/scripts/ownership_repair.sh" || true
        fi
        wait "${BG_PID}" 2>/dev/null
        BG_PID=""
        if [[ "${_c5_size}" == "9000" ]]; then
            fail "interrupt: could not observe a partial mid-run state even at ${_c5_size} items — the case could not be driven, so nothing about FR-004a is claimed (§11.4.6)"
            _c5_done=1
        fi
    fi
done
echo

# ===========================================================================
# CASE 6 — a scope change re-arms the repair (data-model E2).
# Reuses SB1, which already holds a VALID marker from case 1. A newly-declared
# path must actually be repaired; an implementation that keys the marker on
# mere existence would report "already done" about work never performed.
# ===========================================================================
echo "Case 6: scope-fingerprint change re-arms the repair"
if [[ "${MARKER_DETECTOR_PROVEN}" -ne 1 ]]; then
    fail "scope re-arm: case 1 never established a valid marker, so this case has no precondition to invalidate"
else
    NEW1="${SB1}/fixture/newly_declared"
    seed_tree "${NEW1}" 8 "${WRONG_GID}"
    FP_BEFORE="$(sb_fingerprint "${SB1}")"

    printf '%s\tdownloads\tfalse\tfalse\ttrue\n%s\tcredential-store\ttrue\ttrue\tfalse\n%s\tdownloads\tfalse\tfalse\ttrue\n' \
        "${IN1}" "${CRED1}" "${NEW1}" | sb_scope "${SB1}"
    FP_AFTER="$(sb_fingerprint "${SB1}")"

    if [[ -n "${FP_BEFORE}" && -n "${FP_AFTER}" && "${FP_BEFORE}" != "${FP_AFTER}" ]]; then
        pass "scope re-arm: adding a declared path changes the scope fingerprint"
    else
        fail "scope re-arm: the fingerprint did not change when the scope did — the invalidation signal itself is broken"
    fi

    # No --force: the point is that the STALE marker must not suppress this.
    run_repair "${SB1}"
    if [[ "$(wrong_owned_count "${NEW1}")" -eq 0 ]]; then
        pass "scope re-arm: the newly-declared path WAS repaired despite an existing marker"
    else
        fail "scope re-arm: the newly-declared path was left unrepaired — the stale marker suppressed the run, so new scope is silently never repaired (E2)"
    fi
    if marker_present "${SB1}"; then
        pass "scope re-arm: the marker now carries the NEW scope fingerprint"
    else
        fail "scope re-arm: after a successful re-run no artifact carries the new fingerprint — the marker was not refreshed"
    fi
fi
echo

# ===========================================================================
# CASE 7 — honest failure (FR-006).
#
# The unrepairable item is a declared NON-OPTIONAL path that does not exist.
# data-model E1: "an absent non-optional path is an error, not a skip". This is
# a real, deterministic, unprivileged-constructible condition — it is not a
# stand-in for one. The scope file itself is valid and parseable, so exit 2
# ("could not run") does not apply here; the contract's exit 1 does.
# ===========================================================================
echo "Case 7: honest failure — an item that cannot be repaired"
SB4="$(sb_new)" || { fail "could not build sandbox"; finish; }
IN4="${SB4}/fixture/in_scope"
MISSING4="${SB4}/fixture/declared_but_absent"
seed_tree "${IN4}" 6 "${WRONG_GID}"
printf '%s\tdownloads\tfalse\tfalse\ttrue\n%s\tdownloads\tfalse\tfalse\ttrue\n' \
    "${IN4}" "${MISSING4}" | sb_scope "${SB4}"

if [[ -e "${MISSING4}" ]]; then
    fail "honest failure: the fixture's 'absent' path exists — the case would be vacuous"
else
    run_repair "${SB4}"

    # 7a — the FR-006 invariant: never exit 0 with failures outstanding.
    if [[ "${RUN_RC}" -ne 0 ]]; then
        pass "honest failure: did NOT exit 0 with an unrepairable item outstanding (FR-006)"
    else
        fail "honest failure: exit 0 while a declared non-optional path could not be repaired — FR-006 forbids reporting success for items not changed"
    fi

    # 7b — the contract's exit-code table. Reported separately so a 2 is a
    # precise finding (scope-unparseable semantics applied to a parseable
    # scope) rather than an undifferentiated failure.
    if [[ "${RUN_RC}" -eq 1 ]]; then
        pass "honest failure: exit 1 (contract: at least one item could not be repaired)"
    elif [[ "${RUN_RC}" -eq 2 ]]; then
        fail "honest failure: exit 2 (contract reserves 2 for a missing/unparseable SCOPE; this scope parses — an absent declared path is an unrepairable ITEM, exit 1)"
    elif [[ "${RUN_RC}" -eq 0 ]]; then
        skip "honest failure: exit-code table not evaluable on an exit 0 — the finding is already carried by the FR-006 assertion above, not counted twice"
    else
        fail "honest failure: exit ${RUN_RC}; the contract defines only 0/1/2"
    fi

    # 7c — reported INDIVIDUALLY (FR-006), not as an opaque aggregate.
    if printf '%s' "${RUN_OUT}" | grep -qF -- "${MISSING4}"; then
        pass "honest failure: the unrepairable path is named individually in the output"
    else
        fail "honest failure: output never names ${MISSING4} — FR-006 requires items be listed individually"
    fi
fi
echo

# ===========================================================================
# DECLARED GAPS (§11.4.6 — stated, never silently implied covered)
# ===========================================================================
echo "DECLARED GAPS — not covered by this unit suite, by measurement not by choice:"
echo "  * A real host-UID mismatch (the observed uid-100999 defect) cannot be"
echo "    seeded unprivileged: chown -> EPERM, unshare -Ur chown -> EINVAL, and"
echo "    unshare --map-users over the real subuid range -> EPERM (all measured"
echo "    2026-08-21). An unprivileged process also could not repair such an item"
echo "    back, so no implementation could turn that fixture green here. Covered"
echo "    by tests/integration/test_container_writes_owned_files.py instead."
echo "  * A genuine chown/chgrp EPERM on an EXISTING item (the real-world failure"
echo "    mode behind FR-006) needs a foreign-owned file, which is the same"
echo "    privilege gap. Case 7 uses the absent-non-optional-path route, which is"
echo "    real and deterministic but exercises a different code path than EPERM."
echo "  * FR-004d blocking-before-services and FR-004e real progress output are"
echo "    integration-layer properties and are deliberately not asserted here."

finish
