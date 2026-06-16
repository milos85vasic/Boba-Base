# Boba — Feature Status (all components)

**Revision:** 7
**Last modified:** 2026-06-16T23:30:00Z
**Scope:** Every system component, service, infrastructure piece, and client app of the Boba project — one row per REAL unit (endpoint / handler / client method / component control / plugin / subcommand / script), grouped by component.
**Authority:** assembled by READ-ONLY repo inventory (codegraph + grep + source reading) on 2026-06-15, expanded to per-unit granularity (§11.4.118 discovery-pressure) on 2026-06-16. Cross-references `AGENTS.md`, `CLAUDE.md`, `docs/REMAINING_WORK_PLAN.md`.

> **Rev 7 (2026-06-16) — live-PASS update for the search/auth fix batch (HEAD `7e9cab5`):** the multi-word URL-encoding fix (`da7d709`, ~17 nova3 plugins), the new `RUTRACKER_COOKIES` injection (`2fc29fc`), `NNMCLUB_COOKIES` auth, `/auth/status` cookie reflection (`9c2f8dc`), the new `GET /api/v1/healthz` JSON endpoint (`137d7ff`), and §11.4.85 stress+chaos coverage for the multi-word fix (`7e9cab5`) were all PROVEN end-to-end on the live nezha stack — full-fleet `the matrix` = **2600 results / 23 contributing trackers / zero `plugin_bad_query_encoding`**, all four private trackers authenticate (rutracker 50, nnmclub 50, kinozal 50, iptorrents 49). Evidence: `docs/qa/search-fix-verify-20260616/`. `kickass.py` reclassified **Won't-fix structurally-impossible (§11.4.112)** per `docs/research/kickass_403_20260616/`. NOTE (§11.4.6): no Go files were touched this session — the Go rows are unchanged (the pre-existing `magnet_stress_chaos_test.go` guard stands; no NEW Go query-encoding guard was added this session, so none is claimed here).

> Captured-evidence-driven (§11.4.5 / §11.4.45 / §11.4.86). Every feature row cites a real source file (file:line where load-bearing), endpoint, command, or control. **No invented features** (§11.4.6). As of Rev 5 the **Video** column is DEFINITIVE for every row — there is no bare `PENDING`. Each cell is exactly one of: `VIDEO-CONFIRMED — <file>` (the feature is shown on-screen in a committed recording), `PENDING (UI — film next)` (a user-visible control/dialog not yet *individually* filmed), or `N/A (no UI — test-covered + exercised by <journey>)` (a non-user-visible unit — REST endpoint / handler / client method / parser / scanner / service / crypto / repo / script — which has no screen of its own and is confirmed by its cited tests plus the UI/CLI journey that drives it). **Honest classification (§11.4.6/§11.4.143): a row is `VIDEO-CONFIRMED` only when a real recording actually shows it.**
>
> Per-row Video tally (288 feature rows): **28 VIDEO-CONFIRMED**, **14 PENDING (UI — film next)**, **246 N/A (no UI — test-covered)**.
>
> Column legend:
> - **Impl** = implemented / partial / stub / missing
> - **Wired** = reachable on a running default-profile stack (yes / no / opt-in / host)
> - **Tests** = test types present + cite file (unit / integration / e2e / security / stress-chaos / property / contract); `none` if no covering test found
> - **Validation** = honest validation posture (tested-green-in-suite / unit-only / live-evidence-captured / not-validated / operator-blocked)
> - **Video** = DEFINITIVE video-recording status — one of `VIDEO-CONFIRMED — <file>` / `PENDING (UI — film next)` / `N/A (no UI — test-covered + exercised by <journey>)`

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
| `boba-extension-{scan-detect,popup,options,tour}.mp4` | BobaLink extension (MV3, real `--load-extension` Chromium) | content-script **detects a magnet + appends a 🌐 MAGNET badge** (non-torrent correctly skipped); popup UI (header, server status, Refresh + Send All, Detected-torrents); options page (7 settings tabs + server config) | `boba-extension-verdict.md` |
| `boba-web-tabs-theme-tour.mp4` (+ frames `boba-web-tab-active-downloads.png` / `boba-web-tab-schedules.png` / `boba-web-tab-hooks.png` / `boba-web-theme-toggle.png`) + `boba-web-jackett-add-credential.png` | Web dashboard + Jackett page | Active Downloads / Schedules / Hooks tabs each render their empty-state + columns; **theme toggle**; **processing spinner** ("Found N results…"); **bridge/qBit-Connected header indicator**; Jackett **Add-credential dialog** (Name/Username/Password/Cookies + Cancel/Save) | Claude-vision verified 2026-06-16 |

**Honest scope (§11.4.6, no bluff):**
- **Backend services** (download-proxy / merge / boba-jackett / Go) verified **200 server-side inside the VM** and exercised through the web UI recordings.
- **Console errors** seen in the web recordings are an **SSH-tunnel SSE/poll artifact** (macOS↔VM), NOT product defects — every endpoint is 200 in the VM. See the feature-tour verdict.
- **BobaLink extension**: ✅ **VIDEO-CONFIRMED** — the prior `--load-extension` tooling gap was closed by building `extension/scripts/record-features.mjs` (loads the built MV3 artifact into a real Chromium, records the scan/popup/options journeys). Plus its passing test suite.
- **TUI / mobile / desktop**: do not exist in this project (server-side + Angular web + browser extension only) — nothing to record.

---

## Component summary

| # | Component | Service / Port | Features cataloged |
|---|-----------|----------------|--------------------|
| 1 | Download Proxy + Merge Search Service (Python/FastAPI) | `qbittorrent-proxy` :7186 / :7187 | 69 |
| 2 | qBitTorrent-go backend (Go/Gin) | `qbittorrent-proxy-go` :7186/:7187/:7188 (opt-in `--profile go`) | 47 |
| 3 | boba-jackett (Go) | `boba-jackett` :7189 | 26 |
| 4 | Tracker plugins (`plugins/*.py`) | run inside `qbittorrent-proxy` | 30 |
| 5 | Angular 21 frontend dashboard (`frontend/`) | served from :7187 | 34 |
| 6 | BobaLink browser extension (`extension/`) | WXT MV3 client | 39 |
| 7 | WebUI bridge (`webui-bridge.py`) | host process :7188 | 4 |
| 8 | Infrastructure / CLI / shell scripts | host | 40 |

**Total features cataloged: 289** (Rev 7: +1 — new `GET /api/v1/healthz` endpoint)

---

## 1. Download Proxy + Merge Search Service (Python/FastAPI) — `:7186` / `:7187`

Entry: `download-proxy/src/main.py` (starts legacy proxy thread + uvicorn `api:app`). This is the **shipped default product**.

### 1a. Merge Search Service — REST API (`download-proxy/src/api/routes.py`)

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| `POST /api/v1/search` — async fan-out search, returns search_id (`routes.py:283`) | implemented | yes | integration `tests/integration/test_merge_api.py`; e2e `test_full_pipeline.py`; stress `test_merge_search_stress_chaos.py` | tested-green-in-suite + LIVE | **VIDEO-CONFIRMED 2026-06-16** — real web-UI journey (`debian`→829 found/288 merged), `boba-web-search-flow.mp4`; verdict `docs/qa/recordings-20260615/boba-web-search-flow-verdict.md` |
| `POST /api/v1/search/sync` — synchronous search (`routes.py:377`) | implemented | yes | integration `test_merge_api.py`; stress `test_search_stress.py` | tested-green-in-suite; resets over tunnel (RW-08) | N/A (no UI — test-covered + exercised by web search flow) |
| `GET /api/v1/search/stream/{id}` — SSE result stream (`routes.py:547`) | implemented | yes | integration `test_realtime_streaming.py`, `test_streaming_browser.py` | tested-green-in-suite | N/A (no UI — test-covered + exercised by web search flow live-results stream) |
| `GET /api/v1/search/{id}` — poll search state (`routes.py:586`) | implemented | yes | integration `test_merge_api.py` | tested-green-in-suite | N/A (no UI — test-covered + exercised by web search flow) |
| `POST /api/v1/search/{id}/abort` — cancel in-flight search (`routes.py:619`) | implemented | yes | integration `test_merge_api.py` | tested-green-in-suite | N/A (no UI — test-covered + exercised by web search flow) |
| `GET /api/v1/downloads/active` — qBit active torrents (`routes.py:629`) | implemented | yes | integration `test_buttons_api.py` | tested-green-in-suite | N/A (no UI — test-covered + exercised by web dashboard Active Downloads tab) |
| `POST /api/v1/auth/qbittorrent` — qBit WebUI login (`routes.py:671`) | implemented | yes | integration `test_login_actions.py` | tested-green-in-suite | N/A (no UI — test-covered + exercised by web qBit login dialog) |
| `POST /api/v1/download` — add torrent to qBit (magnet/url) (`routes.py:958`) | implemented | yes | integration `test_button_functions.py`, `test_buttons_api.py`; security `test_ssrf_and_magnet_auth.py` | tested-green-in-suite; SSRF gap RW-03 | N/A (no UI — test-covered + exercised by web result-row qBit button) |
| `POST /api/v1/download/upload` — upload .torrent file to qBit (`routes.py:1123`) | implemented | yes | unit `tests/unit/api_layer/test_download_upload.py` | unit-only + integration | N/A (no UI — test-covered + exercised by web download path) |
| `POST /api/v1/download/file` — fetch tracker .torrent w/ auth cookies (`routes.py:1212`) | implemented | yes | integration `test_buttons_api.py`; security `test_ssrf_and_magnet_auth.py` | tested-green-in-suite; SSRF gap RW-03 | N/A (no UI — test-covered + exercised by web result-row Download button) |
| `POST /api/v1/magnet` — resolve result → magnet link (`routes.py:1279`) | implemented | yes | integration `test_magnet_dialog.py`, `test_buttons_api.py` | tested-green-in-suite; auth gap RW-04 | N/A (no UI — test-covered + exercised by web magnet dialog) |
| `GET /api/v1/theme` — read theme state (`routes.py:61`) | implemented | yes | contract `test_crossapp_theme_contract.py` | tested-green-in-suite | N/A (no UI — test-covered + exercised by web theme picker) |
| `PUT /api/v1/theme` — persist theme (`routes.py:67`) | implemented | yes | e2e `test_theme_runtime.py`, `test_crossapp_theme.py` | tested-green-in-suite | N/A (no UI — test-covered + exercised by web theme picker) |
| `GET /api/v1/theme/stream` — SSE theme broadcast (`routes.py:76`) | implemented | yes | e2e `test_crossapp_theme.py` | tested-green-in-suite | N/A (no UI — test-covered + exercised by web theme picker cross-app sync) |

