# Boba — Feature Status Summary

**Revision:** 8
**Last modified:** 2026-08-20T12:27:23Z
**Scope:** Two-audience summary companion of `docs/features/Status.md` (§11.4.56). Page 1 = product/operator audience; Page 2 = software-engineer audience.

> Captured-evidence-driven (§11.4.5 / §11.4.45 / §11.4.56 / §11.4.86). Mirrors `Status.md` (currently Rev 9) — when that file changes, regenerate this one (see `.docs_chain/contexts/features-status.yaml`).
> **Rev 8 note (2026-08-20, BOB-083):** this summary was 65 days stale (last synced
> at `Status.md` Rev 7, 2026-06-16) while `Status.md` had advanced to Rev 9 —
> regenerated from the current `Status.md` to close that gap.

---

## Page 1 — For the product / operator team

**What Boba does.** Boba turns qBittorrent into a multi-tracker search-and-download hub. You type one query; it searches 40+ public and private torrent trackers at once, removes duplicates, adds posters and metadata, and lets you add any result to qBittorrent with one click — from a web dashboard, from a browser extension, or via a themed WebUI proxy.

**What works today (default product — Python/FastAPI on :7187 + :7186):**
- Multi-tracker search with live streaming results, de-duplication, and metadata enrichment (posters, year, type from OMDb/TMDB/TVMaze/AniList/MusicBrainz/OpenLibrary).
- One-click add-to-qBittorrent, magnet copy/open, .torrent upload, and active-downloads view.
- The Angular dashboard (search grid, magnet dialog, theme picker, qBit login, Jackett management tabs) and the BobaLink browser extension (detects magnet/.torrent links on any page, "Send" / "Send-All" to Boba) are both shipping and heavily tested. The extension's test count was re-measured live this session: **822 automated tests across 69 files, 815 currently passing** (see `docs/browser_extension/Status_Summary.md` Rev 4 for the full breakdown of the 7 not currently passing — they are timing/speed checks, not feature-broken checks, and the failure looks like normal computer-was-busy noise, not yet confirmed either way).
- Jackett indexers are auto-configured at startup; credentials live encrypted in a local database, edited from the dashboard's Jackett page (boba-jackett service on :7189).
- Private-tracker support (RuTracker, Kinozal, NNM-Club, IPTorrents) works through the WebUI bridge and download proxy.
- **Search handles multi-word queries** (fixed and live-verified 2026-06-16). A full-fleet `the matrix` search on the live stack returns **2600 results from 23 trackers with zero plugin crashes**, and **all four private trackers authenticate** (RuTracker 50, NNM-Club 50, Kinozal 50, IPTorrents 49) using operator-supplied browser cookies. Proof: `docs/qa/search-fix-verify-20260616/`.
- **Two previously-pending items are now confirmed fixed and live (2026-08-19):** the NNM-Club status indicator on the dashboard now correctly reflects real login state instead of always showing unavailable, and the RuTracker search speed fix is confirmed actually running in the live server (not just sitting in the source code unused). Both were double-checked against the real running system, not just the code.
- **A serious, unrelated background-safety bug was found and permanently fixed since the last update.** A test-cleanup routine could, under a rare condition, accidentally send a "force-quit everything" signal to the whole computer session instead of just the one process it meant to stop — this could force-close the developer's desktop session. It has been root-caused, fixed, and a permanent safeguard was added project-wide so this class of bug cannot recur silently. This does not affect end users running the product normally; it affected developers running the test suite on their own machine.

