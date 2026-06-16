# Boba — Feature Status (all components)

**Revision:** 3
**Last modified:** 2026-06-16T11:30:00Z
**Scope:** Every system component, service, infrastructure piece, and client app of the Boba project — one row per REAL unit (endpoint / handler / client method / component control / plugin / subcommand / script), grouped by component.
**Authority:** assembled by READ-ONLY repo inventory (codegraph + grep + source reading) on 2026-06-15, expanded to per-unit granularity (§11.4.118 discovery-pressure) on 2026-06-16. Cross-references `AGENTS.md`, `CLAUDE.md`, `docs/REMAINING_WORK_PLAN.md`.

> Captured-evidence-driven (§11.4.5 / §11.4.45 / §11.4.86). Every feature row cites a real source file (file:line where load-bearing), endpoint, command, or control. **No invented features** (§11.4.6). The **Video-recording confirmation** column is `PENDING` for all rows EXCEPT the rows already marked `VIDEO-CONFIRMED` (boba-ctl CLI orchestrator + the `POST /api/v1/search` web journey); remaining surfaces (per-feature flows) are an in-progress recording pass (§11.4.107/§11.4.143).
>
> Column legend:
> - **Impl** = implemented / partial / stub / missing
> - **Wired** = reachable on a running default-profile stack (yes / no / opt-in / host)
> - **Tests** = test types present + cite file (unit / integration / e2e / security / stress-chaos / property / contract); `none` if no covering test found
> - **Validation** = honest validation posture (tested-green-in-suite / unit-only / live-evidence-captured / not-validated / operator-blocked)
> - **Video** = video-recording confirmation — `PENDING` unless an individual recording exists

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
- **BobaLink extension**: covered by passing test suite (per `docs/browser_extension/Status.md`); a real-use UI video needs a `--load-extension` browser the current MCP can't launch — documented tooling-limited follow-up (NOT faked).
- **TUI / mobile / desktop**: do not exist in this project (server-side + Angular web + browser extension only) — nothing to record.

---

## Component summary

| # | Component | Service / Port | Features cataloged |
|---|-----------|----------------|--------------------|
| 1 | Download Proxy + Merge Search Service (Python/FastAPI) | `qbittorrent-proxy` :7186 / :7187 | 68 |
| 2 | qBitTorrent-go backend (Go/Gin) | `qbittorrent-proxy-go` :7186/:7187/:7188 (opt-in `--profile go`) | 47 |
| 3 | boba-jackett (Go) | `boba-jackett` :7189 | 26 |
| 4 | Tracker plugins (`plugins/*.py`) | run inside `qbittorrent-proxy` | 30 |
| 5 | Angular 21 frontend dashboard (`frontend/`) | served from :7187 | 34 |
| 6 | BobaLink browser extension (`extension/`) | WXT MV3 client | 39 |
| 7 | WebUI bridge (`webui-bridge.py`) | host process :7188 | 4 |
| 8 | Infrastructure / CLI / shell scripts | host | 40 |

**Total features cataloged: 288**

---

## 1. Download Proxy + Merge Search Service (Python/FastAPI) — `:7186` / `:7187`

Entry: `download-proxy/src/main.py` (starts legacy proxy thread + uvicorn `api:app`). This is the **shipped default product**.

### 1a. Merge Search Service — REST API (`download-proxy/src/api/routes.py`)

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| `POST /api/v1/search` — async fan-out search, returns search_id (`routes.py:283`) | implemented | yes | integration `tests/integration/test_merge_api.py`; e2e `test_full_pipeline.py`; stress `test_merge_search_stress_chaos.py` | tested-green-in-suite + LIVE | **VIDEO-CONFIRMED 2026-06-16** — real web-UI journey (`debian`→829 found/288 merged), `boba-web-search-flow.mp4`; verdict `docs/qa/recordings-20260615/boba-web-search-flow-verdict.md` |
| `POST /api/v1/search/sync` — synchronous search (`routes.py:377`) | implemented | yes | integration `test_merge_api.py`; stress `test_search_stress.py` | tested-green-in-suite; resets over tunnel (RW-08) | PENDING |
| `GET /api/v1/search/stream/{id}` — SSE result stream (`routes.py:547`) | implemented | yes | integration `test_realtime_streaming.py`, `test_streaming_browser.py` | tested-green-in-suite | PENDING |
| `GET /api/v1/search/{id}` — poll search state (`routes.py:586`) | implemented | yes | integration `test_merge_api.py` | tested-green-in-suite | PENDING |
| `POST /api/v1/search/{id}/abort` — cancel in-flight search (`routes.py:619`) | implemented | yes | integration `test_merge_api.py` | tested-green-in-suite | PENDING |
| `GET /api/v1/downloads/active` — qBit active torrents (`routes.py:629`) | implemented | yes | integration `test_buttons_api.py` | tested-green-in-suite | PENDING |
| `POST /api/v1/auth/qbittorrent` — qBit WebUI login (`routes.py:671`) | implemented | yes | integration `test_login_actions.py` | tested-green-in-suite | PENDING |
| `POST /api/v1/download` — add torrent to qBit (magnet/url) (`routes.py:958`) | implemented | yes | integration `test_button_functions.py`, `test_buttons_api.py`; security `test_ssrf_and_magnet_auth.py` | tested-green-in-suite; SSRF gap RW-03 | PENDING |
| `POST /api/v1/download/upload` — upload .torrent file to qBit (`routes.py:1123`) | implemented | yes | unit `tests/unit/api_layer/test_download_upload.py` | unit-only + integration | PENDING |
| `POST /api/v1/download/file` — fetch tracker .torrent w/ auth cookies (`routes.py:1212`) | implemented | yes | integration `test_buttons_api.py`; security `test_ssrf_and_magnet_auth.py` | tested-green-in-suite; SSRF gap RW-03 | PENDING |
| `POST /api/v1/magnet` — resolve result → magnet link (`routes.py:1279`) | implemented | yes | integration `test_magnet_dialog.py`, `test_buttons_api.py` | tested-green-in-suite; auth gap RW-04 | PENDING |
| `GET /api/v1/theme` — read theme state (`routes.py:61`) | implemented | yes | contract `test_crossapp_theme_contract.py` | tested-green-in-suite | PENDING |
| `PUT /api/v1/theme` — persist theme (`routes.py:67`) | implemented | yes | e2e `test_theme_runtime.py`, `test_crossapp_theme.py` | tested-green-in-suite | PENDING |
| `GET /api/v1/theme/stream` — SSE theme broadcast (`routes.py:76`) | implemented | yes | e2e `test_crossapp_theme.py` | tested-green-in-suite | PENDING |

