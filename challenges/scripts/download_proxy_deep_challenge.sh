#!/usr/bin/env bash
# download_proxy_deep_challenge.sh — Validates download_proxy.py deep coverage
#
# EXPECT: Running the test suite against download_proxy.py:
#   1. ZERO failures and ZERO errors — the real invariant.
#   2. Every collected test actually PASSES (passed == collected), so a test
#      that is silently skipped, deselected, or dies at collection cannot be
#      laundered into a green run.
#   3. Every load-bearing CAPABILITY of the proxy is still covered, asserted by
#      collected test-node id (not by a count).
#
# WHY NO NUMERIC FLOOR (§11.4.120 gate reconciliation, 2026-09-02)
# ----------------------------------------------------------------
# This gate previously asserted `PASSED -lt 45 -> FAIL`. On 2026-09-01 the
# themed-WebUI overlay was removed by operator mandate (theme_injector.py
# deleted; see CLAUDE.md "Plugin System"), which legitimately deleted the 18
# theme/logo/CSS/JS-serving tests and INVERTED three others
# (…csp_rewrite -> …csp_forwarded_verbatim, …injects_theme ->
# …passed_through_unmodified). The suite went 49 -> 31 and the floor was never
# reconciled, so a correct product change read as a gate FAIL — a §11.4.1
# FAIL-bluff.
#
# The lazy repair is `-lt 31`: it goes green today and rots again on the very
# next legitimate test add/remove, because a count is a PROXY for coverage, not
# coverage. It also cannot tell "18 tests deliberately removed with the feature"
# from "18 tests quietly deleted to make the suite pass" — the failure mode the
# floor was there to catch in the first place.
#
# So the floor is REPLACED, not lowered, by two assertions that cannot silently
# drift:
#   * passed == collected (derived from the suite AT RUN TIME — a legitimate
#     test change moves both numbers together and the gate stays honest);
#   * a named CAPABILITY ANCHOR set (below) that must appear among the COLLECTED
#     node ids. Deleting a capability's coverage now requires deliberately
#     editing this list — a visible, reviewable diff — instead of quietly
#     lowering an integer nobody re-derives.
#
# Anti-bluff: a no-op handler returning 500 for everything fails the
# success-path anchors. A handler that RE-INTRODUCED theme injection or CSP
# rewriting fails test_proxy_html_response_passed_through_unmodified /
# test_proxy_csp_forwarded_verbatim — the two anchors that encode the
# post-removal contract. Anchors are matched against pytest's own COLLECTED
# node ids, never against a grep of the source, so a test name appearing only
# in a comment or a docstring cannot satisfy this gate (§11.4.201(7)(a) —
# match the thing, not a token that mentions it).
#
# Pass: PASS message + exit 0
# Fail: FAIL: <reason> + exit 1

set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENV="$PROJECT_ROOT/.venv/bin/python3"
TEST_FILE="$PROJECT_ROOT/tests/unit/test_download_proxy_deep.py"

if [ ! -x "$VENV" ]; then
  echo "FAIL: .venv python not found at $VENV"; exit 1
fi
if [ ! -f "$TEST_FILE" ]; then
  echo "FAIL: test file not found at $TEST_FILE"; exit 1
fi

# CAPABILITY ANCHORS — one per load-bearing behaviour of download_proxy.py.
# Keep this list in step with the FEATURE SET, never with a test count.
CAPABILITY_ANCHORS=(
  # nova2dl download path (success + every documented failure mode)
  "TestDownloadViaNova2dl::test_success"
  "TestDownloadViaNova2dl::test_non_zero_returncode"
  "TestDownloadViaNova2dl::test_timeout"
  "TestDownloadViaNova2dl::test_file_not_found"
  # request dispatch / plugin interception
  "TestHandlerHandleRequest::test_plugin_intercept_success"
  "TestHandlerHandleRequest::test_plugin_intercept_download_fails"
  "TestHandlerHandleRequest::test_non_plugin_url_passthrough"
  "TestHandlerHandleRequest::test_exception_sends_500"
  # multipart / binary body handling
  "TestHandlerIsMultipart::test_multipart"
  "TestHandlerHandleRequest::test_multipart_passthrough"
  "TestHandlerHandleRequest::test_binary_body_passthrough"
  # TRANSPARENT proxy contract — the mechanism that REPLACED the themed overlay.
  # These two are the post-2026-09-01 invariant: relay upstream byte-for-byte,
  # forward qBittorrent's CSP untouched. Re-introducing injection breaks them.
  "TestHandlerProxyToQbittorrent::test_proxy_html_response_passed_through_unmodified"
  "TestHandlerProxyToQbittorrent::test_proxy_csp_forwarded_verbatim"
  "TestHandlerProxyToQbittorrent::test_proxy_rewrites_referer"
  "TestHandlerProxyToQbittorrent::test_proxy_http_error"
  # server bootstrap
  "TestRunServer::test_run_server_starts"
)

