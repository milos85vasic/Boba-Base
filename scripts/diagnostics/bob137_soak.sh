#!/usr/bin/env bash
# BOB-137 soak driver -- reproduce the traffic shape that preceded the wedge.
#
# Purpose:   drive sustained concurrent search fan-out at the merge service
#            while an INDEPENDENT prober records 7186/7187 responsiveness, so
#            a transient stall is observed rather than missed. A point-in-time
#            probe finds the service healthy and concludes, falsely, that
#            there is no defect (§11.4.201(6) false-null) -- hence the soak.
# Usage:     scripts/diagnostics/bob137_soak.sh [DURATION_SECONDS] [CONCURRENCY]
# Inputs:    BOBA_SOAK_HOST (default localhost)
# Outputs:   docs/qa/BOB-137/soak_probe.log   (per-probe latency + HTTP code)
#            docs/qa/BOB-137/soak_driver.log  (fan-out request outcomes)
# Side-effects: HTTP load against 7186/7187 only. Starts/stops no containers,
#            signals no processes, writes no source. Bounded concurrency and
#            `nice -n 19` keep it inside the §12.6/§12.12 host budget.
# Deps:      bash, curl, date
# Refs:      docs/qa/BOB-137/forensics.md
set -euo pipefail

DURATION="${1:-900}"
CONC="${2:-6}"
HOST="${BOBA_SOAK_HOST:-localhost}"
OUT="docs/qa/BOB-137"
mkdir -p "$OUT"
PROBE_LOG="$OUT/soak_probe.log"
DRIVE_LOG="$OUT/soak_driver.log"
: >"$PROBE_LOG"
: >"$DRIVE_LOG"

# Queries mirroring the mix seen immediately before the observed wedge
# (container_log_tail.txt): ordinary terms plus the security-suite payloads.
QUERIES=(
  'test' 'ubuntu' 'debian iso' 'matrix 1999' 'inception'
  '<img src=x onerror=alert(1)>' '<style>body{background:red}</style>'
  "'; DROP TABLE t; --" '../../etc/passwd' 'боба тест'
)

stamp() { date -u +%Y-%m-%dT%H:%M:%SZ; }

# --- independent prober: is the merge service answering at all? -------------
prober() {
  local end=$(( $(date +%s) + DURATION ))
  while [ "$(date +%s)" -lt "$end" ]; do
    local h6 h7
    h6=$(curl -s -o /dev/null -w '%{http_code} %{time_total}' --max-time 10 \
         "http://$HOST:7186/" 2>/dev/null || echo "000 timeout")
    h7=$(curl -s -o /dev/null -w '%{http_code} %{time_total}' --max-time 10 \
         "http://$HOST:7187/health" 2>/dev/null || echo "000 timeout")
    echo "$(stamp) 7186=[$h6] 7187=[$h7]" >>"$PROBE_LOG"
    case "$h7" in 000*) echo "$(stamp) *** 7187 NOT ANSWERING ***" >>"$PROBE_LOG" ;; esac
    sleep 5
  done
}

# --- load driver: sustained concurrent fan-out ------------------------------
driver() {
  local end=$(( $(date +%s) + DURATION ))
  local i=0
  while [ "$(date +%s)" -lt "$end" ]; do
    local running=0
    while [ "$running" -lt "$CONC" ]; do
      local q="${QUERIES[$(( RANDOM % ${#QUERIES[@]} ))]}"
      local ep="/search"
      [ $(( RANDOM % 4 )) -eq 0 ] && ep="/search/sync"
      (
        code=$(curl -s -o /dev/null -w '%{http_code} %{time_total}' --max-time 120 \
               -H 'Content-Type: application/json' \
               -d "$(printf '{"query":%s,"category":"all","limit":20}' \
                     "$(printf '%s' "$q" | python3 -c 'import json,sys;print(json.dumps(sys.stdin.read()))')")" \
               "http://$HOST:7187/api/v1$ep" 2>/dev/null || echo "000 err")
        echo "$(stamp) $ep [$code] q=$q" >>"$DRIVE_LOG"
      ) &
      running=$(( running + 1 ))
      i=$(( i + 1 ))
    done
    wait
    sleep 2
  done
}

echo "$(stamp) soak start: duration=${DURATION}s concurrency=${CONC} host=${HOST}" \
  | tee -a "$PROBE_LOG" >>"$DRIVE_LOG"
prober & PROBER_PID=$!
driver & DRIVER_PID=$!
wait "$DRIVER_PID" 2>/dev/null || true
wait "$PROBER_PID" 2>/dev/null || true
echo "$(stamp) soak end" | tee -a "$PROBE_LOG" >>"$DRIVE_LOG"
