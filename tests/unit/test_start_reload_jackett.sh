#!/usr/bin/env bash
# test_start_reload_jackett.sh — behavioural tests for `start.sh
# --reload-jackett` / `--reload-proxy-go`.
#
# Root cause (systematic-debugging, 2026-09-22): boba-jackett and
# qbittorrent-proxy-go are compiled-Go-binary images (source COPIEd + built
# INSIDE the Dockerfile, no bind mount) — unlike download-proxy/src/, a
# source edit is NEVER live on a plain restart. Before this test's subject
# existed, the ONLY path that picked up such a change was --recreate
# (whole-stack down+up); `boba-ctl` (the default orchestrator, cmd/boba-ctl)
# implements no `build` verb at all, so a naive `$COMPOSE_CMD build <svc>`
# under the default mode would silently fail. reload_go_service() bypasses
# boba-ctl and drives REAL_COMPOSE_CMD (podman-compose/docker compose)
# directly for the build step, exactly like reload_python()/reload_plugins()
# already bypass boba-ctl for exec/restart.
#
# Every check drives the REAL entry point (`bash start.sh --reload-jackett`,
# real arg parsing -> real detect_container_runtime -> real
# check_prerequisites -> real reload_go_service) against PATH recorder shims,
# and asserts the exact argv start.sh WOULD have handed the compose tool
# (§11.4.201(11)). No real container is started, stopped, or mutated (§12).
#
# Run:  bash tests/unit/test_start_reload_jackett.sh          # GREEN
#       bash tests/unit/test_start_reload_jackett.sh --red    # §1.1 mutations

# shellcheck disable=SC2034
set -euo pipefail
# shellcheck source=./test_start_reload_harness.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/test_start_reload_harness.sh"

BUILD_LINE='podman-compose|build|boba-jackett'
UP_LINE='podman-compose|up|-d|boba-jackett'
BOBA_CTL_LOG_SUFFIX='repo/scripts/boba-ctl.sh'

RUNNING_ID='38ef117ec563fc347e91573e289107b513bfb321c5d9177f8708516ab3547486'
STALE_ID='2a3173ce19410000000000000000000000000000000000000000000000000000'

# BOB-233 (§11.4.200): reload_go_service now reads the running image back via
# `podman container inspect` / `podman image inspect` and REFUSES when the ids
# are unreadable. A stateless recorder answers those with empty output, which
# is (correctly) an unresolvable signal -- so the `podman` shim here is a
# recorder that ALSO answers the read-back. $2 = image id the fresh build
# resolves to; the running container always reports RUNNING_ID. Equal ids
# model "compose really recreated"; different ids model the BOB-233 stale
# container (podman-compose `up -d` left it on the old image). Every call is
# still recorded in the harness argv.log format.
write_podman_readback_shim() {
    local path="$1" built_id="$2"
    cat > "$path" <<SHIM
#!/usr/bin/env bash
_line="\$(basename "\$0")"; for _a in "\$@"; do _line="\$_line|\$_a"; done
printf '%s\n' "\$_line" >> "\${BOBA_SHIM_LOG:?BOBA_SHIM_LOG unset}"
if [[ "\${1:-}" == container && "\${2:-}" == inspect ]]; then
    case "\${4:-}" in
        '{{.Image}}')        echo '$RUNNING_ID' ;;
        '{{.Config.Image}}') echo "localhost/boba_\${!#}:latest" ;;
        *) exit 2 ;;
    esac
    exit 0
fi
if [[ "\${1:-}" == image && "\${2:-}" == inspect ]]; then echo '$built_id'; exit 0; fi
exit 0
SHIM
    chmod +x "$path"
}

mk() { # $1=mutation  $2..=shim names  (podman => id-consistent read-back shim)
    local mut="$1"; shift
    local sb; sb="$(harness_new_sandbox)"
    local s; for s in "$@"; do harness_add_shim "$sb" "$s"; done
    [[ -f "$sb/bin/podman" ]] && write_podman_readback_shim "$sb/bin/podman" "$RUNNING_ID"
    [[ -n "$mut" ]] && harness_mutate "$sb" "$mut"
    printf '%s\n' "$sb"
}

check_BUILD_ISSUED() {
    local sb; sb="$(mk "$1" podman podman-compose)"
    harness_run "$sb" --reload-jackett
    local ok=1; harness_log_has "$sb" "$BUILD_LINE" && ok=0
    CHECK_DIAG="expected argv: $BUILD_LINE"
    harness_cleanup "$sb"; return $ok
}

check_UP_ISSUED() {
    local sb; sb="$(mk "$1" podman podman-compose)"
    harness_run "$sb" --reload-jackett
    local ok=1; harness_log_has "$sb" "$UP_LINE" && ok=0
    CHECK_DIAG="expected argv: $UP_LINE"
    harness_cleanup "$sb"; return $ok
}

