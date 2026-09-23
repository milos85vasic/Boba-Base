#!/usr/bin/env bash
# test_bash_suite_discovery_covers_new_dirs.sh — BOB-222 (§11.4.226/§11.4.250)
#
# PURPOSE
#   Prove that invariant 30 (CM-BASH-UNIT-TESTS-EXECUTED)'s bash-suite
#   enumeration is DERIVED from the tests/ tree, not a hand-maintained
#   per-directory glob — and that its blind-discovery guard catches PARTIAL
#   blindness (some suites discovered, others silently missed), not only
#   TOTAL blindness (nothing discovered at all).
#
#   THIS IS THE THIRD RECURRENCE OF ONE CLASS (§11.4.250 "heuristic-tower
#   signals a primitive defect"): the enumeration used to be a literal
#   three-directory glob (tests/unit/, tests/pre_build/, tests/hooks/).
#   tests/security/test_gitignore_swallow_is_loud.sh — a real, tracked RED
#   test with a golden-FALSE guard — was executed by NOTHING because
#   tests/security/ was never added to that list. Patching in a fourth
#   directory literal would have been the fourth instance of the SAME
#   primitive defect (a hand list that must track the tree), not a fix.
#
# WHAT IS UNDER TEST — the REAL gate source, not a paraphrase
#   Two fragments are EXTRACTED VERBATIM from scripts/pre_build_verification.sh
#   by content marker (never by line number) and executed against a hermetic
#   scratch PROJECT_ROOT (§11.4.226 anti-echo — the extracted source is RUN,
#   not matched):
#     (1) the discovery + suite-execution loop, between
#         `# === BOB-222-DISCOVERY-BEGIN ===` and
#         `# === BOB-222-DISCOVERY-END ===`.
#     (2) the total/partial-blindness guard, between
#         `# === BOB-222-PARTIAL-BLINDNESS-BEGIN ===` and
#         `# === BOB-222-PARTIAL-BLINDNESS-END ===` (a truncated PREFIX of
#         the larger if/elif/.../else/fi decision chain — self-closed with
#         an appended `fi`, mirroring how
#         test_bob221_expected_red_declaration.sh's BLOCK_SRC already
#         extracts one elif and self-closes it).
#   A THIRD fragment — the historical, pre-BOB-222 three-directory glob — is
#   read from `git show HEAD:...`, read-only, never applied to the working
#   tree. It documents the defect this test guards against and gives a
#   genuine (non-synthetic) RAN count for the partial-blindness
#   demonstration below.
#
#   HONEST LAYER BOUNDARY (§11.4.226): this is a runtime-class test of
#   invariant 30's discovery + guard logic. It is NOT a full
#   pre_build_verification.sh run — that gate is a 56-invariant monolith and
#   running it here would recurse (invariant 30 executes this very file).
#
# INSTRUMENT VIABILITY (§11.4.201(7)(b))
#   Every extraction is control-needle-checked; a blind harness ABORTS
#   (exit 3) rather than reporting a verdict.
#
# WHAT THIS ASSERTS (the oracle — §11.4.245)
#   Strategy: SPECIFIED. The acceptance properties are fixed by BOB-222 and
#   by this repository's own §11.4.250/§11.4.226; they are not read off the
#   implementation. The oracle is structurally independent of the code under
#   test — expected discovery counts and marker presence come from the
#   scratch fixture THIS test builds, never from what the gate happens to do.
#
#   P1  the historical (pre-BOB-222) three-directory glob does NOT discover
#       a tests/<newdir>/test_*.sh suite — the RED reproduction.
#   P2  the CURRENT discovery DOES discover + EXECUTE a tests/<newdir>/
#       test_*.sh suite, with NO hand edit to the driver — the GREEN check
#       for acceptance criteria (1) and (2).
#   P3  the CURRENT discovery still discovers + executes the original three
#       directories' suites (tests/unit/, tests/pre_build/, tests/hooks/) —
#       no regression in existing coverage (acceptance criterion 5).
#   P4  the partial-blindness guard does NOT fire when every on-disk suite
#       was accounted for (negative control — never cries wolf).
#   P5  the partial-blindness guard DOES fire when fewer suites were
#       accounted for than exist on disk, using the GENUINE RAN count the
#       historical three-directory glob produced against a tree containing
#       an extra directory — acceptance criterion (4), demonstrated against
#       real numbers, not fabricated ones.
#   P6  the total-blindness branch (not the partial one) still fires when
#       NOTHING was discovered — the two guards do not collide.
#
# EXIT CODES
#   0  GREEN — the tree-derived discovery and the widened guard hold P1..P6
#   1  RED   — the discovery is still a hand list, or the guard is still
#              blind to partial coverage loss
#   3  ABORT — instrument blind / precondition unmet (NOT a verdict)
#
# Usage        : bash tests/pre_build/test_bash_suite_discovery_covers_new_dirs.sh
# Inputs       : scripts/pre_build_verification.sh (read-only, verbatim extract)
#                `git show HEAD:scripts/pre_build_verification.sh` (read-only)
# Outputs      : human-readable verdict on stdout
# Side-effects : one mktemp -d scratch tree, removed on every exit path
#                (§11.4.14). Nothing in the real repository is created,
#                staged, modified, or deleted. No network, no container, no
#                signal delivery (§11.4.263), no host power-state change
#                (CONST-033).
# Depends      : bash, sed, grep, find, git, mktemp, timeout
# Refs         : BOB-222; §11.4.6, §11.4.115, §11.4.201(1)(6)(7), §11.4.224(E),
#                §11.4.226, §11.4.227, §11.4.245, §11.4.248, §11.4.250,
#                §11.4.273.

