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
# THE FIXTURE IDENTITY, MEASURED — WHY THESE CASES USE A REAL FOREIGN **uid**
# ============================================================================
# The observed production defect is a **uid** mismatch: the download tree's new
# files land at uid 100999 (the rootless-podman subuid mapping) while the
# operator is uid 1000, so the operator cannot rename, move or delete their own
# downloads and cannot read config/boba.db.
#
# THIS BLOCK PREVIOUSLY ASSERTED THAT SUCH A FIXTURE WAS IMPOSSIBLE HERE. It
# claimed "a real host-uid mismatch is NOT constructible in an unprivileged
# hermetic sandbox", citing three probes (2026-08-21): plain `chown` -> EPERM,
# `unshare -Ur` + chown -> EINVAL, and `unshare --map-users` over the real
# subuid range -> EPERM. Those three measurements were correct. The CONCLUSION
# drawn from them was not, because the list omitted the one command that works
# — and it is the very command `docs/guides/file-ownership.md` documents as the
# manual repair for this defect:
#
#   $ podman unshare chown 1:1 f     # then, read back from the host:
#   $ stat -c '%u:%g' f
#   100000:100000                     # measured 2026-08-27, unprivileged
#
# `podman|docker unshare` re-enters the rootless user namespace in which the
# host operator IS uid 0. A `chown 1:1` performed there lands on the host as
# the FIRST SUBORDINATE UID — a genuine not-operator-owned item, built with no
# sudo, no loopback, no mount, on an ordinary filesystem. The symmetric claim
# ("an unprivileged process could not repair such an item back either") was
# false for the same reason: `unshare chown 0:0` restores it, which is exactly
# what ownership_repair.sh's own fallback does.
#
# So these cases now seed the REAL defect rather than a stand-in for it. Under
# §11.4.115(G) that is an upgrade from a CONSTRUCTED precondition to an
# OBSERVED one: the earlier gid fixture was a proxy chosen because uid was
# believed impossible, and a proxy mints at most defensive hardening.
#
# IT ALSO CLOSES A COVERAGE HOLE THE PROXY CONCEALED. A gid-only mismatch is
# repairable by a PLAIN chown (the operator is a member of the group), so the
# proxy exercised only `chown_paths()` and never reached
# `unshare_chown_paths()` — the namespace fallback that is the ONLY code path
# capable of repairing the production defect. A real foreign uid makes the
# plain chown fail with EPERM (measured) and forces that fallback, so the
# production repair path is now under test for the first time.
#
# HONEST NARROWING (§11.4.6). Only FILES and SYMLINKS are given the foreign
# uid; the DIRECTORIES holding them stay operator-owned. In production the
# directories are foreign-owned too, but seeding them that way would make the
# fixture unbuildable by its own harness — Cases 8/9/18 create symlinks INSIDE
# a seeded tree after seeding it, which an operator cannot do in a directory
# they no longer have write access to. The foreign-owned-DIRECTORY half is
# declared as a gap below rather than faked.
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
    if [[ -n "${RUN_ROOT:-}" && "${RUN_ROOT}" == *boba_ownership_repair.* ]]; then
        rm -rf "${RUN_ROOT}" 2>/dev/null || true
        # A deliberately foreign-owned DIRECTORY (seed_wrong -D) cannot be
        # emptied by the operator, so a plain rm leaves it behind. Reap it with
        # the same mechanism that created it, then re-try the plain rm.
        if [[ -d "${RUN_ROOT}" && -n "${NS_RUNTIME:-}" ]]; then
            timeout 120 "${NS_RUNTIME}" unshare rm -rf "${RUN_ROOT}" >/dev/null 2>&1 || true
            rm -rf "${RUN_ROOT}" 2>/dev/null || true
        fi
    fi
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
echo " 16 empty scope     : a scope yielding ZERO locations is 'could not run', not 'complete'"
echo " 17 declared-path fence: a scope may not name /, a system tree, or a .. escape"
echo " 18 hardlink claim   : the out-of-scope hardlink reach is measured and documented"
echo " 19 chown reason     : a failed chown reports WHY it failed"
echo " 20 mode-restore     : a failed FR-015 mode restore is reported, not swallowed"
echo " 21 fingerprint prose: the comment matches what the fingerprint is computed from"
echo " 22 declared-root    : a failure on the declared root itself is named as such"
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

# A user namespace is what makes a REAL not-operator-owned fixture possible
# unprivileged (see THE FIXTURE IDENTITY above). PROBED, never assumed — the
# presence of a runtime binary does not prove its `unshare` can seed here.
NS_RUNTIME=""
WRONG_UID=""
_probe_dir="${RUN_ROOT}/uidprobe"; mkdir -p "${_probe_dir}"; : > "${_probe_dir}/f"
for _rt in podman docker; do
    command -v "${_rt}" >/dev/null 2>&1 || continue
    timeout 60 "${_rt}" unshare chown 1:1 "${_probe_dir}/f" >/dev/null 2>&1 || continue
    _got="$(stat -c '%u' "${_probe_dir}/f" 2>/dev/null || true)"
    if [[ -n "${_got}" && "${_got}" != "${OP_UID}" ]]; then
        NS_RUNTIME="${_rt}"; WRONG_UID="${_got}"; break
    fi
done
rm -rf "${_probe_dir}" 2>/dev/null || true
if [[ -z "${NS_RUNTIME}" ]]; then
    skip "no container runtime whose \`unshare\` can seed a foreign uid — a REAL not-operator-owned fixture cannot be built here (topology_unsupported; see the DECLARED GAPS note)"
    finish
fi
echo "  fixture identity: operator ${OP_UID}:${OP_GID}; wrong-owner fixtures seeded as uid ${WRONG_UID} via ${NS_RUNTIME} unshare"
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

# seed_wrong [-h|-R] <path…> — give paths a REAL foreign uid, via the same user
# namespace the production defect and ownership_repair.sh's own fallback use.
#
#   (default)  the named paths themselves; -h is implied so a symlink is
#              re-owned rather than its target
#   -D         the named DIRECTORY itself. Used only where a foreign-owned
#              directory is the subject under test (Case 22's declared root,
#              which stands in for an unowned mount point). Such a directory
#              cannot be emptied by the operator, so cleanup_all reaps it
#              through the namespace.
#   -R         every FILE and SYMLINK under the named directory. The
#              DIRECTORIES stay operator-owned — see the HONEST NARROWING note
#              in the header block for why, and the DECLARED GAPS note for the
#              half that therefore stays uncovered.
#
# One namespace entry per call (never one per file): `find … -exec chown -h {} +`
# runs INSIDE the namespace, so seeding a 3000-item tree costs one spawn.
seed_wrong() {
    local mode="paths"
    case "${1:-}" in
        -h) shift ;;
        -R) mode="recursive"; shift ;;
        -D) mode="dir"; shift ;;
    esac
    # The -h/link-seeding vehicle is lchown(2), NOT `chown -h`. MEASURED on this
    # host 2026-09-02 (§11.4.201): uutils coreutils 0.8.0 dereferences `-h` for a
    # symlink-to-DIRECTORY — it chowns the TARGET and leaves the link at its
    # original uid, exit 0. That silently under-seeded this fixture (2 of 3 links
    # foreign), which Case 8's own guard then correctly refused to score, so the
    # symlink fence was never actually exercised. Seeding via os.lchown makes all
    # three links genuinely foreign-owned so the fence assertions really run.
    local _seed_py='
import os, sys
for p in (x for x in sys.stdin.buffer.read().split(b"\0") if x):
    os.lchown(p, 1, 1)
'
    if [[ "${mode}" == "dir" ]]; then
        timeout 300 "${NS_RUNTIME}" unshare chown 1:1 -- "$@" >/dev/null 2>&1
    elif [[ "${mode}" == "recursive" ]]; then
        timeout 300 "${NS_RUNTIME}" unshare sh -c \
            'find "$1" \( -type f -o -type l \) -print0 | python3 -c "$2"' \
            _ "$1" "${_seed_py}" >/dev/null 2>&1
    else
        printf '%s\0' "$@" \
            | timeout 300 "${NS_RUNTIME}" unshare python3 -c "${_seed_py}" >/dev/null 2>&1
    fi
}

