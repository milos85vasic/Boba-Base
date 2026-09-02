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
# repo. They are TEMPLATES: every reference to the repo root is written
# as the token @@BOBA_REPO_ROOT@@, which `boba-svc install` substitutes
# with this checkout's real REPO_ROOT while COPYING each unit into
# ~/.config/systemd/user/, then issues daemon-reload.
#
# ─── WHY TEMPLATE + COPY, NOT SYMLINK (defect fixed 2026-09-01) ──────
# Every unit previously hardcoded an absolute
# /run/media/.../Projects/boba prefix that did not exist on this host,
# across WorkingDirectory=, ExecStart=, EnvironmentFile= and
# Documentation= — 14 references in total. Nothing checked it. Such a
# unit installs clean, enables clean, and dies at ACTIVATION on the next
# boot with a bare CHDIR failure: the §11.4.108 source-looks-fine /
# runtime-broken gap. A hardcoded path IS the defect, so the fix is to
# remove the hardcoding rather than correct it to a different constant
# that the next checkout location would break all over again.
#
# Substitution forces COPY: a symlink is a pointer to the template, so
# systemd would read the raw @@BOBA_REPO_ROOT@@ token and fail. The
# tradeoff is accepted deliberately:
#   COST — installed units no longer track repo edits live. Editing a
#          unit under scripts/systemd/user/ now requires re-running
#          `boba-svc install` for the change to reach systemd.
#   BENEFIT — the units are checkout-location-independent. The same repo
#          works from /home/user/Projects/boba, /mnt/track2/boba, a
#          worktree, or any future location, with no edit.
# The cost is a re-run of one idempotent command; the benefit is that
# this entire defect class cannot recur. `boba-svc install` is therefore
# safe to re-run at any time and is the single way units reach systemd.
#
# The drift the COPY introduces is not left to vigilance: `boba-svc
# install` is idempotent and reports whether each unit CHANGED or was
# already current, and tests/pre_build/test_systemd_unit_paths.sh ARM 2
# asserts against the INSTALLED copies — the bytes systemd actually
# reads — not merely against the repo templates.
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
#   install [--copy]  Install unit files into ~/.config/systemd/user/,
#                     substituting @@BOBA_REPO_ROOT@@ with this repo's
#                     real root. Always a COPY (see the template note
#                     above); --copy is accepted as a no-op for
#                     backwards compatibility. Idempotent — safe to
#                     re-run, and required after editing any unit.
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

# The install-time substitution token. Every unit template writes this
# wherever it needs the repo root; _cmd_install replaces it with REPO_ROOT
# above. Kept in a variable so the token appears exactly once as a literal.
BOBA_REPO_ROOT_TOKEN='@@BOBA_REPO_ROOT@@'

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
    # --copy is now the only behaviour (substitution requires a real file,
    # never a symlink). The flag is still accepted so existing docs and
    # muscle memory keep working rather than erroring.
    if [ "${1:-}" = "--copy" ]; then shift; fi
    _require_linux
    mkdir -p "$UNIT_DST"

    local changed=0 unchanged=0
    for u in "${UNITS[@]}"; do
        local src="$UNIT_SRC/$u"
        local dst="$UNIT_DST/$u"
        if [ ! -f "$src" ]; then
            _error "unit source missing: $src"
            exit 1
        fi

        # Render the template into a temp file first, so a failed
        # substitution can never leave a half-written unit where systemd
        # would read it (§11.4.252 fail closed, atomic replace).
        local tmp
        tmp="$(mktemp "${dst}.XXXXXX.tmp")"
        # REPO_ROOT is a filesystem path and may legally contain characters
        # that are special to sed's replacement (& and \). Substituting via
        # awk with a literal index/substr walk avoids that class entirely —
        # no delimiter to collide with (NOTE: awk -v DOES process backslash escapes in the value, so a repo root containing a backslash would be mangled — impossible on Linux paths here, but do not reuse this pattern for arbitrary values).
        if ! awk -v token="$BOBA_REPO_ROOT_TOKEN" -v repl="$REPO_ROOT" '
            {
                out = ""
                line = $0
                while ((i = index(line, token)) > 0) {
                    out = out substr(line, 1, i - 1) repl
                    line = substr(line, i + length(token))
                }
                print out line
            }
        ' "$src" > "$tmp"; then
            rm -f "$tmp"
            _error "failed rendering $u from $src"
            exit 1
        fi

        # FAIL CLOSED: an unsubstituted token means systemd would read a
        # path it cannot expand. Refuse to install it rather than ship a
        # unit that dies at activation (§11.4.201 — assert the real
        # condition; §11.4.252 — refuse rather than proceed).
        if grep -q "$BOBA_REPO_ROOT_TOKEN" "$tmp"; then
            rm -f "$tmp"
            _error "$u still contains $BOBA_REPO_ROOT_TOKEN after substitution — refusing to install"
            _error "  systemd cannot expand that token; installing it would fail at activation."
            exit 1
        fi

        # Idempotency: report CHANGED vs already-current so an operator can
        # see at a glance whether the installed copy had drifted from the
        # repo template.
        if [ -f "$dst" ] && [ ! -L "$dst" ] && cmp -s "$tmp" "$dst"; then
            rm -f "$tmp"
            unchanged=$((unchanged + 1))
            _info "unchanged $u (installed copy already current)"
        else
            # A pre-existing SYMLINK is removed explicitly: mv over a symlink
            # would follow it and write back into the repo.
            [ -L "$dst" ] && rm -f "$dst"
            mv -f "$tmp" "$dst"
            chmod 0644 "$dst"
            changed=$((changed + 1))
            _info "installed $u (copy, @@BOBA_REPO_ROOT@@ → $REPO_ROOT)"
        fi
    done

    systemctl --user daemon-reload
    _info "daemon-reload complete ($changed changed, $unchanged already current)"
    _info "units are COPIES: re-run 'bash $0 install' after editing any unit file."
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
# Units that need their OWN [Install] realised at boot, because nothing
# else pulls them in.
#
# ORPHANED-TIMER DEFECT, MEASURED AND FIXED 2026-09-01
#   boba-stack.service and boba-webui-bridge.service are deliberately left
#   `disabled`: boba.target lists them in Wants=, so enabling the target is
#   what starts them, and enabling them individually would only add a
#   redundant second path to the same thing.
#
#   boba-resource-pressure-check.timer is NOT in that Wants= list — also
#   deliberately, so host-pressure monitoring keeps running while the stack
#   is down. But that deliberate exclusion left it wired to NOTHING:
#   `boba-svc enable` only enabled boba.target, so the timer's own
#   `WantedBy=timers.target` was never realised (verified: no symlink in
#   ~/.config/systemd/user/timers.target.wants/). The hourly
#   forced-logout-precursor probe that task #77 / BOB-076 exists to run
#   would therefore never have fired after a reboot — the monitoring gap
#   the incident itself argued was self-defeating.
#
#   Enabling it here realises WantedBy=timers.target. It stays outside
#   boba.target, so `boba-svc down` still leaves monitoring running.
ENABLE_UNITS=(
    "boba.target"
    "boba-resource-pressure-check.timer"
)

_cmd_enable() {
    _require_linux
    for u in "${ENABLE_UNITS[@]}"; do
        systemctl --user enable "$u"
        _info "$u enabled"
    done
    _info "boba.target auto-starts the stack on login/boot; the timer runs independently of it"
    _cmd_linger_status
}

_cmd_disable() {
    _require_linux
    for u in "${ENABLE_UNITS[@]}"; do
        systemctl --user disable "$u"
        _info "$u disabled"
    done
}
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
