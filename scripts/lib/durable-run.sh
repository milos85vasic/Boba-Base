#!/usr/bin/env bash
# scripts/lib/durable-run.sh — DURABLE remote-execution helper (BOB-064).
#
# ─── PURPOSE ──────────────────────────────────────────────────────────
# Source this from any Boba script that must launch a long-running job
# that SURVIVES the SSH / login session ending. Ported from Lava P1
# (constitution §5 durable remote execution) — see docs/PORTING-FROM-LAVA.md.
#
# ─── WHY ──────────────────────────────────────────────────────────────
# A remote host's systemd-logind reaps ALL of a user's processes when
# its last session closes (KillUserProcesses=yes on many hosts).
# tmux / nohup / setsid ALL live in the login session's session-<n>.scope
# cgroup and die with it. The fix is to run the job as its OWN transient
# user .service unit, owned by the user systemd manager with linger
# enabled — so it outlives the session.
#
# ─── USAGE ────────────────────────────────────────────────────────────
#   source scripts/lib/durable-run.sh
#   durable_launch_cmd     my-long-run 'bash long-runner.sh'
#   durable_wait_sentinel  my-long-run 3600          # blocks; echoes rc
#   durable_fetch_log      my-long-run                # cat captured log
#   durable_stop           my-long-run                # stop + reap
#
# ─── API ──────────────────────────────────────────────────────────────
#   durable_launch        <unit> <script_path>   # launch a runner script
#   durable_launch_cmd    <unit> <command...>    # launch an inline command
#   durable_is_active     <unit>                 # exit 0 iff unit is active
#   durable_main_pid      <unit>                 # echo MainPID (0 if none)
#   durable_wait_sentinel <unit> [timeout_s]     # block; echo exit code
#   durable_fetch_log     <unit>                 # cat captured stdout+err
#   durable_stop          <unit>                 # stop + reap + rm artifacts
#
# ─── INPUTS / OUTPUTS / SIDE-EFFECTS (§11.4.18) ───────────────────────
#   INPUTS       : DURABLE_DIR (env, default $XDG_CACHE_HOME/remoteexec
#                  or ~/.cache/remoteexec); XDG_RUNTIME_DIR auto-derived
#                  from `id -u` if unset.
#   OUTPUTS      : per-unit artifacts under $DURABLE_DIR:
#                    <unit>.runner.sh   — the wrapper the .service exec's
#                    <unit>.log         — combined stdout+stderr capture
#                    <unit>.COMPLETE    — sentinel; contains runner rc
#   SIDE-EFFECTS : loginctl enable-linger for the current user (idempotent,
#                  requires root ONCE per user — see "FIRST-BOOT" below);
#                  creates a transient user .service unit named <unit>.
#
# ─── DEPENDENCIES ─────────────────────────────────────────────────────
#   bash, systemctl (--user), systemd-run (--user), loginctl, awk, cat,
#   sleep, mkdir. Requires a running systemd --user manager: if
#   `systemctl --user is-system-running` is neither `running` nor
#   `degraded`, the helper cannot deliver durability — callers should
#   detect this and SKIP-with-reason (§11.4.3) rather than proceed.
#
# ─── FIRST-BOOT / SUDO-FREE (§11.4.234) ───────────────────────────────
# `loginctl enable-linger` normally requires root, ONCE per user. The
# helper attempts it unconditionally (`|| true`), so a non-root call is
# harmless on a host that already has linger enabled — but on a first-
# boot host without linger, the launched unit will still die with the
# session. Operators MUST run `sudo loginctl enable-linger $USER` ONCE
# per host to activate durability. The helper NEVER auto-sudo's
# (§11.4.161 rootless + §11.4.234 always-unblocked — no interactive
# prompts, no silent escalation).
#
# ─── ANTI-TAIL-BUFFER (§11.4.6) ───────────────────────────────────────
# NEVER pipe the long command through `tail -N` — pipes buffer until
# the writer exits, so a caller watching `tail -f` on the runner's
# stdout would see nothing until completion. The runner ALWAYS redirects
# to <unit>.log, which callers read independently via durable_fetch_log.
#
# ─── CROSS-REFERENCES ─────────────────────────────────────────────────
#   Ported from  : ../lava/submodules/containers/scripts/lib/durable-run.sh
#   Docs         : docs/scripts/durable-run.md (user guide)
#   Challenge    : challenges/scripts/durable_run_helper_challenge.sh
#   Constitution : §11.4.6, §11.4.18, §11.4.35, §11.4.115, §11.4.161,
#                  §11.4.201, §11.4.234
#   Item         : BOB-064 (docs/workable_items.db)
# ──────────────────────────────────────────────────────────────────────

