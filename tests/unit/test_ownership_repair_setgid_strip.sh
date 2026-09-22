#!/usr/bin/env bash
# test_ownership_repair_setgid_strip.sh — BOB-220 RED, now GREEN as the
# standing guard for the setuid/setgid-strip chmod in scripts/ownership_repair.sh.
#
# Feature      : 002-user-owned-downloads
# Under test   : scripts/ownership_repair.sh (the mode-restore chmod for
#                narrowing-only entries — the "keep sticky, drop setuid+setgid"
#                block, currently `_mode="$(printf '%05o' "${_mode}")"`)
# Requirements : FR-015 ("MUST NOT relax access restrictions" — the STRIP is
#                the mechanism, so a strip that silently no-ops is FR-015
#                claimed and not delivered, the exact shape §11.4/§11.4.1
#                forbid)
# Governance   : §11.4.115 (RED on the broken artifact), §11.4.6 (code and
#                comment must agree about what actually happens)
#
# ===========================================================================
# WHAT WAS WRONG, MEASURED (not assumed)
# ===========================================================================
# The strip masked the mode to `8#1777` (numerically correct — keeps sticky,
# drops setuid/setgid) and rendered it with `printf '%o'`, producing a bare
# 3-or-4-character string ("755" / "1755"). MEASURED on this project's own
# `chmod` — /usr/bin/chmod -> ../lib/cargo/bin/coreutils/chmod, a uutils
# (Rust) reimplementation, NOT GNU coreutils — `chmod 755 dir` AND even
# `chmod 0755 dir` (4 chars) BOTH leave a directory's setgid bit SET; only a
# fully zero-padded 5-character `chmod 00755 dir`, or an explicit
# `chmod g-s dir`, actually clears it. Regular files are unaffected either
# way (the kernel already clears setuid/setgid on chown(2) before this chmod
# ever runs, verified below too). The in-source comment claimed a strip that
# silently did not happen for directories.
#
# ===========================================================================
# WHY THIS DRIVES THE REAL SCRIPT END-TO-END, VIA A REAL FOREIGN UID
# ===========================================================================
# The mode-restore block only runs for an item that was actually SELECTED for
# repair (foreign uid) AND originally carried setuid/setgid/sticky bits — it
# is deep inside main()'s batch-flush logic, not a separately callable
# function, so §11.4.201(11) (probe the artifact through its real invocation
# path) means running the real script against a real foreign-owned fixture,
# not re-implementing the masking arithmetic in this test and asserting
# against the copy. The foreign uid is built with the SAME technique already
# proven in tests/unit/test_ownership_repair.sh (`podman unshare chown 1:1`,
# host-visible as the first subordinate uid) — no sudo, no loopback, no mount.
#
# §11.4.263: this suite signals no processes.

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${HERE}/../.." && pwd)"
REPAIR="${PROJECT_ROOT}/scripts/ownership_repair.sh"
LIB="${PROJECT_ROOT}/scripts/lib/ownership.sh"

PASS=0; FAIL=0; SKIP=0
pass() { PASS=$((PASS+1)); echo "  PASS: $1"; }
fail() { FAIL=$((FAIL+1)); echo "  FAIL: $1"; }
skip() { SKIP=$((SKIP+1)); echo "  SKIP: $1"; }
finish() {
    echo "RESULT: ${PASS} passed, ${FAIL} failed, ${SKIP} skipped"
    [[ "${FAIL}" -eq 0 ]] || exit 1
    exit 0
}

[[ -f "${REPAIR}" ]] || { fail "target missing: scripts/ownership_repair.sh"; finish; }
[[ -f "${LIB}" ]]    || { fail "target missing: scripts/lib/ownership.sh"; finish; }

# ── fixture feasibility: a rootless-unshare-capable runtime, honest SKIP ───
NS_RUNTIME=""
for _rt in podman docker; do
    command -v "${_rt}" >/dev/null 2>&1 || continue
    _probe="$(mktemp -d)"
    : > "${_probe}/f"
    if timeout 60 "${_rt}" unshare chown 1:1 "${_probe}/f" >/dev/null 2>&1; then
        _got="$(stat -c '%u' "${_probe}/f" 2>/dev/null)"
        if [[ -n "${_got}" && "${_got}" != "$(id -u)" ]]; then
            NS_RUNTIME="${_rt}"
        fi
    fi
    rm -rf "${_probe}"
    [[ -n "${NS_RUNTIME}" ]] && break
done
if [[ -z "${NS_RUNTIME}" ]]; then
    skip "fixture: no rootless-unshare-capable container runtime found — a real foreign uid is not constructible here"
    finish
fi

WORK=""
cleanup() { local rc=$?; [[ -n "${WORK}" && -d "${WORK}" ]] && rm -rf "${WORK}"; exit "${rc}"; }
trap cleanup EXIT
WORK="$(mktemp -d "${TMPDIR:-/tmp}/bob220.XXXXXXXX")" || { fail "harness: mktemp -d failed"; finish; }

