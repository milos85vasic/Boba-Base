#!/usr/bin/env bash
# test_check_cm_test_mock_pid_patched_when_real_pid.sh — §1.1 paired-
# mutation meta-test for
# scripts/pre_build/check_cm_test_mock_pid_patched_when_real_pid.sh
# (CM-TEST-MOCK-PID-PATCHED-WHEN-REAL-PID).
#
# TDD (§11.4.43/§11.4.115): this meta-test proves the gate is not a
# bluff by exercising it against five hermetic fixtures with KNOWN
# outcomes, plus a real-tree smoke run and a no-op-stub negative
# control (CONST-XII: every new test must fail against a no-op stub of
# the feature it tests):
#
#   golden-good-1  -> gate MUST exit 0 (`.pid = 12345` + a
#                     `patch.object(<mod>.os, "killpg")` object-form
#                     patch — the sanctioned BOB-127 fix pattern,
#                     mirrored from
#                     test_process_group_kill_called_on_deadline)
#   golden-good-2  -> gate MUST exit 0 (`.pid = 12345` + a bare
#                     `patch("os.killpg")` string-literal-form patch —
#                     the alternate sanctioned pattern used throughout
#                     test_search_deep_coverage.py)
#   golden-bad-1   -> gate MUST exit 1 (`.pid = 12345`, NO killpg patch
#                     anywhere — the raw pre-fix BOB-127 defect shape:
#                     test_stuck_subprocess_killed_and_abandoned before
#                     commit 8bedc5a)
#   golden-bad-2   -> gate MUST exit 1 (`.pid = 1111` — a SMALL pid with
#                     materially higher real-world PID-reuse collision
#                     probability — NO killpg patch anywhere; proves
#                     detection is NOT hardcoded to the literal 12345)
#   false-positive-guard
#                  -> gate MUST exit 1 (`.pid = 12345` +
#                     `patch("some_other_module.killpg")` — a patch
#                     that mentions the string "killpg" but targets a
#                     COMPLETELY UNRELATED module, not `os.killpg`. The
#                     sibling gate CM-TEST-MOCK-PID-EXPLICIT-INT's
#                     looser any-module exemption would wrongly accept
#                     this; THIS gate's exemption is narrower and MUST
#                     still flag it — §11.4.201 false-positive-refusal
#                     discipline: an exemption broad enough to accept
#                     an irrelevant patch is itself a bluff)
#   real-tree      -> gate MUST exit 0 against the actual boba
#                     checkout (tests/**/*.py) — all 5 real-pid
#                     reachable-kill-branch mocks in the tree
#                     (test_public_tracker_subprocess_timeout.py x3,
#                     test_deadline_tunable.py x1,
#                     test_search_deep_coverage.py x1) are properly
#                     os.killpg-patched as of the BOB-127 fix
#                     (commit 8bedc5a)
#   no-op-stub     -> a gate that always exits 0 regardless of content
#                     MUST be caught FAILING the golden-bad-1
#                     assertion (proves this harness is not a bluff —
#                     CONST-XII).
#
# A gate that PASSes golden-bad-1/2/false-positive-guard, or FAILs
# golden-good-1/2/real-tree, is itself the bluff (§11.4.107(10)) and
# this harness reports it.
#
# Exit codes:
#   0 — every fixture (+ real-tree smoke + no-op-stub negative control)
#       matched its expected outcome (the gate is honest).
#   1 — one or more checks diverged from the expected outcome.
#   2 — harness/environment error (gate script missing or not
#       executable).
#
# Cross-refs: §11.4.1 §11.4.4 §11.4.6 §11.4.43 §11.4.69 §11.4.107(10)
#             §11.4.108 §11.4.115 §11.4.135 §11.4.201 §11.4.226
#             §11.4.263 CONST-XII.

set -euo pipefail

HARNESS_NAME="test_check_cm_test_mock_pid_patched_when_real_pid"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

GATE="$REPO_ROOT/scripts/pre_build/check_cm_test_mock_pid_patched_when_real_pid.sh"

if [[ ! -f "$GATE" ]]; then
  echo "FAIL($HARNESS_NAME): gate script not found at $GATE" >&2
  echo "  (expected — this meta-test is authored RED-first per §11.4.115;" >&2
  echo "   implement scripts/pre_build/check_cm_test_mock_pid_patched_when_real_pid.sh next)" >&2
  exit 2
fi
if [[ ! -x "$GATE" ]]; then
  echo "FAIL($HARNESS_NAME): gate script not executable at $GATE" >&2
  exit 2
fi

TMPDIR_ROOT="$(mktemp -d -t test_mock_pid_patched_meta.XXXXXX)"
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
# Fixture 1 (golden-good-1): explicit `.pid = 12345` PLUS an
# object-form `patch.object(<mod>.os, "killpg")` patch — the sanctioned
# BOB-127 fix pattern mirrored from
# test_process_group_kill_called_on_deadline in
# tests/unit/merge_service/test_public_tracker_subprocess_timeout.py.
# ------------------------------------------------------------------------
GOOD1_FIXTURE="$TMPDIR_ROOT/golden_good_1.py"
cat > "$GOOD1_FIXTURE" <<'PYEOF'
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import merge_service.search as _search


