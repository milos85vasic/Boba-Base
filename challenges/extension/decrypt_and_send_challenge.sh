#!/usr/bin/env bash
#
# decrypt_and_send_challenge.sh — BobaLink extension decrypt-before-send Challenge
# (Phase 8 — Challenges / HelixQA; §11.4.83 captured-evidence, §11.4.69
# feature class network_throughput; §11.4.10 credentials handling).
#
# Purpose:
#   Drive the BobaLink browser extension's decrypt-before-send token path
#   end-to-end against the REAL, shipped extension modules (no re-implementation),
#   and PASS only on captured runtime evidence proving the user-observable
#   outcome: a SYNTHETIC token encrypted to an EncryptedBundle by the REAL
#   `encrypt` is DECRYPTED by the REAL `BobaClient.create` and the resulting
#   PLAINTEXT — NOT the ciphertext — is what travels on the wire as
#   `Authorization: Bearer <plaintext>` (+ `X-Boba-Token`). The NEGATIVE half
#   proves the default-open contract: with NO passphrase, NO auth header is sent.
#
# How it works:
#   Runs the challenge-scoped Vitest harness
#     challenges/extension/decrypt_and_send.evidence.test.ts
#   via the extension's own Vitest (jsdom; Node's Web Crypto powers AES-GCM).
#   The harness imports the REAL
#     - src/shared/crypto.ts   (encrypt / decrypt)
#     - src/api/boba-client.ts (BobaClient.create — the decrypt-and-send factory)
#   wires them with an injected capturing fetch, and persists the captured wire
#   evidence (header fingerprints + booleans — NEVER the plaintext, §11.4.10) to
#     challenges/extension/.evidence/decrypt_and_send.json
#   This script then RE-READS that evidence file and asserts on it independently,
#   so the verdict is backed by an auditable artefact — not the test's exit code
#   alone.
#
# Inputs:   none (a SYNTHETIC, in-process token + passphrase; no credentials,
#           no private-tracker payload — §11.4.10). The token plaintext is never
#           logged and never written to the evidence file.
# Outputs:  challenges/extension/.evidence/decrypt_and_send.json (captured
#           evidence); a clear "PASS:" / "FAIL:" line; exit 0 on PASS, non-zero
#           otherwise.
# Side-effects: writes the evidence JSON; runs Vitest inside extension/.
# Dependencies: node + the extension's installed node_modules (Vitest); python3
#           (evidence assertions). If node_modules is absent, the run reports an
#           honest blocker (non-zero) — it never fakes a PASS.
# Cross-references:
#   - challenges/extension/decrypt_and_send.evidence.test.ts (the harness)
#   - extension/src/api/boba-client.ts (BobaClient.create — decrypt-and-send)
#   - extension/src/shared/crypto.ts (encrypt / decrypt — AES-256-GCM / PBKDF2)
#   - extension/tests/unit/background-token.test.ts (real-module token wiring)
#   - submodules/helixqa/banks/boba-bobalink.yaml (BOBA-LINK-009)
#
# Anti-bluff (§11.4 / §11.4.83 / §11.4.10): the harness drives the REAL modules;
# a no-op stub of BobaClient.create that "forgot" to decrypt and sent the
# ciphertext on the wire would make the harness FAIL (the captured Authorization
# header would carry the bundle ciphertext, never the plaintext) and write no
# pass:true evidence — the mutation self-check. This script additionally
# re-validates the evidence file independently, so a stale or fabricated
# evidence file cannot mask a broken run.

set -euo pipefail

CHALLENGE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$CHALLENGE_DIR/../.." && pwd)"
EXT_DIR="$REPO_ROOT/extension"
SPEC="$CHALLENGE_DIR/decrypt_and_send.evidence.test.ts"
EVIDENCE="$CHALLENGE_DIR/.evidence/decrypt_and_send.json"
VITEST="$EXT_DIR/node_modules/.bin/vitest"

# Expected user-observable constants (mirrored from the harness + HelixQA bank).
EXPECT_ENDPOINT="http://localhost:7187/api/v1/download"

echo "=== decrypt_and_send_challenge (BobaLink decrypt-before-send token path) ==="

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

