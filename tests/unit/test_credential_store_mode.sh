#!/usr/bin/env bash
# test_credential_store_mode.sh — polarity matrix for assert_credential_store_mode()
# and harden_config_permissions() in start.sh (FR-015 of
# specs/002-user-owned-downloads/: the AES-256-GCM credential store
# config/boba.db must stay no more permissive than 600).
#
# WHY THIS FILE EXISTS, AND WHY THE ORIGINAL MATRIX PROVED NOTHING
#   The mode assertion landed with a "six-case polarity matrix" recorded only
#   in a commit message. That matrix was BLIND, and the way it was blind is the
#   lesson worth keeping: start.sh does `cd "$SCRIPT_DIR"` and both functions
#   address the store as `$SCRIPT_DIR/config/boba.db`, so a matrix that varied
#   the fixture WITHOUT overriding SCRIPT_DIR had all six cases read the same
#   untouched repository file and report six cheerful passes. Six green lines,
#   one file, zero cases exercised — the §11.4.201(6) FALSE-NULL in its purest
#   form: a blind instrument and a healthy tree return the identical quiet
#   success.
#
# HOW THIS HARNESS IS HERMETIC, AND HOW IT PROVES IT IS
#   Every case runs in its OWN process, sources start.sh (which carries an
#   explicit `BASH_SOURCE[0] == $0` guard for exactly this purpose, so main
#   does not run), REASSIGNS SCRIPT_DIR to that case's private sandbox, and
#   only then calls the function. The proof that this worked is not asserted by
#   construction — it is READ BACK from the output: both the success and the
#   refusal print the store's FULL PATH, and every case asserts the path
#   printed is ITS OWN. A case that silently fell back to the repository file
#   would print the repository path and fail here.
#
#   A second, differential control closes the same hole from the other side: a
#   666 sandbox and a 600 sandbox are driven back to back and must produce
#   DIFFERENT verdicts. A blind harness reading one shared file cannot do that
#   no matter which file it reads.
#
# WHY harden_config_permissions IS EXERCISED TOO
#   It is the other half of the same landed change and had no committed test
#   either. Its contract is DIRECTIONAL — FR-015 permits it to remove
#   permission bits and never to add them — and a direction is exactly the kind
#   of property that a "looks fine" reading cannot check. Note it mutates the
#   filesystem (`chmod -R`), which is why SCRIPT_DIR is overridden BEFORE it is
#   ever called: an un-overridden call would chmod the real repository config/.
#   The final residue check reads the real store's mode back to prove none of
#   that happened.
#
# §11.4.263: this harness signals no process. There is no kill/pkill/killpg
# call anywhere in it, so the pgid<=1 hazard cannot arise (and no pid is read,
# so there is none to validate as an int > 1).
#
# Usage:   bash tests/unit/test_credential_store_mode.sh
# Inputs:  none (no stdin, no arguments, no env input).
# Outputs: per-case PASS/FAIL lines, then a RESULT summary.
# Side-effects: writes and chmods ONLY inside one mktemp directory, removed on
#          EVERY exit path via an EXIT trap. Never writes into the repository
#          tree; the residue check at the end asserts that.
# Dependencies: bash, mktemp, stat, chmod.
#
# Exit codes: 0 every case matched; 1 a case diverged; 2 harness/environment
#          error (nothing was asserted — never reported as a pass).
#
# Cross-refs: §11.4.1 §11.4.6 §11.4.14 §11.4.107(10) §11.4.201(1)(5)(6)
#             §11.4.245 §11.4.263.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${HERE}/../.." && pwd)"
START_SH="${PROJECT_ROOT}/start.sh"
REAL_STORE="${PROJECT_ROOT}/config/boba.db"

PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); echo "  PASS: $1"; }
fail() { FAIL=$((FAIL+1)); echo "  FAIL: $1"; }

finish() {
    echo "RESULT: ${PASS} passed, ${FAIL} failed"
    [[ "${FAIL}" -eq 0 ]] || exit 1
    exit 0
}

if [[ ! -f "${START_SH}" ]]; then
    echo "  FAIL: script under test missing: ${START_SH}" >&2
    echo "RESULT: 0 passed, 1 failed" >&2
    exit 2
