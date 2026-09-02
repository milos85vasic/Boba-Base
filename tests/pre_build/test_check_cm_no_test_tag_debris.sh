#!/usr/bin/env bash
# test_check_cm_no_test_tag_debris.sh — §1.1 paired-mutation meta-test for
# scripts/pre_build/check_cm_no_test_tag_debris.sh (CM-NO-TEST-TAG-DEBRIS).
#
# WHY THIS DRIVES THE REAL GATE (§11.4.249): this harness EXECUTES the gate
# and reads its exit code. It does not re-declare the gate's own patterns — a
# harness that reproduces the detector inside itself is a producer=oracle
# collapse and cannot see the gate drift.
#
# WHAT IS ALREADY PROVEN LIVE, AND THEREFORE NOT REPEATED HERE:
#   * clean live instance          -> exit 0
#   * a planted `boba-bridge-go-deadbeef` tag -> exit 1, naming the tag
#   * that tag removed             -> exit 0 again
# That live RED->GREEN was captured on 2026-09-01 against the running stack.
#
# WHAT THIS HARNESS ADDS: the paths that CANNOT be exercised against the live
# stack, because doing so would require stopping the operator's containers —
# which is forbidden while other work depends on them. Those are exactly the
# paths where a gate most easily lies: the not-running case must SKIP honestly
# (never FAIL, or every developer with the stack down gets a §11.4.201(1)
# false-positive refusal), and the reachable-but-unreadable case must be a
# HARNESS ERROR (never a quiet "clean", because a blind reader and a clean
# instance return the identical zero — §11.4.201(6)).
#
# Exit: 0 every arm matched | 1 divergence | 2 harness error.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
GATE="$REPO_ROOT/scripts/pre_build/check_cm_no_test_tag_debris.sh"

if [[ ! -x "$GATE" ]]; then
    echo "HARNESS ERROR: gate missing or not executable at $GATE" >&2
    exit 2
fi

fails=0
pass() { echo "PASS: $*"; }
fail() { echo "FAIL: $*"; fails=$((fails + 1)); }

echo "=== paired-mutation meta-test: CM-NO-TEST-TAG-DEBRIS ==="
echo

# --- ARM 1: service not running -> honest SKIP (exit 0), never FAIL ---------
# Point the gate at a port nothing listens on. A closed port is indistinguishable
# from a stopped stack from the gate's perspective, which is exactly the case
# under test.
CLOSED_PORT=1
OUT="$(QBITTORRENT_HOST=127.0.0.1 QBITTORRENT_PORT="$CLOSED_PORT" bash "$GATE" 2>&1)"
RC=$?
if [[ "$RC" -eq 0 ]] && printf '%s' "$OUT" | grep -q 'SKIP-with-reason=service_not_running'; then
    pass "service-down arm SKIPs honestly (rc=0 with a named reason)"
else
    fail "service-down arm: expected rc=0 + service_not_running, got rc=$RC"
    printf '%s\n' "$OUT" | sed 's/^/      /'
fi

# --- ARM 2: the skip must NOT masquerade as a clean verdict -----------------
# A gate that prints PASS when it observed nothing is the §11.4.201(6)
# false-null this whole gate exists to avoid.
if printf '%s' "$OUT" | grep -q 'CM-NO-TEST-TAG-DEBRIS: PASS'; then
    fail "service-down arm reported PASS — an unobserved instance must never read as clean"
else
    pass "service-down arm does not claim PASS (no false-null)"
fi

# --- ARM 3: reachable but NOT a JSON array -> HARNESS ERROR (exit 2) --------
# Stand up a throwaway HTTP server that accepts the login and then answers the
# tag endpoint with HTML instead of JSON. The gate must refuse rather than
# parse garbage into a confident "clean".
PORT=$(( ( RANDOM % 10000 ) + 40000 ))
PY_SRV="$(mktemp)"
cat > "$PY_SRV" <<'PYEOF'
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.startswith("/api/v2/torrents/tags"):
            body = b"<html>not json</html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"ok")

    def do_POST(self):
        # Mimic a qBittorrent 5.x successful login: 204 + QBT_SID cookie.
        self.send_response(204)
        self.send_header("Set-Cookie", "QBT_SID_7185=meta-test; path=/")
        self.end_headers()

HTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
PYEOF
python3 "$PY_SRV" "$PORT" >/dev/null 2>&1 &
SRV_PID=$!
trap 'kill "$SRV_PID" 2>/dev/null; rm -f "$PY_SRV"' EXIT

# Wait for the stub to accept connections rather than sleeping a guessed amount.
for _ in $(seq 1 40); do
    if (exec 3<>"/dev/tcp/127.0.0.1/$PORT") 2>/dev/null; then
        exec 3>&- 2>/dev/null || true
        break
    fi
    sleep 0.1
done

OUT2="$(QBITTORRENT_HOST=127.0.0.1 QBITTORRENT_PORT="$PORT" bash "$GATE" 2>&1)"
RC2=$?
if [[ "$RC2" -eq 2 ]] && printf '%s' "$OUT2" | grep -q 'HARNESS ERROR'; then
    pass "non-JSON tag endpoint is a HARNESS ERROR (rc=2), not a clean verdict"
else
    fail "non-JSON arm: expected rc=2 + HARNESS ERROR, got rc=$RC2"
    printf '%s\n' "$OUT2" | sed 's/^/      /'
fi

if printf '%s' "$OUT2" | grep -q 'CM-NO-TEST-TAG-DEBRIS: PASS'; then
    fail "non-JSON arm reported PASS — a blind read must never read as clean"
else
    pass "non-JSON arm does not claim PASS"
fi

echo
if [[ "$fails" -gt 0 ]]; then
    echo "=== META-TEST FAIL: $fails arm(s) diverged — the gate is not trustworthy ==="
    exit 1
fi
echo "=== META-TEST PASS: skip and blind-read arms both behave honestly ==="
exit 0
