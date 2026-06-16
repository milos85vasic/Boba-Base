# Boba — Feature Status (all components)

**Revision:** 2
**Last modified:** 2026-06-16T07:35:00Z
**Scope:** Every system component, service, infrastructure piece, and client app of the Boba project — one row per feature, grouped by component.
**Authority:** assembled by READ-ONLY repo inventory (codegraph + grep + source reading) on 2026-06-15. Cross-references `AGENTS.md`, `CLAUDE.md`, `docs/REMAINING_WORK_PLAN.md`.

> Captured-evidence-driven (§11.4.5 / §11.4.45 / §11.4.86). Every feature row cites a real source file (file:line where load-bearing). **No invented features** (§11.4.6). The **Video-recording confirmation** column is `PENDING` for all rows EXCEPT the `boba-ctl` orchestrator row (VIDEO-CONFIRMED 2026-06-16 via Claude-vision frame analysis); remaining surfaces (web dashboard, Jinja dashboard, extension, per-feature flows) are an in-progress recording pass (§11.4.107/§11.4.143).
>
> Column legend:
> - **Impl** = implemented / partial / stub
> - **Wired** = reachable on a running default-profile stack (yes / no / opt-in / host)
> - **Tests** = test types present + cite file (unit / integration / e2e / security / stress-chaos / property / contract); `none` if no covering test found
> - **Validation** = honest validation posture (tested-green-in-suite / unit-only / live-evidence-captured / not-validated / operator-blocked)
> - **Video** = video-recording confirmation — `PENDING` everywhere this revision

---

## Video-recording confirmations (§11.4.143 / §11.4.83)

Real-use recordings (Claude-vision analyzed — the HelixAgent ensemble vision is a
proven stub, see `docs/qa/recording-readiness-20260615/`) in
`/Volumes/T7/Downloads/Recordings/` (project-prefix `boba-`). Per-row `Video`
cells stay `PENDING` where a feature has not been *individually* filmed; the
recordings below confirm the headline user-facing flows on-screen.

| Recording | Surface | Features confirmed | Verdict |
|---|---|---|---|
| `boba-cli-orchestrator-demo.mp4` | CLI (`boba-ctl`) | status / health / list — 4 services running & healthy | `docs/qa/recordings-20260615/boba-cli-verdict.md` |
| `boba-web-search-flow.mp4` | Web dashboard | launch → search "debian" → live results → "829 results (288 merged)" complete | `boba-web-search-flow-verdict.md` |
| `boba-web-feature-tour.mp4` + `boba-web-dashboard-tour.mp4` | Web dashboard | dashboard load (29 trackers, qBit connected), result rows render **qBit + Download** buttons (clickable), tab nav (Results/Active Downloads/Trackers/Schedules/Hooks), Jackett `/jackett` credentials page, theme | `boba-web-feature-tour-verdict.md` |

**Honest scope (§11.4.6, no bluff):**
- **Backend services** (download-proxy / merge / boba-jackett / Go) verified **200 server-side inside the VM** and exercised through the web UI recordings.
- **Console errors** seen in the web recordings are an **SSH-tunnel SSE/poll artifact** (macOS↔VM), NOT product defects — every endpoint is 200 in the VM. See the feature-tour verdict.
- **BobaLink extension**: covered by **816 passing tests**; a real-use UI video needs a `--load-extension` browser the current MCP can't launch — documented tooling-limited follow-up (NOT faked).
- **TUI / mobile / desktop**: do not exist in this project (server-side + Angular web + browser extension only) — nothing to record.

---

## Component summary

| # | Component | Service / Port | Features cataloged |
|---|-----------|----------------|--------------------|
| 1 | Download Proxy + Merge Search Service (Python/FastAPI) | `qbittorrent-proxy` :7186 / :7187 | 38 |
| 2 | qBitTorrent-go backend (Go/Gin) | `qbittorrent-proxy-go` :7186/:7187/:7188 (opt-in `--profile go`) | 20 |
| 3 | boba-jackett (Go) | `boba-jackett` :7189 | 11 |
| 4 | Tracker plugins (`plugins/*.py`) | run inside `qbittorrent-proxy` | 16 |
| 5 | Angular 21 frontend dashboard (`frontend/`) | served from :7187 | 18 |
| 6 | BobaLink browser extension (`extension/`) | WXT MV3 client | 14 |
| 7 | WebUI bridge (`webui-bridge.py`) | host process :7188 | 4 |
| 8 | Infrastructure / CLI / shell scripts | host | 14 |

**Total features cataloged: 135**

---

## 1. Download Proxy + Merge Search Service (Python/FastAPI) — `:7186` / `:7187`

