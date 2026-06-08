# API Summary

OpenAPI specification for the Merge Search Service (FastAPI on `:7187`).

## Contents

- `openapi.json` — Full OpenAPI 3.1 spec: search, download, auth, theme, health, scheduler, and hook endpoints served by the FastAPI application.

## Status

- Domain: API
- Docs count: 1 (OpenAPI spec, JSON)
- Coverage: 49% line coverage via pytest (unit tests)
- Last reviewed: 2026-06-08

## Key Endpoints

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/v1/search` | POST | Fan-out search across enabled trackers |
| `/api/v1/search/{id}/stream` | GET | SSE stream of real-time search results |
| `/api/v1/download` | POST | Proxy download request to qBittorrent |
| `/api/v1/auth/login` | POST | qBittorrent WebUI authentication |
| `/api/v1/health` | GET | Service health check |
| `/api/v1/theme` | GET/POST | Cross-app theme state |
| `/api/v1/scheduler` | GET/POST | Scheduled search configuration |
| `/api/v1/hooks` | GET/POST/PUT/DELETE | Hook registration and invocation |

## Related

- [Architecture Summary](docs/Architecture_Summary.md) — system topology and request lifecycle
- [Architecture diagrams](docs/architecture/) — Mermaid sequence/flow diagrams
