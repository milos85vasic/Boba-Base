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
  exceeds 500 ms at N=1000, or if the bypass path is not measurably
  slower than the cached path.

## `test_scaling_envelope.py` (BOB-109 close)

Added 2026-08-21. Three axes, chosen around the rate limiter rather than
into it — see `docs/testing/scaling.md` for the full rationale, measured
baselines, the RED transcript and the honest sensitivity floor.

| Test | Axis | Ladder | Limiter in the way? | Evidence |
|---|---|---|---|---|
| `TestDedupCostScaling` | dedup cost + identity vs result-set size | 100 / 200 / 400 / 800 (identity: 400; collapse: 300) | no (offline) | `docs/qa/BOB-109/dedup_identity_at_scale.json`, `dedup_collapse_identical.json` — plus `dedup_cost_scaling.json` and `dedup_latency_distribution.json`, **absent by design** (see below) |
| `TestRateLimitAdmissionEnvelope` | declared-vs-served admission ceiling | 1 request per class | the limiter **is** the subject | `docs/qa/BOB-109/rate_limit_admission_envelope.json`, `rate_limit_class_wiring.json` |
| `TestLimiterFreeConcurrencyScaleOut` | concurrency scale-out on `:7189` | 50 / 100 / 200 | no (`:7189` is unlimited) | `docs/qa/BOB-109/healthz_scale_out_curve.json` |

Two notes for anyone reading a green run:

* `test_sse_shaped_routes_serve_a_consistent_limit_class` is a
  `strict=True` **xfail** recording a real, still-open defect (**BOB-167**):
  two SSE-shaped routes serve DIFFERENT rate-limit classes.
  `/api/v1/search/stream` carries `@_rl("sse_stream")` and serves **5**;
  the sibling `/api/v1/theme/stream` carries no limiter at all and falls
  to the **120**/minute default. Which way to reconcile is an operator
  decision, so the test asserts only that the two must AGREE. It flips
  to XPASS and fails the run once they do.
* `dedup_cost_scaling.json` / `dedup_latency_distribution.json` are
  **absent by design**: their tests are quiescence-gated
  (§11.4.201(8)) and this host has not been quiet enough to produce a
  valid measurement. The files previously here were stale specimens
  from a contended run — one a span exponent of 2.1359, which violates
  the suite's own 2.10 gate. Capturing them is tracked as **BOB-170**.
* `test_boba_scaling.py`'s fan-out and SSE assertions were **tautologies**
  until this round; the fan-out one passed against a dead service. Both
  are fixed here — proof in `docs/qa/BOB-109/red_tautology_proof.txt`.

Run with `-p no:schemathesis` (unrelated pre-existing plugin import
failure on this host). If you disable plugin autoloading instead
(`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`), pass `-p timeout` too or
`pytest.mark.timeout` is silently inert. Mutation runs must set
`BOBA_SCALING_MUTATION=1` **and** redirect `EVIDENCE_DIR`; the flag
without a redirect hard-fails rather than overwriting committed
evidence.

On a contended host the two timing-derived tests SKIP (§11.4.201(8));
`test_dedup_identity_preserved_at_scale` and the collapse test are
ungated and still assert at-scale identity, so a busy run is not empty
coverage. Full rationale, measured baselines and the honest gaps:
`docs/testing/scaling.md`.
