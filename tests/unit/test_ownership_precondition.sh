#!/usr/bin/env bash
# test_ownership_precondition.sh — scripts/ownership_precondition.sh must refuse
# to start when a declared location cannot produce operator-owned files, must NOT
# refuse a healthy one, and must never report a check it could not run as a pass.
#
# Contract under test:
#   specs/002-user-owned-downloads/contracts/startup-precondition.md
#   specs/002-user-owned-downloads/data-model.md  (E1 scope, E4 probe result)
#   FR-010, FR-010a, FR-010b
#
# §11.4.43/§11.4.224 RED-FIRST: at the time this file was written the target
# script `scripts/ownership_precondition.sh` DOES NOT EXIST. This suite is
# therefore expected to FAIL, and to fail for exactly that reason — the
# precheck below names it explicitly so a missing target is never confused with
# a broken assertion (§11.4.201(6): a quiet failure is not a diagnosis).
# T033 drives it from RED to GREEN.
#
# §11.4.201(1) BOTH DIRECTIONS — a guard that refuses a healthy system is as
# broken as one that passes a broken one. Case 3 (an `optional: true` location
# that is simply ABSENT) is the mandatory false-positive control and it is not
# optional: without it, "refuse everything" would pass this suite.
#
# §11.4.201(6) A CHECK THAT COULD NOT RUN HAS ASSERTED NOTHING — case 4 pins
# exit 2 for an unreadable scope and asserts explicitly that it is NOT 0. An
# implementation that maps "cannot parse the scope" onto "nothing is wrong" is
# the blind-instrument failure this feature exists to prevent.
#
# ── WHY EVERY INVOCATION FORCES `CONTAINER_RUNTIME=""` ──────────────────────
# The contract's P1 probe runs a THROWAWAY CONTAINER. Unit tests must not do
# that: §12.6/§12.12 host-safety bound this suite, invariant 30 executes every
# tests/unit/*.sh on every pre-build run, and podman IS present on this host
# (/usr/bin/podman, measured 2026-08-21) so an unguarded run would really
# launch containers at gate time. Every invocation below therefore sets
# `CONTAINER_RUNTIME=""` — the project's own canonical no-runtime sentinel
# (start.sh:335 sets it, start.sh:698 refuses on it, tests/integration/*.py
# read it) — so P1 takes its declared `runtime_unavailable` SKIP path.
#
# INTERFACE REQUIREMENT this places on T033 (stated, not smuggled): the script
# MUST treat an explicitly-empty `CONTAINER_RUNTIME` as "no container runtime
# available" rather than re-detecting podman behind the operator's back. That
# is also what makes the fallback path testable at all.
#
# HONEST COVERAGE BOUNDARY (§11.4.6) — because P1 is forced unavailable here,
# this suite CANNOT observe the real container-write condition, and it does not
# claim to. P1's actual behaviour (a container write landing at uid 100999) is
# integration territory and belongs to tests/integration/
# test_container_writes_owned_files.py. What this suite owns is: scope
# handling, the P2 host-write probe, the refusal message, the exit-code
# taxonomy, and the HONESTY of the P1-unavailable report (case 5) — which is
# precisely the defect finding X1 was raised for.
#
# §11.4.14 cleanup on every exit path via trap. §11.4.263: this suite signals
# no processes at all — there is no kill/pkill/killpg anywhere in it.

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${HERE}/../.." && pwd)"
SCRIPT="${PROJECT_ROOT}/scripts/ownership_precondition.sh"

PASS=0; FAIL=0; SKIP=0
pass() { PASS=$((PASS+1)); echo "  PASS: $1"; }
fail() { FAIL=$((FAIL+1)); echo "  FAIL: $1"; }
skip() { SKIP=$((SKIP+1)); echo "  SKIP: $1"; }
finish() {
    echo "RESULT: $PASS passed, $FAIL failed, $SKIP skipped"
    [ "$FAIL" -eq 0 ] || exit 1
    exit 0
}

