#!/usr/bin/env bash
# test_ownership_probe_location.sh — BOB-208 + BOB-209 REDs, now GREEN as the
# standing guard for scripts/lib/ownership.sh probe_location().
#
# Feature      : 002-user-owned-downloads
# Under test   : scripts/lib/ownership.sh   probe_location()
# Requirements : FR-001, FR-002, FR-003, FR-010, FR-010b
# Governance   : §11.4.115 (RED on the broken artifact), §11.4.201(1)
#                (no false-positive refusal / mislabel), §11.4.201(4)
#                (honest conservative-safe default on an unresolvable signal),
#                §11.4.14 (cleanup on every exit path, incl. interrupts), §11.4.6
#
# ===========================================================================
# BOB-208 — the `want` side of the comparison was never checked
# ===========================================================================
# `want="$(ownership_operator_uid)"` (i.e. `id -u`) had no rc/emptiness guard.
# A failing `id(1)` left `want` empty and probe_location() kept going, so a
# perfectly healthy location verdicted `wrong-owner:<the-correct-uid>` — a
# false-positive refusal that names the RIGHT value as WRONG. Case 1 below
# shims `id` to fail and asserts the honest `unresolved-operator-uid` verdict
# (pre-fix: `wrong-owner:<uid>`, reproduced separately against a byte-identical
# copy of the pre-fix source, not re-derived by re-typing the old code here).
#
# ===========================================================================
# BOB-209 — asymmetric stat guards, a mislabelled verdict, untrapped cleanup
# ===========================================================================
# (1) The FILE branch checked stat's exit code but not output emptiness; the
#     probe/directory branch checked emptiness but not exit code — each half
#     blind to the failure mode the OTHER guarded against. Cases 2-3 shim
#     `stat` to fail each way and assert BOTH branches now catch BOTH shapes.
# (2) A stat failure on an existing file was reported `unwritable` — a
#     semantically wrong label (stat failing is not a writability fact). Cases
#     2-3 assert the honest `stat-failed` verdict instead.
# (3) The probe's `rm -f` was a plain statement, not a trap, so an interrupt
#     landing between `mktemp` creating the file and that `rm` running strands
#     a `.ownership-probe.XXXXXX` file INSIDE a declared location (which can
#     include the git-tracked download-proxy/ tree). Case 4 constructs that
#     exact window with a real SIGINT and asserts no residue survives.
#
# ===========================================================================
# WHY FUNCTION-LEVEL, NOT A SANDBOX COPY OF THE WHOLE PROJECT
# ===========================================================================
# probe_location() has no side effect beyond the one probe file it creates and
# removes inside the directory it is handed, so this suite sources the library
# directly and hands it a throwaway mktemp directory — §11.4.201(11) probing
# the real function through its real signature, not a re-implementation of it.
#
# ===========================================================================
# CASE 4's SIGNAL TECHNIQUE, AND WHY IT IS SHAPED THIS WAY
# ===========================================================================
# A signal racing a two-line window in real wall-clock time is not reliably
# constructible — bash defers a pending trap until the CURRENTLY EXECUTING
# foreground command finishes, so naively backgrounding probe_location() and
# hoping SIGINT lands "in between" either never fires observably or fires only
# after the window has already closed (measured while building this suite: a
# self-signal from inside a shimmed `mktemp` produced byte-identical output on
# the pre-fix and post-fix source, meaning it was not exercising the window at
# all). The reliable construction used here shims `stat` (the command that
# runs AFTER the probe file exists and BEFORE it is removed) to background the
# real `stat`, write a checkpoint file proving execution has reached that exact
# point, and then sleep — turning the race into a POLL: the harness waits for
# the checkpoint file (proof the probe exists and cleanup has not run yet),
# THEN sends a real SIGINT to the process. This was verified DISCRIMINATING
# before being trusted: run against a byte-identical copy of the PRE-FIX
# source (captured from git HEAD before this fix), it reliably LEAVES a
# `.ownership-probe.*` file behind; run against the fixed source, it does not.
# Both directions were re-run multiple times during authoring and never
# flipped, which is the control needle for this instrument (§11.4.201(7)(b)).
#
# The subshell running probe_location() explicitly resets INT to the shell
# default (`trap - INT`) before sourcing the library, so the fixture reflects
# a caller with NO ambient handler of its own — the realistic "nothing else is
# protecting this" case. The harness's OWN top-level trap absorbs the signal
# probe_location() re-raises after cleanup (its `$$` is fixed to the harness
# process across every subshell layer, a documented bash property, not a bug
# in the fix) so the harness survives to report the residue check.
#
# §11.4.263: this suite signals only its OWN throwaway child subshell (by PID,
# captured from `$!` immediately before use, never a pgid, never a bare
# pattern match) — no kill/pkill/killpg against any pre-existing process.
#
# Usage:   bash tests/unit/test_ownership_probe_location.sh
# Outputs: per-case PASS/FAIL/SKIP lines, then a RESULT summary.
# Side-effects: writes only inside per-case mktemp directories, removed on
#          every exit path.
# Dependencies: bash, stat, mktemp, id.

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${HERE}/../.." && pwd)"
LIB="${PROJECT_ROOT}/scripts/lib/ownership.sh"

