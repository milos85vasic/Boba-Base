# Boba Browser Extension - Master Execution Plan

## Project Overview
Create comprehensive deep research, full implementation plan, source code, documentation, diagrams, and all deliverables for browser extensions (Yandex, Firefox, Opera, Chrome, Chromium) that parse/extract torrent files and magnet links from web pages or tab groups, then pass them to Boba Project's qBitTorrent web dashboard.

## Stage 1: Deep Research (parallel multi-agent swarm)
**Skill**: `deep-research-swarm` (Route B - Focused Search)
- Agent 1: Boba Project Architecture Research
  - Clone Boba-Base repo, analyze architecture, APIs, qBitTorrent integration, services, data models
- Agent 2: Browser Extension APIs Research  
  - Chrome Extensions API (MV3), Firefox WebExtensions API, Opera, Yandex, Chromium specifics
  - Tab Groups APIs, content scripts, background scripts, messaging
- Agent 3: Torrent/Magnet Link Parsing Research
  - Torrent file format parsing, magnet link URI schemes, DHT infohash extraction
  - Web scraping techniques for torrent discovery on common sites
- Agent 4: Existing Solutions & Security Research
  - Existing torrent browser extensions analysis
  - CORS handling, CSP bypasses, download interception, security considerations

**Output**: Validated research brief with all findings

## Stage 2: Architecture & Technical Design
**Skill**: `report-writing` (Architecture document)
- System architecture diagram
- Extension architecture (content scripts, background, popup, options)
- Boba integration architecture (REST API, WebSocket, authentication)
- Data flow diagrams
- Database schema (SQL definitions)
- Security model
- Error handling strategy

**Output**: architecture.md

## Stage 3: Implementation Plan (Phased)
- Phase 1: Core extension scaffold + manifest + build system
- Phase 2: Content script - torrent/magnet detection & extraction
- Phase 3: Background script - message routing, API communication
- Phase 4: Popup UI - torrent list, status, controls
- Phase 5: Options page - Boba server configuration
- Phase 6: Tab groups support (Yandex/Chrome)
- Phase 7: Boba API integration - add torrents, monitor downloads
- Phase 8: Cross-browser packaging & store submission
- Phase 9: Testing (unit, integration, E2E)
- Phase 10: Documentation & release

**Output**: implementation-plan.md with all sub-tasks

## Stage 4: Source Code Development
**Skill**: `vibecoding-general-swarm`
- Full TypeScript/JavaScript source code for all extension components
- Build system (webpack/vite)
- Manifest V2/V3 compatibility
- Cross-browser API shims
- Test suites (Jest, Playwright)

**Output**: Complete source code tree in /mnt/agents/output/src/

## Stage 5: Diagrams & Visual Assets (parallel multi-agent)
- Agent 1: Mermaid.js diagrams (system architecture, data flow, sequence diagrams)
- Agent 2: SVG/PNG architecture diagrams (enterprise style)
- Agent 3: UML class diagrams, ER diagrams
- Agent 4: draw.io XML diagrams
- Agent 5: HTML interactive diagrams

**Output**: All diagram files in /mnt/agents/output/diagrams/

## Stage 6: Documentation (parallel multi-agent)
- Agent 1: Technical Specification (Markdown)
- Agent 2: API Reference (Markdown)
- Agent 3: User Guide (Markdown)
- Agent 4: Developer Guide (Markdown)
- Agent 5: Installation & Setup Guide (Markdown)

**Output**: All docs in /mnt/agents/output/docs/

## Stage 7: Multi-Format Conversion
**Skills**: `docx`, `pdf`, `html`
- Convert all Markdown docs to DOCX (enterprise styled)
- Convert all Markdown docs to PDF (professional styled)
- Convert all Markdown docs to HTML (clean styled)
- Package everything into final deliverable

**Output**: /mnt/agents/output/final/ with all formats

## Deliverables Summary
1. Research brief (research-brief.md)
2. Architecture document (architecture.md)
3. Implementation plan (implementation-plan.md)
4. Full source code (/src/)
5. SQL schemas (database schemas)
6. All diagrams (Mermaid, SVG, PNG, UML, draw.io, HTML)
7. Technical specification (MD, PDF, DOCX, HTML)
8. API reference (MD, PDF, DOCX, HTML)
9. User guide (MD, PDF, DOCX, HTML)
10. Developer guide (MD, PDF, DOCX, HTML)
11. Installation guide (MD, PDF, DOCX, HTML)