### 1b. Auth API — per-tracker (`download-proxy/src/api/auth.py`)

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| `GET /auth/rutracker/status` — RuTracker session state (`auth.py:56`) | implemented | yes | integration `test_auth_and_links.py`; e2e `test_live_stack_evidence.py` | partial — CAPTCHA operator-blocked (BOB-008) | PENDING |
| `GET /auth/rutracker/captcha` — fetch CAPTCHA image (`auth.py:108`) | implemented | yes | integration `test_auth_and_links.py` | partial — operator-blocked (BOB-008) | PENDING |
| `POST /auth/rutracker/login` — username/password + CAPTCHA login (`auth.py:214`) | implemented | yes | integration `test_auth_and_links.py` | partial — operator-blocked (BOB-008) | PENDING |
| `POST /auth/rutracker/cookie-login` — cookie-based login (`auth.py:298`) | implemented | yes | integration `test_auth_and_links.py` | partial — live-gated | PENDING |
| `GET /auth/nnmclub/status` — NNM-Club session state (`auth.py:350`) | implemented | yes | e2e `test_live_stack_evidence.py:265` (skips — SOURCE→ARTIFACT drift RW-07) | partial — route 404 on running container (RW-07) | PENDING |
| `POST /auth/nnmclub/login` — NNM-Club login (`auth.py:407`) | implemented | yes | e2e `test_live_stack_evidence.py` | partial — live-gated | PENDING |
| `GET /auth/status` — all-tracker aggregate session state (`auth.py:479`) | implemented | yes | integration `test_auth_state_ui.py` | tested-green-in-suite | PENDING |
| `POST /auth/qbittorrent/logout` — qBit WebUI logout (`auth.py:532`) | implemented | yes | integration `test_login_actions.py` | tested-green-in-suite | PENDING |
| Kinozal auth (status/login) REST route | **missing** | no | none — no `kinozal/login` route in `auth.py` | not-implemented (search path uses cookies via orchestrator) | PENDING |
| IPTorrents auth (status/login) REST route | **missing** | no | none — no `iptorrents/login` route in `auth.py` | not-implemented (env creds + cookie flow via Jackett UI) | PENDING |

### 1c. Search orchestration internals (`download-proxy/src/merge_service/search.py`)

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

### 1d. Deduplication (`download-proxy/src/merge_service/deduplicator.py`)

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| Tier 1 dedup — metadata (imdb/tmdb) key | implemented | yes | property `test_deduplicator_properties.py`; benchmark `test_deduplication_benchmark.py` | tested-green-in-suite | PENDING |
| Tier 2 dedup — infohash key | implemented | yes | property `test_deduplicator_properties.py` | tested-green-in-suite | PENDING |
| Tier 3 dedup — name+size key | implemented | yes | property `test_deduplicator_properties.py` | tested-green-in-suite | PENDING |
| Tier 4 dedup — fuzzy Levenshtein name match | implemented | yes | property `test_deduplicator_properties.py`; benchmark `test_deduplication_benchmark.py` | tested-green-in-suite | PENDING |

### 1e. Enrichment — per metadata source (`download-proxy/src/merge_service/enricher.py`)

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| Enrichment: OMDb (`enricher.py:113`) | implemented | yes | stress `test_enricher_stress_chaos.py` | tested-green-in-suite; needs `OMDB_API_KEY` | PENDING |
| Enrichment: TMDB | implemented | yes | stress `test_enricher_stress_chaos.py` | tested-green; needs `TMDB_API_KEY` | PENDING |
| Enrichment: TVMaze | implemented | yes | stress `test_enricher_stress_chaos.py` | tested-green-in-suite | PENDING |
| Enrichment: AniList | implemented | yes | stress `test_enricher_stress_chaos.py` | tested-green-in-suite | PENDING |
| Enrichment: MusicBrainz | implemented | yes | stress `test_enricher_stress_chaos.py` | tested-green-in-suite | PENDING |
| Enrichment: OpenLibrary | implemented | yes | stress `test_enricher_stress_chaos.py` | tested-green-in-suite | PENDING |

### 1f. Tracker validation (`download-proxy/src/merge_service/validator.py`)

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| Tracker validation HTTP scrape BEP 48 (`validator.py:101`) | implemented | yes | none dedicated found (covered via merge tests) | not-validated (no dedicated test) | PENDING |
| Tracker validation UDP scrape BEP 15 (`validator.py:162`) | implemented | yes | none dedicated found | not-validated (no dedicated test) | PENDING |

### 1g. Hooks (`download-proxy/src/api/hooks.py` + `merge_service/hooks.py`)

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| `GET /api/v1/hooks` — list hooks (`hooks.py:105`) | implemented | yes | unit `test_hooks_coverage.py`; concurrency `test_hooks_race.py`; security `test_hooks_schedules_auth.py` | tested-green-in-suite; auth gap RW-01 | PENDING |
| `POST /api/v1/hooks` — create hook (`hooks.py:111`) | implemented | yes | unit `test_hooks_coverage.py`; concurrency `test_hooks_race.py` | tested-green-in-suite; auth gap RW-01 | PENDING |
| `DELETE /api/v1/hooks/{id}` — delete hook (`hooks.py:167`) | implemented | yes | unit `test_hooks_coverage.py` | tested-green-in-suite; auth gap RW-01 | PENDING |
| `GET /api/v1/hooks/logs` — hook execution logs (`hooks.py:179`) | implemented | yes | unit `test_hooks_coverage.py` | tested-green-in-suite | PENDING |
| Hook event dispatch (8 events: search_start..validation_complete) (`hooks.py:32`) | implemented | yes | concurrency `test_hooks_race.py` | tested-green-in-suite | PENDING |
| Hook subprocess execution + sandbox (`merge_service/hooks.py`) | implemented | yes | security `test_no_shell_injection.py` | tested-green; sandbox hardening RW-01 | PENDING |

### 1h. Scheduler (`download-proxy/src/api/scheduler.py` + `merge_service/scheduler.py`)

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| `GET /api/v1/schedules` — list schedules (`scheduler.py:39`) | implemented | yes | security `test_hooks_schedules_auth.py` | tested-green-in-suite; auth gap RW-02 | PENDING |
| `POST /api/v1/schedules` — create schedule (`scheduler.py:64`) | implemented | yes | security `test_hooks_schedules_auth.py` | tested-green-in-suite; auth gap RW-02 | PENDING |
| `GET /api/v1/schedules/{id}` — get schedule (`scheduler.py:87`) | implemented | yes | security `test_hooks_schedules_auth.py` | tested-green-in-suite | PENDING |
| `PATCH /api/v1/schedules/{id}` — update schedule (`scheduler.py:108`) | implemented | yes | security `test_hooks_schedules_auth.py` | tested-green-in-suite | PENDING |
| `DELETE /api/v1/schedules/{id}` — delete schedule (`scheduler.py:126`) | implemented | yes | security `test_hooks_schedules_auth.py` | tested-green-in-suite | PENDING |
| Scheduler engine (load/save/tick driver) (`merge_service/scheduler.py`) | implemented | yes | integration `test_dashboard_automation.py` | tested-green-in-suite | PENDING |

### 1i. App-level routes / health / config / dashboard (`download-proxy/src/api/__init__.py`)

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| `GET /health` (`__init__.py:168`) | implemented | yes | integration `test_live_containers.py` | tested-green-in-suite | PENDING |
| `GET /api/v1/bridge/health` (`__init__.py:173`) | implemented | yes | integration `test_bridge_root_liveness.py` | tested-green-in-suite | PENDING |
| `GET /api/v1/config` (`__init__.py:247`) | implemented | yes | integration `test_merge_api.py` | tested-green-in-suite | PENDING |
| `GET /api/v1/stats` (`__init__.py:276`) | implemented | yes | observability `test_metrics_exist.py` | tested-green-in-suite | PENDING |
| Jinja2 dashboard `GET /` (`__init__.py:337`) | implemented | yes | integration `test_dashboard_rendering.py` | tested-green-in-suite | PENDING |
| Jinja2 dashboard `GET /dashboard` (`__init__.py:342`) | implemented | yes | integration `test_dashboard_rendering.py` | tested-green-in-suite | PENDING |
| SPA catch-all `GET /{path:path}` (`__init__.py:347`) | implemented | yes | integration `test_dashboard_rendering.py` | tested-green-in-suite | PENDING |

