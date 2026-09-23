# BOB-168 closure evidence — 2026-09-23 (staleness-corrected closure)

## Finding
This item went through 3 investigation rounds (self-corrected premise,
runner-behaviour investigation, exit-contract fix, reviewer round-3 GO) —
all fully documented in `docs/qa/BOB-168/` (premise_correction, decision,
runtime_confirmation, round3_guard_residue_fix). Final verdict already
recorded: "Round 3 verdict: GO, zero findings, zero warnings (§11.4.134
satisfied)." — but the tracker status was never advanced.

## Final fix (as recorded in round3_guard_residue_fix.md)
An entirely un-run challenge bank (submodule absent, 16 SKIPs, 0 PASS/FAIL)
previously reported overall success because the exit expression read only
the FAIL count. Fixed: MISSING is now counted separately from SKIP and
surfaces loudly; a shared `usable_root()` predicate (consumed by both the
runner's own guard and every pre-run mutation line) closes a residue class
the reviewer found in round 2 — proven via `strace -f -e trace=unlink,unlinkat`
with a control-needle-proven instrument (§11.4.201(7)(b)).

## Independent verification (coordinator, from clean shell, 2026-09-23)
```
$ bash tests/unit/test_run_all_challenges_missing_entry.sh
PASS: all entries absent -> MISSING: 16 counted separately from SKIP
PASS: NEGATIVE CONTROL: complete roster, all passing -> exit 0
PASS: NEGATIVE CONTROL: complete roster -> MISSING: 0
PASS: one entry not executable -> exit 2
PASS: one entry not executable -> MISSING: 1
PASS: a real challenge failure -> exit 1 (unchanged, outranks MISSING)
PASS: FAIL + MISSING together -> exit 1 (FAIL outranks MISSING)
PASS: FAIL + MISSING together -> MISSING: 1 still reported, not swallowed
PASS: fixture roster is in sync with the runner's CHALLENGE_SCRIPTS
RESULT: 10 passed, 0 failed
```

## Related, distinct, not part of this closure
`scripts/pre_build_verification.sh:1792`'s analogous SKIP/MISSING
conflation for the OTHER runner is explicitly noted in the item's own text
as "filed separately" — not part of this item's scope.

## Status
Fixed. Closed by coordinator after independent re-verification.
