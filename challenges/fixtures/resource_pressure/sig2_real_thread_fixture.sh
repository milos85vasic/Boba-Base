#!/bin/bash
# sig2_real_thread_fixture.sh — §11.4.115(F) RED fixture for SIG-2 (thread
# utilization >SIG2_THREAD_PCT% of ulimit -Su) in
# resource_pressure_signature_challenge.sh.
#
# Rather than mutating the THRESHOLD to a degenerate value (the class the
# §11.4.209 review's IMPORTANT-1 finding rejected for SIG-1's polarity
# evidence), this fixture takes the REAL, currently-live, system-wide
# thread count for $USER — measured with the SAME `ps -L -u $USER | wc -l`
# the detector itself uses — and LOWERS ulimit -Su in a SUBSHELL ONLY so
# that REAL count exceeds 70% of the (lowered) soft limit. This matches the
# review's own suggested design for SIG-2 verbatim: "shim reducing
# ulimit -Su to a value less than current threads * 100/70 (subshell only),
# assert exit 1."
#
# No thread or process is spawned by this fixture. The lowered ulimit is
# scoped to a bash subshell + its children (the challenge script is invoked
# FROM inside the subshell so it inherits the lowered soft limit via fork)
# and never touches any other process on the host — the reduction
# self-reverts the instant the subshell exits (§9.2: no host-wide side
# effect, nothing to clean up).
#
# Usage:
#   bash challenges/fixtures/resource_pressure/sig2_real_thread_fixture.sh
#
# Exit:
#   0 = RED confirmed  1 = RED not reproduced  2 = instrument/precondition SKIP

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
CHALLENGE="$REPO_ROOT/challenges/scripts/resource_pressure_signature_challenge.sh"

if [ ! -r "$CHALLENGE" ]; then
  echo "SKIP (§11.4.3): challenge script not found at $CHALLENGE"
  exit 2
fi

USER_NAME="${USER:-$(id -un)}"
BASELINE=$(ps -L --no-headers -u "$USER_NAME" 2>/dev/null | wc -l)
HARD_LIMIT=$(ulimit -Hu 2>/dev/null || echo 0)

if [ -z "$BASELINE" ] || [ "$BASELINE" -le 0 ]; then
  echo "SKIP (§11.4.3): could not measure a baseline thread count for $USER_NAME"
  exit 2
fi

# Target soft limit so BASELINE/soft_limit ~= 72% — safely above the 70%
# default threshold, leaving a ~39%-of-baseline buffer above BASELINE for
# the challenge script's own transient forks (ps/awk/grep/podman/wc, etc.)
# so THIS fixture's own execution never hits EAGAIN on the lowered limit.
SOFT_LIMIT=$((BASELINE * 100 / 72))
if [ "$HARD_LIMIT" != "unlimited" ] && [ "$HARD_LIMIT" -gt 0 ] && [ "$SOFT_LIMIT" -gt "$HARD_LIMIT" ]; then
  echo "SKIP (§11.4.3): computed soft limit $SOFT_LIMIT exceeds hard limit $HARD_LIMIT — baseline thread count ($BASELINE) is too high on this host to fixture safely"
  exit 2
fi
if [ "$SOFT_LIMIT" -le "$BASELINE" ]; then
  echo "SKIP (§11.4.3): computed soft limit $SOFT_LIMIT does not exceed baseline $BASELINE — arithmetic guard tripped, refusing to proceed"
  exit 2
fi

UTIL_PCT=$((BASELINE * 100 / SOFT_LIMIT))
echo "=== SIG-2 real-thread fixture: baseline=$BASELINE threads (system-wide, $USER_NAME), lowering ulimit -Su to $SOFT_LIMIT (subshell-only) ==="
echo "  target utilization at baseline = ${UTIL_PCT}% (threshold is 70%)"

(
  if ! ulimit -Su "$SOFT_LIMIT" 2>/dev/null; then
    echo "SKIP (§11.4.3): ulimit -Su $SOFT_LIMIT rejected by this shell"
    exit 2
  fi
  echo "Subshell soft limit now: $(ulimit -Su)"
  echo
  echo "=== Running the REAL (un-mutated) challenge under the lowered soft limit ==="
  CHALLENGE_OUT="$(bash "$CHALLENGE" 2>&1)"
  CHALLENGE_RC=$?
  echo "$CHALLENGE_OUT"
  echo
  echo "Challenge exit code: $CHALLENGE_RC"
  if [ "$CHALLENGE_RC" -eq 1 ] && echo "$CHALLENGE_OUT" | grep -q "SIG-2:"; then
    echo "RED CONFIRMED: challenge correctly FAILed on genuine thread-utilization >70%, naming SIG-2"
    exit 0
  else
    echo "RED NOT REPRODUCED: challenge did not FAIL naming SIG-2 under a genuinely-elevated thread-utilization ratio — §11.4.115(F) violation"
    exit 1
  fi
)
RC=$?
echo "=== fixture subshell exited with $RC — host-wide ulimit is unaffected (subshell-scoped, self-reverted) ==="
exit "$RC"