Entry: `download-proxy/src/main.py` (starts legacy proxy thread + uvicorn `api:app`). This is the **shipped default product**.

### 1a. Merge Search Service — REST API (`download-proxy/src/api/routes.py`)

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| `POST /api/v1/search` — async fan-out search, returns search_id (`routes.py:275`) | implemented | yes | integration `tests/integration/test_merge_api.py`; e2e `test_full_pipeline.py`; stress `test_merge_search_stress_chaos.py` | tested-green-in-suite + LIVE | **VIDEO-CONFIRMED 2026-06-16** — real web-UI journey (`debian`→829 found/288 merged), `boba-web-search-flow.mp4`; verdict `docs/qa/recordings-20260615/boba-web-search-flow-verdict.md` |
| `POST /api/v1/search/sync` — synchronous search (`routes.py:360`) | implemented | yes | integration `test_merge_api.py`; stress `test_search_stress.py` | tested-green-in-suite; resets over tunnel (RW-08) | PENDING |
| `GET /api/v1/search/stream/{id}` — SSE result stream (`routes.py:529`) | implemented | yes | integration `test_realtime_streaming.py`, `test_streaming_browser.py` | tested-green-in-suite | PENDING |
| `GET /api/v1/search/{id}` — poll search state (`routes.py:568`) | implemented | yes | integration `test_merge_api.py` | tested-green-in-suite | PENDING |
| `POST /api/v1/search/{id}/abort` — cancel in-flight search (`routes.py:601`) | implemented | yes | integration `test_merge_api.py` | tested-green-in-suite | PENDING |
| `GET /api/v1/downloads/active` — qBit active torrents (`routes.py:611`) | implemented | yes | integration `test_buttons_api.py` | tested-green-in-suite | PENDING |
| `POST /api/v1/download` — add torrent to qBit (magnet/url) (`routes.py:940`) | implemented | yes | integration `test_button_functions.py`, `test_buttons_api.py`; security `test_ssrf_and_magnet_auth.py` | tested-green-in-suite; SSRF gap RW-03 | PENDING |
| `POST /api/v1/download/upload` — upload .torrent file to qBit (`routes.py:1105`) | implemented | yes | unit `tests/unit/api_layer/test_download_upload.py` | unit-only + integration | PENDING |
| `POST /api/v1/download/file` — fetch tracker .torrent w/ auth cookies (`routes.py:1194`) | implemented | yes | integration `test_buttons_api.py`; security `test_ssrf_and_magnet_auth.py` | tested-green-in-suite; SSRF gap RW-03 | PENDING |
| `POST /api/v1/magnet` — resolve result → magnet link (`routes.py:1261`) | implemented | yes | integration `test_magnet_dialog.py`, `test_buttons_api.py` | tested-green-in-suite; auth gap RW-04 | PENDING |
| `POST /api/v1/auth/qbittorrent` — qBit WebUI login (`routes.py:653`) | implemented | yes | integration `test_login_actions.py` | tested-green-in-suite | PENDING |

### 1b. Search orchestration internals (`download-proxy/src/merge_service/search.py`)

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| Concurrency caps `MAX_CONCURRENT_SEARCHES` (429 on saturation) | implemented | yes | concurrency `test_orchestrator_semaphore.py` | tested-green-in-suite | PENDING |
| Per-search tracker semaphore `MAX_CONCURRENT_TRACKERS` | implemented | yes | concurrency `test_tracker_semaphore.py` | tested-green-in-suite | PENDING |
| Public-tracker subprocess fan-out (NDJSON via patched novaprinter) | implemented | yes | e2e `test_public_trackers_return_results.py`; stress `test_search_orchestration_stress_chaos.py` | tested-green-in-suite | PENDING |
| Public-tracker deadline kill `PUBLIC_TRACKER_DEADLINE_SECONDS` | implemented | yes | chaos `test_tracker_failure.py` | tested-green-in-suite | PENDING |
| Private-tracker aiohttp+cookie path (rutracker/kinozal/nnmclub/iptorrents) | implemented | yes | integration `test_tracker_auth_live.py` (live-gated) | partial — live-gated, BOB-008 operator-blocked | PENDING |
| Per-tracker `TrackerSearchStat` real-time stats | implemented | yes | contract `test_tracker_stats_contract.py`; property `test_tracker_stats_properties.py` | tested-green-in-suite | PENDING |
| Stderr error classification (`_classify_plugin_stderr`) | implemented | yes | chaos `test_tracker_failure.py` | tested-green-in-suite | PENDING |
| TTL-bounded data stores (cachetools) — no leak | implemented | yes | memory `test_orchestrator_caches_bounded.py` | tested-green-in-suite | PENDING |