# ── RED-phase precheck: name the missing target, do not guess ───────────────
# Distinguishes "the script does not exist yet" (the expected RED) from "a
# fixture path in this harness is wrong" (a defect in the test itself).
if [[ ! -f "$SCRIPT" ]]; then
    fail "target script missing: scripts/ownership_precondition.sh (expected during RED phase — T033 implements it)"
    echo "       looked for: $SCRIPT" >&2
    finish
fi
if [[ ! -x "$SCRIPT" ]]; then
    fail "target script exists but is not executable: scripts/ownership_precondition.sh"
    finish
fi

FIX="$(mktemp -d)"
# chmod first: case 2 creates a deliberately non-writable directory, and rm -rf
# cannot descend into it otherwise — cleanup would silently leave fixtures behind.
trap 'chmod -R u+rwX "$FIX" 2>/dev/null; rm -rf "$FIX"' EXIT

OPERATOR_UID="$(id -u)"
OUT=""; RC=0

# run_precond <scope-file> [extra args...] — invoke the REAL script through its
# REAL documented invocation path (§11.4.201(11)): the `--scope` flag the
# contract defines, never a re-implementation and never a private env backdoor.
run_precond() {
    local scope="$1"; shift
    OUT="${FIX}/out.$(date +%s%N).$RANDOM"
    CONTAINER_RUNTIME="" bash "$SCRIPT" --scope "$scope" "$@" >"$OUT" 2>&1
    RC=$?
}

dump_out() {
    echo "       --- exit=$RC, output ---" >&2
    sed -n '1,40p' "$OUT" >&2 || true
    echo "       --- end output ---" >&2
}

# ===========================================================================
# Case 1 — GOLDEN-GOOD: every declared location can produce operator-owned
# files -> exit 0.
# ===========================================================================
GOOD_DIR="${FIX}/good_downloads"
mkdir -p "$GOOD_DIR"
cat > "${FIX}/scope_good.yaml" <<EOF
schema_version: 1
paths:
  - path: "${GOOD_DIR}"
    kind: downloads
    optional: false
    preserve_mode: false
    recursive: true
EOF

run_precond "${FIX}/scope_good.yaml"
if [ "$RC" -eq 0 ]; then
    pass "golden-good: a location that produces operator-owned files -> exit 0"
else
    fail "golden-good: healthy location refused (exit $RC, expected 0) — §11.4.201(1) false-positive refusal"
    dump_out
fi

# ===========================================================================
# Case 1b — GOLDEN-GOOD, declared FILE branch. The contract carves this out:
# "Declared FILES (e.g. the credential store) have no write to probe: reading
# the target's own owner IS the real condition there, not a proxy for it." A
# present, operator-owned credential store must therefore pass WITHOUT the
# script trying to create anything inside it.
# ===========================================================================
GOOD_FILE="${FIX}/good_boba.db"
: > "$GOOD_FILE"
chmod 600 "$GOOD_FILE"
cat > "${FIX}/scope_good_file.yaml" <<EOF
schema_version: 1
paths:
  - path: "${GOOD_FILE}"
    kind: credential-store
    optional: true
    preserve_mode: true
    recursive: false
EOF

run_precond "${FIX}/scope_good_file.yaml"
if [ "$RC" -eq 0 ]; then
    pass "golden-good (declared FILE): present operator-owned credential store -> exit 0"
else
    fail "golden-good (declared FILE): present operator-owned credential store refused (exit $RC, expected 0)"
    dump_out
fi
# The probe must not have littered the credential store's directory.
if compgen -G "${FIX}/.ownership-probe.*" >/dev/null 2>&1; then
    fail "golden-good (declared FILE): a probe artefact was left behind next to the declared file"
else
    pass "golden-good (declared FILE): no probe artefact left behind (§11.4.14)"
fi

# ===========================================================================
# Case 1c — the documented `--quiet` flag must be ACCEPTED, not rejected as an
# unknown option. Only the exit code is asserted: the contract states the flag
# exists but does not fix its output shape, and inventing one here would be
# over-specification, not coverage (§11.4.6).
# ===========================================================================
run_precond "${FIX}/scope_good.yaml" --quiet
if [ "$RC" -eq 0 ]; then
    pass "--quiet: documented flag accepted on a healthy scope -> exit 0"
