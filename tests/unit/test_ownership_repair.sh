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
# The real download tree is never read and never touched, and NOTHING outside a
# mktemp sandbox is ever MUTATED.
#
# ONE READ-ONLY EXCEPTION, added deliberately (Case 10): the shipped
# config/owned_paths.yaml and docker-compose.yml are READ — never written — to
# assert that the declared scope covers every container-written location. That
# assertion cannot be made against a fixture: a fixture scope is whatever this
# suite writes into it, so it would only ever prove the suite agrees with
# itself. The property under test is a property of the SHIPPED files, so the
# shipped files are what must be read (§11.4.201(11) — probe the artifact, not a
# stand-in for it).

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
echo "  8 symlink fence   : a link inside scope does NOT carry the repair outside (FR-005)"
echo "  9 preserve_mode fence: preserve_mode must not chmod THROUGH a symlink (FR-005+FR-015)"
echo " 10 scope coverage  : the SHIPPED scope declares every rw bind-mount source (FR-012)"
echo " 11 record loss     : a destroyed change record is REPORTED, not silently replaced"
echo " 12 record rotation : a superseded change record is preserved as its own artifact"
echo " 13 state dir       : OWNERSHIP_STATE_DIR overrides; the default path is unchanged"
echo " 14 relative scope  : a repo-relative entry resolves against the project root (E1)"
echo " 15 dotenv shape    : the shipped .env entry keeps a 600 credential file at 600"
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

# content_digest <dir> — relative path + sha256 of every file's CONTENT, sorted.
# manifest() is blind to content: a reach that truncates or rewrites a file
# while leaving owner and mode alone reads as "unchanged" to it (measured
# 2026-08-21 — a mutation that resolved symlinks by writing through them left
# the manifest assertion GREEN). Used to close that dimension where a scope
# fence is being proven, over trees small enough for it to be free.
content_digest() {
    local root="$1" rel
    while IFS= read -r rel; do
        printf '%s  %s\n' "$(sha256sum < "${root}/${rel}" | cut -d' ' -f1)" "${rel}"
    done < <(find "${root}" -type f -printf '%P\n' 2>/dev/null | LC_ALL=C sort)
}

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
for _c5_size in 800 3000; do
    [[ "${_c5_done}" -eq 1 ]] && break
    SB3="$(sb_new)" || { fail "could not build sandbox"; break; }
    IN3="${SB3}/fixture/in_scope"
    seed_tree "${IN3}" "${_c5_size}" "${WRONG_GID}"
    printf '%s\tdownloads\tfalse\tfalse\ttrue\n' "${IN3}" | sb_scope "${SB3}"
    _c5_total="$(wrong_owned_count "${IN3}")"

    # `exec` is load-bearing: without it $! is the SUBSHELL's pid, whose
    # /proc cmdline is this test script, and signal_pid_safely's identity gate
    # correctly refuses to signal it — the interrupt then never lands and the
    # case reports a false failure against a correct implementation. Measured
    # 2026-08-21 during the reference-implementation validation run.
    (
        cd "${SB3}" && exec env OWNED_PATHS_FILE="${SB3}/config/owned_paths.yaml" \
            bash "${SB3}/scripts/ownership_repair.sh" \
                --scope "${SB3}/config/owned_paths.yaml" >/dev/null 2>&1
    ) &
    BG_PID=$!

    # Poll for genuine PARTIAL progress — evidence-driven, not timing-driven,
    # so the interrupt lands in a real mid-run state rather than a guessed one.
    # Sizes are a ladder, not a guess: the base must be small enough to keep
    # this suite well inside pre_build invariant 30's `timeout 300` (measured
    # 2026-08-21 against a deliberately naive fork-per-file reference
    # implementation), and the escalation exists because a FAST implementation
    # could finish 800 items before the first poll observes a partial state.
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
        _c5_signalled=1
        if ! signal_pid_safely "${BG_PID}" TERM "${SB3}/scripts/ownership_repair.sh"; then
            _c5_signalled=0
        fi
        for _try in $(seq 1 200); do
            kill -0 "${BG_PID}" 2>/dev/null || break
            sleep 0.01
        done
        if kill -0 "${BG_PID}" 2>/dev/null; then
            signal_pid_safely "${BG_PID}" KILL "${SB3}/scripts/ownership_repair.sh" || _c5_signalled=0
        fi
        wait "${BG_PID}" 2>/dev/null
        BG_PID=""

        # A refused signal means the run was NEVER interrupted, so every
        # assertion below would be about a COMPLETED pass. Claim nothing.
        if [[ "${_c5_signalled}" -ne 1 ]]; then
            fail "interrupt: could not signal the backgrounded repair (pid identity gate refused) — the run was not interrupted, so nothing about FR-004a is claimed (§11.4.6)"
            _c5_done=1
            continue
        fi

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
        if [[ "${_c5_size}" == "3000" ]]; then
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
# CASE 8 — the scope fence under SYMLINKS (FR-005).
#
# The repair's most dangerous property is out-of-scope REACH: it changes
# ownership recursively, so a symlink INSIDE the declared scope pointing
# OUTSIDE it is the one construct that could carry that mutation to a file
# nobody declared. `chown -h` and find's default -P are what fence it, and an
# unexercised fence is one refactor away from not being one — case 3's
# negative control proves the walk does not wander, but a sibling tree is not
# a symlink and cannot prove anything about dereference. So this case drives
# all three shapes a symlink can take through a REAL run:
#
#   * a symlink to a FILE outside the scope      — dereference on chown
#   * a symlink to a DIRECTORY outside the scope — recursive descent, the one
#     that could run away and walk a tree nobody declared
#   * a DANGLING symlink                         — must not crash the run nor
#     make it exit non-zero spuriously (§11.4.201(1) false-positive refusal)
#
# NON-VACUITY IS THE WHOLE DIFFICULTY. Two ways this case could pass while
# proving nothing, both guarded before any assertion is made:
#   (a) the out-of-scope targets are already in the state a reach would leave
#       them in, so "unchanged" says nothing -> they are seeded at the WRONG
#       gid, and one of them additionally at mode 600, so a reach in EITHER
#       the ownership or the mode dimension is a visible delta;
#   (b) the symlinks are operator-owned already, so the walk never names them
#       and the fence is never even approached -> they are `chgrp -h`'d to the
#       wrong gid and that is ASSERTED, not assumed, before the run.
#
# Every link points at a target this suite created inside its OWN mktemp
# sandbox. Nothing here points at a real path: if the fence were broken, the
# blast radius is the sandbox the EXIT trap reaps (§11.4.14).
# ===========================================================================
echo "Case 8: out-of-scope reach through symlinks (FR-005)"
SB5="$(sb_new)" || { fail "could not build sandbox"; finish; }
IN5="${SB5}/fixture/in_scope"
OUT5="${SB5}/fixture/out_of_scope"
LNK_FILE="${IN5}/link_to_outside_file"
LNK_DIR="${IN5}/link_to_outside_dir"
LNK_DANGLE="${IN5}/dangling_link"
DANGLE_TARGET="${SB5}/fixture/target_that_never_exists"

