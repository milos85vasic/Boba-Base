#!/usr/bin/env bash
# test_check_cm_killpg_pgid_guard.sh — §1.1 paired-mutation meta-test for
# scripts/pre_build/check_cm_killpg_pgid_guard.sh (CM-KILLPG-PGID-GUARD).
#
# TDD (§11.4.43/§11.4.115): this meta-test is authored BEFORE the gate is
# trusted. It proves the gate is not a bluff by exercising it against six
# hermetic fixtures with KNOWN outcomes, plus a real-tree smoke run:
#
#   golden-good     -> gate MUST exit 0 (properly guarded os.killpg call)
#   golden-good-2   -> gate MUST exit 0 (properly guarded os.killpg call
#                      whose target is a DOTTED-ATTRIBUTE identifier,
#                      `self._pgid` — regression fixture for the
#                      reviewer's Important-2 false-positive finding:
#                      an earlier revision extracted only the bare prefix
#                      `self` and falsely reported this as unguarded)
#   golden-bad-1    -> gate MUST exit 1 (brief-literal shape,
#                      `os.killpg(1, SIGKILL)`, no guard anywhere nearby —
#                      the raw BOB-126 defect shape)
#   golden-bad-2    -> gate MUST exit 1 (guard checks `> 0`, not `> 1` — a
#                      pgid of 1 still slips through: `killpg(1, sig)` ==
#                      `kill(-1, sig)`, the exact defect class BOB-126 fixed)
#   golden-bad-3    -> gate MUST exit 1 (regression fixture for the
#                      reviewer's Critical-1 finding: a literal,
#                      identifier-less target `os.killpg(1, ...)` sitting
#                      near an UNRELATED `isinstance(x, int) and x > 1`
#                      guard for a completely different variable. An
#                      earlier revision fell back to an unscoped window
#                      scan when no identifier could be extracted, so this
#                      unrelated guard falsely "guarded" the literal
#                      broadcast-kill target — the exact BOB-126 defect
#                      shape slipping past the gate. A gate with NO
#                      non-identifier-scoped fallback (identifier-less =
#                      always unguarded) correctly FAILs this fixture.)
#   real-tree       -> gate MUST exit 0 against the actual boba checkout
#                      (download-proxy/src/merge_service/search.py already
#                      carries the BOB-126 guard at both call sites)
#
# A gate that PASSes golden-bad-1/2/3, or FAILs golden-good/golden-good-2/
# real-tree, is itself the bluff (§11.4.107(10)) and this harness reports
# it.
#
# Exit codes:
#   0 — every fixture (+ the real-tree smoke check) matched its expected
#       outcome (the gate is honest).
#   1 — one or more checks diverged from the expected outcome.
#   2 — harness/environment error (gate script missing or not executable).
#
# Cross-refs: §11.4.1 §11.4.4 §11.4.6 §11.4.43 §11.4.69 §11.4.107(10)
#             §11.4.108 §11.4.115 §11.4.135 §11.4.201.

set -euo pipefail

HARNESS_NAME="test_check_cm_killpg_pgid_guard"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

GATE="$REPO_ROOT/scripts/pre_build/check_cm_killpg_pgid_guard.sh"

if [[ ! -f "$GATE" ]]; then
  echo "FAIL($HARNESS_NAME): gate script not found at $GATE" >&2
  echo "  (expected — this meta-test is authored RED-first per §11.4.115;" >&2
  echo "   implement scripts/pre_build/check_cm_killpg_pgid_guard.sh next)" >&2
  exit 2
fi
if [[ ! -x "$GATE" ]]; then
  echo "FAIL($HARNESS_NAME): gate script not executable at $GATE" >&2
  exit 2
fi

TMPDIR_ROOT="$(mktemp -d -t killpg_guard_meta.XXXXXX)"
trap 'rm -rf "$TMPDIR_ROOT"' EXIT

fails=0

