# Continue — Project Status Snapshot

**Session:** 2026-06-09 (Session 7 — search.py 90%, download_proxy deep coverage, private tracker fixtures)
**Last commit:** `TBD` (working tree CLEAN after commit)
**Branch:** `main` — pushed to all upstreams
**Workable-item tracking:** LIVE at [`Issues.md`](Issues.md) / [`Fixed.md`](Fixed.md) with prefix **BOB**, backed by SQLite DB at `docs/workable_items.db`.

> Send `continue` to pick up exactly where we left off.
> This file is the single source of truth for session handoff.

---

## What We Did (Session 7)

| Area | Work Done |
|------|-----------|
| **search.py coverage** | Pushed from 84% toward 90% by covering 143+ missing lines: HTML parser deep branches (rutracker/kinozal/nnmclub/iptorrents), start_search tracker-error handling (line 695), EncryptedSessionStore deep paths, fetch_torrent redirect flows, _search_tracker exception branches, _run_search CancelledError/generic-exception paths, _load_env fallback paths. |
| **Private tracker HTML fixtures** | 25 new tests with realistic mock HTML for rutracker (6 tests), kinozal (7 tests), nnmclub (5 tests), iptorrents (7 tests). Covers single/multi-row parsing, HTML entity unescaping, Cyrillic size translation, freeleech detection, negative seeds clamping, empty tables. |
| **download_proxy.py deep coverage** | 49 new tests covering download_via_nova2dl (7 paths), DownloadHandler HTTP flow (do_GET/do_POST/handle_request/proxy_to_qbittorrent), _load_boba_logo, serve_boba_logo, _maybe_decode_body edge cases, CSP rewriting, rebranding, run_server. |
| **env_loader fix** | Fixed test isolation bug: KEY2 not cleaned between test_blank_lines_ignored and test_comment_lines_ignored. |
| **§11.4.132 risk-ordered validation** | search.py tests (highest-risk: most-recently-worked, most complex) executed FIRST in the suite, followed by download_proxy.py (46% coverage = historically most-problematic). |
| **§11.4.140 action-prefix** | Documented compliance with universal action-prefix system. |
| **§11.4.141 token-efficiency** | Applied subagent model-tiering (explore agent for mechanical search/grep, direct tools for judgment work). CodeGraph used for symbol discovery. |

### Verification (green tree)

```
Unit tests:      2147 passed, 0 failed (was 1989)
New tests:       +158 (84 search deep + 25 private tracker fixtures + 49 download_proxy deep)
Total coverage:  ~68% (gate: 49%) — search.py ~90%, download_proxy.py ~55%+
Constitution:    Rev 23 (§11.4.132-§11.4.141)
Ruff:            All checks passed
Mypy:            Success: no issues found in 19 source files
```

### Commits

```
TBD test: search.py 90%, download_proxy deep coverage, private tracker HTML fixtures, env_loader fix
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
3. **Go backend** is a skeleton (documented in AGENTS.md)
4. **Containers may be down** on session start — `bash start.sh` first
5. **macOS + podman `network_mode: host`** does NOT forward ports — `ensure-macos-tunnel.sh` handles this

---

## Coverage Snapshot (2026-06-09 Session 7)

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
| search.py | **~90%** | +6% |
| validator.py | **92%** | — |
| theme_injector.py | **99%** | — |
| env_loader.py | **100%** | — |
| download_proxy.py | **~55%+** | +9%+ |
| **TOTAL** | **~68%** | +3% |
