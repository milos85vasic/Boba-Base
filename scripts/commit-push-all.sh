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
#   bash scripts/commit-push-all.sh --scope <path> [--scope <path>]... "commit message"
#   bash scripts/commit-push-all.sh --scope <path> --scope-allow-partial "commit message"
#
# ─── task #66 / BOB-068 SWEEP-PATTERN REMEDY ──────────────────────────
# Without --scope, stage 5 runs an unconditional `git add -A`, which
# sweeps ANY other in-flight change in the working tree (e.g. a
# concurrent parallel-subagent's not-yet-committed file) into THIS
# commit — a real §11.4.84 quiescence violation, observed 5x in one
# session (BOB-068). `--scope <path>` (repeatable) opts a caller into a
# SCOPED commit instead: only the declared paths are `git add`-ed, and
# a safety check (§11.4.201-style real-condition assertion) verifies
# the resulting staged set contains ONLY paths under the declared
# scope before allowing the commit — if anything else is staged (e.g.
# a stray `git add -A` from an earlier/concurrent run left residue),
# the commit is REJECTED with the exact unexpected paths named, never
# silently swept in. This is the interim tooling fix; the full
# architectural remedy is §11.4.179 isolated-git-streams (task #67
# proposal). Existing callers WITHOUT --scope are unaffected — the
# `git add -A` sweep remains the default for backwards compatibility.
#
# ─── §11.4.209 review MINOR-5 remedy — reverse-BOB-068 check ──────────
# The safety check above catches EXTRA files staged outside the
# declared scope. It did NOT catch the mirror-image hole: the declared
# scope's OWN dirty state being silently left OUT of what got staged
# (e.g. --scope docs/qa/task-99/ declared, but a file under that same
# directory stays untracked/unstaged — a partial, operator-intent-
# truncating commit). Stage 5 now also runs a WARN-only (never FAIL —
# legitimate reasons exist to leave part of a scope unstaged) check
# after staging: any dirty file inside the declared scope that is NOT
# fully staged is named on stderr. `--scope-allow-partial` silences
# this WARN for a caller that has already reviewed and accepts the
# partial state.
#
# Environment knobs:
#   BOBA_SYNC_SKIP_CI=1      Skip the long pre_build_verification.sh gate
#                            for THIS run. The skip is recorded as a
#                            `[skip-ci]` marker in the commit message so
#                            the deferred gate is trackable.
#   BOBA_SYNC_SKIP_LONG=1    Alias of BOBA_SYNC_SKIP_CI (mirrors Lava's
#                            LAVA_SYNC_SKIP_CI naming in §11.4.234).
#
# ─── §11.4.209 review IMPORTANT-2 remedy — DB delta capture (stage 5.5) ─
# If the commit just landed touches docs/workable_items.db (the §11.4.95
# tracked SSoT database), a message-level claim about its content (e.g.
# "meta table unchanged") is an opaque ARTIFACT-class fact per §11.4.226
# evidence-class-at-closure — never sufficient on its own, and the exact
# gap the same session's Task #41/BOB-068 investigation showed is
# concrete (shared-checkout races on this file). Stage 5.5 invokes
# scripts/capture-workable-items-db-delta.sh AFTER the commit lands but
# BEFORE push, and — when it produces a NEW evidence file — lands that
# file as an immediate scoped follow-up commit so both travel to every
# upstream together in this same run. Capture failure (e.g. sqlite3
# absent) is a non-blocking WARN per the §11.4.234(D) always-unblocked
# invariant — this is evidence capture, not a correctness gate, and it
# must never make the commit/push mechanism unusable. See task #79.
#
# ─── EXIT ─────────────────────────────────────────────────────────────
#   0 = commit + push completed (or nothing to commit)
#   1 = validation failure (cheap check, long gate, or --scope safety
#       check) — remediation printed to stderr
#   2 = invocation error (missing message / malformed --scope)
#   3 = another commit-push-all.sh is already running (flock)

set -euo pipefail

