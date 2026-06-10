# BobaLink Browser Extension — Status

**Revision:** 4
**Last modified:** 2026-06-10T20:40:00Z
**Scope:** BobaLink (`extension/`) — WXT + TypeScript Manifest-V3 browser extension that detects magnet links and `.torrent` URLs and forwards them to the Boba merge service on port 7187.
**Authority:** master plan `docs/browser_extension/IMPLEMENTATION_PLAN.md` (9 phases).

> Captured-evidence-driven (§11.4.5 / §11.4.45). Every PASS cites a real commit hash
> and/or a verified test/file artifact. Rows lacking runtime evidence are marked
> IN-PROGRESS or PENDING — never PASS (§11.4.6 no-guessing).

## Baseline facts (verified this session — Session 11)

- **HEAD:** `2011810` (pushed); wave-4 (Phase-9 `ci-ext.sh` gate + per-store zips, `ru` locale, content-XSS, credential-leak audit, decrypt-throw parity, tab-group Challenge, and the `_locales` packaging fix) staged for the next commit.
- **Extension test corpus:** **413 Vitest tests across 37 spec files** — same-session
  `npx vitest run` → `Tests 413 passed (413)` — under
  `extension/tests/{unit,perf,stress,chaos,integration,security,e2e}` + `src/**`.
  `npx tsc --noEmit` clean; `npm run lint` 0 errors / 0 warnings. (+126 tests over the
  prior 287/22 baseline: integration 7, security 4 files, stress/chaos 10, locale 4,
  token suites 8, tab-groups 13, a11y 18, group-send nits 2, +more.)
- **WXT build wiring — COMPLETE.** WXT entrypoints exist at
  `extension/src/entrypoints/{background.ts, content.ts, popup/index.html, options/index.html}`
  (thin wrappers over the existing logic modules, so all prior test imports stay valid).
  `npx wxt build` produces a **loadable** `extension/.output/chrome-mv3/` AND
  `firefox-mv2/`: `manifest_version:3`, `background.service_worker:background.js`,
  `popup.html`, `options.html`, `content-scripts/content.js`, icons 16/32/48/128,
  AND `_locales/{en,ru}/messages.json` (REQUIRED because `default_locale:"en"` +
  `__MSG_*__` — see the §11.4.138 note below). **Every manifest-referenced asset +
  the default-locale catalog verified present on disk** by the `ci-ext.sh` manual
  gate (§11.4.38). Content-script `matches` are derived from the curated
  `SITE_SELECTORS` (24 hosts, **no `<all_urls>`**); permissions least-privilege
  (no scripting/tabs/cookies; `+tabGroups` for Phase-5); `host_permissions` =
  `http://localhost:7187/*` only; CSP `script-src 'self'`. Per-store zips
  (`bobalink-1.0.0-{chrome,firefox,sources}.zip`) produced by `ci-ext.sh`.

## Per-phase status

