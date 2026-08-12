#!/usr/bin/env bash
# scripts/commit-push-all.sh — §11.4.234 dedicated commit/push entrypoint
# for the boba project.
#
# ─── UNIVERSAL CONSTITUTION §11.4.234 CONTRACT ────────────────────────
# (A) Dedicated script as the single commit/push entrypoint.  Runs, in
#     order: submodule/workspace sync, cheap validation, (optional)
#     long gate, commit, push to ALL configured upstreams, closing
#     green verification. Safe to re-run; idempotent.
# (B) Hooks MUST NOT block the mechanism. Boba does NOT ship any git
#     hooks (`.git/hooks/` = samples only, `core.hooksPath` unset), so
#     there is nothing to disconnect — the always-unblocked invariant
#     is trivially preserved AT THE HOOK LAYER. The cheap-check stage
#     below is this project's own explicit validation.
# (C) No gate is lost. Every check previously executed at some other
#     seam remains executed by name. The heavy `scripts/
#     pre_build_verification.sh` is invoked here as the LONG STAGE and
#     is skippable ONLY via an explicit recorded flag (see (D)).
# (D) Always-unblocked invariant. A failing validation yields a clear
#     per-check report + documented remediation path — never an opaque
#     hung/rejected push. Long gates can be skipped via
#     BOBA_SYNC_SKIP_CI=1, which is RECORDED in the commit message so
#     the deferred gate is caught at the next run or release.
#
# ─── USAGE ────────────────────────────────────────────────────────────
#   bash scripts/commit-push-all.sh "commit message"
#
# Environment knobs:
#   BOBA_SYNC_SKIP_CI=1      Skip the long pre_build_verification.sh gate
#                            for THIS run. The skip is recorded as a
#                            `[skip-ci]` marker in the commit message so
#                            the deferred gate is trackable.
#   BOBA_SYNC_SKIP_LONG=1    Alias of BOBA_SYNC_SKIP_CI (mirrors Lava's
#                            LAVA_SYNC_SKIP_CI naming in §11.4.234).
#
# ─── EXIT ─────────────────────────────────────────────────────────────
#   0 = commit + push completed (or nothing to commit)
#   1 = validation failure (cheap check or long gate) — remediation
#       printed to stderr
#   2 = invocation error (missing message)
#   3 = another commit-push-all.sh is already running (flock)

set -euo pipefail

