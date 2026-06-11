#!/usr/bin/env bash
#
# popup_journey_challenge.sh — BobaLink extension POPUP user-journey Challenge
# (Phase 8 — Challenges / HelixQA; §11.4.83 captured-evidence, §11.4.69
# feature class network_throughput).
#
# Purpose:
#   Drive the BobaLink browser extension's FULL popup user-journey end-to-end
#   against the REAL, shipped extension modules (no re-implementation), and PASS
#   only on captured runtime evidence proving the user-observable outcome:
#   detected torrents seeded into the REAL background are RENDERED as rows by the
#   REAL popup, clicking a row's REAL Send button drives the REAL background
#   client to POST http://localhost:7187/api/v1/download with that torrent's
#   magnet, and the clicked row FLIPS to "Sent" (the popup `r.id` contract fix).
#
# How it works:
#   Runs the challenge-scoped Vitest harness
#     challenges/extension/popup_journey.evidence.test.ts
#   via the extension's own Vitest (jsdom). The harness reuses the production
#   sendMessage→onMessage bridge pattern from
#     extension/tests/integration/popup-background.test.ts
#   to wire the REAL
#     - src/popup/popup.ts        (initPopup — query background, render, send)
#     - src/background/index.ts   (the message router + real BobaClient)
#     - src/api/boba-client.ts    (POST /api/v1/download)
#   over the REAL popup index.html DOM, and persists the captured rendered ids +
#   POST url/body + row-sent state to
#     challenges/extension/.evidence/popup_journey.json
#   This script then RE-READS that evidence file and asserts on it independently,
#   so the verdict is backed by an auditable artefact — not the test's exit code
#   alone.
#
# Inputs:   none (synthetic public-domain-class magnets; no credentials, no
#           private-tracker payload — §11.4.10).
# Outputs:  challenges/extension/.evidence/popup_journey.json (captured evidence);
#           a clear "PASS:" / "FAIL:" line; exit 0 on PASS, non-zero otherwise.
# Side-effects: writes the evidence JSON; runs Vitest inside extension/.
# Dependencies: node + the extension's installed node_modules (Vitest); python3
#           (evidence assertions). If node_modules is absent, the run reports an
#           honest blocker (non-zero) — it never fakes a PASS.
# Cross-references:
#   - challenges/extension/popup_journey.evidence.test.ts (the harness)
#   - extension/tests/integration/popup-background.test.ts (the real bridge pattern)
#   - extension/src/popup/popup.ts (initPopup — the module under test)
#   - submodules/helixqa/banks/boba-bobalink.yaml (BOBA-LINK-011)
#
# Anti-bluff (§11.4 / §11.4.83): the harness drives the REAL modules over the real
# router bridge; a no-op stub of the popup (renders nothing), the router (drops
# the click), or the client (never POSTs / wrong magnet) makes the harness FAIL
# and writes no pass:true evidence — verified by mutation. This script
# additionally re-validates the evidence file independently, so a stale or
# fabricated evidence file cannot mask a broken run.

set -euo pipefail

CHALLENGE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$CHALLENGE_DIR/../.." && pwd)"
EXT_DIR="$REPO_ROOT/extension"
SPEC="$CHALLENGE_DIR/popup_journey.evidence.test.ts"
EVIDENCE="$CHALLENGE_DIR/.evidence/popup_journey.json"
VITEST="$EXT_DIR/node_modules/.bin/vitest"

# Expected user-observable constants (mirrored from the harness + HelixQA bank).
EXPECT_ID_A="1234567890abcdef1234567890abcdef12345678"
EXPECT_ID_B="abcdef1234567890abcdef1234567890abcdef12"
EXPECT_ENDPOINT="http://localhost:7187/api/v1/download"

echo "=== popup_journey_challenge (BobaLink detect → render → send → row-sent) ==="

# --- Preconditions (honest blockers, never a faked PASS) ----------------------
if [ ! -f "$SPEC" ]; then
  echo "FAIL: challenge harness spec missing: $SPEC"; exit 1
fi
if ! command -v node >/dev/null 2>&1; then
  echo "FAIL: node not found on PATH (required to run the real extension modules)"; exit 1
fi
if [ ! -x "$VITEST" ]; then
  echo "FAIL: vitest not installed at $VITEST — run 'cd extension && npm install' first"; exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "FAIL: python3 not found on PATH (required to assert on the evidence JSON)"; exit 1
