#!/usr/bin/env bash
# test_ownership_precondition_docker_premise.sh — BOB-210 RED, now GREEN: the
# in-source claim about detect_rootless()'s docker branch must not contradict
# its measured behaviour.
#
# Feature      : 002-user-owned-downloads
# Under test   : scripts/ownership_precondition.sh (the detect_rootless()
#                header comment, and the docker branch's real behaviour)
# Requirements : FR-011 (§11.4.252 fail-closed-on-a-dangerous-combination)
# Governance   : §11.4.6 (a claim must match measured reality), §11.4.115
#                (RED on the broken artifact), §11.4.201(1) (a false-positive
#                refusal is exactly as forbidden as a false pass — this test
#                does NOT ask for the refusal to be removed, only for the
#                promise about it to be honest)
#
# ===========================================================================
# WHAT WAS WRONG
# ===========================================================================
# The header claimed: "It is deliberately built to fail toward `unknown` ...
# so an unverified reading can never manufacture a refusal." MEASURED: a
# docker `info` call that SUCCEEDS with a NON-EMPTY, well-formed
# `SecurityOptions` list containing no `name=rootless` field is read as a
# CONFIDENT `rootful` — not `unknown` — and that confident verdict DOES reach
# the R3 refusal when a compose service declares PUID=0. The docker branch's
# whole convention (absence of the marker means not-rootless) is itself
# UNVALIDATED against a real docker installation (none exists on any host
# that has authored this script), so the promise that this can "never
# manufacture a refusal" was false for exactly the case this suite drives.
#
# THE FIX IS DOCUMENTATION-ONLY (an explicitly permitted resolution per
# BOB-210's own acceptance criteria): the existing carrier-trap behaviour
# (tests/unit/test_ownership_rootless_detection.sh Case 5/6) is a DELIBERATE,
# desired security property — a docker engine reporting security options with
# no rootless marker legitimately means "not rootless," and refusing PUID=0
# on that reading is correct, not a bug to weaken. Flipping :413 to `unknown`
# would break that already-passing, already-verified-good behaviour (BOB-210
# explicitly forbids this). So the resolution corrects the CLAIM to match the
# CODE, per §11.4.6, rather than weakening the code to match a promise that
# was never true.
#
# ===========================================================================
# WHAT THIS TEST ASSERTS
# ===========================================================================
# (1) The exact absolute claim is gone from the header — a literal grep for
#     the sentence that was proven false.
# (2) The MEASURED behaviour it was making a claim about is unchanged and
#     still real: a shimmed docker with a non-empty, marker-absent
#     SecurityOptions list still produces a confident `rootful` reading that
#     reaches the R3 refusal. (This reuses the already-existing, already
#     control-needled carrier-trap fixture technique from
#     test_ownership_rootless_detection.sh Case 5, driven independently here
#     so this file does not depend on that one's internal state.)
# (3) The header now honestly says the docker branch's convention is
#     unvalidated against a real docker install (the corrected claim itself
#     is present), so a future reader is not misled the other way either.
#
# §11.4.263: this suite signals no processes (only a fake, non-privileged
# runtime binary is exec'd by the driven script itself).

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${HERE}/../.." && pwd)"
SCRIPT="${PROJECT_ROOT}/scripts/ownership_precondition.sh"
REAL_COMPOSE="${PROJECT_ROOT}/docker-compose.yml"

PASS=0; FAIL=0; SKIP=0
pass() { PASS=$((PASS+1)); echo "  PASS: $1"; }
fail() { FAIL=$((FAIL+1)); echo "  FAIL: $1"; }
skip() { SKIP=$((SKIP+1)); echo "  SKIP: $1"; }
finish() {
    echo "RESULT: ${PASS} passed, ${FAIL} failed, ${SKIP} skipped"
    [[ "${FAIL}" -eq 0 ]] || exit 1
    exit 0
}

[[ -f "${SCRIPT}" ]] || { fail "target missing: scripts/ownership_precondition.sh"; finish; }

WORK=""
cleanup() { local rc=$?; [[ -n "${WORK}" && -d "${WORK}" ]] && rm -rf "${WORK}"; exit "${rc}"; }
trap cleanup EXIT
WORK="$(mktemp -d "${TMPDIR:-/tmp}/bob210.XXXXXXXX")" || { fail "harness: mktemp -d failed"; finish; }