### 1b. Auth API — per-tracker (`download-proxy/src/api/auth.py`)

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| `GET /auth/rutracker/status` — RuTracker session state (`auth.py:56`) | implemented | yes | integration `test_auth_and_links.py`; e2e `test_live_stack_evidence.py` | partial — CAPTCHA operator-blocked (BOB-008) | N/A (no UI — test-covered + exercised by web Trackers tab auth chips) |
| `GET /auth/rutracker/captcha` — fetch CAPTCHA image (`auth.py:108`) | implemented | yes | integration `test_auth_and_links.py` | partial — operator-blocked (BOB-008) | N/A (no UI — test-covered + exercised by web Trackers tab auth chips) |
| `POST /auth/rutracker/login` — username/password + CAPTCHA login (`auth.py:214`) | implemented | yes | integration `test_auth_and_links.py` | partial — operator-blocked (BOB-008) | N/A (no UI — test-covered + exercised by web Trackers tab auth chips) |
| `POST /auth/rutracker/cookie-login` — cookie-based login (`auth.py:298`) | implemented | yes | integration `test_auth_and_links.py` | **PASS — LIVE 2026-06-16** — `RUTRACKER_COOKIES` cookie path authenticates (`2fc29fc`); rutracker `the matrix` = 50 real results on nezha (`docs/qa/search-fix-verify-20260616/` §1) | N/A (no UI — test-covered + exercised by web Trackers tab auth chips) |
| `GET /auth/nnmclub/status` — NNM-Club session state (`auth.py:350`) | implemented | yes | e2e `test_live_stack_evidence.py:265` (skips — SOURCE→ARTIFACT drift RW-07) | partial — route 404 on running container (RW-07) | N/A (no UI — test-covered + exercised by web Trackers tab auth chips) |
| `POST /auth/nnmclub/login` — NNM-Club login (`auth.py:407`) | implemented | yes | e2e `test_live_stack_evidence.py` | partial — live-gated | N/A (no UI — test-covered + exercised by web Trackers tab auth chips) |
| `GET /auth/status` — all-tracker aggregate session state (`auth.py:479`) | implemented | yes | integration `test_auth_state_ui.py`; auth-status cookie-reflection test (§1.1) | **PASS — LIVE 2026-06-16** — now reflects `RUTRACKER_COOKIES`/`NNMCLUB_COOKIES` env before first search (`9c2f8dc`), so dashboard chips show rutracker/nnmclub green (`docs/qa/search-fix-verify-20260616/` §3) | N/A (no UI — test-covered + exercised by web Trackers tab auth chips) |
| `POST /auth/qbittorrent/logout` — qBit WebUI logout (`auth.py:532`) | implemented | yes | integration `test_login_actions.py` | tested-green-in-suite | N/A (no UI — test-covered + exercised by web qBit login dialog) |
| Kinozal auth (status/login) REST route | **missing** | no | none — no `kinozal/login` route in `auth.py` | not-implemented (search path uses cookies via orchestrator) | N/A (not implemented — no route) |
| IPTorrents auth (status/login) REST route | **missing** | no | none — no `iptorrents/login` route in `auth.py` | not-implemented (env creds + cookie flow via Jackett UI) | N/A (not implemented — no route) |

### 1c. Search orchestration internals (`download-proxy/src/merge_service/search.py`)

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| Concurrency caps `MAX_CONCURRENT_SEARCHES` (429 on saturation) | implemented | yes | concurrency `test_orchestrator_semaphore.py` | tested-green-in-suite | N/A (no UI — test-covered + exercised by web search flow) |
| Per-search tracker semaphore `MAX_CONCURRENT_TRACKERS` | implemented | yes | concurrency `test_tracker_semaphore.py` | tested-green-in-suite | N/A (no UI — test-covered + exercised by web search flow) |
| Public-tracker subprocess fan-out (NDJSON via patched novaprinter) | implemented | yes | e2e `test_public_trackers_return_results.py`; stress `test_search_orchestration_stress_chaos.py` | tested-green-in-suite | N/A (no UI — test-covered + exercised by web search flow live results) |
| Public-tracker deadline kill `PUBLIC_TRACKER_DEADLINE_SECONDS` | implemented | yes | chaos `test_tracker_failure.py` | tested-green-in-suite | N/A (no UI — test-covered + exercised by web search flow) |
| Private-tracker aiohttp+cookie path (rutracker/kinozal/nnmclub/iptorrents) | implemented | yes | integration `test_tracker_auth_live.py` (live-gated) | partial — live-gated, BOB-008 operator-blocked | N/A (no UI — test-covered + exercised by web search flow) |
| Per-tracker `TrackerSearchStat` real-time stats | implemented | yes | contract `test_tracker_stats_contract.py`; property `test_tracker_stats_properties.py` | tested-green-in-suite | N/A (no UI — test-covered + exercised by web tracker-stat dialog) |
| Stderr error classification (`_classify_plugin_stderr`) | implemented | yes | chaos `test_tracker_failure.py` | tested-green-in-suite | N/A (no UI — test-covered + exercised by web search flow) |
| TTL-bounded data stores (cachetools) — no leak | implemented | yes | memory `test_orchestrator_caches_bounded.py` | tested-green-in-suite | N/A (no UI — test-covered + exercised by web search flow) |

### 1d. Deduplication (`download-proxy/src/merge_service/deduplicator.py`)

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| Tier 1 dedup — metadata (imdb/tmdb) key | implemented | yes | property `test_deduplicator_properties.py`; benchmark `test_deduplication_benchmark.py` | tested-green-in-suite | N/A (no UI — test-covered + exercised by web search flow "288 merged" result) |
| Tier 2 dedup — infohash key | implemented | yes | property `test_deduplicator_properties.py` | tested-green-in-suite | N/A (no UI — test-covered + exercised by web search flow "288 merged" result) |
| Tier 3 dedup — name+size key | implemented | yes | property `test_deduplicator_properties.py` | tested-green-in-suite | N/A (no UI — test-covered + exercised by web search flow "288 merged" result) |
| Tier 4 dedup — fuzzy Levenshtein name match | implemented | yes | property `test_deduplicator_properties.py`; benchmark `test_deduplication_benchmark.py` | tested-green-in-suite | N/A (no UI — test-covered + exercised by web search flow "288 merged" result) |

### 1e. Enrichment — per metadata source (`download-proxy/src/merge_service/enricher.py`)

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| Enrichment: OMDb (`enricher.py:113`) | implemented | yes | stress `test_enricher_stress_chaos.py` | tested-green-in-suite; needs `OMDB_API_KEY` | N/A (no UI — test-covered + exercised by web search flow result quality column) |
| Enrichment: TMDB | implemented | yes | stress `test_enricher_stress_chaos.py` | tested-green; needs `TMDB_API_KEY` | N/A (no UI — test-covered + exercised by web search flow result quality column) |
| Enrichment: TVMaze | implemented | yes | stress `test_enricher_stress_chaos.py` | tested-green-in-suite | N/A (no UI — test-covered + exercised by web search flow result quality column) |
| Enrichment: AniList | implemented | yes | stress `test_enricher_stress_chaos.py` | tested-green-in-suite | N/A (no UI — test-covered + exercised by web search flow result quality column) |
| Enrichment: MusicBrainz | implemented | yes | stress `test_enricher_stress_chaos.py` | tested-green-in-suite | N/A (no UI — test-covered + exercised by web search flow result quality column) |
| Enrichment: OpenLibrary | implemented | yes | stress `test_enricher_stress_chaos.py` | tested-green-in-suite | N/A (no UI — test-covered + exercised by web search flow result quality column) |

### 1f. Tracker validation (`download-proxy/src/merge_service/validator.py`)

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| Tracker validation HTTP scrape BEP 48 (`validator.py:101`) | implemented | yes | none dedicated found (covered via merge tests) | not-validated (no dedicated test) | N/A (no UI — exercised by web search flow seeds/leechers column) |
| Tracker validation UDP scrape BEP 15 (`validator.py:162`) | implemented | yes | none dedicated found | not-validated (no dedicated test) | N/A (no UI — exercised by web search flow seeds/leechers column) |

### 1g. Hooks (`download-proxy/src/api/hooks.py` + `merge_service/hooks.py`)

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| `GET /api/v1/hooks` — list hooks (`hooks.py:105`) | implemented | yes | unit `test_hooks_coverage.py`; concurrency `test_hooks_race.py`; security `test_hooks_schedules_auth.py` | tested-green-in-suite; auth gap RW-01 | N/A (no UI — test-covered + exercised by web dashboard Hooks tab) |
| `POST /api/v1/hooks` — create hook (`hooks.py:111`) | implemented | yes | unit `test_hooks_coverage.py`; concurrency `test_hooks_race.py` | tested-green-in-suite; auth gap RW-01 | N/A (no UI — test-covered + exercised by web dashboard Hooks tab) |
| `DELETE /api/v1/hooks/{id}` — delete hook (`hooks.py:167`) | implemented | yes | unit `test_hooks_coverage.py` | tested-green-in-suite; auth gap RW-01 | N/A (no UI — test-covered + exercised by web dashboard Hooks tab) |
| `GET /api/v1/hooks/logs` — hook execution logs (`hooks.py:179`) | implemented | yes | unit `test_hooks_coverage.py` | tested-green-in-suite | N/A (no UI — test-covered + exercised by web dashboard Hooks tab) |
| Hook event dispatch (8 events: search_start..validation_complete) (`hooks.py:32`) | implemented | yes | concurrency `test_hooks_race.py` | tested-green-in-suite | N/A (no UI — test-covered, internal dispatch) |
| Hook subprocess execution + sandbox (`merge_service/hooks.py`) | implemented | yes | security `test_no_shell_injection.py` | tested-green; sandbox hardening RW-01 | N/A (no UI — test-covered, internal subprocess sandbox) |

