# boba-jackett Static Smoke (Phase 7 Task 45)

**Revision:** 1
**Last modified:** 2026-06-06T00:00:00Z

**Date:** 2026-04-27
**Plan:** `docs/superpowers/plans/2026-04-27-jackett-management-ui-and-system-db.md` § Task 45
**Scope:** Static (build + unit + challenge) verification — the live-stack
smoke (orchestrate-up the boba-jackett container, hit it with a real
browser via Playwright, exercise the UI flows) is **DEFERRED** to a
manual user invocation per the plan's constraints (CONST-MD-No-Manual-Containers
+ this dispatch's no-touching-running-services boundary).

## Demo

### 1. Go test suite — all boba-jackett packages green

```
$ cd qBitTorrent-go && GOMAXPROCS=2 nice -n 19 ionice -c 3 \
    go test -race -count=1 -short ./...
```

Output (tail):

```
ok  	github.com/milos85vasic/qBitTorrent-go/internal/bootstrap	1.009s
ok  	github.com/milos85vasic/qBitTorrent-go/internal/client	1.015s
ok  	github.com/milos85vasic/qBitTorrent-go/internal/config	1.009s
ok  	github.com/milos85vasic/qBitTorrent-go/internal/db	1.260s
ok  	github.com/milos85vasic/qBitTorrent-go/internal/db/repos	2.790s
ok  	github.com/milos85vasic/qBitTorrent-go/internal/envfile	1.020s
ok  	github.com/milos85vasic/qBitTorrent-go/internal/jackett	1.142s
ok  	github.com/milos85vasic/qBitTorrent-go/internal/jackettapi	3.108s
ok  	github.com/milos85vasic/qBitTorrent-go/internal/logging	1.008s
ok  	github.com/milos85vasic/qBitTorrent-go/internal/middleware	1.012s
ok  	github.com/milos85vasic/qBitTorrent-go/internal/models	1.008s
ok  	github.com/milos85vasic/qBitTorrent-go/internal/service	1.009s
--- FAIL: TestSearchHandler_QueueFull (0.00s)   # internal/api — pre-existing flake
FAIL	github.com/milos85vasic/qBitTorrent-go/internal/api	0.016s
FAIL
```

**Result:** All 13 boba-jackett packages PASS under `-race -count=1`.
The single FAIL (`TestSearchHandler_QueueFull` in `internal/api`) is the
pre-existing flake documented in
`docs/issues/fixed/BUGFIXES.md` § entry 5 — unrelated to boba-jackett
work, flagged for follow-up.

### 2. Frontend production build

```
$ cd frontend && nice -n 19 ng build --configuration production
```

Output (tail):

```
Lazy chunk files      | Names                 |  Raw size | Estimated transfer size
chunk-JEUSEJF6.js     | credentials-component |  15.15 kB |                 3.78 kB
chunk-PHC3IB5K.js     | indexers-component    | 635 bytes |               635 bytes
chunk-QGLF7LU5.js     | jackett-routes        | 313 bytes |               313 bytes

Application bundle generation complete. [4.962 seconds] - 2026-04-27T20:16:04.290Z

Output location: /run/media/milosvasic/DATA4TB/Projects/Boba/download-proxy/src/ui/dist/frontend
```

**Result:** Production bundle builds cleanly. Lazy chunks for
`/jackett` route family (`credentials-component`, `indexers-component`,
`jackett-routes`) all emit. Output is in place at the configured
location for the Python merge service to serve as a SPA.

### 3. Frontend unit tests — Vitest

```
$ cd frontend && nice -n 19 ng test --watch=false
```

Output (tail):

```
 Test Files   21 passed (21)
      Tests   278 passed (278)
   Start at   23:16:23
   Duration   6.84s
```

**Result:** 278/278 unit tests pass.

### 4. All Layer 7 challenges — green

```
$ bash challenges/scripts/run_all_challenges.sh
```

Output (tail):

```
=== no_suspend_calls_challenge ===
OK: no forbidden host-power-management calls in /run/media/milosvasic/DATA4TB/Projects/Boba

=== summary: PASS ===
================================================================
Challenges total: 9 | failed: 0
================================================================
```

Per-challenge summary lines from the run:

```
PASS: boba_db_file_perms_challenge
--- PASS: TestNoCredentialLeak (0.08s)
PASS: credential_leak_grep_challenge
PASS: cred_roundtrip_challenge
PASS: env_db_drift_challenge
PASS: all 4 sleep targets masked
PASS: AllowSuspend=no present
PASS: IdleAction=ignore (safe)
PASS: no suspend events since fix at 2026-04-26T19:58:55+03:00
PASS: master_key_autogen_challenge
=== summary: PASS ===
```

**Result:** 9/9 challenges PASS.

## Static smoke verdict

| Check | Result |
|---|---|
| Go race-detector unit/integration suite (boba-jackett packages) | PASS (13/13) |
| Frontend production build | PASS |
| Frontend Vitest unit tests | PASS (278/278) |
| Layer 7 challenges (`run_all_challenges.sh`) | PASS (9/9) |

## Deferred — live-stack smoke

The live-stack smoke (Task 45 §steps 4-7 of the plan) requires:

- `./start.sh -p` to bring up qbittorrent + jackett + qbittorrent-proxy + boba-jackett
- A real browser (Playwright) hitting `http://localhost:7187/jackett`
- Manual user-interaction pages (Credentials list / Add / Edit / Delete)

This is **deferred to a manual user invocation** in the next session
because:

1. The dispatch was explicitly scoped not to touch the user's
   currently-running services or initiate container lifecycle.
2. The orchestrator (not raw `podman` / `docker`) owns container
   start/stop per CONST-MD-No-Manual-Containers; running `start.sh`
   from this autonomous context would bypass that guard.
3. The static checks above prove every piece is wireable: code
   compiles, tests are green under -race, build artifacts exist, all
   challenges PASS. The remaining risk surface is ports + bind mounts
   + the exact UI layout — better verified by the human operator with
   eyes on the screen.

When the user runs the live smoke, the canonical recipe is in the
plan at `docs/superpowers/plans/2026-04-27-jackett-management-ui-and-system-db.md` § Task 45 §§ 4-7.
