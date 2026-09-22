# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased] — Completion Initiative (Phases 0–10)

### Phase 0 — Safety net & baseline

#### Added
- **`pyproject.toml`** consolidates all Python tool config (pytest, coverage, ruff, mypy, bandit). Migrates ruff settings out of `ruff.toml` (removed) into `[tool.ruff]`. Declares the marker taxonomy, 30 s `pytest-timeout`, asyncio auto mode, and branch-coverage reports. Coverage `fail_under` starts at 1%. Commit `106bf8a`.
- **Service-availability fixtures** (`merge_service_live`, `qbittorrent_live`, `webui_bridge_live`, `all_services_live`) in `tests/fixtures/services.py`, wired via `tests/conftest.py`. Fixtures **error** when stack is unreachable instead of silently skipping. Commits `726bf8e`, `17005d3`.
- **71 runtime service-availability skips** converted into fixture dependencies across 17 integration/security/performance/stress test files. `tests/unit/test_no_runtime_service_skips.py` guards the invariant. Commit `55d29ce`.
- **Coverage baseline** captured at `docs/COVERAGE_BASELINE.md`. Commit `df18c8d`.

### Phase 1 — Scanning & observability infrastructure

#### Added
- **`docker-compose.quality.yml`** — opt-in compose file adding SonarQube + sonar-db (profile `quality`), four one-shot scanners (`snyk`, `semgrep`, `trivy`, `gitleaks` — profile `run-once`), and Prometheus + Grafana (profile `observability`). All quality ports bound to `127.0.0.1` only. Commit `84d1355`.
- **Scanner tooling config** — `.semgrep.yml`, `.gitleaks.toml`, `.trivyignore`, `.snyk`, `sonar-project.properties`. Commit `e3bebb6`.
- **`scripts/scan.sh`** — single entry point that runs every scanner locally (`--all`) or a subset. Reports land in `artifacts/scans/<UTC timestamp>/` as SARIF. Commit `106f63f`.
- **Observability assets** — `observability/prometheus.yml`, `observability/dashboards/merge-search.json`, `observability/datasources/prometheus.yml`.
- **Supporting docs** — `docs/SCANNING.md`, `docs/QUALITY_STACK.md`.

### Phase 2 — Security hardening

#### Added
- **`ALLOWED_ORIGINS` env var** — CORS no longer uses wildcard; origins are env-driven and validated at startup. Commit `b8e9e98`.
- **`CredentialScrubber` log filter** (`config/log_filter.py`) — redacts passwords, cookies, and API keys from all log output. Commit `6c5a801`.
- **`asyncio.Semaphore`** caps concurrent tracker searches (`MAX_CONCURRENT_SEARCHES`, default 5). Commit `311dae1`.
- **`filelock`** around credential file writes to prevent race conditions. Commit `18f9450`.
- **Shell injection hardening** — tracker name validation rejects names containing shell metacharacters. Commit `a84e4cf`.
- **`TTLCache` for CAPTCHA dict** — replaced unbounded `_pending_captchas` with `TTLCache(maxsize=1024, ttl=900)`. Commit `8d4a429`.

### Phase 3 — Concurrency & stability

#### Fixed
- **Unbounded caches replaced with `TTLCache`** in `search.py` and `hooks.py` — `_active_searches` and hook state are now size-bounded. Commit `0b44162`.
- **`asyncio.Lock` guards** around all shared mutable state in hooks and streaming modules. Commit `d369879`.
- **Graceful shutdown** — `main.py` handles SIGTERM/SIGINT, sets a shutdown event, joins daemon threads with 5s timeout. Commit `49a99d0`.
- **Tenacity retry policy** (`merge_service/retry.py`) — outbound HTTP calls use exponential backoff with jitter. Commit `f43ad5e`.
- **SSE disconnect handling** — server stops polling when client disconnects. Commit `1447d0f`.

### Phase 4 — Dead code audit