run_gate() {
  # $1 = target path (file or dir). Captures stdout/stderr, returns rc via
  # global GOT_RC/GOT_OUT/GOT_ERR (avoids a $(...) exit-status trap under
  # `set -e` — command substitution of a nonzero-exit command would abort
  # this harness before the assertion runs).
  local target="$1"
  local out err rc
  out="$(mktemp -p "$TMPDIR_ROOT")"
  err="$(mktemp -p "$TMPDIR_ROOT")"
  set +e
  "$GATE" "$target" >"$out" 2>"$err"
  rc=$?
  set -e
  GOT_RC="$rc"
  GOT_OUT="$out"
  GOT_ERR="$err"
}

assert_rc() {
  # $1 = case name, $2 = expected rc
  local name="$1" want_rc="$2"
  if [[ "$GOT_RC" -eq "$want_rc" ]]; then
    echo "PASS: $name (rc=$GOT_RC as expected)"
  else
    echo "FAIL: $name — expected rc=$want_rc got rc=$GOT_RC"
    echo "  --- stdout ---"; sed 's/^/    /' "$GOT_OUT"
    echo "  --- stderr ---"; sed 's/^/    /' "$GOT_ERR"
    fails=$((fails + 1))
  fi
}

# ------------------------------------------------------------------------
# Fixture 1 (golden-good): os.killpg call IS guarded — isinstance(..., int)
# AND `> 1` on the SAME identifier (`_pgid`) within the preceding 10 lines,
# mirroring the real BOB-126 fix shape in search.py:1209-1213.
# ------------------------------------------------------------------------
GOOD_FIXTURE="$TMPDIR_ROOT/golden_good.py"
cat > "$GOOD_FIXTURE" <<'PYEOF'
import contextlib
import os
import signal as _signal


async def _cleanup(proc):
    if proc.returncode is None:
        with contextlib.suppress(Exception):
            proc.kill()
        _pid = proc.pid
        if isinstance(_pid, int) and _pid > 1:
            with contextlib.suppress(Exception):
                _pgid = os.getpgid(_pid)
                if isinstance(_pgid, int) and _pgid > 1:
                    os.killpg(_pgid, _signal.SIGKILL)
PYEOF
run_gate "$GOOD_FIXTURE"
assert_rc "golden-good (guarded os.killpg)" 0

# ------------------------------------------------------------------------
# Fixture 1b (golden-good-2): os.killpg call IS guarded, but the target
# identifier is a DOTTED-ATTRIBUTE chain (`self._pgid`) rather than a
# bare name — regression fixture for the reviewer's Important-2 finding
# (an earlier revision's identifier regex stopped at the `.` and captured
# only `self`, so this correctly-guarded call was falsely flagged as
# unguarded).
# ------------------------------------------------------------------------
GOOD2_FIXTURE="$TMPDIR_ROOT/golden_good_2.py"
cat > "$GOOD2_FIXTURE" <<'PYEOF'
import contextlib
import os
import signal as _signal


class Runner:
    async def cleanup(self, proc):
        if proc.returncode is None:
            with contextlib.suppress(Exception):
                proc.kill()
            self._pgid = os.getpgid(proc.pid)
            if isinstance(self._pgid, int) and self._pgid > 1:
                os.killpg(self._pgid, _signal.SIGKILL)
PYEOF
run_gate "$GOOD2_FIXTURE"
assert_rc "golden-good-2 (guarded os.killpg, dotted-attribute identifier)" 0

# ------------------------------------------------------------------------
# Fixture 2 (golden-bad-1): os.killpg call with NO guard at all, using the
# brief's exact literal shape `os.killpg(1, SIGKILL)` — this is the raw
# BOB-126 defect shape itself: `killpg(1, sig)` == `kill(-1, sig)`
# (broadcast-kill of every process the caller's UID owns).
# ------------------------------------------------------------------------
BAD1_FIXTURE="$TMPDIR_ROOT/golden_bad_1.py"
cat > "$BAD1_FIXTURE" <<'PYEOF'
import os
from signal import SIGKILL