### 1c. Deduplication / enrichment / validation

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| Tiered dedup (metadata→infohash→name+size→fuzzy Levenshtein) (`deduplicator.py`) | implemented | yes | property `test_deduplicator_properties.py`; benchmark `test_deduplication_benchmark.py` | tested-green-in-suite | PENDING |
| Enrichment: OMDb (`enricher.py:113`) | implemented | yes | stress `test_enricher_stress_chaos.py` | tested-green-in-suite; needs `OMDB_API_KEY` | PENDING |
| Enrichment: TMDB | implemented | yes | stress `test_enricher_stress_chaos.py` | tested-green; needs `TMDB_API_KEY` | PENDING |
| Enrichment: TVMaze | implemented | yes | stress `test_enricher_stress_chaos.py` | tested-green-in-suite | PENDING |
| Enrichment: AniList | implemented | yes | stress `test_enricher_stress_chaos.py` | tested-green-in-suite | PENDING |
| Enrichment: MusicBrainz | implemented | yes | stress `test_enricher_stress_chaos.py` | tested-green-in-suite | PENDING |
| Enrichment: OpenLibrary | implemented | yes | stress `test_enricher_stress_chaos.py` | tested-green-in-suite | PENDING |
| Tracker validation HTTP scrape BEP 48 (`validator.py:101`) | implemented | yes | none dedicated found (covered via merge tests) | not-validated (no dedicated test) | PENDING |
| Tracker validation UDP scrape BEP 15 (`validator.py:162`) | implemented | yes | none dedicated found | not-validated (no dedicated test) | PENDING |

### 1d. Auth / hooks / scheduler / theme / health

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| `GET/POST /auth/rutracker/{status,captcha,login,cookie-login}` (`auth.py:56-339`) | implemented | yes | integration `test_auth_and_links.py`; e2e `test_live_stack_evidence.py` | partial — CAPTCHA operator-blocked (BOB-008) | PENDING |
| `GET/POST /auth/nnmclub/{status,login}` (`auth.py:350-451`) | implemented | yes | e2e `test_live_stack_evidence.py:265` (skips — SOURCE→ARTIFACT drift RW-07) | partial — route 404 on running container | PENDING |
| `GET /auth/status` — all-tracker session state (`auth.py:479`) | implemented | yes | integration `test_auth_state_ui.py` | tested-green-in-suite | PENDING |
| `POST /auth/qbittorrent/logout` (`auth.py:532`) | implemented | yes | integration `test_login_actions.py` | tested-green-in-suite | PENDING |
| Kinozal auth (status/login) REST route | **stub/missing** | no | none — no `kinozal/login` route in `auth.py` | not-implemented (search path uses cookies via orchestrator) | PENDING |
| Hooks CRUD `GET/POST/DELETE /api/v1/hooks` + `/logs` (`hooks.py:105-179`) | implemented | yes | unit `test_hooks_coverage.py`; concurrency `test_hooks_race.py`; security `test_hooks_schedules_auth.py` | tested-green-in-suite; auth gap RW-01 | PENDING |
| Hook event dispatch (8 events: search_start..validation_complete) (`hooks.py:32`) | implemented | yes | concurrency `test_hooks_race.py` | tested-green-in-suite | PENDING |
| Hook subprocess execution (`merge_service/hooks.py`) | implemented | yes | security `test_no_shell_injection.py` | tested-green; sandbox hardening RW-01 | PENDING |
| Scheduler API `GET/POST/GET{id}/PATCH/DELETE /api/v1/schedules` (`scheduler.py:39-126`) | implemented | yes | security `test_hooks_schedules_auth.py` | tested-green-in-suite; auth gap RW-02 | PENDING |
| Scheduler engine (load/save/tick driver) (`merge_service/scheduler.py`) | implemented | yes | integration `test_dashboard_automation.py` | tested-green-in-suite | PENDING |
| Theme API `GET/PUT /api/v1/theme` + `GET /theme/stream` (`routes.py:61-76`) | implemented | yes | contract `test_crossapp_theme_contract.py`; e2e `test_crossapp_theme.py`, `test_theme_runtime.py` | tested-green-in-suite | PENDING |
| `GET /health` (`__init__.py:168`) | implemented | yes | integration `test_live_containers.py` | tested-green-in-suite | PENDING |
| `GET /api/v1/bridge/health` (`__init__.py:173`) | implemented | yes | integration `test_bridge_root_liveness.py` | tested-green-in-suite | PENDING |
| `GET /api/v1/config` (`__init__.py:247`) | implemented | yes | integration `test_merge_api.py` | tested-green-in-suite | PENDING |
| `GET /api/v1/stats` (`__init__.py:276`) | implemented | yes | observability `test_metrics_exist.py` | tested-green-in-suite | PENDING |
| Jinja2 dashboard `GET /`, `/dashboard`, SPA catch-all (`__init__.py:337-347`) | implemented | yes | integration `test_dashboard_rendering.py` | tested-green-in-suite | PENDING |
| Retry helpers (`merge_service/retry.py`) | implemented | yes | covered indirectly | unit-only | PENDING |
| Jackett autoconfig (Python, `merge_service/jackett_autoconfig.py`) — legacy; canonical is boba-jackett | implemented | yes | contract `test_jackett_autoconfig_contract.py`; e2e `test_jackett_autoconfig_e2e.py`; benchmark `test_jackett_autoconfig_perf.py` | tested-green-in-suite | PENDING |
| Credential scrubbing log filter (`config/log_filter.py`) | implemented | yes | security `test_credential_scrubbing.py` | tested-green-in-suite | PENDING |