seed_tree "${IN5}" 6 "${WRONG_GID}"
seed_tree "${OUT5}" 4 "${WRONG_GID}"
# A second observable dimension: mode. Seeded at 600 so a mode-following
# restore step would show up in the manifest exactly as an ownership reach does.
printf 'out-of-scope-secret\n' > "${OUT5}/secret.bin"
chgrp "${WRONG_GID}" "${OUT5}/secret.bin"
chmod 600 "${OUT5}/secret.bin"

# Links are created AFTER seed_tree so its `chgrp -R` cannot touch them, and
# are given the wrong gid with `chgrp -h` so the LINK — never its target — is
# what the walk will find not-operator-owned.
ln -s "${OUT5}/secret.bin"    "${LNK_FILE}"
ln -s "${OUT5}/sub"           "${LNK_DIR}"
ln -s "${DANGLE_TARGET}"      "${LNK_DANGLE}"
chgrp -h "${WRONG_GID}" "${LNK_FILE}" "${LNK_DIR}" "${LNK_DANGLE}"

# Only the in-scope tree is declared. preserve_mode is false — the same shape
# the real download tree and config tree use.
printf '%s\tdownloads\tfalse\tfalse\ttrue\n' "${IN5}" | sb_scope "${SB5}"

# -- fixture guards: refuse to claim anything from a blind fixture -----------
_c8_links_wrong=0
for _l in "${LNK_FILE}" "${LNK_DIR}" "${LNK_DANGLE}"; do
    [[ -L "${_l}" ]] || continue
    [[ "$(stat -c '%u:%g' "${_l}")" == "${OP_UID}:${OP_GID}" ]] || _c8_links_wrong=$((_c8_links_wrong + 1))
done
OUT5_BEFORE="$(manifest "${OUT5}")"
OUT5_CONTENT_BEFORE="$(content_digest "${OUT5}")"
OUT5_WRONG_BEFORE="$(wrong_owned_count "${OUT5}")"
IN5_WRONG_BEFORE="$(wrong_owned_count "${IN5}")"

if [[ "${_c8_links_wrong}" -ne 3 ]]; then
    fail "symlink fence: only ${_c8_links_wrong}/3 links are not-operator-owned before the run — the walk would never name them and the fence is never approached (blind fixture, not a result)"
elif [[ "${OUT5_WRONG_BEFORE}" -eq 0 ]]; then
    fail "symlink fence: the out-of-scope tree is already operator-owned — a reach would leave no trace, so 'unchanged' would prove nothing (blind fixture, not a result)"
elif [[ -e "${DANGLE_TARGET}" ]]; then
    fail "symlink fence: the dangling link's target exists — it is not dangling, so the case would not be the case (blind fixture, not a result)"
