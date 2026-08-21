#!/usr/bin/env bash
#
# bob131_container_death_triage.sh
#
# Purpose:
#   Classify why a rootless-podman container stopped, distinguishing the six
#   causes this project has repeatedly confused with one another. Born from
#   BOB-131, where a ticket recorded "podman conmon crash" for two unrelated
#   events: a host power-off (container ABSENT) and a SIGSEGV inside the
#   containerised process (container CRASHED). Neither was a conmon crash.
#
# Usage:
#   bob131_container_death_triage.sh --selftest
#   bob131_container_death_triage.sh collect <container> <since> <until> > bundle.txt
#   bob131_container_death_triage.sh classify <bundle.txt>
#
# Inputs:
#   collect  : container name, and two journalctl-compatible timestamps.
#   classify : an evidence bundle produced by `collect` (or a fixture).
#
# Outputs:
#   classify prints one `VERDICT: <CLASS>` line plus `NOTE:` lines, and exits 0.
#   --selftest exits 0 when every golden fixture classifies as expected, 1 otherwise.
#
# Side-effects:
#   NONE. Every podman/journal/cgroup access is read-only. This script never
#   starts, stops, restarts, removes or signals anything (Hard Stop #3,
#   §11.4.263: it sends no signals at all, so it cannot reach pgid <= 1).
#
# Dependencies: bash, podman (collect only), journalctl (collect only), awk, grep.
#
# Cross-references:
#   docs/incidents/2026-08-21-bob131-container-death-triage.md  (the investigation)
#   docs/guides/container-death-triage.md                        (the triage guide)
#   docs/scripts/bob131_container_death_triage.md                (§11.4.18 companion)
#
set -euo pipefail

readonly CLASS_POWER="HOST-POWER-TRANSITION"
readonly CLASS_THREADS="THREAD-LIMIT-EXHAUSTION"
readonly CLASS_OOMKILL="CGROUP-OOM-KILL"
readonly CLASS_SEGV="PROCESS-SIGSEGV"
readonly CLASS_STOP="ORCHESTRATED-STOP"
readonly CLASS_CEILING="CGROUP-MEMORY-CEILING"
readonly CLASS_UNKNOWN="UNKNOWN"

section() {
    # section <bundle> <NAME> -> prints the lines of that section
    awk -v want="### $2" '
        $0 == want { on = 1; next }
        /^### / { on = 0 }
        on { print }
    ' "$1"
}

