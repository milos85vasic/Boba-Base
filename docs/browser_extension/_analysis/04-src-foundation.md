# 04 — src foundation extraction

> Source: `docs/research/browser_extension/Browser Torrent Extension Guide/src/`
> Reference browser extension **BobaLink** (WXT + TypeScript + Manifest V3). This is the
> foundation layer (build/config + data layer + shared libs + types). Every file below was
> read IN FULL. Exact values are quoted with file + line citations.

## Files read

| File | Lines |
|------|-------|
| `package.json` | 61 |
| `tsconfig.json` | 37 |
| `wxt.config.ts` | 169 |
| `jest.config.ts` | 143 |
| `playwright.config.ts` | 133 |
| `.eslintrc.json` | 56 |
| `.prettierrc` | 14 |
| `_locales/en/messages.json` | 118 |
| `.github/workflows/ci.yml` | 55 |
| `.github/workflows/release.yml` | 416 |
| `sql/schemas.sql` | 276 |
| `sql/migrations/001_initial.sql` | 267 |
| `src/types/api.ts` | 486 |
| `src/types/config.ts` | 232 |
| `src/types/torrent.ts` | 223 |
| `src/shared/constants.ts` | 403 |
| `src/shared/crypto.ts` | 292 |
| `src/shared/errors.ts` | 342 |
| `src/shared/events.ts` | 175 |
| `src/shared/logger.ts` | 167 |
| `src/shared/storage.ts` | 248 |
| `src/shared/utils.ts` | 366 |

---

## 1. Package metadata, dependencies, npm scripts (`package.json`)

- **name** `bobalink`, **version** `1.0.0`, **type** `module`, **license** `MIT`, **author** `Boba Project`.
- **engines.node** `>=20.0.0`.
- **repo** `https://github.com/boba-project/bobalink.git` (HTTPS — note Boba constitution mandates SSH; placeholder only).
- **description**: "Browser extension that detects torrent files and magnet links, sending them to Boba Project's qBitTorrent dashboard".

### Dependencies (1)
| Package | Version |
|---------|---------|
| `webextension-polyfill` | `^0.12.0` |

### devDependencies (15)
| Package | Version |
|---------|---------|
| `@playwright/test` | `^1.49.0` |
| `@types/chrome` | `^0.0.287` |
| `@types/jest` | `^29.5.14` |
| `@types/node` | `^22.10.0` |
| `@types/webextension-polyfill` | `^0.12.1` |
| `@typescript-eslint/eslint-plugin` | `^8.18.0` |
| `@typescript-eslint/parser` | `^8.18.0` |
| `@wxt-dev/auto-icons` | `^1.0.2` |
| `eslint` | `^9.17.0` |
| `jest` | `^29.7.0` |
| `jest-environment-jsdom` | `^29.7.0` |
| `prettier` | `^3.4.0` |
| `ts-jest` | `^29.2.0` |
| `ts-node` | `^10.9.2` |
| `typescript` | `^5.7.0` |
| `wxt` | `^0.19.0` |

### npm scripts (all 15)
| Script | Command |
|--------|---------|
| `dev` | `wxt` |
| `dev:firefox` | `wxt -b firefox` |
| `build` | `wxt build` |
| `build:firefox` | `wxt build -b firefox` |
| `zip` | `wxt zip` |
| `zip:firefox` | `wxt zip -b firefox` |
| `compile` | `tsc --noEmit` |
| `lint` | `eslint src/ --ext .ts` |
| `lint:fix` | `eslint src/ --ext .ts --fix` |
| `format` | `prettier --write "src/**/*.ts"` |
| `format:check` | `prettier --check "src/**/*.ts"` |
| `test` | `jest --coverage` |
| `test:watch` | `jest --watch` |
| `test:e2e` | `playwright test` |
| `test:e2e:ui` | `playwright test --ui` |
| `postinstall` | `wxt prepare` |

> Note: `package.json` references `wxt build` (chrome default) + `build:firefox`. The **release.yml** workflow references `build:chrome` / `build:firefox` scripts that **do not exist** in `package.json` (drift in the reference repo — flagged for the plan).

---

## 2. Manifest / permissions / CSP config (`wxt.config.ts` + `_locales/en/messages.json`)

WXT generates `manifest.json` from `wxt.config.ts`. Extracted manifest config:

- **manifest_version**: `3`
- **name**: `__MSG_extName__` → "BobaLink"
- **description**: `__MSG_extDescription__`
- **version**: `1.0.0`
- **default_locale**: `en`
- **minimum_chrome_version**: `"109"`
- **outDir**: `dist`

### Permissions (6)
`storage`, `alarms`, `notifications`, `activeTab`, `scripting`, `contextMenus`

### host_permissions (3) — the load-bearing endpoint set
- `http://localhost:7187/*` — Boba FastAPI server
- `http://localhost:7189/*` — Boba Go server
- `http://localhost:8080/*` — qBitTorrent WebUI

> ⚠️ Mismatch vs the real Boba port map: actual qBitTorrent WebUI proxy is **7186** (CLAUDE.md port table), merge service **7187**, boba-jackett **7189**. The extension hardcodes **8080** for qBitTorrent and assumes FastAPI on 7187 / Go on 7189. The plan must reconcile (qBittorrent proxy is 7186, not 8080).

### action (toolbar popup)
- `default_popup`: `popup/index.html`
- `default_icon`: 16 → `icon-16.png`, 32 → `icon-32.png`
- `default_title`: `__MSG_extName__`

### background (service worker)
- `service_worker`: `background.js`
- `type`: `module` (ES module service worker)

### content_scripts (1 entry)
- `matches`: `["<all_urls>"]`
- `js`: `["content-scripts/content.js"]`
- `css`: `["content-scripts/content.css"]`
- `run_at`: `document_idle`

### options_page
- `options/index.html`

### web_accessible_resources
- resources `["assets/*"]`, matches `["<all_urls>"]`

### content_security_policy (extension_pages)
```
default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self' http://localhost:7187 http://localhost:7189 http://localhost:8080; img-src 'self' data:;
```
- Strict: no inline scripts (`script-src 'self'`); `style-src` allows `'unsafe-inline'`; `connect-src` restricted to the three localhost backends; `img-src` allows `data:` URIs.

