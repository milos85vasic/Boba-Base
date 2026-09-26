#!/usr/bin/env bash
# tests/unit/test_commit_push_all_args.sh — BOB-246 regression guard for
# scripts/commit-push-all.sh argument parsing and commit-message fidelity.
#
# Purpose:
#   (1) A --scope flag placed AFTER the commit message must be honoured —
#       never silently dropped with a fall-back to an unscoped `git add -A`
#       that sweeps unrelated files into the commit (the BOB-246 hazard).
#   (2) The commit message must land byte-for-byte: backticks, $(...),
#       quotes, newlines, blank lines, trailing whitespace and '#' lines.
#   (3) Malformed invocations (extra positional arguments, a --scope token
#       after `--`, message given twice) are REFUSED with exit 2 and leave
#       no commit behind.
#   (4) Controls: flags-first scoped commit, unscoped `git add -A` default,
#       and a push to a local bare remote all keep working.
#
# Usage:
#   bash tests/unit/test_commit_push_all_args.sh
#   SUT=/path/to/other/commit-push-all.sh bash tests/unit/test_commit_push_all_args.sh
#       (run the same assertions against another copy, e.g. the pre-fix
#        revision, to capture the RED baseline)
#
# Inputs:   SUT (optional) — wrapper under test; default scripts/commit-push-all.sh
# Outputs:  PASS/FAIL lines on stdout, summary line, exit 0 (all pass) / 1
# Side-effects: creates and removes mktemp sandboxes only. Every sandbox is a
#   throwaway repository whose ONLY remote is a throwaway local bare repo, and
#   GIT_CONFIG_GLOBAL/GIT_CONFIG_NOSYSTEM isolate it from the operator's git
#   configuration. The real boba repository and its remotes are never touched.
# Dependencies: bash, git, cmp, mktemp.
# Cross-references: docs/scripts/commit-push-all.md, BOB-246,
#   challenges/scripts/commit_push_all_scope_challenge.sh (BOB-068 layer).

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SUT="${SUT:-${REPO_ROOT}/scripts/commit-push-all.sh}"

PASS=0
FAIL=0
pass() { echo "PASS: $*"; PASS=$((PASS + 1)); }
fail() { echo "FAIL: $*"; FAIL=$((FAIL + 1)); }

ROOT_TMP="$(mktemp -d -t commit-push-all-args.XXXXXX)"
trap 'rm -rf "$ROOT_TMP"' EXIT

export GIT_CONFIG_NOSYSTEM=1
export GIT_CONFIG_GLOBAL="$ROOT_TMP/gitconfig"
cat >"$GIT_CONFIG_GLOBAL" <<'EOF'
[user]
	email = test@boba.test
	name = commit-push-all-args-test
[init]
	defaultBranch = main
EOF

# new_sandbox <name> -> prints path; repo with one baseline commit and a
# local bare remote named "origin" (so stage 6 genuinely pushes somewhere
# harmless and pushes can be asserted).
new_sandbox() {
    local d="$ROOT_TMP/$1"
    mkdir -p "$d"
    git init -q --bare "$d/remote.git"
    git init -q "$d/repo"
    (
        cd "$d/repo" || exit 1
        echo base >README
        git add README
        git commit -q -m baseline
        git remote add origin "$d/remote.git"
        git push -q origin main
    ) >/dev/null 2>&1
    printf '%s\n' "$d/repo"
}

# committed_files <repo> -> sorted file list of HEAD commit
committed_files() {
    (cd "$1" && git diff-tree --no-commit-id --name-only -r HEAD | sort | tr '\n' ' ')
}

# run_sut <repo> <logfile> args... -> sets RC
run_sut() {
    local repo="$1" log="$2"; shift 2
    RC=0
    (cd "$repo" && BOBA_SYNC_SKIP_CI="${SKIP:-1}" bash "$SUT" "$@") >"$log" 2>&1 || RC=$?
}

# message_bytes <repo> <outfile> -> raw commit message bytes of HEAD
message_bytes() {
    (cd "$1" && git cat-file commit HEAD | sed '1,/^$/d') >"$2"
}

echo "=== test_commit_push_all_args (SUT=$SUT) ==="

# ── T1: message FIRST, --scope AFTER — must be honoured ──────────────────
R="$(new_sandbox t1)"
(cd "$R" && echo a >a.txt && echo unrelated >b.txt)
run_sut "$R" "$ROOT_TMP/t1.log" "scoped after message" --scope a.txt
got="$(committed_files "$R")"
if [ "$RC" -eq 0 ] && [ "$got" = "a.txt " ]; then
    pass "T1 --scope after the message is honoured (committed: $got)"
