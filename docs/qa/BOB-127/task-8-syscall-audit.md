# BOB-127 — Task 8 syscall audit (reproduced closure evidence)

**Revision:** 1
**Last modified:** 2026-09-02T00:00:00Z

## Why this file exists

BOB-127 closed on 2026-08-19 (`item_history` id=172, event=`Fixed`, by=`AI`) citing
evidence at `.superpowers/sdd/task-8-syscall-audit.md`. That path was **never
committed** — `git log --all -- '.superpowers/sdd/task-8-syscall-audit.md'` returns
nothing and `.superpowers/` does not exist in the working tree — so the closure's
captured proof was not producible on demand and
`workable-items validate` refused it under §11.4.5 / §11.4.69 / §11.4.123 / §11.4.226.

The claim itself is **re-producible today**, so this file re-executes the audit and
lands it at the project's canonical, tracked evidence location (`docs/qa/<ATM-ID>/`,
§11.4.83 / §11.4.215) rather than an untracked scratch directory. The
`item_history` `evidence_path` is corrected to point here.

**Why the original vanished — known mechanism, not a new discovery.** This project's own
QA discovery ledger already records the class: entry `SCRATCH-LOSS-2026-08-18`
(`docs/QA_DISCOVERY_LEDGER.md`) documents `.superpowers/sdd/` deliverables that were
declared but never written, root-caused to producer subagents crashing on session rate
limits mid-deliverable (§11.4.147(e)), with the follow-up **BOB-107** filed for a
pre-dispatch precondition check. `.superpowers/` is an untracked agent scratchpad, so
anything cited from it is outside version control and unproducible the moment that
scratchpad is gone. Citing a scratchpad path as a closure's captured proof is the
underlying defect; landing evidence under tracked `docs/qa/` is the fix, and matches
every other evidence row in this DB.

## What BOB-127 was

Follow-up to the BOB-126 host-safety sweep (§11.4.263). The Task-8 audit found
**2 test cases** in `tests/unit/merge_service/test_public_tracker_subprocess_timeout.py`
that set an explicit integer `mock.pid` (`12345`, `1111`) — satisfying the *production*
BOB-126 `pid > 1` int-guard — but did **not** patch `os.killpg` / `os.getpgid`, so the
real syscalls fired against hardcoded, non-owned PIDs. Low collision probability on a
typical host, but a §11.4.263(C) test-side hygiene violation in the exact file authored
to regression-guard against host-wide kills.