### commands (keyboard shortcuts, 3)
| Command | Default | Mac | Description (msg) |
|---------|---------|-----|------|
| `send-to-boba` | `Ctrl+Shift+B` | `Command+Shift+B` | `__MSG_cmdSendToBoba__` |
| `scan-page` | `Ctrl+Shift+S` | `Command+Shift+S` | `__MSG_cmdScanPage__` |
| `open-dashboard` | `Ctrl+Shift+D` | `Command+Shift+D` | `__MSG_cmdOpenDashboard__` |

### WXT build options
- `autoIcons.baseIconPath`: `src/assets/icon.svg` (auto-generates icon sizes from one SVG)
- `dev.port`: `3000`
- `runner.disabled`: `true` (no auto browser launch)

### i18n messages (`_locales/en/messages.json`) — 28 keys
Key UI strings: `extName`="BobaLink", `extDescription`, command descriptions (`cmdSendToBoba`/`cmdScanPage`/`cmdOpenDashboard`), popup (`popupTitle`="BobaLink - Detected Torrents", `noTorrentsDetected`, `sendToBoba`, `scanning`, `sending`, `sendSuccess`, `sendFailed`), connection states (`connectionOnline`="Connected", `connectionOffline`="Disconnected", `notConfigured`="No server configured"), options page sections (`optionsTitle`, `serverSectionTitle`, `generalSectionTitle`, `advancedSectionTitle`), buttons (`addServer`, `testConnection`, `autoDiscover`, `saveChanges`, `discardChanges`), type labels (`magnetLink`, `torrentFile`), context menu (`contextMenuSend`, `contextMenuScan`, `contextMenuDashboard`).

---

## 3. TypeScript compiler config (`tsconfig.json`)

| Option | Value |
|--------|-------|
| `target` | `ES2022` |
| `module` | `ESNext` |
| `moduleResolution` | `bundler` |
| `lib` | `["ES2022","DOM","DOM.Iterable"]` |
| `jsx` | `preserve` |
| `strict` | `true` |
| `noImplicitAny` | `true` |
| `strictNullChecks` | `true` |
| `strictFunctionTypes` | `true` |
| `strictBindCallApply` | `true` |
| `strictPropertyInitialization` | `true` |
| `noImplicitReturns` | `true` |
| `noFallthroughCasesInSwitch` | `true` |
| `noUncheckedIndexedAccess` | `true` |
| `exactOptionalPropertyTypes` | `true` |
| `noUnusedLocals` | `true` |
| `noUnusedParameters` | `true` |
| `declaration` | `true` |
| `declarationMap` | `true` |
| `sourceMap` | `true` |
| `esModuleInterop` | `true` |
| `skipLibCheck` | `true` |
| `forceConsistentCasingInFileNames` | `true` |
| `resolveJsonModule` | `true` |
| `isolatedModules` | `true` |
| `types` | `["chrome","jest","node","webextension-polyfill"]` |
| `baseUrl` | `.` |
| `paths` | `~/* → src/*`, `@/* → src/*` |
| `include` | `src/**/*.ts`, `tests/**/*.ts`, `wxt.config.ts`, `jest.config.ts`, `playwright.config.ts` |
| `exclude` | `node_modules`, `dist`, `.wxt` |

Very strict TS posture (all strict flags + `noUncheckedIndexedAccess` + `exactOptionalPropertyTypes`).

### ESLint (`.eslintrc.json`)
- `parser`: `@typescript-eslint/parser`; `project: ./tsconfig.json` (type-aware lint).
- extends: `eslint:recommended`, `plugin:@typescript-eslint/recommended`, `...recommended-requiring-type-checking`, `...strict`.
- env: browser, es2022, node, webextensions, jest.
- Notable rules: `no-explicit-any` **error**; `no-floating-promises` **error**; `no-misused-promises` **error**; `prefer-nullish-coalescing` **error**; `no-console` warn (allows `error`/`warn`/`info`); `eqeqeq` error (null-ignore); `no-unused-vars` error with `^_` ignore. `tests/**` override turns off unsafe/any rules. Ignores `dist/`, `.wxt/`, `node_modules/`, `coverage/`.

### Prettier (`.prettierrc`)
`semi:true`, `trailingComma:"all"`, `singleQuote:false`, `printWidth:100`, `tabWidth:2`, `useTabs:false`, `bracketSpacing:true`, `arrowParens:"always"`, `endOfLine:"lf"`, `quoteProps:"as-needed"`, `bracketSameLine:false`, `proseWrap:"preserve"`.

### Jest (`jest.config.ts`)
- preset `ts-jest/presets/default-esm`, `testEnvironment: jsdom`, ESM (`extensionsToTreatAsEsm: [".ts"]`).
- roots `tests/unit` + `src`; testMatch `**/tests/unit/**/*.test.ts`, `**/src/**/*.test.ts`.
- moduleNameMapper mirrors tsconfig paths (`~/`, `@/`).
- **coverageThreshold global 80% (branches/functions/lines/statements)**.
- `collectCoverageFrom`: `src/**/*.ts` excluding `*.d.ts`, `index.ts`, `assets/`, `popup/`, `options/`, `content/`, `background/` (i.e. covers logic libs only — parsers/api/scanner/shared).
- setupFiles `tests/unit/chrome-mock.ts`; setupFilesAfterEnv `tests/unit/setup.ts`; `clearMocks`+`restoreMocks`; `testTimeout: 10000`; reporters `text,text-summary,lcov,html` → `coverage/`.

### Playwright (`playwright.config.ts`)
- testDir `./tests/e2e`; `fullyParallel: false`; `workers: 1` (extension state); retries 2 in CI; reporters html+list (+github in CI).
- `use.baseURL` `chrome-extension://test-id/`; trace on-first-retry; screenshot only-on-failure; video on-first-retry; viewport 1280×720.
- launchOptions load unpacked ext via `--load-extension=${EXTENSION_PATH||./dist}`.
- projects: `chromium` (channel chromium) + `firefox`.
- `webServer`: `command: npm run build`, url `http://localhost:3000`, timeout 120000.
- `globalSetup`/`globalTeardown`: `./tests/e2e/global-setup.ts` / `global-teardown.ts` (**these files do not exist in the tree** — referenced only).
- `timeout: 30000`, expect timeout 5000.

---

## 4. Data model — SQL schema + TypeScript types

### 4a. SQLite schema (`sql/schemas.sql` = `migrations/001_initial.sql`, schema v1.0.0)

