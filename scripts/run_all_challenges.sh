#!/usr/bin/env bash
# run_all_challenges.sh — Boba-specific challenge aggregator
#
# Sources challenge scripts from the challenges submodule
# and the meta-runner challenges_describe_challenge.sh.
# Reports pass/fail/skip counts and returns non-zero on any failure.
#
# Constitution: §11.4.109 (anti-forgetting), CONST-033 (host power management),
# §11.4 (anti-bluff covenant), §1.1 (paired mutation)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Opt-in DURABLE execution (§5 / pkg/remoteexec): when BOBA_DURABLE=1, re-exec
# this aggregator as a transient systemd --user unit so a long run survives the
# SSH/login session ending (logind would otherwise reap it). Default behavior is
# unchanged when BOBA_DURABLE is unset. The mechanism is the shared containers
# helper — single-sourced, not copy-pasted per repo.
DURABLE_LIB="${PROJECT_ROOT}/submodules/containers/scripts/lib/durable-run.sh"
if [[ "${BOBA_DURABLE:-0}" == "1" && "${BOBA_DURABLE_CHILD:-0}" != "1" ]]; then
  if [[ ! -f "$DURABLE_LIB" ]]; then
    echo "BOBA_DURABLE=1 but durable helper not found at $DURABLE_LIB" >&2; exit 2
  fi
  # shellcheck source=/dev/null
  source "$DURABLE_LIB"
  UNIT="${BOBA_DURABLE_UNIT:-boba-challenges-$(date +%s)}"
  # Absolute self-path: the systemd --user unit runs with a different CWD, so a
  # relative ${BASH_SOURCE[0]} would not resolve.
  SELF="${SCRIPT_DIR}/$(basename "${BASH_SOURCE[0]}")"
  durable_launch_cmd "$UNIT" "BOBA_DURABLE_CHILD=1 bash ${SELF@Q} $*"
  echo "[durable] challenge run launched as user unit: ${UNIT}"
  if [[ "${BOBA_DURABLE_WAIT:-1}" == "1" ]]; then
    rc="$(durable_wait_sentinel "$UNIT" "${BOBA_DURABLE_TIMEOUT:-3600}")" || {
      echo "[durable] timed out waiting for ${UNIT}" >&2; exit 1; }
    durable_fetch_log "$UNIT"
    durable_stop "$UNIT"
    exit "$rc"
  fi
  echo "[durable] detached; tail with: systemctl --user status ${UNIT}"
  exit 0
fi

# Source anti-bluff helpers if available
if [[ -f "${PROJECT_ROOT}/submodules/challenges/lib/anti_bluff.sh" ]]; then
  source "${PROJECT_ROOT}/submodules/challenges/lib/anti_bluff.sh"
fi

CHALLENGES_DIR="${PROJECT_ROOT}/submodules/challenges/challenges/scripts"
CHALLENGES_META="${PROJECT_ROOT}/submodules/challenges/challenges_describe_challenge.sh"

# Challenge scripts to run (in order), relative to CHALLENGES_DIR
CHALLENGE_SCRIPTS=(
  "no_suspend_calls_challenge.sh"       # CONST-033 mandatory
  "host_no_auto_suspend_challenge.sh"    # CONST-033 mandatory
  "bluff_scanner_challenge.sh"
  "anchor_manifest_challenge.sh"
  "challenges_compile_challenge.sh"
  "challenges_functionality_challenge.sh"
  "challenges_unit_challenge.sh"
  "chaos_failure_injection_challenge.sh"
  "ddos_health_flood_challenge.sh"
  "mutation_ratchet_challenge.sh"
  "recording_pipeline_challenge.sh"
  "scaling_horizontal_challenge.sh"
  "stress_sustained_load_challenge.sh"
  "ui_terminal_interaction_challenge.sh"
  "ux_end_to_end_flow_challenge.sh"
)

PASS=0
FAIL=0
SKIP=0
TOTAL=0

echo "=== Boba Challenge Aggregator ==="
echo "Challenges dir: ${CHALLENGES_DIR}"
echo "Project root:   ${PROJECT_ROOT}"
echo "Date:           $(date)"
echo ""

# Run each challenge script
for script in "${CHALLENGE_SCRIPTS[@]}"; do
  script_path="${CHALLENGES_DIR}/${script}"
  TOTAL=$((TOTAL + 1))

  if [[ ! -f "${script_path}" ]]; then
    echo "  SKIP: ${script} — not found"
    SKIP=$((SKIP + 1))
    continue
  fi

  if [[ ! -x "${script_path}" ]]; then
    echo "  SKIP: ${script} — not executable"
    SKIP=$((SKIP + 1))
    continue
  fi

  echo "  RUN:  ${script} (timeout 180s)"
  start_ts=$(date +%s)

  if timeout 180 bash "${script_path}" 2>&1; then
    echo "  PASS: ${script}"
    PASS=$((PASS + 1))
  else
    exit_code=$?
    echo "  FAIL: ${script} (exit code ${exit_code})"
    FAIL=$((FAIL + 1))
  fi

  end_ts=$(date +%s)
  elapsed=$((end_ts - start_ts))
  echo "        (${elapsed}s elapsed)"
  echo ""
done

# Run the meta-runner: challenges_describe_challenge.sh
TOTAL=$((TOTAL + 1))
if [[ -f "${CHALLENGES_META}" ]] && [[ -x "${CHALLENGES_META}" ]]; then
  echo "  RUN:  challenges_describe_challenge.sh (meta-runner, timeout 180s)"
  start_ts=$(date +%s)

  if timeout 180 bash "${CHALLENGES_META}" 2>&1; then
    echo "  PASS: challenges_describe_challenge.sh"
    PASS=$((PASS + 1))
  else
    exit_code=$?
    echo "  FAIL: challenges_describe_challenge.sh (exit code ${exit_code})"
    FAIL=$((FAIL + 1))
  fi

  end_ts=$(date +%s)
  elapsed=$((end_ts - start_ts))
  echo "        (${elapsed}s elapsed)"
  echo ""
else
  echo "  SKIP: challenges_describe_challenge.sh — not found or not executable"
  SKIP=$((SKIP + 1))
fi

# Summary
echo "=== Summary ==="
echo "PASS: ${PASS}"
echo "FAIL: ${FAIL}"
echo "SKIP: ${SKIP}"
echo "TOTAL: ${TOTAL}"

if [[ "${FAIL}" -gt 0 ]]; then
  exit 1
fi
exit 0
