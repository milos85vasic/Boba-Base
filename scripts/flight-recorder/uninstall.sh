#!/usr/bin/env bash
# uninstall.sh — remove the flight-recorder tick from the user crontab
#
# Purpose:
#   Stop the per-minute tick. Removes ONLY the recorder's own marker-delimited
#   block; every other crontab line is preserved verbatim.
#
# Usage:
#   scripts/flight-recorder/uninstall.sh [--dry-run] [--purge]
#
#     --dry-run   show the resulting crontab without applying it
#     --purge     ALSO delete the recorded journal under the state dir
#
# Inputs:  the current user crontab; env BOBA_FR_DIR (optional)
# Outputs: the crontab with the recorder block removed; a timestamped backup
# Side-effects: modifies ONLY the current user's crontab. The recorded journal
#          is KEPT by default — the evidence outlives the recorder, which is the
#          point of having recorded it (§11.4.122: removal of captured data is
#          explicit and opt-in, never a silent side effect of stopping a tool).
# Dependencies: bash 4+, crontab, coreutils
# Cross-references: install.sh, flight-recorder.sh,
#          docs/scripts/flight-recorder.md
#
# Constitution: §11.4.122 (nothing the operator relies on is removed silently),
#   §9.2 (a backup precedes the mutation).

set -o errexit
set -o nounset
set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
readonly BEGIN_MARK="# >>> boba-flight-recorder >>>"
readonly END_MARK="# <<< boba-flight-recorder <<<"

STATE_DIR="${BOBA_FR_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/boba-flight-recorder}"
readonly STATE_DIR

DRY_RUN=false
PURGE=false
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=true ;;
        --purge)   PURGE=true ;;
        *) echo "ERROR: unknown option '$arg'" >&2; exit 1 ;;
    esac
done

current="$(crontab -l 2>/dev/null || true)"

if ! grep -qF "$BEGIN_MARK" <<<"$current"; then
    echo "flight-recorder tick is not installed in the crontab — nothing to remove."
    if [[ "$PURGE" == "true" && -d "$STATE_DIR" ]]; then
        echo "--purge given: removing recorded journal at $STATE_DIR"
        [[ "$DRY_RUN" == "true" ]] || rm -rf "$STATE_DIR"
    fi
    exit 0
fi

stripped="$(awk -v b="$BEGIN_MARK" -v e="$END_MARK" '
    $0 == b { inblock = 1; next }
    $0 == e { inblock = 0; next }
    !inblock { print }
' <<<"$current")"

if [[ "$DRY_RUN" == "true" ]]; then
    echo "--- DRY RUN: crontab would become ---"
    if [[ -z "${stripped//[[:space:]]/}" ]]; then
        echo "(empty — the crontab would be removed entirely)"
    else
        printf '%s\n' "$stripped"
    fi
    echo "--- (nothing was changed) ---"
    exit 0
fi

mkdir -p "$STATE_DIR" 2>/dev/null || true
backup="$STATE_DIR/crontab.backup.$(date -u +%Y%m%dT%H%M%SZ)"
if printf '%s\n' "$current" >"$backup" 2>/dev/null; then
    chmod 600 "$backup"
    echo "  prev crontab saved: $backup"
fi

# If nothing else remains, remove the crontab entirely rather than leaving an
# empty one behind — that restores the machine to its pre-install shape.
if [[ -z "${stripped//[[:space:]]/}" ]]; then
    crontab -r 2>/dev/null || true
    echo "  crontab had no other entries — removed entirely."
else
    printf '%s\n' "$stripped" | crontab -
    echo "  recorder block removed; $(wc -l <<<"$stripped") other line(s) preserved."
fi

# Verify the removal actually took effect rather than reporting success blindly.
if crontab -l 2>/dev/null | grep -qF "$BEGIN_MARK"; then
    echo "ERROR: the recorder block is STILL present after removal." >&2
    exit 1
fi
echo "  verified: no flight-recorder block remains in the crontab."

if [[ "$PURGE" == "true" ]]; then
    echo "  --purge given: deleting recorded journal at $STATE_DIR"
    rm -rf "$STATE_DIR"
else
    echo
    echo "Recorded journal KEPT at $STATE_DIR"
    echo "  read it with: $SCRIPT_DIR/flight-recorder.sh report"
    echo "  delete it with: $0 --purge"
fi
