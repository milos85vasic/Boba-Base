#!/usr/bin/env bash
# flight-recorder.sh — continuous, out-of-scope host-session flight recorder
#
# Purpose:
#   Append one structured (JSONL) sample per tick describing the health of the
#   operator's user session, so that if `user@1000.service` is torn down again
#   (the forced-logout class: BOB-116 / BOB-120 / BOB-123 / BOB-124 / BOB-125 /
#   BOB-126) the aftermath is diagnosable by reading ONE file instead of being
#   reconstructed from journalctl over hours.
#
#   It is a RECORDER, not a controller. It observes and writes. It NEVER sends
#   a signal to any process, never kills, never restarts, never touches host
#   power state (CONST-033). There is deliberately no code path in this file
#   that can terminate anything.
#
# Usage:
#   flight-recorder.sh tick      # take one sample, append it, exit (cron entry)
#   flight-recorder.sh report    # one-step post-incident diagnosis of the log
#   flight-recorder.sh status    # short human summary of recorder health
#   flight-recorder.sh verify    # self-check: preconditions + durability
#
# Inputs (all read-only):
#   /proc/uptime, /proc/meminfo, /proc/loadavg, /proc/pressure/*,
#   /proc/sys/kernel/random/boot_id,
#   /sys/fs/cgroup/.../<target unit>/{pids,memory}.*,
#   `systemctl show <target unit>`, `journalctl` (kernel + target unit).
#
# Outputs (the only things it writes — all under $BOBA_FR_DIR):
#   journal.jsonl    append-only sample history (rotated, size-bounded)
#   journal.jsonl.1  previous rotation generation
#   latest.json      last sample, replaced atomically (temp -> fsync -> rename)
#   state.env        tick-to-tick continuity (prev epoch / cursor / unit start)
#
# Side effects:
#   None outside $BOBA_FR_DIR. No signals. No process control. No network.
#
# Dependencies:
#   bash 4+, coreutils (stat/date/sync/mktemp), systemctl, journalctl, awk, sed.
#   `journalctl` absence degrades to an honest null, never a false zero.
#
# Environment:
#   BOBA_FR_DIR       state dir (default $XDG_STATE_HOME/boba-flight-recorder)
#   BOBA_FR_TARGET    unit to watch (default user@1000.service)
#   BOBA_FR_SCOPE     systemd manager owning it: system (default) | user.
#                     "user" is for drilling the teardown-detection path against
#                     a disposable unit — never needed for the production target.
#   BOBA_FR_TICK_SEC  expected seconds between ticks (default 60)
#   BOBA_FR_MAX_BYTES rotate journal.jsonl above this size (default 8388608)
#   BOBA_FR_TIMEOUT   per-external-command timeout seconds (default 15)
#
# Cross-references:
#   scripts/flight-recorder/install.sh   — installs the cron tick
#   scripts/flight-recorder/uninstall.sh — removes it
#   docs/scripts/flight-recorder.md      — §11.4.18 companion
#   docs/guides/forced-logout-flight-recorder.md — operator guide
#   scripts/system-slice-watchdog/       — the root/system.slice deep-forensics
#                                          watchdog this recorder complements
#
# Constitution: §11.4.6 (never guess — an unreadable source records null, not
#   zero), §11.4.128 (always-on recording, non-invasive, durable layout),
#   §11.4.201 (guards assert the REAL condition; refuse honestly), §11.4.249
#   (flight recorder), §11.4.252 (fail closed on unverifiable preconditions),
#   §11.4.263 (never signal — satisfied by construction: no signal is sent),
#   CONST-033 (host power management: observed, never acted upon).

set -o errexit
set -o nounset
set -o pipefail

readonly RECORDER_VERSION="1.0.0"
readonly SCHEMA_VERSION="1"

