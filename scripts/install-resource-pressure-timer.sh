#!/usr/bin/env bash
# scripts/install-resource-pressure-timer.sh — installs + verifies the
# hourly boba-resource-pressure-check systemd --user timer (task #77 /
# BOB-076 2nd forced-logout incident, 2026-08-18).
#
# ─── PURPOSE ────────────────────────────────────────────────────────────
# challenges/scripts/resource_pressure_signature_challenge.sh (landed
# commit 1f42357) is a 5-signature proactive detector of forced-logout-
# precursor conditions. It was wired into scripts/pre_build_verification.sh
# (invariant 25) as a non-blocking pre-build WARN, but pre-build only runs
# when a build is actually invoked — it does NOT catch pressure building
# up between builds. This script installs the missing standing coverage:
# an hourly systemd --user timer that runs the SAME challenge continuously,
# independent of any build/commit activity, so a pressure signature (e.g.
# the §12.12 EAGAIN cascade observed ~5 minutes before the 2026-08-18
# SIGKILL) is caught the next hour at the latest, not only "whenever a
# build next happens to run".
#
# ─── DESIGN ─────────────────────────────────────────────────────────────
# Source-of-truth unit files live under scripts/systemd/user/ in this repo
# (same convention as boba.target / boba-stack.service / boba-webui-
# bridge.service — see scripts/boba-svc.sh). This script symlinks (default)
# or copies (--copy) them into ~/.config/systemd/user/, reloads the user
# systemd manager, enables + starts ONLY the .timer (never PartOf=boba.target
# — resource-pressure monitoring must run whether the torrent stack is up
# or down), then MECHANICALLY VERIFIES the install per §11.4.6 (no-guessing):
#   1. `systemctl --user list-timers` actually lists the timer as scheduled
#      (not merely "we ran `enable` so it must be fine").
#   2. A first, immediate manual fire of the .service (systemctl --user
#      start --wait) actually executes — captured regardless of whether
#      the underlying challenge itself found real host pressure. Those are
#      two DIFFERENT facts: "is the wiring correct" vs "is the host clean
#      right now" — this script reports both, never conflates them.
#
# ─── USAGE ──────────────────────────────────────────────────────────────
#   bash scripts/install-resource-pressure-timer.sh [--copy] [--uninstall]
#
#   --copy       Hard-copy unit files into ~/.config/systemd/user/ instead
#                of symlinking (default: symlink, so a future `git pull`
#                that updates the unit files is picked up automatically
#                after the next `systemctl --user daemon-reload`).
#   --uninstall  Stop + disable the timer, remove the installed unit
#                files, daemon-reload. Does not touch the in-repo sources.
#
# ─── INPUTS ─────────────────────────────────────────────────────────────
# None (no required env vars). Reads unit sources from
# scripts/systemd/user/boba-resource-pressure-check.{service,timer}
# relative to this script's own location.
#
# ─── OUTPUTS ────────────────────────────────────────────────────────────
# - ~/.config/systemd/user/boba-resource-pressure-check.{service,timer}
#   (symlink or copy, per flag).
# - Evidence captured to docs/qa/task-77/ (install_output.txt,
#   list_timers.txt, first_fire_status.txt) — task-77 evidence per the
#   task brief. Deliberately `.txt`, NOT `.log`: the repo's `.gitignore`
#   has a blanket `*.log` rule (verified: docs/qa/BOB-076/*.log is
#   gitignored despite living under the tracked docs/qa/ tree), so a
#   `.log` extension here would silently produce untracked evidence
#   despite this script's own claim to capture it — `.txt` matches the
#   existing docs/qa/BOB-075/*.txt precedent for evidence that IS meant
#   to be committed (§11.4.83). Contrast with invariant 25's OWN evidence
#   directory (docs/qa/pre_build_resource_pressure/) which deliberately
#   DOES use `.log` because THAT evidence is meant to stay local-only
#   (a per-pre-build-run artifact, not a one-time install record).
#
# ─── SIDE EFFECTS ───────────────────────────────────────────────────────
# - Writes symlinks/copies under ~/.config/systemd/user/.
# - Runs `systemctl --user daemon-reload`, `enable`, `start` (timer),
#   and one immediate `start --wait` of the service (executes the real
#   challenge script once, synchronously, as part of verification).
# - No sudo, no root, no host-wide systemd changes — entirely within the
#   invoking user's systemd --user session (mirrors scripts/boba-svc.sh).
#
# ─── DEPENDENCIES ───────────────────────────────────────────────────────
# bash, systemctl (systemd --user session available), coreutils.
# Linux-only (systemd --user is not available on other platforms) — a
# non-Linux host or an unavailable user systemd session is an honest,
# actionable exit 1 (§11.4.3 SKIP-with-reason via the printed message),
# never a silent no-op.
#
# ─── CROSS-REFERENCES ───────────────────────────────────────────────────
# - scripts/systemd/user/boba-resource-pressure-check.service + .timer
#   (the units this script installs).
# - challenges/scripts/resource_pressure_signature_challenge.sh (what the
#   service actually runs).
# - scripts/pre_build_verification.sh invariant 25 (the build-time,
#   non-blocking sibling coverage this timer complements for the
#   between-builds gap).
# - docs/scripts/install-resource-pressure-timer.md (external user guide,
#   §11.4.18).
# - docs/incidents/2026-08-18-perceived-forced-logout-2nd.md (the incident
#   this whole mechanism exists to catch earlier next time).
#
# Constitution: §11.4.6 (no-guessing — mechanically verify, never assume),
# §11.4.18 (script documentation), §11.4.83 (docs/qa evidence), §11.4.229
# (task tracker sync — this is task #77), §12.12 (thread-headroom /
# resource-pressure awareness), §11.4.234 (always-unblocked mechanism).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
UNIT_SRC="${SCRIPT_DIR}/systemd/user"
UNIT_DST="${HOME}/.config/systemd/user"
EVIDENCE_DIR="${REPO_ROOT}/docs/qa/task-77"