classify_bundle() {
    # Classify ONE container death from an evidence bundle.
    #
    # Precedence is deliberate and runs most-specific first, because the
    # classes overlap in their symptoms and the cheap signals lie:
    #   - a host power-off makes every container "die" at once (exit 0);
    #   - thread exhaustion (EAGAIN on clone) is NOT an OOM and the memory
    #     numbers look healthy while it happens (§12.12);
    #   - a cgroup OOM-kill IS containment working as designed (§12.6), and is
    #     distinguished from mere ceiling pressure by oom_kill > 0;
    #   - hitting memory.max WITHOUT oom_kill is reclaim, not a kill, and is
    #     never on its own a cause of death;
    #   - exit 137 after a restart/stop command is a SIGTERM-timeout SIGKILL;
    #   - conmon <error> lines are CARRIERS: conmon reporting a fault is not
    #     conmon crashing (§11.4.201 — match the thing, not a mention of it).
    local bundle="$1"
    local exit_code kernel logind logs conmon cgroup limits
    exit_code="$(section "$bundle" EXIT_CODE | tr -d '[:space:]')"
    kernel="$(section "$bundle" KERNEL)"
    logind="$(section "$bundle" LOGIND)"
    logs="$(section "$bundle" LOGS)"
    conmon="$(section "$bundle" CONMON)"
    cgroup="$(section "$bundle" CGROUP)"
    limits="$(section "$bundle" LIMITS)"

    local oom_kill mem_max
    oom_kill="$(printf '%s\n' "$cgroup" | awk '/^oom_kill /{print $2}' | head -1)"
    mem_max="$(printf '%s\n' "$cgroup" | awk '/^max /{print $2}' | head -1)"
    [[ "$oom_kill" =~ ^[0-9]+$ ]] || oom_kill=0
    [[ "$mem_max"  =~ ^[0-9]+$ ]] || mem_max=0

    local verdict="$CLASS_UNKNOWN"
    local -a notes=()

    if printf '%s\n' "$logind" | grep -iE 'powering down|will power off' >/dev/null; then
        verdict="$CLASS_POWER"
        notes+=("The host went down; the container did not fail. Containers do NOT")
        notes+=("come back on their own unless a boot-persistence unit is enabled")
        notes+=("(podman-restart.service / boba-stack.service). 'restart: unless-stopped'")
        notes+=("is a within-session policy and does not survive a power cycle.")
    elif printf '%s\n' "$logs" "$kernel" \
         | grep -iE 'failed to create new OS thread|Resource temporarily unavailable|pthread_create failed|Cannot allocate memory|EAGAIN' >/dev/null; then
        verdict="$CLASS_THREADS"
        notes+=("§12.12 thread/RLIMIT_NPROC exhaustion. This is NOT an OOM kill:")
        notes+=("memory can be abundant while clone(2) returns EAGAIN. Check")
        notes+=("'ulimit -u' against live 'ps -L -u \$USER | wc -l'.")
    elif (( oom_kill > 0 )) || printf '%s\n' "$kernel" | grep -iE 'Memory cgroup out of memory|oom-kill|Killed process' >/dev/null; then
        verdict="$CLASS_OOMKILL"
        notes+=("The container was killed AT ITS OWN cgroup limit. This is")
        notes+=("containment working as designed (§12.6), not a runtime defect.")
        notes+=("Decode oom_memcg: 'libpod-...' = the container's own limit.")
    elif [[ "$exit_code" == "139" ]] || printf '%s\n' "$kernel" | grep -iE 'segfault|ANOM_ABEND.*sig=11' >/dev/null; then
        verdict="$CLASS_SEGV"
        notes+=("exit 139 (=128+11) and/or a kernel SIGSEGV/ANOM_ABEND record:")
        notes+=("the container's PID 1 died of SIGSEGV.")
        notes+=("This is a genuine crash INSIDE the container, not a runtime fault.")
        notes+=("Confirm the faulting exe path exists only in the image, then")
        notes+=("byte-match the kernel 'Code:' dump against the library on disk.")
    elif [[ "$exit_code" == "137" ]] && printf '%s\n' "$(section "$bundle" EVENTS)" | grep -iE 'restart|stop|died' >/dev/null; then
        verdict="$CLASS_STOP"
        notes+=("exit 137 = 128+9 = SIGKILL after the stop timeout elapsed.")
        notes+=("An orchestrated stop/restart/down whose PID 1 did not finish")
        notes+=("handling SIGTERM in time. Not a crash and not an OOM.")
    elif (( mem_max > 0 )); then
        verdict="$CLASS_CEILING"
    fi

    if (( mem_max > 0 && oom_kill == 0 )) && [[ "$verdict" != "$CLASS_CEILING" ]]; then
        notes+=("memory.events max=$mem_max with oom_kill=0: the cgroup reached its")
        notes+=("ceiling and the kernel RECLAIMED rather than killed. Pressure, not cause.")
    fi
    if [[ "$verdict" == "$CLASS_CEILING" ]]; then
        notes+=("memory.events max=$mem_max, oom_kill=0. The cgroup repeatedly hit")
        notes+=("memory.max and the kernel reclaimed/swapped. Containment working as")
        notes+=("designed — it did NOT kill anything and is not a cause of death.")
    fi
    if [[ -n "$conmon" ]]; then
        notes+=("A conmon <error> line is present. conmon REPORTING a fault is not")
        notes+=("conmon CRASHING. A conmon crash would appear as conmon itself in a")
        notes+=("kernel segfault/ANOM_ABEND line — check for that before claiming one.")
    fi
    if [[ -n "$limits" ]]; then
        notes+=("limits: $limits")
    fi

    echo "VERDICT: $verdict"
    local n
    for n in "${notes[@]:-}"; do
        [[ -n "$n" ]] && echo "NOTE: $n"
    done
    return 0
}