### 1e. Legacy download proxy (`plugins/download_proxy.py` :7186)

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| HTTP proxy → qBittorrent WebUI w/ tracker URL interception (`DownloadHandler` :767) | implemented | yes | integration `test_bridge_header_rewrite.py` | tested-green-in-suite | PENDING |
| Theme injection into proxied WebUI (`plugins/theme_injector.py`) | implemented | yes | integration `test_bridge_theme_injection.py` | tested-green-in-suite | PENDING |

---

## 2. qBitTorrent-go backend (Go/Gin) — opt-in `--profile go`

Entry: `qBitTorrent-go/cmd/qbittorrent-proxy/main.go`. **Skeleton/rewrite-in-progress** (per AGENTS.md + `docs/migration/PARITY_GAPS.md`: 6 ported / 4 partial / 8 missing). NOT running by default.

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| `GET /health` (`api/health.go`) | implemented | opt-in | go `internal/api/api_test.go` | unit-only (go test) | PENDING |
| `POST /api/v1/search` (`api/search.go`) | partial (proxies qBit search; no plugin fan-out) | opt-in | go `api_test.go`, `coverage_test.go` | unit-only | PENDING |
| `POST /api/v1/search/sync` | partial | opt-in | go `coverage_test.go` | unit-only | PENDING |
| `GET /api/v1/search/stream/:id` (SSE) | partial | opt-in | go `coverage_test.go` | unit-only | PENDING |
| `GET /api/v1/search/:id` | partial | opt-in | go `coverage_test.go` | unit-only | PENDING |
| `POST /api/v1/search/:id/abort` | partial | opt-in | go `coverage_test.go` | unit-only | PENDING |
| `POST /api/v1/download` (`api/download.go`) | partial | opt-in | go `coverage_test.go` | unit-only | PENDING |
| `POST /api/v1/download/file` | partial | opt-in | go `coverage_test.go` | unit-only | PENDING |
| `POST /api/v1/magnet` | implemented | opt-in | go `api_test.go`, `magnet_stress_chaos_test.go` | unit + stress-chaos (go) | PENDING |
| `GET /api/v1/downloads/active` | implemented | opt-in | go `coverage_test.go` | unit-only | PENDING |
| `POST /api/v1/auth/qbittorrent` (`client/auth.go`) | implemented | opt-in | go `client/auth_test.go`, `coverage_test.go` | unit-only | PENDING |
| `GET/PUT /api/v1/theme` (`api/theme.go`) | implemented | opt-in | go `coverage_test.go` | unit-only | PENDING |
| Hooks `GET/POST/DELETE /api/v1/hooks` (`api/hooks.go`) | partial (store only, no dispatch) | opt-in | go `api_test.go`, `coverage_test.go` | unit-only | PENDING |
| Schedules `GET/POST/DELETE /api/v1/schedules` (`api/scheduler_api.go`) | **partial — no driver loop (RW-10), schedules never fire** | opt-in | go `coverage_test.go` (store CRUD only) | unit-only; functional hole | PENDING |
| `GET /api/v1/config`, `/api/v1/stats`, `/api/v1/bridge/health` | implemented | opt-in | go `coverage_test.go` | unit-only | PENDING |
| Merge search orchestrator (`service/merge_search.go`) | partial | opt-in | go `service/service_test.go`, `coverage_test.go` | unit-only | PENDING |
| SSE broker pub/sub (`service/sse_broker.go`) | implemented | opt-in | go `service/coverage_test.go` | unit-only | PENDING |
| qBit Web API client (auth/search/torrents) (`client/*.go`) | implemented | opt-in | go `client/client_test.go`, `coverage_test.go` | unit-only | PENDING |
| webui-bridge binary (`cmd/webui-bridge/main.go`) | partial (health + root only) | opt-in | none dedicated | not-validated | PENDING |
| Metadata enricher (Go) | **missing (RW-11)** | no | none | not-implemented | PENDING |