### 1h. Scheduler (`download-proxy/src/api/scheduler.py` + `merge_service/scheduler.py`)

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| `GET /api/v1/schedules` — list schedules (`scheduler.py:39`) | implemented | yes | security `test_hooks_schedules_auth.py` | tested-green-in-suite; auth gap RW-02 | N/A (no UI — test-covered + exercised by web dashboard Schedules tab) |
| `POST /api/v1/schedules` — create schedule (`scheduler.py:64`) | implemented | yes | security `test_hooks_schedules_auth.py` | tested-green-in-suite; auth gap RW-02 | N/A (no UI — test-covered + exercised by web dashboard Schedules tab) |
| `GET /api/v1/schedules/{id}` — get schedule (`scheduler.py:87`) | implemented | yes | security `test_hooks_schedules_auth.py` | tested-green-in-suite | N/A (no UI — test-covered + exercised by web dashboard Schedules tab) |
| `PATCH /api/v1/schedules/{id}` — update schedule (`scheduler.py:108`) | implemented | yes | security `test_hooks_schedules_auth.py` | tested-green-in-suite | N/A (no UI — test-covered + exercised by web dashboard Schedules tab) |
| `DELETE /api/v1/schedules/{id}` — delete schedule (`scheduler.py:126`) | implemented | yes | security `test_hooks_schedules_auth.py` | tested-green-in-suite | N/A (no UI — test-covered + exercised by web dashboard Schedules tab) |
| Scheduler engine (load/save/tick driver) (`merge_service/scheduler.py`) | implemented | yes | integration `test_dashboard_automation.py` | tested-green-in-suite | N/A (no UI — test-covered, internal tick driver) |

### 1i. App-level routes / health / config / dashboard (`download-proxy/src/api/__init__.py`)

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| `GET /api/v1/healthz` — machine-parsable JSON health probe (`routes.py:37`) | implemented | yes | integration `test_merge_api.py` | **PASS — LIVE 2026-06-16** — NEW endpoint (`137d7ff`): a bare `/healthz` was swallowed by the SPA catch-all; now mounted under `/api/v1` returning JSON (§11.4.43) | N/A (no UI — JSON health probe; test-covered) |
| `GET /health` (`__init__.py:168`) | implemented | yes | integration `test_live_containers.py` | tested-green-in-suite | N/A (no UI — test-covered + exercised by boba-ctl health CLI) |
| `GET /api/v1/bridge/health` (`__init__.py:173`) | implemented | yes | integration `test_bridge_root_liveness.py` | tested-green-in-suite | N/A (no UI — test-covered + exercised by web bridge health indicator) |
| `GET /api/v1/config` (`__init__.py:247`) | implemented | yes | integration `test_merge_api.py` | tested-green-in-suite | N/A (no UI — test-covered + exercised by web dashboard bootstrap) |
| `GET /api/v1/stats` (`__init__.py:276`) | implemented | yes | observability `test_metrics_exist.py` | tested-green-in-suite | N/A (no UI — test-covered + exercised by web tracker-stat dialog) |
| Jinja2 dashboard `GET /` (`__init__.py:337`) | implemented | yes | integration `test_dashboard_rendering.py` | tested-green-in-suite | N/A (route — serves the web dashboard SPA; the dashboard itself is VIDEO-CONFIRMED, `boba-web-feature-tour.mp4`) |
| Jinja2 dashboard `GET /dashboard` (`__init__.py:342`) | implemented | yes | integration `test_dashboard_rendering.py` | tested-green-in-suite | N/A (route — serves the web dashboard SPA; the dashboard itself is VIDEO-CONFIRMED, `boba-web-feature-tour.mp4`) |
| SPA catch-all `GET /{path:path}` (`__init__.py:347`) | implemented | yes | integration `test_dashboard_rendering.py` | tested-green-in-suite | N/A (route — serves SPA deep links incl. `/jackett`, VIDEO-CONFIRMED via `boba-web-feature-tour.mp4`) |

### 1j. Supporting subsystems (Python)

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| Retry helpers (`merge_service/retry.py`) | implemented | yes | covered indirectly | unit-only | N/A (no UI — test-covered, internal helper) |
| Jackett autoconfig (Python, `merge_service/jackett_autoconfig.py`) — legacy; canonical is boba-jackett | implemented | yes | contract `test_jackett_autoconfig_contract.py`; e2e `test_jackett_autoconfig_e2e.py`; benchmark `test_jackett_autoconfig_perf.py` | tested-green-in-suite | N/A (no UI — test-covered, legacy internal; canonical path is boba-jackett) |
| Credential scrubbing log filter (`config/log_filter.py`) | implemented | yes | security `test_credential_scrubbing.py` | tested-green-in-suite | N/A (no UI — test-covered, internal log filter) |

### 1k. Legacy download proxy (`plugins/download_proxy.py` :7186)

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| HTTP proxy → qBittorrent WebUI w/ tracker URL interception (`DownloadHandler` :767) | implemented | yes | integration `test_bridge_header_rewrite.py` | tested-green-in-suite | N/A (no UI of its own — proxy layer; test-covered) |
| Theme injection into proxied WebUI (`plugins/theme_injector.py`) | implemented | yes | integration `test_bridge_theme_injection.py` | tested-green-in-suite | N/A (no UI of its own — proxy theme injection; test-covered) |

---

## 2. qBitTorrent-go backend (Go/Gin) — opt-in `--profile go`

Entry: `qBitTorrent-go/cmd/qbittorrent-proxy/main.go` (routes registered `:54-101`). **Skeleton/rewrite-in-progress** (per AGENTS.md + `docs/migration/PARITY_GAPS.md`). NOT running by default.

### 2a. HTTP handlers (`internal/api/*.go`)

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| `GET /health` — `HealthHandler` (`api/health.go:5`) | implemented | opt-in | go `internal/api/api_test.go` | unit-only (go test) | N/A (no UI — go-test-covered; opt-in profile, not shipped default) |
| `GET /api/v1/config` — `ConfigHandler` (`api/download.go:210`) | implemented | opt-in | go `coverage_test.go` | unit-only | N/A (no UI — go-test-covered; opt-in profile) |
| `GET /api/v1/bridge/health` — `BridgeHealthHandler` (`api/download.go:189`) | implemented | opt-in | go `coverage_test.go` | unit-only | N/A (no UI — go-test-covered; opt-in profile) |
| `POST /api/v1/search` — `SearchHandler` (`api/search.go:14`) | implemented (proxies qBit search; no plugin fan-out) | opt-in | go `api_test.go`, `coverage_test.go` | unit-only | N/A (no UI — go-test-covered; opt-in profile) |
| `POST /api/v1/search/sync` — `SearchSyncHandler` (`api/search.go:50`) | implemented | opt-in | go `coverage_test.go` | unit-only | N/A (no UI — go-test-covered; opt-in profile) |
| `GET /api/v1/search/stream/:id` — `SearchStreamHandler` SSE (`api/search.go:91`) | implemented | opt-in | go `coverage_test.go` | unit-only | N/A (no UI — go-test-covered; opt-in profile) |
| `GET /api/v1/search/:id` — `GetSearchHandler` (`api/search.go:144`) | implemented | opt-in | go `getsearch_results_test.go`, `coverage_test.go` | unit-only | N/A (no UI — go-test-covered; opt-in profile) |
| `POST /api/v1/search/:id/abort` — `AbortSearchHandler` (`api/search.go:177`) | implemented | opt-in | go `coverage_test.go` | unit-only | N/A (no UI — go-test-covered; opt-in profile) |
| `POST /api/v1/download` — `DownloadHandler` (`api/download.go:17`) | **partial — returns mock success, no qBit integration** | opt-in | go `coverage_test.go` | unit-only; functional hole | N/A (no UI — go-test-covered; opt-in profile; functional hole RW) |
| `POST /api/v1/download/file` — `DownloadFileHandler` (`api/download.go:41`) | implemented | opt-in | go `coverage_test.go` | unit-only | N/A (no UI — go-test-covered; opt-in profile) |
| `POST /api/v1/magnet` — `MagnetHandler` (`api/download.go:86`) | implemented | opt-in | go `api_test.go`, `magnet_stress_chaos_test.go` | unit + stress-chaos (go) | N/A (no UI — go-test-covered; opt-in profile) |
| `GET /api/v1/downloads/active` — `ActiveDownloadsHandler` (`api/download.go:147`) | **stub — returns empty array, no qBit query** | opt-in | go `coverage_test.go` | unit-only; functional hole | N/A (no UI — go-test-covered; opt-in profile; stub RW) |
| `POST /api/v1/auth/qbittorrent` — `QBittorrentAuthHandler` (`api/download.go:156`) | implemented | opt-in | go `coverage_test.go` | unit-only | N/A (no UI — go-test-covered; opt-in profile) |
| `GET /api/v1/theme` — `GetThemeHandler` (`api/theme.go:90`) | implemented | opt-in | go `theme_hardening_test.go`, `coverage_test.go` | unit-only | N/A (no UI — go-test-covered; opt-in profile) |
| `PUT /api/v1/theme` — `PutThemeHandler` (`api/theme.go:96`) | implemented | opt-in | go `theme_hardening_test.go` | unit-only | N/A (no UI — go-test-covered; opt-in profile) |
| `GET /api/v1/hooks` — `ListHooksHandler` (`api/hooks.go:91`) | implemented (store only, no dispatch) | opt-in | go `api_test.go`, `coverage_test.go` | unit-only | N/A (no UI — go-test-covered; opt-in profile) |
| `POST /api/v1/hooks` — `CreateHookHandler` (`api/hooks.go:97`) | implemented (store only) | opt-in | go `api_test.go` | unit-only | N/A (no UI — go-test-covered; opt-in profile) |
| `DELETE /api/v1/hooks/:id` — `DeleteHookHandler` (`api/hooks.go:109`) | implemented (store only) | opt-in | go `api_test.go` | unit-only | N/A (no UI — go-test-covered; opt-in profile) |
| `GET /api/v1/schedules` — `ListSchedulesHandler` (`api/scheduler_api.go:86`) | implemented (store only) | opt-in | go `coverage_test.go` | unit-only; **no driver loop (RW-10), schedules never fire** | N/A (no UI — go-test-covered; opt-in profile; never fires RW-10) |
| `POST /api/v1/schedules` — `CreateScheduleHandler` (`api/scheduler_api.go:92`) | implemented (store only) | opt-in | go `coverage_test.go` | unit-only; never fires (RW-10) | N/A (no UI — go-test-covered; opt-in profile; never fires RW-10) |
| `DELETE /api/v1/schedules/:id` — `DeleteScheduleHandler` (`api/scheduler_api.go:104`) | implemented (store only) | opt-in | go `coverage_test.go` | unit-only | N/A (no UI — go-test-covered; opt-in profile) |

