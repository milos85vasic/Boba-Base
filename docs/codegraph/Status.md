# CodeGraph Status — Boba

**Revision:** 1
**Last modified:** 2026-06-06T14:40:00Z
**Authority:** Constitution §11.4.78 / §11.4.79 / §11.4.80
**Scope:** Append-only ledger of CodeGraph install / update / sync / validate
events for the Boba project. Newest entries appended at the bottom by
`constitution/scripts/codegraph_sync.sh`.

---

## 2026-06-06T14:30:00Z — initial setup + update + re-index (§11.4.78/§11.4.79/§11.4.80)

- **Install / update:** host already had CodeGraph via the standalone installer
  (`~/.codegraph/versions/v0.9.7`, shim at `~/.local/bin/codegraph`). The npm
  package (`@colbymchenry/codegraph`, §11.4.78) latest was `0.9.9`.
  `constitution/scripts/codegraph_update.sh` installed `0.9.9` via
  `npm install -g` (no sudo; user-writable prefix `/opt/homebrew`) and the
  §107 anti-bluff check caught that the stale `~/.local/bin` shim still won on
  PATH. Removed the stale standalone shim → `codegraph` on PATH is now the
  npm-managed `0.9.9` at `/opt/homebrew/bin/codegraph`.
- **Config model:** CodeGraph 0.9.9 is **zero-config** — there is NO
  `.codegraph/config.json` exclude list. Exclusion is driven by `.gitignore`
  + built-in defaults (`node_modules`/`vendor`/`dist`/… + files > 1 MB).
  Source: the installed package `README.md` "Configuration" section.
- **Exclusions (§11.4.10 + §11.4.79):** secrets are already covered by root
  `.gitignore` (`.env*`, `*secrets*`, `config/qBittorrent/`, `config/jackett/`,
  `config/boba.db`). Added `submodules/jackett/` to root `.gitignore` to keep
  the third-party Jackett (C#/.NET) submodule OUT of the index — inert for git
  (jackett is a tracked gitlink) but honored by CodeGraph. Added
  `.codegraph/codegraph.db` (+ WAL/SHM/cache) to root `.gitignore`;
  regeneration mechanism (§11.4.77) is `codegraph index`.
- **Re-index:** `codegraph index . --force` on `0.9.9`.
- **Index result:** 509 files, 8906 nodes, 17025 edges. Languages: go,
  python, typescript, properties, xml, yaml.
- **Audit:** `submodules/jackett` = 0 indexed (§11.4.79 ✓); real secret paths
  = 0 indexed (§11.4.10 ✓); `constitution/` own-org = 19 files indexed,
  cross-submodule symbol `versionTagsCmd` resolves (§11.4.79 ✓).
- **MCP wiring:** `.mcp.json` registers `codegraph serve --mcp` (stdio, bare
  command on PATH). Verified the server boots and `codegraph_status` returns
  the live node count (8906) over MCP — the §11.4.78 step-4 unforgeable fact.
- **Validate:** `scripts/codegraph_validate.sh` → 7 PASS / 0 FAIL.

## 2026-06-06T14:38:30Z — codegraph_sync.sh @ .

- duration:        `1s`
- baseline status:
```
  method          2,599
  function        1,722
  file            498
  constant        139
  struct          85
  interface       84
```
- post-sync status:
```
  method          2,599
  function        1,722
  file            498
  constant        139
  struct          85
  interface       84
```
- validate:        **PASS**
```
PASS: codegraph on PATH at /opt/homebrew/bin/codegraph (version 0.9.9)
PASS: index reality — codegraph status reports 8906 nodes across 509 files
PASS: unforgeable MCP challenge — codegraph_status via MCP returned 8906 nodes == CLI 8906
PASS: own-code resolution — 'Deduplicator' resolves in download-proxy/src (8 hit(s))
PASS: own-org INCLUDED (§11.4.79) — 'versionTagsCmd' resolves inside constitution/ (2 hit(s))
PASS: third-party EXCLUDED (§11.4.79) — 0 submodules/jackett paths in index
PASS: secrets EXCLUDED (§11.4.10) — 0 secret/config-credential paths in index
----------------------------------------
CodeGraph validate: 7 PASS / 0 FAIL
VERDICT: PASS
```
