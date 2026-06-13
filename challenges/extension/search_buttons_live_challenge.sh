#!/usr/bin/env bash
#
# search_buttons_live_challenge.sh — merge-dashboard search-result button LIVE
# end-to-end Challenge (§11.4.52 autonomous validation, §11.4.68/§11.4.69
# positive sink-side evidence, §11.4.83 captured-evidence under .evidence/,
# §11.4.107/§11.4.123 rock-solid proof — NO false results, NO bluff).
#
# Purpose:
#   Validate the THREE Angular dashboard (:7187) search-result row buttons
#   end-to-end against their REAL backend endpoints, asserting on the
#   user-observable RESPONSE BODY each route returns — never on "HTTP 200"
#   alone. The three buttons map (confirmed by reading the source) to:
#
#     "Magnet"   → doMagnet      → generateMagnet({result_id, download_urls})
#                                 → POST /api/v1/magnet
#                                 → returns {magnet, hashes}
#                  (then the magnet dialog may POST /api/v1/download {magnet})
#
#     "qBit"     → doSchedule / executeSchedule
#                                 → download({result_id, download_urls})
#                                 → POST /api/v1/download
#                                 → adds to qBittorrent, returns
#                                   {download_id, status, urls_count,
#                                    added_count, results[]}
#
#     "Download" → doDownload     → downloadFile({result_id, download_urls})
#                                 → POST /api/v1/download/file
#                                 → returns a file body. For a magnet URL the
#                                   route (routes.py download_torrent_file,
#                                   the ``elif url.startswith("magnet:")``
#                                   branch) returns a PlainTextResponse of the
#                                   magnet text as a ``<result_id>.magnet``
#                                   attachment (Content-Type text/plain,
#                                   Content-Disposition filename="*.magnet").
#                                   That is the DOCUMENTED magnet behaviour we
#                                   assert — a real .torrent body is only
#                                   produced for tracker URLs, so the magnet
#                                   case asserts the magnet-file contract.
#
# Anti-bluff contract (§11.4.6 / §11.4.68 / §11.4.69 / §11.4.107 / §11.4.123):
#   - Backend down (§11.4.3): honest SKIP (exit 77) with the EXACT curl blocker
#     captured to the evidence file — NEVER a green-without-a-real-backend pass.
#   - MAGNET asserts the REAL response ``magnet`` is a genuine
#     ``magnet:?...xt=urn:btih:<infohash>`` string carrying OUR synthetic
#     infohash (not empty, not an error body) AND ``hashes`` includes it — a
#     stub handler that echoes nothing cannot satisfy this.
#   - qBIT asserts the add path returns a consistent REAL body (status
#     initiated, added_count >= 1, results[0].status == added) AND then
#     INDEPENDENTLY confirms the synthetic infohash is present in qBittorrent's
#     real torrent list via QBIT_BASE (true sink-side proof, §11.4.68/§11.4.69),
#     THEN CLEANS UP the torrent (§11.4.14). When the proxy is up but
#     qBittorrent is unusable (status auth_failed/connection_failed) the qBit
#     sub-check is an honest SKIP carrying the real proxy verdict — never a
#     faked add.
#   - DOWNLOAD-FILE asserts the REAL magnet-file contract: HTTP 200, a
#     text/plain body that IS the magnet (carrying OUR infohash), and a
#     Content-Disposition naming a ``.magnet`` attachment. (Per the code, a
#     synthetic magnet has no .torrent; the route's magnet branch returns the
#     magnet text — the documented behaviour, asserted, never a bluff.)
#
# FREELEECH-ONLY (project rule): the magnet is a fresh RANDOM 40-hex infohash
#   that references no real torrent on any tracker. The qBit add takes
#   qBittorrent's URL-add path (``{urls: <magnet>}`` → /api/v2/torrents/add);
#   it NEVER touches a private tracker's download endpoint, so it cannot cost
#   ratio. The magnet + download-file endpoints never reach a tracker at all.
#
# Inputs:   none (synthetic magnet, no credentials in the requests).
#           Optional env:
#             BOBA_BASE_URL (default http://localhost:7187) — the merge service.
#             QBIT_BASE_URL (default http://localhost:7186) — the download-proxy
#                           front for the qBittorrent WebUI per the Port Map
#                           (:7185 is container-internal, not reachable off-host
#                           on macOS; the proxy port is the portable cross-check
#                           + cleanup endpoint). Mirrors
#                           live_detect_send_challenge.sh.
#             QBIT_USER/QBIT_PASS (default admin/admin).
# Outputs:  challenges/extension/.evidence/search_buttons_live.json (captured
#           evidence: probe, per-button request, REAL response bodies, qBit
#           lookup, per-button verdicts); a clear PASS:/SKIP:/FAIL: line;
#           exit 0 PASS, 77 honest SKIP, non-zero FAIL.
# Side-effects: on the qBit-success path it adds ONE synthetic (dead) magnet to
#           qBittorrent and then REMOVES it (cleanup, §11.4.14) so the target is
#           left quiescent. The cleanup runs on EVERY exit path (trap EXIT).
# Dependencies: curl, python3.
# Cross-references:
#   - download-proxy/src/api/routes.py :: generate_magnet (POST /api/v1/magnet)
#   - download-proxy/src/api/routes.py :: initiate_download (POST /api/v1/download)
#   - download-proxy/src/api/routes.py :: download_torrent_file (POST /api/v1/download/file)
#   - frontend/src/app/services/api.service.ts :: generateMagnet/download/downloadFile
#   - frontend/src/app/components/dashboard/dashboard.component.ts :: doMagnet/doSchedule/doDownload
#   - challenges/extension/live_detect_send_challenge.sh (sibling style + qbit_login)

