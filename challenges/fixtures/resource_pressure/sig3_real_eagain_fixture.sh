#!/bin/bash
# sig3_real_eagain_fixture.sh — §11.4.115(F) RED fixture for SIG-3 (EAGAIN
# cascade in podman container logs) in resource_pressure_signature_challenge.sh.
#
# Spawns a REAL, ephemeral, tiny podman container (from an already-cached
# image — no network pull required, so the fixture never depends on
# network reachability) that echoes 4 lines genuinely matching the SAME
# `grep -iE` pattern the detector uses ("resource temporarily unavailable|
# EAGAIN|SocketException \(11\)|failed to create new (os )?thread|failed to
# spawn") to its own REAL stdout, then sleeps briefly so `podman ps`
# (which the detector's container-enumeration step depends on) still lists
# it as running. The challenge is then run against THIS container's REAL
# logs via the REAL `podman logs --since` command path — no log file is
# mocked or spoofed; every byte the detector reads was produced by an
# actual container the container runtime actually ran.
#
# 4 matching lines exceed SIG3_EAGAIN_THRESHOLD (3, the default/un-mutated
# value) — this is a genuinely-over-threshold real signal, not a threshold
# mutation.
#
# Host-safety: single tiny already-cached alpine-based image, per-container
# memory/pids/oom hygiene bounds (mirrors the boot-and-power-management
# container-hygiene corollary), bounded lifetime (the container self-exits
# after ~45s even if this driver's cleanup trap fails to fire), and an
# explicit `podman rm -f` in that trap.
#
# Known honest limitation (§11.4.6): the detector's own container
# enumeration is `podman ps --format '{{.Names}}' | head -20` — only the
# first 20 RUNNING containers in whatever order podman returns them. If
# this host already has >=20 running containers, the fixture container may
# fall outside that window; this fixture detects that case explicitly and
# SKIPs (§11.4.3) rather than silently passing or failing. This is itself
# a real coverage gap in SIG-3 worth a future MINOR fix (unbounded scan or
# a documented cap with an honest note), tracked separately — not fixed
# here (out of this fixture's scope).
#
# Usage:
#   bash challenges/fixtures/resource_pressure/sig3_real_eagain_fixture.sh
#
# Exit:
#   0 = RED confirmed  1 = RED not reproduced  2 = instrument/precondition SKIP

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
CHALLENGE="$REPO_ROOT/challenges/scripts/resource_pressure_signature_challenge.sh"

CONTAINER_NAME="sig3-eagain-fixture-$$"
IMAGE="${SIG3_FIXTURE_IMAGE:-docker.io/library/python:3.12-alpine}"

cleanup() {
  podman rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

if [ ! -r "$CHALLENGE" ]; then
  echo "SKIP (§11.4.3): challenge script not found at $CHALLENGE"
  exit 2
fi
if ! command -v podman >/dev/null 2>&1; then
  echo "SKIP (§11.4.3): podman unavailable"
  exit 2
fi
if ! podman image exists "$IMAGE" 2>/dev/null; then
  echo "SKIP (§11.4.3): fixture image $IMAGE not locally cached — refusing to pull mid-fixture (network-dependent, not bounded, §11.4.35 host-portability boundary)"
  exit 2
fi

echo "=== SIG-3 real-EAGAIN fixture: launching ephemeral container '$CONTAINER_NAME' from cached image $IMAGE ==="
if ! podman run -d --name "$CONTAINER_NAME" \
  --memory=64m --pids-limit=32 --oom-score-adj=500 \
  "$IMAGE" sh -c '
    echo "Resource temporarily unavailable (sig3 fixture line 1)"
    echo "EAGAIN (sig3 fixture line 2)"
    echo "SocketException (11) (sig3 fixture line 3)"
    echo "failed to create new os thread (sig3 fixture line 4)"
    sleep 45
  ' >/dev/null 2>&1; then
  echo "SKIP (§11.4.3): podman run failed to launch fixture container"
  exit 2
fi

# Give the container a moment to start and emit its lines.
sleep 2

RUNNING=$(podman ps --format '{{.Names}}' 2>/dev/null | grep -c "^${CONTAINER_NAME}$" || true)
if [ "${RUNNING:-0}" -lt 1 ]; then
  echo "SKIP (§11.4.3): fixture container is not in the RUNNING set podman ps reports — cannot exercise the detector's real query path"
  exit 2
fi

# Defensive: the detector only scans the first 20 `podman ps` entries.
POSITION=$(podman ps --format '{{.Names}}' 2>/dev/null | head -20 | grep -n "^${CONTAINER_NAME}$" | cut -d: -f1 || true)
if [ -z "$POSITION" ]; then
  echo "SKIP (§11.4.3): fixture container fell outside the detector's 'head -20' container-scan window (host currently has >=20 running containers) — honest coverage gap, not this fixture's to fix"
  exit 2
fi

echo "Fixture container running (position $POSITION of the detector's head -20 scan window). Real captured logs:"
podman logs "$CONTAINER_NAME" 2>&1

echo
echo "=== Running the REAL (un-mutated) challenge against this live container ==="
CHALLENGE_OUT="$(bash "$CHALLENGE" 2>&1)"
CHALLENGE_RC=$?
echo "$CHALLENGE_OUT"
echo
echo "Challenge exit code: $CHALLENGE_RC"

if [ "$CHALLENGE_RC" -eq 1 ] && echo "$CHALLENGE_OUT" | grep -q "SIG-3:"; then
  echo "RED CONFIRMED: challenge correctly FAILed on a genuine 4-hit EAGAIN cascade (>3 threshold) in a real container's real logs, naming SIG-3"
  exit 0
else
  echo "RED NOT REPRODUCED: challenge did not FAIL naming SIG-3 against a genuinely-over-threshold EAGAIN cascade — §11.4.115(F) violation"
  exit 1
fi
