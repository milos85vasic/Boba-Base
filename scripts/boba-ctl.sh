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
        # Compose-compatibility: start.sh (and any docker/podman-compose caller)
        # passes a `-d`/`--detach` flag. boba-ctl runs detached by default and its
        # `up`/`down` Go flags are `-profile`/`-wait` only, so a bare `-d` aborts
        # with "flag provided but not defined: -d" and the whole boot fails. Drop
        # the detach flag here so boba-ctl is a true drop-in for compose `up -d`.
        _bc_args=()
        for _a in "$@"; do
            case "$_a" in
                -d|--detach|-d=true|--detach=true) continue ;;
                *) _bc_args+=("$_a") ;;
            esac
        done
        exec "$BOBA_CTL_BIN" "${_bc_args[@]}"
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