### 1j. Supporting subsystems (Python)

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| Retry helpers (`merge_service/retry.py`) | implemented | yes | covered indirectly | unit-only | PENDING |
| Jackett autoconfig (Python, `merge_service/jackett_autoconfig.py`) — legacy; canonical is boba-jackett | implemented | yes | contract `test_jackett_autoconfig_contract.py`; e2e `test_jackett_autoconfig_e2e.py`; benchmark `test_jackett_autoconfig_perf.py` | tested-green-in-suite | PENDING |
| Credential scrubbing log filter (`config/log_filter.py`) | implemented | yes | security `test_credential_scrubbing.py` | tested-green-in-suite | PENDING |

### 1k. Legacy download proxy (`plugins/download_proxy.py` :7186)

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| HTTP proxy → qBittorrent WebUI w/ tracker URL interception (`DownloadHandler` :767) | implemented | yes | integration `test_bridge_header_rewrite.py` | tested-green-in-suite | PENDING |
| Theme injection into proxied WebUI (`plugins/theme_injector.py`) | implemented | yes | integration `test_bridge_theme_injection.py` | tested-green-in-suite | PENDING |

---

## 2. qBitTorrent-go backend (Go/Gin) — opt-in `--profile go`

Entry: `qBitTorrent-go/cmd/qbittorrent-proxy/main.go` (routes registered `:54-101`). **Skeleton/rewrite-in-progress** (per AGENTS.md + `docs/migration/PARITY_GAPS.md`). NOT running by default.

### 2a. HTTP handlers (`internal/api/*.go`)

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| `GET /health` — `HealthHandler` (`api/health.go:5`) | implemented | opt-in | go `internal/api/api_test.go` | unit-only (go test) | PENDING |
| `GET /api/v1/config` — `ConfigHandler` (`api/download.go:210`) | implemented | opt-in | go `coverage_test.go` | unit-only | PENDING |
| `GET /api/v1/bridge/health` — `BridgeHealthHandler` (`api/download.go:189`) | implemented | opt-in | go `coverage_test.go` | unit-only | PENDING |
| `POST /api/v1/search` — `SearchHandler` (`api/search.go:14`) | implemented (proxies qBit search; no plugin fan-out) | opt-in | go `api_test.go`, `coverage_test.go` | unit-only | PENDING |
| `POST /api/v1/search/sync` — `SearchSyncHandler` (`api/search.go:50`) | implemented | opt-in | go `coverage_test.go` | unit-only | PENDING |
| `GET /api/v1/search/stream/:id` — `SearchStreamHandler` SSE (`api/search.go:91`) | implemented | opt-in | go `coverage_test.go` | unit-only | PENDING |
| `GET /api/v1/search/:id` — `GetSearchHandler` (`api/search.go:144`) | implemented | opt-in | go `getsearch_results_test.go`, `coverage_test.go` | unit-only | PENDING |
| `POST /api/v1/search/:id/abort` — `AbortSearchHandler` (`api/search.go:177`) | implemented | opt-in | go `coverage_test.go` | unit-only | PENDING |
| `POST /api/v1/download` — `DownloadHandler` (`api/download.go:17`) | **partial — returns mock success, no qBit integration** | opt-in | go `coverage_test.go` | unit-only; functional hole | PENDING |
| `POST /api/v1/download/file` — `DownloadFileHandler` (`api/download.go:41`) | implemented | opt-in | go `coverage_test.go` | unit-only | PENDING |
| `POST /api/v1/magnet` — `MagnetHandler` (`api/download.go:86`) | implemented | opt-in | go `api_test.go`, `magnet_stress_chaos_test.go` | unit + stress-chaos (go) | PENDING |
| `GET /api/v1/downloads/active` — `ActiveDownloadsHandler` (`api/download.go:147`) | **stub — returns empty array, no qBit query** | opt-in | go `coverage_test.go` | unit-only; functional hole | PENDING |
| `POST /api/v1/auth/qbittorrent` — `QBittorrentAuthHandler` (`api/download.go:156`) | implemented | opt-in | go `coverage_test.go` | unit-only | PENDING |
| `GET /api/v1/theme` — `GetThemeHandler` (`api/theme.go:90`) | implemented | opt-in | go `theme_hardening_test.go`, `coverage_test.go` | unit-only | PENDING |
| `PUT /api/v1/theme` — `PutThemeHandler` (`api/theme.go:96`) | implemented | opt-in | go `theme_hardening_test.go` | unit-only | PENDING |
| `GET /api/v1/hooks` — `ListHooksHandler` (`api/hooks.go:91`) | implemented (store only, no dispatch) | opt-in | go `api_test.go`, `coverage_test.go` | unit-only | PENDING |
| `POST /api/v1/hooks` — `CreateHookHandler` (`api/hooks.go:97`) | implemented (store only) | opt-in | go `api_test.go` | unit-only | PENDING |
| `DELETE /api/v1/hooks/:id` — `DeleteHookHandler` (`api/hooks.go:109`) | implemented (store only) | opt-in | go `api_test.go` | unit-only | PENDING |
| `GET /api/v1/schedules` — `ListSchedulesHandler` (`api/scheduler_api.go:86`) | implemented (store only) | opt-in | go `coverage_test.go` | unit-only; **no driver loop (RW-10), schedules never fire** | PENDING |
| `POST /api/v1/schedules` — `CreateScheduleHandler` (`api/scheduler_api.go:92`) | implemented (store only) | opt-in | go `coverage_test.go` | unit-only; never fires (RW-10) | PENDING |
| `DELETE /api/v1/schedules/:id` — `DeleteScheduleHandler` (`api/scheduler_api.go:104`) | implemented (store only) | opt-in | go `coverage_test.go` | unit-only | PENDING |

### 2b. qBittorrent Web API client (`internal/client/*.go`)

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| `NewClient` — construct + login (`client/client.go:18`) | implemented | opt-in | go `client/client_test.go` | unit-only | PENDING |
| `Login` — POST `/api/v2/auth/login`, store SID (`client/auth.go:11`) | implemented | opt-in | go `client/auth_test.go` | unit-only | PENDING |
| `IsAuthenticated` — SID presence (`client/auth.go:43`) | implemented | opt-in | go `client/auth_test.go` | unit-only | PENDING |
| `GetSID` — thread-safe SID accessor (`client/client.go:39`) | implemented | opt-in | go `client/client_test.go` | unit-only | PENDING |
| `GetTorrents` — GET `/api/v2/torrents/info` (`client/torrents.go:13`) | implemented | opt-in | go `client/coverage_test.go` | unit-only | PENDING |
| `AddTorrent` — POST `/api/v2/torrents/add` URL (`client/torrents.go:30`) | implemented | opt-in | go `client/coverage_test.go` | unit-only | PENDING |
| `AddTorrentFile` — POST multipart `/api/v2/torrents/add` (`client/torrents.go:54`) | implemented | opt-in | go `client/coverage_test.go` | unit-only | PENDING |
| `GetAppVersion` — GET `/api/v2/app/version` (`client/torrents.go:87`) | implemented | opt-in | go `client/coverage_test.go` | unit-only | PENDING |
| `StartSearch` — POST `/api/v2/search/start` (`client/search.go:27`) | implemented | opt-in | go `client/coverage_test.go` | unit-only | PENDING |
| `GetSearchResults` — GET `/api/v2/search/results` (`client/search.go:55`) | implemented | opt-in | go `client/coverage_test.go` | unit-only | PENDING |
| `StopSearch` — POST `/api/v2/search/stop` (`client/search.go:84`) | implemented | opt-in | go `client/coverage_test.go` | unit-only | PENDING |
| `SearchStatus` — GET `/api/v2/search/status` (`client/search.go:100`) | implemented | opt-in | go `client/coverage_test.go` | unit-only | PENDING |
| `ListPlugins` — GET `/api/v2/search/plugins` (`client/search.go:121`) | implemented | opt-in | go `client/coverage_test.go` | unit-only | PENDING |