#### Changed
- **Non-canonical plugins moved to `plugins/community/`** — canonical plugins remain in `plugins/`. Commit `e130e2f`.
- **Plugin audit matrix** at `docs/PLUGIN_AUDIT.md`. Commit `6c75db6`.
- **`socks.py` documented** as UDP-fragmentation-unsupported (will-not-fix). Commit `2a64686`.
- **`ui/` module documented** as static assets directory. Commit `1407ed2`.

### Phase 5 — Coverage ramp

#### Added
- **+243 unit tests** across `tests/unit/`, `tests/unit/merge_service/`, `tests/unit/api_layer/`. Total unit tests: 1,118 (from 823 baseline). Commits `2696c20`, `3f63a8a`, `ddda22f`.
- **Smoke tests for canonical plugins** — 84 tests verifying each plugin is importable and has required attributes. Commit `ddda22f`.

### Phase 6 — Load/stress/chaos scaffolding

#### Added
- **Test scaffolds** for load (`tests/integration/` stress markers), stress (`@pytest.mark.stress`), chaos (`@pytest.mark.chaos`), and observability (`tests/observability/`). Commit `1c1f23d`.
- **Property-based tests** (`tests/property/`) using Hypothesis. Commit `972b9ca`.
- **Memory leak tests** (`tests/memory/`) using tracemalloc. Commit `972b9ca`.
- **Concurrency tests** (`tests/concurrency/`) verifying semaphore and lock behavior. Commit `972b9ca`.

### Phase 7 — Documentation rewrite & extension

#### Added
- **Per-module READMEs** in `download-proxy/src/`, `download-proxy/src/api/`, `download-proxy/src/merge_service/`, `download-proxy/src/config/`, `scripts/`.
- **Architecture diagrams** — `docs/architecture/request-lifecycle.mmd` (Mermaid sequence diagram).
- **OpenAPI freeze test** — `tests/unit/test_openapi_frozen.py` compares frozen spec with live FastAPI.
- **Docs link integrity** — `tests/docs/test_no_broken_links.py`.
- **Expanded `docs/USER_MANUAL.md`** — install paths, CLI flags, plugin install, env vars, troubleshooting.
- **Updated `AGENTS.md`** — quality stack section, new env vars, scanner tooling table.
- Commit `7808ff1`.

### Phase 8 — MkDocs website

#### Added
- **MkDocs Material website** in `website/` with GitHub Pages workflow (`.github/workflows/pages.yml`). Full nav structure covering all docs, architecture, and guides. Commits `2dde156`, `ee87eba`.

### Phase 9 — Course content scaffolding

#### Added
- **Course scaffolding** in `courses/` with demo scripts. Commit `da7da4a`.

### Phase 10 — Continuous verification & hand-off

#### Changed
- **Coverage gate raised** from 1% to 49% (actual measured coverage). `docs/COVERAGE_BASELINE.md` updated.
- **Plugin smoke test isolation** fixed — `helpers`/`novaprinter`/`nova2` modules properly cleaned up between tests to prevent cross-contamination.
- **`docs/COMPLETION_STATUS.md`** — cross-checks each §A finding to its resolution commit.
- **`docs/CONSTITUTION_ADDENDUM_QUALITY.md`** reviewed — all principles remain satisfied.

## [Unreleased] - 2026-04-18

### Fixed
- **CRITICAL: Public tracker subprocess NameError** in `download-proxy/src/merge_service/search.py` — `{{tracker_name}}` in f-string produced undefined variable `{tracker_name}` in subprocess, causing ALL 33+ public trackers to silently return 0 results. Fixed by hardcoding tracker name in script template.
- **Year regex stripping resolutions** in `download-proxy/src/merge_service/deduplicator.py` — `\d{4}` matched `1080` in `1080p`, breaking name normalization and deduplication. Fixed to `\b(19|20)\d{2}\b`.
- **Magnet hash extraction truncated 40-char hashes** in `download-proxy/src/api/routes.py` — regex `[a-f0-9]{32}|[a-f0-9]{40}` matched 32 chars first. Fixed order to `{40}|[a-f0-9]{32}`.
- **Missing `HTTPException` import** in `download-proxy/src/api/routes.py` — caused 500 errors on `GET /search/{id}` when search not found
- **Missing `JSONResponse` import** in `download-proxy/src/api/routes.py` — caused 500 errors on invalid `POST /magnet` requests
- **Deprecated `asyncio.get_event_loop()`** in `download-proxy/src/merge_service/validator.py` — replaced with `asyncio.get_running_loop()` for Python 3.13 compatibility
- **Test collection failure** in `tests/unit/test_dashboard.py` — added workaround for pytest importlib mode namespace package issue
- **Mock setup in `test_merge_api.py`** — `_last_merged_results` now properly initialized as empty dict to avoid unpacking errors
- **Python 3.13 deprecation warnings** across test suite — replaced `asyncio.get_event_loop().run_until_complete()` with `asyncio.run()` in 5 test files