**Fix:** commit `8bedc5a` ("test(BOB-126): patch os.killpg/getpgid in remaining 2
subprocess-timeout tests") added `patch.object(_search.os, "getpgid", ...)` +
`patch.object(_search.os, "killpg")` to both tests, copying the sanctioned pattern
already used by the sibling `test_process_group_kill_called_on_deadline`.

## Layer 1 — the fix is present at HEAD (`60729c9`)

```
$ grep -n "getpgid\|killpg\|def test_" tests/unit/merge_service/test_public_tracker_subprocess_timeout.py
15:1.  Process-group kill (`start_new_session=True` + `os.killpg`) so
62:async def test_stuck_subprocess_killed_and_abandoned() -> None:
83:        patch.object(_search.os, "getpgid", return_value=12345),
84:        patch.object(_search.os, "killpg"),
95:async def test_process_group_kill_called_on_deadline() -> None:
117:        patch.object(_search.os, "getpgid", return_value=9999) as mock_getpgid,
118:        patch.object(_search.os, "killpg") as mock_killpg,
122:    mock_getpgid.assert_called_once_with(9999)
123:    mock_killpg.assert_called_once_with(9999, pytest.approx(9))  # SIGKILL = 9
126:async def test_cleanup_timeout_abandons_zombie() -> None:
150:        patch.object(_search.os, "getpgid", return_value=1111),
151:        patch.object(_search.os, "killpg"),
```

Both formerly-unguarded tests (lines 62 and 126) now carry the guard pair at
lines 83-84 and 150-151.

## Layer 2 — the 6 tests still pass (runtime)

Full log: [`pytest_6_tests.log`](pytest_6_tests.log)

```
tests/.../test_stuck_subprocess_killed_and_abandoned      PASSED [ 16%]
tests/.../test_process_group_kill_called_on_deadline      PASSED [ 33%]
tests/.../test_cleanup_timeout_abandons_zombie            PASSED [ 50%]
tests/.../test_outer_backstop_timeout_in_search_tracker   PASSED [ 66%]
tests/.../test_return_exceptions_in_run_search            PASSED [ 83%]
tests/.../test_return_exceptions_preserves_successful_tracker PASSED [100%]

============================== 6 passed in 20.63s ==============================
```

(The closing commit claimed "All 6 tests in file still PASS (21.6s)"; re-measured
today at 20.63 s — the same 6/6.)

## Layer 3 — the audit is now mechanized, and it is GREEN

The audit's finding is no longer a one-off human read: it is the standing pre-build
gate `CM-TEST-MOCK-PID-PATCHED-WHEN-REAL-PID`
(`scripts/pre_build/check_cm_test_mock_pid_patched_when_real_pid.sh`), which the
BOB-127 body recorded as a recommended follow-up and which has since shipped.

GREEN — full log: [`gate_cm_test_mock_pid_GREEN.log`](gate_cm_test_mock_pid_GREEN.log)

```
$ bash scripts/pre_build/check_cm_test_mock_pid_patched_when_real_pid.sh
check_cm_test_mock_pid_patched_when_real_pid — CM-TEST-MOCK-PID-PATCHED-WHEN-REAL-PID static pre-build gate
  scope: default (tests, excluding tests/pre_build/), repo-root: /home/milosvasic/Projects/boba
  forward window: 20 lines; os.killpg-exemption window: ±30 lines
  files scanned: 336

PASS: CM-TEST-MOCK-PID-PATCHED-WHEN-REAL-PID clean across 336 file(s)
GATE_EXIT=0
```

## Layer 4 — §1.1 paired mutation: the gate genuinely catches BOB-127's defect

RED — full log: [`gate_cm_test_mock_pid_RED_mutation.log`](gate_cm_test_mock_pid_RED_mutation.log)

Mutation: delete lines 83-84 (the two guard lines) from
`test_stuck_subprocess_killed_and_abandoned`, restoring exactly the pre-`8bedc5a`
defect. The gate is a **static source scan**, so this RED was captured **without ever
firing an unguarded `killpg`** against a non-owned PID (§11.4.263 — the defect is
proven by detection, never by re-executing the dangerous syscall).

```
=== FINDINGS ===
FAIL: .../test_public_tracker_subprocess_timeout.py:70: real-pid subprocess-mock with
NO os.killpg-targeting patch — proc = AsyncMock() [identifier=proc] (has `proc.pid =
<int>` but no `os.killpg`-targeting patch within 30 lines; see
test_process_group_kill_called_on_deadline ... for the sanctioned fix pattern)

FAIL: 1 unpatched real-pid test-subprocess-mock hit(s) (CM-TEST-MOCK-PID-PATCHED-WHEN-REAL-PID, BOB-127)
GATE_EXIT_UNDER_MUTATION=1
```

The gate names **BOB-127** in its own failure text. The mutation was reverted
immediately and the working tree re-verified clean (`git diff --stat` empty for that
file) before any further work — §11.4.84 working-tree quiescence.

**Polarity pair:** RED exit 1 on the defect present → GREEN exit 0 on the defect fixed.
The guard is therefore validated instrumentation, not decoration (§11.4.115(F)).

## Verdict

BOB-127's closure claim is **re-produced and true at HEAD `60729c9`**: the defect is
fixed in source, the 6 tests pass, the audit is mechanized as a standing gate that is
GREEN, and that gate provably FAILs when the defect is reintroduced. The closure stands;
only its `evidence_path` was wrong, and it now points at this file.

## Honest boundary (§11.4.6)

- The **original** `.superpowers/sdd/task-8-syscall-audit.md` is gone and was never
  committed; its verbatim prose is **not** recovered. What is reproduced here is the
  audit's *substance* — the finding, the fix, and machine-verifiable proof of both —
  re-derived today from the tracked commit `8bedc5a` and the live tree.
- This evidence covers BOB-127's specific finding (2 unguarded test mocks in one file).
  It is not a claim that the whole test corpus is free of every host-safety
  anti-pattern; the standing gate's 336-file scan is the ongoing instrument for that.
