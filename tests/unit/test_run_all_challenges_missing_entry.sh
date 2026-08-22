#!/usr/bin/env bash
# test_run_all_challenges_missing_entry.sh — a listed-but-absent challenge MUST
# participate in the exit code of scripts/run_all_challenges.sh (BOB-168).
#
# Forensic anchor (measured 2026-08-22, this repo, real runner byte-identical):
#   The aggregator's exit code read ONLY the FAIL count. Run where the
#   `submodules/challenges` submodule is not checked out — the ordinary state
#   of a `git clone` WITHOUT `--recursive` — the real runner printed
#     PASS: 0   FAIL: 0   SKIP: 16   TOTAL: 16
#   and exited 0. Sixteen challenges were named, ZERO executed, and the caller
#   was told everything was fine. A blind instrument and a clean artifact
#   returned the identical quiet zero — §11.4.201(6) FALSE-NULL verbatim, and
#   the §11.4.135 principle (ABSENCE blocks exactly as a FAIL does) simply not
#   applied at this seam.
#
#   NOTE the roster itself was NOT dangling: all 15 entries + the meta-runner
#   exist and are executable in the submodule. The defect is the exit semantics,
#   not a missing file. See docs/qa/BOB-168/decision_missing_vs_skip.md.
#
# The decision under test (recorded, not patched in): an absent-or-unrunnable
# entry is a ROSTER-INTEGRITY failure, counted as MISSING — a bucket distinct
# from §11.4.3 topology SKIP — and exits 2 (this script's own existing idiom for
# "the environment is not set up to run this"; cf. its BOBA_DURABLE branch).
#
# §11.4.224 RED-first: against the pre-fix runner, cases 1 and 3 FAIL (observed
# exit 0, no MISSING bucket). Case 2 is the §11.4.201(1) negative control and
# passes both before and after — a fix that makes the runner red always is not
# a fix.
#
# §11.4.201(11) anti-replica: the fixture copies the REAL script and asserts
# byte-identity by sha256 before running it, so this can never decay into
# testing a hand-built lookalike of the loop.

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${HERE}/../.." && pwd)"
RUNNER="${PROJECT_ROOT}/scripts/run_all_challenges.sh"

PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); echo "  PASS: $1"; }
fail() { FAIL=$((FAIL+1)); echo "  FAIL: $1"; }
finish(){ echo "RESULT: $PASS passed, $FAIL failed"; [ "$FAIL" -eq 0 ] || exit 1; exit 0; }

[[ -f "$RUNNER" ]] || { fail "runner missing: scripts/run_all_challenges.sh"; finish; }

# The 15 entries the runner lists, plus its meta-runner. Kept in sync with the
# roster by case 4 below, so this fixture cannot silently drift from the runner.
ENTRIES=(
  no_suspend_calls_challenge.sh host_no_auto_suspend_challenge.sh
  bluff_scanner_challenge.sh anchor_manifest_challenge.sh
  challenges_compile_challenge.sh challenges_functionality_challenge.sh
  challenges_unit_challenge.sh chaos_failure_injection_challenge.sh
  ddos_health_flood_challenge.sh mutation_ratchet_challenge.sh
  recording_pipeline_challenge.sh scaling_horizontal_challenge.sh
  stress_sustained_load_challenge.sh ui_terminal_interaction_challenge.sh
  ux_end_to_end_flow_challenge.sh
)

FIX="$(mktemp -d)"
trap 'rm -rf "$FIX"' EXIT

# Build a fixture root that mirrors the real repo layout, with the REAL runner.
# $1 = fixture name; echoes the fixture root.
make_root() {
  local root="${FIX}/$1"
  mkdir -p "${root}/scripts"
  cp "$RUNNER" "${root}/scripts/run_all_challenges.sh"
  local a b
  a="$(sha256sum "$RUNNER" | cut -d' ' -f1)"
  b="$(sha256sum "${root}/scripts/run_all_challenges.sh" | cut -d' ' -f1)"
  [[ "$a" == "$b" ]] || { echo "ANTI-REPLICA CHECK FAILED — fixture diverged from the real runner" >&2; exit 1; }
  echo "$root"
}

