#!/usr/bin/env bash
# rutracker_redos_regex_bounds_challenge.sh — BOB-093
#
# Verifies that the ReDoS-hardened bounded quantifier regex from commit
# 7de2802 (fix(rutracker)+test: §11.4.85 plugin ReDoS suite + fix quadratic
# search regex) is actually deployed live inside the qbittorrent-proxy
# container — closes the §11.4.108 SOURCE→ARTIFACT→RUNTIME layer-3 gap
# left by Task #86 which only verified source-side.
#
# The original quadratic pattern was:
#   re_search_queries = re.compile(r'<a.+?href="tracker\.php\?(.*?start=\d+)"')
# The bounded (fixed) pattern is:
#   re_search_queries = re.compile(r'<a[^>]{0,512}?href="tracker\.php\?([^"]{0,256}?start=\d+)"')
#
# §11.4.115 polarity switch:
#   RED_MODE=1 (default) — assert the DEPLOYED regex is the BOUNDED (safe) form.
#                          Also assert the UNSAFE (unbounded) shape is absent.
#   RED_MODE=0            — same as RED_MODE=1 (single-oracle harness); this
#                          mode is preserved for compatibility with the
#                          RED-then-GREEN polarity flip a fix-cycle uses.
#
# §11.4.107(10) self-validated: two internal fixtures are checked in-process
# — golden-good (the exact bounded regex line) MUST match the safe assertion;
# golden-bad (the exact legacy unbounded regex line) MUST match the unsafe
# assertion. An analyzer that passes golden-bad is itself the bluff.
#
# §11.4.69 machine-readable evidence written to docs/qa/BOB-093/.
#
# Exit codes:
#   0 — bounded regex present in deployed plugin; self-validation passed.
#   1 — deployed regex is NOT the bounded form OR self-validation failed.
#   2 — harness or environment error (container down, plugin missing).
#     (per §11.4.144: availability failures SKIP rather than FAIL — rc=2 with
#     an honest reason payload is the SKIP-with-reason channel.)
#
# Cross-refs: §11.4.85 §11.4.107(10) §11.4.108 §11.4.115 §11.4.201 §11.4.232.

set -euo pipefail

CHALLENGE_NAME="rutracker_redos_regex_bounds_challenge"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EVIDENCE_DIR="${REPO_ROOT}/docs/qa/BOB-093"
mkdir -p "${EVIDENCE_DIR}"
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
EVIDENCE_FILE="${EVIDENCE_DIR}/run_${RUN_ID}.txt"
VERDICT_FILE="${EVIDENCE_DIR}/verdict_${RUN_ID}.json"

RED_MODE="${RED_MODE:-1}"
CONTAINER="qbittorrent-proxy"
PLUGIN_PATH="/config/qBittorrent/nova3/engines/rutracker.py"

# Container runtime autodetect (podman preferred per §11.4.161).
if command -v podman >/dev/null 2>&1; then
  CR=podman
elif command -v docker >/dev/null 2>&1; then
  CR=docker
else
  echo "SKIP: no container runtime (neither podman nor docker present)" | tee "${EVIDENCE_FILE}"
  printf '{"challenge":"%s","verdict":"SKIP","reason":"no_container_runtime","run_id":"%s"}\n' \
    "${CHALLENGE_NAME}" "${RUN_ID}" > "${VERDICT_FILE}"
  exit 2
fi

log() { printf '%s\n' "$*" | tee -a "${EVIDENCE_FILE}"; }

log "== ${CHALLENGE_NAME} run_id=${RUN_ID} RED_MODE=${RED_MODE} =="

# --- §11.4.144 availability check ---------------------------------------
if ! ${CR} ps --format '{{.Names}}' 2>/dev/null | grep -qx "${CONTAINER}"; then
  log "SKIP: container '${CONTAINER}' not running (reason=hardware_not_present)"
  printf '{"challenge":"%s","verdict":"SKIP","reason":"container_not_running","run_id":"%s"}\n' \
    "${CHALLENGE_NAME}" "${RUN_ID}" > "${VERDICT_FILE}"
  exit 2
fi

if ! ${CR} exec "${CONTAINER}" test -f "${PLUGIN_PATH}" 2>/dev/null; then
  log "SKIP: plugin ${PLUGIN_PATH} absent in container (reason=plugin_not_installed)"
  log "     remediation: run ./install-plugin.sh from repo root, then retry"
  printf '{"challenge":"%s","verdict":"SKIP","reason":"plugin_not_installed","run_id":"%s"}\n' \
    "${CHALLENGE_NAME}" "${RUN_ID}" > "${VERDICT_FILE}"
  exit 2
fi

# --- Extract deployed plugin bytes --------------------------------------
DEPLOYED_COPY="${EVIDENCE_DIR}/rutracker_deployed_${RUN_ID}.py"
${CR} exec "${CONTAINER}" cat "${PLUGIN_PATH}" > "${DEPLOYED_COPY}"
DEPLOYED_SHA="$(sha256sum "${DEPLOYED_COPY}" | awk '{print $1}')"
log "deployed_sha256=${DEPLOYED_SHA}"
log "deployed_bytes=$(wc -c < "${DEPLOYED_COPY}")"

