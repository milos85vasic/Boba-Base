#!/bin/bash
# sig1_real_rss_fixture.sh — §11.4.115(F) RED fixture for SIG-1 (runaway
# process >SIG1_MAX_PROC_RSS_GB RSS) in resource_pressure_signature_challenge.sh.
#
# Origin: §11.4.209 independent review (task-review-457cca4-a7e55f9-report.md,
# IMPORTANT-1) rejected the prior polarity evidence
# (docs/qa/BOB-076/challenge_polarity_forced_fail.log) because it ran the
# challenge with SIG1_MAX_PROC_RSS_GB=0 — i.e. it mutated the THRESHOLD to
# a degenerate value that trips on every process, proving only that the
# comparison operator (`$3 > threshold`) works, not that the detector
# catches the ACTUAL pathological state (a real multi-GB RSS process).
# §11.4.115(F): "a guard never observed FAILing on the genuinely-broken
# artifact is unvalidated instrumentation and mints no verdicts."
#
# This fixture instead spawns a REAL process holding >5 GB (the DEFAULT,
# un-mutated SIG1_MAX_PROC_RSS_GB=5 threshold) of genuinely page-resident
# RSS via sig1_alloc_worker.py, verifies the RSS independently through `ps`
# (never trusting the worker's own self-report alone), and asserts the
# UN-MUTATED challenge script exits 1 naming SIG-1.
#
# Host-safety (§12.6/§12.11/§12.12): bounded to ${SIG1_FIXTURE_GB:-5.5} GB
# (well under 10% of a typical dev host, far under the §12.6 60% ceiling),
# self-cleaning via trap, and the spawned worker ALSO self-terminates via
# its own bounded sleep as a second line of defense if this driver crashes
# before its trap fires.
#
# Usage:
#   bash challenges/fixtures/resource_pressure/sig1_real_rss_fixture.sh
#
# Exit:
#   0 = RED confirmed — challenge genuinely FAILed on the real >5GB process,
#       naming SIG-1
#   1 = RED NOT reproduced — challenge did not FAIL naming SIG-1 against a
#       genuinely pathological artifact (detector under-detects)
#   2 = instrument/precondition SKIP (§11.4.3 SKIP-with-reason) — host
#       could not safely produce the precondition (e.g. insufficient free
#       memory, python3 unavailable)

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
CHALLENGE="$REPO_ROOT/challenges/scripts/resource_pressure_signature_challenge.sh"
WORKER="$SCRIPT_DIR/sig1_alloc_worker.py"

SIG1_FIXTURE_GB="${SIG1_FIXTURE_GB:-5.5}"
SIG1_FIXTURE_SLEEP_SEC="${SIG1_FIXTURE_SLEEP_SEC:-25}"
SIG1_FIXTURE_MIN_AVAIL_GB="${SIG1_FIXTURE_MIN_AVAIL_GB:-15}"

WORKER_PID=""
STDOUT_LOG=""

cleanup() {
  if [ -n "$WORKER_PID" ] && kill -0 "$WORKER_PID" 2>/dev/null; then
    kill -TERM "$WORKER_PID" 2>/dev/null
    sleep 0.3
    kill -KILL "$WORKER_PID" 2>/dev/null
  fi
  [ -n "${STDOUT_LOG:-}" ] && rm -f "$STDOUT_LOG"
}
trap cleanup EXIT INT TERM

if [ ! -r "$CHALLENGE" ]; then
  echo "SKIP (§11.4.3): challenge script not found at $CHALLENGE"
  exit 2
fi
if [ ! -r "$WORKER" ]; then
  echo "SKIP (§11.4.3): allocator worker not found at $WORKER"
  exit 2
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "SKIP (§11.4.3): python3 unavailable — cannot spawn real-RSS allocator"
  exit 2
fi

# §12.6/§12.11 pre-flight: refuse to run on a host without comfortable
# headroom above the fixture's own allocation, rather than guess it is safe.
AVAIL_KB=$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo 2>/dev/null || echo 0)
AVAIL_GB=$((AVAIL_KB / 1024 / 1024))
if [ "$AVAIL_GB" -lt "$SIG1_FIXTURE_MIN_AVAIL_GB" ]; then
  echo "SKIP (§11.4.3): only ${AVAIL_GB} GB MemAvailable — refusing to allocate ${SIG1_FIXTURE_GB} GB (§12.6 host-safety pre-flight, min required ${SIG1_FIXTURE_MIN_AVAIL_GB} GB)"
  exit 2
fi

echo "=== SIG-1 real-RSS fixture: host has ${AVAIL_GB} GB MemAvailable, allocating ${SIG1_FIXTURE_GB} GB (real, page-touched) ==="
STDOUT_LOG="$(mktemp)"
SIG1_FIXTURE_GB="$SIG1_FIXTURE_GB" SIG1_FIXTURE_SLEEP_SEC="$SIG1_FIXTURE_SLEEP_SEC" \
  python3 "$WORKER" > "$STDOUT_LOG" 2>&1 &
WORKER_PID=$!

READY=0
for _ in $(seq 1 100); do
  if grep -q "SIG1_FIXTURE_READY" "$STDOUT_LOG" 2>/dev/null; then
    READY=1
    break
  fi
  if ! kill -0 "$WORKER_PID" 2>/dev/null; then
    break
  fi
  sleep 0.3
done

if [ "$READY" -ne 1 ]; then
  echo "SKIP (§11.4.3): allocator did not report READY within budget — host may be memory-constrained or the allocation was refused"
  cat "$STDOUT_LOG" 2>/dev/null
  exit 2
fi

cat "$STDOUT_LOG"

# Verify the REAL RSS via ps — independent evidence, never trusting the
# worker's own self-report alone.
RSS_KB=$(ps -o rss= -p "$WORKER_PID" 2>/dev/null | tr -d ' ')
echo "Verified via ps: PID=$WORKER_PID RSS=${RSS_KB:-0} KB"
THRESHOLD_KB=$(awk -v gb="$SIG1_FIXTURE_GB" 'BEGIN { printf "%d", gb * 1024 * 1024 }')
if [ -z "$RSS_KB" ] || [ "$RSS_KB" -lt "$THRESHOLD_KB" ]; then
  echo "SKIP (§11.4.3): measured RSS ${RSS_KB:-0} KB did not reach the ${THRESHOLD_KB} KB fixture target — instrument could not create the precondition"
  exit 2
fi

echo
echo "=== Running the REAL (un-mutated) challenge against this live pathological state ==="
CHALLENGE_OUT="$(bash "$CHALLENGE" 2>&1)"
CHALLENGE_RC=$?
echo "$CHALLENGE_OUT"
echo
echo "Challenge exit code: $CHALLENGE_RC"

if [ "$CHALLENGE_RC" -eq 1 ] && echo "$CHALLENGE_OUT" | grep -q "SIG-1:"; then
  echo "RED CONFIRMED: challenge correctly FAILed on a genuine >${SIG1_FIXTURE_GB}GB RSS process, naming SIG-1"
  exit 0
else
  echo "RED NOT REPRODUCED: challenge did not FAIL naming SIG-1 against a genuine ${SIG1_FIXTURE_GB}GB RSS process — §11.4.115(F) violation, detector under-detects"
  exit 1
fi
