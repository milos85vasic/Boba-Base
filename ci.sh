#!/usr/bin/env bash
# =============================================================================
# Manual CI Pipeline for qBitTorrent Project
# =============================================================================
# This script runs ALL validation locally. It is NEVER triggered by Git hooks
# or remote CI services. Run it manually before releases or major changes.
#
# Usage:
#   ./ci.sh                # Full pipeline
#   ./ci.sh --quick        # Quick check (syntax + unit tests only)
#   ./ci.sh --tests-only   # Tests only, skip syntax checks
#   ./ci.sh --verbose      # Verbose output
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
QUICK=false
TESTS_ONLY=false
# VERBOSE is reserved for future use
PASS=0
FAIL=0
SKIP=0

for arg in "$@"; do
    case "$arg" in
        --quick) QUICK=true ;;
        --tests-only) TESTS_ONLY=true ;;
        --verbose) : ;;  # reserved for future use
        --help|-h) echo "Usage: $0 [--quick] [--tests-only] [--verbose]"; exit 0 ;;
    esac
done

# ---------------------------------------------------------------------------
# Python interpreter selection. pyproject.toml declares requires-python ">=3.12"
# (the suite uses tomllib + X|Y union syntax that a bare `python3` < 3.12 cannot
# even COLLECT — it false-reds this gate on a host whose default python3 is older,
# e.g. 3.9). Prefer the project venv, then a versioned python3.1x, then a bare
# python3 that is >= 3.12; abort with a clear message if none qualifies. On a host
# already on python3 >= 3.12 this is a no-op (same interpreter selected as before).
# ---------------------------------------------------------------------------
_select_python() {
    local p
    for p in "${PYTHON:-}" "$SCRIPT_DIR/.venv/bin/python" python3.13 python3.12 python3; do
        [ -n "$p" ] || continue
        if command -v "$p" >/dev/null 2>&1 \
            && "$p" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)' 2>/dev/null; then
            printf '%s\n' "$p"
            return 0
        fi
    done
    return 1
}
PYTHON="$(_select_python)" || {
    echo "ERROR: no Python >= 3.12 found (pyproject requires-python = '>=3.12')." >&2
    echo "       Tried: \$PYTHON, $SCRIPT_DIR/.venv/bin/python, python3.13, python3.12, python3." >&2
    echo "       Create the venv (python3.12+ -m venv .venv && .venv/bin/pip install -e .) or install python3.12+." >&2
    exit 1
}

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

step() {
    local name="$1"
    echo -e "\n${CYAN}>>> ${name}${NC}"
}

pass() {
    ((PASS++)) || true
    echo -e "  ${GREEN}PASS${NC} $1"
}

fail() {
    ((FAIL++)) || true
    echo -e "  ${RED}FAIL${NC} $1"
}

skip() {
    ((SKIP++)) || true
    echo -e "  ${YELLOW}SKIP${NC} $1"
}

section() {
    echo ""
    echo -e "${CYAN}========================================${NC}"
    echo -e "${CYAN} $1${NC}"
    echo -e "${CYAN}========================================${NC}"
}

