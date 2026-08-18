#!/bin/bash
# sig4_seeded_psi_fixture.sh — §11.4.115(F) RED fixture for SIG-4 (user.slice
# memory PSI full avg60 > SIG4_PSI_AVG60_LIMIT) in
# resource_pressure_signature_challenge.sh.
#
# Genuinely inducing sustained (60-second-averaged) host-wide memory
# pressure high enough to cross avg60>50 would risk violating the exact
# §12.6/§12.11/§12.12 host-safety mandates this detector exists to enforce
# — deliberately stressing the shared user.slice to the edge of the crisis
# class this project's forced-logout incidents are about is not a
# "bounded, safe" fixture, it IS the incident.
#
# Per §11.4.35 (consumer-owned data as an injection point) this fixture
# instead feeds the detector's REAL parsing + comparison code path a
# genuinely-high, REALISTICALLY-SHAPED PSI reading via the PSI_FILE
# override added to resource_pressure_signature_challenge.sh in this same
# fix. This dependency-injects the INPUT DATA — it does NOT mutate the
# comparison THRESHOLD (SIG4_PSI_AVG60_LIMIT stays at its default 50) and
# does NOT touch the parsing logic. The awk extraction + numeric comparison
# exercised here is the IDENTICAL code the real
# /sys/fs/cgroup/user.slice/user-1000.slice/memory.pressure path uses; only
# the data SOURCE differs, exactly like injecting a fixture file into any
# other parser under test.
#
# Honest boundary (§11.4.6): this is NOT a claim that real host-wide PSI
# pressure was induced and detected. It IS a claim that the detector's
# real parse-and-compare logic correctly recognizes a genuinely-pathological
# PSI VALUE in the exact on-disk kernel format — as opposed to the
# SIG-1 threshold-mutation class the §11.4.209 review's IMPORTANT-1 finding
# rejected (which mutated the THRESHOLD to a degenerate 0, not the input
# value). If a future reviewer judges data-injection insufficient for this
# signature, the honest next step is a real (bounded, time-boxed) memory
# stressor — deliberately deferred here on host-safety grounds, not
# overlooked.
#
# Usage:
#   bash challenges/fixtures/resource_pressure/sig4_seeded_psi_fixture.sh
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

# Verify the challenge script actually supports the PSI_FILE override
# before claiming this fixture proves anything — refuse honestly rather
# than silently no-op against the hardcoded path.
if ! grep -q 'PSI_FILE="\${PSI_FILE:-' "$CHALLENGE" 2>/dev/null; then
  echo "SKIP (§11.4.3): $CHALLENGE does not yet expose a PSI_FILE override — this fixture requires that change to be landed first"
  exit 2
fi

FIXTURE_PSI_FILE="$(mktemp)"
cleanup() {
  rm -f "$FIXTURE_PSI_FILE"
}
trap cleanup EXIT INT TERM

# Seeded value: full avg60=65.00 — genuinely > the default 50 threshold, in
# the EXACT kernel PSI pseudo-file format (man 5 proc; see also psi(1)):
#   some avg10=X avg60=Y avg300=Z total=N
#   full avg10=X avg60=Y avg300=Z total=N
cat > "$FIXTURE_PSI_FILE" <<'EOF'
some avg10=12.34 avg60=45.67 avg300=8.90 total=123456789
full avg10=20.11 avg60=65.00 avg300=15.22 total=98765432
EOF

echo "=== SIG-4 seeded-PSI fixture: injecting a genuinely-high (full avg60=65.00 > 50 threshold) real-format PSI reading via PSI_FILE override ==="
cat "$FIXTURE_PSI_FILE"
echo
echo "=== Running the REAL (un-mutated) challenge — default threshold, default parsing logic — against this seeded input ==="
CHALLENGE_OUT="$(PSI_FILE="$FIXTURE_PSI_FILE" bash "$CHALLENGE" 2>&1)"
CHALLENGE_RC=$?
echo "$CHALLENGE_OUT"
echo
echo "Challenge exit code: $CHALLENGE_RC"

if [ "$CHALLENGE_RC" -eq 1 ] && echo "$CHALLENGE_OUT" | grep -q "SIG-4:"; then
  echo "RED CONFIRMED: challenge correctly FAILed on a genuinely-high (avg60=65.00) PSI reading, naming SIG-4"
  exit 0
else
  echo "RED NOT REPRODUCED: challenge did not FAIL naming SIG-4 against a genuinely-over-threshold PSI reading — §11.4.115(F) violation"
  exit 1
fi
