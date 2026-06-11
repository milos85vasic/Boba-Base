#!/usr/bin/env bash
#
# options_config_challenge.sh — BobaLink extension OPTIONS config round-trip
# Challenge (Phase 8 — Challenges / HelixQA; §11.4.83 captured-evidence,
# §11.4.69 feature class storage_write).
#
# Purpose:
#   Drive the BobaLink browser extension's OPTIONS save/load round-trip
#   end-to-end against the REAL, shipped extension modules (no re-implementation),
#   and PASS only on captured runtime evidence proving the user-observable
#   outcome: the REAL options page loads the built-in default server URL into the
#   form, the user edits + SAVES a new server URL/name/health-interval, and the
#   REAL background `get-config` handler reads back the SAME config from the SAME
#   chrome.storage — field-for-field identical (a genuine persist→read-back, not a
#   shared in-memory object).
#
# How it works:
#   Runs the challenge-scoped Vitest harness
#     challenges/extension/options_config.evidence.test.ts
#   via the extension's own Vitest (jsdom). The harness reuses the production
#   sendMessage→onMessage bridge pattern from
#     extension/tests/integration/popup-background.test.ts
#   to wire the REAL
#     - src/options/options.ts    (initOptions / saveOptions — load + persist)
#     - src/background/index.ts    (the message router — get-config reader)
#     - src/shared/storage.ts      (the committed chrome.storage.local layer)
#   over the REAL options index.html DOM, and persists the captured default value
#   + saved vs read-back fields to
#     challenges/extension/.evidence/options_config.json
#   This script then RE-READS that evidence file and asserts on it independently,
#   so the verdict is backed by an auditable artefact — not the test's exit code
#   alone.
#
# Inputs:   none (synthetic config values; no credentials, no secret — §11.4.10).
# Outputs:  challenges/extension/.evidence/options_config.json (captured evidence);
#           a clear "PASS:" / "FAIL:" line; exit 0 on PASS, non-zero otherwise.
# Side-effects: writes the evidence JSON; runs Vitest inside extension/.
# Dependencies: node + the extension's installed node_modules (Vitest); python3
#           (evidence assertions). If node_modules is absent, the run reports an
#           honest blocker (non-zero) — it never fakes a PASS.
# Cross-references:
#   - challenges/extension/options_config.evidence.test.ts (the harness)
#   - extension/tests/integration/popup-background.test.ts (the real bridge pattern)
#   - extension/src/options/options.ts (initOptions/saveOptions — modules under test)
#   - submodules/helixqa/banks/boba-bobalink.yaml (BOBA-LINK-012)
#
# Anti-bluff (§11.4 / §11.4.83): the harness drives the REAL modules; the options
# writer and the background reader hit the SAME chrome.storage fake, so the
# round-trip is genuine persistence. A no-op stub of saveOptions (never persists)
# or get-config (returns canned/empty) makes the read-back diverge from the saved
# config and the harness FAILs — verified by mutation. This script additionally
# re-validates the evidence file independently, so a stale or fabricated evidence
# file cannot mask a broken run.

set -euo pipefail

CHALLENGE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$CHALLENGE_DIR/../.." && pwd)"
EXT_DIR="$REPO_ROOT/extension"
SPEC="$CHALLENGE_DIR/options_config.evidence.test.ts"
EVIDENCE="$CHALLENGE_DIR/.evidence/options_config.json"
VITEST="$EXT_DIR/node_modules/.bin/vitest"

# Expected user-observable constants (mirrored from the harness + HelixQA bank).
EXPECT_DEFAULT_URL="http://localhost:7187"
EXPECT_NEW_URL="http://192.168.1.50:7187"
EXPECT_NEW_NAME="Home Boba"
EXPECT_HEALTH_INTERVAL="9"

echo "=== options_config_challenge (BobaLink options load-default → save → read-back) ==="

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