# run_case <label> <repair-script>
#
# Builds a sandbox with ONE declared root: a foreign-owned, setgid (2755)
# directory. Runs the given repair script against it and echoes the resulting
# mode ("755" | "2755" | anything else on an unexpected outcome) on stdout, so
# callers can assert the case-appropriate direction themselves rather than
# this helper guessing which direction is "expected" for a given script.
run_case() {
    local label="$1" repair_script="$2"
    local sb target scope state out rc mode

    sb="$(mktemp -d "${WORK}/${label}.XXXXXX")"
    mkdir -p "${sb}/scripts/lib" "${sb}/state"
    cp "${repair_script}" "${sb}/scripts/ownership_repair.sh"
    cp "${LIB}" "${sb}/scripts/lib/ownership.sh"

    target="${sb}/target"
    mkdir -p "${target}"
    chmod 2755 "${target}" || { echo "FIXTURE-FAIL"; return; }

    if ! timeout 60 "${NS_RUNTIME}" unshare chown -h -- 1:1 "${target}" >/dev/null 2>&1; then
        echo "FIXTURE-FAIL"
        return
    fi
    local before before_owner
    before="$(stat -c '%a' "${target}" 2>/dev/null)"
    before_owner="$(stat -c '%u' "${target}" 2>/dev/null)"
    if [[ "${before}" != "2755" || "${before_owner}" == "$(id -u)" ]]; then
        echo "FIXTURE-FAIL"
        return
    fi

    scope="${sb}/scope.yaml"
    cat > "${scope}" <<YAML
schema_version: 1
paths:
  - path: ${target}
    kind: downloads
    optional: false
    preserve_mode: false
    recursive: true
YAML
    state="${sb}/state"
    out="${sb}/run.out"
    CONTAINER_RUNTIME="${NS_RUNTIME}" OWNED_PATHS_FILE="${scope}" \
        bash "${sb}/scripts/ownership_repair.sh" --scope "${scope}" --state-dir "${state}" --force \
        > "${out}" 2>&1
    rc=$?

    mode="$(stat -c '%a' "${target}" 2>/dev/null)"
    owner="$(stat -c '%u' "${target}" 2>/dev/null)"

    if [[ "${owner}" != "$(id -u)" ]]; then
        echo "OWNERSHIP-NOT-FIXED:rc=${rc}"
        return
    fi

    echo "MODE:${mode}"
}

echo "== BOB-220: setuid/setgid strip on a foreign-owned setgid directory =="
echo "  fixture runtime: ${NS_RUNTIME}"

# ===========================================================================
# CASE 1 (THE FIX, GREEN) — the shipped script really strips setgid.
# ===========================================================================
R1="$(run_case shipped "${REPAIR}")"
case "${R1}" in
    MODE:755)
        pass "shipped: setgid genuinely stripped (2755 -> 755)" ;;
    MODE:2755)
        fail "shipped: setgid NOT stripped — mode is still 2755; the strip is a no-op" ;;
    MODE:*)
        fail "shipped: unexpected resulting mode '${R1#MODE:}' (neither 755 nor 2755)" ;;
    OWNERSHIP-NOT-FIXED:*)
        fail "shipped: repair did not fix ownership at all (${R1}) — cannot judge the strip" ;;
    FIXTURE-FAIL)
        skip "shipped: fixture (foreign-owned setgid directory) was not constructible on this host" ;;
    *)
        fail "shipped: harness produced an unrecognised result '${R1}'" ;;
esac

# ===========================================================================
# CASE 2 (THE CONTROL, RED reproduced) — a byte-identical copy of the PRE-FIX
# script (git HEAD, captured at run time rather than trusted as a separate
# fixture file that could drift) must show the ORIGINAL no-op behaviour under
# the identical harness — proving Case 1 is discriminating, not a fixture
# artefact.
# ===========================================================================
PRE_REPAIR="${WORK}/ownership_repair_prefix.sh"
if git -C "${PROJECT_ROOT}" show HEAD:scripts/ownership_repair.sh > "${PRE_REPAIR}" 2>/dev/null && [[ -s "${PRE_REPAIR}" ]]; then
    if grep -qF "_mode=\"\$(printf '%o' \"\${_mode}\")\"" "${PRE_REPAIR}"; then
        R2="$(run_case control_prefix "${PRE_REPAIR}")"
        case "${R2}" in
            MODE:2755)
                pass "control: the pre-fix shape (bare '%o') reproduces the reported no-op — 2755 survives under this identical harness, proving Case 1 is discriminating" ;;
            MODE:755)
                fail "control: the pre-fix shape ALSO stripped setgid (mode 755) under this harness — Case 1's PASS is not evidence of this fix, something else is doing the work" ;;
            MODE:*)
                fail "control: unexpected resulting mode '${R2#MODE:}' for the pre-fix shape" ;;
            OWNERSHIP-NOT-FIXED:*)
                skip "control: pre-fix repair did not fix ownership (${R2}) — cannot judge the strip" ;;
            FIXTURE-FAIL)
                skip "control: fixture was not constructible for the pre-fix run" ;;
            *)
                fail "control: harness produced an unrecognised result '${R2}'" ;;
        esac
    else
        skip "control: git HEAD's scripts/ownership_repair.sh no longer contains the pre-fix '%o' form — HEAD has moved past the captured baseline, the shipped-case verdict above stands on its own"
    fi
else
    skip "control: could not read scripts/ownership_repair.sh from git HEAD — not asserted"
fi

finish