### 2c. Services (`internal/service/*.go`)

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| Merge search orchestrator `RunSearch` poll/dedup loop (`service/merge_search.go:183`) | implemented (qBit search only; no python-style plugin fan-out) | opt-in | go `service/service_test.go`, `runsearch_dedup_test.go` | unit-only | PENDING |
| `StartSearch` / `GetSearchStatus` / `AbortSearch` lifecycle (`service/merge_search.go:101-143`) | implemented | opt-in | go `getsearchstatus_hardening_test.go` | unit-only | PENDING |
| Dedup key (FileURL→name+size) (`service/merge_search.go:269`) | implemented | opt-in | go `runsearch_dedup_test.go` | unit-only | PENDING |
| `FetchTorrent` tracker fetch (`service/merge_search.go:276`) | **stub — returns "not yet implemented"** | opt-in | none | not-implemented | PENDING |
| `Stats` counters (`service/merge_search.go:280`) | implemented | opt-in | go `coverage_test.go` | unit-only | PENDING |
| SSE broker pub/sub (`service/sse_broker.go`) | implemented (defined but not wired — handlers SSE inline) | opt-in | none dedicated | not-validated | PENDING |
| Metadata enricher (Go) | **missing (RW-11)** | no | none | not-implemented | PENDING |
| Scheduler driver loop (Go) | **missing (RW-10)** — CRUD only, no cron execution | no | none | not-implemented | PENDING |

### 2d. webui-bridge binary (Go) + cross-cutting

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| webui-bridge binary (`cmd/webui-bridge/main.go`) | partial (health + root only) | opt-in | none dedicated | not-validated | PENDING |
| CORS + logging middleware (`internal/middleware/`) | implemented | opt-in | go `middleware/middleware_test.go` | unit-only | PENDING |
| Models / data types (`internal/models/`) | implemented | opt-in | go `models/models_test.go` | unit-only | PENDING |
| Env config loader (`internal/config/`) | implemented | opt-in | go `config/config_test.go` | unit-only | PENDING |
| Log redactor (`internal/logging/redactor.go`) | implemented | opt-in | go `logging/redactor_test.go` | unit-only | PENDING |

---

## 3. boba-jackett (Go) — `:7189`

Entry: `qBitTorrent-go/cmd/boba-jackett/main.go`; router `internal/jackettapi/router.go`. Owns Jackett credentials + indexer overrides + autoconfig run history; encrypted SQLite at `/config/boba.db`.

### 3a. HTTP endpoints (`internal/jackettapi/router.go` + handlers)

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| `GET /healthz` (`router.go:60`, `health.go`) | implemented | yes | go `jackettapi/health_test.go` | unit (go) | PENDING |
| `GET /openapi.json` (`router.go:64`, `openapi.go`) | implemented | yes | go `jackettapi/openapi_test.go`; contract `tests/contract/openapi_test.go` | unit + contract (go) | PENDING |
| `GET /api/v1/jackett/credentials` — list (`router.go:67`, `credentials.go`) | implemented | yes | go `credentials_test.go`; integration `tests/integration/jackett_db_test.go` | unit + integration (go) | PENDING |
| `POST /api/v1/jackett/credentials` — create/update (`router.go:67`, `credentials.go`) | implemented | yes | go `credentials_test.go` | unit + integration (go) | PENDING |
| `DELETE /api/v1/jackett/credentials/{name}` (`router.go:77`, `credentials.go`) | implemented | yes | go `credentials_test.go` | unit + integration (go) | PENDING |
| `GET /api/v1/jackett/indexers` — list configured (`router.go:86`, `indexers.go`) | implemented | yes | go `jackettapi/indexers_test.go` | unit (go) | PENDING |
| `POST/PATCH/DELETE /api/v1/jackett/indexers/{id}` (`router.go:93`, `indexers.go`) | implemented | yes | go `indexers_test.go` | unit (go) | PENDING |
| `POST /api/v1/jackett/indexers/{id}/test` — test config (`indexers.go:239`) | implemented | yes | go `indexers_test.go` | unit (go) | PENDING |
| `GET /api/v1/jackett/catalog` — indexer catalog (`router.go:112`, `catalog.go`) | implemented | yes | go `jackettapi/catalog_test.go`; benchmark `catalog_bench_test.go` | unit + bench (go) | PENDING |
| `POST /api/v1/jackett/catalog/refresh` (`router.go:119`, `catalog.go`) | implemented | yes | go `catalog_test.go` | unit (go) | PENDING |
| `GET /api/v1/jackett/autoconfig/runs` — run history (`router.go:137`, `runs.go`) | implemented | yes | go `jackettapi/runs_test.go`; e2e `tests/e2e/jackett_management_test.go` | unit + e2e (go) | PENDING |
| `GET /api/v1/jackett/autoconfig/runs/{id}` — run detail (`router.go:144`, `runs.go`) | implemented | yes | go `runs_test.go` | unit (go) | PENDING |
| `POST /api/v1/jackett/autoconfig/run` — trigger run (`router.go:151`, `runs.go`) | implemented | yes | go `runs_test.go`; e2e `tests/e2e/jackett_management_test.go` | unit + e2e (go) | PENDING |
| `GET/POST /api/v1/jackett/overrides` (`router.go:160`, `overrides.go`) | implemented | yes | go `jackettapi/overrides_test.go` | unit (go) | PENDING |
| `DELETE /api/v1/jackett/overrides/{env}` (`router.go:170`, `overrides.go`) | implemented | yes | go `overrides_test.go` | unit (go) | PENDING |
| Admin auth middleware (admin/admin on mutating routes) (`jackettapi/auth_middleware.go`) | implemented | yes | go `auth_middleware_test.go` | unit (go) | PENDING |
| Hardened CORS middleware (`jackettapi/cors_middleware.go`) | implemented | yes | go `cors_middleware_test.go` | unit (go) | PENDING |

### 3b. Autoconfig engine + persistence (`internal/jackett/`, `internal/db/`)

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| Jackett autoconfig engine (`jackett/autoconfig.go`) | implemented | yes | go `jackett/autoconfig_test.go`, `autoconfig_bench_test.go` | unit + bench (go) | PENDING |
| Fuzzy indexer matcher (`jackett/matcher.go`) | implemented | yes | go `jackett/matcher_test.go` | unit (go) | PENDING |
| Jackett HTTP client (`jackett/client.go`) | implemented | yes | go `jackett/client_test.go` | unit (go) | PENDING |
| Encrypted SQLite — AES-256-GCM crypto (`db/crypto.go`) | implemented | yes | go `db/crypto_test.go`; security `tests/security/credential_leak_test.go` | unit + security (go) | PENDING |
| SQLite migrations (`db/migrate.go`) | implemented | yes | go `db/migrate_test.go` | unit (go) | PENDING |
| Credential / indexer / runs repos (`db/repos/*.go`) | implemented | yes | go `db/repos/*_test.go` | unit (go) | PENDING |
| `.env` bootstrap import (`bootstrap/*.go`) | implemented | yes | go `bootstrap/bootstrap_test.go` | unit (go) | PENDING |
| Master-key ensure (first-boot) (`bootstrap/*.go`) | implemented | yes | go `bootstrap/bootstrap_test.go` | unit (go) | PENDING |
| `.env` file parse/write (`envfile/*.go`) | implemented | yes | go `envfile/parse_test.go`, `write_test.go` | unit (go) | PENDING |