STATE_DIR="${BOBA_FR_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/boba-flight-recorder}"
readonly STATE_DIR
readonly JOURNAL_FILE="$STATE_DIR/journal.jsonl"
readonly ROTATED_FILE="$STATE_DIR/journal.jsonl.1"
readonly LATEST_FILE="$STATE_DIR/latest.json"
readonly STATE_FILE="$STATE_DIR/state.env"

readonly TARGET_UNIT="${BOBA_FR_TARGET:-user@1000.service}"
# Which systemd manager owns the target. The production target
# (user@1000.service) is a SYSTEM unit — it is the per-user manager, started by
# PID 1 — so "system" is the default. "user" exists so the teardown-detection
# path can be drilled against a disposable `systemctl --user` unit without ever
# restarting the production one (§11.4.108 layer-4 drill; the same reason the
# system-slice watchdog exposes BOBA_WATCHDOG_TARGET).
readonly SCOPE="${BOBA_FR_SCOPE:-system}"
readonly TICK_SEC="${BOBA_FR_TICK_SEC:-60}"
readonly MAX_BYTES="${BOBA_FR_MAX_BYTES:-8388608}"
readonly CMD_TIMEOUT="${BOBA_FR_TIMEOUT:-15}"

# A gap is "anomalous" once at least two expected ticks were missed. A single
# late tick is normal scheduler jitter and must not raise a false positive
# (§11.4.201(1) — a false alarm is as much a defect as a missed one).
readonly GAP_ANOMALY_SEC=$(( TICK_SEC * 5 / 2 ))

log() { printf '[flight-recorder] %s\n' "$*" >&2; }
die() { log "ERROR: $*"; exit 1; }

# systemctl invocation for the configured scope. Read-only queries only — this
# wrapper is never used to start, stop, restart, or kill anything.
sysctl_show() {
    if [[ "$SCOPE" == "user" ]]; then
        timeout "$CMD_TIMEOUT" systemctl --user show "$@" 2>/dev/null || true
    else
        timeout "$CMD_TIMEOUT" systemctl show "$@" 2>/dev/null || true
    fi
}

# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

# Escape a value for embedding in a JSON string. Values captured here are
# machine fields (states, cgroup paths, timestamps), but escaping is applied
# unconditionally rather than assuming they are clean.
json_str() {
    local s="${1-}"
    s="${s//\\/\\\\}"
    s="${s//\"/\\\"}"
    s="${s//$'\t'/\\t}"
    s="${s//$'\r'/\\r}"
    s="${s//$'\n'/\\n}"
    printf '"%s"' "$s"
}

# Emit a bare number if the argument is a non-negative integer/decimal,
# otherwise the JSON literal null. This is the §11.4.6 boundary: a source we
# could not read becomes null (unknown), NEVER 0 (a measured absence).
json_num() {
    local v="${1-}"
    if [[ "$v" =~ ^[0-9]+(\.[0-9]+)?$ ]]; then
        printf '%s' "$v"
    else
        printf 'null'
    fi
}

json_bool() { [[ "${1-}" == "true" ]] && printf 'true' || printf 'false'; }

# Read the first line of a file, or empty string if unreadable. Never fails the
# script — an unreadable source must degrade to null, not abort the tick.
read_line() {
    local f="$1"
    [[ -r "$f" ]] || return 0
    head -n 1 "$f" 2>/dev/null || true
}

# ---------------------------------------------------------------------------
# preflight (§11.4.201 / §11.4.252 — assert the REAL condition, fail closed)
# ---------------------------------------------------------------------------

# The recorder's whole value proposition is that its output survives the event
# it records. Recording onto tmpfs would silently destroy exactly the evidence
# the operator needs, so an ephemeral filesystem is a hard refusal, not a warn.
assert_durable_dir() {
    local dir="$1" fstype
    fstype="$(stat -f -c %T "$dir" 2>/dev/null || echo unknown)"
    case "$fstype" in
        tmpfs|ramfs)
            die "state dir '$dir' is on $fstype (ephemeral). Refusing: the record" \
                "would vanish in exactly the event it exists to document." ;;
        unknown)
            # Fail closed: we could not establish durability, so we do not claim it.
            die "cannot determine filesystem type of '$dir' — refusing rather than" \
                "assuming durability (§11.4.6)." ;;
    esac
    printf '%s' "$fstype"
}

