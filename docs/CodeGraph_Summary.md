# CodeGraph Summary

CodeGraph integration: install, update, sync, and validate events tracking compliance with Constitution §§11.4.78-80.

## Contents

- `Status.md` — Append-only ledger of all CodeGraph operations for the Boba project

## Status

- Domain: CodeGraph
- Docs count: 1
- Index health: active (indexed files available, see `Status.md` for last sync timestamp)
- Last reviewed: 2026-06-08

## Key Events

| Date | Event |
|------|-------|
| 2026-04 | Initial CodeGraph install and index build |
| 2026-05 | Index sync after constitution rebase and submodule updates |
| 2026-06 | Index re-validated after mutmut path restructure |

## Verification

The CodeGraph index is validated by:
1. `docs/scripts/codegraph_validate.md` — anti-bluff verifier proving the local index is real and correctly scoped
2. Pre-build gate invariant CM-MARKDOWN-EXPORT-SYNC checks index freshness
3. Manual: `codegraph_codegraph_status` tool (health check)

## Related

- [Scripts Summary](docs/scripts/codegraph_validate.md) — CodeGraph verification script
- [Architecture Summary](docs/Architecture_Summary.md) — system topology
