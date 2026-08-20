#!/usr/bin/env bash
# run_mutation_check.sh — the paired §1.1 falsifiability proof for tests/ddos/.
#
# Purpose
#   Prove every DDoS-class assertion CATCHES ITS OWN NEGATION. A test that
#   cannot fail is a bluff (§11.4/§11.4.1). For each defence the suite claims to
#   verify, this script breaks that defence and asserts the corresponding tests
#   turn RED. It also runs an UNMUTATED control first, so a failure caused by
#   the copy mechanism itself can never be mistaken for a mutation being caught
#   (§11.4.201(1) — a false-positive refusal is as bad as a false pass).
#
# Usage
#   bash tests/ddos/mutations/run_mutation_check.sh
#
# Inputs   none (reads the repo's own download-proxy/src)
# Outputs  per-mutation PASS/FAIL lines; exit 0 iff every mutation was caught
#          AND the control was green.
# Side-effects
#   Creates a throwaway copy of download-proxy/src under a mktemp -d directory
#   and deletes it on exit. NEVER modifies the real source tree — §11.4.84: this
#   checkout is shared with other agents, so an in-place mutation could be swept
#   into someone else's commit before restoration.
# Dependencies  bash, python3 (project .venv preferred), pytest, sed, cp
# Cross-refs    tests/ddos/conftest.py (BOBA_DDOS_SRC_PATH seam),
#               docs/TESTING.md "DDoS tests"

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../../.." && pwd)"
REAL_SRC="$REPO_ROOT/download-proxy/src"

PYTHON="${PYTHON:-}"
for cand in "$PYTHON" "$REPO_ROOT/.venv/bin/python" python3.13 python3.12 python3; do
    [ -n "$cand" ] || continue
    if command -v "$cand" >/dev/null 2>&1 && "$cand" -c 'import fastapi, slowapi' >/dev/null 2>&1; then
        PYTHON="$cand"; break
    fi
    PYTHON=""
done
if [ -z "$PYTHON" ]; then
    echo "ERROR: no interpreter with fastapi+slowapi found (tried \$PYTHON, .venv, python3.1x)." >&2
    exit 2
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

fresh_copy() {
    rm -rf "$WORK/src"
    cp -a "$REAL_SRC" "$WORK/src"
}

pass=0; fail=0

# run_case <name> <expectation: caught|green> <pytest-target> <mutator-fn|->
run_case() {
    local name="$1" expect="$2" target="$3" mutator="$4"
    fresh_copy
    [ "$mutator" = "-" ] || "$mutator"

    BOBA_DDOS_SRC_PATH="$WORK/src" "$PYTHON" -m pytest "$REPO_ROOT/$target" \
        -p no:randomly -q --timeout=60 >"$WORK/out.txt" 2>&1
    local rc=$?

    if [ "$expect" = "green" ]; then
        if [ $rc -eq 0 ]; then
            echo "  [ok]     CONTROL  $name — unmutated copy is green (rc=0)"; pass=$((pass+1))
        else
            echo "  [FAILED] CONTROL  $name — unmutated copy is NOT green (rc=$rc)"
            tail -6 "$WORK/out.txt" | sed 's/^/           /'
            fail=$((fail+1))
        fi
    else
        if [ $rc -ne 0 ]; then
            local n; n="$(grep -cE '^(FAILED|ERROR) ' "$WORK/out.txt" || true)"
            echo "  [ok]     MUTATION $name — caught (rc=$rc, ${n} failing test(s))"
            grep -E '^FAILED ' "$WORK/out.txt" | head -4 | sed 's/^/           /'
            pass=$((pass+1))
        else
            echo "  [FAILED] MUTATION $name — NOT CAUGHT: suite stayed green. The"
            echo "           assertion is a bluff; strengthen or delete it."
            fail=$((fail+1))
        fi
    fi
}

# --- mutators (each breaks exactly ONE defence in the throwaway copy) --------

m_disable_rate_limiting() {
    # `install()` returns a Limiter but never registers middleware/decorators:
    # simulate the limiter being wired out entirely.
    sed -i 's/^    key = f"RATE_LIMIT_{class_name.upper()}"$/    key = f"RATE_LIMIT_{class_name.upper()}"; return "100000\/minute"/' \
        "$WORK/src/api/rate_limit.py"
}

m_collapse_limiter_key() {
    # Every caller shares one bucket -> one attacker throttles everybody.
    sed -i 's/^def _client_key(request: Request) -> str:$/def _client_key(request: Request) -> str:\n    return "COLLAPSED"/' \
        "$WORK/src/api/rate_limit.py"
}

m_remove_upload_size_guard() {
    # The 10 MiB ceiling is raised out of reach -> oversized uploads accepted.
    sed -i 's/^_MAX_TORRENT_UPLOAD_BYTES = 10 \* 1024 \* 1024$/_MAX_TORRENT_UPLOAD_BYTES = 10 * 1024 * 1024 * 1024/' \
        "$WORK/src/api/routes.py"
}

m_disable_admission_control() {
    # The in-flight cap never trips -> the service accepts unbounded work.
    sed -i 's/^        return self._active_search_count >= self._max_concurrent_searches$/        return False/' \
        "$WORK/src/merge_service/search.py"
}

m_block_the_event_loop() {
    # A synchronous sleep inside the request path -> head-of-line blocking.
    sed -i 's/^async def dispatch_event(event_type: str, event_data: dict\[str, Any\]):.*$/&\n    import time as _t; _t.sleep(0.4)/' \
        "$WORK/src/api/hooks.py"
}

# --- the matrix -------------------------------------------------------------

echo "=== §1.1 paired-mutation check for tests/ddos/ ==="
echo "    interpreter: $PYTHON"
echo "    mutations applied to a COPY at $WORK/src (real source untouched)"
echo

echo "--- control (no mutation): every target must be GREEN on the copy ---"
run_case "flood"      green tests/ddos/test_request_flood.py      -
run_case "payload"    green tests/ddos/test_payload_abuse.py      -
run_case "exhaustion" green tests/ddos/test_resource_exhaustion.py -
run_case "slow"       green tests/ddos/test_slow_request.py       -
echo

echo "--- mutations: each must be CAUGHT (suite turns RED) ---"
run_case "M1 rate limiting neutered (limits raised to 100000/minute)" \
    caught tests/ddos/test_request_flood.py m_disable_rate_limiting
run_case "M2 limiter key collapsed (all clients share one bucket)" \
    caught tests/ddos/test_request_flood.py m_collapse_limiter_key
run_case "M3 upload size guard raised out of reach (10 MiB -> 10 GiB)" \
    caught tests/ddos/test_payload_abuse.py m_remove_upload_size_guard
run_case "M4 admission control disabled (is_search_queue_full -> False)" \
    caught tests/ddos/test_resource_exhaustion.py m_disable_admission_control
run_case "M5 event loop blocked in the request path (sync sleep)" \
    caught tests/ddos/test_slow_request.py m_block_the_event_loop
echo

echo "=== summary: $pass ok, $fail failed ==="
[ "$fail" -eq 0 ] || exit 1
exit 0
