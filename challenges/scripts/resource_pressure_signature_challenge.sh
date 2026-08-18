#!/bin/bash
# resource_pressure_signature_challenge.sh — proactive host resource-pressure guard
#
# Purpose: detect known signatures that PRECEDE forced-logout incidents so we
# fail-loud BEFORE user@1000.service gets SIGKILLed, not after.
#
# Origin: 2026-08-18 forced-logout incident (2nd occurrence on this project).
# CONST-033 triage confirmed:
#   - No kernel OOM-kill markers (dmesg clean)
#   - No systemd-oomd trigger (pressure never crossed 90% threshold)
#   - No lid-suspend event (HandleLidSwitch=ignore, CONST-033 compliant)
#   - user@1000.service Main process SIGKILLed status=9 by unattributed source
#
# Five signatures the triage identified, EACH proactively falsifiable:
#
#   SIG-1: Runaway process >5 GB RSS in current user.slice (e.g. ugrep -o with
#          variable-length alternation on a 10K-line file → 15 GB observed)
#   SIG-2: Thread count >70% of ulimit -u soft limit (§12.12 forensic FACT)
#   SIG-3: Recent EAGAIN cascade in podman container logs (errno 11 =
#          system-wide thread ceiling, precedes SIGKILL by ~5 min)
#   SIG-4: user.slice PSI full avg60 >50 (sustained memory pressure — half the
#          systemd-oomd 90% trigger threshold, the leading indicator)
#   SIG-5: pgrep -f pathological patterns in currently-running ps output
#          (regex "-o" with "\.\\{" bounded quantifier alternation on a source
#          file matches the reaped 20:50:59 forensic instance)
#
# Every hit is REPORTED with §11.4.6 honest boundary — a signature triggered
# does NOT prove logout is imminent, but it does prove the pressure the actual
# incident had.
#
# §11.4.115(F) polarity: run `bash challenges/scripts/verify_resource_pressure_polarity.sh`
# — it drives all 5 per-signature RED fixtures under
# challenges/fixtures/resource_pressure/, each producing (or, for SIG-4,
# safely dependency-injecting — see that fixture's header) the GENUINE
# pathological artifact each detector is supposed to catch, then asserts
# this UN-MUTATED script exits 1 naming the corresponding SIG-N. This
# replaces an earlier polarity claim that only forced SIG1_MAX_PROC_RSS_GB
# to a degenerate 0 (docs/qa/BOB-076/challenge_polarity_forced_fail.log) —
# that evidence proved the comparison operator works, not that the
# detector catches the actual pathological state (§11.4.209 review
# IMPORTANT-1, task-review-457cca4-a7e55f9-report.md). §1.1 paired
# mutation: strip a signature detector, re-run
# verify_resource_pressure_polarity.sh, confirm the corresponding fixture's
# RED flips to "RED NOT REPRODUCED" → proves the detector is load-bearing.
#
# Usage:
#   bash challenges/scripts/resource_pressure_signature_challenge.sh
#
# Exit:
#   0 = clean (all 5 signatures below their thresholds)
#   1 = one or more signatures over threshold
#   2 = invocation error / instrument unavailable (§11.4.3 SKIP-with-reason)
#
# Anti-bluff (§11.4.107(10)):
#   Every threshold value is documented + traceable to captured evidence.
#   Never a hardcoded value without a cited source (§11.4.6).

set -uo pipefail