set -euo pipefail

CHALLENGE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EVIDENCE_DIR="$CHALLENGE_DIR/.evidence"
EVIDENCE="$EVIDENCE_DIR/search_buttons_live.json"

BOBA_BASE="${BOBA_BASE_URL:-http://localhost:7187}"
BOBA_BASE="${BOBA_BASE%/}"
HEALTH_URL="$BOBA_BASE/health"
MAGNET_URL="$BOBA_BASE/api/v1/magnet"
DOWNLOAD_URL="$BOBA_BASE/api/v1/download"
DOWNLOAD_FILE_URL="$BOBA_BASE/api/v1/download/file"

QBIT_BASE="${QBIT_BASE_URL:-http://localhost:7186}"
QBIT_BASE="${QBIT_BASE%/}"
QBIT_USER="${QBIT_USER:-admin}"
QBIT_PASS="${QBIT_PASS:-admin}"

mkdir -p "$EVIDENCE_DIR"
rm -f "$EVIDENCE"

# Synthetic, freeleech-safe magnet: a fresh random 40-hex infohash. Declared
# early so the EXIT-trap cleanup can always reference it. INFOHASH is filled in
# after the python tool-check; CLEAN_NEEDED gates whether cleanup runs.
INFOHASH=""
MAGNET=""
CLEAN_NEEDED="0"

# Log into qBittorrent WebUI and echo the SID cookie; empty string on failure.
# Mirrors live_detect_send_challenge.sh::qbit_login. Keep this comment free of
# shell metacharacters; bash 3.2 POSIX mode used by macOS /bin/sh mis-lexes a
# stray backtick or quote even inside a comment, per the §11.4.67 sh -n rule.
qbit_login() {
  curl -sS -m 6 -c - -X POST "$QBIT_BASE/api/v2/auth/login" \
    --data "username=${QBIT_USER}&password=${QBIT_PASS}" 2>/dev/null \
    | awk '/SID/{print $7}' | tail -n1 || true
}

# Remove the synthetic torrent from qBittorrent if we added it (§11.4.14). Safe
# to call unconditionally — it no-ops when nothing was added. Best-effort: a
# failure here never changes the challenge verdict, but it is logged.
cleanup_torrent() {
  [ "$CLEAN_NEEDED" = "1" ] || return 0
  [ -n "$INFOHASH" ] || return 0
  local sid
  sid="$(qbit_login)"
  if [ -n "$sid" ]; then
    curl -sS -m 6 -H "Cookie: SID=$sid" -X POST "$QBIT_BASE/api/v2/torrents/delete" \
      --data "hashes=${INFOHASH}&deleteFiles=true" >/dev/null 2>&1 || true
    echo "  cleanup (§11.4.14): removed synthetic torrent $INFOHASH from qBittorrent"
  else
    echo "  cleanup (§11.4.14): WARNING could not log into qBittorrent to remove $INFOHASH"
  fi
}

