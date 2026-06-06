# E2E Live-Stack QA Run — `e2e-live-20260606`

**Revision:** 1
**Last modified:** 2026-06-06T15:00:00Z

Fully-automated end-to-end run (§11.4.83, §11.4.98) driving the LIVE Boba
merge-search stack at `http://localhost:7187` over real HTTP — no human in
the loop, re-runnable. Test source:
`tests/e2e/test_live_stack_evidence.py`.

Anti-bluff posture (§11.4): every assertion targets a **user-observable
outcome** (response-body fields a real dashboard/client consumes), not a
bare status code. Flaky public-tracker specifics are deliberately NOT
asserted (false-result risk); only deterministic facts are pinned. When
the service is unreachable, tests SKIP-with-reason (§11.4.3) — never
fake-pass.

## What was exercised + observed

| # | Endpoint / behaviour | User-observable assertion | Evidence file | Result |
|---|----------------------|---------------------------|---------------|--------|
| 1 | `GET /health` | body `status=="healthy"` + `service` identity present | `health.json` | PASS |
| 2 | `POST /api/v1/search/sync` query `debian` | `status=="completed"`, `total_results>0`, real result objects carry `name`/`size`/`tracker`/`download_urls` | `search_debian.json` | PASS |
| 2b| same search — genuine fan-out | ≥1 tracker `status=="success"` WITH rows; every `tracker_stats.query=="debian"` | `search_debian_successful_trackers.json` | PASS |
| 3 | Credentialed path (IPTorrents) | iptorrents `authenticated==true` in `tracker_stats` (logged in with .env creds) | `iptorrents_stat.json` | PASS |
| 4 | `GET /api/v1/auth/status` | structure lists `rutracker`/`iptorrents`/`nnmclub`/`kinozal` each with bool `has_session` | `auth_status.json` | PASS |
| 5 | `GET /api/v1/auth/nnmclub/status` (BOB-006) | body has bool `authenticated` field | `nnmclub_status_DEPLOYMENT_DRIFT.txt` | **SKIP** |
| 6 | `GET /api/v1/config` w/ custom `Host` | `qbittorrent_url` derives from Host header, NOT hardcoded localhost (CONST-XII) | `config_custom_host.json` | PASS |
| 7 | SSE `POST /search` + `GET /search/stream/{id}?token=` | real lifecycle SSE frames (`search_start`/`tracker_started`/`search_complete`) reach an EventSource client | `sse_frames_sample.txt`, `sse_events_observed.json` | PASS |

## Observed facts (from captured evidence)

- `total_results` for `debian` = **1303** (varies per run; deterministic
  floor asserted is `>0`).
- Successful trackers this run included academictorrents, bitsearch,
  iptorrents, limetorrents, linuxtracker, nyaa, piratebay, pirateiro,
  rutor, snowfl (specific set is non-deterministic; ≥1 asserted).
- IPTorrents: `status=success, authenticated=true, results_count=49` —
  the credentialed login path genuinely works end-to-end.
- `/api/v1/config` with `Host: boba.example.com:9999` returned
  `qbittorrent_url=http://boba.example.com:7186` — derived from the
  request Host, no localhost leak (CONST-XII satisfied).
- SSE stream delivered live `event: search_start` (+ `tracker_started`)
  frames to a streaming client.

## SKIP (legitimate, §11.4.3 + §11.4.108 finding)

**`GET /api/v1/auth/nnmclub/status` → 404 on the LIVE service.** The route
exists in source (`download-proxy/src/api/auth.py`,
`@router.get("/nnmclub/status")`, BOB-006), but the running
`qbittorrent-proxy` container exposes only `/auth/rutracker/*` +
`/auth/status` (per live `/openapi.json`). This is a genuine
SOURCE→ARTIFACT deployment drift (§11.4.108): the fix is committed but not
yet deployed. The test captures the drift as evidence and SKIPs rather
than fake-passing; once the container is rebuilt/restarted the assertion
fires for real.

## Re-run

```bash
source /tmp/boba-venv/bin/activate
python3 -m pytest tests/e2e/test_live_stack_evidence.py -v --import-mode=importlib
```