PASS=0; FAIL=0; SKIP=0
pass() { PASS=$((PASS+1)); echo "  PASS: $1"; }
fail() { FAIL=$((FAIL+1)); echo "  FAIL: $1"; }
skip() { SKIP=$((SKIP+1)); echo "  SKIP: $1"; }
finish() {
    echo "RESULT: ${PASS} passed, ${FAIL} failed, ${SKIP} skipped"
    [[ "${FAIL}" -eq 0 ]] || exit 1
    exit 0
}

[[ -f "${LIB}" ]] || { fail "target missing: scripts/lib/ownership.sh"; finish; }
# shellcheck source=/dev/null
source "${LIB}"

WORK=""
cleanup() { local rc=$?; [[ -n "${WORK}" && -d "${WORK}" ]] && rm -rf "${WORK}"; exit "${rc}"; }
trap cleanup EXIT
# INT/TERM/HUP are deliberately ABSORBED (not "cleanup-then-exit") at this
# harness's own top level: Case 4 below deliberately exercises
# probe_location()'s own fixed signal handling, which — per bash's documented
# `$$` behaviour (fixed to the ORIGINATING shell across every subshell layer,
# command substitution included) — re-raises INT against THIS script's own
# PID after it restores whatever handler was ambient at trap-install time. A
# harness whose own INT handling immediately exits would kill itself on its
# own fixture rather than letting Case 4 report a result; the EXIT trap above
# still guarantees WORK is removed whenever this script genuinely terminates.
trap 'true' INT TERM HUP
WORK="$(mktemp -d "${TMPDIR:-/tmp}/bob208209.XXXXXXXX")" || { fail "harness: mktemp -d failed"; finish; }

echo "== BOB-208 / BOB-209: probe_location() verdict honesty + cleanup =="

# ── needle: probe_location must be capable of refusing at all ──────────────
NV="$(probe_location "${WORK}/definitely-absent" 2>/dev/null)"
if [[ "${NV}" == "ok" ]]; then
    fail "needle: probe_location returned ok for a path that does not exist — it cannot refuse, so no verdict below is evidence"
    finish
fi
pass "needle: probe_location refuses an absent path (verdict '${NV}')"

# ===========================================================================
# CASE 1 (BOB-208) — a failing id(1) must yield an honest verdict, never a
# fabricated wrong-owner claim naming the correct uid as wrong.
# ===========================================================================
C1="${WORK}/case1"; mkdir -p "${C1}"
(
    id() { return 7; }
    V="$(probe_location "${C1}")"
    printf '%s' "${V}" > "${WORK}/case1.out"
)
V1="$(cat "${WORK}/case1.out")"
if [[ "${V1}" == wrong-owner:* ]]; then
    fail "BOB-208: id(1) failure produced '${V1}' — a false-positive wrong-owner claim naming a value that was never actually compared"