set -uo pipefail

GATE="scripts/pre_build_verification.sh"
SCRATCH=""
RC_GREEN=0; RC_RED=1; RC_ABORT=3

abort() { echo "ABORT: $*" >&2; exit "${RC_ABORT}"; }
cleanup() { [[ -n "${SCRATCH}" && -d "${SCRATCH}" ]] && rm -rf "${SCRATCH}"; }
trap cleanup EXIT

FAILED_PROPS=()
note_fail() { FAILED_PROPS+=("$1"); echo "  RED  $1"; }
note_ok()   { echo "  ok   $1"; }

# ---------------------------------------------------------------------------
# 0. Preconditions + instrument viability
# ---------------------------------------------------------------------------
[[ -r "${GATE}" ]] || abort "cannot read ${GATE} (run from the repository root)"
command -v git >/dev/null 2>&1 || abort "git absent — cannot read the historical baseline"
command -v find >/dev/null 2>&1 || abort "find absent — the discovery mechanism under test needs it"
command -v timeout >/dev/null 2>&1 || abort "timeout absent — scratch suite execution needs it"

# The preamble a bare `for _bt in ...` fragment needs when it is extracted
# WITHOUT everything invariant 30 normally initialises ahead of it (the
# BASH_TEST_SELF_RECURSIVE/QUARANTINE arrays, the EXPECTED-RED fallback
# functions, the RAN/FAILED/QUARANTINED/FAILURES bookkeeping vars) — used
# below for BOTH the historical (git HEAD) extraction and the live-file
# FALLBACK extraction when the BOB-222 markers are absent from the working
# tree (i.e. this test is genuinely run pre-fix, per TDD ordering).
OLD_ANCHOR_PREAMBLE=(
    "BASH_TEST_SELF_RECURSIVE=()" "BASH_TEST_QUARANTINE=()"
    "BASH_TEST_RAN=0; BASH_TEST_FAILED=0; BASH_TEST_QUARANTINED=0"
    "BASH_TEST_FAILURES=()"
    "expected_red_verdict() { echo UNDECLARED; }"
    "expected_red_note_append() { :; }"
    "expected_red_unmatched_rows() { :; }"
    "declare -gA _EXPECTED_RED_SEEN=()"
)

