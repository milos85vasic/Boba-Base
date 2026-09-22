# BOB-202 closure evidence — 2026-09-22

## Fix

Root cause confirmed: TAB is an IFS-whitespace character in bash even with
IFS explicitly set to a single tab, so `while IFS=$'\t' read -r e_path e_kind
e_opt e_pres e_rec` collapses a RUN of consecutive tabs (an empty `kind`
field) into one delimiter, shifting every later field left by one.

Found the project's own existing precedent for the correct fix:
`scripts/ownership_precondition.sh` already ships `split_tsv()`
(`readarray -d $'\t'`) for exactly this row shape. Per §11.4.251
(one dialect for one question — never reinvent), this was promoted into the
shared library as `ownership_split_tsv()` in `scripts/lib/ownership.sh`
(both scripts already `source` it). `ownership_repair.sh`'s scope-entry read
loop now calls it instead of `IFS=$'\t' read`.
`ownership_precondition.sh`'s own pre-existing `split_tsv()` was left
untouched (out of scope, zero risk, already correct).

## RED/GREEN evidence (real repair runs with an `optional: true`, `kind`-omitted scope entry)

Pre-fix: "declared path does not exist and is not optional" (hard failure,
rc=1) — the `optional` boolean landed in `kind`'s slot instead. Post-fix:
"declared optional — skipped" (rc=0, correctly honours the declaration).

## Golden-FALSE

A fully-specified row (`kind` present) parses identically before and after.

## Independently re-verified this session

```
$ bash tests/unit/test_ownership_repair_scope_tsv.sh
  PASS: control: the pre-fix reader reproduces the reported field-shift (treated non-optional, hard-fails) under this identical harness, proving Case 1 is discriminating
RESULT: 3 passed, 0 failed, 0 skipped
```

Plus the full `tests/unit/test_ownership_repair.sh` (146/146) — confirms no
regression to the 6 shipped `config/owned_paths.yaml` entries (all carry
`kind`, so this was a latent-defect fix, not a live-behavior change, per the
item's own "NOT reachable from the shipped config today" statement).

See `docs/qa/BOB-208/closure_evidence_20260922.md` for the combined
`git diff --stat`.
