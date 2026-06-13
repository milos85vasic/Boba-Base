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
    SECRETS_FOUND=false
    grep -rn --include='*.py' --include='*.sh' --include='*.yml' \
        -E '(?:api_key|secret|password|token)\s*=\s*["\x27][A-Za-z0-9_]{16,}["\x27]' \
        "$SCRIPT_DIR" 2>/dev/null | grep -v '.env.example' | grep -v 'test_' | grep -v 'your_' | grep -v '.pyc' | grep -v __pycache__ | grep -v 'pbkdf2_hash' | grep -v 'admin.*admin' || true
    if [[ -n "$(grep -rn --include='*.py' --include='*.sh' --include='*.yml' \
        -E '(?:api_key|secret)\s*=\s*["\x27][A-Za-z0-9_]{20,}["\x27]' \
        "$SCRIPT_DIR" 2>/dev/null | grep -v '.env.example' | grep -v 'test_' | grep -v 'your_' | grep -v '.pyc' | grep -v __pycache__)" ]]; then
        fail "Potential hardcoded secrets found (see above)"
        SECRETS_FOUND=true
    fi
    if [[ "$SECRETS_FOUND" == "false" ]]; then
        pass "No hardcoded secrets detected"
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
