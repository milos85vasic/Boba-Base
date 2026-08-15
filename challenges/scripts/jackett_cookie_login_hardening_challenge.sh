#!/usr/bin/env bash
# jackett_cookie_login_hardening_challenge.sh — BOB-067 anti-bluff regression
# guard for the Lava-P4 Jackett cookie-login hardening in
# qBitTorrent-go/internal/jackett/client.go.
#
# ─── CONSTITUTION BINDINGS ────────────────────────────────────────────
# §11.4.115  RED-on-broken-artifact + polarity switch (RED_MODE=1 default)
# §11.4.5    Captured runtime evidence — a real go test run, not a grep
# §11.4.69   feature_class=extension_loading (jackett_management_cookie_login)
# §11.4.108  Runtime-signature — the fix is proven by the client code driving
#            a fake-Jackett end-to-end (302→login→retry) and passing, NEVER by
#            greping the source string "login" or "cookiejar"
# §11.4.146  Same test confirms the fix (polarity flip closes the guard)
# §11.4.201  Guard asserts the REAL condition — presence of Cookie login,
#            login retry on 302, and the wrong-password rejection safety net
# §11.4.238  QA is the DISCOVERER — this challenge would have caught the
#            "apikey-only management call silently 302s" defect Lava P4 names
#
# ─── POLARITY (§11.4.115) ─────────────────────────────────────────────
#   RED_MODE=1  (default): PASS on the BROKEN state (client.go missing cookie
#                jar / login / doManaged), FAIL if hardening is already present
#                and Go tests pass — the pre-fix reproduction check.
#   RED_MODE=0            : PASS on the FIXED state (all three cookie tests
#                pass in the Go suite), FAIL if hardening is absent or the
#                Go tests fail — the shipped regression guard consumed by
#                run_all_challenges.sh.
#
# ─── ANTI-BLUFF ───────────────────────────────────────────────────────
# The GREEN assertion RUNS the real Go test suite covering the three
# load-bearing behaviors (§11.4.108 runtime signature, not source grep):
#   1. TestFakeJackettRefusesManagementWithoutCookie — proves the fake
#      is behaviorally equivalent to real password-protected Jackett
#      (302→/UI/Login on apikey-only management, not 200 — a bluff-fake
#      would return 200 and every test built on it would be worthless).
#   2. TestManagementCookieLogin_DiscoveryViaCookiePath — proves an
#      apikey-only client transparently acquires the session cookie
#      and completes discovery (GetCatalog) + template fetch.
#   3. TestManagementCookieLogin_ConfigurableAdminPassword — proves
#      the admin password is injected at runtime (§6.R) AND the wrong
#      -password safety net rejects with an error instead of a false
#      success (401/403 OR 200-with-no-Set-Cookie both mapped to fail).
#
# ─── HONEST BOUNDARY (§11.4.6) ────────────────────────────────────────
# The Go tests use an httptest.Server-backed fake. This challenge PROVES
# the client correctly speaks the cookie-login protocol; it does NOT
# prove it works against every real Jackett version — that is manual QA
# (§11.4.185) or a live docker-run challenge, tracked separately.
# The extract-jackett-key.py file reads ServerConfig.json from disk and
# makes NO HTTP calls; cookie-login hardening does not apply to it and
# claiming otherwise would be a §11.4.6 category error. The hardening
# lives in the Go client (client.go) that consumes the extracted key.
#
# ─── CREDENTIAL HANDLING (§11.4.10) ───────────────────────────────────
# The test fixtures use synthetic values (adminPW = "s3cr3t-dashboard-pw",
# apikey = "test-key") baked into cookie_login_test.go — no real
# credentials are ever exposed, printed, or logged by this challenge.
#
# ─── EXIT ─────────────────────────────────────────────────────────────
#   0 = PASS or SKIP-with-reason
#   1 = FAIL (hardening broken in the current polarity)
set -uo pipefail

BOBA_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
GO_MOD_ROOT="${BOBA_ROOT}/qBitTorrent-go"
CLIENT_GO="${GO_MOD_ROOT}/internal/jackett/client.go"
COOKIE_TEST_GO="${GO_MOD_ROOT}/internal/jackett/cookie_login_test.go"
RED_MODE="${RED_MODE:-0}"

pass() { echo "PASS: $*"; exit 0; }
fail() { echo "FAIL: $*"; exit 1; }
skip() { echo "SKIP: $*"; exit 0; }

