#!/usr/bin/env bash
# tests/hooks/test_pre_push_hook.sh — BOB-251 regression guard for the
# tracked pre-push hook (scripts/git_hooks/pre-push) and its installer
# (scripts/install_git_hooks.sh).
#
# Purpose:
#   (1) The hook must never fail silently. Any step that cannot complete
#       prints "pre-push:" + the failing step + the underlying git error +
#       free space of the git directory and of $TMPDIR, and exits non-zero.
#       (BOB-251: `git worktree add ... >/dev/null 2>&1` under set -e aborted
#       with no output when /tmp was full; git printed only "failed to push
#       some refs".)
#   (2) A full or read-only temp directory must not break a healthy push.
#   (3) The §11.4.75 mutation-marker check must actually run on what is
#       being pushed: a production file carrying a marker, committed with
#       --no-verify, must block the push; the same marker in docs/ must not
#       (same scope rules as the pre-commit hook, which the pre-push hook
#       reuses rather than copies).
#   (4) The installer copies the tracked hooks byte-for-byte into .git/hooks.
#
# Usage:
#   bash tests/hooks/test_pre_push_hook.sh
#   HOOKS_SRC=/path/to/git_hooks INSTALLER=/path/to/install_git_hooks.sh \
#       bash tests/hooks/test_pre_push_hook.sh     # e.g. the pre-fix revision
#
# Inputs:   HOOKS_SRC, INSTALLER (optional overrides)
# Outputs:  PASS/FAIL lines, summary, exit 0 all-pass / 1 otherwise
# Side-effects: mktemp sandboxes only (throwaway repo + throwaway local bare
#   remote, isolated git config). Never touches the real repository, its
#   .git/hooks, or its remotes. Everything is removed on exit.
# Dependencies: bash, git, cmp, df, mktemp.
# Cross-references: docs/scripts/install_git_hooks.md, BOB-251,
#   tests/hooks/test_pre_commit_mutation_scope.sh (pre-commit scope rules).

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${HERE}/../.." && pwd)"
HOOKS_SRC="${HOOKS_SRC:-${PROJECT_ROOT}/scripts/git_hooks}"
INSTALLER="${INSTALLER:-${PROJECT_ROOT}/scripts/install_git_hooks.sh}"
REAL_GIT="$(command -v git)"

PASS=0
FAIL=0
pass() { echo "PASS: $*"; PASS=$((PASS + 1)); }
fail() { echo "FAIL: $*"; FAIL=$((FAIL + 1)); }

ROOT_TMP="$(mktemp -d -t pre-push-hook-test.XXXXXX)"
cleanup() { chmod -R u+w "$ROOT_TMP" 2>/dev/null; rm -rf "$ROOT_TMP"; }
trap cleanup EXIT

export GIT_CONFIG_NOSYSTEM=1
export GIT_CONFIG_GLOBAL="$ROOT_TMP/gitconfig"
cat >"$GIT_CONFIG_GLOBAL" <<'EOF'
[user]
	email = test@boba.test
	name = pre-push-hook-test
[init]
	defaultBranch = main
[advice]
	detachedHead = false
EOF

# Marker assembled indirectly so this file never contains the literal.
MARK="MUT""ATED"
ZERO="0000000000000000000000000000000000000000"

# A git shim that fails the sub-commands listed in $SHIM_FAIL the way a full
# disk makes them fail, and forwards everything else to the real git.
SHIM_DIR="$ROOT_TMP/shim"
mkdir -p "$SHIM_DIR"
cat >"$SHIM_DIR/git" <<EOF
#!/usr/bin/env bash
for a in "\$@"; do
    case " \${SHIM_FAIL:-} " in
        *" \$a "*)
            echo "error: unable to write file (simulated \$a failure)" >&2
            echo "fatal: Could not reset index file to revision 'HEAD'." >&2
            exit 128 ;;
    esac
done
exec "$REAL_GIT" "\$@"
EOF
chmod +x "$SHIM_DIR/git"

# new_sandbox <name> -> prints repo path. The sandbox gets copies of the
# hook sources and of the installer, and hooks are installed by running
# that installer copy inside the sandbox (the project's own mechanism).
new_sandbox() {
    local d="$ROOT_TMP/$1"
    mkdir -p "$d/repo/scripts/git_hooks"
    git init -q --bare "$d/remote.git"
    (
        cd "$d/repo" || exit 1
        git init -q
        cp "$HOOKS_SRC"/pre-commit "$HOOKS_SRC"/pre-push "$HOOKS_SRC"/commit-msg \
           "$HOOKS_SRC"/post-commit scripts/git_hooks/
        cp "$INSTALLER" scripts/install_git_hooks.sh
        bash scripts/install_git_hooks.sh
        echo 'echo ok' >scripts/good.sh
        mkdir -p docs && echo base >docs/readme.md
        git add -A
        git commit -q -m baseline
        git remote add origin "$d/remote.git"
        git push -q origin main
    ) >"$d/setup.log" 2>&1
    printf '%s\n' "$d/repo"
}

remote_head() { git --git-dir="$1/../remote.git" rev-parse "${2:-main}" 2>/dev/null; }

