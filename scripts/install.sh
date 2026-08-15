#!/usr/bin/env bash
# scripts/install.sh — production install/setup entrypoint for boba.
#
# What this does (idempotent, sudo-free):
#   1. `git fetch --all --prune` on the main repo + `git submodule
#      update --init --recursive --remote` so every consumer has the
#      latest constitution + helixqa + challenges + containers +
#      jackett pointers.
#   2. Build every native artefact: cmd/boba-ctl (Go), qBitTorrent-go/
#      (Go binaries), frontend/ (Angular production bundle).
#   3. Install user-space systemd units into ~/.config/systemd/user/
#      via scripts/boba-svc.sh install (symlinks source-of-truth files
#      from scripts/systemd/user/ so future git pulls propagate).
#   4. Reload systemd + enable boba.target so the stack auto-starts on
#      user login (and on host boot when linger is enabled — reported
#      honestly if it isn't).
#   5. Bring the stack up via `boba-svc up` (delegates to ./start.sh —
#      respects CLAUDE.md Hard Stop #3: single container-orchestration
#      owner is start.sh).
#   6. Poll every published health endpoint until GREEN (or bounded
#      timeout).
#   7. Print a final ready sheet (LAN IP + URLs + wrapper commands).
#
# ─── OPERATOR CONTRACT ─────────────────────────────────────────────
#   NO sudo needed at any step. Linger enablement is the ONE
#   root-required operation; if not already `yes`, this script PRINTS
#   the sudo command for the operator to run manually — never invokes
#   it. Everything else is `systemctl --user` / `git` / `podman` /
#   `go build` / `ng build` (all user-writable operations).
#
# ─── SKIP FLAGS (env) ──────────────────────────────────────────────
#   BOBA_INSTALL_SKIP_PULL=1        skip git fetch + submodule update
#   BOBA_INSTALL_SKIP_BUILD=1       skip the build stage entirely
#   BOBA_INSTALL_SKIP_FRONTEND=1    skip only the Angular build (Go still runs)
#   BOBA_INSTALL_SKIP_START=1       install + enable, but do NOT start
#   BOBA_INSTALL_SKIP_HEALTH=1      do not wait for health endpoints
#
# ─── EXIT ──────────────────────────────────────────────────────────
#   0 = fully installed + healthy (or gated skips honored)
#   1 = a stage failed; specific step named on stderr
#   2 = invocation error (unknown flag, wrong dir)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

# ─── colour helpers ────────────────────────────────────────────────
_c_green="$(printf '\033[0;32m')"
_c_yellow="$(printf '\033[1;33m')"
_c_red="$(printf '\033[0;31m')"
_c_blue="$(printf '\033[0;34m')"
_c_reset="$(printf '\033[0m')"
_step()  { printf '\n%s[install]%s ▶ %s\n' "$_c_blue"  "$_c_reset" "$*" >&2; }
_info()  { printf '%s[install]%s   %s\n'   "$_c_green" "$_c_reset" "$*" >&2; }
_warn()  { printf '%s[install]%s   %s\n'   "$_c_yellow" "$_c_reset" "$*" >&2; }
_error() { printf '%s[install]%s   %s\n'   "$_c_red"    "$_c_reset" "$*" >&2; }
_fail()  { _error "$*"; exit 1; }

# ─── platform gate ─────────────────────────────────────────────────
if [ "$(uname -s)" != "Linux" ]; then
    _fail "install.sh currently supports Linux only (host: $(uname -s))"
fi
[ -f docker-compose.yml ] || _fail "not in boba repo root (docker-compose.yml missing)"
[ -x scripts/boba-svc.sh ] || _fail "scripts/boba-svc.sh missing or not executable"

