#!/usr/bin/env bash
# check_cm_no_test_tag_debris.sh — CM-NO-TEST-TAG-DEBRIS
#
# INVARIANT: the live qBittorrent instance carries NO test-generated tags.
#
# RETROACTIVE CATCHER for the 2026-09-01 audit. The operator opened the
# qBittorrent WebUI and found EIGHTEEN tags, every one of them debris:
#
#     boba-bridge-go-273b569c   boba-bridge-red-113376aa   (x8 each)
#     boba-manual-proof-1347499 boba-py-proof
#
# minted by tests/integration/test_webui_bridge_auth_live.py, which generated a
# unique tag per test and removed none of them (§11.4.14 — every test must
# leave the target quiescent). Meanwhile every REAL torrent carried tags='' —
# so the ONLY tags visible in the operator's WebUI were the test suite's
# leftovers. That is what prompted the whole content-tagging work.
#
# WHY THIS GATE EXISTS AND NOT JUST THE CLEANUP FIXTURE (review finding M-e):
# the suite's `_purge_suite_tags` teardown was added, but a teardown FAILURE
# only prints to stderr and the run still reports green. So a cleanup that
# silently stopped working would re-accumulate debris with nothing observing
# it — the exact invisibility that let eighteen tags pile up unnoticed. This
# gate is the independent observer: it reads the LIVE instance rather than
# trusting the cleanup code that is supposed to have run.
#
# THE RULE: no tag may begin with the lowercase-hyphen prefix `boba-`.
# Production tags are exactly `Boba` / `Боба` plus content-derived values
# (Movie, 1080p, 1994, Animation, ...). The `boba-` shape is reserved as a
# defect signature, and download-proxy/src/merge_service/tagging.py plus its
# unit test `test_no_generated_tag_uses_the_boba_hyphen_prefix` already forbid
# production code from emitting it. So any `boba-` tag in the live instance is
# debris by construction.
#
# HONEST SKIP (§11.4.3 / §11.4.69 `artifact_not_yet_built`): when qBittorrent
# is not running, this gate cannot observe anything. A stopped service is an
# environment condition, not a defect — it SKIPs with a reason and exit 0. It
# does NOT fail, because failing every build on a developer machine with the
# stack down would be a §11.4.201(1) false-positive refusal.
#
# BUT A REACHABLE-YET-UNREADABLE INSTANCE IS A HARNESS ERROR, not a clean tree:
# if login succeeds but the tag list cannot be parsed, that is a blind
# instrument and it exits 2 rather than reporting "no debris" (§11.4.201(6) —
# a blind reader and a clean instance return the identical quiet zero).
#
# Exit: 0 clean or honestly skipped | 1 debris present | 2 harness/blind error.

set -uo pipefail

QBT_HOST="${QBITTORRENT_HOST:-localhost}"
QBT_PORT="${QBITTORRENT_PORT:-7185}"
QBT_USER="${QBITTORRENT_USER:-admin}"
QBT_PASS="${QBITTORRENT_PASS:-admin}"
BASE="http://${QBT_HOST}:${QBT_PORT}"

if ! command -v curl >/dev/null 2>&1; then
    echo "CM-NO-TEST-TAG-DEBRIS: SKIP-with-reason=curl_absent (cannot probe)"
    exit 0
fi

JAR="$(mktemp)"
BODY="$(mktemp)"
trap 'rm -f "$JAR" "$BODY"' EXIT

# --- Reachability -----------------------------------------------------------
if ! curl -s -o /dev/null --max-time 5 "${BASE}/" 2>/dev/null; then
    echo "CM-NO-TEST-TAG-DEBRIS: SKIP-with-reason=service_not_running"
    echo "  qBittorrent is not reachable at ${BASE} — nothing to observe."
    echo "  This is an environment condition, not a defect. Start the stack with ./start.sh to enable this check."
    exit 0
fi

