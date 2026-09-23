#!/usr/bin/env bash
# check_cm_sse_route_rate_limit_classed.sh — CM-SSE-ROUTE-RATE-LIMIT-CLASSED
# static pre-build gate (BOB-167 / §11.4.135 permanent regression guard).
#
# Purpose:
#   Enumerate every FastAPI route in the merge service whose response is
#   SSE-shaped (a long-lived Server-Sent-Events connection that pins a
#   worker + a generator for the connection's lifetime) and FAIL the build
#   if any such route carries no explicit rate-limit class.
#
# FORENSIC ANCHOR (BOB-167):
#   `download-proxy/src/api/routes.py` exposed two SSE-shaped routes —
#   `GET /theme/stream` and `GET /search/stream/{search_id}` — but only
#   `/search/stream` carried `@_rl("sse_stream")`. `/theme/stream` silently
#   fell through to the application's looser `default` rate-limit class
#   (measured: 120/minute instead of the sse_stream class), even though it
#   holds the exact same resource shape (long-lived connection + generator
#   + worker) the sse_stream class exists to bound.
#
# WHY THIS IS THE GENERAL FORM, NOT THE ONE-OFF FIX:
#   Adding `@_rl("sse_stream")` to `/theme/stream` closes TODAY's gap. It
#   does nothing to stop a THIRD SSE-shaped route from landing tomorrow
#   with the same silent omission — nothing forces a route author to
#   remember the classification rule. This gate enumerates the ROUTE SHAPE
#   (SSE) and asserts the PROPERTY (an explicit class) on every member of
#   that shape, so the gap this fix closes today cannot recur unnoticed.
#
# DETECTION ENGINE:
#   The DETECTION LOGIC lives in the sibling Python module
#   `sse_route_rate_limit_class_analyzer.py`, which parses the target file
#   with `ast` (never a text grep — see that module's own docstring for the
#   full §11.4.201 rationale: it recognises BOTH established SSE-response
#   idioms in this codebase, a direct `StreamingResponse(...,
#   media_type="text/event-stream")` call and a call to the shared
#   `SSEHandler.create_streaming_response(...)` helper, and BOTH
#   established rate-limit-classing idioms, the `@_rl("<class>")`
#   decorator and a `Depends(rate_limit_dependency("<class>"))`
#   dependency). This wrapper is a thin argument/exit-code adapter; it
#   contains no detection logic of its own so it cannot drift from the
#   engine (§11.4.177 discipline, applied to a same-repo sibling file
#   rather than the constitution submodule — this check is boba-specific
#   route-shape knowledge, not a universal anchor).
#
# Usage:
#   check_cm_sse_route_rate_limit_classed.sh [FILE]
#   check_cm_sse_route_rate_limit_classed.sh --help
#
# Inputs:   optional FILE argument (default: download-proxy/src/api/routes.py
#           relative to the repo root). No stdin, no environment input.
# Outputs:  per-route resolution + verdict on stdout; findings on stderr.
# Side-effects: none (read-only static analysis).
# Dependencies: bash, python3 (standard library `ast` only — no third-party
#           import, so this runs on the bare host interpreter, not only
#           inside a container venv).
#
# Verdict:
#   0 — PASS  every SSE-shaped route resolved carries an explicit class.
#   1 — FAIL  one or more SSE-shaped routes carry no explicit class.
#   2 — ERROR usage error, missing/unparsable file, missing python3, or
#       ZERO SSE-shaped routes resolved — refused as a BLIND instrument
#       rather than an unverified PASS (§11.4.201(6): a blind extractor and
#       a genuinely SSE-route-free file return the identical quiet zero,
#       and this project has at least two SSE-shaped routes today, so a
#       zero here is a signal the extractor broke, not that the file is
#       clean).
#
# Cross-references: §1.1 §11.4.6 §11.4.69 §11.4.107(10) §11.4.115
#   §11.4.135 §11.4.177 §11.4.196(F) §11.4.201 §11.4.226 §11.4.238.
#   Sibling engine: scripts/pre_build/sse_route_rate_limit_class_analyzer.py
#   Paired-mutation + golden-FALSE evidence:
#   tests/unit/api_layer/test_bob167_sse_route_rate_limit_gate.py

set -euo pipefail

SCRIPT_NAME="check_cm_sse_route_rate_limit_classed"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ENGINE="$SCRIPT_DIR/sse_route_rate_limit_class_analyzer.py"

print_help() { sed -n '2,64p' "${BASH_SOURCE[0]}"; }

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  print_help
  exit 0
fi

FILE="${1:-$REPO_ROOT/download-proxy/src/api/routes.py}"

if [[ ! -f "$ENGINE" ]]; then
  echo "ERROR($SCRIPT_NAME): detection engine not found: $ENGINE" >&2
  exit 2
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR($SCRIPT_NAME): python3 not on PATH — cannot resolve routes." >&2
  echo "  Refusing rather than reporting an unverified PASS (§11.4.201(4))." >&2
  exit 2
fi

rc=0
python3 "$ENGINE" --file "$FILE" || rc=$?
exit "$rc"