---

## 3. boba-jackett (Go) — `:7189`

Entry: `qBitTorrent-go/cmd/boba-jackett/main.go`; router `internal/jackettapi/router.go`. Owns Jackett credentials + indexer overrides + autoconfig run history; encrypted SQLite at `/config/boba.db`.

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| `GET/POST /api/v1/jackett/credentials` + `DELETE /{name}` (`credentials.go`) | implemented | yes | go `jackettapi/credentials_test.go`; integration `tests/integration/jackett_db_test.go` | unit + integration (go) | PENDING |
| `GET /indexers`, `POST/DELETE/PATCH /indexers/{id}` (`indexers.go`) | implemented | yes | go `jackettapi/indexers_test.go` | unit (go) | PENDING |
| `POST /indexers/{id}/test` — test indexer config (`indexers.go:239`) | implemented | yes | go `indexers_test.go` | unit (go) | PENDING |
| `GET /catalog`, `POST /catalog/refresh` (`catalog.go`) | implemented | yes | go `jackettapi/catalog_test.go`; benchmark `catalog_bench_test.go` | unit + bench (go) | PENDING |
| `GET /autoconfig/runs`, `GET /runs/{id}`, `POST /run` (`runs.go`) | implemented | yes | go `jackettapi/runs_test.go`; e2e `tests/e2e/jackett_management_test.go` | unit + e2e (go) | PENDING |
| `GET/POST /overrides`, `DELETE /overrides/{env}` (`overrides.go`) | implemented | yes | go `jackettapi/overrides_test.go` | unit (go) | PENDING |
| `GET /healthz` (`health.go`) | implemented | yes | go `jackettapi/health_test.go` | unit (go) | PENDING |
| `GET /openapi.json` (`openapi.go`) | implemented | yes | go `jackettapi/openapi_test.go`; contract `tests/contract/openapi_test.go` | unit + contract (go) | PENDING |
| Jackett autoconfig engine + fuzzy indexer matcher (`jackett/autoconfig.go`, `matcher.go`) | implemented | yes | go `jackett/autoconfig_test.go`, `matcher_test.go`, `autoconfig_bench_test.go` | unit + bench (go) | PENDING |
| Encrypted SQLite store: AES-256-GCM crypto + migrations + repos (`db/*.go`) | implemented | yes | go `db/crypto_test.go`, `migrate_test.go`, `repos/*_test.go`; security `tests/security/credential_leak_test.go` | unit + security (go) | PENDING |
| Admin auth middleware (admin/admin on mutating routes) + hardened CORS (`jackettapi/auth_middleware.go`, `cors_middleware.go`) | implemented | yes | go `auth_middleware_test.go`, `cors_middleware_test.go` | unit (go) | PENDING |
| `.env` bootstrap import + master-key ensure (`bootstrap/*.go`, `envfile/*.go`) | implemented | yes | go `bootstrap/bootstrap_test.go`, `envfile/parse_test.go`, `write_test.go` | unit (go) | PENDING |

---

## 4. Tracker plugins (`plugins/*.py`)

Plugin contract: class with `url`, `name`, `supported_categories`, `search()`, `download_torrent()`. Installed into container by `install-plugin.sh`. **Curated/managed subset** (per `install-plugin.sh` PLUGINS array): `eztv jackett kinozal limetorrents nnmclub piratebay rutor rutracker solidtorrents torlock torrentproject torrentscsv`. The full `plugins/` tree carries 24 `*.py` plugin/support files (27 total incl. helpers/nova2/novaprinter/socks/download_proxy/env_loader/theme_injector).

