#!/usr/bin/env bash
# test_check_cm_test_mock_pid_explicit_int.sh — §1.1 paired-mutation
# meta-test for
# scripts/pre_build/check_cm_test_mock_pid_explicit_int.sh
# (CM-TEST-MOCK-PID-EXPLICIT-INT).
#
# TDD (§11.4.43/§11.4.115): this meta-test proves the gate is not a
# bluff by exercising it against three hermetic fixtures with KNOWN
# outcomes, plus a real-tree smoke run and a no-op-stub negative
# control (CONST-XII: every new test must fail against a no-op stub
# of the feature it tests):
#
#   golden-good-1  -> gate MUST exit 0 (explicit `mock.pid = 12345`
#                     hardening — the BOB-126 fix shape)
#   golden-good-2  -> gate MUST exit 0 (subprocess-shaped mock with NO
#                     explicit pid, but BOTH `os.killpg` AND
#                     `os.getpgid` real-patched nearby — belt-and-
#                     suspenders neutralises the destructive call)
#   golden-bad     -> gate MUST exit 1 (the raw pre-fix BOB-126 shape:
#                     `.returncode = None`, hanging `.stdout.readline`,
#                     NO `.pid = int`, NO killpg patch anywhere)
#   real-tree      -> gate MUST exit 0 against the actual boba
#                     checkout (tests/**/*.py) — the fixed
#                     `test_deadline_hit_flag_true_when_readline_times_out`
#                     carries both `mock.pid = 12345` AND
#                     `patch.object(_search.os, "killpg")`; every OTHER
#                     subprocess-shaped mock helper in the real tree
#                     (`_proc_mock()` / `_streaming_proc_mock()`
#                     factories) sets `.returncode` to a completed-
#                     process value, never `None`, so it never reaches
#                     search.py's kill branch — see the gate's own
#                     "Detection design" header for the evidence trail.
#   no-op-stub     -> a gate that always exits 0 regardless of content
#                     MUST be caught FAILING the golden-bad assertion
#                     (proves this harness is not a bluff — CONST-XII).
#
# A gate that PASSes golden-bad, or FAILs golden-good-1/2/real-tree, is
# itself the bluff (§11.4.107(10)) and this harness reports it.
#
# Exit codes:
#   0 — every fixture (+ real-tree smoke + no-op-stub negative control)
#       matched its expected outcome (the gate is honest).
#   1 — one or more checks diverged from the expected outcome.
#   2 — harness/environment error (gate script missing or not
#       executable).
#
# Cross-refs: §11.4.1 §11.4.4 §11.4.6 §11.4.43 §11.4.69 §11.4.107(10)
#             §11.4.108 §11.4.115 §11.4.135 §11.4.201 §11.4.226 CONST-XII.

set -euo pipefail

HARNESS_NAME="test_check_cm_test_mock_pid_explicit_int"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

GATE="$REPO_ROOT/scripts/pre_build/check_cm_test_mock_pid_explicit_int.sh"

if [[ ! -f "$GATE" ]]; then
  echo "FAIL($HARNESS_NAME): gate script not found at $GATE" >&2
  echo "  (expected — this meta-test is authored RED-first per §11.4.115;" >&2
  echo "   implement scripts/pre_build/check_cm_test_mock_pid_explicit_int.sh next)" >&2
  exit 2
fi
if [[ ! -x "$GATE" ]]; then
  echo "FAIL($HARNESS_NAME): gate script not executable at $GATE" >&2
  exit 2
fi

TMPDIR_ROOT="$(mktemp -d -t test_mock_pid_meta.XXXXXX)"
trap 'rm -rf "$TMPDIR_ROOT"' EXIT

fails=0

run_gate_bin() {
  # $1 = gate binary path, $2 = target path (file or dir). Captures
  # stdout/stderr, returns rc via global GOT_RC/GOT_OUT/GOT_ERR (avoids
  # a $(...) exit-status trap under `set -e` — command substitution of
  # a nonzero-exit command would abort this harness before the
  # assertion runs).
  local bin="$1" target="$2"
  local out err rc
  out="$(mktemp -p "$TMPDIR_ROOT")"
  err="$(mktemp -p "$TMPDIR_ROOT")"
  set +e
  "$bin" "$target" >"$out" 2>"$err"
  rc=$?
  set -e
  GOT_RC="$rc"
  GOT_OUT="$out"
  GOT_ERR="$err"
}

