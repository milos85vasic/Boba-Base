# CodeGraph — Boba Code-Intelligence Integration

**Revision:** 1
**Last modified:** 2026-06-06T14:40:00Z
**Authority:** Constitution §11.4.78 (CodeGraph mandate) · §11.4.79 (own-org
submodules included, third-party excluded) · §11.4.80 (update/sync automation)
· §11.4.10 (secrets never indexed) · §11.4.77 (regeneration mechanism)

CodeGraph (`@colbymchenry/codegraph`,
<https://github.com/colbymchenry/codegraph>) is a 100%-local SQLite semantic
knowledge graph of this codebase, exposed to AI coding agents over MCP. No
cloud, no external API. It gives agents instant, consistent symbol / caller /
callee / impact resolution instead of repeated shallow file scanning.

---

## Install (§11.4.78)

```bash
npm install -g @colbymchenry/codegraph     # Node 18+, NO sudo (user-writable prefix)
codegraph --version                         # confirm the binary runs (exit 0 ≠ working binary)
```

On this host the binary resolves to `/opt/homebrew/bin/codegraph` (the
npm-managed shim). A standalone-installer shim (`~/.local/bin/codegraph`) must
NOT shadow it — if `codegraph --version` reports an older version than
`npm view @colbymchenry/codegraph version`, a stale shim is winning on `PATH`;
remove it so the npm-managed binary is active.

## Configuration model — zero-config (important)

CodeGraph 0.9.x is **zero-config**: there is **no `.codegraph/config.json`
exclude list**. What gets indexed is decided by:

1. **Built-in defaults** — dependency/build/cache dirs (`node_modules`,
   `vendor`, `dist`, `build`, `target`, `.venv`, `Pods`, …) are skipped even
   with no `.gitignore`, plus any file larger than **1 MB**.
2. **`.gitignore`** — honored directly (root + nested). **To keep something out
   of the index, add it to `.gitignore`.** To pull a default-excluded dir back
   in, add a negation (`!path/`).

(Source: the installed package `README.md` → "Configuration".)

### What is tracked vs ignored

| Path | Git | CodeGraph index | Why |
|---|---|---|---|
| `.codegraph/codegraph.db` (+ `*.db-wal`/`*.db-shm`/`cache/`) | gitignored | n/a | Build artifact; regenerate with `codegraph index` (§11.4.77) |
| `.mcp.json` | tracked | n/a | MCP wiring, committed (§11.4.78) |
| `scripts/codegraph_validate.sh` | tracked | indexed | Anti-bluff validator (§11.4.78 step 4) |
| `docs/codegraph/Status.md` | tracked | n/a | Append-only event ledger (§11.4.80) |

## Exclusions — secrets (§11.4.10) + third-party (§11.4.79)

**Secrets are never indexed.** Root `.gitignore` already excludes `.env`,
`.env.*`, `*.env`, `.qbit.env`, `*secrets*`, `config/qBittorrent/`,
`config/jackett/`, `config/boba.db*`. Because CodeGraph honors `.gitignore`,
none of these reach the index. Audited: 0 real secret paths in the index.

**Third-party submodule excluded.** `submodules/jackett` (upstream
`Jackett/Jackett`, C#/.NET) is third-party — §11.4.79 requires it OUT of the
index. CodeGraph 0.9.9 does index C#, so an explicit `.gitignore` entry
`submodules/jackett/` was added. This is **inert for git** (the submodule is a
tracked gitlink via `.gitmodules`; an ignore entry on a tracked path does not
un-track it) but tells CodeGraph to skip it. Audited: 0 `submodules/jackett`
paths in the index (down from 890 before the exclusion).

**Own-org submodule INCLUDED.** `constitution/` (HelixDevelopment, own-org per
§11.4.79) is deliberately NOT ignored, so its Go `workable-items` sources are
indexed and resolve cross-submodule (e.g. `versionTagsCmd`).

## Index / re-generate

```bash
codegraph index .          # full (re)index — the §11.4.77 regeneration mechanism
codegraph index . --force  # force a clean re-index
codegraph sync .           # incremental update since last index
codegraph status .         # files / nodes / edges
```

Current index: **509 files, 8906 nodes, 17025 edges** (go, python, typescript,
properties, xml, yaml).

## MCP wiring (Claude Code, project-scoped + committed)

`.mcp.json` at the repo root registers the CodeGraph MCP server over **stdio**:

```json
{
  "mcpServers": {
    "codegraph": { "command": "codegraph", "args": ["serve", "--mcp"], "env": {} }
  }
}
```

`serve --mcp` is the stdio transport; the command is the bare `codegraph` on
`PATH` (no hardcoded host path, per §11.4.78). It exposes 8 tools:
`codegraph_search`, `codegraph_callers`, `codegraph_callees`,
`codegraph_impact`, `codegraph_node`, `codegraph_explore`, `codegraph_status`,
`codegraph_files`.

Other agents: register the same `codegraph serve --mcp` stdio server via that
agent's MCP config (Cursor, opencode `opencode.json`, Qwen `.qwen/settings.json`,
Codex, etc.) — `codegraph install` automates this for supported agents.

## Anti-bluff verification (§11.4.78 step 4)

```bash
bash scripts/codegraph_validate.sh         # 7 checks; exit 0 = all PASS
```

The validator proves the index is real and correctly scoped — six checks plus
an **unforgeable MCP challenge**: it drives the real `codegraph serve --mcp`
server and asserts the `codegraph_status` node count returned over MCP equals
the CLI node count. An agent answering from its own file-reading tools cannot
fabricate that number. The other checks assert: index reality (nodes > 0),
own-code symbol resolution, own-org `constitution/` symbol resolution
(§11.4.79 included), and zero `submodules/jackett` / zero secret paths in the
index (§11.4.79 + §11.4.10 excluded). The path-audit detection logic is
falsifiability-rehearsed (a synthetic leaked path is detected) so the green
PASS is not a tautology.

## Update + sync automation + cadence (§11.4.80)

Scripts are **inherited by reference** from the constitution submodule — never
copied:

```bash
bash constitution/scripts/codegraph_update.sh      # npm-update to latest + §107 version check
bash constitution/scripts/codegraph_sync.sh .      # status → sync → status → validate, logged
```

`codegraph_sync.sh` appends every run to BOTH this project's
`docs/codegraph/Status.md` and the constitution's own ledger. **Cadence:**
weekly floor (§11.4.45 status-digest cadence); may run more often.

## Troubleshooting

- **`codegraph` reports an old version after npm update** — a stale standalone
  shim on `PATH` (commonly `~/.local/bin/codegraph`) is shadowing the
  npm-managed binary. Remove the stale shim.
- **A path you expect is missing from the index** — check it isn't `.gitignore`d,
  default-excluded (`node_modules`/`dist`/…), > 1 MB, or an unsupported language.
- **Third-party code appears in the index** — add its path to `.gitignore`
  (per the zero-config exclude model) and `codegraph index . --force`.
