#!/bin/bash
# scripts/capture-workable-items-db-delta.sh
#
# Purpose:
#   Captures a differential SQLite dump of docs/workable_items.db
#   (the §11.4.93/§11.4.95 workable-items single-source-of-truth
#   database) between a given commit and its first parent, so a
#   commit that mutates the tracked binary blob NEVER lands with only
#   a message-level claim about its content ("meta table unchanged")
#   as its evidence. Per §11.4.226 evidence-class-at-closure, a
#   binary blob change is an opaque ARTIFACT-class fact until a
#   differential dump elevates it to inspectable RUNTIME/ARTIFACT-
#   class evidence — this script produces exactly that artifact.
#
#   Forensic anchor: §11.4.209 code-review IMPORTANT-2 finding
#   (`.superpowers/sdd/task-review-457cca4-a7e55f9-report.md`) —
#   commit 3520621 committed docs/workable_items.db with only a
#   prose claim ("meta table content is unchanged") and no
#   differential evidence, in the SAME session whose own Task #41
#   investigation (BOB-068) confirmed shared-checkout races on this
#   exact file. Task tracker #79.
#
# Usage:
#   scripts/capture-workable-items-db-delta.sh [<commit-sha>] [--force]
#
#   <commit-sha>   Commit to capture the delta for. Defaults to HEAD.
#                  Resolved via `git rev-parse` (accepts short SHAs,
#                  refs, HEAD~N, etc.) and the OUTPUT FILE is always
#                  named after the resolved FULL sha, so the delta
#                  path is stable regardless of how the commit was
#                  named on the command line.
#   --force        Regenerate the delta even if one already exists
#                  for that commit sha (default: idempotent skip).
#
# Output:
#   docs/qa/db-deltas/<full-commit-sha>.diff — a git-tracked evidence
#   file containing: per-table row counts (before -> after), the full
#   `meta` table content on both sides, and a unified diff of the
#   complete logical `.dump` of the database on both sides.
#
# Exit codes:
#   0 = delta captured, OR honestly SKIPPED with a printed reason
#       (§11.4.3 — missing sqlite3, missing DB at the target commit,
#       or delta already exists and --force was not given)
#   1 = invocation error (bad arguments)
#   2 = usage requested (-h/--help)
#
# Side effects:
#   None beyond writing the single output file under
#   docs/qa/db-deltas/ and using a self-cleaning temp directory
#   (`mktemp -d` + `trap ... EXIT`) for intermediate `.db`/`.sql`
#   extraction. Never mutates docs/workable_items.db itself, never
#   touches the working tree's index, never commits.
#
# Dependencies:
#   git, sqlite3 (>= any version exposing `.dump`), mktemp, date.
#   sqlite3 absence is an HONEST §11.4.3 SKIP — never a fabricated
#   or faked delta.
#
# Cross-references:
#   scripts/commit-push-all.sh (invokes this helper as its stage 5.5
#   when a landed commit's diff touches docs/workable_items.db, per
#   §11.4.234's dedicated-entrypoint contract).
#   docs/scripts/capture-workable-items-db-delta.md (§11.4.18
#   external user guide for this script).
#   docs/QA_DISCOVERY_LEDGER.md (§11.4.238 discovery-channel ledger
#   entry DB-BLOB-COMMITTED-WITHOUT-DELTA-3520621 citing this fix).

set -euo pipefail

DB_PATH="docs/workable_items.db"
OUT_DIR="docs/qa/db-deltas"

usage() {
    cat >&2 <<'EOF'
Usage: scripts/capture-workable-items-db-delta.sh [<commit-sha>] [--force]

Captures a differential SQLite dump of docs/workable_items.db between
<commit-sha> (default: HEAD) and its first parent, so a commit that
touches the tracked SSoT database (§11.4.95) always carries evidence
of EXACTLY what changed inside it -- never only a message-level claim
(§11.4.226 evidence-class-at-closure: a binary blob change alone is
an opaque ARTIFACT-class fact; a differential dump is inspectable
RUNTIME/ARTIFACT-class evidence).

Output: docs/qa/db-deltas/<full-commit-sha>.diff

Options:
  --force    Regenerate the delta even if it already exists for that
             commit sha (default: idempotent skip).
  -h, --help Show this message.
EOF
}

COMMIT_ARG=""
FORCE=0
while [ $# -gt 0 ]; do
    case "$1" in
        --force)
            FORCE=1
            shift
            ;;
        -h|--help)
            usage
            exit 2
            ;;
        -*)
            echo "ERROR: unknown flag: $1" >&2
            usage
            exit 1
            ;;
        *)
            if [ -n "$COMMIT_ARG" ]; then
                echo "ERROR: unexpected extra argument: $1" >&2
                usage
                exit 1
            fi
            COMMIT_ARG="$1"
            shift
            ;;
    esac
done

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

if [ -z "$COMMIT_ARG" ]; then
    COMMIT_ARG="HEAD"
fi

if ! COMMIT="$(git rev-parse "$COMMIT_ARG" 2>/dev/null)"; then
    echo "ERROR: cannot resolve commit-ish '$COMMIT_ARG'" >&2
    exit 1
fi

OUT_FILE="$OUT_DIR/${COMMIT}.diff"

if [ -f "$OUT_FILE" ] && [ "$FORCE" -ne 1 ]; then
    echo "[capture-workable-items-db-delta] delta already exists for $COMMIT — skipping (idempotent)."
    echo "[capture-workable-items-db-delta] use --force to regenerate: $OUT_FILE"
    exit 0