| Phase | Title | Status | Evidence |
|-------|-------|--------|----------|
| 1 | Foundation & scaffolding (WXT config, TS, shared libs, types, constants) | PASS | Scaffolded @`33a9815`; shared-lib + constants + type-guard unit specs green @`15a9a61` |
| 2 | Core detection & parsing engine (parsers, scanners, infohash dedup) | PASS | Parsers @`7225470`/`fa03323`; SHA-1 infohash + link/text scanners + perf/stress @`fa03323`; scanner orchestrator cross-scanner dedup @`946c61e` |
| 3 | Extension shell — content / background / popup / options | PASS | Shell @`e8fde43`; background service-worker message router capstone @`15a9a61` |
| — | WXT build wiring (`entrypoints/`, `wxt build` → `.output/`, manifest validate) | **PASS** | Entrypoints `src/entrypoints/{background.ts,content.ts,popup/index.html,options/index.html}`; `npx wxt build` → loadable `.output/chrome-mv3/` (8/8 manifest assets verified present, §11.4.38); matches derived from `SITE_SELECTORS`, no `<all_urls>` (Session 11 @`5edf6ac`, pushed) |
| 4 | Boba backend integration (real client, queue auth, BE-1/2/3) | IN-PROGRESS | API leaf @`e8fde43`. **Phase-7 decrypt-before-send wired** (Session 11): `BobaClient.create()` decrypts the `encryptedBobaApiToken` bundle via `shared/crypto`; `background` reads the session passphrase from `chrome.storage.session` and sends the decrypted plaintext (default-open when locked). Token suites `boba-client-token.test.ts` 5 + `background-token.test.ts` 3 green. **PENDING:** live-7187 integration (`require_backend(7187)`), end-to-end detect→send→torrent-in-qBittorrent on the real backend |
| 5 | Tab-group batch (`chrome.tabGroups` → per-tab scan → batch send) | IN-PROGRESS | **Wired** (Session 11): `src/tabgroups/index.ts` (dedupe across a group + batch dispatch, 13 tests) **integrated into `background/index.ts` `MENU_SEND_GROUP`** (deduped group batch → one `addMagnets` POST); manifest `+tabGroups` (MINIMAL — research-confirmed `tabs` NOT needed since only `tab.id` is read; §11.4.120 security-test reconciliation, mutation-verified). New `background.test.ts` MENU_SEND_GROUP test (RED-verified: handler no-op → FAIL). Independent review: **GO-with-nits**. Group-send nits (a) offline-queue enqueue-on-failure, (b) network-error notification, (c) hardened async flush — all **FIXED** (Session 11, RED→GREEN + 3×-deterministic, independent review GO). **TRACKED:** decrypt-throw (wrong passphrase) on group send not enqueued/notified — pre-existing parity with Send-All, future phase |
| 6 | UI/UX, i18n, accessibility, themes | IN-PROGRESS | i18n: `locale.test.ts` (en completeness) + **`ru` locale added** with `locale-parity.test.ts` (en⇄ru key + placeholder parity, mutation-proven); **a11y**: `tests/a11y/{popup,options}.a11y.test.ts` (18 tests — roles/accessible-names/tablist↔tabpanel/live-regions, mutation-proven). **PENDING:** 6 more locales (plan targets 8), deeper WCAG (contrast/focus/keyboard), theme-switch evidence |
| 7 | Security & credentials (delegate-by-default, no embedded key, log redaction) | IN-PROGRESS | `crypto.ts` adopted; **decrypt-and-send path landed** + **decrypt-throw on wrong passphrase now enqueues+notifies** (parity, RED→GREEN); session passphrase from `chrome.storage.session`, **no embedded key**, plaintext/passphrase never logged; security suite `tests/security/*` (least-privilege manifest, CSP, no-hardcoded-secret, secret-storage, **content-XSS** — render path proven safe via innerHTML-mutation→FAIL); **§11.4.10.A credential-leak audit** `challenges/security/credential_leak_audit.sh` (PASS, mutation-verified). **PENDING:** full pen-test suite (sender-origin validation, rate-limit) |
| 8 | Testing to 100% (all types) + Challenges + HelixQA | IN-PROGRESS | 413 tests/37 files green (unit/perf/stress/chaos/integration/security/e2e). Challenge `challenges/extension/detect_and_forward_challenge.sh` drives the REAL orchestrator+client end-to-end, PASS on captured evidence, mutation-verified (no-op stub → FAIL). HelixQA `boba-bobalink.yaml` BOBA-LINK-007 (detect→forward) + BOBA-LINK-008 (tab-group batch) added; symlinked into `challenges/helixqa-banks/`. tab-group + detect→forward Challenges both mutation-verified. E2E `tests/e2e/extension-loads.spec.ts` is a real MV3-load test, **operator-gated SKIP** in this headless sandbox (extension load unsupported; §11.4.3). **PENDING:** the full 13-type coverage matrix + live-backend integration + the coverage ledger to 100% |
| 9 | Build, packaging & distribution (manual — NO CI/CD) | IN-PROGRESS | **Manual gate `extension/ci-ext.sh`** (Session 11, §11.4.18 doc'd): tsc → lint → full vitest → chrome+firefox builds → §11.4.38 artifact-verify (opens the manifest, asserts every referenced asset + the `default_locale` catalog exist non-zero) → per-store `wxt zip`. **CI-EXT: PASS** — produces loadable `chrome-mv3/` + `firefox-mv2/` + `bobalink-1.0.0-{chrome,firefox,sources}.zip`. **PENDING:** store-listing metadata/submission + §11.4.65 user/dev/install doc siblings. NO CI/CD (manual only) |

## Status legend

- **PASS** — implemented and backed by a cited commit and/or verified test/file evidence.
- **IN-PROGRESS** — partially landed; some sub-tasks done with evidence, remainder explicitly enumerated as PENDING.
- **PENDING** — not yet started / no runtime evidence; planned in `IMPLEMENTATION_PLAN.md`.

## Anti-bluff notes (§11.4 / §11.4.6 / §11.4.69)

- The 413 figure IS a same-session recorded `npx vitest run` result (`Tests 413 passed (413)`),
  not merely a static grep — it supersedes the prior 287/22 grep-count baseline. tsc + lint
  captured clean in the same session.
- The §11.4.38 loadable-artifact claim is verified by `ci-ext.sh` **opening the produced
  `.output/chrome-mv3/manifest.json`** and confirming every referenced asset AND the
  `default_locale` catalog exist non-zero on disk — not by "build exited 0".
- **§11.4.138 bluff-audit (corrected this session).** An earlier Status revision claimed the
  artifact was loadable on an "8/8 referenced assets present" check. That check was INCOMPLETE:
  the manifest declares `default_locale:"en"` + `__MSG_*__`, but the build packaged **no
  `_locales/`** (WXT copies static assets from `src/public/`, while the catalog lived at
  `src/_locales/`) — so Chrome would have REJECTED the extension at load. Caught by the new
  `ci-ext.sh` §11.4.38 step (which checks the `default_locale → _locales/` invariant). Root
  cause fixed by moving the catalog to `src/public/_locales/{en,ru}/`; the rebuilt artifact now
  packages it (verified on disk). Permanent guard = `ci-ext.sh` (the regression can't recur
  silently). This is the §11.4.108 lesson: build-exit-0 ≠ deployable-artifact.
- The Phase-7 decrypt path is proven by RED→GREEN: ciphertext-on-the-wire (pre-fix) →
  decrypted-plaintext header (post-fix), with the ciphertext never sent and the token never
  logged (`background-token.test.ts`, `boba-client-token.test.ts`).
- The detect→forward Challenge was independently re-run and its no-op-stub negation verified
  (stubbed orchestrator → FAIL) during code review.
- Independent multi-lens subagent code-review (correctness/security/build/docs) was run;
  the security + correctness + build + docs lenses returned GO / GO-with-nits. (The
  correctness/security/build subagent lenses were re-run in the conductor context after a
  transient platform throttle on subagent dispatch; an independent subagent re-pass runs
  before any release tag per §11.4.40.)