# --- Assertions ---------------------------------------------------------
BOUNDED_RE='re_search_queries = re\.compile\(r.<a\[\^>\]\{0,512\}\?href="tracker\\\.php\\\?\(\[\^"\]\{0,256\}\?start=\\d\+\)".\)'
UNSAFE_RE='re_search_queries = re\.compile\(r.<a\.\+\?href="tracker\\\.php\\\?\(\.\*\?start=\\d\+\)".\)'

BOUNDED_HITS=$(grep -cE "${BOUNDED_RE}" "${DEPLOYED_COPY}" || true)
UNSAFE_HITS=$(grep -cE "${UNSAFE_RE}" "${DEPLOYED_COPY}" || true)

log "assertion.bounded_pattern_matches=${BOUNDED_HITS} (expected: 1)"
log "assertion.unsafe_pattern_matches=${UNSAFE_HITS} (expected: 0)"

# --- §11.4.107(10) self-validation ---------------------------------------
GOOD_FIXTURE=$(mktemp)
BAD_FIXTURE=$(mktemp)
cat > "${GOOD_FIXTURE}" <<'GOOD_EOF'
    re_search_queries = re.compile(r'<a[^>]{0,512}?href="tracker\.php\?([^"]{0,256}?start=\d+)"')
GOOD_EOF
cat > "${BAD_FIXTURE}" <<'BAD_EOF'
    re_search_queries = re.compile(r'<a.+?href="tracker\.php\?(.*?start=\d+)"')
BAD_EOF

GOOD_BOUNDED=$(grep -cE "${BOUNDED_RE}" "${GOOD_FIXTURE}" || true)
GOOD_UNSAFE=$(grep -cE "${UNSAFE_RE}"  "${GOOD_FIXTURE}" || true)
BAD_BOUNDED=$(grep -cE  "${BOUNDED_RE}" "${BAD_FIXTURE}"  || true)
BAD_UNSAFE=$(grep -cE   "${UNSAFE_RE}"  "${BAD_FIXTURE}"  || true)
rm -f "${GOOD_FIXTURE}" "${BAD_FIXTURE}"

log "self_validation.golden_good bounded=${GOOD_BOUNDED} unsafe=${GOOD_UNSAFE} (expect 1/0)"
log "self_validation.golden_bad  bounded=${BAD_BOUNDED}  unsafe=${BAD_UNSAFE}  (expect 0/1)"

SV_OK=1
[[ "${GOOD_BOUNDED}" == "1" && "${GOOD_UNSAFE}" == "0" ]] || SV_OK=0
[[ "${BAD_BOUNDED}"  == "0" && "${BAD_UNSAFE}"  == "1" ]] || SV_OK=0

if [[ "${SV_OK}" != "1" ]]; then
  log "FAIL: analyzer self-validation broken — pattern regex is unreliable"
  printf '{"challenge":"%s","verdict":"FAIL","reason":"analyzer_self_validation_failed","run_id":"%s","deployed_sha256":"%s"}\n' \
    "${CHALLENGE_NAME}" "${RUN_ID}" "${DEPLOYED_SHA}" > "${VERDICT_FILE}"
  exit 1
fi

# --- §11.4.115 polarity check on deployed artifact ----------------------
if [[ "${BOUNDED_HITS}" == "1" && "${UNSAFE_HITS}" == "0" ]]; then
  log "PASS: deployed rutracker.py carries bounded ReDoS-safe regex (§11.4.108 layer-3 verified)"
  printf '{"challenge":"%s","verdict":"PASS","run_id":"%s","deployed_sha256":"%s","bounded_hits":%s,"unsafe_hits":%s,"evidence":"%s"}\n' \
    "${CHALLENGE_NAME}" "${RUN_ID}" "${DEPLOYED_SHA}" "${BOUNDED_HITS}" "${UNSAFE_HITS}" "${EVIDENCE_FILE}" > "${VERDICT_FILE}"
  exit 0
else
  log "FAIL: deployed rutracker.py DOES NOT carry the ReDoS-safe bounded regex"
  log "     bounded_hits=${BOUNDED_HITS} unsafe_hits=${UNSAFE_HITS}"
  log "     remediation: rebuild+restart the qbittorrent-proxy container (./start.sh --reload-plugins after ./install-plugin.sh)"
  printf '{"challenge":"%s","verdict":"FAIL","reason":"bounded_regex_not_deployed","run_id":"%s","deployed_sha256":"%s","bounded_hits":%s,"unsafe_hits":%s}\n' \
    "${CHALLENGE_NAME}" "${RUN_ID}" "${DEPLOYED_SHA}" "${BOUNDED_HITS}" "${UNSAFE_HITS}" > "${VERDICT_FILE}"
  exit 1
fi
