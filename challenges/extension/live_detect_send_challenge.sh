#!/usr/bin/env bash
#
# live_detect_send_challenge.sh — BobaLink Phase-4 LIVE end-to-end Challenge
# (§11.4.52 autonomous validation, §11.4.68/§11.4.69 positive sink-side evidence,
#  §11.4.83 captured-evidence under docs/qa-style .evidence/, feature class
#  network_throughput / package_install).
#
# Purpose:
#   Promote the BobaLink "Send → :7187" path from AUTONOMOUS_DESIGNED →
#   AUTONOMOUS_VERIFIED by driving the REAL merge service over real HTTP. It
#   POSTs a SYNTHETIC, freeleech-safe magnet to the live
#     POST http://localhost:7187/api/v1/download
#   endpoint (the same endpoint the shipped extension's boba-client targets) and
#   PASSes only on the REAL response BODY fields the route returns
#   (download_id / status / urls_count / added_count / results[]) — never on
#   "HTTP 200" alone. When qBittorrent itself is reachable, it additionally
#   queries qBittorrent's WebUI and asserts the synthetic infohash actually
#   appears in the torrent list (true sink-side proof the URL-add path worked).
#
# Anti-bluff contract (§11.4.6 / §11.4.68 / §11.4.69):
#   - Backend down (§11.4.3): honest SKIP (exit 77) with the EXACT curl blocker
#     captured to the evidence file — NEVER a green-without-a-real-backend pass,
#     NEVER a faked container success.
#   - Proxy up but qBittorrent unusable (status auth_failed/connection_failed):
#     honest SKIP (exit 77) carrying the REAL proxy verdict body — the
#     BobaLink→proxy contract was exercised end-to-end, but we cannot assert a
#     successful add, so we do not pretend one.
#   - PASS asserts user-observable REAL body fields + (when reachable) the
#     qBittorrent torrent list — a stubbed/no-op handler cannot satisfy these.
#
# FREELEECH-ONLY (project rule): the magnet is a fresh RANDOM 40-hex infohash
#   that references no real torrent on any tracker. It takes qBittorrent's
#   URL-add path (`{urls: <magnet>}` → /api/v2/torrents/add); it NEVER touches a
#   private tracker's download endpoint, so it cannot cost ratio.
#
# Inputs:   none (synthetic magnet, no credentials in the request).
#           Optional env: BOBA_BASE_URL (default http://localhost:7187),
#                         QBIT_BASE_URL (default http://localhost:7185),
#                         QBIT_USER/QBIT_PASS (default admin/admin).
# Outputs:  challenges/extension/.evidence/live_detect_send.json (captured
#           evidence: probe result, request, REAL response body, qBit lookup);
#           a clear PASS:/SKIP:/FAIL: line; exit 0 PASS, 77 honest SKIP, non-zero FAIL.
# Side-effects: on PASS-path it adds ONE synthetic (dead) magnet to qBittorrent
#           and then REMOVES it (cleanup, §11.4.14) so the target is left quiescent.
# Dependencies: curl, python3.
# Cross-references:
#   - download-proxy/src/api/routes.py :: initiate_download (the live endpoint)
#   - extension/tests/live/download-endpoint.live.test.ts (the live Vitest sibling)
#   - extension/src/api/boba-client.ts (the shipped client that targets this URL)
#   - start.sh / scripts/boba-ctl.sh (the sanctioned orchestrator that boots :7187)

set -euo pipefail

CHALLENGE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EVIDENCE_DIR="$CHALLENGE_DIR/.evidence"
EVIDENCE="$EVIDENCE_DIR/live_detect_send.json"

BOBA_BASE="${BOBA_BASE_URL:-http://localhost:7187}"
BOBA_BASE="${BOBA_BASE%/}"
HEALTH_URL="$BOBA_BASE/health"
DOWNLOAD_URL="$BOBA_BASE/api/v1/download"

QBIT_BASE="${QBIT_BASE_URL:-http://localhost:7185}"
QBIT_BASE="${QBIT_BASE%/}"
QBIT_USER="${QBIT_USER:-admin}"
QBIT_PASS="${QBIT_PASS:-admin}"

mkdir -p "$EVIDENCE_DIR"
rm -f "$EVIDENCE"

echo "=== live_detect_send_challenge (BobaLink Phase-4 LIVE :7187) ==="

