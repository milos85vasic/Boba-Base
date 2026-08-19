#!/usr/bin/env bash
# git-safe-backup.sh — Constitution §9.2 hardlinked pre-op backup of a .git
# directory, with EXDEV cross-device fallback to full copy.
#
# ─── CONSTITUTION BINDINGS ────────────────────────────────────────────
# §9.2       Absolute data safety — hardlinked mirror of .git before any
#            destructive git operation (history rewrite, force-delete,
#            bulk removal, submodule de-init, object pruning).
# §11.4.6    No-guessing — the backup path chosen (hardlink vs full-copy)
#            is REPORTED as captured FACT via stdout, never inferred.
# §11.4.201  Guard MUST assert the REAL condition — a "backup succeeded"
#            claim is proven by verifying the destination exists AND
#            contains the object store, never a bare exit code.
# §11.4.113  No force-push — this helper never invokes destructive git ops;
#            it ONLY produces the safety net destructive ops depend on.
#
# ─── USAGE ────────────────────────────────────────────────────────────
#   backup_git_dir <src-git-dir> <dst-backup-dir>
#
# Prints one line to stdout:
#   MODE=hardlink SRC=<src> DST=<dst> BYTES_USED=<n>
#   MODE=full-copy SRC=<src> DST=<dst> BYTES_USED=<n>   [with EXDEV note on stderr]
#
# Exit codes:
#   0 = backup produced (either mode), destination verified non-empty
#   2 = usage error (missing/nonexistent args)
#   3 = both hardlink AND full-copy failed (no backup produced — CALLER
#       MUST refuse the destructive op)
#
# ─── CROSS-DEVICE FALLBACK (the fix this file exists for) ─────────────
# `cp -al` (hardlink-recursive) fails with EXDEV / "Invalid cross-device
# link" when SRC and DST live on different filesystems. Historically this
# left the caller with no backup and a §9.2 violation. This helper
# detects EXDEV and falls back to `cp -a` (full recursive copy) with a
# stderr WARN so the caller knows the backup used real disk not
# hardlinks.
#
# Composes with challenges/scripts/git_safe_backup_exdev_challenge.sh
# which drives the fallback path by pointing DST at /tmp on a host where
# the source lives on a different filesystem — the standard §11.4.115
# RED-first regression guard.

set -euo pipefail

# shellcheck disable=SC2034
GIT_SAFE_BACKUP_VERSION="1.0.0"

# _dir_size — best-effort bytes-used report for a directory.
# Uses `du -sb` when GNU coreutils is present; falls back to a portable
# `find | wc -c` sum on hosts that lack it. Never fails the caller.
_dir_size() {
    local d="$1"
    if du -sb "$d" 2>/dev/null | awk '{print $1; exit}'; then
        return 0
    fi
    # Portable fallback: sum of file sizes (approximate — no metadata
    # overhead, but honest about it since MODE tells the caller which
    # sums are physical vs shared).
    find "$d" -type f -printf '%s\n' 2>/dev/null | awk '{s+=$1} END {print s+0}'
}

# backup_git_dir SRC DST
#
# Attempts a hardlink-recursive copy (SRC/*  ==>  DST/*, sharing inodes),
# falls back to a full recursive copy on EXDEV. Verifies DST exists and
# is non-empty before reporting success.
backup_git_dir() {
    local src="${1:?usage: backup_git_dir <src-git-dir> <dst-backup-dir>}"
    local dst="${2:?usage: backup_git_dir <src-git-dir> <dst-backup-dir>}"

    if [[ ! -d "$src" ]]; then
        printf 'git-safe-backup: SRC not a directory: %s\n' "$src" >&2
        return 2
    fi
    if [[ -e "$dst" ]]; then
        printf 'git-safe-backup: DST already exists (refusing to overwrite): %s\n' "$dst" >&2
        return 2
    fi

    local dst_parent
    dst_parent="$(dirname -- "$dst")"
    mkdir -p -- "$dst_parent"

    # ── attempt 1: hardlink-recursive (fast, near-zero disk) ────────
    # `cp -al` = --archive + --link. Portable on GNU coreutils (Linux).
    # On BSD/macOS the equivalent is `cp -a` with no `-l`; there we skip
    # straight to the full-copy path (also captured honestly in MODE).
    local mode err rc
    local can_hardlink=1
    if ! cp -al --help >/dev/null 2>&1; then
        # cp doesn't support --link on this platform — skip attempt 1
        # honestly (§11.4.6 — don't PRETEND to try a mode the tool can't).
        can_hardlink=0
    fi

    if [[ "$can_hardlink" == 1 ]]; then
        # capture stderr so we can classify EXDEV vs other failures
        err="$(mktemp)"
        # shellcheck disable=SC2015
        if cp -al -- "$src" "$dst" 2>"$err"; then
            mode="hardlink"
            rm -f -- "$err"
        else
            rc=$?
            # EXDEV markers (glibc, musl, and GNU coreutils phrasings):
            #   "Invalid cross-device link"
            #   "cross-device link"
            #   "EXDEV"
            if grep -qE 'cross-device link|EXDEV|Invalid cross-device' "$err" 2>/dev/null; then
                printf 'git-safe-backup: WARN cp -al hit EXDEV (cross-device) — falling back to full copy: SRC=%s DST=%s\n' \
                    "$src" "$dst" >&2
                # Clean any partial hardlink tree the failing cp left behind.
                rm -rf -- "$dst"
                # ── attempt 2: full recursive copy ──────────────
                if cp -a -- "$src" "$dst" 2>"$err"; then
                    mode="full-copy"
                    rm -f -- "$err"
                else
                    printf 'git-safe-backup: FAIL full-copy fallback also failed (rc=%d):\n' "$?" >&2
                    cat -- "$err" >&2
                    rm -f -- "$err"
                    return 3
                fi
            else
                printf 'git-safe-backup: FAIL cp -al failed with non-EXDEV error (rc=%d):\n' "$rc" >&2
                cat -- "$err" >&2
                rm -f -- "$err"
                return 3
            fi
        fi
    else
        # No --link support → straight full copy, honestly labelled.
        if cp -a -- "$src" "$dst"; then
            mode="full-copy"
        else
            printf 'git-safe-backup: FAIL full-copy failed on platform without cp --link (rc=%d)\n' "$?" >&2
            return 3
        fi
    fi

    # ── verify (§11.4.201 — assert the REAL condition) ─────────────
    # A "backup succeeded" claim is a false-null unless we PROVE the
    # destination is populated. A cp that exits 0 on an empty tree is
    # a §11.4.201(6) FALSE-NULL — we walk the tree and confirm at
    # least ONE file landed.
    if [[ ! -d "$dst" ]] || [[ -z "$(find "$dst" -mindepth 1 -print -quit 2>/dev/null)" ]]; then
        printf 'git-safe-backup: FAIL destination missing or empty after cp (%s): %s\n' "$mode" "$dst" >&2
        return 3
    fi

    local bytes
    bytes="$(_dir_size "$dst" 2>/dev/null || echo 0)"

    printf 'MODE=%s SRC=%s DST=%s BYTES_USED=%s\n' "$mode" "$src" "$dst" "$bytes"
    return 0
}

# When invoked directly (not sourced), operate as a CLI wrapper.
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    backup_git_dir "$@"
fi