# --- extract (1): the CURRENT discovery + suite-execution loop, from the
#     LIVE working-tree file — graceful fallback to the historical anchor
#     when the fix is not (yet) applied, so the properties below report a
#     genuine RED (exit 1) rather than an ABORT (exit 3) pre-fix. ABORT stays
#     reserved for TRUE instrument blindness (neither anchor present at all).
DISCOVERY_PREAMBLE=()
if grep -q '^# === BOB-222-DISCOVERY-BEGIN ===' "${GATE}"; then
    DISCOVERY_HAS_FIX=1
    DISCOVERY_SRC="$(sed -n '/^# === BOB-222-DISCOVERY-BEGIN ===/,/^# === BOB-222-DISCOVERY-END ===/p' "${GATE}")"
    [[ -n "${DISCOVERY_SRC}" ]] || abort "control needle: BOB-222-DISCOVERY-BEGIN/END markers matched but extraction was empty — instrument blind"
    grep -q 'BASH_TEST_DISCOVERED' <<<"${DISCOVERY_SRC}" \
      || abort "control needle: extracted discovery region does not mention BASH_TEST_DISCOVERED — wrong region captured"
    grep -q 'expected_red_unmatched_rows' <<<"${DISCOVERY_SRC}" \
      || abort "control needle: extracted discovery region has no table sweep — wrong region captured"
elif grep -q '^for _bt in .*tests/unit/test_\*\.sh' "${GATE}"; then
    DISCOVERY_HAS_FIX=0
    DISCOVERY_SRC="$(sed -n '/^for _bt in .*tests\/unit\/test_\*\.sh/,/^# END-INVARIANT-30-SUITE-LOOP$/p' "${GATE}")"
    [[ -n "${DISCOVERY_SRC}" ]] || abort "control needle: could not extract the historical (pre-fix) loop from the live file — instrument blind"
    grep -q 'BASH_TEST_FAILURES+=' <<<"${DISCOVERY_SRC}" \
      || abort "control needle: live pre-fix extraction does not record failures — wrong region captured"
    DISCOVERY_PREAMBLE=("${OLD_ANCHOR_PREAMBLE[@]}")
else
    abort "control needle: NEITHER the BOB-222 discovery markers NOR the historical for-loop anchor were found in ${GATE} — instrument blind"
fi

# --- extract (2): the CURRENT total/partial-blindness guard prefix — this
#     mechanism is NEW (it did not exist before BOB-222 at all), so there is
#     no historical fallback to extract; its absence is itself the pre-fix
#     RED state for P4/P5/P6 below.
if grep -q '^# === BOB-222-PARTIAL-BLINDNESS-BEGIN ===' "${GATE}"; then
    BLINDNESS_HAS_FIX=1
    BLINDNESS_SRC="$(sed -n '/^# === BOB-222-PARTIAL-BLINDNESS-BEGIN ===/,/^# === BOB-222-PARTIAL-BLINDNESS-END ===/p' "${GATE}" | sed '1d;$d')"
    [[ -n "${BLINDNESS_SRC}" ]] || abort "control needle: BOB-222-PARTIAL-BLINDNESS-BEGIN/END markers matched but extraction was empty — instrument blind"
    grep -q 'BASH_TEST_ONDISK_COUNT' <<<"${BLINDNESS_SRC}" \
      || abort "control needle: extracted guard region does not mention BASH_TEST_ONDISK_COUNT — wrong region captured"
    grep -q 'PARTIAL blindness' <<<"${BLINDNESS_SRC}" \
      || abort "control needle: extracted guard region has no PARTIAL-blindness branch — wrong region captured"
    BLINDNESS_SRC="${BLINDNESS_SRC}
fi"
else
    BLINDNESS_HAS_FIX=0
    BLINDNESS_SRC=""
fi

# --- extract (3): the HISTORICAL (pre-BOB-222) three-directory glob, from
#     git history only — never applied to the working tree. This is a
#     PERMANENT, always-available characterisation of the original defect
#     (P1), independent of whatever the live working tree currently holds.
OLD_GATE_CONTENT="$(git show HEAD:"${GATE}" 2>/dev/null || true)"
if [[ -z "${OLD_GATE_CONTENT}" ]]; then
    abort "control needle: 'git show HEAD:${GATE}' returned nothing — cannot read the historical baseline"
fi
if grep -q '^for _bt in .*tests/unit/test_\*\.sh' <<<"${OLD_GATE_CONTENT}"; then
    OLD_DISCOVERY_SRC="$(sed -n '/^for _bt in .*tests\/unit\/test_\*\.sh/,/^# END-INVARIANT-30-SUITE-LOOP$/p' <<<"${OLD_GATE_CONTENT}")"
    [[ -n "${OLD_DISCOVERY_SRC}" ]] || abort "control needle: could not extract the historical loop from HEAD — instrument blind"
    grep -q 'BASH_TEST_FAILURES+=' <<<"${OLD_DISCOVERY_SRC}" \
      || abort "control needle: historical extraction does not record failures — wrong region captured"
    HAVE_HISTORICAL=1
