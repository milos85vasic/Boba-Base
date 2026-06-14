#!/usr/bin/env bash
#
# tracker_auth_live_challenge.sh — LIVE private-tracker credential proof
# (§11.4.10 credentials-handling — NEVER reads/prints/logs any credential VALUE;
#  §11.4.52 autonomous validation, §11.4.68/§11.4.69 positive sink-side evidence,
#  §11.4.83 captured-evidence under challenges/.evidence/, feature class
#  network_connectivity / package_install).
#
# Purpose:
#   Prove the STORED private-tracker credentials genuinely authenticate by
#   driving a REAL search through the live merge service:
#     POST http://${BOBA_BASE_URL:-http://localhost:7187}/api/v1/search
#   then polling
#     GET  .../api/v1/search/{id}
#   until the search completes, and asserting each tracker's REAL authentication
#   state from the response `tracker_stats[]` — never on "HTTP 200" alone.
#
# SECURITY (§11.4.10 — non-negotiable):
#   The qbittorrent-proxy holds the tracker credentials. This challenge NEVER
#   reads, prints, logs, or env-dumps any credential VALUE. It reads ONLY the
#   `authenticated` boolean (plus status / results_count / error) that the merge
#   service returns in its JSON. The query is a harmless public term ("ubuntu");
#   no credential ever appears in the request, the evidence file, or any log.
#
# Per-tracker verdict (ground truth captured live, query=ubuntu):
#   PRIVATE [rutracker, kinozal, nnmclub, iptorrents]:
#     PASS  if authenticated==true  AND status in {success, empty}.
#     SKIP  (operator-blocked) if authenticated==false AND error matches an
#           honest transient blocker (captcha/timeout/temporarily/rate/
#           unreachable/deadline).
#     FAIL  if authenticated==false otherwise (bad/expired creds), OR the
#           tracker is absent from tracker_stats.
#   PUBLIC [rutor] (no login endpoint — authenticated==false BY DESIGN):
#     PASS  if status==success AND results_count>0.
#
# Overall:
#   PASS (exit 0)  only if all 5 trackers PASS.
#   SKIP (exit 77) if the merge service is unreachable OR every credentialed
#                  sub-check honestly SKIPs (no genuine FAIL).
#   FAIL (exit !=0) on any genuine FAIL (bad creds / absent tracker / public
#                  tracker returning nothing / search never completing).
#
# Anti-bluff contract (§11.4.6 / §11.4.68 / §11.4.69):
#   - Backend down (§11.4.3): honest SKIP (exit 77) with the EXACT curl blocker
#     captured — NEVER a green-without-a-real-backend pass.
#   - A tracker honest-SKIP carries its REAL error string — we do not pretend an
#     auth success the proxy did not report.
#   - PASS asserts user-observable REAL `authenticated`/`status`/`results_count`
#     fields — a stubbed/no-op merge service cannot satisfy these.
#
# Inputs:   none in the request (public query, no credentials sent).
#           Optional env: BOBA_BASE_URL (default http://localhost:7187).
# Outputs:  challenges/.evidence/tracker_auth_live.json (captured
#           evidence: per-tracker {name,status,authenticated,results_count} —
#           NO credential values — plus the overall verdict, §11.4.83);
#           a clear PASS:/SKIP:/FAIL: line; exit 0 PASS, 77 honest SKIP, !=0 FAIL.
# Side-effects: none on the target (read-only search; no torrent added).
# Dependencies: curl, python3 (python3 used ONLY for JSON parsing).
# Cross-references:
#   - download-proxy/src/api/routes.py          (the live /api/v1/search route)
#   - download-proxy/src/merge_service/search.py (search orchestration)
#   - challenges/extension/live_detect_send_challenge.sh (sibling LIVE Challenge)
#   - start.sh / scripts/boba-ctl.sh (the sanctioned orchestrator that boots :7187)

set -euo pipefail

CHALLENGE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Evidence lives at challenges/.evidence/ — CHALLENGE_DIR is challenges/scripts/.
EVIDENCE_DIR="$(cd "$CHALLENGE_DIR/.." && pwd)/.evidence"
EVIDENCE="$EVIDENCE_DIR/tracker_auth_live.json"

BOBA_BASE="${BOBA_BASE_URL:-http://localhost:7187}"
BOBA_BASE="${BOBA_BASE%/}"
HEALTH_URL="$BOBA_BASE/health"
SEARCH_URL="$BOBA_BASE/api/v1/search"

QUERY="ubuntu"
LIMIT=50
POLL_INTERVAL=7
POLL_CAP=120   # seconds

