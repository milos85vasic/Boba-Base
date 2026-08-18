# §11.4.209 review MINOR-1..6 batch remediation

**Revision:** 1
**Last modified:** 2026-08-18T00:00:00Z

Evidence for the 6 MINOR findings from `.superpowers/sdd/task-review-457cca4-a7e55f9-report.md`,
fixed in the same batch task on top of task #78's IMPORTANT-1 landing.

| Finding | File | Verdict | Evidence |
|---|---|---|---|
| MINOR-1 | `scripts/host-power-management/check-no-suspend-calls.sh` | FIXED | [minor-1.log](minor-1.log) |
| MINOR-2 | `challenges/scripts/resource_pressure_signature_challenge.sh` | FIXED | [minor-2.log](minor-2.log) |
| MINOR-3 | `challenges/scripts/resource_pressure_signature_challenge.sh` | FIXED | [minor-3.log](minor-3.log) |
| MINOR-4 | `challenges/scripts/resource_pressure_signature_challenge.sh` | FIXED (design revised after a caught regression — see minor-4.log) | [minor-4.log](minor-4.log) |
| MINOR-5 | `scripts/commit-push-all.sh` | FIXED | [minor-5.log](minor-5.log) |
| MINOR-6 | `scripts/install-dev-tools.sh` | SKIPPED — out of declared scope, concurrently owned by another in-flight remediation stream (see minor-6.log) | [minor-6.log](minor-6.log) |

## Notable finding during remediation

MINOR-1's fix required touching `scripts/host-power-management/check-no-suspend-calls.sh`,
which was **not** in this task's originally declared 3-item scope
(`challenges/scripts/resource_pressure_signature_challenge.sh` +
`scripts/commit-push-all.sh` + this evidence directory). Before editing it,
`git log` / `git status` were checked and showed **no** recent or in-flight
concurrent activity on that file — the safe/reversible/bounded-blast-radius
bar per §11.4.101 was met, so the edit proceeded and the file was added to
this batch's `--scope` commit. MINOR-6's fix location
(`scripts/install-dev-tools.sh`), by contrast, showed a commit from the SAME
review's IMPORTANT-3 remediation landing moments earlier — a live sibling
stream — so it was left untouched and honestly SKIPPED (§11.4.3) rather than
risking a shared-checkout collision.

## Regression caught and fixed during MINOR-4's own remediation

The first draft of the MINOR-4 fix (raising SIG-3's required EAGAIN hit-count
when SIG-2 reads low) was caught, via `verify_resource_pressure_polarity.sh`,
regressing SIG-3's own §11.4.115(F) RED fixture *before* it was ever
committed. The design was revised to attach a confidence label to the
verdict instead of changing the FAIL threshold — see `minor-4.log` for the
full before/after transcript. This is the exact TDD/§11.4.4
test-interrupt-on-discovery discipline this constitution mandates, applied
in-session.

## Full regression proof (all 5 signature detectors, post-fix)

`minor-4.log` also contains the complete `verify_resource_pressure_polarity.sh`
re-run: **5/5 signatures RED CONFIRMED** against their real pathological
artifacts after MINOR-2/3/4's fixes landed — zero regression in detection
power for any of the five `resource_pressure_signature_challenge.sh`
detectors.
