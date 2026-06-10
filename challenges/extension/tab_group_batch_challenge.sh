#!/usr/bin/env bash
#
# tab_group_batch_challenge.sh — BobaLink extension Phase 5 tab-group batch
# Challenge (Challenges / HelixQA; §11.4.83 captured-evidence, §11.4.69 feature
# class network_throughput).
#
# Purpose:
#   Drive the BobaLink browser extension's Phase 5 "send all torrents in this tab
#   group" flow end-to-end against the REAL, shipped extension modules (no
#   re-implementation), and PASS only on captured runtime evidence proving the
#   user-observable outcome: the SAME magnet appearing on two tabs of a group is
#   DEDUPED to one (cross-tab dedup), and the whole group is FORWARDED as a SINGLE
#   batched POST http://localhost:7187/api/v1/download with the exact body
#   {result_id, download_urls:[<the 2 unique magnets>]}.
#
# How it works:
#   Runs the challenge-scoped Vitest harness
#     challenges/extension/tab_group_batch.evidence.test.ts
#   via the extension's own Vitest. The harness imports the REAL
#     - src/tabgroups/index.ts  (batchGroupTorrents — cross-tab dedup;
#                                 dispatchGroupBatch — resolve URLs + send batch)
#     - src/api/boba-client.ts  (addMagnets — the one batched POST)
#     - src/parser/magnet.ts    (parseMagnetUri — real magnet identity)
#   builds a FAKE 3-tab group via the injected GroupBatchDeps (tab A: magnet-1;
#   tab B: magnet-1 DUPLICATE + magnet-2; tab C: empty), runs the dedup + batch,
#   captures the deduped unique set + the exact batched request body, and persists
#   them to
#     challenges/extension/.evidence/tab_group_batch.json
#   This script then RE-READS that evidence file and asserts on it independently,
#   so the verdict is backed by an auditable artefact — not the test exit code
#   alone.
#
# Inputs:   none (two synthetic public-domain Sintel-family CC-BY magnets; no
#           credentials, no private-tracker payload — §11.4.10).
# Outputs:  challenges/extension/.evidence/tab_group_batch.json (captured
#           evidence); a clear "PASS:" / "FAIL:" line; exit 0 on PASS, non-zero
#           otherwise.
# Side-effects: writes the evidence JSON; runs Vitest inside extension/.
# Dependencies: node + the extension's installed node_modules (Vitest); python3
#           (evidence assertions). If node_modules is absent, the run reports an
#           honest blocker (non-zero) — it never fakes a PASS.
# Cross-references:
#   - challenges/extension/tab_group_batch.evidence.test.ts (the harness)
#   - challenges/extension/detect_and_forward_challenge.sh  (sibling Challenge)
#   - extension/src/tabgroups/index.ts  (batchGroupTorrents / dispatchGroupBatch)
#   - submodules/helixqa/banks/boba-bobalink.yaml (BOBA-LINK-008 — same flow)
#
# Anti-bluff (§11.4 / §11.4.83): the harness drives the REAL modules; it asserts
# the USER-OBSERVABLE deduped batch payload (2 unique magnets in one POST), not a
# status code. Mutation self-check — if the cross-tab dedup were removed from
# batchGroupTorrents (the `seen` Set / `identityKey` guard), the duplicate
# magnet-1 on tab B would survive: the unique set would be 3 (not 2), the batched
# download_urls would carry magnet-1 TWICE, and BOTH the harness assertion
# (magnets.length === 2) AND the python re-assertion below (uniqueCount === 2,
# download_urls deduped) FAIL. So this is never a green-on-broken bluff. This
# script additionally re-validates the evidence file independently, so a stale or
# fabricated evidence file cannot mask a broken run.

set -euo pipefail

CHALLENGE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$CHALLENGE_DIR/../.." && pwd)"
EXT_DIR="$REPO_ROOT/extension"
SPEC="$CHALLENGE_DIR/tab_group_batch.evidence.test.ts"
EVIDENCE="$CHALLENGE_DIR/.evidence/tab_group_batch.json"
VITEST="$EXT_DIR/node_modules/.bin/vitest"

# Expected user-observable constants (mirrored from the harness + HelixQA bank).
EXPECT_INFOHASH_1="08ada5a7a6183aae1e09d831df6748d566095a10"
EXPECT_INFOHASH_2="deadbeef00112233445566778899aabbccddeeff"
EXPECT_ENDPOINT="http://localhost:7187/api/v1/download"

echo "=== tab_group_batch_challenge (BobaLink tab-group dedup → one batched POST) ==="

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
echo "Running real-module harness: $(basename "$SPEC") (vitest)…"
# Root at the repo so the harness can import both challenges/ and extension/src.
if ! ( cd "$EXT_DIR" && "$VITEST" run \
        --root "$REPO_ROOT" \
        --environment node \
        --globals \
        --no-coverage \
        "$SPEC" ) ; then
  echo "FAIL: the tab-group batch harness did not pass against the real modules"
  exit 1
