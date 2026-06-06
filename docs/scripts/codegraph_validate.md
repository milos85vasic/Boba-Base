# scripts/codegraph_validate.sh

**Revision:** 1
**Last modified:** 2026-06-06T14:40:00Z

## Overview

Anti-bluff verifier for the CodeGraph integration (Constitution §11.4.78
step 4). Proves the local CodeGraph index is real and correctly scoped — not a
§11.4 PASS-bluff — using facts obtained only from CodeGraph (CLI + MCP), never
from the script reading source files itself.

## Prerequisites

- `codegraph` on `PATH` (npm-installed per §11.4.78).
- `node` on `PATH`.
- A built index: `.codegraph/` present with `codegraph index` already run.

## Usage

```bash
bash scripts/codegraph_validate.sh
```

Exit codes: `0` all checks PASS · `1` one or more checks FAIL · `2` environment
problem (codegraph/node absent, or `.codegraph/` missing).

## What it checks (7)

1. `codegraph` present on `PATH` + version (no hardcoded host path).
2. Index reality — `codegraph status` reports `nodeCount > 0`.
3. **Unforgeable MCP challenge** — drives `codegraph serve --mcp` over stdio
   and asserts the `codegraph_status` node count returned over MCP equals the
   CLI node count.
4. Own-code symbol `Deduplicator` resolves under `download-proxy/src/`.
5. Own-org submodule INCLUDED (§11.4.79) — `versionTagsCmd` resolves under
   `constitution/`.
6. Third-party EXCLUDED (§11.4.79) — 0 `submodules/jackett` paths in index.
7. Secrets EXCLUDED (§11.4.10) — 0 `.env`/config-credential/`boba.db` paths.

## Edge cases

- If `codegraph` reports a stale version, a standalone shim is shadowing the
  npm binary on `PATH` (see `docs/CODEGRAPH.md` troubleshooting).
- The MCP check uses `notifications/initialized` + a short delay; the server is
  async and a torn read returns 0, which fails the check (correct — no bluff).

## Internal behaviour

Read-only against the index; starts and tears down a transient MCP server.
Never prints secrets.

## Related

- `docs/CODEGRAPH.md` — full integration doc.
- `constitution/scripts/codegraph_update.sh` / `codegraph_sync.sh` — update +
  sync automation (§11.4.80); `codegraph_sync.sh` step 4 invokes this script.
- `docs/codegraph/Status.md` — append-only event ledger.

Last verified: 2026-06-06 (7 PASS / 0 FAIL on codegraph 0.9.9, 509 files).
