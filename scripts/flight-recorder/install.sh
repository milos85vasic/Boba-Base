#!/usr/bin/env bash
# install.sh — install the flight-recorder tick into the operator's user crontab
#
# Purpose:
#   Schedule scripts/flight-recorder/flight-recorder.sh from the SYSTEM cron
#   daemon, which lives in system.slice and therefore keeps scheduling ticks
#   even while user@1000.service is being torn down and restarted. That is the
#   whole architectural point: the recorder does not have to survive the event
#   as a process — its SCHEDULER has to, and crond does.
#
# Usage:
#   scripts/flight-recorder/install.sh [--dry-run]
#
# Inputs:  the current user crontab; env BOBA_FR_DIR (optional, non-default
#          state dir is embedded into the cron line so ticks agree with the CLI)
# Outputs: one marker-delimited block appended to the user crontab; a timestamped
#          backup of the pre-change crontab under the state dir
# Side-effects: modifies ONLY the current user's crontab, and only inside its own
#          marker block. Never touches root, other users, or systemd units.
#          Requires no sudo/su — this is exactly why cron was chosen over a
#          root-owned system.slice unit for the always-available layer.
# Dependencies: bash 4+, crontab, coreutils
# Cross-references: uninstall.sh, flight-recorder.sh,
#          docs/scripts/flight-recorder.md,
#          docs/guides/forced-logout-flight-recorder.md
#
# Constitution: §11.4.201 (refuses to install when its own preconditions fail),
#   §11.4.252 (fail closed), §11.4.122 (removal is explicit + reversible),
#   CONST-033 (no power verbs anywhere in the installed line).

set -o errexit
set -o nounset
set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
readonly RECORDER="$SCRIPT_DIR/flight-recorder.sh"
readonly BEGIN_MARK="# >>> boba-flight-recorder >>>"
readonly END_MARK="# <<< boba-flight-recorder <<<"

STATE_DIR="${BOBA_FR_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/boba-flight-recorder}"
readonly STATE_DIR

DRY_RUN=false
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

[[ -f "$RECORDER" ]] || { echo "ERROR: missing $RECORDER" >&2; exit 1; }
chmod +x "$RECORDER" 2>/dev/null || true

# Fail closed (§11.4.252): if the recorder's own preconditions do not hold on
# this host, scheduling it would just manufacture a per-minute failure.
echo "--- pre-install verification ---"
if ! BOBA_FR_DIR="$STATE_DIR" bash "$RECORDER" verify; then
    echo >&2
    echo "ERROR: flight-recorder verify FAILED — refusing to install." >&2
    echo "Fix the reported condition first; a scheduled recorder that cannot" >&2
    echo "record is worse than none, because it looks like coverage." >&2
    exit 1
fi

mkdir -p "$STATE_DIR"
chmod 700 "$STATE_DIR"

# Non-default state dirs are embedded so a cron tick and an interactive
# `flight-recorder.sh report` always read the same journal.
ENV_PREFIX=""
if [[ -n "${BOBA_FR_DIR:-}" ]]; then
    ENV_PREFIX="BOBA_FR_DIR=$STATE_DIR "
fi

# nice/ionice keep the tick off the critical path of a host that is, by
# hypothesis, already under resource pressure when it matters most.
readonly CRON_LINE="* * * * * ${ENV_PREFIX}/usr/bin/nice -n 19 /usr/bin/ionice -c 3 /usr/bin/bash $RECORDER tick >/dev/null 2>$STATE_DIR/tick.err"

current="$(crontab -l 2>/dev/null || true)"

# Strip any previous block so re-running is idempotent, then append a fresh one.
# Every line outside the markers is preserved verbatim — this must never clobber
# an unrelated entry belonging to the operator or another agent.
stripped="$(awk -v b="$BEGIN_MARK" -v e="$END_MARK" '
    $0 == b { inblock = 1; next }
    $0 == e { inblock = 0; next }
    !inblock { print }
' <<<"$current")"

new_crontab="$(printf '%s\n%s\n%s\n%s\n' \
    "$stripped" "$BEGIN_MARK" "$CRON_LINE" "$END_MARK" | awk 'NF || NR > 1')"

if [[ "$DRY_RUN" == "true" ]]; then
    echo
    echo "--- DRY RUN: crontab would become ---"
    printf '%s\n' "$new_crontab"
    echo "--- (nothing was changed) ---"
    exit 0
fi

# Keep a copy of what was there before, so a mistake is reversible.
backup="$STATE_DIR/crontab.backup.$(date -u +%Y%m%dT%H%M%SZ)"
printf '%s\n' "$current" >"$backup"
chmod 600 "$backup"

printf '%s\n' "$new_crontab" | crontab -

echo
echo "--- installed ---"
crontab -l | sed -n "/$(printf '%s' "$BEGIN_MARK" | sed 's/[][\.*^$/]/\\&/g')/,/$(printf '%s' "$END_MARK" | sed 's/[][\.*^$/]/\\&/g')/p"
echo
echo "  state dir      : $STATE_DIR"
echo "  prev crontab   : $backup"
echo "  first record   : within 60s"
echo
echo "Check it with:   $RECORDER status"
echo "Diagnose with:   $RECORDER report"
echo "Remove it with:  $SCRIPT_DIR/uninstall.sh"
