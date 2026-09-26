# BOB-FIXTURE-FRESH-PROCESS — closure evidence

Regression fixture for review finding I-6 (FR-006): the recorded command must
run in a FRESH process, so it must NOT see the audit script's own internal
variables (WORKABLE_ITEMS_BIN), functions (audit_redact_before_write) or its
`set -u` (an unset variable expands to empty instead of aborting).

**Command:** `echo "bin=${WORKABLE_ITEMS_BIN:-unset} fn=$(type -t audit_redact_before_write || echo none) u=[$NOT_SET_ANYWHERE_FIXTURE]"`
**Result Summary:** bin=unset fn=none u=[]
**Evidence Layer:** runtime
**Test Type:** unit