async def _hang():
    await asyncio.sleep(999)


async def test_process_group_kill_called_on_deadline() -> None:
    proc = AsyncMock()
    proc.returncode = None
    proc.pid = 9999
    proc.stdout = MagicMock()
    proc.stdout.readline = AsyncMock(side_effect=_hang)
    proc.stderr = MagicMock()
    proc.stderr.read = AsyncMock(return_value=b"")
    proc.wait = AsyncMock(return_value=-9)
    proc.kill = MagicMock()

    with (
        patch("asyncio.create_subprocess_exec", return_value=proc),
        patch.object(_search.os, "getpgid", return_value=9999),
        patch.object(_search.os, "killpg") as mock_killpg,
    ):
        pass
    return mock_killpg
PYEOF
run_gate "$GOOD1_FIXTURE"
assert_rc "golden-good-1 (.pid=12345-shaped + patch.object(<mod>.os, \"killpg\"))" 0

# ------------------------------------------------------------------------
# Fixture 2 (golden-good-2): explicit `.pid = 12345` PLUS a bare
# string-literal-form `patch("os.killpg")` patch — the alternate
# sanctioned pattern used throughout
# tests/unit/merge_service/test_search_deep_coverage.py.
# ------------------------------------------------------------------------
GOOD2_FIXTURE="$TMPDIR_ROOT/golden_good_2.py"
cat > "$GOOD2_FIXTURE" <<'PYEOF'
from unittest.mock import AsyncMock, MagicMock, patch


async def test_search_public_tracker_proc_cleanup_kill() -> None:
    proc_mock = AsyncMock()
    proc_mock.stdout = MagicMock()
    proc_mock.stdout.readline = AsyncMock(return_value=b"")
    proc_mock.stderr = MagicMock()
    proc_mock.stderr.read = AsyncMock(return_value=b"stderr output")
    proc_mock.returncode = None
    proc_mock.kill = MagicMock()
    proc_mock.pid = 12345
    with patch("asyncio.create_subprocess_exec", return_value=proc_mock):
        with patch("os.killpg"):
            with patch("os.getpgid", return_value=12345):
                pass
PYEOF
run_gate "$GOOD2_FIXTURE"
assert_rc "golden-good-2 (.pid=12345 + bare patch(\"os.killpg\"))" 0

# ------------------------------------------------------------------------
# Fixture 3 (golden-bad-1): explicit `.pid = 12345`, NO killpg patch
# anywhere — the raw pre-fix BOB-127 defect shape (the EXACT shape
# test_stuck_subprocess_killed_and_abandoned had BEFORE commit 8bedc5a,
# per Task 8's syscall-audit DANGEROUS finding #1).
# ------------------------------------------------------------------------
BAD1_FIXTURE="$TMPDIR_ROOT/golden_bad_1.py"
cat > "$BAD1_FIXTURE" <<'PYEOF'
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


async def _hang():
    await asyncio.sleep(999)


async def test_stuck_subprocess_killed_and_abandoned() -> None:
    proc = AsyncMock()
    proc.returncode = None
    proc.pid = 12345
    proc.stdout = MagicMock()
    proc.stdout.readline = AsyncMock(side_effect=_hang)
    proc.stderr = MagicMock()
    proc.stderr.read = AsyncMock(return_value=b"")
    proc.wait = AsyncMock(return_value=-9)
    proc.kill = MagicMock()

    with (
        patch("asyncio.create_subprocess_exec", return_value=proc),
    ):
        pass
PYEOF
run_gate "$BAD1_FIXTURE"
assert_rc "golden-bad-1 (.pid=12345, no killpg patch — the pre-8bedc5a BOB-127 shape)" 1

# ------------------------------------------------------------------------
# Fixture 4 (golden-bad-2): explicit `.pid = 1111` — a SMALL pid with
# materially higher real-world PID-reuse collision probability — NO
# killpg patch anywhere. Proves detection is NOT hardcoded to the
# literal 12345 (per Task 8's DANGEROUS finding #2,
# test_cleanup_timeout_abandons_zombie before commit 8bedc5a).
# ------------------------------------------------------------------------
BAD2_FIXTURE="$TMPDIR_ROOT/golden_bad_2.py"
cat > "$BAD2_FIXTURE" <<'PYEOF'
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


async def _hang():
    await asyncio.sleep(999)


async def test_cleanup_timeout_abandons_zombie() -> None:
    proc = AsyncMock()
    proc.returncode = None
    proc.pid = 1111
    proc.stdout = MagicMock()
    proc.stdout.readline = AsyncMock(return_value=b"")
    proc.stderr = MagicMock()
    proc.stderr.read = AsyncMock(side_effect=_hang)
    proc.wait = AsyncMock(side_effect=_hang)
    proc.kill = MagicMock()

    with (
        patch("asyncio.create_subprocess_exec", return_value=proc),
    ):
        pass
