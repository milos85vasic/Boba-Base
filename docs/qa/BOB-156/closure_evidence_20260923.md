# BOB-156 closure evidence — 2026-09-23

## Root cause + fix

The BOB-145 event-loop-blocking regression guard measured `worst_gap`
(max wall-clock heartbeat gap) against a fixed absolute ceiling
(900ms→1500ms). `merge_results` never yields, so `worst_gap ≈ merge_wall`
— the ceiling was effectively an absolute wall-clock bound on
`merge_results`'s duration. Empirically measured on this host: wall-clock
time for this pure-CPU code inflates dramatically under contention from
UNRELATED processes (up to ~20x observed at 7.5x/core oversubscription),
while `time.process_time()` (actual CPU-seconds consumed) does not — the
OS scheduler time-slices the process among more competitors, stretching
wall-clock without changing the CPU work actually done. The guard was
measuring host business, not code regression — the exact "weather report"
symptom.

**Fix**: `time.process_time()`-measured CPU time is now the PRIMARY
regression gate (`MAX_MERGE_CPU_S = 1.5`, same margin logic as the
original design — >7x above worst observed contended CPU, >2x below the
pre-fix regression's CPU). The heartbeat/`worst_gap` mechanism is retained
as diagnostic evidence plus a generous 15s wall-clock backstop that only
fires on a genuinely catastrophic freeze (BOB-137 measured minutes), never
on ordinary contention. No production code changed — this was a
measurement-methodology defect in the test, not a code regression;
`deduplicator.py` confirmed byte-identical (sha256
`89b20304...df3cf8`, matching the hash cited in the original BOB-145 fix
commit) before and after.

## Independently re-verified this session (coordinator, including a
genuine paired-mutation revert/restore against the real pre-fix commit)

```
$ .venv/bin/python -m pytest tests/unit/merge_service/test_dedup_event_loop_blocking.py -v --import-mode=importlib
... 7 passed in 1.01s

$ sha256sum download-proxy/src/merge_service/deduplicator.py
89b203043e29584a565b34ca71af2f16e399ab7e1f1e011bbdb6e41a94df3cf8  (unchanged)

$ git show 0572b71^:download-proxy/src/merge_service/deduplicator.py > deduplicator.py   # revert to pre-BOB-145
$ .venv/bin/python -m pytest tests/unit/merge_service/test_dedup_event_loop_blocking.py::TestMergeResultsDoesNotBlockTheEventLoop::test_merge_does_not_starve_a_concurrent_coroutine -v --import-mode=importlib
FAILED — AssertionError: merge consumed 5551.8ms of CPU time (ceiling 1500ms) —
  this is a regression in the work merge_results does, not host contention
  ... This is the BOB-145 signature: while a merge this expensive runs,
  port 7187 answers nothing (BOB-137).

$ (restored fixed deduplicator.py, sha256 confirmed byte-identical)
$ .venv/bin/python -m pytest tests/unit/merge_service/test_dedup_event_loop_blocking.py -q --import-mode=importlib
7 passed in 1.06s
```
Genuine paired-mutation confirmed independently: reverting the real code
that BOB-145 fixed reproduces the exact CPU-time-based failure signature
the new guard is designed to catch; restoring returns to green.

## Honest boundary (not silenced, per the subagent's own report)

CPU-time-as-oracle has a measured, stated limit (~1.3-1.9x overhead even
under extreme contention, from cache/context-switch effects) — the chosen
1.5s ceiling has ample margin either side of this. Robustness across
genuinely different/slower HARDWARE (vs. contention specifically on this
one 16-core host) was argued by analogy, not independently measured on a
second machine (none available in scope).

## git diff --stat

```
tests/unit/merge_service/test_dedup_event_loop_blocking.py | 155 ++++++++++++++++++---
1 file changed, 138 insertions(+), 17 deletions(-)
```