# =========================================================================
# PHASE 1: SECRET/LEAK DETECTION
# =========================================================================
if [[ "$TESTS_ONLY" == "false" ]]; then
    section "PHASE 1: Secret Leak Detection"

    step "Check .env is not tracked"
    if git ls-files --error-unmatch .env 2>/dev/null; then
        fail ".env is tracked by git! Remove it immediately: git rm --cached .env"
    else
        pass ".env is not tracked"
    fi

    step "Scan for hardcoded API keys/passwords in tracked files"
    # -------------------------------------------------------------------
    # ROOT CAUSE (fixed 2026-09-01). The previous pattern used PCRE's
    # non-capturing group `(?:...)` under `grep -E`, which is POSIX ERE and
    # has no such construct. Measured on this host with GNU grep 3.12 against
    # a file literally containing `api_key = "AKIA...XXXX"`:
    #     grep -E '(?:api_key|...)...'  -> stderr "? at start of expression", exit 1 (NO MATCH)
    #     grep -E '(api_key|...)...'    -> exit 0 (MATCH)
    # The old code sent that warning to /dev/null, so `$( )` was empty,
    # SECRETS_FOUND stayed false, and the gate printed PASS. Since CI here is
    # manual (`./ci.sh` is the only path), this was the project's ONLY
    # automated secret check and it had never once been able to fail.
    #
    # Three things changed, each load-bearing:
    #  1. Correct POSIX ERE: `(a|b)` not `(?:a|b)`, `[[:space:]]` not `\s`,
    #     and a real apostrophe via `$'...'` instead of `\x27` (inside a
    #     bracket expression `\x27` is five literal chars, not a quote).
    #  2. stderr is CAPTURED, not discarded. Any scanner diagnostic FAILs the
    #     step — a regex engine's complaint must never read as "clean".
    #  3. ONE scan, ONE threshold, ONE filter chain, computed once and used
    #     for BOTH the human-readable listing and the pass/fail decision.
    #     The two old scans disagreed ({16,} vs {20,}, four terms vs two,
    #     and the deciding one lacked the pbkdf2_hash / admin.*admin
    #     exclusions the display one had) so a legitimately-committed PBKDF2
    #     hash could have failed the build the moment the regex started
    #     working. Reconciled deliberately toward DETECTION: the wider term
    #     list and the lower {16,} threshold (strictly more sensitive), with
    #     the FULL exclusion chain (this repo ships a PBKDF2 hash and the
    #     documented admin/admin WebUI credentials by design -- see CLAUDE.md).
    #
    # Scope is git-tracked files of THIS repo when inside a git worktree
    # (matching the step's own title, and what PHASE 2 already does). The old
    # recursive walk of $SCRIPT_DIR also descended into vendored third-party
    # submodule trees; measured, the corrected pattern finds 10 placeholder
    # assignments in vendored llama-index/skyvern sources that are not this
    # project's secrets. Failing on those would be a false-positive refusal
    # that teaches operators to ignore the gate.
    # -------------------------------------------------------------------
    SECRETS_FOUND=false
    SECRET_PATTERN=$'(api_key|secret|password|token)[[:space:]]*=[[:space:]]*["\'][A-Za-z0-9_]{16,}["\']'

    # Shared exclusion chain — identical for the listing and the decision.
    _secret_scan_filter() {
        grep -v '\.env\.example' \
            | grep -v 'test_' \
            | grep -v 'your_' \
            | grep -v '\.pyc' \
            | grep -v '__pycache__' \
            | grep -v 'pbkdf2_hash' \
            | grep -v 'admin.*admin' \
            || true
    }

    SECRET_STDERR="$(mktemp)"

    # CONTROL NEEDLE (constitution 11.4.201(7)(b)): prove the instrument can
    # SEE before trusting a zero. A blind scanner and a clean repo both
    # return the same quiet nothing; only a known-present needle tells them
    # apart. The needle value below is fabricated and is not a credential.
    # The needle is ASSEMBLED at run time from fragments. Writing it as one
    # literal would make ci.sh (a tracked *.sh file) match its own pattern —
    # a carrier false-positive: the scanner reporting the rule that defines it.
    SECRET_NEEDLE_DIR="$(mktemp -d)"
    printf '%s = "%s"\n' 'api_key' 'CINEEDLE_not_a_real_secret_0123' > "$SECRET_NEEDLE_DIR/needle.py"
    if ! grep -qE "$SECRET_PATTERN" "$SECRET_NEEDLE_DIR/needle.py" 2>>"$SECRET_STDERR"; then
        fail "Secret-scan control needle NOT detected — the scanner is blind; treat this repo as UNSCANNED"
        SECRETS_FOUND=true
    fi
    rm -rf "$SECRET_NEEDLE_DIR"

    SECRET_RAW=""
    SECRET_FILE_COUNT=0
    if git rev-parse --git-dir >/dev/null 2>&1; then
        SECRET_FILE_COUNT="$(git ls-files -- '*.py' '*.sh' '*.yml' | wc -l)"
        SECRET_RAW="$(git ls-files -z -- '*.py' '*.sh' '*.yml' \
            | xargs -0 -r grep -nHE "$SECRET_PATTERN" 2>>"$SECRET_STDERR" || true)"
    else
        SECRET_RAW="$(grep -rn --include='*.py' --include='*.sh' --include='*.yml' \
            -E "$SECRET_PATTERN" "$SCRIPT_DIR" 2>>"$SECRET_STDERR" || true)"
    fi

    # A diagnostic from the scanner means the scan did not really run.
    # Silence here is what let the broken pattern survive; never again.
    if [[ -s "$SECRET_STDERR" ]]; then
        echo "  scanner diagnostics (the scan is NOT trustworthy):"
        sed 's/^/    /' "$SECRET_STDERR"
        fail "Secret scan emitted diagnostics — pattern or scanner is broken; treat this repo as UNSCANNED"
        SECRETS_FOUND=true
    fi
    rm -f "$SECRET_STDERR"

    SECRET_HITS=""
    if [[ -n "$SECRET_RAW" ]]; then
        SECRET_HITS="$(printf '%s\n' "$SECRET_RAW" | _secret_scan_filter)"
    fi
    if [[ -n "$SECRET_HITS" ]]; then
        printf '%s\n' "$SECRET_HITS"
        fail "Potential hardcoded secrets found (see above)"
        SECRETS_FOUND=true
    fi
    if [[ "$SECRETS_FOUND" == "false" ]]; then
        pass "No hardcoded secrets detected ($SECRET_FILE_COUNT files scanned, control needle verified)"
    fi

    step "Verify .gitignore covers sensitive files"
    for f in .env .qbit.env *.key *.pem; do
        if git check-ignore -q "$f" 2>/dev/null; then
            pass "$f is gitignored"
        else
            fail "$f is NOT gitignored"
        fi
    done