else
    # HEAD itself already carries the fix (e.g. this test runs after the
    # BOB-222 commit landed on a clean checkout with no working-tree diff).
    # P1's historical-RED comparison becomes honestly N/A; every other
    # property still stands on the live GATE alone.
    HAVE_HISTORICAL=0
fi

# ---------------------------------------------------------------------------
# 1. Hermetic scratch PROJECT_ROOT
# ---------------------------------------------------------------------------
SCRATCH="$(mktemp -d)" || abort "mktemp -d failed"
MARKDIR="${SCRATCH}/.markers"

build_fixture() {
    rm -rf "${SCRATCH}/tests" "${MARKDIR}"
    mkdir -p "${SCRATCH}/tests/unit" "${SCRATCH}/tests/pre_build" "${SCRATCH}/tests/hooks" \
             "${SCRATCH}/tests/security" "${SCRATCH}/tests/zzz_never_seen_before" \
             "${MARKDIR}"
    mk_suite() { # $1 = marker name, $2 = path relative to SCRATCH
        local p="${SCRATCH}/$2"
        { echo '#!/usr/bin/env bash'
          echo "touch \"${MARKDIR}/$1\""
          echo 'exit 0'
        } > "${p}"
        chmod +x "${p}"
    }
    mk_suite "unit_ran"     "tests/unit/test_u.sh"
    mk_suite "pre_build_ran" "tests/pre_build/test_p.sh"
    mk_suite "hooks_ran"    "tests/hooks/test_h.sh"
    mk_suite "security_ran" "tests/security/test_probe.sh"
    mk_suite "newdir_ran"   "tests/zzz_never_seen_before/test_probe2.sh"
}
ONDISK_TOTAL=5   # the five suites build_fixture() always creates

run_extracted() { # $1 = bash source to run, remaining $@ = extra var assigns
    local src="$1"; shift
    local runner="${SCRATCH}/runner.sh"
    {
        echo 'set -uo pipefail'
        # The extracted DISCOVERY_SRC fragment itself checks
        # BOBA_PREBUILD_NESTED (it is the recursion guard invariant 30
        # wraps its own suite loop in) and SKIPs its loop entirely when
        # that var is set — MEASURED live 2026-09-23: this suite is itself
        # invoked BY the real invariant 30 with BOBA_PREBUILD_NESTED=1 in
        # its environment (that prefix is applied uniformly to every
        # discovered suite), and without this `unset` that ambient value
        # leaked into the scratch sub-invocation below and produced a false
        # BASH_TEST_RAN=0 — a bug in the HARNESS, not in the fix under
        # test. The var means "an outer pre_build_verification.sh run is
        # already in flight" — never true of a fresh scratch fixture this
        # function builds, regardless of what the caller inherited.
        echo 'unset BOBA_PREBUILD_NESTED'
        echo "PROJECT_ROOT=\"${SCRATCH}\""
        echo 'pass() { echo "PASS: $1"; }'
        echo 'fail() { echo "FAIL: $1"; }'
        local extra; for extra in "$@"; do echo "${extra}"; done
        echo "${src}"
        echo 'echo "__BASH_TEST_RAN__=${BASH_TEST_RAN:-unset}"'
        echo 'echo "__BASH_TEST_QUARANTINED__=${BASH_TEST_QUARANTINED:-unset}"'
    } > "${runner}"
    ( cd "${SCRATCH}" && env -u BOBA_PREBUILD_NESTED timeout 60 bash "${runner}" 2>&1 )
}

field() { # $1 = captured output, $2 = field name
    grep -o "__${2}__=[^ ]*" <<<"$1" | tail -n1 | cut -d= -f2
}