# seed_tree <dir> <count> <wrong|correct> — a real tree of real files, either
# left operator-owned or given a REAL foreign uid.
seed_tree() {
    local dir="$1" count="$2" want="$3" i
    mkdir -p "${dir}/sub/deeper"
    for (( i = 0; i < count; i++ )); do
        printf 'item %d\n' "${i}" > "${dir}/item_$(printf '%05d' "${i}").bin"
    done
    printf 'nested\n' > "${dir}/sub/nested.bin"
    printf 'deep\n'   > "${dir}/sub/deeper/deep.bin"
    if [[ "${want}" == "wrong" ]]; then
        seed_wrong -R "${dir}"
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

# wrong_owned_count <dir> — items NOT owned by the operator.
#
# uid ALONE, matching the feature's single definition of the property
# (data-model E4 models `probe_uid`/`expected_uid` with no gid field; see the
# BOB-207 note in scripts/ownership_repair.sh). This predicate is deliberately
# the SAME one the repair's walk uses: if the two drift apart again, the suite
# stops measuring what the tool does.
wrong_owned_count() {
    find "$1" ! -uid "${OP_UID}" -printf '.' 2>/dev/null | wc -c
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

seed_tree "${IN1}" 12 wrong
seed_tree "${OUT1}" 6 wrong
mkdir -p "${IN1}/creds"
printf 'pretend-encrypted-credential-store\n' > "${CRED1}"
chmod 600 "${CRED1}"
seed_wrong "${CRED1}"   # AFTER chmod: a foreign-owned file cannot be chmod'd

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
    # Says uid, because that is what wrong_owned_count measures. The gid the
    # chown also writes is asserted separately (the %u:%g pair checks in the
    # symlink-fence cases), so this is a wording bound, not a coverage gap.
    pass "golden-bad: all ${IN1_WRONG_BEFORE} not-operator-owned items are now uid ${OP_UID}"
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
    _cred_uid="$(stat -c '%u' "${CRED1}")"
    if [[ "${_cred_mode}" == "600" ]]; then
        pass "preserve_mode: credential store kept mode 600 exactly"
    else
        fail "preserve_mode: credential store mode is ${_cred_mode}, was 600 — FR-015 forbids relaxing access while changing ownership"
    fi
    if [[ "${_cred_uid}" == "${OP_UID}" ]]; then
        pass "preserve_mode: credential store ownership WAS repaired (preserve_mode guards bits, not ownership)"
    else
        fail "preserve_mode: credential store still uid ${_cred_uid} — preserve_mode must not stop the ownership repair itself"
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
seed_tree "${IN2}" 10 correct
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
    seed_tree "${IN3}" "${_c5_size}" wrong
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
    seed_tree "${NEW1}" 8 wrong
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
seed_tree "${IN4}" 6 wrong
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

seed_tree "${IN5}" 6 wrong
seed_tree "${OUT5}" 4 wrong
# A second observable dimension: mode. Seeded at 600 so a mode-following
# restore step would show up in the manifest exactly as an ownership reach does.
printf 'out-of-scope-secret\n' > "${OUT5}/secret.bin"
chmod 600 "${OUT5}/secret.bin"
seed_wrong "${OUT5}/secret.bin"   # AFTER chmod, same reason

# Links are created AFTER seed_tree so its recursive seeding cannot touch them,
# and are re-owned with `seed_wrong -h` so the LINK — never its target — is
# what the walk will find not-operator-owned.
ln -s "${OUT5}/secret.bin"    "${LNK_FILE}"
ln -s "${OUT5}/sub"           "${LNK_DIR}"
ln -s "${DANGLE_TARGET}"      "${LNK_DANGLE}"
seed_wrong -h "${LNK_FILE}" "${LNK_DIR}" "${LNK_DANGLE}"

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
echo "  * CLOSED 2026-08-27 — a real host-UID mismatch IS now seeded here, via"
echo "    \`${NS_RUNTIME} unshare chown\`, so every case above runs against the"
echo "    real defect and forces the repair's namespace fallback. The earlier"
echo "    claim that this was impossible omitted that command; see THE FIXTURE"
echo "    IDENTITY block at the top of this file."
echo "  * Foreign-owned DIRECTORIES are still not seeded: only files and"
echo "    symlinks carry the foreign uid. Seeding the directories too would"
echo "    leave the harness unable to create the symlinks Cases 8/9/18 add"
echo "    after seeding. NOTE: the container-write suite covers the CREATION"
echo "    side of that shape (a container writing a directory, FR-002) — NOT"
echo "    the repair-side walk over a tree whose interior directories already"
echo "    carry a foreign uid. Case 22's seed_wrong -D covers only a foreign"
echo "    declared ROOT, and only on the failure path. Repair-side directory"
echo "    coverage is tracked as an integration-layer item."
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

seed_tree "${IN6}" 3 wrong
mkdir -p "${OUT6}"
printf 'encrypted-credential-bytes\n' > "${OUT6}/credstore.bin"
chmod 600 "${OUT6}/credstore.bin"

# The LINK is wrongly-owned so the walk finds it; its TARGET is correctly owned
# and mode 600, so any change to the target is unambiguously a reach rather than
# a repair the tool was asked to perform.
ln -s "${OUT6}/credstore.bin" "${LNK6}"
seed_wrong -h "${LNK6}"

printf '%s\tproject-config\tfalse\ttrue\ttrue\n' "${IN6}" | sb_scope "${SB6}"

OUT6_MODE_BEFORE="$(stat -c '%a' "${OUT6}/credstore.bin")"
OUT6_DIGEST_BEFORE="$(content_digest "${OUT6}")"
IN6_WRONG_BEFORE="$(wrong_owned_count "${IN6}")"

if [[ ! -L "${LNK6}" ]]; then
    fail "preserve_mode symlink fence: fixture link is not a symlink — nothing was tested"
elif [[ "$(stat -c '%u' "${LNK6}")" == "${OP_UID}" ]]; then
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
seed_tree "${IN7}" 3 wrong
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
seed_tree "${IN8A}" 3 wrong
printf '%s\tdownloads\tfalse\tfalse\ttrue\n' "${IN8A}" | sb_scope "${SB8}"
run_repair "${SB8}"
_C12_A="${IN8A}/item_00000.bin"

if [[ "${RUN_RC}" -ne 0 ]]; then
    fail "record rotation: the first run exited ${RUN_RC} — no first record to supersede"
elif [[ -z "$(artifact_mentions "${SB8}" "${_C12_A}")" ]]; then
    fail "record rotation: the first run wrote no record naming ${_C12_A} — nothing to supersede"
else
    # Second run, armed by a genuine scope change (the realistic path).
    seed_tree "${IN8B}" 3 wrong
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
seed_tree "${IN9}" 3 wrong
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
seed_tree "${IN9B}" 3 wrong
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
seed_tree "${IN10}" 3 wrong
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
seed_wrong "${_C15_ENV}"
printf 'dotenv_fixture\tcredential-store\ttrue\ttrue\tfalse\n' | sb_scope "${SB11}"

_C15_MODE_BEFORE="$(stat -c '%a' "${_C15_ENV}")"
_C15_UID_BEFORE="$(stat -c '%u' "${_C15_ENV}")"
if [[ "${_C15_MODE_BEFORE}" != "600" || "${_C15_UID_BEFORE}" == "${OP_UID}" ]]; then
    fail "dotenv shape: fixture is mode ${_C15_MODE_BEFORE} uid ${_C15_UID_BEFORE} — a widening or a repair would be invisible"
else
    run_repair "${SB11}"
    _C15_MODE_AFTER="$(stat -c '%a' "${_C15_ENV}" 2>/dev/null)"
    _C15_UID_AFTER="$(stat -c '%u' "${_C15_ENV}" 2>/dev/null)"
    if [[ "${_C15_MODE_AFTER}" == "600" ]]; then
        pass "dotenv shape: credential file still mode 600 after the repair (never widened, FR-015)"
    else
        fail "dotenv shape: credential file went 600 -> ${_C15_MODE_AFTER} — the repair WIDENED the file that holds BOBA_MASTER_KEY"
    fi
    if [[ "${_C15_UID_AFTER}" == "${OP_UID}" ]]; then
        pass "dotenv shape: credential file ownership WAS repaired (preserve_mode guards bits, not ownership)"
    else
        fail "dotenv shape: credential file still uid ${_C15_UID_AFTER} — preserve_mode must not stop the ownership repair itself"
    fi
fi



# ===========================================================================
# T028 REVIEW REMEDIATION — Cases 16-22.
#
# The T028 independent review returned NO-GO with 2 IMPORTANT, 3 MINOR and
# 2 NIT findings, and MEASURED that this suite had ZERO coverage for the two
# IMPORTANT ones:
#
#     grep -niE 'empty scope|no locations|paths: \[\]|absolute|traversal' \
#          tests/unit/test_ownership_repair.sh          ->  0
#
# A zero is not a finding until the instrument is proven able to see through
# the SAME path (§11.4.201(7)(b)). Re-measured 2026-08-25 with a same-shape
# needle (identical tool, identical -E alternation, identical file):
#
#     grep -ncE 'scope|marker|fixture|record|symlink' <this file>   ->  257
#     grep -ncE 'zzzz_nonexistent_token_qqq'          <this file>   ->    0
#
# The instrument sees, the negative control is silent, so the 0 was real: the
# gaps below were genuinely uncovered, and every case here captured a RED
# against the pre-fix artifact before the fix existed.
#
# HELPERS USED ONLY BY THESE CASES
# ---------------------------------------------------------------------------
# Two findings (MINOR-2, MINOR-3) are about what the run REPORTS when `chown`
# or `chmod` FAILS. This suite's own header measured (2026-08-21, three ways)
# that a real foreign-uid item is NOT constructible unprivileged, and a real
# unprivileged chown/chmod failure on an item the walk batched is subject to
# the same wall: every fixture item is created BY this account, so this account
# owns it, so chown-to-self and chmod-on-own both succeed.
#
# The failure is therefore injected by PATH, not by a production test hook:
# a directory holding a `chown`/`chmod` shim is prepended to PATH for the run.
# This is the environment the run executes in, not a branch inside the artifact
# (§11.4.27 forbids test scaffolding in production code, and there is none
# here — the artifact is byte-identical to the shipped one, sha256-verified by
# sb_new). The REAL call site, the REAL failure handling and the REAL operator
# output are what get exercised.
#
# §11.4.115(G) PRECONDITION PROVENANCE: `constructed`, and stated as such.
# The constructed part is the CAUSE of the failure (an injected non-zero exit),
# not the condition under test — the finding is that a non-zero chown/chmod is
# reported without its reason (MINOR-2) or not reported at all (MINOR-3), and
# that condition is reproduced exactly. No defect-closing claim is made about
# any particular errno reaching the operator on a real filesystem.
#
# §11.4.263: the shims exec nothing and signal nothing; they print and exit.
# ---------------------------------------------------------------------------

# shim_dir <sb> <tool> <body> — build a PATH shim directory containing ONE
# executable named <tool>. Echoes the directory. Lives inside the sandbox, so
# the EXIT trap reaps it (§11.4.14).
shim_dir() {
    local sb="$1" tool="$2" body="$3" d
    d="$(mktemp -d "${sb}/shim.XXXXXX")"
    printf '%s\n' "${body}" > "${d}/${tool}"
    chmod +x "${d}/${tool}"
    printf '%s\n' "${d}"
}

# run_repair_with_path <sb> <shim-dir> [args…] — run_repair with the shim dir
# prepended to PATH. `nice`/`ionice` are deliberately NOT shimmed, so the
# artifact's own host-safety re-exec still happens exactly as in production.
run_repair_with_path() {
    local sb="$1" shim="$2"; shift 2
    RUN_OUT="$(
        cd "${sb}" && PATH="${shim}:${PATH}" \
            OWNED_PATHS_FILE="${sb}/config/owned_paths.yaml" \
            bash "${sb}/scripts/ownership_repair.sh" \
                --scope "${sb}/config/owned_paths.yaml" "$@" 2>&1
    )"
    RUN_RC=$?
    return 0
}

# sb_raw_scope <sb> <yaml-text> — write a scope file VERBATIM. sb_scope() can
# only emit well-formed entry rows, and three of the four shapes below are
# precisely the malformed/empty ones it cannot express.
sb_raw_scope() { printf '%s\n' "$2" > "$1/config/owned_paths.yaml"; }

# fence_verdict <sb> <path> <was_relative> <project_root> — call the fence
# predicate DIRECTLY. Used for shapes that cannot be exercised end to end
# because the path must not be created (e.g. `/mnt/DATA`, `/etc/passwd`).
# Echoes "accept" or "refuse"; "missing" when the predicate does not exist.
fence_verdict() {
    local sb="$1" p="$2" rel="$3" root="$4"
    (
        # shellcheck disable=SC1090
        source "${sb}/scripts/lib/ownership.sh"
        if ! declare -F ownership_path_fence >/dev/null 2>&1; then
            printf 'missing\n'; exit 0
        fi
        if ownership_path_fence "${p}" "${rel}" "${root}" >/dev/null 2>&1; then
            printf 'accept\n'
        else
            printf 'refuse\n'
        fi
    )
}

# ===========================================================================
# CASE 16 — AN EMPTY SCOPE IS NOT A COMPLETED REPAIR (IMPORTANT-1, §11.4.252).
#
# The artifact guards an UNREADABLE scope and an UNPARSEABLE scope (exit 2) and
# its own header at scripts/ownership_repair.sh:351-353 declares why:
#
#   "Reporting an unreadable scope as an empty scope would be the
#    §11.4.201(6) false-null: a blind instrument and a clean tree return the
#    same quiet zero."
#
# It defended only half of what it claimed. A scope that is valid YAML yielding
# ZERO entries walked nothing, asserted nothing, and — measured against the
# pre-fix artifact, 2026-08-25 — exited 0 and WROTE A COMPLETION MARKER
# carrying fingerprint e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855,
# which is sha256("") — the fingerprint of nothing. `start.sh` then reads that
# marker as "already repaired" and skips the walk on every subsequent start.
#
# Three shapes, all three measured green-and-complete before the fix:
#   (a) `paths: []`                — an explicitly empty list
#   (b) the top-level key mistyped `path:` instead of `paths:` — valid YAML,
#       parses cleanly, yields nothing
#   (c) every entry's ${VAR} expanding empty — the shipped scope's FIRST entry
#       is `${QBITTORRENT_DATA_DIR:-/mnt/DATA}`, so this is a live shape
#
# The sibling scripts/ownership_precondition.sh:1011-1013 already refuses all
# three (exit 2). This case pins the repair to the SAME decision — §11.4.251:
# one predicate, both callers, never a second dialect.
#
# WHY exit 2 AND NOT exit 1: exit 1 means "an item could not be repaired" and
# invites a retry. Nothing was wrong with any item; the SCOPE is unusable, and
# the contract already reserves 2 for "could not run" (Case 7b pins that
# boundary from the other side).
# ===========================================================================
echo
echo "Case 16: a scope that yields ZERO locations is 'could not run', not 'complete' (IMPORTANT-1)"

# Non-vacuity control FIRST (§11.4.201(7)(b)): the same sandbox shape with a
# REAL entry must exit 0 and DO write a marker. Without this, "exit 2 / no
# marker" below could be produced by a sandbox that never ran at all.
SB16C="$(sb_new)" || { fail "could not build sandbox"; finish; }
IN16C="${SB16C}/fixture/nonempty"
seed_tree "${IN16C}" 3 wrong
printf '%s\tdownloads\tfalse\tfalse\ttrue\n' "${IN16C}" | sb_scope "${SB16C}"
run_repair "${SB16C}"
if [[ "${RUN_RC}" -eq 0 ]] && marker_present "${SB16C}"; then
    pass "empty scope [control needle]: a NON-empty scope in the same sandbox shape exits 0 and writes a marker — the assertions below are not vacuous"
    _C16_NEEDLE=1
else
    _C16_NEEDLE=0
    fail "empty scope [control needle]: a non-empty scope gave rc=${RUN_RC} / marker=$(marker_present "${SB16C}" && echo present || echo absent) — the instrument is blind, so no 'refused' verdict below can be trusted"
fi

# RECONCILED 2026-08-26 (§11.4.120), NOT weakened. Shape (c) below — every
# ${VAR} expanding empty — is now refused one layer EARLIER, by
# ownership_scope_entries itself (R2-M1, Case 23), so it no longer reaches this
# script's "contains no locations" branch and no longer prints that phrase.
# Shapes (a) and (b) still do. Collapsing all three onto one generic regex
# would have been the tautology §11.4.120 forbids, so each shape now asserts
# the evidence ITS OWN cause produces: strictly more specific than before, and
# a shape that started printing another shape's message would now FAIL.
# The exit-2 and no-marker assertions are unchanged for all three.
_c16_probe() {
    local label="$1" yaml="$2" evidence="$3" sb
    sb="$(sb_new)" || { fail "empty scope [${label}]: could not build sandbox"; return 0; }
    mkdir -p "${sb}/fixture/present"
    : > "${sb}/fixture/present/f.bin"
    sb_raw_scope "${sb}" "${yaml}"
    run_repair "${sb}"

    if [[ "${RUN_RC}" -eq 2 ]]; then
        pass "empty scope [${label}]: exit 2 — the run reported 'could not run' rather than 'complete'"
    elif [[ "${RUN_RC}" -eq 0 ]]; then
        fail "empty scope [${label}]: exit 0 — a run that walked ZERO locations reported SUCCESS (§11.4.252 fail-open; §11.4.201(6) false-null)"
    else
        fail "empty scope [${label}]: exit ${RUN_RC} — the contract reserves 2 for 'could not run'"
    fi

    if [[ "${_C16_NEEDLE}" -ne 1 ]]; then
        fail "empty scope [${label}]: marker verdict WITHHELD — the control needle above never fired, so 'no marker' cannot be distinguished from 'detector blind' (§11.4.201(7)(b))"
    elif marker_present "${sb}"; then
        fail "empty scope [${label}]: a COMPLETION MARKER was written for a scope of zero locations — start.sh will skip the repair from now on"
    else
        pass "empty scope [${label}]: no completion marker written — the next start still repairs"
    fi

    if printf '%s' "${RUN_OUT}" | grep -qiE "${evidence}"; then
        pass "empty scope [${label}]: the operator is told why this scope yields nothing"
    else
        fail "empty scope [${label}]: output never matched /${evidence}/ — the refusal must print its resolved evidence (§11.4.201(5))"
        printf '%s\n' "${RUN_OUT}" | grep -iE 'scope|entry|location' | head -4 | sed 's/^/        /'
    fi
}

_c16_probe "paths: []" 'schema_version: 1
paths: []' 'no locations|zero locations'

_c16_probe "top-level key mistyped 'path:'" 'schema_version: 1
path:
  - path: "fixture/present"
    kind: downloads
    optional: false
    preserve_mode: false
    recursive: true' 'no locations|zero locations'

_c16_probe 'every ${VAR} expands empty' 'schema_version: 1
paths:
  - path: "${BOBA_NO_SUCH_VARIABLE_QQQ}"
    kind: downloads
    optional: false
    preserve_mode: false
    recursive: true' 'resolved to no usable location|empty path'

# ===========================================================================
# CASE 17 — THE DECLARED PATH ITSELF IS FENCED (IMPORTANT-2, the dangerous one).
#
# scripts/ownership_repair.sh:741-742 claimed:
#   "The filter IS the scope fence: only items under a declared path are ever
#    named, so an out-of-scope item cannot be reached even by accident."
# That is circular. It fences to the DECLARED path; nothing constrained what a
# declared path may BE. `absolutise()` prepended PROJECT_ROOT to a relative
# path and otherwise passed text through — no normalisation, no bound.
#
# MEASURED against the pre-fix artifact (2026-08-25, all under --dry-run):
#   * an absolute path outside the project      -> 2 items named for chown
#   * "inside/../../mirror/outside_tree"        -> named; `..` never resolved
#   * the shipped entry `${QBITTORRENT_DATA_DIR:-/mnt/DATA}` copied VERBATIM
#     with the env var repointed                -> walked an arbitrary tree
#   * absolutise("/") == "/"  (the `|| p="/"` branch at :381-384)
#     -> a recursive walk of the entire filesystem
#
# `.env` is untracked and unreviewed, and carries QBITTORRENT_DATA_DIR, so an
# unreviewed file fully determined which tree got recursively chowned.
#
# THE FENCE THIS CASE PINS (and why it is shaped this way)
# ---------------------------------------------------------------------------
# A naive "must be under PROJECT_ROOT" rule would BREAK the feature: the
# download root is INTENTIONALLY outside the project. The fence therefore
# splits on how the entry was written:
#
#   F0 normalise  — `.`/`..`/`//` collapsed LEXICALLY, no symlink resolution.
#                   Lexical because resolving symlinks would be a TOCTOU (the
#                   link is swappable between check and walk) and because
#                   find's default -P already refuses to descend a symlinked
#                   root, so nothing is gained by following one.
#   F1 relative   — a repo-relative entry DENOTES something in the repository,
#                   so after F0 it must still be inside PROJECT_ROOT. An entry
#                   that climbs out with `..` was written to escape, and the
#                   scope format does not license that.
#   F2 absolute   — at least 2 path components. MEASURED: the shipped default
#                   `/mnt/DATA` has exactly 2, so 2 is the floor the shipped
#                   configuration forces. Below it lies `/` itself and the bare
#                   top-level directories.
#   F3 absolute   — never a system tree (`/etc`, `/usr`, `/proc`, …) nor
#                   anything under one. F2 alone does NOT catch these:
#                   `/usr/lib` has 2 components and passes the floor.
#
# `/run` is deliberately NOT a system tree here: MEASURED from this host's
# `.env`, the operator's real library is /run/media/milosvasic/DATA4TB/Downloads
# (5 components). A denylist that swallowed /run would be a §11.4.201(1)
# false-positive refusal of the live configuration.
#
# HONEST BOUNDARY (§11.4.6), stated rather than papered over: this fence bounds
# the SHAPE of a declared path. It does NOT and cannot decide that a
# well-shaped absolute path is the tree the operator meant — an absolute
# out-of-project path with enough depth is exactly what the download root is,
# so it must be accepted. What it removes is the class the review traced to a
# catastrophic outcome: filesystem roots, bare top-level directories, system
# trees, and `..` escapes.
# ===========================================================================
echo
echo "Case 17: the DECLARED path is itself fenced — a scope may not name /, a system tree, or a .. escape (IMPORTANT-2)"

# --- 17d FIRST: the golden-FALSE / false-positive guard (§11.4.201(1)). ------
# Every refusal below is worthless if the fence refuses everything. The two
# LEGITIMATE shapes must still work, end to end, and actually repair.
SB17OK="$(sb_new)" || { fail "could not build sandbox"; finish; }
IN17ABS="${SB17OK}/fixture/legit_abs"      # absolute, outside no-one's project
IN17REL="rel_legit"                         # repo-relative, inside PROJECT_ROOT
seed_tree "${IN17ABS}" 3 wrong
seed_tree "${SB17OK}/${IN17REL}" 3 wrong
printf '%s\tdownloads\tfalse\tfalse\ttrue\n%s\tdownloads\tfalse\tfalse\ttrue\n' \
    "${IN17ABS}" "${IN17REL}" | sb_scope "${SB17OK}"
_C17_WRONG_BEFORE=$(( $(wrong_owned_count "${IN17ABS}") + $(wrong_owned_count "${SB17OK}/${IN17REL}") ))
run_repair "${SB17OK}"
if [[ "${_C17_WRONG_BEFORE}" -eq 0 ]]; then
    fail "fence [legitimate shapes]: fixture seeded 0 wrongly-owned items — the case is blind"
    _C17_NEEDLE=0
elif [[ "${RUN_RC}" -ne 0 ]]; then
    _C17_NEEDLE=0
    fail "fence [legitimate shapes]: exit ${RUN_RC} — the fence REFUSED a legitimate scope (absolute out-of-project download root + repo-relative entry). That is the §11.4.201(1) false-positive refusal the fence must not be."
    printf '%s\n' "${RUN_OUT}" | sed 's/^/        /' | head -6
elif [[ "$(wrong_owned_count "${IN17ABS}")" -ne 0 || "$(wrong_owned_count "${SB17OK}/${IN17REL}")" -ne 0 ]]; then
    _C17_NEEDLE=0
    fail "fence [legitimate shapes]: exit 0 but the trees were NOT repaired"
else
    _C17_NEEDLE=1
    pass "fence [legitimate shapes]: an absolute out-of-project path AND a repo-relative path are both accepted and repaired (the fence is not a blanket refusal)"
fi

# _c17_refuse <label> <yaml> [env-assignments…] — the scope must be REFUSED
# with exit 2, and NOTHING may be named for chown.
#
# TWO SAFETY BELTS, and they are not decoration — this case ALREADY ran away
# once. MEASURED 2026-08-25: an earlier draft of 17a declared the shipped
# `${QBITTORRENT_DATA_DIR:-/mnt/DATA}` entry with QBITTORRENT_DATA_DIR=/ and the
# pre-fix artifact really did start
#     find / \( ! -uid 1000 -o ! -gid 1000 \) -printf '%U\t%G\t%m\t%p\0'
# — a walk of the entire filesystem, observed in `ps` and killed by pid. That is
# IMPORTANT-2 reproduced directly rather than traced in code, and it is why the
# probes below never point a possibly-unfenced walk at a tree that exists:
#
#   BELT 1  --dry-run: even unfenced, the RED reproduces the defect and never
#           performs it — nothing is mutated on any path, ever.
#   BELT 2  every dangerous shape names a NON-EXISTENT path of the dangerous
#           SHAPE. The fence is a property of the path, not of its existence,
#           so the shape is what must be refused; and an unfenced run hits the
#           artifact's "declared path does not exist" branch (exit 1) instead of
#           walking anything. The `/` and `/mnt` shapes — the ones that cannot
#           be made non-existent — are pinned by the direct predicate calls in
#           17e, which resolve a verdict without walking at all.
#   BELT 3  `timeout`: if a future change ever makes an unfenced walk reachable
#           here again, it is bounded to seconds instead of the operator's disk.
_c17_refuse() {
    local label="$1" yaml="$2"; shift 2
    local sb out rc
    sb="$(sb_new)" || { fail "fence [${label}]: could not build sandbox"; return 0; }
    sb_raw_scope "${sb}" "${yaml}"
    out="$(cd "${sb}" && timeout 25 env "$@" OWNED_PATHS_FILE="${sb}/config/owned_paths.yaml" \
        bash "${sb}/scripts/ownership_repair.sh" \
        --scope "${sb}/config/owned_paths.yaml" --dry-run 2>&1)"
    rc=$?
    if [[ "${rc}" -eq 124 ]]; then
        fail "fence [${label}]: the run did not refuse and was still walking after 25s — the declared path was ACCEPTED and the walk started (timeout belt fired)"
        return 0
    fi

    if [[ "${rc}" -eq 2 ]]; then
        pass "fence [${label}]: exit 2 — refused before anything was walked"
    else
        fail "fence [${label}]: exit ${rc} — the scope was ACCEPTED; a declared path of this shape must be refused (exit 2, 'could not run')"
    fi

    if printf '%s' "${out}" | grep -q 'would chown'; then
        fail "fence [${label}]: the run NAMED items for chown — the walk reached a tree this shape must never reach"
        printf '%s\n' "${out}" | grep 'would chown' | head -2 | sed 's/^/        /'
    else
        pass "fence [${label}]: no item was named for chown"
    fi

    if printf '%s' "${out}" | grep -q 'REFUSED'; then
        pass "fence [${label}]: the refusal names the offending entry (§11.4.201(5) resolved evidence)"
    else
        fail "fence [${label}]: no REFUSED line — a refusal must print what it refused and why"
    fi
}

# 17a — THE LIVE VECTOR. The entry is byte-for-byte the shipped
# config/owned_paths.yaml entry; only the environment moves — which is the whole
# finding, because `.env` is untracked, unreviewed, and carries that variable.
# The value is a bare top-level directory rather than `/` itself for the belt-2
# reason above; `/` is pinned by the predicate call in 17e.
_c17_refuse 'shipped entry, env repointed to a bare top-level dir' 'schema_version: 1
paths:
  - path: "${QBITTORRENT_DATA_DIR:-/mnt/DATA}"
    kind: downloads
    optional: false
    preserve_mode: false
    recursive: true' QBITTORRENT_DATA_DIR=/boba_fence_probe_qqq

# 17b — a repo-relative entry that climbs out of the project with `..`.
_c17_refuse 'relative entry escaping the project root with ..' 'schema_version: 1
paths:
  - path: "fixture/../../boba_fence_escape_probe_qqq"
    kind: downloads
    optional: false
    preserve_mode: false
    recursive: true'

# 17c — an absolute system tree. Note this one has TWO components, so the
# depth floor alone does not catch it; the system-tree rule is what does.
_c17_refuse 'absolute system tree (under /usr/lib)' 'schema_version: 1
paths:
  - path: "/usr/lib/boba_fence_probe_qqq"
    kind: downloads
    optional: false
    preserve_mode: false
    recursive: true'

# 17e — the fence PREDICATE, called directly, on shapes that must never be
# created on this host to be tested (§11.4.201(11): probe the artifact, and do
# not manufacture a system directory to do it).
_C17_ROOT="/srv/example/project"
_c17_pred() {
    local label="$1" p="$2" rel="$3" want="$4" got
    got="$(fence_verdict "${SB17OK}" "${p}" "${rel}" "${_C17_ROOT}")"
    if [[ "${got}" == "missing" ]]; then
        fail "fence predicate [${label}]: ownership_path_fence is not defined in scripts/lib/ownership.sh — the fence does not exist"
    elif [[ "${got}" == "${want}" ]]; then
        pass "fence predicate [${label}]: ${got} (expected ${want})"
    else
        fail "fence predicate [${label}]: ${got}, expected ${want}"
    fi
}
_c17_pred 'the shipped default /mnt/DATA'          "/mnt/DATA"                 0 accept
_c17_pred 'this host real root /run/media/.../DL'  "/run/media/u/DISK/Downloads" 0 accept
_c17_pred 'filesystem root /'                      "/"                         0 refuse
_c17_pred 'bare top-level /mnt'                    "/mnt"                      0 refuse
_c17_pred 'system tree /etc'                       "/etc"                      0 refuse
_c17_pred 'under a system tree /var/lib/x/y'       "/var/lib/x/y"              0 refuse
_c17_pred 'absolute .. escape /mnt/DATA/../..'     "/mnt/DATA/../.."           0 refuse
_c17_pred 'relative staying inside the root'       "${_C17_ROOT}/config"       1 accept
_c17_pred 'relative escaping the root'             "${_C17_ROOT}/../elsewhere" 1 refuse

# ===========================================================================
# CASE 18 — THE HARDLINK CLAIM MUST MATCH THE HARDLINK BEHAVIOUR (MINOR-1).
#
# scripts/ownership_repair.sh:136-140 asserted, of `chown -h`:
#   "FR-005 requires out-of-scope reach to be impossible by construction."
#
# MEASURED against the artifact (2026-08-25): a hardlink INSIDE the declared
# scope names an inode whose other link lives OUTSIDE every declared path.
# chown(2) acts on the INODE, so the out-of-scope file's ownership changed:
#   BEFORE 1000:10 links=2   ->   AFTER 1000:1000 links=2
#
# So the claim is false as written. It is bounded — the escape needs a writer
# inside the declared scope able to create the link, and both links must be on
# ONE filesystem — but a container running as root inside a declared bind mount
# is exactly such a writer.
#
# FENCING IT WAS CONSIDERED AND REJECTED, and the reason is recorded rather
# than left implicit: refusing every item with st_nlink > 1 would refuse the
# ordinary case, because hardlinking is how a torrent client and a media
# manager share one payload between the download tree and the library. A fence
# there would break the feature for its primary user to close a bounded escape.
#
# So the CLAIM is corrected instead — §11.4.6: an overclaiming comment is
# itself a finding. This case exists so the corrected claim is MACHINE-CHECKED
# rather than prose: it measures the real behaviour AND asserts the header
# documents that behaviour explicitly.
# ===========================================================================
echo
echo "Case 18: the hardlink escape is real, bounded, and the header says so (MINOR-1)"
SB18="$(sb_new)" || { fail "could not build sandbox"; finish; }
IN18="${SB18}/fixture/in_scope"
OUT18="${SB18}/fixture/out_of_scope"
mkdir -p "${IN18}" "${OUT18}"
printf 'payload\n' > "${OUT18}/outside_file.bin"
if ! ln "${OUT18}/outside_file.bin" "${IN18}/inside_link.bin" 2>/dev/null; then
    skip "hardlink escape: this filesystem refuses hardlinks — the behaviour cannot be measured here (topology_unsupported)"
else
    seed_wrong "${OUT18}/outside_file.bin"
    _C18_BEFORE="$(stat -c '%u:%g' "${OUT18}/outside_file.bin")"
    _C18_LINKS="$(stat -c '%h' "${OUT18}/outside_file.bin")"
    printf '%s\tdownloads\tfalse\tfalse\ttrue\n' "${IN18}" | sb_scope "${SB18}"

    if [[ "${_C18_LINKS}" -ne 2 || "${_C18_BEFORE}" == "${OP_UID}:${OP_GID}" ]]; then
        fail "hardlink escape: fixture is links=${_C18_LINKS} owner=${_C18_BEFORE} — a reach would be invisible"
    else
        run_repair "${SB18}"
        _C18_AFTER="$(stat -c '%u:%g' "${OUT18}/outside_file.bin")"

        # The measurement is reported as FACT either way; what is ASSERTED is
        # that the header's claim agrees with it.
        if [[ "${_C18_AFTER}" == "${OP_UID}:${OP_GID}" ]]; then
            _C18_REACHES=1
            echo "    measured: the out-of-scope hardlink target went ${_C18_BEFORE} -> ${_C18_AFTER} (the escape is REAL)"
        else
            _C18_REACHES=0
            echo "    measured: the out-of-scope hardlink target stayed ${_C18_AFTER} (no escape on this filesystem)"
        fi

        _C18_DOCUMENTED=0
        grep -qiE 'hard *link' "${SCRIPT}" && _C18_DOCUMENTED=1

        if [[ "${_C18_REACHES}" -eq 1 && "${_C18_DOCUMENTED}" -eq 1 ]]; then
            pass "hardlink escape: the escape is real AND the artifact documents it — the header no longer overclaims (§11.4.6)"
        elif [[ "${_C18_REACHES}" -eq 1 ]]; then
            fail "hardlink escape: chown reached an out-of-scope inode through a hardlink, and the artifact says out-of-scope reach is 'impossible by construction' — the claim is false as written (§11.4.6 overclaim)"
        else
            skip "hardlink escape: not reproducible on this filesystem — no claim made either way"
        fi

        # The out-of-scope file's CONTENT must be untouched regardless: an
        # ownership escape is bad; a content escape would be worse.
        if [[ "$(cat "${OUT18}/outside_file.bin")" == "payload" ]]; then
            pass "hardlink escape: the out-of-scope file's CONTENT is untouched (the escape is ownership-only, as documented)"
        else
            fail "hardlink escape: the out-of-scope file's CONTENT changed — the escape is wider than documented"
        fi
    fi
fi

# ===========================================================================
# CASE 19 — A FAILED chown MUST PRINT ITS REASON (MINOR-2, §11.4.201(5)).
#
# scripts/ownership_repair.sh:573/:580 discarded chown's stderr with
# `2>/dev/null`, and the FAILED line at :640 named the path but no errno:
#
#   FAILED <path> — cannot change ownership to 1000:1000 (<label>)
#
# MEASURED against the pre-fix artifact with an injected EROFS from chown:
#   grep -ci 'Read-only file system' over the whole run output  ->  0
#
# So the operator could not tell EPERM (wrong identity) from EROFS (remount the
# filesystem) from ENOENT (it vanished) — three different remediations behind
# one undifferentiated sentence. §11.4.201(5): every refusal prints its
# resolved evidence.
# ===========================================================================
echo
echo "Case 19: a failed chown reports the reason it failed, not just that it failed (MINOR-2)"
SB19="$(sb_new)" || { fail "could not build sandbox"; finish; }
IN19="${SB19}/fixture/tree"
seed_tree "${IN19}" 2 wrong
printf '%s\tdownloads\tfalse\tfalse\ttrue\n' "${IN19}" | sb_scope "${SB19}"
_C19_NEEDLE='Read-only file system'
_C19_SHIM="$(shim_dir "${SB19}" chown \
    '#!/bin/sh
echo "chown: changing ownership: '"${_C19_NEEDLE}"'" >&2
exit 1')"
# A runtime `unshare` fallback would mask the shim, so it is switched off the
# way the artifact's own header documents: a SET-BUT-EMPTY CONTAINER_RUNTIME is
# honoured as "no runtime available" (scripts/ownership_repair.sh:325-333).
RUN_OUT="$(
    cd "${SB19}" && PATH="${_C19_SHIM}:${PATH}" CONTAINER_RUNTIME="" \
        OWNED_PATHS_FILE="${SB19}/config/owned_paths.yaml" \
        bash "${SB19}/scripts/ownership_repair.sh" \
            --scope "${SB19}/config/owned_paths.yaml" 2>&1
)"
RUN_RC=$?

