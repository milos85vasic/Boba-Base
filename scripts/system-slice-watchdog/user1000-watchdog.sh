#!/usr/bin/env bash
# user1000-watchdog.sh — system-slice out-of-scope watchdog for user@1000.service
#
# Purpose:
#   Continuously monitors user@1000.service via journalctl. On detection of
#   a SIGKILL / cascade termination, captures full forensics IMMEDIATELY
#   (before scope teardown completes) to a durable path that SURVIVES the
#   kill because THIS script lives in system.slice, not user.slice.
#
# Why:
#   Every in-scope monitor (user timer, user cron, rootless container) dies
#   in the SAME cascade as user@1000. This script is the ONLY way to attribute
#   the SIGKILL initiator + surrounding state without lossy post-hoc journal
#   reconstruction after login.
#
# Constitution: §11.4.4 (four-layer), §11.4.108 (runtime-signature), §11.4.115
# (RED-first), §11.4.6 (never guess), §11.4.10 (no credentials in logs),
# §11.4.128 (recording layout), §11.4.201 (guard-asserts-real-condition),
# BOB-116/BOB-120/BOB-123 (forensic anchors — 4 incidents).
#
# Install: see scripts/system-slice-watchdog/install.sh — operator runs with su
# Runs as: root, in system.slice (NOT user@1000.service — survives its kill)

set -o errexit
set -o nounset
set -o pipefail

readonly WATCHDOG_VERSION="1.1.0"
# TARGET_UNIT is env-tunable so a scratch unit can be used for install-time
# drills (§11.4.108 layer-4 proof without touching user@1000 in production).
# Default remains user@1000.service (the incident target).
readonly TARGET_UNIT="${BOBA_WATCHDOG_TARGET:-user@1000.service}"
readonly EVIDENCE_ROOT="${BOBA_WATCHDOG_ROOT:-/var/log/boba-watchdog}"
readonly RETAIN_LAST_N="${BOBA_WATCHDOG_RETAIN:-20}"
readonly PRE_KILL_WINDOW_SEC="${BOBA_WATCHDOG_PRE_SEC:-60}"
readonly POST_KILL_WINDOW_SEC="${BOBA_WATCHDOG_POST_SEC:-15}"
# I1 fix: cooldown between captures. Same-incident cascade can trigger many
# lines within 1 second — without cooldown, retention rotates out the real
# incident.  60s default: no realistic recurrence of the class in <60s.
readonly CAPTURE_COOLDOWN_SEC="${BOBA_WATCHDOG_COOLDOWN_SEC:-60}"
LAST_CAPTURE_EPOCH=0

log() { printf '[watchdog %(%Y-%m-%dT%H:%M:%S%z)T] %s\n' -1 "$*"; }

# §11.4.201 pre-flight — assert real preconditions, refuse honestly if not met
preflight() {
    if [[ "$(id -u)" -ne 0 ]]; then
        log "ERROR §11.4.201: watchdog requires root (currently uid=$(id -u))"
        log "  Install via scripts/system-slice-watchdog/install.sh"
        return 1
    fi
    if ! command -v journalctl >/dev/null 2>&1; then
        log "ERROR §11.4.201: journalctl not on PATH — cannot monitor"
        return 1
    fi
    if ! command -v systemctl >/dev/null 2>&1; then
        log "ERROR §11.4.201: systemctl not on PATH — cannot verify unit"
        return 1
    fi
    # M2 fix: POSITIVE check (fail-closed) — a cgroup-namespaced context
    # (rootless container) has cgroup "/" or "0::/" and would pass a mere
    # negative check while ACTUALLY being under user.slice from the host's view.
    # Require explicit /system.slice/ in the path.
    local my_cgroup
    my_cgroup=$(awk -F: 'NR==1 {print $NF}' /proc/self/cgroup)
    if [[ "$my_cgroup" == *"/user.slice/"* ]]; then
        log "ERROR §11.4.201: watchdog is in user.slice ($my_cgroup) — would die"
        log "  with user@1000. MUST be installed via system.slice unit."
        return 1
    fi
    if [[ "$my_cgroup" != *"/system.slice/"* ]]; then
        log "ERROR §11.4.201: watchdog cgroup ($my_cgroup) is not under /system.slice/"
        log "  Fail-closed: refusing to run without positive system.slice proof."
        log "  Likely running in a cgroup-namespaced container which may still be"
        log "  under user.slice from host's view — install as native system unit."
        return 1
    fi
    log "preflight OK: uid=0, cgroup=$my_cgroup, target=$TARGET_UNIT"
    log "evidence_root=$EVIDENCE_ROOT retain_last=$RETAIN_LAST_N cooldown=${CAPTURE_COOLDOWN_SEC}s"
    return 0
}

