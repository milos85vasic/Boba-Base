# Continue — Project Status Snapshot

**Session:** 2026-06-09 (Session 8 — parallel plugin testing waves 1+2)
**Last commit:** `a4eb041` (wave 1 pushed; wave 2 uncommitted)
**Branch:** `main` — pushed to all upstreams
**Workable-item tracking:** LIVE at [`Issues.md`](Issues.md) / [`Fixed.md`](Fixed.md) with prefix **BOB**, backed by SQLite DB at `docs/workable_items.db`.

> Send `continue` to pick up exactly where we left off.
> This file is the single source of truth for session handoff.

---

## What We Did (Session 8)

| Area | Work Done |
|------|-----------|
| **Parallel plugin tests** | 5 subagents launched in parallel: eztv (54), piratebay (38), solidtorrents (37), limetorrents (52), torlock (55). Total: 236 new tests, all passing. |
| **gamestorrents B-substring fix** | Fixed `_parse_size` dict ordering (BOB-024). Tests updated to assert correct values. |
| **Bugs discovered** | piratebay `import os` after use (UnboundLocalError), torlock `search()` no exception handling. Both documented with regression tests. |
| **Full suite** | 2433 passed, 0 failed, 3 warnings (+237 from previous 2196). |

### Verification (green tree)

```
Unit tests:      2684 passed, 1 failed (pre-existing flake), 3 warnings (was 2196)
New tests:       +489 (wave 1: 237 + wave 2: 252)
Total coverage:  ~75% (gate: 49%)
Ruff:            All checks passed
Mypy:            8 pre-existing errors (Levenshtein stub missing)
```

### Commits

```
TBD test: wave 2 — nyaa/kickass/anilibra/torrentgalaxy+yts deep tests, kickass guards
a4eb041 test: parallel plugin tests + gamestorrents B-substring fix
eaa6890 test: gamestorrents/iptorrents deep coverage, challenge scripts, constitution docs
20da6dd test: search.py ~90%, download_proxy deep coverage, private tracker HTML fixtures, env_loader fix
173bc94 docs: update CONTINUATION.md for Session 6 (constitution Rev 23)
aa46f07 chore: update constitution submodule to latest upstream (Rev 23, §11.4.132-§11.4.141)
ac226e0 feat: search.py 84%, plugin coverage (theme_injector/env_loader/download_proxy), BOB-015 JSON guards
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
3. **BOB-021**: env_loader flaky test — pre-existing ordering flake, passes in isolation
4. **BOB-022**: iptorrents alt env vars flaky test — pre-existing ordering flake, passes in isolation
5. **Go backend** is a skeleton (documented in AGENTS.md)
6. **Containers may be down** on session start — `bash start.sh` first
7. **macOS + podman `network_mode: host`** does NOT forward ports — `ensure-macos-tunnel.sh` handles this

---

## Coverage Snapshot (2026-06-09 Session 8)

| Module | Coverage | Change |
|--------|----------|--------|
| api/__init__.py | 98% | — |
| api/auth.py | 91% | — |
| api/routes.py | **95%** | — |
| api/streaming.py | 99% | — |
| main.py | 94% | — |
| deduplicator.py | 94% | — |
| enricher.py | 100% | — |
| hooks.py | 95% | — |
| jackett_autoconfig.py | **99%** | — |
| scheduler.py | 93% | — |
| search.py | **~90%** | — |
| validator.py | **92%** | — |
| theme_injector.py | **99%** | — |
| env_loader.py | **100%** | — |
| download_proxy.py | **~55%+** | — |
| iptorrents.py | **~15%→improved** | +new tests |
| gamestorrents.py | **18%→improved** | +new tests |
| **TOTAL** | **~69%** | +1% |
