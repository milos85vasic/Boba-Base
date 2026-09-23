#!/usr/bin/env bash
# test_start_reload_verifies_image.sh — BOB-233 regression guard:
# `start.sh --reload-jackett` / `--reload-proxy-go` MUST verify-after-write
# (§11.4.200) that the RUNNING container holds the FRESHLY BUILT image before
# printing success.
#
# Purpose:
#   Measured 2026-09-23 (docs/Issues.md BOB-233): --reload-jackett rebuilt
#   image 38ef117ec563 and printed "[SUCCESS] boba-jackett recreated — Go
#   source changes are now live", while `podman inspect boba-jackett` still
#   showed the OLD image 2a3173ce1941: podman-compose `up -d <svc>` does not
#   recreate a container whose compose config is unchanged. The compose tool's
#   exit 0 proved only that it ran, never that the intended target holds the
#   intended artifact. This suite drives the REAL entry point against a
#   STATEFUL stub runtime + stub compose that model exactly that behaviour.
#
# Usage:   bash tests/unit/test_start_reload_verifies_image.sh          # GREEN
#          bash tests/unit/test_start_reload_verifies_image.sh --red    # §1.1
# Inputs:  none (all state lives under a mktemp sandbox).
# Outputs: PASS:/FAIL:/RED-OK:/BLUFF: lines + a RESULT line on stdout.
# Exit:    0 every check behaved as specified | non-zero otherwise.
# Side-effects: none outside the mktemp sandbox. Real podman/docker are
#   UNREACHABLE (sanitized PATH from test_start_reload_harness.sh); the live
#   stack is never inspected, restarted, stopped or recreated (§12).
# Dependencies: bash, coreutils, tests/unit/test_start_reload_harness.sh.
# Cross-references: BOB-233, §11.4.200 (verify-after-write on the intended
#   target), §11.4.201 (guard asserts the real condition; unresolvable signal
#   -> conservative refusal), §11.4.115 (RED on the broken artifact),
#   §11.4.224 (test-first), §1.1 (paired mutations), docs/scripts/start.md.

# shellcheck disable=SC2034
set -euo pipefail
# shellcheck source=./test_start_reload_harness.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/test_start_reload_harness.sh"

OLD_ID='2a3173ce19410000000000000000000000000000000000000000000000000000'
NEW_ID='38ef117ec563fc347e91573e289107b513bfb321c5d9177f8708516ab3547486'

# Stateful stub, installed under BOTH names (podman, podman-compose) and
# dispatched on basename. State: $BOBA_STUB_STATE/{image,container}_<svc>.
#   podman-compose build <svc>            -> image_<svc> := NEW_ID
#   podman-compose up -d <svc>            -> container := image  iff UP_MODE=recreate
#   podman-compose up ... --force-recreate -> container := image iff FORCE_MODE=recreate
#   podman container inspect --format '{{.Image}}'        <svc> -> container id
#   podman container inspect --format '{{.Config.Image}}' <svc> -> image ref
#   podman image inspect --format '{{.Id}}' <ref>                -> image id
# Every call is also recorded pipe-joined in $BOBA_SHIM_LOG (harness format).
write_stateful_stub() {
    local path="$1"
    cat > "$path" <<'STUB'
#!/usr/bin/env bash
_n="$(basename "$0")"
_line="$_n"; for _a in "$@"; do _line="$_line|$_a"; done
printf '%s\n' "$_line" >> "${BOBA_SHIM_LOG:?}"
st="${BOBA_STUB_STATE:?}"
svc="${!#}"                                   # last argv token
case "$_n" in
  podman-compose)
    case "$1" in
      build) printf '%s' "${BOBA_STUB_NEW_ID:?}" > "$st/image_$svc"; exit 0 ;;
      up)
        mode="${BOBA_STUB_UP_MODE:-stale}"
        [[ " $* " == *" --force-recreate "* ]] && mode="${BOBA_STUB_FORCE_MODE:-stale}"
        if [[ "$mode" == recreate && -f "$st/image_$svc" ]]; then
            cp "$st/image_$svc" "$st/container_$svc"
        fi
        exit 0 ;;
      *) exit 0 ;;
    esac ;;
  podman|docker)
    if [[ "$1" == container && "$2" == inspect ]]; then
        [[ "${BOBA_STUB_NO_CONTAINER:-0}" == 1 ]] && { echo "Error: no such container $svc" >&2; exit 125; }
        [[ -f "$st/container_$svc" ]] || { echo "Error: no such container $svc" >&2; exit 125; }
        case "$4" in
          '{{.Image}}')        cat "$st/container_$svc"; echo ;;
          '{{.Config.Image}}') echo "localhost/boba_$svc:latest" ;;
          *) exit 2 ;;
        esac
        exit 0
    fi
    if [[ "$1" == image && "$2" == inspect ]]; then
        ref="$svc"; s="${ref#localhost/boba_}"; s="${s%:latest}"
        [[ -f "$st/image_$s" ]] || { echo "Error: no such image $ref" >&2; exit 125; }
        [[ "${BOBA_STUB_SHA_PREFIX:-0}" == 1 ]] && printf 'sha256:'
        cat "$st/image_$s"; echo
        exit 0
    fi
    exit 0 ;;
