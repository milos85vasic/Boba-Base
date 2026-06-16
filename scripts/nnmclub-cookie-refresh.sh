#!/usr/bin/env bash
#
# nnmclub-cookie-refresh.sh
#
# Purpose:
#   Out-of-the-box refresh of the NNMClub session cookies. Runs the Playwright
#   harvester (scripts/nnmclub-cookie-harvest.mjs), writes/updates the
#   NNMCLUB_COOKIES line in ./.env (mode 0600, value never echoed), and restarts
#   the qbittorrent-proxy container so the new cookies take effect.
#
#   nnmclub.to login.php is gated behind a Cloudflare Turnstile JS CAPTCHA
#   (docs/qa/nnmclub-login-diagnosis-20260616.md); the harvester drives a real
#   browser to obtain the cookies. Cookies expire periodically, so run this on
#   boot / on a schedule (see "Out of the box" below).
#
# Usage:
#   scripts/nnmclub-cookie-refresh.sh
#   NNMCLUB_HARVEST_HEADFUL=1 scripts/nnmclub-cookie-refresh.sh   # interactive once
#
# Inputs:
#   NNMCLUB_USERNAME / NNMCLUB_PASSWORD must be present (in ./.env or the
#   environment). Values are never printed or logged.
#
# Outputs / side-effects:
#   - Updates the NNMCLUB_COOKIES=... line in ./.env (chmod 600).
#   - Restarts the qbittorrent-proxy container (clears __pycache__ first).
#
# Exit codes:
#   0 success; 2 Turnstile blocked / no session; 3 missing creds; 1 other error.
#
# "Out of the box" (cookies expire — refresh periodically):
#   - On boot: add to start.sh, or a systemd/launchd unit, or cron, e.g.
#       0 */6 * * *  cd /path/to/boba && scripts/nnmclub-cookie-refresh.sh >> /tmp/nnmclub-refresh.log 2>&1
#   - Manually whenever nnmclub searches start returning upstream_captcha.
#
# Dependencies: node, podman (or docker), Playwright (extension/node_modules).
# Cross-references: scripts/nnmclub-cookie-harvest.mjs,
#   download-proxy/src/merge_service/search.py (_search_nnmclub).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${REPO_ROOT}/.env"
HARVESTER="${SCRIPT_DIR}/nnmclub-cookie-harvest.mjs"

log() { printf '[nnmclub-refresh] %s\n' "$1" >&2; }

# Container runtime auto-detect (podman preferred), matching repo convention.
if command -v podman >/dev/null 2>&1; then
    RUNTIME="podman"
elif command -v docker >/dev/null 2>&1; then
    RUNTIME="docker"
else
    log "FATAL: neither podman nor docker found on PATH."
    exit 1
fi

[[ -f "${HARVESTER}" ]] || { log "FATAL: harvester not found at ${HARVESTER}"; exit 1; }

# Load NNMCLUB_USERNAME/PASSWORD (and optional base url) from .env if not already
# in the environment. We source ONLY the keys we need, never echoing values.
load_env_var() {
    local key="$1"
    if [[ -z "${!key:-}" && -f "${ENV_FILE}" ]]; then
        local line
        line="$(grep -E "^${key}=" "${ENV_FILE}" | tail -1 || true)"
        if [[ -n "${line}" ]]; then
            export "${key}=${line#*=}"
        fi
    fi
}
load_env_var NNMCLUB_USERNAME
load_env_var NNMCLUB_PASSWORD
load_env_var NNMCLUB_BASE_URL

if [[ -z "${NNMCLUB_USERNAME:-}" || -z "${NNMCLUB_PASSWORD:-}" ]]; then
    log "FATAL: NNMCLUB_USERNAME / NNMCLUB_PASSWORD not set (env or ${ENV_FILE})."
    exit 3
fi

log "running Playwright harvester (real headless browser)…"
set +e
COOKIES="$(node "${HARVESTER}")"
HARVEST_RC=$?
set -e

if [[ ${HARVEST_RC} -ne 0 || -z "${COOKIES}" ]]; then
    log "harvest FAILED (rc=${HARVEST_RC}). NNMCLUB_COOKIES NOT changed."
    log "If Turnstile is blocking unattended automation, supply NNMCLUB_COOKIES manually."
    exit "${HARVEST_RC}"
fi

# Confirm the harvested string actually carries a session id (no bluff).
if [[ "${COOKIES}" != *"phpbb2mysql_4_sid="* ]]; then
    log "FATAL: harvested cookie string lacks phpbb2mysql_4_sid — refusing to write."
    exit 2
fi
log "harvest OK (session cookie obtained; value not logged)."

# --- Update NNMCLUB_COOKIES in .env atomically, mode 0600, no value echo. ---
touch "${ENV_FILE}"
chmod 600 "${ENV_FILE}"
TMP_ENV="$(mktemp "${ENV_FILE}.XXXXXX")"
chmod 600 "${TMP_ENV}"
# Strip any existing NNMCLUB_COOKIES line, then append the fresh one.
grep -v -E '^NNMCLUB_COOKIES=' "${ENV_FILE}" > "${TMP_ENV}" || true
printf 'NNMCLUB_COOKIES=%s\n' "${COOKIES}" >> "${TMP_ENV}"
mv "${TMP_ENV}" "${ENV_FILE}"
chmod 600 "${ENV_FILE}"
log "wrote NNMCLUB_COOKIES to ${ENV_FILE} (chmod 600)."

# --- Restart the proxy so it picks up the new cookies. ---
PROXY_CT="qbittorrent-proxy"
log "clearing proxy __pycache__ and restarting ${PROXY_CT}…"
"${RUNTIME}" exec "${PROXY_CT}" sh -c \
    'find /config/download-proxy -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true' \
    >/dev/null 2>&1 || log "warn: could not clear __pycache__ (container may be down)."
"${RUNTIME}" restart "${PROXY_CT}" >/dev/null 2>&1 \
    || log "warn: '${RUNTIME} restart ${PROXY_CT}' failed — restart the proxy manually."

log "done. Verify: curl -s localhost:7187/api/v1/auth/status | grep nnmclub"
exit 0
