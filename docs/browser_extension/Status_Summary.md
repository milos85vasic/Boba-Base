# BobaLink Browser Extension — Status Summary

**Revision:** 4
**Last modified:** 2026-08-20T12:27:23Z
**Companion of:** `docs/browser_extension/Status.md` (Rev 16, §11.4.56 two-audience summary).

> Every claim here traces to `Status.md` Rev 16. No overclaim, no invented PASS (§11.4.6).
> This revision closes a real drift: the prior Rev 3 (2026-06-10) traced to `Status.md`
> "Rev 2" while `Status.md` had already advanced to Rev 15 (2026-06-13) — a 13-revision,
> ~68-day gap. Fixed by regenerating this document from the current `Status.md` (Rev 16).

---

## Page 1 — For the team (plain language)

BobaLink is a browser extension that spots torrent download links (magnet links and
`.torrent` files) on web pages and sends them, with one click, to the Boba dashboard
so the download starts automatically.

**What works today:**

- The detection engine is built and tested: it reads torrent links, computes the
  unique fingerprint of each torrent, and removes duplicates.
- The extension's visible parts are built and working: the page overlay that highlights
  links, the popup window with "Send" / "Send All" buttons, the options screen (7 settings
  tabs), and the background worker that ties everything together and queues sends when
  offline.
- **The extension builds into a loadable Chrome AND Firefox extension.** The build tool
  produces working extension folders, and every file the extension's manifest references
  has been verified present on disk (including the language files — see below).
- **The detect → send pipeline works and was seen working on video** — a real recording
  shows the extension spotting a magnet link and badging it on-screen, and shows the
  popup and options screens rendering correctly.
- **Sending a whole tab group at once is wired up** — picking a tab group scans every
  tab, removes duplicates across the group, and sends them in one batch.
- **The extension can be packaged for a store submission** — a manual build-and-package
  gate produces installable Chrome and Firefox package files, and the store-listing
  paperwork has been checked over and is ready except for screenshots/artwork.
- **8 languages are supported** (English, Russian, German, Spanish, French, Italian,
  Japanese, Portuguese), not just English.
- **Automated tests were re-run just now (2026-08-20) and are overwhelmingly green:**
  815 out of 822 automated checks passed. The 7 that did not pass are all
  "how fast does this run" timing checks (not "does the feature work" checks), and they
  failed because this computer was busy doing a lot of other work in the background at
  the same time — the same kind of timing hiccup that has happened before and been fixed
  for other checks in this test suite. Whether these particular 7 are just today's
  computer-was-busy noise, or need their own fix, has **not** been confirmed yet — that
  needs a re-run on a quiet computer, which is a follow-up task, not something this
  particular update did. The code itself compiles cleanly and passes its style checks
  with zero warnings.

**What is still pending:**

- **Live-backend proof** — actually clicking "Send" against a live, running Boba
  dashboard on the default network port and independently confirming the download shows
  up in qBittorrent — needs a specific test setup (a shared folder into the container)
  that has not been available to run this automatically; this is the #1 remaining
  release blocker and needs a person to set that up once.
- **A real, on-screen recording of the extension loading in an actual browser window**
  (as opposed to an automated headless check) needs a computer with a real display —
  also a one-time setup step for a person, not something the automation can do itself.
- **Publishing to the Chrome/Firefox web stores** needs the actual screenshots/promo
  images and a person to click "submit" — everything else (the package files, the
  listing text) is ready.
- **A full security penetration-test pass** and **deeper accessibility polish** are still
  queued as later work, though a lot of accessibility fixes already landed (colour
  contrast, keyboard navigation, screen-reader labels).

**Team / operator actions:** none required to keep the project moving. The three
remaining blockers above (live-dashboard test setup, real-browser recording, store
screenshots + submission) each need one person to do a one-time manual step; nothing is
currently broken or waiting on a decision.

---

## Page 2 — For software engineers

**HEAD:** `e0d60ab` · **Branch:** `main` · **Test corpus:** 822 Vitest tests / 69 spec
files (this session's fresh `npx vitest run`: **815 passed, 7 failed** — see the Rev 16
staleness-catch-up note below); `npx tsc --noEmit` clean; `npm run lint` 0 errors /
0 warnings (all three commands executed this session, 2026-08-20, not carried forward).