esac
exit 0
STUB
    chmod +x "$path"
}

# $1 = mutation ('' for pristine), $2 = service. Container+image start on OLD.
mk() {
    local sb; sb="$(harness_new_sandbox)"
    write_stateful_stub "$sb/bin/podman"
    write_stateful_stub "$sb/bin/podman-compose"
    mkdir -p "$sb/state"
    printf '%s' "$OLD_ID" > "$sb/state/image_$2"
    printf '%s' "$OLD_ID" > "$sb/state/container_$2"
    [[ -n "$1" ]] && harness_mutate "$sb" "$1"
    printf '%s\n' "$sb"
}

# $1 sandbox, $2 flag; env knobs forwarded explicitly (never inherited blindly).
run_stub() {
    local sb="$1" flag="$2" out rc=0
    set +e
    out="$(
        cd "$sb/repo" && \
        PATH="$sb/bin:$sb/sysbin" HOME="$sb/home" \
        BOBA_SHIM_LOG="$sb/argv.log" BOBA_STUB_STATE="$sb/state" \
        BOBA_STUB_NEW_ID="$NEW_ID" \
        BOBA_STUB_UP_MODE="${UP_MODE:-stale}" \
        BOBA_STUB_FORCE_MODE="${FORCE_MODE:-stale}" \
        BOBA_STUB_NO_CONTAINER="${NO_CONTAINER:-0}" \
        BOBA_STUB_SHA_PREFIX="${SHA_PREFIX:-0}" \
        bash "$sb/repo/start.sh" "$flag" 2>&1
    )"
    rc=$?
    set -e
    HARNESS_OUT="$out"; HARNESS_RC="$rc"
}

running_id() { cat "$1/state/container_$2"; }
force_line() { printf 'podman-compose|up|-d|--force-recreate|--no-deps|%s' "$1"; }

# THE BOB-233 repro: `up -d` leaves the old container; the fix must notice
# and force a scoped recreate, ending with the running container on NEW_ID.
check_STALE_UP_IS_FORCE_RECREATED() {
    local sb; sb="$(mk "$1" boba-jackett)"
    UP_MODE=stale FORCE_MODE=recreate run_stub "$sb" --reload-jackett
    local ok=1 rid; rid="$(running_id "$sb" boba-jackett)"
    if [[ "$HARNESS_RC" -eq 0 && "$rid" == "$NEW_ID" ]] \
       && harness_log_has "$sb" "$(force_line boba-jackett)"; then ok=0; fi
    CHECK_DIAG="rc=$HARNESS_RC running=${rid:0:12} (want ${NEW_ID:0:12}); force-recreate issued=$(harness_log_count "$sb" "$(force_line boba-jackett)")"
    harness_cleanup "$sb"; return $ok
}

# If even the forced recreate leaves the old image running: FAIL loudly,
# never print the "now live" success line (§11.4.200 / §11.4.201).
check_STILL_STALE_FAILS_LOUD() {
    local sb; sb="$(mk "$1" boba-jackett)"
    UP_MODE=stale FORCE_MODE=stale run_stub "$sb" --reload-jackett
    local ok=1
    if [[ "$HARNESS_RC" -ne 0 && "$HARNESS_OUT" != *"are now live"* \
          && "$HARNESS_OUT" == *"[ERROR]"* \
          && "$HARNESS_OUT" == *"${OLD_ID:0:12}"* && "$HARNESS_OUT" == *"${NEW_ID:0:12}"* ]]; then ok=0; fi
    CHECK_DIAG="rc=$HARNESS_RC; output tail: $(printf '%s' "$HARNESS_OUT" | tail -3 | tr '\n' ' ')"
    harness_cleanup "$sb"; return $ok
}

# Golden-FALSE (§11.4.201(1)): a compose that DOES recreate must not trigger a
# second, unnecessary forced recreate, and must succeed.
check_HEALTHY_UP_NO_FORCE() {
    local sb; sb="$(mk "$1" boba-jackett)"
    UP_MODE=recreate run_stub "$sb" --reload-jackett
    local ok=1
    if [[ "$HARNESS_RC" -eq 0 && "$HARNESS_OUT" == *"are now live"* ]] \
       && ! grep -q -- '--force-recreate' "$sb/argv.log"; then ok=0; fi
    CHECK_DIAG="rc=$HARNESS_RC; force-recreate calls=$(grep -c -- '--force-recreate' "$sb/argv.log" || true)"
    harness_cleanup "$sb"; return $ok
}

