# BOB-FIXTURE-NO-COMMAND closure evidence

**Evidence Layer:** runtime

Deliberately malformed evidence file for a regression test: it has no
**Command:** field at all, which the fresh re-run step depends on to
know what to re-execute. This fixture exists to prove the
`recorded_command`/`recorded_summary` grep assignments fail loud (exit 2,
per the documented "no **Command:** field to re-run" contract) rather
than silently aborting with a bare, unexplained exit 1 via the
set -e/pipefail footgun (§11.4.201(12)) confirmed live in this exact code
by the Task 5 implementer's own report.