run_selftest() {
    local tmp
    tmp="$(mktemp -d)"

    # --- golden fixtures: one per class, plus a negative control -------------
    cat > "$tmp/power.txt" <<'EOF'
### EXIT_CODE
0
### EVENTS
died exit=0
cleanup
remove
### LOGIND
systemd-logind[1296]: The system will power off now!
systemd-logind[1296]: System is powering down.
### CGROUP
oom_kill 0
max 0
EOF

    cat > "$tmp/threads.txt" <<'EOF'
### EXIT_CODE
1
### LOGS
runtime/cgo: pthread_create failed: Resource temporarily unavailable
fatal error: failed to create new OS thread (have 12 already; errno=11)
### LIMITS
threads=63000 nproc_soft=65536
### CGROUP
oom_kill 0
max 0
EOF

    cat > "$tmp/oomkill.txt" <<'EOF'
### EXIT_CODE
137
### KERNEL
Memory cgroup out of memory: Killed process 4242 (python3)
### CGROUP
oom_kill 3
max 900
EOF

    cat > "$tmp/segv.txt" <<'EOF'
### EXIT_CODE
139
### KERNEL
python3[314359]: segfault at 70 ip 00007fb2d690fea0 error 4 in libpython3.12.so.1.0[141ea0,7fb2d68d2000+2c3000]
audit[314359]: ANOM_ABEND auid=1000 pid=314359 comm="python3" exe="/usr/local/bin/python3.12" sig=11 res=1
### CGROUP
oom_kill 0
max 1584
EOF

    cat > "$tmp/stop.txt" <<'EOF'
### EXIT_CODE
137
### EVENTS
2026-08-20T14:59:21Z restart
2026-08-20T14:59:32Z died exit=137
### CGROUP
oom_kill 0
max 12
EOF

    cat > "$tmp/ceiling.txt" <<'EOF'
### EXIT_CODE
running
### CGROUP
oom_kill 0
max 1584
EOF

    # negative control: a healthy, quiet container must NOT trip any class.
    cat > "$tmp/negctrl.txt" <<'EOF'
### EXIT_CODE
running
### CGROUP
oom_kill 0
max 0
EOF

    # a conmon <error> line is a CARRIER, not a conmon crash: must not
    # change the verdict away from the orchestrated stop it accompanies.
    cat > "$tmp/conmon_carrier.txt" <<'EOF'
### EXIT_CODE
137
### EVENTS
2026-08-20T14:59:21Z restart
2026-08-20T14:59:32Z died exit=137
### CONMON
conmon 99612613c648 <error>: Failed to write 137 to exit file: No such file or directory
### CGROUP
oom_kill 0
max 0
EOF

    local -a names=(power  threads  oomkill  segv  stop  ceiling  negctrl  conmon_carrier)
    local -a want=("$CLASS_POWER" "$CLASS_THREADS" "$CLASS_OOMKILL" "$CLASS_SEGV" \
                   "$CLASS_STOP" "$CLASS_CEILING" "$CLASS_UNKNOWN" "$CLASS_STOP")

    local fails=0 i
    for i in "${!names[@]}"; do
        local out got
        out="$(classify_bundle "$tmp/${names[$i]}.txt")"
        got="$(printf '%s\n' "$out" | awk '/^VERDICT: /{print $2}')"
        if [[ "$got" == "${want[$i]}" ]]; then
            printf '  PASS  %-16s -> %s\n' "${names[$i]}" "$got"
        else
            printf '  FAIL  %-16s -> got=%-24s want=%s\n' "${names[$i]}" "$got" "${want[$i]}"
            fails=$((fails + 1))
        fi
    done

    echo
    rm -rf "$tmp"
    if (( fails == 0 )); then
        echo "SELFTEST: PASS (${#names[@]}/${#names[@]})"
        return 0
    fi
    echo "SELFTEST: FAIL ($fails/${#names[@]} wrong)"
    return 1
}