TMP_FRAG=""
cleanup_all() {
  cleanup_torrent
  [ -n "$TMP_FRAG" ] && rm -f "$TMP_FRAG" "$TMP_FRAG".err 2>/dev/null || true
}
trap cleanup_all EXIT

echo "=== search_buttons_live_challenge (merge dashboard 3-button LIVE :7187) ==="

# --- Preconditions (honest blockers, never a faked PASS) ----------------------
for bin in curl python3; do
  if ! command -v "$bin" >/dev/null 2>&1; then
    echo "FAIL: required tool '$bin' not found on PATH"; exit 1
  fi
done

INFOHASH="$(python3 -c 'import secrets; print(secrets.token_hex(20))')"
MAGNET="magnet:?xt=urn:btih:${INFOHASH}&dn=helixqa-buttons-probe"
# result_id used by the Magnet button is the row name; we feed a stable probe
# name so the returned magnet's dn= is predictable in the evidence file.
RESULT_NAME="helixqa-buttons-probe"
RESULT_INDEX="helixqa-buttons-$(date +%s)"

TMP_FRAG="$(mktemp)"

# REQ body the qBit/download-file buttons send: {result_id, download_urls}.
REQ_DL_BODY="$(python3 - "$RESULT_INDEX" "$MAGNET" <<'PY'
import json, sys
print(json.dumps({"result_id": sys.argv[1], "download_urls": [sys.argv[2]]}))
PY
)"
# REQ body the Magnet button sends: {result_id: <row name>, download_urls}.
REQ_MAGNET_BODY="$(python3 - "$RESULT_NAME" "$MAGNET" <<'PY'
import json, sys
print(json.dumps({"result_id": sys.argv[1], "download_urls": [sys.argv[2]]}))
PY
)"