### 2b. qBittorrent Web API client (`internal/client/*.go`)

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| `NewClient` — construct + login (`client/client.go:18`) | implemented | opt-in | go `client/client_test.go` | unit-only | N/A (no UI — go-test-covered client method; opt-in profile) |
| `Login` — POST `/api/v2/auth/login`, store SID (`client/auth.go:11`) | implemented | opt-in | go `client/auth_test.go` | unit-only | N/A (no UI — go-test-covered client method; opt-in profile) |
| `IsAuthenticated` — SID presence (`client/auth.go:43`) | implemented | opt-in | go `client/auth_test.go` | unit-only | N/A (no UI — go-test-covered client method; opt-in profile) |
| `GetSID` — thread-safe SID accessor (`client/client.go:39`) | implemented | opt-in | go `client/client_test.go` | unit-only | N/A (no UI — go-test-covered client method; opt-in profile) |
| `GetTorrents` — GET `/api/v2/torrents/info` (`client/torrents.go:13`) | implemented | opt-in | go `client/coverage_test.go` | unit-only | N/A (no UI — go-test-covered client method; opt-in profile) |
| `AddTorrent` — POST `/api/v2/torrents/add` URL (`client/torrents.go:30`) | implemented | opt-in | go `client/coverage_test.go` | unit-only | N/A (no UI — go-test-covered client method; opt-in profile) |
| `AddTorrentFile` — POST multipart `/api/v2/torrents/add` (`client/torrents.go:54`) | implemented | opt-in | go `client/coverage_test.go` | unit-only | N/A (no UI — go-test-covered client method; opt-in profile) |
| `GetAppVersion` — GET `/api/v2/app/version` (`client/torrents.go:87`) | implemented | opt-in | go `client/coverage_test.go` | unit-only | N/A (no UI — go-test-covered client method; opt-in profile) |
| `StartSearch` — POST `/api/v2/search/start` (`client/search.go:27`) | implemented | opt-in | go `client/coverage_test.go` | unit-only | N/A (no UI — go-test-covered client method; opt-in profile) |
| `GetSearchResults` — GET `/api/v2/search/results` (`client/search.go:55`) | implemented | opt-in | go `client/coverage_test.go` | unit-only | N/A (no UI — go-test-covered client method; opt-in profile) |
| `StopSearch` — POST `/api/v2/search/stop` (`client/search.go:84`) | implemented | opt-in | go `client/coverage_test.go` | unit-only | N/A (no UI — go-test-covered client method; opt-in profile) |
| `SearchStatus` — GET `/api/v2/search/status` (`client/search.go:100`) | implemented | opt-in | go `client/coverage_test.go` | unit-only | N/A (no UI — go-test-covered client method; opt-in profile) |
| `ListPlugins` — GET `/api/v2/search/plugins` (`client/search.go:121`) | implemented | opt-in | go `client/coverage_test.go` | unit-only | N/A (no UI — go-test-covered client method; opt-in profile) |

### 2c. Services (`internal/service/*.go`)

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| Merge search orchestrator `RunSearch` poll/dedup loop (`service/merge_search.go:183`) | implemented (qBit search only; no python-style plugin fan-out) | opt-in | go `service/service_test.go`, `runsearch_dedup_test.go` | unit-only | N/A (no UI — go-test-covered service; opt-in profile) |
| `StartSearch` / `GetSearchStatus` / `AbortSearch` lifecycle (`service/merge_search.go:101-143`) | implemented | opt-in | go `getsearchstatus_hardening_test.go` | unit-only | N/A (no UI — go-test-covered service; opt-in profile) |
| Dedup key (FileURL→name+size) (`service/merge_search.go:269`) | implemented | opt-in | go `runsearch_dedup_test.go` | unit-only | N/A (no UI — go-test-covered service; opt-in profile) |
| `FetchTorrent` tracker fetch (`service/merge_search.go:276`) | **stub — returns "not yet implemented"** | opt-in | none | not-implemented | N/A (no UI — stub; opt-in profile; not implemented) |
| `Stats` counters (`service/merge_search.go:280`) | implemented | opt-in | go `coverage_test.go` | unit-only | N/A (no UI — go-test-covered service; opt-in profile) |
| SSE broker pub/sub (`service/sse_broker.go`) | implemented (defined but not wired — handlers SSE inline) | opt-in | none dedicated | not-validated | N/A (no UI — internal broker; opt-in profile; not wired) |
| Metadata enricher (Go) | **missing (RW-11)** | no | none | not-implemented | N/A (not implemented — RW-11) |
| Scheduler driver loop (Go) | **missing (RW-10)** — CRUD only, no cron execution | no | none | not-implemented | N/A (not implemented — RW-10) |

### 2d. webui-bridge binary (Go) + cross-cutting

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| webui-bridge binary (`cmd/webui-bridge/main.go`) | partial (health + root only) | opt-in | none dedicated | not-validated | N/A (no UI of its own — proxy binary; opt-in profile) |
| CORS + logging middleware (`internal/middleware/`) | implemented | opt-in | go `middleware/middleware_test.go` | unit-only | N/A (no UI — go-test-covered middleware; opt-in profile) |
| Models / data types (`internal/models/`) | implemented | opt-in | go `models/models_test.go` | unit-only | N/A (no UI — go-test-covered data types; opt-in profile) |
| Env config loader (`internal/config/`) | implemented | opt-in | go `config/config_test.go` | unit-only | N/A (no UI — go-test-covered config loader; opt-in profile) |
| Log redactor (`internal/logging/redactor.go`) | implemented | opt-in | go `logging/redactor_test.go` | unit-only | N/A (no UI — go-test-covered redactor; opt-in profile) |

---

## 3. boba-jackett (Go) — `:7189`

Entry: `qBitTorrent-go/cmd/boba-jackett/main.go`; router `internal/jackettapi/router.go`. Owns Jackett credentials + indexer overrides + autoconfig run history; encrypted SQLite at `/config/boba.db`.

### 3a. HTTP endpoints (`internal/jackettapi/router.go` + handlers)

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| `GET /healthz` (`router.go:60`, `health.go`) | implemented | yes | go `jackettapi/health_test.go` | unit (go) | N/A (no UI — go-test-covered endpoint) |
| `GET /openapi.json` (`router.go:64`, `openapi.go`) | implemented | yes | go `jackettapi/openapi_test.go`; contract `tests/contract/openapi_test.go` | unit + contract (go) | N/A (no UI — go-test + contract-covered endpoint) |
| `GET /api/v1/jackett/credentials` — list (`router.go:67`, `credentials.go`) | implemented | yes | go `credentials_test.go`; integration `tests/integration/jackett_db_test.go` | unit + integration (go) | N/A (no UI — test-covered + exercised by web /jackett credentials page) |
| `POST /api/v1/jackett/credentials` — create/update (`router.go:67`, `credentials.go`) | implemented | yes | go `credentials_test.go` | unit + integration (go) | N/A (no UI — test-covered + exercised by web /jackett credentials page) |
| `DELETE /api/v1/jackett/credentials/{name}` (`router.go:77`, `credentials.go`) | implemented | yes | go `credentials_test.go` | unit + integration (go) | N/A (no UI — test-covered + exercised by web /jackett credentials page) |
| `GET /api/v1/jackett/indexers` — list configured (`router.go:86`, `indexers.go`) | implemented | yes | go `jackettapi/indexers_test.go` | unit (go) | N/A (no UI — test-covered + exercised by web /jackett indexers page) |
| `POST/PATCH/DELETE /api/v1/jackett/indexers/{id}` (`router.go:93`, `indexers.go`) | implemented | yes | go `indexers_test.go` | unit (go) | N/A (no UI — test-covered + exercised by web /jackett indexers page) |
| `POST /api/v1/jackett/indexers/{id}/test` — test config (`indexers.go:239`) | implemented | yes | go `indexers_test.go` | unit (go) | N/A (no UI — test-covered + exercised by web /jackett indexers page) |
| `GET /api/v1/jackett/catalog` — indexer catalog (`router.go:112`, `catalog.go`) | implemented | yes | go `jackettapi/catalog_test.go`; benchmark `catalog_bench_test.go` | unit + bench (go) | N/A (no UI — test-covered + exercised by web /jackett catalog tab) |
| `POST /api/v1/jackett/catalog/refresh` (`router.go:119`, `catalog.go`) | implemented | yes | go `catalog_test.go` | unit (go) | N/A (no UI — test-covered + exercised by web /jackett catalog tab) |
| `GET /api/v1/jackett/autoconfig/runs` — run history (`router.go:137`, `runs.go`) | implemented | yes | go `jackettapi/runs_test.go`; e2e `tests/e2e/jackett_management_test.go` | unit + e2e (go) | N/A (no UI — test-covered + exercised by web /jackett History tab) |
| `GET /api/v1/jackett/autoconfig/runs/{id}` — run detail (`router.go:144`, `runs.go`) | implemented | yes | go `runs_test.go` | unit (go) | N/A (no UI — test-covered + exercised by web /jackett History tab) |
| `POST /api/v1/jackett/autoconfig/run` — trigger run (`router.go:151`, `runs.go`) | implemented | yes | go `runs_test.go`; e2e `tests/e2e/jackett_management_test.go` | unit + e2e (go) | N/A (no UI — test-covered + exercised by web /jackett History tab) |
| `GET/POST /api/v1/jackett/overrides` (`router.go:160`, `overrides.go`) | implemented | yes | go `jackettapi/overrides_test.go` | unit (go) | N/A (no UI — go-test-covered endpoint) |
| `DELETE /api/v1/jackett/overrides/{env}` (`router.go:170`, `overrides.go`) | implemented | yes | go `overrides_test.go` | unit (go) | N/A (no UI — go-test-covered endpoint) |
| Admin auth middleware (admin/admin on mutating routes) (`jackettapi/auth_middleware.go`) | implemented | yes | go `auth_middleware_test.go` | unit (go) | N/A (no UI — go-test-covered middleware) |
| Hardened CORS middleware (`jackettapi/cors_middleware.go`) | implemented | yes | go `cors_middleware_test.go` | unit (go) | N/A (no UI — go-test-covered middleware) |

