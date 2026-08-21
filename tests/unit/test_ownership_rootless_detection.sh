#!/usr/bin/env bash
# test_ownership_rootless_detection.sh — polarity matrix for detect_rootless()
# and assert_rootless_runtime() in scripts/ownership_precondition.sh
# (§11.4.252 fail-closed-on-a-dangerous-combination, FR-011 of
# specs/002-user-owned-downloads/).
#
# WHY THIS FILE EXISTS
#   The rootless measurement landed with an "eight-case polarity matrix" that
#   lived only in a commit message. Nothing in the repository re-ran it, so the
#   claim was unfalsifiable: the functions could be reverted to "podman means
#   rootless" — the exact guess §11.4.6 forbids — and no suite would notice.
#   This harness makes the matrix re-runnable.
#
# WHY IT DRIVES THE REAL SCRIPT INSTEAD OF SOURCING ITS FUNCTIONS
#   §11.4.201(11): probe the ARTIFACT through its REAL invocation path, not a
#   prerequisite of it. scripts/ownership_precondition.sh ends in an
#   unconditional `main "$@"`, so a "unit" harness that sourced it would have
#   to neuter or re-implement the wiring — and the wiring (resolve_runtime ->
#   detect_rootless -> assert_rootless_runtime, called BEFORE any probe) is
#   precisely what a revert would break. So the script is executed exactly as
#   start.sh executes it, and the runtime is injected through the script's OWN
#   documented override, `CONTAINER_RUNTIME` (see resolve_runtime) — a public
#   input, not a test backdoor.
#
# WHAT A FAKE RUNTIME BUYS
#   `podman info` / `docker info` on this host reports ONE reality; the matrix
#   needs eight, including ones this host can never produce (a rootful engine,
#   a docker daemon that is not installed here). A shim that emits controlled
#   output on stdout is the only way to reach them without a privileged or
#   destructive setup, and it needs no privileges at all.
#
# THE CONTROL NEEDLE (§11.4.201(7)(b)) — load-bearing, not decoration
#   A shim that was NEVER INVOKED and a shim whose reading was ignored produce
#   the same quiet "SKIP (unknown:...)" line. Every shim therefore APPENDS to a
#   per-case call log, and every case asserts the log is non-empty — so a
#   `detect_rootless` that stopped consulting the runtime at all would fail
#   here instead of passing as an honest skip.
#
# WHAT IS NEVER DONE
#   No container is started, no image is pulled, no container is restarted. The
#   scope handed to the script is a temp directory that NO compose service
#   mounts, so the in-container P1 probe short-circuits to
#   `skip:route_undeclared` before it would ever exec the runtime with `run`.
#   Each case additionally ASSERTS its shim log contains no `run` verb.
#
# §11.4.263: this harness signals no process. There is no kill/pkill/killpg
# call anywhere in it, so the pgid<=1 hazard cannot arise (and no pid is read,
# so there is none to validate as an int > 1).
#
# Usage:   bash tests/unit/test_ownership_rootless_detection.sh
# Inputs:  none (no stdin, no arguments, no env input).
# Outputs: per-case PASS/FAIL lines, then a RESULT summary.
# Side-effects: writes ONLY inside one mktemp directory, removed on EVERY exit
#          path via an EXIT trap. Never writes into the repository tree.
# Dependencies: bash, mktemp, timeout, plus whatever the script under test
#          needs (python3 with PyYAML).
#
# Exit codes: 0 every case matched; 1 a case diverged; 2 harness/environment
#          error (nothing was asserted — never reported as a pass).
#
# Cross-refs: §11.4.1 §11.4.6 §11.4.14 §11.4.107(10) §11.4.201(1)(6)(7)(11)
#             §11.4.245 §11.4.252 §11.4.263.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${HERE}/../.." && pwd)"
SCRIPT="${PROJECT_ROOT}/scripts/ownership_precondition.sh"
REAL_COMPOSE="${PROJECT_ROOT}/docker-compose.yml"

PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); echo "  PASS: $1"; }
fail() { FAIL=$((FAIL+1)); echo "  FAIL: $1"; }