Persisted via **chrome.storage.local with an sql.js wrapper** (header comment). 9 tables, ~25 indexes (header says "7" but actual index count is higher), 30 default site selectors, 25 default config rows. Migration file wraps everything in `BEGIN TRANSACTION; … COMMIT;` and adds a `migration_id='001_initial'` metadata row.

**Table 1 — `app_metadata`** (key/value app state)
| Col | Type | Constraint |
|-----|------|-----------|
| key | TEXT | PRIMARY KEY |
| value | TEXT | NOT NULL |
| updated_at | INTEGER | NOT NULL |

Seeded keys: `schema_version='1.0.0'`, `app_name='BobaLink'`, `app_version='1.0.0'`, `installed_at`, `last_db_vacuum` (migration also seeds `migration_id='001_initial'`).

**Table 2 — `extension_config`** (typed key-value settings)
| Col | Type | Constraint |
|-----|------|-----------|
| key | TEXT | PRIMARY KEY |
| value | TEXT | NOT NULL |
| data_type | TEXT | CHECK IN (`string`,`number`,`boolean`,`json`,`encrypted`) NOT NULL |
| description | TEXT | |
| updated_at | INTEGER | NOT NULL |

25 seeded config rows (key, value, data_type):
- `server.base_url`=`http://localhost:8080` (string), `server.auth_method`=`cookie` (string), `server.api_key`=`` (**encrypted**), `server.username`=`` (string), `server.password`=`` (**encrypted**)
- `download.default_category`=`` , `download.default_save_path`=``, `download.start_paused`=`false` (bool), `download.auto_manage`=`true` (bool)
- `behavior.auto_scan`=`true`, `behavior.highlight_detected`=`true`, `behavior.show_notifications`=`true`, `behavior.rate_limit_requests`=`30` (number), `behavior.max_storage_mb`=`50` (number)
- `security.require_https`=`true`, `security.encrypt_credentials`=`true`, `security.session_timeout`=`3600` (number)
- `ui.theme`=`auto`, `ui.popup_width`=`400`, `ui.popup_height`=`600`, `ui.show_tracker_list`=`true`, `ui.batch_select_default`=`true`
- `advanced.debug_mode`=`false`, `advanced.scan_interval_ms`=`2000`, `advanced.max_torrent_size_gb`=`100`

**Table 3 — `discovered_torrents`** (per-session discovery)
| Col | Type | Notes |
|-----|------|-------|
| id | TEXT | PRIMARY KEY — infoHash (40-char hex) |
| page_url | TEXT | NOT NULL |
| page_title | TEXT | |
| magnet_uri | TEXT | |
| torrent_url | TEXT | |
| torrent_data_b64 | TEXT | Base64 .torrent content |
| name | TEXT | |
| display_name | TEXT | URL-decoded for UI |
| trackers | TEXT | JSON array |
| size_bytes | INTEGER | nullable |
| source_type | TEXT | CHECK IN (`magnet-link`,`torrent-file`,`torrent-url`,`infohash`) NOT NULL |
| discovery_method | TEXT | CHECK IN (`link-scan`,`text-scan`,`site-specific`,`manual`) DEFAULT `link-scan` |
| is_private | INTEGER | DEFAULT 0 |
| detected_at | INTEGER | NOT NULL |
| sent_to_boba | INTEGER | DEFAULT 0 |
| sent_at | INTEGER | |
| boba_status | TEXT | CHECK IN (`pending`,`queued`,`sending`,`added`,`duplicate`,`error`,`retrying`) DEFAULT `pending` |
| boba_error | TEXT | |
| tab_id | INTEGER | |
| tab_group_id | INTEGER | |
| selected | INTEGER | DEFAULT 1 |
| metadata_json | TEXT | |

**Table 4 — `download_queue`** (offline support)
| Col | Type | Notes |
|-----|------|-------|
| id | INTEGER | PK AUTOINCREMENT |
| info_hash | TEXT | NOT NULL |
| magnet_uri | TEXT | |
| torrent_data_b64 | TEXT | |
| name | TEXT | |
| category | TEXT | |
| save_path | TEXT | |
| tags | TEXT | JSON array |
| add_paused | INTEGER | DEFAULT 0 |
| skip_checking | INTEGER | DEFAULT 0 |
| sequential_download | INTEGER | DEFAULT 0 |
| first_last_piece_prio | INTEGER | DEFAULT 0 |
| added_at | INTEGER | NOT NULL |
| retry_count | INTEGER | DEFAULT 0 |
| last_retry_at | INTEGER | |
| next_retry_at | INTEGER | exponential backoff |
| last_error | TEXT | |
| error_code | TEXT | |
| status | TEXT | CHECK IN (`pending`,`retrying`,`failed_permanent`,`completed`,`cancelled`) DEFAULT `pending` |
| server_url | TEXT | NOT NULL |
| server_id | INTEGER | → server_config.id |

**Table 5 — `server_config`** (multi-server)
| Col | Type | Notes |
|-----|------|-------|
| id | INTEGER | PK AUTOINCREMENT |
| name | TEXT | NOT NULL |
| base_url | TEXT | NOT NULL **UNIQUE** |
| auth_method | TEXT | CHECK IN (`none`,`cookie`,`api_key`,`basic`) NOT NULL DEFAULT `none` |
| api_key_encrypted | TEXT | |
| username | TEXT | |
| password_encrypted | TEXT | |
| is_default | INTEGER | DEFAULT 0 |
| is_reachable | INTEGER | DEFAULT 0 |
| last_check_at | INTEGER | |
| last_check_result | TEXT | CHECK IN (`success`,`auth_required`,`unreachable`,`error`) |
| qbittorrent_version | TEXT | |
| boba_version | TEXT | |
| boba_fastapi_port | INTEGER | DEFAULT **7187** |
| boba_go_port | INTEGER | DEFAULT **7189** |
| qbittorrent_port | INTEGER | DEFAULT **8080** |
| created_at | INTEGER | NOT NULL |
| updated_at | INTEGER | NOT NULL |
| notes | TEXT | |

**Table 6 — `send_history`** (immutable send log)
| Col | Type | Notes |
|-----|------|-------|
| id | INTEGER | PK AUTOINCREMENT |
| info_hash | TEXT | NOT NULL |
| name | TEXT | |
| magnet_uri | TEXT | |
| source_type | TEXT | NOT NULL |
| sent_at | INTEGER | NOT NULL |
| server_id | INTEGER | REFERENCES server_config(id) |
| server_url | TEXT | NOT NULL |
| success | INTEGER | NOT NULL (1/0) |
| response_code | INTEGER | HTTP code |
| error_message | TEXT | |
| torrent_added_hash | TEXT | hash returned by qBitTorrent |

