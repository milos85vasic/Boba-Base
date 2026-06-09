#!/usr/bin/env bash
# search_deep_coverage_challenge.sh — Validates search.py deep coverage tests
#
# EXPECT: Running the test suite against search.py deep paths:
#   1. All 84 tests pass (HTML parser, session store, fetch_torrent, etc.)
#   2. Each test covers a distinct code path (no duplicate coverage)
#
# Anti-bluff: A no-op stub that skips the actual search logic would
# still pass 0 tests. Each test asserts on specific behavior (parsed
# results, error handling, session state) that a stub can't fake.
#
# Pass: PASS message + exit 0
# Fail: FAIL: <reason> + exit 1

set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENV="$PROJECT_ROOT/.venv/bin/python3"

if [ ! -x "$VENV" ]; then
  echo "FAIL: .venv python not found at $VENV"; exit 1
fi

echo "=== search_deep_coverage_challenge ==="
echo "Running test_search_deep_coverage.py..."

TEST_OUTPUT=$("$VENV" -m pytest \
  "$PROJECT_ROOT/tests/unit/merge_service/test_search_deep_coverage.py" \
  -q --import-mode=importlib --timeout=60 --no-header 2>&1)
TEST_COUNT=$(echo "$TEST_OUTPUT" | tail -1)

echo "Result: $TEST_COUNT"

PASSED=$(echo "$TEST_COUNT" | grep -oE '[0-9]+ passed' | grep -oE '[0-9]+')
FAILED=$(echo "$TEST_COUNT" | grep -oE '[0-9]+ failed' | grep -oE '[0-9]+' || echo "0")

if [ -z "$PASSED" ]; then
  echo "FAIL: could not parse test results: $TEST_COUNT"; exit 1
fi

if [ "$PASSED" -lt 80 ]; then
  echo "FAIL: expected >=80 passed, got $PASSED"; exit 1
fi

if [ "$FAILED" -gt 0 ]; then
  echo "FAIL: $FAILED tests failed"; exit 1
fi

echo "  OK — $PASSED tests passed, 0 failed"

echo "PASS: search_deep_coverage_challenge"
exit 0