# ─── args ─────────────────────────────────────────────────────────────
SCOPES=()
SCOPE_ALLOW_PARTIAL=0
while [ $# -gt 0 ]; do
    case "$1" in
        --scope)
            if [ $# -lt 2 ] || [ -z "${2:-}" ]; then
                echo "ERROR: --scope requires a non-empty path argument" >&2
                exit 2
            fi
            SCOPES+=("$2")
            shift 2
            ;;
        --scope=*)
            v="${1#--scope=}"
            if [ -z "$v" ]; then
                echo "ERROR: --scope= requires a non-empty path" >&2
                exit 2
            fi
            SCOPES+=("$v")
            shift
            ;;
        --scope-allow-partial)
            # §11.4.209 review MINOR-5: silences the reverse-BOB-068 WARN
            # (declared scope has dirty file(s) that were NOT staged) for a
            # caller that has already reviewed the partial state and
            # confirms it is intentional (e.g. a WIP file under the same
            # directory that isn't ready yet). Never affects the existing
            # --scope safety check (unexpected files OUTSIDE scope still
            # REJECT unconditionally).
            SCOPE_ALLOW_PARTIAL=1
            shift
            ;;
        --)
            shift
            break
            ;;
        -*)
            echo "ERROR: unknown flag: $1" >&2
            echo "Usage: $0 [--scope <path>]... [--scope-allow-partial] \"commit message\"" >&2
            exit 2
            ;;
        *)
            break
            ;;
    esac
done