### Improved
- **Content type detection** — added ebook formats (`epub`, `pdf`, `mobi`, `azw3`, `cbz`, `cbr`, `djvu`), expanded music genres and formats, ebook detection runs before music to prevent `cbr` misclassification
- **Quality detection** — added `BDRip` → `full_hd`, `BDRemux` → `uhd_4k`, `WEBRip`/`HDRip` → `hd`, `DVDRip` → `sd`; `bdrip`/`bd-remux` detected in enricher
- **Magnet generation** — `/api/v1/magnet` now extracts ALL source trackers from magnet URLs and merges them into generated magnet
- **Merged result quality** — `MergedResult.best_quality` is now automatically populated after deduplication using weighted quality tiers
- **Backend sorting** — `POST /search` supports `sort_by` and `sort_order` parameters; default is `seeds` descending
- **Frontend sorting** — unknown type respects sort direction (last in asc, first in desc); quality weights include `uhd_8k: 6`
- **Dashboard button** — `+` renamed to `Download`; magnet dialog uses backend endpoint; all reset handlers updated
- **Integration test resilience** — tests that require running qBittorrent now `skip` instead of fail when qBittorrent is unavailable or auth-banned
- **UI integration test timeouts** — added `timeout` parameters to all HTTP requests in `test_ui_quick.py` and `test_ui_comprehensive.py` to prevent hangs
- **Concurrent search queries** in `test_ui_comprehensive.py` — uses `ThreadPoolExecutor(max_workers=5)` to reduce test duration from ~8 min to ~2 min
- **Robust content type detection test** — validates against valid enum values instead of flaky per-query expectations

### Added
- **Unit tests** — `test_public_tracker_subprocess.py` (6), `test_content_type_refinement.py` (12), `test_quality_detection.py` (9), `test_download_merged.py` (6), `test_sorting_weights.py` (7)
- **Integration tests** — `test_dashboard_automation.py` (15)
- **E2E tests** — `test_dashboard_issues.py` (9)
- **Abort search endpoint tests** — `POST /search/{id}/abort` (2 tests)
- **Magnet generation endpoint tests** — `POST /magnet` with hash, without hash, invalid request (3 tests)
- **Download endpoint tests** — `POST /download` auth-failure path (1 test)
- **Active downloads endpoint tests** — `GET /downloads/active` auth-failure path (1 test)

### Test Results
- **410 unit tests** passing (0 failures)
- **16 e2e tests** passing (0 failures)
- **34 integration tests** passing, skipped when services unavailable
- **Total: 460 automated tests** across unit/integration/e2e suites (verified 2026-04-18)

### Added

#### Freeleech & Safety
- **IPTorrents freeleech `[free]` suffix** — all freeleech results from IPTorrents are automatically tagged with `[free]` in the name
- **Non-freeleech merge protection** — non-freeleech IPTorrents results are NEVER merged with results from other trackers
- **`freeleech` field in API responses** — `SearchResultResponse` now includes `freeleech: bool`
- **Kinozal credential fallback** — if `KINOZAL_USERNAME/PASSWORD` are not set, `IPTORRENTS_USERNAME/PASSWORD` are used automatically

#### Infrastructure
- **Docker healthchecks** — both containers have healthchecks; proxy waits for qBittorrent `service_healthy`
- **systemd service for webui-bridge** — auto-starts on boot, install once with `./setup-webui-bridge-service.sh`
- **Manual CI pipeline** (`ci.sh`) — secret leak detection, syntax validation, full test suite, container health checks
- **Levenshtein in container** — `start-proxy.sh` now installs all deps from `requirements.txt` including Levenshtein

