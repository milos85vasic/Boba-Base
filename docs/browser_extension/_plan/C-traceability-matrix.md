# C — Master Traceability Matrix (browser extension)

**Revision:** 1
**Last modified:** 2026-06-10T00:00:00Z
**Purpose:** Anti-skip backbone (operator mandate + §11.4.118 enumerated coverage). One row per atomic requirement / feature / entity / edge-case / NFR / dimension-decision drawn from ALL six analysis files (`docs/browser_extension/_analysis/01..06`). EVERY item from the source corpus appears. Proves nothing is silently dropped: deferred items are listed explicitly with rationale; untraceable items are listed OPEN.

**Stable ID scheme:**
- `FR-001..FR-025` — 25 functional requirements (file 01 §B).
- `NFR-001..NFR-015` — 15 non-functional requirements (file 01 §C).
- `DIM01-Rxx .. DIM12-Rxx` — per-dimension consolidated decisions (file 02).
- `ER-<entity>` — 6 ER entities (file 03 §2) + SQL-table superset (file 04 §4a).
- `EDGE-xx` — documented edge cases (file 01 §I + scattered).
- `SEC-xx` — security/STRIDE controls (file 02 Dim11 + file 03 §6 + file 01 §N).
- `INS-xx` — 10 cross-dimension insights (file 02).
- `CV-xx` — cross-verification conflicts/low-confidence items (file 02).
- `FND-xx` — foundation/source-layer facts (files 04/05).
- `TST-xx` — test-type coverage requirements (file 06).
- `BLD-xx` — build/release/distribution (file 01 §M + file 02 Dim12 + file 03 §7).
- `OQ-xx` — open questions / ambiguities (all files).

Phase column uses the authoritative 8-phase impl-plan (file 01 §P.2): P1 Foundation, P2 Core Engine, P3 Extension Shell, P4 API Integration, P5 Tab Groups, P6 UI/UX Polish, P7 Testing, P8 Build/Dist. `v2` = deferred (see Coverage Ledger). Boba constraint flags are noted in Notes.

---

## 1. Functional Requirements (25)

| ID | Source | Requirement | Category | Phase | Notes/Dependencies |
|---|---|---|---|---|---|
| FR-001 | 01 §B.1 FR-001 | Detect magnet links (`href` `magnet:?`) in DOM of any page, dynamic across SPA; iframe via all_frames; ≤500 ms after injection | detection | P2/P3 | MutationObserver debounce 500 ms (EDGE-06); regex `MAGNET_REGEX` (FND-12) |
| FR-002 | 01 §B.1 FR-002 | Detect `.torrent` file links via `.torrent` suffix (case-insens) + `Content-Type: application/x-bittorrent` | detection | P2/P3 | `TORRENT_FILE_REGEX` (FND-12); CORS-aware (DIM07) |
| FR-003 | 01 §B.1 FR-003 | Parse magnet URI per BEP-9: xt/dn/tr/xl/ws/x.pe; xt mandatory valid 40-hex; dn fallback "Unknown Torrent"; malformed tr discarded | parsing | P2 | OQ-07 param-set drift (xs/as/kt/mt vs x.pe); DIM06 |
| FR-004 | 01 §B.1 FR-004 | Download + parse `.torrent` via fetch; max 10 MB (`maxTorrentFileSize`); 30 s timeout; CORS→Boba-proxy fallback; bencode decode | parsing/api | P2/P4 | EDGE-04, EDGE-05; FND parser is dead code in ref (FND-23) |
| FR-005 | 01 §B.1 FR-005 | Compute SHA-1 over bencoded `info` dict → 40-hex infohash; MUST match xt | parsing | P2 | RAW bencode, not decode-re-encode (DIM07-R; FND-22) |
| FR-006 | 01 §B.1 FR-006 | Deduplicate torrents by lowercase infohash; merge longest displayName + union trackers + earliest detectedAt | parsing | P2 | INS-02 unified identity; ref time-salted ids unreliable (OQ-16) |
| FR-007 | 01 §B.2 FR-007 | Send magnets to qBitTorrent `/api/v2/torrents/add` `urls` param; cookie session; opt category/tags/savepath/rename | api | P4 | DIM02; Boba→7186 proxy (OQ-01) |
| FR-008 | 01 §B.2 FR-008 | Upload `.torrent` via multipart `torrents` field to `/api/v2/torrents/add`; blobs in-memory only | api | P4 | `addTorrentFromFile` (FND-31) |
| FR-009 | 01 §B.2 FR-009 | Tab-group batch: enumerate group tabs, SCAN each, aggregate + dedup, transmit unified batch | tab-groups | P5 | NET-NEW design — ref has NO tabGroups code (OQ-17/FND-33) |
| FR-010 | 01 §B.2 FR-010 | Enumerate tab groups + extract URLs via `chrome.tabGroups.query()` + `chrome.tabs.query()`; show titles/colors; multi-select | tab-groups | P5 | DIM05; Chrome/Yandex only (EDGE-21) |
| FR-011 | 01 §B.3 FR-011 | Auto-discover Boba on LAN: probe well-known ports + `/health`; parse version ≥1.0.0; ranked list; persist | api | P4 | Re-point 8443/8080→7186/7187/7189 (OQ-01); INS-01 |
| FR-012 | 01 §B.3 FR-012 | Support 4 auth methods: cookie (SID), API key (X-API-Key), Basic, Custom Header | security/api | P4 | C1: support both cookie+JWT/apikey; ref drops custom-header (OQ-06) |
| FR-013 | 01 §B.3 FR-013 | Encrypt stored credentials AES-256-GCM; PBKDF2 from per-install salt; key in storage.session; 96-bit IV; 128-bit tag | security | P1/P4 | §11.4.10; ref uses fixed/empty passphrase BLUFF (OQ-15/FND-30) |
| FR-014 | 01 §B.4 FR-014 | Offline FIFO queue: max 1000; exp backoff 5 s→5 min; max 5 retries; persist storage.local; Dead-Letter substore | queue | P4 | ref max 50 / 3 attempts diverges (OQ-19); DIM09 |
| FR-015 | 01 §B.4 FR-015 | Badge: numeric queued count; colors green idle/blue sending/orange queued/red error; ≤200 ms update | ui | P3/P6 | INS-09 badge sync; BADGE_COLORS (FND-26) |
| FR-016 | 01 §B.5 FR-016 | Context menu: link(magnet)→Send Magnet; link(.torrent)→Download; page→Scan; tab-group→Send Group | ui | P3/P5 | `chrome.contextMenus`; ref `bobalink-send/scan/dashboard` (FND-32) |
| FR-017 | 01 §B.5 FR-017 | Keyboard shortcuts: send-current-page Ctrl+Shift+B; open-popup Ctrl+Shift+L; send-tab-group Ctrl+Shift+G (customizable) | ui | P3 | OQ-08 3-vs-4 cmds; ref ships B/S/D not L/G (FND-29) |
| FR-018 | 01 §B.5 FR-018 | Cross-browser single codebase: Chrome 88+, Firefox 109+, Opera 74+, Yandex 21+; BrowserAdapter abstraction | cross-browser | P1/P8 | DIM04; WXT handles per-browser manifest |
| FR-019 | 01 §B.5 FR-019 | i18n via `_locales/{lang}/messages.json`: en default + zh_CN/zh_TW/es/fr/de/ja/ko; no hardcoded strings | i18n | P6 | ref ships en only (28 keys, FND-19) |
| FR-020 | 01 §B.5 FR-020 | Accessibility WCAG 2.1 AA: contrast ≥4.5:1; keyboard nav; ARIA on icon buttons; aria-live; focus indicators | ui | P6 | §11.4.117 pixel-oracle for verification |
| FR-021 | 01 §B.5 FR-021 | Dark/Light theme: respect `prefers-color-scheme` + manual override; CSS custom properties | ui | P6 | DIM10 §9; ref `ui.theme=auto` (FND-25) |
| FR-022 | 01 §B.5 FR-022 | Notifications via `chrome.notifications`: Sent / Send Failed(retry) / Batch Complete / Retrying; suppressible per-category | ui | P3/P6 | DIM10 §5; MV3 no base64 icons (DIM03) |
| FR-023 | 01 §B.5 FR-023 | Options page: server URL+mode, auth(masked)+test-connection, default category/tags/path, notif prefs, queue settings, theme, reset | ui | P3 | DIM10 §2; ref Servers/General/Advanced/About (FND-43) |
| FR-024 | 01 §B.5 FR-024 | Health check: poll 30 s; `/api/v2/app/version` or `/health`; states connected/connecting/disconnected/error; tooltip last-ping | api | P4 | ref `HealthChecker` thresholds 2 s/5 s (FND-34) |
| FR-025 | 01 §B.5 FR-025 | Rate limiting: 10 req/s burst, 60/min sustained; 1 concurrent + 500 ms inter-call; honor 429 Retry-After; in-memory | api | P4 | Token-bucket (file 01 §S); ref RATE_LIMIT 10/1000ms (FND-27) |

