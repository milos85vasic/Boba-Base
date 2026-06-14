#!/usr/bin/env bash
# ensure-macos-tunnel.sh — macOS podman host-network SSH tunnel.
#
# Podman on macOS with `network_mode: host` does not forward container
# ports to the macOS host. This script creates SSH tunnels from the
# podman machine VM to localhost for the required ports.
#
# Ports forwarded:
#   7186  — Download proxy (→ qBittorrent WebUI)
#   7187  — Merge Search Service (FastAPI + Angular SPA)
#   7189  — boba-jackett management API
#   9117  — Jackett indexer API
#
# Safe to run multiple times — kills stale tunnels and recreates them.

set -euo pipefail

PORTS=(7186 7187 7189 9117)
# Bind address for the local forwards. Default 127.0.0.1 (localhost-only, safe).
# Set TUNNEL_BIND_ADDR=0.0.0.0 to expose the stack on ALL interfaces so the Mac's
# own LAN IP (e.g. http://192.168.x.y:7187) and other LAN devices can reach it.
# SECURITY: 0.0.0.0 exposes qBittorrent (admin/admin via 7186), the merge
# dashboard (7187), boba-jackett (7189), and Jackett (9117) to the local
# network — only enable on a trusted LAN.
BIND_ADDR="${TUNNEL_BIND_ADDR:-127.0.0.1}"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IDENTITY="$HOME/.local/share/containers/podman/machine/machine"

# Find the podman machine SSH port. Prefer `machine inspect` (gives the port
# directly); fall back to parsing the connection URI (ssh://core@host:PORT/...).
# The old `awk '{print $1}'` grabbed the connection NAME, not the port, which
# produced "Bad port 'podman-machine-default'".
PODMAN_PORT=$(podman machine inspect --format '{{.SSHConfig.Port}}' 2>/dev/null | head -1)
if ! printf '%s' "$PODMAN_PORT" | grep -qE '^[0-9]+$'; then
  PODMAN_PORT=$(podman system connection list --format '{{.URI}}' 2>/dev/null \
    | grep -oE '@[^/]+:[0-9]+' | grep -oE '[0-9]+$' | head -1)
fi

if [ -z "$PODMAN_PORT" ]; then
  # Fallback: try the default port range
  PODMAN_PORT=51347
  # Try to detect from running ssh processes
  EXISTING=$(ps aux | grep "ssh.*-L.*7187" | grep -v grep | awk '{print $2}' | head -1)
  if [ -n "$EXISTING" ]; then
    echo "Existing tunnel found (pid $EXISTING) — OK"
    exit 0
  fi
fi

echo "Podman SSH port: $PODMAN_PORT"

# Build the -L argument list
TUNNEL_ARGS=()
for port in "${PORTS[@]}"; do
  TUNNEL_ARGS+=(-L "${BIND_ADDR}:${port}:127.0.0.1:${port}")
done

# Kill any existing tunnel processes for these ports
for port in "${PORTS[@]}"; do
  ps aux | grep "ssh.*-L.*${port}" | grep -v grep | awk '{print $2}' | xargs -r kill 2>/dev/null || true
done
sleep 0.5

# Create the tunnel.
#   ServerAliveInterval/CountMax — probe the VM every 15s; after 3 missed
#     probes (~45s) the ssh client tears the connection down instead of
#     hanging half-open, so the keepalive supervisor can re-establish it.
#   ExitOnForwardFailure=yes — if a -L forward can't be set up (e.g. the
#     port is still held by a dying tunnel), ssh exits non-zero rather than
#     sitting connected-but-useless.
ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
  -o ServerAliveInterval=15 -o ServerAliveCountMax=3 \
  -o ExitOnForwardFailure=yes \
  -i "$IDENTITY" \
  -p "$PODMAN_PORT" \
  -N -f \
  "${TUNNEL_ARGS[@]}" \
  core@127.0.0.1

echo "SSH tunnel established: ports ${PORTS[*]} (bind ${BIND_ADDR})"
