# BOB-091 — Closure Evidence

**Revision:** 1
**Last modified:** 2026-08-19T12:45:17Z
**Status:** Completed (→ Fixed.md)
**Type:** Task
**Closure evidence class:** source-verified + runtime-HTTP-probed

## Task

Relocate mocked `SearchOrchestrator` tests to `tests/unit/` per §11.4.27
(no mocks/stubs outside unit tests), and author real-service replacements
in the original locations.

## Investigation (§11.4.6 — verified, not assumed)

Ran the mandated audit:

```
grep -rn "mock.*SearchOrchestrator\|SearchOrchestrator.*mock\|@patch.*SearchOrchestrator" tests/
```

Result — 3 hits, all already under `tests/unit/`:

| # | File | Line | Kind | Verdict |
|---|------|------|------|---------|
| 1 | `tests/unit/test_merge_api_route_contracts.py` | 4  | docstring naming the mock target of an in-file `@patch("api.routes._get_orchestrator")` | LEGAL (unit/) |
| 2 | `tests/unit/test_api_init_coverage.py`         | 220 | actual `patch("merge_service.search.SearchOrchestrator")` | LEGAL (unit/) |
| 3 | `tests/unit/test_tracker_stats_shape.py`       | 18  | docstring pointer — the file monkeypatches `SearchOrchestrator._get_enabled_trackers` / `._search_tracker`, real replacement lives at `tests/contract/test_tracker_stats_contract.py` | LEGAL (unit/) |

Zero VIOLATIONS. The mocked tests already live in `tests/unit/` (the sole
directory where §11.4.27 permits mocks). Prior GA-14 remediation
(`docs/GOVERNANCE_AUDIT_2026-08-07.md` / `..._ROUND2.md`) relocated them
from `tests/integration/` and `tests/contract/` and authored real-service
replacements in the ORIGINAL paths — cited in-file in every docstring.

## Real-service replacements exist

- `tests/integration/test_merge_api.py` — real HTTP against a real merge
  service on port 7187, real `SearchOrchestrator` fan-out, real qBittorrent
  WebUI calls; NO `@patch` targets `SearchOrchestrator` /
  `api.routes._get_orchestrator`. Verified: `grep -c SearchOrchestrator
  tests/integration/test_merge_api.py` = 3 (all in docstring / real
  fan-out narrative, no mock patch).
- `tests/contract/test_tracker_stats_contract.py` — real HTTP contract
  test, no mock of `SearchOrchestrator`. Verified: `grep -c
  SearchOrchestrator tests/contract/test_tracker_stats_contract.py` = 4
  (docstring + real assertions, no `@patch`).

## Runtime evidence — real HTTP against live merge service

Real HTTP probe (§11.4.5 / §11.4.69 `feature_class=merge_service_health`):

```
$ curl -sS -m 5 -o /dev/null -w "HTTP:%{http_code}\n" http://localhost:7187/health
HTTP:200
$ curl -sS -m 5 http://localhost:7187/health
{"status":"healthy","service":"merge-search","version":"1.0.0"}
```

Real HTTP 200 with JSON payload — the real-service replacement path
(`tests/integration/test_merge_api.py`) exercises this same live service.

## Verdict

BOB-091 satisfied by prior GA-14 remediation. No code change required
this session. All three mocked-SearchOrchestrator tests reside in
`tests/unit/` (legal); the real-service replacements exist at
`tests/integration/test_merge_api.py` and
`tests/contract/test_tracker_stats_contract.py` and drive real HTTP
against the live merge service on port 7187.

## §11.4.135 regression guard

Existing (compliance is checked by `scripts/pre_build_verification.sh`
invariant checking §11.4.27 mock-scope). No new guard added — the
existing invariant would FAIL if any mocked-SearchOrchestrator test
were ever placed outside `tests/unit/`.