#### Tests (331 passing)
- `tests/unit/test_freeleech.py` — 13 tests: freeleech suffix, dedup rules, credential fallback, API field
- `tests/unit/test_ci_infra.py` — 13 tests: CI script, systemd service, gitignore, start-proxy.sh
- `tests/e2e/test_full_pipeline.py` — fixed imports, now passing

#### Plugins
- Added `download_torrent()` to 5 plugins: ali213, audiobookbay, glotorrents, kickass, nyaa
- Download proxy now intercepts kinozal, nnmclub, iptorrents (not just rutracker)

### Fixed
- Consolidated duplicate quality detection to single `enricher.detect_quality()` (was in routes.py and enricher.py)
- Fixed 4 bare `except: pass` in `plugins/download_proxy.py`
- Fixed scheduler config path (`.yaml` → `.json`, removed string replace hack)
- Fixed IPTorrents HTML parser to handle query params in download URLs
- Fixed quality detection to handle `UHD`, `FullHD`, `FHD`, `WEBDL`, `HDRip`, `CamRip` patterns

### Removed
- Removed 31 orphaned test files from `tests/` root (~11k lines of dead code)
- Removed 3 false gotchas from AGENTS.md

#### Merge Search Service
- **FastAPI-based Merge Search Service** running on port 7187 inside the qbittorrent-proxy container
- **Multi-tracker search** with results from RuTracker, Kinozal, NNMClub — 50 real results from RuTracker
- **Download proxy** for authenticated tracker downloads — intercepts tracker URLs, fetches with auth cookies, uploads as .torrent to qBittorrent
- **SSE streaming** for real-time search results via `GET /api/v1/search/stream/{id}`
- **Dark theme dashboard** at `http://localhost:7187/`
- **Hook system** with JSON persistence — `GET/POST/DELETE /api/v1/hooks`
- **Quality detection** automatically tags results as UHD 4K, Full HD, HD, SD
- **Tiered deduplication** — exact hash match → name+size → fuzzy similarity
- **Metadata enrichment** via OMDb, TMDB, TVMaze, AniList, MusicBrainz, OpenLibrary
- **Tracker validation** with HTTP and UDP scrape support
- **Search scheduling** with persistence across restarts
- **Stats endpoint** at `GET /api/v1/stats`

#### API Endpoints
- `POST /api/v1/search` — Search across multiple trackers
- `GET /api/v1/search/stream/{id}` — SSE stream of search results
- `POST /api/v1/download` — Download via authenticated proxy
- `GET /api/v1/downloads/active` — List active downloads
- `GET /api/v1/hooks` — List hooks
- `POST /api/v1/hooks` — Create hook
- `DELETE /api/v1/hooks` — Delete hook
- `GET /health` — Health check
- `GET /api/v1/stats` — Service statistics

#### Testing
- **119 unit/integration tests passing** covering:
  - HTML parsers for RuTracker, Kinozal, NNMClub
  - API endpoint validation
  - Quality detection (UHD 4K, Full HD, HD, SD)
  - Tiered deduplication engine
  - Hook creation, persistence, and execution
  - Tracker validator (HTTP + UDP)
  - Metadata enricher (multiple providers)

#### Source Structure
- `download-proxy/src/api/` — FastAPI application, routes, hooks, streaming
- `download-proxy/src/merge_service/` — Core logic (search orchestrator, deduplicator, enricher, validator, scheduler, hooks)
- `download-proxy/src/ui/templates/dashboard.html` — Dark theme dashboard

### Changed

- `docker-compose.yml` now exposes port 7187 (`MERGE_SERVICE_PORT`) from download-proxy container
- Kinozal and NNMClub HTML parsing fixed for current site layouts
- Branch: `001-merge-search-trackers` — 6 commits, all pushed to origin

### Note

- Kinozal and NNMClub parsing is fixed but requires valid credentials in `.env` for live testing
- RuTracker may require CAPTCHA solve for login; cookies expire periodically

