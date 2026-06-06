# Continue — Project Status Snapshot

**Session:** 2026-06-06 (full-stack completion sweep — committed & pushed)
**Last commit:** `25ffe5d` (working tree CLEAN)
**Branch:** `main` — in sync with origin/github/upstream (all at `25ffe5d`)
**Uncommitted work:** none · **Unpushed:** none

> Send `continue` to pick up exactly where we left off.
> This file is the single source of truth for session handoff.

---

## Last Push (2026-06-06)

```
839304b chore(go): remove unused trackerStatsFromMeta helper (staticcheck U1000)
86f563b test: complete full-stack test/type/lint sweep + fix PreToolUse hook schema
25ffe5d docs(continuation): refresh handoff snapshot to committed state
```

Pushed to all remotes as a clean fast-forward `c4a2def..25ffe5d` (no
force — §11.4.113). `origin`, `github`, `upstream` all resolve to the
canonical repo (`qBitTorrent.git` redirects to `Boba-Base.git`) and are
all at `25ffe5d`. §11.4.71 fetch-before-push: no divergence found.

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

### 1. macOS + podman `network_mode: host` does NOT forward ports
On macOS, podman runs containers inside a Linux VM. `network_mode: host` makes ports reachable *inside* the VM but NOT on the macOS host `localhost`. The SSH tunnel (`scripts/ensure-macos-tunnel.sh`) bridges this but is:
- Not wired into `start.sh`
- Untested (just created this session)
- Temporary fix — manual restart if podman machine reboots

**Workaround used:** `ssh -L 7186:127.0.0.1:7186 -L 7187:127.0.0.1:7187 -L 7189:127.0.0.1:7189 -L 9117:127.0.0.1:9117 ...` to the podman machine VM.

### 2. Containers may be down on session start
4 containers need to be running for full integration/e2e/security/stress/chaos tests. They may be stopped between sessions. Run:
```bash
export QBITTORRENT_DATA_DIR="$HOME/qbit-data"
mkdir -p "$QBITTORRENT_DATA_DIR"
podman compose up -d
scripts/ensure-macos-tunnel.sh
```

### 3. `/mnt/DATA` doesn't exist on macOS
`docker-compose.yml` hardcodes `/mnt/DATA` as `QBITTORRENT_DATA_DIR` default. macOS workaround: `export QBITTORRENT_DATA_DIR="$HOME/qbit-data"`. This isn't persisted anywhere — must be set each session.

### 4. Go backend is a skeleton
`AGENTS.md` documents this honestly. It replicates the API surface and proxies to qBittorrent's built-in search API but **lacks**: plugin subsystem, deduplication, enrichment, private-tracker auth, real download proxying, scheduled execution. Python is the real backend.

### 5. CORS is wide open (`allow_origins=["*"]`)
Phase 3 plans to tighten to `ALLOWED_ORIGINS` env var. Not done.

### 6. SSE streams unprotected (only UUID barrier)
Phase 3 plans per-client bearer tokens. Not done.

### 7. Tracker sessions in plaintext in-memory
Phase 2.3 plans Fernet-at-rest encryption. Not done.

### 8. Coverage 49.32% — barely over threshold
Weak areas: `plugins/helpers.py` (36%), `plugins/` source files, many error paths in `search.py` (77%). Coverage gate is 49% in `pyproject.toml`.

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
