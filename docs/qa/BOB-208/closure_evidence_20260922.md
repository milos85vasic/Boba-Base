# BOB-208 closure evidence — 2026-09-22

## Fix

`scripts/lib/ownership.sh` `probe_location()`: `want="$(ownership_operator_uid)"`
is now guarded — `if ! want="$(ownership_operator_uid)" || [[ -z "${want}" ]]; then
echo "unresolved-operator-uid"; return 1; fi` — so a failing `id(1)` yields an
honest, distinct verdict naming the unresolved precondition instead of a
fabricated `wrong-owner:<correct-uid>` claim. Every consumer of the verdict
already refuses on any unrecognised string (`ownership_precondition.sh`'s
`case "${verdict}" in ... *) FAILURES+=(...)`), so this still fails closed.

## RED evidence (id shimmed to fail)

Pre-fix verdict: `wrong-owner:1000` on a perfectly healthy location — naming
the CORRECT uid as wrong.

## GREEN evidence

Post-fix verdict: `unresolved-operator-uid`.

## Golden-FALSE

A healthy location with a working `id` still verdicts `ok`.

## Independently re-verified this session

```
$ bash tests/unit/test_ownership_probe_location.sh
  PASS: sandbox: no stray probe files left directly under the harness work dir
RESULT: 10 passed, 0 failed, 0 skipped
```

(Combined test file covering BOB-208 and BOB-209, since both live in the same
`probe_location()` rewrite — see also `docs/qa/BOB-209/closure_evidence_20260922.md`.)

Also re-verified: `tests/unit/test_ownership_repair.sh` (146/146 pass, the
full existing regression suite for the consuming script) and
`tests/pre_build/test_check_cm_ownership_invariants.sh` (42/42 pass).

## git diff --stat (shared across BOB-207/208/209/210/220/202, one combined change)

```
scripts/lib/ownership.sh          | 120 +++++++++++++++++++++++++++++++++++---
scripts/ownership_precondition.sh |  49 +++++++++++++---
scripts/ownership_repair.sh       |  33 ++++++++++-
3 files changed, 184 insertions(+), 18 deletions(-)
```