**Table 7 — `site_selectors`** (CSS selectors per site)
| Col | Type | Notes |
|-----|------|-------|
| id | INTEGER | PK AUTOINCREMENT |
| domain_pattern | TEXT | NOT NULL (e.g. `thepiratebay.*`) |
| selector_type | TEXT | CHECK IN (`magnet-link`,`torrent-link`,`name`,`size`,`seeders`,`leechers`,`date`,`uploader`) NOT NULL |
| css_selector | TEXT | NOT NULL |
| attribute | TEXT | e.g. `href`, null for text |
| regex_filter | TEXT | optional |
| priority | INTEGER | DEFAULT 100 (lower = higher prio) |
| is_enabled | INTEGER | DEFAULT 1 |
| notes | TEXT | |

30 seeded selector rows covering: thepiratebay, 1337x (magnet+torrent), nyaa.si (magnet+torrent), rutracker (magnet+torrent), kinozal, nnm-club, iptorrents (torrent), limetorrents, torrentgalaxy, glodls, torlock, eztv, yts, rarbg, demonoid, torrentfunk, yourbittorrent, bitsearch, bt4g, solidtorrents, knaben, snowfl, bittorrent, megapeer, badasstorrents, extratorrent. Most use `a[href^="magnet:"]` @ priority 10; direct `.torrent` links @ priority 20 (or 10 for iptorrents).

**Table 8 — `queue_log`** (queue event log)
| Col | Type | Notes |
|-----|------|-------|
| id | INTEGER | PK AUTOINCREMENT |
| queue_item_id | INTEGER | REFERENCES download_queue(id) |
| action | TEXT | NOT NULL CHECK IN (`enqueue`,`retry`,`success`,`fail`,`cancel`,`skip`) |
| timestamp | INTEGER | NOT NULL |
| details | TEXT | JSON |
| error | TEXT | |

**Table 9 — `statistics`** (daily aggregates)
| Col | Type | Notes |
|-----|------|-------|
| id | INTEGER | PK AUTOINCREMENT |
| stat_type | TEXT | NOT NULL CHECK IN (`torrents_detected`,`torrents_sent`,`torrents_failed`,`api_calls`,`api_errors`,`queue_items`,`queue_retries`,`scans_performed`,`page_visits`) |
| stat_value | INTEGER | NOT NULL DEFAULT 0 |
| stat_date | TEXT | NOT NULL (YYYY-MM-DD) |
| created_at | INTEGER | NOT NULL |
| — | — | **UNIQUE(stat_type, stat_date)** |

**Indexes** (CREATE INDEX IF NOT EXISTS):
- discovered_torrents: `idx_discovered_page_url(page_url)`, `idx_discovered_status(boba_status)`, `idx_discovered_tab(tab_id)`, `idx_discovered_detected(detected_at)`, `idx_discovered_selected(selected) WHERE selected=1` (partial)
- download_queue: `idx_queue_status(status)`, `idx_queue_next_retry(next_retry_at)`, `idx_queue_hash(info_hash)`, `idx_queue_server(server_url)`
- send_history: `idx_history_hash(info_hash)`, `idx_history_date(sent_at)`, `idx_history_server(server_id)`
- extension_config: `idx_config_key(key)`
- server_config: `idx_server_default(is_default) WHERE is_default=1` (partial), `idx_server_url(base_url)`
- site_selectors: `idx_selectors_domain(domain_pattern)`, `idx_selectors_enabled(is_enabled) WHERE is_enabled=1` (partial)
- queue_log: `idx_queue_log_item(queue_item_id)`, `idx_queue_log_timestamp(timestamp)`
- statistics: `idx_stats_type_date(stat_type, stat_date)`

> Compatible with SQLite 3.38+ / sql.js. **§11.4.10 note**: `extension_config` stores `server.api_key` and `server.password` as `data_type='encrypted'`; `server_config` has `api_key_encrypted`/`password_encrypted` columns — credentials are designed to be encrypted-at-rest (see §6 crypto).

### 4b. TypeScript domain types

#### `src/types/torrent.ts`
- **interface `MagnetInfo`**: `uri:string`, `infohash:string` (40-char hex SHA-1), `displayName:string|null`, `trackers:readonly string[]`, `webSeeds:readonly string[]`, `exactLength:number|null`, `exactSource:string|null`, `keywords:readonly string[]`, `acceptableSource:string|null`, `manifest:string|null`, `detectedAt:number`, `sourceElement:Element|null`. (Covers magnet params xt/dn/tr/ws/xl/xs/kt/as/mt.)
- **interface `TorrentFile`**: `url:string`, `filename:string`, `size:number|null`, `sameOrigin:boolean`, `detectedAt:number`, `sourceElement:Element|null`.
- **interface `ParsedTorrent`**: `infohash:string`, `name:string`, `creationDate:number|null`, `comment:string|null`, `createdBy:string|null`, `pieceLength:number`, `isPrivate:boolean`, `trackers:readonly string[]`, `source:string|null`, `files:readonly TorrentFileInfo[]`, `totalSize:number`, `numPieces:number`.
- **interface `TorrentFileInfo`**: `path:readonly string[]`, `length:number`, `fullPath:string`.
- **type `TorrentContentType`** = `"magnet" | "torrent-file"`.
- **interface `DetectedTorrent`** (unified detection type): `id:string`, `type:TorrentContentType`, `magnet:MagnetInfo|null`, `torrentFile:TorrentFile|null`, `displayName:string`, `selected:boolean` (mutable), `sent:boolean` (mutable), `sendStatus:SendStatus|null` (mutable), `detectedAt:number`.
- **type `SendStatus`** = `"pending" | "sending" | "success" | "error" | "queued"`.
- **interface `SendResult`**: `success:boolean`, `torrent:DetectedTorrent`, `error:string|null`, `response:Record<string,unknown>|null`, `completedAt:number`.
- **interface `PageScanResult`**: `pageUrl:string`, `pageTitle:string`, `items:readonly DetectedTorrent[]`, `magnetCount:number`, `torrentFileCount:number`, `scannedAt:number`, `scanDurationMs:number`.