# --- Configuration (thresholds tuned to the 2026-08-18 forensic instance) ---
# Rationale for each threshold cites its evidence anchor.
SIG1_MAX_PROC_RSS_GB="${SIG1_MAX_PROC_RSS_GB:-5}"     # forensic FACT: 15 GB ugrep
SIG2_THREAD_PCT="${SIG2_THREAD_PCT:-70}"              # §12.12: 3900/4096 = 95% was crisis
SIG3_EAGAIN_LOOKBACK_MIN="${SIG3_EAGAIN_LOOKBACK_MIN:-15}"  # ~5 min crisis window observed
SIG3_EAGAIN_THRESHOLD="${SIG3_EAGAIN_THRESHOLD:-3}"  # 4 trackers hit EAGAIN simultaneously
# §11.4.209 review MINOR-4: SIG-3 in isolation is a proxy-for-a-proxy — the
# §12.12 real signature is EAGAIN AS A SYMPTOM OF thread-ceiling pressure,
# not EAGAIN alone (transient socket unavailability / upstream slow-start /
# disk-pressure retries also emit errno-11 with zero thread-ceiling
# involvement). The fix is CORRELATION-AS-CONTEXT, never
# correlation-as-suppression: SIG-3's own EAGAIN_COUNT vs
# SIG3_EAGAIN_THRESHOLD comparison (below, unchanged) remains the ONLY FAIL
# condition. A first draft of this fix RAISED the required hit-count when
# SIG-2 read LOW, and was caught regressing SIG-3's own §11.4.115(F) RED
# fixture (sig3_real_eagain_fixture.sh) in testing BEFORE landing: SIG-2 and
# SIG-3 measure DIFFERENT TIME WINDOWS — SIG-2 is a POINT-IN-TIME read of
# "right now", SIG-3 is a SIG3_EAGAIN_LOOKBACK_MIN-minute LOOKBACK over past
# container logs — so a genuine EAGAIN cascade from several minutes ago
# legitimately co-occurs with a LOW *current* SIG-2 reading once the
# thread-ceiling pressure has subsided; raising the bar in that case would
# have suppressed the exact real-incident class SIG-3 exists to catch (a
# §11.4.101 conservative-safe-default violation — see
# docs/qa/task-review-457cca4-a7e55f9-minor-fixes/minor-4.log for the
# caught-and-reverted transcript). The CORRECT fix keeps the original
# sensitivity and instead attaches a CONFIDENCE label to the failure
# message so an operator can immediately see whether SIG-3 correlates with
# CURRENT thread pressure (elevated SIG-2 = the real §12.12 pattern) or not
# (low current SIG-2 = still a genuine cascade, but possibly from an
# already-subsided or non-thread-ceiling episode) — never suppressing
# detection either way.
SIG2_LOW_UTIL_PCT="${SIG2_LOW_UTIL_PCT:-30}"          # below this, current-moment correlation with thread-ceiling is unlikely

# §11.4.209 review MINOR-4 correlation function, extracted so it is
# independently sourceable/testable (see
# docs/qa/task-review-457cca4-a7e55f9-minor-fixes/minor-4.log for the
# golden-good/golden-bad paired-mutation evidence). NEVER changes whether
# SIG-3 fails — only the CONFIDENCE label attached to that verdict.
#   $1 = SIG-2 thread-utilization pct as a bare integer, or "" if SIG-2
#        itself could not resolve (unlimited ulimit / SKIP).
# Prints "elevated-current-SIG-2" or "SIG-2-not-currently-elevated".
_sig3_confidence_label() {
  local pct="$1"
  if [ -n "$pct" ] && [ "$pct" -lt "$SIG2_LOW_UTIL_PCT" ] 2>/dev/null; then
    echo "SIG-2-not-currently-elevated"
  else
    echo "elevated-current-SIG-2-or-unresolved"
  fi
}
SIG4_PSI_AVG60_LIMIT="${SIG4_PSI_AVG60_LIMIT:-50}"    # half the systemd-oomd 90% threshold
SIG5_PATHOLOGICAL_PATTERN_REGEX='\bugrep .*-o .*\.\\\{[0-9]+,[0-9]+\\\}.*\\\|'

# --- Preflight ---
USER="${USER:-$(id -un)}"
FAILURES=0
FAIL_MESSAGES=()

log_fail() {
  FAILURES=$((FAILURES + 1))
  FAIL_MESSAGES+=("$1")
}

# --- SIG-1: runaway process >N GB RSS ---
echo "=== SIG-1: runaway process >${SIG1_MAX_PROC_RSS_GB} GB RSS ==="
# ps prints RSS in KB. Threshold in GB.
THRESHOLD_KB=$((SIG1_MAX_PROC_RSS_GB * 1024 * 1024))
LARGE_PROCS=$(ps -o pid,user,rss,comm --no-headers -u "$USER" 2>/dev/null | \
  awk -v t="$THRESHOLD_KB" '$3 > t')