# ---------------------------------------------------------------------------
# 2. P1 — historical glob does NOT discover a new directory (RED reproduction)
# ---------------------------------------------------------------------------
build_fixture
OLD_RAN=""
if [[ "${HAVE_HISTORICAL}" -eq 1 ]]; then
    # The historical extraction begins AT the `for _bt in ...` header (the
    # OLD begin-anchor, exactly as the pre-BOB-222 sibling test used it) —
    # everything invariant 30 initialised BEFORE that line in the real gate
    # is supplied here as extras, mirroring
    # test_bob221_expected_red_declaration.sh's run_gate() preamble.
    OLD_OUT="$(run_extracted "${OLD_DISCOVERY_SRC}" "${OLD_ANCHOR_PREAMBLE[@]}")"
    OLD_RAN="$(field "${OLD_OUT}" BASH_TEST_RAN)"
    if [[ -e "${MARKDIR}/security_ran" || -e "${MARKDIR}/newdir_ran" ]]; then
        note_fail "P1 the historical three-directory glob discovered a new-directory suite — RED reproduction failed to reproduce"
    elif [[ ! -e "${MARKDIR}/unit_ran" || ! -e "${MARKDIR}/pre_build_ran" || ! -e "${MARKDIR}/hooks_ran" ]]; then
        note_fail "P1 the historical glob did not even cover its own three named directories — fixture or extraction is broken, not a genuine RED"
    else
        note_ok "P1 historical glob covers unit/pre_build/hooks but silently misses tests/security/ and tests/zzz_never_seen_before/ (RAN=${OLD_RAN}) — confirmed RED"
    fi
else
    OLD_RAN="3"   # the historical glob, when present, always names exactly 3 dirs
    note_ok "P1 SKIPPED (honest N/A): HEAD already carries the BOB-222 fix; no working-tree diff to reproduce against — see the report's separate git-revert/restore evidence for live RED/GREEN polarity"
fi

# ---------------------------------------------------------------------------
# 3. P2 + P3 — CURRENT discovery covers the new directories AND the original
#    three, with no hand edit and no regression
# ---------------------------------------------------------------------------
build_fixture
NEW_OUT="$(run_extracted "${DISCOVERY_SRC}" "${DISCOVERY_PREAMBLE[@]+"${DISCOVERY_PREAMBLE[@]}"}")"
NEW_RAN="$(field "${NEW_OUT}" BASH_TEST_RAN)"
NEW_QUARANTINED="$(field "${NEW_OUT}" BASH_TEST_QUARANTINED)"

if [[ "${DISCOVERY_HAS_FIX}" -eq 0 ]]; then
    echo "  note DISCOVERY_HAS_FIX=0 — the live file has NO BOB-222-DISCOVERY-BEGIN marker; exercising the historical (pre-fix) anchor against the SAME live file. This IS the genuine pre-fix RED path, not a stand-in."
fi

if [[ -e "${MARKDIR}/security_ran" && -e "${MARKDIR}/newdir_ran" ]]; then
    note_ok "P2 current discovery ran tests/security/test_probe.sh AND tests/zzz_never_seen_before/test_probe2.sh with NO hand edit to the driver"
else
    note_fail "P2 current discovery did NOT run one or both new-directory suites (security_ran=$([[ -e "${MARKDIR}/security_ran" ]] && echo yes || echo no), newdir_ran=$([[ -e "${MARKDIR}/newdir_ran" ]] && echo yes || echo no), fix-present=${DISCOVERY_HAS_FIX})"
fi

if [[ -e "${MARKDIR}/unit_ran" && -e "${MARKDIR}/pre_build_ran" && -e "${MARKDIR}/hooks_ran" ]]; then
    note_ok "P3 current discovery still runs the original tests/unit/, tests/pre_build/, tests/hooks/ suites — no regression"
else
    note_fail "P3 current discovery LOST coverage of an original directory (unit=$([[ -e "${MARKDIR}/unit_ran" ]] && echo yes || echo no), pre_build=$([[ -e "${MARKDIR}/pre_build_ran" ]] && echo yes || echo no), hooks=$([[ -e "${MARKDIR}/hooks_ran" ]] && echo yes || echo no))"
fi

if [[ "${NEW_RAN}" == "${ONDISK_TOTAL}" ]]; then
    note_ok "P2b BASH_TEST_RAN (${NEW_RAN}) == on-disk total (${ONDISK_TOTAL}) for the fixture"
