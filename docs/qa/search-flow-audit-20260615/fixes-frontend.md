# Frontend fixes — search-flow-audit-20260615 (BUG-2, BUG-5)

**Revision:** 1
**Last modified:** 2026-06-15T00:00:00Z

TDD (Vitest, §11.4.115 RED-first, §11.4.135 regression guards). Work scoped to `frontend/` only.

## BUG-2 — Dashboard SSE service never forwarded merged_update / tracker_started / tracker_completed

Root cause (confirmed in code): `EventSource` dispatches a NAMED event only to a listener registered for that exact name; unregistered named events are silently dropped (no `onmessage` fallthrough). `sse.service.ts` registered listeners for `search_start, result_found, results_update, search_complete, download_*` but NOT `merged_update`, `tracker_started`, `tracker_completed` — which the backend emits and `dashboard.component.ts` has `case` branches for (lines 367/377/380). Live de-duplicated grid + tracker chips never updated during a search.

Fix: added the 3 missing `addEventListener` registrations, mirroring the existing pattern, wired to `events$`.

## BUG-5 — API base + SSE URL hardcoded relative → remote API instance unreachable

Root cause (confirmed in code): `api.service.ts` `baseUrl = ''` and `sse.service.ts` built a relative EventSource URL (`/api/v1/search/stream/{id}`). A dashboard served from a different origin than the API hit its OWN origin, not the configured API.

Fix: new `src/app/config/api-base.ts` exporting an `API_BASE_URL` `InjectionToken` (root-provided) with a factory that resolves a runtime-configured base from `window.__BOBA_API_BASE__` or `<meta name="boba-api-base">`, defaulting to `''` (same-origin, back-compat) — no hardcoded localhost/host per CLAUDE.md. Both `ApiService` and `SseService` now `inject(API_BASE_URL)` and prefix it. SSE also sets `withCredentials` when a cross-origin base is configured.

Follow-up (NOT done here — out of frontend scope): the Python (`download-proxy`) and Go SSE routes must allow the dashboard origin in CORS (and `Access-Control-Allow-Credentials` if a token/cookie is used) for a cross-origin remote instance to actually connect. Flagged for the server layer.

## Files changed

- `frontend/src/app/config/api-base.ts` (NEW — API_BASE_URL token + resolver)
- `frontend/src/app/services/sse.service.ts` (inject base, absolute stream URL + withCredentials, 3 new listeners)
- `frontend/src/app/services/api.service.ts` (inject base instead of hardcoded '')

## RED tests added (regression guards)

- `frontend/src/app/services/sse.service.spec.ts`:
  - `forwards merged_update events to the grid/state (BUG-2 RED)`
  - `forwards tracker_started events (BUG-2 RED)`
  - `forwards tracker_completed events (BUG-2 RED)`
  - `uses the configured API base for the stream URL (BUG-5 RED)`
  - `configured base with token builds an absolute stream URL (BUG-5 RED)`
- `frontend/src/app/services/api.service.spec.ts`:
  - `search() POSTs to the configured remote API base` (BUG-5)
  - `getSearch() GETs the configured remote API base` (BUG-5)

## RED baseline (pre-fix) — 7 failures

```
 FAIL  src/app/services/sse.service.spec.ts > uses the configured API base for the stream URL (BUG-5 RED)
AssertionError: expected '/api/v1/search/stream/abc' to be 'https://remote.example:7187/api/v1/se…'
Expected: "https://remote.example:7187/api/v1/search/stream/abc"
Received: "/api/v1/search/stream/abc"
...
 Test Files  2 failed (2)
      Tests  7 failed | 30 passed (37)
```
(3 BUG-2 listener tests + 2 BUG-5 SSE-base + 2 BUG-5 API-base failed against pre-fix code.)

## GREEN (post-fix) — targeted specs

```
 RUN  v4.1.8 /Volumes/T7/Projects/boba/frontend
 Test Files  2 passed (2)
      Tests  37 passed (37)
   Duration  1.81s
```

## GREEN — full frontend suite (no regression)

```
 RUN  v4.1.8 /Volumes/T7/Projects/boba/frontend
 Test Files  29 passed (29)
      Tests  363 passed (363)
   Duration  6.86s
```
(The "Not implemented: navigation to another Document" lines are pre-existing jsdom noise from download-file tests, unrelated to this change.)