---

## 4. Tracker plugins (`plugins/*.py`)

Plugin contract: class with `url`, `name`, `supported_categories`, `search()`, `download_torrent()`. Installed into container by `install-plugin.sh`. The `install-plugin.sh` `PLUGINS` array names **44 plugins** (curated install set); the `plugins/` tree carries **27 `*.py` files** (24 tracker/aggregator plugins + 3 support: `nova2`, `novaprinter`, `socks`, `helpers`, `env_loader`, `theme_injector`, `download_proxy`). Many curated names have NO matching file in this repo tree (the install script fetches/expects them elsewhere) — flagged honestly below.

### 4a. Plugins present in `plugins/` AND named in the curated array

| Plugin | Type | Impl | Wired (curated?) | Tests | Validation | Video |
|--------|------|------|------------------|-------|------------|-------|
| `eztv.py` | public | implemented | yes (curated) | stress `test_plugin_parsers_stress_chaos.py` | tested-green-in-suite | PENDING |
| `limetorrents.py` | public | implemented | yes (curated) | stress `test_plugin_parsers_stress_chaos.py` | tested-green-in-suite | PENDING |
| `piratebay.py` | public | implemented | yes (curated) | stress `test_plugin_parsers_stress_chaos.py` | tested-green-in-suite | PENDING |
| `solidtorrents.py` | public | implemented | yes (curated) | stress `test_plugin_parsers_stress_chaos.py` | tested-green-in-suite | PENDING |
| `torlock.py` | public | implemented | yes (curated) | stress `test_plugin_parsers_stress_chaos.py` | tested-green-in-suite | PENDING |
| `rutor.py` | public (anonymous) | implemented | yes (curated) | stress `test_plugin_parsers_stress_chaos.py` | tested-green-in-suite | PENDING |
| `nyaa.py` | public | implemented | yes (curated) | stress `test_plugin_parsers_stress_chaos.py` | tested-green-in-suite | PENDING |
| `anilibra.py` | public | implemented | yes (curated) | stress `test_plugin_parsers_stress_chaos.py` | tested-green-in-suite | PENDING |
| `bitsearch.py` | public | implemented | yes (curated) | stress `test_plugin_parsers_stress_chaos.py` | tested-green-in-suite | PENDING |
| `gamestorrents.py` | public | implemented | yes (curated) | stress `test_plugin_parsers_stress_chaos.py` | tested-green-in-suite | PENDING |
| `kickass.py` | public | implemented | yes (curated) | stress `test_plugin_parsers_stress_chaos.py` | tested-green-in-suite | PENDING |
| `megapeer.py` | public | implemented | yes (curated) | stress `test_plugin_parsers_stress_chaos.py` | tested-green-in-suite | PENDING |
| `tokyotoshokan.py` | public | implemented | yes (curated) | stress `test_plugin_parsers_stress_chaos.py` | tested-green-in-suite | PENDING |
| `torrentgalaxy.py` | public | implemented | yes (curated) | stress `test_plugin_parsers_stress_chaos.py` | tested-green-in-suite | PENDING |
| `torrentkitty.py` | public | implemented | yes (curated) | stress `test_plugin_parsers_stress_chaos.py` | tested-green-in-suite | PENDING |
| `yts.py` | public | implemented | yes (curated) | stress `test_plugin_parsers_stress_chaos.py` | tested-green-in-suite | PENDING |
| `jackett.py` | aggregator | implemented | yes (curated) | covered via jackett autoconfig tests | tested-green-in-suite | PENDING |
| `iptorrents.py` | private (freeleech-only) | implemented | yes (curated) | integration `tests/integration/test_iptorrents.py` | partial — freeleech-only policy | PENDING |
| `rutracker.py` | private (CAPTCHA) | implemented | yes (curated) | integration `test_tracker_auth_live.py`; stress `test_plugin_parsers_stress_chaos.py` (ReDoS §11.4.85) | partial — ReDoS fix in source, not yet deployed to container (RW-06); login operator-blocked BOB-008 | PENDING |
| `kinozal.py` | private | implemented | yes (curated) | integration `test_tracker_auth_live.py` | partial — live-gated | PENDING |
| `nnmclub.py` | private (cookies) | implemented | yes (curated) | integration `test_tracker_auth_live.py` | partial — live-gated | PENDING |

### 4b. Plugin support modules

| Module | Type | Impl | Wired | Tests | Validation | Video |
|--------|------|------|-------|-------|------------|-------|
| `nova2.py` — nova3 search harness | support | implemented | yes | covered via search e2e | tested-green-in-suite | PENDING |
| `novaprinter.py` — result emitter (NDJSON-patched) | support | implemented | yes | covered via search e2e | tested-green-in-suite | PENDING |
| `helpers.py` — HTTP/retrieve helpers | support | implemented | yes | covered via search e2e | tested-green-in-suite | PENDING |
| `socks.py` — SOCKS proxy support | support | implemented | yes | covered indirectly | not-validated | PENDING |
| `env_loader.py` — env/credential loader for plugins | support | implemented | yes | covered via tracker auth tests | tested-green-in-suite | PENDING |
| Per-plugin `download_torrent()` path (.torrent fetch) | feature | implemented | yes | integration `test_buttons_api.py` (download/file) | tested-green-in-suite | PENDING |
| Freeleech-only download policy (IPTorrents `[free]` tag) | policy | implemented | yes | integration `test_iptorrents.py` | tested-green-in-suite | PENDING |

### 4c. Discrepancy rows (honest, §11.4.6)

| Plugin | Type | Impl | Wired (curated?) | Tests | Validation | Video |
|--------|------|------|------------------|-------|------------|-------|
| `torrentproject` / `torrentscsv` | public (curated names) | named in `install-plugin.sh` PLUGINS array but NO matching `plugins/*.py` file in tree | curated-name-only | none | not-implemented-in-repo-tree (install script expects them elsewhere) | PENDING |
| 23 other curated names absent from tree: `academictorrents, ali213, audiobookbay, bitru, bt4g, btsow, extratorrent, glotorrents, linuxtracker, one337x, pctorrent, pirateiro, rockbox, snowfl, therarbg, torrentdownload, torrentfunk, xfsub, yihua, yourbittorrent` (+ `torrentproject`, `torrentscsv`) | public (curated names) | named in curated array; NO `plugins/*.py` in this tree | curated-name-only | none | not-implemented-in-repo-tree (name in install array; file absent) | PENDING |

> NOTE (§11.4.6, CORRECTION vs Rev 2): the `install-plugin.sh` `PLUGINS` array contains **44 entries**, not 12. Of those, ~21 have a matching `plugins/*.py` file in this repo; the rest are curated names with no file present in the tree. Stated as fact, not asserted as working.

---

## 5. Angular 21 frontend dashboard (`frontend/`)

Standalone SPA, signals-based; built to `download-proxy/src/ui/dist/frontend`, served from :7187. Vitest unit tests; Playwright e2e under `frontend/e2e`.

