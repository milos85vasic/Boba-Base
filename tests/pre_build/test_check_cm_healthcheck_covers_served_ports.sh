#!/usr/bin/env bash
# test_check_cm_healthcheck_covers_served_ports.sh — §1.1 paired-mutation
# meta-test for scripts/pre_build/check_cm_healthcheck_covers_served_ports.sh
# (CM-HEALTHCHECK-COVERS-SERVED-PORTS), wired as pre-build invariant 44.
#
# WHY THIS GATE NEEDED A META-TEST IN *BOTH* DIRECTIONS (§11.4.201(1)):
#   This gate has a DOCUMENTED false-positive history. CLAUDE.md records it
#   verbatim: the gate "failed a service whose healthcheck was already correct
#   — a §11.4.201(1) false-positive refusal caused by trusting the doc over
#   the Dockerfile." The defect was in the gate's consumer-owned INPUT DATA
#   (config/served_ports.yaml declared qbittorrent-proxy-go as serving
#   7186+7187+7188 on the strength of stale README prose, when the container
#   runs ONE binary that binds only 7187). So a golden-TRUE arm alone would
#   validate half of this gate. The golden-FALSE arms below are the
#   load-bearing half: a false refusal is a FAIL-bluff exactly as forbidden as
#   a false pass, and this gate has already committed one.
#
# WHY THIS DRIVES THE REAL GATE (§11.4.249 producer != oracle):
#   Every arm EXECUTES scripts/pre_build/check_cm_healthcheck_covers_served_ports.sh
#   — the boba delegator, which is what pre_build_verification.sh actually
#   runs — and reads its exit code. The harness does NOT re-implement the
#   port-coverage analysis; a harness that reproduces the detector cannot see
#   the gate (or the shared engine behind it) drift.
#
# SCOPE NOTE (§11.4.177): the DETECTION ENGINE lives in the constitution
#   submodule and carries its own mutation test. This harness covers what that
#   one structurally cannot: the boba delegator's argument plumbing, its
#   missing-engine ERROR branch, and — most importantly — boba's OWN scope
#   DATA at config/served_ports.yaml, which is exactly where the historical
#   false positive lived.
#
# ARMS
#   golden-FALSE (must PASS, rc=0) — the load-bearing direction
#     F1  the REAL repo defaults: docker-compose.yml + config/served_ports.yaml
#         with no arguments. This is the arm that would have caught the
#         historical false positive at authoring time.
#     F2  the exact shape that produced it: a service with a CORRECT single-
#         port healthcheck whose block also carries UNSERVED port env vars
#         (a dependency port, and ports the container declares but never
#         binds). The gate must not demand coverage for a port not served.
#     F3  a multi-port service whose healthcheck probes BOTH served ports.
#   carrier (must PASS — §11.4.201(7)(a) the number is MENTIONED, not served)
#     R1  the served port number appears in an UNRELATED service's block and
#         in a YAML comment; coverage must be judged from THIS service's
#         healthcheck only, not from the file containing the digits.
#   golden-TRUE (must FAIL, rc=1, naming the offender)
#     T1  BOB-138 itself: serves 7186+7187, healthcheck probes only 7186.
#     T2  a declared service with NO healthcheck at all.
#     T3  substring evasion: healthcheck probes 71870, served port is 7187.
#     T4  a manifest entry ABSENT from the compose file (stale declaration).
#     T5  a compose service with ports/healthcheck UNDECLARED in the manifest.
#     T6  Property A — zero services checked is BLIND, not clean.
#     T7  a missing input file is FAIL, never a silent skip.
#     T8  Property B — no python with PyYAML is FAIL, never SKIP.
#   error (must ERROR, rc=2)
#     E1  the shared engine absent -> honest ERROR naming the submodule.
#   control needle (§11.4.201(7)(b))
#     N1  take the fixture pair that just PASSed, change ONE digit in its
#         healthcheck, re-run through the SAME path, and require a flip to
#         FAIL. Without this the PASS arms are unproven zeros.
#
# Exit: 0 every arm matched | 1 divergence (gate not trustworthy) | 2 harness error.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
GATE="$REPO_ROOT/scripts/pre_build/check_cm_healthcheck_covers_served_ports.sh"
ENGINE="$REPO_ROOT/constitution/scripts/gates/cm_healthcheck_covers_served_ports.sh"