else
    run_repair "${SB5}"

    # -- 8a: the run genuinely DID work, so 8b is not green on a no-op ------
    if [[ "${IN5_WRONG_BEFORE}" -gt 0 && "$(wrong_owned_count "${IN5}")" -eq 0 ]]; then
        pass "symlink fence: the in-scope tree WAS repaired in this run (the fence is proven against a run that really mutated, not a no-op)"
    else
        fail "symlink fence: the in-scope tree was not repaired ($(wrong_owned_count "${IN5}")/${IN5_WRONG_BEFORE} still wrong) — every out-of-scope assertion below would be vacuous"
    fi

    # -- 8b: THE FENCE. Out-of-scope tree byte-identical in owner/group/mode.
    # One assertion covers all three reach vectors: dereference-on-chown (the
    # file link), recursive descent (the directory link), and any mode-follow.
    OUT5_AFTER="$(manifest "${OUT5}")"
    if [[ "${OUT5_BEFORE}" == "${OUT5_AFTER}" ]]; then
        pass "symlink fence: out-of-scope targets byte-identical in owner/group/mode — a symlink inside the scope did NOT carry the repair outside it (FR-005)"
    else
        fail "symlink fence: the repair reached OUTSIDE the declared scope THROUGH A SYMLINK — FR-005 violation"
        diff <(printf '%s\n' "${OUT5_BEFORE}") <(printf '%s\n' "${OUT5_AFTER}") | head -8 | sed 's/^/        /'
    fi

    # -- 8b2: and unchanged in CONTENT. A fence that only watches metadata
    # would call a reach that truncated or rewrote an out-of-scope file
    # "byte-identical" — the worse reach reported as the clean one.
    if [[ "${OUT5_CONTENT_BEFORE}" == "$(content_digest "${OUT5}")" ]]; then
        pass "symlink fence: out-of-scope file CONTENT unchanged (no write reached through a link either)"
    else
        fail "symlink fence: out-of-scope file content changed — the repair WROTE through a symlink"
        diff <(printf '%s\n' "${OUT5_CONTENT_BEFORE}") <(printf '%s\n' "$(content_digest "${OUT5}")") | head -8 | sed 's/^/        /'
    fi

    # -- 8c: nor is an out-of-scope path recorded as touched (E3).
    # Probed under BOTH spellings, because a walk that follows links records
    # the path AS IT REACHED IT: a resolved walk names ${OUT5}/sub/nested.bin,
    # while a link-traversing walk names ${LNK_DIR}/nested.bin — the same
    # out-of-scope file under a name the first probe alone would never match.
    # (Measured: probing only the resolved spelling left this assertion GREEN
    # against a deliberately link-following `find -L` mutation.) The links
    # THEMSELVES are in scope and are legitimately recorded, so only paths
    # strictly UNDER the directory link are treated as a leak.
    _c8_leaked=""
    for _p in "${OUT5}/secret.bin" "${OUT5}/sub/nested.bin" "${OUT5}/sub/deeper/deep.bin" \
              "${LNK_DIR}/nested.bin" "${LNK_DIR}/deeper/deep.bin"; do
        if [[ -n "$(artifact_mentions "${SB5}" "${_p}")" ]]; then _c8_leaked="${_p}"; break; fi
    done
    if [[ -z "${_c8_leaked}" ]]; then
        pass "symlink fence: no out-of-scope path appears in the change record, under either the resolved or the link-traversed spelling"
    else
        fail "symlink fence: the change record names the out-of-scope path ${_c8_leaked} — the walk went through a link and treated what it found as in scope"
    fi

    # -- 8d: the links THEMSELVES are in scope and must be repaired AS links.
    # This is the suite's own contract: wrong_owned_count uses find's default
    # -P, so a link counts by its own lstat identity.
    _c8_unrepaired=""
    for _l in "${LNK_FILE}" "${LNK_DIR}" "${LNK_DANGLE}"; do
        if [[ "$(stat -c '%u:%g' "${_l}" 2>/dev/null)" != "${OP_UID}:${OP_GID}" ]]; then
            _c8_unrepaired="${_l}"; break
        fi
    done
    if [[ -z "${_c8_unrepaired}" ]]; then
        pass "symlink fence: all three in-scope links are now operator-owned AS LINKS (fencing the target is not an excuse to skip the link)"
    else
        fail "symlink fence: ${_c8_unrepaired} is still not operator-owned — an in-scope item was skipped rather than repaired"
    fi

    # -- 8e: the links survive as links, still pointing where they did ------
    _c8_mangled=""
    for _l in "${LNK_FILE}:${OUT5}/secret.bin" "${LNK_DIR}:${OUT5}/sub" "${LNK_DANGLE}:${DANGLE_TARGET}"; do
        _lp="${_l%%:*}"; _lt="${_l#*:}"
        if [[ ! -L "${_lp}" || "$(readlink "${_lp}")" != "${_lt}" ]]; then _c8_mangled="${_lp}"; break; fi
    done
    if [[ -z "${_c8_mangled}" ]]; then
        pass "symlink fence: every link is still a link pointing at its original target (the repair did not resolve or replace it)"
    else
        fail "symlink fence: ${_c8_mangled} is no longer a symlink to its original target — the repair rewrote the link itself"
    fi

    # -- 8f: a DANGLING link is not a failure. §11.4.201(1): refusing a run
    # over a broken link the operator legitimately has is a FAIL-bluff exactly
    # as a missed defect is a PASS-bluff.
    if [[ "${RUN_RC}" -eq 0 ]]; then
        pass "symlink fence: exit 0 with a dangling symlink in scope (a broken link is not an unrepairable item)"
    else
        fail "symlink fence: exit ${RUN_RC} — a dangling symlink in scope made the run report failure (§11.4.201(1) false-positive refusal)"
    fi

    # -- 8g: and the dangling link's absent target is still absent ----------
    if [[ ! -e "${DANGLE_TARGET}" && ! -L "${DANGLE_TARGET}" ]]; then
        pass "symlink fence: the dangling link's absent target was not created by the run"
    else
        fail "symlink fence: the run created ${DANGLE_TARGET} — a broken link must be chowned as a link, never materialised"
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
echo "    by tests/ownership/test_container_writes_owned_files.py instead."
echo "  * A genuine chown/chgrp EPERM on an EXISTING item (the real-world failure"
echo "    mode behind FR-006) needs a foreign-owned file, which is the same"
echo "    privilege gap. Case 7 uses the absent-non-optional-path route, which is"
echo "    real and deterministic but exercises a different code path than EPERM."
echo "  * FR-004d blocking-before-services and FR-004e real progress output are"
echo "    integration-layer properties and are deliberately not asserted here."
echo "  * The preserve_mode:TRUE symlink path WAS broken and is now covered"
echo "    by Case 9: a bare chmod follows a symlink on Linux (there is no -h),"
echo "    and a symlink's find %m is 777, so the mode-restore step moved an"
echo "    OUT-OF-SCOPE target from 600 to 777. Measured and fixed 2026-08-21."