echo "== BOB-210: the docker-branch header claim must match measured behaviour =="

# ===========================================================================
# CASE 1 — the false absolute claim no longer stands UNQUALIFIED.
# ===========================================================================
# The claim's TEXT may legitimately still appear as a QUOTED, explicitly
# refuted historical citation (exactly what the fix does, for the record —
# §11.4.6 prefers "here is what was wrong and why" over silent deletion). The
# defect this case actually guards against is the claim standing as a live,
# unqualified assertion; a bare substring match on the claim's wording alone
# would be the §11.4.201(7)(a) match-structure-not-substring failure this
# project's own governance names explicitly — so this checks CONTEXT, not
# mere presence.
FALSE_CLAIM="so an unverified reading can never manufacture a refusal"
if grep -qF "${FALSE_CLAIM}" "${SCRIPT}"; then
    # The claim's text is present — it MUST be inside a passage that marks it
    # refuted (quoted historically, labelled FALSE), never standing alone.
    if grep -B2 -A2 -F "${FALSE_CLAIM}" "${SCRIPT}" | grep -qiE 'FALSE for the (branch|docker)|was corrected'; then
        pass "the false claim's text is present only as an explicitly-refuted historical citation, not a standing assertion"
    else
        fail "the header still asserts '${FALSE_CLAIM}' with no nearby refutation — this is measured FALSE for the docker branch's confident-rootful reading (Case 2 below)"
    fi
else
    pass "the false absolute claim ('${FALSE_CLAIM}') is no longer present at all"
fi

# ===========================================================================
# CASE 2 — the measured behaviour the claim was wrong about is still real:
# a successful, non-empty, marker-absent docker read still reaches a
# confident rootful + R3 refusal (this is the DESIRED security property,
# per BOB-210's explicit "do not weaken case 5/6" instruction — this case
# proves that property is intact, not merely that the doc was edited).
# ===========================================================================
if ! grep -qE '^[[:space:]]*-[[:space:]]*PUID=0[[:space:]]*$' "${REAL_COMPOSE}" 2>/dev/null; then
    skip "case 2: ${REAL_COMPOSE} declares no PUID=0 service — the refusal this case drives requires it, so this host cannot exercise it"
else
    SCOPE_DIR="${WORK}/declared_location"
    mkdir -p "${SCOPE_DIR}"
    SCOPE_FILE="${WORK}/scope.yaml"
    cat > "${SCOPE_FILE}" <<YAML
schema_version: 1
paths:
  - path: ${SCOPE_DIR}
    kind: dir
YAML

    SHIM_DIR="${WORK}/shim"
    mkdir -p "${SHIM_DIR}"
    SHIM="${SHIM_DIR}/docker"
    cat > "${SHIM}" <<'SHIMEOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >>"${SHIM_LOG}"
if [[ "${1:-}" == "info" ]]; then
    # A successful, non-empty, WELL-FORMED SecurityOptions list that simply
    # never mentions "rootless" — the shape the corrected header now
    # describes as "confident rootful, not unknown".
    cat <<'INFO'
name=seccomp,profile=default
name=apparmor
INFO
    exit 0
fi
echo "fake runtime: unexpected verb: $*" >&2
exit 125
SHIMEOF
    chmod +x "${SHIM}"

    SHIM_LOG="${WORK}/calls.log"
    RUN_OUT="${WORK}/output.txt"
    set +e
    CONTAINER_RUNTIME="${SHIM}" SHIM_LOG="${SHIM_LOG}" timeout 60 bash "${SCRIPT}" \
        --scope "${SCOPE_FILE}" >"${RUN_OUT}" 2>&1
    RUN_RC=$?
    set -e

    if [[ ! -s "${SHIM_LOG}" ]]; then
        fail "case 2: control needle — the fake docker runtime was never invoked, so this case asserts nothing"
    elif [[ "${RUN_RC}" -eq 1 ]] && grep -qF "measured ROOTFUL" "${RUN_OUT}" && grep -qF "Startup refused." "${RUN_OUT}"; then
        pass "case 2: a successful, non-empty, marker-absent docker read still refuses (measured ROOTFUL, exit 1) — the corrected header describes this correctly as confident, not unknown"
    else
        fail "case 2: expected exit 1 with 'measured ROOTFUL' + 'Startup refused.', got exit ${RUN_RC}: $(cat "${RUN_OUT}")"
    fi
