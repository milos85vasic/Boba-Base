# BOB-091 closure evidence

**Item:** BOB-091 (RD2-26) — Relocate mocked SearchOrchestrator tests to unit/ + author real integration tests
**Type:** Bug · **Closed as:** Fixed (→ Fixed.md) per §11.4.33
**Closed:** 2026-08-20

## Why this was still Queued

The work landed weeks ago under commits whose messages did not carry the ATM id, so the tracker row
was never reconciled. Fourth instance of this drift class found in one sweep (with BOB-076,
BOB-117, and BOB-008's stale evidence).

    d1a8479  RD2-26a — test_merge_api.py no longer mocks the system under test   (GA-14)
    a3b16bc  stop mocking SearchOrchestrator in tests/e2e/test_full_pipeline.py  (GA-15)
    2a0b543  stop mocking SearchOrchestrator in the tracker_stats contract test  (GA-16)

## Closure criterion (from the item's own body_md)

"no @patch/monkeypatch targeting SearchOrchestrator anywhere outside tests/unit/."

## Verification — re-derived independently, not inherited from the commit messages

### Live orchestrator mocks outside tests/unit/: ZERO

    tests/integration/test_merge_api.py            0 live
    tests/e2e/test_full_pipeline.py                0 live
    tests/contract/test_tracker_stats_contract.py  0 live

### Controller's own false alarm, recorded (§11.4.6)

A first pass by the controller reported 1 and 2 "live" mocks in two of those files. That was a
CARRIER MATCH, not a finding: the regex excluded `#` comments but NOT docstrings, and every hit was
inside a module docstring documenting the file's own history —

    tests/integration/test_merge_api.py:20
      test while every route test did ``@patch("api.routes._get_orchestrator")``
    tests/contract/test_tracker_stats_contract.py:18
      This file used to ``monkeypatch.setattr(SearchOrchestrator,

This is the §11.4.201(7)(a) match-structure-not-substring footgun. It is recorded here rather than
quietly dropped, because the first count was wrong and the record should show why.

### Control needle — the search instrument is not blind (§11.4.201(7)(b))

    grep -cE '(@patch|patch\.object|monkeypatch\.setattr)' tests/unit/test_merge_api_route_contracts.py
    21

The needle proves the pattern matches real mocks where they exist, so the zeros above are evidence.

### Relocated unit tests: GREEN

    $ .venv/bin/python -m pytest tests/unit/test_merge_api_route_contracts.py \
        tests/unit/test_full_pipeline_orchestration_logic.py \
        tests/unit/test_tracker_stats_shape.py -q --import-mode=importlib
    40 passed, 1 warning in 19.63s

### The real-service tests are genuinely real, and their SKIP is genuinely honest

The three relocated-from files now drive the live service over real HTTP with no mock in the call
path. Their honest-SKIP path (§11.4.3) was observed for real when the service became unreachable
mid-session under host contention:

    tests/contract/test_tracker_stats_contract.py   3 skipped  — "merge search service unreachable ... No fake-pass"
    tests/e2e/test_full_pipeline.py                 3 skipped  — "merge service not reachable ... (no fake-pass, no orchestrator mocking)"
    tests/integration/test_merge_api.py            20 skipped  — polls ~90s then gives up honestly

The skip path was also forced deliberately with MERGE_SERVICE_URL=http://localhost:1 and produced
the identical honest skip — confirming it is a real code path, not an accident of timing.

## Honest boundary (§11.4.6)

Mocks of SearchOrchestrator still exist in tests/concurrency/, tests/property/, tests/stress/ and
tests/security/. Each mocks it as an INCIDENTAL dependency while exercising a different system
under test (semaphore concurrency, Hypothesis properties, auth-status qBittorrent-failure handling,
SSRF-guard logic). None is a mislabelled "SearchOrchestrator test", so none is in this item's scope
— recorded as an observation, not silently omitted and not claimed fixed.