check_BUILD_BEFORE_UP() {
    local sb; sb="$(mk "$1" podman podman-compose)"
    harness_run "$sb" --reload-jackett
    local ok=1; harness_log_before "$sb" "$BUILD_LINE" "$UP_LINE" && ok=0
    CHECK_DIAG="build must happen BEFORE up, else up -d recreates from the stale image"
    harness_cleanup "$sb"; return $ok
}

check_UP_EXACTLY_ONCE() {
    local sb; sb="$(mk "$1" podman podman-compose)"
    harness_run "$sb" --reload-jackett
    local n ok=1; n="$(harness_log_count "$sb" "$UP_LINE")"
    [[ "$n" -eq 1 ]] && ok=0
    CHECK_DIAG="expected exactly 1 up, saw $n"
    harness_cleanup "$sb"; return $ok
}

check_NEVER_USES_BOBA_CTL_FOR_BUILD() {
    # THE root-cause-specific regression: boba-ctl (cmd/boba-ctl) has no
    # `build` verb. If reload_go_service() ever regresses to using
    # $COMPOSE_CMD instead of $REAL_COMPOSE_CMD, the build call would route
    # through the boba-ctl.sh shim instead of podman-compose -- this check
    # asserts the boba-ctl shim log has zero build-shaped lines.
    local sb; sb="$(mk "$1" podman podman-compose)"
    harness_run "$sb" --reload-jackett
    local ok=0
    grep -qE '\|build\|' "$sb/argv.log" 2>/dev/null || true
    if grep -qxF "boba-ctl.sh|build|boba-jackett" "$sb/argv.log"; then ok=1; fi
    CHECK_DIAG="boba-ctl.sh must never receive a build call (it has no build verb): $(grep 'boba-ctl' "$sb/argv.log" | tr '\n' ' ')"
    harness_cleanup "$sb"; return $ok
}

check_NO_STACK_TEARDOWN() {
    # Must NOT recreate the whole stack -- that is --recreate's job.
    local sb; sb="$(mk "$1" podman podman-compose)"
    harness_run "$sb" --reload-jackett
    local ok=0
    grep -qE '\|down$' "$sb/argv.log" && ok=1
    grep -qxF 'podman-compose|up|-d' "$sb/argv.log" && ok=1
    CHECK_DIAG="--reload-jackett must never issue a bare compose down/up (whole-stack): $(grep -E '\|down$|^podman-compose\|up\|-d$' "$sb/argv.log" | tr '\n' ' ')"
    harness_cleanup "$sb"; return $ok
}

check_EXIT_ZERO_AND_LIVE_MSG() {
    local sb; sb="$(mk "$1" podman podman-compose)"
    harness_run "$sb" --reload-jackett
    local ok=1
    [[ "$HARNESS_RC" -eq 0 ]] && [[ "$HARNESS_OUT" == *"are now live"* ]] && ok=0
    CHECK_DIAG="rc=$HARNESS_RC; success message missing"
    harness_cleanup "$sb"; return $ok
}

check_MISMATCH_FAILS_LOUD() {
    # BOB-233: the running container reports a DIFFERENT image than the fresh
    # build, and this recorder compose never recreates anything -- so even the
    # forced recreate leaves it stale. Must exit non-zero with NO success line,
    # after exactly one scoped --force-recreate --no-deps attempt.
    local sb; sb="$(mk "$1" podman podman-compose)"
    write_podman_readback_shim "$sb/bin/podman" "$STALE_ID"
    harness_run "$sb" --reload-jackett
    local ok=1
    if [[ "$HARNESS_RC" -ne 0 && "$HARNESS_OUT" != *"are now live"* ]] \
       && [[ "$(harness_log_count "$sb" 'podman-compose|up|-d|--force-recreate|--no-deps|boba-jackett')" -eq 1 ]]; then ok=0; fi
    CHECK_DIAG="rc=$HARNESS_RC; force-recreates=$(harness_log_count "$sb" 'podman-compose|up|-d|--force-recreate|--no-deps|boba-jackett')"
    harness_cleanup "$sb"; return $ok
}

check_BUILD_FAILURE_IS_FATAL() {
    # If the image rebuild fails, up -d MUST NOT run: recreating from the
    # OLD image would serve stale code while reporting success.
    local sb; sb="$(mk "$1" podman podman-compose)"
    local BOBA_SHIM_FAIL="$BUILD_LINE"
    harness_run "$sb" --reload-jackett
    local ok=1
    if [[ "$HARNESS_RC" -ne 0 ]] && ! harness_log_has "$sb" "$UP_LINE"; then ok=0; fi
    CHECK_DIAG="rc=$HARNESS_RC; up-after-failed-build=$(harness_log_count "$sb" "$UP_LINE")"
    harness_cleanup "$sb"; return $ok
}

