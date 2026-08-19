# tests/scaling/ — Scaling-class tests (BOB-109 / §11.4.27)

Closes the §11.4.27 mandated test-type matrix gap flagged by
BOB-074 followup: the `scaling` class had no home in the boba
`tests/` tree.

## Axes covered

| File | Axis | N range | Endpoint | Evidence |
|---|---|---|---|---|
| `test_boba_scaling.py::TestVerticalScaleSSE` | Vertical (SSE fan-in) | 1, 3, 10, 50 | `GET :7187/api/v1/theme/stream` | `docs/qa/BOB-109/sse_subscribers_matrix.json` |
| `test_boba_scaling.py::TestHorizontalScaleProxyFanOut` | Horizontal (proxy fan-out) | 1, 2, 5, 8 | `POST :7187/api/v1/search` | `docs/qa/BOB-109/proxy_fanout_matrix.json` |
| `test_boba_scaling.py::TestCacheWarming` | Cache warming (rps) | 10, 100, 500, 1000 | `GET :7189/healthz` | `docs/qa/BOB-109/cache_warming_matrix.json` |
| `test_boba_scaling.py::TestCacheWarming::test_red_capture_cache_bypass_shows_upstream_latency` | §11.4.115 RED (cache bypass) | 200 | `GET :9117/UI/Dashboard` | `docs/qa/BOB-109/red_cache_bypass.json` |

## RED-first capture (§11.4.115)

The RED test bypasses the BOB-112 TTL cache by hitting Jackett's
upstream endpoint directly — equivalent to setting the boba-jackett
`HealthDeps.CacheTTL = 0`. The captured artifact records the p50
latency + throughput ratio between the cached and bypass paths.
A speedup ratio > 1× is proof the cache is load-bearing.

## Running

```bash
python3 -m pytest tests/scaling/ -v --import-mode=importlib \
    -p no:schemathesis --timeout=240
```

Services on `:7185 / :7187 / :7189 / :9117` MUST already be up — the
suite refuses to synthesize (§11.4.6) and skips honestly when a port
is unreachable.

## Anti-bluff (§11.4 / §11.4.14 / §11.4.6)

* Every measurement is captured from a live service; nothing is
  simulated.
* Every stream response is `.close()`d in a `finally` before the
  executor exits, so the test never leaks server-side subscriber
  queues.
* Every attempted call resolves to a labeled verdict
  (`accepted` / `429` / `client_timeout` / `other`); silent drops
  are asserted absent.
* The cache-warming assertion fails LOUD if the cached-path p50
  exceeds 50 ms at N=1000, or if the bypass path is not measurably
  slower than the cached path.
