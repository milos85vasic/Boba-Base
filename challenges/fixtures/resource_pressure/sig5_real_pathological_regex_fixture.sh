#!/bin/bash
# sig5_real_pathological_regex_fixture.sh — §11.4.115(F) RED fixture for
# SIG-5 (pathological ugrep -o variable-length-alternation regex pattern in
# a live process cmdline) in resource_pressure_signature_challenge.sh.
#
# The REAL 2026-08-18 incident's SIG-5 instance was a genuine 15 GB `ugrep
# -o` invocation — reproducing that exact memory-hungry workload here would
# itself be the resource-pressure event this suite exists to prevent, and
# would fight this very fixture's own §12.6 host-safety obligations.
#
# SIG-5 detects PURELY by scanning /proc/*/cmdline text — it never executes
# or interprets the matched command. So a process whose RECORDED argv
# genuinely contains the pathological substring IS the artifact the
# detector inspects, regardless of what binary is actually running behind
# a disguised argv[0]. This fixture spawns a bounded, harmless
# `sleep`-backed process whose argv is disguised via bash's `exec -a` to
# carry the SAME literal byte sequence the detector's own regex requires.
#
# IMPORTANT DETAIL discovered while authoring this fixture (kept here so
# the mistake is not silently repeatable): the detector's regex
# (SIG5_PATHOLOGICAL_PATTERN_REGEX in the challenge script) is
#   \bugrep .*-o .*\.\\\{[0-9]+,[0-9]+\\\}.*\\\|
# which — read char-by-char as an ERE fed to `grep -E` — requires a LITERAL
# BACKSLASH byte immediately before the "{", before the "}", and before the
# "|" (i.e. the target cmdline must contain the literal bytes
# `.\{N,M\}...\|`, BRE-style escaping, matching how `ugrep`/`grep` itself
# requires `\{...\}` and `\|` for bounded-repetition/alternation outside
# full ERE mode — NOT bare `{N,M}` / `|`). An earlier draft of this fixture
# disguised the process with BARE braces/pipe (no backslashes) and the
# real, un-mutated challenge correctly did NOT flag it — that was this
# fixture under-constructing its own precondition, not the detector
# under-detecting (§11.4.6: verified before either conclusion was drawn,
# per §11.4.199 exact-reproduction-sequence discipline). To make this
# class of authoring error impossible going forward, this fixture EXTRACTS
# the real regex directly from the challenge script at run time (single
# source of truth) and self-checks its own disguised cmdline against that
# EXACT regex — not a hand-retyped copy — before ever invoking the
# challenge.
#
# Host-safety: the disguised process is a harmless helper (sig5_sleeper_
# helper.sh) that only sleeps (${SIG5_FIXTURE_SLEEP_SEC:-20}s, bounded,
# self-exiting even if this driver's cleanup trap fails to fire),
# consuming no real memory/CPU pressure.
#
# Usage:
#   bash challenges/fixtures/resource_pressure/sig5_real_pathological_regex_fixture.sh
#
# Exit:
#   0 = RED confirmed  1 = RED not reproduced  2 = instrument/precondition SKIP

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
CHALLENGE="$REPO_ROOT/challenges/scripts/resource_pressure_signature_challenge.sh"
SLEEPER="$SCRIPT_DIR/sig5_sleeper_helper.sh"

export SIG5_SLEEP_SECONDS="${SIG5_FIXTURE_SLEEP_SEC:-20}"
DISGUISED_PID=""

cleanup() {
  if [ -n "$DISGUISED_PID" ] && kill -0 "$DISGUISED_PID" 2>/dev/null; then
    kill -TERM "$DISGUISED_PID" 2>/dev/null
    sleep 0.2
    kill -KILL "$DISGUISED_PID" 2>/dev/null
  fi
}
trap cleanup EXIT INT TERM

if [ ! -r "$CHALLENGE" ]; then
  echo "SKIP (§11.4.3): challenge script not found at $CHALLENGE"
  exit 2
fi
if [ ! -r "$SLEEPER" ]; then
  echo "SKIP (§11.4.3): sleeper helper not found at $SLEEPER"
  exit 2
fi

# Single source of truth: extract the REAL regex from the challenge script
# itself rather than hand-retyping it here (the exact class of mistake
# this fixture's header documents above).
REAL_REGEX_LINE=$(grep '^SIG5_PATHOLOGICAL_PATTERN_REGEX=' "$CHALLENGE" || true)
if [ -z "$REAL_REGEX_LINE" ]; then
  echo "SKIP (§11.4.3): could not locate SIG5_PATHOLOGICAL_PATTERN_REGEX assignment in $CHALLENGE"
  exit 2
fi
REAL_REGEX=$(bash -c "$REAL_REGEX_LINE"'; printf "%s" "$SIG5_PATHOLOGICAL_PATTERN_REGEX"')
echo "Extracted detector regex (single source of truth): $REAL_REGEX"

echo "=== SIG-5 real-pathological-regex fixture: spawning argv-disguised process ==="
# exec -a sets argv[0] to "ugrep". The sleeper script itself IGNORES its
# positional args (it only sleeps, per SIG5_SLEEP_SECONDS), but
# /proc/<pid>/cmdline records the FULL argv vector verbatim — including the
# disguise + the pathological-looking tail below. The tail uses REAL
# backslash bytes (BRE-style `.\{0,120\}...\|`) — see the header note.
(
  exec -a ugrep bash "$SLEEPER" -o '.\{0,120\}decoy\|pathological'
) &
DISGUISED_PID=$!

sleep 0.5
if ! kill -0 "$DISGUISED_PID" 2>/dev/null; then
  echo "SKIP (§11.4.3): disguised process exited before verification"
  exit 2
fi

if [ ! -r "/proc/$DISGUISED_PID/cmdline" ]; then
  echo "SKIP (§11.4.3): /proc/$DISGUISED_PID/cmdline unreadable"
  exit 2
fi
CMDLINE_SEEN=$(tr '\0' ' ' < "/proc/$DISGUISED_PID/cmdline" 2>/dev/null || true)
echo "Verified via /proc/$DISGUISED_PID/cmdline: $CMDLINE_SEEN"
if ! echo "$CMDLINE_SEEN" | grep -qE "$REAL_REGEX"; then
  echo "SKIP (§11.4.3): disguised cmdline did not match the detector's OWN (extracted) pattern — fixture construction failed"
  exit 2
fi

echo
echo "=== Running the REAL (un-mutated) challenge against this live disguised process ==="
CHALLENGE_OUT="$(bash "$CHALLENGE" 2>&1)"
CHALLENGE_RC=$?
echo "$CHALLENGE_OUT"
echo
echo "Challenge exit code: $CHALLENGE_RC"

if [ "$CHALLENGE_RC" -eq 1 ] && echo "$CHALLENGE_OUT" | grep -q "SIG-5:"; then
  echo "RED CONFIRMED: challenge correctly FAILed on a live process whose real cmdline matches the pathological pattern, naming SIG-5"
  exit 0
else
  echo "RED NOT REPRODUCED: challenge did not FAIL naming SIG-5 against a live pathological-cmdline process — §11.4.115(F) violation"
  exit 1
fi
