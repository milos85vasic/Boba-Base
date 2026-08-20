#!/usr/bin/env bash
# test_start_reload_plugins.sh — behavioural tests for `start.sh --reload-plugins`
# (BOB-089 / RD2-24). Restart level 2 per CLAUDE.md "Pick the right restart level":
# restart the container ONLY. It deliberately does NOT copy plugin files --
# ./install-plugin.sh must run FIRST -- and it does NOT clear __pycache__.
# The load-bearing assertions here are the NEGATIVE ones: what level 2 must
# NOT do is exactly what distinguishes it from levels 1 and 3.
#
# Run:  bash tests/unit/test_start_reload_plugins.sh          # GREEN
#       bash tests/unit/test_start_reload_plugins.sh --red    # §1.1 mutations

# SC2034: CHECK_NAMES/CHECK_DESC/CHECK_MUTATION/CHECK_DIAG/BOBA_SHIM_FAIL are
# read by harness_drive()/harness_run() in the sourced harness via bash
# dynamic scope, which shellcheck cannot follow across the `source` boundary.
# shellcheck disable=SC2034
set -euo pipefail
# shellcheck source=./test_start_reload_harness.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/test_start_reload_harness.sh"

RESTART_LINE='podman|restart|qbittorrent-proxy'

mk() {
    local mut="$1"; shift
    local sb; sb="$(harness_new_sandbox)"
    local s; for s in "$@"; do harness_add_shim "$sb" "$s"; done
    [[ -n "$mut" ]] && harness_mutate "$sb" "$mut"
    printf '%s\n' "$sb"
}

check_RESTART_ISSUED() {
    local sb; sb="$(mk "$1" podman podman-compose)"
    harness_run "$sb" --reload-plugins
    local ok=1; harness_log_has "$sb" "$RESTART_LINE" && ok=0
    CHECK_DIAG="expected argv: $RESTART_LINE"
    harness_cleanup "$sb"; return $ok
}

check_RESTART_EXACTLY_ONCE() {
    local sb; sb="$(mk "$1" podman podman-compose)"
    harness_run "$sb" --reload-plugins
    local n ok=1; n="$(harness_log_count "$sb" "$RESTART_LINE")"
    [[ "$n" -eq 1 ]] && ok=0
    CHECK_DIAG="expected exactly 1 restart, saw $n"
    harness_cleanup "$sb"; return $ok
}

check_NO_CACHE_CLEAR() {
    # The documented difference from --reload-python: level 2 does NOT exec
    # into the container to clear __pycache__.
    local sb; sb="$(mk "$1" podman podman-compose)"
    harness_run "$sb" --reload-plugins
    local ok=0
    grep -q '|exec|' "$sb/argv.log" && ok=1
    CHECK_DIAG="unexpected exec: $(grep '|exec|' "$sb/argv.log" | tr '\n' ' ')"
    harness_cleanup "$sb"; return $ok
}

check_NO_STACK_TEARDOWN() {
    local sb; sb="$(mk "$1" podman podman-compose)"
    harness_run "$sb" --reload-plugins
    local ok=0
    grep -qE '\|down$|\|up\|-d$' "$sb/argv.log" && ok=1
    CHECK_DIAG="unexpected compose down/up: $(grep -E '\|down$|\|up\|-d$' "$sb/argv.log" | tr '\n' ' ')"
    harness_cleanup "$sb"; return $ok
}

check_WARNS_INSTALL_PLUGIN_FIRST() {
    # Restarting alone reloads whatever is ALREADY installed; without this
    # warning an operator silently re-runs the old plugin and calls it fixed.
    local sb; sb="$(mk "$1" podman podman-compose)"
    harness_run "$sb" --reload-plugins
    local ok=1
    [[ "$HARNESS_OUT" == *"install-plugin.sh"* && "$HARNESS_OUT" == *"does NOT copy"* ]] && ok=0
    CHECK_DIAG="output must warn that files are NOT copied and install-plugin.sh runs first"
    harness_cleanup "$sb"; return $ok
}