if [[ "${RUN_RC}" -eq 0 ]]; then
    fail "chown reason: exit 0 while every chown failed — the shim never took effect, so this case proved nothing (instrument blind, §11.4.201(7)(b))"
else
    pass "chown reason [control needle]: the injected chown failure really reached the artifact (exit ${RUN_RC}, not 0)"
    if printf '%s' "${RUN_OUT}" | grep -qF -- "${_C19_NEEDLE}"; then
        pass "chown reason: the FAILED report carries the reason chown gave ('${_C19_NEEDLE}')"
    else
        fail "chown reason: the reason chown gave was DISCARDED — the operator sees 'cannot change ownership' with no errno, and EPERM/EROFS/ENOENT need three different remediations (§11.4.201(5))"
        printf '%s\n' "${RUN_OUT}" | grep -i 'FAILED' | head -2 | sed 's/^/        /'
    fi
fi

# ===========================================================================
# CASE 20 — A FAILED MODE RESTORE MUST NOT BE SWALLOWED (MINOR-3, FR-015).
#
# scripts/ownership_repair.sh:702 was:
#     chmod "${_mode}" -- "${path}" 2>/dev/null || true
# The step that DELIVERS FR-015 ("the exact bits are preserved") swallowed its
# own failure: no record entry, no log line, no effect on the exit code.
#
# MEASURED against the pre-fix artifact with an injected chmod failure on a
# preserve_mode entry — every mode restore failed and the run still reported:
#     [ownership-repair] complete: 2 item(s) repaired; ... marker s6/repair-marker.json
#     rc=0
# So it exited 0, WROTE A COMPLETION MARKER, and claimed the bits were
# preserved when not one of them had been restored. The direction is
# narrowing-only, so this is not a widening risk — but "exact bits preserved"
# is claimed by FR-015 and was never verified.
# ===========================================================================
echo
echo "Case 20: a failed mode restore is reported and blocks the completion marker (MINOR-3, FR-015)"
SB20="$(sb_new)" || { fail "could not build sandbox"; finish; }
IN20="${SB20}/fixture/preserved"
mkdir -p "${IN20}"
printf 'x\n' > "${IN20}/f.bin"
chmod 640 "${IN20}/f.bin"
seed_wrong -R "${IN20}"
printf '%s\tcredential-store\tfalse\ttrue\ttrue\n' "${IN20}" | sb_scope "${SB20}"
_C20_SHIM="$(shim_dir "${SB20}" chmod \
    '#!/bin/sh