fi

# Start from a clean slate so we can never pass on a stale evidence file.
rm -f "$EVIDENCE"

# --- Drive the REAL popup journey via the challenge-scoped Vitest harness ------
echo "Running real-module harness: $(basename "$SPEC") (jsdom, vitest)…"
# Root at the repo so the harness can import both challenges/ and extension/src.
if ! ( cd "$EXT_DIR" && "$VITEST" run \
        --root "$REPO_ROOT" \
        --environment jsdom \
        --globals \
        --no-coverage \
        "$SPEC" ) ; then
  echo "FAIL: the popup user-journey harness did not pass against the real modules"
  exit 1
fi

# --- Independently assert on the CAPTURED evidence ----------------------------
if [ ! -s "$EVIDENCE" ]; then
  echo "FAIL: no captured evidence written to $EVIDENCE"; exit 1
fi

echo "Asserting on captured evidence: $EVIDENCE"
EXPECT_ID_A="$EXPECT_ID_A" EXPECT_ID_B="$EXPECT_ID_B" EXPECT_ENDPOINT="$EXPECT_ENDPOINT" \
python3 - "$EVIDENCE" <<'PY'
import json, os, sys

path = sys.argv[1]
exp_a = os.environ["EXPECT_ID_A"]
exp_b = os.environ["EXPECT_ID_B"]
exp_endpoint = os.environ["EXPECT_ENDPOINT"]

with open(path, encoding="utf-8") as fh:
    ev = json.load(fh)

errors = []

if ev.get("pass") is not True:
    errors.append("evidence.pass is not true")

det = ev.get("detect", {})
if det.get("seedAccepted") is not True:
    errors.append("background did not accept the seeded scan-result")

ren = ev.get("render", {})
if ren.get("renderedRowCount") != 2:
    errors.append(f"expected 2 rendered rows, got {ren.get('renderedRowCount')}")
if ren.get("renderedIds") != [exp_a, exp_b]:
    errors.append(f"rendered ids {ren.get('renderedIds')!r} != [{exp_a!r}, {exp_b!r}]")

snd = ev.get("send", {})
if snd.get("clickedId") != exp_b:
    errors.append(f"clicked id {snd.get('clickedId')!r} != {exp_b!r}")
if snd.get("requestCount") != 1:
    errors.append(f"expected exactly 1 download POST, got {snd.get('requestCount')}")
if snd.get("url") != exp_endpoint:
    errors.append(f"POST url {snd.get('url')!r} != {exp_endpoint!r}")
if snd.get("method") != "POST":
    errors.append(f"method {snd.get('method')!r} != POST")
urls = snd.get("downloadUrls")
if not isinstance(urls, list) or len(urls) != 1:
    errors.append(f"download_urls is not a single-element list: {urls!r}")
elif exp_b not in urls[0]:
    errors.append(f"sent magnet does not carry the clicked infohash {exp_b}: {urls[0]!r}")

row = ev.get("rowSent", {})
if row.get("sentRowId") != exp_b:
    errors.append(f"sent row id {row.get('sentRowId')!r} != clicked {exp_b!r}")
if row.get("sentRowHasSentClass") is not True:
    errors.append("clicked row did NOT flip to torrent-sent (the r.id contract fix)")
if row.get("sentButtonDisabled") is not True:
    errors.append("sent row's Send button was not disabled after send")
if row.get("otherRowStillUnsent") is not True:
    errors.append("the unclicked row was wrongly marked sent")

if errors:
    print("  EVIDENCE MISMATCH:")
    for e in errors:
        print(f"    - {e}")
    sys.exit(1)

print("  OK — rendered rows:", ren.get("renderedIds"))
print("  OK — sent:", snd.get("method"), snd.get("url"), snd.get("downloadUrls"))
print("  OK — row flipped to Sent:", row.get("sentRowId"))
PY
ASSERT_RC=$?

if [ "$ASSERT_RC" -ne 0 ]; then
  echo "FAIL: captured evidence did not match the expected user-observable outcome"
  exit 1
fi

echo "PASS: popup_journey_challenge — popup renders the detected rows, clicking Send"
echo "      POSTs the clicked magnet to $EXPECT_ENDPOINT, and the row flips to Sent"
echo "      evidence: $EVIDENCE"
exit 0
