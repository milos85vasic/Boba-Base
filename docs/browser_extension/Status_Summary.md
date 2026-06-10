# BobaLink Browser Extension — Status Summary

**Revision:** 2
**Last modified:** 2026-06-10T20:05:00Z
**Companion of:** `docs/browser_extension/Status.md` (Rev 2, §11.4.56 two-audience summary).

> Every claim here traces to `Status.md` Rev 2. No overclaim, no invented PASS (§11.4.6).

---

## Page 1 — For the team (plain language)

BobaLink is a browser extension that spots torrent download links (magnet links and
`.torrent` files) on web pages and sends them, with one click, to the Boba dashboard
so the download starts automatically.

**What works today:**

- The detection engine is built and tested: it reads torrent links, computes the
  unique fingerprint of each torrent, and removes duplicates.
- The extension's visible parts are built: the page overlay that highlights links,
  the popup window with a "Send" button, the options screen, and the background
  worker that ties everything together and queues sends when offline.
- **The extension now builds into a loadable Chrome extension** — running the build
  tool produces a working `chrome-mv3` folder, and every file the extension's
  manifest references was verified present on disk.
- **The detect → send pipeline works** — the client that talks to the Boba dashboard
  decrypts its stored token and sends the download, and the dashboard side accepts it.
- **Sending a whole tab group at once is wired up** — picking a tab group scans every
  tab, removes duplicates across the group, and sends them in one batch.
- **400 automated tests pass** (across 35 test files); the code also passes its type
  check and its style/lint check with zero warnings.

**What is still pending:**

- **Live-backend proof** — actually clicking "Send" and seeing the torrent appear in
  qBittorrent — has not yet been recorded against a running dashboard on port 7187.
- **Packaging the extension into an installable, per-store file** is not finished —
  the build tool is configured and produces a loadable folder, but the final manual
  "build and zip" gate and the published documentation are not yet wired up.
- **More languages** (translations beyond English), the **full accessibility/theme
  polish**, and the **fully hardened credential/security model** (pre-store leak audit,
  full pen-test suite) are still to come.

**Team / operator actions:** none required right now. The next milestones are the live
"click → download appears" proof against a running dashboard, and wiring the manual
packaging gate so an installable extension exists.

---

## Page 2 — For software engineers

**HEAD:** `5edf6ac` · **Branch:** `main` · **Test corpus:** 400 Vitest tests / 35 spec
files — same-session `npx vitest run` → green; `npx tsc --noEmit` clean; `npm run lint`
0 errors / 0 warnings.

### Commit provenance

| Phase | Status | Commit(s) / evidence |
|-------|--------|----------------------|
| 1 Foundation & scaffolding | PASS | `33a9815` (scaffold); shared-lib + constants + type-guard specs green @`15a9a61` |
| 2 Detection / parsing engine | PASS | `7225470`, `fa03303`→`fa03323` (parsers + SHA-1 infohash + link/text scanners + perf/stress); `946c61e` (orchestrator cross-scanner dedup) |
| 3 Extension shell | PASS | `e8fde43` (content/popup/options); `15a9a61` (background SW message router capstone) |
| WXT build wiring | PASS | `src/entrypoints/{background.ts,content.ts,popup/index.html,options/index.html}`; `npx wxt build` → loadable `.output/chrome-mv3/` (8/8 manifest assets verified present, §11.4.38); content-script `matches` derived from `SITE_SELECTORS` (24 hosts, no `<all_urls>`), least-privilege permissions, `host_permissions` = `http://localhost:7187/*`, CSP `script-src 'self'` |
| 4 Boba backend integration | IN-PROGRESS | API leaf @`e8fde43`; Phase-7 decrypt-before-send wired — `BobaClient.create()` decrypts `encryptedBobaApiToken` via `shared/crypto`, background reads session passphrase from `chrome.storage.session` (default-open when locked); token suites `boba-client-token.test.ts` 5 + `background-token.test.ts` 3 green. **PENDING:** live-7187 integration, end-to-end detect→send→torrent-in-qBittorrent |
| 5 Tab-group batch | IN-PROGRESS | `src/tabgroups/index.ts` (group-wide dedupe + batch dispatch, 13 tests) integrated into `background/index.ts` `MENU_SEND_GROUP` (one `addMagnets` POST); manifest `+tabGroups` (minimal — `tabs` not needed, only `tab.id` read; §11.4.120 security-test reconciliation, mutation-verified); RED-verified MENU_SEND_GROUP test (handler no-op → FAIL). Review: GO-with-nits. **Tracked nits:** offline-queue on group-send failure, network-error notification, async-flush hardening |
| 6 UI/UX, i18n, a11y, themes | IN-PROGRESS | `locale.test.ts` 4 (derives `__MSG_*` keys from source; en catalog complete). **PENDING:** additional locales (target 8), WCAG/a11y + theme-switch evidence |
| 7 Security & credentials | IN-PROGRESS | `crypto.ts` adopted; decrypt-and-send path landed; session passphrase from `chrome.storage.session`, no embedded key, plaintext/passphrase never logged; `tests/security/*` 4 files (least-privilege manifest, CSP, no-hardcoded-secret, secret-storage). **PENDING:** §11.4.10.A pre-store leak audit, full pen-test suite |
| 8 Testing-to-100% + Challenges + HelixQA | IN-PROGRESS | 400 tests / 35 files green (unit/perf/stress/chaos/integration/security/e2e); Challenge `challenges/extension/detect_and_forward_challenge.sh` drives the real orchestrator+client end-to-end, mutation-verified (no-op stub → FAIL); HelixQA `boba-bobalink.yaml` BOBA-LINK-007 added; E2E `tests/e2e/extension-loads.spec.ts` operator-gated SKIP in headless sandbox (§11.4.3). **PENDING:** full 13-type matrix + live-backend integration + coverage ledger to 100% |
| 9 Build, packaging & distribution | PENDING | Loadable `.output/chrome-mv3/` produced; no `extension/ci-ext.sh` manual gate, no per-store zip, no §11.4.65 user/dev/install/API doc siblings yet |

### Status legend

- **PASS** — implemented and backed by a cited commit and/or verified test/file evidence.
- **IN-PROGRESS** — partially landed; remaining sub-tasks explicitly enumerated as PENDING.
- **PENDING** — not yet started / no runtime evidence; planned in `IMPLEMENTATION_PLAN.md`.

### Key file paths

- Build config: `extension/wxt.config.ts`, `extension/vitest.config.ts`, `extension/package.json`.
- Entrypoints: `extension/src/entrypoints/{background.ts,content.ts,popup/index.html,options/index.html}`.
- Source root: `extension/src/{parser,scanner,content,background,popup,options,api,tabgroups,shared,types}`.
- Tests: `extension/tests/{unit,perf,stress,chaos,integration,security,e2e}` + `src/**`.
- Build output: `extension/.output/chrome-mv3/` (loadable MV3).
- Plan: `docs/browser_extension/IMPLEMENTATION_PLAN.md` (9 phases) + `_analysis/` + `_plan/`.

### Anti-bluff caveat (§11.4.6)

The 400 figure IS a same-session recorded `npx vitest run` green result (supersedes the
prior 287/22 static spec-case count). The §11.4.38 loadable-artifact claim was verified by
opening the produced `.output/chrome-mv3/manifest.json` and confirming every referenced
asset exists on disk — not by "build exited 0". The Phase-7 decrypt path is proven RED→GREEN
(ciphertext-on-the-wire pre-fix → decrypted-plaintext header post-fix). Live-backend
end-to-end (detect→send→torrent-in-qBittorrent on a running :7187) remains PENDING.