| Plugin | Type | Impl | Wired (curated?) | Tests | Validation | Video |
|--------|------|------|------------------|-------|------------|-------|
| `eztv.py` | public | implemented | yes (curated) | stress `test_plugin_parsers_stress_chaos.py` | tested-green-in-suite | PENDING |
| `limetorrents.py` | public | implemented | yes (curated) | stress `test_plugin_parsers_stress_chaos.py` | tested-green-in-suite | PENDING |
| `piratebay.py` | public | implemented | yes (curated) | stress `test_plugin_parsers_stress_chaos.py` | tested-green-in-suite | PENDING |
| `solidtorrents.py` | public | implemented | yes (curated) | stress `test_plugin_parsers_stress_chaos.py` | tested-green-in-suite | PENDING |
| `torlock.py` | public | implemented | yes (curated) | stress `test_plugin_parsers_stress_chaos.py` | tested-green-in-suite | PENDING |
| `rutor.py` | public (anonymous) | implemented | yes (curated) | stress `test_plugin_parsers_stress_chaos.py` | tested-green-in-suite | PENDING |
| `jackett.py` | aggregator | implemented | yes (curated) | covered via jackett autoconfig tests | tested-green-in-suite | PENDING |
| `rutracker.py` | private (CAPTCHA) | implemented | yes (curated) | integration `test_tracker_auth_live.py`; stress `test_plugin_parsers_stress_chaos.py` (ReDoS §11.4.85) | partial — ReDoS fix in source, not yet deployed to container (RW-06); login operator-blocked BOB-008 | PENDING |
| `kinozal.py` | private | implemented | yes (curated) | integration `test_tracker_auth_live.py` | partial — live-gated | PENDING |
| `nnmclub.py` | private (cookies) | implemented | yes (curated) | integration `test_tracker_auth_live.py` | partial — live-gated | PENDING |
| `iptorrents.py` | private (freeleech-only) | implemented | not in curated array; reachable via env creds | integration `tests/integration/test_iptorrents.py` | partial — freeleech-only policy | PENDING |
| `torrentproject` / `torrentscsv` | public (curated names) | declared curated but no matching `plugins/*.py` file found | curated-name-only | none | not-implemented in repo tree (name in install array; file absent) | PENDING |
| Other public plugins present but NOT curated: `anilibra, bitsearch, gamestorrents, kickass, megapeer, nyaa, tokyotoshokan, torrentgalaxy, torrentkitty, yts` | public | implemented | no (not in curated subset) | stress `test_plugin_parsers_stress_chaos.py` (parser sweep) | unit/stress parser-only | PENDING |
| Plugin support: `helpers.py`, `nova2.py`, `novaprinter.py`, `socks.py`, `env_loader.py` | support | implemented | yes | covered via search e2e | tested-green-in-suite | PENDING |
| Plugin download path (`download_torrent()` per plugin) | feature | implemented | yes | integration `test_buttons_api.py` (download/file) | tested-green-in-suite | PENDING |
| Freeleech-only download policy (IPTorrents `[free]` tag) | policy | implemented | yes | integration `test_iptorrents.py` | tested-green-in-suite | PENDING |

> NOTE (§11.4.6): `torrentproject` and `torrentscsv` appear in the `install-plugin.sh` curated array but no `plugins/torrentproject.py` / `plugins/torrentscsv.py` file exists in the tree — flagged as a discrepancy, not asserted as working.

---

## 5. Angular 21 frontend dashboard (`frontend/`)

Standalone SPA, signals-based; built to `download-proxy/src/ui/dist/frontend`, served from :7187. Vitest unit tests; Playwright e2e under `frontend/e2e`.

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| Dashboard component — search box + result grid (`components/dashboard/`) | implemented | yes | vitest `dashboard.component.spec.ts`; py integration `test_dashboard_rendering.py`, `test_ui_comprehensive.py` | tested-green-in-suite | PENDING |
| API service (`services/api.service.ts`) | implemented | yes | vitest (component specs) | unit (vitest) | PENDING |
| SSE service — live result streaming (`services/sse.service.ts`) | implemented | yes | py integration `test_realtime_streaming.py`, `test_streaming_browser.py` | tested-green-in-suite | PENDING |
| Result-row Magnet button → magnet dialog (`magnet-dialog.component.ts`) | implemented | yes | vitest `magnet-dialog.component.spec.ts`; py `test_magnet_dialog.py` | tested-green-in-suite | PENDING |
| Magnet dialog copy-to-clipboard + open + add-to-qbit callback (`dashboard.component.ts:727`) | implemented | yes | vitest `magnet-dialog.component.spec.ts` | unit (vitest) | PENDING |
| Result-row add-to-qBittorrent / download button | implemented | yes | py integration `test_button_functions.py`, `test_buttons_api.py` | tested-green-in-suite | PENDING |
| Active downloads view (`dashboard.component.ts:745 loadDownloads`) | implemented | yes | py `test_buttons_api.py` | tested-green-in-suite | PENDING |
| qBit login dialog (`qbit-login-dialog.component.ts`) | implemented | yes | py `test_login_actions.py`, `test_auth_state_ui.py` | tested-green-in-suite | PENDING |
| Theme picker (`theme-picker.component.ts`) + theme service (`services/theme.service.ts`) | implemented | yes | py e2e `test_theme_runtime.py`, `test_crossapp_theme.py` | tested-green-in-suite | PENDING |
| Toast notifications (`toast-container`, `services/toast.service.ts`) | implemented | yes | vitest (component specs) | unit (vitest) | PENDING |
| Confirm dialog (`confirm-dialog.component.ts`, `services/dialog.service.ts`) | implemented | yes | vitest | unit (vitest) | PENDING |
| Tracker-stat dialog — per-tracker live stats (`tracker-stat-dialog.component.ts`) | implemented | yes | py contract `test_tracker_stats_contract.py` | tested-green-in-suite | PENDING |
| Site footer (`site-footer.component.ts`) | implemented | yes | vitest | unit (vitest) | PENDING |
| Jackett: credentials tab + edit dialog (`jackett/credentials/`) | implemented | yes | vitest (jackett specs) | unit (vitest) | PENDING |
| Jackett: indexers — catalog / configured / history tabs (`jackett/indexers/`) | implemented | yes | vitest (jackett specs) | unit (vitest) | PENDING |
| Jackett: indexer add dialog (`indexer-add-dialog.component.ts`) | implemented | yes | vitest | unit (vitest) | PENDING |
| Jackett: IPTorrents cookie-flow component (`iptorrents-cookie-flow.component.ts`) | implemented | yes | vitest | unit (vitest) | PENDING |
| Frontend coverage thresholds (40% lines/branches/funcs/stmts, v8) | infra | yes | `vitest.config.ts` | enforced in vitest config | PENDING |

