#!/usr/bin/env bash
# scripts/boba-svc.sh — sudo-free systemctl --user wrapper for the boba
# user-space service topology (boba.target + boba-stack.service).
#
# ─── DESIGN ─────────────────────────────────────────────────────────
# Every subcommand goes through `systemctl --user` — the operator's
# systemd session bus, no root, no sudo, no polkit prompt. Linger
# (loginctl show-user <u> -p Linger) is expected to already be `yes` on
# this host — if not, `boba-svc enable` will report it and print the
# operator-run command to enable it (still not run by this script per
# the no-sudo rule).
#
# Source-of-truth unit files live under scripts/systemd/user/ in the
# repo. `boba-svc install` symlinks (or copies, --copy flag) them into
# ~/.config/systemd/user/ + issues daemon-reload. This lets git carry
# the units + the operator's local install match them by construction.
#
# Universal Constitution §11.4.234 posture:
# - Dedicated single entrypoint for the boba service lifecycle.
# - Hooks never block (no git hooks touched here — the systemd
#   integration is the mechanism this wrapper owns).
# - No gate is lost (health probes are an explicit stage; `boba-svc
#   health` runs the same checks the challenge script does).
# - Always-unblocked: every subcommand returns actionable output on
#   failure, never silently hangs. Long stages timeout-bounded.
#
# ─── SUBCOMMANDS ────────────────────────────────────────────────────
#   install [--copy]  Install unit files into ~/.config/systemd/user/.
#                     Symlinks by default; --copy makes hard copies.
#                     Always issues `systemctl --user daemon-reload`.
#   uninstall         Remove the boba-* units and reload.
#   up                systemctl --user start boba.target
#   down              systemctl --user stop  boba.target
#   restart           down + up (sequential, waits for stop to complete)
#   status            systemctl --user status of the target + stack
#   logs [N]          journalctl --user -u boba-stack.service -n ${N:-100}
#   enable            enable boba.target (auto-start at login/boot)
#   disable           disable boba.target
#   reload            systemctl --user daemon-reload
#   health            HTTP probes of every published boba endpoint
#   linger-status     Print whether linger is enabled + how to enable
#                     it if not (never runs sudo itself)
#   help              This help.
#
# ─── EXIT ───────────────────────────────────────────────────────────
#   0 = success (or health all-green)
#   1 = subcommand failed
#   2 = invocation error (unknown subcommand, missing arg)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
UNIT_SRC="$SCRIPT_DIR/systemd/user"
UNIT_DST="$HOME/.config/systemd/user"

# The full unit inventory. When we add more services, extend this list.
#
# INVENTORY DRIFT, MEASURED AND FIXED 2026-08-21 (feature
# 002-user-owned-downloads, T029/T030): the resource-pressure pair was
# installed into ~/.config/systemd/user/ (symlinks dated Aug 18) while
# being absent from this list, so `boba-svc install` did not manage them
# and `boba-svc uninstall` left two dangling symlinks pointing back into
# the repo. The inventory must list every unit shipped in
# scripts/systemd/user/ — that is what makes install/uninstall total.
#
# Listing them here installs and removes them with the rest; it does NOT
# make them part of boba.target. They are deliberately outside the target
# so host resource-pressure monitoring keeps running while the stack is
# down (see the comment in boba-resource-pressure-check.service).
UNITS=(
    "boba.target"
    "boba-stack.service"
    "boba-webui-bridge.service"
    "boba-resource-pressure-check.service"
    "boba-resource-pressure-check.timer"
)

# Health probe targets — { NAME PORT PATH EXPECTED_CODES }.
# EXPECTED_CODES is a `|` pipe-separated list of acceptable HTTP codes.
HEALTH_PROBES=(
    "qBittorrent 7185 /              200|401"
    "Jackett     9117 /UI/Dashboard  200|302"
    "MergeSvc    7187 /health        200"
    "BobaJackett 7189 /healthz       200"
    "WebUIBridge 7188 /bridge/health 200"
)