if [ -n "$LARGE_PROCS" ]; then
  echo "OVER THRESHOLD:"
  echo "$LARGE_PROCS"
  # Exception: known legitimate large services. §11.4.209 review MINOR-3:
  # this list was a hardcoded project literal (a §11.4.28 decoupling
  # violation for a challenge shipped to be inherited universally per
  # §11.4.17) despite the prior comment already claiming §11.4.35
  # consumer-DATA status. It is now genuinely consumer-owned: an operator
  # extends it via SIG1_LEGIT_EXCLUSIONS (an ERE alternation, same syntax
  # as before) WITHOUT editing this shipped script. The literal below is
  # kept ONLY as this project's own default value — never hardcoded for a
  # consumer that overrides the env var.
  LEGIT_EXCLUSIONS="${SIG1_LEGIT_EXCLUSIONS:-ollama|firefox|yandex_browser|chrome}"
  UNCLASSIFIED=$(echo "$LARGE_PROCS" | grep -vE "$LEGIT_EXCLUSIONS" || true)
  if [ -n "$UNCLASSIFIED" ]; then
    log_fail "SIG-1: unclassified process(es) over ${SIG1_MAX_PROC_RSS_GB} GB RSS"
    echo "UNCLASSIFIED (not in legitimate-large exclusion set):"
    echo "$UNCLASSIFIED"
  else
    echo "(all over-threshold procs matched legitimate-large exclusion — accepted)"
  fi
else
  echo "OK: no process >${SIG1_MAX_PROC_RSS_GB} GB RSS"
fi
echo

# --- SIG-2: thread count vs soft ulimit ---
echo "=== SIG-2: thread count >${SIG2_THREAD_PCT}% of soft ulimit -u ==="
THREADS=$(ps -L --no-headers -u "$USER" 2>/dev/null | wc -l)
SOFT_LIMIT=$(ulimit -Su 2>/dev/null || ulimit -u 2>/dev/null)
# §11.4.209 review MINOR-4: captured so SIG-3 below can correlate its
# EAGAIN-cascade verdict against real SIG-2 state instead of treating
# EAGAIN as a standalone signal (a proxy-for-a-proxy — see the
# _sig3_effective_threshold() rationale above). Empty = SIG-2 unresolved.
SIG2_PCT_VALUE=""
if [ -n "$SOFT_LIMIT" ] && [ "$SOFT_LIMIT" != "unlimited" ] && [ "$SOFT_LIMIT" -gt 0 ]; then
  PCT=$((THREADS * 100 / SOFT_LIMIT))
  SIG2_PCT_VALUE="$PCT"
  echo "  threads=$THREADS  soft_limit=$SOFT_LIMIT  utilization=${PCT}%"
  if [ "$PCT" -gt "$SIG2_THREAD_PCT" ]; then
    log_fail "SIG-2: thread utilization ${PCT}% exceeds ${SIG2_THREAD_PCT}% threshold"
  else
    echo "OK: thread utilization ${PCT}% within safe zone"
  fi
else
  echo "SKIP (§11.4.3 SKIP-with-reason): ulimit soft-limit unresolvable"
fi
echo

