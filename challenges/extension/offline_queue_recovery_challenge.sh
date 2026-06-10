#!/usr/bin/env bash
#
# offline_queue_recovery_challenge.sh — BobaLink extension offline-queue Challenge
# (Phase 8 — Challenges / HelixQA; §11.4.83 captured-evidence, §11.4.69
# feature class storage_write).
#
# Purpose:
#   Drive the BobaLink browser extension's offline-queue failure→recover→drain
#   path end-to-end against the REAL, shipped OfflineQueue module (no
#   re-implementation), and PASS only on captured runtime evidence proving the
#   user-observable outcome: when Boba is unreachable, N enqueued items PERSIST
#   to chrome.storage.local and DEAD-LETTER after the retry budget (nothing is
#   silently lost); when Boba comes back, the items are reset and DRAIN — the
#   working sender POSTs every one and the queue (and its persisted state) ends
#   empty.
#
# How it works:
#   Runs the challenge-scoped Vitest harness
#     challenges/extension/offline_queue_recovery.evidence.test.ts
#   via the extension's own Vitest (jsdom). The harness imports the REAL
#     - src/api/queue.ts                (OfflineQueue — enqueue/persist/retry/
#                                        dead-letter/drain/clear)
#     - tests/unit/chrome-fake.ts       (the SAME in-memory chrome.storage fake
#                                        the production storage suite uses)
#   wires them with an injected FAILING sender (throws) then a WORKING sender
#   (resolves true), reads the real persisted bytes back from the backing store,
#   and persists the captured counts to
#     challenges/extension/.evidence/offline_queue_recovery.json
#   This script then RE-READS that evidence file and asserts on it independently,
#   so the verdict is backed by an auditable artefact — not the test's exit code
#   alone.
#
# Inputs:   none (synthetic infohashes; no credentials, no private-tracker
#           payload — §11.4.10).
# Outputs:  challenges/extension/.evidence/offline_queue_recovery.json (captured
#           evidence); a clear "PASS:" / "FAIL:" line; exit 0 on PASS, non-zero
#           otherwise.
# Side-effects: writes the evidence JSON; runs Vitest inside extension/.
# Dependencies: node + the extension's installed node_modules (Vitest); python3
#           (evidence assertions). If node_modules is absent, the run reports an
#           honest blocker (non-zero) — it never fakes a PASS.
# Cross-references:
#   - challenges/extension/offline_queue_recovery.evidence.test.ts (the harness)
#   - extension/src/api/queue.ts (OfflineQueue — the real module under test)
#   - extension/tests/unit/api-queue.test.ts (the canonical real-module wiring)
#   - submodules/helixqa/banks/boba-bobalink.yaml (BOBA-LINK-010)
#
# Anti-bluff (§11.4 / §11.4.83): the harness drives the REAL OfflineQueue against
# the real chrome.storage fake; a no-op stub of the queue that silently drops
# items (no persist), never dead-letters, or never drains would make the harness
# FAIL and write no pass:true evidence — verified by the failure-vs-recovery
# count assertions. This script additionally re-validates the evidence file
# independently, so a stale or fabricated evidence file cannot mask a broken run.

set -euo pipefail

CHALLENGE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$CHALLENGE_DIR/../.." && pwd)"
EXT_DIR="$REPO_ROOT/extension"
SPEC="$CHALLENGE_DIR/offline_queue_recovery.evidence.test.ts"
EVIDENCE="$CHALLENGE_DIR/.evidence/offline_queue_recovery.json"
VITEST="$EXT_DIR/node_modules/.bin/vitest"

echo "=== offline_queue_recovery_challenge (BobaLink offline-queue fail→recover→drain) ==="

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

