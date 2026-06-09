# Continue — Project Status Snapshot

**Session:** 2026-06-09 (Session 4 — coverage push: routes.py 95%, search.py 80%, submodules synced)
**Last commit:** `6953662` (working tree CLEAN)
**Branch:** `main` — pushed to all upstreams
**Workable-item tracking:** LIVE at [`Issues.md`](Issues.md) / [`Fixed.md`](Fixed.md) with prefix **BOB**, backed by SQLite DB at `docs/workable_items.db`.

> Send `continue` to pick up exactly where we left off.
> This file is the single source of truth for session handoff.

---

## What We Did (Session 4)

| Area | Work Done |
|------|-----------|
| **routes.py coverage** | 75% → 95% (+20%). Added 78 tests: search_sync flow/sorting/CAPTCHA, SSE stream cap 429, get_search with merged results, auth bad-JSON fallback + save credentials, tracker download flow (temp file + upload), non-tracker failure, per-URL exception, direct URL download, multi-hash magnet generation. |
| **search.py coverage** | 79% → 80% (+1%). Added stream token issue/validate, get_all_tracker_results with results, get_live_results empty-tracker-results branch, get_search_status found, get_active_searches non-empty. |
| **validator.py coverage** | 72% → 92% (from previous session, committed this session) |
| **jackett_autoconfig.py coverage** | 72% → 99% (from previous session, committed this session) |
| **Submodules synced** | constitution + helixqa pulled from upstream, all repos pushed |
| **Coverage baseline** | Updated COVERAGE_BASELINE.md (Revision 2): 60% total, 1802 tests |

### Verification (green tree)

```
Pre-build gate:  18 passed, 0 failed
Unit tests:      1802 passed, 0 failed
Total coverage:  60% (gate: 49%)
Core modules:    all ≥80%
routes.py:       95%
search.py:       80%
validator.py:    92%
jackett_autoconfig.py: 99%
```

### Commits

```
6953662 chore: update helixqa submodule to latest upstream
995986c chore: update constitution submodule to latest upstream
d2b14ed test: routes.py 95%, search.py 80%, validator 92%, jackett_autoconfig 99%
e5fcdb1 test: api/__init__ lifespan, CORS, SPA routes, dashboard — 70% to 98%
6a01128 test: harden main.py, enricher, streaming — 100% enricher, 94% main, 99% streaming
```

---

## Quick-Start for Next Session

```bash
# 1. Pre-build gate
bash scripts/pre_build_verification.sh

# 2. Tests
python3 -m pytest tests/unit/ -q --import-mode=importlib

# 3. Coverage
python3 -m pytest tests/unit/ --cov=download-proxy/src --cov=plugins --cov-report=term --import-mode=importlib

# 4. Lint + typecheck
ruff check . && mypy download-proxy/src/

# 5. Frontend
cd frontend && npx vitest run
```

---

## Quick Reference — Key Commands

```bash
# Pre-build gate
bash scripts/pre_build_verification.sh

# Tests
python3 -m pytest tests/unit/ -q --import-mode=importlib

# Coverage
python3 -m pytest tests/unit/ --cov=download-proxy/src --cov=plugins --cov-report=term --import-mode=importlib

# Lint
ruff check . && mypy download-proxy/src/

# Containers
bash start.sh && bash stop.sh

# Workable items
./bin/workable-items validate --db docs/workable_items.db
./bin/workable-items report --db docs/workable_items.db --by-status
```

---

## Architecture TL;DR

| Port | Service | Tech | Notes |
|------|---------|------|-------|
| 7185 | qBittorrent WebUI | LinuxServer image | `admin`/`admin` hardcoded |
| 7186 | Download Proxy | Python HTTP | Proxies WebUI + private-tracker auth |
| 7187 | Merge Search Service | FastAPI + Angular SPA | SSE streaming, dedup, enrichment |
| 7188 | WebUI Bridge | Python | Host process (not containerized) |
| 7189 | boba-jackett | Go/Gin | Jackett management API, encrypted SQLite |
| 9117 | Jackett | LinuxServer image | Indexer API, auto-configured |

---

## Known Issues (open)

1. **BOB-008**: RuTracker CAPTCHA — operator-blocked (needs manual cookie paste)
2. **BOB-015**: Remaining public-tracker failures are external/non-deterministic — low priority
3. **Go backend** is a skeleton (documented in AGENTS.md)
4. **Containers may be down** on session start — `bash start.sh` first
5. **macOS + podman `network_mode: host`** does NOT forward ports — `ensure-macos-tunnel.sh` handles this

---

## Coverage Snapshot (2026-06-09)

| Module | Coverage |
|--------|----------|
| api/__init__.py | 98% |
| api/auth.py | 91% |
| api/routes.py | **95%** |
| api/streaming.py | 99% |
| main.py | 94% |
| deduplicator.py | 94% |
| enricher.py | 100% |
| hooks.py | 95% |
| jackett_autoconfig.py | **99%** |
| scheduler.py | 93% |
| search.py | **80%** |
| validator.py | **92%** |
| **TOTAL** | **60%** |
