# Boba — Feature Status Summary

**Revision:** 3
**Last modified:** 2026-06-16T11:30:00Z
**Scope:** Two-audience summary companion of `docs/features/Status.md` (§11.4.56). Page 1 = product/operator audience; Page 2 = software-engineer audience.

> Captured-evidence-driven (§11.4.5 / §11.4.45 / §11.4.56 / §11.4.86). Mirrors `Status.md` — when that file changes, regenerate this one (see `.docs_chain/contexts/features-status.yaml`).

---

## Page 1 — For the product / operator team

**What Boba does.** Boba turns qBittorrent into a multi-tracker search-and-download hub. You type one query; it searches 40+ public and private torrent trackers at once, removes duplicates, adds posters and metadata, and lets you add any result to qBittorrent with one click — from a web dashboard, from a browser extension, or via a themed WebUI proxy.

**What works today (default product — Python/FastAPI on :7187 + :7186):**
- Multi-tracker search with live streaming results, de-duplication, and metadata enrichment (posters, year, type from OMDb/TMDB/TVMaze/AniList/MusicBrainz/OpenLibrary).
- One-click add-to-qBittorrent, magnet copy/open, .torrent upload, and active-downloads view.
- The Angular dashboard (search grid, magnet dialog, theme picker, qBit login, Jackett management tabs) and the BobaLink browser extension (detects magnet/.torrent links on any page, "Send" / "Send-All" to Boba) are both shipping and heavily tested (the extension alone has 559 passing tests).
- Jackett indexers are auto-configured at startup; credentials live encrypted in a local database, edited from the dashboard's Jackett page (boba-jackett service on :7189).
- Private-tracker support (RuTracker, Kinozal, NNM-Club, IPTorrents) works through the WebUI bridge and download proxy.

**What's partial or pending:**
- **RuTracker login needs a human** — it has a CAPTCHA, so automated login is operator-assisted (paste a cookie or solve the CAPTCHA once). This is a real-world limit, not a bug.
- **A few security hardenings are queued** — some write endpoints are open by default on the LAN tunnel, and a couple of fetch paths need SSRF protection (tracked as RW-01..RW-05 in the remaining-work plan). An operator decision on LAN exposure gates how aggressive these need to be.
- **One private-tracker status route (NNM-Club)** needs a container redeploy to go live (a source-vs-running drift, RW-07).
- **The RuTracker ReDoS speed fix** is in the code but needs to be pushed into the running container (RW-06).
- **The Go backend is an opt-in preview, not the product** — it replicates the API shape but is missing real plugin search, enrichment, and a working scheduler. The Python backend is the complete one.

**What you (the operator) may need to act on:**
- Decide whether the LAN tunnel should stay open (`0.0.0.0`) or bind to localhost (RW-05).
- Solve the RuTracker CAPTCHA once when private RuTracker search is needed (BOB-008).
- Decide whether the Go profile parity is a release goal (RW-09).

**Honest note on testing depth:** every feature in this catalog is backed by a real source file and, in nearly all cases, an automated test. **A few headline flows now have real screen recordings** — the boba-ctl CLI (status/health/list) and the web dashboard search journey, tab navigation, qBit/Download buttons, theme, and Jackett credentials page (`docs/qa/recordings-20260615/`). The remaining per-feature visual confirmations are an in-progress recording pass.

---

## Page 2 — For software engineers

**Inventory method (2026-06-15, expanded 2026-06-16):** read-only codegraph + grep + source reading across the repo, then expanded to per-unit granularity (§11.4.118). **288 features cataloged** across 8 components (was 135 at Rev 2 — finer granularity, one row per real endpoint/handler/client-method/component-control/plugin/subcommand/script). Every row in `Status.md` cites a source file (file:line where load-bearing), endpoint, command, or control. No invented features (§11.4.6).

**Component / feature counts + posture:**

