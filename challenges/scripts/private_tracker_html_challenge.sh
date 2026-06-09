#!/usr/bin/env bash
# private_tracker_html_challenge.sh — Validates private tracker HTML parsing
#
# EXPECT: Running the HTML fixture tests:
#   1. All 25 tests pass (rutracker, kinozal, nnmclub, iptorrents parsers)
#   2. Each parser handles single-row, multi-row, entities, Cyrillic, freeleech
#   3. Edge cases (empty tables, negative seeds, zero size) are covered
#
# Anti-bluff: A no-op parser that returns [] for all input would fail
# the single-row and multi-row tests. A parser that doesn't unescape
# HTML entities would fail the entity tests. Each test asserts on
# specific parsed field values that prove the parser actually works.
#
# Pass: PASS message + exit 0
# Fail: FAIL: <reason> + exit 1

set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENV="$PROJECT_ROOT/.venv/bin/python3"

if [ ! -x "$VENV" ]; then
  echo "FAIL: .venv python not found at $VENV"; exit 1
fi

echo "=== private_tracker_html_challenge ==="
echo "Running test_private_tracker_html_fixtures.py..."

TEST_COUNT=$("$VENV" -m pytest \
  "$PROJECT_ROOT/tests/unit/merge_service/test_private_tracker_html_fixtures.py" \
  -q --import-mode=importlib --timeout=60 --no-header 2>&1 | tail -1)

echo "Result: $TEST_COUNT"

PASSED=$(echo "$TEST_COUNT" | grep -oE '[0-9]+ passed' | grep -oE '[0-9]+')
FAILED=$(echo "$TEST_COUNT" | grep -oE '[0-9]+ failed' | grep -oE '[0-9]+' || echo "0")

if [ -z "$PASSED" ]; then
  echo "FAIL: could not parse test results: $TEST_COUNT"; exit 1
fi

if [ "$PASSED" -lt 23 ]; then
  echo "FAIL: expected >=23 passed, got $PASSED"; exit 1
fi

if [ "$FAILED" -gt 0 ]; then
  echo "FAIL: $FAILED tests failed"; exit 1
fi

echo "  OK — $PASSED tests passed, 0 failed"

# Verify all 4 parsers are tested
for PARSER in rutracker kinozal nnmclub iptorrents; do
  PARSER_COUNT=$("$VENV" -m pytest \
    "$PROJECT_ROOT/tests/unit/merge_service/test_private_tracker_html_fixtures.py" \
    -k "$PARSER" -q --import-mode=importlib --timeout=60 --no-header 2>&1 | grep -oE '[0-9]+ passed' | grep -oE '[0-9]+')
  if [ -z "$PARSER_COUNT" ] || [ "$PARSER_COUNT" -lt 4 ]; then
    echo "FAIL: $PARSER parser has only $PARSER_COUNT tests (expected >=4)"; exit 1
  fi
  echo "  OK — $PARSER: $PARSER_COUNT tests"
done

echo "PASS: private_tracker_html_challenge"
exit 0