echo "chmod: cannot change permissions: injected failure" >&2
exit 1')"
RUN_OUT="$(
    cd "${SB20}" && PATH="${_C20_SHIM}:${PATH}" CONTAINER_RUNTIME="" \
        OWNED_PATHS_FILE="${SB20}/config/owned_paths.yaml" \
        bash "${SB20}/scripts/ownership_repair.sh" \
            --scope "${SB20}/config/owned_paths.yaml" 2>&1
)"
RUN_RC=$?

if printf '%s' "${RUN_OUT}" | grep -qiE 'mode|chmod|permission'; then
    pass "mode-restore failure: the run REPORTS that a mode could not be restored"
else
    fail "mode-restore failure: silence — the FR-015 mode restore failed for every item and nothing said so (no log line, no record, no exit-code effect)"
fi

if [[ "${RUN_RC}" -eq 0 ]]; then
    fail "mode-restore failure: exit 0 — the run claimed the exact bits were preserved while every restore failed (§11.4 PASS-bluff at the FR-015 layer)"
else
    pass "mode-restore failure: did not exit 0 with FR-015 undelivered"
fi

if [[ "${MARKER_DETECTOR_PROVEN}" -ne 1 ]]; then
    fail "mode-restore failure: marker verdict WITHHELD — the detector needle never fired (§11.4.201(7)(b))"