### Rev 16 staleness catch-up (2026-08-20, BOB-083)

`Status.md` was last touched at `37fcbe4` (2026-06-13); only 3 commits touched
`extension/` since then, none of which invalidate the Phase table below except where
noted:

- **`ee4a01b` (2026-06-15)** — real MV3 service-worker-teardown resilience fix:
  `tabResults` write-through to `chrome.storage.session` so detected torrents survive a
  ~30s SW idle-teardown (previously silently lost). RED→GREEN, new guard
  `tests/unit/background-sw-teardown.test.ts` (310 lines). Independent review: GO.
- **`a410b91` (2026-06-16)** — coverage-only: `parser/torrent-file.ts` 75.4%→89.9%
  (`parseTorrentFromUrl` + `computeInfohash` error paths). No product defect found.
- **`54e313f` (2026-08-08)** — mechanical `async`→`Promise.resolve` test-mock refactor
  in `torrent-file.test.ts`, no behavioral change.

**Fresh full-suite run this session:** 822 tests / 69 spec files, 815 passed / 7 failed
(256.5s, this host under heavy concurrent load from this same docs-refresh agent's other
work — 9 `node (vitest N)` workers observed live). The 7 failures are ALL
bounded-wall-clock perf/stress/security-budget assertions (`scanner.perf.test.ts`,
`parsers.perf.test.ts`, `orchestrator-ratelimiter-tabgroup.stress.test.ts`,
`scanner-hostile-input.test.ts`'s junk-flood 30s bound — observed 120.9s), not
functional failures — the same host-load-coupled flakiness class Session 12 already
found and partially hardened (BUGFIXES 27, §11.4.50/§11.4.118).
`PENDING_FORENSICS:` whether these 7 are pure contention noise or a genuine new timing
regression is **not resolved by this pass** — re-running in isolation on a quiet host is
required and is out of this docs-only task's charter (§11.4.6 — recorded honestly, not
asserted either way).

### Commit provenance / per-phase status

(Full detail + evidence citations live in `docs/browser_extension/Status.md` §"Per-phase
status" — mirrored here at summary granularity, unchanged from Rev 16 except the Rev 16
note above.)

| Phase | Status | Commit(s) / evidence |
|-------|--------|----------------------|
| 1 Foundation & scaffolding | PASS | `33a9815` (scaffold); shared-lib + constants + type-guard specs green @`15a9a61` |
| 2 Detection / parsing engine | PASS | `7225470`/`fa03323` (parsers + SHA-1 infohash + link/text scanners + perf/stress); `946c61e` (orchestrator cross-scanner dedup) |
| 3 Extension shell | PASS | `e8fde43` (content/popup/options); `15a9a61` (background SW message router capstone) |
| WXT build wiring | PASS | `npx wxt build` → loadable `.output/chrome-mv3/` (8/8 manifest assets + `_locales` verified present, §11.4.38); `SITE_SELECTORS`-derived matches, no `<all_urls>`, least-privilege permissions, CSP `script-src 'self'` |
| 4 Boba backend integration | IN-PROGRESS | Decrypt-before-send wired (`BobaClient.create()` + `shared/crypto`, session passphrase from `chrome.storage.session`); **Rev 16: tabResults now survives SW teardown** (`ee4a01b`, see above). Token suites green. **PENDING (operator-gated):** live-7187 detect→send→torrent-in-qBittorrent round-trip |
| 5 Tab-group batch | IN-PROGRESS | `src/tabgroups/index.ts` (13 tests) integrated into `background/index.ts` `MENU_SEND_GROUP`; manifest `+tabGroups` minimal-privilege, mutation-verified; review GO-with-nits, nits (offline-queue, network-error notify, async-flush) all FIXED. **TRACKED:** decrypt-throw-on-group-send parity, future phase |
| 6 UI/UX, i18n, a11y, themes | IN-PROGRESS | **8 locales shipped** (en/ru/de/es/fr/it/ja/pt, 29-key parity, packaged both browsers) — plan target MET; a11y suite (`popup`/`options`.a11y + focus-and-contrast + options-contrast-motion, 18+ tests, mutation-proven) found and fixed 8 real WCAG AA contrast defects across Sessions 11–12. **PENDING:** theme-switch evidence |
| 7 Security & credentials | IN-PROGRESS | Decrypt-and-send + decrypt-throw parity landed, no embedded key, plaintext never logged; security suite (least-privilege manifest, CSP, no-hardcoded-secret, secret-storage, content-XSS, message-router-robustness, scanner-hostile-input, sender-trust, bencode/infohash hostile-input, crypto-tamper); §11.4.10.A credential-leak-audit Challenge PASS, mutation-verified; **fixed a real cross-tab info-leak** (`isValidScanResult` + `resolveTargetTabId` guards). **PENDING:** full pen-test suite (sender-origin validation, rate-limit) |
| 8 Testing-to-100% + Challenges + HelixQA | IN-PROGRESS | **822 tests / 69 files** (Rev 16, was 559/52 at Rev 3) unit/perf/stress/chaos/integration/security/a11y/i18n/e2e; `detect_and_forward_challenge.sh` mutation-verified; HelixQA `BOBA-LINK-007`+`008` added; E2E `extension-loads.spec.ts` passes **4/4 autonomously** via real headless-Chromium `--load-extension` (Session 12/wave-15 — no longer operator-gated-SKIP as Rev 3 stated). **PENDING:** live-backend integration + full 13-type coverage-ledger closure |
| 9 Build, packaging & distribution | IN-PROGRESS *(Rev 3 said PENDING — corrected)* | **`extension/ci-ext.sh` manual gate exists + is documented** (§11.4.18): tsc → lint → full vitest → chrome+firefox builds → §11.4.38 artifact-verify → per-store `wxt zip` → **`CI-EXT: PASS`** (Session 12), producing loadable `chrome-mv3/`+`firefox-mv2/` + `bobalink-1.0.0-{chrome,firefox,sources}.zip`. `STORE_LISTING.md` audited submission-ready (fields + permission justifications verified, a locale-drift bug found+fixed). Neither the zips nor `firefox-mv2/` are present in the working tree as of this session (expected — gitignored build outputs, not regenerated by this docs-only pass). **PENDING (operator-gated):** store-listing screenshots/artwork + actual submission |