# Rotate old evidence dirs to bound disk usage
rotate_evidence() {
    if [[ ! -d "$EVIDENCE_ROOT" ]]; then return 0; fi
    local count
    # List newest-first; skip the first RETAIN_LAST_N; remove the rest
    count=$(find "$EVIDENCE_ROOT" -mindepth 1 -maxdepth 1 -type d | wc -l)
    if [[ "$count" -le "$RETAIN_LAST_N" ]]; then return 0; fi
    # M6 fix: null-delimit path names so spaces don't split. -printf '%T@\t%p\0'
    # gives NUL-separated records; sort -z / read -d '' handle them safely.
    find "$EVIDENCE_ROOT" -mindepth 1 -maxdepth 1 -type d -printf '%T@\t%p\0' \
      | sort -zrn \
      | tail -zn +$((RETAIN_LAST_N + 1)) \
      | while IFS= read -r -d '' rec; do
          local path="${rec#*$'\t'}"
          log "rotating out: $path"
          rm -rf -- "$path"
        done
}

# Capture forensics on detected kill event
capture_forensics() {
    local kill_ts="$1"  # ISO-8601 or "now"
    local trigger_line="$2"
    local ts_dir_iso
    ts_dir_iso=$(date -u +'%Y-%m-%dT%H-%M-%SZ')
    local out_dir="$EVIDENCE_ROOT/$ts_dir_iso"
    mkdir -p "$out_dir"
    chmod 700 "$out_dir"

    log "KILL DETECTED — capturing to $out_dir"

    {
        echo "# boba user@1000 watchdog forensic capture"
        echo "# version: $WATCHDOG_VERSION"
        echo "# captured_at_iso: $ts_dir_iso"
        echo "# kill_ts_from_journal: $kill_ts"
        echo "# trigger_line: $trigger_line"
        echo "# host: $(hostname)"
        echo "# kernel: $(uname -a)"
        echo
        echo "## uptime + load"
        uptime
        echo
        echo "## last logins (milosvasic gap will be visible)"
        last milosvasic | head -10 2>&1 || true
        echo
        echo "## loginctl show-user milosvasic (Linger status)"
        loginctl show-user milosvasic 2>&1 | head -20 || true
        echo
        echo "## /proc/meminfo (RAM + swap at moment of kill)"
        head -20 /proc/meminfo
        echo
        echo "## PSI — memory + cpu + io"
        for f in memory cpu io; do
            echo "--- /proc/pressure/$f ---"
            cat "/proc/pressure/$f" 2>&1 || true
        done
        echo
        echo "## user.slice cgroup memory + pressure"
        for f in memory.current memory.high memory.max memory.peak memory.pressure \
                 pids.current pids.max cpu.pressure io.pressure; do
            local p="/sys/fs/cgroup/user.slice/user-1000.slice/$f"
            if [[ -r "$p" ]]; then
                printf '--- %s ---\n' "$p"
                cat "$p" 2>&1 || true
            fi
        done
        echo
        echo "## thread count for uid 1000"
        ps -L --no-headers -u 1000 | wc -l 2>&1 || true
    } > "$out_dir/state.log" 2>&1

    # Journal capture — before + after
    {
        echo "## journalctl pre-kill window (${PRE_KILL_WINDOW_SEC}s before)"
        journalctl --since "$PRE_KILL_WINDOW_SEC seconds ago" \
                   --until "now" 2>&1 | tail -500 || true
        echo
        echo "## journalctl PID=1 (systemd manager) user@1000 mentions"
        # M1 fix: PID=1 only sees systemd's own log lines. pam_tcb comes from
        # gdm-session-worker, session_close from audit, logind from logind's PID.
        # This filter previously produced a permanent §11.4.201(6) false-null.
        # Do PID=1 for user@1000 explicitly; use ALL sources for the PAM/logind hits.
        journalctl _PID=1 --since "$PRE_KILL_WINDOW_SEC seconds ago" 2>&1 \
          | grep -iE "user@1000" | tail -50 || true
        echo
        echo "## journalctl (all sources) PAM close + logind + gdm-session-worker"
        journalctl --since "$PRE_KILL_WINDOW_SEC seconds ago" 2>&1 \
          | grep -iE "pam_tcb|session_close|logind|gdm-session-worker|Removed session" \
          | tail -100 || true
    } > "$out_dir/journal-pre.log" 2>&1 &
    local journal_pid=$!

    # Process tree — snapshot BEFORE all children die
    {
        echo "## full process tree (immediate snapshot)"
        ps auxf 2>&1 || true
        echo
        echo "## top 20 by RSS"
        ps -eo pid,user,rss,cmd --sort=-rss --no-headers 2>&1 | head -20 || true
    } > "$out_dir/proctree.log" 2>&1

    # Kernel audit log for the kill (needs Path-1 audit rules installed)
    {
        echo "## audit log — logout_investigation key (loginctl/systemctl)"
        ausearch -k logout_investigation --start "recent" 2>&1 | tail -100 || \
            echo "(ausearch failed — audit rules may not be installed)"
        echo
        echo "## audit log — sigkill_investigation key"
        ausearch -k sigkill_investigation --start "recent" 2>&1 | tail -100 || true
    } > "$out_dir/audit.log" 2>&1

    # Wait briefly for journal capture (bounded)
    for _ in {1..30}; do
        if ! kill -0 "$journal_pid" 2>/dev/null; then break; fi
        sleep 0.1
    done

    # Post-kill window — captured AFTER 5s to see cascade fully
    sleep "$POST_KILL_WINDOW_SEC"
    journalctl --since "$PRE_KILL_WINDOW_SEC seconds ago" 2>&1 | tail -800 \
        > "$out_dir/journal-post.log" 2>&1 || true

    log "capture COMPLETE — $out_dir"
    ls -la "$out_dir" 2>&1 | while IFS= read -r l; do log "  $l"; done

    rotate_evidence
}