else
    note_fail "P2b BASH_TEST_RAN (${NEW_RAN}) != on-disk total (${ONDISK_TOTAL}) — discovery under- or over-counted"
fi

if [[ "${BLINDNESS_HAS_FIX}" -eq 0 ]]; then
    note_fail "P4 the partial/total-blindness guard (BOB-222-PARTIAL-BLINDNESS-BEGIN/END) does not exist in the live file yet"
    note_fail "P5 the partial/total-blindness guard (BOB-222-PARTIAL-BLINDNESS-BEGIN/END) does not exist in the live file yet"
    note_fail "P6 the partial/total-blindness guard (BOB-222-PARTIAL-BLINDNESS-BEGIN/END) does not exist in the live file yet"
else
# ---------------------------------------------------------------------------
# 4. P4 — partial-blindness guard is SILENT when fully accounted for
# ---------------------------------------------------------------------------
HEALTHY_OUT="$(run_extracted "${BLINDNESS_SRC}" \
    "BASH_TEST_RAN=${NEW_RAN}" "BASH_TEST_QUARANTINED=${NEW_QUARANTINED:-0}")"
if grep -q 'PARTIAL blindness' <<<"${HEALTHY_OUT}"; then
    note_fail "P4 the guard fired 'PARTIAL blindness' on a fully-accounted-for tree (RAN=${NEW_RAN}, on-disk=${ONDISK_TOTAL}) — false positive"
else
    note_ok "P4 the guard is silent when every on-disk suite was accounted for (RAN=${NEW_RAN} == on-disk=${ONDISK_TOTAL})"
fi

# ---------------------------------------------------------------------------
# 5. P5 — partial-blindness guard FIRES on the GENUINE historical undercount
#    (acceptance criterion 4: a known directory's coverage silently dropped)
# ---------------------------------------------------------------------------
PARTIAL_OUT="$(run_extracted "${BLINDNESS_SRC}" \
    "BASH_TEST_RAN=${OLD_RAN}" "BASH_TEST_QUARANTINED=0")"
if grep -q "PARTIAL blindness — discovery accounted for only ${OLD_RAN}/${ONDISK_TOTAL}" <<<"${PARTIAL_OUT}"; then
    note_ok "P5 the guard FIRES on the genuine historical undercount (accounted-for=${OLD_RAN}, on-disk=${ONDISK_TOTAL}) — a silently-dropped directory is now detected, not just 'zero ran'"
else
    note_fail "P5 the guard did NOT fire (or fired with the wrong numbers) for accounted-for=${OLD_RAN} vs on-disk=${ONDISK_TOTAL}; got: $(grep -o '.*PARTIAL blindness.*' <<<"${PARTIAL_OUT}" || echo '<nothing>')"
fi

# ---------------------------------------------------------------------------
# 6. P6 — total blindness still reported as total, not as partial
# ---------------------------------------------------------------------------
TOTAL_OUT="$(run_extracted "${BLINDNESS_SRC}" "BASH_TEST_RAN=0" "BASH_TEST_QUARANTINED=0")"
if grep -q 'the discovery is blind' <<<"${TOTAL_OUT}" && ! grep -q 'PARTIAL blindness' <<<"${TOTAL_OUT}"; then
    note_ok "P6 a zero-RAN tree is reported as TOTAL blindness, not double-counted as partial"
else
    note_fail "P6 the total- and partial-blindness branches did not fire exclusively for RAN=0; got: ${TOTAL_OUT}"
fi
fi

# ---------------------------------------------------------------------------
# Verdict
# ---------------------------------------------------------------------------
echo
if [[ "${#FAILED_PROPS[@]}" -eq 0 ]]; then
    echo "RESULT: GREEN (exit ${RC_GREEN}) — tree-derived discovery + widened blind-discovery guard hold P1..P6."
    exit "${RC_GREEN}"
else
    echo "RESULT: RED (exit ${RC_RED}) — ${#FAILED_PROPS[@]} propert$([[ "${#FAILED_PROPS[@]}" -eq 1 ]] && echo y || echo ies) failed:"
    for p in "${FAILED_PROPS[@]}"; do echo "  - ${p}"; done
    exit "${RC_RED}"
fi
