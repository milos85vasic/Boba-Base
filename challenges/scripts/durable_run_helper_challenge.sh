#!/usr/bin/env bash
# durable_run_helper_challenge.sh — BOB-064 anti-bluff regression guard for
# the durable-run helper (scripts/lib/durable-run.sh) ported from Lava P1.
#
# ─── CONSTITUTION BINDINGS ────────────────────────────────────────────
# §11.4.115  RED-on-broken-artifact + polarity switch (RED_MODE=1 default)
# §11.4.5    Captured runtime evidence (real cgroup + systemd unit reads)
# §11.4.69   feature_class=durable_execution (systemd_user_unit_survives_launcher)
# §11.4.108  Runtime-signature — a systemd .service unit whose cgroup differs
#            from the launching shell's session scope IS the fix's signature
# §11.4.146  Same test confirms the fix (polarity flip closes the guard)
#
# ─── POLARITY (§11.4.115) ─────────────────────────────────────────────
#   RED_MODE=0  (default, GREEN): PASS on the FIXED state (helper
#                present + working under a real systemd --user manager),
#                FAIL if the helper is absent / broken — this is the
#                shipped regression guard consumed by run_all_challenges.sh.
#   RED_MODE=1              (RED): PASS on the BROKEN state (helper
#                absent or unsourceable), FAIL if the helper is present
#                + working — the pre-fix reproduction check kept for
#                §11.4.146 same-test-confirms-fix polarity flip proofs.
#
# ─── ANTI-BLUFF ───────────────────────────────────────────────────────
# The GREEN assertion drives the helper end-to-end: launches a real
# sleeper, reads its MainPID from `systemctl --user`, reads the
# process's actual cgroup from /proc/<pid>/cgroup, and asserts that
# cgroup is an independently-managed .service unit DIFFERENT from the
# launching shell's session scope. A "process alive" check alone is a
# §11.4.201(6) false-null — a process alive INSIDE the session scope
# would die with the login session, so we must READ the cgroup, not
# just PID existence.
#
# ─── HONEST BOUNDARY (§11.4.6) ────────────────────────────────────────
# When no systemd --user manager is running (container, CI without a
# user manager, non-systemd host), the GREEN half honestly SKIPs with
# reason — durability requires systemd-run --user by design (§11.4.3
# topology SKIP-with-reason). SKIP is neither PASS nor FAIL; the
# challenge exits 0 with a SKIP: prefix so the aggregator does not
# count it as a failure.
#
# ─── EXIT ─────────────────────────────────────────────────────────────
#   0 = PASS or SKIP-with-reason
#   1 = FAIL (helper broken in the current polarity)
set -uo pipefail

BOBA_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HELPER="${BOBA_ROOT}/scripts/lib/durable-run.sh"
RED_MODE="${RED_MODE:-0}"

pass() { echo "PASS: $*"; exit 0; }
fail() { echo "FAIL: $*"; exit 1; }
skip() { echo "SKIP: $*"; exit 0; }

# ─── polarity-independent pre-flight: bash -n on the helper if present
if [ -f "$HELPER" ]; then
    if ! bash -n "$HELPER" 2>/dev/null; then
        # Broken bash — always a FAIL, regardless of polarity
        fail "durable-run.sh exists but has bash -n parse errors"
    fi
fi

# ─── RED path: assert BROKEN state (helper missing OR unsourceable) ──
if [ "$RED_MODE" = "1" ]; then
    if [ ! -f "$HELPER" ]; then
        pass "RED_MODE=1 — durable-run.sh helper absent at $HELPER (BOB-064 pre-fix state reproduced)"
    fi
    # helper present — check it exports the required API surface
    # shellcheck source=/dev/null
    if ! ( source "$HELPER" 2>/dev/null && \
           declare -F durable_launch_cmd >/dev/null && \
           declare -F durable_is_active >/dev/null && \
           declare -F durable_wait_sentinel >/dev/null ); then
        pass "RED_MODE=1 — durable-run.sh present but missing required API (pre-fix state)"
    fi
    fail "RED_MODE=1 — durable-run.sh present AND API complete (BOB-064 already fixed; flip RED_MODE=0)"
fi

# ─── GREEN path: assert FIXED state (helper works end-to-end) ────────
[ -f "$HELPER" ] || fail "GREEN — durable-run.sh missing at $HELPER"

# Honest SKIP when no user systemd manager available
state="$(systemctl --user is-system-running 2>&1)"
case "$state" in
    running|degraded) : ;;
    *) skip "no systemd --user manager (state=$state) — durability requires systemd-run --user (§11.4.3 topology)" ;;
esac

# Isolate artifacts from any real DURABLE_DIR
tmp_dir="$(mktemp -d)"
export DURABLE_DIR="$tmp_dir"

# shellcheck source=/dev/null
source "$HELPER" || fail "cannot source $HELPER"

UNIT="boba-durable-guard-$$-$RANDOM"
cleanup() {
    declare -F durable_stop >/dev/null && durable_stop "$UNIT" 2>/dev/null || true
    rm -rf "$tmp_dir"
}
trap cleanup EXIT

# Launch a real short-lived sleeper with two log markers
durable_launch_cmd "$UNIT" 'echo START_MARKER; sleep 3; echo DONE_MARKER' \
    || fail "durable_launch_cmd returned non-zero"

# Poll for is-active (systemd-run returns before the unit's exec starts)
active=0
for _ in $(seq 1 30); do
    if durable_is_active "$UNIT"; then active=1; break; fi
    sleep 0.1
done
[ "$active" = 1 ] || fail "unit not active after launch — job did not survive the launcher"

# Read the MainPID + its cgroup — the load-bearing evidence
pid="$(durable_main_pid "$UNIT")"
[ "${pid:-0}" -gt 0 ] || fail "no MainPID for unit"

job_cg="$(awk -F: '$1=="0"{print $3}' "/proc/${pid}/cgroup" 2>/dev/null)"
self_cg="$(awk -F: '$1=="0"{print $3}' "/proc/$$/cgroup" 2>/dev/null)"
echo "  evidence: job cgroup  = $job_cg"
echo "  evidence: self cgroup = $self_cg"

# The .service-unit suffix is the runtime-signature (§11.4.108) that
# proves the fix is active — a session-scope cgroup would be reaped
# with the login session (the pre-fix failure mode).
case "$job_cg" in
    */"${UNIT}.service") : ;;
    *) fail "runtime-signature absent: job cgroup is not an independently-managed .service unit ($job_cg)" ;;
esac
[ "$job_cg" != "$self_cg" ] || fail "job shares launcher cgroup — would be reaped with the session"

# Wait for completion sentinel + verify real output (§11.4.107(1) — a
# single frame is not proof; we assert both markers landed in the log)
rc="$(durable_wait_sentinel "$UNIT" 20)" || fail "wait_sentinel timed out — sentinel never appeared"
[ "$rc" = 0 ] || fail "durable job exit code = $rc, want 0"
log="$(durable_fetch_log "$UNIT")"
case "$log" in
    *START_MARKER*DONE_MARKER*) : ;;
    *) fail "durable job log missing markers (did not run to completion): $log" ;;
esac

pass "durable-run.sh helper — job survived launcher in own .service cgroup, ran to completion (BOB-064 fix intact)"