# ---------------------------------------------------------------------------
# CASE 9 — the scope fence under symlinks with preserve_mode TRUE (FR-005 + FR-015).
#
# WHY SEPARATE FROM CASE 8. Case 8 fences a preserve_mode:FALSE entry, the shape
# the download tree and config tree use. preserve_mode:TRUE is DIFFERENT CODE:
# it runs a mode-restore step after the chown, and that step is where the fence
# leaked.
#
# `chmod` has NO `-h` counterpart on Linux, so it ALWAYS follows a symlink and
# changes the TARGET. A symlink's `find -printf '%m'` is 777, so "restoring the
# item's own mode" meant chmod 777 ON THE TARGET, which may sit outside the
# declared scope. Measured against the real script before the fix:
# out-of-scope target 600 -> 777.
#
# Not academic: the SHIPPED config/owned_paths.yaml has exactly ONE
# preserve_mode:true entry — config/boba.db, the encrypted credential store. An
# operator who had relocated that DB and symlinked it into config/ would have
# had the real store widened to 777 by the very tool whose FR-015 exists to stop
# a usability fix from becoming a security regression.
# ---------------------------------------------------------------------------
echo
echo "Case 9: preserve_mode TRUE must not chmod through a symlink (FR-005 + FR-015)"
SB6="$(sb_new)" || { fail "could not build sandbox"; finish; }
IN6="${SB6}/fixture/in_scope_pm"
OUT6="${SB6}/fixture/out_of_scope_pm"
LNK6="${IN6}/relocated_store.db"

seed_tree "${IN6}" 3 "${WRONG_GID}"
mkdir -p "${OUT6}"
printf 'encrypted-credential-bytes\n' > "${OUT6}/credstore.bin"
chmod 600 "${OUT6}/credstore.bin"

# The LINK is wrongly-owned so the walk finds it; its TARGET is correctly owned
# and mode 600, so any change to the target is unambiguously a reach rather than
# a repair the tool was asked to perform.
ln -s "${OUT6}/credstore.bin" "${LNK6}"
chgrp -h "${WRONG_GID}" "${LNK6}"

printf '%s\tproject-config\tfalse\ttrue\ttrue\n' "${IN6}" | sb_scope "${SB6}"

OUT6_MODE_BEFORE="$(stat -c '%a' "${OUT6}/credstore.bin")"
OUT6_DIGEST_BEFORE="$(content_digest "${OUT6}")"
IN6_WRONG_BEFORE="$(wrong_owned_count "${IN6}")"

if [[ ! -L "${LNK6}" ]]; then
    fail "preserve_mode symlink fence: fixture link is not a symlink — nothing was tested"
elif [[ "$(stat -c '%g' "${LNK6}")" == "${OP_GID}" ]]; then
    fail "preserve_mode symlink fence: fixture link already operator-owned — the walk would never reach it"
elif [[ "${OUT6_MODE_BEFORE}" != "600" ]]; then
    fail "preserve_mode symlink fence: fixture target is mode ${OUT6_MODE_BEFORE}, expected 600 — a widening would be invisible"
else
    run_repair "${SB6}"

    if [[ "${IN6_WRONG_BEFORE}" -gt 0 && "$(wrong_owned_count "${IN6}")" -eq 0 ]]; then
        pass "preserve_mode symlink fence: the in-scope tree WAS repaired in this run (9b is not green on a no-op)"
    else
        fail "preserve_mode symlink fence: in-scope tree not repaired — the fence assertion would be vacuous"
    fi

    _c9_mode_after="$(stat -c '%a' "${OUT6}/credstore.bin" 2>/dev/null)"
    if [[ "${_c9_mode_after}" == "${OUT6_MODE_BEFORE}" ]]; then
        pass "preserve_mode symlink fence: out-of-scope target still mode ${OUT6_MODE_BEFORE} — chmod did not follow the link"
    else
        fail "preserve_mode symlink fence: out-of-scope target went ${OUT6_MODE_BEFORE} -> ${_c9_mode_after} — chmod followed the symlink (FR-005 breach; FR-015 inverted when that target is a credential store)"
    fi

    if [[ "$(content_digest "${OUT6}")" == "${OUT6_DIGEST_BEFORE}" ]]; then
        pass "preserve_mode symlink fence: out-of-scope content byte-identical"
    else
        fail "preserve_mode symlink fence: out-of-scope content changed"
    fi

    if [[ -L "${LNK6}" && "$(readlink "${LNK6}")" == "${OUT6}/credstore.bin" ]]; then
        pass "preserve_mode symlink fence: the link is still a link pointing at its original target"
    else
        fail "preserve_mode symlink fence: the link was resolved, rewritten or replaced"
    fi
