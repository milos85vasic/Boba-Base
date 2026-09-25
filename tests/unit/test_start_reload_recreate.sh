#!/usr/bin/env bash
# test_start_reload_recreate.sh — behavioural tests for `start.sh --recreate`
# (BOB-089 / RD2-24). Restart level 3 per CLAUDE.md "Pick the right restart
# level": full `<compose> down && <compose> up -d`.
#
# The orchestrator binding is the point (Hard Stop #3 -- container
# orchestration is owned exclusively by start.sh, operators never type raw
# podman/docker): by default $COMPOSE_CMD is boba-ctl, and --no-boba-ctl
# switches it to the raw compose CLI. Both bindings are asserted, as is the
# absence of any direct runtime call on this path.
#
# Run:  bash tests/unit/test_start_reload_recreate.sh          # GREEN
#       bash tests/unit/test_start_reload_recreate.sh --red    # §1.1 mutations

# SC2034: CHECK_NAMES/CHECK_DESC/CHECK_MUTATION/CHECK_DIAG/BOBA_SHIM_FAIL are
# read by harness_drive()/harness_run() in the sourced harness via bash
# dynamic scope, which shellcheck cannot follow across the `source` boundary.
# shellcheck disable=SC2034
set -euo pipefail
# shellcheck source=./test_start_reload_harness.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/test_start_reload_harness.sh"

CTL_DOWN='boba-ctl.sh|down'
CTL_UP='boba-ctl.sh|up|-d'
OWN_PRE='ownership_precondition.sh'
OWN_REP='ownership_repair.sh'

mk() {
    local mut="$1"; shift
    local sb; sb="$(harness_new_sandbox)"
    local s; for s in "$@"; do harness_add_shim "$sb" "$s"; done
    [[ -n "$mut" ]] && harness_mutate "$sb" "$mut"
    printf '%s\n' "$sb"
}

check_BOBACTL_DOWN_AND_UP() {
    local sb; sb="$(mk "$1" podman podman-compose)"
    harness_run "$sb" --recreate
    local ok=1
    harness_log_has "$sb" "$CTL_DOWN" && harness_log_has "$sb" "$CTL_UP" && ok=0
    CHECK_DIAG="expected '$CTL_DOWN' and '$CTL_UP' via the boba-ctl orchestrator"
    harness_cleanup "$sb"; return $ok
}

check_DOWN_BEFORE_UP() {
    local sb; sb="$(mk "$1" podman podman-compose)"
    harness_run "$sb" --recreate
    local ok=1; harness_log_before "$sb" "$CTL_DOWN" "$CTL_UP" && ok=0
    CHECK_DIAG="down must precede up -d"
    harness_cleanup "$sb"; return $ok
}

check_UP_IS_DETACHED() {
    # Without -d the orchestrator blocks in the foreground and start.sh never
    # returns -- the exact argv matters, not just "up was called".
    local sb; sb="$(mk "$1" podman podman-compose)"
    harness_run "$sb" --recreate
    local ok=1; harness_log_has "$sb" "$CTL_UP" && ok=0
    CHECK_DIAG="up must carry -d; log: $(grep '|up' "$sb/argv.log" | tr '\n' ' ')"
    harness_cleanup "$sb"; return $ok
}

check_NO_RAW_RUNTIME_CALLS() {
    # Hard Stop #3: --recreate goes through the orchestrator, never a raw
    # podman/docker verb.
    local sb; sb="$(mk "$1" podman podman-compose)"
    harness_run "$sb" --recreate
    local ok=0
    grep -qE '^(podman|docker)\|' "$sb/argv.log" && ok=1
    CHECK_DIAG="raw runtime calls: $(grep -E '^(podman|docker)\|' "$sb/argv.log" | tr '\n' ' ')"
    harness_cleanup "$sb"; return $ok
}

check_NO_BOBA_CTL_USES_COMPOSE() {
    # --no-boba-ctl re-binds $COMPOSE_CMD to the raw compose CLI.
    local sb; sb="$(mk "$1" podman podman-compose)"
    harness_run "$sb" --no-boba-ctl --recreate
    local ok=1
    if harness_log_has "$sb" 'podman-compose|down' \
       && harness_log_has "$sb" 'podman-compose|up|-d' \
       && harness_log_before "$sb" 'podman-compose|down' 'podman-compose|up|-d'; then ok=0; fi
    CHECK_DIAG="expected podman-compose down then up -d; log: $(tr '\n' ' ' < "$sb/argv.log")"
    harness_cleanup "$sb"; return $ok
}

check_EXIT_ZERO_AND_SUCCESS_MSG() {
    local sb; sb="$(mk "$1" podman podman-compose)"
    harness_run "$sb" --recreate
    local ok=1
    [[ "$HARNESS_RC" -eq 0 && "$HARNESS_OUT" == *"Stack recreated successfully"* ]] && ok=0
    CHECK_DIAG="rc=$HARNESS_RC"
    harness_cleanup "$sb"; return $ok
}