fi

# §11.4.3 honest SKIP-with-reason: sqlite3 is a hard dependency of this
# evidence-capture mechanism. Its absence is NOT a licence to fake the
# evidence -- it is an honest, loud, non-fatal skip.
if ! command -v sqlite3 >/dev/null 2>&1; then
    echo "[capture-workable-items-db-delta] SKIP (reason: sqlite3 not found on PATH) — cannot capture differential dump." >&2
    echo "[capture-workable-items-db-delta] honest §11.4.3 skip: no fabricated delta written." >&2
    exit 0
fi

if ! git cat-file -e "${COMMIT}:${DB_PATH}" 2>/dev/null; then
    echo "[capture-workable-items-db-delta] SKIP (reason: ${DB_PATH} does not exist at ${COMMIT})" >&2
    exit 0
fi

PARENT=""
if git rev-parse --verify -q "${COMMIT}^" >/dev/null 2>&1; then
    PARENT="$(git rev-parse "${COMMIT}^")"
fi

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

AFTER_DB="$TMP_DIR/after.db"
git show "${COMMIT}:${DB_PATH}" > "$AFTER_DB"

HAVE_BEFORE=0
BEFORE_DB="$TMP_DIR/before.db"
if [ -n "$PARENT" ] && git cat-file -e "${PARENT}:${DB_PATH}" 2>/dev/null; then
    git show "${PARENT}:${DB_PATH}" > "$BEFORE_DB"
    HAVE_BEFORE=1
fi

# Table roster read from the AFTER db so a newly-added table is still
# enumerated (the BEFORE side just reports "absent" for it).
TABLES="$(sqlite3 "$AFTER_DB" "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")"

mkdir -p "$OUT_DIR"

{
    echo "# Differential SQLite Dump — ${DB_PATH}"
    echo "# §11.4.226 evidence-class-at-closure / §11.4.95 SSoT / §11.4.115(F) machine-written evidence"
    echo "# §11.4.209 review IMPORTANT-2 remedy — task tracker #79"
    echo "#"
    echo "# Commit:    ${COMMIT}"
    if [ "$HAVE_BEFORE" -eq 1 ]; then
        echo "# Parent:    ${PARENT}"
    else
        echo "# Parent:    (none — ${DB_PATH} newly added at this commit, or repo root commit)"
    fi
    echo "# Generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "# Tool:      sqlite3 $(sqlite3 --version 2>/dev/null | awk '{print $1}')"
    echo "#"
    echo "## Row counts (table: before -> after)"
    while IFS= read -r t; do
        [ -z "$t" ] && continue
        AFTER_COUNT="$(sqlite3 "$AFTER_DB" "SELECT count(*) FROM \"$t\";" 2>/dev/null || echo "ERR")"
        if [ "$HAVE_BEFORE" -eq 1 ]; then
            BEFORE_COUNT="$(sqlite3 "$BEFORE_DB" "SELECT count(*) FROM \"$t\";" 2>/dev/null || echo "absent")"
        else
            BEFORE_COUNT="absent"
        fi
        MARK="same"
        if [ "$BEFORE_COUNT" != "$AFTER_COUNT" ]; then
            MARK="CHANGED"
        fi
        printf '%-24s %10s -> %-10s  [%s]\n' "$t" "$BEFORE_COUNT" "$AFTER_COUNT" "$MARK"
    done <<EOF_TABLES
$TABLES
EOF_TABLES
    echo "#"
    echo "## meta table (full content)"
    echo "### before"
    if [ "$HAVE_BEFORE" -eq 1 ]; then
        sqlite3 "$BEFORE_DB" "SELECT * FROM meta;" 2>/dev/null || echo "(meta table absent/unreadable)"
    else
        echo "(no parent DB)"
    fi
    echo "### after"
    sqlite3 "$AFTER_DB" "SELECT * FROM meta;" 2>/dev/null || echo "(meta table absent/unreadable)"
    echo "#"
    echo "## Full logical .dump unified diff (before -> after)"
    echo "#"
    if [ "$HAVE_BEFORE" -eq 1 ]; then
        BEFORE_DUMP="$TMP_DIR/before.sql"
        AFTER_DUMP="$TMP_DIR/after.sql"
        sqlite3 "$BEFORE_DB" ".dump" > "$BEFORE_DUMP"
        sqlite3 "$AFTER_DB" ".dump" > "$AFTER_DUMP"
        if diff -u "$BEFORE_DUMP" "$AFTER_DUMP" > "$TMP_DIR/dump.diff"; then
            echo "(no logical content difference — the binary blob change was pure SQLite housekeeping: WAL/page-cache churn with zero row-level delta)"
        else
            cat "$TMP_DIR/dump.diff"
        fi
    else
        echo "(no parent DB to diff against — dumping full AFTER content)"
        sqlite3 "$AFTER_DB" ".dump"
    fi
} > "$TMP_DIR/output.tmp"

# Atomic publish: only move the evidence file into place once the ENTIRE
# capture block above has completed successfully. A mid-capture failure
# (missing/broken sqlite3 invocation, etc.) must NEVER leave a partial,
# misleadingly-truncated file sitting at the real output path — that
# would read as "clean, nothing after this line" instead of the genuine
# failure it is (the exact false-negative-null class §11.4.201(6) bans).
mv -- "$TMP_DIR/output.tmp" "$OUT_FILE"

echo "[capture-workable-items-db-delta] wrote $OUT_FILE"