if [[ ! -f "$GATE" ]]; then
    echo "HARNESS ERROR: gate not found at $GATE" >&2; exit 2
fi
if [[ ! -f "$ENGINE" ]]; then
    # §11.4.201(6): without the engine every arm below would ERROR for the
    # wrong reason and the run would prove nothing. Refuse, do not "skip".
    echo "HARNESS ERROR: shared engine missing at $ENGINE" >&2
    echo "  run 'git submodule update --init constitution'" >&2; exit 2
fi

TMPD="$(mktemp -d -t cm_hcports_meta.XXXXXX)"
trap 'rm -rf "$TMPD"' EXIT
fails=0

# run_arm <name> <expected-rc> <needle|-> <gate args...>
run_arm() {
    local name="$1" want="$2" needle="$3"; shift 3
    local out rc
    out="$(bash "$GATE" "$@" 2>&1)"; rc=$?
    if [[ "$rc" -ne "$want" ]]; then
        echo "FAIL: $name — expected rc=$want got rc=$rc"
        printf '%s\n' "$out" | sed 's/^/      /'
        fails=$((fails + 1)); return
    fi
    if [[ "$needle" != "-" ]] && ! printf '%s' "$out" | grep -qF -- "$needle"; then
        echo "FAIL: $name — rc=$want as expected but output never said '$needle'"
        printf '%s\n' "$out" | sed 's/^/      /'
        fails=$((fails + 1)); return
    fi
    echo "PASS: $name (rc=$rc)"
}

echo "=== paired-mutation meta-test: CM-HEALTHCHECK-COVERS-SERVED-PORTS ==="
echo

# ---------------------------------------------------------------------------
# golden-FALSE F1 — the REAL repo defaults, invoked exactly as pre-build does.
# This arm is the standing guard against the documented false-positive class
# recurring in boba's own scope DATA (config/served_ports.yaml).
# ---------------------------------------------------------------------------
run_arm "golden-FALSE F1 real docker-compose.yml + config/served_ports.yaml" 0 \
        "CM-HEALTHCHECK-COVERS-SERVED-PORTS: PASS"

# §11.4.201(9) field identity: a PASS that verified ZERO services would be a
# false-null wearing a pass's uniform. Assert the count is a real positive.
F1_OUT="$(bash "$GATE" 2>&1)"
F1_N="$(printf '%s' "$F1_OUT" | sed -n 's/.*PASS (\([0-9]\{1,\}\) services verified).*/\1/p')"
if [[ -n "$F1_N" && "$F1_N" -gt 0 ]]; then
    echo "PASS: golden-FALSE F1 verdict names a non-zero service count ($F1_N)"
else
    echo "FAIL: golden-FALSE F1 PASSed without naming a positive verified count"
    printf '%s\n' "$F1_OUT" | sed 's/^/      /'; fails=$((fails + 1))
fi

# ---------------------------------------------------------------------------
# golden-FALSE F2 — the exact shape of the historical false positive.
# The service block carries port env vars it does NOT serve: a dependency
# port it only connects to, and ports the image declares but never binds. Its
# healthcheck correctly probes the one port it really serves.
# ---------------------------------------------------------------------------
cat > "$TMPD/f2_compose.yml" <<'YAML'
services:
  qbittorrent-proxy-go:
    network_mode: host
    environment:
      - PROXY_PORT=7186          # declared in env, bound by no process
      - BRIDGE_PORT=7188         # a separate binary this container never starts
      - MERGE_SERVICE_PORT=7187  # the ONE port this container actually serves
      - QBITTORRENT_PORT=7185    # an UPSTREAM dependency, not served here
    healthcheck:
      test: ["CMD-SHELL", "wget -qO- http://127.0.0.1:7187/health || exit 1"]
YAML
cat > "$TMPD/f2_manifest.yml" <<'YAML'
schema_version: 1
services:
  qbittorrent-proxy-go:
    serves: [7187]
YAML
run_arm "golden-FALSE F2 correct hc + unserved env ports must NOT be demanded" 0 \
        "ok  qbittorrent-proxy-go" "$TMPD/f2_compose.yml" "$TMPD/f2_manifest.yml"

# ---------------------------------------------------------------------------
# golden-FALSE F3 — a genuinely multi-port service, fully covered.
# ---------------------------------------------------------------------------
cat > "$TMPD/f3_compose.yml" <<'YAML'
services:
  download-proxy:
    healthcheck:
      test: ["CMD-SHELL", "curl -fsS http://127.0.0.1:7186/ && curl -fsS http://127.0.0.1:7187/ || exit 1"]