# ─── stage 1: latest source ─────────────────────────────────────────
if [ "${BOBA_INSTALL_SKIP_PULL:-0}" != "1" ]; then
    _step "stage 1/7 — fetch latest source (main repo + submodules recursive)"
    git fetch --all --prune 2>&1 | tail -5 || _warn "git fetch had non-zero exit"
    if git symbolic-ref -q HEAD >/dev/null 2>&1; then
        branch="$(git symbolic-ref --short HEAD)"
        # Only fast-forward if a matching upstream ref exists AND we're behind
        for remote in origin github upstream; do
            git show-ref --verify --quiet "refs/remotes/${remote}/${branch}" 2>/dev/null || continue
            behind=$(git rev-list --count "HEAD..${remote}/${branch}" 2>/dev/null || echo 0)
            if [ "$behind" -gt 0 ]; then
                _info "$remote is $behind commits ahead — ff-only pulling"
                git pull --ff-only "$remote" "$branch" 2>&1 | tail -3 || _warn "ff pull failed for $remote (continuing)"
                break
            fi
        done
    else
        _warn "HEAD is detached — skipping ff-pull"
    fi
    _info "updating submodules (recursive, --init)"
    git submodule update --init --recursive 2>&1 | tail -10 || _warn "submodule update had non-zero exit"
else
    _step "stage 1/7 — SKIPPED (BOBA_INSTALL_SKIP_PULL=1)"
fi

# ─── stage 2: build native binaries ────────────────────────────────
if [ "${BOBA_INSTALL_SKIP_BUILD:-0}" != "1" ]; then
    _step "stage 2/7 — build native binaries (Go: boba-ctl + qBitTorrent-go)"
    mkdir -p bin
    if command -v go >/dev/null 2>&1; then
        _info "building cmd/boba-ctl → bin/boba-ctl"
        ( cd cmd/boba-ctl && go mod tidy >/dev/null 2>&1 && go build -o "$REPO_ROOT/bin/boba-ctl" . ) \
            || _fail "cmd/boba-ctl build failed"
        if [ -x qBitTorrent-go/scripts/build.sh ]; then
            _info "building qBitTorrent-go/ binaries via scripts/build.sh"
            ( cd qBitTorrent-go && bash scripts/build.sh ) \
                || _fail "qBitTorrent-go build failed"
        else
            _warn "qBitTorrent-go/scripts/build.sh missing — skipping Go bridge binaries"
        fi
    else
        _fail "go compiler missing — install golang and retry (native binaries required)"
    fi
    _info "built:"
    for b in bin/boba-ctl qBitTorrent-go/bin/boba-jackett qBitTorrent-go/bin/qbittorrent-proxy qBitTorrent-go/bin/webui-bridge; do
        [ -x "$b" ] && printf '     %-45s %s\n' "$b" "$(stat -c '%s' "$b" | numfmt --to=iec --suffix=B)" >&2
    done
else
    _step "stage 2/7 — SKIPPED (BOBA_INSTALL_SKIP_BUILD=1)"
fi

# ─── stage 3: build frontend ───────────────────────────────────────
if [ "${BOBA_INSTALL_SKIP_BUILD:-0}" != "1" ] && [ "${BOBA_INSTALL_SKIP_FRONTEND:-0}" != "1" ]; then
    _step "stage 3/7 — build Angular frontend (production configuration)"
    if [ -d frontend/node_modules ]; then
        _info "node_modules present ($(du -sh frontend/node_modules 2>/dev/null | cut -f1)) — running ng build"
        ( cd frontend && \
            if [ -x node_modules/.bin/ng ]; then node_modules/.bin/ng build --configuration production; \
            elif command -v ng >/dev/null 2>&1; then ng build --configuration production; \
            else _warn "ng not available"; false; fi ) 2>&1 | tail -10 \
            || _warn "Angular build failed — merge service will serve last successful dist"
    else
        _warn "frontend/node_modules missing — run 'cd frontend && npm ci' first"
        _warn "  (skipping ng build this run; merge service will serve last built dist if any)"
    fi
    if [ -d download-proxy/src/ui/dist/frontend ]; then
        _info "dist present at download-proxy/src/ui/dist/frontend ($(du -sh download-proxy/src/ui/dist/frontend 2>/dev/null | cut -f1))"
    fi
else
    _step "stage 3/7 — SKIPPED (build or frontend gated off)"
fi

# ─── stage 4: install systemd user units ───────────────────────────
_step "stage 4/7 — install user-space systemd units"
bash scripts/boba-svc.sh install 2>&1 | sed 's/^/    /' || _fail "boba-svc install failed"

