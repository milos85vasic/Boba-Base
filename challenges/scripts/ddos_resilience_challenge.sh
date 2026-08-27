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
#                             threshold is exceeded, per endpoint. §11.4.115
#                             polarity: RED_MODE=1 asserts the ABSENCE of any
#                             429 under heavy load (the pre-limiter defect
#                             state); RED_MODE=0 (default, GREEN guard) asserts
#                             a 429 DOES appear, and treats its absence as an
#                             honest §11.4.3 SKIP (reason=extension_absent)
#                             rather than a bluffed PASS or an unearned FAIL —
#                             §11.4.6 forbids inventing a threshold nothing
#                             enforces. STATE AS OF 2026-08-26 (measured live,
#                             this same run prints it): merge_search :7187 now
#                             DOES enforce a limiter — `x-ratelimit-limit: 120`
#                             with a `retry-after`, 33 x 429 at c=50 — so it
#                             PASSes in GREEN and would FAIL in RED, exactly
#                             the polarity flip this clause predicted. :7185
#                             and :7189 still SKIP as extension_absent. (The
#                             2026-08-18 note that NO limiter existed anywhere
#                             in the stack is superseded; it was true when
#                             written and is no longer.)
#   (c) CROSS-ENDPOINT ISOLATION — while one endpoint is under its heaviest
#                             tier, the OTHER two stay RESPONSIVE within a
#                             bounded latency. "Responsive" is any 2xx, OR a
#                             429 carrying a WELL-FORMED Retry-After
#                             (BOB-163, operator decision 2026-08-26: "Yes,
#                             if Retry-After is well-formed" — a 429 that
#                             tells the caller when to come back is evidence
#                             of a LIVE service correctly protecting itself,
#                             not of a degraded one). DEGRADED is a
#                             connection failure, a timeout, any 5xx, any
#                             other non-2xx, and a 429 whose Retry-After is
#                             ABSENT or MALFORMED. See sibling_classify().
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
# endpoint capped at 200 — a 3-tier ramp of REQUESTS_PER_TIER=50 (150, and the
# live run prints "0/150 requests" to confirm it) plus ONE re-run of the
# heaviest tier during the assertion-(c) isolation probe (50). (This line read
# "capped at 90 (3 tiers x 30)" until 2026-08-26; REQUESTS_PER_TIER has been 50
# since it was raised to satisfy `ab`'s c <= n rule at the c=50 tier, and the
# isolation re-run was never counted at all — a stale published number, which
# is the same defect class as the stale rate-limiter claims corrected above.)
# Per-request timeout 3s, per-tier
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

# --- the rate-limit detector: ONE implementation, two consumers -------------
# §11.4.249 (producer != oracle): the live run and --self-validate call the
# SAME functions below, so a mutation to the detector breaks the self-test
# too. A second copy inside the self-test would validate the copy, not the
# detector that actually mints live verdicts — a tautology.
#
# ratelimit_classify answers the only question the detector asks: did this
# endpoint emit any 429 under the burst? It matches on FIELD 1 of the probe
# log — the curl-reported HTTP STATUS CODE — and never on response bodies or
# headers. §11.4.201(7)(a): a token that MENTIONS rate limiting is a CARRIER,
# not the thing; the golden-FALSE carrier fixture in --self-validate locks
# that structural match in so it cannot regress to a substring match.
ratelimit_classify() {
  local n429
  n429=$(tally_field "$1" '^429')
  if [ "${n429:-0}" -gt 0 ] 2>/dev/null; then echo "engaged"; else echo "absent"; fi
}