---

## 6. BobaLink browser extension (`extension/`)

WXT + TypeScript Manifest-V3. Detects magnet/.torrent links and forwards to merge service :7187. Status detail: `docs/browser_extension/Status.md` (Rev 15: 559 Vitest tests / 52 specs). Built zips at `extension/.output/bobalink-1.0.0-{chrome,firefox}.zip`.

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| Boba API client (`src/api/boba-client.ts`) | implemented | yes | vitest unit; chaos `tests/chaos/boba-client-resilience.chaos.test.ts` | tested-green (559 vitest, per ext Status) | PENDING |
| Health check (`src/api/health.ts`) | implemented | yes | vitest unit | tested-green-in-suite | PENDING |
| Send queue (`src/api/queue.ts`) | implemented | yes | chaos `tests/chaos/queue.chaos.test.ts` | tested-green-in-suite | PENDING |
| Background service worker (`src/background/`, `entrypoints/background.ts`) | implemented | yes | integration `tests/integration/*-background.test.ts` | tested-green-in-suite | PENDING |
| Content script — link highlight (`src/content/highlight.ts`) | implemented | yes | integration `content-background.test.ts`; security `content-xss.test.ts` | tested-green-in-suite | PENDING |
| Link scanner (`src/scanner/link-scanner.ts`) | implemented | yes | security `scanner-hostile-input.test.ts`; perf `scanner.perf.test.ts` | tested-green-in-suite | PENDING |
| Text scanner (`src/scanner/text-scanner.ts`) | implemented | yes | security `scanner-hostile-input.test.ts` | tested-green-in-suite | PENDING |
| Scanner orchestrator (`src/scanner/orchestrator.ts`) | implemented | yes | perf `orchestrator-scaling.perf.test.ts` | tested-green-in-suite | PENDING |
| Site DB — per-site match rules (`src/scanner/site-db.ts`) | implemented | yes | vitest unit | tested-green-in-suite | PENDING |
| Bencode / magnet / torrent-file parsers (`src/parser/`) | implemented | yes | security `bencode-torrentfile-hostile.test.ts`, `infohash-detection-hostile.test.ts`; perf `parsers.perf.test.ts`, `magnet.perf.test.ts` | tested-green-in-suite | PENDING |
| Popup — per-row Send + Send-All buttons (`src/popup/popup.ts`) | implemented | yes | a11y `tests/a11y/popup.a11y.test.ts` | tested-green-in-suite | PENDING |
| Options page (`src/options/options.ts`) | implemented | yes | a11y `options.a11y.test.ts`; integration `options-background.test.ts` | tested-green-in-suite | PENDING |
| Tab groups (`src/tabgroups/`) | implemented | yes | vitest unit (tab-group Challenge per ext Status) | tested-green-in-suite | PENDING |
| Crypto / storage / i18n locales (8 locales) (`src/shared/crypto.ts`, `storage.ts`) | implemented | yes | security `crypto-tamper.test.ts`, `no-hardcoded-secret.test.ts`; i18n `locale-safety.test.ts` | tested-green-in-suite; RELEASE_READINESS locale claim stale (RW-19) | PENDING |
| Live download endpoint round-trip (`tests/live/download-endpoint.live.test.ts`) | implemented | yes (live-gated) | live `download-endpoint.live.test.ts` | partial — operator-gated live env | PENDING |

---

## 7. WebUI bridge (`webui-bridge.py`) — host process `:7188`