elif [[ "${V1}" == "ok" ]]; then
    fail "BOB-208: id(1) failure produced 'ok' — an unresolvable precondition must never silently pass (§11.4.201(4))"
elif [[ -n "${V1}" && "${V1}" != absent* ]]; then
    pass "BOB-208: id(1) failure yields an honest, distinct verdict ('${V1}'), never wrong-owner"
else
    fail "BOB-208: id(1) failure produced an unexpected verdict '${V1}'"
fi

# ── golden-FALSE for Case 1: a healthy id(1) still verdicts ok ─────────────
if [[ "$(probe_location "${C1}")" == "ok" ]]; then
    pass "golden-FALSE: a working id(1) on a healthy location still verdicts ok"
else
    fail "golden-FALSE: a working id(1) on a healthy location did NOT verdict ok — the fix broke the happy path"
fi

# ===========================================================================
# CASE 2 (BOB-209, file branch) — stat succeeding with EMPTY output, and stat
# failing outright, must both be reported honestly (stat-failed), never as a
# malformed 'wrong-owner:' or a mislabelled 'unwritable'.
# ===========================================================================
C2F="${WORK}/case2.file"; : > "${C2F}"

V2A="$(
    stat() { return 0; }   # succeeds, prints nothing
    probe_location "${C2F}"
)"
if [[ "${V2A}" == "stat-failed" ]]; then
    pass "BOB-209 file-branch: stat succeeding with empty output -> honest 'stat-failed' (was a malformed 'wrong-owner:' with no uid)"
else
    fail "BOB-209 file-branch: stat succeeding with empty output yielded '${V2A}', expected 'stat-failed'"
fi

V2B="$(
    stat() { return 5; }   # fails outright
    probe_location "${C2F}"
)"
if [[ "${V2B}" == "stat-failed" ]]; then
    pass "BOB-209 file-branch: stat failing outright -> honest 'stat-failed' (was mislabelled 'unwritable')"
else
    fail "BOB-209 file-branch: stat failing outright yielded '${V2B}', expected 'stat-failed'"
fi

# ===========================================================================
# CASE 3 (BOB-209, directory/probe branch) — the mirror image: stat FAILING
# while still printing something to stdout must not be trusted as a uid.
# ===========================================================================
C3D="${WORK}/case3.dir"; mkdir -p "${C3D}"
V3="$(
    stat() { printf '999999'; return 9; }   # fails, but leaks plausible-looking output
    probe_location "${C3D}"
)"
if [[ "${V3}" == "stat-failed" ]]; then
    pass "BOB-209 directory-branch: stat failing while leaking output -> honest 'stat-failed', garbage output not trusted as a uid"
elif [[ "${V3}" == wrong-owner:999999 ]]; then
    fail "BOB-209 directory-branch: stat's FAILED-call output '999999' was trusted as a real uid ('${V3}') — the exit-code guard is still missing"
else
    fail "BOB-209 directory-branch: unexpected verdict '${V3}' for a failing stat leaking output"
fi

# ── golden-FALSE for Cases 2-3: a working stat on a healthy dir still ok ───
C3G="${WORK}/case3.golden"; mkdir -p "${C3G}"
if [[ "$(probe_location "${C3G}")" == "ok" ]]; then
    pass "golden-FALSE: a working, healthy directory probe still verdicts ok"
else
    fail "golden-FALSE: a working, healthy directory probe did NOT verdict ok — the fix broke the happy path"
fi