fi

# =========================================================================
# PHASE 2: SYNTAX VALIDATION
# =========================================================================
if [[ "$TESTS_ONLY" == "false" ]]; then
    section "PHASE 2: Syntax Validation"

    step "Python syntax check (py_compile)"
    PY_FAIL=0
    PY_TOTAL=0
    # When inside a git repo, only check tracked files (avoids generated
    # artefacts, worktrees, and untracked scratch files).
    if git rev-parse --git-dir >/dev/null 2>&1; then
        mapfile -t py_files < <(git ls-files '*.py')
    else
        mapfile -t py_files < <(find "$SCRIPT_DIR" -name '*.py' \
            -not -path '*/__pycache__/*' \
            -not -path '*/.git/*' \
            -not -path '*/.worktrees/*' \
            -not -path '*/.specify/*' \
            -not -path '*/venv/*' \
            -not -path '*/node_modules/*' \
            -not -path '*/tmp/*' \
            -not -path '*/config/download-proxy/*')
    fi
    for f in "${py_files[@]}"; do
        [[ -f "$f" ]] || continue
        ((PY_TOTAL++)) || true
        if ! "$PYTHON" -m py_compile "$f" 2>/dev/null; then
            # Show stderr so the actual syntax error is visible in logs
            "$PYTHON" -m py_compile "$f" 2>&1 || true
            fail "$f"
            ((PY_FAIL++)) || true
        fi
    done
    if [[ $PY_FAIL -eq 0 ]]; then
        pass "All $PY_TOTAL Python files compile"
    fi

    step "Bash syntax check (bash -n)"
    SH_FAIL=0
    SH_TOTAL=0
    for f in "$SCRIPT_DIR"/*.sh; do
        [[ -f "$f" ]] || continue
        ((SH_TOTAL++)) || true
        if ! bash -n "$f" 2>/dev/null; then
            fail "$(basename "$f")"
            ((SH_FAIL++)) || true
        fi
    done
    if [[ $SH_FAIL -eq 0 ]]; then
        pass "All $SH_TOTAL shell scripts pass bash -n"
    fi
fi

# =========================================================================
# PHASE 3: UNIT TESTS
# =========================================================================
section "PHASE 3: Unit Tests"

step "pytest — unit tests"
if "$PYTHON" -m pytest "$SCRIPT_DIR/tests/unit/" -v --import-mode=importlib --tb=short -m "not requires_compose" 2>&1 | tail -3; then
    pass "Unit tests"
else
    fail "Unit tests"
fi

if [[ "$QUICK" == "true" ]]; then
    skip "Integration and E2E tests (--quick mode)"
else
    # =====================================================================
    # PHASE 4: INTEGRATION TESTS
    # =====================================================================
    section "PHASE 4: Integration Tests"

    step "pytest — integration tests"
    if "$PYTHON" -m pytest "$SCRIPT_DIR/tests/integration/" -v --import-mode=importlib --tb=short --timeout=120 2>&1 | tail -3; then
        pass "Integration tests"
    else
        fail "Integration tests"
    fi

    # =====================================================================
    # PHASE 4.5: OWNERSHIP TESTS
    # =====================================================================
    # tests/ownership/test_container_writes_owned_files.py is the §11.4.115
    # RED-turned-regression-guard for FR-011/FR-007 (002-user-owned-downloads)
    # — proven via a docker-compose.yml revert mutation to catch the real
    # defect. It moved OUT of tests/integration/ (commit 58d340a) because that
    # package's autouse fixture waits on the live merge service and hangs for
    # a test that needs only a container RUNTIME, not the running stack. It
    # was never re-wired into any runner afterward (reported, not fixed, in
    # commit 04742d7's own message) — closed here.
    #
    # The suite's own `pytest.mark.skipif(_runtime() is None, ...)` is the
    # gate: on a host with no podman/docker it reports SKIPPED (rc 0), never
    # a failure — verified 2026-08-21 with PATH stripped of both runtimes
    # ("2 skipped in 0.28s", rc=0). The runtime probe below only decides
    # whether to bother invoking pytest at all; it does not change what the
    # suite itself would report.
    section "PHASE 4.5: Ownership Tests"

    OWNERSHIP_RUNTIME="${CONTAINER_RUNTIME:-$(command -v podman 2>/dev/null || command -v docker 2>/dev/null || echo "")}"
    if [[ -n "$OWNERSHIP_RUNTIME" ]]; then
        step "pytest — ownership tests (container-write ownership, FR-011/FR-007)"
        if "$PYTHON" -m pytest "$SCRIPT_DIR/tests/ownership/" -v --import-mode=importlib --tb=short --timeout=180 2>&1 | tail -6; then
            pass "Ownership tests"
        else
            fail "Ownership tests"
        fi
    else
        skip "Ownership tests (no podman/docker)"
    fi

    # =====================================================================
    # PHASE 5: E2E TESTS
    # =====================================================================
    section "PHASE 5: E2E Tests"

    step "pytest — e2e tests"
    if "$PYTHON" -m pytest "$SCRIPT_DIR/tests/e2e/" -v --import-mode=importlib --tb=short --timeout=120 2>&1 | tail -3; then
        pass "E2E tests"
    else
        fail "E2E tests"
    fi

    # =====================================================================
    # PHASE 6: CONTAINER HEALTH
    # =====================================================================
    section "PHASE 6: Container Health"

    RUNTIME="${CONTAINER_RUNTIME:-$(command -v podman 2>/dev/null || command -v docker 2>/dev/null || echo "")}"

    if [[ -n "$RUNTIME" ]]; then
        step "Check container status"
        for svc in qbittorrent qbittorrent-proxy; do
            STATUS=$("$RUNTIME" inspect --format='{{.State.Status}}' "$svc" 2>/dev/null || echo "not_found")
            if [[ "$STATUS" == "running" ]]; then
                pass "$svc is running"
            else
                fail "$svc is $STATUS"
            fi
        done

        step "Check service endpoints"
        for port_name in "7185:qBittorrent" "7186:proxy" "7187:merge"; do
            PORT="${port_name%%:*}"
            NAME="${port_name##*:}"
            if curl -sf -o /dev/null -m 5 "http://localhost:${PORT}/" 2>/dev/null; then
                pass "$NAME on :$PORT"
            else
                if curl -sf -o /dev/null -m 5 "http://localhost:${PORT}/health" 2>/dev/null; then
                    pass "$NAME on :$PORT (/health)"
                else
                    fail "$NAME on :$PORT not reachable"
                fi
            fi
        done
    else
        skip "Container checks (no podman/docker)"
    fi
fi

# =========================================================================
# SUMMARY
# =========================================================================
section "SUMMARY"

echo ""
echo -e "  ${GREEN}PASS${NC}: $PASS"
echo -e "  ${RED}FAIL${NC}: $FAIL"
echo -e "  ${YELLOW}SKIP${NC}: $SKIP"
echo ""

if [[ $FAIL -gt 0 ]]; then
    echo -e "${RED}PIPELINE FAILED${NC} — $FAIL check(s) failed"
    exit 1
else
    echo -e "${GREEN}PIPELINE PASSED${NC} — All checks successful"
    exit 0
fi
