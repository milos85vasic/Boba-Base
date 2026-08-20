#!/usr/bin/env bash
# test_start_reload_python.sh — behavioural tests for `start.sh --reload-python`
# (BOB-089 / RD2-24). Restart level 1 per CLAUDE.md "Pick the right restart level":
# clear __pycache__ inside qbittorrent-proxy, THEN restart it.
#
# Every check drives the REAL entry point (`bash start.sh --reload-python`,
# real arg parsing -> real detect_container_runtime -> real check_prerequisites
# -> real reload_python) against PATH recorder shims, and asserts the exact
# argv start.sh WOULD have handed the container runtime (§11.4.201(11)).
# No real container is started, stopped, or mutated (§12 host safety).
#
# Run:  bash tests/unit/test_start_reload_python.sh          # GREEN
#       bash tests/unit/test_start_reload_python.sh --red    # §1.1 mutations

# SC2034: CHECK_NAMES/CHECK_DESC/CHECK_MUTATION/CHECK_DIAG/BOBA_SHIM_FAIL are
# read by harness_drive()/harness_run() in the sourced harness via bash
# dynamic scope, which shellcheck cannot follow across the `source` boundary.
# shellcheck disable=SC2034
set -euo pipefail
# shellcheck source=./test_start_reload_harness.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/test_start_reload_harness.sh"

CACHE_LINE='podman|exec|qbittorrent-proxy|find|/config/download-proxy|-name|__pycache__|-type|d|-exec|rm|-rf|{}|+'
RESTART_LINE='podman|restart|qbittorrent-proxy'

# Build a sandbox with the requested runtime shims and an optional mutation.
mk() { # $1=mutation  $2..=shim names
    local mut="$1"; shift
    local sb; sb="$(harness_new_sandbox)"
    local s; for s in "$@"; do harness_add_shim "$sb" "$s"; done
    [[ -n "$mut" ]] && harness_mutate "$sb" "$mut"
    printf '%s\n' "$sb"
}

check_CACHE_CLEARED() {
    local sb; sb="$(mk "$1" podman podman-compose)"
    harness_run "$sb" --reload-python
    local ok=1; harness_log_has "$sb" "$CACHE_LINE" && ok=0
    CHECK_DIAG="expected argv: $CACHE_LINE"
    harness_cleanup "$sb"; return $ok
}

check_RESTART_ISSUED() {
    local sb; sb="$(mk "$1" podman podman-compose)"
    harness_run "$sb" --reload-python
    local ok=1; harness_log_has "$sb" "$RESTART_LINE" && ok=0
    CHECK_DIAG="expected argv: $RESTART_LINE"
    harness_cleanup "$sb"; return $ok
}

check_CACHE_BEFORE_RESTART() {
    local sb; sb="$(mk "$1" podman podman-compose)"
    harness_run "$sb" --reload-python
    local ok=1; harness_log_before "$sb" "$CACHE_LINE" "$RESTART_LINE" && ok=0
    CHECK_DIAG="__pycache__ must be cleared BEFORE the restart, else the stale cache shadows the edit"
    harness_cleanup "$sb"; return $ok
}

check_RESTART_EXACTLY_ONCE() {
    local sb; sb="$(mk "$1" podman podman-compose)"
    harness_run "$sb" --reload-python
    local n ok=1; n="$(harness_log_count "$sb" "$RESTART_LINE")"
    [[ "$n" -eq 1 ]] && ok=0
    CHECK_DIAG="expected exactly 1 restart, saw $n"
    harness_cleanup "$sb"; return $ok
}

check_NO_STACK_TEARDOWN() {
    # Level 1 must NOT recreate the stack -- that is --recreate's job.
    local sb; sb="$(mk "$1" podman podman-compose)"
    harness_run "$sb" --reload-python
    local ok=0
    grep -qE '\|down$|\|up\|-d$' "$sb/argv.log" && ok=1
    CHECK_DIAG="--reload-python must never issue compose down/up: $(grep -E '\|down$|\|up\|-d$' "$sb/argv.log" | tr '\n' ' ')"
    harness_cleanup "$sb"; return $ok
}

check_EXIT_ZERO_AND_LIVE_MSG() {
    local sb; sb="$(mk "$1" podman podman-compose)"
    harness_run "$sb" --reload-python
    local ok=1
    [[ "$HARNESS_RC" -eq 0 ]] && [[ "$HARNESS_OUT" == *"are now live"* ]] && ok=0
    CHECK_DIAG="rc=$HARNESS_RC; success message missing"
    harness_cleanup "$sb"; return $ok
}

check_EXEC_FAILURE_IS_FATAL() {
    # If the cache clear fails, the restart MUST NOT happen: restarting on a
    # stale cache would serve the OLD code while reporting success.
    local sb; sb="$(mk "$1" podman podman-compose)"
    local BOBA_SHIM_FAIL='podman|exec|*'
    harness_run "$sb" --reload-python
    local ok=1
    if [[ "$HARNESS_RC" -ne 0 ]] && ! harness_log_has "$sb" "$RESTART_LINE"; then ok=0; fi
    CHECK_DIAG="rc=$HARNESS_RC; restart-after-failed-cache-clear=$(harness_log_count "$sb" "$RESTART_LINE")"
    harness_cleanup "$sb"; return $ok
}

