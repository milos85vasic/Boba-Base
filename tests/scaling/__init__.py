"""Scaling-class tests for boba (BOB-109).

Closes the §11.4.27 test-type matrix gap flagged by BOB-074 followup: the
mandated `scaling` class had no home.

Axes:

* **Vertical scale** — one process, growing subscriber fan-in on the
  SSE endpoint (`/api/v1/theme/stream`).
* **Horizontal scale (proxy fan-out)** — one client-facing endpoint
  (`/api/v1/search`) fanning out to N tracker plugins in parallel.
* **Cache warming** — `/healthz` on boba-jackett (7189) at rising rps,
  proving the BOB-112 TTL cache holds. RED capture bypasses the cache
  by hitting the upstream Jackett endpoint directly (what /healthz
  degrades to when the cache TTL is 0).

Every test emits a machine-readable evidence artifact under
`docs/qa/BOB-109/` per §11.4.5/§11.4.69 and cleans up on every exit
path per §11.4.14.
"""
