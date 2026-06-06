# Boba Browser Extension — Research Dimension Decomposition

## Dimension 01: Boba Project Architecture Deep Dive
**Scope**: Complete understanding of Boba-Base repo architecture, services, APIs, data models, plugin system, and how torrents flow through the system.
**Key areas**: qBitTorrent-go service, FastAPI merge search, webui-bridge, download-proxy, plugin system, frontend dashboard, auth model.

## Dimension 02: qBitTorrent WebUI API Complete Reference
**Scope**: Every endpoint, parameter, auth mechanism, and response format needed to add/manage torrents programmatically.
**Key areas**: /api/v2/auth/login, /api/v2/torrents/add, /torrents/info, /sync/maindata, cookie auth, multipart upload, CSRF handling.

## Dimension 03: Browser Extension Architecture (MV3)
**Scope**: Manifest V3 architecture patterns for torrent extraction extensions.
**Key areas**: manifest.json, service workers, content scripts, popup pages, options pages, messaging (chrome.runtime.sendMessage), storage API.

## Dimension 04: Cross-Browser Compatibility Matrix
**Scope**: Differences and compatibility shims for Chrome, Firefox, Opera, Yandex, Chromium.
**Key areas**: Manifest V2 vs V3, browser.* vs chrome.* API, polyfills, store submission requirements, Yandex specifics.

## Dimension 05: Tab Groups API Deep Dive (Chrome/Yandex)
**Scope**: How to query, enumerate, and extract URLs from tab groups in Yandex Browser and Chrome.
**Key areas**: chrome.tabGroups.query(), chrome.tabs.query({groupId}), group permissions, extracting all URLs from a group.

## Dimension 06: Magnet Link Detection & Parsing Algorithms
**Scope**: Comprehensive regex patterns, URI parsing, and infohash extraction from magnet links.
**Key areas**: magnet:?xt=urn:btih: format, URI decoding, infohash validation (40-char hex), dn/tr/xl parameter extraction, edge cases.

## Dimension 07: Torrent File Detection, Download & Bencode Parsing
**Scope**: How to detect .torrent links, download files, parse bencode, extract infohash.
**Key areas**: .torrent link detection, fetch with CORS, bencode parser in JS/TS, SHA-1 infohash computation, File/Blob handling.

## Dimension 08: Web Page DOM Scraping & Dynamic Content
**Scope**: Strategies for finding torrents and magnets on any web page including dynamically loaded content.
**Key areas**: DOM traversal, MutationObserver for SPAs, common torrent site patterns, link detection, iframe handling.

## Dimension 09: Extension ↔ Boba API Integration
**Scope**: How the browser extension communicates with Boba services and qBitTorrent WebUI.
**Key areas**: REST API calls, CORS handling, authentication (API keys, cookies), WebSocket for progress, error handling, retry logic.

## Dimension 10: Extension UI/UX Design Patterns
**Scope**: User interface components for torrent management extension.
**Key areas**: Popup design, options page, context menus, notifications, badge counters, torrent list display, status indicators.

## Dimension 11: Security Model & Privacy Architecture
**Scope**: Secure credential storage, permission model, CSP, and privacy considerations.
**Key areas**: manifest permissions, host permissions, chrome.storage.local vs sync, secure key storage, content script isolation, CSP compliance.

## Dimension 12: Testing, Build System & Store Distribution
**Scope**: Complete testing strategy and cross-browser build/packaging pipeline.
**Key areas**: Jest for unit tests, Playwright for E2E, webpack/vite build, CI/CD, store submission packages (Chrome Web Store, AMO, Opera, Yandex).