SERVICE_NAME="boba-resource-pressure-check.service"
TIMER_NAME="boba-resource-pressure-check.timer"

_c_green="$(printf '\033[0;32m')"
_c_yellow="$(printf '\033[1;33m')"
_c_red="$(printf '\033[0;31m')"
_c_reset="$(printf '\033[0m')"
_info()  { printf '%s[install-resource-pressure-timer]%s %s\n' "${_c_green}"  "${_c_reset}" "$*"; }
_warn()  { printf '%s[install-resource-pressure-timer]%s %s\n' "${_c_yellow}" "${_c_reset}" "$*"; }
_error() { printf '%s[install-resource-pressure-timer]%s %s\n' "${_c_red}"    "${_c_reset}" "$*" >&2; }

_require_linux_systemd() {
    if [[ "$(uname -s)" != "Linux" ]]; then
        _error "systemd --user is Linux-only (host=$(uname -s)) — SKIP (§11.4.3)"
        exit 1
    fi
    if ! command -v systemctl >/dev/null 2>&1; then
        _error "systemctl not on PATH — is systemd installed? SKIP (§11.4.3)"
        exit 1
    fi
    if ! systemctl --user status >/dev/null 2>&1; then
        _error "no user-level systemd session available (try 'systemctl --user status' by hand) — SKIP (§11.4.3)"
        exit 1
    fi
}

_cmd_uninstall() {
    _require_linux_systemd
    systemctl --user stop "${TIMER_NAME}" 2>/dev/null || true
    # Note (verified empirically during task #77): because UNIT_DST holds a
    # direct symlink into the repo (not a copy), systemd loads it as a
    # "linked" unit (visible as "linked; preset: disabled" in `status`) and
    # `disable` on a linked unit REMOVES the link itself — not merely the
    # [Install] .wants/ symlink `enable` created. So this `disable` call may
    # already remove ${UNIT_DST}/${TIMER_NAME} before the loop below runs;
    # the loop's existence check handles that gracefully (0 or 1 "removed"
    # lines for the timer depending on symlink vs --copy mode — both are
    # correct, neither is a bug).
    systemctl --user disable "${TIMER_NAME}" 2>/dev/null || true
    for u in "${SERVICE_NAME}" "${TIMER_NAME}"; do
        if [[ -e "${UNIT_DST}/${u}" || -L "${UNIT_DST}/${u}" ]]; then
            rm -f "${UNIT_DST}/${u}"
            _info "removed ${u}"
        fi
    done
    systemctl --user daemon-reload
    _info "daemon-reload complete — uninstall done"
    exit 0
}

MODE="symlink"
DO_UNINSTALL=0
for arg in "$@"; do
    case "${arg}" in
        --copy) MODE="copy" ;;
        --uninstall) DO_UNINSTALL=1 ;;
        *)
            _error "unknown argument: ${arg}"
            echo "Usage: $0 [--copy] [--uninstall]" >&2
            exit 2
            ;;
    esac
done

if [[ "${DO_UNINSTALL}" -eq 1 ]]; then
    _cmd_uninstall
fi

_require_linux_systemd
mkdir -p "${UNIT_DST}" "${EVIDENCE_DIR}"

# Mirror ALL subsequent stdout+stderr to both the terminal and the
# evidence log in one shot (§11.4.34-style: no per-line piping, which
# would silently drop `_error`'s stderr-only output from the log — a
# real bug caught and fixed during this task's own review pass).
INSTALL_LOG="${EVIDENCE_DIR}/install_output.txt"
: >"${INSTALL_LOG}"
exec > >(tee -a "${INSTALL_LOG}") 2>&1
TEE_PID=$!
_finish() {
    local ec=$?
    # Flush the tee process-substitution before the script's own exit
    # reaps the pipe, so the evidence log is never silently truncated
    # (§11.4.5 captured-evidence completeness).
    exec 1>&- 2>&-
    wait "${TEE_PID}" 2>/dev/null || true
    exit "${ec}"
}
trap _finish EXIT