finish() {
    echo "RESULT: ${PASS} passed, ${FAIL} failed"
    [[ "${FAIL}" -eq 0 ]] || exit 1
    exit 0
}

if [[ ! -f "${SCRIPT}" ]]; then
    echo "  FAIL: script under test missing: ${SCRIPT}" >&2
    echo "RESULT: 0 passed, 1 failed" >&2
    exit 2
fi

TMP_ROOT="$(mktemp -d -t ownership_rootless_matrix.XXXXXX)"
trap 'rm -rf "${TMP_ROOT}"' EXIT

# ---------------------------------------------------------------------------
# Hermetic scope: one directory this harness owns, that no compose service
# mounts. probe_location() writes and removes one file inside it; that is the
# only filesystem effect of a passing run, and it lands in the sandbox.
# ---------------------------------------------------------------------------
SCOPE_DIR="${TMP_ROOT}/declared_location"
mkdir -p "${SCOPE_DIR}"
SCOPE_FILE="${TMP_ROOT}/scope.yaml"
cat >"${SCOPE_FILE}" <<YAML
schema_version: 1
paths:
  - path: ${SCOPE_DIR}
    kind: dir
YAML

# ---------------------------------------------------------------------------
# PRECONDITION (§11.4.6 — stated, not assumed): the dangerous-combination cases
# only mean something while the real compose file still declares PUID=0
# somewhere. assert_rootless_runtime refuses on rootful AND PUID=0; with no
# PUID=0 anywhere it takes the "nothing to refuse" branch, and a rootful case
# would pass for a reason that has nothing to do with the code under test.
# The compose file is not overridable from the command line, so this is
# checked rather than injected.
# ---------------------------------------------------------------------------
if ! grep -qE '^[[:space:]]*-[[:space:]]*PUID=0[[:space:]]*$' "${REAL_COMPOSE}" 2>/dev/null; then
    echo "  FAIL: harness precondition: ${REAL_COMPOSE} declares no 'PUID=0' service." >&2
    echo "        The rootful cases below assert a refusal that requires it, so this" >&2
    echo "        harness would be asserting nothing. Not reported as a pass." >&2
    echo "RESULT: 0 passed, 1 failed" >&2
    exit 2
fi

# ---------------------------------------------------------------------------
# make_shim <case> <runtime-basename> — write an executable fake runtime whose
# `info` output is supplied on stdin, and which logs every invocation.
#
# The basename is load-bearing: detect_rootless() branches on `basename` of the
# resolved runtime, so the file must literally be named `podman` or `docker`.
# Echoes the shim path.
# ---------------------------------------------------------------------------
make_shim() {
    local case_name="$1" runtime="$2"
    local dir="${TMP_ROOT}/${case_name}"
    mkdir -p "${dir}"
    local payload="${dir}/info_output"
    cat >"${payload}"
    local shim="${dir}/${runtime}"
    cat >"${shim}" <<SHIM
#!/usr/bin/env bash
# Fake container runtime. Records every invocation, answers only \`info\`.
printf '%s\n' "\$*" >>"${dir}/calls.log"
if [[ "\${1:-}" == "info" ]]; then
    cat "${payload}"
    exit ${SHIM_INFO_RC}
fi
# Anything else (run/image/...) is refused loudly: this harness must never
# start a container, so an unexpected verb is a harness bug, not a fixture.
echo "fake runtime: unexpected verb: \$*" >&2
exit 125
SHIM
    chmod +x "${shim}"
    printf '%s\n' "${shim}"
}

RUN_OUT=""
RUN_RC=0
RUN_LOG=""

# ---------------------------------------------------------------------------
# drive <case> <shim-path-or-empty> — run the REAL script with the fake runtime
# injected. An EMPTY shim path means CONTAINER_RUNTIME is exported empty, which
# resolve_runtime documents as "explicitly declared absent".
# ---------------------------------------------------------------------------
drive() {
    local case_name="$1" shim="$2"
    RUN_OUT="${TMP_ROOT}/${case_name}/output.txt"
    RUN_LOG="${TMP_ROOT}/${case_name}/calls.log"
    mkdir -p "${TMP_ROOT}/${case_name}"
    set +e
    CONTAINER_RUNTIME="${shim}" timeout 120 bash "${SCRIPT}" \
        --scope "${SCOPE_FILE}" >"${RUN_OUT}" 2>&1
    RUN_RC=$?
    set -e
}