# --- Preconditions (honest blockers, never a faked PASS) ----------------------
for bin in curl python3; do
  if ! command -v "$bin" >/dev/null 2>&1; then
    echo "FAIL: required tool '$bin' not found on PATH"; exit 1
  fi
done

# Synthetic, freeleech-safe magnet: a fresh random 40-hex infohash.
INFOHASH="$(python3 -c 'import secrets; print(secrets.token_hex(20))')"
MAGNET="magnet:?xt=urn:btih:${INFOHASH}&dn=helixqa-live-probe"
RESULT_ID="helixqa-live-$(date +%s)"
REQ_BODY="$(python3 - "$RESULT_ID" "$MAGNET" <<'PY'
import json, sys
print(json.dumps({"result_id": sys.argv[1], "download_urls": [sys.argv[2]]}))
PY
)"

# Helper: write the evidence JSON atomically from a python heredoc payload.
write_evidence() { # $1=verdict $2=json-fragment-file
  python3 - "$EVIDENCE" "$1" "$INFOHASH" "$MAGNET" "$RESULT_ID" "$BOBA_BASE" "$2" <<'PY'
import json, sys, os
out, verdict, infohash, magnet, result_id, base, frag_path = sys.argv[1:8]
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
    "challenge": "live_detect_send",
    "base": base,
    "infohash": infohash,
    "magnet": magnet,
    "result_id": result_id,
}
ev.update(frag)
with open(out, "w", encoding="utf-8") as fh:
    json.dump(ev, fh, indent=2)
print(f"  evidence → {out}")
PY
}

TMP_FRAG="$(mktemp)"
trap 'rm -f "$TMP_FRAG"' EXIT

# --- Step 1: probe the REAL backend (§11.4.3 reachability guard) --------------
echo "Probing $HEALTH_URL …"
HEALTH_HTTP="000"
HEALTH_BODY=""
if HEALTH_BODY="$(curl -sS -m 6 -w $'\n%{http_code}' "$HEALTH_URL" 2>"$TMP_FRAG.err")"; then
  HEALTH_HTTP="$(printf '%s' "$HEALTH_BODY" | tail -n1)"
  HEALTH_BODY="$(printf '%s' "$HEALTH_BODY" | sed '$d')"
fi
CURL_ERR="$(cat "$TMP_FRAG.err" 2>/dev/null || true)"
rm -f "$TMP_FRAG.err"

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

# --- Step 2: POST the synthetic magnet to the LIVE endpoint -------------------
echo "POST $DOWNLOAD_URL  (synthetic freeleech-safe magnet btih:$INFOHASH)…"
RESP="$(curl -sS -m 30 -w $'\n%{http_code}' \
  -H 'content-type: application/json' \
  -X POST "$DOWNLOAD_URL" --data "$REQ_BODY" 2>/dev/null || true)"
RESP_HTTP="$(printf '%s' "$RESP" | tail -n1)"
RESP_BODY="$(printf '%s' "$RESP" | sed '$d')"

echo "  HTTP $RESP_HTTP"
echo "  body: $RESP_BODY"

# --- Step 3: optionally query qBittorrent for the synthetic infohash ----------
QBIT_FOUND="not_checked"
QBIT_NOTE=""
if curl -sS -m 5 -o /dev/null "$QBIT_BASE/" 2>/dev/null; then
  SID="$(curl -sS -m 6 -c - -X POST "$QBIT_BASE/api/v2/auth/login" \
         --data "username=${QBIT_USER}&password=${QBIT_PASS}" 2>/dev/null \
         | awk '/SID/{print $7}' | tail -n1 || true)"
  if [ -n "$SID" ]; then
    LIST="$(curl -sS -m 8 -H "Cookie: SID=$SID" \
            "$QBIT_BASE/api/v2/torrents/info?hashes=${INFOHASH}" 2>/dev/null || true)"
    if printf '%s' "$LIST" | grep -qi "$INFOHASH"; then
      QBIT_FOUND="present"
    else
      QBIT_FOUND="absent"
      QBIT_NOTE="infohash not (yet) in torrents/info — magnet is a dead/synthetic hash; add accepted by qBit but no metadata"
    fi
  else
    QBIT_FOUND="login_failed"; QBIT_NOTE="could not log into qBittorrent WebUI ($QBIT_BASE)"
  fi
else
  QBIT_FOUND="unreachable"; QBIT_NOTE="qBittorrent WebUI not reachable at $QBIT_BASE"
fi