check_DOWN_FAILURE_IS_NONFATAL() {
    # A stack that was not running must still come UP -- `down` failing is a
    # warning, not an abort.
    local sb; sb="$(mk "$1" podman podman-compose)"
    local BOBA_SHIM_FAIL='boba-ctl.sh|down'
    harness_run "$sb" --recreate
    local ok=1
    if [[ "$HARNESS_RC" -eq 0 ]] \
       && harness_log_has "$sb" "$CTL_UP" \
       && [[ "$HARNESS_OUT" == *"may not have been running"* ]]; then ok=0; fi
    CHECK_DIAG="rc=$HARNESS_RC (want 0); up issued=$(harness_log_count "$sb" "$CTL_UP")"
    harness_cleanup "$sb"; return $ok
}

check_UP_FAILURE_IS_FATAL() {
    local sb; sb="$(mk "$1" podman podman-compose)"
    local BOBA_SHIM_FAIL='boba-ctl.sh|up|-d'
    harness_run "$sb" --recreate
    local ok=1
    [[ "$HARNESS_RC" -ne 0 && "$HARNESS_OUT" == *"Failed to bring the stack back up"* ]] && ok=0
    CHECK_DIAG="rc=$HARNESS_RC (want non-zero); out tail: ${HARNESS_OUT: -80}"
    harness_cleanup "$sb"; return $ok
}


# --- FR-004d ordering (T041 IMPORTANT-2) -----------------------------------
# The repair WALKS AND CHOWNS the declared tree. A container that is still up
# can write a new non-operator-owned file BEHIND the walk, after which the
# completion marker records "complete" over a tree that is not -- and those
# stragglers are never repaired without a manual --force. The worst case is
# precisely the migration moment this feature exists for: the first
# `--recreate` after the fix, with the OLD PUID=1000 qbittorrent mid-download.
#
# The precondition is the opposite: it READS docker-compose.yml, needs no
# quiescence, and must run FIRST so a bad compose is refused BEFORE the
# operator's stack is taken down rather than after.

check_PRECONDITION_BEFORE_DOWN() {
    local sb; sb="$(mk "$1" podman podman-compose)"
    harness_run "$sb" --recreate
    local ok=1; harness_log_before "$sb" "$OWN_PRE" "$CTL_DOWN" && ok=0
    CHECK_DIAG="precondition must precede down (refuse before tearing the stack down); log: $(tr '\n' ' ' < "$sb/argv.log")"
    harness_cleanup "$sb"; return $ok
}

check_REPAIR_AFTER_DOWN() {
    local sb; sb="$(mk "$1" podman podman-compose)"
    harness_run "$sb" --recreate
    local ok=1; harness_log_before "$sb" "$CTL_DOWN" "$OWN_REP" && ok=0
    CHECK_DIAG="down must precede the repair (FR-004d: no live writer during the walk); log: $(tr '\n' ' ' < "$sb/argv.log")"
    harness_cleanup "$sb"; return $ok
}

check_REPAIR_BEFORE_UP() {
    local sb; sb="$(mk "$1" podman podman-compose)"
    harness_run "$sb" --recreate
    local ok=1; harness_log_before "$sb" "$OWN_REP" "$CTL_UP" && ok=0
    CHECK_DIAG="the repair must complete before up -d restores writers; log: $(tr '\n' ' ' < "$sb/argv.log")"
    harness_cleanup "$sb"; return $ok
}

# --- BOB-159: warm-start bounded repair-until-stable ------------------------
# Operator decision 2026-08-26 (§11.4.66): REPAIR, THEN RE-VERIFY UNTIL
# STABLE. The --recreate path above needs no loop -- stack_down() already
# quiesces every writer before its single repair pass runs (FR-004d). The
# WARM path (plain `./start.sh`, no flags) has no stack_down(): a live
# container can write a new non-operator-owned file BEHIND a single walk, so
# run_ownership_gate() now calls run_ownership_repair_until_stable(), which
# walks, re-verifies, and repeats -- bounded -- until a pass finds NOTHING
# NEW, or honestly gives up as UNPROVEN rather than exit 0.
#
# harness_run() drives main() end to end, which is right for the --recreate
# checks above but would drag in start_container/wait_for_jackett/curl/
# python3/etc for no added assurance here: the function under test is a
# fixed, self-contained unit, and start.sh is deliberately hermetically
# sourceable (see its own trailing `if [[ "${BASH_SOURCE[0]}" == "${0}" ]]`
# guard) for exactly this reason. These two checks SOURCE the sandboxed
# start.sh (main() never runs) and call run_ownership_repair_until_stable
# directly, against a purpose-built ownership_repair.sh DOUBLE -- not the
# harness's generic argv-recorder shim -- that reports a SCRIPTED per-call
# item count (DOUBLE_ITEMS_SEQUENCE, colon-separated) via ownership_repair.sh's
# own real "complete: N item(s) repaired" line shape, so convergence and
# non-convergence are both reproducible without a real filesystem walk.