else
    fail "--quiet: documented flag rejected or altered the verdict (exit $RC, expected 0)"
    dump_out
fi

# ===========================================================================
# Case 2 — GOLDEN-BAD (unwritable): a location that CANNOT produce
# operator-owned files -> exit 1, and the message NAMES that location.
#
# Unprivileged realisation of "cannot produce operator-owned files": a
# directory the operator cannot write at all. Per the contract, "P2 fails =>
# refuse. The location is unusable regardless of P1", and E4 lists `unwritable`
# as a first-class verdict. The `wrong-owner` flavour needs a file owned by
# ANOTHER uid, which is unreachable unprivileged and belongs to the container
# integration test — stated here rather than faked (§11.4.6).
# ===========================================================================
if [ "$OPERATOR_UID" -eq 0 ]; then
    skip "golden-bad (unwritable): running as uid 0 — mode bits do not restrain root, so this fixture cannot reproduce the condition (§11.4.3)"
else
    BAD_DIR="${FIX}/bad_downloads"
    mkdir -p "$BAD_DIR"
    chmod 500 "$BAD_DIR"          # r-x: readable, traversable, NOT writable

    # Prove the fixture actually reproduces the condition before asserting on
    # it — a golden-bad fixture that is not bad makes the case vacuous
    # (§11.4.201(7)(b): the fixture is part of the instrument).
    # Subshell, not `: > f 2>/dev/null`: bash applies redirections left to
    # right, so the failing `>` reports to the ORIGINAL stderr before
    # `2>/dev/null` is in effect — the fixture check would print a spurious
    # "Permission denied" on the very path where denial is the expected result.
    if ( : > "${BAD_DIR}/.fixture_needle" ) 2>/dev/null; then
        rm -f "${BAD_DIR}/.fixture_needle"
        skip "golden-bad (unwritable): fixture did not reproduce — this filesystem let the operator write into a mode-500 directory"
    else
        cat > "${FIX}/scope_bad.yaml" <<EOF
schema_version: 1
paths:
  - path: "${GOOD_DIR}"
    kind: downloads
    optional: false
    preserve_mode: false
    recursive: true
  - path: "${BAD_DIR}"
    kind: downloads
    optional: false
    preserve_mode: false
    recursive: true
EOF
        run_precond "${FIX}/scope_bad.yaml"
        if [ "$RC" -eq 1 ]; then
            pass "golden-bad: unusable location -> exit 1"
        else
            fail "golden-bad: unusable location did NOT refuse (exit $RC, expected 1)"
            dump_out
        fi

        # FR-010a: never a bare "precondition failed" — the operator must be
        # able to act without further diagnosis.
        if grep -qF "$BAD_DIR" "$OUT"; then
            pass "golden-bad: refusal message NAMES the offending location (FR-010a)"
        else
            fail "golden-bad: refusal did not name the offending location $BAD_DIR (FR-010a)"
            dump_out
        fi

        if grep -qF 'OWNERSHIP-PRECONDITION: FAIL' "$OUT"; then
            pass "golden-bad: refusal carries the contract's OWNERSHIP-PRECONDITION: FAIL banner"
        else
            fail "golden-bad: refusal is missing the contract's 'OWNERSHIP-PRECONDITION: FAIL' banner"
            dump_out
        fi
    fi
fi

# ===========================================================================
# Case 2b — GOLDEN-BAD (absent, NOT optional): data-model E1 — "an absent
# non-optional path is an error, not a skip". Root-proof, so it keeps this
# suite's teeth even where case 2's mode bits do not bite.
# ===========================================================================
MISSING_DIR="${FIX}/definitely_absent_$RANDOM"
cat > "${FIX}/scope_absent_required.yaml" <<EOF
schema_version: 1
paths:
  - path: "${MISSING_DIR}"
    kind: downloads
    optional: false
    preserve_mode: false
    recursive: true