### 3b. Autoconfig engine + persistence (`internal/jackett/`, `internal/db/`)

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| Jackett autoconfig engine (`jackett/autoconfig.go`) | implemented | yes | go `jackett/autoconfig_test.go`, `autoconfig_bench_test.go` | unit + bench (go) | N/A (no UI — go-test-covered engine; exercised by web /jackett autoconfig run) |
| Fuzzy indexer matcher (`jackett/matcher.go`) | implemented | yes | go `jackett/matcher_test.go` | unit (go) | N/A (no UI — go-test-covered matcher) |
| Jackett HTTP client (`jackett/client.go`) | implemented | yes | go `jackett/client_test.go` | unit (go) | N/A (no UI — go-test-covered client) |
| Encrypted SQLite — AES-256-GCM crypto (`db/crypto.go`) | implemented | yes | go `db/crypto_test.go`; security `tests/security/credential_leak_test.go` | unit + security (go) | N/A (no UI — go-test + security-covered crypto) |
| SQLite migrations (`db/migrate.go`) | implemented | yes | go `db/migrate_test.go` | unit (go) | N/A (no UI — go-test-covered migrations) |
| Credential / indexer / runs repos (`db/repos/*.go`) | implemented | yes | go `db/repos/*_test.go` | unit (go) | N/A (no UI — go-test-covered repos) |
| `.env` bootstrap import (`bootstrap/*.go`) | implemented | yes | go `bootstrap/bootstrap_test.go` | unit (go) | N/A (no UI — go-test-covered bootstrap) |
| Master-key ensure (first-boot) (`bootstrap/*.go`) | implemented | yes | go `bootstrap/bootstrap_test.go` | unit (go) | N/A (no UI — go-test-covered first-boot key ensure) |
| `.env` file parse/write (`envfile/*.go`) | implemented | yes | go `envfile/parse_test.go`, `write_test.go` | unit (go) | N/A (no UI — go-test-covered env file I/O) |

---

## 4. Tracker plugins (`plugins/*.py`)

Plugin contract: class with `url`, `name`, `supported_categories`, `search()`, `download_torrent()`. Installed into container by `install-plugin.sh`. The `install-plugin.sh` `PLUGINS` array names **44 plugins** (curated install set); the `plugins/` tree carries **27 `*.py` files** (24 tracker/aggregator plugins + 3 support: `nova2`, `novaprinter`, `socks`, `helpers`, `env_loader`, `theme_injector`, `download_proxy`). Many curated names have NO matching file in this repo tree (the install script fetches/expects them elsewhere) — flagged honestly below.

### 4a. Plugins present in `plugins/` AND named in the curated array

| Plugin | Type | Impl | Wired (curated?) | Tests | Validation | Video |
|--------|------|------|------------------|-------|------------|-------|
| `eztv.py` | public | implemented | yes (curated) | stress `test_plugin_parsers_stress_chaos.py` | tested-green-in-suite | N/A (no UI — test-covered + exercised by web search flow) (tracker backend) |
| `limetorrents.py` | public | implemented | yes (curated) | stress `test_plugin_parsers_stress_chaos.py`; multi-word `tests/unit/test_plugin_multiword_query_encoding.py` + stress/chaos `tests/stress_chaos/test_multiword_query_encoding_{stress,chaos}.py` (§11.4.85) | **PASS — LIVE 2026-06-16** — multi-word URL-encoding fix (`da7d709`) verified on nezha: `the matrix` returns results, zero `plugin_bad_query_encoding` (`docs/qa/search-fix-verify-20260616/`) | N/A (no UI — test-covered + exercised by web search flow) (tracker backend) |
| `piratebay.py` | public | implemented | yes (curated) | stress `test_plugin_parsers_stress_chaos.py` | tested-green-in-suite | N/A (no UI — test-covered + exercised by web search flow) (tracker backend) |
| `solidtorrents.py` | public | implemented | yes (curated) | stress `test_plugin_parsers_stress_chaos.py` | tested-green-in-suite | N/A (no UI — test-covered + exercised by web search flow) (tracker backend) |
| `torlock.py` | public | implemented | yes (curated) | stress `test_plugin_parsers_stress_chaos.py` | tested-green-in-suite | N/A (no UI — test-covered + exercised by web search flow) (tracker backend) |
| `rutor.py` | public (anonymous) | implemented | yes (curated) | stress `test_plugin_parsers_stress_chaos.py` | tested-green-in-suite | N/A (no UI — test-covered + exercised by web search flow) (tracker backend) |
| `nyaa.py` | public | implemented | yes (curated) | stress `test_plugin_parsers_stress_chaos.py` | tested-green-in-suite | N/A (no UI — test-covered + exercised by web search flow) (tracker backend) |
| `anilibra.py` | public | implemented | yes (curated) | stress `test_plugin_parsers_stress_chaos.py` | tested-green-in-suite | N/A (no UI — test-covered + exercised by web search flow) (tracker backend) |
| `bitsearch.py` | public | implemented | yes (curated) | stress `test_plugin_parsers_stress_chaos.py` | tested-green-in-suite | N/A (no UI — test-covered + exercised by web search flow) (tracker backend) |
| `gamestorrents.py` | public | implemented | yes (curated) | stress `test_plugin_parsers_stress_chaos.py` | tested-green-in-suite | N/A (no UI — test-covered + exercised by web search flow) (tracker backend) |
| `kickass.py` | public | implemented (degrades to honest empty) | yes (curated) | stress `test_plugin_parsers_stress_chaos.py` | **Won't-fix — structurally-impossible (§11.4.112)** — every live KAT mirror is Cloudflare-403 or a JS bot-challenge a non-JS `urllib` client cannot clear; deep multi-angle research (§11.4.150) + live probes 2026-06-16 in `docs/research/kickass_403_20260616/`; upstream maintainer confirms. Reopen only on NEW evidence a mirror serves listing HTML to a non-JS client (§11.4.34/§11.4.7) | N/A (no UI — test-covered; structurally blocked upstream) (tracker backend) |
| `megapeer.py` | public | implemented | yes (curated) | stress `test_plugin_parsers_stress_chaos.py` | tested-green-in-suite | N/A (no UI — test-covered + exercised by web search flow) (tracker backend) |
| `tokyotoshokan.py` | public | implemented | yes (curated) | stress `test_plugin_parsers_stress_chaos.py` | tested-green-in-suite | N/A (no UI — test-covered + exercised by web search flow) (tracker backend) |
| `torrentgalaxy.py` | public | implemented | yes (curated) | stress `test_plugin_parsers_stress_chaos.py` | tested-green-in-suite | N/A (no UI — test-covered + exercised by web search flow) (tracker backend) |
| `torrentkitty.py` | public | implemented | yes (curated) | stress `test_plugin_parsers_stress_chaos.py` | tested-green-in-suite | N/A (no UI — test-covered + exercised by web search flow) (tracker backend) |
| `yts.py` | public | implemented | yes (curated) | stress `test_plugin_parsers_stress_chaos.py` | tested-green-in-suite | N/A (no UI — test-covered + exercised by web search flow) (tracker backend) |
| `jackett.py` | aggregator | implemented | yes (curated) | covered via jackett autoconfig tests | tested-green-in-suite | N/A (no UI — test-covered + exercised by web search flow) (tracker backend) |
| `iptorrents.py` | private (freeleech-only) | implemented | yes (curated) | integration `tests/integration/test_iptorrents.py` | **PASS — LIVE 2026-06-16** — full-fleet `the matrix` on nezha: **49** results, `success` (`docs/qa/search-fix-verify-20260616/` §6); freeleech-only policy enforced | N/A (no UI — test-covered + exercised by web search flow) (tracker backend) |
| `rutracker.py` | private (cookies / CAPTCHA) | implemented | yes (curated) | integration `test_tracker_auth_live.py`; cookie-injection `tests/unit/` rutracker-cookie test (§1.1); stress `test_plugin_parsers_stress_chaos.py` (ReDoS §11.4.85) | **PASS — LIVE 2026-06-16** — new `RUTRACKER_COOKIES` injection (`2fc29fc`) bypasses the CAPTCHA-walled login; `the matrix` returns **50** results incl. "Матрица / The Matrix" (`docs/qa/search-fix-verify-20260616/` §1,§6). ReDoS fix in source not yet deployed (RW-06); CAPTCHA password-login still operator-blocked (BOB-008) | N/A (no UI — test-covered + exercised by web search flow) (tracker backend) |
| `kinozal.py` | private | implemented | yes (curated) | integration `test_tracker_auth_live.py` | **PASS — LIVE 2026-06-16** — full-fleet `the matrix` on nezha: **50** results, `success` (`docs/qa/search-fix-verify-20260616/` §6) | N/A (no UI — test-covered + exercised by web search flow) (tracker backend) |
| `nnmclub.py` | private (cookies) | implemented | yes (curated) | integration `test_tracker_auth_live.py` | **PASS — LIVE 2026-06-16** — `NNMCLUB_COOKIES` auth (Cloudflare Turnstile bypass): `the matrix` returns **50** results incl. "Matrix Resurrections (2021)" (`docs/qa/search-fix-verify-20260616/` §1,§6) | N/A (no UI — test-covered + exercised by web search flow) (tracker backend) |

### 4b. Plugin support modules

| Module | Type | Impl | Wired | Tests | Validation | Video |
|--------|------|------|-------|-------|------------|-------|
| `nova2.py` — nova3 search harness | support | implemented | yes | covered via search e2e | tested-green-in-suite | N/A (no UI — test-covered, search harness; exercised by web search flow) |
| `novaprinter.py` — result emitter (NDJSON-patched) | support | implemented | yes | covered via search e2e | tested-green-in-suite | N/A (no UI — test-covered, result emitter; exercised by web search flow) |
| `helpers.py` — HTTP/retrieve helpers | support | implemented | yes | covered via search e2e | tested-green-in-suite | N/A (no UI — test-covered helper; exercised by web search flow) |
| `socks.py` — SOCKS proxy support | support | implemented | yes | covered indirectly | not-validated | N/A (no UI — internal SOCKS support; covered indirectly) |
| `env_loader.py` — env/credential loader for plugins | support | implemented | yes | covered via tracker auth tests | tested-green-in-suite | N/A (no UI — test-covered credential loader; exercised by web Trackers tab) |
| Per-plugin `download_torrent()` path (.torrent fetch) | feature | implemented | yes | integration `test_buttons_api.py` (download/file) | tested-green-in-suite | N/A (no UI — test-covered + exercised by web result-row Download button) |
| Freeleech-only download policy (IPTorrents `[free]` tag) | policy | implemented | yes | integration `test_iptorrents.py` | tested-green-in-suite | N/A (no UI — test-covered + exercised by web result-row Download (freeleech) policy) |

### 4c. Discrepancy rows (honest, §11.4.6)