fi

# --- Independently assert on the CAPTURED evidence ----------------------------
if [ ! -s "$EVIDENCE" ]; then
  echo "FAIL: no captured evidence written to $EVIDENCE"; exit 1
fi

echo "Asserting on captured evidence: $EVIDENCE"
EXPECT_INFOHASH_1="$EXPECT_INFOHASH_1" EXPECT_INFOHASH_2="$EXPECT_INFOHASH_2" \
EXPECT_ENDPOINT="$EXPECT_ENDPOINT" \
python3 - "$EVIDENCE" <<'PY'
import json, os, sys

path = sys.argv[1]
exp_ih1 = os.environ["EXPECT_INFOHASH_1"]
exp_ih2 = os.environ["EXPECT_INFOHASH_2"]
exp_endpoint = os.environ["EXPECT_ENDPOINT"]

with open(path, encoding="utf-8") as fh:
    ev = json.load(fh)

errors = []

if ev.get("pass") is not True:
    errors.append("evidence.pass is not true")

grp = ev.get("group", {})
# The group carried 3 raw torrent occurrences across its tabs (1 + 2 + 0).
if grp.get("rawOccurrenceCount") != 3:
    errors.append(
        f"expected 3 raw cross-tab occurrences, got {grp.get('rawOccurrenceCount')}"
    )

dedup = ev.get("dedup", {})
# Cross-tab dedup: the magnet-1 duplicate on two tabs collapses → 2 unique.
if dedup.get("uniqueCount") != 2:
    errors.append(f"expected exactly 2 deduped magnets, got {dedup.get('uniqueCount')}")
if dedup.get("uniqueInfohashes") != [exp_ih1, exp_ih2]:
    errors.append(
        f"deduped infohashes {dedup.get('uniqueInfohashes')!r} != "
        f"expected {[exp_ih1, exp_ih2]!r}"
    )
# Anti-bluff: if dedup were removed, the raw count (3) would equal the unique
# count — they MUST differ here (3 raw → 2 unique).
if grp.get("rawOccurrenceCount") == dedup.get("uniqueCount"):
    errors.append("raw occurrence count == unique count — cross-tab dedup did NOT happen")

fwd = ev.get("forward", {})
# The WHOLE group batched into exactly ONE POST.
if fwd.get("requestCount") != 1:
    errors.append(f"expected exactly 1 batched request, got {fwd.get('requestCount')}")
if fwd.get("url") != exp_endpoint:
    errors.append(f"forward URL {fwd.get('url')!r} != expected {exp_endpoint!r}")
if fwd.get("method") != "POST":
    errors.append(f"forward method {fwd.get('method')!r} != POST")
if fwd.get("sent") != 2:
    errors.append(f"expected sent=2, got {fwd.get('sent')}")
if fwd.get("skipped") != 0:
    errors.append(f"expected skipped=0, got {fwd.get('skipped')}")

body = fwd.get("requestBody", {})
if "result_id" not in body:
    errors.append("request body missing result_id")
urls = body.get("download_urls")
if not isinstance(urls, list) or len(urls) != 2:
    errors.append(f"download_urls is not a 2-element list: {urls!r}")
else:
    # The batched body carries the TWO UNIQUE magnets (one each), not the three
    # raw tab occurrences — proving the duplicate did NOT leak into the payload.
    if exp_ih1 not in urls[0]:
        errors.append(f"first batched magnet does not carry infohash-1: {urls[0]!r}")
    if exp_ih2 not in urls[1]:
        errors.append(f"second batched magnet does not carry infohash-2: {urls[1]!r}")
    if urls != list(dedup.get("uniqueUris", [])):
        errors.append("batched download_urls != the deduped unique magnet URIs (identity mismatch)")
    if urls[0] == urls[1]:
        errors.append("batched download_urls contains a duplicate — dedup leaked into the payload")

if errors:
    print("  EVIDENCE MISMATCH:")
    for e in errors:
        print(f"    - {e}")
    sys.exit(1)

print("  OK — cross-tab dedup:", grp.get("rawOccurrenceCount"), "raw →",
      dedup.get("uniqueCount"), "unique")
print("  OK — deduped infohashes:", dedup.get("uniqueInfohashes"))
print("  OK — one batched POST:", fwd.get("method"), fwd.get("url"))
print("  OK — body:", json.dumps(body, separators=(",", ":")))
PY
ASSERT_RC=$?

if [ "$ASSERT_RC" -ne 0 ]; then
  echo "FAIL: captured evidence did not match the expected user-observable outcome"
  exit 1
fi

echo "PASS: tab_group_batch_challenge — same magnet on 2 tabs deduped to 1, whole"
echo "      group forwarded as ONE POST $EXPECT_ENDPOINT"
echo "      {result_id, download_urls:[magnet-1, magnet-2]}"
echo "      evidence: $EVIDENCE"
exit 0
