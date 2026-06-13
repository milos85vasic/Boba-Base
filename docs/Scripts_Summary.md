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
| `scripts/pre_build_verification.sh` | Pre-build gate: 18 invariants (constitution, infrastructure, exports, workable-items, docs chain) |
| `scripts/docs_chain.sh` | 3-step pipeline: workable-items export → domain summaries → HTML/PDF/DOCX |
| `scripts/boba-ctl.sh` | boba-ctl CLI wrapper (Go binary orchestrator) |
| `scripts/generate_markdown_exports.sh` | Universal Markdown → HTML/PDF/DOCX export (§11.4.65) |
| `scripts/run-tests.sh` | Test suite runner (hermetic/live/all) |
| `scripts/run_all_challenges.sh` | Challenge suite runner |
| `ci.sh` | Full local CI pipeline |

## Related

- [CodeGraph Summary](CodeGraph_Summary.md) — CodeGraph integration status
- [Pre-build gate invariants](../scripts/pre_build_verification.sh) — source of truth for CI gates
