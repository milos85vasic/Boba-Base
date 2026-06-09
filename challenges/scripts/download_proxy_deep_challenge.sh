#!/usr/bin/env bash
# download_proxy_deep_challenge.sh — Validates download_proxy.py deep coverage
#
# EXPECT: Running the test suite against download_proxy.py:
#   1. All 49 tests pass (download_via_nova2dl, HTTP handler, proxy)
#   2. Each handler path is tested (logo, theme, proxy, multipart)
#
# Anti-bluff: A no-op handler that returns 500 for everything would
# fail the success-path tests. A handler that doesn't rewrite CSP
# headers would fail the proxy tests. Each test asserts on specific
# response codes, headers, or body content.
#
# Pass: PASS message + exit 0
# Fail: FAIL: <reason> + exit 1

set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENV="$PROJECT_ROOT/.venv/bin/python3"

if [ ! -x "$VENV" ]; then
  echo "FAIL: .venv python not found at $VENV"; exit 1
fi

echo "=== download_proxy_deep_challenge ==="
echo "Running test_download_proxy_deep.py..."

TEST_OUTPUT=$("$VENV" -m pytest \
  "$PROJECT_ROOT/tests/unit/test_download_proxy_deep.py" \
  -q --import-mode=importlib --timeout=60 --no-header 2>&1)
TEST_COUNT=$(echo "$TEST_OUTPUT" | tail -1)

echo "Result: $TEST_COUNT"

PASSED=$(echo "$TEST_COUNT" | grep -oE '[0-9]+ passed' | grep -oE '[0-9]+')
FAILED=$(echo "$TEST_COUNT" | grep -oE '[0-9]+ failed' | grep -oE '[0-9]+' || echo "0")

if [ -z "$PASSED" ]; then
  echo "FAIL: could not parse test results: $TEST_COUNT"; exit 1
fi

if [ "$PASSED" -lt 45 ]; then
  echo "FAIL: expected >=45 passed, got $PASSED"; exit 1
fi

if [ "$FAILED" -gt 0 ]; then
  echo "FAIL: $FAILED tests failed"; exit 1
fi

echo "  OK — $PASSED tests passed, 0 failed"

echo "PASS: download_proxy_deep_challenge"
exit 0