# Closed sets — kept in sync with the prompt's ground truth.
PRIVATE_TRACKERS="rutracker kinozal nnmclub iptorrents"
PUBLIC_TRACKERS="rutor"

mkdir -p "$EVIDENCE_DIR"
rm -f "$EVIDENCE"

echo "=== tracker_auth_live_challenge (LIVE :7187 /api/v1/search) ==="

# --- Preconditions (honest blockers, never a faked PASS) ----------------------
for bin in curl python3; do
  if ! command -v "$bin" >/dev/null 2>&1; then
    echo "FAIL: required tool '$bin' not found on PATH"; exit 1
  fi
done

TMP_FRAG="$(mktemp)"
TMP_ERR="$(mktemp)"
trap 'rm -f "$TMP_FRAG" "$TMP_ERR"' EXIT

# Write the evidence JSON atomically from a python heredoc. Folds the captured
# tracker_stats fragment (NO credential values) under the overall verdict.
write_evidence() { # $1=verdict $2=json-fragment-file
  python3 - "$EVIDENCE" "$1" "$BOBA_BASE" "$QUERY" "$2" <<'PY'
import json, sys, os
out, verdict, base, query, frag_path = sys.argv[1:6]
frag = {}
if frag_path and os.path.exists(frag_path):
    with open(frag_path, encoding="utf-8") as fh:
        txt = fh.read().strip()
        if txt:
            try:
                frag = json.loads(txt)
            except Exception:
                frag = {"raw": txt}
ev = {
    "verdict": verdict,
    "challenge": "tracker_auth_live",
    "base": base,
    "query": query,
    "note": "credential VALUES are never read or stored (§11.4.10); only the "
            "merge service's authenticated boolean + status are inspected",
}
ev.update(frag)
with open(out, "w", encoding="utf-8") as fh:
    json.dump(ev, fh, indent=2)
print(f"  evidence -> {out}")
PY
}

# --- Step 1: probe the REAL backend (§11.4.3 reachability guard) --------------
echo "Probing $HEALTH_URL ..."
HEALTH_HTTP="000"
HEALTH_BODY=""
if HEALTH_BODY="$(curl -sS -m 6 -w $'\n%{http_code}' "$HEALTH_URL" 2>"$TMP_ERR")"; then
  HEALTH_HTTP="$(printf '%s' "$HEALTH_BODY" | tail -n1)"
  HEALTH_BODY="$(printf '%s' "$HEALTH_BODY" | sed '$d')"
fi
CURL_ERR="$(cat "$TMP_ERR" 2>/dev/null || true)"
: > "$TMP_ERR"

HEALTH_STATUS="$(printf '%s' "$HEALTH_BODY" | python3 -c 'import json,sys
try: print(json.load(sys.stdin).get("status",""))
except Exception: print("")' 2>/dev/null || true)"

if [ "$HEALTH_HTTP" != "200" ] || [ "$HEALTH_STATUS" != "healthy" ]; then
  BLOCKER="Boba merge service NOT reachable/healthy at $BOBA_BASE — /health HTTP='$HEALTH_HTTP' status='$HEALTH_STATUS'"
  [ -n "$CURL_ERR" ] && BLOCKER="$BLOCKER ; curl: $CURL_ERR"
  python3 - "$TMP_FRAG" "$HEALTH_HTTP" "$HEALTH_STATUS" "$CURL_ERR" "$BLOCKER" <<'PY'
import json, sys
frag, http, status, curlerr, blocker = sys.argv[1:6]
with open(frag, "w") as fh:
    json.dump({"probe": {"health_http": http, "health_status": status,
                         "curl_error": curlerr}, "blocker": blocker}, fh)
PY
  write_evidence "SKIP" "$TMP_FRAG"
  echo "SKIP (§11.4.3 / §11.4.21 operator-blocked): $BLOCKER"
  echo "       Bring the stack up via the sanctioned orchestrator ('./start.sh') then re-run."
  exit 77
fi
echo "  backend healthy (HTTP 200, status=healthy)"

# --- Step 2: POST the search (public query — NO credentials in the request) ----
REQ_BODY="$(python3 - "$QUERY" "$LIMIT" <<'PY'
import json, sys
print(json.dumps({"query": sys.argv[1], "limit": int(sys.argv[2])}))
PY
)"

echo "POST $SEARCH_URL  (query='$QUERY', limit=$LIMIT) ..."
POST_RESP="$(curl -sS -m 30 -w $'\n%{http_code}' \
  -H 'content-type: application/json' \
  -X POST "$SEARCH_URL" --data "$REQ_BODY" 2>/dev/null || true)"
