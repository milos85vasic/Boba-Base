# BOB-200 closure evidence — 2026-09-23

## Defect
`cm_dangerous_combination_fail_closed.sh` built its scan file list via
`find(1)` piped through a process substitution that silently discarded
find's own exit status — a permission-denied/resource-exhausted `find`
failure produced an empty file list, read as "no files in scope" → honest
topology SKIP → exit 0, indistinguishable from a genuinely clean corpus
(§11.4.201(6) false-null).

## Fix
Replaced the process-substitution `mapfile -d '' -t files < <(find ...)`
with a scratch-file capture: `find ... > "$find_scratch"; find_rc=$?`
checked explicitly before reading. A non-zero `find_rc` is now refused
(exit 1, "scan enumeration failed: find exited N"), distinct from the
genuine "find succeeded, zero files" honest SKIP path (unchanged, exit 0).

## Independent verification (coordinator, from clean shell)

### Manual, real-fixture reproduction (not trusted from report)
```
$ mkdir -p /tmp/.../bob200_repro/blocked && chmod 000 /tmp/.../bob200_repro/blocked
$ bash constitution/scripts/gates/cm_dangerous_combination_fail_closed.sh --root /tmp/.../bob200_repro --quiet
find: '.../blocked': Permission denied
CM-DANGEROUS-COMBINATION-FAIL-CLOSED: FAIL — scan enumeration failed: find exited 1 ...
EXIT=1
```
Genuine, live permission-denied fixture — not a synthetic/mocked find
stub — correctly refused rather than silently SKIPped.

### Golden-FALSE confirmed (genuinely empty root still SKIPs honestly)
Confirmed via the full mutation suite's L80/L81 fixtures (below) — a
genuinely-empty, fully-readable root still produces the honest SKIP/exit 0
path unchanged.

### Full mutation suite
```
$ bash constitution/scripts/gates/cm_dangerous_combination_fail_closed_mutation_test.sh
✅ META OK:   L80 a find(1) enumeration failure (permission-denied subtree) is refused ...
✅ META OK:   L80 the refusal names the unresolved precondition ("scan enumeration failed"), never silent
✅ META OK:   L81 a normal violation is still caught after the BOB-200 find-failure fix ...
✅ META PASS ... META_EXIT=0
```

## Status
Fixed. Closed by coordinator after independent re-verification, including a
manual live-fixture reproduction distinct from the automated suite.