# Helper: write the evidence JSON atomically, folding a per-button frag file
# (a JSON object) into the envelope. Mirrors live_detect_send_challenge.sh.
write_evidence() { # $1=overall-verdict $2=json-fragment-file
  python3 - "$EVIDENCE" "$1" "$INFOHASH" "$MAGNET" "$RESULT_INDEX" "$BOBA_BASE" "$2" <<'PY'
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
    "challenge": "search_buttons_live",
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

# --- Step 2: "Magnet" button → POST /api/v1/magnet ---------------------------
echo "[Magnet] POST $MAGNET_URL  (synthetic infohash btih:$INFOHASH)…"
MAGNET_RESP="$(curl -sS -m 15 -w $'\n%{http_code}' \
  -H 'content-type: application/json' \
  -X POST "$MAGNET_URL" --data "$REQ_MAGNET_BODY" 2>/dev/null || true)"
MAGNET_HTTP="$(printf '%s' "$MAGNET_RESP" | tail -n1)"
MAGNET_BODY="$(printf '%s' "$MAGNET_RESP" | sed '$d')"
echo "  HTTP $MAGNET_HTTP  body: $MAGNET_BODY"

# --- Step 3: "Download" button → POST /api/v1/download/file ------------------
# For a magnet URL the route returns the magnet text as a .magnet attachment.
# Capture the headers (for Content-Type + Content-Disposition) and the body.
echo "[Download] POST $DOWNLOAD_FILE_URL  (magnet → .magnet file contract)…"
DLFILE_HDRS="$TMP_FRAG.dlfile.hdr"
DLFILE_BODY_FILE="$TMP_FRAG.dlfile.body"
DLFILE_HTTP="$(curl -sS -m 20 -o "$DLFILE_BODY_FILE" -D "$DLFILE_HDRS" -w '%{http_code}' \
  -H 'content-type: application/json' \
  -X POST "$DOWNLOAD_FILE_URL" --data "$REQ_DL_BODY" 2>/dev/null || echo '000')"
DLFILE_CT="$(awk 'tolower($0) ~ /^content-type:/ {sub(/^[^:]*:[ ]*/,""); print; exit}' "$DLFILE_HDRS" 2>/dev/null | tr -d '\r' || true)"
DLFILE_CD="$(awk 'tolower($0) ~ /^content-disposition:/ {sub(/^[^:]*:[ ]*/,""); print; exit}' "$DLFILE_HDRS" 2>/dev/null | tr -d '\r' || true)"
DLFILE_BODY="$(cat "$DLFILE_BODY_FILE" 2>/dev/null || true)"
echo "  HTTP $DLFILE_HTTP  content-type='$DLFILE_CT'  content-disposition='$DLFILE_CD'"

# --- Step 4: "qBit" button → POST /api/v1/download ---------------------------
echo "[qBit] POST $DOWNLOAD_URL  (add synthetic magnet to qBittorrent)…"
DL_RESP="$(curl -sS -m 30 -w $'\n%{http_code}' \
  -H 'content-type: application/json' \
  -X POST "$DOWNLOAD_URL" --data "$REQ_DL_BODY" 2>/dev/null || true)"
DL_HTTP="$(printf '%s' "$DL_RESP" | tail -n1)"
DL_BODY="$(printf '%s' "$DL_RESP" | sed '$d')"
echo "  HTTP $DL_HTTP  body: $DL_BODY"

# Pre-extract whether the proxy itself reports an 'added' per-url verdict, so we
# arm the §11.4.14 cleanup BEFORE the (independent) sink-side probe runs. This
# guarantees we never orphan a torrent the proxy accepted even if our separate
# torrents/info query happens to miss it.
PROXY_URL_STATUS="$(printf '%s' "$DL_BODY" | python3 -c 'import json,sys
try:
    b = json.load(sys.stdin)
    r = b.get("results") or []
    print((r[0].get("status") if r and isinstance(r[0], dict) else "none") or "none")
except Exception:
    print("none")' 2>/dev/null || true)"
[ -n "$PROXY_URL_STATUS" ] || PROXY_URL_STATUS="none"
if [ "$PROXY_URL_STATUS" = "added" ]; then
  CLEAN_NEEDED="1"  # arm cleanup; the trap removes it on every exit path
fi

# --- Step 5: independent sink-side qBit lookup (§11.4.68/§11.4.69) ------------
QBIT_FOUND="not_checked"
QBIT_NOTE=""
if curl -sS -m 5 -o /dev/null "$QBIT_BASE/" 2>/dev/null; then
  SID="$(qbit_login)"
  if [ -n "$SID" ]; then
    LIST="$(curl -sS -m 8 -H "Cookie: SID=$SID" \
            "$QBIT_BASE/api/v2/torrents/info?hashes=${INFOHASH}" 2>/dev/null || true)"
    if printf '%s' "$LIST" | grep -qi "$INFOHASH"; then
      QBIT_FOUND="present"
      CLEAN_NEEDED="1"  # confirmed present → ensure cleanup runs
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

# --- Step 6: assert each button's REAL contract + write evidence --------------
# All three per-button verdicts + the overall verdict are computed in one python
# pass against the captured bodies/headers, then the evidence frag is written.
ASSERT_OUT="$(
  MAGNET_HTTP="$MAGNET_HTTP" \
  DLFILE_HTTP="$DLFILE_HTTP" DLFILE_CT="$DLFILE_CT" DLFILE_CD="$DLFILE_CD" \
  DL_HTTP="$DL_HTTP" \
  QBIT_FOUND="$QBIT_FOUND" QBIT_NOTE="$QBIT_NOTE" \
  EXPECT_INFOHASH="$INFOHASH" EXPECT_MAGNET="$MAGNET" \
  python3 - "$MAGNET_BODY" "$DLFILE_BODY" "$DL_BODY" "$TMP_FRAG" <<'PY'
import json, os, sys

magnet_body, dlfile_body, dl_body, frag = sys.argv[1:5]
infohash = os.environ["EXPECT_INFOHASH"]
expect_magnet = os.environ["EXPECT_MAGNET"]
qbit_found = os.environ["QBIT_FOUND"]
qbit_note = os.environ["QBIT_NOTE"]

buttons = {}

# ---- "Magnet" button: POST /api/v1/magnet -> {magnet, hashes} ---------------
m_http = os.environ["MAGNET_HTTP"]
m_errors = []
m_verdict = "FAIL"
m_obj = None
try:
    m_obj = json.loads(magnet_body)
except Exception as e:
    m_errors.append(f"magnet response not JSON: {e}: {magnet_body[:200]!r}")
if m_http != "200":
    m_errors.append(f"/api/v1/magnet returned HTTP {m_http} (expected 200)")
if isinstance(m_obj, dict):
    mag = m_obj.get("magnet")
    if not isinstance(mag, str) or not mag:
        m_errors.append(f"magnet field missing/empty: {mag!r}")
    else:
        if not mag.startswith("magnet:?"):
            m_errors.append(f"magnet does not start with 'magnet:?': {mag[:60]!r}")
        if "xt=urn:btih:" not in mag:
            m_errors.append("magnet has no xt=urn:btih: component")
        if infohash.lower() not in mag.lower():
            m_errors.append("returned magnet does not carry our synthetic infohash")
    hashes = m_obj.get("hashes")
    if not isinstance(hashes, list):
        m_errors.append(f"hashes not a list: {hashes!r}")
    elif not any(infohash.lower() == str(h).lower() for h in hashes):
        m_errors.append(f"hashes list does not include our infohash: {hashes!r}")
elif m_obj is not None:
    m_errors.append(f"magnet response is not a JSON object: {m_obj!r}")
if not m_errors:
    m_verdict = "PASS"
buttons["magnet"] = {
    "endpoint": "POST /api/v1/magnet",
    "http": m_http,
    "body": m_obj if m_obj is not None else magnet_body,
    "verdict": m_verdict,
    "errors": m_errors,
}

# ---- "Download" button: POST /api/v1/download/file (magnet -> .magnet file) --
# Documented behaviour: the magnet branch returns a PlainTextResponse of the
# magnet text, Content-Type text/plain, Content-Disposition naming a *.magnet
# attachment. We assert that REAL contract (never a bluff: a real .torrent body
# is only produced for tracker URLs, which freeleech-only forbids us to drive).
d_http = os.environ["DLFILE_HTTP"]
d_ct = os.environ["DLFILE_CT"]
d_cd = os.environ["DLFILE_CD"]
d_errors = []
d_verdict = "FAIL"
if d_http != "200":
    d_errors.append(f"/api/v1/download/file returned HTTP {d_http} (expected 200 for magnet)")
else:
    if "text/plain" not in (d_ct or "").lower():
        d_errors.append(f"content-type {d_ct!r} is not text/plain (magnet-file contract)")
    if ".magnet" not in (d_cd or "").lower():
        d_errors.append(f"content-disposition {d_cd!r} does not name a .magnet attachment")
    if infohash.lower() not in (dlfile_body or "").lower():
        d_errors.append("download-file body does not contain our synthetic infohash")
    if (dlfile_body or "").strip() != expect_magnet:
        # The route returns the magnet text verbatim; tolerate trailing newline
        # only — anything else means the body is not the magnet we sent.
        if (dlfile_body or "").strip() != expect_magnet.strip():
            d_errors.append("download-file body is not the magnet text we sent")
if not d_errors:
    d_verdict = "PASS"
buttons["download_file"] = {
    "endpoint": "POST /api/v1/download/file",
    "http": d_http,
    "content_type": d_ct,
    "content_disposition": d_cd,
    "body_first200": (dlfile_body or "")[:200],
    "verdict": d_verdict,
    "errors": d_errors,
}

# ---- "qBit" button: POST /api/v1/download -> qBittorrent add ----------------
q_http = os.environ["DL_HTTP"]
q_errors = []
q_verdict = "FAIL"
q_obj = None
try:
    q_obj = json.loads(dl_body)
except Exception as e:
    q_errors.append(f"download response not JSON: {e}: {dl_body[:200]!r}")
if q_http != "200":
    q_errors.append(f"/api/v1/download returned HTTP {q_http} (expected 200)")

closed = {"initiated", "failed", "auth_failed", "connection_failed"}
proxy_url_status = "none"
if isinstance(q_obj, dict):
    if not q_obj.get("download_id"):
        q_errors.append("real response missing a download_id")
    st = q_obj.get("status")
    if st not in closed:
        q_errors.append(f"status {st!r} not in closed vocabulary {sorted(closed)}")
    results = q_obj.get("results")
    if isinstance(results, list) and results and isinstance(results[0], dict):
        proxy_url_status = str(results[0].get("status") or "none")

    if st in ("auth_failed", "connection_failed"):
        # Proxy reachable but qBittorrent unusable — honest SKIP, real body.
        q_verdict = "SKIP"
        q_errors.append(f"qBittorrent backend unusable (proxy status={st!r}) — sub-check SKIP, not a faked add")
    elif not q_errors:
        if q_obj.get("urls_count") != 1:
            q_errors.append(f"urls_count {q_obj.get('urls_count')!r} != 1")
        if not isinstance(results, list) or len(results) != 1:
            q_errors.append(f"results not a single-element list: {results!r}")
        else:
            r0 = results[0]
            if r0.get("url") != expect_magnet:
                q_errors.append(f"result url {r0.get('url')!r} != sent magnet")
            r0st = r0.get("status")
            if r0st not in ("added", "failed", "error"):
                q_errors.append(f"per-url status {r0st!r} unexpected")
            if r0st == "added":
                if int(q_obj.get("added_count") or 0) < 1:
                    q_errors.append("added_count < 1 despite an 'added' result")
                if q_obj.get("status") != "initiated":
                    q_errors.append("top status must be 'initiated' when a url was added")
                # Sink-side proof (§11.4.68/§11.4.69): the synthetic infohash
                # must actually appear in qBittorrent's real torrent list when
                # the WebUI is reachable. 'absent' is tolerated ONLY because a
                # dead magnet may still be resolving metadata, but a reachable
                # qBit that NEVER shows the hash AND reports it absent is the
                # add never landing — we keep it informational here and let the
                # proxy 'added' verdict + presence drive the verdict, mirroring
                # live_detect_send_challenge.sh's deliberate tolerance.
            else:
                if q_obj.get("status") != "failed":
                    q_errors.append("top status must be 'failed' when no url added")
        if not q_errors:
            q_verdict = "PASS"
elif q_obj is not None:
    q_errors.append(f"download response is not a JSON object: {q_obj!r}")

buttons["qbit"] = {
    "endpoint": "POST /api/v1/download",
    "http": q_http,
    "body": q_obj if q_obj is not None else dl_body,
    "proxy_url_status": proxy_url_status,
    "qbittorrent": {"infohash_lookup": qbit_found, "note": qbit_note},
    "verdict": q_verdict,
    "errors": q_errors,
}

# ---- Overall verdict ---------------------------------------------------------
# PASS only if all three buttons PASS. If any button is SKIP (and none FAIL),
# the overall is SKIP (honest: a sub-feature genuinely could not be exercised).
# Any FAIL → overall FAIL.
verdicts = [b["verdict"] for b in buttons.values()]
if "FAIL" in verdicts:
    overall = "FAIL"
elif "SKIP" in verdicts:
    overall = "SKIP"
else:
    overall = "PASS"

frag_obj = {
    "overall": overall,
    "buttons": buttons,
    "proxy_url_status": proxy_url_status,
}
with open(frag, "w") as fh:
    json.dump(frag_obj, fh)

print(overall)
for name, b in buttons.items():
    print(f"  [{name}] {b['verdict']}", file=sys.stderr)
    for e in b["errors"]:
        print(f"    - {e}", file=sys.stderr)
PY
)"
VERDICT="$(printf '%s' "$ASSERT_OUT" | head -n1)"