## 2. Non-Functional Requirements (15)

| ID | Source | Requirement | Category | Phase | Notes/Dependencies |
|---|---|---|---|---|---|
| NFR-001 | 01 §C.1 | Content script init ≤10 ms (`performance.now()`) | performance | P7 | benchmark test (TST-09) |
| NFR-002 | 01 §C.1 | Magnet detection ≤5 ms/link (1,000-link page benchmark) | performance | P7 | DOM-first querySelector (INS-03) |
| NFR-003 | 01 §C.1 | Popup render ≤100 ms (Lighthouse) | performance | P7 | |
| NFR-004 | 01 §C.1 | Options page load ≤200 ms (Lighthouse) | performance | P7 | |
| NFR-005 | 01 §C.1 | API round-trip ≤500 ms local (p95 over 100 calls) | performance | P7 | |
| NFR-006 | 01 §C.1 | Service worker cold start ≤50 ms | performance | P7 | |
| NFR-007 | 01 §C.1 | Bundle size compressed ≤350 KB | build | P8 | tree-shake + code-split |
| NFR-008 | 01 §C.2 | Credential encryption at rest: AES-256-GCM via Web Crypto | security | P1/P4 | composes FR-013/SEC-04 |
| NFR-009 | 01 §C.2 | No cleartext credential logging (ESLint rule + review) | security | P1 | §11.4.10; logger must redact |
| NFR-010 | 01 §C.2 | HTTPS-only API comms (URL scheme validation + CSP) | security | P4 | except localhost (SEC-08) |
| NFR-011 | 01 §C.2 | CSP `script-src 'self'; object-src 'none'` | security | P1 | MV3 CSP object (SEC-06) |
| NFR-012 | 01 §C.2 | Minimum permission model: activeTab + declared host perms only | security | P1 | OQ-09 activeTab vs https://*/ ; ref over-broad (FND-08) |
| NFR-013 | 01 §C.3 | Crash-free session rate ≥99.9% | reliability | P7 | chaos/stress (TST-07/08) |
| NFR-014 | 01 §C.3 | Offline queue durability 100% — all items survive restart | reliability | P4/P7 | persist storage.local; chaos test |
| NFR-015 | 01 §C.3 | API compatibility qBitTorrent 4.4.x–5.x | api | P4/P7 | version matrix (file 01 §R); v5 state renames (DIM02) |

**NFR §4.4 Scalability sub-items (non-numbered, captured as NFR-SCAL):**
| ID | Source | Requirement | Category | Phase | Notes |
|---|---|---|---|---|---|
| NFR-SCAL-1 | 01 §C.4 | Tab-group batch size unlimited (memory-bound) | scalability | P5 | |
| NFR-SCAL-2 | 01 §C.4 | Offline queue 1,000 default / 10,000 max | scalability | P4 | |
| NFR-SCAL-3 | 01 §C.4 | 10,000+ links must not jank (>16 ms frame); requestIdleCallback >500 links | performance | P2/P7 | EDGE-13; yieldToBrowser (FND) |
| NFR-MAINT-1 | 01 §C.5 | Coverage ≥80% unit / ≥60% E2E; JSDoc; TS strict zero `any`; ≤20 runtime deps | maintainability | P7 | Boba mandate raises to ~100% types (TST-15) |

## 3. Research-Dimension Consolidated Decisions (12 dimensions)