# ─── log helpers ────────────────────────────────────────────────────
_c_green="$(printf '\033[0;32m')"
_c_yellow="$(printf '\033[1;33m')"
_c_red="$(printf '\033[0;31m')"
_c_reset="$(printf '\033[0m')"
_info()  { printf '%s[boba-svc]%s %s\n' "$_c_green"  "$_c_reset" "$*" >&2; }
_warn()  { printf '%s[boba-svc]%s %s\n' "$_c_yellow" "$_c_reset" "$*" >&2; }
_error() { printf '%s[boba-svc]%s %s\n' "$_c_red"    "$_c_reset" "$*" >&2; }

# ─── platform gate ──────────────────────────────────────────────────
_require_linux() {
    if [ "$(uname -s)" != "Linux" ]; then
        _error "systemctl --user is Linux-only (host=$(uname -s))"
        exit 1
    fi
    if ! command -v systemctl >/dev/null 2>&1; then
        _error "systemctl not on PATH — is systemd installed?"
        exit 1
    fi
    if ! systemctl --user status >/dev/null 2>&1; then
        _error "no user-level systemd session available — try 'systemctl --user status' by hand"
        exit 1
    fi
}

# ─── subcommands ────────────────────────────────────────────────────
_cmd_install() {
    local mode="symlink"
    if [ "${1:-}" = "--copy" ]; then mode="copy"; fi
    _require_linux
    mkdir -p "$UNIT_DST"
    for u in "${UNITS[@]}"; do
        local src="$UNIT_SRC/$u"
        local dst="$UNIT_DST/$u"
        if [ ! -f "$src" ]; then
            _error "unit source missing: $src"
            exit 1
        fi
        rm -f "$dst"
        if [ "$mode" = "copy" ]; then
            cp -f "$src" "$dst"
            _info "installed $u (copy)"
        else
            ln -s "$src" "$dst"
            _info "installed $u (symlink → $src)"
        fi
    done
    systemctl --user daemon-reload
    _info "daemon-reload complete"
    _info "next: bash $0 enable && bash $0 up"
}

_cmd_uninstall() {
    _require_linux
    for u in "${UNITS[@]}"; do
        if [ -e "$UNIT_DST/$u" ] || [ -L "$UNIT_DST/$u" ]; then
            rm -f "$UNIT_DST/$u"
            _info "removed $u"
        fi
    done
    systemctl --user daemon-reload
    _info "daemon-reload complete"
}

# §11.4.234 always-unblocked: refresh cookies from ~/Downloads/cookies_*.txt
# before containers come up so a browser re-export is picked up automatically.
# Loader failure is a WARNING, never a block — the containers still boot with
# whatever cookies .env already holds.
_refresh_cookies_from_downloads() {
    local loader="$SCRIPT_DIR/load-tracker-cookies.sh"
    if [ -x "$loader" ]; then
        _info "refreshing per-tracker cookies from \${TRACKER_COOKIE_DIR:-\$HOME/Downloads}..."
        if ! bash "$loader" 2>&1 | sed 's/^/    /' >&2; then
            _warn "cookie loader had non-zero exit — continuing with existing .env (§11.4.234 always-unblocked)"
        fi
    else
        _warn "cookie loader not found at $loader — skipping cookie refresh"
    fi
}

_cmd_up()      { _require_linux; _refresh_cookies_from_downloads; systemctl --user start   boba.target; _info "boba.target started"; }
_cmd_down()    { _require_linux; systemctl --user stop    boba.target; _info "boba.target stopped"; }
_cmd_enable()  { _require_linux; systemctl --user enable  boba.target; _info "boba.target enabled (auto-start on login/boot)"; _cmd_linger_status; }
_cmd_disable() { _require_linux; systemctl --user disable boba.target; _info "boba.target disabled"; }
_cmd_reload()  { _require_linux; systemctl --user daemon-reload; _info "daemon-reload complete"; }