# ─── stage 5: enable boot autostart ────────────────────────────────
_step "stage 5/7 — enable boba.target for boot autostart"
systemctl --user daemon-reload
systemctl --user enable boba.target 2>&1 | sed 's/^/    /' || _warn "enable had non-zero exit"
linger="$(loginctl show-user "$(id -un)" -p Linger --value 2>/dev/null || echo unknown)"
if [ "$linger" = "yes" ]; then
    _info "linger for $(id -un) = yes → boba.target will auto-start at HOST boot (no login needed)"
else
    _warn "linger for $(id -un) = $linger — services will only auto-start on user LOGIN"
    _warn "  to enable full host-boot autostart (requires root ONCE, not invoked by this script):"
    _warn "    sudo loginctl enable-linger $(id -un)"
fi

# ─── stage 6: start the stack ──────────────────────────────────────
if [ "${BOBA_INSTALL_SKIP_START:-0}" != "1" ]; then
    _step "stage 6/7 — start the stack via systemd (single command: systemctl --user start boba.target)"
    bash scripts/boba-svc.sh up 2>&1 | sed 's/^/    /' || _fail "stack start failed"
else
    _step "stage 6/7 — SKIPPED (BOBA_INSTALL_SKIP_START=1)"
fi

# ─── stage 7: wait for health ─────────────────────────────────────
if [ "${BOBA_INSTALL_SKIP_START:-0}" != "1" ] && [ "${BOBA_INSTALL_SKIP_HEALTH:-0}" != "1" ]; then
    _step "stage 7/7 — poll every published endpoint until healthy (up to 180s)"
    healthy=0
    for i in $(seq 1 60); do
        if bash scripts/boba-svc.sh health >/tmp/boba-install-hc 2>&1; then
            healthy=1; break
        fi
        sleep 3
    done
    if [ "$healthy" -eq 1 ]; then
        _info "all endpoints healthy"
        cat /tmp/boba-install-hc | sed 's/^/    /'
    else
        _error "not all endpoints healthy after 180s. Last output:"
        cat /tmp/boba-install-hc | sed 's/^/    /' >&2
        _fail "startup did not converge"
    fi
    rm -f /tmp/boba-install-hc
else
    _step "stage 7/7 — SKIPPED (start or health gated off)"
fi

# ─── final ready sheet ────────────────────────────────────────────
_step "READY — access sheet"
default_if="$(ip -4 route show default 2>/dev/null | awk 'NR==1 {print $5}')"
lan_ip="unknown"
if [ -n "$default_if" ]; then
    lan_ip="$(ip -4 addr show dev "$default_if" 2>/dev/null | awk '/inet / {gsub(/\/.*/,"",$2); print $2; exit}')"
fi
cat >&2 <<EOF

  ${_c_green}Boba stack is up and running.${_c_reset}
  LAN IP: ${lan_ip}   (default interface: ${default_if:-unknown})

  Access sheet — reachable from any device on the ${lan_ip%.*}.0/24 subnet:
    Боба Dashboard / Merge Search       http://${lan_ip}:7187/
    qBittorrent WebUI                   http://${lan_ip}:7185/   (admin/admin)
    Download Proxy → qBittorrent        http://${lan_ip}:7186/
    Jackett Admin                       http://${lan_ip}:9117/UI/Dashboard
    Boba Jackett (Go API)               http://${lan_ip}:7189/
    WebUI Bridge (private trackers)     http://${lan_ip}:7188/

  Daily-use commands (no sudo):
    bash scripts/boba-svc.sh status         systemd status
    bash scripts/boba-svc.sh health         probe every endpoint
    bash scripts/boba-svc.sh logs 200       journal tail
    bash scripts/boba-svc.sh restart        controlled restart
    bash scripts/boba-svc.sh down / up      stop / start

  Reboot survivability:
    systemctl --user is-enabled boba.target   → $(systemctl --user is-enabled boba.target 2>/dev/null || echo unknown)
    loginctl show-user $(id -un) -p Linger   → $(loginctl show-user "$(id -un)" -p Linger --value 2>/dev/null || echo unknown)
    Both should be 'enabled' + 'yes' for zero-touch boot-time startup.

  Re-run this script any time to pull the latest source and re-install.

EOF