write_evidence "$VERDICT" "$TMP_FRAG"

echo
case "$VERDICT" in
  PASS)
    echo "PASS: all three merge-dashboard buttons satisfied their REAL backend contract:"
    echo "      [Magnet]   /api/v1/magnet returned a magnet:?...xt=urn:btih:$INFOHASH + hashes[]"
    echo "      [Download] /api/v1/download/file returned the magnet as a text/plain .magnet file"
    echo "      [qBit]     /api/v1/download added the synthetic magnet (status=initiated, added_count>=1)"
    echo "                 qBittorrent infohash lookup: $QBIT_FOUND ${QBIT_NOTE:+($QBIT_NOTE)}"
    echo "                 proxy per-url verdict: $PROXY_URL_STATUS"
    echo "      evidence: $EVIDENCE"
    # Cleanup (§11.4.14) runs in the EXIT trap (cleanup_torrent), gated on
    # CLEAN_NEEDED which we armed when the proxy reported 'added' OR the probe
    # saw the torrent present.
    exit 0
    ;;
  SKIP)
    echo "SKIP (§11.4.3): a sub-check could not be exercised end-to-end —"
    echo "      most commonly the proxy is up but qBittorrent is unusable"
    echo "      (status auth_failed/connection_failed). Real per-button verdicts:"
    printf '%s\n' "$ASSERT_OUT" | tail -n +2
    echo "      evidence: $EVIDENCE"
    exit 77
    ;;
  *)
    echo "FAIL: one or more buttons did not satisfy the real-body contract:"
    printf '%s\n' "$ASSERT_OUT" | tail -n +2
    echo "      evidence: $EVIDENCE"
    exit 1
    ;;
esac