#### `src/types/config.ts`
- **type `AuthMethod`** = `"none"|"cookie"|"api_key"|"basic"` (duplicated in `types/api.ts`).
- **interface `ServerConfig`** (28 fields): `id`, `name`, `url`, `active:boolean`, `authMethod:AuthMethod`, `username:string|null`, `encryptedPassword:string|null`, `encryptedApiKey:string|null`, `requestTimeout:number`, `verifySsl:boolean`, `defaultCategory:string|null`, `defaultSavePath:string|null`, `startPaused:boolean`, `skipHashCheck:boolean`, `contentLayout:"original"|"subfolder"|"no_subfolder"`, `autoTMM:boolean`, `uploadLimit:number` (KiB/s, 0=unlimited), `downloadLimit:number`.
- **interface `ExtensionConfig`**: `schemaVersion:number`, `servers:readonly ServerConfig[]`, `activeServerId:string|null`, `autoScan:boolean`, `autoScanDelay:number`, `highlightTorrents:boolean`, `highlightStyle:"badge"|"border"|"glow"`, `showNotifications:boolean`, `notificationSound:boolean`, `autoSend:boolean`, `maxHistoryItems:number`, `debugMode:boolean`, `healthCheckInterval:number` (min), `offlineQueue:boolean`, `maxOfflineQueueSize:number`, `showContextMenu:boolean`, `keyboardShortcuts:boolean`, `lastUpdated:number`, `encryptionKeyVersion:number`.
- **const `DEFAULT_CONFIG`**: `schemaVersion:1`, `servers:[]`, `activeServerId:null`, `autoScan:true`, `autoScanDelay:2000`, `highlightTorrents:true`, `highlightStyle:"badge"`, `showNotifications:true`, `notificationSound:false`, `autoSend:false`, `maxHistoryItems:100`, `debugMode:false`, `healthCheckInterval:5`, `offlineQueue:true`, `maxOfflineQueueSize:50`, `showContextMenu:true`, `keyboardShortcuts:true`, `lastUpdated:0`, `encryptionKeyVersion:1`.
- **interface `AutoDiscoveryConfig`**: `ports:readonly number[]`, `scanTimeout:number`, `scanQbittorrent:boolean`, `scanFastApi:boolean`, `scanGo:boolean`.
- **const `DEFAULT_AUTO_DISCOVERY`**: `ports:[7187,7189,8080]`, `scanTimeout:3000`, all three scan flags `true`.
- **interface `ConnectionTestResult`**: `success`, `url`, `version:string|null`, `error:string|null`, `responseTimeMs`, `testedAt`.
- **interface `ConfigChangeEvent`**: `key`, `newValue:unknown`, `oldValue:unknown`, `changedAt`.

#### `src/types/api.ts`
qBitTorrent API + auth + health + Boba + queue + messaging types:
- **`QBittorrentVersion`**: `version:string`.
- **`QBittorrentAppPreferences`**: `locale`, `save_path`, `temp_path`, `preallocate_all:boolean`, `listen_port`, `max_active_downloads`, `max_active_uploads`, `max_active_torrents`, `dl_limit`, `up_limit`, `web_ui_username` (all readonly).
- **`QBittorrentAddTorrentParams`** (maps `/api/v2/torrents/add`): `urls?`, `torrents?:File`, `savepath?`, `cookie?`, `category?`, `tags?`, `skip_checking?` ("true"/"false" string), `paused?`, `root_folder?`, `rename?`, `upLimit?:number`, `dlLimit?:number`, `autoTMM?`, `sequentialDownload?`, `firstLastPiecePrio?`, `contentLayout?:"Original"|"Subfolder"|"NoSubfolder"`, `stopCondition?`.
- **`QBittorrentAddResponse`**: `success:boolean`, `error?:string`.
- **`QBittorrentTorrentInfo`**: hash, name, magnet_uri, size, progress (0–1), dlspeed, upspeed, priority, num_seeds, num_leechs, ratio, eta, state, category, tags, added_on, completion_on, save_path.
- **Auth credential interfaces**: `CookieAuthCredentials{method:"cookie",username,password}`, `ApiKeyAuthCredentials{method:"api_key",apiKey}`, `BasicAuthCredentials{method:"basic",username,password}`, `NoAuthCredentials{method:"none"}`; union **`AuthCredentials`**.
- **`AuthState`**: `method:AuthMethod`, `isAuthenticated:boolean`, `sidCookie:string|null`, `sidExpiresAt:number|null`, `basicAuthHeader:string|null`, `apiKeyHeader:string|null`, `lastRefreshedAt:number|null`, `consecutiveFailures:number`.
- **type `AuthMethod`** = `"none"|"cookie"|"api_key"|"basic"`.
- **type `HealthStatus`** = `"healthy"|"degraded"|"unhealthy"|"unknown"`.
- **`HealthCheckResult`**: `serverId`, `url`, `status:HealthStatus`, `version:string|null`, `responseTimeMs`, `authValid:boolean`, `error:string|null`, `checkedAt`.
- **`BobaServerInfo`**: `name`, `version`, `features:readonly string[]`, `qbittorrent_connected:boolean`, `qbittorrent_version:string|null`.
- **`BobaSearchResult`**: `id`, `name`, `infohash`, `magnet_uri`, `size`, `seeders`, `leechers`, `source`, `upload_date`, `category`.
- **`BobaSearchResponse`**: `results:readonly BobaSearchResult[]`, `total`, `page`, `per_page`.
- **`QueueItem`**: `id`, `torrent:{infohash,magnetUri:string|null,torrentUrl:string|null,displayName}`, `serverId`, `addedAt`, `attempts`, `lastError:string|null`, `lastAttemptAt:number|null`, `priority:"high"|"normal"|"low"`.
- **`QueueProcessResult`**: `processed`, `succeeded`, `failed`, `remaining`, `results:ReadonlyArray<{itemId,success,error:string|null}>`.
- **type `MessageType`** (20 values): `scan-page`, `scan-result`, `send-torrent`, `send-result`, `get-detected`, `get-config`, `set-config`, `get-auth-state`, `authenticate`, `health-check`, `health-result`, `queue-process`, `queue-status`, `open-dashboard`, `show-notification`, `update-badge`, `torrent-detected`, `selection-change`.
- **`ExtensionMessage`**: `type:MessageType`, `payload?:Record<string,unknown>`, `requestId?:string`.
- **`ExtensionMessageResponse`**: `success:boolean`, `data?:Record<string,unknown>`, `error?:string`.

