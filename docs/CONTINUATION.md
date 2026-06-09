# Continue — Project Status Snapshot

**Session:** 2026-06-09 (Session 8 complete — 47 test files, 4,074+ tests, 88%+ coverage, 21 bugs fixed)
**Last commit:** `c8254ee`
**Branch:** `main`
**Working tree:** CLEAN

> Send `continue` to pick up exactly where we left off.
> This file is the single source of truth for session handoff.

---

## Session 8 Summary

| Metric | Value |
|--------|-------|
| Test files | 47 test modules (222 `test_*.py` files total across all suites) |
| Test cases | 4,074+ passed |
| Coverage (unit) | 88%+ (gate: 49%) |
| Bugs fixed | 21 (BOB-001 through BOB-025, minus BOB-008) |
| Submodules aligned | constitution, challenges, containers, helixqa, jackett |
| Ruff / Mypy | pre-existing warnings only, 0 new |

### Bug Tracker

21 bugs fixed across Session 8:
- 10 B-substring parsing fixes
- 3 `import re` missing fixes
- 2 comma-size parsing fixes
- 2 crash guards
- 1 bt4g hang fix
- 1 dedup circular import fix
- 1 env_loader flaky test fix
- 1 pirateiro full test suite (44/44)

**1 remaining:** BOB-008 (RuTracker CAPTCHA) — operator-blocked, needs manual cookie paste.

### Test File Inventory

```
tests/unit/merge_service/          (31 files)
  test_cors_config.py
  test_dead_tracker_bucket.py
  test_deadline_tunable.py
  test_deduplicator.py
  test_deduplicator_edge.py
  test_diag_no_stale_leakage.py
  test_edge_case_challenges.py
  test_enricher.py
  test_enricher_edge.py
  test_hooks.py
  test_html_parsers.py
  test_jackett_autoconfig.py
  test_nnmclub_session_login.py
  test_private_tracker_html_fixtures.py
  test_public_plugin_harness.py
  test_public_plugin_harness_broad.py
  test_public_tracker_capture.py
  test_public_tracker_subprocess_timeout.py
  test_quality_detection.py
  test_scheduler.py
  test_scheduler_coverage.py
  test_search_concurrency.py
  test_search_coverage.py
  test_search_deep_coverage.py
  test_search_error_paths.py
  test_session_encryption.py
  test_theme_endpoint.py
  test_tracker_stats.py
  test_ttl_caches.py
  test_validator.py
  test_validator_coverage.py

tests/unit/api_layer/              (14 files)
  test_auth_coverage_extra.py
  test_concurrent_writers.py
  test_cors_config.py
  test_hooks_coverage.py
  test_hooks_endpoints.py
  test_hooks_remaining.py
  test_nnmclub_auth_endpoints.py
  test_routes_coverage.py
  test_sse_disconnect.py
  test_sse_token_auth.py
  test_theme_state_coverage.py
  test_theme_stream.py
  test_tracker_stats_sse.py

tests/unit/                        (55 files, infrastructure + plugin tests)
  test_auth.py, test_auth_coverage.py, test_auth_models.py
  test_config.py, test_main.py, test_dashboard.py
  test_content_type_refinement.py
  test_credential_env_wiring.py
  test_download_proxy_coverage.py, test_download_proxy_deep.py
  test_download_merged.py
  test_env_loader.py
  test_freeleech.py
  test_graceful_shutdown.py
  test_helpers.py
  test_log_filter.py
  test_merge_trackers.py
  test_novaprinter.py
  test_private_tracker_search.py
  test_public_tracker_subprocess.py
  test_retry_policy.py
  test_routes.py, test_routes_coverage.py
  test_scheduler_api.py
  test_sorting_weights.py
  test_sse_disconnect.py
  test_streaming.py
  test_theme_injector.py, test_theme_wiring.py
  test_webui_theme_injector.py
  test_ui_module.py, test_ui_sorting.py
  test_plugin_*.py                  (39 plugin modules: eztv, piratebay, solidtorrents,
                                     limetorrents, torlock, gamestorrents, nyaa, kickass,
                                     anilibra, torrentgalaxy, yts, rutor, tokyotoshokan,
                                     snowfl, torrentdownload, linuxtracker, kinozal,
                                     nnmclub, rutracker, megapeer, jackett, audiobookbay,
                                     one337x, extratorrent, torrentfunk, torrentproject,
                                     therarbg, academictorrents, ali213, yourbittorrent,
                                     glotorrents, pctorrent, rockbox, bitru, btsow,
                                     torrentscsv, xfsub, yihua, pirateiro, bt4g, iptorrents)
  test_*_guards.py, test_*_deep.py  (crash guards + deep coverage variants)
  test_ci_infra.py, test_ci_workflows.py
  test_community_plugins_compile.py
  test_courses_scaffold.py, test_course_scripts_lint.py
  test_docs_presence.py
  test_frontend_spec_coverage.py
  test_install_plugin_json_config.py
  test_jackett_integration.py, test_jackett_plugin_pool.py
  test_nnmclub_config_selfheal.py, test_nnmclub_plugin_login.py
  test_no_runtime_service_skips.py
  test_openapi_frozen.py
  test_page_title.py, test_footer_restored.py
  test_palette_catalog.py, test_palette_catalog_python_mirror.py
  test_quality_compose.py, test_quality_detection.py
  test_readme_landing_page.py
  test_runtime_requirements_includes_new_deps.py
  test_scan_script_non_interactive.py
  test_scanner_configs.py
  test_service_fixtures.py
  test_shadow_tokens.py
  test_socks_udp.py
  test_start_sh_copy_plugins_framework.py
  test_toolchain_config.py
  test_tracker_validator.py
  test_website_config.py
  test_branding_assets.py
  test_architecture_diagrams.py
  test_build_releases_non_interactive.py
  tests/benchmark/                  (3)
  tests/chaos/                      (2)
  tests/concurrency/                (3)
  tests/contract/                   (5)
  tests/docs/                       (3)
  tests/e2e/                        (7)
  tests/integration/                (19)
  tests/memory/                     (1)
  tests/observability/              (2)
  tests/performance/                (1)
  tests/property/                   (2)
  tests/security/                   (10)
  tests/stress/                     (2)
```

