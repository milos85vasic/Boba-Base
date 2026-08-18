#!/usr/bin/env bash
# ddos_resilience_challenge.sh — BOB-074 DDoS-class testing scaffold.
#
# boba has three public HTTP surfaces vulnerable to a naive flood:
#   - merge search    :7187  (FastAPI/uvicorn — fans out to up to 43 trackers
#                              on POST /api/v1/search, expensive)
#   - qBittorrent WebUI :7185 (linuxserver/qbittorrent, network_mode: host)
#   - Boba Jackett API :7189  (Go/Gin, owns Jackett credentials + overrides)
#
# This challenge drives a BOUNDED, LOCALHOST-ONLY concurrency ramp against
# each endpoint's cheap health surface and asserts three things per §11.4.85
# (stress + chaos mandate) / §11.4.27 (DDoS test-type coverage):
#
#   (a) CRASH RESISTANCE   — no 5xx and no connection failure (including a
#                             client-side timeout under load — from the
#                             caller's perspective an endpoint that never
#                             answers within its timeout budget is exactly as
#                             "down" as one that resets the connection) under
#                             the ramp.
#   (b) RATE LIMITING      — a 429 (or equivalent) appears once a configured
#                             threshold is exceeded. §11.4.115 polarity:
#                             RED_MODE=1 reproduces boba's CURRENT real state
#                             (no rate limiter anywhere in the stack — verified
#                             2026-08-18: no slowapi/limiter/throttle in the
#                             Python service, no rate-limit middleware in the
#                             Go services, no nginx/reverse-proxy layer) by
#                             asserting the ABSENCE of any 429 under heavy
#                             load; RED_MODE=0 (default, GREEN guard) treats
#                             that same absence as an honest §11.4.3 SKIP
#                             (reason=extension_absent) rather than a bluffed
#                             PASS or an unearned FAIL — §11.4.6 forbids
#                             inventing a threshold nothing enforces. The day
#                             a rate limiter is wired, GREEN mode starts
#                             asserting 429s appear (PASS) and RED_MODE=1
#                             starts FAILing (defect fixed) — real polarity,
#                             "strip rate limiting -> challenge FAILs" holds
#                             from that point forward.
#   (c) CROSS-ENDPOINT ISOLATION — while one endpoint is under its heaviest
#                             tier, the OTHER two stay responsive (2xx within
#                             a bounded latency).
#
# Deliberately OUT OF SCOPE (documented, not silently skipped — see
# docs/testing/ddos_resilience.md "Scoping decisions"): the real fanout path
# `POST /api/v1/search` is NEVER driven by this challenge — hammering it would
# flood up to 43 REAL third-party tracker sites (risking IP bans on shared
# trackers, violating good-netizen practice, and doing real off-host damage
# no localhost-only chaos budget can bound). The cheap `/health` /
# `/api/v1/config` surface stands in for "the merge-search process is up and
# answering", which is what §11.4.85's crash-resistance clause needs.
#
# §12.6/§12.11 host-safety: concurrency capped at 50, total requests per
# endpoint capped at 90 (3 tiers x 30), per-request timeout 3s, per-tier
# hard wall-clock BUDGET 12s (a genuinely slow backend gets a smaller SAMPLE
# — fewer requests launched — never a longer-running script; see
# run_curl_status_probe). Measured worst case (2026-08-18, boba-jackett's
# amplifying /healthz — see docs/testing/ddos_resilience.md "Findings"): well
# under a minute per endpoint. Never targets anything but 127.0.0.1. Never
# forces a real crash — self-validation exercises a THROWAWAY local python3
# server, never the real boba stack.
#
# §11.4.10: no credentials are used or logged — every probed path is
# reachable unauthenticated (qBittorrent WebUI's `/` serves its login page
# without needing admin/admin).
#
# Exit:
#   0 = all PASS (SKIPs allowed — honest gaps, not failures)
#   1 = one or more FAIL
#   2 = invocation error (curl itself absent — nothing here can run)

set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RED_MODE="${RED_MODE:-0}"
MODE="${1:-}"

