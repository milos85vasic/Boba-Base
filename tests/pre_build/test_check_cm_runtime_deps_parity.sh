#!/usr/bin/env bash
# test_check_cm_runtime_deps_parity.sh — §1.1 paired-mutation meta-test for
# scripts/pre_build/check_cm_runtime_deps_parity.sh (CM-RUNTIME-DEPS-PARITY).
#
# TDD (§11.4.43/§11.4.115/§11.4.224): this harness proves the gate is not a
# bluff before the gate is trusted. It drives the gate against hermetic
# snapshot fixtures with KNOWN outcomes, and — the load-bearing part — against
# a MUTATED copy of the gate whose comparator has been blinded, to prove the
# embedded control needle is doing real work rather than decorating the output.
#
# WHY A GATE AT ALL (BOB-154, measured 2026-08-21): the host venv resolved
# Python 3.14.6 + starlette 1.4.1 while the production container resolved
# Python 3.12.13 + starlette 1.6.0. Eight packages plus the interpreter
# diverged, and nothing in the stack reported it, so every green suite was
# evidence about a stack nobody served.
#
# Fixtures (each is a pair of injected snapshots — the gate reads them instead
# of probing, so no container and no venv are touched):
#   golden-good              -> rc 0  parity holds
#   golden-good-hostonly     -> rc 0  host carries extra DEV TOOLING (pytest,
#                                     ruff). The §11.4.201(1) false-POSITIVE
#                                     guard: a gate that demanded set equality
#                                     would refuse every healthy checkout,
#                                     because a venv is supposed to hold test
#                                     tooling a production image must not.
#   golden-good-patch        -> rc 0  interpreter differs in PATCH only
#                                     (3.12.7 vs 3.12.13). Documented as
#                                     non-fatal; failing here would make the
#                                     gate unusable and get it switched off.
#   golden-good-normalise    -> rc 0  `typing_extensions` vs `typing-extensions`
#                                     at the SAME version. PEP 503 says these
#                                     are one package. Without normalisation
#                                     this reports a phantom divergence AND
#                                     hides real ones by treating the two
#                                     spellings as unrelated packages.
#   golden-good-installer    -> rc 0  `pip` differs across the two sides. It is
#                                     excluded by name and deliberately not
#                                     pinned, so flagging it would demand an
#                                     action the fix cannot perform.
#   golden-bad-version       -> rc 1  starlette 1.4.1 vs 1.6.0 — the exact
#                                     BOB-154 shape.
#   golden-bad-interpreter   -> rc 1  CPython 3.14.6 vs 3.12.13 — the largest
#                                     divergence BOB-154 measured, and the one
#                                     NO requirements pin can ever reach.
#   golden-bad-absent        -> rc 1  a production dependency missing from the
#                                     host entirely: worse than a skew, since
#                                     the tests cannot exercise it at all.
#   golden-bad-empty         -> rc 1  container snapshot with zero packages.
#                                     The §11.4.201(6) false-NULL guard: a
#                                     blind probe and a matching stack both
#                                     return a quiet zero, and reading that as
#                                     parity is the bluff this gate exists to
#                                     prevent.
#   golden-bad-installer-only-> rc 1  proves the installer exclusion is a NAMED
#                                     list and not a hole: `pip` is ignored in
#                                     the SAME run where a real dependency skew
#                                     is still caught.
#   declared-tolerated       -> rc 0  a divergence listed in
#                                     DECLARED_DIVERGENCES is reported loudly
#                                     but does not fail (the BOB-154 acceptance
#                                     criterion: a deliberate divergence may be
#                                     DECLARED rather than eliminated).
#   declared-stale           -> rc 1  a declaration matching NO current
#                                     divergence FAILs. This is what stops the
#                                     declaration mechanism becoming an off
#                                     switch: an excuse cannot be filed
#                                     pre-emptively and cannot outlive the
#                                     condition it excuses (§11.4.227 ratchet).
#   skip-no-container        -> rc 0, verdict must begin `SKIP(` — a stopped
#                                     stack is a legitimate state. A gate that
#                                     hard-failed here would be disabled by the
#                                     first person to build with the stack down.
#   MUTATION blinded-comparator -> rc 1 against a fixture that would otherwise
#                                     PASS. The §1.1 mutation: the comparator
#                                     is replaced with one that reports
#                                     nothing. If the gate still passed, its
#                                     silence would mean nothing and the
#                                     control needle would be decoration.
#   real-tree                -> executes against the live stack and must emit a
#                                     well-formed verdict with the needle line.
#                                     rc is NOT asserted to a fixed value: it
#                                     is 1 while the venv is still unreconciled
#                                     and 0 afterwards, and pinning either
#                                     would make this harness lie on the other
#                                     side of the operator's apply step.
#
# A gate that PASSes any golden-bad, or FAILs any golden-good, is itself the
# bluff (§11.4.107(10)) and this harness reports it.
#
# Usage:   bash tests/pre_build/test_check_cm_runtime_deps_parity.sh
# Inputs:  none (no stdin, no arguments).
# Outputs: per-case PASS/FAIL lines on stdout; diagnostics on stdout.
# Side-effects: creates and removes one `mktemp -d` tree. Touches nothing in
#               the repository and never starts, stops or mutates a container.
# Dependencies: bash, mktemp, sed, grep.
#
set -euo pipefail