# harness_write_repair_double <sandbox> — overwrite the generic recorder shim
# scripts/ownership_repair.sh with the scripted double described above.
harness_write_repair_double() {
    local sb="$1"
    cat > "$sb/repo/scripts/ownership_repair.sh" <<'DOUBLE'
#!/usr/bin/env bash
# BOB-159 test double for scripts/ownership_repair.sh — returns a SCRIPTED
# per-call item count (DOUBLE_ITEMS_SEQUENCE, colon-separated) instead of
# performing a real filesystem walk, so run_ownership_repair_until_stable's
# convergence / non-convergence behaviour is reproducible without one.
set -euo pipefail
state_dir="${DOUBLE_STATE_DIR:?DOUBLE_STATE_DIR unset}"
mkdir -p "$state_dir"
count_file="$state_dir/repair_calls"
n=0
[[ -f "$count_file" ]] && n="$(cat "$count_file")"
n=$((n + 1))
printf '%s' "$n" > "$count_file"
printf '%s\n' "$*" >> "$state_dir/repair_argv.log"

IFS=':' read -r -a seq <<< "${DOUBLE_ITEMS_SEQUENCE:?DOUBLE_ITEMS_SEQUENCE unset}"
idx=$((n - 1))
if (( idx < ${#seq[@]} )); then
    items="${seq[$idx]}"
else
    items="${seq[${#seq[@]}-1]}"
fi

printf '[ownership-repair] complete: %s item(s) repaired; record x.ndjson; marker repair-marker.json\n' "$items"
exit 0
DOUBLE
    chmod +x "$sb/repo/scripts/ownership_repair.sh"
}

# harness_call_stable <sandbox> <colon-separated-item-sequence> — source the
# sandboxed start.sh (main() never runs, per its own sourcing guard) and call
# run_ownership_repair_until_stable() directly. Sets HARNESS_OUT / HARNESS_RC,
# same contract as harness_run().
harness_call_stable() {
    local sb="$1" seq="$2"
    local out rc=0
    mkdir -p "$sb/state"
    set +e
    out="$(
        cd "$sb/repo" && \
        PATH="$sb/bin:$sb/sysbin" \
        HOME="$sb/home" \
        DOUBLE_STATE_DIR="$sb/state" \
        DOUBLE_ITEMS_SEQUENCE="$seq" \
        bash -c 'source "$1/repo/start.sh"; run_ownership_repair_until_stable' _ "$sb" 2>&1
    )"
    rc=$?
    set -e
    HARNESS_OUT="$out"
    HARNESS_RC="$rc"
}

check_WARM_REVERIFY_UNTIL_STABLE() {
    # First pass finds 2 stragglers (repaired), second pass finds 0 (nothing
    # new) -- the function must STOP re-verifying there: exactly 2 calls,
    # rc=0, and it must say so as "STABLE after 2 pass(es)".
    local sb; sb="$(harness_new_sandbox)"
    harness_write_repair_double "$sb"
    [[ -n "$1" ]] && harness_mutate "$sb" "$1"
    harness_call_stable "$sb" "2:0"
    local ok=1 calls
    calls="$(cat "$sb/state/repair_calls" 2>/dev/null || echo 0)"
    if [[ "$HARNESS_RC" -eq 0 && "$HARNESS_OUT" == *"STABLE after 2 pass(es)"* && "$calls" == "2" ]]; then
        ok=0
    fi
    CHECK_DIAG="rc=$HARNESS_RC calls=$calls out tail: ${HARNESS_OUT: -200}"
    harness_cleanup "$sb"; return $ok
}

check_WARM_REVERIFY_UNPROVEN_ON_NONCONVERGENCE() {
    # Every pass reports 3 NEW items -- an active download writing faster
    # than the walk completes never lets a pass find nothing. The loop MUST
    # be bounded (exactly OWNERSHIP_REPAIR_MAX_PASSES=4 calls, never more),
    # MUST exit non-zero, and MUST say UNPROVEN + name the realistic cause --
    # never silently exit 0 over an unverified tree (§11.4.201(6)).
    local sb; sb="$(harness_new_sandbox)"
    harness_write_repair_double "$sb"
    [[ -n "$1" ]] && harness_mutate "$sb" "$1"
    harness_call_stable "$sb" "3:3:3:3:3:3"
    local ok=1 calls
    calls="$(cat "$sb/state/repair_calls" 2>/dev/null || echo 0)"
    if [[ "$HARNESS_RC" -ne 0 && "$HARNESS_OUT" == *"UNPROVEN"* \
          && "$HARNESS_OUT" == *"ACTIVE DOWNLOAD"* && "$calls" == "4" ]]; then
        ok=0
    fi
    CHECK_DIAG="rc=$HARNESS_RC calls=$calls out tail: ${HARNESS_OUT: -240}"
    harness_cleanup "$sb"; return $ok
}

CHECK_NAMES=(
    PRECONDITION_BEFORE_DOWN
    REPAIR_AFTER_DOWN
    REPAIR_BEFORE_UP
    WARM_REVERIFY_UNTIL_STABLE
    WARM_REVERIFY_UNPROVEN_ON_NONCONVERGENCE
    BOBACTL_DOWN_AND_UP DOWN_BEFORE_UP UP_IS_DETACHED NO_RAW_RUNTIME_CALLS
    NO_BOBA_CTL_USES_COMPOSE EXIT_ZERO_AND_SUCCESS_MSG
    DOWN_FAILURE_IS_NONFATAL UP_FAILURE_IS_FATAL
)
declare -A CHECK_DESC=(
    [PRECONDITION_BEFORE_DOWN]='probes ownership BEFORE tearing the stack down (FR-010)'
    [REPAIR_AFTER_DOWN]='repairs only after down, so no container writes behind the walk (FR-004d)'
    [REPAIR_BEFORE_UP]='completes the repair before up -d restores writers (FR-004d)'
    [WARM_REVERIFY_UNTIL_STABLE]='warm start re-verifies until a pass finds nothing new, then stops (BOB-159)'
    [WARM_REVERIFY_UNPROVEN_ON_NONCONVERGENCE]='bounded give-up reports ownership UNPROVEN, never a silent exit 0 (BOB-159, §11.4.201(6))'
    [BOBACTL_DOWN_AND_UP]='issues down and up -d through the boba-ctl orchestrator'
    [DOWN_BEFORE_UP]='tears the stack down before bringing it up'
    [UP_IS_DETACHED]='brings the stack up detached (-d)'
    [NO_RAW_RUNTIME_CALLS]='never issues a raw podman/docker verb (Hard Stop #3)'
    [NO_BOBA_CTL_USES_COMPOSE]='--no-boba-ctl re-binds to raw podman-compose'
    [EXIT_ZERO_AND_SUCCESS_MSG]='exits 0 and reports success'
    [DOWN_FAILURE_IS_NONFATAL]='a failing down warns but still brings the stack up'
    [UP_FAILURE_IS_FATAL]='exits non-zero when up fails'
)
declare -A CHECK_MUTATION=(
    [PRECONDITION_BEFORE_DOWN]='s/^        run_ownership_precondition$//; /^        stack_down$/a \        run_ownership_precondition'
    [REPAIR_AFTER_DOWN]='/^        stack_down$/i \        run_ownership_repair'
    [REPAIR_BEFORE_UP]='s/^        run_ownership_repair$//; /^        stack_up$/a \        run_ownership_repair'
    [WARM_REVERIFY_UNTIL_STABLE]='s/if \[\[ "\$items" -eq 0 \]\]; then/if [[ "$items" -eq 999999 ]]; then/'
    [WARM_REVERIFY_UNPROVEN_ON_NONCONVERGENCE]='/or wait for the write activity to settle/{n;s/exit 1/:/}'
    [BOBACTL_DOWN_AND_UP]='s/COMPOSE_CMD="\$SCRIPT_DIR\/scripts\/boba-ctl.sh"/COMPOSE_CMD="$SCRIPT_DIR\/scripts\/boba-ctl-TYPO.sh"/'
    [DOWN_BEFORE_UP]='/print_info "Recreating the full stack/a \    $COMPOSE_CMD up -d'
    [UP_IS_DETACHED]='s/if ! \$COMPOSE_CMD up -d; then/if ! $COMPOSE_CMD up; then/'
    [NO_RAW_RUNTIME_CALLS]='/print_info "Recreating the full stack/a \    $CONTAINER_RUNTIME restart qbittorrent-proxy'
    [NO_BOBA_CTL_USES_COMPOSE]='s/COMPOSE_CMD="podman-compose"/COMPOSE_CMD="podman-compose-TYPO"/'
    [EXIT_ZERO_AND_SUCCESS_MSG]='s/print_success "Stack recreated successfully"/print_success "maybe"/'
    [DOWN_FAILURE_IS_NONFATAL]='/Stack may not have been running/a \        exit 1'
    [UP_FAILURE_IS_FATAL]='/Failed to bring the stack back up/{n;s/exit 1/:/}'
)

echo "== start.sh --recreate (${1:---green}) =="
harness_drive "$([[ "${1:-}" == "--red" ]] && echo red || echo green)"