def _cleanup(proc):
    os.killpg(1, SIGKILL)
PYEOF
run_gate "$BAD1_FIXTURE"
assert_rc "golden-bad-1 (no guard at all, brief-literal os.killpg(1, SIGKILL))" 1

# ------------------------------------------------------------------------
# Fixture 3 (golden-bad-2): guard present but checks `> 0` instead of
# `> 1` — a pgid of 1 (the exact MagicMock.__int__ default that caused
# BOB-116/120/123/124/125/126) still slips through this weaker guard.
# ------------------------------------------------------------------------
BAD2_FIXTURE="$TMPDIR_ROOT/golden_bad_2.py"
cat > "$BAD2_FIXTURE" <<'PYEOF'
import contextlib
import os
import signal as _signal


async def _cleanup(proc):
    if proc.returncode is None:
        with contextlib.suppress(Exception):
            proc.kill()
        _pid = proc.pid
        if isinstance(_pid, int) and _pid > 1:
            with contextlib.suppress(Exception):
                _pgid = os.getpgid(_pid)
                if isinstance(_pgid, int) and _pgid > 0:
                    os.killpg(_pgid, _signal.SIGKILL)
PYEOF
run_gate "$BAD2_FIXTURE"
assert_rc "golden-bad-2 (guard uses > 0, not > 1 — pgid=1 slips through)" 1

# ------------------------------------------------------------------------
# Fixture 4 (golden-bad-3): CRITICAL regression fixture. A literal,
# identifier-less target — `os.killpg(1, ...)`, the raw BOB-126 defect
# shape — sitting within the 10-line window of a completely UNRELATED
# `isinstance(x, int) and x > 1` guard that guards a different variable
# (`retry_count`) in an unrelated function. An earlier revision of the
# gate fell back to a non-identifier-scoped window scan whenever no
# identifier could be extracted from the call, so this unrelated guard
# text falsely "guarded" the literal broadcast-kill target — a
# false-negative PASS-bluff on the exact defect class this gate exists
# to catch (reviewer-reproduced live against the tree checkout). The
# fixed gate has NO such fallback: an identifier-less target is ALWAYS
# unguarded, so this fixture MUST FAIL regardless of nearby text.
# ------------------------------------------------------------------------
BAD3_FIXTURE="$TMPDIR_ROOT/golden_bad_3.py"
cat > "$BAD3_FIXTURE" <<'PYEOF'
import os
import signal as _signal


def _other_check(retry_count):
    if isinstance(retry_count, int) and retry_count > 1:
        pass


def _cleanup():
    os.killpg(1, _signal.SIGKILL)
PYEOF
run_gate "$BAD3_FIXTURE"
assert_rc "golden-bad-3 (literal target near UNRELATED int guard — must still FAIL)" 1

# ------------------------------------------------------------------------
# Real-tree smoke check (acceptance criterion 1): the gate MUST pass its
# own default in-repo scope (download-proxy/src, plugins, scripts) against
# the CURRENT boba checkout, whose BOB-126 fix already guards both real
# call sites in search.py.
# ------------------------------------------------------------------------
out="$(mktemp -p "$TMPDIR_ROOT")"
err="$(mktemp -p "$TMPDIR_ROOT")"
set +e
"$GATE" >"$out" 2>"$err"
rc=$?
set -e
GOT_RC="$rc"; GOT_OUT="$out"; GOT_ERR="$err"
assert_rc "real-tree default scope (BOB-126 fix already guards search.py)" 0

echo
if [[ $fails -ne 0 ]]; then
  echo "$HARNESS_NAME: FAIL — $fails check(s) diverged from expected outcome" >&2
  exit 1
fi
echo "$HARNESS_NAME: PASS — CM-KILLPG-PGID-GUARD honest across 5 fixtures + real tree (§11.4.107(10))"
exit 0