# Populate every listed entry as a trivially-passing stub (nothing heavy ever
# runs in this suite — §12.6 / the 30-40% host cap).
populate_all() {
  # B-1 fail-closed: an empty root would mkdir -p at FILESYSTEM ROOT.
  [[ -n "${1:-}" && -d "${1}/scripts" ]] || return 1
  local root="$1" dir="$1/submodules/challenges/challenges/scripts"
  mkdir -p "$dir"
  local e
  for e in "${ENTRIES[@]}"; do
    printf '#!/usr/bin/env bash\nexit 0\n' > "${dir}/${e}"
    chmod 755 "${dir}/${e}"
  done
  printf '#!/usr/bin/env bash\nexit 0\n' > "${root}/submodules/challenges/challenges_describe_challenge.sh"
  chmod 755 "${root}/submodules/challenges/challenges_describe_challenge.sh"
}

run_runner() {  # $1 = root; sets OUT and RC
  # B-1 FAIL CLOSED (§11.4.252). make_root runs in a command substitution, so its
  # `exit 1` — the anti-replica trip, or any mktemp/mkdir/cp failure — kills only
  # the subshell; this script is `set -uo pipefail` WITHOUT -e, so execution
  # continues with root="". Measured on bash 5.2.37: `cd ""` SUCCEEDS as a no-op,
  # so an unguarded `cd "$1" && bash scripts/run_all_challenges.sh` would run
  # relative to the INVOKER's cwd — from the project root, that is the REAL
  # aggregator with the real submodule, firing ddos_health_flood,
  # stress_sustained_load and chaos_failure_injection against the 30-40% host cap.
  # The guard's designed-FOR failure must never detonate its designed-AGAINST
  # outcome, so a bad root is a loud assertion failure with NOTHING executed.
  if [[ -z "${1:-}" || ! -f "${1}/scripts/run_all_challenges.sh" ]]; then
    OUT="fixture setup failed for root='${1:-}' — runner NOT executed"
    RC=97
    return
  fi
  OUT="$(cd "$1" && nice -n 19 ionice -c 3 env GOMAXPROCS=2 bash scripts/run_all_challenges.sh 2>&1)"
  RC=$?
}

# ---- Case 1: EVERY entry absent (a clone without --recursive). The bank
# attested nothing, so the runner MUST NOT report success.
R="$(make_root case1)"
run_runner "$R"
if [[ "$RC" -eq 2 ]]; then
  pass "all entries absent -> exit 2 (bank could not be run)"
else
  fail "all entries absent -> expected exit 2, got $RC (pre-fix behaviour: 0)"
fi
if grep -q 'MISSING: 16' <<<"$OUT"; then
  pass "all entries absent -> MISSING: 16 counted separately from SKIP"
else
  fail "all entries absent -> expected 'MISSING: 16' in summary; got:
$(grep -E '^(PASS|FAIL|SKIP|MISSING|TOTAL):' <<<"$OUT" | sed 's/^/      /')"
fi

# ---- Case 2: NEGATIVE CONTROL (§11.4.201(1)). Every listed entry EXISTS and
# passes. A correct runner must still exit 0. A fix that reddens a healthy
# roster is not a fix.
R="$(make_root case2)"; populate_all "$R" || fail "case2 fixture setup failed"
run_runner "$R"
if [[ "$RC" -eq 0 ]]; then
  pass "NEGATIVE CONTROL: complete roster, all passing -> exit 0"
else
  fail "NEGATIVE CONTROL: complete roster -> expected exit 0, got $RC (runner reddens a healthy bank)"
fi
if grep -q 'MISSING: 0' <<<"$OUT"; then
  pass "NEGATIVE CONTROL: complete roster -> MISSING: 0"
else
  fail "NEGATIVE CONTROL: complete roster -> expected 'MISSING: 0'; got:
$(grep -E '^(PASS|FAIL|SKIP|MISSING|TOTAL):' <<<"$OUT" | sed 's/^/      /')"
fi