# ─── polarity-independent pre-flight ─────────────────────────────────
command -v go >/dev/null 2>&1 || skip "go toolchain absent (host cannot exercise cookie-login client)"
[ -d "$GO_MOD_ROOT" ] || fail "qBitTorrent-go module root missing at $GO_MOD_ROOT"

# ─── RED path: assert BROKEN state (client.go missing cookie infra) ──
if [ "$RED_MODE" = "1" ]; then
    if [ ! -f "$CLIENT_GO" ]; then
        pass "RED_MODE=1 — client.go missing (BOB-067 pre-port state)"
    fi
    # Required API surface for the P4 hardening (function names read from
    # the file structure, not their string bodies — §11.4.201 real condition).
    missing=""
    for symbol in 'func NewClientWithPassword' 'func (c \*Client) WarmUp' 'func (c \*Client) login' 'func (c \*Client) doManaged' 'cookiejar.New'; do
        if ! grep -q "$symbol" "$CLIENT_GO" 2>/dev/null; then
            missing="${missing}${symbol}; "
        fi
    done
    if [ -n "$missing" ]; then
        pass "RED_MODE=1 — client.go missing required cookie-login surface: $missing"
    fi
    if [ ! -f "$COOKIE_TEST_GO" ]; then
        pass "RED_MODE=1 — cookie_login_test.go absent (fake + tests not ported yet)"
    fi
    fail "RED_MODE=1 — cookie-login hardening ALREADY present (BOB-067 done; flip RED_MODE=0 for the ratchet)"
fi

# ─── GREEN path: assert FIXED state (Go tests pass end-to-end) ───────
[ -f "$CLIENT_GO" ]      || fail "GREEN — client.go missing at $CLIENT_GO"
[ -f "$COOKIE_TEST_GO" ] || fail "GREEN — cookie_login_test.go missing at $COOKIE_TEST_GO"

# Runtime signature: the three load-bearing behaviors, executed for real.
cd "$GO_MOD_ROOT" || fail "GREEN — cannot cd into $GO_MOD_ROOT"

TEST_PATTERN='TestFakeJackettRefusesManagementWithoutCookie|TestManagementCookieLogin_DiscoveryViaCookiePath|TestManagementCookieLogin_ConfigurableAdminPassword'
if ! go test -count=1 -run "$TEST_PATTERN" ./internal/jackett/ >/tmp/bob067_gotest.$$.log 2>&1; then
    echo "--- go test output ---"
    cat /tmp/bob067_gotest.$$.log
    rm -f /tmp/bob067_gotest.$$.log
    fail "GREEN — cookie-login Go tests failed (see output above)"
fi

# Positive-evidence assertion: verify all three tests actually ran
# (not just the top-level "ok" line — a filter that matched zero tests
# also prints "ok"). Real go test -v output would enumerate them; here
# we use -count=1 without -v, so require the tests were compiled.
if ! grep -qE '^ok\s' /tmp/bob067_gotest.$$.log; then
    cat /tmp/bob067_gotest.$$.log
    rm -f /tmp/bob067_gotest.$$.log
    fail "GREEN — go test output has no 'ok' line (compile or import failure)"
fi

# Deep verification: run with -v and count the PASS lines, so a mistyped
# TEST_PATTERN matching zero tests is caught (§11.4.201 false-null guard).
if ! go test -v -count=1 -run "$TEST_PATTERN" ./internal/jackett/ >/tmp/bob067_gotestv.$$.log 2>&1; then
    cat /tmp/bob067_gotestv.$$.log
    rm -f /tmp/bob067_gotest.$$.log /tmp/bob067_gotestv.$$.log
    fail "GREEN — verbose go test rerun failed"
fi
pass_count=$(grep -cE '^--- PASS: Test(FakeJackettRefusesManagementWithoutCookie|ManagementCookieLogin_(DiscoveryViaCookiePath|ConfigurableAdminPassword))\b' /tmp/bob067_gotestv.$$.log || true)
rm -f /tmp/bob067_gotest.$$.log /tmp/bob067_gotestv.$$.log
if [ "$pass_count" -lt 3 ]; then
    fail "GREEN — only $pass_count/3 cookie-login tests reported --- PASS: (false-null: filter matched too few tests)"
fi

pass "BOB-067 cookie-login hardening runtime-signature verified — 3/3 tests passed (fake refuses management without cookie; discovery via cookie path; wrong-password rejection)"