fi



# ===========================================================================
# CASE 10 — the SHIPPED scope declares every container-written location.
#
# WHY THIS CASE READS THE REAL FILES (the one read-only exception, see header).
# FR-012's scope is "ALL container-written paths". A location the containers
# write but that config/owned_paths.yaml does not declare is invisible to the
# whole feature at once: the precondition never probes it, the repair never
# walks it, and the pre-build gate reports nothing about it. That is not a
# backlog question ("is it wrongly owned TODAY?") but a DETECTION question, and
# owned_paths.yaml's own header answers it: "A location the system writes but
# that is absent here is UNDECLARED, and the gate reports it rather than
# silently passing — silence is not an exemption (§11.4.201(6))."
#
# The expected set is DERIVED from docker-compose.yml, never hardcoded here: a
# hardcoded list is a second source of truth that drifts the moment a mount is
# added, which is the very way the gap arose (§11.4.238 — the automated check
# must be the discoverer).
#
# READ-ONLY mounts are excluded by construction: a container cannot write
# through `:ro`, so it cannot create wrongly-owned content there.
# A declared ANCESTOR counts as coverage — `config/jackett` is written rw by
# the jackett service and is covered by the declared `config` tree.
# ===========================================================================
echo
echo "Case 10: the SHIPPED scope declares every container-written (rw bind-mount) location"
_C10_COMPOSE="${PROJECT_ROOT}/docker-compose.yml"
_C10_SCOPE="${PROJECT_ROOT}/config/owned_paths.yaml"
if [[ ! -f "${_C10_COMPOSE}" ]]; then
    fail "scope coverage: ${_C10_COMPOSE} missing — cannot derive the container-written set"
elif [[ ! -f "${_C10_SCOPE}" ]]; then
    fail "scope coverage: ${_C10_SCOPE} missing — nothing declares the ownership scope"
else
    _C10_OUT="$(python3 - "${_C10_COMPOSE}" "${_C10_SCOPE}" "${PROJECT_ROOT}" <<'PYEOF'
import os, re, sys, yaml

compose_p, scope_p, root = sys.argv[1], sys.argv[2], sys.argv[3]

def expand(raw):
    def sub(m):
        var, dflt = m.group(1), m.group(3)
        return os.environ.get(var) or (dflt if dflt is not None else "")
    return re.sub(r'\$\{([A-Za-z_][A-Za-z0-9_]*)(:-([^}]*))?\}', sub, raw)

def split_mount(vol):
    """Split a compose volume spec on ':' — but NEVER inside a ${...} span.

    MEASURED 2026-08-21: a naive vol.split(':') cuts
    '${QBITTORRENT_DATA_DIR:-/mnt/DATA}:/downloads' at the ':-' INSIDE the
    default-value syntax, yielding the source '${QBITTORRENT_DATA_DIR'. That
    reported the download root as UNDECLARED when it is the first entry in the
    shipped scope — a §11.4.201 instrument defect producing a confident wrong
    answer, in the very check whose job is to detect undeclared paths.
    """
    out, cur, depth, i = [], [], 0, 0
    while i < len(vol):
        c = vol[i]
        if c == "$" and vol[i + 1:i + 2] == "{":
            depth += 1
            cur.append("${")
            i += 2
            continue
        if c == "}" and depth > 0:
            depth -= 1
        if c == ":" and depth == 0:
            out.append("".join(cur))
            cur = []
            i += 1
            continue
        cur.append(c)
        i += 1
    out.append("".join(cur))
    return out


def absolutise(p):
    p = expand(p)
    if not p:
        return ""
    if not p.startswith("/"):
        p = os.path.join(root, p)
    return os.path.normpath(p)

# ---- the container-written set, derived from the compose file --------------
compose = yaml.safe_load(open(compose_p)) or {}
written = {}   # abs path -> "svc[, svc]"
for svc, body in (compose.get("services") or {}).items():
    for vol in ((body or {}).get("volumes") or []):
        if not isinstance(vol, str):
            continue
        parts = split_mount(vol)
        if len(parts) < 2:
            continue
        src, opts = parts[0], parts[2:]
        # read-only mounts cannot produce wrongly-owned content
        if any("ro" == o.strip() for o in opts):
            continue
        # named volumes are managed by the runtime, not host paths in this repo
        if not (src.startswith("./") or src.startswith("/") or src.startswith("${")):
            continue
        a = absolutise(src)
        if not a:
            continue
        written.setdefault(a, set()).add(svc)

# ---- the declared set ------------------------------------------------------
scope = yaml.safe_load(open(scope_p)) or {}
declared = []
for e in (scope.get("paths") or []):
    a = absolutise(str(e.get("path", "")))
    if a:
        declared.append(a)

def covered(target):
    for d in declared:
        if target == d or target.startswith(d.rstrip("/") + "/"):
            return True
    return False

missing = sorted(t for t in written if not covered(t))
for m in missing:
    print("MISSING\t%s\t%s" % (m, ",".join(sorted(written[m]))))