echo "=== download_proxy_deep_challenge ==="

# --- Step 1: what does pytest actually COLLECT? -------------------------------
# Collected node ids are the authoritative "these tests exist and will run"
# signal. Assigned on its own line so `set -e` sees the real exit status
# (a `local`/pipeline assignment would mask it — §11.4.201(12)).
COLLECT_OUT=""
if ! COLLECT_OUT="$("$VENV" -m pytest "$TEST_FILE" \
      --collect-only -q --import-mode=importlib --no-header 2>&1)"; then
  echo "FAIL: pytest collection failed:"
  printf '%s\n' "$COLLECT_OUT"
  exit 1
fi

COLLECTED_IDS="$(printf '%s\n' "$COLLECT_OUT" | grep -E '::test_' || true)"
COLLECTED=$(printf '%s' "$COLLECTED_IDS" | grep -c '::test_' || true)

if [ "$COLLECTED" -eq 0 ]; then
  echo "FAIL: pytest collected 0 tests from $TEST_FILE"
  echo "      (a collection that yields nothing is BLIND, never clean)"
  exit 1
fi
echo "Collected: $COLLECTED tests"

# --- Step 2: every capability anchor must be among the collected ids ----------
MISSING=()
for anchor in "${CAPABILITY_ANCHORS[@]}"; do
  if ! printf '%s\n' "$COLLECTED_IDS" | grep -qF "$anchor"; then
    MISSING+=("$anchor")
  fi
done

if [ "${#MISSING[@]}" -gt 0 ]; then
  echo "FAIL: ${#MISSING[@]} capability anchor(s) no longer collected:"
  for m in "${MISSING[@]}"; do echo "  - $m"; done
  echo
  echo "A capability lost its coverage. If the capability was REMOVED"
  echo "deliberately, delete its anchor from CAPABILITY_ANCHORS in this"
  echo "script IN THE SAME COMMIT as the removal, citing the mandate."
  exit 1
fi
echo "  OK — all ${#CAPABILITY_ANCHORS[@]} capability anchors collected"

# --- Step 3: run the suite ----------------------------------------------------
echo "Running test_download_proxy_deep.py..."
TEST_OUTPUT=""
TEST_RC=0
TEST_OUTPUT="$("$VENV" -m pytest "$TEST_FILE" \
  -q --import-mode=importlib --timeout=60 --no-header 2>&1)" || TEST_RC=$?

SUMMARY=$(printf '%s\n' "$TEST_OUTPUT" | tail -1)
echo "Result: $SUMMARY"

PASSED=$(printf '%s' "$SUMMARY" | grep -oE '[0-9]+ passed' | grep -oE '[0-9]+' || true)
FAILED=$(printf '%s' "$SUMMARY" | grep -oE '[0-9]+ failed' | grep -oE '[0-9]+' || echo "0")
ERRORS=$(printf '%s' "$SUMMARY" | grep -oE '[0-9]+ error' | grep -oE '[0-9]+' || echo "0")
SKIPPED=$(printf '%s' "$SUMMARY" | grep -oE '[0-9]+ skipped' | grep -oE '[0-9]+' || echo "0")
DESELECTED=$(printf '%s' "$SUMMARY" | grep -oE '[0-9]+ deselected' | grep -oE '[0-9]+' || echo "0")

if [ -z "$PASSED" ]; then
  echo "FAIL: could not parse test results: $SUMMARY"
  printf '%s\n' "$TEST_OUTPUT" | tail -20
  exit 1
fi

# --- Step 4: the real invariants ---------------------------------------------
if [ "$FAILED" -gt 0 ] || [ "$ERRORS" -gt 0 ]; then
  echo "FAIL: $FAILED failed, $ERRORS error(s)"
  printf '%s\n' "$TEST_OUTPUT" | tail -40
  exit 1
fi

if [ "$SKIPPED" -gt 0 ] || [ "$DESELECTED" -gt 0 ]; then
  echo "FAIL: $SKIPPED skipped / $DESELECTED deselected — every collected test"
  echo "      in this suite must RUN. A silent skip is not a pass."
  exit 1
fi

if [ "$PASSED" -ne "$COLLECTED" ]; then
  echo "FAIL: collected $COLLECTED but only $PASSED passed —"
  echo "      $((COLLECTED - PASSED)) collected test(s) did not report a pass"
  exit 1
fi

if [ "$TEST_RC" -ne 0 ]; then
  echo "FAIL: pytest exited $TEST_RC despite a clean summary line"
  exit 1
fi

echo "  OK — $PASSED/$COLLECTED passed, 0 failed, 0 error, 0 skipped"
echo "PASS: download_proxy_deep_challenge"
exit 0