fi

# Snapshot the REAL store's mode BEFORE anything runs. harden_config_permissions
# chmods a tree, so "this harness did not touch the real one" is asserted with a
# measurement, not with a promise.
REAL_STORE_MODE_BEFORE=""
[[ -f "${REAL_STORE}" ]] && REAL_STORE_MODE_BEFORE="$(stat -c '%a' "${REAL_STORE}" 2>/dev/null || true)"

TMP_ROOT="$(mktemp -d -t credential_store_mode.XXXXXX)"
trap 'chmod -R u+rwX "${TMP_ROOT}" 2>/dev/null || true; rm -rf "${TMP_ROOT}"' EXIT

# ---------------------------------------------------------------------------
# make_case <name> [mode] — build a private sandbox holding config/boba.db at
# the given mode. Omitting the mode leaves the store ABSENT (the fresh-host
# negative control: config/boba.db does not exist before first boot).
# Echoes the sandbox root, which becomes that case's SCRIPT_DIR.
# ---------------------------------------------------------------------------
make_case() {
    local name="$1" mode="${2:-}"
    local root="${TMP_ROOT}/${name}"
    mkdir -p "${root}/config"
    if [[ -n "${mode}" ]]; then
        : >"${root}/config/boba.db"
        chmod "${mode}" "${root}/config/boba.db"
    fi
    printf '%s\n' "${root}"
}

RUN_OUT=""
RUN_RC=0

# ---------------------------------------------------------------------------
# call_fn <function> <sandbox> — source start.sh in a FRESH process, point
# SCRIPT_DIR at this case's sandbox, then invoke the function.
#
# A fresh process per case is required, not tidiness: assert_credential_store_mode
# calls `exit 1` on a refusal, which would take the whole harness with it.
# ---------------------------------------------------------------------------
call_fn() {
    local fn="$1" sandbox="$2"
    set +e
    RUN_OUT="$(bash -c '
        source "$1"
        SCRIPT_DIR="$2"
        "$3"
    ' _ "${START_SH}" "${sandbox}" "${fn}" 2>&1)"
    RUN_RC=$?
    set -e
}

# expect_mode_case <label> <sandbox> <expected_rc> [required_substring...]
#
# Always asserts, in addition to the caller's needles, that the report names
# THIS sandbox's store path. That assertion is the anti-blindness control: it
# is what the original matrix lacked, and it is what makes a green line here
# mean "this fixture was read" rather than "something was read".
expect_mode_case() {
    local label="$1" sandbox="$2" expected="$3"
    shift 3
    call_fn assert_credential_store_mode "${sandbox}"
    if [[ "${RUN_RC}" -ne "${expected}" ]]; then
        fail "${label}: expected exit ${expected}, got ${RUN_RC}"
        printf '%s\n' "${RUN_OUT}" | sed 's/^/        /'
        return 0
    fi
    local needle
    for needle in "$@"; do
        # §11.4.245: a matching exit code is not proof of the RIGHT reason.
        if ! printf '%s' "${RUN_OUT}" | grep -qF -- "${needle}"; then
            fail "${label}: exit ${RUN_RC} correct, but the report never says '${needle}'"
            printf '%s\n' "${RUN_OUT}" | sed 's/^/        /'
            return 0
        fi
    done
    pass "${label} (exit ${RUN_RC})"
}

# assert_read_own_file <label> <sandbox> — the per-case hermeticity control.
assert_read_own_file() {
    local label="$1" sandbox="$2"
    if printf '%s' "${RUN_OUT}" | grep -qF -- "${sandbox}/config/boba.db"; then
        pass "${label}: read ITS OWN store (${sandbox##*/}/config/boba.db named in the report)"
    else
        fail "${label}: the report never names this case's own store — SCRIPT_DIR did not take effect, so the case is blind"
        printf '%s\n' "${RUN_OUT}" | sed 's/^/        /'
    fi
}

echo "assert_credential_store_mode / harden_config_permissions polarity matrix"
echo "  script: ${START_SH}"

# === THE SIX-CASE MODE MATRIX (FR-015) ====================================
# More permissive than 600 -> REFUSE. The mask is `mode & 0177`: any bit set
# outside owner rw is a leak of the credential store to other local accounts.