elif marker_present "${SB20}"; then
    fail "mode-restore failure: a COMPLETION MARKER was written although FR-015 was not delivered — the next start will skip the repair"
else
    pass "mode-restore failure: no completion marker — the next run retries"
fi

# ===========================================================================
# CASE 21 — THE FINGERPRINT COMMENT MUST DESCRIBE THE FINGERPRINT (NIT-1).
#
# scripts/ownership_repair.sh:132-134 said the fingerprint is computed
# "from the scope file's literal text". It is not: scripts/lib/ownership.sh
# :161-163 computes it over `ownership_scope_entries`, which is the PARSED and
# ENVIRONMENT-EXPANDED row set.
#
# MEASURED 2026-08-25 on one unchanged scope file whose only entry is the
# shipped `${QBITTORRENT_DATA_DIR:-/mnt/DATA}`:
#   env unset                 -> 76b3930629a1e422...
#   QBITTORRENT_DATA_DIR=/tmp/aaa -> cc412df3ff7e2435...
#   QBITTORRENT_DATA_DIR=/tmp/bbb -> e4a6c4b467dc0ce3...
#   sha256 of the file's literal bytes -> a73b307a006a3117...   (matches none)
#
# The consequence is operational, not cosmetic: the fingerprint moves with the
# ENVIRONMENT, so a hand-run repair in a shell that has not sourced `.env`
# computes a different fingerprint and its marker does not satisfy start.sh's
# check — and vice versa. That is the behaviour; the comment must say so.
# ===========================================================================
echo
echo "Case 21: the fingerprint comment matches what the fingerprint actually is (NIT-1)"
SB21="$(sb_new)" || { fail "could not build sandbox"; finish; }
sb_raw_scope "${SB21}" 'schema_version: 1
paths:
  - path: "${QBITTORRENT_DATA_DIR:-/mnt/DATA}"
    kind: downloads
    optional: false
    preserve_mode: false
    recursive: true'
_c21_fp() {
    (
        export OWNED_PATHS_FILE="${SB21}/config/owned_paths.yaml"
        [[ -n "${1:-}" ]] && export QBITTORRENT_DATA_DIR="$1"
        # shellcheck disable=SC1090
        source "${SB21}/scripts/lib/ownership.sh"
        ownership_scope_fingerprint
    )
}
_C21_A="$(_c21_fp "")"
_C21_B="$(_c21_fp "/tmp/boba_c21_alpha")"
_C21_LITERAL="$(sha256sum "${SB21}/config/owned_paths.yaml" | cut -d' ' -f1)"

if [[ -z "${_C21_A}" || -z "${_C21_B}" ]]; then
    fail "fingerprint prose: the fingerprint helper returned nothing — the measurement is blind"
elif [[ "${_C21_A}" == "${_C21_B}" ]]; then
    fail "fingerprint prose: the fingerprint did NOT move with the environment — this case's premise no longer holds and its assertions below are stale"
else
    pass "fingerprint prose [measured]: one unchanged scope file yields two fingerprints under two environments — it is NOT the file's literal text"
    if [[ "${_C21_A}" == "${_C21_LITERAL}" || "${_C21_B}" == "${_C21_LITERAL}" ]]; then
        fail "fingerprint prose: a fingerprint equals sha256 of the file's literal bytes — contradicts the measurement above"
    else
        pass "fingerprint prose [measured]: neither fingerprint equals sha256 of the file's literal bytes"
    fi
fi

if grep -qF "scope file's literal text" "${SCRIPT}"; then
    fail "fingerprint prose: the artifact still claims the fingerprint comes from \"the scope file's literal text\" — measured false above (§11.4.6)"
else
    pass "fingerprint prose: the artifact no longer claims the fingerprint is the file's literal text"
fi
if grep -qiE 'expand|environment' <(sed -n '120,150p' "${SCRIPT}"); then
    pass "fingerprint prose: the corrected comment names the environment-expanded parse as the fingerprint's input"
else
    fail "fingerprint prose: the corrected comment does not say the fingerprint is computed over the ENVIRONMENT-EXPANDED parse, which is what makes an unsourced .env invalidate a marker"
fi

# ===========================================================================
# CASE 22 — A FAILURE ON THE DECLARED ROOT ITSELF IS DIAGNOSED AS SUCH (NIT-2).
#
# scripts/ownership_repair.sh:743 has find name the declared root itself, so a
# root-owned mount point (the ordinary state of `/mnt/DATA` before udisks hands
# it over) fails both chown paths, sets RC=1, suppresses the marker, and forces
# a full re-walk of the whole library on every start — with an operator-facing
# message identical to the one a single unreadable file produces.
#
# The failure itself is CORRECT and is deliberately preserved: an in-scope item
# that could not be repaired must not be reported as repaired (§11.4.201, and
# §11.4.120 forbids weakening an assertion to make a gate pass). What was wrong
# is that the operator could not tell WHICH failure they had. This case pins
# the diagnosis: when the item that failed IS the declared root of the entry,
# the report must say so, so the remediation (fix the mount, not the files) is
# reachable from the message.
# ===========================================================================
echo
echo "Case 22: a chown failure on the DECLARED ROOT itself is named as such (NIT-2)"
SB22="$(sb_new)" || { fail "could not build sandbox"; finish; }
IN22="${SB22}/fixture/mountpoint"
seed_tree "${IN22}" 2 wrong
# The declared ROOT itself carries the foreign uid — that IS the case's
# subject (an unowned mount point), and a uid-owned root would never be
# selected by the walk at all. Seeded LAST: nothing writes into it afterwards.
seed_wrong -D "${IN22}"
printf '%s\tdownloads\tfalse\tfalse\ttrue\n' "${IN22}" | sb_scope "${SB22}"
# Fail ONLY on the declared root, exactly as an unowned mount point does; every
# child still chowns normally, so the case distinguishes "the root failed" from
# "everything failed".
_C22_SHIM="$(shim_dir "${SB22}" chown \
    '#!/bin/sh
for a in "$@"; do
  if [ "$a" = "'"${IN22}"'" ]; then
    echo "chown: changing ownership of '"'"''"${IN22}"''"'"': Operation not permitted" >&2
    exit 1
  fi
done
exec /usr/bin/chown "$@"')"
RUN_OUT="$(
    cd "${SB22}" && PATH="${_C22_SHIM}:${PATH}" CONTAINER_RUNTIME="${NS_RUNTIME}" \
        OWNED_PATHS_FILE="${SB22}/config/owned_paths.yaml" \
        bash "${SB22}/scripts/ownership_repair.sh" \
            --scope "${SB22}/config/owned_paths.yaml" 2>&1
)"
RUN_RC=$?

if [[ "${RUN_RC}" -eq 0 ]]; then
    fail "declared-root failure: exit 0 — the shim never took effect, so this case proved nothing (instrument blind)"
else
    pass "declared-root failure [control needle]: the injected root-only failure really reached the artifact (exit ${RUN_RC})"
    if printf '%s' "${RUN_OUT}" | grep -qiE 'declared (path|root)|mount point'; then
        pass "declared-root failure: the report identifies the failing item as the DECLARED ROOT, so the remediation is the mount and not the files"
    else
        fail "declared-root failure: the failing declared root is reported exactly like an ordinary in-scope file — the operator cannot tell a root-owned mount point from a bad file, and the consequence is a full re-walk of the library on every start"
        printf '%s\n' "${RUN_OUT}" | grep -i 'FAILED' | head -3 | sed 's/^/        /'
    fi
fi

# ===========================================================================
# CASE 23 — A DECLARED ENTRY THAT EXPANDS TO NOTHING REFUSES THE WHOLE RUN
#           (R2-M1 — the PARTIAL half of the empty-scope family).
#
# Case 16 pinned the TOTAL-empty scope (exit 2, no marker). Its PARTIAL sibling
# was uncovered and, MEASURED 2026-08-26 against the pre-fix artifact:
#
#     a 2-entry scope whose first entry is `${UNSET_VAR}` (no `:-` default)
#     reported "(1 declared locations)", walked only the survivor, exited 0,
#     and WROTE A COMPLETION MARKER.
#
# One DECLARED location silently vanished. `ownership_scope_entries`
# (scripts/lib/ownership.sh) dropped it with a bare `continue`, so no consumer
# — not this repair, not scripts/ownership_precondition.sh, not the pre-build
# gate — could tell a 2-entry scope with a hole from an honest 1-entry scope.
# That is the same §11.4.201(6) false-null the IMPORTANT-1 remediation names:
# a blind read and a clean tree return the same quiet number.
#
# WHY THE WHOLE RUN AND NOT JUST THE ENTRY (the decision this case pins):
#   The completion marker carries a fingerprint over the PARSED entries and
#   start.sh reads it as "already repaired", so a partial walk that exits 0
#   does not merely miss a location once — it LATCHES the miss for every
#   subsequent start. scripts/ownership_repair.sh:485-489 already recorded the
#   identical decision for the fence ("ONE BAD ENTRY REFUSES THE WHOLE RUN …
#   Refusing per-entry and proceeding with the rest would silently repair a
#   partial scope while writing a marker that claims the whole one"), and two
#   different answers to one question inside one file is the second dialect
#   §11.4.251 forbids.
#
# WHY THIS LIVES IN THE PARSER AND NOT IN THIS CONSUMER:
#   The parser is the only layer that still holds the raw spelling and the
#   variable name; every layer above it has already lost the information
#   (§11.4.241 — enforce at the strongest rung that can see the invariant).
#   Putting it there also gives all three consumers one predicate rather than
#   three crosschecks that could disagree about expansion semantics.
#
# THE GOLDEN-FALSE HALF IS LOAD-BEARING (§11.4.201(1)): the shipped scope's
# FIRST entry is `${QBITTORRENT_DATA_DIR:-/mnt/DATA}`. A refusal that also
# refused the `:-default` shape would refuse the live product configuration —
# a false-positive refusal, forbidden exactly as firmly as a false pass.
# ===========================================================================
echo
echo "Case 23: a declared entry that expands to NOTHING refuses the whole run (R2-M1)"

# --- control needle FIRST (§11.4.201(7)(b)) --------------------------------
# Two LITERAL entries in the same sandbox shape must report TWO declared
# locations, exit 0 and write a marker. Without this, every "exit 2 / no
# marker" verdict below could be produced by a sandbox that never ran, and a
# "(1 declared locations)" assertion could be read off the wrong scope file —
# both instrument failures this task has already produced once.
SB23C="$(sb_new)" || { fail "could not build sandbox"; finish; }
mkdir -p "${SB23C}/fixture/a23" "${SB23C}/fixture/b23"
seed_tree "${SB23C}/fixture/a23" 2 wrong
seed_tree "${SB23C}/fixture/b23" 2 wrong
{
    printf '%s\tdownloads\tfalse\tfalse\ttrue\n' "${SB23C}/fixture/a23"
    printf '%s\tdownloads\tfalse\tfalse\ttrue\n' "${SB23C}/fixture/b23"
} | sb_scope "${SB23C}"
run_repair "${SB23C}"
_C23_NEEDLE=0
if [[ "${RUN_RC}" -eq 0 ]] \
   && printf '%s' "${RUN_OUT}" | grep -qF '(2 declared locations)' \
   && marker_present "${SB23C}"; then
    _C23_NEEDLE=1
    pass "vanished entry [control needle]: two literal entries report '(2 declared locations)', exit 0 and write a marker — the count is read from THIS sandbox's scope, and the assertions below are not vacuous"