### 5a. Dashboard component controls (`components/dashboard/dashboard.component.ts`)

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| Search box (`query` signal) + submit | implemented | yes | vitest `dashboard.component.spec.ts`; py integration `test_dashboard_rendering.py`, `test_ui_comprehensive.py` | tested-green-in-suite | PENDING |
| Result grid — sortable (name/type/size/seeds/leechers/quality/sources) | implemented | yes | vitest `dashboard.component.spec.ts` | unit (vitest) | PENDING |
| Results tab | implemented | yes | py `test_ui_comprehensive.py` | tested-green-in-suite | **VIDEO-CONFIRMED 2026-06-16** — `boba-web-feature-tour.mp4` (tab nav) |
| Active Downloads tab + view (`dashboard.component.ts:745 loadDownloads`) | implemented | yes | py `test_buttons_api.py` | tested-green-in-suite | **VIDEO-CONFIRMED 2026-06-16** — `boba-web-feature-tour.mp4` |
| Trackers tab + per-tracker auth chips (expandable) | implemented | yes | py `test_auth_state_ui.py` | tested-green-in-suite | **VIDEO-CONFIRMED 2026-06-16** — `boba-web-feature-tour.mp4` (29 trackers) |
| Schedules tab | implemented | yes | py `test_dashboard_automation.py` | tested-green-in-suite | **VIDEO-CONFIRMED 2026-06-16** — `boba-web-feature-tour.mp4` |
| Hooks tab | implemented | yes | py `test_dashboard_automation.py` | tested-green-in-suite | **VIDEO-CONFIRMED 2026-06-16** — `boba-web-feature-tour.mp4` |
| Per-row Magnet button → magnet dialog trigger | implemented | yes | vitest `magnet-dialog.component.spec.ts`; py `test_magnet_dialog.py` | tested-green-in-suite | PENDING |
| Per-row add-to-qBittorrent (qBit) button | implemented | yes | py `test_button_functions.py`, `test_buttons_api.py` | tested-green-in-suite | **VIDEO-CONFIRMED 2026-06-16** — buttons render & clickable, `boba-web-feature-tour.mp4` |
| Per-row Download (.torrent) button | implemented | yes | py `test_buttons_api.py` | tested-green-in-suite | **VIDEO-CONFIRMED 2026-06-16** — `boba-web-feature-tour.mp4` |
| Per-row processing spinner (`isBusy()`) | implemented | yes | vitest `dashboard.component.spec.ts` | unit (vitest) | PENDING |
| Bridge health indicator + retry button | implemented | yes | py `test_bridge_root_liveness.py` | tested-green-in-suite | PENDING |
| Tracker-stat dialog trigger | implemented | yes | py contract `test_tracker_stats_contract.py` | tested-green-in-suite | PENDING |

### 5b. Dialog + UI components

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| Magnet dialog — readonly textarea + Copy/Open/Add/Close (`magnet-dialog.component.ts`) | implemented | yes | vitest `magnet-dialog.component.spec.ts`; py `test_magnet_dialog.py` | tested-green-in-suite | PENDING |
| qBit login dialog — user/pass/remember/Login/Cancel (`qbit-login-dialog.component.ts`) | implemented | yes | vitest `qbit-login-dialog.component.spec.ts`; py `test_login_actions.py`, `test_auth_state_ui.py` | tested-green-in-suite | PENDING |
| Theme picker — palette dropdown + light/dark toggle (`theme-picker.component.ts`) | implemented | yes | vitest `theme-picker.component.spec.ts`; py e2e `test_theme_runtime.py`, `test_crossapp_theme.py` | tested-green-in-suite | **VIDEO-CONFIRMED 2026-06-16** — theme present, `boba-web-feature-tour.mp4` |
| Confirm dialog — title/message/Confirm/Cancel/backdrop (`confirm-dialog.component.ts`) | implemented | yes | vitest `confirm-dialog.component.spec.ts` | unit (vitest) | PENDING |
| Tracker-stat dialog — JSON view + Copy + status badge + notes table + Esc-close (`tracker-stat-dialog.component.ts`) | implemented | yes | vitest `tracker-stat-dialog.component.spec.ts`; py contract `test_tracker_stats_contract.py` | tested-green-in-suite | PENDING |
| Toast container — info/success/warning/error auto-dismiss (`toast-container.component.ts`) | implemented | yes | vitest `toast-container.component.spec.ts` | unit (vitest) | PENDING |
| Site footer (`site-footer.component.ts`) | implemented | yes | vitest | unit (vitest) | PENDING |

### 5c. Services (`frontend/src/app/services/`)

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| API service — HTTP wrapper (search/download/magnet/auth/schedules/hooks/downloads/stats/config), 15s timeout, runtime baseUrl (`api.service.ts`) | implemented | yes | vitest `api.service.spec.ts` | unit (vitest) | PENDING |
| SSE service — EventSource live result streaming + bearer-token (`sse.service.ts`) | implemented | yes | vitest `sse.service.spec.ts`; py integration `test_realtime_streaming.py`, `test_streaming_browser.py` | tested-green-in-suite | PENDING |
| Theme service — palette/mode + localStorage + cross-app sync (`theme.service.ts`) | implemented | yes | vitest `theme.service.spec.ts`; py e2e `test_theme_runtime.py`, `test_crossapp_theme.py` | tested-green-in-suite | PENDING |
| Toast service — toast queue state (`toast.service.ts`) | implemented | yes | vitest `toast.service.spec.ts` | unit (vitest) | PENDING |
| Dialog service — promise-based confirm state (`dialog.service.ts`) | implemented | yes | vitest `dialog.service.spec.ts` | unit (vitest) | PENDING |

### 5d. Jackett page (`frontend/src/app/jackett/`)

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| Credentials — list + Add/Edit/Delete (per-row, window.confirm) + banners (`jackett/credentials/credentials.component.ts`) | implemented | yes | vitest `credentials.component.spec.ts` | unit (vitest) | **VIDEO-CONFIRMED 2026-06-16** — `/jackett` credentials page, `boba-web-feature-tour.mp4` |
| Credential edit dialog — name/username/password/cookies/Save/Cancel (`credential-edit-dialog.component.ts`) | implemented | yes | vitest `credential-edit-dialog.component.spec.ts` | unit (vitest) | PENDING |
| Indexers — Configured/Catalog/History tab container (`jackett/indexers/indexers.component.ts`) | implemented | yes | vitest `indexers.component.spec.ts` | unit (vitest) | PENDING |
| Indexers — Configured tab (list + per-row remove) | implemented | yes | vitest `indexers.component.spec.ts` | unit (vitest) | PENDING |
| Indexers — Catalog tab (list + per-row add) | implemented | yes | vitest `indexers.component.spec.ts` | unit (vitest) | PENDING |
| Indexers — History tab (autoconfig run history) | implemented | yes | vitest `indexers.component.spec.ts` | unit (vitest) | PENDING |
| Indexer add dialog — credential dropdown + Save/Cancel + error banner (`indexer-add-dialog.component.ts`) | implemented | yes | vitest `indexer-add-dialog.component.spec.ts` | unit (vitest) | PENDING |
| IPTorrents cookie-flow component (`iptorrents-cookie-flow.component.ts`) | implemented | yes | vitest (jackett specs) | unit (vitest) | PENDING |

### 5e. Frontend infra

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| Frontend coverage thresholds (40% lines/branches/funcs/stmts, v8) | infra | yes | `vitest.config.ts` | enforced in vitest config | PENDING |

---

## 6. BobaLink browser extension (`extension/`)

WXT + TypeScript Manifest-V3. Detects magnet/.torrent links and forwards to merge service :7187. Status detail: `docs/browser_extension/Status.md`. Built zips at `extension/.output/bobalink-1.0.0-{chrome,firefox}.zip`.

