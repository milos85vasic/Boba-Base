# Continue — Project Status Snapshot

**Session:** 2026-06-09 (Session 5 — search.py 84%, plugin coverage, BOB-015 fixes)
**Last commit:** `HEAD` (working tree CLEAN)
**Branch:** `main` — pushed to all upstreams
**Workable-item tracking:** LIVE at [`Issues.md`](Issues.md) / [`Fixed.md`](Fixed.md) with prefix **BOB**, backed by SQLite DB at `docs/workable_items.db`.

> Send `continue` to pick up exactly where we left off.
> This file is the single source of truth for session handoff.

---

## What We Did (Session 5)

| Area | Work Done |
|------|-----------|
| **search.py coverage** | 80% → 84% (+4%). Added 44 tests: size-based quality fallback, cancel_search, no-creds early returns, deadline ValueError fallback, HTML parser malformed-result guards, EncryptedSessionStore iter, load_env fallback. |
| **Plugin coverage** | theme_injector 0%→99%, env_loader 0%→100%, download_proxy 36%→46%. 136 new tests across 3 plugin test files. |
| **BOB-015 fixes** | yts.py + piratebay.py JSON decode guards (empty/invalid JSON no longer crashes). Verified kickass, eztv, nyaa, limetorrents handle empty HTML gracefully. |
| **Submodules synced** | constitution + helixqa pulled from upstream, all repos pushed |

### Verification (green tree)

```
Unit tests:      1989 passed, 0 failed
Total coverage:  65% (gate: 49%)
search.py:       84%
theme_injector:  99%
env_loader:      100%
```

### Commits

```
HEAD  feat: search.py 84%, plugin coverage (theme_injector/env_loader/download_proxy), BOB-015 JSON guards
6953662 chore: update helixqa submodule to latest upstream
995986c chore: update constitution submodule to latest upstream
d2b14ed test: routes.py 95%, search.py 80%, validator 92%, jackett_autoconfig 99%
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
| search.py | **84%** |
| validator.py | **92%** |
| theme_injector.py | **99%** |
| env_loader.py | **100%** |
| **TOTAL** | **65%** |