# --- SIG-3: recent EAGAIN cascade in container logs ---
echo "=== SIG-3: EAGAIN cascade in last ${SIG3_EAGAIN_LOOKBACK_MIN} minutes ==="
if command -v podman >/dev/null 2>&1; then
  # Collect container logs from last N minutes filtered for EAGAIN class errors
  EAGAIN_COUNT=0
  CONTAINERS=$(podman ps --format '{{.Names}}' 2>/dev/null | head -20)
  if [ -n "$CONTAINERS" ]; then
    for cname in $CONTAINERS; do
      HITS=$(podman logs --since "${SIG3_EAGAIN_LOOKBACK_MIN}m" "$cname" 2>&1 | \
        grep -iE "resource temporarily unavailable|EAGAIN|SocketException \(11\)|failed to create new (os )?thread|failed to spawn" | \
        wc -l)
      EAGAIN_COUNT=$((EAGAIN_COUNT + HITS))
      if [ "$HITS" -gt 0 ]; then
        echo "  container '$cname': $HITS EAGAIN hits"
      fi
    done
  fi
  echo "  total EAGAIN-class hits last ${SIG3_EAGAIN_LOOKBACK_MIN}min: $EAGAIN_COUNT"
  # §11.4.209 review MINOR-4: the FAIL condition itself is UNCHANGED
  # (SIG3_EAGAIN_THRESHOLD, sensitive by design) — only the message now
  # carries a SIG-2 confidence label so an operator can tell a
  # currently-thread-pressured cascade from a historical/already-subsided
  # one at a glance, without losing detection of either (see the
  # correlation-as-context rationale above SIG3_EAGAIN_THRESHOLD's
  # definition).
  SIG3_CONFIDENCE=$(_sig3_confidence_label "$SIG2_PCT_VALUE")
  echo "  correlation: ${SIG3_CONFIDENCE} (current SIG-2 utilization=${SIG2_PCT_VALUE:-unresolved}%)"
  if [ "$EAGAIN_COUNT" -gt "$SIG3_EAGAIN_THRESHOLD" ]; then
    log_fail "SIG-3: $EAGAIN_COUNT EAGAIN hits exceed ${SIG3_EAGAIN_THRESHOLD} threshold [${SIG3_CONFIDENCE}, SIG-2=${SIG2_PCT_VALUE:-unresolved}%] — thread ceiling being hit"
  else
    echo "OK: EAGAIN hits within safe zone"
  fi
else
  echo "SKIP (§11.4.3): podman unavailable"
fi
echo

# --- SIG-4: user.slice PSI full avg60 ---
echo "=== SIG-4: user.slice memory PSI full avg60 > ${SIG4_PSI_AVG60_LIMIT} ==="
# PSI_FILE is overridable (§11.4.35 consumer-owned data injection point) so
# the REAL parsing+threshold-comparison code path below can be exercised
# against a genuinely-high, realistically-shaped PSI reading captured/seeded
# in a fixture file (see challenges/fixtures/resource_pressure/
# sig4_seeded_psi_fixture.sh) — WITHOUT inducing real sustained host-wide
# memory pressure to test it, which would itself risk the exact
# §12.6/§12.11/§12.12 host-safety violation this detector exists to catch.
# Default path unchanged from the original hardcoded value.
PSI_FILE="${PSI_FILE:-/sys/fs/cgroup/user.slice/user-1000.slice/memory.pressure}"
if [ -r "$PSI_FILE" ]; then
  # Extract "full avg60=X.YZ" and compare to threshold
  FULL_AVG60=$(awk '/^full/ { for(i=1;i<=NF;i++) if($i ~ /^avg60=/) {gsub("avg60=","",$i); print $i} }' "$PSI_FILE")
  echo "  full avg60=$FULL_AVG60 threshold=${SIG4_PSI_AVG60_LIMIT}"
  if [ -n "$FULL_AVG60" ]; then
    # bc-less compare using awk
    OVER=$(awk -v a="$FULL_AVG60" -v b="$SIG4_PSI_AVG60_LIMIT" 'BEGIN { print (a > b) ? 1 : 0 }')
    if [ "$OVER" = "1" ]; then
      log_fail "SIG-4: PSI full avg60=$FULL_AVG60 exceeds ${SIG4_PSI_AVG60_LIMIT} — sustained memory pressure"
    else
      echo "OK: PSI within safe zone"
    fi
  fi
else
  echo "SKIP (§11.4.3): $PSI_FILE not readable"
fi
echo