YAML
cat > "$TMPD/f3_manifest.yml" <<'YAML'
schema_version: 1
services:
  download-proxy:
    serves: [7186, 7187]
YAML
run_arm "golden-FALSE F3 multi-port service with both ports probed" 0 \
        "PASS (1 services verified)" "$TMPD/f3_compose.yml" "$TMPD/f3_manifest.yml"

# ---------------------------------------------------------------------------
# CARRIER R1 (§11.4.201(7)(a)) — the served digits appear elsewhere in the
# file (a comment, and a NEIGHBOUR service's healthcheck) but the service
# under test probes its own port correctly. Coverage must be decided from
# THIS service's healthcheck, never from "the number is in the file".
# ---------------------------------------------------------------------------
cat > "$TMPD/r1_compose.yml" <<'YAML'
services:
  # note: the merge service historically lived on 7187 behind this proxy
  neighbour:
    healthcheck:
      test: ["CMD-SHELL", "curl -fsS http://127.0.0.1:7187/ || exit 1"]
  boba-jackett:
    healthcheck:
      test: ["CMD-SHELL", "curl -fsS http://127.0.0.1:7189/ || exit 1"]
YAML
cat > "$TMPD/r1_manifest.yml" <<'YAML'
schema_version: 1
services:
  neighbour:
    serves: [7187]
  boba-jackett:
    serves: [7189]
YAML
run_arm "carrier R1 digits elsewhere in the file do not decide coverage" 0 \
        "PASS (2 services verified)" "$TMPD/r1_compose.yml" "$TMPD/r1_manifest.yml"

# ---------------------------------------------------------------------------
# golden-TRUE arms — each must be REFUSED.
# ---------------------------------------------------------------------------
cat > "$TMPD/t1_compose.yml" <<'YAML'
services:
  download-proxy:
    healthcheck:
      test: ["CMD-SHELL", "curl -fsS http://127.0.0.1:7186/ || exit 1"]
YAML
run_arm "golden-TRUE T1 BOB-138: serves 7186+7187, probes only 7186" 1 \
        "probes none of [7187]" "$TMPD/t1_compose.yml" "$TMPD/f3_manifest.yml"

cat > "$TMPD/t2_compose.yml" <<'YAML'
services:
  boba-jackett:
    image: boba-jackett:local
YAML
cat > "$TMPD/t2_manifest.yml" <<'YAML'
schema_version: 1
services:
  boba-jackett:
    serves: [7189]
YAML
run_arm "golden-TRUE T2 declared service with NO healthcheck" 1 \
        "declares NO healthcheck at all" "$TMPD/t2_compose.yml" "$TMPD/t2_manifest.yml"

cat > "$TMPD/t3_compose.yml" <<'YAML'
services:
  svc:
    healthcheck:
      test: ["CMD-SHELL", "curl -fsS http://127.0.0.1:71870/ || exit 1"]
YAML
cat > "$TMPD/t3_manifest.yml" <<'YAML'
schema_version: 1
services:
  svc:
    serves: [7187]
YAML
run_arm "golden-TRUE T3 substring 71870 must not satisfy served 7187" 1 \
        "probes none of [7187]" "$TMPD/t3_compose.yml" "$TMPD/t3_manifest.yml"

cat > "$TMPD/t4_manifest.yml" <<'YAML'
schema_version: 1
services:
  download-proxy:
    serves: [7186, 7187]
  vanished:
    serves: [1234]
YAML
run_arm "golden-TRUE T4 stale manifest entry absent from compose" 1 \
        "ABSENT from" "$TMPD/f3_compose.yml" "$TMPD/t4_manifest.yml"

cat > "$TMPD/t5_compose.yml" <<'YAML'
services:
  download-proxy:
    healthcheck:
      test: ["CMD-SHELL", "curl -fsS http://127.0.0.1:7186/ && curl -fsS http://127.0.0.1:7187/ || exit 1"]
  ghost:
    ports:
      - "9999:9999"
YAML
run_arm "golden-TRUE T5 undeclared compose service is not exempt" 1 \
        "UNDECLARED in" "$TMPD/t5_compose.yml" "$TMPD/f3_manifest.yml"

cat > "$TMPD/t6_compose.yml" <<'YAML'
services:
  plain:
    image: alpine