| Component | Path / port | Features | Posture |
|-----------|-------------|----------|---------|
| Download Proxy + Merge Search (Python/FastAPI) | `download-proxy/src` :7186/:7187 | 68 | Shipped default; nearly all tested-green-in-suite. Now itemized per route (search/auth/hooks/schedules/theme/download), per dedup tier, per enrichment source, per validator. Open gaps: hooks auth (RW-01), default-open write surface (RW-02), SSRF (RW-03), magnet auth (RW-04); validator (BEP48/15) has no dedicated test; Kinozal/IPTorrents have no REST auth route. |
| qBitTorrent-go (Go/Gin) | `qBitTorrent-go` :7186/7187/7188 opt-in | 47 | Skeleton; unit-only (go test). Itemized per handler/client-method/service. `DownloadHandler` mock-only, `ActiveDownloadsHandler` empty stub, `FetchTorrent` stub; scheduler has no driver loop (RW-10, never fires); enricher missing (RW-11); SSE broker defined-but-unwired. |
| boba-jackett (Go) | `qBitTorrent-go/cmd/boba-jackett` :7189 | 26 | Implemented; unit + integration + e2e + security (go). Itemized per endpoint + autoconfig engine/matcher/client + crypto/migrate/repos/bootstrap/envfile. Encrypted SQLite (AES-256-GCM), autoconfig, runs history, overrides, admin auth, hardened CORS. |
| Tracker plugins | `plugins/*.py` | 30 | One row per real plugin present in tree (21 with matching file) + support modules. Parser sweep stress-chaos coverage. rutracker ReDoS fix not yet deployed (RW-06). CORRECTION: `install-plugin.sh` PLUGINS array has **44 entries**, not 12; ~23 (incl. `torrentproject`/`torrentscsv`) are curated names with no file in this tree — itemized as discrepancy rows, not asserted working. |
| Angular 21 frontend | `frontend/` served :7187 | 34 | Vitest unit + Python Playwright/integration; signals-based; 40% coverage floor. Itemized per dashboard control (search/grid/5 tabs/qBit+Download/magnet/theme/auth chips), per dialog, per service, per Jackett page control. |
| BobaLink extension | `extension/` (WXT MV3) | 39 | Per `docs/browser_extension/Status.md`; unit/integration/security/chaos/perf/a11y/live; built zips present. Itemized per popup control, scanner, parser, api module, shared util, and **8 locales** (en/de/es/fr/it/ja/pt/ru). |
| WebUI bridge | `webui-bridge.py` :7188 host | 4 | Integration + stress-chaos; private-tracker auth live-gated. |
| Infra / CLI / scripts | repo root + `scripts/` | 40 | Itemized: boba-ctl 5 subcommands + wrapper, lifecycle scripts, CI/test wrappers, and the full `scripts/` helper set. CORRECTION: `boba-ctl.sh` DOES exist (`scripts/boba-ctl.sh`), Rev 2 said it did not. Several scripts un-validated (no dedicated test). |

**Key evidence anchors (file:line):**
- FastAPI routes: `download-proxy/src/api/routes.py:61-1261`, `auth.py:56-532`, `hooks.py:105-179`, `scheduler.py:39-126`, `__init__.py:168-347`.
- Orchestration: `download-proxy/src/merge_service/search.py` (semaphores, subprocess fan-out, `_classify_plugin_stderr`); `deduplicator.py` (tiered); `enricher.py:113` (6 providers); `validator.py:101/162` (BEP48/15).
- Go routes: `qBitTorrent-go/cmd/qbittorrent-proxy/main.go:54-100`; jackett `internal/jackettapi/router.go` + `*.go` handlers; `internal/db/crypto.go`, `repos/*.go`.
- Frontend: `frontend/src/app/components/{dashboard,magnet-dialog,qbit-login-dialog,theme-picker,tracker-stat-dialog}/`, `services/{api,sse,theme,toast,dialog}.service.ts`, `jackett/{credentials,indexers}/`.
- Extension: `extension/src/{api,scanner,parser,popup,options,tabgroups,shared}/`.

**Test corpus locations:** Python `tests/{unit,integration,e2e,security,stress,chaos,property,contract,concurrency,memory,observability,benchmark,performance,load,docs}/`; Go `qBitTorrent-go/internal/**/*_test.go` + `tests/{contract,e2e,integration,security}`; frontend `frontend/**/*.spec.ts` + `e2e/`; extension `extension/tests/{unit,integration,security,chaos,perf,a11y,e2e,live,i18n}`.

**Open work cross-reference:** `docs/REMAINING_WORK_PLAN.md` RW-01..RW-21 + BOB-008 (operator-blocked CAPTCHA).

**Engineering follow-ups for this doc:**
- Capture per-feature `video_display`/UI screen recordings per §11.4.107/§11.4.143 (most of the 288 rows are still `PENDING`; headline CLI + web flows are now VIDEO-CONFIRMED) — the largest remaining evidence gap.
- Confirm whether a Prometheus `/metrics` endpoint exists or stats are in-process only (`GET /api/v1/stats`) — no `Counter()/Histogram()/Gauge()` definitions found in `download-proxy/src`.
- Resolve the curated-name-vs-missing-file discrepancy for the ~23 plugins in the 44-entry `install-plugin.sh` array with no `plugins/*.py` (incl. `torrentproject`/`torrentscsv`).
- Wire the Go `DownloadHandler`/`ActiveDownloadsHandler`/`FetchTorrent` stubs + scheduler driver loop (RW-10/RW-11) before the Go profile can claim parity.