# push <repo> <log> [args...] -> RC
push() {
    local repo="$1" log="$2"; shift 2
    RC=0
    (cd "$repo" && git push origin "${@:-main}") >"$log" 2>&1 || RC=$?
}

# invoke_hook <repo> <log> <local_ref> <local_sha> <remote_ref> <remote_sha>
# Runs the INSTALLED hook directly (git itself prepends its exec-path to
# PATH for hooks, which would shadow the shim), with the shim first on PATH.
invoke_hook() {
    local repo="$1" log="$2"
    RC=0
    (cd "$repo" && printf '%s %s %s %s\n' "$3" "$4" "$5" "$6" \
        | PATH="$SHIM_DIR:$PATH" .git/hooks/pre-push origin "$repo/../remote.git") >"$log" 2>&1 || RC=$?
}

echo "=== test_pre_push_hook (HOOKS_SRC=$HOOKS_SRC) ==="

# ── H0: installer copies the tracked pre-push byte-for-byte ─────────────
R="$(new_sandbox h0)"
if cmp -s "$HOOKS_SRC/pre-push" "$R/.git/hooks/pre-push" && [ -x "$R/.git/hooks/pre-push" ]; then
    pass "H0 installer installed an executable, byte-identical .git/hooks/pre-push"
else
    fail "H0 installer did not install the tracked pre-push byte-for-byte (see $R/../setup.log)"
fi

# ── H1: healthy control push ─────────────────────────────────────────────
R="$(new_sandbox h1)"
(cd "$R" && echo 'echo two' >scripts/two.sh && git add -A && git commit -q -m two)
push "$R" "$ROOT_TMP/h1.log"
if [ "$RC" -eq 0 ] && [ "$(remote_head "$R")" = "$(cd "$R" && git rev-parse HEAD)" ]; then
    pass "H1 control: clean push succeeds and updates the remote"
else
    fail "H1 control: rc=$RC"; sed 's/^/    /' "$ROOT_TMP/h1.log"
fi

# ── H2: production marker committed past pre-commit must block the push ──
R="$(new_sandbox h2)"
before="$(remote_head "$R")"
(cd "$R" && printf '# %s leftover\necho bad\n' "$MARK" >scripts/bad.sh && git add -A && git commit -q --no-verify -m bad)
push "$R" "$ROOT_TMP/h2.log"
if [ "$RC" -ne 0 ] && [ "$(remote_head "$R")" = "$before" ] && grep -q "scripts/bad.sh" "$ROOT_TMP/h2.log"; then
    pass "H2 production marker in a pushed commit blocks the push and names the file"
else
    fail "H2 production marker: rc=$RC remote-updated=$([ "$(remote_head "$R")" = "$before" ] && echo no || echo YES) (the §11.4.75 push check must see pushed content)"
    sed 's/^/    /' "$ROOT_TMP/h2.log"
fi

# ── H3: same marker in docs/ is out of scope (pre-commit scope rules) ────
R="$(new_sandbox h3)"
(cd "$R" && printf 'prose about %s tests\n' "$MARK" >docs/method.md && git add -A && git commit -q -m docs)
push "$R" "$ROOT_TMP/h3.log"
if [ "$RC" -eq 0 ]; then
    pass "H3 marker in docs/ does not block the push (scope parity with pre-commit)"
else
    fail "H3 docs marker blocked the push: rc=$RC"; sed 's/^/    /' "$ROOT_TMP/h3.log"
fi

# ── H4: marker added then removed inside the pushed range → allowed ──────
R="$(new_sandbox h4)"
(cd "$R" && printf '# %s\n' "$MARK" >scripts/tmp.sh && git add -A && git commit -q --no-verify -m add \
    && echo 'echo clean' >scripts/tmp.sh && git commit -q -am clean)
push "$R" "$ROOT_TMP/h4.log"
if [ "$RC" -eq 0 ]; then
    pass "H4 marker removed before the pushed tip does not block"
else
    fail "H4 cleaned-up marker blocked the push: rc=$RC"; sed 's/^/    /' "$ROOT_TMP/h4.log"
fi

# ── H5: read-only temp directory must not break a healthy push ───────────
R="$(new_sandbox h5)"
RO="$ROOT_TMP/readonly-tmp"; mkdir -p "$RO"; chmod 555 "$RO"
(cd "$R" && echo 'echo five' >scripts/five.sh && git add -A && git commit -q -m five)
RC=0
(cd "$R" && TMPDIR="$RO" git push origin main) >"$ROOT_TMP/h5.log" 2>&1 || RC=$?
if [ "$RC" -eq 0 ]; then
    pass "H5 unwritable TMPDIR does not break a healthy push"
elif grep -q "pre-push:" "$ROOT_TMP/h5.log"; then
    fail "H5 unwritable TMPDIR: push refused loudly (rc=$RC) — acceptable only if the hook needs temp space; it should not"
else
    fail "H5 unwritable TMPDIR: push failed SILENTLY (rc=$RC, no pre-push message) — the BOB-251 defect"
    sed 's/^/    /' "$ROOT_TMP/h5.log"