# --- Drive the REAL queue via the challenge-scoped Vitest harness --------------
echo "Running real-module harness: $(basename "$SPEC") (jsdom, vitest)…"
# Root at the repo so the harness can import both challenges/ and extension/src.
if ! ( cd "$EXT_DIR" && "$VITEST" run \
        --root "$REPO_ROOT" \
        --environment jsdom \
        --globals \
        --no-coverage \
        "$SPEC" ) ; then
  echo "FAIL: the offline-queue recovery harness did not pass against the real module"
  exit 1
fi

# --- Independently assert on the CAPTURED evidence ----------------------------
if [ ! -s "$EVIDENCE" ]; then
  echo "FAIL: no captured evidence written to $EVIDENCE"; exit 1
fi

echo "Asserting on captured evidence: $EVIDENCE"
python3 - "$EVIDENCE" <<'PY'
import json, sys

path = sys.argv[1]

with open(path, encoding="utf-8") as fh:
    ev = json.load(fh)

errors = []

if ev.get("pass") is not True:
    errors.append("evidence.pass is not true")

cfg = ev.get("config", {})
n = cfg.get("enqueued")
max_retries = cfg.get("maxRetries")
if not isinstance(n, int) or n < 1:
    errors.append(f"config.enqueued is not a positive int: {n!r}")
if not isinstance(max_retries, int) or max_retries < 1:
    errors.append(f"config.maxRetries is not a positive int: {max_retries!r}")

# FAILURE phase: items persisted across the failure window + all dead-lettered.
fp = ev.get("failurePhase", {})
if fp.get("failingSenderCalls", 0) < (n or 0):
    errors.append(
        f"failing sender called {fp.get('failingSenderCalls')} times, expected >= {n} "
        "(items were silently skipped, not really attempted)"
    )
if fp.get("persistedAfterEnqueue") != n:
    errors.append(f"persistedAfterEnqueue {fp.get('persistedAfterEnqueue')} != enqueued {n}")
if fp.get("persistedAfterFail") != n:
    errors.append(
        f"persistedAfterFail {fp.get('persistedAfterFail')} != {n} — items were LOST under failure"
    )
if fp.get("deadLetteredCount") != n:
    errors.append(f"deadLetteredCount {fp.get('deadLetteredCount')} != {n}")
if fp.get("allDeadLettered") is not True:
    errors.append("not every item reached the dead-letter state under the failing sender")
if fp.get("allReachedRetryBudget") is not True:
    errors.append("not every item reached the retry budget (attempts >= maxRetries)")

# RECOVERY phase: all items drained, queue + persisted state empty.
rp = ev.get("recoverPhase", {})
if rp.get("drainedCount") != n:
    errors.append(
        f"working sender drained {rp.get('drainedCount')} != {n} (not all items recovered)"
    )
if rp.get("succeeded") != n:
    errors.append(f"recoverPhase.succeeded {rp.get('succeeded')} != {n}")
if rp.get("failed") not in (0, None) and rp.get("failed") != 0:
    errors.append(f"recoverPhase.failed {rp.get('failed')} != 0")
if rp.get("queueSizeAfterDrain") != 0:
    errors.append(f"queue not empty after drain: size {rp.get('queueSizeAfterDrain')}")
if rp.get("persistedAfterDrain") != 0:
    errors.append(f"persisted state not empty after drain: {rp.get('persistedAfterDrain')}")

if errors:
    print("  EVIDENCE MISMATCH:")
    for e in errors:
        print(f"    - {e}")
    sys.exit(1)

print(f"  OK — failure: {n} items persisted + dead-lettered (attempts >= {max_retries}), none lost")
print(f"  OK — recovery: working sender drained all {n}, queue + persisted state empty")
PY
ASSERT_RC=$?

if [ "$ASSERT_RC" -ne 0 ]; then
  echo "FAIL: captured evidence did not match the expected user-observable outcome"
  exit 1
fi

echo "PASS: offline_queue_recovery_challenge — items persist + dead-letter under a"
echo "      failing sender (nothing lost), then drain completely under a working sender"
echo "      evidence: $EVIDENCE"
exit 0
