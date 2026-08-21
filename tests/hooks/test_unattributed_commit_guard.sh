#!/usr/bin/env bash
# test_unattributed_commit_guard.sh — Hermetic executing test for BOB-106's
# §11.4.84 quiescence-check helper (scripts/hooks/unattributed-commit-guard.sh).
#
# Drives the REAL invocation path — not a `bash -n` parse-check
# (§11.4.224(A)): the script's --self-test seeds a disposable temp git repo
# with golden-good/golden-bad commits and asserts on the guard's real exit
# status + stdout, and a separate real-repo check confirms the tracked,
# genuinely-unattributed "Auto-commit" commits already in THIS repo's
# history are detected (RD2-00 / BOB-068 forensic anchor).
#
# §1.1 — Paired meta-test mutation: neuter the bare-pattern match in the
# guard (`false && [[ ... =~ $pat ]]`) -> --self-test flips to FAIL and the
# real-repo scan silently reports OK on known-violating history -> restore
# -> re-assert GREEN. Proven manually during authoring (sha256 recorded);
# this test format re-proves it live via subshell tooling below.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${HERE}/../.." && pwd)"
GUARD="${PROJECT_ROOT}/scripts/hooks/unattributed-commit-guard.sh"

PASS_COUNT=0
FAIL_COUNT=0
pass() { PASS_COUNT=$((PASS_COUNT + 1)); echo "  PASS: $1"; }
fail() { FAIL_COUNT=$((FAIL_COUNT + 1)); echo "  FAIL: $1"; }

if [[ ! -x "${GUARD}" ]]; then
    echo "FATAL: guard script missing or not executable at ${GUARD}" >&2
    exit 2
fi

# --- 1: bash -n parse sanity (necessary, never sufficient per §11.4.224(A)) ---
if bash -n "${GUARD}"; then
    pass "guard script is syntactically valid bash"
else
    fail "guard script fails bash -n"
fi

# --- 2: real invocation, --self-test polarity (golden-good + golden-bad) ---
SELFTEST_OUT="$(bash "${GUARD}" --self-test 2>&1)"
SELFTEST_EXIT=$?
if [[ "${SELFTEST_EXIT}" -eq 0 ]]; then
    pass "guard --self-test exits 0 on unmutated source"
else
    fail "guard --self-test exited ${SELFTEST_EXIT} on unmutated source (expected 0): ${SELFTEST_OUT}"
fi
if echo "${SELFTEST_OUT}" | grep -q "golden-bad      PASS"; then
    pass "self-test golden-bad line reports PASS"
else
    fail "self-test golden-bad line missing/not-PASS: ${SELFTEST_OUT}"
fi
if echo "${SELFTEST_OUT}" | grep -q "golden-good     PASS"; then
    pass "self-test golden-good line reports PASS"
else
    fail "self-test golden-good line missing/not-PASS: ${SELFTEST_OUT}"
fi

# --- 3: real invocation against a hermetic temp repo, exercising the
#     PUBLIC --range interface directly (not just via --self-test) so a
#     regression in --range parsing specifically is caught. ---
TMPREPO="$(mktemp -d)"
_cleanup_tmprepo() { rm -rf "${TMPREPO}" 2>/dev/null || true; }
trap _cleanup_tmprepo EXIT

git -C "${TMPREPO}" init -q -b main
git -C "${TMPREPO}" config user.email "test@example.invalid"
git -C "${TMPREPO}" config user.name "test"
git -C "${TMPREPO}" commit -q --allow-empty -m "root: seed"
BASE_SHA="$(git -C "${TMPREPO}" rev-parse HEAD)"
git -C "${TMPREPO}" commit -q --allow-empty -m "feat: real change (ATM-500)"
HEAD_SHA="$(git -C "${TMPREPO}" rev-parse HEAD)"

# 3a: a range with NO violations must exit 0 and print OK.
if OUT="$(cd "${TMPREPO}" && bash "${GUARD}" --range "${BASE_SHA}..${HEAD_SHA}" 2>&1)"; then
    if echo "${OUT}" | grep -q "OK —"; then
        pass "clean --range reports OK and exits 0"
    else
        fail "clean --range exited 0 but did not print OK: ${OUT}"
    fi
else
    fail "clean --range exited nonzero (expected 0): ${OUT}"
fi

# 3b: add a real unattributed bare commit; the SAME range must now
# detect it, name its SHA, and exit 1 (state-delta assertion, §11.4.238).
git -C "${TMPREPO}" commit -q --allow-empty -m "Auto-commit"
VIOLATION_SHA="$(git -C "${TMPREPO}" rev-parse HEAD)"
DIRTY_EXIT=0
OUT="$(cd "${TMPREPO}" && bash "${GUARD}" --range "${BASE_SHA}..${VIOLATION_SHA}" 2>&1)" || DIRTY_EXIT=$?
if [[ "${DIRTY_EXIT}" -eq 1 ]]; then
    pass "range with an injected bare 'Auto-commit' exits 1"
else
    fail "range with an injected bare 'Auto-commit' exited ${DIRTY_EXIT} (expected 1)"
fi
if echo "${OUT}" | grep -q "${VIOLATION_SHA:0:12}"; then
    pass "violating commit SHA is named in the refusal output"
else
    fail "violating commit SHA not named in refusal output: ${OUT}"
fi

# --- 4: real-repo evidence — the genuinely-tracked, already-existing
#     RD2-00/BOB-068 unattributed commits in THIS repository's history are
#     detected by the default (no-args) invocation. Skips honestly
#     (§11.4.3) if this checkout has no reachable tag (fresh shallow clone).
# ---
if git -C "${PROJECT_ROOT}" describe --tags --abbrev=0 HEAD >/dev/null 2>&1; then
    REAL_EXIT=0
    REAL_OUT="$(cd "${PROJECT_ROOT}" && bash "${GUARD}" 2>&1)" || REAL_EXIT=$?
    KNOWN_BARE_COUNT="$(git -C "${PROJECT_ROOT}" log --oneline --all --grep='^Auto-commit$' | wc -l)"
    if [[ "${KNOWN_BARE_COUNT}" -gt 0 ]]; then
        if [[ "${REAL_EXIT}" -eq 1 ]]; then
            pass "default-range scan of THIS repo's real history exits 1 (genuine RD2-00 commits present)"
        else
            fail "default-range scan of THIS repo's real history exited ${REAL_EXIT} (expected 1 — ${KNOWN_BARE_COUNT} known bare 'Auto-commit' commits exist)"
        fi
    else
        echo "  SKIP (§11.4.3): no bare 'Auto-commit' commits reachable in this checkout's history right now"
    fi
else
    echo "  SKIP (§11.4.3): no tag reachable from HEAD in this checkout — default-range mode needs one"
fi

# --- 5: invocation-error path (§11.4.201) — a bogus range fails closed
#     with exit 2, never a false OK. ---
BOGUS_EXIT=0
bash "${GUARD}" --range "not-a-real-ref..also-not-real" >/dev/null 2>&1 || BOGUS_EXIT=$?
if [[ "${BOGUS_EXIT}" -eq 2 ]]; then
    pass "an unresolvable rev-range fails closed with exit 2"
else
    fail "an unresolvable rev-range exited ${BOGUS_EXIT} (expected 2 — fail-closed, §11.4.201)"
fi

echo
echo "=== Result: ${PASS_COUNT} passed, ${FAIL_COUNT} failed ==="
if [[ "${FAIL_COUNT}" -gt 0 ]]; then
    exit 1
fi
exit 0