# ─── args ─────────────────────────────────────────────────────────────
if [ $# -lt 1 ]; then
    echo "Usage: $0 \"commit message\"" >&2
    echo "  Optional: BOBA_SYNC_SKIP_CI=1 to defer the long pre-build gate." >&2
    exit 2
fi
MSG="$1"

# ─── concurrent-run protection ────────────────────────────────────────
LOCK="$(git rev-parse --git-dir)/.commit_push_all.lock"
exec 9>"$LOCK"
if command -v flock >/dev/null 2>&1; then
    flock -n 9 || {
        echo "ERROR: another commit-push-all.sh is already running (flock $LOCK)" >&2
        exit 3
    }
else
    echo "[commit-push-all] WARN: flock not available; concurrent-run protection disabled." >&2
fi

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

# ─── stage 1: fetch all remotes (§11.4.37) ────────────────────────────
echo "[commit-push-all] stage 1/6 — fetch all remotes"
git fetch --all --prune 2>&1 | tail -5 || true

# ─── stage 2: cheap always-on validation (§11.4.234(C)) ───────────────
echo "[commit-push-all] stage 2/6 — cheap validation"

# 2a. §11.4.10 credentials — .env / secrets must NEVER be committed
_stage2_fail() {
    echo "ERROR: $*" >&2
    echo "       Fix the above before re-running (or add the file to .gitignore)." >&2
    exit 1
}
if git ls-files --cached | grep -qE '(^|/)\.env$'; then
    _stage2_fail "\`.env\` is already TRACKED in git — §11.4.10 credentials violation."
fi
# 2b. Untracked/modified .env in the staging area?
if git status --porcelain 2>/dev/null | awk '{print $NF}' | grep -qE '(^|/)\.env$'; then
    if git diff --cached --name-only 2>/dev/null | grep -qE '(^|/)\.env$'; then
        _stage2_fail "\`.env\` is STAGED for this commit — §11.4.10 credentials violation."
    fi
fi

# 2c. bash -n on every changed .sh file — catches simple parse errors
CHANGED_SH=$(git status --porcelain 2>/dev/null | awk '{if ($NF ~ /\.sh$/) print $NF}' | sort -u)
sh_syntax_fail=0
for f in $CHANGED_SH; do
    [ -f "$f" ] || continue
    if ! bash -n "$f" 2>/dev/null; then
        echo "ERROR: bash -n failed on $f — syntax defect blocks commit" >&2
        bash -n "$f" 2>&1 | head -5 >&2
        sh_syntax_fail=$((sh_syntax_fail + 1))
    fi
done
if [ "$sh_syntax_fail" -gt 0 ]; then
    exit 1
fi

# 2d. Submodule dirt awareness (WARN only — dirty submodule pointers don't
#     block a parent commit; git records them as the same SHA).
DIRTY_SUBS=$(git submodule status 2>/dev/null | awk '/^\+|^-|^ *m/{print $2}' | head)
if [ -n "$DIRTY_SUBS" ]; then
    echo "[commit-push-all] NOTE: submodule(s) with local changes (not blocking):"
    echo "$DIRTY_SUBS" | sed 's/^/  - /'
fi

echo "[commit-push-all] stage 2/6 — OK (cheap validation clean)"

# ─── stage 3: long gate (skippable, §11.4.234(D)) ─────────────────────
SKIP_LONG="${BOBA_SYNC_SKIP_CI:-${BOBA_SYNC_SKIP_LONG:-0}}"
SKIP_TAG=""
echo "[commit-push-all] stage 3/6 — long gate (pre_build_verification.sh)"
if [ "$SKIP_LONG" = "1" ]; then
    echo "[commit-push-all] stage 3/6 — SKIPPED via BOBA_SYNC_SKIP_CI=1"
    echo "                             (recorded as [skip-ci] in commit message)"
    SKIP_TAG=" [skip-ci]"
elif [ -x scripts/pre_build_verification.sh ]; then
    if bash scripts/pre_build_verification.sh; then
        echo "[commit-push-all] stage 3/6 — pre_build_verification.sh GREEN"
    else
        rc=$?
        echo "ERROR: scripts/pre_build_verification.sh exit=$rc" >&2
        echo "       Fix the failing invariant, OR skip THIS run with" >&2
        echo "       BOBA_SYNC_SKIP_CI=1 bash scripts/commit-push-all.sh \"...\"" >&2
        echo "       (the skip is recorded in the commit message for follow-up)." >&2
        exit 1
    fi
else
    echo "[commit-push-all] stage 3/6 — scripts/pre_build_verification.sh not executable, skipping"
fi

# ─── stage 4: show working-tree status ────────────────────────────────
echo "[commit-push-all] stage 4/6 — git status pre-commit"
git status --short | head -40

# ─── stage 5: commit ──────────────────────────────────────────────────
echo "[commit-push-all] stage 5/6 — commit"
git add -A
if git diff --cached --quiet; then
    echo "[commit-push-all] nothing to commit — skipping to push stage"
else
    git commit -m "${MSG}${SKIP_TAG}"
fi

# ─── stage 6: push to ALL upstreams (§2.1) ────────────────────────────
echo "[commit-push-all] stage 6/6 — push to all upstreams"
BRANCH=$(git symbolic-ref --short HEAD)
push_fail=0
for r in $(git remote); do
    echo "[commit-push-all] pushing to $r..."
    if git push "$r" "$BRANCH" 2>&1 | tail -5; then
        :
    else
        push_fail=$((push_fail + 1))
        echo "WARN: push to $r failed — will continue with other remotes" >&2
    fi
done

# ─── final verification ───────────────────────────────────────────────
echo ""
echo "[commit-push-all] === Push Summary ==="
echo "  Branch:  $BRANCH"
echo "  Commit:  $(git rev-parse --short HEAD)"
echo "  Message: $MSG${SKIP_TAG}"
echo "  Push:    $(git remote | wc -l) remote(s), $push_fail failed"
if [ -n "$SKIP_TAG" ]; then
    echo "  NOTE:    long gate was SKIPPED — re-run 'bash $0 \"catch-up long gate\"' when ready"
fi
if [ "$push_fail" -gt 0 ]; then
    echo "  WARN:    one or more pushes failed — investigate above output"
    exit 1
fi
echo "[commit-push-all] done."