# ---- Case 3: exactly ONE entry present-but-not-executable. Same roster-
# integrity class as absent: the named entry cannot be run, so it attests
# nothing. One bad entry in an otherwise healthy bank must still block.
R="$(make_root case3)"; populate_all "$R" || fail "case3 fixture setup failed"
chmod 644 "${R}/submodules/challenges/challenges/scripts/scaling_horizontal_challenge.sh"
run_runner "$R"
if [[ "$RC" -eq 2 ]]; then
  pass "one entry not executable -> exit 2"
else
  fail "one entry not executable -> expected exit 2, got $RC"
fi
if grep -q 'MISSING: 1' <<<"$OUT"; then
  pass "one entry not executable -> MISSING: 1"
else
  fail "one entry not executable -> expected 'MISSING: 1'; got:
$(grep -E '^(PASS|FAIL|SKIP|MISSING|TOTAL):' <<<"$OUT" | sed 's/^/      /')"
fi

# ---- Case 4: a genuine FAIL still exits 1, and outranks MISSING. The two
# conditions demand different responses (fix the code vs fix the checkout);
# neither may swallow the other.
R="$(make_root case4)"; populate_all "$R" || fail "case4 fixture setup failed"
printf '#!/usr/bin/env bash\nexit 1\n' > "${R}/submodules/challenges/challenges/scripts/bluff_scanner_challenge.sh"
run_runner "$R"
if [[ "$RC" -eq 1 ]]; then
  pass "a real challenge failure -> exit 1 (unchanged, outranks MISSING)"
else
  fail "a real challenge failure -> expected exit 1, got $RC"
fi

# ---- Case 4b: FAIL and MISSING SIMULTANEOUSLY. Case 4 alone cannot see the
# documented FAIL-outranks-MISSING precedence, because a complete roster never
# populates both counters at once — a reviewer mutation that swapped the two
# exit blocks survived the suite. Without this case a caller would be told
# "fix the checkout" (2) while a real challenge was failing, and would find the
# code defect a cycle late.
R="$(make_root case4b)"; populate_all "$R" || fail "case4b fixture setup failed"
printf '#!/usr/bin/env bash\nexit 1\n' > "${R}/submodules/challenges/challenges/scripts/bluff_scanner_challenge.sh"
rm -f "${R}/submodules/challenges/challenges/scripts/scaling_horizontal_challenge.sh"
run_runner "$R"
if [[ "$RC" -eq 1 ]]; then
  pass "FAIL + MISSING together -> exit 1 (FAIL outranks MISSING)"
else
  fail "FAIL + MISSING together -> expected exit 1, got $RC (precedence inverted?)"
fi
if grep -q 'MISSING: 1' <<<"$OUT"; then
  pass "FAIL + MISSING together -> MISSING: 1 still reported, not swallowed"
else
  fail "FAIL + MISSING together -> expected 'MISSING: 1' in summary; got:
$(grep -E '^(PASS|FAIL|SKIP|MISSING|TOTAL):' <<<"$OUT" | sed 's/^/      /')"
fi

# ---- Case 5: this fixture's roster must match the runner's, or cases 2-4 are
# measuring a stale list and their green means nothing (§11.4.201(7)(b)).
ROSTER_IN_RUNNER="$(sed -n '/^CHALLENGE_SCRIPTS=(/,/^)/p' "$RUNNER" \
  | grep -oE '[a-z0-9_]+_challenge\.sh' | sort)"
ROSTER_IN_TEST="$(printf '%s\n' "${ENTRIES[@]}" | sort)"
if [[ "$ROSTER_IN_RUNNER" == "$ROSTER_IN_TEST" ]]; then
  pass "fixture roster is in sync with the runner's CHALLENGE_SCRIPTS"
else
  fail "fixture roster drifted from the runner's CHALLENGE_SCRIPTS:
$(diff <(echo "$ROSTER_IN_TEST") <(echo "$ROSTER_IN_RUNNER") | sed 's/^/      /')"
fi

finish