# Main event loop — journalctl -f + pattern match
main() {
    preflight || exit 2
    mkdir -p "$EVIDENCE_ROOT"
    chmod 700 "$EVIDENCE_ROOT"
    log "watchdog $WATCHDOG_VERSION started, tailing $TARGET_UNIT"

    # Follow the target unit's journal in real time.
    # I1 fix: the trigger MUST be anchored on "<TARGET_UNIT>: Main process exited"
    # specifically — journalctl -u user@1000.service also emits per-child scope
    # lines like "app-foo.scope: Main process exited, code=killed, status=9/KILL"
    # whenever any user-level app service dies. Matching bare "code=killed"
    # false-positives on those and floods the retention window with noise,
    # evicting real incident dirs (the artifact would defeat its own purpose).
    # We match on the exact "<TARGET_UNIT>: Main process exited" prefix.
    local -r trigger_prefix="$TARGET_UNIT: Main process exited"
    journalctl -f -o short-iso -u "$TARGET_UNIT" 2>&1 | \
    while IFS= read -r line; do
        if [[ "$line" == *"$trigger_prefix"* ]] && \
           [[ "$line" == *"status=9"* || "$line" == *"code=killed"* ]]; then
            # I1 fix: cooldown to dedup rapid-fire triggers of the same incident
            local now
            now=$(date +%s)
            if (( now - LAST_CAPTURE_EPOCH < CAPTURE_COOLDOWN_SEC )); then
                log "COOLDOWN: ignoring trigger within ${CAPTURE_COOLDOWN_SEC}s of previous capture"
                log "  (line: $line)"
                continue
            fi
            LAST_CAPTURE_EPOCH="$now"
            log "TRIGGER: $line"
            capture_forensics "$(echo "$line" | awk '{print $1,$2}')" "$line" &
            # keep tailing — we want next incident too
        fi
    done

    log "journalctl tail exited unexpectedly — watchdog stopping"
    exit 3
}

main "$@"