HARNESS_NAME="test_check_cm_runtime_deps_parity.sh"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
GATE="${REPO_ROOT}/scripts/pre_build/check_cm_runtime_deps_parity.sh"

[[ -f "$GATE" ]] || { echo "$HARNESS_NAME: ERROR — gate not found at $GATE" >&2; exit 2; }

TMP="$(mktemp -d -t cm_deps_parity_test.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT

fails=0
LAST_OUT=""
LAST_RC=0

# Run a gate (real or mutated) against a fixture pair. Snapshots are INJECTED,
# so the case is hermetic: no container, no venv, no network.
run_gate() {
    local gate="$1" host="$2" cont="$3"
    LAST_RC=0
    LAST_OUT="$(CM_DEPS_HOST_SNAPSHOT="$host" CM_DEPS_CONTAINER_SNAPSHOT="$cont" \
        bash "$gate" 2>&1)" || LAST_RC=$?
}

assert_rc() {
    local label="$1" want="$2"
    if [[ "$LAST_RC" -eq "$want" ]]; then
        echo "  PASS  $label"
    else
        echo "  FAIL  $label (expected rc $want, got $LAST_RC)"
        sed 's/^/          | /' <<< "$LAST_OUT"
        fails=$((fails + 1))
    fi
}

assert_out_matches() {
    local label="$1" pattern="$2"
    if grep -qE "$pattern" <<< "$LAST_OUT"; then
        echo "  PASS  $label"
    else
        echo "  FAIL  $label (output did not match /$pattern/)"
        sed 's/^/          | /' <<< "$LAST_OUT"
        fails=$((fails + 1))
    fi
}

# A minimal but realistic production set: the packages BOB-154 actually
# measured as divergent, so the fixtures exercise the real shape.
write_snapshot() {
    local path="$1"; shift
    printf '%s\n' "$@" > "$path"
}

PROD=(
    "#python 3.12.13"
    "fastapi==0.141.1"
    "starlette==1.6.0"
    "uvicorn==0.52.4"
    "idna==3.19"
    "filelock==3.32.3"
)

echo "$HARNESS_NAME: CM-RUNTIME-DEPS-PARITY fixture sweep"
echo

# --- golden-good -----------------------------------------------------------
write_snapshot "$TMP/good_host" "${PROD[@]}"
write_snapshot "$TMP/prod"      "${PROD[@]}"
run_gate "$GATE" "$TMP/good_host" "$TMP/prod"
assert_rc "golden-good (identical sets — must PASS)" 0
assert_out_matches "golden-good reports the control needle was seen" "control needle: seen"

# --- golden-good-hostonly (false-positive guard) ---------------------------
write_snapshot "$TMP/hostonly" "${PROD[@]}" "pytest==8.3.2" "ruff==0.6.9" "mypy==1.11.2"
run_gate "$GATE" "$TMP/hostonly" "$TMP/prod"
assert_rc "golden-good-hostonly (venv dev tooling must not be flagged)" 0

# --- golden-good-patch -----------------------------------------------------
write_snapshot "$TMP/patch_host" "#python 3.12.7" "fastapi==0.141.1" "starlette==1.6.0" \
    "uvicorn==0.52.4" "idna==3.19" "filelock==3.32.3"
