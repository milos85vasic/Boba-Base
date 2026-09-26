# BOB-FIXTURE-MISMATCH-CREDENTIAL — closure evidence

Regression fixture for the Task 5C security-reviewer Important finding
(agent a3c502c254c1b2ffc): "no integration-level test for the actual leak
path." This fixture's recorded evidence AND its fresh command output are
both credential-shaped, so a MISMATCH exercises `cmd_verify_closure`'s real
`print_error` line (`scripts/zero_shortcomings_audit.sh` MISMATCH branch),
not the standalone `audit_redact_before_write` function in isolation.

**Command:** `echo 'BOBA_API_TOKEN=live-token-fixture-not-real'`
**Result Summary:** RUTRACKER_PASSWORD=hunter2-recorded-fixture-not-real
**Evidence Layer:** runtime
**Test Type:** unit
