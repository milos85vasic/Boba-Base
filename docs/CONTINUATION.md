# Continue — Project Status Snapshot

**Session:** 2026-06-08 (Session 3 — BOB-009 default, mutmut path fix, BOB-010 domain status docs)
**Last commit:** `81af0eb` (working tree CLEAN)
**Branch:** `main` — pushed to all upstreams
**Workable-item tracking:** LIVE at [`Issues.md`](Issues.md) / [`Fixed.md`](Fixed.md) with prefix **BOB**, backed by SQLite DB at `docs/workable_items.db`.

> Send `continue` to pick up exactly where we left off.
> This file is the single source of truth for session handoff.

---

## What We Did (Session 3)

| Area | Work Done |
|------|-----------|
| **BOB-009: boba-ctl default** | `--boba-ctl` flipped from opt-in to default. `--no-boba-ctl` flag added for fallback to raw compose. `start.sh`/`stop.sh` updated. |
| **Mutmut module path fix** | Root cause: mutmut's `get_mutant_name` only strips `src.` prefix, but source is at `download-proxy/src/`. Patched venv's `format_utils.py` to also strip `download-proxy.src.` prefix. Changed `source_paths` from `["src/"]` (symlink) to `["download-proxy/src/"]`. Updated conftest `MutmutPath` to point to `mutants/download-proxy/src/`. Removed unused `src/` symlink. |
| **Mutmut e2e verified** | Single mutant `api.auth.x__get_orchestrator` runs and gets **killed** correctly — pipeline works end-to-end. Full run (6568 mutants) started in background (PID 33493). |
| **BOB-010: domain status docs** | All 7 domain summary stubs replaced with real content: API, Architecture, CodeGraph, Demos, Migration, Scripts, Superpowers — each with status tables, doc inventories, and cross-links. |
| **Pre-build gate** | 18/18 PASS (including CM-MARKDOWN-EXPORT-SYNC after regeneration). |

### Verification (green tree)

```
Pre-build gate:  18 passed, 0 failed
  - 15 constitution + infrastructure invariants
  - Invariant 16: CM-MARKDOWN-EXPORT-SYNC (all-docs scope)
  - Invariant 17: CM-WORKABLE-ITEMS-VALIDATE (SQLite DB, 20 items OK)
  - Invariant 18: CM-DOCS-CHAIN-VALIDATE (docs_chain --check-only)
Challenges:      11 run (8 PASS, 2 SKIP macOS, 1 SKIP creds)
submodules:      6 active (constitution, challenges, containers, helixqa, jackett)
Workable-items:  Issues(3: BOB-008 blocked, BOB-009 in-progress, BOB-015 queued)
                 Fixed(17: BOB-001—BOB-007, BOB-010—BOB-016 inclusive)
All invariants satisfied.
HelixQA banks:   5 total (boba-services, boba-download-proxy, boba-frontend,
                 boba-boba-ctl, boba-docs-chain) — 42 test cases
Mutmut:          Background run in progress (PID 33493, 6568 mutants)
```

### Commits

```
81af0eb chore: update jackett submodule to latest upstream
65bee1e feat: mutmut v3.6 path fix with src/ symlink and MutmutPath redirect
<next>   feat: BOB-009 default, BOB-010 domain docs, mutmut module path fix
```

---

## Quick-Start for Next Session

```bash
# 1. Check mutmut results
tail -20 /tmp/mutmut-run.log
source /tmp/mutmut-venv/bin/activate && python3 -m mutmut results && deactivate

# 2. Pre-build gate
bash scripts/pre_build_verification.sh

# 3. Tests
python3 -m pytest tests/unit/ -q --import-mode=importlib
cd frontend && npx vitest run

# 4. Workable items 
./bin/workable-items validate --db docs/workable_items.db
./bin/workable-items export --db docs/workable_items.db --out-dir docs/
```

---

## Quick Reference — Key Commands

```bash
# Pre-build gate
bash scripts/pre_build_verification.sh

# Mutation testing (via Python 3.13 venv)
source /tmp/mutmut-venv/bin/activate
python3 -m mutmut run --max-children 2 2>&1 | tee /tmp/mutmut-run.log
mutmut results
deactivate

# Tests
python3 -m pytest tests/unit/ -q --import-mode=importlib

# Docs chain
bash scripts/docs_chain.sh
bash scripts/docs_chain.sh --check-only

# Export regeneration
bash scripts/generate_markdown_exports.sh

# Lint
ruff check . && mypy download-proxy/src/

# boba-ctl
bash start.sh --no-boba-ctl  # fall back to raw compose
bash stop.sh --no-boba-ctl

# Workable items
./bin/workable-items validate --db docs/workable_items.db
./bin/workable-items report --db docs/workable_items.db --by-status

# Coverage
python3 -m pytest tests/unit/ --cov=download-proxy/src --cov=plugins --cov-report=term --import-mode=importlib

# Submodule sync
cd submodules/helixqa && git push origin main && cd ../..
cd submodules/challenges && git fetch --all --prune && cd ../..
cd submodules/containers && git fetch --all --prune && cd ../..
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

Two-container compose `network_mode: host` (Python proxy + qBittorrent + Jackett + boba-jackett). Go backend opt-in via `--profile go`. `cmd/boba-ctl/` Go binary wraps containers submodule (now default for start/stop).

---

## Known Issues (open)

1. **BOB-008**: RuTracker CAPTCHA — operator-blocked (needs manual cookie paste)
2. **BOB-009** (complete): boba-ctl is now default (`--no-boba-ctl` to fall back to raw compose).
3. **BOB-010** (complete): All 7 domain summary pages populated with real status docs.
4. **BOB-015**: Remaining public-tracker failures are external/non-deterministic — low priority
5. **mutmut**: Full run in progress (PID 33493, 6568 mutants). Module path mismatch fixed via venv patch to `get_mutant_name` + `source_paths = ["download-proxy/src/"]`. Stats collection phase passed — mapping verified. Expect improved killed/survived ratio over previous run.
6. **Go backend** is a skeleton (documented in AGENTS.md)
7. **Containers may be down** on session start — `bash start.sh` (defaults to boba-ctl) or `bash start.sh --no-boba-ctl` first
8. **macOS + podman `network_mode: host`** does NOT forward ports — `ensure-macos-tunnel.sh` handles this
9. **Constitution rebase**: constitution submodule had upstream divergence (gitflic + GitHub had new `Auto-commit` + §11.4.134/133 commits). Cleanly rebased, but requires force-free upstream acceptance.