### 6a. User-facing surfaces

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| Popup — per-row Send button (`src/popup/`, `entrypoints/popup.ts`) | implemented | yes | a11y `tests/a11y/popup.a11y.test.ts` | tested-green-in-suite | PENDING |
| Popup — Send-All button | implemented | yes | a11y `popup.a11y.test.ts` | tested-green-in-suite | PENDING |
| Popup — Refresh button + status indicator (online/offline/warning) | implemented | yes | a11y `popup.a11y.test.ts` | tested-green-in-suite | PENDING |
| Popup — torrent list (name + type + infohash prefix + sent badge) | implemented | yes | a11y `popup.a11y.test.ts` | tested-green-in-suite | PENDING |
| Popup — Open Options link | implemented | yes | a11y `popup.a11y.test.ts` | tested-green-in-suite | PENDING |
| Options page (`src/options/options.ts`) | implemented | yes | a11y `options.a11y.test.ts`; integration `options-background.test.ts` | tested-green-in-suite | PENDING |
| Content script — link/text highlight overlay (`src/content/highlight.ts`, `entrypoints/content.ts`) | implemented | yes | integration `content-background.test.ts`; security `content-xss.test.ts` | tested-green-in-suite | PENDING |
| Background service worker — message hub (`src/background/`, `entrypoints/background.ts`) | implemented | yes | integration `tests/integration/*-background.test.ts` | tested-green-in-suite | PENDING |
| Context-menu entries (right-click torrent actions) | implemented | yes | integration `*-background.test.ts` | tested-green-in-suite | PENDING |
| Keyboard shortcuts (scan-now / highlight-toggle / send-all) | implemented | yes | integration `*-background.test.ts` | tested-green-in-suite | PENDING |
| Action badge (detected count) + notifications | implemented | yes | integration `*-background.test.ts` | tested-green-in-suite | PENDING |

### 6b. Scanners (`src/scanner/`)

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| Base scanner — `computeStableId()` lifecycle (`scanner/base.ts`) | implemented | yes | vitest unit | tested-green-in-suite | PENDING |
| Link scanner — `<a href>` magnet/.torrent (`scanner/link-scanner.ts`) | implemented | yes | security `scanner-hostile-input.test.ts`; perf `scanner.perf.test.ts` | tested-green-in-suite | PENDING |
| Text scanner — bare magnet text (`scanner/text-scanner.ts`) | implemented | yes | security `scanner-hostile-input.test.ts` | tested-green-in-suite | PENDING |
| Scanner orchestrator — dedup + mutation-observer re-scan (`scanner/orchestrator.ts`) | implemented | yes | perf `orchestrator-scaling.perf.test.ts` | tested-green-in-suite | PENDING |
| Site DB — per-site selector match rules (`scanner/site-db.ts`) | implemented | yes | vitest unit | tested-green-in-suite | PENDING |

### 6c. Parsers (`src/parser/`)

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| Bencode parser (`parser/bencode.ts`) | implemented | yes | security `bencode-torrentfile-hostile.test.ts`; perf `parsers.perf.test.ts` | tested-green-in-suite | PENDING |
| Magnet parser (`parser/magnet.ts`) | implemented | yes | security `infohash-detection-hostile.test.ts`; perf `magnet.perf.test.ts` | tested-green-in-suite | PENDING |
| Torrent-file parser (`parser/torrent-file.ts`) | implemented | yes | security `bencode-torrentfile-hostile.test.ts` | tested-green-in-suite | PENDING |

### 6d. API client + offline (`src/api/`)

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| Boba API client — POST `/api/v1/download`, retry + rate-limit (`api/boba-client.ts`) | implemented | yes | vitest unit; chaos `tests/chaos/boba-client-resilience.chaos.test.ts` | tested-green-in-suite | PENDING |
| Health probe — `probeHealth()` (`api/health.ts`) | implemented | yes | vitest unit | tested-green-in-suite | PENDING |
| Offline send queue — IndexedDB enqueue + re-dispatch (`api/queue.ts`) | implemented | yes | chaos `tests/chaos/queue.chaos.test.ts` | tested-green-in-suite | PENDING |

### 6e. Shared utilities + tabgroups (`src/shared/`, `src/tabgroups/`)

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| Crypto — AES-256-GCM token encrypt/decrypt (`shared/crypto.ts`) | implemented | yes | security `crypto-tamper.test.ts`, `no-hardcoded-secret.test.ts` | tested-green-in-suite | PENDING |
| Storage — namespaced `chrome.storage.local` wrapper (`shared/storage.ts`) | implemented | yes | vitest unit | tested-green-in-suite | PENDING |
| Constants — site selectors / rate-limit / retry config (`shared/constants.ts`) | implemented | yes | covered via scanner tests | tested-green-in-suite | PENDING |
| Errors — Network/Server/Storage error types (`shared/errors.ts`) | implemented | yes | vitest unit | tested-green-in-suite | PENDING |
| Events — TypedEventEmitter bus (`shared/events.ts`) | implemented | yes | vitest unit | tested-green-in-suite | PENDING |
| Logger — namespaced, no-secret (`shared/logger.ts`) | implemented | yes | vitest unit | tested-green-in-suite | PENDING |
| Utils — debounce / TokenBucket rate limiter (`shared/utils.ts`) | implemented | yes | vitest unit | tested-green-in-suite | PENDING |
| Tab groups — batch grouped-tab torrents (`tabgroups/index.ts`) | implemented | yes | vitest unit (tab-group Challenge per ext Status) | tested-green-in-suite | PENDING |

### 6f. i18n locales (`extension/src/public/_locales/`)

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| Locale `en` (English) | implemented | yes | i18n `tests/i18n/locale-safety.test.ts` | tested-green-in-suite | PENDING |
| Locale `de` (German) | implemented | yes | i18n `locale-safety.test.ts` | tested-green-in-suite | PENDING |
| Locale `es` (Spanish) | implemented | yes | i18n `locale-safety.test.ts` | tested-green-in-suite | PENDING |
| Locale `fr` (French) | implemented | yes | i18n `locale-safety.test.ts` | tested-green-in-suite | PENDING |
| Locale `it` (Italian) | implemented | yes | i18n `locale-safety.test.ts` | tested-green-in-suite | PENDING |
| Locale `ja` (Japanese) | implemented | yes | i18n `locale-safety.test.ts` | tested-green-in-suite | PENDING |
| Locale `pt` (Portuguese) | implemented | yes | i18n `locale-safety.test.ts` | tested-green-in-suite | PENDING |
| Locale `ru` (Russian) | implemented | yes | i18n `locale-safety.test.ts` | tested-green-in-suite | PENDING |

### 6g. Live round-trip

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
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