YAML
cat > "$TMPD/t6_manifest.yml" <<'YAML'
schema_version: 1
services: {}
YAML
run_arm "golden-TRUE T6 Property A: zero services checked is BLIND not clean" 1 \
        "checked 0 services" "$TMPD/t6_compose.yml" "$TMPD/t6_manifest.yml"

run_arm "golden-TRUE T7 a missing input file FAILs, never skips" 1 \
        "missing input" "$TMPD/does_not_exist.yml" "$TMPD/f3_manifest.yml"

# Property B — no YAML parser is a BLIND gate, and blind is FAIL not SKIP.
# The delegator hands PYTHON_BIN to the engine as the FIRST candidate but the
# engine still falls back to python3/python (correct behaviour), so this arm
# must starve the candidate list at the engine boundary to test the property.
B_OUT="$(HEALTHCHECK_PORTS_PYTHON="/nonexistent/python" bash "$ENGINE" \
        --compose "$TMPD/f3_compose.yml" --manifest "$TMPD/f3_manifest.yml" 2>&1)"; B_RC=$?
if [[ "$B_RC" -eq 1 ]] && printf '%s' "$B_OUT" | grep -qF 'BLIND gate'; then
    echo "PASS: golden-TRUE T8 Property B: no PyYAML is FAIL-because-blind (rc=1)"
else
    echo "FAIL: golden-TRUE T8 — a gate with no YAML parser must FAIL, got rc=$B_RC"
    printf '%s\n' "$B_OUT" | sed 's/^/      /'; fails=$((fails + 1))
fi

# ---------------------------------------------------------------------------
# ERROR E1 — engine absent. The delegator must say so honestly with rc=2, not
# silently pass because it had nothing to run. Exercised on a THROWAWAY COPY
# in a fixture tree with no constitution/ submodule; this is a test fixture,
# not a §11.4.177 production copy, and it is deleted with the temp dir.
# ---------------------------------------------------------------------------
mkdir -p "$TMPD/fakeroot/scripts/pre_build"
cp "$GATE" "$TMPD/fakeroot/scripts/pre_build/"
E_OUT="$(bash "$TMPD/fakeroot/scripts/pre_build/$(basename "$GATE")" \
        "$TMPD/f3_compose.yml" "$TMPD/f3_manifest.yml" 2>&1)"; E_RC=$?
if [[ "$E_RC" -eq 2 ]] && printf '%s' "$E_OUT" | grep -qF 'shared gate engine missing'; then
    echo "PASS: ERROR E1 absent engine is an honest rc=2, never a quiet pass"
else
    echo "FAIL: ERROR E1 — expected rc=2 naming the missing engine, got rc=$E_RC"
    printf '%s\n' "$E_OUT" | sed 's/^/      /'; fails=$((fails + 1))
fi

# ---------------------------------------------------------------------------
# CONTROL NEEDLE (§11.4.201(7)(b)) — every PASS arm above asserts an ABSENCE
# of findings. An absence is not evidence until the instrument is proven able
# to SEE through the SAME path. Take F3's fixture pair (which just PASSed),
# change ONE digit of its healthcheck, and require the verdict to flip.
# ---------------------------------------------------------------------------
sed 's|127\.0\.0\.1:7187|127.0.0.1:7999|' "$TMPD/f3_compose.yml" > "$TMPD/needle_compose.yml"
N_OUT="$(bash "$GATE" "$TMPD/needle_compose.yml" "$TMPD/f3_manifest.yml" 2>&1)"; N_RC=$?
if [[ "$N_RC" -eq 1 ]] && printf '%s' "$N_OUT" | grep -qF 'probes none of [7187]'; then
    echo "PASS: control needle — the same path that PASSed F3 DOES see a one-digit break"
else
    echo "FAIL: control needle — gate did not fire on a fixture broken by one digit"
    echo "      (rc=$N_RC). Every PASS arm above is therefore an unproven zero."
    printf '%s\n' "$N_OUT" | sed 's/^/      /'; fails=$((fails + 1))
fi

echo
if [[ "$fails" -gt 0 ]]; then
    echo "=== META-TEST FAIL: $fails arm(s) diverged — the gate is not trustworthy ==="
    exit 1
fi
echo "=== META-TEST PASS: gate refuses every uncovered-port shape, stays quiet on"
echo "    correct services and carriers, refuses blindness, and is proven seeing ==="
exit 0