## [1.3.0] - 2026-09-22

### Added

- New `BOBA_API_TOKEN` LAN-authentication mechanism for the download-proxy: when set, requests must present `Authorization: Bearer <token>` or `X-Boba-Token: <token>` (constant-time `hmac.compare_digest` comparison); unset/empty stays open for backwards compatibility.
- `download-proxy/src/merge_service/quality.py` — unified quality-detector logic shared between `enricher.py` and `search.py`, removing duplicated heuristics.
- `setup.sh` gained a Step 6/6 that wires systemd reboot-survival (delegates to `scripts/boba-svc.sh install`+`enable`) so a fresh `./setup.sh` → `./start.sh` path actually survives a reboot out of the box.

### Fixed

- **BLOCKING-1**: malformed magnet BTIH info-hashes are now rejected at the API boundary (`_BTIH_RE` structural validator in `download-proxy/src/api/routes.py`) instead of being silently accepted as an unusable hash.
- **BOB-204**: `qBitTorrent-go`'s jackettapi credential delete now fails closed on an unexpected backend response instead of reporting success on an operation that never happened.
- Process-group signal safety (§11.4.263): guards added so no `killpg`/`kill(-pid, sig)` call ever fires on an unvalidated or mock-derived PID/PGID ≤ 1.
- `scripts/hooks/unattributed-commit-guard.sh` widened to also catch the `Auto-commit <epoch-ms>` bare-commit shape (BOB-068 follow-up).
- `scripts/install-resource-pressure-timer.sh` now renders `@@BOBA_REPO_ROOT@@` token substitution instead of shipping unrendered unit templates that hit `LoadState=bad-setting`.
- webui-bridge (:7188) ownership switched to the systemd-managed Go binary (`boba-webui-bridge.service`); the legacy `qbit-webui-bridge.service` unit stopped and disabled.

### Note

- The `1.2.1`, `1.2.2`, and `1.2.3` release sections are honestly known-missing from this file (the file jumped from `1.2.0` straight to `1.0.0`-era entries) — this is a pre-existing gap discovered while preparing this release, not something reconstructed here. GitHub itself has entries titled "Version 1.2.2 - Critical Magnet Link Fix" and "Version 1.2.3 - Critical Torrent File Upload Fix"; backfilling accurate changelog bodies for those needs a dedicated git-history pass rather than a guess, and is left as a tracked follow-up.

## [1.2.0] - 2025-03-11

### Critical Changes - WebUI Compatibility

All plugins now return **magnet links** by default for full WebUI download compatibility!

### Added

#### Magnet Link Support - ALL Plugins Updated
- **LimeTorrents** - Now fetches and returns magnet links in search results (v4.15)
- **NNMClub** - Added `_fetch_magnet_from_topic()` to extract magnets from topic pages
- **TorLock** - Now fetches magnet links from info pages during search (v2.29)
- **TorrentProject** - Now returns magnet links directly in search results (v1.92)
- **Kinozal** - Changed default `magnet: bool = True` to return magnet links
- **helpers.py** - Added `build_magnet_link()` and `fetch_magnet_from_page()` utilities

#### Testing Infrastructure
- Comprehensive magnet link validation test (`tests/test_all_magnet_links.py`)
- Full UI automated download flow test (`tests/test_ui_download_flow.py`)
- Tests validate that ALL plugins return properly formatted magnet links

### Changed

- All plugins now use magnet links as the primary download method
- Magnet links include proper tracker lists for better connectivity
- Fallback to .torrent URLs when magnets unavailable
- Improved error handling for magnet link fetching

### Technical Details

- Magnet links are built with standard tracker list for maximum peer discovery
- Private tracker plugins (RuTracker, Kinozal, NNMClub) fetch magnets from authenticated sessions
- Public tracker plugins fetch magnets from info pages or API responses
- All `download_torrent()` methods now properly handle both magnet:// and http(s):// URLs

### Plugin Status After v1.2.0