# expect <label> <expected_rc> [required_substring...]
expect() {
    local label="$1" expected="$2"
    shift 2
    if [[ "${RUN_RC}" -ne "${expected}" ]]; then
        fail "${label}: expected exit ${expected}, got ${RUN_RC}"
        sed 's/^/        /' "${RUN_OUT}" | head -20
        return 0
    fi
    local needle
    for needle in "$@"; do
        if ! grep -qF -- "${needle}" "${RUN_OUT}"; then
            # §11.4.245: a matching exit code is not proof of the RIGHT reason.
            fail "${label}: exit ${RUN_RC} correct, but the report never says '${needle}'"
            sed 's/^/        /' "${RUN_OUT}" | head -20
            return 0
        fi
    done
    pass "${label} (exit ${RUN_RC})"
}

# assert_shim_consulted <label> — the control needle. Also proves no container
# was started: the only verb the script may use here is `info`.
assert_shim_consulted() {
    local label="$1"
    if [[ ! -s "${RUN_LOG}" ]]; then
        fail "${label}: control needle — the fake runtime was NEVER invoked, so this case asserts nothing about detect_rootless"
        return 0
    fi
    if grep -qE '^run( |$)' "${RUN_LOG}"; then
        fail "${label}: the script invoked the runtime with 'run' — this harness must never start a container"
        sed 's/^/        /' "${RUN_LOG}" | head -10
        return 0
    fi
    pass "${label}: control needle (runtime consulted $(wc -l <"${RUN_LOG}" | tr -d ' ')x, no 'run' verb)"
}

echo "detect_rootless / assert_rootless_runtime polarity matrix"
echo "  script: ${SCRIPT}"

# === 1. MEASURED ROOTFUL + PUID=0 -> REFUSE, naming BOTH halves ============
# The dangerous combination of §11.4.252. Under a rootful runtime container
# uid 0 is REAL host root, so PUID=0 would run the app as genuine root — the
# one reading that must stop startup.
SHIM_INFO_RC=0
SHIM="$(make_shim rootful_puid0 podman <<<'false')"
drive rootful_puid0 "${SHIM}"
expect "rootful + PUID=0 -> REFUSE" 1 \
    "measured ROOTFUL" \
    "declare PUID=0" \
    "REAL HOST ROOT" \
    "Startup refused."
assert_shim_consulted "rootful + PUID=0"

# The refusal must name the SERVICES, not merely the condition: a refusal that
# does not say what to look at is the §11.4.201(5) evidence gap.
if grep -qE 'declare PUID=0: [A-Za-z0-9_-]+' "${RUN_OUT}"; then
    pass "rootful + PUID=0: refusal names the offending service(s)"
else
    fail "rootful + PUID=0: refusal never names which service declares PUID=0"
fi

# === 2. MEASURED ROOTLESS -> must NOT fire ================================
# §11.4.201(1): refusing a healthy host is exactly as broken as passing a
# dangerous one. This is the false-positive guard for case 1.
SHIM_INFO_RC=0
SHIM="$(make_shim rootless podman <<<'true')"
drive rootless "${SHIM}"
expect "rootless -> no refusal" 0 \
    "measured ROOTLESS" \
    "PUID=0 grants no host privilege"
assert_shim_consulted "rootless"

if grep -q "Startup refused." "${RUN_OUT}"; then
    fail "rootless: the script refused a measured-ROOTLESS host"
else
    pass "rootless: no refusal emitted"
fi

# === 3. `podman info` FAILS -> NAMED SKIP, exit 0 =========================
# An unresolvable reading must NEVER manufacture a refusal (§11.4.201(1)) and
# must never be silently swallowed as a pass either (§11.4.201(6)): it is
# reported as an honest, NAMED skip that says which probe did not run.
SHIM_INFO_RC=7
SHIM="$(make_shim podman_info_fails podman <<<'')"
drive podman_info_fails "${SHIM}"
expect "podman info fails -> named SKIP, exit 0" 0 \
    "rootless assertion: SKIP" \
    "podman_info_failed(exit 7)" \
    "asserts NOTHING about it"