| Plugin | Type | Impl | Wired (curated?) | Tests | Validation | Video |
|--------|------|------|------------------|-------|------------|-------|
| `torrentproject` / `torrentscsv` | public (curated names) | named in `install-plugin.sh` PLUGINS array but NO matching `plugins/*.py` file in tree | curated-name-only | none | not-implemented-in-repo-tree (install script expects them elsewhere) | N/A (not implemented in repo tree — curated name, no plugin file) |
| 23 other curated names absent from tree: `academictorrents, ali213, audiobookbay, bitru, bt4g, btsow, extratorrent, glotorrents, linuxtracker, one337x, pctorrent, pirateiro, rockbox, snowfl, therarbg, torrentdownload, torrentfunk, xfsub, yihua, yourbittorrent` (+ `torrentproject`, `torrentscsv`) | public (curated names) | named in curated array; NO `plugins/*.py` in this tree | curated-name-only | none | not-implemented-in-repo-tree (name in install array; file absent) | N/A (not implemented in repo tree — curated names, no plugin files) |

> NOTE (§11.4.6, CORRECTION vs Rev 2): the `install-plugin.sh` `PLUGINS` array contains **44 entries**, not 12. Of those, ~21 have a matching `plugins/*.py` file in this repo; the rest are curated names with no file present in the tree. Stated as fact, not asserted as working.

---

## 5. Angular 21 frontend dashboard (`frontend/`)

Standalone SPA, signals-based; built to `download-proxy/src/ui/dist/frontend`, served from :7187. Vitest unit tests; Playwright e2e under `frontend/e2e`.

### 5a. Dashboard component controls (`components/dashboard/dashboard.component.ts`)

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| Search box (`query` signal) + submit | implemented | yes | vitest `dashboard.component.spec.ts`; py integration `test_dashboard_rendering.py`, `test_ui_comprehensive.py` | tested-green-in-suite | **VIDEO-CONFIRMED 2026-06-16** — `boba-web-search-flow.mp4` + `boba-web-feature-tour.mp4` — search box drives the confirmed search flow |
| Result grid — sortable (name/type/size/seeds/leechers/quality/sources) | implemented | yes | vitest `dashboard.component.spec.ts` | unit (vitest) | **VIDEO-CONFIRMED 2026-06-16** — result grid rows render, `boba-web-feature-tour.mp4` |
| Results tab | implemented | yes | py `test_ui_comprehensive.py` | tested-green-in-suite | **VIDEO-CONFIRMED 2026-06-16** — `boba-web-feature-tour.mp4` (tab nav) |
| Active Downloads tab + view (`dashboard.component.ts:745 loadDownloads`) | implemented | yes | py `test_buttons_api.py` | tested-green-in-suite | **VIDEO-CONFIRMED 2026-06-16** — `boba-web-feature-tour.mp4` |
| Trackers tab + per-tracker auth chips (expandable) | implemented | yes | py `test_auth_state_ui.py` | tested-green-in-suite | **VIDEO-CONFIRMED 2026-06-16** — `boba-web-feature-tour.mp4` (29 trackers) |
| Schedules tab | implemented | yes | py `test_dashboard_automation.py` | tested-green-in-suite | **VIDEO-CONFIRMED 2026-06-16** — `boba-web-feature-tour.mp4` |
| Hooks tab | implemented | yes | py `test_dashboard_automation.py` | tested-green-in-suite | **VIDEO-CONFIRMED 2026-06-16** — `boba-web-feature-tour.mp4` |
| Per-row Magnet button → magnet dialog trigger | implemented | yes | vitest `magnet-dialog.component.spec.ts`; py `test_magnet_dialog.py` | tested-green-in-suite | PENDING (UI — film next) |
| Per-row add-to-qBittorrent (qBit) button | implemented | yes | py `test_button_functions.py`, `test_buttons_api.py` | tested-green-in-suite | **VIDEO-CONFIRMED 2026-06-16** — buttons render & clickable, `boba-web-feature-tour.mp4` |
| Per-row Download (.torrent) button | implemented | yes | py `test_buttons_api.py` | tested-green-in-suite | **VIDEO-CONFIRMED 2026-06-16** — `boba-web-feature-tour.mp4` |
| Per-row processing spinner (`isBusy()`) | implemented | yes | vitest `dashboard.component.spec.ts` | unit (vitest) | **VIDEO-CONFIRMED 2026-06-16** — processing spinner ("Found N results…") shown, `boba-web-tabs-theme-tour.mp4` |
| Bridge health indicator + retry button | implemented | yes | py `test_bridge_root_liveness.py` | tested-green-in-suite | **VIDEO-CONFIRMED 2026-06-16** — bridge/qBit-Connected header indicator shown, `boba-web-tabs-theme-tour.mp4` |
| Tracker-stat dialog trigger | implemented | yes | py contract `test_tracker_stats_contract.py` | tested-green-in-suite | PENDING (UI — film next) |

### 5b. Dialog + UI components

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| Magnet dialog — readonly textarea + Copy/Open/Add/Close (`magnet-dialog.component.ts`) | implemented | yes | vitest `magnet-dialog.component.spec.ts`; py `test_magnet_dialog.py` | tested-green-in-suite | PENDING (UI — film next) |
| qBit login dialog — user/pass/remember/Login/Cancel (`qbit-login-dialog.component.ts`) | implemented | yes | vitest `qbit-login-dialog.component.spec.ts`; py `test_login_actions.py`, `test_auth_state_ui.py` | tested-green-in-suite | PENDING (UI — film next) |
| Theme picker — palette dropdown + light/dark toggle (`theme-picker.component.ts`) | implemented | yes | vitest `theme-picker.component.spec.ts`; py e2e `test_theme_runtime.py`, `test_crossapp_theme.py` | tested-green-in-suite | **VIDEO-CONFIRMED 2026-06-16** — theme present, `boba-web-feature-tour.mp4` |
| Confirm dialog — title/message/Confirm/Cancel/backdrop (`confirm-dialog.component.ts`) | implemented | yes | vitest `confirm-dialog.component.spec.ts` | unit (vitest) | PENDING (UI — film next) |
| Tracker-stat dialog — JSON view + Copy + status badge + notes table + Esc-close (`tracker-stat-dialog.component.ts`) | implemented | yes | vitest `tracker-stat-dialog.component.spec.ts`; py contract `test_tracker_stats_contract.py` | tested-green-in-suite | PENDING (UI — film next) |
| Toast container — info/success/warning/error auto-dismiss (`toast-container.component.ts`) | implemented | yes | vitest `toast-container.component.spec.ts` | unit (vitest) | PENDING (UI — film next) |
| Site footer (`site-footer.component.ts`) | implemented | yes | vitest | unit (vitest) | PENDING (UI — film next) |

### 5c. Services (`frontend/src/app/services/`)

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| API service — HTTP wrapper (search/download/magnet/auth/schedules/hooks/downloads/stats/config), 15s timeout, runtime baseUrl (`api.service.ts`) | implemented | yes | vitest `api.service.spec.ts` | unit (vitest) | N/A (no UI — TS service; exercised by every web dashboard call) |
| SSE service — EventSource live result streaming + bearer-token (`sse.service.ts`) | implemented | yes | vitest `sse.service.spec.ts`; py integration `test_realtime_streaming.py`, `test_streaming_browser.py` | tested-green-in-suite | N/A (no UI — TS service; exercised by web search flow live-results stream) |
| Theme service — palette/mode + localStorage + cross-app sync (`theme.service.ts`) | implemented | yes | vitest `theme.service.spec.ts`; py e2e `test_theme_runtime.py`, `test_crossapp_theme.py` | tested-green-in-suite | N/A (no UI — TS service; exercised by web theme picker) |
| Toast service — toast queue state (`toast.service.ts`) | implemented | yes | vitest `toast.service.spec.ts` | unit (vitest) | N/A (no UI — TS service; exercised by web toast notifications) |
| Dialog service — promise-based confirm state (`dialog.service.ts`) | implemented | yes | vitest `dialog.service.spec.ts` | unit (vitest) | N/A (no UI — TS service; exercised by web confirm dialogs) |

### 5d. Jackett page (`frontend/src/app/jackett/`)

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| Credentials — list + Add/Edit/Delete (per-row, window.confirm) + banners (`jackett/credentials/credentials.component.ts`) | implemented | yes | vitest `credentials.component.spec.ts` | unit (vitest) | **VIDEO-CONFIRMED 2026-06-16** — `/jackett` credentials page, `boba-web-feature-tour.mp4` |
| Credential edit dialog — name/username/password/cookies/Save/Cancel (`credential-edit-dialog.component.ts`) | implemented | yes | vitest `credential-edit-dialog.component.spec.ts` | unit (vitest) | **VIDEO-CONFIRMED 2026-06-16** — Jackett Add-credential dialog (Name/Username/Password/Cookies + Cancel/Save) shown, `boba-web-jackett-add-credential.png` |
| Indexers — Configured/Catalog/History tab container (`jackett/indexers/indexers.component.ts`) | implemented | yes | vitest `indexers.component.spec.ts` | unit (vitest) | PENDING (UI — film next) |
| Indexers — Configured tab (list + per-row remove) | implemented | yes | vitest `indexers.component.spec.ts` | unit (vitest) | PENDING (UI — film next) |
| Indexers — Catalog tab (list + per-row add) | implemented | yes | vitest `indexers.component.spec.ts` | unit (vitest) | PENDING (UI — film next) |
| Indexers — History tab (autoconfig run history) | implemented | yes | vitest `indexers.component.spec.ts` | unit (vitest) | PENDING (UI — film next) |
| Indexer add dialog — credential dropdown + Save/Cancel + error banner (`indexer-add-dialog.component.ts`) | implemented | yes | vitest `indexer-add-dialog.component.spec.ts` | unit (vitest) | PENDING (UI — film next) |
| IPTorrents cookie-flow component (`iptorrents-cookie-flow.component.ts`) | implemented | yes | vitest (jackett specs) | unit (vitest) | PENDING (UI — film next) |

### 5e. Frontend infra

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| Frontend coverage thresholds (40% lines/branches/funcs/stmts, v8) | infra | yes | `vitest.config.ts` | enforced in vitest config | N/A (no UI — build/coverage infra) |

---

## 6. BobaLink browser extension (`extension/`)

WXT + TypeScript Manifest-V3. Detects magnet/.torrent links and forwards to merge service :7187. Status detail: `docs/browser_extension/Status.md`. Built zips at `extension/.output/bobalink-1.0.0-{chrome,firefox}.zip`.