# --- bounded chaos knobs (§12.6/§12.11 — do not raise without re-justifying) --
# Discovery during authoring (2026-08-18, documented in
# docs/testing/ddos_resilience.md): boba-jackett's /healthz makes a
# SYNCHRONOUS, uncached upstream Jackett.GetCatalog() call on every hit
# (qBitTorrent-go/internal/jackettapi/health.go) — at c=10/n=90/timeout=5s the
# very first live run took 47s+ for ONE tier because requests queued behind
# that upstream call. These knobs are deliberately conservative so a
# genuinely-slow endpoint can still be characterized honestly without letting
# any single tier (or the whole challenge) run away past a bounded budget.
CONCURRENCY_TIERS=(10 25 50)
REQUESTS_PER_TIER=50        # must be >= max(CONCURRENCY_TIERS) — `ab` refuses c > n
REQUEST_TIMEOUT_S=3
TIER_WALLCLOCK_BUDGET_S=12   # hard early-stop per tier regardless of $REQUESTS_PER_TIER
CROSS_ENDPOINT_TIMEOUT_S=3

EP_NAMES=(merge_search qbittorrent boba_jackett)

ep_url() {
  case "$1" in
    merge_search) echo "http://127.0.0.1:7187/health" ;;
    qbittorrent)  echo "http://127.0.0.1:7185/" ;;
    boba_jackett) echo "http://127.0.0.1:7189/healthz" ;;
  esac
}
ep_label() {
  case "$1" in
    merge_search) echo "merge search :7187 (fanout endpoint's health surface — see scoping note)" ;;
    qbittorrent)  echo "qBittorrent WebUI :7185" ;;
    boba_jackett) echo "Boba Jackett API :7189" ;;
  esac
}

pass=0
fail=0
skip=0
notes=()

verdict() {
  local kind="$1" msg="$2"
  case "$kind" in
    PASS) pass=$((pass + 1)); echo "  [PASS] $msg" ;;
    FAIL) fail=$((fail + 1)); echo "  [FAIL] $msg" ;;
    SKIP) skip=$((skip + 1)); echo "  [SKIP] $msg" ;;
  esac
}

if ! command -v curl >/dev/null 2>&1; then
  echo "=== ddos_resilience_challenge ==="
  echo "INVOCATION ERROR: curl not found — this challenge has no HTTP client to drive load with."
  exit 2
fi

HAVE_AB=0
command -v ab >/dev/null 2>&1 && HAVE_AB=1

# --- curl-parallel-loop: the primary, tool-independent stress+probe --------
# Fires up to $n requests at $url with at most $c concurrent in flight,
# appending "<http_code> <curl_exit_code>" per request to $outfile. Each
# append is a short single line (< PIPE_BUF) so concurrent O_APPEND writers
# don't tear. Enforces a hard wall-clock budget ($TIER_WALLCLOCK_BUDGET_S) —
# once the budget is spent, no NEW requests are launched (in-flight ones are
# still awaited, self-bounded by their own --max-time) — so a genuinely-slow
# backend degrades the SAMPLE SIZE, never the total test duration.
run_curl_status_probe() {
  local url="$1" n="$2" c="$3" outfile="$4"
  : > "$outfile"
  local start_ts launched=0
  start_ts=$(date +%s)
  local pids=()
  local i
  for ((i = 0; i < n; i++)); do
    now_ts=$(date +%s)
    if [ $((now_ts - start_ts)) -ge "$TIER_WALLCLOCK_BUDGET_S" ]; then
      echo "    (wall-clock budget ${TIER_WALLCLOCK_BUDGET_S}s reached — stopped after launching $launched/$n requests)"
      break
    fi
    (
      code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time "$REQUEST_TIMEOUT_S" "$url" 2>/dev/null)
      rc=$?
      echo "${code:-000} ${rc}" >> "$outfile"
    ) &
    pids+=("$!")
    launched=$((launched + 1))
    if [ "${#pids[@]}" -ge "$c" ]; then
      wait "${pids[@]}" 2>/dev/null
      pids=()
    fi
  done
  [ "${#pids[@]}" -gt 0 ] && wait "${pids[@]}" 2>/dev/null
  return 0
}

