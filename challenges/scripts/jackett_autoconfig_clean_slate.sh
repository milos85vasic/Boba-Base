#!/usr/bin/env bash
# CONST-032 regression guard: clean-slate Jackett autoconfig flow.
#
# 1. Tear down stack
# 2. Wipe ./config/jackett
# 3. Boot stack
# 4. Wait for /health (3 min ceiling)
# 5. Poll boba-jackett:7189 GET /api/v1/jackett/autoconfig/runs until a run
#    row exists or 60s
# 6. Fetch the full run via GET /api/v1/jackett/autoconfig/runs/{id} and
#    validate response shape
# 7. Run a search; assert no 5xx
#
# NOTE (GA-21, 2026-08-08): the Python `/api/v1/jackett/autoconfig/last`
# endpoint this script originally polled was removed in favour of the
# canonical Go boba-jackett service on port 7189 (see CLAUDE.md "Jackett
# auto-configuration" + download-proxy/src/api/__init__.py's routing
# comment). The equivalent flow is GET /api/v1/jackett/autoconfig/runs
# (list, most-recent-first, per qBitTorrent-go/internal/jackettapi/runs.go
# HandleListRuns) followed by GET /api/v1/jackett/autoconfig/runs/{id}
# (per HandleGetRun) for the full result — the same two-call pattern the
# Angular dashboard's JackettService.getLatestRun() uses.
#
# Exit:
#   0 = pass
#   1 = fail
set -uo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT"

RUNTIME="${CONTAINER_RUNTIME:-podman}"
if ! command -v "$RUNTIME" >/dev/null 2>&1; then
  RUNTIME="docker"
fi
MERGE="${MERGE_SERVICE_URL:-http://localhost:7187}"
# boba-jackett (Go) owns Jackett credentials/indexer overrides/autoconfig
# run history on its own port — network_mode: host in docker-compose.yml,
# never proxied through the merge service. See CLAUDE.md "Port Map".
BOBA_JACKETT="${BOBA_JACKETT_URL:-http://localhost:7189}"

step() { echo ">>> $*"; }
fail() { echo "FAIL: $*" >&2; exit 1; }

step "1. Tear down"
"$RUNTIME" compose down --remove-orphans >/dev/null 2>&1 || true

step "2. Wipe ./config/jackett"
# Jackett-LSIO writes some files as root; podman unshare maps host
# uid 0 ↔ container root inside the user namespace so we can delete.
if ! rm -rf ./config/jackett 2>/dev/null; then
  if command -v podman >/dev/null 2>&1; then
    podman unshare rm -rf ./config/jackett || fail "could not wipe ./config/jackett"
  else
    sudo rm -rf ./config/jackett || fail "could not wipe ./config/jackett (need sudo or podman)"
  fi
fi
[ ! -e ./config/jackett ] || fail "./config/jackett still exists after wipe"

step "3. Boot stack"
"$RUNTIME" compose up -d >/dev/null

step "4. Wait for /health (3 min)"
deadline=$(( $(date +%s) + 180 ))
while [ "$(date +%s)" -lt "$deadline" ]; do
  if curl -sf "$MERGE/health" >/dev/null 2>&1; then
    echo "    healthy"
    break
  fi
  sleep 5
done
curl -sf "$MERGE/health" >/dev/null 2>&1 || fail "merge service unhealthy after 3 min"

step "5. Poll boba-jackett GET /api/v1/jackett/autoconfig/runs (60s)"
deadline=$(( $(date +%s) + 60 ))
saw_200=0
run_id=""
while [ "$(date +%s)" -lt "$deadline" ]; do
  http=$(curl -s -o /tmp/autoconfig_runs.json -w '%{http_code}' "$BOBA_JACKETT/api/v1/jackett/autoconfig/runs?limit=1" || true)
  if [ "$http" = "200" ]; then
    saw_200=1
    run_id=$(python3 -c "
import json
rows = json.load(open('/tmp/autoconfig_runs.json'))
print(rows[0]['id'] if rows else '')
" 2>/dev/null || true)
    [ -n "$run_id" ] && break
  fi
  sleep 2
done
# HandleListRuns always returns 200 (an empty JSON array when no run has
# recorded yet) — it never 404s. A poll window with no 200 at all means
# boba-jackett itself never became reachable, which IS a failure.
[ "$saw_200" = "1" ] || fail "GET /api/v1/jackett/autoconfig/runs never returned 200 (boba-jackett unreachable on $BOBA_JACKETT?)"

step "6. Validate response shape"
if [ -n "$run_id" ]; then
  http=$(curl -s -o /tmp/autoconfig.json -w '%{http_code}' "$BOBA_JACKETT/api/v1/jackett/autoconfig/runs/$run_id" || true)
  [ "$http" = "200" ] || fail "GET /api/v1/jackett/autoconfig/runs/$run_id returned $http"
  python3 -m json.tool /tmp/autoconfig.json >/dev/null || fail "autoconfig body is not valid JSON"
  for key in ran_at discovered configured_now already_present skipped_no_match errors; do
    if ! python3 -c "import json,sys; sys.exit(0 if '$key' in json.load(open('/tmp/autoconfig.json')) else 1)"; then
      fail "key '$key' missing from autoconfig payload"
    fi
  done
  configured_now=$(python3 -c "import json; print(len(json.load(open('/tmp/autoconfig.json')).get('configured_now',[])))")
  echo "    configured_now count: $configured_now"
else
  echo "    autoconfig has no recorded run (acceptable when no creds in env)"
fi

step "7. Run a search; assert no 5xx"
search_code=$(curl -s -o /tmp/search.json -w '%{http_code}' \
  -X POST "$MERGE/api/v1/search" \
  -H 'Content-Type: application/json' \
  -d '{"query":"ubuntu","category":"all"}' || true)
[ "$search_code" -ge 500 ] && fail "search returned $search_code"
echo "    search returned $search_code — OK"

echo "PASS: jackett_autoconfig_clean_slate"
exit 0