fi

# ===========================================================================
# CASE 3 — the honest replacement claim is present: the docker branch's
# convention is stated as unvalidated against a real docker install, so the
# fix does not silently overclaim confidence in the other direction either.
# ===========================================================================
if grep -qF "has NEVER been run against a" "${SCRIPT}" && grep -qiF "docker is NOT" "${SCRIPT}"; then
    pass "the header now honestly states the docker branch is unvalidated against a real docker install"
else
    fail "the header does not clearly state the docker branch remains unvalidated against a real docker install — §11.4.6 requires the honest gap to be stated, not merely the false claim removed"
fi

# ===========================================================================
# CASE 4 (THE CONTROL, RED reproduced) — Case 1's context-aware check must
# genuinely FAIL against an IMMUTABLE PRE-FIX commit, where the claim stood
# unqualified with no refutation nearby — proving Case 1 discriminates
# rather than being satisfied by any file whatsoever.
# ===========================================================================
# `git HEAD` is NOT usable as this baseline: the fix this suite guards
# landed in commit 03bf860, and once that commit is HEAD (as it is on this
# checkout, and on any checkout after this suite is committed alongside its
# own fix), `HEAD` is POST-fix, not pre-fix — the control would then be
# diffing the fixed file against itself, which trivially "passes" the
# nearby-refutation check for the wrong reason (the refutation is only
# absent BEFORE the fix, never after). §11.4.115(F): a RED-baseline control
# needs a STABLE reference to the pre-fix state, not "whatever HEAD happens
# to be when this test runs" — HEAD moves forward with every commit
# INCLUDING the fix being verified. The BOB-217 suite in this same batch
# hit the identical footgun and pins a specific immutable SHA instead; this
# case does the same, pinning the last commit to touch this file BEFORE the
# fixing commit (03bf860's parent for this path, `af48019`), which is
# immutable and stays a genuine pre-fix baseline regardless of how far HEAD
# subsequently advances.
#
# The pre-fix wording wraps "...can never" / "manufacture a refusal." across
# TWO comment lines, so the single-line joined FALSE_CLAIM used above (which
# quotes it collapsed onto one line, `grep -F` cannot match across a real
# newline) will never match the pre-fix file even though it carries the same
# claim — a distinct, line-safe fragment is used here instead, on purpose.
PRE_FRAGMENT="an unverified reading can never"
PRE_FIX_COMMIT="af48019"
PRE_SCRIPT="${WORK}/ownership_precondition_prefix.sh"
if git -C "${PROJECT_ROOT}" show "${PRE_FIX_COMMIT}:scripts/ownership_precondition.sh" > "${PRE_SCRIPT}" 2>/dev/null && [[ -s "${PRE_SCRIPT}" ]]; then
    if grep -qF "${PRE_FRAGMENT}" "${PRE_SCRIPT}"; then
        if grep -B2 -A2 -F "${PRE_FRAGMENT}" "${PRE_SCRIPT}" | grep -qiE 'FALSE for the (branch|docker)|was corrected'; then
            fail "control: pinned pre-fix commit ${PRE_FIX_COMMIT}'s header ALREADY carries a nearby refutation — this is no longer a valid pre-fix baseline, Case 1's PASS above needs re-derivation against an earlier commit"
        else
            pass "control: pinned pre-fix commit ${PRE_FIX_COMMIT}'s header asserts the claim with NO nearby refutation, reproducing the reported defect — Case 1 is discriminating"
        fi
    else
        skip "control: pinned pre-fix commit ${PRE_FIX_COMMIT}'s scripts/ownership_precondition.sh does not contain the fragment '${PRE_FRAGMENT}' — the pinned SHA does not predate the fix as expected, not asserted"
    fi
else
    skip "control: could not read scripts/ownership_precondition.sh from pinned commit ${PRE_FIX_COMMIT} (shallow clone or unreachable object) — not asserted"
fi

finish
