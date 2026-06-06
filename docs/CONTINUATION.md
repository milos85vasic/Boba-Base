# Continue — Project Status Snapshot

**Session:** 2026-06-06 (security & cross-platform hardening — backlog burn-down)
**Last commit:** `e45cae7` (working tree CLEAN apart from this file)
**Branch:** `main` — 5 commits ahead of pushed `25ffe5d` (push pending below)
**Uncommitted work:** none · **Unpushed:** the 5 hardening commits + this doc

> Send `continue` to pick up exactly where we left off.
> This file is the single source of truth for session handoff.

---

## This Session — Known-Issue Backlog Burn-down

Tackled the CONTINUATION "Known Issues" backlog (all TDD RED-first):

| # | Issue | Resolution |
|---|-------|-----------|
| 5 | CORS wide open (`*`) | Default localhost allowlist; `*` opt-in warns. `ALLOWED_ORIGINS` override. Compose de-hardcoded. |
| 6 | SSE streams only UUID-gated | Per-search `stream_token` issued + validated; opt-in enforce via `SSE_REQUIRE_TOKEN` (query/​Bearer). Frontend threads token. |
| 7 | Tracker sessions plaintext | `EncryptedSessionStore` Fernet-encrypts `_tracker_sessions` at rest. `SESSION_ENCRYPTION_KEY` pins key. |
| 1 | macOS podman ports not forwarded | `start.sh ensure_macos_tunnel` runs the tunnel on Darwin (best-effort). |
| 3 | `/mnt/DATA` breaks macOS | `default_data_dir()` platform-aware (`$HOME/qbit-data` on macOS). |
| 8 | Coverage barely over floor | helpers.py network paths covered; total 49.32% → **50.73%**. |

Commits (unpushed): `b74f4cf` CORS · `7783070` Fernet+SSE-token ·
`256ec7e` platform · `7d4e64c` coverage · `e45cae7` docs.

**Verification (clean tree this session):** Python unit **1393 passed**
(cov **50.73%**) · mypy clean (19) · ruff clean · go vet/`-race` 13 pkgs ·
pre-build gate 15/15 · guard-hook 27 · bash data-dir 4 · `ng build` OK ·
frontend **328 passed**.

**To push** (§11.4.71 fetch-first, §11.4.113 no force):
`git fetch --all --prune && git push origin main && git push github main && git push upstream main`

---

## Prior Push (2026-06-06, earlier)

```
839304b chore(go): remove unused trackerStatsFromMeta helper (staticcheck U1000)
86f563b test: complete full-stack test/type/lint sweep + fix PreToolUse hook schema
25ffe5d docs(continuation): refresh handoff snapshot to committed state
```

Pushed to all remotes as a clean fast-forward `c4a2def..25ffe5d`.

---

## What We Did (this session, now committed)

| Area | Work Done |
|------|-----------|
| **/doctor hook fix** | `.claude/settings.json` `PreToolUse` was a bare string (schema-invalid, silently ignored) — wrapped in matcher-array form so the §11.4.109 guard hook actually runs. Validated by pre-build gate [11]. |
| **Python test fixes** | Fixed 100+ mypy errors (19 source files, `Success: no issues found`). Fixed 22 ruff errors. Coverage 44% → 49.32% (above 49% threshold). Added tests: validator, theme_state, hooks, scheduler, env_loader, novaprinter, helpers, auth_models, log_filter |
| **Go backend** | Removed dead `trackerStatsFromMeta` (`staticcheck` U1000, isolated commit per §11.4.124). `go vet` clean. All 13 packages pass with `-race` |
| **Frontend** | Fixed 143→0 failures with `@analogjs/vite-plugin-angular`. 29 files, 326 tests pass |
| **Stress/security/chaos** | `tests/fixtures/health.py` skipif marker (probes `localhost:7187/healthz`). Security 50 pass/34 skip; stress 6 skip; chaos skip; memory 6/6 |
| **Infrastructure** | `scripts/ensure-macos-tunnel.sh` (SSH tunnel for podman macOS host ports) |

### Verification (re-confirmed green this session, clean tree)

```
Python unit:     1358 passed  (0 failed, exit 0)
Go tests:        13 packages  (all pass, -race, GOMAXPROCS=2)
ruff:            0 issues
go vet:          0 issues
staticcheck:     0 issues  (per prior run)
Pre-build gate:  15/15 passed
```

> Note: integration/e2e/security/stress/chaos suites require the 4
> containers + macOS tunnel running (see Known Issues). They were NOT
> re-run this session — only the container-independent suites above.

---

## Known Issues (honest, not swept)

### 1. macOS + podman `network_mode: host` does NOT forward ports — ✅ RESOLVED (this session)
`scripts/ensure-macos-tunnel.sh` is now wired into `start.sh` via
`ensure_macos_tunnel` (Darwin-only, best-effort, no-op on Linux). Still a
tunnel (the underlying podman-on-macOS limitation is unchanged) and needs a
re-run if the podman machine reboots, but it's automatic on `./start.sh`.