check_NO_RUNTIME_REFUSES() {
    # No podman AND no docker on PATH -> refuse with a real error, touch nothing.
    local sb; sb="$(mk "$1")"
    harness_run "$sb" --reload-python
    local ok=1
    if [[ "$HARNESS_RC" -eq 1 ]] \
       && [[ "$HARNESS_OUT" == *"No container runtime"* ]] \
       && ! grep -qE '^(podman|docker)\|' "$sb/argv.log"; then ok=0; fi
    CHECK_DIAG="rc=$HARNESS_RC (want 1); runtime calls: $(grep -cE '^(podman|docker)\|' "$sb/argv.log" || true)"
    harness_cleanup "$sb"; return $ok
}

check_PODMAN_PREFERRED_OVER_DOCKER() {
    # Both runtimes available -> podman wins, docker is never driven.
    local sb; sb="$(mk "$1" podman podman-compose docker docker-compose)"
    harness_run "$sb" --reload-python
    local ok=1
    if harness_log_has "$sb" "$RESTART_LINE" && ! grep -q '^docker|' "$sb/argv.log"; then ok=0; fi
    CHECK_DIAG="docker invocations: $(grep '^docker|' "$sb/argv.log" | tr '\n' ' ')"
    harness_cleanup "$sb"; return $ok
}

check_DOCKER_FALLBACK() {
    # podman absent -> docker drives the same two commands.
    local sb; sb="$(mk "$1" docker docker-compose)"
    harness_run "$sb" --reload-python
    local ok=1
    if harness_log_has "$sb" 'docker|restart|qbittorrent-proxy' \
       && harness_log_has "$sb" 'docker|exec|qbittorrent-proxy|find|/config/download-proxy|-name|__pycache__|-type|d|-exec|rm|-rf|{}|+'; then ok=0; fi
    CHECK_DIAG="docker path did not issue both commands"
    harness_cleanup "$sb"; return $ok
}

CHECK_NAMES=(
    CACHE_CLEARED RESTART_ISSUED CACHE_BEFORE_RESTART RESTART_EXACTLY_ONCE
    NO_STACK_TEARDOWN EXIT_ZERO_AND_LIVE_MSG EXEC_FAILURE_IS_FATAL
    NO_RUNTIME_REFUSES PODMAN_PREFERRED_OVER_DOCKER DOCKER_FALLBACK
)
declare -A CHECK_DESC=(
    [CACHE_CLEARED]='clears __pycache__ under /config/download-proxy with the exact find(1) argv'
    [RESTART_ISSUED]='restarts the qbittorrent-proxy container'
    [CACHE_BEFORE_RESTART]='cache clear is ordered BEFORE the restart'
    [RESTART_EXACTLY_ONCE]='restarts exactly once'
    [NO_STACK_TEARDOWN]='never issues compose down/up (that is --recreate)'
    [EXIT_ZERO_AND_LIVE_MSG]='exits 0 and reports the source is live'
    [EXEC_FAILURE_IS_FATAL]='aborts without restarting when the cache clear fails'
    [NO_RUNTIME_REFUSES]='exits 1 with an honest error when no runtime exists'
    [PODMAN_PREFERRED_OVER_DOCKER]='prefers podman and never drives docker'
    [DOCKER_FALLBACK]='falls back to docker when podman is absent'
)
declare -A CHECK_MUTATION=(
    [CACHE_CLEARED]='s#find /config/download-proxy -name __pycache__#find /config/WRONGPATH -name __pycache__#'
    [RESTART_ISSUED]='s#\$CONTAINER_RUNTIME restart qbittorrent-proxy#$CONTAINER_RUNTIME restart WRONGCONTAINER#'
    [CACHE_BEFORE_RESTART]='/print_info "Clearing __pycache__/i \    $CONTAINER_RUNTIME restart qbittorrent-proxy'
    [RESTART_EXACTLY_ONCE]='/are now live/a \    $CONTAINER_RUNTIME restart qbittorrent-proxy'
    [NO_STACK_TEARDOWN]='/print_info "Clearing __pycache__/i \    $COMPOSE_CMD down'
    [EXIT_ZERO_AND_LIVE_MSG]='s/are now live/are stale/'
    [EXEC_FAILURE_IS_FATAL]='/Failed to clear __pycache__/{n;s/exit 1/:/}'
    [NO_RUNTIME_REFUSES]='s/if \[\[ -z "\$CONTAINER_RUNTIME" \]\]; then/if false; then/'
    [PODMAN_PREFERRED_OVER_DOCKER]='s/if command -v podman &> \/dev\/null; then/if command -v podman-ABSENT \&> \/dev\/null; then/'
    [DOCKER_FALLBACK]='s/CONTAINER_RUNTIME="docker"/CONTAINER_RUNTIME="docker-TYPO"/'
)

echo "== start.sh --reload-python (${1:---green}) =="
harness_drive "$([[ "${1:-}" == "--red" ]] && echo red || echo green)"