else
    fail "vanished entry [control needle]: two literal entries gave rc=${RUN_RC}, count line '$(printf '%s' "${RUN_OUT}" | grep -o '([0-9]* declared locations)' || echo NONE)' — the instrument is blind, so no verdict below can be trusted"
fi

# _c23_refuses <label> <yaml> [env-assignment…]
# Asserts the four properties a vanished declaration must produce.
_c23_refuses() {
    local label="$1" yaml="$2"; shift 2
    local sb
    sb="$(sb_new)" || { fail "vanished entry [${label}]: could not build sandbox"; return 0; }
    mkdir -p "${sb}/fixture/survivor"
    seed_tree "${sb}/fixture/survivor" 2 wrong
    # The survivor's absolute path is substituted into the fixture YAML so the
    # scope really does declare a walkable location alongside the broken one.
    sb_raw_scope "${sb}" "${yaml//@SURVIVOR@/${sb}/fixture/survivor}"
    local before after
    before="$(manifest "${sb}/fixture/survivor")"
    RUN_OUT="$(
        cd "${sb}" && env "$@" OWNED_PATHS_FILE="${sb}/config/owned_paths.yaml" \
            bash "${sb}/scripts/ownership_repair.sh" \
                --scope "${sb}/config/owned_paths.yaml" 2>&1
    )"
    RUN_RC=$?
    after="$(manifest "${sb}/fixture/survivor")"

    if [[ "${RUN_RC}" -eq 2 ]]; then
        pass "vanished entry [${label}]: exit 2 — 'could not run', not a completed repair"
    elif [[ "${RUN_RC}" -eq 0 ]]; then
        fail "vanished entry [${label}]: exit 0 — a DECLARED location vanished and the run reported SUCCESS (§11.4.201(6) false-null; the marker latches the miss on every subsequent start)"
    else
        fail "vanished entry [${label}]: exit ${RUN_RC} — the contract reserves 2 for 'could not run'"
    fi

    if printf '%s' "${RUN_OUT}" | grep -qE '\([0-9]+ declared locations\)'; then
        fail "vanished entry [${label}]: the run announced '$(printf '%s' "${RUN_OUT}" | grep -o '([0-9]* declared locations)')' and proceeded — a scope with a hole was reported as an honest scope of that size"
    else
        pass "vanished entry [${label}]: the run never announced a shrunken location count — it refused before walking"
    fi

    if [[ "${_C23_NEEDLE}" -ne 1 ]]; then
        fail "vanished entry [${label}]: marker verdict WITHHELD — the control needle never fired (§11.4.201(7)(b))"
    elif marker_present "${sb}"; then
        fail "vanished entry [${label}]: a COMPLETION MARKER was written for a scope with a vanished declaration — start.sh will skip the repair from now on"
    else
        pass "vanished entry [${label}]: no completion marker written — the next start still repairs"
    fi

    # §11.4.201(5): the refusal must print its resolved evidence — WHICH entry
    # and WHY, not merely that something was empty.
    if printf '%s' "${RUN_OUT}" | grep -qiE 'entry [0-9]+' \
       && printf '%s' "${RUN_OUT}" | grep -qiE 'empty path|expanded to nothing|no path'; then
        pass "vanished entry [${label}]: the refusal names WHICH declared entry produced no path"
    else
        fail "vanished entry [${label}]: the refusal does not name the offending entry — the operator cannot act on it (§11.4.201(5))"
        printf '%s\n' "${RUN_OUT}" | grep -iE 'scope|entry|empty' | head -4 | sed 's/^/        /'
    fi

    if [[ "${before}" == "${after}" ]]; then
        pass "vanished entry [${label}]: the surviving location was not touched — the refusal happened before any walk"
    else
        fail "vanished entry [${label}]: the surviving location was MUTATED despite the refusal"
    fi
}

_c23_refuses 'unset ${VAR}, no default' 'schema_version: 1
paths:
  - path: "${BOBA_T028_UNSET_QQQ}"
    kind: downloads
    optional: false
    preserve_mode: false
    recursive: true
  - path: "@SURVIVOR@"
    kind: downloads
    optional: false
    preserve_mode: false
    recursive: true'

_c23_refuses 'set-but-EMPTY ${VAR}, no default' 'schema_version: 1
paths:
  - path: "@SURVIVOR@"
    kind: downloads
    optional: false
    preserve_mode: false
    recursive: true
  - path: "${BOBA_T028_EMPTY_QQQ}"
    kind: downloads
    optional: false
    preserve_mode: false
    recursive: true' BOBA_T028_EMPTY_QQQ=

_c23_refuses 'entry with no path: key at all' 'schema_version: 1
paths:
  - kind: downloads
    optional: false
    preserve_mode: false
    recursive: true
  - path: "@SURVIVOR@"
    kind: downloads
    optional: false
    preserve_mode: false
    recursive: true'

# An `optional: true` entry is NOT an escape hatch. `optional` declares that the
# path may be ABSENT from the filesystem; it does not declare that the path may
# be absent from the DECLARATION. The scope format already has a vocabulary for
# "this location is not configured on this host" — `${VAR:-default}` — and the
# remedy for a hole is to supply one or delete the entry.
_c23_refuses 'vanished entry marked optional: true' 'schema_version: 1
paths:
  - path: "${BOBA_T028_UNSET_QQQ}"
    kind: credential-store
    optional: true
    preserve_mode: true
    recursive: false
  - path: "@SURVIVOR@"
    kind: downloads
    optional: false
    preserve_mode: false
    recursive: true'

# --- ADJACENT CASE, found while fixing R2-M1 and closed with it (§11.4.238) --
# A `${VAR}` with no default that resolves empty MID-PATH does not empty the
# path — it SILENTLY REWRITES it. MEASURED 2026-08-26 against the pre-fix
# artifact: `<sb>/fixture/decoy/${UNSET}/leaf` collapsed to
# `<sb>/fixture/decoy/leaf`, the fence accepted it (absolute, deep enough), and
# the repair walked and chowned a tree the scope never declared, exit 0.
#
# The depth floor catches the shapes that collapse to `/x` or `/`, but not one
# that collapses to another well-formed deep path — so the fence is NOT a
# backstop for this and the parser must refuse it. `${VAR:-default}` (and the
# explicit `${VAR:-}`) are the operator SAYING what empty means, and are not
# refused; the golden-FALSE below pins that.
SB23M="$(sb_new)" || { fail "could not build sandbox"; finish; }
mkdir -p "${SB23M}/fixture/decoy/leaf"
seed_tree "${SB23M}/fixture/decoy/leaf" 2 wrong
sb_raw_scope "${SB23M}" "schema_version: 1
paths:
  - path: \"${SB23M}/fixture/decoy/\${BOBA_T028_UNSET_QQQ}/leaf\"
    kind: downloads
    optional: false
    preserve_mode: false
    recursive: true"
_C23M_BEFORE="$(manifest "${SB23M}/fixture/decoy/leaf")"
run_repair "${SB23M}"
if [[ "${RUN_RC}" -eq 2 ]]; then
    pass "vanished entry [unresolved \${VAR} mid-path]: exit 2 — a declaration that silently rewrote itself into a different path is refused"
else
    fail "vanished entry [unresolved \${VAR} mid-path]: exit ${RUN_RC} — an unset variable collapsed the declared path into a DIFFERENT well-formed path and the run proceeded (the depth floor cannot catch this shape)"
fi
if [[ "${_C23M_BEFORE}" == "$(manifest "${SB23M}/fixture/decoy/leaf")" ]]; then
    pass "vanished entry [unresolved \${VAR} mid-path]: the substituted tree was not touched"
else
    fail "vanished entry [unresolved \${VAR} mid-path]: the repair CHOWNED a tree the scope never declared — the operator declared one path and a different one was rewritten"
fi

# golden-FALSE for the mid-path rule: an interpolated `:-default` must still run.
SB23N="$(sb_new)" || { fail "could not build sandbox"; finish; }
mkdir -p "${SB23N}/fixture/mid/real/leaf"
seed_tree "${SB23N}/fixture/mid/real/leaf" 2 wrong
sb_raw_scope "${SB23N}" "schema_version: 1
paths:
  - path: \"${SB23N}/fixture/mid/\${BOBA_T028_UNSET_QQQ:-real}/leaf\"
    kind: downloads
    optional: false
    preserve_mode: false
    recursive: true"
run_repair "${SB23N}"
if [[ "${RUN_RC}" -eq 0 ]] && [[ "$(wrong_owned_count "${SB23N}/fixture/mid/real/leaf")" -eq 0 ]]; then
    pass "vanished entry [golden-FALSE, interpolated \${VAR:-default}]: a mid-path default is NOT refused — it resolved and really repaired the tree"
else
    fail "vanished entry [golden-FALSE, interpolated \${VAR:-default}]: exit ${RUN_RC}, $(wrong_owned_count "${SB23N}/fixture/mid/real/leaf") item(s) still wrongly owned — the mid-path rule swallowed a legitimate default (§11.4.201(1))"
fi

# --- R3-N1: a spelling the documented grammar cannot resolve ---------------
# The header documents exactly TWO forms: `${VAR}` and `${VAR:-default}`.
# MEASURED 2026-08-26 against the round-3 artifact: a NESTED `${A:-${B}}`
# satisfies neither and was NOT refused — the default group `[^}]*` stops at
# the INNER `}`, so with both unset the row came out as the literal
# `…/${BOBA_T028_UNSET_B}/leaf`, and with A set as the corrupted `…//tmp/x}/leaf`
# (the outer `}` stranded). Neither is the path the operator declared.
#
# WHY THIS IS THE R2-M1 FAMILY AND NOT A CURIOSITY: a NON-optional entry then
# fails honestly ("does not exist", exit 1), but an `optional: true` one logs
# `absent, declared optional — skipped` and the run EXITS 0 and writes the
# marker — a corrupted path that looks like a successful run while repairing
# nothing. That is the same under-repair-while-reporting-success shape R2-M1
# closed for the whole-path case, still open for this one.
#
# THE RULE IS ABOUT SPELLING, NEVER ABOUT A VARIABLE'S VALUE (§11.4.201(1)).
# The two golden-FALSE cases below are the false-positive guards that pin it:
# a literal `}` in a path that also interpolates, and a variable whose VALUE
# contains `${`, must both still resolve and really repair. A value is
# env-writer-controlled exactly as QBITTORRENT_DATA_DIR is (round-2 RM9).
#
# _c23_unresolved <label> <yaml> [env-assignment…]
# Its own CAUSE-SPECIFIC evidence regex (§11.4.120): the existing families keep
# theirs, so broadening nothing — this one dies if the rule is reverted OR if
# the message stops naming the unresolved spelling.
_c23_unresolved() {
    local label="$1" yaml="$2"; shift 2
    local sb before after
    sb="$(sb_new)" || { fail "unresolved spelling [${label}]: could not build sandbox"; return 0; }
    mkdir -p "${sb}/fixture/survivor"
    seed_tree "${sb}/fixture/survivor" 2 wrong
    sb_raw_scope "${sb}" "${yaml//@SURVIVOR@/${sb}/fixture/survivor}"
    before="$(manifest "${sb}/fixture/survivor")"
    RUN_OUT="$(
        cd "${sb}" && env "$@" OWNED_PATHS_FILE="${sb}/config/owned_paths.yaml" \
            bash "${sb}/scripts/ownership_repair.sh" \
                --scope "${sb}/config/owned_paths.yaml" 2>&1
    )"
    RUN_RC=$?
    after="$(manifest "${sb}/fixture/survivor")"

    if [[ "${RUN_RC}" -eq 2 ]]; then
        pass "unresolved spelling [${label}]: exit 2 — a declaration the documented grammar cannot resolve is refused before any walk"
    else
        fail "unresolved spelling [${label}]: exit ${RUN_RC} — a path the grammar could not resolve was accepted; marked \`optional: true\` this is a silent skip that exits 0 while repairing nothing (§11.4.201(6))"
    fi

    if printf '%s' "${RUN_OUT}" | grep -qiE 'entry [0-9]+' \
       && printf '%s' "${RUN_OUT}" | grep -qiE 'not fully resolved'; then
        pass "unresolved spelling [${label}]: the refusal names WHICH entry and says the spelling was not fully resolved (§11.4.201(5))"
    else
        fail "unresolved spelling [${label}]: the refusal names neither the entry nor the unresolved spelling — the operator cannot act on it (§11.4.201(5))"
        printf '%s\n' "${RUN_OUT}" | grep -iE 'entry|resolv|scope' | head -4 | sed 's/^/        /'
    fi

    if [[ "${_C23_NEEDLE}" -ne 1 ]]; then
        fail "unresolved spelling [${label}]: marker verdict WITHHELD — the control needle never fired (§11.4.201(7)(b))"
    elif marker_present "${sb}"; then
        fail "unresolved spelling [${label}]: a COMPLETION MARKER was written for a scope whose spelling never resolved — start.sh will skip the repair from now on"
    else
        pass "unresolved spelling [${label}]: no completion marker written — the next start still repairs"
    fi

    if [[ "${before}" == "${after}" ]]; then
        pass "unresolved spelling [${label}]: the surviving location was not touched — the refusal happened before any walk"
    else
        fail "unresolved spelling [${label}]: the surviving location was MUTATED despite the refusal"
    fi
}

