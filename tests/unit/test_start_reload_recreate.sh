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

CHECK_NAMES=(
    BOBACTL_DOWN_AND_UP DOWN_BEFORE_UP UP_IS_DETACHED NO_RAW_RUNTIME_CALLS
    NO_BOBA_CTL_USES_COMPOSE EXIT_ZERO_AND_SUCCESS_MSG
    DOWN_FAILURE_IS_NONFATAL UP_FAILURE_IS_FATAL
)
declare -A CHECK_DESC=(
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