check_EXIT_ZERO() {
    local sb; sb="$(mk "$1" podman podman-compose)"
    harness_run "$sb" --reload-plugins
    local ok=1
    [[ "$HARNESS_RC" -eq 0 && "$HARNESS_OUT" == *"qbittorrent-proxy restarted"* ]] && ok=0
    CHECK_DIAG="rc=$HARNESS_RC"
    harness_cleanup "$sb"; return $ok
}

check_RESTART_FAILURE_IS_FATAL() {
    local sb; sb="$(mk "$1" podman podman-compose)"
    local BOBA_SHIM_FAIL='podman|restart|*'
    harness_run "$sb" --reload-plugins
    local ok=1
    [[ "$HARNESS_RC" -ne 0 && "$HARNESS_OUT" == *"Failed to restart"* ]] && ok=0
    CHECK_DIAG="rc=$HARNESS_RC (want non-zero on restart failure)"
    harness_cleanup "$sb"; return $ok
}

check_NO_RUNTIME_REFUSES() {
    local sb; sb="$(mk "$1")"
    harness_run "$sb" --reload-plugins
    local ok=1
    if [[ "$HARNESS_RC" -eq 1 ]] \
       && [[ "$HARNESS_OUT" == *"No container runtime"* ]] \
       && ! grep -qE '^(podman|docker)\|' "$sb/argv.log"; then ok=0; fi
    CHECK_DIAG="rc=$HARNESS_RC (want 1); runtime calls: $(grep -cE '^(podman|docker)\|' "$sb/argv.log" || true)"
    harness_cleanup "$sb"; return $ok
}

CHECK_NAMES=(
    RESTART_ISSUED RESTART_EXACTLY_ONCE NO_CACHE_CLEAR NO_STACK_TEARDOWN
    WARNS_INSTALL_PLUGIN_FIRST EXIT_ZERO RESTART_FAILURE_IS_FATAL NO_RUNTIME_REFUSES
)
declare -A CHECK_DESC=(
    [RESTART_ISSUED]='restarts the qbittorrent-proxy container'
    [RESTART_EXACTLY_ONCE]='restarts exactly once'
    [NO_CACHE_CLEAR]='does NOT exec into the container to clear __pycache__ (that is --reload-python)'
    [NO_STACK_TEARDOWN]='does NOT issue compose down/up (that is --recreate)'
    [WARNS_INSTALL_PLUGIN_FIRST]='warns that files are not copied and install-plugin.sh must run first'
    [EXIT_ZERO]='exits 0 and reports the restart'
    [RESTART_FAILURE_IS_FATAL]='exits non-zero when the restart fails'
    [NO_RUNTIME_REFUSES]='exits 1 with an honest error when no runtime exists'
)
declare -A CHECK_MUTATION=(
    [RESTART_ISSUED]='s#\$CONTAINER_RUNTIME restart qbittorrent-proxy#$CONTAINER_RUNTIME restart WRONGCONTAINER#'
    [RESTART_EXACTLY_ONCE]='/print_success "qbittorrent-proxy restarted"/i \    $CONTAINER_RUNTIME restart qbittorrent-proxy'
    [NO_CACHE_CLEAR]='/Restarting qbittorrent-proxy container to pick up/i \    $CONTAINER_RUNTIME exec qbittorrent-proxy find /config/download-proxy -name __pycache__ -type d -exec rm -rf {} +'
    [NO_STACK_TEARDOWN]='/Restarting qbittorrent-proxy container to pick up/i \    $COMPOSE_CMD down'
    [WARNS_INSTALL_PLUGIN_FIRST]='/does NOT copy plugin files/d'
    [EXIT_ZERO]='s/print_success "qbittorrent-proxy restarted"/print_success "done"/'
    [RESTART_FAILURE_IS_FATAL]='/Failed to restart qbittorrent-proxy container/{n;s/exit 1/:/}'
    [NO_RUNTIME_REFUSES]='s/if \[\[ -z "\$CONTAINER_RUNTIME" \]\]; then/if false; then/'
)

echo "== start.sh --reload-plugins (${1:---green}) =="
harness_drive "$([[ "${1:-}" == "--red" ]] && echo red || echo green)"