PYEOF
run_gate "$BAD2_FIXTURE"
assert_rc "golden-bad-2 (.pid=1111, no killpg patch — proves not hardcoded to 12345)" 1

# ------------------------------------------------------------------------
# Fixture 5 (false-positive-guard, §11.4.201): explicit `.pid = 12345`
# PLUS a patch that MENTIONS the string "killpg" but targets a
# COMPLETELY UNRELATED module (`some_other_module.killpg`), never
# `os.killpg`. The sibling gate CM-TEST-MOCK-PID-EXPLICIT-INT's looser
# any-module exemption regex (`patch(\.object)?\([^)]*["']killpg["']`)
# would WRONGLY accept this as an exemption; THIS gate's narrower
# os.killpg-targeting exemption MUST NOT be fooled by it and MUST still
# flag the hit — proving the exemption regex genuinely anchors on
# `os.killpg`, not merely the substring "killpg" anywhere in a patch
# call (the exact near-carrier false-negative class §11.4.201(6)-(7)
# names: a token that MENTIONS the pattern matched as if it WERE the
# pattern).
# ------------------------------------------------------------------------
FALSEPOS_FIXTURE="$TMPDIR_ROOT/false_positive_guard.py"
cat > "$FALSEPOS_FIXTURE" <<'PYEOF'
from unittest.mock import AsyncMock, MagicMock, patch


async def test_unrelated_killpg_patch_must_not_exempt() -> None:
    proc = AsyncMock()
    proc.returncode = None
    proc.pid = 12345
    proc.stdout = MagicMock()
    proc.stdout.readline = AsyncMock(return_value=b"")
    proc.stderr = MagicMock()
    proc.stderr.read = AsyncMock(return_value=b"")
    proc.wait = AsyncMock(return_value=-9)
    proc.kill = MagicMock()

    with (
        patch("asyncio.create_subprocess_exec", return_value=proc),
        patch("some_other_module.killpg"),
    ):
        pass
PYEOF
run_gate "$FALSEPOS_FIXTURE"
assert_rc "false-positive-guard (.pid=12345 + patch(\"some_other_module.killpg\") — must still FAIL, patch targets a random module, not os.killpg)" 1

# ------------------------------------------------------------------------
# Real-tree smoke check (acceptance criterion 1): the gate MUST pass
# its own default in-repo scope (tests/**/*.py) against the CURRENT
# boba checkout. All 5 real-pid reachable-kill-branch subprocess mocks
# in the tree (test_public_tracker_subprocess_timeout.py x3,
# test_deadline_tunable.py x1, test_search_deep_coverage.py x1) are
# properly os.killpg-patched as of the BOB-127 fix (commit 8bedc5a).
# ------------------------------------------------------------------------
out="$(mktemp -p "$TMPDIR_ROOT")"
err="$(mktemp -p "$TMPDIR_ROOT")"
set +e
"$GATE" >"$out" 2>"$err"
rc=$?
set -e
GOT_RC="$rc"; GOT_OUT="$out"; GOT_ERR="$err"
assert_rc "real-tree default scope (tests/**/*.py, BOB-127 fix at 8bedc5a already patches all 5 real-pid mocks)" 0

# ------------------------------------------------------------------------
# No-op-stub negative control (CONST-XII anti-bluff: every new test
# MUST fail against a no-op stub of the feature it tests). A gate that
# always exits 0 regardless of content must be caught FAILING the
# golden-bad-1 assertion — proving this harness genuinely
# discriminates rather than rubber-stamping whatever gate happens to
# be on disk.
# ------------------------------------------------------------------------
STUB_GATE="$TMPDIR_ROOT/stub_always_pass.sh"
cat > "$STUB_GATE" <<'STUBEOF'
#!/usr/bin/env bash
echo "PASS: stub always passes"
exit 0
STUBEOF
chmod +x "$STUB_GATE"
run_gate_bin "$STUB_GATE" "$BAD1_FIXTURE"
if [[ "$GOT_RC" -eq 0 ]]; then
  echo "PASS: no-op-stub negative control (stub wrongly PASSed golden-bad-1, as expected — proves the golden-bad-1 fixture is genuinely dangerous-shaped and this harness would have caught a bluff gate)"
else
  echo "FAIL: no-op-stub negative control — the stub gate unexpectedly exited nonzero; the negative control is not exercising a real no-op"
  fails=$((fails + 1))
fi

echo
if [[ $fails -ne 0 ]]; then
  echo "$HARNESS_NAME: FAIL — $fails check(s) diverged from expected outcome" >&2
  exit 1
fi
echo "$HARNESS_NAME: PASS — CM-TEST-MOCK-PID-PATCHED-WHEN-REAL-PID honest across 5 fixtures + real tree + no-op-stub negative control (§11.4.107(10))"
exit 0
