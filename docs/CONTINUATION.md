# Continue — Project Status Snapshot

**Session:** 2026-06-09 (Session 6 — constitution submodule Rev 23, §11.4.132-§11.4.141)
**Last commit:** `aa46f07` (working tree CLEAN)
**Branch:** `main` — pushed to all upstreams
**Workable-item tracking:** LIVE at [`Issues.md`](Issues.md) / [`Fixed.md`](Fixed.md) with prefix **BOB**, backed by SQLite DB at `docs/workable_items.db`.

> Send `continue` to pick up exactly where we left off.
> This file is the single source of truth for session handoff.

---

## What We Did (Session 6)

| Area | Work Done |
|------|-----------|
| **Constitution submodule** | Updated from Rev 22 (§11.4.131) to Rev 23 (§11.4.132-§11.4.141). Key additions: risk-ordered validation (§11.4.132), target-system safety (§11.4.133), code-review iterate-until-GO (§11.4.134), standing regression-guard (§11.4.135), real-content playback-test (§11.4.136), subtitle correctness oracle (§11.4.137), operator-escape bluff-audit (§11.4.138), fresh-process clean-artifact (§11.4.139), action-prefix system (§11.4.140), token-efficiency mandate (§11.4.141). |
| **Action-prefix system** | Universal `ACTION_NAME ::` prompt-prefix system with 4 equivalent forms. Currently registers `BACKGROUND` action. Scripts: `action_prefix_lib.sh`, `action_prefix_expand.sh`, `install_action_prefix.sh`. |
| **Token efficiency** | §11.4.141 mandate to cut token spend 60-70% via: prompt-cache governance prefix, subagent model-tiering (mechanical=Haiku, judgment=strong), thin index + on-demand detail, CodeGraph/retrieval-first, output reduction, tool-call batching. |
| **Subagent tiering** | Registry mapping 7 mechanical classes (code_search, status_probe, doc_export, etc.) to Haiku + 6 judgment classes (verdict, fix_design, code_review, etc.) to strong model. |
| **GEMINI.md** | New agent profile for Gemini CLI added to constitution. |

### Verification (green tree)

```
Unit tests:      1989 passed, 0 failed
Total coverage:  65% (gate: 49%)
Constitution:    Rev 23 (§11.4.132-§11.4.141)
```

### Commits

```
aa46f07 chore: update constitution submodule to latest upstream (Rev 23, §11.4.132-§11.4.141)
ac226e0 feat: search.py 84%, plugin coverage (theme_injector/env_loader/download_proxy), BOB-015 JSON guards
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