# Resolve artifact dir + the user runtime dir up front (no hardcoded uid/home).
: "${DURABLE_DIR:=${XDG_CACHE_HOME:-$HOME/.cache}/remoteexec}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"

_durable_paths() {
    # $1 = unit (with or without .service); sets _D_RUNNER/_D_LOG/_D_SENTINEL/_D_UNIT
    local u="${1%.service}"
    _D_UNIT="${u}.service"
    _D_RUNNER="${DURABLE_DIR}/${u}.runner.sh"
    _D_LOG="${DURABLE_DIR}/${u}.log"
    _D_SENTINEL="${DURABLE_DIR}/${u}.COMPLETE"
}

# Write the wrapper runner script for an arbitrary body, capturing combined
# output to the log and ALWAYS recording the exit code in the sentinel.
_durable_write_runner() {
    local body="$1"
    mkdir -p "${DURABLE_DIR}"
    cat >"${_D_RUNNER}" <<EOF
#!/usr/bin/env bash
set -uo pipefail
__log=${_D_LOG@Q}
__sentinel=${_D_SENTINEL@Q}
{
${body}
} >"\$__log" 2>&1
__rc=\$?
printf '%s\n' "\$__rc" > "\$__sentinel"
exit \$__rc
EOF
    chmod 0755 "${_D_RUNNER}"
}

# durable_launch <unit> <script_path>
durable_launch() {
    local unit="$1" script_path="$2"
    _durable_paths "$unit"
    _durable_write_runner "bash ${script_path@Q}"
    _durable_start "${unit%.service}"
}

# durable_launch_cmd <unit> <command...>
durable_launch_cmd() {
    local unit="$1"; shift
    _durable_paths "$unit"
    _durable_write_runner "$*"
    _durable_start "${unit%.service}"
}

# _durable_start <unit-bare> — linger + systemd-run --user (the durability core).
_durable_start() {
    local bare="$1"
    loginctl enable-linger >/dev/null 2>&1 || true
    systemctl --user reset-failed "${bare}.service" >/dev/null 2>&1 || true
    systemd-run --user --unit="${bare}" --collect bash "${_D_RUNNER}"
}

durable_is_active() {
    _durable_paths "$1"
    [ "$(systemctl --user is-active "${_D_UNIT}" 2>/dev/null)" = "active" ]
}

durable_main_pid() {
    _durable_paths "$1"
    local pid
    pid="$(systemctl --user show -p MainPID --value "${_D_UNIT}" 2>/dev/null)"
    printf '%s\n' "${pid:-0}"
}

# durable_wait_sentinel <unit> [timeout_s]  — echoes the recorded exit code.
durable_wait_sentinel() {
    _durable_paths "$1"
    local timeout="${2:-0}" waited=0
    while :; do
        if [ -f "${_D_SENTINEL}" ]; then
            cat "${_D_SENTINEL}"
            return 0
        fi
        if [ "$timeout" -gt 0 ] && [ "$waited" -ge "$timeout" ]; then
            echo "durable_wait_sentinel: ${_D_SENTINEL} did not appear within ${timeout}s" >&2
            return 1
        fi
        sleep 1
        waited=$((waited + 1))
    done
}

durable_fetch_log() {
    _durable_paths "$1"
    cat "${_D_LOG}" 2>/dev/null
}

durable_stop() {
    _durable_paths "$1"
    systemctl --user stop "${_D_UNIT}" >/dev/null 2>&1 || true
    systemctl --user reset-failed "${_D_UNIT}" >/dev/null 2>&1 || true
    rm -f "${_D_RUNNER}" "${_D_LOG}" "${_D_SENTINEL}" >/dev/null 2>&1 || true
}

# ─── FIRST-BOOT LINGER HINT (§11.4.234 always-unblocked) ──────────────
# Print a one-line reminder if linger is NOT enabled for the current
# user AND we can detect it deterministically. NEVER interactive, NEVER
# blocking — the helper functions still work (systemd-run --user
# succeeds regardless), but the .service unit will not survive the
# session's last logout without linger.
if command -v loginctl >/dev/null 2>&1; then
    _linger_state="$(loginctl show-user "$(id -un)" -p Linger --value 2>/dev/null || echo 'unknown')"
    if [ "$_linger_state" = "no" ]; then
        echo "durable-run.sh NOTE: linger DISABLED for user '$(id -un)'." >&2
        echo "  Units survive across sessions ONLY with linger enabled. Enable once:" >&2
        echo "    sudo loginctl enable-linger $(id -un)" >&2
    fi
    unset _linger_state
fi