EOF

run_precond "${FIX}/scope_absent_required.yaml"
if [ "$RC" -eq 1 ]; then
    pass "golden-bad: absent NON-optional location -> exit 1 (E1: absence is an error, not a skip)"
else
    fail "golden-bad: absent non-optional location returned exit $RC, expected 1"
    dump_out
fi
if grep -qF "$MISSING_DIR" "$OUT"; then
    pass "golden-bad: refusal names the absent non-optional location (FR-010a)"
else
    fail "golden-bad: refusal did not name the absent non-optional location (FR-010a)"
    dump_out
fi

# ===========================================================================
# Case 3 — NEGATIVE CONTROL (§11.4.201(1), MANDATORY): an `optional: true`
# location that is simply ABSENT must NOT be a refusal.
#
# Without this case, an implementation that refuses everything would score a
# perfect suite. `config/boba.db` is exactly this shape in the real scope:
# absent before first boot, and its absence is not an error.
# ===========================================================================
ABSENT_OPTIONAL="${FIX}/never_created_$RANDOM/boba.db"
cat > "${FIX}/scope_optional_absent.yaml" <<EOF
schema_version: 1
paths:
  - path: "${GOOD_DIR}"
    kind: downloads
    optional: false
    preserve_mode: false
    recursive: true
  - path: "${ABSENT_OPTIONAL}"
    kind: credential-store
    optional: true
    preserve_mode: true
    recursive: false
EOF

run_precond "${FIX}/scope_optional_absent.yaml"
if [ "$RC" -eq 0 ]; then
    pass "negative control: absent optional: true location -> exit 0, NOT a refusal (§11.4.201(1))"
else
    fail "negative control: absent optional: true location REFUSED (exit $RC, expected 0) — false-positive refusal"
    dump_out
fi
if grep -qF 'OWNERSHIP-PRECONDITION: FAIL' "$OUT"; then
    fail "negative control: refusal banner emitted for an absent optional location"
    dump_out
else
    pass "negative control: no refusal banner emitted for an absent optional location"
fi

# ===========================================================================
# Case 4 — CANNOT RUN -> exit 2, and 2 is NOT a pass.
#
# "A check that cannot run has asserted nothing, and reporting that as success
# is the §11.4.201(6) blind-instrument failure." Both sub-cases assert exit 2
# AND assert explicitly that the code is not 0, so an implementation that
# swallows an unreadable scope into a green result is caught by name.
# ===========================================================================
run_precond "${FIX}/this_scope_file_does_not_exist.yaml"
if [ "$RC" -eq 2 ]; then
    pass "cannot-run: missing scope file -> exit 2"
else
    fail "cannot-run: missing scope file returned exit $RC, expected 2"
    dump_out
fi
if [ "$RC" -eq 0 ]; then
    fail "cannot-run: missing scope file reported SUCCESS — a check that could not run asserted nothing (§11.4.201(6))"
else
    pass "cannot-run: missing scope file did not report success"
fi