print("SUMMARY\t%d\t%d" % (len(written), len(missing)))
PYEOF
)"
    _C10_RC=$?
    if [[ "${_C10_RC}" -ne 0 || -z "${_C10_OUT}" ]]; then
        fail "scope coverage: could not derive the container-written set (python/PyYAML failure) — this is a BLIND read, not a clean result (§11.4.201(6))"
    else
        _c10_total="$(printf '%s\n' "${_C10_OUT}" | awk -F'\t' '$1=="SUMMARY"{print $2}')"
        _c10_miss="$(printf '%s\n' "${_C10_OUT}"  | awk -F'\t' '$1=="SUMMARY"{print $3}')"
        # CONTROL NEEDLE (§11.4.201(7)(b)): a zero-missing reading is only
        # evidence if the derivation actually saw the mounts. A derivation that
        # found NO rw bind mounts at all is blind, and its zero says nothing.
        if [[ -z "${_c10_total}" || "${_c10_total}" -eq 0 ]]; then
            fail "scope coverage: derived 0 rw bind-mount sources from docker-compose.yml — the instrument is BLIND, so 'nothing missing' is not evidence"
        elif [[ "${_c10_miss}" -eq 0 ]]; then
            pass "scope coverage: all ${_c10_total} rw bind-mount source(s) in docker-compose.yml are declared (or covered by a declared ancestor)"
        else
            fail "scope coverage: ${_c10_miss}/${_c10_total} container-written location(s) are UNDECLARED — FR-012 says the scope is ALL container-written paths, and an undeclared path is invisible to the precondition, the repair AND the gate"
            printf '%s\n' "${_C10_OUT}" | awk -F'\t' '$1=="MISSING"{printf "        UNDECLARED: %s  (written rw by: %s)\n", $2, $3}'
        fi
    fi
fi

# ===========================================================================
# CASE 11 — a destroyed change record is REPORTED, never silently replaced.
#
# FORENSIC ANCHOR (measured on the live host, 2026-08-21): the completion
# marker and the FR-004b change record were both written at 17:20 (the journal
# carries "already complete for this scope (marker: logs/ownership/
# repair-marker.json)"), and by 20:32 logs/ was EMPTY with a 19:21 mtime — a
# repo actor had deleted the operator's recovery trail. Nothing noticed.
#
# The record's home is a gitignored logs/ tree that repo actors demonstrably
# clean, so "append-only" describes this script's own discipline, NOT a
# guarantee about the file's survival. A run that finds its predecessor's
# record gone and quietly starts a new one reports a recovery trail it does not
# have, which is the §11.4/§11.4.1 bluff at the durability layer. It must say so.
# ===========================================================================
echo
echo "Case 11: a destroyed change record is reported, not silently replaced"
SB7="$(sb_new)" || { fail "could not build sandbox"; finish; }
IN7="${SB7}/fixture/t1"
seed_tree "${IN7}" 3 "${WRONG_GID}"
printf '%s\tdownloads\tfalse\tfalse\ttrue\n' "${IN7}" | sb_scope "${SB7}"

run_repair "${SB7}"
_C11_PROBE="${IN7}/item_00000.bin"
mapfile -t _C11_RECORDS < <(artifact_mentions "${SB7}" "${_C11_PROBE}")

if [[ "${RUN_RC}" -ne 0 ]]; then
    fail "record loss: the seeding run exited ${RUN_RC} — no precondition to destroy"
elif [[ "${#_C11_RECORDS[@]}" -eq 0 ]]; then
    fail "record loss: the seeding run wrote no change record naming ${_C11_PROBE} — nothing to destroy, so this case would prove nothing"
else
    # Destroy exactly what an external actor destroyed: the record file(s).
    # The marker is deliberately LEFT IN PLACE — it is the thing that still
    # claims a completed run, and the loss is only detectable against it.
    for _f in "${_C11_RECORDS[@]}"; do rm -f -- "${_f}"; done
    if [[ -n "$(artifact_mentions "${SB7}" "${_C11_PROBE}")" ]]; then
        fail "record loss: could not destroy the change record — the fixture precondition was not established"
    else
        run_repair "${SB7}" --force
        if grep -qi 'change record named by the completion marker is MISSING' <<< "${RUN_OUT}"; then
            pass "record loss: the run REPORTS that the marker's named change record is gone (FR-004b trail loss is surfaced, not swallowed)"
        else
            fail "record loss: the run started a fresh record SILENTLY — a destroyed FR-004b recovery trail was neither detected nor reported"
            printf '%s\n' "${RUN_OUT}" | sed 's/^/        /' | head -8
        fi
    fi
fi

# ===========================================================================
# CASE 12 — a superseded change record is PRESERVED as its own artifact.
#
# data-model E3 calls the record "durable" and "append-only". Appending forever
# into ONE file makes that single file the whole trail: it is the single point
# of loss Case 11 just demonstrated, and it also means run N's record cannot be
# read without reading every prior run's. Rotating each run's record into its
# own artifact preserves the superseded trail WITHOUT depending on one file
# surviving, and makes each run's record self-contained.
# ===========================================================================
echo
echo "Case 12: a superseded change record is preserved as a distinct artifact"
SB8="$(sb_new)" || { fail "could not build sandbox"; finish; }
IN8A="${SB8}/fixture/first"
IN8B="${SB8}/fixture/second"
seed_tree "${IN8A}" 3 "${WRONG_GID}"
printf '%s\tdownloads\tfalse\tfalse\ttrue\n' "${IN8A}" | sb_scope "${SB8}"
run_repair "${SB8}"
_C12_A="${IN8A}/item_00000.bin"

if [[ "${RUN_RC}" -ne 0 ]]; then
    fail "record rotation: the first run exited ${RUN_RC} — no first record to supersede"
