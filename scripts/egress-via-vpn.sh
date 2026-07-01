#!/usr/bin/env bash
# scripts/egress-via-vpn.sh — thin Boba glue over the containers submodule's
# egress capability (submodules/containers/pkg/egress). Routes outbound traffic
# through a VPN-connected host so Jackett / download-proxy / qBitTorrent-go /
# plugin engines can reach trackers that are network-blocked from this host.
#
# This is the SHELL diagnosis/operations entry point; the canonical, tested Go
# implementation (used by in-process consumers) is pkg/egress in the containers
# submodule. Both use the same mechanism:
#   ssh -D 127.0.0.1:<port> -N <vpnhost>     (dynamic SOCKS5 forward)
#   curl --socks5-hostname 127.0.0.1:<port>  (remote DNS through the proxy)
#
# The block these solve is ISP/DPI (DNS-fail / TLS-MITM / refused), NOT a
# Cloudflare challenge — so FlareSolverr cannot fix it; a different egress can.
#
# No secrets are echoed or hardcoded. The VPN host + targets come from env / .env
# (gitignored) per CONST no-hardcoding.
#
# Usage:
#   egress-via-vpn.sh up         [--host H] [--port P] [--ssh-port N] [--key K]
#   egress-via-vpn.sh verify     [--port P] [--ip-echo URL] [TARGET_URL ...]
#   egress-via-vpn.sh diagnose   [--host H] [--port P] [TARGET_URL ...]
#   egress-via-vpn.sh down       [--port P]
#
# Env (overridable by flags):
#   BOBA_VPN_HOST            ssh destination of the VPN host (e.g. user@nezha)
#   BOBA_EGRESS_SOCKS_PORT   local SOCKS port (default 1080)
#   BOBA_EGRESS_SSH_PORT     VPN host ssh port (default 22)
#   BOBA_EGRESS_KEY          ssh identity file (optional)
#   BOBA_EGRESS_IP_ECHO      IP-echo URL (default https://api.ipify.org)
#   BOBA_EGRESS_TARGETS      space-separated default target URLs to probe
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Load .env (gitignored) if present, without echoing it.
[[ -f "${PROJECT_ROOT}/.env" ]] && set -a && . "${PROJECT_ROOT}/.env" && set +a

HOST="${BOBA_VPN_HOST:-}"
PORT="${BOBA_EGRESS_SOCKS_PORT:-1080}"
SSH_PORT="${BOBA_EGRESS_SSH_PORT:-22}"
KEY="${BOBA_EGRESS_KEY:-}"
IP_ECHO="${BOBA_EGRESS_IP_ECHO:-https://api.ipify.org}"
BIND="127.0.0.1"
PIDDIR="${XDG_RUNTIME_DIR:-/tmp}/boba-egress"
mkdir -p "$PIDDIR"

cmd="${1:-}"; shift || true
TARGETS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --host) HOST="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    --ssh-port) SSH_PORT="$2"; shift 2 ;;
    --key) KEY="$2"; shift 2 ;;
    --ip-echo) IP_ECHO="$2"; shift 2 ;;
    *) TARGETS+=("$1"); shift ;;
  esac
done
# Fall back to env-provided default targets when none given on the CLI.
if [[ ${#TARGETS[@]} -eq 0 && -n "${BOBA_EGRESS_TARGETS:-}" ]]; then
  read -r -a TARGETS <<< "${BOBA_EGRESS_TARGETS}"
fi

_pidfile() { echo "${PIDDIR}/socks-${PORT}.pid"; }
_socks() { echo "${BIND}:${PORT}"; }

egress_up() {
  [[ -n "$HOST" ]] || { echo "egress: set BOBA_VPN_HOST or pass --host" >&2; exit 2; }
  local key_args=(); [[ -n "$KEY" ]] && key_args=(-i "$KEY")
  echo "[egress] up: SOCKS $(_socks) via ${HOST} (ssh port ${SSH_PORT})"
  ssh -f -N -D "$(_socks)" \
    -o StrictHostKeyChecking=no -o BatchMode=yes \
    -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
    -p "$SSH_PORT" "${key_args[@]}" "$HOST"
  # Record the backgrounded ssh pid bound to this dynamic forward.
  pgrep -f "ssh.*-D $(_socks)" | tail -1 > "$(_pidfile)" || true
  # Wait for the local SOCKS port to accept connections (anti-bluff: do not
  # report success on a dead proxy).
  for _ in $(seq 1 30); do
    if (exec 3<>"/dev/tcp/${BIND}/${PORT}") 2>/dev/null; then exec 3>&- 3<&-; echo "[egress] SOCKS ready on $(_socks)"; return 0; fi
    sleep 0.4
  done
  echo "[egress] SOCKS $(_socks) did not become ready" >&2; exit 1
}

egress_down() {
  local pf; pf="$(_pidfile)"
  if [[ -f "$pf" ]]; then
    local p; p="$(cat "$pf")"; [[ -n "$p" ]] && kill "$p" 2>/dev/null || true
    rm -f "$pf"
  fi
  pkill -f "ssh.*-D $(_socks)" 2>/dev/null || true
  echo "[egress] down: SOCKS $(_socks)"
}

# verify: egress IP through the proxy + per-target HTTP code. Exits non-zero if
# the egress IP cannot be fetched (a dead tunnel is never a green verify).
egress_verify() {
  local ip
  if ! ip="$(curl -fsS --max-time 20 --socks5-hostname "$(_socks)" "$IP_ECHO")"; then
    echo "[egress] FAIL: cannot reach ip-echo via $(_socks) (tunnel dead?)" >&2
    exit 1
  fi
  echo "egress_ip_via_proxy=${ip}"
  local t code
  for t in "${TARGETS[@]:-}"; do
    [[ -z "$t" ]] && continue
    code="$(curl -o /dev/null -s --max-time 25 -w '%{http_code}' --socks5-hostname "$(_socks)" "$t" || echo 000)"
    echo "target ${t} -> ${code}"
  done
}

# diagnose: direct vs via-proxy egress IP + per-target codes (the §0/§4 decision).
egress_diagnose() {
  local direct
  direct="$(curl -fsS --max-time 20 "$IP_ECHO" 2>/dev/null || echo '<direct-failed>')"
  echo "direct_egress_ip=${direct}"
  local t code_direct
  for t in "${TARGETS[@]:-}"; do
    [[ -z "$t" ]] && continue
    code_direct="$(curl -o /dev/null -s --max-time 20 -w '%{http_code}' "$t" || echo 000)"
    echo "direct  ${t} -> ${code_direct}"
  done
  echo "--- via proxy ---"
  egress_verify
}

case "$cmd" in
  up)       egress_up ;;
  down)     egress_down ;;
  verify)   egress_verify ;;
  diagnose) egress_diagnose ;;
  *) echo "usage: egress-via-vpn.sh {up|verify|diagnose|down} [opts] [targets...]" >&2; exit 2 ;;
esac