**What's partial or pending:**
- **RuTracker login** — automated cookie login now works: an operator pastes their browser cookies once (`RUTRACKER_COOKIES`) and RuTracker search authenticates without the CAPTCHA (verified live, 50 results for "the matrix"). Solving the CAPTCHA via username/password is still operator-assisted (BOB-008) — a real-world limit, not a bug.
- **Kickass torrents is permanently unavailable (won't-fix)** — every live KickassTorrents mirror is behind Cloudflare or a JavaScript bot-challenge that the search plugin (a plain non-browser fetch) cannot pass. This is an upstream anti-bot design, not a Boba bug; the plugin returns an honest empty result. Research + live proof: `docs/research/kickass_403_20260616/`.
- **A few security hardenings are queued** — some write endpoints are open by default on the LAN tunnel, and a couple of fetch paths need SSRF protection (tracked as RW-01..RW-05 in the remaining-work plan). An operator decision on LAN exposure gates how aggressive these need to be.
- ~~One private-tracker status route (NNM-Club) needs a container redeploy to go live~~ **DONE (2026-08-19) — see above.**
- ~~The RuTracker ReDoS speed fix is in the code but needs to be pushed into the running container~~ **DONE (2026-08-19) — see above.**
- **The Go backend is an opt-in preview, not the product** — it replicates the API shape but is missing real plugin search, enrichment, and a working scheduler. The Python backend is the complete one.

**What you (the operator) may need to act on:**
- Decide whether the LAN tunnel should stay open (`0.0.0.0`) or bind to localhost (RW-05).
- Solve the RuTracker CAPTCHA once when private RuTracker search is needed (BOB-008).
- Decide whether the Go profile parity is a release goal (RW-09).

**Honest note on testing depth:** every feature in this catalog is backed by a real source file and, in nearly all cases, an automated test. `Status.md` now catalogs **292 rows** (unchanged this pass — only 2 rows' correctness was updated, no rows added/removed). Its own per-row video tally (291 of the 292 rows; a 1-row pre-existing count discrepancy `Status.md` itself flags and has not yet resolved) is: **28 VIDEO-CONFIRMED** — shown on-screen in a committed recording (the boba-ctl CLI status/health/list, the web dashboard search journey + tab navigation + qBit/Download buttons + theme + processing spinner + bridge/qBit-Connected header indicator + Jackett credentials page & Add-credential dialog, and the BobaLink extension scan/popup/options) (`docs/qa/recordings-20260615/`); **249 N/A (no UI)** — back-end endpoints, handlers, parsers, services and scripts that have no screen of their own and are confirmed by their tests plus the UI/CLI journey that drives them; **14 PENDING (UI — film next)** — user-visible dialogs/controls (magnet dialog, qBit login dialog [can't be shown without logout — qBit is already connected], confirm/tracker-stat dialogs, the Jackett indexer dialogs/tabs) not yet *individually* filmed. The 14 PENDING-UI items are the remaining visual-confirmation pass. **Not re-verified this pass:** the other ~289 pre-existing rows were not re-checked against the ~161 commits that landed since the last full pass (2026-08-18) — see the engineering note below.

---

## Page 2 — For software engineers

**Inventory method (2026-06-15, expanded 2026-06-16):** read-only codegraph + grep + source reading across the repo, then expanded to per-unit granularity (§11.4.118). **292 features cataloged** across 8 components (Rev 8: +3 new host-script rows — `scripts/load-tracker-cookies.sh`, `scripts/boba-svc.sh`, `scripts/commit-push-all.sh`; Rev 7: +1 new `/api/v1/healthz` endpoint; was 135 at Rev 2 — finer granularity, one row per real endpoint/handler/client-method/component-control/plugin/subcommand/script). Every row in `Status.md` cites a source file (file:line where load-bearing), endpoint, command, or control. No invented features (§11.4.6).

**Rev 9 delta (2026-08-20, BOB-083 / RD2-16) — 2 rows corrected with live evidence, 0 rows added:**
- `GET /auth/nnmclub/status` (§1b): `partial — 404 (RW-07)` → **`PASS — LIVE 2026-08-19`** (`7baef2b`, BOB-092): the e2e's SKIP-on-404 fallback was removed after a live probe post-`./start.sh -p` confirmed HTTP 200 with `authenticated:bool`; evidence `docs/qa/2026-08-19-bob-092/nnmclub_status_probe_post_removal.txt`. RW-07 is CLOSED.
- `rutracker.py` (§4b): `ReDoS fix not yet deployed (RW-06)` → **`PASS — LIVE 2026-08-19`** (`1c0389a`, BOB-093): the bounded `{0,512}` regex confirmed present (sha256-pinned) in the deployed container copy, RED-mutated unsafe form correctly flagged, live search smoke HTTP 200. RW-06 is CLOSED. Challenge: `challenges/scripts/rutracker_redos_regex_bounds_challenge.sh` (self-validated, §11.4.107(10)).
- The other 161 commits in the `e6162f7..HEAD` range (2026-08-18→2026-08-20) are almost entirely the **BOB-126 killpg forced-logout incident chain** (`os.killpg(pgid, SIGKILL)` on an unvalidated `pgid` — a `MagicMock`-default `pid=1` propagated to `os.getpgid(1)==1` → `kill(-1, SIGKILL)`, force-killing every UID-1000 process; root-caused, fixed at `ad4b46a`, new universal constitution anchor **§11.4.263**) plus its surrounding gate/test/quality hardening (BOB-127..135). Process-safety and CI-discipline work, not a new product feature — no new rows minted from that set. `extension/`'s own 3-commit delta in the same window is covered separately in `docs/browser_extension/Status_Summary.md` Rev 4.