---

## 5. Shared-lib API surface (every exported fn/class signature)

### `src/shared/crypto.ts` — AES-256-GCM credential encryption (Web Crypto)
- **interface `EncryptedBundle`**: `salt:string` (b64), `iv:string` (b64), `ciphertext:string` (b64, auth tag appended), `version:number`.
- `async function encrypt(plaintext:string, passphrase:string): Promise<EncryptedBundle>` — generates fresh random salt(16B)+IV(12B), derives key via PBKDF2, AES-GCM encrypt (tagLength 128). Throws `StorageError` on empty plaintext/passphrase or failure.
- `async function decrypt(bundle:EncryptedBundle, passphrase:string): Promise<string>` — re-derives key from salt+passphrase, AES-GCM decrypt. Throws `StorageError` ("passphrase may be incorrect") on failure.
- `function generateSecurePassphrase(): string` — 32 random bytes → base64.
- `function isEncrypted(value:unknown): value is EncryptedBundle` — structural type guard.
- `async function sha256(input:string): Promise<string>` — hex SHA-256 digest.
- `function simpleHash(input:string): number` — non-crypto 32-bit hash (cache keys only).
- (private: `deriveKey`, `generateRandomBytes`, `bytesToBase64`, `base64ToBytes`.)

### `src/shared/errors.ts` — error taxonomy
- **class `BobaLinkError extends Error`**: fields `code:string`, `statusCode:number|null`, `recoverable:boolean`, `cause:Error|null`, `context:Readonly<Record<string,unknown>>`. Ctor `(message, options{code?,statusCode?,recoverable?,cause?,context?})`. Methods `getUserMessage():string`, `toJSON():Record<string,unknown>`. Default code `BOBA_UNKNOWN`.
- **class `AuthError`** — code `BOBA_AUTH_FAILED`, statusCode default 401, recoverable true.
- **class `NetworkError`** — code `BOBA_NETWORK_ERROR`, statusCode null, recoverable true.
- **class `TorrentError`** — code `BOBA_TORRENT_ERROR`, statusCode default 400, recoverable true.
- **class `ParseError`** — code `BOBA_PARSE_ERROR`, statusCode null, recoverable **false**.
- **class `ConfigError`** — code `BOBA_CONFIG_ERROR`, recoverable true.
- **class `StorageError`** — code `BOBA_STORAGE_ERROR`, recoverable true.
- **class `RateLimitError`** — code `BOBA_RATE_LIMITED`, statusCode 429, recoverable true, extra field `retryAfter:number`. Ctor `(message, retryAfter, options{context?})`.
- **class `ServerError`** — code `BOBA_SERVER_<status>`, statusCode required, recoverable when `>=500 || ===429`. Ctor `(message, statusCode, options)`.
- `function isBobaLinkError(value:unknown): value is BobaLinkError`.
- `function normalizeError(error:unknown, context={}): BobaLinkError`.

### `src/shared/events.ts` — typed event emitter
- **interface `EventMap`** (13 events): `torrent-detected{id,type:"magnet"|"torrent-file",displayName,url}`, `scan-started{url,timestamp}`, `scan-completed{url,magnetCount,torrentFileCount,durationMs}`, `scan-error{url,error}`, `send-started{ids}`, `send-completed{results[{id,success}]}`, `send-error{id,error}`, `auth-state-changed{method,authenticated}`, `connection-status{serverId,connected,latency:number|null}`, `config-changed{key,newValue,oldValue}`, `queue-updated{size}`, `badge-update{count,color}`, `notification{title,message,type:"info"|"success"|"warning"|"error"}`.
- **type `EventName`** = keyof EventMap; **type `EventListener<T>`** = `(payload:EventMap[T])=>void`.
- **class `TypedEventEmitter`**: `on<T>(event,listener):()=>void` (returns unsub); `once<T>(event,listener):void`; `emit<T>(event,payload):void` (try/catch per listener); `off(event?):void`; `listenerCount(event):number`; `hasListeners(event):boolean`.
- **const `globalEvents`** = new TypedEventEmitter().

### `src/shared/logger.ts` — structured logging
- type `LogLevel` = `"debug"|"info"|"warn"|"error"` (severity 0/1/2/3). Default min level `info`; `debug` when debug mode on.
- `function initLogger(isDebug:boolean): void`.
- `function debug/info/warn/error(context:string, message:string, data?:unknown): void` (error always emitted).
- `function timed(context, operation): ()=>void` — logs start, returns end fn logging duration.
- `function createLogger(context:string)` → `{debug,info,warn,error,timed}` (bound). **type `Logger`** = ReturnType.
- `function isDebugEnabled(): boolean`.
- Format: `[ISO-timestamp] [LEVEL] [context] message`.

### `src/shared/storage.ts` — chrome.storage.local wrapper
- `async function storageGet<T>(key): Promise<T|null>`.
- `async function storageSet<T>(key, value): Promise<void>`.
- `async function storageRemove(key): Promise<void>`.
- `async function storageGetMultiple<T>(keys:readonly string[]): Promise<ReadonlyMap<string,T|null>>`.
- `async function storageClearAll(): Promise<void>` — removes only `bobalink_`-prefixed keys.
- `function getStorageKeys(): typeof STORAGE_KEYS`.
- `function onStorageChange<T>(keys, callback): ()=>void` — local-area only; returns unsub.
- **class `NamespacedStorage`**: ctor `(namespace)` → prefix `bobalink_<namespace>_`; methods `get<T>(key)`, `set<T>(key,value)`, `remove(key)`, `getAllKeys()`, `clear()`. All errors wrapped as `StorageError`.

