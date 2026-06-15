# Recording readiness inventory — Boba client surfaces + HelixAgent ensemble + per-surface recording plan

**Revision:** 1
**Last modified:** 2026-06-15T00:00:00Z
**Scope:** Feasibility for §11.4.153/.154/.155 video-recording confirmation of ALL Boba client apps,
driven by the HelixAgent ensemble, saved to `/Volumes/T7/Downloads/Recordings` with a `boba---` prefix.
Anti-bluff (§11.4.6): EXISTS/ABSENT claims below carry path evidence; unknowns are marked UNCONFIRMED.

---

## 1. Client-surface inventory (EXISTS / DOES-NOT-EXIST, with evidence)

| Surface | Status | Evidence / path | Notes |
|---|---|---|---|
| **Web — Angular dashboard** | **EXISTS** | `frontend/` (`angular.json`, `frontend/package.json` name=`frontend`, `frontend/playwright.config.ts`, `frontend/e2e/`) | Angular 21 SPA. Playwright already configured for e2e → ideal recording driver. Routes incl. `/jackett`. |
| **Web — FastAPI Jinja2 dashboard (:7187)** | **EXISTS** | merge service dashboard at `http://localhost:7187/` (CLAUDE.md port map; served by `download-proxy/src/api/`) | Server-rendered HTML dashboard, separate from the Angular SPA. Browser-recordable. |
| **CLI — `boba-ctl`** | **EXISTS (CLI, not TUI)** | `cmd/boba-ctl/main.go` (built binary `cmd/boba-ctl/boba-ctl`), wrapper `scripts/boba-ctl.sh` | Subcommand CLI: `up/down/status/health/list`. **NO TUI** — no bubbletea/tview/textual dep in `cmd/boba-ctl/go.mod`. The operator's "boba-ctl TUI?" → it is a plain CLI. Record via terminal capture. |
| **Shell-script CLIs** | **EXISTS** | `start.sh`, `stop.sh`, `setup.sh`, `test.sh`, `ci.sh`, `install-plugin.sh`, `webui-bridge.py` | Operator-facing command surfaces; terminal-recordable. |
| **Browser extension — BobaLink** | **EXISTS** | `extension/` (WXT/Manifest V3, `extension/wxt.config.ts` name "BobaLink (Boba Project browser extension)", `extension/playwright.config.ts`, `extension/tests/`) | MV3 extension, popup/background. Scoped to merge service `localhost:7187`. Record popup + content via Playwright-with-extension / chrome-devtools. |
| **TUI (dedicated terminal UI app)** | **DOES-NOT-EXIST** | grep for bubbletea/tview/textual/blessed → no Boba hit (only test files / a course demo.sh) | No TUI surface. If the operator wants a "TUI", boba-ctl CLI is the closest existing surface. |
| **Mobile app (iOS/Android/Flutter)** | **DOES-NOT-EXIST** | no `*.swift` / `*.kt` / `*.dart` / `Info.plist` in repo (excluding submodules/node_modules) | No mobile surface to record. |
| **Desktop native (Electron/Tauri)** | **DOES-NOT-EXIST** | no `electron`/`tauri` dep in `frontend/package.json` or `extension/package.json` | The "desktop" surface is the web dashboard in a browser, not a native app. |

**Bottom line:** 4 real recordable client surfaces — (1) Angular web `frontend/`, (2) FastAPI Jinja2
dashboard :7187, (3) `boba-ctl` CLI + shell scripts, (4) BobaLink browser extension. **No** TUI, **no**
mobile, **no** desktop-native app. Do NOT produce recordings for apps that don't exist (§11.4.6).

---

## 2. HelixAgent ensemble location — THE KEY BLOCKER

The operator wants recordings "driven by the helix agent ensemble obtained from the helix agent Submodule".

**Finding (FACT, with evidence):**
- The ensemble IS present on the host at **`/Volumes/T7/Projects/helix_code/submodules/helix_agent`**
  (EXISTS — verified). It is **HelixAgent: AI-Powered Ensemble LLM Service** (its `README.md` H1), a Go
  service with entrypoints `bin/helixagent`, `cmd/api`, `cmd/grpc-server`, `cmd/mcp-bridge`,
  `cmd/helixagent`. Catalogue: `vasic-digital/HelixAgent` + `HelixDevelopment/HelixAgent` ("LLMs Agent").
- Its containers ARE running: `helixagent-postgres`, `helixagent-redis`, `helixagent-chromadb`,
  `helixagent-cognee` (compose project `helix_agent`, config
  `/Volumes/T7/Projects/helix_code/submodules/helix_agent/docker-compose.yml`), plus `helix_ollama_video`
  (an Ollama instance, 6h uptime — plausibly the vision/video-analysis model host, UNCONFIRMED which
  model it serves).
