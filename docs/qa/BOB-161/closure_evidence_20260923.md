# BOB-161 closure evidence — CM-NO-FAIL-OPEN-SKIP gate

**Revision:** 1
**Last modified:** 2026-09-23T16:19:41Z

## Claim
The §11.4.69 gate CM-NO-FAIL-OPEN-SKIP now exists (`scripts/pre_build/check_cm_no_fail_open_skip.sh` + `cm_no_fail_open_skip_analyzer.py`), is wired as pre-build invariant 57, and ratchets the fail-open skips that exist today against `scripts/pre_build/cm_no_fail_open_skip.baseline` as a SET (NEW and STALE both fail).

## Evidence (this session)
- RED (harness written before the gate): `FAIL: gate or engine missing ... CM-NO-FAIL-OPEN-SKIP does not exist` rc=1 (subagent capture).
- GREEN, independently re-run from the conductor shell: `bash tests/pre_build/test_check_cm_no_fail_open_skip.sh` -> `=== all cases PASS ===` rc=0; last case `PASS: case 10/M3: neutered baseline comparison flips case 1`.
- Real tree, conductor shell: `PASS: CM-NO-FAIL-OPEN-SKIP: 10 finding(s) (10 baselined, 0 new, 0 stale) across 412 test files, 69 skip sites; control-needle: seen`
- Paired §1.1 mutations M1 (detection off -> control needle refuses rc=2), M2 (detection+needle off -> gate passes known-bad tree; caught by harness case 1), M3 (baseline comparison off -> case 1 flips).
- Golden-FALSE-with-carrier: comments/strings/docstrings and environment-derived skips produce no findings (harness case).

## Honest gaps
- Baseline records 10 findings, not the 6 BOB-192 described; BOB-192 acceptance is now "these 10 rows to 0" (tracked there, remains open).
- Tracing is per-file; fixture-parameter flows and `getfixturevalue` wrappers are not followed; shell coverage is the `ab_skip` family only.
- Ordinal in the key means swapping two same-type skips inside one function is not detected.
