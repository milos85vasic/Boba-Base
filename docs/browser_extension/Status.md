# BobaLink Browser Extension — Status

**Revision:** 2
**Last modified:** 2026-06-10T19:30:00Z
**Scope:** BobaLink (`extension/`) — WXT + TypeScript Manifest-V3 browser extension that detects magnet links and `.torrent` URLs and forwards them to the Boba merge service on port 7187.
**Authority:** master plan `docs/browser_extension/IMPLEMENTATION_PLAN.md` (9 phases).

> Captured-evidence-driven (§11.4.5 / §11.4.45). Every PASS cites a real commit hash
> and/or a verified test/file artifact. Rows lacking runtime evidence are marked
> IN-PROGRESS or PENDING — never PASS (§11.4.6 no-guessing).

## Baseline facts (verified this session — Session 11)

- **HEAD:** `15a9a61`; the work below is staged for the next commit (reviewed checkpoint).
- **Extension test corpus:** **379 Vitest tests across 33 spec files** — same-session
  `npx vitest run` → `Tests 379 passed (379)` — under
  `extension/tests/{unit,perf,stress,chaos,integration,security,e2e}` + `src/**`.
  `npx tsc --noEmit` clean; `npm run lint` 0 errors / 0 warnings. (+92 tests over the
  prior 287/22 baseline: integration 7, security 4 files, stress/chaos 10, locale 4,
  token suites 8, tab-groups 13.)
- **WXT build wiring — COMPLETE.** WXT entrypoints exist at
  `extension/src/entrypoints/{background.ts, content.ts, popup/index.html, options/index.html}`
  (thin wrappers over the existing logic modules, so all prior test imports stay valid).
  `npx wxt build` produces a **loadable** `extension/.output/chrome-mv3/`:
  `manifest_version:3`, `background.service_worker:background.js`, `popup.html`,
  `options.html`, `content-scripts/content.js`, icons 16/32/48/128 — **every
  manifest-referenced asset verified present on disk** (§11.4.38: PASS). Content-script
  `matches` are derived from the curated `SITE_SELECTORS` (24 hosts, **no `<all_urls>`**);
  permissions least-privilege (no scripting/tabs/cookies); `host_permissions` =
  `http://localhost:7187/*` only; CSP `script-src 'self'`.

## Per-phase status

| Phase | Title | Status | Evidence |
|-------|-------|--------|----------|
| 1 | Foundation & scaffolding (WXT config, TS, shared libs, types, constants) | PASS | Scaffolded @`33a9815`; shared-lib + constants + type-guard unit specs green @`15a9a61` |
| 2 | Core detection & parsing engine (parsers, scanners, infohash dedup) | PASS | Parsers @`7225470`/`fa03323`; SHA-1 infohash + link/text scanners + perf/stress @`fa03323`; scanner orchestrator cross-scanner dedup @`946c61e` |
| 3 | Extension shell — content / background / popup / options | PASS | Shell @`e8fde43`; background service-worker message router capstone @`15a9a61` |
| — | WXT build wiring (`entrypoints/`, `wxt build` → `.output/`, manifest validate) | **PASS** | Entrypoints `src/entrypoints/{background.ts,content.ts,popup/index.html,options/index.html}`; `npx wxt build` → loadable `.output/chrome-mv3/` (8/8 manifest assets verified present, §11.4.38); matches derived from `SITE_SELECTORS`, no `<all_urls>` (Session 11, uncommitted) |
| 4 | Boba backend integration (real client, queue auth, BE-1/2/3) | IN-PROGRESS | API leaf @`e8fde43`. **Phase-7 decrypt-before-send wired** (Session 11): `BobaClient.create()` decrypts the `encryptedBobaApiToken` bundle via `shared/crypto`; `background` reads the session passphrase from `chrome.storage.session` and sends the decrypted plaintext (default-open when locked). Token suites `boba-client-token.test.ts` 5 + `background-token.test.ts` 3 green. **PENDING:** live-7187 integration (`require_backend(7187)`), end-to-end detect→send→torrent-in-qBittorrent on the real backend |
| 5 | Tab-group batch (`chrome.tabGroups` → per-tab scan → batch send) | IN-PROGRESS | **Wired** (Session 11): `src/tabgroups/index.ts` (dedupe across a group + batch dispatch, 13 tests) **integrated into `background/index.ts` `MENU_SEND_GROUP`** (deduped group batch → one `addMagnets` POST); manifest `+tabGroups` (MINIMAL — research-confirmed `tabs` NOT needed since only `tab.id` is read; §11.4.120 security-test reconciliation, mutation-verified). New `background.test.ts` MENU_SEND_GROUP test (RED-verified: handler no-op → FAIL). Independent review: **GO-with-nits**. **TRACKED future-phase nits:** (a) enqueue the batch into `OfflineQueue` on group-send failure (UX parity with Send-All); (b) surface a notification on a group-send network error; (c) harden the test's async flush to await a real completion signal |
| 6 | UI/UX, i18n, accessibility, themes | IN-PROGRESS | i18n locale completeness guarded: `locale.test.ts` 4 (derives referenced `__MSG_*` keys from source; en catalog complete). **PENDING:** additional locales (plan targets 8), WCAG/a11y + theme-switch evidence |
| 7 | Security & credentials (delegate-by-default, no embedded key, log redaction) | IN-PROGRESS | `crypto.ts` adopted; **decrypt-and-send path landed** (Phase-4 row); session passphrase from `chrome.storage.session`, **no embedded key**, plaintext/passphrase never logged; security suite `tests/security/*` 4 files (least-privilege manifest, CSP, no-hardcoded-secret, secret-storage). **PENDING:** §11.4.10.A pre-store leak audit, full pen-test suite |
| 8 | Testing to 100% (all types) + Challenges + HelixQA | IN-PROGRESS | 379 tests/33 files green (unit/perf/stress/chaos/integration/security/e2e). Challenge `challenges/extension/detect_and_forward_challenge.sh` drives the REAL orchestrator+client end-to-end, PASS on captured evidence, mutation-verified (no-op stub → FAIL). HelixQA `boba-bobalink.yaml` BOBA-LINK-007 added; symlinked into `challenges/helixqa-banks/`. E2E `tests/e2e/extension-loads.spec.ts` is a real MV3-load test, **operator-gated SKIP** in this headless sandbox (extension load unsupported; §11.4.3). **PENDING:** the full 13-type coverage matrix + live-backend integration + the coverage ledger to 100% |
| 9 | Build, packaging & distribution (manual — NO CI/CD) | PENDING | Loadable `.output/chrome-mv3/` produced, but no `extension/ci-ext.sh` manual gate, no per-store zip, no §11.4.65 user/dev/install/API doc siblings yet |

## Status legend

- **PASS** — implemented and backed by a cited commit and/or verified test/file evidence.
- **IN-PROGRESS** — partially landed; some sub-tasks done with evidence, remainder explicitly enumerated as PENDING.
- **PENDING** — not yet started / no runtime evidence; planned in `IMPLEMENTATION_PLAN.md`.

## Anti-bluff notes (§11.4 / §11.4.6 / §11.4.69)

- The 379 figure IS a same-session recorded `npx vitest run` result (`Tests 379 passed (379)`),
  not merely a static grep — it supersedes the prior 287/22 grep-count baseline. tsc + lint
  captured clean in the same session.
- The §11.4.38 loadable-artifact claim was verified by **opening the produced
  `.output/chrome-mv3/manifest.json`** and confirming every referenced asset exists on disk —
  not by "build exited 0".
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