# Golden-FALSE: docker reports 'sha256:<id>' for images but podman does not;
# the comparison must normalize, not false-refuse a correct recreate.
check_SHA_PREFIX_NORMALIZED() {
    local sb; sb="$(mk "$1" boba-jackett)"
    UP_MODE=recreate SHA_PREFIX=1 run_stub "$sb" --reload-jackett
    local ok=1
    if [[ "$HARNESS_RC" -eq 0 ]] && ! grep -q -- '--force-recreate' "$sb/argv.log"; then ok=0; fi
    CHECK_DIAG="rc=$HARNESS_RC; force-recreate calls=$(grep -c -- '--force-recreate' "$sb/argv.log" || true)"
    harness_cleanup "$sb"; return $ok
}

# Unresolvable signal (no container to read back) -> conservative refusal,
# never a success claim (§11.4.201(4)).
check_UNRESOLVABLE_FAILS_LOUD() {
    local sb; sb="$(mk "$1" boba-jackett)"
    UP_MODE=recreate NO_CONTAINER=1 run_stub "$sb" --reload-jackett
    local ok=1
    if [[ "$HARNESS_RC" -ne 0 && "$HARNESS_OUT" != *"are now live"* ]]; then ok=0; fi
    CHECK_DIAG="rc=$HARNESS_RC; output tail: $(printf '%s' "$HARNESS_OUT" | tail -2 | tr '\n' ' ')"
    harness_cleanup "$sb"; return $ok
}

# Same guarantee for --reload-proxy-go, scoped to ITS service.
check_PROXY_GO_VERIFIED() {
    local sb; sb="$(mk "$1" qbittorrent-proxy-go)"
    UP_MODE=stale FORCE_MODE=recreate run_stub "$sb" --reload-proxy-go
    local ok=1 rid; rid="$(running_id "$sb" qbittorrent-proxy-go)"
    if [[ "$HARNESS_RC" -eq 0 && "$rid" == "$NEW_ID" ]] \
       && harness_log_has "$sb" "$(force_line qbittorrent-proxy-go)" \
       && ! grep -q 'boba-jackett' "$sb/argv.log"; then ok=0; fi
    CHECK_DIAG="rc=$HARNESS_RC running=${rid:0:12}; log: $(tr '\n' ' ' < "$sb/argv.log")"
    harness_cleanup "$sb"; return $ok
}

CHECK_NAMES=(
    STALE_UP_IS_FORCE_RECREATED STILL_STALE_FAILS_LOUD HEALTHY_UP_NO_FORCE
    SHA_PREFIX_NORMALIZED UNRESOLVABLE_FAILS_LOUD PROXY_GO_VERIFIED
)
declare -A CHECK_DESC=(
    [STALE_UP_IS_FORCE_RECREATED]='BOB-233 repro: stale `up -d` is detected and force-recreated onto the new image'
    [STILL_STALE_FAILS_LOUD]='still-stale after forced recreate -> non-zero exit, both image ids printed, no success line'
    [HEALTHY_UP_NO_FORCE]='golden-FALSE: correct recreate -> success, no extra forced recreate'
    [SHA_PREFIX_NORMALIZED]='golden-FALSE: sha256: prefix difference is not a mismatch'
    [UNRESOLVABLE_FAILS_LOUD]='unreadable running image id -> refuse, never claim success'
    [PROXY_GO_VERIFIED]='--reload-proxy-go gets the same verify+force, scoped to its own service'
)
declare -A CHECK_MUTATION=(
    [STALE_UP_IS_FORCE_RECREATED]='s#up -d --force-recreate --no-deps "\$service"#up -d "$service"#'
    [STILL_STALE_FAILS_LOUD]='/after a forced recreate/{n;n;s/exit 1/return 0/}'
    [HEALTHY_UP_NO_FORCE]='s#if ! _go_service_image_matches "\$service"; then#if true; then#'
    [SHA_PREFIX_NORMALIZED]='s#_GO_BUILT_ID="\${_GO_BUILT_ID\#sha256:}"#:#'
    [UNRESOLVABLE_FAILS_LOUD]='/Cannot read back the running image/{n;s/exit 1/return 0/}'
    [PROXY_GO_VERIFIED]='s/reload_go_service "qbittorrent-proxy-go"/reload_go_service "boba-jackett"/'
)

echo "== BOB-233 start.sh reload verify-after-write (${1:---green}) =="
harness_drive "$([[ "${1:-}" == "--red" ]] && echo red || echo green)"