preflight() {
    mkdir -p "$STATE_DIR" 2>/dev/null || die "cannot create state dir '$STATE_DIR'"
    [[ -w "$STATE_DIR" ]] || die "state dir '$STATE_DIR' is not writable"
    chmod 700 "$STATE_DIR" 2>/dev/null || true
    assert_durable_dir "$STATE_DIR" >/dev/null
}

# ---------------------------------------------------------------------------
# sample collection
# ---------------------------------------------------------------------------

# Locate the target unit's cgroup directory. Derived from systemctl's own
# ControlGroup property rather than assembled from a guessed path, so a
# differently-sliced host does not silently produce nulls (§11.4.111 — resolve
# by reported identity, never by an assumed layout).
resolve_cgroup_dir() {
    local cg
    cg="$(sysctl_show "$TARGET_UNIT" -p ControlGroup --value)"
    [[ -n "$cg" && "$cg" != "/" ]] || return 0
    printf '/sys/fs/cgroup%s' "$cg"
}

collect_and_emit() {
    local epoch ts_utc boot_id uptime_sec host
    epoch="$(date -u +%s)"
    ts_utc="$(date -u -d "@$epoch" +%Y-%m-%dT%H:%M:%SZ)"
    boot_id="$(read_line /proc/sys/kernel/random/boot_id)"
    uptime_sec="$(awk '{print $1}' /proc/uptime 2>/dev/null || true)"
    host="$(cat /proc/sys/kernel/hostname 2>/dev/null || echo unknown)"

    # ---- previous-tick continuity -------------------------------------------
    local prev_epoch="" prev_start_nz="" prev_boot="" prev_cursor="" prev_active=""
    if [[ -r "$STATE_FILE" ]]; then
        # shellcheck disable=SC1090
        . "$STATE_FILE" 2>/dev/null || true
        prev_epoch="${FR_PREV_EPOCH:-}"
        # Last NON-ZERO start timestamp, not merely the last one. A stopped unit
        # reports 0, so carrying the last live value across the dead window is
        # what lets tick N+2 still see "this is a different instance than the one
        # running at tick N" after an intervening tick saw the unit down.
        prev_start_nz="${FR_PREV_UNIT_START_NZ:-}"
        prev_boot="${FR_PREV_BOOT_ID:-}"
        prev_cursor="${FR_PREV_CURSOR:-}"
        prev_active="${FR_PREV_UNIT_ACTIVE:-}"
    fi

    local gap_sec="" gap_anomaly="false"
    if [[ "$prev_epoch" =~ ^[0-9]+$ ]]; then
        gap_sec=$(( epoch - prev_epoch ))
        (( gap_sec > GAP_ANOMALY_SEC )) && gap_anomaly="true"
    fi

    local boot_changed="false"
    [[ -n "$prev_boot" && -n "$boot_id" && "$prev_boot" != "$boot_id" ]] && boot_changed="true"

    # ---- target unit state ---------------------------------------------------
    local u_active="" u_sub="" u_start="" u_nrestarts=""
    local show_out
    show_out="$(sysctl_show "$TARGET_UNIT" \
        -p ActiveState -p SubState -p ExecMainStartTimestampMonotonic -p NRestarts)"
    if [[ -n "$show_out" ]]; then
        u_active="$(sed -n 's/^ActiveState=//p' <<<"$show_out")"
        u_sub="$(sed -n 's/^SubState=//p' <<<"$show_out")"
        u_start="$(sed -n 's/^ExecMainStartTimestampMonotonic=//p' <<<"$show_out")"
        u_nrestarts="$(sed -n 's/^NRestarts=//p' <<<"$show_out")"
    fi

    # The load-bearing fingerprint of the forced-logout class: the user manager's
    # start timestamp changed between two consecutive ticks while the boot id did
    # NOT. That is a session teardown, and it is distinguishable from a reboot
    # (boot id changes) and from a suspend (kernel suspend records appear).
    local unit_restarted="false" unit_down="false"
    if [[ -n "$prev_start_nz" && -n "$u_start" && "$u_start" != "0" \
          && "$prev_start_nz" != "$u_start" ]]; then
        unit_restarted="true"
    fi
    # Distinct signal: the unit is NOT running now but was running at the
    # previous tick. Counting this as a "restart" would inflate the incident
    # count — a teardown and the re-creation that follows it are one event, and
    # reporting them as two is a §11.4.201(1) false positive.
    if [[ "$prev_active" == "active" && -n "$u_active" && "$u_active" != "active" ]]; then
        unit_down="true"
    fi

    local start_nz="$prev_start_nz"
    [[ -n "$u_start" && "$u_start" != "0" ]] && start_nz="$u_start"

    # ---- cgroup attribution --------------------------------------------------
    local cg_dir pids_cur="" pids_peak="" mem_cur="" mem_peak=""
    cg_dir="$(resolve_cgroup_dir)"
    if [[ -n "$cg_dir" && -d "$cg_dir" ]]; then
        # pids.current / memory.current in cgroup v2 are recursive over the
        # subtree, which is what we want: a collapse of this number is the
        # cascade-kill fingerprint.
        pids_cur="$(read_line "$cg_dir/pids.current")"
        pids_peak="$(read_line "$cg_dir/pids.peak")"
        mem_cur="$(read_line "$cg_dir/memory.current")"
        mem_peak="$(read_line "$cg_dir/memory.peak")"
    fi

    # ---- host resource axes --------------------------------------------------
    local mem_total mem_avail swap_free load1 threads
    mem_total="$(awk '/^MemTotal:/{print $2}' /proc/meminfo 2>/dev/null || true)"
    mem_avail="$(awk '/^MemAvailable:/{print $2}' /proc/meminfo 2>/dev/null || true)"
    swap_free="$(awk '/^SwapFree:/{print $2}' /proc/meminfo 2>/dev/null || true)"
    load1="$(awk '{print $1}' /proc/loadavg 2>/dev/null || true)"
    # §12.12 thread-exhaustion axis — orthogonal to memory, and the axis behind
    # the 2026-07-07 incident.
    threads="$(ps -L -u "$(id -u)" --no-headers 2>/dev/null | wc -l || true)"

    local psi_mem_some psi_mem_full psi_cpu_some psi_io_some
    psi_mem_some="$(sed -n 's/^some avg10=\([0-9.]*\).*/\1/p' /proc/pressure/memory 2>/dev/null | head -1 || true)"
    psi_mem_full="$(sed -n 's/^full avg10=\([0-9.]*\).*/\1/p' /proc/pressure/memory 2>/dev/null | head -1 || true)"
    psi_cpu_some="$(sed -n 's/^some avg10=\([0-9.]*\).*/\1/p' /proc/pressure/cpu 2>/dev/null | head -1 || true)"
    psi_io_some="$(sed -n 's/^some avg10=\([0-9.]*\).*/\1/p' /proc/pressure/io 2>/dev/null | head -1 || true)"

    # ---- kernel/journal triage signals since the previous tick ---------------
    # This is the CONST-033 triage protocol, sampled continuously instead of
    # reconstructed after the fact: suspend records, OOM records WITH cgroup
    # attribution (libpod-* = a container hit its own limit; user@1000.service =
    # a user-slice OOM perceived as a logout), and the unit-kill signature.
    local journal_ok="false" cursor="$prev_cursor"
    local k_suspend="" k_oom="" k_unit_kill="" oom_cgroups=""
    if command -v journalctl >/dev/null 2>&1; then
        local jargs=()
        if [[ -n "$prev_cursor" ]]; then
            jargs=(--after-cursor="$prev_cursor")
        else
            jargs=(--since "-${TICK_SEC} seconds")
        fi
        local jout
        # `|| true` because journalctl exits non-zero when the window is empty;
        # an empty window is a valid observation, not an error.
        jout="$(timeout "$CMD_TIMEOUT" journalctl "${jargs[@]}" --no-pager -q -o short-iso 2>/dev/null || true)"
        local newcur
        newcur="$(timeout "$CMD_TIMEOUT" journalctl -n 1 --no-pager -q --show-cursor 2>/dev/null \
            | sed -n 's/^-- cursor: //p' || true)"
        if [[ -n "$newcur" ]]; then
            journal_ok="true"
            cursor="$newcur"
            k_suspend="$(grep -icE 'PM: suspend entry|Freezing user space|will suspend|systemd-suspend' <<<"$jout" || true)"
            k_oom="$(grep -icE 'oom-kill|Killed process|Out of memory' <<<"$jout" || true)"
            k_unit_kill="$(grep -cE "${TARGET_UNIT}: Main process exited, code=killed" <<<"$jout" || true)"
            # Attribution: which cgroup actually hit its limit.
            oom_cgroups="$(grep -oE 'oom_memcg=[^ ,]+' <<<"$jout" | sed 's/^oom_memcg=//' \
                | sort -u | paste -sd';' - || true)"
        fi
    fi

    # ---- build the record ----------------------------------------------------
    local rec
    rec="{"
    rec+="\"schema\":$SCHEMA_VERSION"
    rec+=",\"v\":$(json_str "$RECORDER_VERSION")"
    rec+=",\"ts_utc\":$(json_str "$ts_utc")"
    rec+=",\"epoch\":$(json_num "$epoch")"
    rec+=",\"host\":$(json_str "$host")"
    rec+=",\"boot_id\":$(json_str "$boot_id")"
    rec+=",\"boot_changed\":$(json_bool "$boot_changed")"
    rec+=",\"uptime_sec\":$(json_num "$uptime_sec")"
    rec+=",\"gap_sec\":$(json_num "$gap_sec")"
    rec+=",\"gap_anomaly\":$(json_bool "$gap_anomaly")"
    rec+=",\"unit\":$(json_str "$TARGET_UNIT")"
    rec+=",\"scope\":$(json_str "$SCOPE")"
    rec+=",\"unit_active\":$(json_str "$u_active")"
    rec+=",\"unit_sub\":$(json_str "$u_sub")"
    rec+=",\"unit_start_mono\":$(json_num "$u_start")"
    rec+=",\"unit_nrestarts\":$(json_num "$u_nrestarts")"
    rec+=",\"unit_restarted\":$(json_bool "$unit_restarted")"
    rec+=",\"unit_down\":$(json_bool "$unit_down")"
    rec+=",\"unit_pids\":$(json_num "$pids_cur")"
    rec+=",\"unit_pids_peak\":$(json_num "$pids_peak")"
    rec+=",\"unit_mem_bytes\":$(json_num "$mem_cur")"
    rec+=",\"unit_mem_peak_bytes\":$(json_num "$mem_peak")"
    rec+=",\"mem_total_kb\":$(json_num "$mem_total")"
    rec+=",\"mem_avail_kb\":$(json_num "$mem_avail")"
    rec+=",\"swap_free_kb\":$(json_num "$swap_free")"
    rec+=",\"psi_mem_some10\":$(json_num "$psi_mem_some")"
    rec+=",\"psi_mem_full10\":$(json_num "$psi_mem_full")"
    rec+=",\"psi_cpu_some10\":$(json_num "$psi_cpu_some")"
    rec+=",\"psi_io_some10\":$(json_num "$psi_io_some")"
    rec+=",\"load1\":$(json_num "$load1")"
    rec+=",\"threads_self_uid\":$(json_num "$threads")"
    rec+=",\"journal_ok\":$(json_bool "$journal_ok")"
    rec+=",\"k_suspend\":$(json_num "$k_suspend")"
    rec+=",\"k_oom\":$(json_num "$k_oom")"
    rec+=",\"k_unit_kill\":$(json_num "$k_unit_kill")"
    rec+=",\"oom_cgroups\":$(json_str "$oom_cgroups")"
    rec+="}"

    rotate_if_needed
    # Single append in one write, then flush to stable storage. The record is
    # small and built entirely in memory first, so a torn tail is limited to a
    # crash mid-write of one line — which `latest.json` below then covers.
    printf '%s\n' "$rec" >>"$JOURNAL_FILE"
    sync -d "$JOURNAL_FILE" 2>/dev/null || sync 2>/dev/null || true

    # latest.json is the always-consistent view: temp -> fsync -> rename, so a
    # reader after an abrupt teardown always sees a whole record.
    local tmp
    tmp="$(mktemp "$STATE_DIR/.latest.XXXXXX")"
    printf '%s\n' "$rec" >"$tmp"
    sync -d "$tmp" 2>/dev/null || true
    mv -f "$tmp" "$LATEST_FILE"
    sync -d "$STATE_DIR" 2>/dev/null || true

    # Continuity state, also written atomically.
    local stmp
    stmp="$(mktemp "$STATE_DIR/.state.XXXXXX")"
    {
        printf 'FR_PREV_EPOCH=%s\n' "$epoch"
        printf 'FR_PREV_UNIT_START_NZ=%s\n' "$start_nz"
        printf 'FR_PREV_UNIT_ACTIVE=%s\n' "$u_active"
        printf 'FR_PREV_BOOT_ID=%s\n' "$boot_id"
        printf 'FR_PREV_CURSOR=%s\n' "$cursor"
    } >"$stmp"
    sync -d "$stmp" 2>/dev/null || true
    mv -f "$stmp" "$STATE_FILE"

    printf '%s\n' "$rec"
}

