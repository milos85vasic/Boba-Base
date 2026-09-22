# BOB-201 closure evidence — 2026-09-23

## Operator decision implemented

"Resolve symlinks (realpath) and re-fence" (option a). `ownership_path_fence()`
(`scripts/lib/ownership.sh`, the single shared implementation used by both
`scripts/ownership_repair.sh` and `scripts/ownership_precondition.sh`) now
resolves every intermediate path component that is a symlink via a real
filesystem check (`readlink -f` per-component, with `[[ -e "$target" ]]`
existence verification closing a subtlety plain rc-code checking misses:
a standalone dangling symlink returns rc=0 with its raw nonexistent target
text) BEFORE the existing lexical containment/denylist checks judge the
path. The FINAL (leaf) path component is deliberately never resolved
(already covered by `find`'s own `-P` behaviour per the suite's existing
Case 17), and a genuinely-not-yet-created component (never a symlink) still
falls through to the pre-fix lexical-append behaviour, preserving the
legitimate "declared download root not yet created" case (data-model E1) —
this data-loss-avoidance edge case was explicitly identified and protected
against during implementation, not merely assumed safe.

## Independently re-verified this session (coordinator, including a genuine
paired-mutation revert/restore reproduced from a clean shell)

```
$ bash tests/unit/test_ownership_repair.sh
... Case 25: an intermediate symlink is resolved before the fence judges the path (BOB-201)
  PASS x7 (all 7 sub-cases, including the golden-FALSE symlinked-but-in-scope
  case and both not-yet-created-path non-regression guards)
RESULT: 153 passed, 0 failed, 0 skipped

$ git stash push -m "coordinator-verify-bob201-mutation" -- scripts/lib/ownership.sh
$ bash tests/unit/test_ownership_repair.sh
  FAIL x4 (the four symlink-escape variants — genuinely reproduces the
  pre-fix defect) + Case 24's own citation-text assertion also correctly
  fails against the reverted file (an expected 5th failure, not a bug)
RESULT: 148 passed, 5 failed, 0 skipped

$ git stash pop
$ bash tests/unit/test_ownership_repair.sh
RESULT: 153 passed, 0 failed, 0 skipped
```

```
$ bash tests/unit/test_ownership_precondition.sh
RESULT: 29 passed, 0 failed, 0 skipped

$ bash tests/unit/test_ownership_rootless_detection.sh
RESULT: 19 passed, 0 failed
```
Both sibling suites (which share the fixed function) unaffected.

```
$ grep -n "judges the spelling\|JUDGES THE SPELLING" scripts/lib/ownership.sh tests/unit/test_ownership_repair.sh
(empty)
```
The stale "IT JUDGES THE SPELLING; THE KERNEL RESOLVES THE PATH" claim (now
false — intermediate components genuinely ARE resolved) was corrected
in-source alongside Case 24's matching assertion, per §11.4.6 (a claim must
match measured reality). All existing BOB-159 citations were audited
(`grep -rn "BOB-159" scripts/ tests/`) and confirmed to be deliberate
historical narrative already correctly resolved to BOB-201 by an earlier
commit (03bf860) — none were live/incorrect, none were touched.

## Honest boundary (not silenced)

**TOCTOU is accepted, not eliminated**: the fence resolves at judgment
time; the later recursive walk uses the original (unresolved) declared
path. A symlink swapped in between fence-time and walk-time is not caught
by this fix — the accepted cost of the operator's chosen resolve-and-refence
direction, documented explicitly in-source rather than implying stronger
guarantees than are actually provided. A permission-denied plain (non-symlink)
intermediate component is treated as "not yet created" (accepted, falls
through), not refused — judged in-scope-correct since the original lexical
fence never checked filesystem permissions at all.

## git diff --stat

```
scripts/lib/ownership.sh            | 206 ++++++++++++++++++++++++++++++++----
tests/unit/test_ownership_repair.sh | 177 ++++++++++++++++++++++++++++---
2 files changed, 346 insertions(+), 37 deletions(-)
```
