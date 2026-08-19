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

readonly WATCHDOG_VERSION="1.0.0"
readonly TARGET_UNIT="user@1000.service"
readonly EVIDENCE_ROOT="${BOBA_WATCHDOG_ROOT:-/var/log/boba-watchdog}"
readonly RETAIN_LAST_N="${BOBA_WATCHDOG_RETAIN:-20}"
readonly PRE_KILL_WINDOW_SEC="${BOBA_WATCHDOG_PRE_SEC:-60}"
readonly POST_KILL_WINDOW_SEC="${BOBA_WATCHDOG_POST_SEC:-15}"

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
    # Assert we are in system.slice, NOT user.slice (the WHOLE POINT)
    local my_cgroup
    my_cgroup=$(awk -F: 'NR==1 {print $NF}' /proc/self/cgroup)
    if [[ "$my_cgroup" == *"/user.slice/"* ]]; then
        log "ERROR §11.4.201: watchdog is in user.slice ($my_cgroup) — would die"
        log "  with user@1000. MUST be installed via system.slice unit."
        return 1
    fi
    log "preflight OK: uid=0, cgroup=$my_cgroup, target=$TARGET_UNIT"
    log "evidence_root=$EVIDENCE_ROOT retain_last=$RETAIN_LAST_N"
    return 0
}

# Rotate old evidence dirs to bound disk usage
rotate_evidence() {
    if [[ ! -d "$EVIDENCE_ROOT" ]]; then return 0; fi
    local count
    # List newest-first; skip the first RETAIN_LAST_N; remove the rest
    count=$(find "$EVIDENCE_ROOT" -mindepth 1 -maxdepth 1 -type d | wc -l)
    if [[ "$count" -le "$RETAIN_LAST_N" ]]; then return 0; fi
    find "$EVIDENCE_ROOT" -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\n' \
      | sort -rn | tail -n +$((RETAIN_LAST_N + 1)) | awk '{print $2}' \
      | while IFS= read -r old; do
          log "rotating out: $old"
          rm -rf -- "$old"
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
        echo "## journalctl user@1000.service specifically"
        journalctl _PID=1 --since "$PRE_KILL_WINDOW_SEC seconds ago" 2>&1 \
          | grep -iE "user@1000|pam_tcb|session_close|logind" | tail -100 || true
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

    # Follow the target unit's journal in real time; on SIGKILL detection capture
    # journalctl -o short-iso ensures parseable timestamps
    journalctl -f -o short-iso -u "$TARGET_UNIT" 2>&1 | \
    while IFS= read -r line; do
        # The exact pattern we saw in ALL 4 incidents:
        #   user@1000.service: Main process exited, code=killed, status=9/KILL
        if [[ "$line" == *"Main process exited"*"status=9"* ]] || \
           [[ "$line" == *"code=killed"* ]]; then
            log "TRIGGER: $line"
            capture_forensics "$(echo "$line" | awk '{print $1,$2}')" "$line" &
            # keep tailing — we want next incident too
        fi
    done

    log "journalctl tail exited unexpectedly — watchdog stopping"
    exit 3
}

main "$@"
