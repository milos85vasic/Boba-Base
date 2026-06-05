#!/usr/bin/env bash
# track-build-resources.sh — Build-resource stats tracker (§11.4.24)
#
# Wraps a build/test command with CPU/memory/time tracking.
# Usage:
#   scripts/track-build-resources.sh <command> [args...]
#
# Output: Appends one JSON line to docs/build-stats.ndjson

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
STATS_FILE="${PROJECT_ROOT}/docs/build-stats.ndjson"
START_TS=$(date +%s)
START_RUSAGE=$(python3 -c "import os; r=os.times(); print(f'{r.user} {r.system}')" 2>/dev/null || echo "0 0")

echo "[track-build-resources] Running: $*"

if ! /usr/bin/time -p "$@" 2>"${PROJECT_ROOT}/.build-time.$$"; then
    RC=$?
fi

END_TS=$(date +%s)
END_RUSAGE=$(python3 -c "import os; r=os.times(); print(f'{r.user} {r.system}')" 2>/dev/null || echo "0 0")
ELAPSED=$((END_TS - START_TS))

read -r _ WALL_SEC < "${PROJECT_ROOT}/.build-time.$$" 2>/dev/null || WALL_SEC=$ELAPSED
rm -f "${PROJECT_ROOT}/.build-time.$$"

read -r USER_START SYS_START <<< "$START_RUSAGE"
read -r USER_END SYS_END <<< "$END_RUSAGE"
CPU_USER=$(python3 -c "print(round(float('$USER_END') - float('$USER_START'), 2))" 2>/dev/null || echo "0")
CPU_SYS=$(python3 -c "print(round(float('$SYS_END') - float('$SYS_START'), 2))" 2>/dev/null || echo "0")

HOSTNAME=$(hostname -s 2>/dev/null || echo "unknown")

mkdir -p "$(dirname "$STATS_FILE")"

echo "{\"ts\":$START_TS,\"host\":\"$HOSTNAME\",\"cmd\":\"$*\",\"wall_sec\":$WALL_SEC,\"cpu_user\":$CPU_USER,\"cpu_sys\":$CPU_SYS,\"rc\":${RC:-0}}" >> "$STATS_FILE"

echo "[track-build-resources] wall=${WALL_SEC}s cpu_user=${CPU_USER}s cpu_sys=${CPU_SYS}s rc=${RC:-0}"
exit ${RC:-0}
