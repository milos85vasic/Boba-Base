# BOB-193 closure evidence — 2026-09-23

## Fix (coordinator-decided option (c), implemented)

`download-proxy/src/api/streaming.py`: the SSE dedup sets (`seen_hashes`,
`seen_hashes_local`) previously wrote the hash BEFORE the yield/emit — a
raising `format_event` therefore permanently dropped the result (its hash
was already recorded, so no later poll would ever re-emit it), even though
later polls of the SAME batch that hadn't yet been added DID correctly
re-emit — explaining the item's observed "partial loss" symptom.

Of the item's three named options — (a) do nothing/log-only, (b) add-after-
success (risks an unbounded hot loop on a deterministic failure), (c) keep
add-before-yield but discard the hash on emit failure so exactly one retry
occurs — the coordinator chose (c): it fixes the reported defect (a
transient failure is no longer permanently dropped) without introducing a
new unbounded-retry risk.

**Exact bound implemented**: at most 2 total emit attempts per result, per
stream, ever (1 initial + at most 1 retry) — via a second per-site tracking
set (`retry_attempted_hashes` / `retry_attempted_local`) recording which
hashes have already had one failed attempt; a hash's SECOND failure is left
recorded in `seen_hashes` (never discarded again), so no third attempt can
occur. Applied at both dedup sites named in the item (main polling loop and
completion-flush branch) — the completion-flush site's own second-attempt
path is honestly noted as currently dead code in practice (that branch
executes at most once per stream lifetime today), implemented anyway for
code-shape symmetry per the item's explicit "measured at both sites"
framing and defensive correctness if that control flow is ever refactored.

## Independently re-verified this session (coordinator, from a clean shell,
including a genuine paired-mutation revert/restore)

```
$ .venv/bin/python -m pytest tests/unit/test_streaming.py::TestBob193EmitFailureDedup -v --import-mode=importlib
... 4 passed in 0.94s

$ git stash push -m "coordinator-verify-bob193-mutation" -- download-proxy/src/api/streaming.py
$ .venv/bin/python -m pytest tests/unit/test_streaming.py::TestBob193EmitFailureDedup -v --import-mode=importlib
FAILED ...test_transient_emit_failure_is_retried_exactly_once_then_recovers
FAILED ...test_deterministically_failing_result_is_bounded_never_an_infinite_retry_storm
AssertionError: expected the flaky result to be emitted EXACTLY once after its one retry succeeded, got 0: []
assert 0 == 1
2 failed, 2 passed in 1.10s

$ git stash pop
$ .venv/bin/python -m pytest tests/unit/test_streaming.py::TestBob193EmitFailureDedup -v --import-mode=importlib
... 4 passed in 0.80s
```
Genuine reproduction confirmed independently — reverting the source alone
(test file untouched) reproduces the exact permanent-loss failure signature
(`0 == 1`), and restoring the fix returns to green.

```
$ .venv/bin/python -m pytest tests/unit/test_streaming.py -v --import-mode=importlib
... 32 passed in 3.08s
```
No regressions across the full streaming test file.

## Honest boundary (not silenced)

The completion-flush dedup site's own second-attempt branch is currently
unreachable in practice given today's control flow (noted above) — harmless
and correct if reached, but not independently exercised by real traffic
today; only its sibling test (`test_completion_flush_site_also_discards_hash_on_emit_failure`,
which observes exactly 1 attempt there) covers it.

## git diff --stat

```
download-proxy/src/api/streaming.py |  89 +++++++++++-
tests/unit/test_streaming.py        | 282 +++++++++++++++++++++++++++++++++++-
2 files changed, 364 insertions(+), 7 deletions(-)
```