- **BLOCKER 1:** the ensemble is owned by **`helix_code`, NOT by Boba**. It is NOT in Boba's `.gitmodules`
  (Boba's submodules are only: constitution, jackett, helixqa, challenges, containers). To use it per the
  constitution it must be incorporated into Boba per §11.4.74 (catalogue-first) + §11.4.36
  (install_upstreams on add) — OR consumed as a running service via its API/gRPC/MCP endpoints without a
  submodule. The operator's phrase "obtained from the helix agent Submodule" implies incorporation;
  that decision is operator-gated.
- **BLOCKER 2 (interface UNCONFIRMED):** how exactly the ensemble ingests a VIDEO file and returns a
  per-feature analysis verdict is not yet verified. `helix_ollama_video` suggests a vision pipeline
  exists, but the concrete "analyse this mp4 → JSON verdict" entrypoint (API route / CLI flag / MCP tool)
  was NOT confirmed in this pass. The main agent must verify the ensemble's video-analysis API before
  the §11.4.153 (4) remediation loop can be wired.

**docs_chain (the §11.4.153 (5) sync engine) — secondary blocker:**
- `docs_chain` EXISTS at `/Volumes/T7/Projects/docs_chain` AND `/Volumes/T7/Projects/helix_code/submodules/docs_chain`,
  but is **NOT a Boba submodule** (absent from Boba `.gitmodules`). §11.4.106 requires consuming it by
  reference; Boba must wire it (register `.docs_chain/contexts/*.yaml`) before the always-in-sync clause holds.

---

## 3. Recording-corpus state + project-name prefix

- Recording path `/Volumes/T7/Downloads/Recordings` **EXISTS**. It currently holds **`helixcode-*`**
  files (mp4/png/.cast) — another project's recordings. **No `boba-*` / `boba---*` recordings yet.**
- **Prefix to use = `boba`** (§11.4.155 resolution): `HELIX_RELEASE_PREFIX` is **NOT set** in Boba's
  `.env` or `.env.example` → fallback to lowercased snake_case repo-dir name → repo dir is lowercase
  **`boba`**. Canonical filename form: **`boba---<surface-or-feature>---<run-id>.<ext>`** (triple-hyphen
  separator per §11.4.155). Recommend setting `HELIX_RELEASE_PREFIX=boba` in `.env` explicitly so the
  prefix is authoritative and matches §11.4.151 release-tag prefix.
- §11.4.154 fresh-corpus rotation applies only to Boba's OWN prior `boba---*` recordings — the existing
  `helixcode-*` files are FOREIGN and MUST NOT be deleted (§11.4.122 + §9.2).

---

## 4. Per-surface recording recommendation

| Surface | Recommended capture mechanism | Window-scoped (§11.4.154) | Notes |
|---|---|---|---|
| Angular web `frontend/` | **Playwright** (already configured: `frontend/playwright.config.ts`) with `video: 'on'` / `recordVideo`, OR chrome-devtools-mcp `performance_start_trace` + screen-record of the tab | Yes — Playwright records the page viewport only, not the desktop | Strongest path; e2e specs already exist in `frontend/e2e/`. |
| FastAPI Jinja2 dashboard :7187 | Playwright / chrome-devtools-mcp against `http://localhost:7187/` | Yes — browser viewport | Needs containers up (`boba-ctl up` / `start.sh`). |
| BobaLink extension | Playwright with the unpacked extension loaded (`.output/`) → record popup + content-script interaction; or chrome-devtools-mcp | Yes — browser/popup window | `extension/playwright.config.ts` + `extension/tests/` already exist. |
| `boba-ctl` CLI + shell scripts | **asciinema** (`asciinema rec`) → convert to mp4 via `agg`/`ffmpeg`; or `script` + `ffmpeg`. (Existing `helixcode-cli-*.cast` files show asciinema is already the host's CLI-recording tool.) | Yes — record the terminal pane only (tmux target / window id), NOT the whole desktop | Window-scope = single terminal window; do NOT `ffmpeg -f avfoundation` whole-screen. |

All four are window/surface-scoped by construction (Playwright = viewport, asciinema = terminal pane),
so §11.4.154 is naturally satisfied — provided the asciinema→mp4 step captures only the terminal, and
no whole-screen `avfoundation` fallback is used.

---

## 5. What the main agent must resolve with the operator (blockers)

1. **Incorporate HelixAgent ensemble + docs_chain into Boba** (per §11.4.74 + §11.4.36 + §11.4.106) — or
   confirm "consume as running service via API/gRPC/MCP, no submodule". Operator-gated decision.
2. **Confirm the ensemble's video-analysis interface** (the mp4 → verdict entrypoint) before wiring the
   §11.4.153 (4) loop — UNCONFIRMED in this pass.
3. **Confirm `helix_ollama_video` is the intended vision model host** for video analysis — UNCONFIRMED.
4. **Decide PART 1 path** (Option A project-instantiation vs Option B §11.4.153 refinement) — the rule
   already exists; a new §11.4.156 would duplicate §11.4.153/.154/.155.