### `src/shared/utils.ts` — utilities
- `function debounce<T extends unknown[]>(fn, delay): {(...args:T):void; cancel():void}`.
- `function throttle<T extends unknown[]>(fn, interval): {(...args:T):void; cancel():void}`.
- `function generateId(): string` — crypto.randomUUID or timestamp+random fallback.
- `function truncate(str, maxLength): string` — ellipsis.
- `function escapeHtml(text): string` — via textContent/innerHTML (XSS-safe; **DOM-dependent**, not service-worker safe).
- `function sleep(ms): Promise<void>`.
- `async function retryWithBackoff<T>(fn, maxRetries=3, baseDelay=1000, maxDelay=30000): Promise<T>` — exponential backoff + 0.3 jitter.
- **class `TokenBucket`**: ctor `(capacity, refillRate)`; `consume():boolean`; `getAvailableTokens():number`; private `refill()`.
- `function yieldToBrowser(): Promise<void>` — rAF or setTimeout(0).
- `async function processInChunks<T>(items, processor, chunkSize=50): Promise<void>`.
- `function isValidHttpUrl(url): boolean`.
- `function getDomain(url): string` — hostname or "".
- `function formatBytes(bytes, decimals=2): string` — B/KB/MB/GB/TB/PB.
- `function deepClone<T>(obj): T` — JSON round-trip.
- `function arraysEqual<T>(a, b): boolean` — shallow.

---

## 6. Every constant value (`src/shared/constants.ts`) — esp. URLs/ports/timeouts/secrets

### Regex patterns
- `MAGNET_REGEX` = `/magnet:\?xt=urn:btih:[a-fA-F0-9]{40}[^\s"'<>]*/gi`
- `MAGNET_VALIDATION_REGEX` = `/^magnet:\?xt=urn:btih:[a-fA-F0-9]{40}(?:[&;][^\s"'<>]*)?$/i`
- `INFOHASH_REGEX` = `/xt=urn:btih:([a-fA-F0-9]{40})/i`
- `TORRENT_FILE_REGEX` = `/https?:\/\/[^\s"'<>]+\.torrent(?:\?[^\s"'<>]*)?/gi`
- `TORRENT_FILE_VALIDATION_REGEX` = `/^https?:\/\/.+\.torrent(\?.*)?$/i`
- `INFOHASH_HEX_REGEX` = `/^[a-fA-F0-9]{40}$/`
- `INFOHASH_BASE32_REGEX` = `/^[A-Z2-7]{32}$/`
- `MAGNET_DN_REGEX` = `/[?&]dn=([^&;]*)/`
- `MAGNET_TR_REGEX` = `/[?&]tr=([^&;]*)/g`

### Ports / URLs / endpoints (load-bearing)
- `DEFAULT_PORTS` = `{FAST_API:7187, GO:7189, QBITTORRENT:8080}`
- `DEFAULT_URLS` = `{FAST_API:"http://localhost:7187", GO:"http://localhost:7189", QBITTORRENT:"http://localhost:8080"}`
- `QBITTORRENT_ENDPOINTS`:
  - `AUTH_LOGIN:"/api/v2/auth/login"`, `AUTH_LOGOUT:"/api/v2/auth/logout"`
  - `APP_VERSION:"/api/v2/app/version"`, `APP_PREFERENCES:"/api/v2/app/preferences"`, `APP_SET_PREFERENCES:"/api/v2/app/setPreferences"`
  - `TORRENTS_ADD:"/api/v2/torrents/add"`, `TORRENTS_INFO:"/api/v2/torrents/info"`, `TORRENTS_DELETE:"/api/v2/torrents/delete"`, `TORRENTS_PAUSE:"/api/v2/torrents/pause"`, `TORRENTS_RESUME:"/api/v2/torrents/resume"`
  - `TRANSFER_INFO:"/api/v2/transfer/info"`

> ⚠️ Port reconciliation needed: extension assumes qBitTorrent direct on **8080**; Boba's actual proxy exposes qBitTorrent WebUI on **7186** (merge service 7187, boba-jackett 7189). FastAPI 7187 + Go 7189 match. Magnet/.torrent send goes through `/api/v2/torrents/add` on the chosen base URL.

### Timing / retry / rate limit
- `DEBOUNCE_DELAYS` = `{MUTATION:500, STORAGE_WRITE:250, AUTO_SCAN:1000, BADGE_UPDATE:300, NOTIFICATION:2000}` (ms)
- `REQUEST_TIMEOUTS` = `{DEFAULT:15000, HEALTH_CHECK:5000, AUTH:10000, ADD_TORRENT:30000, AUTO_DISCOVERY:3000}` (ms)
- `RETRY_CONFIG` = `{MAX_RETRIES:3, BASE_DELAY_MS:1000, MAX_DELAY_MS:30000, JITTER_FACTOR:0.3}`
- `RATE_LIMIT` = `{MAX_REQUESTS:10, WINDOW_MS:1000}` (note: differs from DB seed `behavior.rate_limit_requests=30`)

### Storage keys (`STORAGE_KEYS`, all `bobalink_`-prefixed)
- `CONFIG:"bobalink_config"`, `AUTH_STATE:"bobalink_auth_state"`, `CREDENTIALS:"bobalink_credentials"`, `DETECTED:"bobalink_detected"`, `HISTORY:"bobalink_history"`, `QUEUE:"bobalink_queue"`, `HEALTH:"bobalink_health"`, `KEY_MATERIAL:"bobalink_key_material"`

### Encryption (`ENCRYPTION`) — **§11.4.10 secret-handling scheme**
- `ALGORITHM:"AES-GCM"`, `KEY_LENGTH_BITS:256`, `IV_LENGTH_BYTES:12`, `SALT_LENGTH_BYTES:16`, `KDF_ALGORITHM:"PBKDF2"`, `KDF_ITERATIONS:100000`, `KDF_HASH:"SHA-256"`, `CURRENT_KEY_VERSION:1`.
- Scheme: passphrase → PBKDF2 (100k iters, SHA-256, 16-byte random salt) → AES-256-GCM (12-byte random IV, 128-bit auth tag). Each `encrypt()` is independent (fresh salt+IV). Stored bundle = `{salt,iv,ciphertext,version}` all base64. Aligns with Boba's AES-256-GCM master-key model (boba-jackett). The passphrase source/storage is **not defined in these foundation files** — see open questions.

### UI constants
- `BADGE_COLORS` = `{HEALTHY:"#4CAF50", DEGRADED:"#FF9800", ERROR:"#F44336", SCANNING:"#2196F3", DETECTED:"#9C27B0", DEFAULT:"#757575"}`
- `ICON_SIZES` = `[16,32,48,128]`