**Component / feature counts + posture:**

| Component | Path / port | Features | Posture |
|-----------|-------------|----------|---------|
| Download Proxy + Merge Search (Python/FastAPI) | `download-proxy/src` :7186/:7187 | 69 | Shipped default; nearly all tested-green-in-suite. Multi-word URL-encoding fix + cookie auth PROVEN live on nezha (2600 results / 23 trackers / 0 encoding crashes; rutracker/nnmclub/kinozal/iptorrents 50/50/50/49). **Rev 9: `/auth/nnmclub/status` RW-07 drift CLOSED live (BOB-092).** `GET /api/v1/healthz` JSON endpoint (`routes.py:37`). Open gaps: hooks auth (RW-01), default-open write surface (RW-02), SSRF (RW-03), magnet auth (RW-04); validator (BEP48/15) has no dedicated test; Kinozal/IPTorrents have no REST auth route. |
| qBitTorrent-go (Go/Gin) | `qBitTorrent-go` :7186/7187/7188 opt-in | 47 | Skeleton; unit-only (go test). Itemized per handler/client-method/service. `DownloadHandler` mock-only, `ActiveDownloadsHandler` empty stub, `FetchTorrent` stub; scheduler has no driver loop (RW-10, never fires); enricher missing (RW-11); SSE broker defined-but-unwired. |
| boba-jackett (Go) | `qBitTorrent-go/cmd/boba-jackett` :7189 | 26 | Implemented; unit + integration + e2e + security (go). Itemized per endpoint + autoconfig engine/matcher/client + crypto/migrate/repos/bootstrap/envfile. Encrypted SQLite (AES-256-GCM), autoconfig, runs history, overrides, admin auth, hardened CORS. |
| Tracker plugins | `plugins/*.py` | 30 | One row per real plugin present in tree (21 with matching file) + support modules. Parser sweep stress-chaos coverage. Multi-word URL-encoding fix live-verified; rutracker/nnmclub/kinozal/iptorrents auth PASS live (50/50/50/49); `kickass.py` reclassified Won't-fix structurally-impossible (§11.4.112, Cloudflare/JS-challenge). **Rev 9: rutracker ReDoS deploy RW-06 CLOSED live (BOB-093).** CORRECTION: `install-plugin.sh` PLUGINS array has **44 entries**, not 12; ~23 (incl. `torrentproject`/`torrentscsv`) are curated names with no file in this tree — itemized as discrepancy rows, not asserted working. |
| Angular 21 frontend | `frontend/` served :7187 | 34 | Vitest unit + Python Playwright/integration; signals-based; 40% coverage floor. Itemized per dashboard control (search/grid/5 tabs/qBit+Download/magnet/theme/auth chips), per dialog, per service, per Jackett page control. |
| BobaLink extension | `extension/` (WXT MV3) | 39 | Per `docs/browser_extension/Status.md` (Rev 16) / `Status_Summary.md` (Rev 4); unit/integration/security/chaos/perf/a11y/i18n/e2e/live. **Re-measured live 2026-08-20: 822 tests / 69 spec files, 815 passing** (up from the 559/52 baseline this summary previously cited — see the companion doc for the full analysis of the 7 currently-not-passing timing tests). Itemized per popup control, scanner, parser, api module, shared util, and **8 locales** (en/de/es/fr/it/ja/pt/ru). |
| WebUI bridge | `webui-bridge.py` :7188 host | 4 | Integration + stress-chaos; private-tracker auth live-gated. |
| Infra / CLI / scripts | repo root + `scripts/` | 43 | Itemized: boba-ctl 5 subcommands + wrapper, lifecycle scripts, CI/test wrappers, and the full `scripts/` helper set. Rev 8 added 3 rows: `load-tracker-cookies.sh` (tracker-cookies autoload), `boba-svc.sh` (sudo-free systemd wrapper), `commit-push-all.sh` (§11.4.234 dedicated commit/push entrypoint). Several scripts un-validated (no dedicated test). |