check_NO_RUNTIME_REFUSES() {
    # No podman AND no docker on PATH -> refuse with a real error, touch nothing.
    local sb; sb="$(mk "$1")"
    harness_run "$sb" --reload-jackett
    local ok=1
    if [[ "$HARNESS_RC" -eq 1 ]] \
       && [[ "$HARNESS_OUT" == *"No podman-compose/docker-compose"* ]] \
       && ! grep -qE '^podman-compose\|' "$sb/argv.log"; then ok=0; fi
    CHECK_DIAG="rc=$HARNESS_RC (want 1); compose calls: $(grep -cE '^podman-compose\|' "$sb/argv.log" || true)"
    harness_cleanup "$sb"; return $ok
}

check_PROXY_GO_TARGETS_DIFFERENT_SERVICE() {
    # --reload-proxy-go must build/recreate qbittorrent-proxy-go, NOT
    # boba-jackett -- proves the two flags are correctly parametrized rather
    # than both silently targeting the same hardcoded service name.
    local sb; sb="$(mk "$1" podman podman-compose)"
    harness_run "$sb" --reload-proxy-go
    local ok=1
    if harness_log_has "$sb" 'podman-compose|build|qbittorrent-proxy-go' \
       && harness_log_has "$sb" 'podman-compose|up|-d|qbittorrent-proxy-go' \
       && ! harness_log_has "$sb" "$BUILD_LINE"; then ok=0; fi
    CHECK_DIAG="expected qbittorrent-proxy-go build+up, got: $(harness_log "$sb" | tr '\n' ' ')"
    harness_cleanup "$sb"; return $ok
}

CHECK_NAMES=(
    BUILD_ISSUED UP_ISSUED BUILD_BEFORE_UP UP_EXACTLY_ONCE
    NEVER_USES_BOBA_CTL_FOR_BUILD NO_STACK_TEARDOWN EXIT_ZERO_AND_LIVE_MSG
    BUILD_FAILURE_IS_FATAL NO_RUNTIME_REFUSES PROXY_GO_TARGETS_DIFFERENT_SERVICE
    MISMATCH_FAILS_LOUD
)
declare -A CHECK_DESC=(
    [BUILD_ISSUED]='rebuilds the boba-jackett image with the exact compose argv'
    [UP_ISSUED]='recreates the boba-jackett container with the exact compose argv'
    [BUILD_BEFORE_UP]='build is ordered BEFORE up (else up recreates from the stale image)'
    [UP_EXACTLY_ONCE]='recreates exactly once'
    [NEVER_USES_BOBA_CTL_FOR_BUILD]='bypasses boba-ctl for build (it has no build verb) — the root-cause fix'
    [NO_STACK_TEARDOWN]='never issues a bare compose down/up (that is --recreate)'
    [EXIT_ZERO_AND_LIVE_MSG]='exits 0 and reports the source is live'
    [BUILD_FAILURE_IS_FATAL]='aborts without recreating when the image rebuild fails'
    [NO_RUNTIME_REFUSES]='exits 1 with an honest error when no compose tool exists'
    [PROXY_GO_TARGETS_DIFFERENT_SERVICE]='--reload-proxy-go targets qbittorrent-proxy-go, not boba-jackett'
    [MISMATCH_FAILS_LOUD]='BOB-233: running image != fresh build and still stale after a forced recreate -> non-zero exit, no success line'
)
declare -A CHECK_MUTATION=(
    [BUILD_ISSUED]='s#\$REAL_COMPOSE_CMD build "\$service"#$REAL_COMPOSE_CMD build "WRONGSERVICE"#'
    [UP_ISSUED]='s#\$REAL_COMPOSE_CMD up -d "\$service"#$REAL_COMPOSE_CMD up -d "WRONGSERVICE"#'
    [BUILD_BEFORE_UP]='/print_info "Rebuilding \$service image/i \    $REAL_COMPOSE_CMD up -d "$service"'
    [UP_EXACTLY_ONCE]='/are now live/a \    $REAL_COMPOSE_CMD up -d "$service"'
    [NEVER_USES_BOBA_CTL_FOR_BUILD]='s#\$REAL_COMPOSE_CMD build#$COMPOSE_CMD build#'
    [NO_STACK_TEARDOWN]='/print_info "Rebuilding \$service image/i \    $REAL_COMPOSE_CMD up -d'
    [EXIT_ZERO_AND_LIVE_MSG]='s/are now live/are stale/'
    [BUILD_FAILURE_IS_FATAL]='/Failed to rebuild \$service image/{n;s/exit 1/:/}'
    [NO_RUNTIME_REFUSES]='s/if \[\[ -z "\$REAL_COMPOSE_CMD" \]\]; then/if false; then/'
    [PROXY_GO_TARGETS_DIFFERENT_SERVICE]='s/reload_go_service "qbittorrent-proxy-go"/reload_go_service "boba-jackett"/'
    [MISMATCH_FAILS_LOUD]='/after a forced recreate/{n;n;s/exit 1/return 0/}'
)

echo "== start.sh --reload-jackett / --reload-proxy-go (${1:---green}) =="
harness_drive "$([[ "${1:-}" == "--red" ]] && echo red || echo green)"