collect_bundle() {
    local container="$1" since="$2" until_="$3"
    local events died_code
    events="$(nice -n 19 ionice -c 3 podman events --since "$since" --until "$until_" --stream=false \
        --filter "container=$container" --format '{{.Time}} {{.Status}} exit={{.ContainerExitCode}}' 2>/dev/null \
        | grep -vE ' (health_status|exec|exec_died) ' || true)"
    # The exit code MUST come from the `died` event inside the window. Reading
    # it from `podman inspect` describes whatever container carries that NAME
    # right now, which for any historical window is a different container --
    # a §11.4.201 wrong-source read that silently answers about the wrong thing.
    died_code="$(printf '%s\n' "$events" | awk '/ died exit=/{sub(/.*exit=/,""); print}' | head -1)"
    echo "### EXIT_CODE"
    if [[ -n "$died_code" && "$died_code" != "<nil>" ]]; then
        echo "$died_code"
    else
        podman inspect "$container" --format '{{.State.ExitCode}}' 2>/dev/null || echo "unknown"
    fi
    echo "### EVENTS"
    printf '%s\n' "$events"
    echo "### KERNEL"
    nice -n 19 ionice -c 3 journalctl --since "$since" --until "$until_" --no-pager 2>/dev/null \
        | grep -iE 'segfault|ANOM_ABEND|Memory cgroup out of memory|oom-kill|Killed process' || true
    echo "### LOGIND"
    nice -n 19 ionice -c 3 journalctl --since "$since" --until "$until_" --no-pager 2>/dev/null \
        | grep -iE 'logind.*(power off|powering down)' || true
    echo "### LOGS"
    nice -n 19 ionice -c 3 journalctl "CONTAINER_NAME=$container" --since "$since" --until "$until_" \
        --no-pager 2>/dev/null | grep -iE 'Resource temporarily unavailable|failed to create new OS thread|Cannot allocate memory|EAGAIN' || true
    echo "### CONMON"
    nice -n 19 ionice -c 3 journalctl --since "$since" --until "$until_" --no-pager 2>/dev/null \
        | grep -E 'conmon\[[0-9]+\].*<error>' || true
    echo "### CGROUP"
    # Read LIVE from the container currently carrying this name. For a
    # historical window this is a DIFFERENT container -- the numbers describe
    # today's pressure, never the dead container's (§11.4.201: name the source).
    echo "# scope: LIVE container carrying this name, not the historical one"
    local cid cg
    cid="$(podman inspect "$container" --format '{{.Id}}' 2>/dev/null || true)"
    cg=""
    if [[ -n "$cid" ]]; then
        cg="$(find /sys/fs/cgroup -maxdepth 8 -type d -name "libpod-${cid}.scope" 2>/dev/null | head -1 || true)"
    fi
    if [[ -n "$cg" && -r "$cg/memory.events" ]]; then
        grep -E '^(oom_kill|max) ' "$cg/memory.events"
    else
        echo "oom_kill unknown"
        echo "max unknown"
    fi
    echo "### LIMITS"
    echo "threads=$(ps -L --no-headers -u "$USER" 2>/dev/null | wc -l) nproc_soft=$(ulimit -u)"
}

main() {
    case "${1:---help}" in
        --selftest) run_selftest ;;
        collect)    shift; collect_bundle "$@" ;;
        classify)   shift; classify_bundle "$@" ;;
        *) sed -n '2,30p' "$0"; exit 0 ;;
    esac
}

main "$@"