### 2. Containers may be down on session start
4 containers need to be running for full integration/e2e/security/stress/chaos tests. They may be stopped between sessions. Run:
```bash
export QBITTORRENT_DATA_DIR="$HOME/qbit-data"
mkdir -p "$QBITTORRENT_DATA_DIR"
podman compose up -d
scripts/ensure-macos-tunnel.sh
```

### 3. `/mnt/DATA` doesn't exist on macOS — ✅ RESOLVED (this session)
`start.sh default_data_dir()` is platform-aware: `/mnt/DATA` on Linux,
`$HOME/qbit-data` on macOS. Explicit `QBITTORRENT_DATA_DIR` still overrides.
(`docker-compose.yml` still defaults `/mnt/DATA` for direct `compose` use —
set `QBITTORRENT_DATA_DIR` or start via `./start.sh`.)

### 4. Go backend is a skeleton
`AGENTS.md` documents this honestly. It replicates the API surface and proxies to qBittorrent's built-in search API but **lacks**: plugin subsystem, deduplication, enrichment, private-tracker auth, real download proxying, scheduled execution. Python is the real backend.

### 5. CORS is wide open (`allow_origins=["*"]`) — ✅ RESOLVED (this session)
Default is now a localhost allowlist; `ALLOWED_ORIGINS` overrides; explicit
`*` opt-in logs a warning. See `api/__init__.py` + `test_cors_config.py`.

### 6. SSE streams unprotected (only UUID barrier) — ✅ RESOLVED (this session)
Per-search `stream_token` issued in the search response and validated by the
stream endpoint when `SSE_REQUIRE_TOKEN` is enabled (via `?token=` or
`Authorization: Bearer`). Frontend threads the token automatically.
Enforcement defaults OFF (non-breaking) — flip the env var to harden.

### 7. Tracker sessions in plaintext in-memory — ✅ RESOLVED (this session)
`EncryptedSessionStore` (`merge_service/search.py`) Fernet-encrypts
`_tracker_sessions` at rest. `SESSION_ENCRYPTION_KEY` pins the key.

### 8. Coverage 49.32% — barely over threshold — ✅ IMPROVED (this session)
Now **50.73%** (gate 49%). `plugins/helpers.py` network paths covered.
Remaining low: other `plugins/` source files, some `search.py` error paths.

### 9. Private-tracker tests skip without credentials
34 security tests skip without valid `.env` credentials (IPTorrents, NNMClub, etc.). Those code paths are untested in this environment.

### 10. Frontend coverage unenforced
`AGENTS.md` mentions 40% frontend coverage threshold but no enforcement pipeline exists.

### 11. No CI/CD (by design — Hard Stop rule)
No `.github/workflows/`, no automated pipelines. All verification is manual via `./ci.sh`. Zero regression safety net between manual runs.

### 12. `ruff` and `staticcheck` had issues we fixed
- `SIM300` Yoda condition in `test_hooks_coverage.py` → fixed
- `ASYNC230` blocking `open` in `test_scheduler_coverage.py` → fixed
- `U1000` unused `trackerStatsFromMeta` in Go → removed

These should not reappear, but the fact that lint/static-analysis issues existed means gaps were present before this session.

---

## Uncommitted Changes

None — all session work is committed in `839304b` + `86f563b` (see
"Unpushed Commits" at the top). The only step remaining is pushing those
two commits to `origin/main`, which is held for operator confirmation.

Pre-commit scans run this session (all clean): mutation-marker residue
(§11.4.84), debug prints in source, secrets (§11.4.10).

---

## Quick-Start for Next Session

```bash
# 1. Start infra
export QBITTORRENT_DATA_DIR="$HOME/qbit-data"
mkdir -p "$QBITTORRENT_DATA_DIR"
podman compose up -d
scripts/ensure-macos-tunnel.sh

# 2. Activate virtualenv
source /tmp/boba-venv/bin/activate

# 3. Verify
podman ps
curl -s http://localhost:7187/ | head -1
curl -s http://localhost:7189/healthz
cd frontend && npx vitest run

# 4. Full validation
./ci.sh
```

---

## Quick Reference — Key Commands

```bash
# Tests
./ci.sh                              # Full local CI
./ci.sh --quick                      # Syntax + unit only
python3.14 -m pytest tests/unit/ -q --import-mode=importlib

# Lint
ruff check .
ruff check --fix .
mypy download-proxy/src/

# Go
cd qBitTorrent-go && go test -race -count=1 ./...
cd qBitTorrent-go && go vet ./...
cd qBitTorrent-go && staticcheck ./...

# Frontend
cd frontend && npx vitest run

# Coverage
python3.14 -m pytest tests/unit/ --cov=download-proxy/src --cov=plugins --cov-report=term --import-mode=importlib

# Challenges
bash scripts/pre_build_verification.sh
FULL_VALIDATION=1 bash scripts/pre_build_verification.sh
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

Two-container compose `network_mode: host` (Python proxy + qBittorrent + Jackett + boba-jackett). Go backend opt-in via `--profile go`.