# --- Drive the REAL options round-trip via the challenge-scoped Vitest harness -
echo "Running real-module harness: $(basename "$SPEC") (jsdom, vitest)…"
# Root at the repo so the harness can import both challenges/ and extension/src.
if ! ( cd "$EXT_DIR" && "$VITEST" run \
        --root "$REPO_ROOT" \
        --environment jsdom \
        --globals \
        --no-coverage \
        "$SPEC" ) ; then
  echo "FAIL: the options config round-trip harness did not pass against the real modules"
  exit 1
fi

# --- Independently assert on the CAPTURED evidence ----------------------------
if [ ! -s "$EVIDENCE" ]; then
  echo "FAIL: no captured evidence written to $EVIDENCE"; exit 1
fi

echo "Asserting on captured evidence: $EVIDENCE"
EXPECT_DEFAULT_URL="$EXPECT_DEFAULT_URL" EXPECT_NEW_URL="$EXPECT_NEW_URL" \
EXPECT_NEW_NAME="$EXPECT_NEW_NAME" EXPECT_HEALTH_INTERVAL="$EXPECT_HEALTH_INTERVAL" \
python3 - "$EVIDENCE" <<'PY'
import json, os, sys

path = sys.argv[1]
exp_default = os.environ["EXPECT_DEFAULT_URL"]
exp_url = os.environ["EXPECT_NEW_URL"]
exp_name = os.environ["EXPECT_NEW_NAME"]
exp_health = int(os.environ["EXPECT_HEALTH_INTERVAL"])

with open(path, encoding="utf-8") as fh:
    ev = json.load(fh)

errors = []

if ev.get("pass") is not True:
    errors.append("evidence.pass is not true")

ld = ev.get("load", {})
if ld.get("storeEmptyBeforeLoad") is not True:
    errors.append("store was not empty before load (default-load not exercised)")
if ld.get("loadedDefaultUrl") != exp_default:
    errors.append(f"loaded default url {ld.get('loadedDefaultUrl')!r} != {exp_default!r}")

sv = ev.get("save", {})
if sv.get("persisted") is not True:
    errors.append("config was not persisted to storage after save")
if sv.get("savedServerUrl") != exp_url:
    errors.append(f"saved server url {sv.get('savedServerUrl')!r} != {exp_url!r}")
if sv.get("savedServerName") != exp_name:
    errors.append(f"saved server name {sv.get('savedServerName')!r} != {exp_name!r}")
if sv.get("savedHealthInterval") != exp_health:
    errors.append(f"saved health interval {sv.get('savedHealthInterval')!r} != {exp_health}")

rt = ev.get("roundTrip", {})
if rt.get("backgroundSuccess") is not True:
    errors.append("background get-config did not succeed")
if rt.get("readServerUrl") != exp_url:
    errors.append(f"read-back url {rt.get('readServerUrl')!r} != saved {exp_url!r}")
if rt.get("readServerName") != exp_name:
    errors.append(f"read-back name {rt.get('readServerName')!r} != saved {exp_name!r}")
if rt.get("readHealthInterval") != exp_health:
    errors.append(f"read-back health interval {rt.get('readHealthInterval')!r} != {exp_health}")
# Field-for-field identity between what was saved and what the background read.
for flag in ("urlMatches", "nameMatches", "idMatches",
             "healthIntervalMatches", "activeServerMatches"):
    if rt.get(flag) is not True:
        errors.append(f"round-trip identity check failed: {flag} is not true")

if errors:
    print("  EVIDENCE MISMATCH:")
    for e in errors:
        print(f"    - {e}")
    sys.exit(1)

print("  OK — loaded default url:", ld.get("loadedDefaultUrl"))
print("  OK — saved url/name:", sv.get("savedServerUrl"), "/", sv.get("savedServerName"))
print("  OK — background read-back identical (url/name/id/health/active)")
PY
ASSERT_RC=$?

if [ "$ASSERT_RC" -ne 0 ]; then
  echo "FAIL: captured evidence did not match the expected user-observable outcome"
  exit 1
fi

echo "PASS: options_config_challenge — options loads the default, persists the edited"
echo "      config, and the background reads back the SAME config field-for-field"
echo "      evidence: $EVIDENCE"
exit 0