run_gate "$GATE" "$TMP/patch_host" "$TMP/prod"
assert_rc "golden-good-patch (interpreter patch skew is non-fatal by design)" 0

# --- golden-good-normalise (PEP 503) ---------------------------------------
write_snapshot "$TMP/norm_host" "${PROD[@]}" "typing_extensions==4.16.0"
write_snapshot "$TMP/norm_cont" "${PROD[@]}" "typing-extensions==4.16.0"
run_gate "$GATE" "$TMP/norm_host" "$TMP/norm_cont"
assert_rc "golden-good-normalise (typing_extensions == typing-extensions)" 0

# --- golden-good-installer -------------------------------------------------
write_snapshot "$TMP/inst_host" "${PROD[@]}" "pip==26.2.1"
write_snapshot "$TMP/inst_cont" "${PROD[@]}" "pip==25.0.1"
run_gate "$GATE" "$TMP/inst_host" "$TMP/inst_cont"
assert_rc "golden-good-installer (pip skew excluded by name)" 0

# --- golden-bad-version (the literal BOB-154 shape) ------------------------
write_snapshot "$TMP/bad_ver" "#python 3.12.13" "fastapi==0.141.1" "starlette==1.4.1" \
    "uvicorn==0.52.4" "idna==3.19" "filelock==3.32.3"
run_gate "$GATE" "$TMP/bad_ver" "$TMP/prod"
assert_rc "golden-bad-version (starlette 1.4.1 vs 1.6.0 — must FAIL)" 1
assert_out_matches "golden-bad-version names the offending package + both versions" "starlette: venv has 1\.4\.1, container runs 1\.6\.0"

# --- golden-bad-interpreter (no pin can reach this) ------------------------
write_snapshot "$TMP/bad_py" "#python 3.14.6" "fastapi==0.141.1" "starlette==1.6.0" \
    "uvicorn==0.52.4" "idna==3.19" "filelock==3.32.3"
run_gate "$GATE" "$TMP/bad_py" "$TMP/prod"
assert_rc "golden-bad-interpreter (CPython 3.14 vs 3.12 — must FAIL)" 1
assert_out_matches "golden-bad-interpreter names both interpreter versions" "CPython 3\.14\.6.*CPython 3\.12\.13"

# --- golden-bad-absent -----------------------------------------------------
write_snapshot "$TMP/bad_absent" "#python 3.12.13" "fastapi==0.141.1" "uvicorn==0.52.4" \
    "idna==3.19" "filelock==3.32.3"
run_gate "$GATE" "$TMP/bad_absent" "$TMP/prod"
assert_rc "golden-bad-absent (prod dep missing from venv — must FAIL)" 1
assert_out_matches "golden-bad-absent says the tests cannot exercise it" "ABSENT from the host venv"

# --- golden-bad-empty (false-null guard) -----------------------------------
: > "$TMP/empty"
run_gate "$GATE" "$TMP/good_host" "$TMP/empty"
assert_rc "golden-bad-empty (empty container snapshot — must FAIL, not pass)" 1
assert_out_matches "golden-bad-empty calls out the blind probe" "blind probe, not parity"

# --- golden-bad-installer-only (the exclusion is a list, not a hole) -------
write_snapshot "$TMP/bad_mix_host" "#python 3.12.13" "fastapi==0.141.1" "starlette==1.4.1" \
    "uvicorn==0.52.4" "idna==3.19" "filelock==3.32.3" "pip==26.2.1"
write_snapshot "$TMP/bad_mix_cont" "${PROD[@]}" "pip==25.0.1"
run_gate "$GATE" "$TMP/bad_mix_host" "$TMP/bad_mix_cont"
assert_rc "golden-bad-installer-only (pip ignored, real skew still caught)" 1

# ---------------------------------------------------------------------------
# Declaration mechanism. A doctored copy of the gate carries one declaration;
# everything else about it is identical, so these two cases isolate exactly the
# declaration behaviour.
# ---------------------------------------------------------------------------
DECL_GATE="$TMP/gate_declared.sh"
sed 's|^DECLARED_DIVERGENCES=($|DECLARED_DIVERGENCES=(\n    "starlette\|pinned raise pending operator sequencing\|BOB-154"|' \
    "$GATE" > "$DECL_GATE"
grep -q 'pinned raise pending' "$DECL_GATE" || {
    echo "  FAIL  harness could not inject a declaration into the gate copy"; fails=$((fails + 1)); }