# ratelimit_verdict_kind maps (class, RED_MODE) -> PASS|FAIL|SKIP. Pure: it
# prints the kind and nothing else and touches no counters, so
# --self-validate can assert the FULL truth table without side effects.
#   engaged + GREEN -> PASS  a configured limiter demonstrably fires
#   engaged + RED   -> FAIL  RED reproduces the ABSENCE; a 429 means fixed
#   absent  + GREEN -> SKIP  honest §11.4.3 extension_absent, never a bluff
#   absent  + RED   -> PASS  RED reproduces boba's real current state
ratelimit_verdict_kind() {
  case "$1/$2" in
    engaged/1) echo FAIL ;;
    engaged/*) echo PASS ;;
    absent/1)  echo PASS ;;
    *)         echo SKIP ;;
  esac
}

# --- the sibling-responsiveness detector (BOB-163) --------------------------
# §11.4.249 (producer != oracle): assertion (c)'s live verdict and
# --self-validate's golden fixtures call the SAME two functions below, so a
# mutation to the parse breaks the self-test too. A second copy of the parse
# inside the self-test would validate the copy, not the detector that ships.
#
# WHY THIS EXISTS. Assertion (c) originally required a sibling probe to answer
# `^2`. :7187 now enforces a real limiter (measured live 2026-08-26:
# `x-ratelimit-limit: 120`, `x-ratelimit-remaining: 86`, `retry-after: 45`,
# `server: uvicorn`). A full run of this challenge sends ~250 requests to
# :7187, so a sibling probe fired while ANOTHER endpoint is under its heaviest
# tier lands on an exhausted bucket and gets a 429 — which the `^2` rule read
# as "endpoint degraded". That is a §11.4.1 FAIL-bluff: it condemns a service
# that is working correctly and protecting itself exactly as designed.
#
# RESIDUAL RISK, STATED NOT HIDDEN (§11.4.6). A genuinely WEDGED endpoint that
# nonetheless answers 429-with-a-well-formed-Retry-After would be classified
# RESPONSIVE by this detector and would pass assertion (c). Parsing the
# Retry-After NARROWS that hole — a limiter that emits a real, positive,
# parseable "come back in N" is running enough code to compute and serialize
# one, and the common degradation shapes (reset, timeout, 5xx, 429 with no
# header at all) are all still caught — but it does NOT close it. Closing it
# needs a semantic liveness oracle (assert the sibling still SERVES its own
# payload once its window reopens), which is out of this challenge's bounded
# localhost chaos budget and is NOT claimed here. Assertion (c) therefore
# proves "the sibling's HTTP stack is alive and answering coherently under a
# neighbour's load", never "the sibling is fully functional".

# HAVE_DATE_PARSE is itself a §11.4.201(7)(b) CONTROL NEEDLE: it runs a string
# KNOWN to be a valid IMF-fixdate through the exact parser retry_after_wellformed
# would use. If that needle does not parse, the host has no usable date parser
# and a `date -d` rejection below would be a property of the INSTRUMENT, not of
# the header — so the semantic parse is skipped and the structural match stands
# alone, honestly and without pretending a check ran that could not.
HAVE_DATE_PARSE=0
DATE_PARSE_STATUS=absent
if date -d "Sun, 06 Nov 1994 08:49:37 GMT" +%s >/dev/null 2>&1; then
  # NEGATIVE CONTROL (MINOR-2). The accept-valid needle alone cannot tell a
  # correct parser from one that accepts EVERYTHING: both answer "yes" to a
  # real date. Without this second probe a permissive/stubbed date(1) is
  # trusted, `Sun, 32 Nov 1994 25:99:99 GMT` parses "fine", and the fixture
  # that depends on rejection then accuses the DETECTOR of misclassifying -
  # the same instrument-vs-product misattribution the r429_baddate gating
  # fixed, for the opposite parser shape. A needle that only proves "can see a
  # valid date" does not prove "can reject an invalid one" (§11.4.201(7)(b)).
  if date -d "Sun, 32 Nov 1994 25:99:99 GMT" +%s >/dev/null 2>&1; then
    DATE_PARSE_STATUS=unreliable
  else
    HAVE_DATE_PARSE=1
    DATE_PARSE_STATUS=usable
  fi
fi

# retry_after_wellformed <raw-header-value> -> 0 well-formed, 1 otherwise.
# The operator decision is "well-formed", NOT "present": a non-empty check
# would accept `Retry-After: soon-ish` and hand the same PASS to a service
# emitting noise. So this PARSES.
retry_after_wellformed() {
  local v="${1:-}"
  v="${v//$'\r'/}"
  v="${v//$'\n'/}"
  # trim leading/trailing whitespace (OWS is legal around a field value)
  v="${v#"${v%%[![:space:]]*}"}"
  v="${v%"${v##*[![:space:]]}"}"
  [ -n "$v" ] || return 1

  # Form 1 — delta-seconds (RFC 9110 §10.2.3: 1*DIGIT). Required POSITIVE:
  # `0` and any negative value are not a limiter telling the caller when to
  # come back, they are noise in the shape of a number.
  if [[ "$v" =~ ^[0-9]+$ ]]; then
    [ "$v" -gt 0 ] 2>/dev/null && return 0
    return 1
  fi

  # Form 2 — HTTP-date. RFC 9110 §5.6.7 permits a SENDER only the IMF-fixdate
  # form, but REQUIRES a RECIPIENT to accept all three; rejecting a legal
  # obsolete form would be exactly the §11.4.201(1) false-positive refusal
  # this whole change exists to remove. Structure is matched STRUCTURALLY
  # (§11.4.201(7)(a)) — anchored, field-shaped, never a substring sniff.
  local d3='(Mon|Tue|Wed|Thu|Fri|Sat|Sun)'
  local df='(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)'
  local mo='(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)'
  local tm='[0-9]{2}:[0-9]{2}:[0-9]{2}'
  local re_imf="^${d3}, [0-9]{2} ${mo} [0-9]{4} ${tm} GMT\$"
  local re_850="^${df}, [0-9]{2}-${mo}-[0-9]{2} ${tm} GMT\$"
  local re_asc="^${d3} ${mo} [ 0-9][0-9] ${tm} [0-9]{4}\$"
  local shaped=0
  if   [[ "$v" =~ $re_imf ]]; then shaped=1
  elif [[ "$v" =~ $re_850 ]]; then shaped=1
  elif [[ "$v" =~ $re_asc ]]; then shaped=1
  fi
  [ "$shaped" -eq 1 ] || return 1

  # Structure is NECESSARY, not SUFFICIENT: `Sun, 32 Nov 1994 25:99:99 GMT`
  # is correctly shaped and is not a date. Parse it for real wherever the
  # control needle above proved a parser exists.
  if [ "$HAVE_DATE_PARSE" -eq 1 ]; then
    date -d "$v" +%s >/dev/null 2>&1 || return 1
  fi
  return 0
}

# sibling_classify <http_code> <curl_rc> <retry_after_raw> -> responsive|degraded
# Pure: prints the class and nothing else, touches no counters, so
# --self-validate can drive the whole truth table without side effects.
sibling_classify() {
  local code="${1:-000}" rc="${2:-1}" retry="${3:-}"
  # curl rc != 0 covers connection reset/refused (7) AND the timeout (28)
  # assertion (a) already treats as "down from the caller's perspective".
  if [ "$rc" != "0" ]; then echo degraded; return 0; fi
  case "$code" in
    2??) echo responsive ;;
    429) if retry_after_wellformed "$retry"; then echo responsive; else echo degraded; fi ;;
    *)   echo degraded ;;
  esac
  return 0
}

# sibling_reason renders the human explanation for a class. Display only — it
# never decides anything, so it can never disagree with sibling_classify.
sibling_reason() {
  local code="${1:-000}" rc="${2:-1}" retry="${3:-}"
  if [ "$rc" != "0" ]; then
    if [ "$rc" = "28" ]; then echo "no answer within ${CROSS_ENDPOINT_TIMEOUT_S}s (curl rc=28 timeout)"
    else echo "connection failed (curl rc=$rc, code=$code)"; fi
    return 0
  fi
  case "$code" in
    2??) echo "HTTP $code" ;;
    429)
      if retry_after_wellformed "$retry"; then
        echo "HTTP 429 with well-formed Retry-After: $retry — limiter engaged, service alive and protecting itself"
      elif [ -z "$retry" ]; then
        echo "HTTP 429 carrying NO Retry-After header — cannot distinguish a limiter from a wedged service"
      else
        echo "HTTP 429 with MALFORMED Retry-After: '$retry' — non-empty is not well-formed"
      fi ;;
    *)   echo "HTTP $code" ;;
  esac
}

# sibling_isolation_report <sibling-log> <endpoint-under-load> <expected-count>
# Consumes a probe_sibling log and renders assertion (c)'s decision:
#   prints one indented human line per sibling
#   returns 0 = isolation HELD, 1 = at least one sibling DEGRADED **or** fewer
#   observations were parsed than probes were launched
#
# <expected-count> is how many sibling probes were LAUNCHED, and the verdict is
# fail-closed against it (MINOR-1): a run may read "isolation held" only when it
# parsed an observation for EVERY probe it fired. A zero-BYTE check catches only
# the narrowest shape of the §11.4.201(6) false-null; these all read "held" without
# the count contract - a blank-line or whitespace-only log (>0 bytes, 0 parsed);
# a TORN final line, where a complete observation lost its trailing newline and
# `while read` skips it, silently dropping the one sibling that WAS degraded
# (hence the `|| [ -n "$sname" ]` guard below); and a PARTIAL log, where a probe
# subshell died before appending and isolation reads "proven" on half the
# evidence. None is reachable from this file's own writers under POSIX append
# semantics (probe_sibling emits one short newline-terminated line per probe, a
# single atomic write below PIPE_BUF), so this is defence in depth against a
# future writer, a full disk or a killed subshell - never a claim that the
# current writers produce torn output.
# §11.4.249 producer != oracle, applied to the WHOLE decision rather than only
# the classifier: the live verdict and --self-validate call THIS function, so
# there is a single seam and no inline second copy of the rule for a mutation
# to diverge (the pre-BOB-163 code inlined the `^2` test in the live loop,
# where no fixture could ever reach it - the §11.4.196(F) configured-not-in-use
# shape).
# $sretry deliberately takes the REST of the line: an HTTP-date contains spaces.
sibling_isolation_report() {
  local logfile="$1" under_load="$2" expected="${3:-0}"
  local bad=0 parsed=0 sname scode src selapsed sretry sclass sreason
  # `|| [ -n "$sname" ]` processes a final line that lost its trailing newline.
  # On true EOF `read` clears every named variable, so the guard is false and
  # the loop terminates - it cannot spin.
  while read -r sname scode src selapsed sretry || [ -n "${sname:-}" ]; do
    [ -z "${sname:-}" ] && continue
    parsed=$((parsed + 1))
    sclass="$(sibling_classify "$scode" "$src" "$sretry")"
    sreason="$(sibling_reason "$scode" "$src" "$sretry")"
    if [ "$sclass" = "degraded" ]; then
      bad=1
      echo "    $sname DEGRADED while $under_load was under load - $sreason (elapsed=${selapsed}s)"
    else
      echo "    $sname stayed responsive while $under_load was under load - $sreason (elapsed=${selapsed}s)"
    fi
  done < "$logfile"
  if [ "$parsed" -lt "$expected" ] 2>/dev/null; then
    if [ "$parsed" -eq 0 ]; then
      echo "    NO SIBLING OBSERVATIONS while $under_load was under load - parsed 0 of $expected probes, so isolation is UNPROVEN (not proven held); treating as degraded (§11.4.201(6) false-null)"
    else
      echo "    INCOMPLETE SIBLING OBSERVATIONS while $under_load was under load - parsed only $parsed of $expected probes, so isolation is UNPROVEN for the missing $((expected - parsed)); treating as degraded (§11.4.201(6) false-null)"
    fi
    return 1
  fi
  return "$bad"
}

# probe_sibling <label> <url> <outfile> <hdrfile>
# ONE bounded request; appends a single short line (< PIPE_BUF, so concurrent
# O_APPEND writers do not tear) of the form
#   "<label> <http_code> <curl_rc> <elapsed_s> <retry-after raw...>"
# The Retry-After value is LAST because an HTTP-date contains spaces: the
# reader takes it as the rest of the line. Used by BOTH the live assertion-(c)
# path and --self-validate, so the self-test exercises the real probe, real
# curl, real header capture and real log format — not a stand-in.
probe_sibling() {
  local label="$1" ourl="$2" outfile="$3" hdrfile="$4"
  local st0 st1 ocode orc elapsed retry
  : > "$hdrfile"
  st0=$(date +%s.%N 2>/dev/null || date +%s)
  ocode=$(curl -sS -o /dev/null -D "$hdrfile" -w '%{http_code}' --max-time "$CROSS_ENDPOINT_TIMEOUT_S" "$ourl" 2>/dev/null)
  orc=$?
  st1=$(date +%s.%N 2>/dev/null || date +%s)
  elapsed=$(awk -v a="$st0" -v b="$st1" 'BEGIN{printf "%.3f", b-a}')
  # Last occurrence wins (a redirect chain writes several header blocks).
  retry=$(grep -i '^[[:space:]]*retry-after[[:space:]]*:' "$hdrfile" 2>/dev/null \
          | tail -1 | sed 's/^[^:]*:[[:space:]]*//' | tr -d '\r\n')
  echo "$label ${ocode:-000} $orc $elapsed $retry" >> "$outfile"
}