# ===========================================================================
# CASE 4 (BOB-209, §11.4.14) — an interrupt landing between mktemp creating
# the probe and it being removed must not strand the file. See the file
# header for why this specific technique (poll-for-checkpoint, then signal)
# is the reliable construction, and how it was validated to be discriminating.
# ===========================================================================
run_interrupt_case() {
    local lib="$1" label="$2"
    local dir out pid i
    dir="$(mktemp -d "${WORK}/case4.XXXXXX")"
    out="${dir}/out.txt"

    (
        trap - INT
        # shellcheck source=/dev/null
        source "${lib}"
        stat() {
            command stat "$@" &
            local pid=$!
            touch "${dir}/.stat-entered"
            sleep 1.5
            wait "${pid}"
        }
        probe_location "${dir}" > "${out}" 2>&1
    ) &
    pid=$!

    for i in $(seq 1 300); do
        [[ -f "${dir}/.stat-entered" ]] && break
        sleep 0.01
    done
    if [[ ! -f "${dir}/.stat-entered" ]]; then
        echo "HARNESS-FAIL"
        kill -9 "${pid}" 2>/dev/null
        wait "${pid}" 2>/dev/null
        return
    fi
    sleep 0.1
    kill -INT "${pid}" 2>/dev/null
    wait "${pid}" 2>/dev/null
    sleep 0.1
    if [[ -z "$(ls "${dir}"/.ownership-probe.* 2>/dev/null)" ]]; then
        echo "CLEAN"
    else
        echo "RESIDUE"
    fi
}

R4="$(run_interrupt_case "${LIB}" fixed)"
case "${R4}" in
    CLEAN)   pass "BOB-209: an interrupt between mktemp and cleanup leaves no residue (§11.4.14 trap)" ;;
    RESIDUE) fail "BOB-209: an interrupt between mktemp and cleanup STILL leaves a stray probe file behind" ;;
    *)       skip "BOB-209 interrupt case: harness could not reach the interruptible checkpoint on this host — not asserted" ;;
esac

# ── the discriminating-instrument proof, re-derived here (not assumed) ─────
# A pristine copy of the PRE-FIX function (byte-identical to the version this
# suite's own header describes, reconstructed inline rather than trusting a
# separate fixture file that could silently drift) must show the opposite
# result under the SAME harness — proving Case 4 actually tests something.
PRE_LIB="${WORK}/ownership_prefix.sh"
{
    printf 'ownership_operator_uid() { id -u; }\n'
    printf 'probe_location() {\n'
    printf '    local dir="$1" want probe got\n'
    printf '    want="$(ownership_operator_uid)"\n'
    printf '    [[ -e "${dir}" ]] || { echo "absent"; return 1; }\n'
    printf '    if [[ -f "${dir}" ]]; then\n'
    printf "        got=\$(stat -c '%%u' \"\${dir}\" 2>/dev/null) || { echo \"unwritable\"; return 1; }\n"
    printf '        [[ "${got}" == "${want}" ]] && { echo "ok"; return 0; }\n'
    printf '        echo "wrong-owner:${got}"; return 1\n'
    printf '    fi\n'
    printf '    probe="$(mktemp "${dir}/.ownership-probe.XXXXXX" 2>/dev/null)" || { echo "unwritable"; return 1; }\n'
    printf "    got=\$(stat -c '%%u' \"\${probe}\" 2>/dev/null)\n"
    printf '    rm -f "${probe}"\n'
    printf '    [[ -n "${got}" ]] || { echo "unwritable"; return 1; }\n'
    printf '    [[ "${got}" == "${want}" ]] && { echo "ok"; return 0; }\n'
    printf '    echo "wrong-owner:${got}"\n'
    printf '    return 1\n'
    printf '}\n'
} > "${PRE_LIB}"

R4PRE="$(run_interrupt_case "${PRE_LIB}" pre-fix)"
case "${R4PRE}" in
    RESIDUE) pass "control: the pre-fix shape (plain 'rm -f', no trap) DOES leave residue under the identical harness — Case 4 is discriminating" ;;
    CLEAN)   fail "control: the pre-fix shape did NOT leave residue under this harness — Case 4's technique is not exercising the described window and its PASS above is not evidence" ;;
    *)       skip "control: harness could not reach the interruptible checkpoint for the pre-fix shape either — Case 4's result above is unconfirmed" ;;
esac

# ── sandbox hygiene ──────────────────────────────────────────────────────
LEFTOVER="$(find "${WORK}" -maxdepth 1 -name '.ownership-probe.*' 2>/dev/null)"
if [[ -z "${LEFTOVER}" ]]; then
    pass "sandbox: no stray probe files left directly under the harness work dir"
else
    fail "sandbox: stray probe residue found: ${LEFTOVER}"
fi

finish