# --- SIG-5: pathological regex in current process cmdlines ---
echo "=== SIG-5: pathological regex pattern (ugrep -o variable-length alternation) ==="
# Scan currently-running process cmdlines for the class that triggered
# incident 2. Read /proc/*/cmdline to avoid shell-expansion of the pattern.
PATHOLOGICAL_HITS=0
PATHOLOGICAL_LIST=""
for pdir in /proc/[0-9]*; do
  cmdfile="$pdir/cmdline"
  [ -r "$cmdfile" ] || continue
  # Convert NUL-delimited cmdline to space-delimited
  CMDLINE=$(tr '\0' ' ' < "$cmdfile" 2>/dev/null)
  # Skip the challenge's own process to avoid self-match (§11.4.196(D))
  PID=${pdir#/proc/}
  [ "$PID" = "$$" ] && continue
  [ "$PID" = "$PPID" ] && continue
  # §11.4.209 review MINOR-2: $$/$PPID alone only protects THIS run's own
  # PID + parent — it does NOT protect against a CONCURRENT second
  # invocation of this same challenge, whose own `grep -qE
  # "$SIG5_PATHOLOGICAL_PATTERN_REGEX"` child (or an unrelated `grep`/`awk`/
  # `ps` invocation whose cmdline happens to embed the pattern's literal
  # text, e.g. a reviewer grepping this file's source for the pattern
  # string) could appear in THIS instance's /proc snapshot and be
  # misclassified as a pathological ugrep — a §11.4.201(1) false-positive
  # REFUSAL. Requiring comm=="ugrep" outright was considered and REJECTED:
  # the RED fixture (sig5_real_pathological_regex_fixture.sh) deliberately
  # disguises only argv[0] via `exec -a ugrep bash ...` — its real comm is
  # "bash" by kernel design (comm reflects the executed binary, not a
  # disguised argv[0]) — so an exact comm=="ugrep" gate would silently
  # BREAK that fixture's detection and regress the freshly-landed
  # §11.4.115(F) RED evidence. Instead: exclude the SPECIFIC helper-tool
  # comms this script itself spawns as children throughout SIG-1..SIG-5
  # (grep/awk/ps) — those are exactly the process classes a concurrent
  # instance's own internals, or an unrelated source-grep, would present
  # as, and NONE of them is a legitimate SIG-5 target (the real forensic
  # incident's comm was "ugrep"; the fixture's disguised comm is "bash";
  # neither is ever "grep"/"awk"/"ps"). Detection power is unchanged for
  # both the real-incident class and the fixture's disguised-argv class.
  COMM=$(tr -d '\n' < "$pdir/comm" 2>/dev/null)
  case "$COMM" in
    grep|awk|ps) continue ;;
  esac
  # Match the pathological class
  if echo "$CMDLINE" | grep -qE "$SIG5_PATHOLOGICAL_PATTERN_REGEX"; then
    PATHOLOGICAL_HITS=$((PATHOLOGICAL_HITS + 1))
    RSS_KB=$(awk '/^VmRSS:/ {print $2}' "$pdir/status" 2>/dev/null)
    PATHOLOGICAL_LIST="${PATHOLOGICAL_LIST}\n  PID=$PID RSS=${RSS_KB}KB CMD=$(echo "$CMDLINE" | head -c 200)"
  fi
done
if [ "$PATHOLOGICAL_HITS" -gt 0 ]; then
  log_fail "SIG-5: $PATHOLOGICAL_HITS process(es) running pathological regex"
  printf "$PATHOLOGICAL_LIST\n"
else
  echo "OK: no pathological-regex processes detected"
fi
echo

# --- Verdict ---
echo "=== summary ==="
if [ "$FAILURES" -eq 0 ]; then
  echo "PASS: no resource-pressure signatures over threshold"
  exit 0
else
  echo "FAIL: $FAILURES signature(s) tripped"
  for m in "${FAIL_MESSAGES[@]}"; do
    echo "  - $m"
  done
  echo
  echo "Take corrective action per docs/incidents/2026-08-18-perceived-forced-logout-2nd.md:"
  echo "  - SIG-1: identify + kill runaway process"
  echo "  - SIG-2: reduce parallel subagent fan-out"
  echo "  - SIG-3: examine container that emits EAGAIN, throttle its outbound"
  echo "  - SIG-4: reduce memory-consuming workload"
  echo "  - SIG-5: kill the pathological regex process immediately"
  exit 1
fi
