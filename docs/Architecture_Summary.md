# Architecture Summary

System topology, data flow, and lifecycle diagrams for the Boba project.

## Contents

- `container-topology.mmd` — Two-container + one host-process topology (qBittorrent + Jackett proxy/merge-service, host webui-bridge)
- `plugin-execution.mmd` — Nova3 plugin execution: subprocess (public trackers) vs aiohttp (private trackers)
- `private-tracker-bridge.mmd` — Authenticated download path via webui-bridge.py on `:7188`
- `request-lifecycle.mmd` — Full user-visible flow: search query → merge → stream → download
- `search-lifecycle.mmd` — Detailed search: Angular → FastAPI → SearchOrchestrator → subprocess/aiohttp
- `shutdown-sequence.mmd` — Graceful shutdown: SIGTERM/SIGINT → signal handler → uvicorn → SearchOrchestrator

## Status

- Domain: Architecture
- Docs count: 6 (Mermaid diagrams)
- Format: Mermaid `.mmd` (rendered in Markdown viewers with Mermaid support)
- Last reviewed: 2026-06-08

## Diagram Overview

| Diagram | Scope |
|---------|-------|
| container-topology | Physical deployment: containers, ports, host processes |
| plugin-execution | Public vs private tracker execution model |
| private-tracker-bridge | Authenticated download proxy for private sites |
| request-lifecycle | End-to-end user request path |
| search-lifecycle | Internal fan-out, dedup, enrichment, streaming |
| shutdown-sequence | Graceful shutdown and resource cleanup |

## Related

- [API Summary](API_Summary.md) — REST endpoints served by the merge service
- [Migration Summary](migration/Migration_Python_Codebase_To_Go.md) — Go backend parity
