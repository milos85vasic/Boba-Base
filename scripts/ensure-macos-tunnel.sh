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
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IDENTITY="$HOME/.local/share/containers/podman/machine/machine"

# Find the podman machine SSH port.
PODMAN_PORT=$(podman system connection list 2>/dev/null \
  | awk '/^podman-machine-default[^*]/ {print $1} /^podman-machine-default\*/ {print $1}' \
  | head -1 \
  | sed 's/.*://; s/\/run.*//')

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
  TUNNEL_ARGS+=(-L "${port}:127.0.0.1:${port}")
done

# Kill any existing tunnel processes for these ports
for port in "${PORTS[@]}"; do
  ps aux | grep "ssh.*-L.*${port}" | grep -v grep | awk '{print $2}' | xargs -r kill 2>/dev/null || true
done
sleep 0.5

# Create the tunnel
ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
  -i "$IDENTITY" \
  -p "$PODMAN_PORT" \
  -N -f \
  "${TUNNEL_ARGS[@]}" \
  core@127.0.0.1

echo "SSH tunnel established: ports ${PORTS[*]}"
