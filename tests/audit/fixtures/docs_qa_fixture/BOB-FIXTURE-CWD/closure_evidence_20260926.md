# BOB-FIXTURE-CWD — closure evidence

Regression fixture for review finding I-6 (FR-006): the recorded command runs
with its working directory at the repository root, so its result does not
depend on the directory verify-closure was invoked from.

**Command:** `test -f scripts/zero_shortcomings_audit.sh && echo repo-root-cwd || echo wrong-cwd`
**Result Summary:** repo-root-cwd
**Evidence Layer:** runtime
**Test Type:** unit