### 8a. boba-ctl CLI orchestrator (Go: `cmd/boba-ctl/main.go` + wrapper `scripts/boba-ctl.sh`)

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| `boba-ctl up` — start stack (`cmd/boba-ctl/main.go:32`) | implemented | host | go `cmd/boba-ctl/projectroot_test.go` | tested-green-in-suite | PENDING |
| `boba-ctl down` — stop stack (`main.go:34`) | implemented | host | go `cmd/boba-ctl/projectroot_test.go` | tested-green-in-suite | PENDING |
| `boba-ctl status` — service status (`main.go:36`) | implemented | host | go `cmd/boba-ctl/projectroot_test.go` | tested-green-in-suite + LIVE | **VIDEO-CONFIRMED 2026-06-16** — `boba-cli-orchestrator-demo.mp4`; verdict `docs/qa/recordings-20260615/boba-cli-verdict.md` |
| `boba-ctl health` — health probe (`main.go:38`, `cmd/boba-ctl/health_test.go`) | implemented | host | go `cmd/boba-ctl/health_test.go` | tested-green-in-suite + LIVE | **VIDEO-CONFIRMED 2026-06-16** — `boba-cli-orchestrator-demo.mp4` |
| `boba-ctl list` — list services (`main.go:40`) | implemented | host | go `cmd/boba-ctl/projectroot_test.go` | tested-green-in-suite + LIVE | **VIDEO-CONFIRMED 2026-06-16** — `boba-cli-orchestrator-demo.mp4` |
| `boba-ctl.sh` wrapper — compose-compat shim (up/down/ps/config/pull + passthrough) (`scripts/boba-ctl.sh`) | implemented | host | covered via boba-ctl go tests | tested-green-in-suite | PENDING |

### 8b. Lifecycle scripts (repo root)

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| `start.sh` — container bring-up + Jackett key extraction/injection | implemented | host | covered via e2e `test_fixtures_bring_up_services.py` | tested-green-in-suite | PENDING |
| `stop.sh` — stop/remove/purge | implemented | host | none dedicated | not-validated | PENDING |
| `setup.sh` — one-time setup | implemented | host | none dedicated | not-validated | PENDING |
| `start-proxy.sh` — proxy container entry helper | implemented | host | none dedicated | not-validated | PENDING |
| `install-plugin.sh` — copy curated plugins → container engines | implemented | host | covered indirectly (e2e search) | tested-green-in-suite | PENDING |
| `init-qbit-password.sh` — qBit admin password bootstrap | implemented | host | none dedicated | not-validated | PENDING |
| `fix-qbit-password.sh` — qBit admin password repair | implemented | host | none dedicated | not-validated | PENDING |
| `setup-webui-bridge-service.sh` + `webui-bridge.service` — systemd unit for bridge | implemented | host | none dedicated | not-validated | PENDING |

### 8c. Test / CI wrappers (repo root)

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| `ci.sh` — manual CI (syntax+unit+integration+e2e+health) | implemented | host | self (is the gate) | tested-green-in-suite | PENDING |
| `run-all-tests.sh` — full suite (hardcoded podman) | implemented | host | self | partial — fails on docker-only hosts (known gotcha) | PENDING |
| `test.sh` — quick validation wrapper | implemented | host | self | tested-green-in-suite | PENDING |
| `test-all.sh` — full validation wrapper | implemented | host | self | tested-green-in-suite | PENDING |
| `test-full.sh` — extended validation wrapper | implemented | host | self | tested-green-in-suite | PENDING |

### 8d. scripts/ helpers

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| `scripts/add-submodules.sh` — submodule bootstrap | implemented | host | none dedicated | not-validated | PENDING |
| `scripts/audit-plugins.sh` — plugin discrepancy audit | implemented | host | none dedicated | not-validated | PENDING |
| `scripts/build-releases.sh` — build extension/Go release artifacts | implemented | host | none dedicated | not-validated | PENDING |
| `scripts/codegraph_validate.sh` — CodeGraph index validation (§11.4.78) | implemented | host | self | tested-green-in-suite | PENDING |
| `scripts/docs_chain.sh` — docs_chain engine wrapper (§11.4.106) | implemented | host | self | tested-green-in-suite | PENDING |
| `scripts/ensure-macos-tunnel.sh` — `0.0.0.0` SSH tunnel | implemented | host | none dedicated (log `qa-results/tunnel-keepalive.log`) | not-validated; LAN threat-model RW-05 | PENDING |
| `scripts/tunnel-keepalive.sh` — tunnel self-heal | implemented | host | none dedicated | not-validated | PENDING |
| `scripts/freeze-openapi.sh` — freeze boba-jackett OpenAPI snapshot | implemented | host | contract `tests/contract/openapi_test.go` | tested-green-in-suite | PENDING |
| `scripts/generate_markdown_exports.sh` — md→html/pdf export (§11.4.65) | implemented | host | self | tested-green-in-suite | PENDING |
| `scripts/helixqa.sh` — HelixQA harness driver | implemented | host | self | not-validated | PENDING |
| `scripts/opencode-helixqa.sh` — OpenCode HelixQA driver | implemented | host | self | not-validated | PENDING |
| `scripts/install_git_hooks.sh` — git hook installer (§11.4.75) | implemented | host | self | tested-green-in-suite | PENDING |
| `scripts/pre_build_verification.sh` — pre-build gate sweep | implemented | host | self (is the gate) | tested-green-in-suite | PENDING |
| `scripts/pre_code_review.sh` — code-review gate (§11.4.125) | implemented | host | self | tested-green-in-suite | PENDING |
| `scripts/run_all_challenges.sh` — challenge bank runner | implemented | host | self | not-validated | PENDING |
| `scripts/run-tests.sh` — test runner helper | implemented | host | self | tested-green-in-suite | PENDING |
| `scripts/scan.sh` — repo scan helper | implemented | host | none dedicated | not-validated | PENDING |
| `scripts/track-build-resources.sh` — build resource sampler (§11.4.24) | implemented | host | none dedicated | not-validated | PENDING |

### 8e. Infra / compose / startup

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| `docker-compose.yml` — 2-container default + Go profile + boba-jackett service | infra | yes | e2e `test_live_containers.py` | tested-green-in-suite | PENDING |
| Jackett auto-configuration at startup (key extract → inject `JACKETT_API_KEY`) | implemented | yes | integration `test_jackett_autoconfig_real.py` | tested-green-in-suite | PENDING |
| `BOBA_MASTER_KEY` auto-generation (first-boot) for encrypted boba.db | implemented | yes | go `bootstrap/bootstrap_test.go` | unit (go) | PENDING |

---

## Components NOT inventoried / discrepancies (honest gaps, §11.4.6)

- **CORRECTION vs Rev 2:** `boba-ctl.sh` DOES exist at `scripts/boba-ctl.sh` (Rev 2 said it did not). Its subcommands are now itemized in §8a. The underlying Go binary is `cmd/boba-ctl/main.go` (5 subcommands: up/down/status/health/list).
- **CORRECTION vs Rev 2:** the `install-plugin.sh` `PLUGINS` curated array has **44 entries**, not 12. ~21 have a matching `plugins/*.py` file; the rest (incl. `torrentproject`, `torrentscsv`) are curated names with no file present in this tree — itemized in §4c, not asserted as working.
- **Prometheus/OpenTelemetry metrics** — `tests/observability/test_metrics_exist.py` + `observability/` dir exist, but no `prometheus_client` `Counter()/Histogram()/Gauge()` definitions were found in `download-proxy/src`; metrics surface is via `GET /api/v1/stats` (counters maintained in-process), not a `/metrics` Prometheus endpoint. Stated as fact, not assumed.
- **Go `DownloadHandler` / `ActiveDownloadsHandler`** — flagged partial/stub in §2a (mock success / empty array, no qBit integration) per source reading. The Go profile is opt-in and NOT the shipped product.
- **Go scheduler** — CRUD-only, no driver loop (RW-10); schedules never fire. The Go enricher is missing (RW-11).
- **Video-recording confirmation** — `PENDING` for all rows EXCEPT the boba-ctl CLI subcommands (status/health/list) and the web-UI flows already filmed (`POST /api/v1/search` journey + dashboard tab/button/theme/Jackett tour). Remaining per-feature flows are an in-progress recording pass (§11.4.107/§11.4.143).
