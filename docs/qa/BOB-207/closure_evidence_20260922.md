# BOB-207 closure evidence — 2026-09-22

## Finding

BOB-207 ("probe_location() is GID-BLIND") is already resolved — NOT by
widening `probe_location()` to check gid (the item's own suggested
direction), but by NARROWING `ownership_repair.sh`'s walk-selection
predicate to select on uid only, landed in a prior session (commit
`5c9b9e0`, corrected by docs commit `1444367` after a mislabelled commit
message). `scripts/lib/ownership.sh:299-321` carries an in-source block
headed "THE AGREED PROPERTY IS uid, NOT uid+gid (BOB-207, §11.4.250)"
documenting the resolution and rationale.

Independently re-verified this session by a dedicated subagent, then
independently re-run by the coordinator.

## Verification

```
$ bash tests/unit/test_ownership_gid_agreement.sh
  PASS: golden-FALSE: precondition and repair agree on a correct location
RESULT: 5 passed, 0 failed, 0 skipped
```

`tests/unit/test_ownership_gid_agreement.sh`'s own header states it was
authored as the RED that reproduced the defect; the same source now passes
and serves as the permanent regression guard. `docs/qa/BOB-207/` (pre-existing,
from the prior session) holds the full measurement trail.

No new code was written for this item — it was correctly resolved as-is.