_c23_unresolved 'nested ${A:-${B}}, both unset' 'schema_version: 1
paths:
  - path: "/tmp/boba-t028-nested/${BOBA_T028_UNSET_QQQ:-${BOBA_T028_UNSET_B}}/leaf"
    kind: downloads
    optional: false
    preserve_mode: false
    recursive: true
  - path: "@SURVIVOR@"
    kind: downloads
    optional: false
    preserve_mode: false
    recursive: true'

_c23_unresolved 'nested ${A:-${B}}, A set — the corrupted-path variant' 'schema_version: 1
paths:
  - path: "/tmp/boba-t028-nested/${BOBA_T028_SET_A:-${BOBA_T028_UNSET_B}}/leaf"
    kind: downloads
    optional: false
    preserve_mode: false
    recursive: true
  - path: "@SURVIVOR@"
    kind: downloads
    optional: false
    preserve_mode: false
    recursive: true' BOBA_T028_SET_A=/tmp/boba-t028-a

# The motivating case: `optional: true` turned the corrupted path into an
# exit-0 skip. It must be refused exactly as the non-optional one is.
_c23_unresolved 'nested ${A:-${B}} marked optional: true' 'schema_version: 1
paths:
  - path: "/tmp/boba-t028-nested/${BOBA_T028_UNSET_QQQ:-${BOBA_T028_UNSET_B}}/leaf"
    kind: credential-store
    optional: true
    preserve_mode: true
    recursive: false
  - path: "@SURVIVOR@"
    kind: downloads
    optional: false
    preserve_mode: false
    recursive: true'

# Out-of-grammar openers the substitution never consumes: round 2 recorded
# these as "left literal, walks nothing silently" — which is the same silent
# under-repair. They belong to this family.
_c23_unresolved 'out-of-grammar ${} opener' 'schema_version: 1
paths:
  - path: "/tmp/boba-t028-nested/${}/leaf"
    kind: downloads
    optional: false
    preserve_mode: false
    recursive: true
  - path: "@SURVIVOR@"
    kind: downloads
    optional: false
    preserve_mode: false
    recursive: true'

_c23_unresolved 'out-of-grammar ${1} positional' 'schema_version: 1
paths:
  - path: "/tmp/boba-t028-nested/${1}/leaf"
    kind: downloads
    optional: false
    preserve_mode: false
    recursive: true
  - path: "@SURVIVOR@"
    kind: downloads
    optional: false
    preserve_mode: false
    recursive: true'

# golden-FALSE A (§11.4.201(1)): a LITERAL `}` in a path that ALSO interpolates.
# The rule must judge the interpolation, not every brace character — a
# directory named with a `}` is legal and must still be repaired.
SB23U="$(sb_new)" || { fail "could not build sandbox"; finish; }
mkdir -p "${SB23U}/fixture/brace/real/od}d"
seed_tree "${SB23U}/fixture/brace/real/od}d" 2 wrong
sb_raw_scope "${SB23U}" "schema_version: 1
paths:
  - path: \"${SB23U}/fixture/brace/\${BOBA_T028_UNSET_QQQ:-real}/od}d\"
    kind: downloads
    optional: false
    preserve_mode: false
    recursive: true"
run_repair "${SB23U}"
if [[ "${RUN_RC}" -eq 0 ]] && [[ "$(wrong_owned_count "${SB23U}/fixture/brace/real/od}d")" -eq 0 ]]; then
    pass "unresolved spelling [golden-FALSE, literal } beside an interpolation]: NOT refused — it resolved and really repaired the tree"
else
    fail "unresolved spelling [golden-FALSE, literal } beside an interpolation]: exit ${RUN_RC}, $(wrong_owned_count "${SB23U}/fixture/brace/real/od}d") item(s) still wrongly owned — the rule judged a brace CHARACTER instead of the interpolation (§11.4.201(1))"
fi

# golden-FALSE B (§11.4.201(1)): a variable whose VALUE contains `${`. Values
# are env-writer-controlled exactly as QBITTORRENT_DATA_DIR is, so the rule
# must never reach into them.
SB23V="$(sb_new)" || { fail "could not build sandbox"; finish; }
mkdir -p "${SB23V}/fixture/val/\${weird}"
seed_tree "${SB23V}/fixture/val/\${weird}" 2 wrong
sb_raw_scope "${SB23V}" "schema_version: 1
paths:
  - path: \"\${BOBA_T028_VALUE_QQQ}/leaf\"
    kind: downloads
    optional: false
    preserve_mode: false
    recursive: true"
mkdir -p "${SB23V}/fixture/val/\${weird}/leaf"
seed_tree "${SB23V}/fixture/val/\${weird}/leaf" 2 wrong
RUN_OUT="$(
    cd "${SB23V}" && env "BOBA_T028_VALUE_QQQ=${SB23V}/fixture/val/\${weird}" \
        OWNED_PATHS_FILE="${SB23V}/config/owned_paths.yaml" \
        bash "${SB23V}/scripts/ownership_repair.sh" \
            --scope "${SB23V}/config/owned_paths.yaml" 2>&1
)"
RUN_RC=$?
if [[ "${RUN_RC}" -eq 0 ]] && [[ "$(wrong_owned_count "${SB23V}/fixture/val/\${weird}/leaf")" -eq 0 ]]; then
    pass "unresolved spelling [golden-FALSE, a VALUE containing \${]: NOT refused — the rule judges the declared spelling, never the variable's value"
else
    fail "unresolved spelling [golden-FALSE, a VALUE containing \${]: exit ${RUN_RC}, $(wrong_owned_count "${SB23V}/fixture/val/\${weird}/leaf") item(s) still wrongly owned — the rule reached into a variable's VALUE, refusing an env-writer-controlled path (§11.4.201(1))"
fi

# --- GOLDEN-FALSE (§11.4.201(1)): the SHIPPED entry shape must still run ----
# `${VAR:-default}` with VAR unset is the shape of the shipped scope's first
# entry. A refusal that swallowed it would refuse the live product.
SB23G="$(sb_new)" || { fail "could not build sandbox"; finish; }
mkdir -p "${SB23G}/fixture/defaulted"
seed_tree "${SB23G}/fixture/defaulted" 2 wrong
sb_raw_scope "${SB23G}" "schema_version: 1
paths:
  - path: \"\${BOBA_T028_UNSET_QQQ:-${SB23G}/fixture/defaulted}\"
    kind: downloads
    optional: false
    preserve_mode: false
    recursive: true"
run_repair "${SB23G}"
if [[ "${RUN_RC}" -eq 0 ]] && [[ "$(wrong_owned_count "${SB23G}/fixture/defaulted")" -eq 0 ]]; then
    pass "vanished entry [golden-FALSE, \${VAR:-default}]: the shipped entry shape is NOT refused — it resolved to its default and really repaired the tree"
else
    fail "vanished entry [golden-FALSE, \${VAR:-default}]: exit ${RUN_RC}, $(wrong_owned_count "${SB23G}/fixture/defaulted") item(s) still wrongly owned — the refusal swallowed the SHIPPED entry shape, which is a false-positive refusal (§11.4.201(1))"
fi

# --- the predicate is SHARED, not a repair-only dialect (§11.4.251) ---------
# scripts/ownership_precondition.sh and the pre-build gate read the same scope
# through the same parser. Asserted against the shared helper directly, so a
# future fix that moved the rule up into ownership_repair.sh alone fails here.
SB23S="$(sb_new)" || { fail "could not build sandbox"; finish; }
mkdir -p "${SB23S}/fixture/keep"
: > "${SB23S}/fixture/keep/f.bin"
sb_raw_scope "${SB23S}" "schema_version: 1
paths:
  - path: \"\${BOBA_T028_UNSET_QQQ}\"
    kind: downloads
    optional: false
    preserve_mode: false
    recursive: true
  - path: \"${SB23S}/fixture/keep\"
    kind: downloads
    optional: false
    preserve_mode: false
    recursive: true"
_C23_LIB_OUT="$(
    OWNED_PATHS_FILE="${SB23S}/config/owned_paths.yaml"
    export OWNED_PATHS_FILE
    # shellcheck disable=SC1090
    source "${SB23S}/scripts/lib/ownership.sh"
    ownership_scope_entries 2>&1
)"
_C23_LIB_RC=$?
if [[ "${_C23_LIB_RC}" -eq 2 ]]; then
    pass "vanished entry [shared predicate]: ownership_scope_entries itself returns 2 — every consumer of the scope inherits the refusal, no second dialect (§11.4.251)"
else
    fail "vanished entry [shared predicate]: ownership_scope_entries returned ${_C23_LIB_RC} — the rule lives above the shared parser, so scripts/ownership_precondition.sh and the pre-build gate still read a scope with a hole as an honest scope (§11.4.251)"
fi
if printf '%s' "${_C23_LIB_OUT}" | grep -qF 'BOBA_T028_UNSET_QQQ'; then
    pass "vanished entry [shared predicate]: the diagnosis names the unresolved variable, so the operator's remedy is reachable from the message"
else
    fail "vanished entry [shared predicate]: the diagnosis never names the unresolved variable — the operator is told something vanished but not what to set"
fi
if [[ -z "$(printf '%s' "${_C23_LIB_OUT}" | grep -v 'BOBA_T028_UNSET_QQQ' | grep -F "${SB23S}/fixture/keep")" ]]; then
    pass "vanished entry [shared predicate]: no survivor rows were emitted alongside the refusal — a caller cannot accidentally consume a partial scope"
else
    fail "vanished entry [shared predicate]: survivor rows were emitted on stdout despite the refusal — a caller that ignores the exit code would walk a partial scope"
fi

# ===========================================================================
# CASE 24 — THE FENCE'S TWO NAMED BOUNDARIES (R2-N1, R2-N2).
#
# R2-N1 is documentation-only BY DECISION: an existing symlink in a NON-FINAL
# component of a declared path steers the walk to the link's target (MEASURED,
# no race needed), and the fence — lexical by design, so that it cannot be
# raced and can judge paths that do not exist yet — cannot see it. The reach is
# bounded by who can write components ABOVE the declared root, which is outside
# every container bind mount and is already the trust boundary that the
# untracked `.env` sits on. What was owed is the SENTENCE: a fence whose stated
# limits let a reader infer symlink safety it does not provide is the
# overstatement §11.4.6 forbids. This case pins that the sentence is there.
#
# R2-N2 is a real DENY, not just a sentence: `/home/<user>` clears the depth
# floor and is deliberately not denylisted (`/home/<user>/Downloads` is an
# ordinary download root), so a declared root at or above the rootless
# container storage would be accepted and the `podman unshare` fallback would
# rewrite subuid-owned image storage. The deny is computed per host, so this
# case drives ownership_path_fence() DIRECTLY with a controlled HOME — a pure
# string predicate, touching nothing real, and never the operator's own $HOME.
#
# THE GOLDEN-FALSE HALF IS THE POINT (§11.4.201(1)): a fence that over-refuses
# is a FAIL-bluff of exactly the severity of one that under-refuses, so the
# ordinary $HOME-rooted download directory must still be ACCEPTED, and must
# still really repair end to end.
# ===========================================================================
echo
echo "Case 24: the fence names its symlink limit and denies container storage without refusing \$HOME (R2-N1, R2-N2)"

