# BOB-FIXTURE-STDERR-CREDENTIAL — closure evidence

Regression fixture: the recorded command writes a credential-shaped value to
STDERR. verify-closure must pass that stderr through the redactor before it
reaches the terminal (review finding I-4). The value is a fixture, not a secret.

**Command:** `echo 'BOBA_API_TOKEN=stderr-leak-fixture-not-real' >&2; echo '3 passed, 0 failed'`
**Result Summary:** 3 passed, 0 failed
**Evidence Layer:** runtime
**Test Type:** unit