cat > "${FIX}/scope_unparseable.yaml" <<'EOF'
schema_version: 1
paths:
  - path: "/tmp/whatever
    kind: [downloads
   optional:: false
	tab-indented: and an unterminated quote above
EOF

run_precond "${FIX}/scope_unparseable.yaml"
if [ "$RC" -eq 2 ]; then
    pass "cannot-run: unparseable scope file -> exit 2"
else
    fail "cannot-run: unparseable scope file returned exit $RC, expected 2"
    dump_out
fi
if [ "$RC" -eq 0 ]; then
    fail "cannot-run: unparseable scope file reported SUCCESS — blind instrument reported as clean (§11.4.201(6))"
else
    pass "cannot-run: unparseable scope file did not report success"
fi

# ===========================================================================
# Case 5 — P1 UNAVAILABLE MUST BE REPORTED HONESTLY (finding X1).
#
# This is the case the contract amendment exists for. With no container
# runtime the check falls back to asserting the ownership route declared in
# docker-compose.yml — CONFIGURATION, not BEHAVIOUR — and it must SAY SO. A
# fallback reported as though the real condition had been checked is exactly
# the proxy-standing-in-for-the-condition defect (§11.4.201) that X1 named,
# inside the check written to prevent proxies.
#
# Assertions are on OUTPUT, deliberately: the exit code cannot distinguish
# "P1 verified the container write" from "P1 was skipped and something weaker
# was substituted". Only the report can.
# ===========================================================================
run_precond "${FIX}/scope_good.yaml"

if grep -qF 'runtime_unavailable' "$OUT"; then
    pass "P1-unavailable: honest 'runtime_unavailable' skip reason emitted (§11.4.3)"
else
    fail "P1-unavailable: no 'runtime_unavailable' reason in the report — the skip is silent"
    dump_out
fi

if grep -qE '(^|[^A-Za-z0-9])P1([^A-Za-z0-9]|$)' "$OUT"; then
    pass "P1-unavailable: the report identifies the skipped probe as P1"
else
    fail "P1-unavailable: report never names P1, so P1 and P2 cannot be told apart"
    dump_out
fi

if grep -qiE 'route|docker-compose' "$OUT"; then
    pass "P1-unavailable: report states the fallback used (route assertion)"
else
    fail "P1-unavailable: report does not say what was checked instead of P1"
    dump_out
fi

if grep -qiE 'configuration' "$OUT" && grep -qiE 'behaviour|behavior' "$OUT"; then
    pass "P1-unavailable: report states the fallback verifies CONFIGURATION, not BEHAVIOUR"
else
    fail "P1-unavailable: report does not state that a route assertion verifies configuration, not behaviour"
    dump_out
fi

# TEETH: the fallback must never be dressed up as a passing P1. Anything that
# reads as "P1 ok / P1 passed / container probe ok" while no container ran is
# the bluff this case exists to catch.
if grep -qiE 'P1[^A-Za-z0-9]{0,12}(ok|pass|passed|verified|success)' "$OUT" \
   || grep -qiE 'container[- ]?write[^.]{0,20}(ok|pass|passed|verified)' "$OUT"; then
    fail "P1-unavailable: report CLAIMS the container-write probe passed while no runtime was available (finding X1 defect)"
    dump_out
else
    pass "P1-unavailable: report never claims the container-write probe passed"
fi


# ===========================================================================
# Case 6 (BOB-187) — THE DECLARED-PATH FENCE
#
# scripts/ownership_precondition.sh consumes the SAME `.env`-driven, unreviewed
# scope as scripts/ownership_repair.sh and CREATES PROBE FILES inside it (see
# this script's own "Side-effects" header: "One probe file per declared
# DIRECTORY"), yet nothing constrained what a declared path may BE. The repair
# path was fenced in 8a08d49 via ownership_path_fence() in
# scripts/lib/ownership.sh; that commit's message records this sibling as still
# unfenced and files it as BOB-187.
#
# §11.4.251 — ONE predicate. These cases pin the precondition to the SHARED
# fence, never to a second dialect of its rules. They assert the OBSERVABLE
# CONSEQUENCE (refusal before any probe), not the fence's internals, which
# tests/unit/test_ownership_repair.sh already owns.
#
# EXIT 2, not 1. A scope naming a path of that shape is one this check does not
# trust at all — the same class the header at :47 already maps to 2 ("scope
# missing/unparseable/empty"). A fence refusal is NOT a per-location verdict:
# reporting it as FAIL(1) would assert "this location cannot produce
# operator-owned files", which is a different — and unproven — claim.
#
# TIMEOUT BELT on every invocation: during T028 remediation a probe declaring
# the verbatim shipped entry with QBITTORRENT_DATA_DIR=/ hung the suite.
# ===========================================================================

fence_scope() {   # fence_scope <scope-file> <declared-path>
    printf '%s\n' \
        'schema_version: 1' \
        'paths:' \
        "  - path: \"$2\"" \
        '    kind: downloads' \
        '    optional: false' \
        '    preserve_mode: false' \
        '    recursive: true' > "$1"
}

run_precond_fenced() {   # same documented --scope path, with a timeout belt
    local scope="$1"; shift
    OUT="${FIX}/out.$(date +%s%N).$RANDOM"
    CONTAINER_RUNTIME="" timeout 60 bash "$SCRIPT" --scope "$scope" "$@" >"$OUT" 2>&1
    RC=$?
}

# ---- 6a: an absolute entry naming a SYSTEM TREE (fence rule F3) ------------
fence_scope "${FIX}/scope_fence_systree.yaml" "/etc"
run_precond_fenced "${FIX}/scope_fence_systree.yaml"
if [ "$RC" -eq 2 ]; then
    pass "fence: absolute system tree /etc -> exit 2 (CANNOT-RUN, not a location verdict)"
else
    fail "fence: absolute system tree /etc -> exit $RC, expected 2 — the declared path was not fenced"
    dump_out
fi
if grep -q 'OWNERSHIP-PRECONDITION: CANNOT-RUN' "$OUT"; then
    pass "fence: system-tree refusal carries the contract's CANNOT-RUN banner"
else
    fail "fence: system-tree refusal did not emit the CANNOT-RUN banner"
    dump_out
fi

# ---- 6b: the FILESYSTEM ROOT (fence rule F2, depth floor) ------------------
# The exact value that drove `find / ...` in the repair, reaching the walk intact.
fence_scope "${FIX}/scope_fence_root.yaml" "/"
run_precond_fenced "${FIX}/scope_fence_root.yaml"
if [ "$RC" -eq 2 ]; then
    pass "fence: declared '/' -> exit 2"
else
    fail "fence: declared '/' -> exit $RC, expected 2 — the filesystem root was accepted as a scope"
    dump_out
fi
# TEETH: exit 2 must not be reachable by accident. The refusal must NAME the reason.
if grep -qE "filesystem root|path component" "$OUT"; then
    pass "fence: '/' refusal names the offending shape rather than failing silently"
else
    fail "fence: '/' refusal does not name why it refused (§11.4.201(5))"
    dump_out
fi

# ---- 6c: a repo-relative entry that CLIMBS OUT with '..' (fence rule F1) ---
# THE OBSERVABLE CASE. Pre-fix, absolutise() prepends PROJECT_ROOT and passes
# the '..' through untouched; the kernel resolves it at syscall time, so the
# probe file is really created OUTSIDE the project. Post-fix the entry is
# refused and the directory is never opened.
#
# The assertion is a real STATE DELTA (§11.4.69), not "no error": a directory's
# mtime changes when a file is created in it and again when it is unlinked, so
# an UNCHANGED mtime is positive evidence that probe_location() never ran there.
ESCAPE_DIR="${FIX}/escape_target"
mkdir -p "$ESCAPE_DIR"
CLIMB=""
for _ in $(seq 1 24); do CLIMB="${CLIMB}../"; done
fence_scope "${FIX}/scope_fence_climb.yaml" "${CLIMB}${ESCAPE_DIR#/}"

ESCAPE_MTIME_BEFORE="$(stat -c %y "$ESCAPE_DIR")"
run_precond_fenced "${FIX}/scope_fence_climb.yaml"
ESCAPE_MTIME_AFTER="$(stat -c %y "$ESCAPE_DIR")"

if [ "$RC" -eq 2 ]; then
    pass "fence: repo-relative '..' escape out of PROJECT_ROOT -> exit 2"
else
    fail "fence: repo-relative '..' escape -> exit $RC, expected 2 — a relative entry climbed out of the project"
    dump_out
fi
if [ "$ESCAPE_MTIME_BEFORE" = "$ESCAPE_MTIME_AFTER" ]; then
    pass "fence: no probe file was created in the escaped directory (mtime unchanged — positive evidence)"
else
    fail "fence: a probe file WAS created outside the project root — escaped directory mtime changed ($ESCAPE_MTIME_BEFORE -> $ESCAPE_MTIME_AFTER)"
    dump_out
fi

# ---- 6d: NEGATIVE CONTROL (§11.4.201(1)) ----------------------------------
# MANDATORY. A fence that refuses the live configuration is exactly as broken as
# no fence at all. The six entries SHIPPED in config/owned_paths.yaml must all
# ACCEPT — one absolute env-driven download root plus five repo-relative paths.
#
# Asserted at the FENCE, not by running the precondition: the real scope names
# the operator's real media library, and this suite must never create probe
# files there. The fence is the unit BOB-187 wires in, so the fence is the unit
# under test.
#
# Two environments, because both are real:
#   (i)  QBITTORRENT_DATA_DIR unset -> the shipped default /mnt/DATA, exactly 2
#        components — the floor the config itself forces.
#   (ii) a deep /run/media/... value — the shape this host's real library has.
#        /run is deliberately NOT denylisted; if it were, this control fails.
# When a real .env is present at the project root its value is used as well, so
# in the operator's own checkout this control exercises the live value.
LIVE_SCOPE="${PROJECT_ROOT}/config/owned_paths.yaml"
if [ ! -f "$LIVE_SCOPE" ]; then
    fail "negative control: shipped scope missing at ${LIVE_SCOPE}"
else
    DATA_DIR_CASES=("" "/run/media/operator/DISK4TB/Downloads")
    if [ -f "${PROJECT_ROOT}/.env" ]; then
        ENV_DATA_DIR="$(sed -n 's/^[[:space:]]*QBITTORRENT_DATA_DIR=//p' "${PROJECT_ROOT}/.env" | tail -1)"
        [ -n "$ENV_DATA_DIR" ] && DATA_DIR_CASES+=("$ENV_DATA_DIR")
    fi

    for DDIR in "${DATA_DIR_CASES[@]}"; do
        NC_OUT="${FIX}/nc.$(date +%s%N).$RANDOM"
        # Subshell: sourcing the library and exporting the scope override must
        # not leak into the rest of this suite.
        (
            set -uo pipefail
            # shellcheck source=scripts/lib/ownership.sh
            source "${PROJECT_ROOT}/scripts/lib/ownership.sh" || exit 90
            export OWNED_PATHS_FILE="$LIVE_SCOPE"
            if [ -n "$DDIR" ]; then export QBITTORRENT_DATA_DIR="$DDIR"; else unset QBITTORRENT_DATA_DIR; fi
            rows="$(ownership_scope_entries)" || exit 91
            n=0; refused=0
            while IFS=$'\t' read -r p _rest; do
                [ -n "$p" ] || continue
                n=$((n+1))
                wr=1
                case "$p" in /*) wr=0 ;; esac
                abs="$p"
                [ "$wr" -eq 1 ] && abs="${PROJECT_ROOT}/${p}"
                if ! reason="$(ownership_path_fence "$abs" "$wr" "$PROJECT_ROOT" 2>&1)"; then
                    echo "REFUSED: ${p} -- ${reason}"
                    refused=$((refused+1))
                fi
            done <<< "$rows"
            echo "ENTRIES=${n} REFUSED=${refused}"
        ) > "$NC_OUT" 2>&1
        NC_RC=$?

        LABEL="QBITTORRENT_DATA_DIR=${DDIR:-<unset, shipped default /mnt/DATA>}"
        if [ "$NC_RC" -ne 0 ]; then
            fail "negative control (${LABEL}): harness could not evaluate the live scope (rc=$NC_RC)"
            sed -n '1,20p' "$NC_OUT" >&2
        elif grep -q 'ENTRIES=6 REFUSED=0' "$NC_OUT"; then
            pass "negative control: all 6 shipped entries ACCEPT with ${LABEL}"
        else
            fail "negative control (${LABEL}): the fence refuses the live shipped scope — false-positive refusal (§11.4.201(1))"
            sed -n '1,20p' "$NC_OUT" >&2
        fi
    done
fi

finish