# --- Authenticate -----------------------------------------------------------
# NOTE: qBittorrent 5.x answers a successful login with HTTP 204 and an EMPTY
# body, setting cookie QBT_SID_<port>. Never gate on the legacy 200 "Ok.".
LOGIN_CODE=$(curl -s -o /dev/null -w '%{http_code}' -c "$JAR" \
    -H "Referer: ${BASE}" \
    --data-urlencode "username=${QBT_USER}" \
    --data-urlencode "password=${QBT_PASS}" \
    "${BASE}/api/v2/auth/login" 2>/dev/null || echo "000")

if ! grep -q 'QBT_SID' "$JAR" 2>/dev/null && [[ "$LOGIN_CODE" != "204" && "$LOGIN_CODE" != "200" ]]; then
    echo "CM-NO-TEST-TAG-DEBRIS: SKIP-with-reason=cannot_authenticate (HTTP ${LOGIN_CODE})"
    echo "  The service answered but credentials were refused, so the tag list cannot be read."
    echo "  Not reported as debris-free: an unread instance is not a clean instance."
    exit 0
fi

# --- Read the tag list ------------------------------------------------------
if ! curl -s --max-time 10 -b "$JAR" -H "Referer: ${BASE}" \
        "${BASE}/api/v2/torrents/tags" -o "$BODY" 2>/dev/null; then
    echo "HARNESS ERROR: authenticated but the tag list request failed — refusing to report a clean tree" >&2
    exit 2
fi

# The endpoint returns a JSON array. Anything else means we are not reading what
# we think we are reading (§11.4.201(9) — verify field identity before trusting).
if ! grep -qE '^\s*\[' "$BODY" 2>/dev/null; then
    echo "HARNESS ERROR: tag endpoint did not return a JSON array; got: $(head -c 120 "$BODY")" >&2
    exit 2
fi

# --- CONTROL NEEDLE (§11.4.201(7)(b)) ---------------------------------------
# A "no debris" result is a NULL, and a blind extractor returns the same quiet
# zero as a genuinely clean instance. Prove the extractor can see a tag of the
# forbidden shape through the SAME parsing path before trusting any zero.
NEEDLE_OUT=$(printf '["Boba","boba-bridge-go-deadbeef","1080p"]' \
    | tr ',' '\n' | tr -d '[]"' | grep -c '^boba-' || true)
if [[ "$NEEDLE_OUT" != "1" ]]; then
    echo "HARNESS ERROR: control needle not seen (expected 1 match, got ${NEEDLE_OUT}) — extractor is blind" >&2
    exit 2
fi

# --- Extract and judge ------------------------------------------------------
DEBRIS=$(tr ',' '\n' < "$BODY" | tr -d '[]"' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' \
    | grep '^boba-' || true)

if [[ -n "$DEBRIS" ]]; then
    COUNT=$(printf '%s\n' "$DEBRIS" | grep -c . || true)
    echo "CM-NO-TEST-TAG-DEBRIS: FAIL — ${COUNT} test-generated tag(s) present in the live instance"
    printf '%s\n' "$DEBRIS" | sed 's/^/    /'
    echo
    echo "  These are TEST DEBRIS, not a tagging scheme. Production tags are exactly"
    echo "  'Boba' / 'Боба' plus content-derived values; the lowercase 'boba-' prefix is"
    echo "  reserved as a defect signature and production code is forbidden from emitting it."
    echo
    echo "  Most likely cause: a test that creates tags stopped cleaning up after itself."
    echo "  See the _purge_suite_tags fixture in tests/integration/test_webui_bridge_auth_live.py."
    echo
    echo "  Remove them with (adjust the list):"
    echo "    curl -b <jar> -H 'Referer: ${BASE}' --data-urlencode 'tags=<comma,separated>' \\"
    echo "         ${BASE}/api/v2/torrents/deleteTags"
    exit 1
fi

TOTAL=$(tr ',' '\n' < "$BODY" | tr -d '[]"' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' | grep -c . || true)
echo "CM-NO-TEST-TAG-DEBRIS: PASS — no 'boba-' test debris among ${TOTAL} live tag(s)"
exit 0