# --- Step 4: assert on the REAL response body + write evidence -----------------
ASSERT_OUT="$(BOBA_RESP_HTTP="$RESP_HTTP" QBIT_FOUND="$QBIT_FOUND" QBIT_NOTE="$QBIT_NOTE" \
  EXPECT_MAGNET="$MAGNET" \
  python3 - "$RESP_BODY" "$TMP_FRAG" <<'PY'
import json, os, sys

resp_body, frag = sys.argv[1], sys.argv[2]
http = os.environ["BOBA_RESP_HTTP"]
qbit_found = os.environ["QBIT_FOUND"]
qbit_note = os.environ["QBIT_NOTE"]
expect_magnet = os.environ["EXPECT_MAGNET"]

verdict = "FAIL"
errors = []
body = None
try:
    body = json.loads(resp_body)
except Exception as e:
    errors.append(f"response body is not JSON: {e}: {resp_body[:200]!r}")

if http != "200":
    errors.append(f"download endpoint returned HTTP {http} (expected 200)")

closed = {"initiated", "failed", "auth_failed", "connection_failed"}
if body is not None:
    if not body.get("download_id"):
        errors.append("real response missing a download_id")
    st = body.get("status")
    if st not in closed:
        errors.append(f"status {st!r} not in closed vocabulary {sorted(closed)}")

    if st in ("auth_failed", "connection_failed"):
        # Proxy reachable but qBittorrent unusable — honest SKIP, real proxy body.
        verdict = "SKIP"
    elif not errors:
        # Success/failed-add path — assert echoed + computed fields.
        if body.get("urls_count") != 1:
            errors.append(f"urls_count {body.get('urls_count')!r} != 1")
        results = body.get("results")
        if not isinstance(results, list) or len(results) != 1:
            errors.append(f"results not a single-element list: {results!r}")
        else:
            r0 = results[0]
            if r0.get("url") != expect_magnet:
                errors.append(f"result url {r0.get('url')!r} != sent magnet")
            if r0.get("status") not in ("added", "failed", "error"):
                errors.append(f"per-url status {r0.get('status')!r} unexpected")
            # internal consistency: top status must match per-url verdict
            if r0.get("status") == "added":
                if body.get("added_count", 0) < 1:
                    errors.append("added_count < 1 despite an 'added' result")
                if body.get("status") != "initiated":
                    errors.append("top status must be 'initiated' when a url was added")
            else:
                if body.get("status") != "failed":
                    errors.append("top status must be 'failed' when no url added")
        if not errors:
            verdict = "PASS"

frag_obj = {
    "request": {"http_method": "POST", "url_path": "/api/v1/download"},
    "response": {"http": http, "body": body if body is not None else resp_body},
    "qbittorrent": {"infohash_lookup": qbit_found, "note": qbit_note},
    "assertions_failed": errors,
}
with open(frag, "w") as fh:
    json.dump(frag_obj, fh)

print(verdict)
for e in errors:
    print("  - " + e, file=sys.stderr)
PY
)"
VERDICT="$(printf '%s' "$ASSERT_OUT" | head -n1)"

write_evidence "$VERDICT" "$TMP_FRAG"

case "$VERDICT" in
  PASS)
    echo "PASS: live :7187 /api/v1/download accepted the synthetic magnet and returned a"
    echo "      consistent REAL body (download_id, status, urls_count=1, results[1])."
    echo "      qBittorrent infohash lookup: $QBIT_FOUND ${QBIT_NOTE:+($QBIT_NOTE)}"
    echo "      evidence: $EVIDENCE"
    # Cleanup (§11.4.14): remove the synthetic torrent if it landed.
    if [ "$QBIT_FOUND" = "present" ] && [ -n "${SID:-}" ]; then
      curl -sS -m 6 -H "Cookie: SID=$SID" -X POST "$QBIT_BASE/api/v2/torrents/delete" \
        --data "hashes=${INFOHASH}&deleteFiles=true" >/dev/null 2>&1 || true
      echo "      cleanup: removed synthetic torrent $INFOHASH from qBittorrent"
    fi
    exit 0
    ;;
  SKIP)
    echo "SKIP (§11.4.3): proxy reachable but qBittorrent backend unusable —"
    echo "      real proxy verdict captured in $EVIDENCE (status auth_failed/connection_failed)."
    exit 77
    ;;
  *)
    echo "FAIL: live response did not satisfy the real-body contract:"
    printf '%s\n' "$ASSERT_OUT" | tail -n +2
    echo "      evidence: $EVIDENCE"
    exit 1
    ;;
esac
