# Superpowers Summary

Design specs and implementation plans for major cross-cutting features ("superpowers").

## Contents

### Plans (5)

- `plans/2026-04-17-realtime-streaming-plan.md` — Implement real-time search results streaming via SSE: modify SearchOrchestrator to yield intermediate results, update FastAPI SSE endpoint, add EventSource in frontend
- `plans/2026-04-19-completion-initiative.md` — Drive the platform to zero-debt: wire every module, unskip all tests, reach 100% coverage, harden security/concurrency/memory, add Snyk + SonarQube scanning
- `plans/2026-04-22-python-to-go-migration.md` — Large-scale migration plan (3993 lines): port Python/FastAPI merge search to Go/Gin with feature parity, preserving two-container topology, keeping plugins as Python subprocesses
- `plans/2026-04-26-jackett-autoconfig-clean-rebuild.md` — Jackett indexer auto-configuration: discover env credential triples, fuzzy-match tracker names, idempotently configure Jackett at proxy startup (all 84 tasks shipped)
- `plans/2026-04-27-jackett-management-ui-and-system-db.md` — boba-jackett Go service on port 7189 with encrypted SQLite system DB, Angular management UI, 13-item DoD from design spec

### Specs (2)

- `specs/2026-04-26-jackett-autoconfig-clean-rebuild-design.md` — Design spec for Jackett auto-configuration: clean-slate rebuild, full indexer integration from env credentials, comprehensive test/challenge layers, parity audit for eventual Go flip
- `specs/2026-04-27-jackett-management-ui-and-system-db-design.md` — Design spec for boba-jackett management UI + SQLite system DB: AES-256-GCM encrypted credentials, Angular routes for credential/indexer management

## Status

- Domain: Superpowers
- Docs count: 7 (5 plans + 2 specs)
- Last reviewed: 2026-06-08

## Completion by Plan

| Plan | Status | Notes |
|------|--------|-------|
| Real-time SSE streaming | ✅ Shipped | Fully implemented in FastAPI + Angular |
| Completion initiative | 🔄 Ongoing | Coverage at 49%, mutation testing active, gap analysis ongoing |
| Python-to-Go migration | 🔄 In progress | Blueprint complete, skeleton Go backend, full parity deferred |
| Jackett autoconfig | ✅ Shipped | All 84 tasks complete |
| boba-jackett system DB | ✅ Shipped | 13/13 DoD items complete |

## Related

- [API Summary](API_Summary.md) — REST endpoints implementing the plans
- [Migration Summary](Migration_Summary.md) — Go migration parity tracking
- [Demos Summary](Demos_Summary.md) — verification demos for shipped features