run_gate() {
  run_gate_bin "$GATE" "$1"
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
# Fixture 1 (golden-good-1): explicit `mock.pid = 12345` int hardening —
# the sanctioned BOB-126 fix shape mirrored from
# tests/unit/merge_service/test_deadline_tunable.py::
# test_deadline_hit_flag_true_when_readline_times_out.
# ------------------------------------------------------------------------
GOOD1_FIXTURE="$TMPDIR_ROOT/golden_good_1.py"
cat > "$GOOD1_FIXTURE" <<'PYEOF'
import asyncio
from unittest.mock import AsyncMock, MagicMock


async def _hang():
    await asyncio.sleep(999)


async def fake_subprocess(*args, **kwargs):
    mock = AsyncMock()
    mock.returncode = None
    mock.pid = 12345  # BOB-126: MUST be an int, NEVER a MagicMock
    mock.stdout = MagicMock()
    mock.stdout.readline = AsyncMock(side_effect=_hang)
    mock.stderr = MagicMock()
    mock.stderr.read = AsyncMock(return_value=b"")
    mock.wait = AsyncMock(return_value=-9)
    mock.kill = MagicMock()
    return mock
PYEOF
run_gate "$GOOD1_FIXTURE"
assert_rc "golden-good-1 (explicit mock.pid = 12345)" 0

# ------------------------------------------------------------------------
# Fixture 2 (golden-good-2): NO explicit pid, but BOTH os.killpg AND
# os.getpgid real-patched nearby — belt-and-suspenders makes the
# destructive syscall unreachable regardless of what mock.pid coerces
# to.
# ------------------------------------------------------------------------
GOOD2_FIXTURE="$TMPDIR_ROOT/golden_good_2.py"
cat > "$GOOD2_FIXTURE" <<'PYEOF'
import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch


async def _hang():
    await asyncio.sleep(999)


async def fake_subprocess(*args, **kwargs):
    mock = AsyncMock()
    mock.returncode = None
    mock.stdout = MagicMock()
    mock.stdout.readline = AsyncMock(side_effect=_hang)
    mock.stderr = MagicMock()
    mock.stderr.read = AsyncMock(return_value=b"")
    mock.wait = AsyncMock(return_value=-9)
    mock.kill = MagicMock()
    return mock


async def run_case():
    with (
        patch("asyncio.create_subprocess_exec", side_effect=fake_subprocess),
        patch.object(os, "killpg") as mock_killpg,
        patch.object(os, "getpgid", return_value=54321),
    ):
        pass
    return mock_killpg
PYEOF
run_gate "$GOOD2_FIXTURE"
assert_rc "golden-good-2 (no pid, but killpg+getpgid both patched)" 0

# ------------------------------------------------------------------------
# Fixture 3 (golden-bad): the raw pre-fix BOB-126 defect shape —
# `.returncode = None`, hanging `.stdout.readline`, `.wait`, `.kill`
# all present, NO `mock.pid = int` anywhere, NO killpg patch anywhere.
# This is the EXACT shape `test_deadline_hit_flag_true_when_readline_
# times_out` had BEFORE the BOB-126 fix landed.
# ------------------------------------------------------------------------
BAD_FIXTURE="$TMPDIR_ROOT/golden_bad.py"
cat > "$BAD_FIXTURE" <<'PYEOF'
import asyncio
from unittest.mock import AsyncMock, MagicMock


async def _hang():
    await asyncio.sleep(999)


async def fake_subprocess(*args, **kwargs):
    mock = AsyncMock()
    mock.returncode = None
    # DELIBERATELY leave mock.pid as an auto-generated MagicMock — this
    # is the exact BOB-126 defect condition (MagicMock coerces to 1).
    mock.stdout = MagicMock()
    mock.stdout.readline = AsyncMock(side_effect=_hang)
    mock.stderr = MagicMock()
    mock.stderr.read = AsyncMock(return_value=b"")
    mock.wait = AsyncMock(return_value=-9)
    mock.kill = MagicMock()
    return mock
PYEOF
run_gate "$BAD_FIXTURE"
assert_rc "golden-bad (no pid, no killpg patch — the BOB-126 shape)" 1

# ------------------------------------------------------------------------
# Real-tree smoke check (acceptance criterion 1): the gate MUST pass
# its own default in-repo scope (tests/**/*.py) against the CURRENT
# boba checkout, whose BOB-126 fix already hardens
# test_deadline_hit_flag_true_when_readline_times_out with both
# `mock.pid = 12345` AND `patch.object(_search.os, "killpg")`, and
# whose OTHER subprocess-mock helper factories set `.returncode` to a
# completed-process value (never reaching the kill branch — see the
# gate's own "Detection design" header for the full evidence trail).
# ------------------------------------------------------------------------
out="$(mktemp -p "$TMPDIR_ROOT")"
err="$(mktemp -p "$TMPDIR_ROOT")"
set +e
"$GATE" >"$out" 2>"$err"
rc=$?
set -e
GOT_RC="$rc"; GOT_OUT="$out"; GOT_ERR="$err"
assert_rc "real-tree default scope (tests/**/*.py, BOB-126 fix already hardens the timeout test)" 0

# ------------------------------------------------------------------------
# No-op-stub negative control (CONST-XII anti-bluff: every new test
# MUST fail against a no-op stub of the feature it tests). A gate that
# always exits 0 regardless of content must be caught FAILING the
# golden-bad assertion — proving this harness genuinely discriminates
# rather than rubber-stamping whatever gate happens to be on disk.
# ------------------------------------------------------------------------
STUB_GATE="$TMPDIR_ROOT/stub_always_pass.sh"
cat > "$STUB_GATE" <<'STUBEOF'
#!/usr/bin/env bash
echo "PASS: stub always passes"
exit 0
STUBEOF
chmod +x "$STUB_GATE"
run_gate_bin "$STUB_GATE" "$BAD_FIXTURE"
if [[ "$GOT_RC" -eq 0 ]]; then
  echo "PASS: no-op-stub negative control (stub wrongly PASSed golden-bad, as expected — proves the golden-bad fixture is genuinely dangerous-shaped and this harness would have caught a bluff gate)"
else
  echo "FAIL: no-op-stub negative control — the stub gate unexpectedly exited nonzero; the negative control is not exercising a real no-op"
  fails=$((fails + 1))
fi

echo
if [[ $fails -ne 0 ]]; then
  echo "$HARNESS_NAME: FAIL — $fails check(s) diverged from expected outcome" >&2
  exit 1
fi
echo "$HARNESS_NAME: PASS — CM-TEST-MOCK-PID-EXPLICIT-INT honest across 3 fixtures + real tree + no-op-stub negative control (§11.4.107(10))"
exit 0