elif [[ -z "$(artifact_mentions "${SB8}" "${_C12_A}")" ]]; then
    fail "record rotation: the first run wrote no record naming ${_C12_A} — nothing to supersede"
else
    # Second run, armed by a genuine scope change (the realistic path).
    seed_tree "${IN8B}" 3 "${WRONG_GID}"
    printf '%s\tdownloads\tfalse\tfalse\ttrue\n%s\tdownloads\tfalse\tfalse\ttrue\n' \
        "${IN8A}" "${IN8B}" | sb_scope "${SB8}"
    run_repair "${SB8}"
    _C12_B="${IN8B}/item_00000.bin"

    mapfile -t _C12_FA < <(artifact_mentions "${SB8}" "${_C12_A}")
    mapfile -t _C12_FB < <(artifact_mentions "${SB8}" "${_C12_B}")

    if [[ "${#_C12_FA[@]}" -eq 0 ]]; then
        fail "record rotation: the FIRST run's record was DESTROYED by the second run — a superseded trail must be preserved, never overwritten"
    else
        pass "record rotation: the first run's record survives the second run"
    fi

    if [[ "${#_C12_FB[@]}" -eq 0 ]]; then
        fail "record rotation: the second run wrote no record naming ${_C12_B} — the second run recorded nothing"
    else
        # Disjointness is the rotation property: run 2 must NOT have appended
        # into run 1's artifact, and run 1's artifact must still exist alongside.
        _c12_shared=0
        for _a in "${_C12_FA[@]}"; do
            for _b in "${_C12_FB[@]}"; do
                [[ "${_a}" == "${_b}" ]] && _c12_shared=1
            done
        done
        if [[ "${_c12_shared}" -eq 0 ]]; then
            pass "record rotation: each run's record is its own artifact (run 1 and run 2 share no record file)"
        else
            fail "record rotation: run 2 appended into run 1's record file — the two runs share an artifact, so ONE deletion still destroys BOTH trails (the Case 11 failure mode, unmitigated)"
        fi
    fi
fi

# ===========================================================================
# CASE 13 — the state directory is overridable, and its DEFAULT is unchanged.
#
# STATE_DIR was a fixed constant, so an ad-hoc invocation shared the live
# operator's marker and change record: a hand-run repair could mark the live
# scope "complete" or interleave its records with the real ones. Overridable
# state makes an ad-hoc run harmless. The default MUST NOT move — the live path
# logs/ownership/ is what the operator, the journal line and the documentation
# all already name, so this case pins it explicitly rather than trusting it.
# ===========================================================================
echo
echo "Case 13: the state directory is overridable, default unchanged"
SB9="$(sb_new)" || { fail "could not build sandbox"; finish; }
IN9="${SB9}/fixture/statedir"
seed_tree "${IN9}" 3 "${WRONG_GID}"
printf '%s\tdownloads\tfalse\tfalse\ttrue\n' "${IN9}" | sb_scope "${SB9}"

_C13_EXT="$(mktemp -d "${RUN_ROOT}/extstate.XXXXXXXX")"
_C13_OUT="$(
    cd "${SB9}" && OWNERSHIP_STATE_DIR="${_C13_EXT}" \
        bash "${SB9}/scripts/ownership_repair.sh" --scope "${SB9}/config/owned_paths.yaml" 2>&1
)"
_C13_RC=$?
_C13_FP="$(sb_fingerprint "${SB9}")"

if [[ "${_C13_RC}" -ne 0 ]]; then
    fail "state-dir override: the run exited ${_C13_RC} with OWNERSHIP_STATE_DIR set"
    printf '%s\n' "${_C13_OUT}" | sed 's/^/        /' | head -6
else
    if [[ -n "${_C13_FP}" ]] && grep -rqF -- "${_C13_FP}" "${_C13_EXT}" 2>/dev/null; then
        pass "state-dir override: the marker landed in OWNERSHIP_STATE_DIR"
    else
        fail "state-dir override: OWNERSHIP_STATE_DIR was ignored — no artifact there carries the scope fingerprint"
    fi
    if [[ ! -e "${SB9}/logs" ]]; then
        pass "state-dir override: the DEFAULT state directory was not created when the override is set (an ad-hoc run does not touch the live trail)"
    else
        fail "state-dir override: the run also wrote ${SB9}/logs — the override did not redirect state, it duplicated it"
    fi
fi

# The default must remain byte-for-byte the documented live path.
SB9B="$(sb_new)" || { fail "could not build sandbox"; finish; }
IN9B="${SB9B}/fixture/defaultstate"
seed_tree "${IN9B}" 3 "${WRONG_GID}"
printf '%s\tdownloads\tfalse\tfalse\ttrue\n' "${IN9B}" | sb_scope "${SB9B}"
run_repair "${SB9B}"
if [[ -f "${SB9B}/logs/ownership/repair-marker.json" ]]; then
    pass "state-dir default: unchanged — marker at logs/ownership/repair-marker.json (the live path the journal and docs already name)"
else
    fail "state-dir default: logs/ownership/repair-marker.json absent — the default state location MOVED, which breaks the live path"
fi