else
    fail "T1 --scope after the message: rc=$RC committed=[$got] (BOB-246: must be exactly a.txt, never a git add -A sweep)"
fi

# ── T2: message BETWEEN two --scope flags ────────────────────────────────
R="$(new_sandbox t2)"
(cd "$R" && echo a >a.txt && echo c >c.txt && echo unrelated >b.txt)
run_sut "$R" "$ROOT_TMP/t2.log" --scope a.txt "between scopes" --scope c.txt
got="$(committed_files "$R")"
if [ "$RC" -eq 0 ] && [ "$got" = "a.txt c.txt " ]; then
    pass "T2 --scope on both sides of the message is honoured (committed: $got)"
else
    fail "T2 --scope on both sides: rc=$RC committed=[$got] (expected a.txt c.txt)"
fi

# ── T3: --scope=path form after the message ──────────────────────────────
R="$(new_sandbox t3)"
(cd "$R" && echo a >a.txt && echo unrelated >b.txt)
run_sut "$R" "$ROOT_TMP/t3.log" "equals form after" --scope=a.txt
got="$(committed_files "$R")"
if [ "$RC" -eq 0 ] && [ "$got" = "a.txt " ]; then
    pass "T3 --scope=path after the message is honoured"
else
    fail "T3 --scope=path after the message: rc=$RC committed=[$got]"
fi

# ── T4: extra positional argument → refuse, no commit ───────────────────
R="$(new_sandbox t4)"
(cd "$R" && echo a >a.txt)
before="$(cd "$R" && git rev-parse HEAD)"
run_sut "$R" "$ROOT_TMP/t4.log" "first positional" "second positional"
after="$(cd "$R" && git rev-parse HEAD)"
if [ "$RC" -eq 2 ] && [ "$before" = "$after" ] && grep -q "second positional" "$ROOT_TMP/t4.log"; then
    pass "T4 extra positional argument refused (exit 2, named, no commit)"
else
    fail "T4 extra positional: rc=$RC new-commit=$([ "$before" = "$after" ] && echo no || echo YES) (expected exit 2, no commit, offending token named)"
fi

# ── T5: a --scope token after `--` must never fall back to git add -A ────
R="$(new_sandbox t5)"
(cd "$R" && echo a >a.txt && echo unrelated >b.txt)
before="$(cd "$R" && git rev-parse HEAD)"
run_sut "$R" "$ROOT_TMP/t5.log" -- --scope
after="$(cd "$R" && git rev-parse HEAD)"
if [ "$RC" -eq 2 ] && [ "$before" = "$after" ]; then
    pass "T5 --scope-shaped token after -- refused (exit 2, no commit)"
else
    fail "T5 --scope-shaped token after --: rc=$RC new-commit=$([ "$before" = "$after" ] && echo no || echo YES)"
fi

# ── T6: message fidelity, byte-for-byte (no long-gate skip tag) ──────────
# Built with printf so the TEST's own shell expands nothing: backticks,
# $(...), both quote kinds, trailing spaces, a tab, blank lines, a '#' line.
TRICKY="$(printf 'fix(x): keep the %s guard and %s literally\n\nbody with "double" and '"'"'single'"'"' quotes  \n\n\n# hash-led line\n\tindented\t' '`|| true`' '$(echo hi)')"
printf '%s' "$TRICKY" >"$ROOT_TMP/t6.expected"
R="$(new_sandbox t6)"
(cd "$R" && echo a >a.txt)
SKIP=0 run_sut "$R" "$ROOT_TMP/t6.log" --scope a.txt "$TRICKY"
message_bytes "$R" "$ROOT_TMP/t6.actual"
if [ "$RC" -eq 0 ] && cmp -s "$ROOT_TMP/t6.expected" "$ROOT_TMP/t6.actual"; then
    pass "T6 commit message landed byte-for-byte (backticks, \$(...), quotes, whitespace, newlines)"
else
    fail "T6 message fidelity: rc=$RC; diff expected vs actual:"
    diff <(od -c "$ROOT_TMP/t6.expected") <(od -c "$ROOT_TMP/t6.actual") | head -20
fi