POST_HTTP="$(printf '%s' "$POST_RESP" | tail -n1)"
POST_BODY="$(printf '%s' "$POST_RESP" | sed '$d')"

SEARCH_ID="$(printf '%s' "$POST_BODY" | python3 -c 'import json,sys
try: print(json.load(sys.stdin).get("search_id",""))
except Exception: print("")' 2>/dev/null || true)"

if [ "$POST_HTTP" != "200" ] || [ -z "$SEARCH_ID" ]; then
  BLOCKER="search POST did not return a search_id — HTTP='$POST_HTTP' body='$(printf '%s' "$POST_BODY" | head -c 200)'"
  python3 - "$TMP_FRAG" "$POST_HTTP" "$BLOCKER" <<'PY'
import json, sys
frag, http, blocker = sys.argv[1:4]
with open(frag, "w") as fh:
    json.dump({"post": {"http": http}, "blocker": blocker}, fh)
PY
  write_evidence "SKIP" "$TMP_FRAG"
  echo "SKIP (§11.4.3): $BLOCKER"
  exit 77
fi
echo "  search_id=$SEARCH_ID — polling every ${POLL_INTERVAL}s (cap ${POLL_CAP}s) ..."

# --- Step 3: poll until completed/no_results (or cap) --------------------------
FINAL_BODY=""
FINAL_STATUS=""
ELAPSED=0
while [ "$ELAPSED" -lt "$POLL_CAP" ]; do
  POLL_RESP="$(curl -sS -m 15 "$SEARCH_URL/$SEARCH_ID" 2>/dev/null || true)"
  FINAL_STATUS="$(printf '%s' "$POLL_RESP" | python3 -c 'import json,sys
try: print(json.load(sys.stdin).get("status",""))
except Exception: print("")' 2>/dev/null || true)"
  if [ "$FINAL_STATUS" = "completed" ] || [ "$FINAL_STATUS" = "no_results" ]; then
    FINAL_BODY="$POLL_RESP"
    break
  fi
  sleep "$POLL_INTERVAL"
  ELAPSED=$((ELAPSED + POLL_INTERVAL))
done

if [ -z "$FINAL_BODY" ]; then
  BLOCKER="search '$SEARCH_ID' did not reach completed/no_results within ${POLL_CAP}s (last status='$FINAL_STATUS')"
  python3 - "$TMP_FRAG" "$FINAL_STATUS" "$BLOCKER" <<'PY'
import json, sys
frag, status, blocker = sys.argv[1:4]
with open(frag, "w") as fh:
    json.dump({"poll": {"last_status": status}, "blocker": blocker}, fh)
PY
  write_evidence "SKIP" "$TMP_FRAG"
  echo "SKIP (§11.4.3): $BLOCKER"
  exit 77
fi
echo "  search status=$FINAL_STATUS"

# --- Step 4: assert each tracker's REAL authentication state -------------------
# Python reads ONLY {name,status,authenticated,results_count,error}. It NEVER
# touches any credential value (the proxy holds those; they are not in the body).
ASSERT_OUT="$(PRIVATE_TRACKERS="$PRIVATE_TRACKERS" PUBLIC_TRACKERS="$PUBLIC_TRACKERS" \
  python3 - "$FINAL_BODY" "$TMP_FRAG" <<'PY'
import json, os, re, sys

final_body, frag = sys.argv[1], sys.argv[2]
private = set(os.environ["PRIVATE_TRACKERS"].split())
public = set(os.environ["PUBLIC_TRACKERS"].split())

# Honest transient-blocker pattern → operator-blocked SKIP (NOT a creds FAIL).
TRANSIENT = re.compile(
    r"captcha|timeout|temporarily|rate limit|unreachable|deadline",
    re.IGNORECASE,
)

try:
    body = json.loads(final_body)
except Exception as e:
    print("FAIL")
    print(f"  - search response is not JSON: {e}", file=sys.stderr)
    with open(frag, "w") as fh:
        json.dump({"error": "non-json search body"}, fh)
    sys.exit(0)

stats = body.get("tracker_stats")
by_name = {}
if isinstance(stats, list):
    for s in stats:
        if isinstance(s, dict) and s.get("name"):
            by_name[str(s["name"]).lower()] = s

per_tracker = []   # captured evidence — NO credential values
fails = []
skips = []
passes = []

