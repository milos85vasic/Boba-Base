# BOB-094 — Tracker-fetch stress + chaos automation evidence

**Revision:** 1
**Last modified:** 2026-08-19T00:00:00Z

## Scope

`tests/stress/test_tracker_fetch_stress_chaos.py` — §11.4.85 stress + chaos
coverage for `SearchOrchestrator.fetch_torrent` (the outbound HTTP + response
classification path in `download-proxy/src/merge_service/search.py`).

## Scenarios delivered (8 + 1 meta = 9 tests, all GREEN)

### STRESS

| # | Test | Category |
|---|------|----------|
| 1 | `test_stress_sustained_100_sequential_fetches` | sustained-load — p50/p95/p99 over 100 iters |
| 2 | `test_stress_concurrent_10_parallel_no_fd_leak` | concurrent-contention — no deadlock, no fd leak |
| 3 | `test_boundary_empty_url_returns_none_or_error` | boundary — empty URL |
| 4 | `test_boundary_max_length_url_survives` | boundary — 2000-char URL |
| 5 | `test_boundary_off_by_one_content_type_edges` | boundary — CT classifier edges |

### CHAOS

| # | Test | Category |
|---|------|----------|
| 6 | `test_chaos_network_drop_20pct_categorised_as_network` | network-fault — §11.4.69 `feature_class=network` |
| 7 | `test_chaos_midflight_kill_clean_degradation` | process-death — real HTTP server killed mid-fetch |
| 8 | `test_chaos_input_corruption_malformed_response_quarantined` | input-corruption — malformed body quarantined |
| 9 | `test_section_114_85_category_map` | meta — mechanical coverage-claim assertion |

## §11.4.115 RED capture (production-mutation-driven)

**Scenarios with captured RED:** `test_chaos_input_corruption_malformed_response_quarantined`
AND `test_boundary_off_by_one_content_type_edges`.

Applied always-accept mutation to the CT/prefix classifier at
`download-proxy/src/merge_service/search.py:1893-1898`
(replaced the boolean guard with `if True:` so a malformed HTML body would be
returned to the caller). Both tests FAILED with user-observable assertion
errors proving the classifier bypass was detected — see
`evidence/red_capture_against_mutated_classifier.txt`.

Production tree restored (`git diff --stat` empty); re-ran the full suite —
9/9 GREEN — see `evidence/green_capture_after_restore.txt`.

## Evidence artefacts

`evidence/*.json` — one per scenario, written by the tests themselves via the
Python analogue of `ab_pass_with_evidence` (path exists + non-empty + parses).
Each carries `section=11.4.85`, `feature_class` per §11.4.69 taxonomy, and
user-observable metrics (latency percentiles, byte-equality, FD deltas,
error-category counts, quarantine counts).

## Discipline

- §11.4.161 rootless — no root, hermetic (in-process aiohttp stub +
  ephemeral loopback HTTP server for the mid-flight-kill scenario)
- §11.4.5 captured evidence — per-iteration latency histogram, categorised
  error counts, state deltas
- §11.4.14 chaos cleanup — `atexit` + `finally` teardown for the real HTTP
  server (no bound port left behind)
- §11.4.69 taxonomy — `feature_class` recorded per scenario
- §11.4.201 no false-null — FD-leak check honestly reports
  `unmeasurable_on_this_host` when `/proc/<pid>/fd` is unavailable
- §11.4.113 — no force-push in this delivery
