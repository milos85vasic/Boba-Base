#!/usr/bin/env bash
# tunnel-keepalive.sh — self-healing supervisor for the macOS podman SSH tunnel.
#
# Purpose:
#   Keep the Boba dashboard stack (ports 7186/7187/7189/9117) continuously
#   reachable on the macOS host. The SSH tunnel created by
#   ensure-macos-tunnel.sh occasionally dies (connection drop). This
#   supervisor polls the canonical health port (7187) on a fixed interval
#   and, whenever it becomes unreachable, re-runs ensure-macos-tunnel.sh to
#   re-establish all four forwards — so the operator's dashboard auto-heals
#   instead of silently staying offline.
#
# Usage:
#   scripts/tunnel-keepalive.sh                 # run in foreground (Ctrl-C to stop)
#   nohup scripts/tunnel-keepalive.sh >/dev/null 2>&1 & disown   # background
#   TUNNEL_BIND_ADDR=0.0.0.0 scripts/tunnel-keepalive.sh         # LAN-exposed stack
#
# Inputs (environment):
#   TUNNEL_BIND_ADDR   Bind address passed through to ensure-macos-tunnel.sh
#                      (default 127.0.0.1). The health check always probes
#                      127.0.0.1 — that loopback is reachable for both the
#                      127.0.0.1 and 0.0.0.0 binds.
#   KEEPALIVE_INTERVAL Seconds between health checks (default 10).
#   KEEPALIVE_HEALTH_PORT  Port used for the reachability probe (default 7187).
#   KEEPALIVE_LOG      Logfile path (default <project>/qa-results/tunnel-keepalive.log).
#
# Outputs:
#   Timestamped lines appended to the logfile: startup, every detected
#   outage, every re-establish attempt + its result, and clean shutdown.
#
# Side-effects:
#   - Writes a pidfile (.git/.tunnel-keepalive.pid by default, falls back to
#     the project root) so a second supervisor refuses to start (single-owner).
#   - Invokes ensure-macos-tunnel.sh ONLY when 7187 is unreachable; that
#     helper kills + recreates the SSH tunnel processes for the four ports.
#   - Appends to the logfile under qa-results/.
#   - Does NOT touch containers, git, or any other file.
#
# Dependencies:
#   bash, curl (preferred) or nc, sleep, mkdir, date; ensure-macos-tunnel.sh
#   in the same scripts/ directory.
#
# Cross-references:
#   scripts/ensure-macos-tunnel.sh   (the (re)establish mechanism)
#   docs/scripts/tunnel-keepalive.md (companion user guide)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENSURE_SCRIPT="$SCRIPT_DIR/ensure-macos-tunnel.sh"

INTERVAL="${KEEPALIVE_INTERVAL:-10}"
HEALTH_PORT="${KEEPALIVE_HEALTH_PORT:-7187}"
BIND_ADDR="${TUNNEL_BIND_ADDR:-127.0.0.1}"
LOG_FILE="${KEEPALIVE_LOG:-$PROJECT_ROOT/qa-results/tunnel-keepalive.log}"

# Single-owner pidfile. Prefer .git/ (already gitignored); fall back to root.
if [ -d "$PROJECT_ROOT/.git" ]; then
  PID_FILE="$PROJECT_ROOT/.git/.tunnel-keepalive.pid"
else
  PID_FILE="$PROJECT_ROOT/.tunnel-keepalive.pid"
fi

log() {
  # Timestamped append; also echo to stdout for foreground runs.
  msg="$(date '+%Y-%m-%dT%H:%M:%S%z') [tunnel-keepalive] $*"
  printf '%s\n' "$msg" >>"$LOG_FILE"
  printf '%s\n' "$msg"
}

cleanup() {
  # Only remove the pidfile if it is ours.
  if [ -f "$PID_FILE" ] && [ "$(cat "$PID_FILE" 2>/dev/null || true)" = "$$" ]; then
    rm -f "$PID_FILE"
  fi
  log "supervisor stopped (pid $$)"
}

# Reachability probe of 127.0.0.1:<port>. Returns 0 if up, 1 if down.
is_up() {
  if command -v curl >/dev/null 2>&1; then
    curl -s -o /dev/null --max-time 3 "http://127.0.0.1:${HEALTH_PORT}"
    return $?
  elif command -v nc >/dev/null 2>&1; then
    nc -z -G 3 127.0.0.1 "$HEALTH_PORT" >/dev/null 2>&1
    return $?
  else
    # No probe tool available — fail closed so we don't pretend it's up.
    return 1
  fi
}

main() {
  mkdir -p "$(dirname "$LOG_FILE")"

  # Single-owner guard: if a live supervisor already holds the pidfile, exit.
  if [ -f "$PID_FILE" ]; then
    existing="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [ -n "$existing" ] && kill -0 "$existing" 2>/dev/null; then
      log "another supervisor is already running (pid $existing) — exiting"
      exit 0
    fi
    # Stale pidfile — reclaim it.
    log "removing stale pidfile (pid ${existing:-unknown} not alive)"
    rm -f "$PID_FILE"
  fi

  printf '%s\n' "$$" >"$PID_FILE"
  trap cleanup EXIT INT TERM

  if [ ! -x "$ENSURE_SCRIPT" ] && [ ! -f "$ENSURE_SCRIPT" ]; then
    log "FATAL: ensure-macos-tunnel.sh not found at $ENSURE_SCRIPT"
    exit 1
  fi

  log "supervisor started (pid $$) — port $HEALTH_PORT every ${INTERVAL}s, bind $BIND_ADDR, log $LOG_FILE"

  while true; do
    if ! is_up; then
      log "health check FAILED on 127.0.0.1:${HEALTH_PORT} — re-establishing tunnel"
      if TUNNEL_BIND_ADDR="$BIND_ADDR" bash "$ENSURE_SCRIPT" >>"$LOG_FILE" 2>&1; then
        if is_up; then
          log "tunnel re-established — 127.0.0.1:${HEALTH_PORT} is reachable again"
        else
          log "ensure script ran but 127.0.0.1:${HEALTH_PORT} still down — will retry"
        fi
      else
        log "ensure-macos-tunnel.sh exited non-zero — will retry next cycle"
      fi
    fi
    sleep "$INTERVAL"
  done
}

main "$@"
