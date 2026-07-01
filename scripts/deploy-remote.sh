#!/usr/bin/env bash
# scripts/deploy-remote.sh — distributed boot of the Boba System onto a remote
# host defined in deploy/hosts.yaml. Realizes the SSH + remote-podman-compose
# pattern of the vasic-digital/containers submodule's pkg/remote (§11.4.76):
# rsync the System → remote, transfer the per-host .env (operator-approved,
# §11.4.10), fix the host-specific data dir, install plugins, podman-compose up,
# health-check. Idempotent; re-runnable.
#
# Usage:  ./scripts/deploy-remote.sh <host-name> [--profile go]
#         ./scripts/deploy-remote.sh nezha
# Inputs: deploy/hosts.yaml (host name/address/user/remote_path), local .env.
# Side effects: writes/updates <remote_path> on the remote + boots containers.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$REPO_ROOT"
HOST_NAME="${1:?usage: deploy-remote.sh <host-name> [--profile go]}"
PROFILE=""; [[ "${2:-}" == "--profile" ]] && PROFILE="${3:-}"
HOSTS="deploy/hosts.yaml"

# Minimal YAML field extraction for the named host block (structured file).
_field() { awk -v h="$HOST_NAME" -v k="$2" '
  $0 ~ "name: *"h"$" {f=1} f && $0 ~ "^  - name:" && $0 !~ "name: *"h"$" {f=0}
  f && $0 ~ "^ *"k":" {sub("^ *"k": *",""); sub(/[ \t]+#.*$/,""); gsub(/[ \t]+$/,""); print; exit}' "$HOSTS"; }

ADDR="$(_field x address)"; USER="$(_field x user)"; RPATH="$(_field x remote_path)"
: "${ADDR:?host not found in $HOSTS}" "${USER:?}" "${RPATH:?}"
SSH="ssh -o BatchMode=yes ${USER}@${ADDR}"
echo "[deploy-remote] host=$HOST_NAME ${USER}@${ADDR}:${RPATH} profile='${PROFILE:-default}'"

echo "[1/5] rsync System → remote (source only; container-owned config/ excluded)"
$SSH "mkdir -p '$RPATH'"
rsync_rc=0
rsync -az --delete \
  --exclude='.git' --exclude='.env' --exclude='.env.*' --exclude='*.env' \
  --exclude='node_modules' --exclude='.venv' --exclude='qa-results' \
  --exclude='releases' --exclude='.playwright-mcp' --exclude='__pycache__' \
  --exclude='.angular' --exclude='*.db' --exclude='submodules/jackett' \
  --exclude='.git-backup*' \
  --exclude='config' \
  ./ "${USER}@${ADDR}:${RPATH}/" || rsync_rc=$?
# §11.4.108: the WHOLE config/ tree is owned by the qBittorrent container user
# (PUID) — qBittorrent.conf, jackett/, boba.db, logs, BT_backup, nova3/engines.
# Syncing it from the SSH user hits "Permission denied"; under set -e that
# aborted the deploy BEFORE [3/5] install, so fixed plugin bytes never landed.
# config/ is RUNTIME state, not source — the merge service source is
# ./download-proxy (bind-mounted) and ./plugins (installed via podman cp by
# install-plugin.sh in [3/5]). So config/ is excluded entirely. rsync exit
# 23/24 (partial/vanished) is tolerated; any other code is fatal.
if [[ $rsync_rc -ne 0 && $rsync_rc -ne 23 && $rsync_rc -ne 24 ]]; then
  echo "[deploy-remote] rsync failed (rc=$rsync_rc)"; exit "$rsync_rc"
fi

echo "[2/5] transfer .env (operator-approved §11.4.10) + host-correct data dir"
[[ -f .env ]] || { echo "no local .env"; exit 1; }
scp -o BatchMode=yes .env "${USER}@${ADDR}:${RPATH}/.env"
$SSH "cd '$RPATH' && chmod 600 .env && mkdir -p '$RPATH/tmp' \$HOME/boba-downloads && \
  sed -i 's#^QBITTORRENT_DATA_DIR=.*#QBITTORRENT_DATA_DIR='\"\$HOME\"'/boba-downloads#' .env"

# Opt-in DURABLE remote execution (§5 / pkg/remoteexec): when BOBA_DURABLE=1,
# the heavy install + compose-up steps run as a transient systemd --user unit ON
# THE REMOTE HOST, so they survive this SSH session ending (logind would
# otherwise reap them mid-deploy). Default behavior (BOBA_DURABLE unset) is the
# original inline steps below, unchanged.
DURABLE_LIB="${REPO_ROOT}/submodules/containers/scripts/lib/durable-run.sh"
if [[ "${BOBA_DURABLE:-0}" == "1" ]]; then
  [[ -f "$DURABLE_LIB" ]] || { echo "BOBA_DURABLE=1 but $DURABLE_LIB missing"; exit 2; }
  echo "[3-4/5] DURABLE install + podman-compose up on remote (survives SSH drop)"
  scp -o BatchMode=yes "$DURABLE_LIB" "${USER}@${ADDR}:${RPATH}/.durable-run.sh"
  PROF=(); [[ -n "$PROFILE" ]] && PROF=(--profile "$PROFILE")
  UNIT="boba-deploy-$(date +%s)"
  $SSH "source '$RPATH/.durable-run.sh'; durable_launch_cmd '$UNIT' \"cd '$RPATH' && chmod +x install-plugin.sh && ./install-plugin.sh --all && podman-compose -f docker-compose.yml --project-name boba ${PROF[*]} up -d\""
  echo "[deploy-remote] launched durable unit $UNIT on remote; waiting for completion"
  rc="$($SSH "source '$RPATH/.durable-run.sh'; durable_wait_sentinel '$UNIT' ${BOBA_DURABLE_TIMEOUT:-1800}")" || {
    echo "[deploy-remote] durable deploy timed out"; exit 1; }
  $SSH "source '$RPATH/.durable-run.sh'; durable_fetch_log '$UNIT'; durable_stop '$UNIT'"
  echo "[5/5] health"
  $SSH "cd '$RPATH' && podman ps --format '{{.Names}}\t{{.Status}}' | grep -iE 'qbittorrent|jackett|download-proxy|boba'"
  echo "[deploy-remote] done (durable) — ports inside host: 7186/7187/7189/9117"
  exit "$rc"
fi

echo "[3/5] install curated plugins"
# Install ALL managed plugins that have plugins/ source (install-plugin.sh skips
# any source-less orphan engine names gracefully). Self-maintaining: every
# plugin with maintained source — incl. the multi-word-encoding fixes and the
# §11.4.124 adopted plugins — lands in nova3/engines without a drifting hand-list.
$SSH "cd '$RPATH' && chmod +x install-plugin.sh && ./install-plugin.sh --all"

echo "[4/5] podman-compose up"
PROF=(); [[ -n "$PROFILE" ]] && PROF=(--profile "$PROFILE")
$SSH "cd '$RPATH' && podman-compose -f docker-compose.yml --project-name boba ${PROF[*]} up -d"

echo "[5/5] health"
$SSH "cd '$RPATH' && podman ps --format '{{.Names}}\t{{.Status}}' | grep -iE 'qbittorrent|jackett|download-proxy|boba'"
echo "[deploy-remote] done — health-probe ports inside the host (host-net): 7186/7187/7189/9117"