### 6a. User-facing surfaces

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| Popup — per-row Send button (`src/popup/`, `entrypoints/popup.ts`) | implemented | yes | a11y `tests/a11y/popup.a11y.test.ts` | tested-green-in-suite | **VIDEO-CONFIRMED 2026-06-16** — `boba-extension-popup.mp4`; verdict `docs/qa/recordings-20260615/boba-extension-verdict.md` |
| Popup — Send-All button | implemented | yes | a11y `popup.a11y.test.ts` | tested-green-in-suite | **VIDEO-CONFIRMED 2026-06-16** — `boba-extension-popup.mp4`; verdict `docs/qa/recordings-20260615/boba-extension-verdict.md` |
| Popup — Refresh button + status indicator (online/offline/warning) | implemented | yes | a11y `popup.a11y.test.ts` | tested-green-in-suite | **VIDEO-CONFIRMED 2026-06-16** — `boba-extension-popup.mp4`; verdict `docs/qa/recordings-20260615/boba-extension-verdict.md` |
| Popup — torrent list (name + type + infohash prefix + sent badge) | implemented | yes | a11y `popup.a11y.test.ts` | tested-green-in-suite | **VIDEO-CONFIRMED 2026-06-16** — `boba-extension-popup.mp4`; verdict `docs/qa/recordings-20260615/boba-extension-verdict.md` |
| Popup — Open Options link | implemented | yes | a11y `popup.a11y.test.ts` | tested-green-in-suite | **VIDEO-CONFIRMED 2026-06-16** — `boba-extension-popup.mp4`; verdict `docs/qa/recordings-20260615/boba-extension-verdict.md` |
| Options page (`src/options/options.ts`) | implemented | yes | a11y `options.a11y.test.ts`; integration `options-background.test.ts` | tested-green-in-suite | **VIDEO-CONFIRMED 2026-06-16** — `boba-extension-options.mp4`; verdict `docs/qa/recordings-20260615/boba-extension-verdict.md` |
| Content script — link/text highlight overlay (`src/content/highlight.ts`, `entrypoints/content.ts`) | implemented | yes | integration `content-background.test.ts`; security `content-xss.test.ts` | tested-green-in-suite | **VIDEO-CONFIRMED 2026-06-16** — `boba-extension-scan-detect.mp4`; verdict `docs/qa/recordings-20260615/boba-extension-verdict.md` |
| Background service worker — message hub (`src/background/`, `entrypoints/background.ts`) | implemented | yes | integration `tests/integration/*-background.test.ts` | tested-green-in-suite | N/A (no UI — test-covered + exercised by extension scan/popup) |
| Context-menu entries (right-click torrent actions) | implemented | yes | integration `*-background.test.ts` | tested-green-in-suite | N/A (no UI — test-covered + exercised by extension scan/popup) |
| Keyboard shortcuts (scan-now / highlight-toggle / send-all) | implemented | yes | integration `*-background.test.ts` | tested-green-in-suite | N/A (no UI — test-covered + exercised by extension scan/popup) |
| Action badge (detected count) + notifications | implemented | yes | integration `*-background.test.ts` | tested-green-in-suite | N/A (no UI — test-covered + exercised by extension scan/popup) |

### 6b. Scanners (`src/scanner/`)

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| Base scanner — `computeStableId()` lifecycle (`scanner/base.ts`) | implemented | yes | vitest unit | tested-green-in-suite | N/A (no UI — test-covered scanner; exercised by extension scan-detect) |
| Link scanner — `<a href>` magnet/.torrent (`scanner/link-scanner.ts`) | implemented | yes | security `scanner-hostile-input.test.ts`; perf `scanner.perf.test.ts` | tested-green-in-suite | N/A (no UI — test-covered scanner; exercised by extension scan-detect) |
| Text scanner — bare magnet text (`scanner/text-scanner.ts`) | implemented | yes | security `scanner-hostile-input.test.ts` | tested-green-in-suite | N/A (no UI — test-covered scanner; exercised by extension scan-detect) |
| Scanner orchestrator — dedup + mutation-observer re-scan (`scanner/orchestrator.ts`) | implemented | yes | perf `orchestrator-scaling.perf.test.ts` | tested-green-in-suite | N/A (no UI — test-covered scanner; exercised by extension scan-detect) |
| Site DB — per-site selector match rules (`scanner/site-db.ts`) | implemented | yes | vitest unit | tested-green-in-suite | N/A (no UI — test-covered scanner; exercised by extension scan-detect) |

### 6c. Parsers (`src/parser/`)

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| Bencode parser (`parser/bencode.ts`) | implemented | yes | security `bencode-torrentfile-hostile.test.ts`; perf `parsers.perf.test.ts` | tested-green-in-suite | N/A (no UI — test-covered parser; exercised by extension scan-detect) |
| Magnet parser (`parser/magnet.ts`) | implemented | yes | security `infohash-detection-hostile.test.ts`; perf `magnet.perf.test.ts` | tested-green-in-suite | N/A (no UI — test-covered parser; exercised by extension scan-detect) |
| Torrent-file parser (`parser/torrent-file.ts`) | implemented | yes | security `bencode-torrentfile-hostile.test.ts` | tested-green-in-suite | N/A (no UI — test-covered parser; exercised by extension scan-detect) |

### 6d. API client + offline (`src/api/`)

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| Boba API client — POST `/api/v1/download`, retry + rate-limit (`api/boba-client.ts`) | implemented | yes | vitest unit; chaos `tests/chaos/boba-client-resilience.chaos.test.ts` | tested-green-in-suite | N/A (no UI — test-covered API client; exercised by extension Send) |
| Health probe — `probeHealth()` (`api/health.ts`) | implemented | yes | vitest unit | tested-green-in-suite | N/A (no UI — test-covered health probe; exercised by extension status indicator) |
| Offline send queue — IndexedDB enqueue + re-dispatch (`api/queue.ts`) | implemented | yes | chaos `tests/chaos/queue.chaos.test.ts` | tested-green-in-suite | N/A (no UI — test-covered offline queue; chaos-covered) |

### 6e. Shared utilities + tabgroups (`src/shared/`, `src/tabgroups/`)

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| Crypto — AES-256-GCM token encrypt/decrypt (`shared/crypto.ts`) | implemented | yes | security `crypto-tamper.test.ts`, `no-hardcoded-secret.test.ts` | tested-green-in-suite | N/A (no UI — test-covered crypto; exercised by extension Send token path) |
| Storage — namespaced `chrome.storage.local` wrapper (`shared/storage.ts`) | implemented | yes | vitest unit | tested-green-in-suite | N/A (no UI — test-covered storage wrapper) |
| Constants — site selectors / rate-limit / retry config (`shared/constants.ts`) | implemented | yes | covered via scanner tests | tested-green-in-suite | N/A (no UI — test-covered constants) |
| Errors — Network/Server/Storage error types (`shared/errors.ts`) | implemented | yes | vitest unit | tested-green-in-suite | N/A (no UI — test-covered error types) |
| Events — TypedEventEmitter bus (`shared/events.ts`) | implemented | yes | vitest unit | tested-green-in-suite | N/A (no UI — test-covered event bus) |
| Logger — namespaced, no-secret (`shared/logger.ts`) | implemented | yes | vitest unit | tested-green-in-suite | N/A (no UI — test-covered logger) |
| Utils — debounce / TokenBucket rate limiter (`shared/utils.ts`) | implemented | yes | vitest unit | tested-green-in-suite | N/A (no UI — test-covered utils/rate-limiter) |
| Tab groups — batch grouped-tab torrents (`tabgroups/index.ts`) | implemented | yes | vitest unit (tab-group Challenge per ext Status) | tested-green-in-suite | N/A (no UI of its own — test-covered tab-group batching; exercised by extension Send-All) |

### 6f. i18n locales (`extension/src/public/_locales/`)

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| Locale `en` (English) | implemented | yes | i18n `tests/i18n/locale-safety.test.ts` | tested-green-in-suite | N/A (no UI of its own — i18n locale data; test-covered; surfaced inside extension popup/options) |
| Locale `de` (German) | implemented | yes | i18n `locale-safety.test.ts` | tested-green-in-suite | N/A (no UI of its own — i18n locale data; test-covered; surfaced inside extension popup/options) |
| Locale `es` (Spanish) | implemented | yes | i18n `locale-safety.test.ts` | tested-green-in-suite | N/A (no UI of its own — i18n locale data; test-covered; surfaced inside extension popup/options) |
| Locale `fr` (French) | implemented | yes | i18n `locale-safety.test.ts` | tested-green-in-suite | N/A (no UI of its own — i18n locale data; test-covered; surfaced inside extension popup/options) |
| Locale `it` (Italian) | implemented | yes | i18n `locale-safety.test.ts` | tested-green-in-suite | N/A (no UI of its own — i18n locale data; test-covered; surfaced inside extension popup/options) |
| Locale `ja` (Japanese) | implemented | yes | i18n `locale-safety.test.ts` | tested-green-in-suite | N/A (no UI of its own — i18n locale data; test-covered; surfaced inside extension popup/options) |
| Locale `pt` (Portuguese) | implemented | yes | i18n `locale-safety.test.ts` | tested-green-in-suite | N/A (no UI of its own — i18n locale data; test-covered; surfaced inside extension popup/options) |
| Locale `ru` (Russian) | implemented | yes | i18n `locale-safety.test.ts` | tested-green-in-suite | N/A (no UI of its own — i18n locale data; test-covered; surfaced inside extension popup/options) |

### 6g. Live round-trip

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| Live download endpoint round-trip (`tests/live/download-endpoint.live.test.ts`) | implemented | yes (live-gated) | live `download-endpoint.live.test.ts` | partial — operator-gated live env | N/A (no UI — live round-trip test; operator-gated live env) |

---

## 7. WebUI bridge (`webui-bridge.py`) — host process `:7188`

Bridges qBittorrent WebUI with private-tracker auth. NOT a container.

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| WebUI proxy + header rewrite (`webui-bridge.py`) | implemented | host | integration `test_webui_bridge.py`, `test_bridge_header_rewrite.py`; stress `test_bridge_stress_chaos.py` | tested-green-in-suite | N/A (no UI of its own — host proxy; test-covered) |
| Private-tracker auth bridging (rutracker/kinozal/nnmclub/iptorrents) | implemented | host | integration `test_webui_bridge.py` | partial — live-gated | N/A (no UI of its own — host proxy auth bridging; test-covered, live-gated) |
| Theme injection into bridged WebUI (`plugins/theme_injector.py`) | implemented | host | integration `test_bridge_theme_injection.py` | tested-green-in-suite | N/A (no UI of its own — proxy theme injection; test-covered) |
| Bridge root liveness (`/`) | implemented | host | integration `test_bridge_root_liveness.py` | tested-green-in-suite | N/A (no UI of its own — proxy root liveness; test-covered) |

