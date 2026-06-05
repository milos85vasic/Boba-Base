# Python → Go Parity Gaps

**Revision:** 1
**Last modified:** 2026-06-06T00:00:00Z

**Last audited:** 2026-04-27 (commit `5f12be0`)
**Audit method:** side-by-side read of public surface (`grep -E "^func"` on Go,
module-level inspection on Python). No behavior testing performed.
**Spec reference:** `docs/superpowers/specs/2026-04-26-jackett-autoconfig-clean-rebuild-design.md` §7

## Status definitions

- **Ported** — feature exists in Go with equivalent behavior. Note inline divergences.
- **Partial** — feature exists in Go but lacks a sub-behavior. Note the gap.
- **Missing** — feature has no Go counterpart. Note user-visible risk.

## Summary

| Status | Count |
|---|---|
| Ported | 6 |
| Partial | 4 |
| Missing | 8 |
| **Total Python features audited** | **18** |

## Matrix

### `download-proxy/src/merge_service/`

| Python module | Feature | Go location | Status | Risk if Go-only today |
|---|---|---|---|---|
| `search.py` | `start_search()` orchestrator | `internal/service/merge_search.go: StartSearch` | Partial | Go path lacks plugin subprocess fan-out — no public tracker results from Python plugins |
| `search.py` | `_classify_plugin_stderr()` error categorization | (none) | Missing | No structured per-tracker error reporting on Go path |
| `search.py` | Public tracker subprocess + NDJSON parser | (none) | Missing | Public tracker plugins (eztv, piratebay, etc.) unreachable on Go path |
| `search.py` | Private tracker direct aiohttp (RuTracker, Kinozal, NNMClub, IPTorrents) | Partial in `internal/service/merge_search.go` | Partial | Verify per-tracker auth flow parity before flipping |
| `deduplicator.py` | Tiered dedup (infohash → name+size → fuzzy) | `merge_search.go` (inlined) | Partial | Verify Levenshtein parity; Python's `Deduplicator.merge_results()` has explicit tiered fallback that's not visible as a Go function |
| `enricher.py` | TMDB title resolution | (none) | Missing | Search results lack posters / years / content type on Go path |
| `enricher.py` | OMDb fallback | (none) | Missing | No fallback when TMDB rate-limits |
| `enricher.py` | TVMaze / AniList / MusicBrainz / OpenLibrary | (none) | Missing | No music / book / anime metadata enrichment on Go path |
| `validator.py` | BEP 48 HTTP scrape | (none) | Missing | No peer-count health check; results may show stale availability |
| `validator.py` | BEP 15 UDP scrape + bencode parser | (none) | Missing | Same |
| `scheduler.py` | Recurring search driver (cron-like) | `internal/api/scheduler_api.go: ScheduleStore` | Partial | Go has *storage* for schedules but **no driver loop that actually fires them** — UI lets you create schedules that never run |
| `hooks.py` | Pre/post-search + download hooks (callback dispatch) | `internal/api/hooks.go: HookStore` | Partial | Same shape: storage exists, runtime dispatch unclear (need runtime audit) |
| `retry.py` | Shared retry policy via tenacity | (none) | Missing | Each Go call site reimplements retry inline if at all — inconsistent backoff |
| `jackett_autoconfig.py` | Env-discovery + Jackett indexer auto-config (NEW in this spec) | (none) | Missing | Go boot does NOT auto-configure Jackett — operator must use Jackett UI |

### `download-proxy/src/api/`

| Python module | Feature | Go location | Status |
|---|---|---|---|
| `routes.py` | merge/search REST endpoints | `internal/api/search.go` | Ported |
| `auth.py` | Private-tracker auth (login, session refresh, CAPTCHA) | (none) | Missing |
| `hooks.py` | hooks REST endpoints | `internal/api/hooks.go` | Ported |
| `scheduler.py` | scheduler REST endpoints | `internal/api/scheduler_api.go` | Ported (storage only — see scheduler driver gap above) |
| `streaming.py` | SSE streaming endpoint | `internal/service/sse_broker.go` + `internal/api/search.go` | Ported |
| `theme_state.py` | Dashboard theme state | `internal/api/theme.go` | Ported |
| `jackett.py` | `/api/v1/jackett/autoconfig/last` (NEW) | (none) | Missing |

### `download-proxy/src/ui/`

| Python module | Feature | Go location | Status |
|---|---|---|---|
| Jinja2 dashboard templates | Operator UI fallback | (none) | Missing |

The Angular SPA dashboard is shared (lives in `frontend/`, served by both).
The Jinja2 fallback dashboard is Python-only.

## User-visible regressions if you flip Go-only today

In priority order:

1. **No metadata enrichment.** Search results lose posters, year, content type. Highest user-visible degradation.
2. **No Jackett auto-config.** Every fresh boot requires manual Jackett UI clicks.
3. **No public tracker plugin fan-out.** 600+ Python plugins (eztv, piratebay, etc.) unreachable. Search would only return whatever Jackett aggregates + the 4 private trackers (and only those wired in Go).
4. **No tracker validation.** Stale peer counts, no health detection.
5. **Schedules silently no-op.** UI creates them, driver never fires.
6. **No private-tracker auth REST surface.** No CAPTCHA refresh flow.

## Per-gap follow-up specs (proposed, in priority order)

1. **`enricher.go`** port — biggest user-visible gap. Wraps 6 external APIs. Estimate 2-3 days with tests.
2. **`validator.go`** port — BEP 48/15 with bencode parser. Estimate 1-2 days.
3. **`scheduler.go` driver loop** — make existing storage actually fire schedules. Estimate 1 day.
4. **Public tracker plugin subprocess fan-out** — replicate `_search_tracker()` subprocess pattern. Estimate 2-3 days.
5. **`jackett_autoconfig.go`** port of `jackett_autoconfig.py`. Estimate 1 day.
6. **`auth.go`** REST surface for private-tracker auth flows. Estimate 1-2 days.
7. **`hooks.go` runtime dispatch** — verify and complete callback firing.
8. **`retry.go`** shared policy.
9. **`deduplicator.go`** explicit tiered structure (clarification, not new behavior).

Each gap should ship as its own spec → plan → implementation cycle in the
superpowers flow, so nothing gets lost during the eventual Go-only flip.

## Audit data points captured

- Go service exports (count): 18 functions across `merge_search.go` + `sse_broker.go`.
- Go API exports (count): ~30 handler/store functions across 6 files.
- Python `merge_service/` modules: 7 (deduplicator, enricher, hooks, jackett_autoconfig, retry, scheduler, search, validator).
- Python `api/` modules: 7 (auth, hooks, jackett, routes, scheduler, streaming, theme_state).