# ===========================================================================
# CASE 14 — a repo-relative declared path resolves against the PROJECT ROOT,
# not the caller's cwd (data-model E1: "declared paths may be repo-relative").
#
# MEASURED 2026-08-21 against the pre-fix script: with a relative entry, a run
# started from a different working directory reported
#   "FAILED fixture/... — declared path does not exist and is not optional"
# and exited 1, on a path that plainly exists. That is the §11.4.201(1)
# false-positive refusal — the repair refusing on a condition that is absent.
#
# It is not academic: the SHIPPED scope declares `config`, `config/boba.db`,
# `.env`, `tmp` and `download-proxy` RELATIVELY, so every one of them behaves
# this way from any cwd but the project root. The sibling consumer
# scripts/ownership_precondition.sh already absolutises via its `absolutise()`
# helper, so the two consumers of ONE scope file disagreed about what a
# relative entry means.
# ===========================================================================
echo
echo "Case 14: a repo-relative declared path resolves against the project root, from any cwd"
SB10="$(sb_new)" || { fail "could not build sandbox"; finish; }
IN10="${SB10}/fixture/relscope"
seed_tree "${IN10}" 3 "${WRONG_GID}"
# The entry is deliberately RELATIVE — the shipped shape.
printf 'fixture/relscope\tdownloads\tfalse\tfalse\ttrue\n' | sb_scope "${SB10}"
_C14_WRONG_BEFORE="$(wrong_owned_count "${IN10}")"

# Run from a cwd that is NOT the project root. `/` is chosen because it is
# guaranteed to exist and guaranteed not to contain `fixture/relscope`.
_C14_OUT="$(
    cd / && bash "${SB10}/scripts/ownership_repair.sh" \
        --scope "${SB10}/config/owned_paths.yaml" 2>&1
)"
_C14_RC=$?

if [[ "${_C14_WRONG_BEFORE}" -eq 0 ]]; then
    fail "relative scope: fixture seeded 0 wrongly-owned items — the fixture is blind"
elif [[ "${_C14_RC}" -ne 0 ]]; then
    fail "relative scope: exit ${_C14_RC} from a foreign cwd — a relative declared path was read as absent (§11.4.201(1) false-positive refusal)"
    printf '%s\n' "${_C14_OUT}" | sed 's/^/        /' | head -6
elif [[ "$(wrong_owned_count "${IN10}")" -ne 0 ]]; then
    fail "relative scope: exit 0 but the tree was NOT repaired — the run resolved the relative path to somewhere else and reported success about nothing"
else
    pass "relative scope: a repo-relative entry was resolved against the project root and repaired from a foreign cwd"
fi

# ===========================================================================
# CASE 15 — the SHIPPED `.env` entry shape: a mode-600 credential file declared
# preserve_mode/optional/non-recursive keeps mode 600 exactly.
#
# HONESTY NOTE (§11.4.6): this case was GREEN the moment it was written. The
# code path it exercises is the same one Case 2 already proves, so it captured
# no RED and no defect is claimed for it. It exists as a shipped-shape pin: the
# `.env` entry added to config/owned_paths.yaml is the FIRST preserve_mode entry
# that is not config/boba.db, and .env is the file start.sh chmods to 0600 and
# the file boba-jackett rewrites (bootstrap.EnsureMasterKey) through a
# tmp+rename that REPLACES the inode. A future change that widened the
# mode-restore step would silently widen the file holding BOBA_MASTER_KEY.
#
# §11.4.10: the fixture contains a variable NAME and a placeholder only. No
# credential value is created, read, printed or logged anywhere in this suite.
# ===========================================================================
echo
echo "Case 15: shipped .env entry shape — preserve_mode keeps a 600 credential file at 600"
SB11="$(sb_new)" || { fail "could not build sandbox"; finish; }
_C15_ENV="${SB11}/dotenv_fixture"
printf 'PLACEHOLDER_NAME_ONLY=not-a-credential\n' > "${_C15_ENV}"
chmod 600 "${_C15_ENV}"
chgrp "${WRONG_GID}" "${_C15_ENV}"
printf 'dotenv_fixture\tcredential-store\ttrue\ttrue\tfalse\n' | sb_scope "${SB11}"

_C15_MODE_BEFORE="$(stat -c '%a' "${_C15_ENV}")"
_C15_GID_BEFORE="$(stat -c '%g' "${_C15_ENV}")"
if [[ "${_C15_MODE_BEFORE}" != "600" || "${_C15_GID_BEFORE}" == "${OP_GID}" ]]; then
    fail "dotenv shape: fixture is mode ${_C15_MODE_BEFORE} gid ${_C15_GID_BEFORE} — a widening or a repair would be invisible"
else
    run_repair "${SB11}"
    _C15_MODE_AFTER="$(stat -c '%a' "${_C15_ENV}" 2>/dev/null)"
    _C15_GID_AFTER="$(stat -c '%g' "${_C15_ENV}" 2>/dev/null)"
    if [[ "${_C15_MODE_AFTER}" == "600" ]]; then
        pass "dotenv shape: credential file still mode 600 after the repair (never widened, FR-015)"
    else
        fail "dotenv shape: credential file went 600 -> ${_C15_MODE_AFTER} — the repair WIDENED the file that holds BOBA_MASTER_KEY"
    fi
    if [[ "${_C15_GID_AFTER}" == "${OP_GID}" ]]; then
        pass "dotenv shape: credential file ownership WAS repaired (preserve_mode guards bits, not ownership)"
    else
        fail "dotenv shape: credential file still gid ${_C15_GID_AFTER} — preserve_mode must not stop the ownership repair itself"
    fi
fi


finish
