# F — Adopt vs Refactor vs Rewrite vs Net-New decision table

**Revision:** 1
**Last modified:** 2026-06-10T00:00:00Z

> Per-module disposition of the reference BobaLink implementation (44 `.ts` files under
> `docs/research/browser_extension/Browser Torrent Extension Guide/src/src/`) for the Boba
> browser-extension build. Decisions are evidence-based: every defect is cited to the
> reference file (and verified by direct read where the extraction's claim was ambiguous).
>
> **Decision vocabulary**
> - **ADOPT** — reuse mostly as-is (rename/port only; no logic change). §11.4.74 reuse.
> - **REFACTOR** — reuse the structure, fix bounded defects (1–N targeted edits).
> - **REWRITE** — defects too deep / design wrong; rebuild from the contract, may salvage shape.
> - **NET-NEW** — does not exist in the reference; must be authored.
>
> Anti-bluff (§11.4): a module is ADOPTed only when reading the source shows it is genuinely
> sound. Defective code is never ADOPTed just because it exists.

Reference path prefix (note the spaces), abbreviated `<REF>/` below:
`docs/research/browser_extension/Browser Torrent Extension Guide/src/src/`

---

## 1. Parser layer

| Module/File | Quality assessment (defect cited or "sound") | Decision | Required fixes | Risk |
|---|---|---|---|---|
| `parser/bencode.ts` | **Sound.** Zero-dep `Uint8Array` bencode; dict keys sorted lexicographically (`bencode.ts:139-151`) — load-bearing for stable infohash; rejects trailing data, unterminated ints/strings/lists/dicts; bounds-checks byte-strings; binary-vs-utf-8 mode; `sha1` via Web Crypto. Strongly unit-tested (`bencode.test.ts`). | **ADOPT** | Remove dead-assert in test (`bencode.test.ts:156`). Add property/fuzz + deep-recursion-limit (chaos) tests per §11.4.85. No source change. | Low |
| `parser/magnet.ts` | **Sound.** Repeated-key query parsing (multiple `tr`/`xt` preserved), hex+base32 infohash, `base32ToHex` RFC4648, full param extraction (xt/dn/tr/ws/xl/xs/kt/as/mt), recurse on base32. Fixture-driven tests. | **ADOPT** | Wire the unused 7-case `invalidMagnets` negative fixture. Consider BitTorrent v2 (`btmh`/multihash) — out of scope unless required. | Low |
| `parser/torrent-file.ts` | **Sound but DEAD CODE.** `parseTorrentFile`/`computeInfohash` correct (infohash = `sha1(encode(infoDict))`, BT v1 canonical) and tested — **but never invoked** by scanners/adapter/background (sends upload raw `File`). Re-encode reorders non-sorted info keys (hash-divergence caveat, `torrent-file.ts:46-48`). | **REFACTOR** | Source is sound → keep. The fix is **wiring**: invoke `computeInfohash` in the scanner/adapter to derive stable ids + local dedup against Boba. §11.4.124 (don't delete unwired code — wire it). | Med (wiring touches scanner + adapter contracts) |

## 2. Scanner layer

| Module/File | Quality assessment | Decision | Required fixes | Risk |
|---|---|---|---|---|
| `scanner/base.ts` | **One real defect.** Abstract base + shadow-DOM-aware `querySelectorAllDeep` + hidden-element skip + re-entrancy guard are sound. **Defect (verified by read):** `hashString` returns `Math.abs(hash).toString(36) + Date.now().toString(36)` (`base.ts:272`) — **time-salts the id** despite the doc-comment "stable ID", so the same torrent gets a new id every scan; cross-scan/cross-tab dedup is unreliable. | **REFACTOR** | Drop the `Date.now()` salt; derive id from `infohash` (now available once `torrent-file.ts` is wired) so ids are stable. One-method change. | Med (dedup correctness depends on it) |
| `scanner/link-scanner.ts` | **Sound.** Site-specific pass (resolve selectors by domain) + generic `a[href]` fallback, dedup by normalized href, relative→absolute resolution, `sameOrigin` flag. | **ADOPT** | Reconcile the selector source (see `site-db` row). | Low |
| `scanner/text-scanner.ts` | **Sound.** `TreeWalker(SHOW_TEXT)` with skip-list + min-length filter, `findMagnetUris` dedup. Catches forum-pasted magnets. | **ADOPT** | None. | Low |
| `scanner/orchestrator.ts` | **Sound.** Coordinates scanners + MutationObserver, per-site debounce, cooperative `yieldToBrowser()` between scanners, relevant-mutation filter, emits scan events, dedups by id into a Map. Initial-state-only tested (orchestrator never actually scans in the reference suite). | **ADOPT** | Depends on the `base.ts` stable-id fix for reliable `mergeResults` dedup. Add real scan + mutation-rescan + debounce tests (the reference does not exercise scanning). | Med (dedup correctness) |
| `scanner/site-db.ts` | **Defect: two divergent selector tables.** `SITES` (15 rich entries, used ONLY for per-site debounce) overlaps and disagrees with `constants.SITE_SELECTORS` (~21 flat entries, used by `LinkScanner`). The private trackers Boba actually supports (rutracker/iptorrents/kinozal/nnmclub) are split across both. | **REFACTOR** | Merge into ONE authoritative site registry (single source of truth) covering Boba's real trackers (rutracker, kinozal, nnmclub, rutor, IPTorrents). Reconcile against the SQL `site_selectors` seed (30 rows) too. | Med (3-way reconcile: constants + site-db + SQL seed) |

## 3. API layer

| Module/File | Quality assessment | Decision | Required fixes | Risk |
|---|---|---|---|---|
| `api/client.ts` | **Sound HTTP client, WRONG TARGET.** TokenBucket rate-limit, AbortController timeout, `retryWithBackoff`, 429→`RateLimitError`, content-type branching — all sound. **But it speaks ONLY raw qBittorrent WebUI v2** (`/api/v2/...`) and the default base assumes qBittorrent on `:8080`. Nothing reaches Boba's real services (7186 proxy / 7187 merge / 7189 jackett). `set-cookie` SID parse (`client.ts:128-166`) is browser-fragile. | **REFACTOR** | Keep the transport (rate-limit/retry/timeout/error mapping). Re-point base URL/endpoints to Boba's real ports and routes; add a Boba-endpoint path set distinct from the raw qBt path set. Harden SID handling. | **HIGH** (transport reuse is safe; endpoint re-targeting is the load-bearing integration work) |
| `api/auth.ts` | **Mostly sound, one crypto-coupling defect.** Four auth methods + failure backoff + `refreshIfNeeded` are sound. `createCredentialsFromConfig(config, passphrase)` (`auth.ts:170`) decrypts via `shared/crypto` — its correctness is hostage to the broken passphrase provenance (see crypto rows). Reads `client["authCookie"]` private field (`auth.ts:247`) — fragile TS escape hatch. | **REFACTOR** | Re-wire to the real key source (NET-NEW below). Replace the private-field read with a public accessor on the client. Decide which auth model Boba actually uses (delegate to proxy/jackett vs raw qBt login). | High (couples to credential rewrite) |
| `api/qbittorrent.ts` | **Sound.** Domain wrapper: `sendTorrent`/`sendTorrents` (250ms spacing), `buildAddOptions` maps `ServerConfig`→add params, never rethrows (normalizes to `getUserMessage()`). | **ADOPT** | Inherits the re-targeted client. None of its own logic is defective. | Low |
| `api/queue.ts` | **Defect: never authenticates (verified by read).** Enqueue/dequeue/FIFO-eviction/persist sound. But `processQueue` (`queue.ts:170`) builds `new BobaAPIClient(config.url,...)` + adapter and runs the send loop **with no `login()`/`authenticate()` call** — retries against an authed server 403/fail-loop forever. | **REFACTOR** | Inject auth into `processQueue` (build+authenticate the client, or accept an authenticated client/adapter). Add retry/attempts/backoff tests (reference only asserts structure). | Med-High (offline retries silently broken without it) |
| `api/health.ts` | **Sound, wrong port list.** Health thresholds, caching, `testConnection`, `autoDiscover`. **Defect:** `autoDiscover` probes `[8080, 7187, 7189]` (`health.ts:201`) — 8080 is wrong for Boba (qBt WebUI is proxied on 7186). | **REFACTOR** | Change probe port set to Boba's real map (7186/7187/7189). | Low |

## 4. Content layer

| Module/File | Quality assessment | Decision | Required fixes | Risk |
|---|---|---|---|---|
| `content/index.ts` | **Sound.** Wires orchestrator→background (`scan-result`), message handler (`scan-now`/`get-detected`/`toggle-selection`/`get-scan-status`). **Defect (contract):** content `get-detected` returns `{torrents:[…]}` while background `get-detected` returns `{data:{result}}` — divergent shapes the popup juggles. | **REFACTOR** | Unify the `get-detected` response contract across content + background + popup. | Med |
| `content/scanner.ts` | **Sound.** Thin content-side orchestrator glue (90 lines). | **ADOPT** | None. | Low |
| `content/highlight.ts` | **Sound.** Three highlight styles (badge/border/glow), event-bus driven. | **ADOPT** | None (presentation). | Low |
| `content/styles.css` | Presentation only, `.bobalink-*` + `!important`. | **ADOPT** | Rebrand class prefix if extension is renamed. | Low |

## 5. Entrypoints (background / popup / options)

| Module/File | Quality assessment | Decision | Required fixes | Risk |
|---|---|---|---|---|
| `background/index.ts` | **Sound hub, ONE critical defect.** Lifecycle, message router, context menus, commands, alarms (keepalive ~20s / health 5min), badge/notifications — all sound. **Critical (verified `index.ts:409`):** `sendTorrents` decrypts creds with **empty passphrase `""`** — can only ever read `""`-encrypted bundles, and is mutually incompatible with the options page's `"bobalink-extension"` encryption ⇒ the whole credential path is broken end-to-end. `open-dashboard` fallback hardcodes `:8080`. Has zero unit coverage in the reference. | **REFACTOR** | Replace the `""` decrypt call-site with the real key source. Fix `:8080` fallback. Add the missing background unit/integration coverage. | **HIGH** (credential correctness + the unrouted message types decision) |
| `popup/popup.ts` + `popup/index.html` + `popup/styles.css` | **Sound.** Per-tab list, select/deselect, send, connection-status dot, empty-state scan. Excluded from reference coverage. | **ADOPT** | Adapt to the unified `get-detected` contract. Add real UI/UX behavior tests (reference e2e asserts presence only). | Low-Med |
| `options/options.ts` + `index.html` + `styles.css` | **CRITICAL defect (verified `options.ts:327`).** Form↔config bridge, server modal, test-connection, settings toggles all sound. **But every secret is AES-encrypted with the literal fixed passphrase `"bobalink-extension"`** — trivially reversible by anyone with the source (§11.4.10 leak). Auto-discover checkboxes are display-only (real ports hardcoded elsewhere). | **REFACTOR** | Remove the fixed passphrase; route encryption through the real key source (NET-NEW). Wire the auto-discover checkboxes to actual config. | **HIGH** (§11.4.10 credential leak is a release blocker) |

## 6. Shared libs

| Module/File | Quality assessment | Decision | Required fixes | Risk |
|---|---|---|---|---|
| `shared/constants.ts` | **Sound values, WRONG PORTS + duplication.** Regexes, timeouts, retry/rate config, badge colors, encryption params all sound. **Defects:** `DEFAULT_PORTS.QBITTORRENT=8080` / `DEFAULT_URLS.QBITTORRENT` wrong (should be 7186); `SITE_SELECTORS` duplicates `site-db.SITES`; `RATE_LIMIT.MAX_REQUESTS=10` disagrees with DB seed `behavior.rate_limit_requests=30`. | **REFACTOR** | Fix qBt port 8080→7186 across host_permissions/CSP/URLs/PORTS/auto-discover. Collapse the duplicate selector table. Pick canonical rate-limit. | Med (port fix is cross-cutting: constants + manifest + SQL + auto-discover) |
| `shared/crypto.ts` | **SOUND PRIMITIVE — extraction's "REWRITE" is too broad (DISAGREE, see §8).** Verified by read: PBKDF2 100k iters / AES-256-GCM / fresh 16-byte salt + 12-byte IV per op / 128-bit GCM tag / proper `StorageError` wrapping / rejects empty plaintext+passphrase. The crypto *module itself is correct and reusable*. The defect lives entirely in the **callers'** passphrase (`options.ts:327`, `background:409`), not here. | **ADOPT** (module) | None to the module. The fix is the NET-NEW key source feeding it. Rewrite the **test** to import this real module (reference test tests a copy). | Low (module) / High (caller key source — separate NET-NEW) |
| `shared/errors.ts` | **Sound.** Typed error taxonomy (`BobaLinkError` + 8 subclasses), `getUserMessage`, `normalizeError`, `isBobaLinkError`. | **ADOPT** | Add direct error-class unit tests. | Low |
| `shared/events.ts` | **Sound.** `TypedEventEmitter` + 13-event `EventMap`, per-listener try/catch isolation, unsub returns. Thoroughly tested. | **ADOPT** | None. | Low |
| `shared/logger.ts` | **Sound.** Structured leveled logging, `timed`, `createLogger`, debug-gating. | **ADOPT** | None. | Low |
| `shared/storage.ts` | **Sound.** `chrome.storage.local` wrapper, `NamespacedStorage`, change listener, `bobalink_`-prefixed clear. **Note:** only the JSON-blob model is implemented here — the parallel SQL-schema (sql.js) model has NO wrapper file. | **ADOPT** | Decide one persistence source of truth (JSON-blob vs sql.js); the sql.js wrapper is NET-NEW if chosen. Add direct storage unit tests (always mocked away in the reference). | Med (dual-storage architecture decision) |
| `shared/utils.ts` | **Sound.** debounce/throttle, `retryWithBackoff`, `TokenBucket`, `processInChunks`, `formatBytes`, url helpers. **Note:** `escapeHtml` is DOM-dependent (not service-worker safe); `processInChunks` defined but unused. | **ADOPT** | Provide a SW-safe `escapeHtml` variant for background context. | Low |

## 7. Types

| Module/File | Quality assessment | Decision | Required fixes | Risk |
|---|---|---|---|---|
| `types/torrent.ts` | **Sound.** `MagnetInfo`/`TorrentFile`/`ParsedTorrent`/`DetectedTorrent`/`SendResult`/`PageScanResult`. | **ADOPT** | None. | Low |
| `types/config.ts` | **Sound, with duplication.** `ServerConfig`/`ExtensionConfig`/`DEFAULT_CONFIG`. **Defect:** `AuthMethod` duplicated in `types/api.ts`; `ServerConfig` (TS) diverges from `server_config` (SQL) field naming. | **REFACTOR** | De-duplicate `AuthMethod` (single canonical). Reconcile TS `ServerConfig` ↔ SQL `server_config`. Fix default ports (auto-discovery `[7187,7189,8080]`→ Boba map). | Low |
| `types/api.ts` | **Sound, declares unused contracts.** qBt/auth/health/queue/message types. `BobaServerInfo`/`BobaSearchResponse` declared but **nothing consumes them** (no Boba-API client). `MessageType` declares 7 values with no handler branch. | **REFACTOR** | De-dup `AuthMethod`. Decide which declared-but-unrouted message types to implement vs drop. The Boba-API consumer that uses `BobaSearchResponse` is NET-NEW. | Low (types) / High (the consumer is net-new) |

## 8. SQL schema

| Module/File | Quality assessment | Decision | Required fixes | Risk |
|---|---|---|---|---|
| `sql/schemas.sql` (= `migrations/001_initial.sql`) | **Sound schema, wrong default + unresolved dual-storage.** 9 tables, ~25 indexes, partial indexes, encrypted-credential columns (`api_key_encrypted`/`password_encrypted`), 30 selector seeds, 25 config seeds — well-formed SQLite 3.38+/sql.js. **Defects:** seeds `qbittorrent_port DEFAULT 8080` + `server.base_url=http://localhost:8080`; and the runtime has NO sql.js wrapper (only the JSON-blob storage path is implemented) so it is currently unused-by-design. | **REFACTOR** (if SQL chosen) / **drop** (if JSON-blob chosen) | First decide the single persistence model. If SQL: fix port seeds 8080→7186, reconcile site-selector seed with the merged site registry, author the sql.js wrapper (NET-NEW). If JSON-blob: this schema is not adopted. | Med (architecture decision gates everything) |

## 9. Build / test configs

| Module/File | Quality assessment | Decision | Required fixes | Risk |
|---|---|---|---|---|
| `wxt.config.ts` | **Sound MV3 manifest gen, wrong endpoints.** WXT manifest, 6 permissions, CSP, commands, auto-icons. **Defects:** host_permissions + CSP `connect-src` include `:8080` (should be `:7186`); icon PNGs referenced but absent. | **REFACTOR** | Fix 8080→7186 in host_permissions + CSP. Confirm Firefox MV3 module-SW support. | Med |
| `tsconfig.json` | **Sound.** Very strict (all strict flags + `noUncheckedIndexedAccess` + `exactOptionalPropertyTypes`). | **ADOPT** | None. | Low |
| `package.json` | **Sound, drift.** Deps/scripts fine. **Defects:** HTTPS repo URL (Boba mandates SSH); release.yml references non-existent `build:chrome` script. | **REFACTOR** | SSH remote; rebrand name; align scripts; drop CI-only assumptions. | Low |
| `jest.config.ts` | **Defect: 80% threshold + UI/entrypoints excluded from coverage.** `collectCoverageFrom` excludes `popup/options/content/background/**/index.ts` — UI/entrypoint logic has ZERO coverage enforcement. Conflicts with §11.4.27. | **REWRITE** (or replace w/ Vitest) | Decide runner (Vitest recommended — matches Boba `frontend/` + the crypto test). Bring UI/entrypoints INTO coverage; raise toward 100%. | Med (runner decision is foundational) |
| `playwright.config.ts` | **Defect: non-functional e2e config.** References missing `global-setup.ts`/`global-teardown.ts`; dead `webServer.url :3000`; Firefox project can't load extension via Chromium args; `reporter:github`+`forbidOnly:CI` assume GitHub Actions. | **REWRITE** | Author global-setup/teardown (build `dist`, launch persistent Chromium with `--load-extension`, capture real extension id, rewrite `chrome-extension://<id>/...`). Remove GH-Actions assumptions (Boba manual CI). | Med |
| `.eslintrc.json` / `.prettierrc` | **Sound.** Type-aware lint (`no-explicit-any`/`no-floating-promises` errors), Prettier 100-col. | **ADOPT** | Align with Boba project lint config. | Low |
| `_locales/en/messages.json` | **Sound.** 28 i18n keys. | **ADOPT** | Rebrand strings if renamed. | Low |
| `.github/workflows/ci.yml`, `release.yml` | **FORBIDDEN.** Boba Hard-Stop: no `.github/workflows/*.yml` ever. | **drop (do NOT port)** | Extract only the *commands* (lint/compile/test/build/zip/sha256) into a manual `ci.sh`-style script. Never copy the YAML. | Low (but a constitution hard-stop) |

## 10. Tests

| Module/File | Quality assessment | Decision | Required fixes | Risk |
|---|---|---|---|---|
| `bencode.test.ts` | Sound; dead-assert line 156. | **ADOPT** | Remove dead assert; add fuzz/chaos. | Low |
| `magnet.test.ts` | Sound, fixture-driven; `invalidMagnets` (7) unused. | **ADOPT** | Wire negative fixtures. | Low |
| `torrent-file.test.ts` | Sound (infohash determinism, single/multi parse). | **ADOPT** | None. | Low |
| `api-client.test.ts` | **Partial BLUFF.** Auth block ends `expect(true).toBe(true)` (no observable check); 429 test asserts `ServerError` despite name saying `RateLimitError`. | **REFACTOR** | Replace the bluff Auth assertions with real cookie-header propagation checks; fix the 429 assertion. | Med |
| `queue.test.ts` | **Partial BLUFF.** Auto-processing block ends `expect(true).toBe(true)`; processQueue only asserts *structure*, not success/failure. | **REFACTOR** | Assert real retry/attempts/outcomes; remove no-ops. | Med |
| `scanner.test.ts` | **Weak.** Event-emitter block sound; but orchestrator block asserts initial-state only (never scans); DOM block tests raw `querySelectorAll`, NOT the production scanner. | **REFACTOR** | Drive the real orchestrator over real DOM; assert detected torrents + mutation rescans. | Med |
| `crypto.test.ts` | **BLUFF (§11.4.1).** 44 thorough tests — but against an **inline re-implemented copy**, never `src/shared/crypto.ts`. Cannot fail against a no-op stub of the real module. Also imports `vitest` while the other 6 files use Jest (mixed runners). | **REWRITE** | Re-point every test at the production `shared/crypto` module; standardize runner. | Med (it's the most-thorough file but proves nothing as-is) |
| `chrome-mock.ts` / `setup.ts` | Mock infra; happy-path only (no error injection), no `cookies`/`scripting`/`sync`; `setup.ts:14` wrong path (type-only). | **REFACTOR** | Add error-injecting variant for chaos/stress; fix the stale path. | Low |
| `content.spec.ts` / `options.spec.ts` / `popup.spec.ts` (e2e) | **NON-FUNCTIONAL.** Hardcoded `chrome-extension://test-id/...`; no fixture loads the extension or resolves the real id; content spec asserts raw DOM, not the injected content script. Asserts presence/visibility, never user outcomes. | **REWRITE** | Real extension-loading fixture + user-observable assertions (torrent rendered, server persisted, send→appears in qBittorrent). | High (load-bearing for §11.4 anti-bluff e2e) |

## 11. NET-NEW (does not exist in the reference — must be authored)

| Item | Why net-new | Risk |
|---|---|---|
| **Real key source for credential encryption** | crypto.ts is a sound primitive but has NO real passphrase provenance — callers use a fixed string + an empty string. Need a master-passphrase prompt, OS-keychain, OR delegation to boba-jackett/proxy (which already own encrypted creds at `/config/boba.db`). §11.4.10 blocker. | **HIGH** |
| **Real Boba service integration (7186/7187/7189)** | Reference speaks ONLY raw qBittorrent v2; `BobaServerInfo`/`BobaSearchResponse` types are declared but nothing consumes them. The merge-search API (7187), tracker-cookie download path (7186 proxy), and boba-jackett (7189) clients do not exist. | **HIGH** |
| **`chrome.tabGroups` tab-group batching** | Verified: the reference has NO `chrome.tabGroups` usage. The only "batching" is intra-tab `yieldToBrowser()` cooperative yielding + per-tab `tabTorrents` map + an unused `processInChunks`. Tab-group batch behavior is fresh design. | Med |
| **Icon PNG rasterization (16/32/48/128)** | Verified: `src/assets/` contains `icon.svg` only — zero `.png` files. Code/manifest reference rasterized PNGs that must be produced at build (WXT auto-icons from the SVG). | Low |
| **sql.js storage wrapper** (only if SQL persistence chosen) | The 9-table schema exists but NO runtime wrapper implements it; only the JSON-blob `storage.ts` path is live. | Med |
| **Playwright `global-setup.ts` / `global-teardown.ts`** | Referenced by config, absent from tree. Must build `dist`, launch persistent Chromium `--load-extension`, capture real extension id. | Med |
| **Missing test TYPES** (§11.4.27/§11.4.85): integration (real cross-module → live 7186/7187), functional e2e, automation/HelixQA, security/pen (credential-leak, XSS via magnet `dn`, CSP, permission-scope), DDoS/load, scaling, chaos (storage corruption / network fault / SW termination), stress, performance, benchmark, UI/UX, Challenges | Reference covers only unit + e2e (and those have bluffs). 13 of 15 mandated types absent. | **HIGH** (volume) |

---

## Reuse estimate

Counting the **44 `.ts` source files** plus the SQL schema and the build/test configs:

| Disposition | Approx. count | Examples |
|---|---|---|
| **ADOPT** (reuse ~as-is) | ~17 | bencode, magnet, link/text-scanner, content/scanner+highlight, qbittorrent adapter, crypto module, errors, events, logger, storage, utils, types/torrent, eslint/prettier/tsconfig, i18n |
| **REFACTOR** (bounded fixes) | ~18 | torrent-file (wire), base (un-salt id), site-db (merge tables), client (re-target), auth, queue (auth), health (ports), content/index (contract), background, options, popup, constants (ports), types/config, types/api, wxt.config, package.json, chrome-mock, sql schema |
| **REWRITE** | ~7 | jest.config (runner + coverage), playwright.config, crypto.test, api-client.test (bluff), queue.test (bluff), scanner.test, all 3 e2e specs |
| **NET-NEW** | 7+ areas | key source, Boba-service clients, tab-groups, icon PNGs, sql.js wrapper, e2e global setup, 13 missing test types |
| **DROP** | 2 | both `.github/workflows/*.yml` (constitution hard-stop) |

**Headline: roughly 80% of the reference's logic/structure is reusable** (ADOPT + REFACTOR ≈ 35 of ~44 source-bearing files — the parsers, scanners, shared libs, types, and the API transport are sound), **~20% must be rewritten** (the test suite's bluffs/non-functional e2e + the runner/coverage configs), **and the highest-value work is NET-NEW integration** (real Boba endpoints + a real key source) that the reference never attempted. The reference is a strong *skeleton with sound primitives* whose two structural gaps — credential key-management and Boba-service integration — are exactly the parts it left as placeholders.

## Top 5 highest-risk rewrites

1. **Real key source for credential encryption (NET-NEW).** The sound crypto primitive is currently fed a fixed (`"bobalink-extension"`, `options.ts:327`) and an empty (`""`, `background:409`) passphrase that are even mutually incompatible — the credential path is broken end-to-end and is a §11.4.10 leak (release blocker). Touches options + background + auth.
2. **Boba-service integration / `api/client.ts` re-target (REFACTOR→effectively rewrite of the endpoint layer).** The client speaks only raw qBittorrent v2 on `:8080`; nothing reaches 7186/7187/7189. Re-targeting + adding the Boba-API consumer (`BobaSearchResponse`) is the load-bearing integration, and the SID/cookie + CORS/host-permission story is fragile.
3. **Functional e2e suite (REWRITE all 3 specs + author global-setup/teardown).** Every reference e2e is non-functional (hardcoded `chrome-extension://test-id`, no extension load, presence-only asserts). §11.4 anti-bluff demands real extension load + user-observable outcomes — this is from-scratch.
4. **`crypto.test.ts` (REWRITE).** The single most thorough test file (44 cases) is a §11.4.1 bluff — it tests an inline copy, never the production module, so it passes against a no-op stub. Must be re-pointed at `shared/crypto` and the runner standardized (mixed Jest/Vitest).
5. **Test runner + coverage config (jest.config REWRITE).** 80% threshold with UI/entrypoints excluded conflicts with §11.4.27; the runner decision (Vitest vs Jest) is foundational and gates every other test file's port. (Close behind: `queue.ts` auth-gap fix + the `base.ts` time-salted-id fix, both correctness-critical for offline retries and dedup.)

---

## Disagreements with the extraction's defect claims (re-verified by reading source)

1. **`crypto.ts` → the extraction tags it "🔴 REWRITE"; I DISAGREE — the MODULE is ADOPT, the KEY SOURCE is NET-NEW.** Direct read of `shared/crypto.ts` (lines 42-228) shows the encrypt/decrypt machinery is genuinely sound: PBKDF2 100k iterations, AES-256-GCM, a fresh 16-byte random salt + 12-byte IV per operation, a 128-bit GCM auth tag, and correct `StorageError` wrapping that rejects empty plaintext/passphrase. **No defect exists inside this file.** The defects the extraction cites — fixed passphrase `"bobalink-extension"` (verified `options.ts:327`) and empty passphrase `""` (verified `background/index.ts:409`) — live entirely in the *callers*, not in the crypto module. So the correct disposition is: **ADOPT the crypto primitive unchanged; author the real key source as NET-NEW; REFACTOR the two call-sites.** Rewriting the crypto module itself would be discarding sound, reusable work (§11.4.74). The extraction's "🔴 crypto … → REWRITE" headline conflates the module with its misuse.

2. **Minor: the extraction calls `base.ts` id generation a generic "unstable / time-salted" concern; verified it is a one-line REFACTOR, not a rewrite.** `base.ts:272` literally appends `Date.now().toString(36)` to the hash; removing that suffix and sourcing the id from the (now-wireable) infohash is a bounded fix to a single private method — the rest of `base.ts` (shadow-DOM traversal, hidden-element filtering, re-entrancy guard) is sound and ADOPT-grade.

All other extraction defect claims I sampled were verified accurate: the queue never authenticates (`queue.ts:170` builds+runs with no login), the `.torrent` parser is genuinely never invoked, the two selector tables genuinely diverge, the icon PNGs are genuinely absent (only `icon.svg`), and the two passphrase call-sites are genuinely incompatible.