| ID | Source | Requirement / Decision | Category | Phase | Notes/Dependencies |
|---|---|---|---|---|---|
| DIM01-R1 | 02 Dim01 | Treat Dim01 as authoritative Boba topology: qBt 7185 (proxy 7186), FastAPI 7187, bridge 7188, jackett 9117, boba-jackett 7189; Go proxy 7187 (profile go) | data-model/api | P1/P4 | overrides spec 8443/8080 (OQ-01) |
| DIM01-R2 | 02 Dim01 | Extension talks to FastAPI :7187: `/api/v1/search`(+SSE stream), `/api/v1/download`, `/api/v1/download/file`, `/api/v1/magnet`, `/api/v1/auth/status`, `/api/v1/config`, `/health` | api | P4 | confirm vs live OpenAPI (OQ-12) |
| DIM01-R3 | 02 Dim01 | Boba CORS via `ALLOWED_ORIGINS` env incl. `chrome-extension://<id>`; SW not subject to CORS | security/api | P4 | INS-05 satellite |
| DIM01-R4 | 02 Dim01 | qBt default creds admin/admin (cookie SID); private trackers env-driven; 48 nova3 plugins; freeleech-only IPTorrents | api | P4 | K.3 never commit secrets |
| DIM02-R1 | 02 Dim02 | qBt WebUI v2: cookie auth `/api/v2/auth/login`→SID; Referer/Origin MUST match Host (CSRF); 403=IP ban | api/security | P4 | exp backoff to avoid bans |
| DIM02-R2 | 02 Dim02 | `/torrents/add`: magnets in `urls`, .torrent multipart `torrents`; 415 invalid; 200≠guaranteed-added; 405 wrong-method v4.4.4+ | api | P4 | |
| DIM02-R3 | 02 Dim02 | API-key auth (Bearer qbt_) v5.2.0+ only; cookie is safe baseline | api | P4 | CV low-confidence (CV-03) |
| DIM02-R4 | 02 Dim02 | Monitoring via polling `/sync/maindata?rid=` (no native WS/SSE); v5 renames pausedUP→stoppedUP/pausedDL→stoppedDL | api | P4 | INS-09 badge sync |
| DIM03-R1 | 02 Dim03 | MV3 manifest: host_permissions separate; background `{service_worker,type:module}`; perms storage/notifications/contextMenus/scripting/alarms/activeTab | cross-browser | P1 | |
| DIM03-R2 | 02 Dim03 | SW HARD timeouts: 30 s idle / 5 min request / 30 s fetch; chrome.alarms keep-alive; register listeners synchronously top-level; `return true` for async | cross-browser | P3 | EDGE-15; ref keepalive 20 s (FND) |
| DIM03-R3 | 02 Dim03 | Content scripts `document_idle`; ISOLATED world; cross-origin fetch routed through SW (CS can't since Chrome 85) | detection/security | P3 | DIM07-R4 |
| DIM03-R4 | 02 Dim03 | Storage quotas: local ~10 MB, sync ~100 KB/8 KB-item, session ~10 MB in-memory; badge ≤4 chars | data-model | P1 | |
| DIM03-R5 | 02 Dim03 | Offscreen documents for DOM/parse in MV3 (one/profile); NOT in Firefox | parsing | P2 | EDGE Firefox fallback |
| DIM04-R1 | 02 Dim04 | MV3 everywhere; Firefox uses Event Pages (WXT handles); webextension-polyfill for browser.* on Chromium + own feature-detect | cross-browser | P1/P8 | C2/C3 resolved |
| DIM04-R2 | 02 Dim04 | Firefox MV3 REQUIRES gecko.id + strict_min_version; version `x.y.z` only; data_collection_permissions since Nov 2025 | build | P8 | BLD |
| DIM04-R3 | 02 Dim04 | Opera lacks storage.sync/storage.managed; notifications partial on Mac; sidebarAction Opera/FF only | cross-browser | P6/P8 | compat matrix (ER/diagram #12) |
| DIM04-R4 | 02 Dim04 | UA detection order Yandex→Opera→Edge→Chrome→Chromium; prefer feature detection | cross-browser | P1 | |
| DIM05-R1 | 02 Dim05 | tabGroups Chrome 89+/MV3; query/get/update/move; create via tabs.group/ungroup; groupId NOT persistent (id by title+color+URLs) | tab-groups | P5 | EDGE-21; Firefox incompatible |
| DIM05-R2 | 02 Dim05 | Accessing tab.url/title needs `tabs` perm or host perms; collapsed groups still API-accessible | tab-groups | P5 | conflicts NFR-012 minimal perms |
| DIM05-R3 | 02 Dim05 | Yandex Chromium ~147+ full tabGroups; Chrome 148+ chrome://newtab cannot be grouped | tab-groups | P5 | EDGE-21 |
| DIM06-R1 | 02 Dim06 | Magnet BEP-9: xt only mandatory; hash v1 40-hex / 32-base32 (convert) / v2 btmh 1220+64-hex; two-phase detect+validate | parsing | P2 | base32→hex (DIM06-R2) |
| DIM06-R2 | 02 Dim06 | base32 (32-char) infohash MUST convert to hex (40-char); RFC4648 alphabet | parsing | P2 | `base32ToHex` (FND) |
| DIM06-R3 | 02 Dim06 | Decode dn (decodeURIComponent + `+`→space); tr/xs/as/ws decode; kt split `+`; so BEP-53 ranges; duplicate params→array | parsing | P2 | |
| DIM06-R4 | 02 Dim06 | Sanitize dn before HTML render (strip control/`<>`, ≤255, textContent); chunk large text 100 KB vs backtracking | security/parsing | P2 | SEC-10 |
| DIM07-R1 | 02 Dim07 | .torrent = bencode dict announce+info; info required piece length/pieces(20-byte SHA-1)/name; single length XOR multi files[] | parsing | P2 | |
| DIM07-R2 | 02 Dim07 | Bencode: dict keys lexicographic RAW-byte sorted (load-bearing for infohash); strict type rules | parsing | P2 | TST bencode |
| DIM07-R3 | 02 Dim07 | Infohash = SHA-1 of RAW bencoded info dict as-in-file (never decode-re-encode); Web Crypto needs HTTPS secure ctx | parsing | P2 | FND-22 ref re-encodes (caveat) |
| DIM07-R4 | 02 Dim07 | CORS download: CS can't cross-origin fetch since Chrome 85 → delegate to SW; size ≤10 MB (50 MB max); validate first byte `0x64` | api/parsing | P2/P4 | EDGE-05 |
| DIM07-R5 | 02 Dim07 | Private torrents (BEP-27): info.private==1 disables DHT/PEX; sanitize passkey to ***PASSKEY*** (never log) | security | P2 | SEC; §11.4.10 |
| DIM08-R1 | 02 Dim08 | Content-script timing document_idle + readyState checks for heavy SPAs (safeInitialize) | detection | P3 | |
| DIM08-R2 | 02 Dim08 | DOM-first querySelectorAll('a[href^="magnet:"]') (~90% catch) + TreeWalker text-node scan skipping script/style | detection | P2 | INS-03 tier-1+tier-3 |
| DIM08-R3 | 02 Dim08 | MutationObserver debounced 500 ms (~88× faster than polling), incremental scan new nodes; IntersectionObserver infinite scroll | detection | P2 | EDGE-06 |
| DIM08-R4 | 02 Dim08 | iframe all_frames:true + match_about_blank:true; Shadow DOM recursive shadowRoot (querySelectorAll doesn't pierce) | detection | P2 | EDGE-07 |
| DIM08-R5 | 02 Dim08 | Site-specific selector DB top ~20 sites (TPB/1337x/nyaa/rutracker/generic) — tier-2 detection | detection | P2 | INS-03; FND two tables to reconcile (OQ) |
| DIM08-R6 | 02 Dim08 | Scanner cleanup: track observers/timers/listeners, disconnect on navigation (memory-leak prevention); 16 ms frame budget | performance | P2 | NFR-SCAL-3 |
| DIM09-R1 | 02 Dim09 | Communication patterns: fetch (ext→server), EventSource SSE, WebSocket progress, runtime.sendMessage, storage.local, alarms | api | P4 | |
| DIM09-R2 | 02 Dim09 | Auth strategies: cookie/SID, JWT Bearer (60 s buffer + single-flight refresh, password NOT stored), API key, Basic | security/api | P4 | C1 support both |
| DIM09-R3 | 02 Dim09 | Retry classification: retry 0/429/500/502/503/504/401-after-refresh; non-retry 400/403/404/415; exp backoff+jitter (base 1000, max 30000, ×2, jitter 0.5, max 3) | queue/api | P4 | file 01 §F.3 differs (5 retries) (OQ-19) |
| DIM09-R4 | 02 Dim09 | SSE/EventSource cannot send custom headers — auth via URL query param; reconnect exp backoff; Chrome 116+ keeps SW alive on WebSocket | api | P4 | CV-low SSE path (CV-04) |
| DIM09-R5 | 02 Dim09 | Credential storage: store tokens only never plaintext password; chrome.storage.local NOT encrypted by default; clear on logout; HTTPS+validate certs | security | P4 | FR-013 adds encryption |
| DIM09-R6 | 02 Dim09 | Health: separate liveness/readiness; parallel checks AbortSignal.timeout(5000); status healthy/degraded/unhealthy | api | P4 | |
| DIM09-R7 | 02 Dim09 | Offline queue persist + retry on reconnect; navigator.onLine unreliable for LAN → proactive `/app/version` ping every 30 s via alarms | queue | P4 | INS-06 |
| DIM09-R8 | 02 Dim09 | Rate limiting token-bucket per-endpoint; RequestBatcher (maxBatch 10, maxWait 50 ms) | api | P4 | FR-025 |
| DIM09-R9 | 02 Dim09 | Manifest host_permissions localhost+127.0.0.1 (http+https `*` port); externally_connectable localhost; NEVER `<all_urls>` in prod | security | P1 | NFR-012; OQ-09 |
| DIM10-R1 | 02 Dim10 | Popup Chrome max 800×600 / min 25×25; sweet spot 380–450px wide; fixed header/connection bar/scroll/footer | ui | P3 | FND popup 400px |
| DIM10-R2 | 02 Dim10 | Context menus require contextMenus perm; >1 visible item auto-collapses into extension-named parent | ui | P3 | |
| DIM10-R3 | 02 Dim10 | Badge text ≤4 chars; per-tab via tabId (resets on close); setBadgeText/Color | ui | P3 | FR-015 |
| DIM10-R4 | 02 Dim10 | Commands max 4 suggested keys; all need Ctrl/Alt; Mac Ctrl→Command default; fires in SW | ui | P3 | OQ-08 |
| DIM10-R5 | 02 Dim10 | Side panel Chrome 114+ (open 116+, close 141+); cannot auto-open without user gesture | ui | v2 | CV-low (CV-05); optional surface |
| DIM10-R6 | 02 Dim10 | i18n `_locales/<locale>/messages.json`; manifest default_locale required if _locales; `__MSG_key__`+`getMessage()`; @@bidi for RTL | i18n | P6 | FR-019 |
| DIM11-R1 | 02 Dim11 | Design principles: Least Privilege, Defense in Depth, Zero Trust, Secure by Default, Privacy First | security | P1 | SEC umbrella |
| DIM11-R2 | 02 Dim11 | STRIDE mitigations S1-4/T1-4/R1-2/I1-5/D1-3/E1-3 + trust boundaries TB1-4 | security | P1/P7 | SEC-xx; security test (TST-04) |
| DIM11-R3 | 02 Dim11 | Minimal perms storage/alarms/notifications/activeTab; optional clipboardWrite; host localhost; NEVER all_urls/tabs/cookies/webRequest/scripting/downloads/history | security | P1 | NFR-012; ref declares scripting (FND-08) |
| DIM11-R4 | 02 Dim11 | Specific per-site matches (never wildcard — wildcards nullify postMessage protection) | security | P1 | conflicts ref `<all_urls>` CS (FND-08) |
| DIM11-R5 | 02 Dim11 | AES-256-GCM + PBKDF2-HMAC-SHA256 100k iters; 128-bit salt; 96-bit IV; non-extractable key; master pw never stored; decrypted cache storage.session; Clear All Data (GDPR) | security | P4 | FR-013/NFR-008 |
| DIM11-R6 | 02 Dim11 | Input validation: magnet/info-hash 40-hex v1/64-hex v2; sanitize dn textContent; validate Boba URL; reject javascript:/data:/vbscript:; block dangerous ports | security | P2/P4 | SEC-10 |
| DIM11-R7 | 02 Dim11 | Privacy: collect only Boba URL/creds(encrypted) + ephemeral magnet/names; NO page content/history/IP; analytics opt-in; eraseAllData(); no 3rd-party/selling | privacy | P6 | defaults analytics false |
| DIM11-R8 | 02 Dim11 | Secure fetch: `credentials:'omit'` + `referrerPolicy:'no-referrer'`; HTTPS-only except localhost; HSTS; self-signed cert pinning/CA install | security | P4 | conflicts qBt needs credentials:include (FND-31) — reconcile |
| DIM11-R9 | 02 Dim11 | Validate sender.id + sender.url (chrome-extension://) on ALL onMessage; action allow-listing | security | P3 | ref does NOT validate sender (OQ) |
| DIM11-R10 | 02 Dim11 | Update security: official-store signed distribution; FF self-hosted update_hash HTTPS; verify perms unchanged on update | build | P8 | |
| DIM12-R1 | 02 Dim12 | Build WXT (Vite); test Jest unit + Playwright E2E; mock sinon-chrome; versioning Conventional Commits→SemVer | build/testing | P7/P8 | OQ Jest-vs-Vitest (OQ-03) |
| DIM12-R2 | 02 Dim12 | Playwright needs launchPersistentContext + --load-extension + --disable-extensions-except; jsdom for DOM tests | testing | P7 | E2E fixture (TST-02) |
| DIM12-R3 | 02 Dim12 | Coverage threshold global 70% config (aspirational 80%+ INS-10); reporters lcov/html/json-summary; optional Sonar/Snyk/Semgrep/Trivy/Gitleaks | testing | P7 | Boba→~100% types |
| DIM12-R4 | 02 Dim12 | Store assets: icons 16/32/48/128(+512); screenshots 640×480 or 1280×800; privacy policy; no console.log/source-maps in prod; CSP set; no remote code | build | P8 | BLD |

## 4. ER Entities / Data Model (6 ER + SQL superset)

| ID | Source | Entity / Requirement | Category | Phase | Notes/Dependencies |
|---|---|---|---|---|---|
| ER-extension_config | 03 §2; 04 §4a T2 | Single per-install settings (config_id PK, server_url, api_key, qbittorrent_url, username, password_encrypted, auto_detect, default_category, scan_interval_ms, max_retries, retry_delay_ms, timestamps) | data-model | P1 | SQL key-value form (25 seed rows); OQ FK to discovered (diagram #9) |
| ER-discovered_torrents | 03 §2; 04 §4a T3 | Torrents found on pages (id=infohash PK UK, magnet_uri, name, size_bytes, source_url, source_tab_id, status, discovered_at, sent_at, error_message; SQL adds discovery_method/is_private/tab_group_id/selected/boba_status) | data-model | P2/P3 | mmd authoritative superset (file 03 note) |
| ER-download_queue | 03 §2; 04 §4a T4 | Offline/retry queue (queue_id PK, torrent_id FK, magnet_uri, priority 0-10, retry_count, status queued/retrying/failed/completed, queued_at, last_retry_at, error_log; SQL adds next_retry_at/server_id/torrent_data_b64) | queue/data-model | P4 | FR-014 |
| ER-server_config | 03 §2; 04 §4a T5 | Per-Boba-server multi-server (server_id PK, name, fastapi_url, go_service_url, qbittorrent_url, api_key, is_active, health_check_interval, last_health_check, last_check_result; SQL ports 7187/7189/8080→7186) | data-model | P1/P4 | DIM01-R1 port reconcile |
| ER-send_history | 03 §2; 04 §4a T6 | Audit log every send (history_id PK, infohash, magnet_uri, name, server_id FK, success, qbittorrent_hash, category, tags, sent_at, response_time_ms, error_message) | data-model | P4 | immutable log |
| ER-search_cache | 03 §2; 04 §4a (n/a) | Cached search results TTL'd (cache_id PK, query_hash, query_text, results JSON, result_count, cached_at, ttl_seconds, is_valid) — standalone, no relationship | data-model | v2 | search aggregation gated Boba 1.2+; OQ-12 storage backend |
| ER-REL | 03 §2 relationships | Cardinality: extension_config 1—o{ discovered_torrents; discovered_torrents 1—o{ download_queue; server_config 1—o{ send_history | data-model | P1 | extension_config→discovered FK conceptual only (OQ) |
| ER-SQL-extra | 04 §4a T1/T7/T8/T9 | SQL superset tables: app_metadata, site_selectors (30 seed rows), queue_log, statistics (daily aggregates) | data-model | P1/P2 | sql.js-over-storage.local OR chrome.storage JSON — pick one (OQ dual-storage) |

## 5. Edge Cases (documented)

| ID | Source | Edge case | Category | Phase | Notes |
|---|---|---|---|---|---|
| EDGE-01 | 01 §I | Magnet without dn → "Unknown Torrent"; qBt resolves from metadata | parsing | P2 | FR-003 |
| EDGE-02 | 01 §I | Duplicate infohash → silently skipped "duplicate"; merge longest dn+union tr+earliest ts | parsing | P2 | FR-006 |
| EDGE-03 | 01 §I | Malformed tracker URLs → logged + discarded | parsing | P2 | FR-003 |
| EDGE-04 | 01 §I | .torrent >10 MB → not downloaded; E_FILE_TOO_LARGE 413 → "use magnet" | api | P4 | FR-004 |
| EDGE-05 | 01 §I | CORS-blocked .torrent → Boba proxies (Boba mode); qBt-direct manual copy | api | P4 | FR-004; E_CORS |
| EDGE-06 | 01 §I | Dynamic SPA/infinite-scroll links → MutationObserver debounce 250/500 ms | detection | P2 | DIM08-R3 |
| EDGE-07 | 01 §I | iframe links → only when all_frames; may be inaccessible | detection | P2 | DIM08-R4 |
| EDGE-08 | 01 §I | JS click-handler "links" (not real `<a>`) → not detected; manual copy | detection | P3 | documented limitation |
| EDGE-09 | 01 §I | Non-standard/encoded magnet formats → not detected; manual copy | detection | P2 | |
| EDGE-10 | 01 §I | Login-gated / logged-in-only sites | detection | P3 | documented |
| EDGE-11 | 01 §I | Strict-CSP pages → extension respects CSP, will NOT inject scripts | detection/security | P3 | threat model |
| EDGE-12 | 01 §I | Forgotten encryption password → no recovery; reset extension + reconfigure | security | P4 | FR-013 |
| EDGE-13 | 01 §I | Pages 10,000+ links → no jank (>16 ms); requestIdleCallback >500; pagination | performance | P2 | NFR-SCAL-3 |
| EDGE-14 | 01 §I | Browser restart w/o password → session key lost → re-enter credentials | security | P4 | storage.session loss |
| EDGE-15 | 01 §I | Storage quota exceeded → E_STORAGE_FULL; Firefox stricter; clear old queue | data-model | P4 | DIM03-R4 |
| EDGE-16 | 01 §I | MV3 SW termination → chrome.alarms keep-alive; Firefox suspends more aggressively | cross-browser | P3 | DIM03-R2 |
| EDGE-17 | 01 §I | qBt rejects duplicate → already downloading/completed | api | P4 | FR-007 |
| EDGE-18 | 01 §I | Private-tracker torrents → work if accessible; may need passkey in tracker URL | api/security | P4 | DIM07-R5 |
| EDGE-19 | 01 §I | Self-signed certs → browser exception / system trust; HTTPS-only temporarily disabled for testing | security | P4 | DIM11-R8 |
| EDGE-20 | 01 §I | macOS `__MACOSX` metadata folder in ZIP → load error, must delete | build | P8 | |
| EDGE-21 | 01 §I | Mobile browsers unsupported; Safari only Partial MV3 not tested; Firefox tab-groups incompatible | cross-browser | P8 | DIM05-R1 |
| EDGE-22 | 02 Dim06/08 | URL-encoded magnet hrefs; javascript: URLs containing magnets; data-* attrs; base32 hashes | detection | P2 | DIM06/08 |
| EDGE-23 | 02 Dim07 | Empty/invalid bencode, missing info, leading zeros, neg-zero, out-of-order keys, unicode/binary filenames, unterminated structures | parsing | P2 | TST bencode |
| EDGE-24 | 02 Dim05 | groupId reuse across sessions; incognito groups don't persist; pinned tabs auto-unpinned; max ~32-64 groups/window | tab-groups | P5 | DIM05 |

## 6. Security / STRIDE Controls

| ID | Source | Control | Category | Phase | Notes |
|---|---|---|---|---|---|
| SEC-01 | 01 §N; 02 Dim11 | Threat model: credential theft, MITM, XSS, privilege escalation, fingerprinting | security | P1 | DIM11-R2 |
| SEC-02 | 02 Dim11 S | Spoofing: cert pinning/HTTPS, origin validation, isolated world, magnet hash validation | security | P1/P4 | |
| SEC-03 | 02 Dim11 T | Tampering: store-signed packages, HTTPS/HSTS, AES-GCM, infohash validation | security | P1/P8 | |
| SEC-04 | 01 §N; 02 Dim11 I | Info disclosure: AES-256-GCM creds; minimal matches no all_urls; restrict web_accessible_resources + use_dynamic_url; sender validation; no telemetry | security | P1/P4 | FR-013 |
| SEC-05 | 02 Dim11 D/E | DoS: client rate-limit, document_idle, storage quotas; EoP: sender validation + action allow-list, no eval, strict CSP | security | P1/P4 | |
| SEC-06 | 01 §N; 02 Dim11 | CSP object: extension_pages `script-src 'self'; object-src 'self'; connect-src 'self' https:` | security | P1 | NFR-011; ref CSP (FND-09) |
| SEC-07 | 03 §6 | Crypto ops in Offscreen Document (Web Crypto SubtleCrypto.encrypt) + PBKDF2 key derivation | security | P4 | DIM03-R5; Firefox bg-page fallback |
| SEC-08 | 02 Dim11; 03 §6 | Network layer HTTPS-only TLS 1.2+ (except localhost); cert validation no self-signed / pinning | security | P4 | DIM11-R8 |
| SEC-09 | 03 §6 | Boba-services controls: API-key auth (X-Api-Key), Basic auth, rate-limit 100 req/min/key | security | P4 | diagram #10 |
| SEC-10 | 02 Dim06/Dim11 | Sanitize display names textContent; reject javascript:/data:/vbscript:; block dangerous ports; chunk text vs backtracking | security | P2 | DIM11-R6 |
| SEC-11 | 02 Dim11 | Privacy policy + opt-in analytics/error-reporting; no third-party sharing/selling; Limited-Use compliance | privacy | P6/P8 | DIM11-R7 |

## 7. Cross-Dimension Insights (10)

| ID | Source | Insight | Category | Phase | Notes |
|---|---|---|---|---|---|
| INS-01 | 02 Insight 1 | Zero-config discovery via well-known localhost ports (7187/7189/8080→7186) + version pings → one-click Auto-Discover | api | P4 | FR-011 |
| INS-02 | 02 Insight 2 | Unified torrent identity `{infoHash,name,source,type}`; magnet + .torrent converge on 40-char BTIH; dedup across tab group | parsing | P2 | FR-006 |
| INS-03 | 02 Insight 3 | 3-tier progressive detection: universal link scan (~90%) + site-specific selectors + text-based + MutationObserver | detection | P2 | DIM08 |
| INS-04 | 02 Insight 4 | Tab group as batch job: right-click group → extract all URLs → parse → submit batch newline-separated | tab-groups | P5 | FR-009 |
| INS-05 | 02 Insight 5 | Extension as Boba satellite ("send-to"), not management tool; use Boba auth/config; extend not duplicate UI (~30% less code) | api | P1/P4 | architecture decision |
| INS-06 | 02 Insight 6 | Offline-aware queue; navigator.onLine unreliable for LAN → proactive `/app/version` ping 30 s via alarms + persistent queue | queue | P4 | FR-014; DIM09-R7 |
| INS-07 | 02 Insight 7 | Privacy-first activeTab + optional host perms + scripting.executeScript on demand (MEDIUM — reviewers may prefer declared host perms) | security | P1 | OQ-09 decision |
| INS-08 | 02 Insight 8 | Multi-client gateway: TorrentClient interface (qBt/Transmission/Deluge/rTorrent) | data-model | **v2** | DEFERRED — adds complexity; v1 leaves seam, targets Boba only |
| INS-09 | 02 Insight 9 | Real-time badge sync: poll `/sync/maindata` incremental RID → badge count/color | ui | P3/P4 | FR-015 |
| INS-10 | 02 Insight 10 | Enterprise-grade testing: 80%+ coverage, real-Boba-in-Docker E2E, security scanners, signed releases | testing | P7 | TST-15; Boba mandate |

## 8. Cross-Verification Conflicts & Low-Confidence Items

| ID | Source | Item | Category | Phase | Notes |
|---|---|---|---|---|---|
| CV-01 | 02 cross-verif C1 | Auth for Boba APIs: cookie (qBt direct) AND JWT/API-key (Boba own) — support BOTH | security/api | P4 | RESOLVED both valid; FR-012 |
| CV-02 | 02 cross-verif C2/C3 | Build tool WXT (built on Vite); MV3 everywhere (WXT handles FF Event Pages) | build/cross-browser | P1 | RESOLVED |
| CV-03 | 02 cross-verif low | qBt API-key Bearer only v5.2.0+; cookie baseline | api | P4 | low-confidence; DIM02-R3 |
| CV-04 | 02 cross-verif low/C4 | Boba SSE path `/api/v1/search/stream/{id}` not confirmed in official docs; ports user-configurable | api | P4 | confirm vs live OpenAPI (OQ-12) |
| CV-05 | 02 cross-verif low | Firefox E2E Playwright extension-ID extraction limits; side panel Chrome 114+ limits | testing/ui | P7/v2 | TST-03; DIM10-R5 |

## 9. Foundation / Source-Layer Facts (load-bearing for the port)

| ID | Source | Fact / Requirement | Category | Phase | Notes |
|---|---|---|---|---|---|
| FND-01 | 04 §1 | Reference name `bobalink` v1.0.0 MIT (impl-plan says Apache-2.0 — OQ-10); rename for Boba (OQ naming) | build | P1 | LICENSE + name decision |
| FND-02 | 04 §2 | host_permissions 7187/7189/8080 — must change 8080→7186 (real qBt proxy) | cross-browser/api | P1 | OQ-01 critical |
| FND-03 | 04 §3 | TS strict posture: all strict flags + noUncheckedIndexedAccess + exactOptionalPropertyTypes; zero any (no-explicit-any error) | build | P1 | NFR-MAINT |
| FND-04 | 04 §3 | ESLint type-aware: no-floating-promises/no-misused-promises error; no-console warn (allow error/warn/info) | build | P1 | NFR-009 |
| FND-05 | 04 §3 | Jest preset ts-jest ESM jsdom; coverage 80%; collectCoverageFrom EXCLUDES popup/options/content/background/index.ts | testing | P7 | TST-15 must include UI |
| FND-06 | 04 §3 | Playwright baseURL chrome-extension://test-id (placeholder); --load-extension=./dist; chromium+firefox projects | testing | P7 | TST-02; global-setup absent |
| FND-07 | 04 §2 | content_scripts matches `<all_urls>` run_at document_idle (ref) — reconcile with minimal-perms | detection/security | P1/P3 | DIM11-R4 conflict |
| FND-08 | 04 §2; 05 §9 | ref CSP connect-src localhost 7187/7189/8080; permissions include scripting (DIM11 says avoid) | security | P1 | OQ-09 |
| FND-09 | 04 §6 | Regex set: MAGNET_REGEX/MAGNET_VALIDATION/INFOHASH/TORRENT_FILE/INFOHASH_HEX/BASE32/DN/TR | parsing | P2 | FR-001/002/003 |
| FND-10 | 04 §6; 05 §8 | DEFAULT_PORTS FastAPI 7187/Go 7189/qBt 8080; DEFAULT_URLS; QBITTORRENT_ENDPOINTS map | api | P1/P4 | OQ-01 |
| FND-11 | 04 §6 | Timing: DEBOUNCE MUTATION 500/AUTO_SCAN 1000; REQUEST_TIMEOUTS DEFAULT 15000/AUTH 10000/ADD 30000/DISCOVERY 3000; RETRY max 3 base 1000 max 30000 jitter 0.3; RATE_LIMIT 10/1000ms | api/detection | P2/P4 | config drift (OQ-19) |
| FND-12 | 04 §6 | STORAGE_KEYS all bobalink_ prefixed (CONFIG/AUTH_STATE/CREDENTIALS/DETECTED/HISTORY/QUEUE/HEALTH/KEY_MATERIAL); only CONFIG/QUEUE/HEALTH actually written | data-model | P1 | unused keys (OQ) |
| FND-13 | 04 §6 | ENCRYPTION AES-GCM 256, IV 12B, salt 16B, PBKDF2 SHA-256 100000 iters, key version 1; passphrase source UNDEFINED in foundation | security | P4 | OQ-15 critical |
| FND-14 | 04 §6 | BADGE_COLORS (HEALTHY #4CAF50/DEGRADED #FF9800/ERROR #F44336/SCANNING #2196F3/DETECTED #9C27B0/DEFAULT); ICON_SIZES 16/32/48/128 | ui | P6 | FR-015/FR-021 |
| FND-15 | 04 §4b | TS types: MagnetInfo, TorrentFile, ParsedTorrent, DetectedTorrent, SendResult, PageScanResult, ServerConfig(28 fields), ExtensionConfig, DEFAULT_CONFIG, AuthMethod, AutoDiscoveryConfig | data-model | P1 | type duplication (OQ) |
| FND-16 | 04 §5 | shared libs: crypto (encrypt/decrypt/sha256/generateSecurePassphrase), errors (BobaLinkError+8 subclasses), events (TypedEventEmitter 13-event EventMap), logger, storage (NamespacedStorage), utils (debounce/throttle/TokenBucket/retryWithBackoff/yieldToBrowser/processInChunks) | data-model | P1 | foundation modules |
| FND-17 | 05 §2.1 | BobaAPIClient: login/logout/getVersion/addTorrentFromMagnet/addTorrentFromFile/getTorrents/deleteTorrents/pauseTorrents/resumeTorrents; requestWithRetry+rate-limit+timeout | api | P4 | FR-007/008/024/025 |
| FND-18 | 05 §2.2 | AuthHandler 4 methods (none/cookie/api_key/basic); createCredentialsFromConfig decrypt point; MAX_CONSECUTIVE_FAILURES 3 | security/api | P4 | FR-012; §11.4.10 |
| FND-19 | 05 §2.3 | OfflineQueue: DEFAULT_MAX_SIZE 50, PROCESS_INTERVAL 60000, ITEM_SEND_DELAY 500; enqueue FIFO evict/dequeue/processQueue/startAutoProcessing | queue | P4 | FR-014; ref max 50 vs spec 1000 (OQ-19); auth-gap (OQ) |
| FND-20 | 05 §2.4 | HealthChecker: thresholds healthy<2000/degraded<5000, MAX_FAILURES 2; checkServer/checkAllServers/testConnection/autoDiscover(ports 8080/7187/7189) | api | P4 | FR-024; FR-011 |
| FND-21 | 05 §2.5 | qBitTorrentAdapter: sendTorrent/sendTorrents (250 ms delay)/addTorrentFile/buildAddOptions/mapContentLayout | api | P4 | FR-007/008 |
| FND-22 | 05 §3 | bencode (zero-dep Uint8Array, sorted keys, sha1), magnet (parseMagnetUri xt/dn/tr/ws/xl/xs/kt/as/mt + base32ToHex), torrent-file (parseTorrentFile infohash=sha1(encode(info))) | parsing | P2 | FR-003/004/005; re-encode caveat |
| FND-23 | 05 §3 (note) | .torrent parser fully built but NEVER invoked (dead code) — sends upload raw File | parsing | P4 | wire for dedup (OQ) |
| FND-24 | 05 §4 | Scanner: BaseScanner (shadow-DOM querySelectorAllDeep, maxElements 10000), LinkScanner (site-specific+generic), TextScanner (TreeWalker), ScannerOrchestrator (MutationObserver debounce 500, per-site override, yieldToBrowser) | detection | P2/P3 | FR-001/002; INS-03 |
| FND-25 | 05 §4 (note) | NO chrome.tabGroups usage in ref; only intra-tab yieldToBrowser + per-tab tabTorrents Map — tab-group batching is net-new | tab-groups | P5 | OQ-17; FR-009 |
| FND-26 | 05 §4.5 | Two overlapping selector tables: constants.SITE_SELECTORS (~21 domains, used by LinkScanner) vs site-db.SITES (15 richer, used only for debounce) — reconcile | detection | P2 | OQ; INS-03 |
| FND-27 | 05 §5 | Message protocol: ExtensionMessage{type,payload,requestId}; background handles scan-result/get-detected/send-torrent/get-config/set-config/health-check/test-connection/auto-discover/authenticate/scan-page/open-dashboard/queue-status/queue-process | api | P3 | declared-but-unrouted types (OQ) |
| FND-28 | 05 §6 | Background SW: lifecycle onInstalled/onStartup, initialize, initializeApiClient, sendTorrents, context menus, commands, alarms (keepalive ~20 s / health 5 min), badge/notifications, storage listeners | cross-browser | P3 | DIM03-R2 |
| FND-29 | 04 §2; 05 §6 | commands: send-to-boba Ctrl+Shift+B, scan-page Ctrl+Shift+S, open-dashboard Ctrl+Shift+D (ref ships 3, differs from FR-017 B/L/G) | ui | P3 | OQ-08 |
| FND-30 | 05 §9; 05 banner | §11.4.10 BLUFF: options encrypts with FIXED passphrase "bobalink-extension"; background decrypts with EMPTY "" — broken-by-design, MUST replace | security | P4 | OQ-15 critical |
| FND-31 | 05 §2.5 | fetch uses credentials:include/same-origin (qBt SID needs it) — conflicts DIM11-R8 credentials:omit — reconcile | security/api | P4 | DIM11-R8 |
| FND-32 | 05 §6 | Context menus bobalink-send (magnet/.torrent link patterns) / bobalink-scan / bobalink-dashboard | ui | P3 | FR-016 |
| FND-33 | 05 §7.1 | Popup controls: status dot, Select All/Deselect/Refresh, torrent list (checkbox/name/type/infohash16/Sent), empty-state Scan Page, Send to Boba, progress overlay | ui | P3 | FR-023; DIM10-R1 |
| FND-34 | 05 §7.2 | Options sections Servers/General/Advanced/About; server modal (name/url/auth/category/savepath/Test Connection); Auto Discovery card; General+Advanced toggles; Reset All | ui | P3 | FR-023 |
| FND-35 | 04 §4a | SQL dual-storage model: sql.js-over-storage.local (9 tables) vs STORAGE_KEYS JSON-blob + NamespacedStorage — pick one source of truth | data-model | P1 | OQ dual-storage |

## 10. Test-Type Coverage Requirements (toward 100% per §11.4.27)

| ID | Source | Requirement | Category | Phase | Notes |
|---|---|---|---|---|---|
| TST-01 | 06 §types 1 | Integration: real parser→queue→api-client→live qBt/proxy (7186/7187); no mocks outside unit | testing | P7 | §11.4.27(A) |
| TST-02 | 06 §types 2 | E2E functional: load real built MV3 bundle, resolve real ext id, drive popup/options/content with user-observable assertions | testing | P7 | fixture builds dist + captures id (OQ) |
| TST-03 | 06 §types 3 | Automation/autonomous QA: self-driving N×-rerunnable (§11.4.98/§11.4.50); HelixQA banks | testing | P7 | §11.4.116 sync channel |
| TST-04 | 06 §types 4 | Security/penetration: credential-leak audit (§11.4.10), XSS via magnet/dn, CSP, perm-scope, host-perm abuse, malformed injection, SID handling, crypto-at-rest | security/testing | P7 | SEC-xx |
| TST-05 | 06 §types 5 | DDoS/load: 1000s magnet links/page, rapid scan cycles, queue enqueue burst, API flood/rate-limit under load | testing | P7 | §11.4.85 |
| TST-06 | 06 §types 6 | Scaling: large .torrent files, 1000s-item queue+persistence, large detected-set render, many servers | testing | P7 | NFR-SCAL |
| TST-07 | 06 §types 7 | Chaos: storage failure/corruption mid-write, network drop/timeout/reorder, SW termination mid-op, corrupt-state recovery (§11.4.85 closed-set) | testing | P7 | error-injecting mock needed |
| TST-08 | 06 §types 8 | Stress: sustained N≥100/≥30 s, concurrent N≥10 enqueues/scans, boundary inputs, p50/p95/p99 latency | testing | P7 | §11.4.85 |
| TST-09 | 06 §types 9 | Performance: parse-time benchmarks, scan latency heavy DOM, popup render — captured evidence | performance/testing | P7 | NFR-001..006 |
| TST-10 | 06 §types 10 | Benchmark: formal suite + baselines + regression detection | testing | P7 | |
| TST-11 | 06 §types 11 | UI tests: rendering correctness, badge counts, list render, modal state changes | testing | P7 | beyond DOM-presence |
| TST-12 | 06 §types 12 | UX tests: detect→select→send happy path, error feedback, empty/loading/error states, a11y, keyboard nav, shortcuts | testing | P7 | FR-020 |
| TST-13 | 06 §types 13 | Challenges (`./challenges/scripts/`): real built ext vs real qBt+proxy, user-observable outcomes | testing | P7 | §11.4.27(B) |
| TST-14 | 06 §types 14 | HelixQA banks + autonomous QA sessions with captured evidence | testing | P7 | §11.4.27 |
| TST-15 | 06 §types 15; §critical | Anti-bluff remediation: fix ref bluffs — `expect(true).toBe(true)` Auth/auto-proc blocks, crypto-copy-not-module, non-functional e2e (hardcoded test-id), dead-asserts; every test fails vs no-op stub; bring UI/entrypoints INTO coverage | testing | P7 | §11.4/§11.4.1; reference unit+e2e is starting floor |
| TST-16 | 06 fixtures | Wire `invalidMagnets` (7 negative cases) + magnets.json/base32 fixtures; reference test inventory (bencode/magnet/torrent-file/api-client/queue/scanner strong; crypto thorough-but-copy) | testing | P7 | EDGE-23 |

## 11. Build / Release / Distribution

| ID | Source | Requirement | Category | Phase | Notes |
|---|---|---|---|---|---|
| BLD-01 | 01 §M.1 | Build: npm install; npm run dev (WXT HMR); npm run build → chrome/firefox/opera/edge MV3 prod; per-browser `wxt build -b` | build | P8 | DIM12-R1 |
| BLD-02 | 01 §M.2 | Test commands: jest --coverage (80%), playwright; coverage thresholds; per-file targets | testing | P7 | TST-15 |
| BLD-03 | 01 §M.3 | Release: main→release branch→bump manifest→CHANGELOG→full suite→git tag→build all→GitHub Release→submit stores | build | P8 | §K.1 strip auto-submit (CI/CD) |
| BLD-04 | 01 §M.4; 02 Dim12 | Distribution: Chrome Web Store CRX ($5), Firefox AMO XPI, Opera CRX, Edge, GitHub ZIP; per-store assets/2FA/review SLA | build | P8 | DIM12-R4; DIM04-R2 |
| BLD-05 | 01 §M.5 | Git: GitHub Flow; Conventional Commits (feat/fix/.../scopes); branch prefixes — Boba: SSH remotes not HTTPS | build | P1/P8 | FND-01 repo URL HTTPS |
| BLD-06 | 03 §7 | Pipeline stages Code→Lint→Test(≥80%)→Build→Package→Deploy; quality gates 0 ESLint errors/valid manifest/<5MB | build | P7/P8 | diagram #11 |
| BLD-07 | 02 Dim12; 04 §7 | release-please + Husky pre-commit + lint-staged + web-ext sign — Boba: DROP Husky (git hooks forbidden) | build | P8 | §K.1 |
| BLD-08 | 01 §K.1; 03 §9; 04 §7; 06 §10 | **CI/CD REMOVAL (Boba Hard-Stop):** strip ALL `.github/workflows/*.yml` (ci.yml, release.yml), Husky hooks, "enforced in CI", auto store-submission → convert to manual `./ci.sh`-style script | build | P8 | MANDATORY constraint |
| BLD-09 | 04 §7 | Manual version-bump touches package.json + wxt.config manifest + both SQL files + app_metadata/extension_config schema_version rows together | build | P8 | release.yml sed |

## 12. Open Questions / Ambiguities (consolidated, for conductor)

| ID | Source | Question | Category | Phase | Notes |
|---|---|---|---|---|---|
| OQ-01 | 01 §T1; 03 §9.4; 04 §8.1; 05 §9.2 | Real Boba port mapping: 8443/8080→7186/7187/7189; qBt direct→proxy 7186? Boba REST/SSE→7187? search→7189? Re-point all discovery defaults | api | P1/P4 | HIGH/critical |
| OQ-02 | 01 §T2; 03 §9.1; 04 §7; 06 §10 | CI/CD removal shape — manual `./ci.sh` | build | P8 | HIGH; BLD-08 |
| OQ-03 | 01 §T3; 06 §1 | Jest vs Vitest (Boba frontend uses Vitest; crypto.test.ts already Vitest) | testing | P7 | MED |
| OQ-04 | 01 §T4; 01 §O.3 | Two divergent source layouts (src/parser/scanner/api/shared vs src/modules/utils/content-scripts) — pick canonical | data-model | P1 | MED |
| OQ-05 | 01 §T5; 01 §P.1 | Two divergent phase plans (plan.md 10 vs impl-plan 8) — use 8-phase | build | P1 | MED; this matrix uses 8 |
| OQ-06 | 01 §T6; 01 §D.7 | Data-model vocabulary drift: source_type adds torrent-url; status completed vs dead-letter; auth_method adds none drops custom-header — reconcile enums | data-model | P1 | MED |
| OQ-07 | 01 §T7 | Magnet param superset: FR-003 xt/dn/tr/xl/ws/x.pe vs impl-plan xs/as/kt/mt (no x.pe) — which implemented | parsing | P2 | LOW; ref impl xt/dn/tr/ws/xl/xs/kt/as/mt |
| OQ-08 | 01 §T8; 04 §2; 05 §6 | Keyboard-shortcut count 3 vs 4; ref ships B/S/D, FR-017 says B/L/G; Ctrl+Shift+L collision | ui | P3 | LOW; FND-29 |
| OQ-09 | 01 §T9; 02 INS-07; 04 §8 | host_permissions scope: https://*/ (ref) vs activeTab minimal (NFR-012) — store-review/privacy | security | P1 | LOW-MED |
| OQ-10 | 01 §T10; 04 §1 | LICENSE: impl-plan Apache 2.0 vs package.json MIT — confirm | build | P1 | LOW |
| OQ-11 | 01 §T11 | Naming: "BobaLink" reference name — confirm Boba repo extension name + icon | build | P1 | LOW |
| OQ-12 | 01 §T12; 02 §509-510; 03 §9.6 | Search/SSE scope: does Boba 7187 expose `/api/v1/torrents/search`+SSE as spec, or call existing merge routes? Confirm vs live `/openapi.json` | api | P4 | MED; CV-04 |
| OQ-13 | 01 §T13 | Boba `/api/v1/health` vs real `/health` — confirm path/port | api | P4 | LOW-MED |
| OQ-14 | 04 §8.3; 05 §9.3 | Dual storage model (sql.js 9-table vs JSON-blob NamespacedStorage) — one source of truth | data-model | P1 | FND-35 |
| OQ-15 | 04 §8.2; 05 §9.1 | Encryption passphrase provenance UNDEFINED; ref fixed/empty-passphrase BLUFF — design real key source (master pw prompt / OS keychain / delegate to boba-jackett /config/boba.db) | security | P4 | CRITICAL §11.4.10; FND-30 |
| OQ-16 | 05 §9.9 | Time-salted detection ids (Date.now() in hashString) → unreliable cross-scan dedup → use infohash-derived stable ids | parsing | P2 | FR-006 |
| OQ-17 | 05 §9.8; 04 §4.5 | Tab-group batching does NOT exist in ref — net-new design | tab-groups | P5 | FND-25; FR-009 |
| OQ-18 | 05 §9.2 | Boba integration only port-deep — client speaks only qBt WebUI v2; no merge-search/proxy(7186)/boba-jackett(7189) code; define how ext reaches Boba's own endpoints | api | P4 | DIM01-R2 |
| OQ-19 | 01 §T6; 05 §2.3; 04 §8.5 | Config-value drift: queue max 50(ref)/1000(spec)/100(Dim09); retries 3/5; RATE_LIMIT 10 vs DB seed 30; autoScanDelay 2000 vs DEBOUNCE 1000 — pick canonical | queue/api | P4 | FR-014/025 |
| OQ-20 | 05 §9.5 | Offline queue processQueue never authenticates → 403 loop against authed server — wire auth | queue | P4 | FND-19 |
| OQ-21 | 05 §9.10/9.11 | Two get-detected response shapes; unrouted message types (send-result/get-auth-state/health-result/show-notification/update-badge/torrent-detected/selection-change) — unify/decide | api | P3 | FND-27 |
| OQ-22 | 05 §9.3/9.4/9.12 | set-cookie SID parsing brittle across CORS; CORS/host-perm story for cross-origin localhost; manifest/commands/icon rasterization to author | api/build | P3/P4 | DIM07-R4 |
| OQ-23 | 06 §OQ | E2E extension-loading fixture (build dist → persistent context --load-extension → capture id); Chromium-only vs Firefox MV3; global-setup/teardown contract; live backends for integration | testing | P7 | TST-02/03 |
| OQ-24 | 03 §9.2/9.3/9.5/9.7 | Single-send routing dual-write FastAPI+Go ambiguity; batch endpoint path (`/api/torrents/batch` vs direct qBt); extension_config↔discovered FK conceptual; X-Api-Key+Basic together vs per-service | api/data-model | P4 | diagram inconsistencies |

---

## COVERAGE LEDGER

### Item counts by category (every row classified)

| Category | Count |
|---|---|
| detection | 22 |
| parsing | 27 |
| api | 41 |
| queue | 12 |
| ui | 24 |
| security | 35 |
| privacy | 4 |
| i18n | 3 |
| build | 18 |
| data-model | 22 |
| cross-browser | 11 |
| tab-groups | 12 |
| performance | 12 |
| reliability | 3 |
| scalability | 4 |
| maintainability | 1 |
| testing | 23 |
| **(rows are multi-tagged; primary-category tallies above)** | |

### Item counts by section (authoritative row totals)

| Section | Rows |
|---|---|
| 1. Functional Requirements | 25 (FR-001..FR-025) |
| 2. Non-Functional Requirements | 15 (NFR-001..NFR-015) + 4 scalability/maint (NFR-SCAL-1..3, NFR-MAINT-1) |
| 3. Research-Dimension Decisions | 56 (DIM01-R1..DIM12-R4 across all 12 dims) |
| 4. ER Entities / Data Model | 8 (6 ER entities + ER-REL + ER-SQL-extra) |
| 5. Edge Cases | 24 (EDGE-01..EDGE-24) |
| 6. Security / STRIDE | 11 (SEC-01..SEC-11) |
| 7. Insights | 10 (INS-01..INS-10) |
| 8. Cross-Verification | 5 (CV-01..CV-05) |
| 9. Foundation Facts | 35 (FND-01..FND-35) |
| 10. Test-Type Coverage | 16 (TST-01..TST-16) |
| 11. Build / Release | 9 (BLD-01..BLD-09) |
| 12. Open Questions | 24 (OQ-01..OQ-24) |
| **TOTAL traceable items** | **245** |

### v1 vs v2 split

- **v1 (in-scope for initial release):** 240 items — all FRs, all NFRs, all dimension decisions except deferred, all ER entities except search_cache, all edge cases, all security, 8 of 10 insights, all foundation facts, all test types, all build (CI/CD converted to manual), all open questions resolved during build.
- **v2 (explicitly deferred):** 5 items.

### Items intentionally deferred to v2 (with rationale)

| ID | Item | Rationale |
|---|---|---|
| INS-08 | Multi-Client Gateway (TorrentClient interface: Transmission/Deluge/rTorrent adapters) | MEDIUM confidence; adds complexity; v1 targets Boba/qBittorrent only. v1 architecture leaves a `TorrentClient` seam but ships ONE adapter. (file 02 Insight 8; file 01 §509 OQ-7.) |
| ER-search_cache | Search-result cache entity (TTL'd, standalone, no FK) | Search aggregation is gated to Boba 1.2+ (file 01 §R feature-availability); not needed for the core detect→send v1 flow. Storage backend unresolved (OQ-12/OQ-24). |
| DIM01-R2 (search subset) | Boba merge-search `/api/v1/search` + SSE `/api/v1/search/stream/{id}` live-progress in popup | "Search aggregation = Boba 1.2+ only"; SSE progress = Boba 1.1+ only (file 01 §R). v1 ships detect→send + qBt-direct + basic health; rich search/SSE is a post-v1 enhancement. (Core `/api/v1/download` + `/api/v1/magnet` stay v1.) |
| DIM10-R5 | Side panel (Chrome 114+, open 116+, close 141+; cannot auto-open) | LOW confidence (CV-05); browser-floor too high vs Chrome 88 target; popup covers v1 UX. Optional surface. |
| DIM02-R3 / CV-03 | qBittorrent API-key (Bearer `qbt_`) auth, v5.2.0+ only | LOW confidence; only on newest qBt; cookie auth is the safe v1 baseline. API-key path deferred until version floor justifies it. |

> NOTE: deferral means "not built in v1," NOT "dropped." Each carries a v1 seam (TorrentClient interface, search-cache storage decision, SSE client stub, side-panel optional entry, API-key auth branch) so v2 is additive.

### Cross-check: completeness of the mandated baselines

- **25 FR — ALL represented:** FR-001…FR-025 each have exactly one row (§1). ✓
- **15 NFR — ALL represented:** NFR-001…NFR-015 each have one row; scalability/maintainability sub-clauses captured as NFR-SCAL-1..3 + NFR-MAINT-1 (§2). ✓
- **12 Dimensions — ALL represented:** DIM01 (4), DIM02 (4), DIM03 (5), DIM04 (4), DIM05 (3), DIM06 (4), DIM07 (5), DIM08 (6), DIM09 (9), DIM10 (6), DIM11 (10), DIM12 (4) — every dimension has ≥3 consolidated decision rows; 56 total (§3). ✓
- **6 ER entities — ALL represented:** ER-extension_config, ER-discovered_torrents, ER-download_queue, ER-server_config, ER-send_history, ER-search_cache; + ER-REL relationships + ER-SQL-extra (app_metadata/site_selectors/queue_log/statistics) superset (§4). ✓
- **Edge cases:** all 16 file-01-§I cases (EDGE-01..21 incl. multi-item lines) + Dim06/07/05/08 cases (EDGE-22..24) (§5). ✓
- **Insights:** all 10 (INS-01..10) (§7). ✓
- **Cross-verification:** 4 conflicts + low-confidence set (CV-01..05) (§8). ✓

### Items that could NOT be placed (OPEN)

**NONE.** Every FR, NFR, dimension-decision, ER entity, edge case, insight, cross-verification conflict, foundation fact, test-type, build step, and open question from all six analysis files has been assigned a stable ID and a row. No source item is unaccounted for.

The reference-deliverable internal inconsistencies (dual source layouts, dual storage models, two phase plans, port mismatches, config-value drift, the §11.4.10 fixed/empty-passphrase bluff, dead/unrouted code, missing E2E fixtures, CI/CD-vs-Boba-Hard-Stop) are NOT untraceable items — they are captured as explicit OQ-xx / FND-xx rows requiring a conductor decision during the corresponding phase, per §11.4.118 enumerated coverage and §11.4.66 interactive clarification.

---

*End of C-traceability-matrix.md — anti-skip backbone for the implementation plan.*
