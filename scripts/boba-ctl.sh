#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BOBA_CTL_BIN="$PROJECT_ROOT/cmd/boba-ctl/boba-ctl"

# Compile on demand if binary doesn't exist
if [[ ! -x "$BOBA_CTL_BIN" ]]; then
    echo "[boba-ctl] Compiling boba-ctl..." >&2
    cd "$PROJECT_ROOT/cmd/boba-ctl" && go build -o boba-ctl . && cd "$PROJECT_ROOT"
fi

CMD="${1:-help}"

case "$CMD" in
    up|down)
        exec "$BOBA_CTL_BIN" "$@"
        ;;
    ps)
        exec "$BOBA_CTL_BIN" status
        ;;
    config)
        if [[ -f "$PROJECT_ROOT/docker-compose.yml" ]]; then
            exit 0
        fi
        echo "docker-compose.yml not found" >&2
        exit 1
        ;;
    pull)
        echo "[boba-ctl] WARNING: pull not supported in boba-ctl mode — skipping" >&2
        exit 0
        ;;
    *)
        exec "$BOBA_CTL_BIN" "$@"
        ;;
esac