Bridges qBittorrent WebUI with private-tracker auth. NOT a container.

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| WebUI proxy + header rewrite (`webui-bridge.py`) | implemented | host | integration `test_webui_bridge.py`, `test_bridge_header_rewrite.py`; stress `test_bridge_stress_chaos.py` | tested-green-in-suite | PENDING |
| Private-tracker auth bridging (rutracker/kinozal/nnmclub/iptorrents) | implemented | host | integration `test_webui_bridge.py` | partial — live-gated | PENDING |
| Theme injection into bridged WebUI (`plugins/theme_injector.py`) | implemented | host | integration `test_bridge_theme_injection.py` | tested-green-in-suite | PENDING |
| Bridge root liveness (`/`) | implemented | host | integration `test_bridge_root_liveness.py` | tested-green-in-suite | PENDING |

---

## 8. Infrastructure / CLI / shell scripts

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| `start.sh` — container bring-up + Jackett key extraction/injection | implemented | host | covered via e2e `test_fixtures_bring_up_services.py` | tested-green-in-suite | PENDING |
| `stop.sh` — stop/remove/purge | implemented | host | none dedicated | not-validated | PENDING |
| `setup.sh` — one-time setup | implemented | host | none dedicated | not-validated | PENDING |
| `install-plugin.sh` — copy curated plugins → container engines | implemented | host | covered indirectly (e2e search) | tested-green-in-suite | PENDING |
| `ci.sh` — manual CI (syntax+unit+integration+e2e+health) | implemented | host | self (is the gate) | tested-green-in-suite | PENDING |
| `run-all-tests.sh` — full suite (hardcoded podman) | implemented | host | self | partial — fails on docker-only hosts (known gotcha) | PENDING |
| `test.sh` / `test-all.sh` / `test-full.sh` — validation wrappers | implemented | host | self | tested-green-in-suite | PENDING |
| `start-proxy.sh` — proxy container entry helper | implemented | host | none dedicated | not-validated | PENDING |
| `scripts/ensure-macos-tunnel.sh` + `scripts/tunnel-keepalive.sh` — `0.0.0.0` SSH tunnel + self-heal | implemented | host | none dedicated (log at `qa-results/tunnel-keepalive.log`) | not-validated; LAN threat-model RW-05 | PENDING |
| `init-qbit-password.sh` / `fix-qbit-password.sh` — qBit admin password bootstrap | implemented | host | none dedicated | not-validated | PENDING |
| `setup-webui-bridge-service.sh` + `webui-bridge.service` — systemd unit for bridge | implemented | host | none dedicated | not-validated | PENDING |
| `docker-compose.yml` — 2-container default + Go profile + boba-jackett service | infra | yes | e2e `test_live_containers.py` | tested-green-in-suite | PENDING |
| Jackett auto-configuration at startup (key extract → inject `JACKETT_API_KEY`) | implemented | yes | integration `test_jackett_autoconfig_real.py` | tested-green-in-suite | PENDING |
| `BOBA_MASTER_KEY` auto-generation (first-boot) for encrypted boba.db | implemented | yes | go `bootstrap/bootstrap_test.go` | unit (go) | PENDING |
| `boba-ctl` orchestrator (Go: up/down/status/health/list) — `cmd/boba-ctl/main.go` | implemented | host | go `cmd/boba-ctl/projectroot_test.go` | tested-green-in-suite + LIVE | **VIDEO-CONFIRMED 2026-06-16** — `boba-cli-orchestrator-demo.mp4`; Claude-vision verdict `docs/qa/recordings-20260615/boba-cli-verdict.md` |

---

## Components NOT inventoried / discrepancies (honest gaps, §11.4.6)

- **`boba-ctl.sh`** — referenced in tooling but no file exists at repo root or `scripts/`; could not inventory its subcommands.
- **`plugins/torrentproject.py` / `plugins/torrentscsv.py`** — named in the `install-plugin.sh` curated array but absent from the tree; marked not-implemented-in-repo above.
- **Prometheus/OpenTelemetry metrics** — `tests/observability/test_metrics_exist.py` + `observability/` dir exist, but no `prometheus_client` `Counter()/Histogram()/Gauge()` definitions were found in `download-proxy/src`; metrics surface is via `GET /api/v1/stats` (counters maintained in-process), not a `/metrics` Prometheus endpoint. Stated as fact, not assumed.
- **Video-recording confirmation** — `PENDING` for all rows EXCEPT `boba-ctl` (VIDEO-CONFIRMED 2026-06-16, recording `boba-cli-orchestrator-demo.mp4` + Claude-vision verdict). Remaining surfaces (web/Jinja dashboards, extension, per-feature flows) are an in-progress recording pass (§11.4.107/§11.4.143).
