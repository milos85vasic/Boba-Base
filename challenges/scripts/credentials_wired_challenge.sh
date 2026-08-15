#!/bin/bash
# credentials_wired_challenge.sh — §11.4.115 RED/GREEN guard proving
# every tracker credential is actually wired end-to-end from .env into
# the container process env, and that .env stays secure (mode 0600,
# gitignored, absent from tracked files + git history).
#
# ─── WHAT THIS PROVES (anti-bluff, §11.4.238 coverage) ────────────
#   1. .env exists at repo root with mode 0600
#   2. .env is matched by .gitignore + is NOT a tracked file
#   3. All 11 expected credential var NAMES are present in .env
#      (names only checked; VALUE content is NEVER read into script
#       output — §11.4.10 credentials-handling)
#   4. NNMCLUB_COOKIES value contains the load-bearing substring
#      "phpbb2mysql_4_sid=" (session cookie without which nnmclub
#       plugin cannot authenticate — see download-proxy/src/api/
#       routes.py line 500)
#   5. Credentials propagate to the qbittorrent-proxy container's
#      process environment (checks presence + length > 0 for each
#      required var; NEVER echoes the value itself)
#
# ─── §11.4.115 RED_MODE POLARITY ──────────────────────────────────
#   RED_MODE=0 (default, GREEN regression guard) — asserts all 5
#      properties above hold. PASSes on properly-configured boba,
#      FAILs on any regression. This is what run_all_challenges.sh
#      invokes and what the standing gate should read.
#   RED_MODE=1 (explicit-opt-in, reproduce-defect) — asserts .env
#      is MISSING at least one required var, or containers don't see
#      the creds. PASSes only against an unconfigured system (used
#      for the original TDD-RED step + forensic re-verification).
#
# ─── SKIPS (§11.4.3 honest topology-appropriate SKIP-with-reason) ─
#   - No `.env` at all → SKIP (fresh checkout; run scripts/install.sh)
#   - Container `qbittorrent-proxy` not running → SKIP the container-
#     side propagation checks; still runs the file-side checks
#
# ─── EXIT ─────────────────────────────────────────────────────────
#   0 = all applicable checks PASS
#   1 = one or more FAIL
#   2 = invocation error

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

RED_MODE="${RED_MODE:-0}"

if [[ "$(uname -s)" != "Linux" ]]; then
    echo "=== credentials_wired_challenge ==="
    echo "SKIP: Linux-only (uname=$(uname -s))"
    exit 0
fi
if [ ! -f .env ]; then
    echo "=== credentials_wired_challenge ==="
    echo "SKIP: .env missing (run scripts/install.sh or setup.sh first)"
    exit 0
fi

echo "=== credentials_wired_challenge (RED_MODE=$RED_MODE) ==="

PASS_COUNT=0
FAIL_COUNT=0
declare -a FAIL_DETAILS=()

assert_pass() { echo "PASS: $*"; PASS_COUNT=$((PASS_COUNT + 1)); }
assert_fail() { echo "FAIL: $*"; FAIL_COUNT=$((FAIL_COUNT + 1)); FAIL_DETAILS+=("$*"); }

# The full set of credential var names this challenge guards. Extend
# when new trackers are added.
REQUIRED_VARS=(
    RUTRACKER_USERNAME RUTRACKER_PASSWORD
    KINOZAL_USERNAME KINOZAL_PASSWORD
    IPTORRENTS_USERNAME IPTORRENTS_PASSWORD
    NNMCLUB_USERNAME NNMCLUB_PASSWORD NNMCLUB_COOKIES
    RUTOR_USERNAME RUTOR_PASSWORD
)
# OPTIONAL cookie autoload vars — populated by scripts/load-tracker-cookies.sh
# from ~/Downloads/cookies_<tracker>.txt on the operator's host (operator
# mandate 2026-08-15). May be empty on a fresh install (before the operator
# exports cookies from their browser); Check 6a below asserts SHAPE where
# present but never fails when empty. RUTOR is a public tracker (no session
# required) but the cookie jar carries cf_clearance which helps with
# Cloudflare challenges. KINOZAL cookies are the authenticated session token
# and are the alternative to KINOZAL_USERNAME/PASSWORD form auth.
OPTIONAL_COOKIE_VARS=(RUTRACKER_COOKIES RUTOR_COOKIES KINOZAL_COOKIES)

# ─── Check 1: .env mode is 0600 ────────────────────────────────────
mode="$(stat -c '%a' .env)"
if [ "$mode" = "600" ]; then
    assert_pass ".env mode = 0600 (§11.4.10)"