# --- R2-N1: the honest boundary states the intermediate-symlink limit -------
if grep -qiE 'intermediate|NON-FINAL component' "${LIB}" \
   && grep -qi 'judges the spelling' "${LIB}"; then
    pass "fence boundary [R2-N1]: the fence's honest boundary states that it judges the SPELLING and that the kernel resolves intermediate components"
else
    fail "fence boundary [R2-N1]: the fence declares its limits without naming static intermediate-symlink resolution — a reader can infer symlink safety the fence does not provide (§11.4.6)"
fi
# THE STRING IS NOT THE TRACKING (R3-M1, MEASURED 2026-08-26). Round 3 cited
# BOB-159 here; that item's 4674-character body contains ZERO occurrences of
# `symlink` or `intermediate` (control needle: 30 hits for `warm|repair`
# through the same sqlite read), and no item in the tracker mentioned symlinks
# at all — a pointer that LOOKS like coverage and is not, which is exactly the
# lost-defect shape §11.4.214 warns about: no tracker query could find the
# static reach. A `grep` for the literal could not see that, because it pinned
# the SPELLING of the citation and never asked whether the pointee records the
# pointed-at content. So this check reads the ids OUT of the fence and asks the
# tracker two questions per id: does that item EXIST, and does it actually
# record THIS reach. The next dangling citation fails here instead of passing.
#
# ONE CITATION IS NOT EVERY CITATION (R4-N2, MEASURED 2026-08-26). Round 4
# extracted the id through `head -1`, so only the FIRST `Tracked as` citation
# was ever judged. The round-4 reviewer's mutation M-F — a SECOND, dangling
# `Tracked as BOB-159` appended after the real one, exactly the shape a future
# edit adding another residual-reach clause would take — SURVIVED at 146/0/0,
# re-opening the R3-M1 shape invisibly through the very check built to close
# it. Re-measured here before fixing (RED): the mutated fence still PASSED with
# "linked to BOB-201 … really records the symlink reach" while a dangling
# BOB-159 sat two lines below it, unasked. This loop judges EVERY distinct
# citation the fence carries. `sort -u` because judging one id twice adds
# nothing: the property is that no cited id goes UNASKED, not that occurrences
# are counted. One aggregate verdict is emitted regardless of how many ids are
# cited, so the suite's assertion count does not drift with the fence's prose.
#
# WHAT "RECORDS THIS REACH" MEANS, AND WHAT IT DOES NOT (§11.4.6). Round 4
# asked only `grep -qi symlink`. That was anchored by LUCK: BOB-201 is the ONLY
# symlink-mentioning item in this tracker (measured 2026-08-26: 1 item of 200),
# so ANY symlink-mentioning item would have satisfied a message claiming the
# item "really records the symlink reach". The reach has two halves — an
# INTERMEDIATE component, and a SYMLINK — so both tokens must be present.
# Measured on this tracker: BOB-201 carries both (its title reads "intermediate
# symlink components"); BOB-159, the round-3 dangling citation, carries NEITHER
# (0 occurrences of each) — the same discriminator the round-3 forensic used.
# Two independent whole-body greps rather than an adjacency regex ON PURPOSE: a
# future re-wording that names "symlink" in the title and "intermediate" three
# paragraphs down still records this reach, and refusing it would be the
# §11.4.201(1) false refusal this suite spends nine golden-FALSE assertions
# guarding against. This stays a PROXY — it asserts both concepts are present,
# never that the prose is correct.
_C24_IDS="$(grep -oE 'Tracked as BOB-[0-9]+' "${LIB}" | grep -oE 'BOB-[0-9]+' | sort -u)"
_C24_IDLIST="$(printf '%s' "${_C24_IDS}" | tr '\n' ' ' | sed 's/ *$//')"
_C24_DB="${PROJECT_ROOT}/docs/workable_items.db"
if [[ -z "${_C24_IDS}" ]]; then
    fail "fence boundary [R2-N1]: the documented residual reach names no tracked item"
elif ! command -v sqlite3 >/dev/null 2>&1; then
    # Honest SKIP, never a pass: the citations ARE present, but this host cannot
    # read the tracker to judge them (§11.4.3 topology_unsupported).
    skip "fence boundary [R2-N1]: cites ${_C24_IDLIST}, but sqlite3 is absent — the tracker cannot be read here, so the citations are unjudged rather than approved"
elif [[ ! -f "${_C24_DB}" ]]; then
    skip "fence boundary [R2-N1]: cites ${_C24_IDLIST}, but ${_C24_DB} is absent — the tracker cannot be read here, so the citations are unjudged rather than approved"
else
    # CONTROL NEEDLE (§11.4.201(7)(b)): a zero from the per-id queries below is
    # evidence ONLY if this same read can see a known-present row. A blind read
    # and an absent item return the identical quiet nothing.
    _C24_ROWS="$(sqlite3 "${_C24_DB}" "SELECT COUNT(*) FROM items;" 2>/dev/null)"
    if [[ -z "${_C24_ROWS}" ]] || [[ "${_C24_ROWS}" -eq 0 ]]; then
        skip "fence boundary [R2-N1]: the tracker read returned no rows at all — treating this as a BLIND read, not as absence (§11.4.201(7)(b))"
    else
        # VERDICT ORDER: FAIL > SKIP > PASS. A proven dangling citation is a
        # defect whether or not some OTHER id read blind, so a FAIL anywhere
        # dominates; and a blind read anywhere forbids a PASS, because
        # approving on a quiet nothing is precisely the §11.4.201(6)
        # false-null. Only an all-ids-judged-clean run reaches `pass`.
        _C24_BAD=""
        _C24_BLIND=""
        for _c24_id in ${_C24_IDS}; do
            _C24_EXISTS="$(sqlite3 "${_C24_DB}" "SELECT COUNT(*) FROM items WHERE atm_id='${_c24_id}';" 2>/dev/null)"
            _C24_BODY="$(sqlite3 "${_C24_DB}" "SELECT COALESCE(title,'')||' '||COALESCE(description,'') FROM items WHERE atm_id='${_c24_id}';" 2>/dev/null)"
            if [[ -z "${_C24_EXISTS}" ]]; then
                # The whole-table needle succeeded but THIS query returned
                # nothing: a blind per-id read, never evidence of absence.
                _C24_BLIND="${_C24_BLIND} ${_c24_id}(existence read returned nothing)"
            elif [[ "${_C24_EXISTS}" != "1" ]]; then
                _C24_BAD="${_C24_BAD} ${_c24_id}(no such item exists in the tracker)"
            elif [[ -z "${_C24_BODY}" ]]; then
                # The row EXISTS but its body read came back empty: that is a
                # blind read of the body, not an item empty of content.
                _C24_BLIND="${_C24_BLIND} ${_c24_id}(body read returned nothing)"
            else
                _c24_miss=""
                printf '%s' "${_C24_BODY}" | grep -qi 'symlink'      || _c24_miss="${_c24_miss} symlink"
                printf '%s' "${_C24_BODY}" | grep -qi 'intermediate' || _c24_miss="${_c24_miss} intermediate"
                [[ -z "${_c24_miss}" ]] || _C24_BAD="${_C24_BAD} ${_c24_id}(exists, but its body never says:${_c24_miss})"
            fi
        done
        if [[ -n "${_C24_BAD}" ]]; then
            fail "fence boundary [R2-N1]: the fence's citation(s)${_C24_BAD} — a citation that does not resolve to an item recording THIS reach looks like coverage and is none, so no tracker query can find the defect (§11.4.214)"
        elif [[ -n "${_C24_BLIND}" ]]; then
            skip "fence boundary [R2-N1]: cited${_C24_BLIND} — BLIND tracker read, unjudged rather than approved (§11.4.201(7)(b))"
        else
            pass "fence boundary [R2-N1]: every citation the fence carries (${_C24_IDLIST}) EXISTS in the tracker and really records this reach — body carries both 'symlink' and 'intermediate' (§11.4.197/§11.4.214)"
        fi
    fi
fi

# --- R2-N2: behaviour, driven directly with a controlled HOME ---------------
# _c24_fence <label> <HOME> <abs-path> <expect: accept|refuse>
_c24_fence() {
    local label="$1" home="$2" path="$3" expect="$4" out rc
    out="$(
        HOME="${home}"
        unset XDG_DATA_HOME
        export HOME
        # shellcheck disable=SC1090
        source "${LIB}"
        ownership_path_fence "${path}" 0 "${home}/project" 2>&1
    )"
    rc=$?
    if [[ "${expect}" == "refuse" ]]; then
        if [[ "${rc}" -ne 0 ]]; then
            pass "fence boundary [${label}]: REFUSED — ${out}"
        else
            fail "fence boundary [${label}]: ACCEPTED '${path}' — a recursive ownership change of rootless container storage breaks the runtime this project mandates (§11.4.161)"
        fi
    else
        if [[ "${rc}" -eq 0 ]]; then
            pass "fence boundary [${label}]: ACCEPTED — an ordinary \$HOME-rooted location is not swallowed by the deny"
        else
            fail "fence boundary [${label}]: REFUSED '${path}' — ${out} — this is a false-positive refusal of a legitimate download root (§11.4.201(1))"
        fi
    fi
}

_C24_HOME="${RUN_ROOT}/fakehome"
mkdir -p "${_C24_HOME}"
_c24_fence 'container storage root'  "${_C24_HOME}" "${_C24_HOME}/.local/share/containers"                 refuse
_c24_fence 'inside container storage' "${_C24_HOME}" "${_C24_HOME}/.local/share/containers/storage/overlay" refuse
# GOLDEN-FALSE set — every one of these must survive the deny.
_c24_fence 'golden-FALSE $HOME/Downloads'      "${_C24_HOME}" "${_C24_HOME}/Downloads"            accept
_c24_fence 'golden-FALSE $HOME/.local/share'   "${_C24_HOME}" "${_C24_HOME}/.local/share"         accept
_c24_fence 'golden-FALSE sibling of storage'   "${_C24_HOME}" "${_C24_HOME}/.local/share/containerz" accept
_c24_fence 'golden-FALSE the real library shape' "${_C24_HOME}" "/run/media/someone/DISK/Downloads" accept

# A degenerate computed value must never broaden into a top-level prefix: with
# HOME unset the deny would compute /.local/share/containers, and it must not
# start swallowing unrelated roots.
_C24_UNSET_OUT="$(
    unset HOME XDG_DATA_HOME
    # shellcheck disable=SC1090
    source "${LIB}"
    ownership_path_fence "/run/media/someone/DISK/Downloads" 0 "/run/media/someone/DISK/project" 2>&1
)"
if [[ $? -eq 0 ]]; then
    pass "fence boundary [degenerate HOME]: with HOME unset the computed deny still accepts an ordinary absolute root — it did not broaden"
else
    fail "fence boundary [degenerate HOME]: with HOME unset the fence refused an ordinary root — ${_C24_UNSET_OUT}"
fi

# --- R2-N2 end-to-end: a $HOME-rooted download tree still really repairs ----
SB24="$(sb_new)" || { fail "could not build sandbox"; finish; }
mkdir -p "${SB24}/fakehome/Downloads"
seed_tree "${SB24}/fakehome/Downloads" 3 wrong
printf '%s\tdownloads\tfalse\tfalse\ttrue\n' "${SB24}/fakehome/Downloads" | sb_scope "${SB24}"
RUN_OUT="$(
    cd "${SB24}" && HOME="${SB24}/fakehome" CONTAINER_RUNTIME="${NS_RUNTIME}" \
        OWNED_PATHS_FILE="${SB24}/config/owned_paths.yaml" \
        bash "${SB24}/scripts/ownership_repair.sh" \
            --scope "${SB24}/config/owned_paths.yaml" 2>&1
)"
RUN_RC=$?
if [[ "${RUN_RC}" -eq 0 ]] && [[ "$(wrong_owned_count "${SB24}/fakehome/Downloads")" -eq 0 ]]; then
    pass "fence boundary [golden-FALSE end-to-end]: a \$HOME-rooted download tree is walked and really repaired — the deny did not break the ordinary case"
else
    fail "fence boundary [golden-FALSE end-to-end]: exit ${RUN_RC}, $(wrong_owned_count "${SB24}/fakehome/Downloads") item(s) still wrongly owned — the container-storage deny broke a legitimate \$HOME-rooted root"
fi

finish