# §11.4.263: never signal a pgid, never trust an unset pid. Validate as an
# integer > 1 before any kill — kill(-1)/killpg(1) SIGKILLs every process of
# this uid, the exact BOB-126 forced-logout mechanism.
kill_pid_safe() {
  local p="${1:-}"
  case "$p" in ''|*[!0-9]*) return 0 ;; esac
  [ "$p" -gt 1 ] 2>/dev/null || return 0
  kill "$p" >/dev/null 2>&1
  return 0
}

# --- §11.4.107(10) self-validation: prove BOTH detectors can actually see --
# Spins up THROWAWAY local python3 servers (never the real boba stack) and
# asserts each detector distinguishes a healthy fixture from a broken one.
# An analyzer that PASSes its own golden-BAD fixture is itself the bluff.
#
# Detector 1 — CRASH RESISTANCE (assertion (a)):
#   golden-GOOD   always 200                  -> must NOT be flagged
#   golden-BAD    always 500                  -> must see 30/30 5xx
#
# Detector 2 — RATE LIMITING (assertion (b)) — added by BOB-114, closing the
# BOB-074 gap where this detector had NO fixture at all and had therefore
# never been observed to FAIL (unvalidated instrumentation, §11.4.115(F);
# the §1.1 mutation "make the 429 tally always report 999" left the old
# self-test fully green, proving it was blind to a detector that would
# certify a completely unprotected deployment as rate-limited):
#   golden-GOOD   200 up to a threshold, 429 past it -> class MUST be
#                 "engaged". This drives the detector's positive arm, which
#                 no fixture had ever exercised.
#   golden-BAD    always 200, never 429 and never 503, no matter the burst
#                 -> class MUST be "absent". This is the artifact BOB-114
#                 names: a deployment with no rate limiting at all.
#   golden-FALSE-WITH-CARRIER (§11.4.201(7)(a), and (1): a false-positive
#                 refusal is as forbidden as a false pass) — 200 responses
#                 carrying X-RateLimit-Limit / X-RateLimit-Remaining /
#                 Retry-After headers AND a body that literally reads
#                 "429 Too Many Requests: rate limit exceeded", while
#                 enforcing nothing. A server that ADVERTISES a limit it
#                 never applies is the exact lookalike a substring-matching
#                 detector false-fires on; class MUST STILL be "absent".
#   Plus the full (class x RED_MODE) verdict truth table, so both polarity
#   arms of ratelimit_verdict_kind are exercised, not just the one boba's
#   current limiter-less state happens to hit.
#
# Detector 3 - SIBLING RESPONSIVENESS (assertion (c)) - added by BOB-163,
# closing the gap where assertion (c)'s oracle had NO fixture at all:
#   golden-GOOD   200, and 429 carrying a well-formed Retry-After (both a
#                 positive delta-seconds AND a real IMF-fixdate) -> responsive
#   golden-BAD    5xx, and connection-refused                    -> degraded
#   golden-BAD-WITH-CARRIER - 429 responses that DO carry a Retry-After header
#                 whose value is `soon-ish` / `0` / `-5` / a correctly-shaped
#                 but impossible `Sun, 32 Nov 1994 25:99:99 GMT`. A detector
#                 that merely checks the header is PRESENT passes every one of
#                 these; only a real parse rejects them. class MUST stay
#                 "degraded".
#
# Returns 0 = detectors honest, 1 = a detector failed its own fixtures.
run_self_validation() {
  echo "=== ddos_resilience_challenge: self-validate ==="
  if ! command -v python3 >/dev/null 2>&1; then
    echo "SKIP: python3 not found (reason=tooling_absent) — cannot spin up golden fixtures"
    return 0
  fi
  # Fixture probes are deliberately smaller than a live tier: these are
  # localhost throwaway servers, so 12 requests at c=6 already drives every
  # detector arm, and fewer forks means less wall-clock on a loaded host.
  # The self-test also runs under its OWN, larger wall-clock budget: the
  # 12s live budget exists to bound a genuinely-slow REAL backend, and
  # borrowing it here would let ordinary host load TRUNCATE the fixture
  # sample and turn a healthy detector into a false FAIL (§11.4.201(1)).
  # SV_MIN_SAMPLE is the floor below which a truncated sample is not
  # evidence either way (§11.4.201(6)) and the self-test says so instead of
  # guessing.
  local SV_PROBE_N=12 SV_PROBE_C=6 SV_MIN_SAMPLE=8
  local sv_saved_budget="$TIER_WALLCLOCK_BUDGET_S"
  TIER_WALLCLOCK_BUDGET_S=30
  local tmp
  tmp="$(mktemp -d)"
  sv_pids=()
  cleanup_sv() {
    local p
    for p in ${sv_pids[@]+"${sv_pids[@]}"}; do kill_pid_safe "$p"; done
    rm -rf "$tmp"
    TIER_WALLCLOCK_BUDGET_S="$sv_saved_budget"
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

srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
print("PORT=%d" % srv.server_address[1], flush=True)
srv.serve_forever()
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

srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
print("PORT=%d" % srv.server_address[1], flush=True)
srv.serve_forever()
PYEOF

  # golden-GOOD for the rate-limit detector: a limiter that really fires.
  cat > "$tmp/rl_enforcing_server.py" <<'PYEOF'
import sys, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else 5
_lock = threading.Lock()
_seen = 0

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        global _seen
        with _lock:
            _seen += 1
            n = _seen
        if n > LIMIT:
            self.send_response(429)
            self.send_header("Retry-After", "1")
            self.end_headers()
            self.wfile.write(b"429 Too Many Requests")
        else:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
    def log_message(self, *a):
        pass

srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
print("PORT=%d" % srv.server_address[1], flush=True)
srv.serve_forever()
PYEOF

  # golden-BAD for the rate-limit detector: no limiting whatsoever. Never a
  # 429, never a 503, no matter how hard the burst hits it.
  cat > "$tmp/rl_absent_server.py" <<'PYEOF'
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok - unlimited, this server enforces no request rate limit")
    def log_message(self, *a):
        pass

srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
print("PORT=%d" % srv.server_address[1], flush=True)
srv.serve_forever()
PYEOF

  # golden-FALSE-WITH-CARRIER: every TEXTUAL signal of rate limiting, zero
  # enforcement. Status stays 200 forever.
  cat > "$tmp/rl_carrier_server.py" <<'PYEOF'
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("X-RateLimit-Limit", "5")
        self.send_header("X-RateLimit-Remaining", "0")
        self.send_header("X-RateLimit-Policy", "429-on-exceed")
        self.send_header("Retry-After", "1")
        self.end_headers()
        self.wfile.write(
            b"429 Too Many Requests: rate limit exceeded -- ADVISORY TEXT ONLY. "
            b"This server advertises a limit it never enforces; the status line "
            b"stays 200 forever. A detector that matches this is matching a "
            b"carrier, not the thing."
        )
    def log_message(self, *a):
        pass

srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
print("PORT=%d" % srv.server_address[1], flush=True)
srv.serve_forever()
PYEOF

  # golden fixtures for the sibling-responsiveness detector (BOB-163). ONE
  # process, one path per case, so nine cases cost one python3 instead of nine.
  cat > "$tmp/sib_server.py" <<'PYEOF'
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# path -> (status, Retry-After value; None means "send no such header")
CASES = {
    "/ok200":               (200, None),
    "/srv500":              (500, None),
    # well-formed: a POSITIVE delta-seconds, and a real IMF-fixdate
    "/r429_valid_seconds":  (429, "30"),
    "/r429_valid_httpdate": (429, "Wed, 21 Oct 2015 07:28:00 GMT"),
    # malformed: absent / non-numeric noise / non-positive / shaped-but-impossible.
    # Every one of these EXCEPT r429_missing is NON-EMPTY on purpose: a
    # "the header is present" check passes all of them, a real parse rejects
    # all of them. That difference is exactly what the paired mutation flips.
    "/r429_missing":        (429, None),
    "/r429_garbage":        (429, "soon-ish"),
    "/r429_zero":           (429, "0"),
    "/r429_neg":            (429, "-5"),
    "/r429_baddate":        (429, "Sun, 32 Nov 1994 25:99:99 GMT"),
}

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        status, retry = CASES.get(self.path, (404, None))
        self.send_response(status)
        if retry is not None:
            self.send_header("Retry-After", retry)
        self.end_headers()
        self.wfile.write(b"sibling fixture")
    def log_message(self, *a):
        pass

srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
print("PORT=%d" % srv.server_address[1], flush=True)
srv.serve_forever()
PYEOF

  # Start a fixture and learn the kernel-assigned port from its own stdout.
  # Port 0 + read-back removes the fixed-port collision that would make this
  # self-test flaky (§11.4.248 — a flaky gate is a bluff). ThreadingHTTPServer
  # binds AND listens in its constructor, so the printed PORT= line is itself
  # the readiness signal: no HTTP poll is needed, and none is sent (a poll
  # would consume the enforcing fixture's limit budget).
  sv_last_port=""
  sv_start_server() {
    local script="$1" portfile="$2"
    shift 2
    : > "$portfile"
    python3 "$script" "$@" > "$portfile" 2>/dev/null &
    local pid=$!
    sv_pids+=("$pid")
    sv_last_port=""
    local i
    for ((i = 0; i < 100; i++)); do
      sv_last_port=$(sed -n 's/^PORT=\([0-9][0-9]*\)$/\1/p' "$portfile" 2>/dev/null | head -1)
      [ -n "$sv_last_port" ] && return 0
      sleep 0.05
    done
    return 1
  }

  local good_port bad_port rl_on_port rl_off_port rl_carrier_port
  if ! sv_start_server "$tmp/good_server.py"        "$tmp/p_good.txt";    then echo "FAIL: self-validate — golden-good fixture never bound a port";      cleanup_sv; trap - EXIT; return 1; fi
  good_port="$sv_last_port"
  if ! sv_start_server "$tmp/bad_server.py"         "$tmp/p_bad.txt";     then echo "FAIL: self-validate — golden-bad fixture never bound a port";       cleanup_sv; trap - EXIT; return 1; fi
  bad_port="$sv_last_port"
  if ! sv_start_server "$tmp/rl_enforcing_server.py" "$tmp/p_rlon.txt" 2; then echo "FAIL: self-validate — rate-limit enforcing fixture never bound a port"; cleanup_sv; trap - EXIT; return 1; fi
  rl_on_port="$sv_last_port"
  if ! sv_start_server "$tmp/rl_absent_server.py"   "$tmp/p_rloff.txt";   then echo "FAIL: self-validate — rate-limit absent fixture never bound a port"; cleanup_sv; trap - EXIT; return 1; fi
  rl_off_port="$sv_last_port"
  if ! sv_start_server "$tmp/rl_carrier_server.py"  "$tmp/p_rlcar.txt";   then echo "FAIL: self-validate — rate-limit carrier fixture never bound a port"; cleanup_sv; trap - EXIT; return 1; fi
  rl_carrier_port="$sv_last_port"
  local sib_port
  if ! sv_start_server "$tmp/sib_server.py"        "$tmp/p_sib.txt";     then echo "FAIL: self-validate - sibling fixture never bound a port";           cleanup_sv; trap - EXIT; return 1; fi
  sib_port="$sv_last_port"

  # A port nothing listens on, for the connection-refused arm: bind an
  # ephemeral port, learn its number, release it. VERIFIED to actually refuse
  # before use - an unverified "should be free" port would make this self-test
  # flaky, and a flaky gate is a bluff (§11.4.248).
  local sib_dead_port="" dead_try dead_code dead_rc
  for ((dead_try = 0; dead_try < 5; dead_try++)); do
    sib_dead_port=$(python3 -c 'import socket
s = socket.socket()
s.bind(("127.0.0.1", 0))
print(s.getsockname()[1])
s.close()' 2>/dev/null)
    [ -n "$sib_dead_port" ] || continue
    dead_code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 2 "http://127.0.0.1:$sib_dead_port/" 2>/dev/null)
    dead_rc=$?
    if [ "$dead_rc" -ne 0 ]; then break; fi
    sib_dead_port=""
  done


  local sv_bad=0

  # --- Detector 1: crash resistance -----------------------------------------
  local goodfile="$tmp/good.log" badfile="$tmp/bad.log"
  run_curl_status_probe "http://127.0.0.1:$good_port/" "$SV_PROBE_N" "$SV_PROBE_C" "$goodfile"
  run_curl_status_probe "http://127.0.0.1:$bad_port/"  "$SV_PROBE_N" "$SV_PROBE_C" "$badfile"

  local good_n good_5xx good_fail bad_n bad_5xx bad_fail
  good_n=$(wc -l < "$goodfile" 2>/dev/null | tr -d '[:space:]')
  good_5xx=$(tally_field "$goodfile" '^5')
  good_fail=$(tally_nonzero_rc "$goodfile")
  bad_n=$(wc -l < "$badfile" 2>/dev/null | tr -d '[:space:]')
  bad_5xx=$(tally_field "$badfile" '^5')
  bad_fail=$(tally_nonzero_rc "$badfile")

  echo "--- detector 1: crash resistance ---"
  echo "  golden-good: n=$good_n 5xx=$good_5xx conn_fail=$good_fail (want 5xx=0 conn_fail=0)"
  echo "  golden-bad:  n=$bad_n 5xx=$bad_5xx conn_fail=$bad_fail (want 5xx=n)"
  # Assertions are SAMPLE-RELATIVE, never against the literal request count:
  # run_curl_status_probe stops launching once its wall-clock budget is spent,
  # so a hard "== 30" would turn ordinary host load into a false FAIL.
  if ! [ "${good_n:-0}" -ge "$SV_MIN_SAMPLE" ] 2>/dev/null; then
    echo "  [SELF-VAL BAD] golden-good sample too small ($good_n < $SV_MIN_SAMPLE) — truncated sample is not evidence either way (§11.4.201(6)); host is too loaded to validate the crash detector"
    sv_bad=1
  fi
  if [ "$good_5xx" != "0" ] || [ "$good_fail" != "0" ]; then
    echo "  [SELF-VAL BAD] crash-detector flagged the golden-GOOD fixture as crashing"
    sv_bad=1
  fi
  if ! [ "${bad_n:-0}" -ge "$SV_MIN_SAMPLE" ] 2>/dev/null; then
    echo "  [SELF-VAL BAD] golden-bad sample too small ($bad_n < $SV_MIN_SAMPLE) — truncated sample is not evidence either way (§11.4.201(6))"
    sv_bad=1
  elif [ "$bad_5xx" != "$bad_n" ]; then
    echo "  [SELF-VAL BAD] crash-detector saw only $bad_5xx of $bad_n responses as 5xx on the golden-BAD fixture (every single one is a 500)"
    sv_bad=1
  fi

  # --- Detector 2: rate limiting (BOB-114) ----------------------------------
  # Drives the REAL detector (ratelimit_classify / ratelimit_verdict_kind —
  # the same functions the live run mints verdicts from), never a copy.
  echo "--- detector 2: rate limiting ---"
  rl_check() {
    # rl_check <label> <url> <expected-class>
    local label="$1" url="$2" want="$3"
    local log="$tmp/rl_${label}.log"
    run_curl_status_probe "$url" "$SV_PROBE_N" "$SV_PROBE_C" "$log"
    local n n429 n5xx got kg kr want_kg want_kr
    n=$(wc -l < "$log" 2>/dev/null | tr -d '[:space:]')
    n429=$(tally_field "$log" '^429')
    n5xx=$(tally_field "$log" '^5')
    got=$(ratelimit_classify "$log")
    kg=$(ratelimit_verdict_kind "$got" 0)
    kr=$(ratelimit_verdict_kind "$got" 1)
    if [ "$want" = "engaged" ]; then want_kg=PASS; want_kr=FAIL; else want_kg=SKIP; want_kr=PASS; fi
    echo "  fixture '$label': n=$n 429=$n429 5xx=$n5xx -> class=$got (want=$want)  verdict GREEN=$kg RED=$kr"
    if [ "$got" != "$want" ]; then
      echo "  [SELF-VAL BAD] rate-limit detector classified '$label' as '$got', expected '$want'"
      sv_bad=1
    fi
    if [ "$kg" != "$want_kg" ] || [ "$kr" != "$want_kr" ]; then
      echo "  [SELF-VAL BAD] rate-limit verdict table wrong for '$label': GREEN=$kg (want $want_kg) RED=$kr (want $want_kr)"
      sv_bad=1
    fi
    if ! [ "${n:-0}" -ge "$SV_MIN_SAMPLE" ] 2>/dev/null; then
      echo "  [SELF-VAL BAD] fixture '$label' sample too small ($n < $SV_MIN_SAMPLE) — truncated sample is not evidence either way (§11.4.201(6))"
      sv_bad=1
    fi
    if [ "$want" = "engaged" ]; then
      if ! [ "${n429:-0}" -ge 1 ] 2>/dev/null; then
        echo "  [SELF-VAL BAD] enforcing fixture '$label' produced 0 x 429 — the detector's 'engaged' arm was never driven"
        sv_bad=1
      fi
    else
      if [ "${n429:-0}" != "0" ]; then
        echo "  [SELF-VAL BAD] non-enforcing fixture '$label' produced ${n429} x 429 — detector saw a limit that does not exist"
        sv_bad=1
      fi
      if [ "${n5xx:-0}" != "0" ]; then
        echo "  [SELF-VAL BAD] non-enforcing fixture '$label' produced ${n5xx} x 5xx — fixture is not a clean never-429/503 stub"
        sv_bad=1
      fi
    fi
  }
  rl_check enforcing "http://127.0.0.1:$rl_on_port/"      engaged
  rl_check absent    "http://127.0.0.1:$rl_off_port/"     absent
  rl_check carrier   "http://127.0.0.1:$rl_carrier_port/" absent

  # --- Detector 3: sibling responsiveness (assertion (c), BOB-163) ----------
  # Drives the REAL probe (probe_sibling) and the REAL classifier
  # (sibling_classify / retry_after_wellformed) that the live assertion-(c)
  # path mints its verdict from - never a copy. Before this, assertion (c)'s
  # oracle had NO fixture at all and had therefore never been observed to FAIL
  # on a genuinely broken artifact: unvalidated instrumentation, which
  # §11.4.115(F) forbids from minting verdicts.
  echo "--- detector 3: sibling responsiveness ---"
  sib_check() {
    # sib_check <label> <url> <expected-class>
    local label="$1" url="$2" want="$3"
    local log="$tmp/sib_${label}.log" hdr="$tmp/sib_${label}.hdr"
    : > "$log"
    probe_sibling "$label" "$url" "$log" "$hdr"
    local sname scode src selapsed sretry got
    sname=""; scode=""; src=""; selapsed=""; sretry=""
    read -r sname scode src selapsed sretry < "$log"
    got=$(sibling_classify "$scode" "$src" "$sretry")
    echo "  fixture '$label': code=$scode rc=$src retry_after='${sretry}' -> class=$got (want=$want)"
    if [ "$got" != "$want" ]; then
      echo "  [SELF-VAL BAD] sibling detector classified '$label' as '$got', expected '$want'"
      sv_bad=1
    fi
  }
  # RESPONSIVE arm
  sib_check ok200               "http://127.0.0.1:$sib_port/ok200"               responsive
  sib_check r429_valid_seconds  "http://127.0.0.1:$sib_port/r429_valid_seconds"  responsive
  sib_check r429_valid_httpdate "http://127.0.0.1:$sib_port/r429_valid_httpdate" responsive
  # DEGRADED arm. r429_garbage / r429_zero / r429_neg / r429_baddate are the
  # golden-BAD-WITH-CARRIER cases: the Retry-After header IS present on every
  # one of them, so only a real PARSE tells them apart from the responsive
  # arm. A detector that merely checks for a non-empty header passes them all
  # and this self-test goes red - which is precisely the §1.1 mutation for
  # this change.
  sib_check r429_missing        "http://127.0.0.1:$sib_port/r429_missing"        degraded
  sib_check r429_garbage        "http://127.0.0.1:$sib_port/r429_garbage"        degraded
  sib_check r429_zero           "http://127.0.0.1:$sib_port/r429_zero"           degraded
  sib_check r429_neg            "http://127.0.0.1:$sib_port/r429_neg"            degraded
  # F1: this fixture asserts the SEMANTIC parse - a correctly-SHAPED but
  # impossible date. It is only meaningful where a date(1) parser exists.
  # retry_after_wellformed documents the portability branch (HAVE_DATE_PARSE=0
  # -> structural match stands alone), so on such a host `Sun, 32 Nov 1994
  # 25:99:99 GMT` classifies RESPONSIVE *by design*. Asserting `degraded`
  # unconditionally made the two halves of one mechanism contradict each other
  # and - because BOB-114 runs self-validation on EVERY live invocation - turned
  # an INSTRUMENT property into a whole-challenge exit 1 against a healthy
  # product: the §11.4.201(1) false-positive refusal this challenge forbids.
  # The refusal is kept (an unexercised arm IS unvalidated instrumentation,
  # same policy as the refused-port arm below) but it now NAMES ITS RESOLVED
  # CAUSE (§11.4.201(4)(5)) instead of accusing the detector.
  if [ "$HAVE_DATE_PARSE" -eq 1 ]; then
    sib_check r429_baddate      "http://127.0.0.1:$sib_port/r429_baddate"        degraded
  else
    if [ "$DATE_PARSE_STATUS" = "unreliable" ]; then
      echo "  fixture 'r429_baddate': NOT EXERCISED (reason=unreliable_date_parser_on_host) - this host's date(1) ACCEPTS an impossible date, so it cannot be used to reject one; retry_after_wellformed falls back to structural matching alone and the semantic-parse arm is unvalidated this run. Cause is the INSTRUMENT, not the detector."
    else
      echo "  fixture 'r429_baddate': NOT EXERCISED (reason=no_date_parser_on_host) - this host's date(1) refuses -d, so retry_after_wellformed falls back to structural matching alone and a correctly-shaped impossible date is indistinguishable from a real one; the semantic-parse arm is unvalidated this run. Cause is the INSTRUMENT, not the detector."
    fi
    sv_bad=1
  fi
  sib_check srv500              "http://127.0.0.1:$sib_port/srv500"              degraded
  if [ -n "$sib_dead_port" ]; then
    sib_check refused           "http://127.0.0.1:$sib_dead_port/"               degraded
    # --- the DECISION, not just the classification --------------------------
    # Feeds REAL probe output (captured from the fixtures above, never
    # hand-written) into the same sibling_isolation_report the live assertion
    # (c) calls, and drives EVERY polarity of its verdict. Without this, the
    # classifier could be perfect while the live path never consulted it -
    # measured 2026-08-26: an adversarial mutation that left the classifier
    # intact and unwired the live loop survived a classifier-only self-test.
    # MINOR-1 added the count-contract shapes: a log can be non-empty and still
    # carry FEWER parsed observations than probes launched, which read "held"
    # under the original zero-BYTE check.
    local dec_out dec_rc
    sib_decision_check() {
      # sib_decision_check <label> <logfile> <expected-count> <want-rc> [must-contain]
      local label="$1" lf="$2" exp="$3" want="$4" must="${5:-}" bytes
      bytes=$(wc -c < "$lf" 2>/dev/null | tr -d '[:space:]')
      dec_out="$(sibling_isolation_report "$lf" selftest "$exp")"; dec_rc=$?
      echo "  decision '$label': rc=$dec_rc (want $want; expected=$exp, log_bytes=${bytes:-0})"
      if [ "$dec_rc" -ne "$want" ]; then
        echo "  [SELF-VAL BAD] decision '$label' returned rc=$dec_rc, want $want"
        sv_bad=1
      fi
      if [ -n "$must" ] && ! printf '%s\n' "$dec_out" | grep -q "$must"; then
        echo "  [SELF-VAL BAD] decision '$label' output did not contain '$must' - the verdict may be right for the wrong reason"
        sv_bad=1
      fi
    }

    local held_log="$tmp/sib_d_held.log" degr_log="$tmp/sib_d_degr.log"
    cat "$tmp/sib_ok200.log" "$tmp/sib_r429_valid_seconds.log" "$tmp/sib_r429_valid_httpdate.log" > "$held_log" 2>/dev/null
    cat "$held_log" "$tmp/sib_r429_garbage.log" "$tmp/sib_refused.log" > "$degr_log" 2>/dev/null
    # Torn fixtures: a COMPLETE observation whose trailing newline was lost.
    # `printf %s "$(cat ...)"` strips the final newline, reproducing the shape
    # exactly. Their must-contain is "DEGRADED", NOT the count message: that is
    # what proves the torn line was PARSED rather than merely counted-missing -
    # without the `|| [ -n "$sname" ]` guard these fail closed on the COUNT and
    # would still return rc=1 for the wrong reason.
    printf '%s' "$(cat "$tmp/sib_r429_garbage.log" 2>/dev/null)"  > "$tmp/sib_d_torn.log"
    { cat "$tmp/sib_ok200.log" 2>/dev/null; printf '%s' "$(cat "$tmp/sib_refused.log" 2>/dev/null)"; } > "$tmp/sib_d_tornmix.log"
    printf '\n'        > "$tmp/sib_d_blank.log"
    printf '   \n\t\n' > "$tmp/sib_d_ws.log"
    cat "$tmp/sib_ok200.log" > "$tmp/sib_d_partial.log" 2>/dev/null
    cat "$tmp/sib_ok200.log" "$tmp/sib_r429_valid_seconds.log" > "$tmp/sib_d_complete.log" 2>/dev/null
    : > "$tmp/sib_d_empty.log"

    local held_n degr_n
    held_n=$(wc -l < "$held_log" | tr -d '[:space:]')
    degr_n=$(wc -l < "$degr_log" | tr -d '[:space:]')

    sib_decision_check all-responsive "$held_log"               "$held_n" 0 "limiter engaged, service alive"
    sib_decision_check one-degraded   "$degr_log"               "$degr_n" 1 "DEGRADED"
    sib_decision_check empty-log      "$tmp/sib_d_empty.log"    2         1 "NO SIBLING OBSERVATIONS"
    sib_decision_check blank-line     "$tmp/sib_d_blank.log"    2         1 "NO SIBLING OBSERVATIONS"
    sib_decision_check whitespace-only "$tmp/sib_d_ws.log"      2         1 "NO SIBLING OBSERVATIONS"
    sib_decision_check torn-degraded  "$tmp/sib_d_torn.log"     1         1 "DEGRADED"
    sib_decision_check torn-mixed     "$tmp/sib_d_tornmix.log"  2         1 "DEGRADED"
    sib_decision_check partial        "$tmp/sib_d_partial.log"  2         1 "INCOMPLETE SIBLING OBSERVATIONS"
    # The false-positive guard (§11.4.201(1)): a COMPLETE log must still read held.
    sib_decision_check complete-2of2  "$tmp/sib_d_complete.log" 2         0 "stayed responsive"

  else
    # §11.4.6 / §11.4.201(6): could not obtain a port that PROVABLY refuses,
    # so say so instead of pretending the arm ran. Counted as a self-validation
    # failure because an unexercised arm is unvalidated instrumentation, and
    # the honest reason is printed so it is never mistaken for a real defect.
    echo "  fixture 'refused': NOT EXERCISED (reason=no_provably_refusing_port_available) - connection-failure arm unvalidated this run"
    sv_bad=1
  fi

  cleanup_sv
  trap - EXIT
  if [ "$sv_bad" -eq 0 ]; then
    echo "PASS: self-validate — crash-resistance, rate-limit AND sibling-responsiveness"
    echo "      detectors each distinguish their golden-good from their golden-bad"
    echo "      fixture; the rate-limit detector does NOT fire on the"
    echo "      advertises-but-never-enforces carrier; and the sibling detector holds"
    echo "      the line against four 429s that DO carry a Retry-After header whose"
    echo "      value is not well-formed, plus both polarities of the isolation"
    echo "      decision and its empty-log fail-closed arm"
    echo "      (§11.4.107(10) + §11.4.201(1)(6)(7)(a))"
    return 0
  fi
  echo "FAIL: self-validate — detector honesty check failed"
  return 1
}

if [ "$MODE" = "--self-validate" ]; then
  run_self_validation
  exit $?
fi

# --- §11.4.115 RED/GREEN regression guard: BOB-112 /healthz TTL cache ------
# Added by task #74 (live wrk verification of BOB-112's health.go TTL
# cache). Runs a bounded `wrk` load against boba-jackett's :7189/healthz on
# EVERY future invocation of this challenge and asserts both:
#   (a) the client-observed timeout rate stays low, and
#   (b) the server-side upstream Jackett.GetCatalog() call count (read from
#       `podman/docker logs boba-jackett`'s "cache refresh" lines) stays
#       bounded — proving the cache is actually collapsing the load, not
#       merely that the endpoint happened to be fast this particular run.
# Thresholds are calibrated against real captured evidence, not guessed
# (§11.4.6) — see docs/qa/BOB-112/summary.md for the full RED/GREEN numbers:
# RED (cache bypassed via a §1.1 mutation): 97.1% timeouts, 13.71 req/s.
# GREEN (real committed code): 0.0% timeouts, 27,049.00 req/s. The
# thresholds below sit far inside that gap so this guard trips only on a
# genuine regression, never on ordinary host-load noise.
if [ "$MODE" = "--healthz" ]; then
  echo "=== ddos_resilience_challenge: --healthz (BOB-112 cache regression guard) ==="
  HEALTHZ_URL="http://127.0.0.1:7189/healthz"
  HEALTHZ_WRK_THREADS=2
  HEALTHZ_WRK_CONNS=20
  HEALTHZ_WRK_DURATION="5s"
  HEALTHZ_WRK_TIMEOUT_S=3
  # GREEN observed 0%, RED observed 97.1% — 20% is a wide, conservative
  # trip-wire far above ordinary jitter and far below the RED baseline.
  HEALTHZ_MAX_TIMEOUT_PCT=20
  # GREEN observed ~27k req/s, RED observed ~14 req/s — 500 is >35x the RED
  # baseline and <2% of the GREEN baseline, so it only fires on genuine
  # regression, never on host contention alone.
  HEALTHZ_MIN_REQS_PER_SEC=500
  # TTL=30s > the 5s test window, so a healthy cache produces 0-1 refreshes
  # from a warm/cold start; allow slack for cold-start double-checked-lock
  # races.
  HEALTHZ_MAX_CACHE_REFRESH_DELTA=3

  reachable_code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 3 "$HEALTHZ_URL" 2>/dev/null)
  if [ -z "$reachable_code" ] || [ "$reachable_code" = "000" ]; then
    echo "SKIP: boba-jackett unreachable at $HEALTHZ_URL (reason=services_not_running — start the stack via ./start.sh)"
    exit 0
  fi

  if ! command -v wrk >/dev/null 2>&1; then
    echo "SKIP-with-fallback: wrk not installed (reason=tooling_absent — run 'bash scripts/install-dev-tools.sh', see docs/scripts/install-dev-tools.md). Falling back to the bounded curl-loop probe already used above so this mode still produces a real signal on hosts without wrk."
    fb_file="$(mktemp)"
    run_curl_status_probe "$HEALTHZ_URL" 100 "$HEALTHZ_WRK_CONNS" "$fb_file"
    fb_n=$(wc -l < "$fb_file" 2>/dev/null | tr -d '[:space:]')
    fb_timeouts=$(tally_rc "$fb_file" 28)
    rm -f "$fb_file"
    fb_pct=0
    [ -n "$fb_n" ] && [ "$fb_n" -gt 0 ] 2>/dev/null && fb_pct=$(awk -v t="$fb_timeouts" -v n="$fb_n" 'BEGIN{printf "%.1f", (t/n)*100}')
    echo "curl-loop fallback: ${fb_timeouts:-0}/${fb_n:-0} timeouts (${fb_pct}%)"
    if awk -v p="$fb_pct" -v m="$HEALTHZ_MAX_TIMEOUT_PCT" 'BEGIN{exit !(p>m)}'; then
      echo "FAIL: --healthz curl-loop fallback — ${fb_pct}% timeout rate exceeds ${HEALTHZ_MAX_TIMEOUT_PCT}% threshold"
      exit 1
    fi
    echo "PASS: --healthz curl-loop fallback — ${fb_pct}% timeout rate within ${HEALTHZ_MAX_TIMEOUT_PCT}% threshold (wrk unavailable, degraded check — install wrk for the full-fidelity check)"
    exit 0
  fi

  # Server-side cache-behavior check (best-effort; honestly skipped if no
  # container runtime CLI is reachable — never faked, §11.4.6).
  LOG_CLI=""
  command -v podman >/dev/null 2>&1 && LOG_CLI="podman"
  [ -z "$LOG_CLI" ] && command -v docker >/dev/null 2>&1 && LOG_CLI="docker"
  have_container=0
  if [ -n "$LOG_CLI" ] && "$LOG_CLI" ps --format '{{.Names}}' 2>/dev/null | grep -qx boba-jackett; then
    have_container=1
  fi
  refresh_before=0
  [ "$have_container" -eq 1 ] && refresh_before=$("$LOG_CLI" logs boba-jackett 2>&1 | grep -c "cache refresh")

  wrk_out="$(wrk -t"$HEALTHZ_WRK_THREADS" -c"$HEALTHZ_WRK_CONNS" -d"$HEALTHZ_WRK_DURATION" --timeout "${HEALTHZ_WRK_TIMEOUT_S}s" --latency "$HEALTHZ_URL" 2>&1)"
  echo "$wrk_out"

  total_reqs=$(echo "$wrk_out" | grep -oE '[0-9]+ requests in' | grep -oE '^[0-9]+')
  reqs_per_sec=$(echo "$wrk_out" | grep -E '^Requests/sec:' | awk '{print $2}')
  timeout_n=$(echo "$wrk_out" | grep -E '^  Socket errors:' | grep -oE 'timeout [0-9]+' | grep -oE '[0-9]+$')
  [ -z "$timeout_n" ] && timeout_n=0
  [ -z "$total_reqs" ] && total_reqs=0
  timeout_pct=0
  [ "$total_reqs" -gt 0 ] 2>/dev/null && timeout_pct=$(awk -v t="$timeout_n" -v n="$total_reqs" 'BEGIN{printf "%.1f", (t/n)*100}')

  refresh_delta=0
  cache_check_note="cache-behavior check SKIPPED (no accessible container runtime CLI/container found — timeout-rate + throughput checks below still apply)"
  if [ "$have_container" -eq 1 ]; then
    refresh_after=$("$LOG_CLI" logs boba-jackett 2>&1 | grep -c "cache refresh")
    refresh_delta=$((refresh_after - refresh_before))
    cache_check_note="server-side cache refresh delta during this run: $refresh_delta (bound: <= $HEALTHZ_MAX_CACHE_REFRESH_DELTA)"
  fi

  echo ""
  echo "--- --healthz verdict inputs ---"
  echo "  total_requests=$total_reqs  timeouts=$timeout_n  timeout_pct=${timeout_pct}%  reqs_per_sec=${reqs_per_sec:-0}"
  echo "  $cache_check_note"

  bad=0
  if awk -v p="$timeout_pct" -v m="$HEALTHZ_MAX_TIMEOUT_PCT" 'BEGIN{exit !(p>m)}'; then
    echo "  [FAIL] timeout rate ${timeout_pct}% exceeds ${HEALTHZ_MAX_TIMEOUT_PCT}% threshold — BOB-112 cache regression suspected"
    bad=1
  fi
  if [ -n "${reqs_per_sec:-}" ] && awk -v r="$reqs_per_sec" -v m="$HEALTHZ_MIN_REQS_PER_SEC" 'BEGIN{exit !(r<m)}'; then
    echo "  [FAIL] throughput ${reqs_per_sec} req/s below ${HEALTHZ_MIN_REQS_PER_SEC} req/s floor — BOB-112 cache regression suspected"
    bad=1
  fi
  if [ "$have_container" -eq 1 ] && [ "$refresh_delta" -gt "$HEALTHZ_MAX_CACHE_REFRESH_DELTA" ] 2>/dev/null; then
    echo "  [FAIL] $refresh_delta cache refreshes during a ${HEALTHZ_WRK_DURATION} window exceeds bound $HEALTHZ_MAX_CACHE_REFRESH_DELTA — cache does not appear to be collapsing upstream calls"
    bad=1
  fi

  if [ "$bad" -eq 0 ]; then
    echo "PASS: --healthz — BOB-112 /healthz TTL cache still effective (see docs/qa/BOB-112/summary.md for the full RED/GREEN evidence this guard is calibrated against)"
    exit 0
  fi
  echo "FAIL: --healthz — BOB-112 cache regression guard tripped"
  exit 1