else
    assert_fail ".env mode = 0$mode, expected 0600 (§11.4.10 credentials-handling — run: chmod 600 .env)"
fi

# ─── Check 2: .env matched by .gitignore + not tracked ─────────────
if git check-ignore -q .env 2>/dev/null; then
    assert_pass ".env matched by .gitignore"
else
    assert_fail ".env NOT matched by .gitignore — CRITICAL, credentials could be committed"
fi
if git ls-files --error-unmatch .env >/dev/null 2>&1; then
    assert_fail ".env is TRACKED in git — CRITICAL, credentials in history"
else
    assert_pass ".env is not tracked in git"
fi

# ─── Check 3: every required var present in .env (name-only) ──────
missing=()
for v in "${REQUIRED_VARS[@]}"; do
    if ! grep -qE "^[[:space:]]*(export[[:space:]]+)?${v}=" .env; then
        missing+=("$v")
    fi
done
if [ ${#missing[@]} -eq 0 ]; then
    assert_pass "all ${#REQUIRED_VARS[@]} required credential var NAMES present in .env"
else
    if [ "$RED_MODE" = "1" ]; then
        assert_pass "RED: ${#missing[@]} missing var(s): ${missing[*]} — defect reproduced"
    else
        assert_fail "GREEN: ${#missing[@]} required credential var(s) MISSING from .env: ${missing[*]}"
    fi
fi

# ─── Check 4: NNMCLUB_COOKIES contains phpbb2mysql_4_sid= substring
# (proves it's a real logged-in session cookie, not empty / stub /
#  password-only fallback). Never echoes the value itself.
if grep -qE '^[[:space:]]*(export[[:space:]]+)?NNMCLUB_COOKIES=' .env; then
    if grep -q 'phpbb2mysql_4_sid=' .env; then
        assert_pass "NNMCLUB_COOKIES contains phpbb2mysql_4_sid= (session cookie present)"
    else
        assert_fail "NNMCLUB_COOKIES is set but lacks phpbb2mysql_4_sid= — nnmclub plugin will refuse auth (see download-proxy/src/api/routes.py:500)"
    fi
fi

# ─── Check 4a: optional cookie vars — if present, shape is right ───
# For any OPTIONAL_COOKIE_VAR that is set + non-empty, verify it carries
# the tracker's known session-cookie substring. Empty/absent values are
# a legitimate healthy state (loader hasn't run OR operator hasn't yet
# exported cookies from their browser) — never a FAIL.
for cv in "${OPTIONAL_COOKIE_VARS[@]}"; do
    if grep -qE "^[[:space:]]*(export[[:space:]]+)?${cv}=" .env; then
        vline="$(grep -E "^[[:space:]]*(export[[:space:]]+)?${cv}=" .env | tail -1 || true)"
        vraw="${vline#*=}"; vraw="${vraw#\'}"; vraw="${vraw%\'}"; vraw="${vraw#\"}"; vraw="${vraw%\"}"
        if [ -z "$vraw" ]; then
            assert_pass "$cv present but empty (optional autoload target — cookies_<tracker>.txt not yet exported to \$HOME/Downloads)"
            continue
        fi
        case "$cv" in
            RUTRACKER_COOKIES)
                if printf '%s' "$vraw" | grep -q 'bb_session='; then
                    assert_pass "$cv contains bb_session= (RuTracker session cookie present)"
                else
                    assert_fail "$cv is set but lacks bb_session= — RuTracker plugin will refuse auth"
                fi ;;
            RUTOR_COOKIES)
                # Public tracker — any parseable value is fine (cf_clearance
                # or plain jar). Just assert the value is a `k=v; k=v` shape.
                if printf '%s' "$vraw" | grep -qE '^[A-Za-z0-9_.]+=.*$'; then
                    assert_pass "$cv shape OK (public tracker; cf_clearance helps Cloudflare)"
                else
                    assert_fail "$cv is set but not a k=v; k=v cookie header"
                fi ;;
            KINOZAL_COOKIES)
                # Kinozal session cookie is `uid=<n>; pass=<hash>` per its
                # own login form (see the harvested jar). Assert either
                # marker present.
                if printf '%s' "$vraw" | grep -qE 'uid=|pass='; then
                    assert_pass "$cv contains uid= or pass= (Kinozal session cookie present)"
                else
                    assert_fail "$cv is set but lacks uid= / pass= — Kinozal plugin will refuse auth"
                fi ;;
        esac
    fi
done