assert_shim_consulted "podman info fails"

# === 4. docker with EMPTY SecurityOptions -> named skip ===================
# An engine that reported NO security options told us nothing. Reading that
# empty list as "no rootless marker, therefore rootful" would refuse on a
# FALSE-NULL — the instrument's silence, not the engine's answer.
SHIM_INFO_RC=0
SHIM="$(make_shim docker_empty_opts docker <<<'')"
drive docker_empty_opts "${SHIM}"
expect "docker empty SecurityOptions -> named SKIP, exit 0" 0 \
    "rootless assertion: SKIP" \
    "docker_security_options_empty"
assert_shim_consulted "docker empty SecurityOptions"

# === 5. CARRIER: `name=rootless-lookalike` must NOT read as rootless ======
# §11.4.201(7)(a) match-structure-not-substring. A substring scan for
# "rootless" fires on this output twice — once inside a profile path — and
# would wave the dangerous combination straight through. The field-equality
# match must read it as rootful, and with PUID=0 declared that means REFUSE.
# The refusal IS the evidence the carrier was not mistaken for the marker.
SHIM_INFO_RC=0
SHIM="$(make_shim docker_carrier docker <<'INFO'
name=seccomp,profile=/etc/docker/name=rootless-lookalike.json
name=rootless-lookalike
INFO
)"
drive docker_carrier "${SHIM}"
expect "docker 'name=rootless-lookalike' carrier -> NOT rootless" 1 \
    "measured ROOTFUL" \
    "Startup refused."
assert_shim_consulted "docker carrier"

# === 6. docker with the GENUINE marker -> rootless ========================
# The carrier case above only proves something if the REAL marker still reads
# as rootless through the same path (otherwise case 5 would pass with a
# detector that simply never returns rootless for docker).
SHIM_INFO_RC=0
SHIM="$(make_shim docker_genuine docker <<'INFO'
name=seccomp,profile=builtin
name=rootless
INFO
)"
drive docker_genuine "${SHIM}"
expect "docker genuine 'name=rootless' -> rootless, no refusal" 0 \
    "measured ROOTLESS"
assert_shim_consulted "docker genuine marker"

# === 7. podman reporting an UNRECOGNISED value -> named skip ==============
# Neither `true` nor `false`. Guessing either way is the §11.4.6 violation;
# the reading is reported verbatim so the operator can see what confused it.
SHIM_INFO_RC=0
SHIM="$(make_shim podman_weird podman <<<'<nil>')"
drive podman_weird "${SHIM}"
expect "podman unrecognised field -> named SKIP, exit 0" 0 \
    "rootless assertion: SKIP" \
    "podman_rootless_field_unrecognised"
assert_shim_consulted "podman unrecognised field"

# === 8. NO runtime at all -> named skip, never a refusal ==================
# CONTAINER_RUNTIME exported EMPTY is resolve_runtime's documented "explicitly
# declared absent". No runtime means nothing was measured; a host without
# podman must not be refused for it. No shim exists, so the control needle
# does not apply — the absence IS the input.
drive no_runtime ""
expect "no runtime -> named SKIP, exit 0" 0 \
    "rootless assertion: SKIP" \
    "no_container_runtime"
if [[ -s "${RUN_LOG}" ]]; then
    fail "no runtime: something was invoked as a container runtime"
else
    pass "no runtime: nothing invoked (correct — there is no runtime to consult)"
fi

# === Sandbox hygiene (§11.4.14): everything written stayed in TMP_ROOT =====
# probe_location() creates and removes one file inside the declared location.
# A leftover would mean the probe did not clean up after itself.
LEFTOVER="$(find "${SCOPE_DIR}" -mindepth 1 2>/dev/null | head -5 || true)"
if [[ -z "${LEFTOVER}" ]]; then
    pass "sandbox: declared location left empty (no probe residue)"
else
    fail "sandbox: probe residue left behind in ${SCOPE_DIR}: ${LEFTOVER}"
fi

finish