if [ $# -lt 1 ]; then
    echo "Usage: $0 [--scope <path>]... [--scope-allow-partial] \"commit message\"" >&2
    echo "  --scope <path>          Repeatable. Only stage these path(s) —" >&2
    echo "                          NEVER 'git add -A'. See task #66." >&2
    echo "  --scope-allow-partial   Silence the WARN when part of a declared" >&2
    echo "                          --scope is left dirty/unstaged (reverse-" >&2
    echo "                          BOB-068 check, §11.4.209 review MINOR-5)." >&2
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
# Captured BEFORE either commit branch runs so stage 5.5 (below) can
# tell whether a NEW commit actually landed, and if so, whether ITS
# diff touches docs/workable_items.db.
PRE_COMMIT_HEAD="$(git rev-parse HEAD 2>/dev/null || echo "")"

# §11.4.201-style real-condition assertion for the --scope safety layer:
# a path is "in scope" iff it EQUALS a declared scope entry, or sits
# UNDER one (declared entry is a directory prefix). Never a substring
# match (§11.4.201(7)(a) — match structure, not substring).
_scope_contains() {
    # $1 = staged path, remaining args = declared scope entries
    local path="$1"; shift
    local s
    for s in "$@"; do
        s="${s%/}"        # normalize a trailing slash on a directory scope
        s="${s#./}"       # normalize a leading ./
        if [ "$path" = "$s" ] || [ "${path#"$s"/}" != "$path" ]; then
            return 0
        fi
    done
    return 1
}

if [ "${#SCOPES[@]}" -gt 0 ]; then
    echo "[commit-push-all] stage 5/6 — SCOPED commit (--scope mode, ${#SCOPES[@]} path(s) declared)"
    for s in "${SCOPES[@]}"; do
        echo "                             scope: $s"
    done
    git add -- "${SCOPES[@]}"

    # ── §11.4.201 safety check: staged set MUST be a subset of the
    #    declared scope. If anything else is staged — e.g. residue from
    #    a stray `git add -A` in-flight elsewhere — REJECT (BOB-068).
    STAGED_FILES="$(git diff --cached --name-only)"
    UNEXPECTED=()
    while IFS= read -r f; do
        [ -z "$f" ] && continue
        if ! _scope_contains "$f" "${SCOPES[@]}"; then
            UNEXPECTED+=("$f")
        fi
    done <<<"$STAGED_FILES"

    if [ "${#UNEXPECTED[@]}" -gt 0 ]; then
        echo "ERROR: --scope safety check FAILED — staged file(s) OUTSIDE the declared scope:" >&2
        for f in "${UNEXPECTED[@]}"; do
            echo "  - $f" >&2
        done
        echo "       Declared scope: ${SCOPES[*]}" >&2
        echo "       This is the exact BOB-068 sweep pattern --scope exists to prevent —" >&2
        echo "       a concurrent process (or a stray earlier 'git add -A') left" >&2
        echo "       unrelated work staged. NOT committing." >&2
        echo "       Remediation: inspect + unstage the file(s) above yourself" >&2
        echo "       ('git restore --staged <file>'), then re-run this command." >&2
        exit 1
    fi
    echo "[commit-push-all] stage 5/6 — --scope safety check OK (staged set == declared scope)"

    # ── §11.4.209 review MINOR-5: reverse-BOB-068 check — the mirror image
    #    of the check above. That check catches EXTRA files staged outside
    #    the declared scope; this one catches the declared scope's OWN
    #    dirty state being SILENTLY left OUT of what actually got staged
    #    (e.g. a caller declares --scope docs/qa/task-99/ but a file under
    #    that same directory stays untracked/unstaged — the operator's
    #    intent silently truncated, the same category of scope-safety hole
    #    as BOB-068, just in the opposite direction). WARN, never FAIL —
    #    legitimate reasons exist to leave part of a declared scope
    #    unstaged (a WIP file not yet ready); --scope-allow-partial
    #    silences this WARN for a caller that has already reviewed and
    #    accepts the partial state.
    if [ "$SCOPE_ALLOW_PARTIAL" != "1" ]; then
        MISSING_FROM_SCOPE="$(git status --porcelain -- "${SCOPES[@]}" 2>/dev/null | grep -vE '^[AMDR]' | grep -v '^$' || true)"
        if [ -n "$MISSING_FROM_SCOPE" ]; then
            echo "WARN: declared scope has dirty file(s) NOT staged for this commit (reverse-BOB-068):" >&2
            echo "$MISSING_FROM_SCOPE" | sed 's/^/  /' >&2
            echo "       Declared scope: ${SCOPES[*]}" >&2
            echo "       If intentional (e.g. a WIP file not ready yet), re-run with" >&2
            echo "       --scope-allow-partial to silence this warning." >&2
            echo "       If NOT intentional, stage it explicitly or add it to --scope." >&2
        fi
    fi

    if git diff --cached --quiet; then
        echo "[commit-push-all] nothing to commit — skipping to push stage"
    else
        git commit -m "${MSG}${SKIP_TAG}"
    fi
else
    git add -A
    if git diff --cached --quiet; then
        echo "[commit-push-all] nothing to commit — skipping to push stage"
    else
        git commit -m "${MSG}${SKIP_TAG}"
    fi
fi

# ─── stage 5.5: differential SQLite dump for docs/workable_items.db ───
# (§11.4.226 evidence-class-at-closure / §11.4.209 review IMPORTANT-2
# remedy, task #79 — see the header comment above for the full mandate)
POST_COMMIT_HEAD="$(git rev-parse HEAD 2>/dev/null || echo "")"
if [ -n "$POST_COMMIT_HEAD" ] && [ "$POST_COMMIT_HEAD" != "$PRE_COMMIT_HEAD" ] \
    && [ -n "$PRE_COMMIT_HEAD" ] \
    && git diff --name-only "$PRE_COMMIT_HEAD" "$POST_COMMIT_HEAD" 2>/dev/null | grep -qx 'docs/workable_items.db'; then
    echo "[commit-push-all] stage 5.5/6 — docs/workable_items.db touched by $(git rev-parse --short "$POST_COMMIT_HEAD") — capturing differential dump"
    if [ -x scripts/capture-workable-items-db-delta.sh ]; then
        if bash scripts/capture-workable-items-db-delta.sh "$POST_COMMIT_HEAD"; then
            DELTA_FILE="docs/qa/db-deltas/${POST_COMMIT_HEAD}.diff"
            if [ -f "$DELTA_FILE" ]; then
                git add -- "$DELTA_FILE"
                if git diff --cached --quiet -- "$DELTA_FILE"; then
                    echo "[commit-push-all] stage 5.5/6 — delta already tracked identically, nothing new to commit"
                else
                    git commit -m "docs(qa,db-delta): capture differential dump for HEAD $(git rev-parse --short "$POST_COMMIT_HEAD")"
                    echo "[commit-push-all] stage 5.5/6 — delta commit created: $(git rev-parse --short HEAD)"
                fi
            else
                echo "[commit-push-all] stage 5.5/6 — helper exited 0 but produced no delta file (honest §11.4.3 skip — e.g. sqlite3 absent); nothing to commit"
            fi
        else
            echo "WARN: capture-workable-items-db-delta.sh failed (exit $?) — commit/push proceeds per §11.4.234(D) always-unblocked; DB delta evidence NOT captured for $(git rev-parse --short "$POST_COMMIT_HEAD"), tracked as a follow-up" >&2
        fi
    else
        echo "WARN: scripts/capture-workable-items-db-delta.sh missing or not executable — DB delta evidence NOT captured" >&2
    fi
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
