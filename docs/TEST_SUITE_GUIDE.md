# Test Suite Guide

**Revision:** 1
**Last modified:** 2026-06-06T00:00:00Z

Reference for running, writing, and interpreting tests in this repo.

## Directory layout

| Directory              | Purpose                                                          | Hermetic? |
|------------------------|------------------------------------------------------------------|-----------|
| `tests/unit/`          | Python unit tests; mock external services                        | yes       |
| `tests/unit/merge_service/` | Merge-service unit tests (deduplicator, search, classifier) | yes       |
| `tests/contract/`      | API schema / response contract checks                            | mostly    |
| `tests/integration/`   | Cross-component tests against the running stack                  | no        |
| `tests/e2e/`           | Full-browser (Playwright) and multi-service scenarios            | no        |
| `tests/concurrency/`   | Semaphore / fan-out concurrency guarantees                       | yes       |
| `tests/property/`      | Hypothesis property tests                                        | yes       |
| `tests/memory/`        | Tracemalloc / leak checks                                        | yes       |
| `tests/observability/` | Prometheus + metrics scrapes                                     | yes       |
| `tests/security/`      | Auth-bypass / CSRF protection                                    | no        |
| `tests/stress/`        | High-concurrency stress for the merge service                    | no        |
| `tests/benchmark/`     | Wall-clock performance budgets                                   | no        |
| `tests/performance/`   | Similar to benchmark, latency-focused                            | no        |

## Running tests

### Hermetic suites (fast, ~15 s total)

```bash
python3 -m pytest tests/unit tests/contract tests/concurrency tests/property \
                  tests/memory tests/observability --import-mode=importlib
```

These tests don't need any services running. Suitable for pre-commit
and CI gate.

### Live-service suites (slow, 30–90 min)

```bash
./start.sh -p            # start containers (idempotent)
python3 webui-bridge.py  # separate shell or systemd user service
SERVICE_PROBE_TIMEOUT=15 SERVICE_PROBE_RETRIES=10 \
  python3 -m pytest tests/integration tests/e2e --import-mode=importlib \
                    --timeout=300 -p no:randomly
```

The live-service fixtures in `tests/fixtures/services.py` error
(not skip) when services are down — so a failing run here means the
stack needs attention.

### Stress / benchmark / security (opt-in)

```bash
python3 -m pytest tests/stress tests/benchmark tests/security
```

These drive the service hard — don't run them on a production host.

## Test-writing rules

1. **No skips.** Every test must either pass or fail. If a test needs
   a specific service, use the matching `*_live` fixture (see
   `tests/fixtures/services.py`) — the fixture errors loudly when the
   service is down.
2. **No data-dependent conditionals.** Don't write
   `if not results: pytest.skip(...)`. Use a query guaranteed to
   return data (`"linux"`), assert on the result, or mock the
   upstream. The `no-results` branch hides breakage.
3. **Use `timeout=300`** on any blocking `/api/v1/search/sync` call
   — the fan-out can take 90–150 s under realistic load.
4. **Use `timeout=30`** on trivial GET endpoints (`/`, `/dashboard`,
   `/health`, `/api/v1/config`). They're fast on idle probes but can
   wait a few seconds when the orchestrator is busy.
5. **Use `POST /api/v1/search`** (non-blocking) if the test is about
   the async kick-off contract. Use `POST /api/v1/search/sync` if the
   test needs actual results.
6. **Generate unique magnet hashes per file** via
   `secrets.token_hex(20)`. qBittorrent rejects duplicate torrent
   adds with `Fails.` — a shared hash across tests breaks flaky.

## Error classifications

When a tracker returns zero results, the merge service now tags the
``TrackerSearchStat`` with a structured error. See
`docs/MERGE_SEARCH_DIAGNOSTICS.md` for the full classifier table —
short version:

- `upstream_http_403` / `_404` / `_timeout` — CDN / DNS issues
- `dns_failure` / `tls_failure` — domain is down
- `plugin_env_missing` / `plugin_parse_failure` / `plugin_crashed`
  — plugin-side bug (open an issue + patch the plugin)
- `deadline_timeout` — plugin ran the full 25 s with no results
- `auth_failure` / `upstream_captcha` — private-tracker login wall

Tests that search "linux" and check `tracker_stats[].error_type`
should cover at least these common cases.

## Live service toggles (env vars)

| Var                             | Default      | Effect                                  |
|---------------------------------|--------------|-----------------------------------------|
| `PUBLIC_TRACKER_DEADLINE_SECONDS` | `25`       | per-plugin deadline, clamped [5, 120]   |
| `MAX_CONCURRENT_TRACKERS`       | `5`          | per-fan-out parallel plugin limit       |
| `MAX_CONCURRENT_SEARCHES`       | `8`          | orchestrator-level search concurrency   |
| `ENABLE_DEAD_TRACKERS`          | `0`          | force dead trackers back in             |
| `SERVICE_PROBE_TIMEOUT`         | `3`          | fixture probe timeout                   |
| `SERVICE_PROBE_RETRIES`         | `5`          | fixture probe retries                   |

## Continuous integration

CI is currently manual (`./ci.sh`). Recommended gate:

1. Hermetic suites — run every push (fast, no infra dependency).
2. Integration + e2e — run nightly or pre-release (needs live stack).
3. Stress — ad-hoc (before deploys that touch the orchestrator).