---

## 8. Infrastructure / CLI / shell scripts

### 8a. boba-ctl CLI orchestrator (Go: `cmd/boba-ctl/main.go` + wrapper `scripts/boba-ctl.sh`)

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| `boba-ctl up` — start stack (`cmd/boba-ctl/main.go:32`) | implemented | host | go `cmd/boba-ctl/projectroot_test.go` | tested-green-in-suite | N/A (CLI — go-test-covered; exercised by boba-ctl CLI demo, `boba-cli-orchestrator-demo.mp4`) |
| `boba-ctl down` — stop stack (`main.go:34`) | implemented | host | go `cmd/boba-ctl/projectroot_test.go` | tested-green-in-suite | N/A (CLI — go-test-covered; exercised by boba-ctl CLI demo, `boba-cli-orchestrator-demo.mp4`) |
| `boba-ctl status` — service status (`main.go:36`) | implemented | host | go `cmd/boba-ctl/projectroot_test.go` | tested-green-in-suite + LIVE | **VIDEO-CONFIRMED 2026-06-16** — `boba-cli-orchestrator-demo.mp4`; verdict `docs/qa/recordings-20260615/boba-cli-verdict.md` |
| `boba-ctl health` — health probe (`main.go:38`, `cmd/boba-ctl/health_test.go`) | implemented | host | go `cmd/boba-ctl/health_test.go` | tested-green-in-suite + LIVE | **VIDEO-CONFIRMED 2026-06-16** — `boba-cli-orchestrator-demo.mp4` |
| `boba-ctl list` — list services (`main.go:40`) | implemented | host | go `cmd/boba-ctl/projectroot_test.go` | tested-green-in-suite + LIVE | **VIDEO-CONFIRMED 2026-06-16** — `boba-cli-orchestrator-demo.mp4` |
| `boba-ctl.sh` wrapper — compose-compat shim (up/down/ps/config/pull + passthrough) (`scripts/boba-ctl.sh`) | implemented | host | covered via boba-ctl go tests | tested-green-in-suite | N/A (CLI shim — test-covered; exercised by boba-ctl CLI demo) |

### 8b. Lifecycle scripts (repo root)

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| `start.sh` — container bring-up + Jackett key extraction/injection | implemented | host | covered via e2e `test_fixtures_bring_up_services.py` | tested-green-in-suite | N/A (host script — no UI; test-covered/operational) |
| `stop.sh` — stop/remove/purge | implemented | host | none dedicated | not-validated | N/A (host script — no UI; test-covered/operational) |
| `setup.sh` — one-time setup | implemented | host | none dedicated | not-validated | N/A (host script — no UI; test-covered/operational) |
| `start-proxy.sh` — proxy container entry helper | implemented | host | none dedicated | not-validated | N/A (host script — no UI; test-covered/operational) |
| `install-plugin.sh` — copy curated plugins → container engines | implemented | host | covered indirectly (e2e search) | tested-green-in-suite | N/A (host script — no UI; test-covered/operational) |
| `init-qbit-password.sh` — qBit admin password bootstrap | implemented | host | none dedicated | not-validated | N/A (host script — no UI; test-covered/operational) |
| `fix-qbit-password.sh` — qBit admin password repair | implemented | host | none dedicated | not-validated | N/A (host script — no UI; test-covered/operational) |
| `setup-webui-bridge-service.sh` + `webui-bridge.service` — systemd unit for bridge | implemented | host | none dedicated | not-validated | N/A (host script — no UI; test-covered/operational) |

### 8c. Test / CI wrappers (repo root)

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| `ci.sh` — manual CI (syntax+unit+integration+e2e+health) | implemented | host | self (is the gate) | tested-green-in-suite | N/A (host CI/test wrapper — no UI; is the gate) |
| `run-all-tests.sh` — full suite (hardcoded podman) | implemented | host | self | partial — fails on docker-only hosts (known gotcha) | N/A (host CI/test wrapper — no UI; is the gate) |
| `test.sh` — quick validation wrapper | implemented | host | self | tested-green-in-suite | N/A (host CI/test wrapper — no UI; is the gate) |
| `test-all.sh` — full validation wrapper | implemented | host | self | tested-green-in-suite | N/A (host CI/test wrapper — no UI; is the gate) |
| `test-full.sh` — extended validation wrapper | implemented | host | self | tested-green-in-suite | N/A (host CI/test wrapper — no UI; is the gate) |

### 8d. scripts/ helpers

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| `scripts/add-submodules.sh` — submodule bootstrap | implemented | host | none dedicated | not-validated | N/A (host script — no UI; test-covered/operational) |
| `scripts/audit-plugins.sh` — plugin discrepancy audit | implemented | host | none dedicated | not-validated | N/A (host script — no UI; test-covered/operational) |
| `scripts/build-releases.sh` — build extension/Go release artifacts | implemented | host | none dedicated | not-validated | N/A (host script — no UI; test-covered/operational) |
| `scripts/codegraph_validate.sh` — CodeGraph index validation (§11.4.78) | implemented | host | self | tested-green-in-suite | N/A (host script — no UI; test-covered/operational) |
| `scripts/docs_chain.sh` — docs_chain engine wrapper (§11.4.106) | implemented | host | self | tested-green-in-suite | N/A (host script — no UI; test-covered/operational) |
| `scripts/ensure-macos-tunnel.sh` — `0.0.0.0` SSH tunnel | implemented | host | none dedicated (log `qa-results/tunnel-keepalive.log`) | not-validated; LAN threat-model RW-05 | N/A (host script — no UI; test-covered/operational) |
| `scripts/tunnel-keepalive.sh` — tunnel self-heal | implemented | host | none dedicated | not-validated | N/A (host script — no UI; test-covered/operational) |
| `scripts/freeze-openapi.sh` — freeze boba-jackett OpenAPI snapshot | implemented | host | contract `tests/contract/openapi_test.go` | tested-green-in-suite | N/A (host script — no UI; test-covered/operational) |
| `scripts/generate_markdown_exports.sh` — md→html/pdf export (§11.4.65) | implemented | host | self | tested-green-in-suite | N/A (host script — no UI; test-covered/operational) |
| `scripts/helixqa.sh` — HelixQA harness driver | implemented | host | self | not-validated | N/A (host script — no UI; test-covered/operational) |
| `scripts/opencode-helixqa.sh` — OpenCode HelixQA driver | implemented | host | self | not-validated | N/A (host script — no UI; test-covered/operational) |
| `scripts/install_git_hooks.sh` — git hook installer (§11.4.75) | implemented | host | self | tested-green-in-suite | N/A (host script — no UI; test-covered/operational) |
| `scripts/pre_build_verification.sh` — pre-build gate sweep | implemented | host | self (is the gate) | tested-green-in-suite | N/A (host script — no UI; test-covered/operational) |
| `scripts/pre_code_review.sh` — code-review gate (§11.4.125) | implemented | host | self | tested-green-in-suite | N/A (host script — no UI; test-covered/operational) |
| `scripts/run_all_challenges.sh` — challenge bank runner | implemented | host | self | not-validated | N/A (host script — no UI; test-covered/operational) |
| `scripts/run-tests.sh` — test runner helper | implemented | host | self | tested-green-in-suite | N/A (host script — no UI; test-covered/operational) |
| `scripts/scan.sh` — repo scan helper | implemented | host | none dedicated | not-validated | N/A (host script — no UI; test-covered/operational) |
| `scripts/track-build-resources.sh` — build resource sampler (§11.4.24) | implemented | host | none dedicated | not-validated | N/A (host script — no UI; test-covered/operational) |

### 8e. Infra / compose / startup

| Feature | Impl | Wired | Tests | Validation | Video |
|---------|------|-------|-------|------------|-------|
| `docker-compose.yml` — 2-container default + Go profile + boba-jackett service | infra | yes | e2e `test_live_containers.py` | tested-green-in-suite | N/A (infra — no UI; e2e-test-covered orchestration) |
| Jackett auto-configuration at startup (key extract → inject `JACKETT_API_KEY`) | implemented | yes | integration `test_jackett_autoconfig_real.py` | tested-green-in-suite | N/A (infra — no UI; integration-test-covered startup autoconfig) |
| `BOBA_MASTER_KEY` auto-generation (first-boot) for encrypted boba.db | implemented | yes | go `bootstrap/bootstrap_test.go` | unit (go) | N/A (infra — no UI; go-test-covered first-boot key generation) |

---

## Components NOT inventoried / discrepancies (honest gaps, §11.4.6)

- **CORRECTION vs Rev 2:** `boba-ctl.sh` DOES exist at `scripts/boba-ctl.sh` (Rev 2 said it did not). Its subcommands are now itemized in §8a. The underlying Go binary is `cmd/boba-ctl/main.go` (5 subcommands: up/down/status/health/list).
- **CORRECTION vs Rev 2:** the `install-plugin.sh` `PLUGINS` curated array has **44 entries**, not 12. ~21 have a matching `plugins/*.py` file; the rest (incl. `torrentproject`, `torrentscsv`) are curated names with no file present in this tree — itemized in §4c, not asserted as working.
- **Prometheus/OpenTelemetry metrics** — `tests/observability/test_metrics_exist.py` + `observability/` dir exist, but no `prometheus_client` `Counter()/Histogram()/Gauge()` definitions were found in `download-proxy/src`; metrics surface is via `GET /api/v1/stats` (counters maintained in-process), not a `/metrics` Prometheus endpoint. Stated as fact, not assumed.
- **Go `DownloadHandler` / `ActiveDownloadsHandler`** — flagged partial/stub in §2a (mock success / empty array, no qBit integration) per source reading. The Go profile is opt-in and NOT the shipped product.
- **Go scheduler** — CRUD-only, no driver loop (RW-10); schedules never fire. The Go enricher is missing (RW-11).
- **Video-recording confirmation** — `PENDING` for all rows EXCEPT the boba-ctl CLI subcommands (status/health/list) and the web-UI flows already filmed (`POST /api/v1/search` journey + dashboard tab/button/theme/Jackett tour). Remaining per-feature flows are an in-progress recording pass (§11.4.107/§11.4.143).