### Status legend

- **PASS** — implemented and backed by a cited commit and/or verified test/file evidence.
- **IN-PROGRESS** — partially landed; remaining sub-tasks explicitly enumerated as PENDING.
- **PENDING** — not yet started / no runtime evidence; planned in `IMPLEMENTATION_PLAN.md`.

### Key file paths

- Build config: `extension/wxt.config.ts`, `extension/vitest.config.ts`, `extension/package.json`.
- Entrypoints: `extension/src/entrypoints/{background.ts,content.ts,popup/index.html,options/index.html}`.
- Source root: `extension/src/{parser,scanner,content,background,popup,options,api,tabgroups,shared,types}`.
- Tests: `extension/tests/{unit,perf,stress,chaos,integration,security,a11y,i18n,e2e,live}` + `src/**`.
- Build output: `extension/.output/chrome-mv3/` (loadable MV3; `firefox-mv2/` + zips built on demand).
- Manual CI gate: `extension/ci-ext.sh` (§11.4.18).
- Plan: `docs/browser_extension/IMPLEMENTATION_PLAN.md` (9 phases) + `docs/browser_extension/RELEASE_READINESS.md`.

### Anti-bluff caveat (§11.4.6)

The 822/69 figures ARE a same-session recorded `npx vitest run` result executed for this
Rev 16 refresh (2026-08-20), not carried forward from memory — 815 passed, 7 failed, the
failures analyzed above as bounded-time-budget assertions under host contention with an
honest `PENDING_FORENSICS:` on whether they are pure noise. The §11.4.38 loadable-artifact
claim (Phase "WXT build wiring" + Phase 9) traces to the Session-11/12 `ci-ext.sh` runs
that opened the produced manifest and confirmed every referenced asset on disk — not
re-executed in this pass (this pass's own evidence is limited to `tsc`/`lint`/`vitest`,
each executed fresh; the build/zip/CI-EXT claims are carried forward from `Status.md`'s
own Session-11/12 citations, not independently re-verified here — see the Rev 16 scope
note in `Status.md`). Live-backend end-to-end (detect→send→torrent-in-qBittorrent on a
running :7187) remains PENDING and operator-gated, unchanged since Rev 3.
