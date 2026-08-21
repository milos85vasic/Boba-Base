#!/usr/bin/env bash
# BOB-137 thread-state census -- observe the GIL-starvation signature directly.
#
# Purpose:   BOB-137's acceptance criteria require "a thread-state census showing
#            no permanently-R thread". The wedge signature was ONE thread in state
#            R with wchan 0 (spinning, holding the GIL) while every other thread
#            sat in futex_wait_queue. This sampler records the per-thread state
#            census of the merge-service process for the duration of a soak, so
#            the presence OR absence of a persistently-running thread is an
#            observation rather than an inference (§11.4.201(6): a single
#            point-in-time sample of a healthy process is a false-null).
# Usage:     scripts/diagnostics/bob137_thread_census.sh [DURATION_SECONDS] [INTERVAL]
# Inputs:    BOBA_CENSUS_OUT   (default qa-results/BOB-137)
#            BOBA_CENSUS_CTR   (default qbittorrent-proxy)
# Outputs:   $OUT/thread_census.log  -- one line per sample:
#            <utc> states=<S:n,R:n,...> R_tids=<tid,...> cpu_pct=<n>
# Side-effects: READ-ONLY. Executes only `cat`/`awk` inside the container via
#            `podman exec`. Starts/stops/signals nothing (§11.4.263: no signal is
#            ever sent, no pkill -f is ever used).
# Deps:      bash, podman|docker, awk, date
# Refs:      docs/qa/BOB-137/forensics.md, docs/qa/BOB-137/threads.txt
set -euo pipefail

DURATION="${1:-900}"
INTERVAL="${2:-10}"
OUT="${BOBA_CENSUS_OUT:-qa-results/BOB-137}"
CTR="${BOBA_CENSUS_CTR:-qbittorrent-proxy}"
RUNTIME="$(command -v podman || command -v docker)"
mkdir -p "$OUT"
LOG="$OUT/thread_census.log"
: >"$LOG"

stamp() { date -u +%Y-%m-%dT%H:%M:%SZ; }

echo "$(stamp) census start: duration=${DURATION}s interval=${INTERVAL}s container=${CTR}" >>"$LOG"

end=$(( $(date +%s) + DURATION ))
prev_jiffies=""; prev_epoch=""
while [ "$(date +%s)" -lt "$end" ]; do
  # One exec per sample: per-thread state (field 3) + the R-state tids,
  # plus the process-wide utime+stime so a spinning thread shows as CPU burn.
  sample="$($RUNTIME exec "$CTR" sh -c '
    states=""; rtids=""
    for t in /proc/1/task/*/stat; do
      tid=$(basename "$(dirname "$t")")
      st=$(awk "{print \$3}" "$t" 2>/dev/null) || continue
      states="$states$st "
      [ "$st" = "R" ] && rtids="$rtids$tid,"
    done
    jif=$(awk "{print \$14+\$15}" /proc/1/stat)
    echo "STATES:$states|RTIDS:$rtids|JIF:$jif"
  ' 2>/dev/null || echo "STATES:|RTIDS:|JIF:")"

  states=$(printf '%s' "$sample" | sed 's/^STATES://; s/|RTIDS.*//')
  rtids=$(printf '%s' "$sample"  | sed 's/.*|RTIDS://; s/|JIF.*//')
  jif=$(printf '%s' "$sample"    | sed 's/.*|JIF://')

  census=$(printf '%s\n' $states | sort | uniq -c | awk '{printf "%s:%s,", $2, $1}')
  now=$(date +%s)
  cpu="n/a"
  if [ -n "$prev_jiffies" ] && [ -n "$jif" ] && [ "$now" -gt "$prev_epoch" ]; then
    cpu=$(awk -v a="$jif" -v b="$prev_jiffies" -v d="$(( now - prev_epoch ))" \
          'BEGIN{ printf "%.1f", (a-b)/100.0/d*100 }')
  fi
  printf '%s states=%s R_tids=%s cpu_pct=%s\n' "$(stamp)" "${census:-none}" "${rtids:-none}" "$cpu" >>"$LOG"
  prev_jiffies="$jif"; prev_epoch="$now"
  sleep "$INTERVAL"
done
echo "$(stamp) census end" >>"$LOG"