fi
chmod 755 "$RO"

# ── H6: the observed failure — worktree creation fails (full tmpfs) ──────
R="$(new_sandbox h6)"
(cd "$R" && echo 'echo six' >scripts/six.sh && git add -A && git commit -q -m six)
L="$(cd "$R" && git rev-parse HEAD)"; B="$(remote_head "$R")"
SHIM_FAIL="worktree" invoke_hook "$R" "$ROOT_TMP/h6.log" refs/heads/main "$L" refs/heads/main "$B"
if [ "$RC" -eq 0 ]; then
    pass "H6 a failing 'git worktree add' cannot break the hook (no worktree needed)"
elif grep -q "pre-push:" "$ROOT_TMP/h6.log" && grep -q "unable to write file" "$ROOT_TMP/h6.log"; then
    pass "H6 a failing 'git worktree add' is reported loudly with the git error"
else
    fail "H6 failing 'git worktree add': rc=$RC with $(wc -c <"$ROOT_TMP/h6.log") bytes of output — silent failure (BOB-251)"
fi

# ── H7: an object-read failure inside the hook is loud and named ─────────
R="$(new_sandbox h7)"
(cd "$R" && echo 'echo seven' >scripts/seven.sh && git add -A && git commit -q -m seven)
L="$(cd "$R" && git rev-parse HEAD)"; B="$(remote_head "$R")"
SHIM_FAIL="ls-tree show cat-file diff-tree rev-list worktree" TMPDIR="$ROOT_TMP" \
    invoke_hook "$R" "$ROOT_TMP/h7.log" refs/heads/main "$L" refs/heads/main "$B"
if [ "$RC" -ne 0 ] && grep -q "pre-push:" "$ROOT_TMP/h7.log" \
   && grep -q "unable to write file" "$ROOT_TMP/h7.log" \
   && grep -qi "step" "$ROOT_TMP/h7.log" \
   && grep -q "$ROOT_TMP" "$ROOT_TMP/h7.log" && grep -qi "free" "$ROOT_TMP/h7.log"; then
    pass "H7 git failure inside the hook: non-zero, names the step, shows the git error and free space incl. TMPDIR"
else
    fail "H7 git failure inside the hook: rc=$RC; output:"
    sed 's/^/    /' "$ROOT_TMP/h7.log"
fi

# ── H7b: a failing content read is an error, never "no marker found" ────
# Only the tree/blob reads fail, so the hook gets as far as scanning; an
# implementation that treats an unreadable file as absent would pass here.
R="$(new_sandbox h7b)"
(cd "$R" && echo 'echo seven b' >scripts/sevenb.sh && git add -A && git commit -q -m sevenb)
L="$(cd "$R" && git rev-parse HEAD)"; B="$(remote_head "$R")"
SHIM_FAIL="ls-tree show" invoke_hook "$R" "$ROOT_TMP/h7b.log" refs/heads/main "$L" refs/heads/main "$B"
if [ "$RC" -eq 2 ] && grep -q "pre-push: FAILED at step 'scan pushed files" "$ROOT_TMP/h7b.log" \
   && grep -q "unable to write file" "$ROOT_TMP/h7b.log"; then
    pass "H7b unreadable pushed content is reported as an error (exit 2), not as clean"
else
    fail "H7b unreadable pushed content: rc=$RC; output:"
    sed 's/^/    /' "$ROOT_TMP/h7b.log"
fi

# ── H8: new branch (remote sha all zeros) is checked too ─────────────────
R="$(new_sandbox h8)"
(cd "$R" && git checkout -q -b topic && printf '# %s\n' "$MARK" >scripts/topic.sh && git add -A && git commit -q --no-verify -m topic)
push "$R" "$ROOT_TMP/h8.log" topic
if [ "$RC" -ne 0 ] && grep -q "scripts/topic.sh" "$ROOT_TMP/h8.log"; then
    pass "H8 marker on a brand-new branch blocks its first push"
else
    fail "H8 new-branch marker: rc=$RC"; sed 's/^/    /' "$ROOT_TMP/h8.log"
fi

# ── H9: branch deletion (local sha all zeros) passes ─────────────────────
R="$(new_sandbox h9)"
(cd "$R" && git checkout -q -b gone && git push -q origin gone && git checkout -q main) >/dev/null 2>&1
push "$R" "$ROOT_TMP/h9.log" --delete gone
if [ "$RC" -eq 0 ]; then
    pass "H9 branch deletion push passes"
else
    fail "H9 branch deletion: rc=$RC"; sed 's/^/    /' "$ROOT_TMP/h9.log"
fi

# ── H10: direct invocation with a deletion line (zero local sha) passes ──
R="$(new_sandbox h10)"
invoke_hook "$R" "$ROOT_TMP/h10.log" "(delete)" "$ZERO" refs/heads/x "$(remote_head "$R")"
if [ "$RC" -eq 0 ]; then
    pass "H10 zero local sha (deletion) needs no check"
else
    fail "H10 deletion line: rc=$RC"; sed 's/^/    /' "$ROOT_TMP/h10.log"
fi

echo
echo "Total: PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ]