fi

# --- §11.4.115(F): an unvalidated detector mints no verdicts ------------------
# BOB-114 wired the self-validation to run AUTOMATICALLY on every live
# invocation — including the bare no-arg form challenges/scripts/
# run_all_challenges.sh uses — instead of waiting for an operator to remember
# `--self-validate`. Registration is not coverage (§11.4.226): before this,
# the self-test existed but nothing ever executed it in the normal path, so
# both detectors could have rotted silently between manual runs. Measured
# cost of running it first: ~1s, against this challenge's 180s aggregator
# budget. python3-less hosts SKIP honestly and the live run proceeds.
if ! run_self_validation; then
  echo ""
  echo "FAIL: ddos_resilience_challenge — detector self-validation FAILED; refusing to"
  echo "      mint live verdicts from unvalidated instrumentation (§11.4.115(F))."
  exit 1
fi
echo ""

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
  # The classification and the verdict kind come from ratelimit_classify /
  # ratelimit_verdict_kind — the SAME two functions --self-validate drives
  # its golden-good / golden-bad / golden-false-carrier fixtures through
  # (BOB-114). This live verdict is therefore minted by instrumentation that
  # has been OBSERVED to FAIL on a genuinely broken artifact, which is what
  # §11.4.115(F) requires before a detector may mint verdicts at all.
  heaviest_file="$workdir/${name}_c${heaviest_c}.log"
  r429_heaviest=$(tally_field "$heaviest_file" '^429')
  rl_class=$(ratelimit_classify "$heaviest_file")
  rl_kind=$(ratelimit_verdict_kind "$rl_class" "$RED_MODE")
  case "$rl_class/$rl_kind" in
    engaged/FAIL)
      verdict FAIL "$name: rate limiting IS engaged ($r429_heaviest x 429 at c=$heaviest_c) — RED expected its absence; defect appears fixed" ;;
    engaged/PASS)
      verdict PASS "$name: rate limiting engaged — $r429_heaviest x 429 observed at heaviest tier c=$heaviest_c" ;;
    absent/PASS)
      verdict PASS "$name: confirmed absence of rate limiting at c=$heaviest_c (RED reproduces the real current defect)" ;;
    *)
      verdict SKIP "$name: no rate limiting observed on THIS endpoint at c=$heaviest_c (reason=extension_absent — measured 2026-08-26, merge_search :7187 DOES enforce a limiter and PASSes; :7185/:7189 do not yet; tracked as BOB-074 followup, see docs/testing/ddos_resilience.md)"
      notes+=("$name: rate limiting SKIP'd — extension_absent, followup filed") ;;
  esac

  # --- (c) cross-endpoint isolation while this endpoint is under load ---
  sibling_file="$workdir/${name}_siblings.log"
  : > "$sibling_file"
  sib_pids=()
  for other in "${EP_NAMES[@]}"; do
    [ "$other" = "$name" ] && continue
    ourl="$(ep_url "$other")"
    probe_sibling "$other" "$ourl" "$sibling_file" "$workdir/${name}_sib_${other}.hdr" &
    sib_pids+=("$!")
  done
  # Re-run the heaviest tier concurrently with the sibling probes above.
  run_curl_status_probe "$url" "$REQUESTS_PER_TIER" "$heaviest_c" "$workdir/${name}_isolation.log"
  [ "${#sib_pids[@]}" -gt 0 ] && wait "${sib_pids[@]}" 2>/dev/null

  # BOB-163: the ENTIRE decision - classification, wording and pass/fail - comes
  # from sibling_isolation_report, the SAME function --self-validate drives its
  # golden fixtures through. This live verdict is therefore minted by
  # instrumentation that has been OBSERVED to FAIL on a genuinely broken
  # artifact, which is what §11.4.115(F) requires before a detector may mint
  # verdicts at all.
  # RESIDUAL RISK #2, STATED NOT HIDDEN (§11.4.6). This ONE call is the only
  # step of assertion (c) that NO test in this repository guards. Every rule it
  # applies is fixture-covered (sibling_classify, retry_after_wellformed and
  # sibling_isolation_report are all driven by --self-validate, and mutating any
  # of them turns tests/unit/test_ddos_sibling_retry_after_classification.sh
  # red), but deleting or bypassing THIS call site - inlining a different rule
  # here, or hardcoding isolation_bad=0 - is NOT detected: measured 2026-08-26,
  # exactly that mutation left the unit test fully green at every suite size it
  # has been run against (16/16, then 22/22, then 32/32). Guarding it needs the
  # real :7185/:7187/:7189 topology under real load, which no localhost fixture
  # can own and which this challenge's bounded chaos budget cannot stand up in
  # a unit test. A grep-gate asserting this call site "looks right" is NOT the
  # closure - that is the §11.4.201(7)(a) substring check this file forbids
  # elsewhere. The honest control is the §11.4.142 review of any diff touching
  # this line; naming the gap here is what makes that review possible.
  isolation_bad=0
  # ${#sib_pids[@]} is the number of sibling probes actually LAUNCHED for this
  # endpoint, so the verdict is fail-closed against the real expected count
  # rather than against "the file has some bytes in it".
  sibling_isolation_report "$sibling_file" "$name" "${#sib_pids[@]}" || isolation_bad=1
  if [ "$isolation_bad" -eq 0 ]; then
    verdict PASS "$name under load: sibling endpoints stayed responsive (cross-endpoint isolation held)"
  else
    verdict FAIL "$name under load: at least one sibling endpoint degraded — no isolation between endpoints (a 429 carrying a well-formed Retry-After does NOT count as degraded — BOB-163)"
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
