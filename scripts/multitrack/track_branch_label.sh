#!/usr/bin/env bash
# scripts/multitrack/track_branch_label.sh
#
# Purpose : boba's own §11.4.182 work-stream label, delegating almost
#           entirely to the canonical, inherited-by-reference labeler
#           (constitution/scripts/multitrack/track_branch_label.sh) per
#           §11.4.28(B)/§11.4.177 — this project NEVER edits that shared,
#           fleet-wide script in place; it only wraps its output.
#
# Boba-specific identity (operator decision, 2026-08-08): this checkout
# (wherever it lives on disk — NOT under /mnt/track<N>) is permanently
# registered as the home of TRACK 11 in the operator's multi-track fleet.
# The canonical script has no way to know that (it only recognises the
# `/mnt/track<N>/...` cwd convention for non-trunk branches), so on a
# non-trunk branch it correctly, honestly emits `T?` for this path. This
# wrapper's ONLY job is to fill that specific `?` in with `11`.
#
# The canonical script's TRUNK RULE (main/master -> always T1, regardless
# of checkout path, §11.4.182 amendment 2026-07-28) is NEVER overridden
# here — trunk work stays T1, on purpose, exactly as the shared engine
# mandates ("no escape hatch"). Only non-trunk (feature/product/flavor,
# §11.4.195) work dispatched from this checkout is labelled Track 11.
#
# Usage   : bash scripts/multitrack/track_branch_label.sh
# Output  : one line, the same `(T<N>/<branch> - <alias> - <model> - <effort>)`
#           shape the canonical script emits, with `T?` replaced by `T11`
#           ONLY when the branch is non-trunk (never touches the trunk case).
# Deps    : the canonical constitution/scripts/multitrack/track_branch_label.sh
#           (resolved relative to this file, so it works from any cwd inside
#           this checkout).
# Cross-refs: §11.4.178 (track-qualified identity), §11.4.182 (label mandate
#           + TRUNK RULE), §11.4.28(B)/§11.4.177 (decoupling — wrap, never
#           edit, the shared engine), docs/MULTITRACK.md (this project's
#           full track-11 registration + rationale).
# Classification: project-specific (boba's track-number assignment is not
#           universal — every consumer project registers its own).

set -uo pipefail

_self_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_repo_root="$(cd "$_self_dir/../.." && pwd)"
_canonical="$_repo_root/constitution/scripts/multitrack/track_branch_label.sh"

if [[ ! -x "$_canonical" && ! -r "$_canonical" ]]; then
  echo "track_branch_label.sh: canonical labeler not found at $_canonical" >&2
  exit 1
fi

_line="$(bash "$_canonical")"

# Only rewrite T? -> T11, and only when NOT trunk (the canonical script's
# own TRUNK RULE already guarantees T? never appears for main/master, so
# this substitution is inherently trunk-safe — it has nothing to match on
# a trunk line — but the branch check is kept explicit for auditability).
_branch="$(git -C "$_repo_root" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
case "$_branch" in
  main|master)
    printf '%s\n' "$_line"
    ;;
  *)
    printf '%s\n' "$_line" | sed 's/^(T?\//(T11\//'
    ;;
esac
