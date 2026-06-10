#!/usr/bin/env bash
#
# detect_and_forward_challenge.sh — BobaLink extension end-to-end Challenge
# (Phase 8 — Challenges / HelixQA; §11.4.83 captured-evidence, §11.4.69
# feature class network_throughput).
#
# Purpose:
#   Drive the BobaLink browser extension's detection → payload pipeline
#   end-to-end against the REAL, shipped extension modules (no
#   re-implementation), and PASS only on captured runtime evidence proving the
#   user-observable outcome: a known magnet on a page is DETECTED with its exact
#   infohash, then FORWARDED as POST http://localhost:7187/api/v1/download with
#   the exact body {result_id, download_urls:[<magnet>]}.
#
# How it works:
#   Runs the challenge-scoped Vitest harness
#     challenges/extension/detect_and_forward.evidence.test.ts
#   via the extension's own Vitest (jsdom). The harness imports the REAL
#     - src/scanner/orchestrator.ts (+ committed Link/Text scanners, parser/magnet)
#     - src/api/boba-client.ts
#   wires them together over a known page fixture, and persists the captured
#   request body + detected infohash to
#     challenges/extension/.evidence/detect_and_forward.json
#   This script then RE-READS that evidence file and asserts on it independently,
#   so the verdict is backed by an auditable artefact — not the test's exit code
#   alone.
#
# Inputs:   none (synthetic public-domain Sintel CC-BY magnet; no credentials,
#           no private-tracker payload — §11.4.10).
# Outputs:  challenges/extension/.evidence/detect_and_forward.json (captured
#           evidence); a clear "PASS:" / "FAIL:" line; exit 0 on PASS, non-zero
#           otherwise.
# Side-effects: writes the evidence JSON; runs Vitest inside extension/.
# Dependencies: node + the extension's installed node_modules (Vitest); python3
#           (evidence assertions). If node_modules is absent, the run reports an
#           honest blocker (non-zero) — it never fakes a PASS.
# Cross-references:
#   - challenges/extension/detect_and_forward.evidence.test.ts (the harness)
#   - extension/tests/integration/pipeline.test.ts (the canonical real-module wiring)
#   - submodules/helixqa/banks/boba-bobalink.yaml (BOBA-LINK-003 — same magnet)
#   - docs/browser_extension/IMPLEMENTATION_PLAN.md (Phase 8 — T8.3/T8.4)
#
# Anti-bluff (§11.4 / §11.4.83): the harness drives the REAL modules; a no-op
# stub of the orchestrator (returns []) or the client (never POSTs / wrong URL /
# wrong body) makes the harness FAIL and writes no pass:true evidence — verified
# by mutation. This script additionally re-validates the evidence file
# independently, so a stale or fabricated evidence file cannot mask a broken run.

set -euo pipefail

CHALLENGE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$CHALLENGE_DIR/../.." && pwd)"
EXT_DIR="$REPO_ROOT/extension"
SPEC="$CHALLENGE_DIR/detect_and_forward.evidence.test.ts"
EVIDENCE="$CHALLENGE_DIR/.evidence/detect_and_forward.json"
VITEST="$EXT_DIR/node_modules/.bin/vitest"

# Expected user-observable constants (mirrored from the harness + HelixQA bank).
EXPECT_INFOHASH="08ada5a7a6183aae1e09d831df6748d566095a10"
EXPECT_ENDPOINT="http://localhost:7187/api/v1/download"

echo "=== detect_and_forward_challenge (BobaLink detect → forward) ==="

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

# --- Drive the REAL pipeline via the challenge-scoped Vitest harness -----------
echo "Running real-module harness: $(basename "$SPEC") (jsdom, vitest)…"
# Root at the repo so the harness can import both challenges/ and extension/src.
if ! ( cd "$EXT_DIR" && "$VITEST" run \
        --root "$REPO_ROOT" \
        --environment jsdom \
        --globals \
        --no-coverage \
        "$SPEC" ) ; then
  echo "FAIL: the detect→forward harness did not pass against the real modules"
  exit 1
fi

# --- Independently assert on the CAPTURED evidence ----------------------------
if [ ! -s "$EVIDENCE" ]; then
  echo "FAIL: no captured evidence written to $EVIDENCE"; exit 1
fi

echo "Asserting on captured evidence: $EVIDENCE"
EXPECT_INFOHASH="$EXPECT_INFOHASH" EXPECT_ENDPOINT="$EXPECT_ENDPOINT" \
python3 - "$EVIDENCE" <<'PY'
import json, os, sys

path = sys.argv[1]
exp_infohash = os.environ["EXPECT_INFOHASH"]
exp_endpoint = os.environ["EXPECT_ENDPOINT"]

with open(path, encoding="utf-8") as fh:
    ev = json.load(fh)

errors = []

if ev.get("pass") is not True:
    errors.append("evidence.pass is not true")

det = ev.get("detection", {})
if det.get("magnetCount") != 1:
    errors.append(f"expected exactly 1 deduped magnet, got {det.get('magnetCount')}")
if det.get("detectedInfohash") != exp_infohash:
    errors.append(
        f"detected infohash {det.get('detectedInfohash')!r} != expected {exp_infohash!r}"
    )

fwd = ev.get("forward", {})
if fwd.get("requestCount") != 1:
    errors.append(f"expected exactly 1 forwarded request, got {fwd.get('requestCount')}")
if fwd.get("url") != exp_endpoint:
    errors.append(f"forward URL {fwd.get('url')!r} != expected {exp_endpoint!r}")
if fwd.get("method") != "POST":
    errors.append(f"forward method {fwd.get('method')!r} != POST")

body = fwd.get("requestBody", {})
if "result_id" not in body:
    errors.append("request body missing result_id")
urls = body.get("download_urls")
if not isinstance(urls, list) or len(urls) != 1:
    errors.append(f"download_urls is not a single-element list: {urls!r}")
else:
    if exp_infohash not in urls[0]:
        errors.append(f"forwarded magnet does not carry detected infohash: {urls[0]!r}")
    if urls[0] != det.get("detectedUri"):
        errors.append("forwarded magnet != the detected magnet URI (identity mismatch)")

if errors:
    print("  EVIDENCE MISMATCH:")
    for e in errors:
        print(f"    - {e}")
    sys.exit(1)

print("  OK — detected infohash:", det.get("detectedInfohash"))
print("  OK — forwarded:", fwd.get("method"), fwd.get("url"))
print("  OK — body:", json.dumps(body, separators=(",", ":")))
PY
ASSERT_RC=$?

if [ "$ASSERT_RC" -ne 0 ]; then
  echo "FAIL: captured evidence did not match the expected user-observable outcome"
  exit 1
fi

echo "PASS: detect_and_forward_challenge — magnet detected with exact infohash and"
echo "      forwarded as POST $EXPECT_ENDPOINT {result_id, download_urls:[magnet]}"
echo "      evidence: $EVIDENCE"
exit 0
