# BobaLink Browser Extension — Changelog

**Revision:** 1
**Last modified:** 2026-06-10T23:55:00Z
**Scope:** BobaLink (`extension/`) — WXT + TypeScript Manifest-V3 cross-browser
extension that detects magnet links and `.torrent` URLs and forwards them to the
Boba merge service on port 7187.
**Authority:** `docs/browser_extension/Status.md` (Rev 7),
`docs/browser_extension/RELEASE_READINESS.md`, `git log --oneline`.

> Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
> [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
> **Anti-bluff (§11.4.6 / §11.4.123).** Every entry cites a real commit hash from
> the Session-11 commit set (`024210f 5edf6ac 2011810 5fa78d9 e80c9d9 5e44c85
> 750e4e5`, verified via `git log --oneline`). The five Fixed defects each trace
> to the Status.md Rev 7 / RELEASE_READINESS.md §3 record. No invented entries.

---

## [1.0.0] — Unreleased

**Status: code-complete + comprehensively tested, NOT yet released.** Per
`RELEASE_READINESS.md` §6, a store release is gated on (a) the live-backend
`detect → send → torrent-in-qBittorrent` round-trip against a running `:7187`
turning GREEN (currently INFRA-BLOCKED, honest SKIP — `fetchImpl` stub
substitutes the network boundary) and (b) operator-produced store assets
(screenshots, promotional images, listing submission). Phases 1–3 are PASS;
Phases 4–9 are IN-PROGRESS with enumerated PENDING items.

### Added

- **WXT build wiring → loadable cross-browser artifacts.** WXT entrypoints at
  `src/entrypoints/{background.ts, content.ts, popup/index.html,
  options/index.html}` (thin wrappers over the existing logic modules, so all
  prior test imports stay valid); `wxt build` produces a loadable
  `.output/chrome-mv3/` (`manifest_version:3`, service worker, popup, options,
  content-script, icons 16/32/48/128) AND `.output/firefox-mv2/`. Content-script
  `matches` are derived at build time from the curated `SITE_SELECTORS` table —
  no `<all_urls>`. (`024210f`, `5edf6ac`)
- **Tab-group batched send (`MENU_SEND_GROUP`).** `src/tabgroups/index.ts`
  dedupes detected torrents across a tab group (infohash-first) and dispatches
  the batch as ONE `addMagnets` POST, wired into `background/index.ts`'s
  `MENU_SEND_GROUP` context-menu action. Manifest gains the minimal-privilege
  `tabGroups` permission only (research-confirmed `tabs` not needed — only
  `tab.id` is read). Group-send hardening: offline-queue enqueue-on-failure,
  network-error notification, hardened async flush. (`5edf6ac`, `2011810`)
- **Phase-7 decrypt-before-send credential path.** `BobaClient.create()` decrypts
  the `ServerConfig.encryptedBobaApiToken` AES-256-GCM bundle via `shared/crypto`;
  the background reads the session passphrase from `chrome.storage.session`
  (in-memory, never disk-persisted) and sends the decrypted PLAINTEXT token as a
  bearer header. Default-open when locked / no token — the ciphertext is never
  sent. The token value and passphrase are never logged. (`e8fde43`, `2011810`)
- **8-locale internationalization.** `_locales/{en,ru,de,fr,es,it,pt,ja}` — the
  plan's 8-locale target reached — each at 29-key + placeholder parity, packaged
  into both the chrome and firefox builds, mutation-proven by
  `locale-parity.test.ts` (every non-`en` locale checked against `en`).
  (`5fa78d9`, `e80c9d9`, `750e4e5`)
- **Accessibility — WAI-ARIA structure + keyboard navigation.** Structural a11y
  tests (`tests/a11y/{popup,options}.a11y.test.ts`, 18 — roles / accessible
  names / tablist↔tabpanel / live-regions) plus the options tablist WAI-ARIA
  Arrow/Home/End keyboard pattern (`tests/a11y/keyboard-nav.a11y.test.ts`, 18),
  all mutation-proven. (`2011810`, `5e44c85`)
- **Multi-type test corpus.** Performance/benchmark (`tests/perf/*` — parser /
  scanner / crypto distributions, 10×-regression-catching, 3×-deterministic),
  stress (`tests/stress/{parsers,queue}.stress.test.ts` — ≥1000 enqueue, FIFO,
  concurrent), chaos (`tests/chaos/queue.chaos.test.ts` — corruption, soft/hard
  fail, dead-letter, send-failure injection), security (`tests/security/*`), and
  integration (`tests/integration/pipeline.test.ts` — detect → POST `:7187`
  request URL+body → queue persist+drain over the real `sendMessage→onMessage`
  bridge). (`fa03323`, `024210f`, `2011810`, `5e44c85`, `750e4e5`)
- **Manual CI gate `extension/ci-ext.sh`.** tsc → lint → full Vitest → chrome +
  firefox builds → §11.4.38 artifact-verify (opens the produced `manifest.json`
  and asserts every referenced asset + the `default_locale → _locales/` catalog
  exist non-zero on disk) → per-store `wxt zip`
  (`bobalink-1.0.0-{chrome,firefox,sources}.zip`). Final line `CI-EXT: PASS`. No
  CI/CD — manual only. (`5fa78d9`)
- **Challenges + HelixQA bank.**
  `challenges/extension/detect_and_forward_challenge.sh` drives the REAL
  orchestrator + client end-to-end (PASS on captured evidence, mutation-verified:
  no-op stub → FAIL); plus `decrypt_and_send_challenge.sh`,
  `offline_queue_recovery_challenge.sh`; HelixQA bank `boba-bobalink.yaml`
  (BOBA-LINK-007/008/009/010, `http:` cases live-gated on `:7187`). (`2011810`,
  `5e44c85`)

### Fixed

- **`_locales` packaging — would have FAILED Chrome load.** The manifest declared
  `default_locale:"en"` + `__MSG_*__` but the build packaged no `_locales/` (WXT
  copies static assets from `src/public/`, the catalog lived at `src/_locales/`),
  so Chrome would have rejected the unpacked extension. Fixed by moving the
  catalog to `src/public/_locales/`; permanent guard is the `ci-ext.sh` §11.4.38
  artifact-open step. (`5fa78d9`)
- **Popup false-failure — popup↔background contract bug.** The popup read
  `r.torrent.id` but the real background returns a flat `SendOutcome {id,…}`, so a
  SUCCESSFUL send threw in the popup and showed a false "Send failed" (the row
  never flipped to Sent). Fixed (popup reads `r.id`; the popup-unit fake that had
  masked it corrected; integration assertion reconciled per §11.4.120). (`e80c9d9`)
- **Scan-result trust-overwrite — content-script trust bug.** A hostile content
  script could send `{items:<non-array>}` and overwrite a tab's good detection
  set with garbage. Fixed with the `isValidScanResult` shape-guard in the
  background message router (the non-array test seeds-good→corrupt and asserts the
  good set survives). (`e80c9d9`)
- **ReDoS in `sanitizeDisplayName` — O(n²) → linear.** A hostile magnet `dn` of
  `'<'×100k` took 4s+ and could hang the content script. Fixed `/<[^>]*>/g` →
  `/<[^<>]*>/g`: linear time (output identical on valid input, strictly safer on
  hostile — now catches `<scr<script>ipt>` evasion). 19 hostile-input tests in
  `tests/security/scanner-hostile-input.test.ts`. (`5e44c85`,
  `src/parser/magnet.ts`)
- **A11y keyboard gap — WAI-ARIA tablist arrow-key pattern (WCAG 2.1.1).** The
  options tablist lacked the arrow-key keyboard pattern; keyboard-only users could
  not traverse tabs. Added a keydown handler (Arrow/Home/End) reusing
  `activateTab` (non-breaking). 18 keyboard-nav tests. (`5e44c85`,
  `src/options/options.ts`)

### Security

- **ReDoS hardening of the magnet display-name sanitizer** (see Fixed above) —
  linear-time tag stripping, hostile-input fuzz corpus. (`5e44c85`)
- **Scan-result trust-guard** — `isValidScanResult` shape-validation at the
  content→background trust boundary so a hostile content script cannot poison a
  tab's detection set (16 message-router-robustness tests). (`e80c9d9`)
- **Least-privilege manifest.** No `<all_urls>` (content-script `matches` derived
  from `SITE_SELECTORS`); no `scripting`/`tabs`/`cookies`; `tabGroups` added only
  for the Phase-5 batch send; `host_permissions` = `http://localhost:7187/*`
  only; CSP `script-src 'self'`. Backed by `tests/security/*` (least-privilege
  manifest, CSP, no-hardcoded-secret, secret-storage, content-XSS) and the
  §11.4.10.A `challenges/security/credential_leak_audit.sh` (mutation-verified).
  (`024210f`, `5fa78d9`)
- **No embedded key.** The Boba token is stored AES-256-GCM-encrypted under a
  user-supplied session passphrase (`chrome.storage.session`, never disk); the
  plaintext token and passphrase are never logged or persisted. (`2011810`)

---

## Sources verified 2026-06-10

- `git log --oneline` — Session-11 commits `024210f 5edf6ac 2011810 5fa78d9
  e80c9d9 5e44c85 750e4e5`
- `docs/browser_extension/Status.md` (Rev 7) — per-phase status, baseline facts,
  §11.4.138 bluff-audit
- `docs/browser_extension/RELEASE_READINESS.md` (Rev 1) — five defects,
  release-blocker enumeration, honest classification
- `extension/src/**` — the real modules each entry traces to (`background/index.ts`,
  `content/index.ts`, `api/boba-client.ts`, `parser/magnet.ts`,
  `options/options.ts`, `tabgroups/index.ts`, `entrypoints/*`)