tally_field() {
  # tally_field <file> <awk-pattern-on-\$1>
  awk -v pat="$2" '$1 ~ pat' "$1" 2>/dev/null | wc -l | tr -d '[:space:]'
}
tally_nonzero_rc() {
  awk '$2 != 0' "$1" 2>/dev/null | wc -l | tr -d '[:space:]'
}
tally_rc() {
  # tally_rc <file> <exact-curl-exit-code>
  awk -v rc="$2" '$2 == rc' "$1" 2>/dev/null | wc -l | tr -d '[:space:]'
}

# --- §11.4.107(10)-style self-validation: prove the crash-detector can see -
# a genuinely broken endpoint. Spins up two THROWAWAY local python3 servers
# (never the real boba stack) — one that always answers 200, one that always
# answers 500 — and asserts our detection logic PASSes the good one and
# FAILs the bad one. This validates assertion (a)'s detector honesty; the
# rate-limit detector (b) has no equivalent synthetic fixture in this round
# (documented gap — see docs/testing/ddos_resilience.md "Self-validation
# scope").
if [ "$MODE" = "--self-validate" ]; then
  echo "=== ddos_resilience_challenge: self-validate ==="
  if ! command -v python3 >/dev/null 2>&1; then
    echo "SKIP: python3 not found — cannot spin up golden-good/golden-bad fixtures"
    exit 0
  fi
  tmp="$(mktemp -d)"
  cleanup_sv() {
    [ -n "${good_pid:-}" ] && kill "$good_pid" >/dev/null 2>&1
    [ -n "${bad_pid:-}" ] && kill "$bad_pid" >/dev/null 2>&1
    rm -rf "$tmp"
  }
  trap cleanup_sv EXIT

  cat > "$tmp/good_server.py" <<'PYEOF'
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")
    def log_message(self, *a):
        pass

port = int(sys.argv[1])
ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
PYEOF
  cat > "$tmp/bad_server.py" <<'PYEOF'
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(500)
        self.end_headers()
        self.wfile.write(b"synthetic golden-bad failure")
    def log_message(self, *a):
        pass

port = int(sys.argv[1])
ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
PYEOF

  good_port=18743
  bad_port=18744
  python3 "$tmp/good_server.py" "$good_port" &
  good_pid=$!
  python3 "$tmp/bad_server.py" "$bad_port" &
  bad_pid=$!

  # Wait for both to accept connections (bounded poll, host-safe).
  ok=0
  for _ in $(seq 1 30); do
    if curl -sS -o /dev/null --max-time 1 "http://127.0.0.1:$good_port/" 2>/dev/null \
       && curl -sS -o /dev/null --max-time 1 "http://127.0.0.1:$bad_port/" 2>/dev/null; then
      ok=1
      break
    fi
    sleep 0.1
  done
  if [ "$ok" -ne 1 ]; then
    echo "FAIL: self-validate — golden fixtures never came up"
    exit 1
  fi

  goodfile="$tmp/good.log"
  badfile="$tmp/bad.log"
  run_curl_status_probe "http://127.0.0.1:$good_port/" 30 10 "$goodfile"
  run_curl_status_probe "http://127.0.0.1:$bad_port/" 30 10 "$badfile"

  good_5xx=$(tally_field "$goodfile" '^5')
  good_fail=$(tally_nonzero_rc "$goodfile")
  bad_5xx=$(tally_field "$badfile" '^5')
  bad_fail=$(tally_nonzero_rc "$badfile")

  echo "golden-good: 5xx=$good_5xx conn_fail=$good_fail (expect both 0)"
  echo "golden-bad:  5xx=$bad_5xx conn_fail=$bad_fail (expect 5xx=30)"

  sv_bad=0
  if [ "$good_5xx" != "0" ] || [ "$good_fail" != "0" ]; then
    echo "[SELF-VAL BAD] crash-detector flagged the golden-GOOD fixture as crashing"
    sv_bad=1
  fi
  if [ "$bad_5xx" != "30" ]; then
    echo "[SELF-VAL BAD] crash-detector did NOT see all 30/30 5xx on the golden-BAD fixture"
    sv_bad=1
  fi

  if [ "$sv_bad" -eq 0 ]; then
    echo "PASS: self-validate — crash-resistance detector correctly distinguishes golden-good from golden-bad"
    exit 0
  fi
  echo "FAIL: self-validate — detector honesty check failed"
  exit 1