C666="$(make_case mode_666 666)"
expect_mode_case "mode 666 (world read+write) -> REFUSE" "${C666}" 1 \
    "is mode 666" "more permissive than 600 (FR-015)" \
    "Refusing to report a successful start on a widened credential store."
assert_read_own_file "mode 666" "${C666}"

C660="$(make_case mode_660 660)"
expect_mode_case "mode 660 (group read+write) -> REFUSE" "${C660}" 1 \
    "is mode 660" "more permissive than 600 (FR-015)"
assert_read_own_file "mode 660" "${C660}"

C640="$(make_case mode_640 640)"
expect_mode_case "mode 640 (group read) -> REFUSE" "${C640}" 1 \
    "is mode 640" "more permissive than 600 (FR-015)"
assert_read_own_file "mode 640" "${C640}"

# At or below the floor -> PASS. §11.4.201(1): refusing these would be the
# false-positive refusal, exactly as broken as passing a widened store.
C600="$(make_case mode_600 600)"
expect_mode_case "mode 600 (the floor itself) -> PASS" "${C600}" 0 \
    "mode 600" "no more permissive than 600 (FR-015)"
assert_read_own_file "mode 600" "${C600}"

C400="$(make_case mode_400 400)"
expect_mode_case "mode 400 (stricter than the floor) -> PASS" "${C400}" 0 \
    "mode 400" "no more permissive than 600 (FR-015)"
assert_read_own_file "mode 400" "${C400}"

# ABSENT is the fresh-host negative control: config/boba.db does not exist
# before first boot, which is why the ownership scope declares it optional.
# Refusing on absence would refuse every clean install.
CABS="$(make_case mode_absent)"
expect_mode_case "store ABSENT (fresh host) -> PASS, skipped honestly" "${CABS}" 0 \
    "Credential store not created yet" "absent, not a failure"
# This case names no path (there is no file to name), so the per-case path
# control does not apply; the differential control below covers it instead.

# === THE DIFFERENTIAL BLINDNESS CONTROL ===================================
# The decisive proof that cases are isolated. Two sandboxes, two modes, one
# function, back to back: the verdicts MUST differ. A harness reading one
# shared file — the exact defect in the original matrix — returns the SAME
# verdict twice regardless of what the fixtures say.
call_fn assert_credential_store_mode "${C666}"; DIFF_RC_A="${RUN_RC}"; DIFF_OUT_A="${RUN_OUT}"
call_fn assert_credential_store_mode "${C600}"; DIFF_RC_B="${RUN_RC}"; DIFF_OUT_B="${RUN_OUT}"
if [[ "${DIFF_RC_A}" -eq "${DIFF_RC_B}" ]]; then
    fail "differential control: 666 and 600 returned the SAME exit (${DIFF_RC_A}) — the cases are not isolated, this harness is blind"
elif printf '%s' "${DIFF_OUT_A}" | grep -qF -- "${C600}/config/boba.db" \
  || printf '%s' "${DIFF_OUT_B}" | grep -qF -- "${C666}/config/boba.db"; then
    fail "differential control: a case reported the OTHER case's store path — the sandboxes leak into each other"
else
    pass "differential control: 666 -> ${DIFF_RC_A}, 600 -> ${DIFF_RC_B}, each naming its own store (cases are isolated)"
fi

# === harden_config_permissions: DIRECTION IS ONE-WAY (FR-015) =============
# The function may only ever REMOVE permission bits.

CH1="$(make_case harden_widened 666)"
printf 'x' >"${CH1}/config/other.conf"; chmod 664 "${CH1}/config/other.conf"
call_fn harden_config_permissions "${CH1}"
if [[ "${RUN_RC}" -ne 0 ]]; then
    fail "harden: exited ${RUN_RC} on a widened tree (expected 0)"
    printf '%s\n' "${RUN_OUT}" | sed 's/^/        /'