# --- Drive the REAL path via the challenge-scoped Vitest harness ---------------
echo "Running real-module harness: $(basename "$SPEC") (jsdom, vitest)…"
# Root at the repo so the harness can import both challenges/ and extension/src.
if ! ( cd "$EXT_DIR" && "$VITEST" run \
        --root "$REPO_ROOT" \
        --environment jsdom \
        --globals \
        --no-coverage \
        "$SPEC" ) ; then
  echo "FAIL: the decrypt→send harness did not pass against the real modules"
  exit 1
fi

# --- Independently assert on the CAPTURED evidence ----------------------------
if [ ! -s "$EVIDENCE" ]; then
  echo "FAIL: no captured evidence written to $EVIDENCE"; exit 1
fi

echo "Asserting on captured evidence: $EVIDENCE"
EXPECT_ENDPOINT="$EXPECT_ENDPOINT" \
python3 - "$EVIDENCE" <<'PY'
import json, os, sys

path = sys.argv[1]
exp_endpoint = os.environ["EXPECT_ENDPOINT"]

with open(path, encoding="utf-8") as fh:
    ev = json.load(fh)

errors = []

if ev.get("pass") is not True:
    errors.append("evidence.pass is not true")

das = ev.get("decryptAndSend", {})
if das.get("url") != exp_endpoint:
    errors.append(f"forward URL {das.get('url')!r} != expected {exp_endpoint!r}")
if das.get("method") != "POST":
    errors.append(f"forward method {das.get('method')!r} != POST")

# The wire MUST carry the DECRYPTED plaintext (Bearer <plaintext>) …
if das.get("authHeaderEqualsPlaintextBearer") is not True:
    errors.append("Authorization header did NOT equal 'Bearer <decrypted-plaintext>'")
if das.get("xBobaTokenEqualsPlaintext") is not True:
    errors.append("X-Boba-Token did NOT equal the decrypted plaintext")
# …confirmed by fingerprint match (sha256 of the captured header == expected).
if das.get("authHeaderSha256") != das.get("expectedAuthHeaderSha256"):
    errors.append("Authorization-header sha256 did not match sha256('Bearer '+plaintext)")

# …and MUST NOT carry the ciphertext, the JSON bundle, or the passphrase.
if das.get("authHeaderContainsCiphertext") is not False:
    errors.append("CIPHERTEXT leaked onto the wire — decrypt was skipped (bluff)")
if das.get("authHeaderContainsBundle") is not False:
    errors.append("the encrypted bundle leaked onto the wire")
if das.get("authHeaderContainsPassphrase") is not False:
    errors.append("the passphrase leaked onto the wire")

# Fingerprints must differ (real encryption made ciphertext != plaintext).
fp = ev.get("fingerprints", {})
if fp.get("tokenSha256") and fp.get("tokenSha256") == fp.get("ciphertextSha256"):
    errors.append("token and ciphertext fingerprints are identical — encryption was a no-op")

# NEGATIVE: no passphrase ⇒ default-open, NO auth header.
neg = ev.get("negativeNoPassphrase", {})
if neg.get("hasAuthHeader") is not False:
    errors.append("default-open broken: an Authorization header was sent without a passphrase")
if neg.get("hasXBobaHeader") is not False:
    errors.append("default-open broken: an X-Boba-Token header was sent without a passphrase")

if errors:
    print("  EVIDENCE MISMATCH:")
    for e in errors:
        print(f"    - {e}")
    sys.exit(1)

print("  OK — decrypted plaintext sent as Bearer (fingerprint match), ciphertext NOT on wire")
print("  OK — forward:", das.get("method"), das.get("url"))
print("  OK — negative: no passphrase ⇒ no auth header (default-open)")
PY
ASSERT_RC=$?

if [ "$ASSERT_RC" -ne 0 ]; then
  echo "FAIL: captured evidence did not match the expected user-observable outcome"
  exit 1
fi

echo "PASS: decrypt_and_send_challenge — the encrypted token is DECRYPTED and the"
echo "      plaintext (not the ciphertext) is sent as Authorization: Bearer <token>"
echo "      to POST $EXPECT_ENDPOINT; no passphrase ⇒ no auth header (default-open)"
echo "      evidence: $EVIDENCE"
exit 0