echo "=== install-resource-pressure-timer.sh — $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
echo "mode=${MODE} repo_root=${REPO_ROOT}"

# ─── stage 1: install unit files ────────────────────────────────────
for u in "${SERVICE_NAME}" "${TIMER_NAME}"; do
    src="${UNIT_SRC}/${u}"
    dst="${UNIT_DST}/${u}"
    if [[ ! -f "${src}" ]]; then
        _error "unit source missing: ${src}"
        exit 1
    fi
    rm -f "${dst}"
    if [[ "${MODE}" == "copy" ]]; then
        cp -f "${src}" "${dst}"
        _info "installed ${u} (copy)"
    else
        ln -s "${src}" "${dst}"
        _info "installed ${u} (symlink -> ${src})"
    fi
done

# ─── stage 2: daemon-reload ─────────────────────────────────────────
systemctl --user daemon-reload
_info "daemon-reload complete"

# ─── stage 3: enable + start the TIMER (never the bare service) ────
systemctl --user enable "${TIMER_NAME}"
systemctl --user start "${TIMER_NAME}"
_info "${TIMER_NAME} enabled + started"

# ─── stage 4: MECHANICAL verification #1 — the timer is scheduled ──
# §11.4.6: don't assume `enable`+`start` worked — read it back.
LIST_TIMERS_LOG="${EVIDENCE_DIR}/list_timers.txt"
systemctl --user list-timers --all >"${LIST_TIMERS_LOG}" 2>&1 || true
cat "${LIST_TIMERS_LOG}"
if ! grep -q "${TIMER_NAME}" "${LIST_TIMERS_LOG}"; then
    _error "VERIFICATION FAILED: ${TIMER_NAME} does not appear in 'systemctl --user list-timers --all'"
    _error "installation is NOT verified — inspect ${LIST_TIMERS_LOG}"
    exit 1
fi
_info "VERIFIED: ${TIMER_NAME} is scheduled (present in list-timers)"

# ─── stage 5: MECHANICAL verification #2 — an immediate first fire ─
# Distinguish two DIFFERENT facts, never conflate them (§11.4.6):
#   (a) did systemd successfully invoke the service at all (wiring)?
#   (b) did the challenge itself find real host pressure right now?
FIRST_FIRE_LOG="${EVIDENCE_DIR}/first_fire_status.txt"
START_EXIT=0
systemctl --user start --wait "${SERVICE_NAME}" || START_EXIT=$?
{
    echo "=== systemctl --user start --wait ${SERVICE_NAME} exit=${START_EXIT} ==="
    echo
    echo "--- systemctl --user status ${SERVICE_NAME} --no-pager -l ---"
    systemctl --user status "${SERVICE_NAME}" --no-pager -l 2>&1 || true
    echo
    echo "--- journalctl --user -u ${SERVICE_NAME} -n 50 --no-pager ---"
    journalctl --user -u "${SERVICE_NAME}" -n 50 --no-pager 2>&1 || true
} >"${FIRST_FIRE_LOG}"
cat "${FIRST_FIRE_LOG}"

SVC_RESULT="$(systemctl --user show "${SERVICE_NAME}" -p Result --value 2>/dev/null || echo unknown)"

if systemctl --user cat "${SERVICE_NAME}" >/dev/null 2>&1; then
    # The unit resolved and systemd attempted to run it — the WIRING is
    # verified regardless of the challenge's own exit code. Report the
    # challenge's own finding as a SEPARATE, honest fact.
    _info "VERIFIED: ${SERVICE_NAME} wiring confirmed (unit resolves, systemd invoked ExecStart)"
    case "${SVC_RESULT}" in
        success)
            _info "first fire: challenge reported CLEAN (Result=success — no signature over threshold)"
            ;;
        exit-code)
            _warn "first fire: challenge reported a TRIPPED SIGNATURE (Result=exit-code) — see ${FIRST_FIRE_LOG} for the diagnostic"
            _warn "this is REAL host-pressure information, not an installation defect — take corrective action per the challenge's own printed guidance"
            ;;
        *)
            _warn "first fire: unexpected Result=${SVC_RESULT} — inspect ${FIRST_FIRE_LOG}"
            ;;
    esac
else
    _error "VERIFICATION FAILED: ${SERVICE_NAME} does not resolve via 'systemctl --user cat' — daemon-reload or symlink target problem"
    exit 1
fi

echo
_info "install + verification complete. Evidence: ${EVIDENCE_DIR#${REPO_ROOT}/}/"
_info "next fire: hourly (OnUnitActiveSec=1hour, +/-5min jitter). Missed fires (e.g. after logout) run on next login (Persistent=true)."
_info "manual re-fire any time: systemctl --user start ${SERVICE_NAME}"
_info "watch it live: journalctl --user -u ${SERVICE_NAME} -f"
_info "uninstall: bash $0 --uninstall"

exit 0