else
    got_db="$(stat -c '%a' "${CH1}/config/boba.db")"
    got_other="$(stat -c '%a' "${CH1}/config/other.conf")"
    if [[ "${got_db}" == "600" ]]; then
        pass "harden: credential store forced 666 -> 600 (FR-015 floor)"
    else
        fail "harden: credential store left at ${got_db} after hardening 666 (expected 600)"
    fi
    # The same group/other-only-shrinks invariant, on the widened side.
    if [[ "$(( (8#${got_db} & 8#077) & ~(8#666 & 8#077) ))" -eq 0 ]]; then
        pass "harden: group/other bits only shrank (0$(( 8#666 & 8#077 )) -> 0$(( 8#${got_db} & 8#077 )))"
    else
        fail "harden: group/other bits GREW while hardening 666 -> ${got_db}"
    fi
    if [[ "${got_other}" == "644" ]]; then
        pass "harden: sibling config file 664 -> 644 (group/other WRITE stripped, READ left alone)"
    else
        fail "harden: sibling config file is ${got_other} after hardening 664 (expected 644)"
    fi
fi

# The one-way property, stated as the requirement states it. FR-015 is about
# WHO ELSE can reach the store: "MUST remain no more permissive than it is
# today", where today is 600. So the invariant asserted here is the GROUP/OTHER
# direction — no bit may be added for any principal other than the owner — plus
# the 600 ceiling.
#
# MEASURED FACT worth recording, because a stricter assertion here fails and
# the reason is not obvious (2026-08-21, this harness): the implementation ends
# with an UNCONDITIONAL `chmod 600 "$cfg/boba.db"`, so a store already at 400
# comes out at 600 — owner-WRITE is re-added. That is still FR-015-compliant
# (600 is not more permissive than 600, and group/other stay 000; an owner can
# chmod their own file back at will, so no principal gained access), but it is
# NOT what start.sh's own header comment claims, which says the store is
# "forced DOWN to 600 only when it is currently more permissive". The comment
# is stronger than the code. That is doc-vs-code drift in a file this harness
# is not scoped to change, and it is REPORTED rather than silently baked in as
# expected behaviour: asserting the comment's wording here would fail on
# compliant code, which is the §11.4.201(1) false-positive refusal.
CH2="$(make_case harden_stricter 400)"
before_go="$(( 8#400 & 8#077 ))"
call_fn harden_config_permissions "${CH2}"
got_strict="$(stat -c '%a' "${CH2}/config/boba.db")"
after_go="$(( 8#${got_strict} & 8#077 ))"
if [[ "$(( after_go & ~before_go ))" -ne 0 ]]; then
    fail "harden: a 400 store gained group/other bits (${before_go} -> ${after_go}, mode ${got_strict}) — FR-015 forbids widening who can reach the store"
elif [[ "$(( 8#${got_strict} & 8#177 ))" -ne 0 ]]; then
    fail "harden: a 400 store came out at ${got_strict}, more permissive than the FR-015 600 ceiling"
else
    pass "harden: a 400 store stayed within FR-015 (400 -> ${got_strict}, group/other still 0${after_go}) — no principal gained access"
fi

# An absent config/ directory is a clean no-op, not an error.
CH3="${TMP_ROOT}/harden_no_config"
mkdir -p "${CH3}"
call_fn harden_config_permissions "${CH3}"
if [[ "${RUN_RC}" -eq 0 ]]; then
    pass "harden: absent config/ directory -> clean no-op (exit 0)"
else
    fail "harden: absent config/ directory returned ${RUN_RC} (expected 0)"
fi

# === RESIDUE: the real repository store was never touched =================
# harden_config_permissions chmods a whole tree. This reads the real store's
# mode back and asserts it is exactly what it was before this harness started.
if [[ -n "${REAL_STORE_MODE_BEFORE}" ]]; then
    REAL_STORE_MODE_AFTER="$(stat -c '%a' "${REAL_STORE}" 2>/dev/null || true)"
    if [[ "${REAL_STORE_MODE_AFTER}" == "${REAL_STORE_MODE_BEFORE}" ]]; then
        pass "residue: real ${REAL_STORE##*/} still mode ${REAL_STORE_MODE_AFTER} (unchanged by this harness)"
    else
        fail "residue: real credential store mode moved ${REAL_STORE_MODE_BEFORE} -> ${REAL_STORE_MODE_AFTER} — this harness wrote outside its sandbox"
    fi
else
    pass "residue: no real credential store on this host — nothing this harness could have touched"
fi

finish