### Commits (latest 10+)

```
c8254ee fix: 21 test failures, pirateiro 44/44, coverage gate 88%, dedup circular import
ccd0dc9 fix: env_loader flaky test + coverage baseline 88.14% + minor test fixes
3d1819c docs: finalize Session 8 — Fixed.md Rev 12, 59 items, 18 bugs, 41 plugins
f924841 test: wave 8 — btsow/torrentscsv/xfsub/yihua (170 tests) + bt4g fix + 2 fixes
6773203 test: wave 7 — yourbittorrent/glotorrents/pctorrent/rockbox/bitru (164 tests) + bitru fix
f191401 test: wave 6 — torrentfunk/torrentproject/therarbg/academictorrents/ali213 (178 tests) + 2 fixes
1446cc5 test: wave 5 — audiobookbay/one337x/extratorrent (155 tests) + 3 fixes
fd543b0 docs: update CONTINUATION.md for Session 8 (4 waves, 23 plugins)
aae4069 test: wave 4 — kinozal/nnmclub/rutracker/megapeer/jackett + megapeer B-substring fix
e3b7acb test: wave 3 — rutor/tokyotoshokan/snowfl/torrentdownload/linuxtracker + nyaa/kickass fixes
```

---

## Coverage Snapshot

| Module | Coverage |
|--------|----------|
| api/__init__.py | 98% |
| api/auth.py | 91% |
| api/routes.py | 95% |
| api/streaming.py | 99% |
| main.py | 94% |
| deduplicator.py | 94% |
| enricher.py | 100% |
| hooks.py | 95% |
| jackett_autoconfig.py | 99% |
| scheduler.py | 93% |
| search.py | ~90% |
| validator.py | 92% |
| theme_injector.py | 99% |
| env_loader.py | 100% |
| download_proxy.py | ~55%+ |
| **TOTAL (unit)** | **88%+** |

---

## Known Issues

1. **BOB-008**: RuTracker CAPTCHA — operator-blocked (needs manual cookie paste)
2. Go backend is a skeleton (documented in AGENTS.md)
3. Containers may be down on session start — `bash start.sh` first
4. macOS + podman `network_mode: host` does NOT forward ports — `ensure-macos-tunnel.sh` handles this

---

## Quick-Start

```bash
# Pre-build gate
bash scripts/pre_build_verification.sh

# Unit tests
python3 -m pytest tests/unit/ -q --import-mode=importlib

# Coverage
python3 -m pytest tests/unit/ --cov=download-proxy/src --cov=plugins --cov-report=term --import-mode=importlib

# Lint + typecheck
ruff check . && mypy download-proxy/src/

# Frontend
cd frontend && npx vitest run

# Containers
bash start.sh && bash stop.sh
```

---

## Architecture

| Port | Service | Tech |
|------|---------|------|
| 7185 | qBittorrent WebUI | LinuxServer (`admin`/`admin`) |
| 7186 | Download Proxy | Python HTTP |
| 7187 | Merge Search Service | FastAPI + Angular SPA |
| 7188 | WebUI Bridge | Python (host process) |
| 7189 | boba-jackett | Go/Gin |
| 9117 | Jackett | LinuxServer (auto-configured) |