**Key evidence anchors (file:line):**
- FastAPI routes: `download-proxy/src/api/routes.py:61-1261`, `auth.py:56-532`, `hooks.py:105-179`, `scheduler.py:39-126`, `__init__.py:168-347`.
- Orchestration: `download-proxy/src/merge_service/search.py` (semaphores, subprocess fan-out, `_classify_plugin_stderr`); `deduplicator.py` (tiered); `enricher.py:113` (6 providers); `validator.py:101/162` (BEP48/15).
- Go routes: `qBitTorrent-go/cmd/qbittorrent-proxy/main.go:54-100`; jackett `internal/jackettapi/router.go` + `*.go` handlers; `internal/db/crypto.go`, `repos/*.go`.
- Frontend: `frontend/src/app/components/{dashboard,magnet-dialog,qbit-login-dialog,theme-picker,tracker-stat-dialog}/`, `services/{api,sse,theme,toast,dialog}.service.ts`, `jackett/{credentials,indexers}/`.
- Extension: `extension/src/{api,scanner,parser,popup,options,tabgroups,shared,background}/`.
- BOB-126 killpg fix: `merge_service` guard code + §11.4.263 (constitution anchor), evidence under `docs/incidents/` and the DB entries for BOB-124/125/126.

**Test corpus locations:** Python `tests/{unit,integration,e2e,security,stress,chaos,property,contract,concurrency,memory,observability,benchmark,performance,load,docs}/`; Go `qBitTorrent-go/internal/**/*_test.go` + `tests/{contract,e2e,integration,security}`; frontend `frontend/**/*.spec.ts` + `e2e/`; extension `extension/tests/{unit,integration,security,chaos,perf,a11y,e2e,live,i18n}`.

**Open work cross-reference:** `docs/REMAINING_WORK_PLAN.md` RW-01..RW-21 + BOB-008 (operator-blocked CAPTCHA). **RW-06 and RW-07 are now CLOSED (2026-08-19, see Rev 9 delta above) — `docs/REMAINING_WORK_PLAN.md` itself was NOT edited by this pass** (out of this task's owned-file scope; a follow-up should update that plan doc's own RW-06/RW-07 entries to match). Live-verified fix batch: `docs/qa/search-fix-verify-20260616/` (search/auth) + `docs/research/kickass_403_20260616/` (kickass won't-fix) + `docs/qa/BOB-093/` (RW-06) + `docs/qa/2026-08-19-bob-092/` (RW-07); commits `137d7ff`/`da7d709`/`2fc29fc`/`9c2f8dc`/`7e9cab5`/`1c0389a`/`7baef2b`.

**Engineering follow-ups for this doc:**
- The Video column is DEFINITIVE for 291 of 292 rows (28 VIDEO-CONFIRMED / 14 PENDING-UI / 249 N/A-no-UI; `Status.md` itself flags an unresolved 1-row count discrepancy from Rev ≤7, not reconciled by this pass). Remaining UI evidence gap = the 14 `PENDING (UI — film next)` rows (magnet/qBit-login/confirm/tracker-stat dialogs + Jackett indexer dialogs/tabs); film those per §11.4.107/§11.4.143 to close it. The 249 N/A rows are back-end/script units with no screen of their own (test-covered + exercised by the confirmed UI/CLI journeys) — not a recording gap.
- **Owed from this pass:** a full per-unit re-audit of the ~290 pre-existing rows against the 161-commit delta (2026-08-18→2026-08-20) was judged out of scope for this staleness-catch-up (§11.4.6 option B, same discipline as Rev 7→8). `docs/REMAINING_WORK_PLAN.md`'s own RW-06/RW-07 entries still read PARTIAL/UNVERIFIABLE and need a follow-up edit to match this doc's now-CLOSED status for both.
- Confirm whether a Prometheus `/metrics` endpoint exists or stats are in-process only (`GET /api/v1/stats`) — no `Counter()/Histogram()/Gauge()` definitions found in `download-proxy/src`.
- Resolve the curated-name-vs-missing-file discrepancy for the ~23 plugins in the 44-entry `install-plugin.sh` array with no `plugins/*.py` (incl. `torrentproject`/`torrentscsv`).
- Wire the Go `DownloadHandler`/`ActiveDownloadsHandler`/`FetchTorrent` stubs + scheduler driver loop (RW-10/RW-11) before the Go profile can claim parity.
- Confirm (in isolation, on a quiet host) whether the 7 currently-failing BobaLink extension timing/perf/stress tests are pure host-contention flakiness or a genuine new regression — not resolved by this pass (see `docs/browser_extension/Status_Summary.md` Rev 4).