# Bounded disk by construction: one previous generation is retained, so the
# recorder can never grow past ~2 x MAX_BYTES no matter how long it runs.
rotate_if_needed() {
    [[ -f "$JOURNAL_FILE" ]] || return 0
    local size
    size="$(stat -c %s "$JOURNAL_FILE" 2>/dev/null || echo 0)"
    if (( size > MAX_BYTES )); then
        mv -f "$JOURNAL_FILE" "$ROTATED_FILE"
        log "rotated journal at ${size} bytes -> $(basename "$ROTATED_FILE")"
    fi
}

# ---------------------------------------------------------------------------
# report — the "one step" the whole recorder exists to make possible
# ---------------------------------------------------------------------------

report() {
    local files=()
    [[ -f "$ROTATED_FILE" ]] && files+=("$ROTATED_FILE")
    [[ -f "$JOURNAL_FILE" ]] && files+=("$JOURNAL_FILE")
    if (( ${#files[@]} == 0 )); then
        echo "No flight-recorder journal found at $STATE_DIR."
        echo "Nothing has been recorded yet — install the tick with:"
        echo "    scripts/flight-recorder/install.sh"
        return 0
    fi

    cat "${files[@]}" | awk '
    function field(line, key,   re, m) {
        re = "\"" key "\":"
        if (match(line, re "[^,}]*")) {
            m = substr(line, RSTART + length(re), RLENGTH - length(re))
            gsub(/^"|"$/, "", m)
            return m
        }
        return ""
    }
    {
        n++
        ts = field($0, "ts_utc")
        if (first == "") first = ts
        last = ts
        if (field($0, "gap_anomaly") == "true") {
            gaps[++g] = ts " (gap " field($0, "gap_sec") "s)"
        }
        if (field($0, "unit_restarted") == "true") {
            restarts[++r] = ts " (unit " field($0, "unit") " is a NEW instance; boot_changed=" \
                            field($0, "boot_changed") ")"
        }
        if (field($0, "unit_down") == "true") {
            downs[++d] = ts " (unit " field($0, "unit") " went " field($0, "unit_active") \
                         "; pids=" field($0, "unit_pids") ")"
        }
        if (field($0, "boot_changed") == "true") boots[++b] = ts
        if (field($0, "k_suspend") + 0 > 0) susp[++s] = ts " (" field($0, "k_suspend") " records)"
        if (field($0, "k_oom") + 0 > 0) {
            ooms[++o] = ts " (" field($0, "k_oom") " records) cgroups=[" field($0, "oom_cgroups") "]"
        }
        if (field($0, "k_unit_kill") + 0 > 0) kills[++k] = ts " (" field($0, "k_unit_kill") " records)"
        if (field($0, "journal_ok") == "false") blind++
    }
    END {
        printf "Flight-recorder report\n"
        printf "======================\n"
        printf "  records          : %d\n", n
        printf "  span             : %s .. %s\n", first, last
        printf "  ticks journal-blind: %d%s\n", blind+0,
               (blind+0 > 0 ? "  (journalctl unreadable in those ticks - signals are null, not zero)" : "")
        printf "\n"
        printf "  recording gaps (>= 2 missed ticks) : %d\n", g+0
        for (i = 1; i <= g; i++) printf "      - %s\n", gaps[i]
        printf "  watched unit went down             : %d\n", d+0
        for (i = 1; i <= d; i++) printf "      - %s\n", downs[i]
        printf "  watched unit came back as new inst.: %d\n", r+0
        for (i = 1; i <= r; i++) printf "      - %s\n", restarts[i]
        printf "  reboots (boot_id changed)          : %d\n", b+0
        for (i = 1; i <= b; i++) printf "      - %s\n", boots[i]
        printf "  kernel suspend records             : %d\n", s+0
        for (i = 1; i <= s; i++) printf "      - %s\n", susp[i]
        printf "  OOM records (with attribution)     : %d\n", o+0
        for (i = 1; i <= o; i++) printf "      - %s\n", ooms[i]
        printf "  unit SIGKILL signatures            : %d\n", k+0
        for (i = 1; i <= k; i++) printf "      - %s\n", kills[i]
        printf "\n  VERDICT: "
        if (b + 0 > 0) {
            printf "REBOOT recorded (boot_id changed) - a session teardown here is\n"
            printf "           explained by the reboot, not by the forced-logout class.\n"
        } else if (s + 0 > 0) {
            printf "SUSPEND records present - triage as a power-state event first\n"
            printf "           (CONST-033 operational note), not as a forced logout.\n"
        } else if (r + 0 > 0 || k + 0 > 0 || d + 0 > 0) {
            printf "SESSION TEARDOWN of the forced-logout class.\n"
            printf "           The user manager restarted with NO reboot and NO suspend\n"
            printf "           record. Cross-check the OOM attribution above: a libpod-*\n"
            printf "           cgroup means a container hit its own limit; a user@<uid>\n"
            printf "           cgroup means a user-slice OOM perceived as a logout; no OOM\n"
            printf "           record at all means an external SIGKILL - escalate to the\n"
            printf "           system.slice watchdog for initiator attribution.\n"
        } else if (g + 0 > 0) {
            printf "RECORDING GAP with no teardown evidence. The recorder itself was\n"
            printf "           not scheduled during that window (host asleep, cron stopped,\n"
            printf "           or the recorder was uninstalled). Not itself an incident.\n"
        } else {
            printf "no session-teardown event recorded in this window.\n"
        }
    }'
}

status() {
    echo "flight-recorder $RECORDER_VERSION"
    echo "  state dir : $STATE_DIR"
    echo "  target    : $TARGET_UNIT"
    echo "  tick      : every ${TICK_SEC}s (gap alarm at >${GAP_ANOMALY_SEC}s)"
    if [[ -f "$JOURNAL_FILE" ]]; then
        echo "  records   : $(wc -l <"$JOURNAL_FILE") in $(stat -c %s "$JOURNAL_FILE") bytes"
    else
        echo "  records   : (none yet)"
    fi
    [[ -f "$ROTATED_FILE" ]] && echo "  rotated   : $(wc -l <"$ROTATED_FILE") records retained"
    if [[ -f "$LATEST_FILE" ]]; then
        echo "  latest    : $(cat "$LATEST_FILE")"
    fi
    if crontab -l 2>/dev/null | grep -q 'boba-flight-recorder'; then
        echo "  cron tick : INSTALLED"
    else
        echo "  cron tick : not installed (scripts/flight-recorder/install.sh)"
    fi
}

# Self-check that the recorder's load-bearing claims actually hold on this host,
# rather than being asserted by the documentation (§11.4.201).
verify() {
    local rc=0
    echo "flight-recorder verify"
    echo "----------------------"

    mkdir -p "$STATE_DIR"
    local fstype
    fstype="$(stat -f -c %T "$STATE_DIR" 2>/dev/null || echo unknown)"
    if [[ "$fstype" == "tmpfs" || "$fstype" == "ramfs" || "$fstype" == "unknown" ]]; then
        echo "  [FAIL] state dir is on '$fstype' — not durable"
        rc=1
    else
        echo "  [ok]   state dir durable: $STATE_DIR ($fstype)"
    fi

    # The whole architecture rests on the scheduler living outside the unit we
    # watch. Assert it, do not assume it.
    local crond_cg="" crond_pid
    crond_pid="$(timeout "$CMD_TIMEOUT" systemctl show crond -p MainPID --value 2>/dev/null || true)"
    if [[ "$crond_pid" =~ ^[0-9]+$ ]] && (( crond_pid > 1 )); then
        crond_cg="$(sed -n 's/^0:://p' "/proc/$crond_pid/cgroup" 2>/dev/null || true)"
    fi
    if [[ -z "$crond_cg" ]]; then
        echo "  [WARN] could not resolve the cron daemon's cgroup — scheduler survivability UNVERIFIED"
    elif [[ "$crond_cg" == *"/user.slice/"* ]]; then
        echo "  [FAIL] cron daemon is inside user.slice ($crond_cg) — it would die with the session"
        rc=1
    else
        echo "  [ok]   scheduler outside user.slice: crond in $crond_cg"
    fi

    # The recorder must not be able to signal anything. Prove it from its own
    # source rather than from a claim in the docs.
    local self="${BASH_SOURCE[0]}"
    if grep -nE '\b(kill|pkill|killall|killpg)\b[[:space:]]*(-|\()' "$self" \
        | grep -vE '^[0-9]+:[[:space:]]*#' | grep -q .; then
        echo "  [FAIL] recorder source contains a signal-sending call"
        rc=1
    else
        echo "  [ok]   recorder sends no signals (§11.4.263 satisfied by construction)"
    fi

    if timeout "$CMD_TIMEOUT" journalctl -n 1 --no-pager -q >/dev/null 2>&1; then
        echo "  [ok]   journalctl readable — triage signals will be counted"
    else
        echo "  [WARN] journalctl unreadable — triage signals will record as null, not zero"
    fi

    echo "----------------------"
    (( rc == 0 )) && echo "  VERIFY: PASS" || echo "  VERIFY: FAIL"
    return "$rc"
}

main() {
    local cmd="${1:-tick}"
    case "$cmd" in
        tick)   preflight; collect_and_emit >/dev/null ;;
        tick-v) preflight; collect_and_emit ;;
        report) report ;;
        status) status ;;
        verify) verify ;;
        -h|--help|help)
            sed -n '2,60p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' ;;
        *) die "unknown command '$cmd' (expected: tick|tick-v|report|status|verify)" ;;
    esac
}

main "$@"