fi

# --- Live run ----------------------------------------------------------------
echo "=== ddos_resilience_challenge (BOB-074) ==="
echo "RED_MODE=$RED_MODE  (0=GREEN guard, 1=reproduce pre-fix defect state)"
echo "stress tool: curl-parallel-loop (primary)$( [ "$HAVE_AB" -eq 1 ] && echo ' + ab (supplementary evidence)' || echo ' — ab not installed, curl-loop only')"
echo "tiers: ${CONCURRENCY_TIERS[*]}  requests/tier: $REQUESTS_PER_TIER  per-request timeout: ${REQUEST_TIMEOUT_S}s"
echo ""

workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT

for name in "${EP_NAMES[@]}"; do
  url="$(ep_url "$name")"
  label="$(ep_label "$name")"
  echo "--- $name: $label ---"

  reachable_code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 3 "$url" 2>/dev/null)
  reachable_rc=$?
  if [ "$reachable_rc" -ne 0 ] || [ -z "$reachable_code" ] || [ "$reachable_code" = "000" ]; then
    verdict SKIP "$name unreachable at $url (reason=services_not_running — start the stack via ./start.sh to exercise this endpoint)"
    notes+=("$name: SKIP'd — stack not running at probe time")
    echo ""
    continue
  fi
  echo "    reachable: HTTP $reachable_code"

  # --- (a) crash resistance across the concurrency ramp ---
  heaviest_c="${CONCURRENCY_TIERS[-1]}"
  crash_5xx_total=0
  crash_fail_total=0
  crash_requests_total=0
  for c in "${CONCURRENCY_TIERS[@]}"; do
    outfile="$workdir/${name}_c${c}.log"
    t0=$(date +%s.%N 2>/dev/null || date +%s)
    run_curl_status_probe "$url" "$REQUESTS_PER_TIER" "$c" "$outfile"
    t1=$(date +%s.%N 2>/dev/null || date +%s)
    n=$(wc -l < "$outfile" 2>/dev/null | tr -d '[:space:]')
    fivexx=$(tally_field "$outfile" '^5')
    connfail=$(tally_nonzero_rc "$outfile")
    timeouts=$(tally_rc "$outfile" 28)
    otherfail=$((connfail - timeouts))
    r429=$(tally_field "$outfile" '^429')
    crash_5xx_total=$((crash_5xx_total + fivexx))
    crash_fail_total=$((crash_fail_total + connfail))
    crash_requests_total=$((crash_requests_total + n))
    echo "    tier c=$c n=$n: 5xx=$fivexx conn_fail=$connfail (timeout=$timeouts other=$otherfail) 429=$r429  elapsed=$(awk -v a="$t0" -v b="$t1" 'BEGIN{printf "%.2f", b-a}')s"
    if [ "$HAVE_AB" -eq 1 ] && [ "$c" = "$heaviest_c" ]; then
      if [ "$REQUESTS_PER_TIER" -lt "$c" ]; then
        echo "    --- ab evidence skipped: REQUESTS_PER_TIER ($REQUESTS_PER_TIER) < concurrency ($c) — ab refuses c > n ---"
      else
        echo "    --- ab evidence (heaviest tier, supplementary; -t deliberately omitted — combining -n with -t"
        echo "        makes ab treat -t as authoritative and run far past the requested -n, per ApacheBench's"
        echo "        own '-t implies -n 50000' semantics; observed 2373 completed requests in one early run"
        echo "        against merge_search's /health when -t was present) ---"
        ab -n "$REQUESTS_PER_TIER" -c "$c" -s "$REQUEST_TIMEOUT_S" -r "$url" 2>&1 \
          | grep -E "Complete requests:|Failed requests:|Non-2xx responses:|Requests per second:|Time per request:" \
          | sed 's/^/    ab: /'
      fi
    fi
  done

  if [ "$crash_5xx_total" -eq 0 ] && [ "$crash_fail_total" -eq 0 ]; then
    verdict PASS "$name: 0/$crash_requests_total requests returned 5xx or failed to connect across tiers ${CONCURRENCY_TIERS[*]}"
  else
    verdict FAIL "$name: $crash_5xx_total 5xx + $crash_fail_total connection failures out of $crash_requests_total requests — endpoint degraded under bounded load"
  fi

  # --- (b) rate limiting: real RED/GREEN polarity, no invented threshold ---
  heaviest_file="$workdir/${name}_c${heaviest_c}.log"
  r429_heaviest=$(tally_field "$heaviest_file" '^429')
  if [ "$r429_heaviest" -gt 0 ]; then
    if [ "$RED_MODE" = "1" ]; then
      verdict FAIL "$name: rate limiting IS engaged ($r429_heaviest x 429 at c=$heaviest_c) — RED expected its absence; defect appears fixed"
    else
      verdict PASS "$name: rate limiting engaged — $r429_heaviest x 429 observed at heaviest tier c=$heaviest_c"
    fi
  else
    if [ "$RED_MODE" = "1" ]; then
      verdict PASS "$name: confirmed absence of rate limiting at c=$heaviest_c (RED reproduces the real current defect)"
    else
      verdict SKIP "$name: no rate limiting configured (reason=extension_absent — no rate-limit middleware/proxy exists anywhere in boba's stack as of 2026-08-18; tracked as BOB-074 followup, see docs/testing/ddos_resilience.md)"
      notes+=("$name: rate limiting SKIP'd — extension_absent, followup filed")
    fi
  fi

  # --- (c) cross-endpoint isolation while this endpoint is under load ---
  sibling_file="$workdir/${name}_siblings.log"
  : > "$sibling_file"
  sib_pids=()
  for other in "${EP_NAMES[@]}"; do
    [ "$other" = "$name" ] && continue
    ourl="$(ep_url "$other")"
    (
      st0=$(date +%s.%N 2>/dev/null || date +%s)
      ocode=$(curl -sS -o /dev/null -w '%{http_code}' --max-time "$CROSS_ENDPOINT_TIMEOUT_S" "$ourl" 2>/dev/null)
      orc=$?
      st1=$(date +%s.%N 2>/dev/null || date +%s)
      elapsed=$(awk -v a="$st0" -v b="$st1" 'BEGIN{printf "%.3f", b-a}')
      echo "$other ${ocode:-000} $orc $elapsed" >> "$sibling_file"
    ) &
    sib_pids+=("$!")
  done
  # Re-run the heaviest tier concurrently with the sibling probes above.
  run_curl_status_probe "$url" "$REQUESTS_PER_TIER" "$heaviest_c" "$workdir/${name}_isolation.log"
  [ "${#sib_pids[@]}" -gt 0 ] && wait "${sib_pids[@]}" 2>/dev/null

  isolation_bad=0
  isolation_msgs=()
  while read -r sname scode src selapsed; do
    [ -z "${sname:-}" ] && continue
    if [ "$src" != "0" ] || ! [[ "$scode" =~ ^2 ]]; then
      isolation_bad=1
      isolation_msgs+=("$sname unreachable/errored while $name was under load (code=$scode rc=$src elapsed=${selapsed}s)")
    else
      isolation_msgs+=("$sname stayed responsive (code=$scode elapsed=${selapsed}s) while $name was under load")
    fi
  done < "$sibling_file"
  for m in "${isolation_msgs[@]}"; do echo "    $m"; done
  if [ "$isolation_bad" -eq 0 ]; then
    verdict PASS "$name under load: sibling endpoints stayed responsive (cross-endpoint isolation held)"
  else
    verdict FAIL "$name under load: at least one sibling endpoint degraded — no isolation between endpoints"
  fi

  echo ""
done

echo "=========================================="
echo "Summary: PASS=$pass  FAIL=$fail  SKIP=$skip"
if [ "${#notes[@]}" -gt 0 ]; then
  echo "Notes:"
  for n in "${notes[@]}"; do echo "  - $n"; done
fi
echo "=========================================="

if [ "$fail" -gt 0 ]; then
  echo "FAIL: ddos_resilience_challenge — $fail check(s) failed"
  exit 1
fi
echo "PASS: ddos_resilience_challenge — bounded DDoS-resilience checks complete; honest gaps tracked as followups"
exit 0