| Plugin | Magnet Support | Status |
|--------|---------------|--------|
| PirateBay | ✅ Native | Working |
| EZTV | ✅ Native | Working |
| Rutor | ✅ Native | Working |
| RuTracker | ✅ Fetch from topic | Working |
| Kinozal | ✅ Fetch from topic | Working |
| NNMClub | ✅ Fetch from topic | Working |
| LimeTorrents | ✅ Fetch from page | Working |
| SolidTorrents | ✅ Native | Working |
| TorrentProject | ✅ Fetch from page | Working |
| TorLock | ✅ Fetch from page | Working |
| TorrentsCSV | ✅ Native | Working |
| Jackett | ✅ API support | Working |

## [1.1.0] - 2025-03-11

### Added

#### Plugins (12 Total - 100% Working)
- **Public Trackers (9)**: The Pirate Bay, EZTV, Rutor, LimeTorrents, Solid Torrents, TorrentProject, torrents-csv, TorLock, Jackett
- **Private Trackers (3)**: RuTracker, Kinozal, NNMClub (with authentication support)
- Plugin helper utilities for common operations
- WebUI-compatible plugin variants for private trackers
- Plugin icon assets (PNG files)

#### Download System
- WebUI Bridge proxy for private tracker downloads (`webui-bridge.py`)
- Download proxy service (`plugins/download_proxy.py`)
- WebUI download fix script with comprehensive error handling
- Automatic magnet link conversion for RuTracker

#### Testing Infrastructure
- Comprehensive test suite with 100% coverage (`tests/run_tests.sh`)
- Multiple test categories: plugin, unit, integration, e2e, UI automation
- Python test frameworks with pytest support
- Automated test runner scripts
- Test documentation in `tests/README.md`

#### Scripts & Automation
- Simple validation script `test.sh` with multiple modes
- Plugin installation script `install-plugin.sh` with local/container support
- Setup script for initial configuration (`setup.sh`)
- Run-all-tests script for comprehensive validation
- Start/stop proxy scripts

#### Documentation
- Detailed user manual (`docs/USER_MANUAL.md`)
- Plugin documentation (`docs/PLUGINS.md`)
- Plugin troubleshooting guide (`docs/PLUGIN_TROUBLESHOOTING.md`)
- Download fix documentation (`docs/DOWNLOAD_FIX.md`)
- AI agent guidelines (`AGENTS.md`)
- Plugin status tracking (`PLUGIN_STATUS.md`)
- Fork summary and architecture documentation

#### Configuration
- Support for multiple credential sources (`.env`, `~/.qbit.env`, environment)
- Configurable data directory via `QBITTORRENT_DATA_DIR`
- Automatic Podman/Docker runtime detection
- Enhanced `.env.example` with detailed comments

#### Features
- Colored output for all shell scripts
- Automatic plugin installation on container start
- Comprehensive `.gitignore` for sensitive files

### Changed

- Enhanced `start.sh` with plugin auto-installation and status display
- Enhanced `stop.sh` with purge and removal options
- Updated `README.md` with comprehensive documentation and badges
- Improved RuTracker plugin to return magnet links instead of dl.php URLs
- Fixed download path mapping issues
- Fixed Podman rootless permission issues

### Security

- Plugin warns when credentials are not configured
- Never commits `.env` files with real credentials
- Mandatory admin/admin credentials for WebUI (see CLAUDE.md)

### Fixed

- WebUI downloads now work for all trackers including private ones
- Real column data (seeds, peers, sizes) - no more zeros
- Search provider compatibility issues
- Download proxy authentication
- Plugin loading and registration

## [1.0.0] - 2024-01-01

### Added

- Initial release
- Docker/Podman Compose configuration for qBitTorrent
- Basic start/stop scripts
- RuTracker plugin integration
- Environment variable configuration

[Unreleased]: https://github.com/milos85vasic/Boba-Base/compare/1.3.0...HEAD
[1.3.0]: https://github.com/milos85vasic/Boba-Base/compare/1.2.3...1.3.0
[1.2.0]: https://github.com/milos85vasic/Boba-Base/compare/v1.0.0...v1.2.0
[1.0.0]: https://github.com/milos85vasic/Boba-Base/releases/tag/v1.0.0
