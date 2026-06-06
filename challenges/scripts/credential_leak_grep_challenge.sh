#!/usr/bin/env bash
# credential_leak_grep_challenge.sh — Layer 4 leak gate.
#
# EXPECT: TestNoCredentialLeak under the security build tag completes
# with "PASS" — all four leak channels (logs, response bodies,
# /proc/self/environ, DB hex) reject every seeded plaintext, AND wrong-
# key decryption fails for every row.
#
# CONST-XII anti-bluff: a no-op redactor would put plaintext into the
# captured log buffer; a stub Encrypt would leave plaintext in the DB
# file; either failure surfaces here as a Go test failure (non-zero
# exit), and this script forwards that exit code.
#
# Pass: PASS message + exit 0
# Fail: FAIL: <reason> + exit 1

set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT/qBitTorrent-go"

GOMAXPROCS=2 nice -n 19 $(command -v ionice &>/dev/null && echo "ionice -c 3" || true) \
  go test -tags=security -race -count=1 ./tests/security/ -run '^TestNoCredentialLeak$' -v \
  > /tmp/cred_leak_grep.out 2>&1
status=$?
echo "--- output (last 30 lines) ---"
tail -n 30 /tmp/cred_leak_grep.out
echo "--- end output ---"
if [ $status -ne 0 ]; then
  echo "FAIL: credential_leak_grep_challenge — Go test exited $status"
  exit 1
fi
if ! grep -q '^--- PASS: TestNoCredentialLeak' /tmp/cred_leak_grep.out; then
  echo "FAIL: credential_leak_grep_challenge — PASS line missing"
  exit 1
fi
echo "PASS: credential_leak_grep_challenge"
exit 0
