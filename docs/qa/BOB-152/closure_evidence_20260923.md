# BOB-152 closure evidence — 2026-09-23

## Defect
The constitution sweep (`config/constitution-sweep.conf` driving
`scripts/verify-all-constitution-rules.sh`) passed `--root @ROOT@` to most
gates with no exclusion, so `cm_oracle_strategy_named_and_independent`,
`cm_killpg_pgid_guard`, and `cm_test_mock_pid_explicit_int` walked
`submodules/` (vendored third-party code) — measured 82%/88% of one gate's
tens of thousands of findings originating there, burying first-party
findings under noise.

## Fix
All three gates already had their own env-var-driven exclude mechanism
(`ORACLE_GUARD_EXCLUDE`/`KILLPG_GUARD_EXCLUDE`/`MOCK_PID_GUARD_EXCLUDE`,
identical shape to the dangerous-combination gate's own). `submodules` is
now appended to the already-wired `_BOB143_SWEEP_EXCLUDE` base (renamed
`_BOB152_VENDORED_EXCLUDE`), applied ONLY to these 3 gates —
`DANGEROUS_COMBO_EXCLUDE` deliberately left untouched (different gate,
out of scope). `config/constitution-sweep.conf` needed no edit — the
exclude wiring lives in `scripts/verify-all-constitution-rules.sh`
directly.

## Independent verification (coordinator, from clean shell)
```
$ bash tests/pre_build/test_bob152_vendored_exclude_scope.sh
wiring confirmed: MOCK_PID_GUARD_EXCLUDE / ORACLE_GUARD_EXCLUDE / KILLPG_GUARD_EXCLUDE all read $_BOB152_VENDORED_EXCLUDE
confirmed OUT OF SCOPE preserved: DANGEROUS_COMBO_EXCLUDE is still bound to $_BOB143_SWEEP_EXCLUDE, not $_BOB152_VENDORED_EXCLUDE
---- killpg ----
PASS: with BOB-152 exclude active, submodules/-rooted probe EXCLUDED (0 hits), tests/-rooted control STILL CAUGHT (1 hit(s)).
---- oracle ----
PASS: with BOB-152 exclude active, submodules/-rooted probe EXCLUDED (0 hits), tests/-rooted control STILL CAUGHT (1 hit(s)).
---- mock_pid ----
PASS: with BOB-152 exclude active, submodules/-rooted probe EXCLUDED (0 hits), tests/-rooted control STILL CAUGHT (1 hit(s)).
VERDICT: PASS — BOB-152 exclude is load-bearing for all 3 affected gates.
```
Instrument viability proven for all 3 gates (both submodules/-rooted and
tests/-rooted synthetic violations detected BEFORE the exclude is active),
then the exclude proven load-bearing (submodules/ dropped, tests/ still
caught) — not a blind zero.

## Honest gaps disclosed (not fixed here, correctly out of scope)
`cm_killpg_pgid_guard`'s full-root unfiltered total was not fully
measured (runtime budget) — the fix's correctness does not depend on that
number, only on the mutation-proof above. The gate's own "self-reference
carrier" concern (golden-bad fixtures counted as findings) investigated
and found largely already resolved; 9 remaining first-party findings
recommended as a smaller, separate follow-up (not this item's scope).

## Status
Fixed. Closed by coordinator after independent re-verification.