run_gate "$DECL_GATE" "$TMP/bad_ver" "$TMP/prod"
assert_rc "declared-tolerated (declared starlette skew must NOT fail)" 0
assert_out_matches "declared-tolerated reports the declaration loudly" "DECLARED:"

run_gate "$DECL_GATE" "$TMP/good_host" "$TMP/prod"
assert_rc "declared-stale (declaration excusing nothing must FAIL)" 1
assert_out_matches "declared-stale explains the ratchet" "stale declaration"

# ---------------------------------------------------------------------------
# Honest SKIP: no such container. Uses the real probe path (no injection), so
# it exercises the actual runtime/container detection the gate ships with.
# ---------------------------------------------------------------------------
SKIP_RC=0
SKIP_OUT="$(PROXY_CONTAINER="cm-parity-no-such-container-$$" bash "$GATE" 2>&1)" || SKIP_RC=$?
if [[ "$SKIP_RC" -eq 0 ]] && grep -q '^SKIP(' <<< "$(tail -n1 <<< "$SKIP_OUT")"; then
    echo "  PASS  skip-no-container (absent container SKIPs honestly, rc 0)"
else
    echo "  FAIL  skip-no-container (rc=$SKIP_RC, last line: $(tail -n1 <<< "$SKIP_OUT"))"
    fails=$((fails + 1))
fi
if grep -q 'not running' <<< "$SKIP_OUT"; then
    echo "  PASS  skip-no-container states the reason (never a silent skip)"
else
    echo "  FAIL  skip-no-container did not state a reason"
    fails=$((fails + 1))
fi

# ---------------------------------------------------------------------------
# §1.1 MUTATION — blind the comparator. Against golden-good the unmutated gate
# PASSes. The mutant reports no findings at all, so if the control needle were
# decoration the mutant would PASS too and the gate's silence would be
# worthless. The needle must catch it.
# ---------------------------------------------------------------------------
MUT_GATE="$TMP/gate_blinded.sh"
awk '
    /^compare_snapshots\(\) \{$/ { print; print "    return 0   # MUTATED for paired-mutation test"; inblock=1; next }
    { print }
' "$GATE" > "$MUT_GATE"
grep -q 'MUTATED for paired-mutation test' "$MUT_GATE" || {
    echo "  FAIL  harness could not build the blinded mutant"; fails=$((fails + 1)); }

run_gate "$MUT_GATE" "$TMP/good_host" "$TMP/prod"
assert_rc "MUTATION blinded-comparator (must FAIL a case the real gate PASSes)" 1
assert_out_matches "MUTATION is caught by the control needle, not by luck" "control needle not detected"

# ---------------------------------------------------------------------------
# Real-tree smoke: run against the live stack through the real probe path.
# The rc is deliberately NOT asserted — it is 1 while the venv is still
# unreconciled and 0 once the operator has applied the reconcile step, and
# asserting either would make this harness lie on the other side of that step.
# What IS asserted: the gate ran the comparison it claims to run.
# ---------------------------------------------------------------------------
REAL_RC=0
REAL_OUT="$(bash "$GATE" 2>&1)" || REAL_RC=$?
if [[ "$REAL_RC" -eq 0 || "$REAL_RC" -eq 1 ]]; then
    echo "  PASS  real-tree (gate executed and produced a verdict, rc=$REAL_RC)"
else
    echo "  FAIL  real-tree (unexpected rc=$REAL_RC — expected a verdict, not an error)"
    sed 's/^/          | /' <<< "$REAL_OUT"
    fails=$((fails + 1))
fi
if grep -qE 'control needle: seen|^SKIP\(' <<< "$REAL_OUT"; then
    echo "  PASS  real-tree either proved the comparator seeing, or SKIPped honestly"
else
    echo "  FAIL  real-tree neither proved the needle nor SKIPped"
    sed 's/^/          | /' <<< "$REAL_OUT"
    fails=$((fails + 1))
fi

echo
if [[ $fails -ne 0 ]]; then
    echo "$HARNESS_NAME: FAIL — $fails check(s) diverged from expected outcome" >&2
    exit 1
fi
echo "$HARNESS_NAME: PASS — CM-RUNTIME-DEPS-PARITY honest across 11 fixtures, 1 skip case, 1 paired mutation and the real tree (§11.4.107(10))"
exit 0
