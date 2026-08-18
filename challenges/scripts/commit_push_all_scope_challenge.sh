#!/usr/bin/env bash
# commit_push_all_scope_challenge.sh — task #66 / BOB-068 sweep-pattern
# remedy proof for `scripts/commit-push-all.sh --scope <path>`.
#
# BOB-068 (discovered 5x in one session): commit-push-all.sh's default
# `git add -A` sweeps ANY in-flight change in the working tree — e.g. a
# concurrent parallel-subagent's not-yet-committed file — into an
# unrelated commit (a real §11.4.84 quiescence violation). `--scope`
# opts a caller into a scoped `git add` PLUS a safety check that
# REJECTS the commit if anything outside the declared scope ends up
# staged. This challenge proves that safety check is real and
# load-bearing.
#
# Runs entirely against a THROWAWAY sandbox git repo with zero remotes
# (mktemp -d, git init) — NEVER touches the real boba repo, NEVER
# pushes anywhere. scripts/commit-push-all.sh resolves its own
# REPO_ROOT via `git rev-parse --show-toplevel` from the invocation
# cwd, so pointing cwd at the sandbox is sufficient isolation.
#
# EXPECT:
#   Step A (always runs): a genuine single-scope commit via --scope
#     succeeds cleanly (exit 0) and the landed commit contains EXACTLY
#     the declared path — nothing more, nothing less.
#   Step B (RED polarity, RED_MODE=1 default): reproduce the BOB-068
#     hazard — a second, out-of-scope file is ALREADY staged before
#     --scope runs (simulating a concurrent subagent's own `git add`,
#     or residue from a stray earlier unscoped run) — and confirm
#     --scope REJECTS (non-zero exit), names the unexpected file in
#     its error output, and leaves NO new commit behind.
#
# CONST-XII / §11.4.115 anti-bluff polarity:
#   RED_MODE=1 (default) — Step A + Step B both run. Step B is the
#     defect-reproduction: against a no-op/stripped implementation
#     (the scope-verification check removed) this step would silently
#     SUCCEED and sweep the out-of-scope file into the commit —
#     exactly the BOB-068 hazard this feature exists to prevent. On
#     the real, fixed script it MUST reject.
#   RED_MODE=0 — Step A only (lightweight regression-guard: proves the
#     normal single-scope path still works, for fast CI reruns).
#
# §1.1 mutation (verified manually during task #66 implementation, see
# .superpowers/sdd/task-66-report.md for the pasted terminal proof):
# stripping the "--scope safety check" block from
# scripts/commit-push-all.sh and re-running Step B's exact procedure
# against the mutated copy makes the sweep silently succeed — proving
# the check is load-bearing, not decorative.
#
# Pass: PASS message + exit 0
# Fail: FAIL: <reason> + exit 1
# Skip: SKIP: <reason> + exit 0 (§11.4.3 — SUT script missing)

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SUT="${REPO_ROOT}/scripts/commit-push-all.sh"
RED_MODE="${RED_MODE:-1}"

echo "=== commit_push_all_scope_challenge ==="

if [ ! -e "$SUT" ]; then
    echo "SKIP: $SUT missing"
    exit 0
fi
if [ ! -x "$SUT" ] && ! bash -n "$SUT" 2>/dev/null; then
    echo "SKIP: $SUT not executable and does not parse — nothing to challenge"
    exit 0
fi

PASS_COUNT=0
FAIL_COUNT=0
declare -a FAIL_DETAILS=()
assert_pass() { echo "PASS: $*"; PASS_COUNT=$((PASS_COUNT + 1)); }
assert_fail() { echo "FAIL: $*"; FAIL_COUNT=$((FAIL_COUNT + 1)); FAIL_DETAILS+=("$*"); }

SANDBOX="$(mktemp -d -t commit-push-all-scope-challenge.XXXXXX)"
cleanup() { rm -rf "$SANDBOX"; }
trap cleanup EXIT

# ── sandbox bootstrap: isolated repo, zero remotes, one baseline commit ──
(
    cd "$SANDBOX" || exit 1
    git init -q
    git config user.email "challenge@boba.test"
    git config user.name "commit_push_all_scope_challenge"
    echo "sandbox baseline" >README.md
    git add README.md
    git commit -q -m "baseline"
) >/dev/null 2>&1

if [ ! -d "$SANDBOX/.git" ]; then
    echo "SKIP: could not bootstrap an isolated sandbox git repo (git init failed)"
    exit 0
fi

BASE_SHA="$(cd "$SANDBOX" && git rev-parse HEAD)"

