# Migration Summary

Python-to-Go migration blueprint and parity tracking.

## Contents

- `Migration_Python_Codebase_To_Go.md` — Comprehensive 1342-line blueprint for migrating the Python/FastAPI backend to Go/Gin, covering:
  - Project structure and data models
  - Config management and env loading
  - qBittorrent Web API client
  - Phased implementation plan with feature parity
- `PARITY_GAPS.md` — Side-by-side audit of Python vs. Go surface area, tracking: Ported, Partial, Missing, Not-Applicable

## Status

- Domain: Migration
- Docs count: 2
- Migration phase: **Blueprint complete, implementation ongoing**
- Go backend status: Skeleton/rewrite-in-progress — replicates API surface but lacks plugin ecosystem, dedup, enrichment, download proxying, scheduler, and private-tracker auth
- Last reviewed: 2026-06-08

## Parity Summary

| Area | Python | Go | Notes |
|------|--------|----|-------|
| Search API | ✅ Full | ✅ Basic | Go proxies to qBittorrent's built-in search |
| Deduplication | ✅ Tiered + Levenshtein | ❌ Missing | Core merge service feature |
| Enrichment | ✅ TMDB/OMDb/TVMaze/AniList | ❌ Missing | |
| Download proxy | ✅ Full (7186) | ❌ Missing | |
| Private-tracker auth | ✅ RuTracker/Kinozal/NNMClub/IPT | ❌ Missing | |
| WebUI bridge | ✅ Full (7188) | ⚠️ Skeleton | |
| SSE streaming | ✅ Full | ❌ Missing | |
| Scheduler | ✅ Full | ❌ Missing | |
| Theme injection | ✅ Cross-app | ❌ Missing | |

## Related

- [Architecture Summary](docs/Architecture_Summary.md) — current system topology
- [PARITY_GAPS.md](docs/migration/PARITY_GAPS.md) — detailed parity audit
