# Scripts Summary

Build, validation, and utility scripts for the Boba project.

## Contents

- `codegraph_validate.md` — Anti-bluff verifier for the CodeGraph integration (Constitution §11.4.78 step 4). Proves the local CodeGraph index is real and correctly scoped using facts from CodeGraph CLI + MCP only.

## Status

- Domain: Scripts
- Docs count: 1
- Last reviewed: 2026-06-08

## Key Scripts (source)

| Script | Purpose |
|--------|---------|
| `scripts/pre_build_verification.sh` | Pre-build gate: 24 invariants (constitution, infrastructure, exports, workable-items, docs chain engine) |
| `scripts/workable-items-export.sh` | 3-step pipeline: workable-items DB export → domain summaries → HTML/PDF/DOCX (renamed 2026-08-15 BOB-104 from `docs_chain.sh` — that name was a misnomer; the REAL Docs Chain §11.4.106 engine lives at `constitution/submodules/docs_chain/`) |
| `constitution/submodules/docs_chain/docs_chain` | Real §11.4.106 Docs Chain engine (Go binary) — `verify` / `sync` / `doctor` / `graph` / `watch` against `.docs_chain/contexts/*.yaml` |
| `scripts/boba-ctl.sh` | boba-ctl CLI wrapper (Go binary orchestrator) |
| `scripts/generate_markdown_exports.sh` | Universal Markdown → HTML/PDF/DOCX export (§11.4.65) |
| `scripts/run-tests.sh` | Test suite runner (hermetic/live/all) |
| `scripts/run_all_challenges.sh` | Challenge suite runner |
| `ci.sh` | Full local CI pipeline |

## Related

- [CodeGraph Summary](CodeGraph_Summary.md) — CodeGraph integration status
- [Pre-build gate invariants](../scripts/pre_build_verification.sh) — source of truth for CI gates