_cmd_restart() {
    _require_linux
    _info "daemon-reload (in case unit files changed since last session)..."
    systemctl --user daemon-reload || true
    _info "stopping boba.target (tolerating 'Unit not loaded' — nothing to stop is not an error)..."
    # §11.4.234 always-unblocked: a not-loaded / already-stopped state is
    # a legitimate outcome, not a failure. Set +e for this one step so
    # `set -euo pipefail` at the top of the script does not abort restart
    # before the up phase runs.
    set +e
    systemctl --user stop boba.target 2>/dev/null
    stop_rc=$?
    set -e
    if [ "$stop_rc" -ne 0 ]; then
        _warn "systemctl stop returned $stop_rc (probably not loaded / already stopped) — continuing to start phase"
    fi
    # Wait for the stack.service to be fully down (up to 60s).
    for i in $(seq 1 20); do
        local state
        state="$(systemctl --user is-active boba-stack.service 2>/dev/null || true)"
        if [ "$state" != "active" ] && [ "$state" != "activating" ]; then
            break
        fi
        sleep 3
    done
    _refresh_cookies_from_downloads
    _info "starting boba.target..."
    systemctl --user start boba.target
    _info "restart complete"
}

_cmd_status() {
    _require_linux
    systemctl --user --no-pager status boba.target boba-stack.service 2>&1 | head -50
}

_cmd_logs() {
    _require_linux
    local n="${1:-100}"
    journalctl --user -u boba-stack.service -n "$n" --no-pager
}

_cmd_health() {
    _require_linux
    local overall=0
    printf '%-14s %-6s %-15s %s\n' "SERVICE" "PORT" "PATH" "RESULT"
    for probe in "${HEALTH_PROBES[@]}"; do
        local name port path expected
        # shellcheck disable=SC2086
        set -- $probe
        name="$1"; port="$2"; path="$3"; expected="$4"
        local code
        code="$(curl -s -o /dev/null -w '%{http_code}' -m 5 "http://localhost:${port}${path}" || true)"
        if [[ "|${expected}|" == *"|${code}|"* ]]; then
            printf '%-14s %-6s %-15s %sOK%s (HTTP %s)\n' \
                "$name" "$port" "$path" "$_c_green" "$_c_reset" "$code"
        else
            printf '%-14s %-6s %-15s %sFAIL%s (HTTP %s, expected %s)\n' \
                "$name" "$port" "$path" "$_c_red" "$_c_reset" "$code" "$expected"
            overall=1
        fi
    done
    return $overall
}

_cmd_linger_status() {
    local u; u="$(id -un)"
    local ling
    ling="$(loginctl show-user "$u" -p Linger --value 2>/dev/null || echo unknown)"
    if [ "$ling" = "yes" ]; then
        _info "linger for $u = yes — services will start on host boot even without login."
    else
        _warn "linger for $u = $ling"
        _warn "  services will only start when you log in as $u."
        _warn "  to enable boot-time autostart (requires root ONCE, not run by this script):"
        _warn "    sudo loginctl enable-linger $u"
    fi
}

_cmd_help() {
    grep -E '^# {2,}[a-z-]+' "${BASH_SOURCE[0]}" | sed -E 's/^# +//'
}

# ─── dispatch ───────────────────────────────────────────────────────
if [ $# -lt 1 ]; then
    _cmd_help
    exit 2
fi
sub="$1"; shift || true
case "$sub" in
    install)       _cmd_install    "$@" ;;
    uninstall)     _cmd_uninstall  "$@" ;;
    up)            _cmd_up         "$@" ;;
    down)          _cmd_down       "$@" ;;
    restart)       _cmd_restart    "$@" ;;
    status)        _cmd_status     "$@" ;;
    logs)          _cmd_logs       "$@" ;;
    enable)        _cmd_enable     "$@" ;;
    disable)       _cmd_disable    "$@" ;;
    reload)        _cmd_reload     "$@" ;;
    health)        _cmd_health     "$@" ;;
    linger-status) _cmd_linger_status "$@" ;;
    help|-h|--help) _cmd_help ;;
    *) _error "unknown subcommand: $sub"; _cmd_help; exit 2 ;;
esac