# ── T6b: same message with the recorded long-gate skip ──────────────────
printf '%s [skip-ci]' "$TRICKY" >"$ROOT_TMP/t6b.expected"
R="$(new_sandbox t6b)"
(cd "$R" && echo a >a.txt)
SKIP=1 run_sut "$R" "$ROOT_TMP/t6b.log" --scope a.txt "$TRICKY"
message_bytes "$R" "$ROOT_TMP/t6b.actual"
if [ "$RC" -eq 0 ] && cmp -s "$ROOT_TMP/t6b.expected" "$ROOT_TMP/t6b.actual"; then
    pass "T6b message + recorded [skip-ci] tag landed byte-for-byte"
else
    fail "T6b message+skip fidelity: rc=$RC"
    diff <(od -c "$ROOT_TMP/t6b.expected") <(od -c "$ROOT_TMP/t6b.actual") | head -20
fi

# ── T7: --message-file <path> (no shell quoting of the message at all) ──
R="$(new_sandbox t7)"
(cd "$R" && echo a >a.txt)
SKIP=0 run_sut "$R" "$ROOT_TMP/t7.log" --scope a.txt --message-file "$ROOT_TMP/t6.expected"
message_bytes "$R" "$ROOT_TMP/t7.actual"
if [ "$RC" -eq 0 ] && cmp -s "$ROOT_TMP/t6.expected" "$ROOT_TMP/t7.actual"; then
    pass "T7 --message-file <path> landed byte-for-byte"
else
    fail "T7 --message-file <path>: rc=$RC"
fi

# ── T7b: --message-file - reads stdin ────────────────────────────────────
R="$(new_sandbox t7b)"
(cd "$R" && echo a >a.txt)
RC=0
(cd "$R" && BOBA_SYNC_SKIP_CI=0 bash "$SUT" --scope a.txt --message-file - <"$ROOT_TMP/t6.expected") >"$ROOT_TMP/t7b.log" 2>&1 || RC=$?
message_bytes "$R" "$ROOT_TMP/t7b.actual"
if [ "$RC" -eq 0 ] && cmp -s "$ROOT_TMP/t6.expected" "$ROOT_TMP/t7b.actual"; then
    pass "T7b --message-file - (stdin) landed byte-for-byte"
else
    fail "T7b --message-file -: rc=$RC"
fi

# ── T8: message given twice (file + positional) → refuse ────────────────
R="$(new_sandbox t8)"
(cd "$R" && echo a >a.txt)
before="$(cd "$R" && git rev-parse HEAD)"
run_sut "$R" "$ROOT_TMP/t8.log" --scope a.txt --message-file "$ROOT_TMP/t6.expected" "positional too"
after="$(cd "$R" && git rev-parse HEAD)"
if [ "$RC" -eq 2 ] && [ "$before" = "$after" ]; then
    pass "T8 message supplied twice refused (exit 2, no commit)"
else
    fail "T8 message supplied twice: rc=$RC"
fi

# ── T9: control — flags-first scoped commit + push to bare remote ───────
R="$(new_sandbox t9)"
(cd "$R" && echo a >a.txt && echo unrelated >b.txt)
run_sut "$R" "$ROOT_TMP/t9.log" --scope a.txt "flags first control"
got="$(committed_files "$R")"
local_head="$(cd "$R" && git rev-parse HEAD)"
remote_head="$(git --git-dir="$ROOT_TMP/t9/remote.git" rev-parse main)"
if [ "$RC" -eq 0 ] && [ "$got" = "a.txt " ] && [ "$local_head" = "$remote_head" ]; then
    pass "T9 control: flags-first scoped commit landed and was pushed to the (local bare) remote"
else
    fail "T9 control: rc=$RC committed=[$got] pushed=$([ "$local_head" = "$remote_head" ] && echo yes || echo NO)"
fi

# ── T10: control — unscoped default still stages everything ─────────────
R="$(new_sandbox t10)"
(cd "$R" && echo a >a.txt && echo b >b.txt)
run_sut "$R" "$ROOT_TMP/t10.log" "unscoped default"
got="$(committed_files "$R")"
if [ "$RC" -eq 0 ] && [ "$got" = "a.txt b.txt " ]; then
    pass "T10 control: unscoped invocation keeps the documented git add -A default"
else
    fail "T10 control: rc=$RC committed=[$got]"
fi

# ── T11: missing message → exit 2 ────────────────────────────────────────
R="$(new_sandbox t11)"
run_sut "$R" "$ROOT_TMP/t11.log" --scope README
if [ "$RC" -eq 2 ]; then
    pass "T11 missing message refused (exit 2)"
else
    fail "T11 missing message: rc=$RC (expected 2)"
fi

echo
echo "Total: PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ]