# ─────────────────────────────────────────────────────────────────────
# Step A (always runs): genuine single-scope commit succeeds cleanly.
# ─────────────────────────────────────────────────────────────────────
echo "[A] genuine single-scope commit via --scope (EXPECT exit 0, exactly 1 file committed)"

(cd "$SANDBOX" && echo "in-scope content" >in_scope.txt) >/dev/null 2>&1

A_LOG="$(mktemp)"
A_EXIT=0
(cd "$SANDBOX" && bash "$SUT" --scope in_scope.txt "scoped commit A") >"$A_LOG" 2>&1 || A_EXIT=$?

if [ "$A_EXIT" -ne 0 ]; then
    assert_fail "Step A: --scope with a genuinely single-file scope should exit 0, got $A_EXIT"
    sed 's/^/       /' "$A_LOG"
else
    NEW_SHA_A="$(cd "$SANDBOX" && git rev-parse HEAD)"
    if [ "$NEW_SHA_A" = "$BASE_SHA" ]; then
        assert_fail "Step A: exit 0 but no new commit landed"
    else
        COMMITTED_A="$(cd "$SANDBOX" && git diff-tree --no-commit-id --name-only -r "$NEW_SHA_A")"
        if [ "$COMMITTED_A" = "in_scope.txt" ]; then
            assert_pass "Step A: scoped commit landed exactly {in_scope.txt} (${NEW_SHA_A:0:7})"
        else
            assert_fail "Step A: scoped commit landed unexpected file set: [$COMMITTED_A]"
        fi
    fi
fi
rm -f "$A_LOG"

# ─────────────────────────────────────────────────────────────────────
# Step B (RED polarity, default on): concurrent-sweep hazard.
# ─────────────────────────────────────────────────────────────────────
if [ "$RED_MODE" != "0" ]; then
    echo "[B] RED polarity: concurrent-sweep hazard — out-of-scope file already staged"
    echo "    (EXPECT --scope REJECTS: non-zero exit, names the file, no new commit)"

    BASE_SHA_B="$(cd "$SANDBOX" && git rev-parse HEAD)"
    (
        cd "$SANDBOX" || exit 1
        echo "in-scope content v2" >in_scope.txt
        # Simulates a concurrent subagent's own work (or residue from a
        # stray earlier unscoped run) landing in the index BEFORE this
        # scoped commit runs — the exact BOB-068 precondition.
        echo "concurrent subagent work — must NEVER be swept in" >out_of_scope.txt
        git add out_of_scope.txt
    ) >/dev/null 2>&1

    B_LOG="$(mktemp)"
    B_EXIT=0
    (cd "$SANDBOX" && bash "$SUT" --scope in_scope.txt "scoped commit B") >"$B_LOG" 2>&1 || B_EXIT=$?

    if [ "$B_EXIT" -eq 0 ]; then
        assert_fail "Step B: --scope SILENTLY SUCCEEDED while out_of_scope.txt was staged — the BOB-068 sweep hazard is NOT caught (this is the exact bluff the check exists to prevent)"
        sed 's/^/       /' "$B_LOG"
    else
        AFTER_SHA_B="$(cd "$SANDBOX" && git rev-parse HEAD)"
        if [ "$AFTER_SHA_B" != "$BASE_SHA_B" ]; then
            assert_fail "Step B: --scope exited non-zero ($B_EXIT) but STILL created a commit (${AFTER_SHA_B:0:7}) — reject-after-commit is worse than a clean reject"
        elif ! grep -q "out_of_scope.txt" "$B_LOG"; then
            assert_fail "Step B: rejection happened (exit $B_EXIT, no new commit) but the error output does not NAME out_of_scope.txt — not actionable per task #66 spec"
            sed 's/^/       /' "$B_LOG"
        else
            assert_pass "Step B: --scope correctly REJECTED (exit $B_EXIT), named out_of_scope.txt, left no new commit"
        fi
    fi
    rm -f "$B_LOG"
else
    echo "[B] RED_MODE=0 — skipping the concurrent-sweep hazard reproduction (regression-guard mode)"
fi

echo
echo "Total: PASS=$PASS_COUNT FAIL=$FAIL_COUNT"
if [ "$FAIL_COUNT" -gt 0 ]; then
    echo "FAIL: commit_push_all_scope_challenge — ${FAIL_DETAILS[*]}"
    exit 1
fi
echo "PASS: commit_push_all_scope_challenge — --scope safety layer proven (BOB-068 hazard caught, normal scoped path clean)"
exit 0