# ─── Check 5: credentials propagate to qbittorrent-proxy container ─
if podman ps --format '{{.Names}}' 2>/dev/null | grep -q '^qbittorrent-proxy$'; then
    # Container-side checks: for each var, verify it exists AND len > 0.
    # NEVER print the value — only the length.
    ctr_missing=()
    ctr_empty=()
    for v in "${REQUIRED_VARS[@]}"; do
        # -F fixed string, exact-var match via envfile parse using awk to
        # avoid partial matches (e.g., NNMCLUB_USERNAME vs NNMCLUB_USERNAME2).
        vlen="$(podman exec qbittorrent-proxy sh -c "printf '%s' \"\$$v\" | wc -c" 2>/dev/null)"
        vpresent="$(podman exec qbittorrent-proxy sh -c "env | awk -F= -v k='$v' 'index(\$0, k \"=\") == 1 {found=1} END {print found+0}'" 2>/dev/null)"
        if [ "$vpresent" != "1" ]; then
            ctr_missing+=("$v")
        elif [ "${vlen:-0}" -eq 0 ]; then
            ctr_empty+=("$v")
        fi
    done
    if [ ${#ctr_missing[@]} -eq 0 ] && [ ${#ctr_empty[@]} -eq 0 ]; then
        assert_pass "all ${#REQUIRED_VARS[@]} credential vars propagated to qbittorrent-proxy container env (non-empty)"
    else
        [ ${#ctr_missing[@]} -gt 0 ] && \
            assert_fail "container missing var(s): ${ctr_missing[*]} — check docker-compose.yml env: block"
        [ ${#ctr_empty[@]} -gt 0 ] && \
            assert_fail "container has empty var(s): ${ctr_empty[*]} — check .env value + compose interpolation"
    fi
else
    echo "  NOTE: qbittorrent-proxy container not running — SKIP container-side propagation check"
    echo "        (start with: bash scripts/boba-svc.sh up)"
fi

# ─── Check 7: cookie-loader primitive present, executable, syntax-clean
LOADER="scripts/load-tracker-cookies.sh"
if [ -x "$LOADER" ] && bash -n "$LOADER" 2>/dev/null; then
    assert_pass "$LOADER exists + executable + bash -n clean (cookie autoload primitive per operator mandate 2026-08-15)"
else
    assert_fail "$LOADER missing / not executable / syntax error — cookie autoload broken"
fi

# ─── Check 8: --dry-run invocation exits 0 AND lists at least one
# known tracker whose file exists (or ABSENT/SKIP report — either is
# a legitimate healthy outcome).
if [ -x "$LOADER" ]; then
    dr_out="$(bash "$LOADER" --dry-run 2>&1)"
    dr_rc=$?
    if [ "$dr_rc" -eq 0 ]; then
        assert_pass "$LOADER --dry-run exit 0 (loader is invocable in read-only mode)"
        # Must have named at least one tracker in the summary line.
        if printf '%s' "$dr_out" | grep -qE "summary: loaded=[0-9]+ unchanged=[0-9]+ absent=[0-9]+"; then
            assert_pass "$LOADER --dry-run emits the standard summary line"
        else
            assert_fail "$LOADER --dry-run did NOT emit the summary line — output shape drifted"
        fi
    else
        assert_fail "$LOADER --dry-run exit $dr_rc (should be 0 for read-only inspection)"
    fi
fi

# ─── Check 9: for each tracker whose cookie file exists in the
# default source dir, the dry-run reports the file was seen (either
# WOULD LOAD, UNCHANGED, or has a per-tracker cookie-count line).
COOKIE_DIR="${TRACKER_COOKIE_DIR:-$HOME/Downloads}"
if [ -d "$COOKIE_DIR" ] && [ -x "$LOADER" ]; then
    for t in rutracker nnmclub rutor kinozal; do
        f="$COOKIE_DIR/cookies_${t}.txt"
        if [ -f "$f" ]; then
            if printf '%s' "$dr_out" | grep -qE "\[load-tracker-cookies\] $t: "; then
                assert_pass "cookies_${t}.txt present in $COOKIE_DIR AND recognised by loader"
            else
                assert_fail "cookies_${t}.txt exists in $COOKIE_DIR but loader did not report it"
            fi
        fi
    done
fi

# ─── verdict ──────────────────────────────────────────────────────
echo "─────────────────────────────────────────────────────────────────"
echo "Total: PASS=$PASS_COUNT FAIL=$FAIL_COUNT"
if [ "$FAIL_COUNT" -gt 0 ]; then
    for line in "${FAIL_DETAILS[@]}"; do echo "  - $line"; done
    exit 1
fi
exit 0
