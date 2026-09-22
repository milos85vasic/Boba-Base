# BOB-210 test-suite self-fix — 2026-09-23

## What broke, and why it is not a product regression

`tests/unit/test_ownership_precondition_docker_premise.sh`'s Case 4 (the
RED-baseline control) pinned its "pre-fix" reference to `git show HEAD`,
captured at *run time*. That is only a valid pre-fix baseline in the narrow
window between authoring the fix and committing it. Once the fix commit
(`03bf860`) landed and became `HEAD` — which is the normal, expected state
of any checkout after the commit that carries both the fix and this test —
`HEAD` is *post*-fix, so the control diffed the fixed file against itself:
it found the claim's text (kept deliberately, as an explicitly-refuted
historical citation — Case 1's own documented, intended design) *and* found
the nearby refutation that marks it refuted, and correctly reported that as
"this is no longer a pre-fix baseline" via its `fail` branch.

This is exactly the failure mode `docs/qa/BOB-217/closure_evidence_20260922.md`
already worked around by pinning to an immutable SHA (`eb5cfce`) instead of
`HEAD` — this suite (authored in the same batch) used the less robust `HEAD`
form and hit the footgun once `HEAD` genuinely advanced past the fix.

## Root cause (confirmed, not guessed — §11.4.6)

```
$ git log --oneline -3 -- scripts/ownership_precondition.sh
03bf860 fix(security,ownership,ratelimit): close 12 tracked defects — ...
5c9b9e0 test-probe-do-not-use [skip-ci]
af48019 feat(BOB-183,BOB-187): a freshness gate for the served bundle, ...

$ git show HEAD:scripts/ownership_precondition.sh | grep -B2 -A2 -F "an unverified reading can never"
# ... claim text present ...
# claim is FALSE for the branch as shipped and was corrected here rather than
# left standing: ...
```
`HEAD` (`eb5cfce`, built on `03bf860`) already carries the fix's refutation
text next to the claim — confirming the control's premise ("HEAD reproduces
the pre-fix defect") no longer holds, by direct evidence, not inference.

```
$ git show af48019:scripts/ownership_precondition.sh | grep -B2 -A2 -F "an unverified reading can never"
#               indicator and is UNMEASURED here. It is deliberately built to
#               fail toward `unknown` (a named skip) rather than toward a
#               confident `rootful`, so an unverified reading can never
#               manufacture a refusal.
```
`af48019` (the commit immediately preceding the fix on this file's history)
carries the claim with NO nearby refutation — a genuine, immutable pre-fix
baseline.

## Fix

`tests/unit/test_ownership_precondition_docker_premise.sh` Case 4: pinned
`git show HEAD:...` → `git show af48019:...` (an immutable commit SHA, per
the same pattern already used by `tests/unit/test_bob217_plugin_update_pinned_hash_verification.py`),
with the in-source comment rewritten to explain why `HEAD` is unusable here
and why this specific SHA is the correct pin. Behaviour of the three
substantive cases (1-3) is completely unchanged.

## Independently re-verified this session

```
$ bash -n tests/unit/test_ownership_precondition_docker_premise.sh
(clean)

$ bash tests/unit/test_ownership_precondition_docker_premise.sh
== BOB-210: the docker-branch header claim must match measured behaviour ==
  PASS: the false claim's text is present only as an explicitly-refuted historical citation, not a standing assertion
  PASS: case 2: a successful, non-empty, marker-absent docker read still refuses (measured ROOTFUL, exit 1) — the corrected header describes this correctly as confident, not unknown
  PASS: the header now honestly states the docker branch is unvalidated against a real docker install
  PASS: control: pinned pre-fix commit af48019's header asserts the claim with NO nearby refutation, reproducing the reported defect — Case 1 is discriminating
RESULT: 4 passed, 0 failed, 0 skipped
```

## Determinism (§11.4.50, 3 consecutive runs)

```
run 1: exit=0 RESULT: 4 passed, 0 failed, 0 skipped
run 2: exit=0 RESULT: 4 passed, 0 failed, 0 skipped
run 3: exit=0 RESULT: 4 passed, 0 failed, 0 skipped
```

## Trigger

This was caught by `scripts/commit-push-all.sh`'s stage-3
`pre_build_verification.sh` invariant `[30/55] CM-BASH-UNIT-TESTS-EXECUTED`
(`FAIL [1]: 1/52 bash unit/pre_build test(s) FAILED — test_ownership_precondition_docker_premise.sh`)
on the batch-3 commit attempt for BOB-217/BOB-224/BOB-228-partial. The
wrapper correctly refused the commit rather than landing a broken suite —
exactly its designed behaviour. Bug in the test, not the product; no
`scripts/ownership_precondition.sh` behaviour changed.
