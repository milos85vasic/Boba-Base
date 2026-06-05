# docs/ — Project Documentation Index

**Revision:** 1
**Last modified:** 2026-06-06T00:00:00Z

This directory is the written source of truth for the qBittorrent-Fixed
project. Each file below is either end-user facing, operator-facing, or
contributor-facing. When a topic appears both here and in the top-level
`README.md`, this directory is authoritative.

## Purpose

- Collect every cross-cutting design note, runbook, and subsystem manual.
- Keep the top-level `README.md` short (one-page overview + quickstart).
- Feed the MkDocs Material site planned under Phase 8 of the
  completion-initiative plan (`docs/superpowers/plans/`).

## How to add a new doc

1. Drop a `*.md` file here (no subdirectories except the existing ones).
2. Add a one-line entry to the table below.
3. Reference the file from the appropriate top-level doc (`README.md`,
   `AGENTS.md`, or `CLAUDE.md`) so it is actually discoverable.
4. `tests/unit/test_docs_presence.py` guards that a fixed set of subsystem
   docs exists — extend the guard when a new canonical subsystem doc
   appears.

## Files in this directory

| File | Audience | Topic |
|---|---|---|
| `USER_MANUAL.md` | End users | Day-to-day usage, WebUI, download flow |
| `MAGNET_LINKS.md` | End users | How magnet links are generated and handled |
| `PLUGINS.md` | Operators | Canonical 12-plugin roster, how to install/remove |
| `PLUGIN_TROUBLESHOOTING.md` | Operators | Common plugin failure modes and fixes |
| `DOWNLOAD_FIX.md` | Operators | Known-good recovery procedure for broken downloads |
| `RELEASE_TORRENT_UPLOAD_FIX.md` | Operators | Fix for the upload-release edge case |
| `TEST_RESULTS.md` | Operators | Snapshot of last full test run |
| `TESTING.md` | Contributors | Authoritative test-type catalogue + how to add a new test |
| `SECURITY.md` | Contributors | Threat model, credential storage, scanner stack |
| `CONCURRENCY.md` | Contributors | Asyncio model, semaphores, retries, graceful shutdown |
| `OBSERVABILITY.md` | Contributors | Prometheus + Grafana stack, metric names |
| `PERFORMANCE.md` | Contributors | pytest-benchmark suite, Locust load profile, SLOs |
| `DATA_MODEL.md` | Contributors | Pydantic + dataclass schemas (no relational DB) |
| `COVERAGE_BASELINE.md` | Contributors | Module-by-module coverage zero point |
| `QUALITY_STACK.md` | Contributors | `docker-compose.quality.yml` architecture |
| `SCANNING.md` | Contributors | Seven-scanner stack and triage policy |
| `architecture/*.mmd` | Contributors | Mermaid diagrams for container, search, shutdown, plugin, bridge |
| `issues/*.md` | Contributors | Frozen post-mortems for specific incidents |
| `superpowers/plans/*.md` | Contributors | Long-horizon implementation plans |
| `../courses/README.md` | All audiences | Asciinema video-course tracks (operator, plugin author, contributor, security/ops) |

## Conventions

- Markdown only. Diagrams are Mermaid (`.mmd`), not PlantUML / drawio.
- Wrap at 80 columns where practical; long URLs and code blocks are
  exempt.
- Link siblings with relative paths (`./SECURITY.md`), never absolute.
- Code blocks must specify a language tag so the MkDocs build renders
  syntax highlighting.
- Filenames use `UPPERCASE_SNAKE_CASE.md` for canonical subsystem docs,
  `lowercase-kebab-case.md` for transient notes under `issues/`.

## What does NOT live here

- API reference — FastAPI auto-generates OpenAPI at `/docs` on the live
  service (port 7187).
- Frontend docs — see `frontend/README.md` (Angular 19, Vitest).
- Constitution / GitSpec memory — see `.specify/README.md`.
- Test runner README — see `tests/README.md`.
- Commit style and PR rules — see `CONTRIBUTING.md`.

## Tests

- `tests/unit/test_docs_presence.py` verifies the canonical subsystem
  docs (`TESTING`, `SECURITY`, `CONCURRENCY`, `OBSERVABILITY`,
  `PERFORMANCE`, `DATA_MODEL`, `SCANNING`, `QUALITY_STACK`,
  `COVERAGE_BASELINE`) are present.
- `tests/unit/test_architecture_diagrams.py` verifies the Mermaid files
  under `architecture/` exist.

## Gotchas

- The current structure has **no docs-site generator**; Phase 8 of the
  completion plan introduces MkDocs Material under `website/`. Until
  then these files are read as plain markdown on GitHub.
- `docs/superpowers/plans/` is written by the `superpowers:writing-plans`
  skill and is not meant to be edited by hand mid-phase.