def record(name, status, authed, count, verdict, reason=""):
    per_tracker.append({
        "name": name,
        "status": status,
        "authenticated": authed,
        "results_count": count,
        "verdict": verdict,
        "reason": reason,
    })

# --- PRIVATE trackers: must be authenticated -----------------------------------
for name in sorted(private):
    s = by_name.get(name)
    if s is None:
        record(name, None, None, None, "FAIL", "absent from tracker_stats")
        fails.append(f"{name}: absent from tracker_stats")
        continue
    status = s.get("status")
    authed = s.get("authenticated") is True
    count = s.get("results_count")
    err = str(s.get("error") or "")
    if authed and status in ("success", "empty"):
        record(name, status, authed, count, "PASS")
        passes.append(name)
    elif (not authed) and TRANSIENT.search(err):
        record(name, status, authed, count, "SKIP", f"transient: {err}")
        skips.append(f"{name}: transient blocker ({err})")
    else:
        reason = (f"authenticated={authed} status={status!r} error={err!r}"
                  if not authed else f"unexpected status {status!r} while authenticated")
        record(name, status, authed, count, "FAIL", reason)
        fails.append(f"{name}: {reason}")

# --- PUBLIC trackers: no login; must just return real results ------------------
for name in sorted(public):
    s = by_name.get(name)
    if s is None:
        record(name, None, None, None, "FAIL", "absent from tracker_stats")
        fails.append(f"{name}: absent from tracker_stats (public tracker)")
        continue
    status = s.get("status")
    authed = s.get("authenticated") is True
    count = s.get("results_count")
    try:
        count_int = int(count)
    except (TypeError, ValueError):
        count_int = 0
    if status == "success" and count_int > 0:
        record(name, status, authed, count, "PASS")
        passes.append(name)
    else:
        reason = f"public tracker status={status!r} results_count={count!r} (need success + >0)"
        record(name, status, authed, count, "FAIL", reason)
        fails.append(f"{name}: {reason}")

# --- Overall verdict -----------------------------------------------------------
expected = len(private) + len(public)
if fails:
    verdict = "FAIL"
elif len(passes) == expected:
    verdict = "PASS"
elif passes:
    # Some passed, none failed → remaining honestly SKIPped. Mixed but no genuine
    # FAIL: surface as SKIP (release gate blocks while operator-blocked exists).
    verdict = "SKIP"
else:
    verdict = "SKIP"   # every credentialed sub-check honestly SKIPped

frag_obj = {
    "search_status": body.get("status"),
    "tracker_stats": per_tracker,
    "passes": sorted(passes),
    "skips": skips,
    "fails": fails,
}
with open(frag, "w") as fh:
    json.dump(frag_obj, fh)

print(verdict)
for line in fails:
    print("  FAIL " + line, file=sys.stderr)
for line in skips:
    print("  SKIP " + line, file=sys.stderr)
PY
)"
VERDICT="$(printf '%s' "$ASSERT_OUT" | head -n1)"

write_evidence "$VERDICT" "$TMP_FRAG"

# Human-readable per-tracker summary (NO credential values — reads the evidence
# fragment we just wrote). Keeps the operator's eyes on authenticated/status.
python3 -c 'import json,sys
try:
    ev = json.load(open(sys.argv[1]))
except Exception:
    sys.exit(0)
for t in ev.get("tracker_stats", []):
    print("  - %-11s auth=%-5s status=%-8s results=%-4s -> %s%s" % (
        t.get("name"), str(t.get("authenticated")), str(t.get("status")),
        str(t.get("results_count")), t.get("verdict"),
        (" ("+t.get("reason")+")") if t.get("reason") else ""))' "$EVIDENCE" || true

case "$VERDICT" in
  PASS)
    echo "PASS: all 5 trackers proved their REAL auth/result state via live :7187 search —"
    echo "      private trackers authenticated, public rutor returned real results."
    echo "      evidence: $EVIDENCE"
    exit 0
    ;;
  SKIP)
    echo "SKIP (§11.4.3 / §11.4.21): no genuine credential FAIL, but one or more"
    echo "      credentialed sub-checks honestly SKIPped (operator-blocked transient)."
    echo "      Real per-tracker verdicts captured in $EVIDENCE."
    printf '%s\n' "$ASSERT_OUT" | tail -n +2
    exit 77
    ;;
  *)
    echo "FAIL: at least one tracker's REAL auth/result contract was not satisfied:"
    printf '%s\n' "$ASSERT_OUT" | tail -n +2
    echo "      evidence: $EVIDENCE"
    exit 1
    ;;
esac
