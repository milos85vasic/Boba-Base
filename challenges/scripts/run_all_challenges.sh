#!/usr/bin/env bash
# run_all_challenges.sh — runs every *_challenge.sh script in this dir.
#
# Filters by the `_challenge.sh` suffix so legacy scripts that don't
# match (e.g. jackett_autoconfig_clean_slate.sh which targets the full
# stack) are NOT run by this aggregator. To run the legacy clean-slate
# script, invoke it directly.
#
# COVERAGE GUARD (§11.4.238, added 2026-09-02)
# --------------------------------------------
# A suffix glob silently drops any challenge that does not match it. On
# 2026-09-02 `user1000-watchdog-challenge.sh` (DASHES) was found to have sat
# outside the release gate since it landed — never run, never reported, a
# silent coverage escape that no verdict line could reveal because an
# unmatched file produces no output at all.
#
# The file was renamed to the underscore convention, but a rename alone only
# fixes THIS instance: the next dash- or oddly-named challenge escapes exactly
# the same way. So every *.sh in this directory must now be ACCOUNTED FOR —
# either it matches the glob, or it is explicitly declared below as a
# non-challenge. An unaccounted script is a hard FAIL. Widening the glob was
# rejected: it would swallow the two scripts that are deliberately excluded,
# and it still would not catch a file whose name matches no pattern at all.
#
# Each challenge is given a generous per-script timeout (180s default,
# overridable via CHALLENGE_TIMEOUT env). A timed-out challenge counts
# as a fail.
#
# Exit-status contract (per-challenge):
#     0 = PASS
#    77 = SKIP — an honest, documented not-applicable (e.g. a live backend is
#         unreachable per §11.4.3). Counted as NOT-a-failure, matching this
#         script's long-standing "0 = all PASS / SKIP" promise below. Before
#         2026-09-02 a 77 was scored as a FAIL, so an honest SKIP was reported
#         as a product failure — a §11.4.1 FAIL-bluff.
#   124 = TIMEOUT (counted as a fail)
#     * = FAIL
#
# Exit:
#   0 = all PASS / SKIP
#   1 = one or more FAIL or timeout
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TIMEOUT_S="${CHALLENGE_TIMEOUT:-180}"

# Scripts in this directory that are deliberately NOT aggregator challenges.
# Adding a name here is a visible, reviewable decision; forgetting to add one
# is a hard FAIL (see COVERAGE GUARD above).
NON_CHALLENGE_SCRIPTS=(
  "run_all_challenges.sh"              # this aggregator
  "jackett_autoconfig_clean_slate.sh"  # destructive full-stack; run manually
  "verify_resource_pressure_polarity.sh" # polarity harness for a challenge
)

is_declared_non_challenge() {
  local name="$1" n
  for n in "${NON_CHALLENGE_SCRIPTS[@]}"; do
    [ "$name" = "$n" ] && return 0
  done
  return 1
}

# --- Coverage guard: every *.sh must be accounted for -------------------------
unaccounted=()
for script in "$HERE"/*.sh; do
  [ -e "$script" ] || continue
  name="$(basename "$script")"
  case "$name" in
    *_challenge.sh) continue ;;   # will be run below
  esac
  is_declared_non_challenge "$name" || unaccounted+=("$name")
done

if [ "${#unaccounted[@]}" -gt 0 ]; then
  echo "================================================================"
  echo "FAIL: ${#unaccounted[@]} script(s) in challenges/scripts/ are neither"
  echo "      matched by the *_challenge.sh glob nor declared as a"
  echo "      non-challenge — they would run in NO gate at all:"
  for u in "${unaccounted[@]}"; do echo "  - $u"; done
  echo
  echo "Either rename it to *_challenge.sh, or add it to"
  echo "NON_CHALLENGE_SCRIPTS in this script with a reason."
  echo "================================================================"
  exit 1
fi

fails=0
skips=0
passes=0
total=0
failed_names=()
for script in "$HERE"/*_challenge.sh; do
  [ -e "$script" ] || continue
  name="$(basename "$script")"
  total=$((total + 1))
  echo "================================================================"
  echo "=== $name (timeout ${TIMEOUT_S}s)"
  echo "================================================================"
  # Run FIRST, capture $? on its own line. The previous form was
  # `if ! timeout ...; then rc=$?` — after `!` the shell has already
  # replaced the status with the negated result, so $? was ALWAYS 0 and
  # every failure printed "(exit 0)". The reported code was a lie
  # (§11.4.201(12)-class shell-instrument footgun).
  timeout "$TIMEOUT_S" bash "$script"
  rc=$?
  case "$rc" in
    0)
      passes=$((passes + 1))
      ;;
    77)
      echo "SKIP: $name (exit 77 — honest not-applicable)"
      skips=$((skips + 1))
      ;;
    124)
      echo "TIMEOUT: $name (exceeded ${TIMEOUT_S}s)"
      fails=$((fails + 1))
      failed_names+=("$name (timeout)")
      ;;
    *)
      echo "FAIL: $name (exit $rc)"
      fails=$((fails + 1))
      failed_names+=("$name (exit $rc)")
      ;;
  esac
done
echo "================================================================"
echo "Challenges total: $total | passed: $passes | skipped: $skips | failed: $fails"
if [ "$fails" -gt 0 ]; then
  echo "Failed:"
  for f in "${failed_names[@]}"; do echo "  - $f"; done
fi
echo "================================================================"
[ "$fails" -eq 0 ] && exit 0
exit 1