### Site selectors (`SITE_SELECTORS`, code-level supplement to DB table)
Record<domain, selectors[]>: `generic` (`a[href^="magnet:"]`, `a[href$=".torrent"]`, `a[href*=".torrent?"]`, `a[href*="download.php?id="]`); plus per-domain entries for 1337x.to, thepiratebay.org/thepiratebay10.org, rarbg.to/rarbgtorrents.org, yts.mx/yts.lt, eztv.re, limetorrents.lol, torrentgalaxy.to, nyaa.si, animetosho.org, torrentz2.eu, fitgirl-repacks.site, rutracker.org, katcr.co, demonoid.is, iptorrents.com (`a[href$=".torrent"]`,`a[href*="download.php/"]`), torrentleech.org (`a[href$=".torrent"]`,`a[href*="/download/"]`), beyond-hd.me, passthepopcorn.me.

### Misc (`EXT`)
- `ID:"bobalink"`, `NAME:"BobaLink"`, `DEFAULT_CATEGORY:"BobaLink"`, `MAX_POPUP_ITEMS:50`, `MAX_DISPLAY_NAME_LENGTH:80`.

---

## 7. CI flag + which build/test commands to keep as manual scripts

🚩 **CONSTITUTION FLAG (Boba forbids ALL CI/CD — Hard Stop rule, CLAUDE.md):** the reference repo ships **two GitHub Actions workflows** that MUST NOT be ported:

- `.github/workflows/ci.yml` — jobs: `lint` (lint + format:check + compile), `unit-test` (test + coverage upload), `build` (npm run build + dist upload). Triggers on push/PR to main/develop.
- `.github/workflows/release.yml` — 6 jobs: version-bump (semver validate, CHANGELOG check, manifest version edit), build-all (matrix chrome/firefox), sign-firefox (AMO via `web-ext sign` + Mozilla secrets), create-release (GitHub Release), upload-chrome (Chrome Web Store publish API), release-summary. Uses secrets `MOZILLA_API_KEY/SECRET`, `FIREFOX_EXTENSION_ID`, `CHROME_CLIENT_ID/SECRET/REFRESH_TOKEN`, `CHROME_WEBSTORE_ID`.

**Both `.yml` files MUST be deleted / never copied** into the Boba tree (no `.github/workflows/*.yml` allowed; CI is manual via `./ci.sh`). Extract only the **commands** worth keeping as manual scripts:

Keep as manual local commands (e.g. wired into a `ci.sh`-style script or Makefile target):
- **Lint/format/compile gate**: `npm run lint` → `npm run format:check` → `npm run compile` (`tsc --noEmit`).
- **Unit tests + coverage**: `npm run test` (`jest --coverage`, 80% threshold).
- **E2E**: `npm run test:e2e` (`playwright test`) — requires built `dist/` + globalSetup/teardown files (absent; must be authored).
- **Build**: `npm run build` (chrome) / `npm run build:firefox`; package: `npm run zip` / `zip:firefox`.
- **Release packaging mechanics worth reusing manually** (NOT as automation): zip dist dir, `sha256sum` checksum, inject `VERSION`/`BUILD_SHA`/`BUILD_DATE` files into dist. Firefox `web-ext sign` and Chrome Web Store upload are out of scope for the local-manual model (and need real store credentials — handle per §11.4.10 if ever used, never in-repo).
- The release workflow's `sed -i "s/1.0.0/$VERSION/g" src/sql/schemas.sql src/sql/migrations/001_initial.sql` shows version is also embedded in SQL seed rows — a manual bump script must touch package.json + wxt.config.ts manifest version + both SQL files + `app_metadata`/`extension_config` schema_version/app_version rows together.

---

## 8. Open questions / drift to resolve in the plan

1. **Port mismatch (critical).** Extension hardcodes qBitTorrent on **8080** (host_permissions, CSP, DEFAULT_URLS/PORTS, DB defaults). Boba's real qBitTorrent WebUI is proxied on **7186** (CLAUDE.md port table); 7187=merge service, 7189=boba-jackett. FastAPI(7187)/Go(7189) match but qBitTorrent must change 8080→7186 across `wxt.config.ts` (host_permissions + CSP connect-src), `constants.ts`, SQL seeds, and `DEFAULT_AUTO_DISCOVERY.ports`.
2. **Encryption passphrase provenance undefined.** `crypto.ts` requires a `passphrase` for encrypt/decrypt and `STORAGE_KEYS.KEY_MATERIAL` / `EXTENSION/encryptionKeyVersion` exist, but **where the passphrase comes from / how it's persisted** is not in the foundation layer (must be in background/options — not in scope here). Must confirm it satisfies §11.4.10 (no plaintext secret at rest, no secret in git). The `server.api_key`/`server.password` SQL seeds are empty strings (data_type=encrypted) — fine.
3. **Dual storage model.** Two parallel persistence designs exist: (a) the SQL schema (sql.js over chrome.storage) with 9 tables, and (b) the `STORAGE_KEYS` JSON-blob model + `NamespacedStorage`. The foundation does not show which is authoritative at runtime (storage.ts only implements the JSON-blob path; no sql.js wrapper file present in this layer). Plan must decide one source of truth.
4. **Type duplication.** `AuthMethod` defined identically in both `types/api.ts` and `types/config.ts`; `ServerConfig` (TS) and `server_config` (SQL) diverge in field naming (`url` vs `base_url`, `encryptedPassword` vs `password_encrypted`, port fields only in SQL). Reconcile.
5. **Config-value mismatch.** `RATE_LIMIT.MAX_REQUESTS=10`/`WINDOW_MS=1000` (constants) vs DB seed `behavior.rate_limit_requests=30`. And `autoScanDelay` default 2000 (config) vs `DEBOUNCE_DELAYS.AUTO_SCAN=1000`. Decide canonical.
6. **Referenced-but-absent files** (in this layer): `tests/e2e/global-setup.ts`, `tests/e2e/global-teardown.ts`, `src/assets/icon.svg`, popup/options/content/background source, and the sql.js wrapper. These are downstream layers, not foundation — flagged so the plan doesn't assume they exist yet.
7. **Release workflow references non-existent npm scripts** (`build:chrome`) and non-existent `src/manifest.chrome.json`/`manifest.firefox.json` (WXT generates the manifest, there are no static manifest files). Drift in the reference repo — ignore for porting.
8. **Repo URL is HTTPS** (`https://github.com/boba-project/bobalink.git`) — Boba constitution mandates SSH remotes (`git@…`). Fix when integrating.
9. **`minimum_chrome_version "109"`** + MV3 module service worker — confirm target browser floor is acceptable; Firefox MV3 support (release.yml builds firefox) needs verification of background `type:module` SW support.
