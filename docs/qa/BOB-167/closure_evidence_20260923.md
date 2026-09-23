# BOB-167 closure evidence — 2026-09-23

## Defect
Two Server-Sent-Events routes in `download-proxy/src/api/routes.py` — the
same expensive resource-holding shape — were asymmetrically classed:
`/search/stream/{search_id}` carried `@_rl("sse_stream")`, `/theme/stream`
carried no limiter decorator and fell through to the 120/min application
default (24x looser).

## Decision (coordinator, §11.4.101 — reversible, evidence-based)
`/theme/stream` belongs in the `sse_stream` class, matching its sibling
route's existing shape exactly.

## Fix
- `@_rl("sse_stream")` added to `/theme/stream` (routes.py:161).
- New general guard `scripts/pre_build/check_cm_sse_route_rate_limit_classed.sh`
  (+ AST-based `sse_route_rate_limit_class_analyzer.py`) enumerates every
  SSE-shaped route (both the inline `StreamingResponse(media_type=...)`
  idiom and the shared `create_streaming_response(...)` helper) and FAILs
  the build if any carries no explicit rate-limit class — so a future
  third SSE route cannot silently repeat this gap.
- Two new test files (`tests/unit/api_layer/test_bob167_sse_rate_limit_classification.py`,
  `tests/unit/api_layer/test_bob167_sse_route_rate_limit_gate.py`, 10 tests
  total) covering both routes' classification, the general gate's
  golden-good/golden-bad fixtures (6 shapes including a non-SSE
  `StreamingResponse` negative control and a zero-SSE-route ERROR-not-
  silent-PASS guard), and a permanent in-memory paired-mutation regression
  test that mechanically strips the fix and asserts the gate re-fails.

## Independent verification (coordinator, from clean shell)

### Diff scope confirmed minimal
```
download-proxy/src/api/routes.py | 11 +++++++++++
```
Plus 4 new files (gate wrapper, analyzer, 2 test files) — matches the
implementing agent's own report exactly.

### RED independently reproduced (via git stash, not trusted from report)
```
$ git stash push -m "..." -- download-proxy/src/api/routes.py
$ bash scripts/pre_build/check_cm_sse_route_rate_limit_classed.sh
FAIL(CM-SSE-ROUTE-RATE-LIMIT-CLASSED): 1 unclassed SSE-shaped route(s) of 2 resolved.
$ .venv/bin/python -m pytest tests/unit/api_layer/test_bob167_sse_rate_limit_classification.py -q
1 failed, 1 passed
$ git stash pop   # byte-identical restore confirmed via py_compile
```

### GREEN independently confirmed (unit level)
```
$ bash scripts/pre_build/check_cm_sse_route_rate_limit_classed.sh
PASS(CM-SSE-ROUTE-RATE-LIMIT-CLASSED): all 2 SSE-shaped route(s) carry an explicit rate-limit class.
$ .venv/bin/python -m pytest tests/unit/api_layer/test_bob167_sse_rate_limit_classification.py tests/unit/api_layer/test_bob167_sse_route_rate_limit_gate.py -q
10 passed
```

### LIVE RUNTIME SIGNATURE — the strongest evidence tier (§11.4.108), beyond
what the implementing agent's own scope covered:

A pre-existing `xfail(strict=True)` test
(`tests/scaling/test_scaling_envelope.py::TestRateLimitAdmissionEnvelope::test_sse_shaped_routes_serve_a_consistent_limit_class`),
authored by the coordinator when BOB-167 was originally filed, was flagged
by the implementing agent as an out-of-scope concern: its `strict=True`
marker is deliberately load-bearing (its own comment: "the moment both SSE
routes carry the same class this flips to XPASS and FAILS the run, forcing
this marker's removal"). The coordinator investigated this rather than
leaving it as a residual gap:

1. The merge service was live (curl 200) but still serving PRE-fix code —
   running the xfail test against it produced genuine `XFAIL` (not
   `XPASS`), confirming the source fix alone does not update a running
   container (the exact SOURCE→ARTIFACT→RUNTIME distinction §11.4.108
   exists to catch).
2. Reloaded via the project's own sanctioned mechanism:
   `./start.sh --reload-python` — clears `__pycache__` inside
   `qbittorrent-proxy` and restarts the container (CLAUDE.md-documented
   path, not a raw podman/docker command).
3. Verified served content matches committed code (cache-bust guard):
   `podman exec qbittorrent-proxy grep -n '@_rl("sse_stream")'
   /config/download-proxy/src/api/routes.py` → both routes confirmed
   present in the running container.
4. Re-ran the xfail test:
   ```
   FAILED ... [XPASS(strict)] BOB-167: two SSE routes, one rate-limit class...
   ```
   Genuine `XPASS(strict)` — live, runtime proof the fix works against the
   real running service, not just unit-level mocks.
5. Removed the now-obsolete `@pytest.mark.xfail(...)` decorator (its own
   documented self-clearing condition, exactly as designed) and confirmed
   the test PASSES cleanly:
   ```
   test_sse_shaped_routes_serve_a_consistent_limit_class PASSED
   ```
6. 3x determinism, live stack:
   ```
   run 1: 1 passed in 0.24s
   run 2: 1 passed in 0.26s
   run 3: 1 passed in 0.26s
   ```

## Honest boundary
Per the item's own criterion (d): no claim is made that 5/minute (or the
previous 120/minute) is itself an adequate limit value for either route in
this deployment — this closure is scoped purely to the classification
symmetry gap.

## Status
Fixed. Closed by coordinator after independent verification at BOTH the
unit-test layer AND a live-runtime-signature layer beyond the implementing
agent's own authorized scope.
