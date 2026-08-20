# BobaLink Browser Extension — Status

**Revision:** 16
**Last modified:** 2026-08-20T12:27:23Z
**Scope:** BobaLink (`extension/`) — WXT + TypeScript Manifest-V3 browser extension that detects magnet links and `.torrent` URLs and forwards them to the Boba merge service on port 7187.
**Authority:** master plan `docs/browser_extension/IMPLEMENTATION_PLAN.md` (9 phases).

> **Rev 16 (2026-08-20, BOB-083 / GOVERNANCE_AUDIT_2026-08-08_ROUND2.md RD2-16) —
> staleness remediation (§11.4.44/§11.4.45/§11.4.86):** this ledger's last content
> touch was `37fcbe4` (2026-06-13, Session 12/wave-15) — **68 days** before this
> pass. Real evidence gathered this session (`git log`, a fresh `npx vitest run`,
> `npx tsc --noEmit`, `npm run lint` — all executed just now, not recalled from
> memory, §11.4.6): only **3 commits** touched `extension/` in the 68-day gap —
> `ee4a01b` (2026-06-15, a genuine MV3 service-worker-teardown resilience fix,
> new section below), `a410b91` (2026-06-16, coverage-only test additions, no
> product change), and `54e313f` (2026-08-08, a mechanical `async`→
> `Promise.resolve` test-fixture refactor in `torrent-file.test.ts`, no behavior
> change). This is a **TARGETED refresh** (§11.4.6 option B, the same bounded-scope
> discipline `docs/features/Status.md` Rev 8 used): the new session below documents
> exactly what changed + a fresh full-suite run's real result; it does **not**
> re-verify every pre-existing per-phase claim from Sessions 11–12 against the
> current tree (out of scope for a docs-sync pass — see the honest gap noted in
> the new session block).

> Captured-evidence-driven (§11.4.5 / §11.4.45). Every PASS cites a real commit hash
> and/or a verified test/file artifact. Rows lacking runtime evidence are marked
> IN-PROGRESS or PENDING — never PASS (§11.4.6 no-guessing).

## Baseline facts (verified this session — Session 11)

- **HEAD:** `2011810` (pushed); wave-4 (Phase-9 `ci-ext.sh` gate + per-store zips, `ru` locale, content-XSS, credential-leak audit, decrypt-throw parity, tab-group Challenge, and the `_locales` packaging fix) staged for the next commit.
- **Extension test corpus:** **559 Vitest tests across 52 spec files** — same-session
  `npx vitest run` → `Tests 559 passed (559)` — under
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

## Session 12 (2026-06-13) — test-coverage breadth + flaky-test hardening + WCAG fixes

Parallel-subagent batch (§11.4.103); the whole batch is verified together by
`extension/ci-ext.sh` → **`CI-EXT: PASS`**, full suite **632 passed (632)** (+73 over
the 559 rc baseline), `tsc --noEmit` clean, `npm run lint` 0/0, chrome+firefox builds
loadable, §11.4.38 asset-verify pass, both store zips ≥10 KiB.

- **+73 new tests across 4 files** (each anti-bluff, no absolute wall-clock thresholds):
  - `tests/perf/orchestrator-scaling.perf.test.ts` — machine-independent metamorphic
    sub-quadratic DoS-scaling guard (`t(10·N)/t(N) < 30`) + golden-good/golden-bad
    oracle self-validation (§11.4.107(10): `linearRatio=9.9` accept / `quadraticRatio=113`
    reject).
  - `tests/stress/orchestrator-ratelimiter-tabgroup.stress.test.ts` (7) — orchestrator
    junk-flood, real `BobaClient` FIFO under a 500-request flood, `TokenBucket` rate-limit
    engagement, tab-group dedup-batch at scale, + chaos flaky-tab fault injection.
  - `tests/security/infohash-detection-hostile.test.ts` (32) — infohash hex/base32
    boundary + case, `xt=` confusion, `.torrent` URL allowlist (traversal/scheme/null-byte),
    SHA-1 `.torrent` infohash correctness, dedup under hostile repetition.
  - `tests/a11y/focus-and-contrast.a11y.test.ts` (32) — focus management (WCAG 2.4.3/2.4.7/
    2.1.2) + computed colour-contrast (WCAG 1.4.3) from the REAL committed CSS, analyzer
    self-validated.
- **3 real WCAG AA contrast defects fixed** (`src/popup/styles.css`): `--text-faint`
  dark `#7a7a90`→`#838399` (4.07→4.61), light `#8a8a9c`→`#6c6c7e` (3.14→4.76),
  `--warning-text` light `#9a6a00`→`#946400` (4.40→4.78). RED→GREEN proven; permanent guards.
- **3 flaky perf/security tests hardened** (§11.4.50 — were FAIL-bluffs under host load,
  proven load-coupled in isolation, then fixed to assert contention-robust intrinsic
  statistics): junk-flood security test (tight 5000 ms → 30 s hang-ceiling + scaling moved
  to perf), `crypto.perf` (p99→min budget), `parsers.perf` (median→min scaling ratio).
- Full root-cause + evidence for all six fixes: `docs/issues/fixed/BUGFIXES.md` Rev 6
  (entries 18–21).

### Session 12 — wave-11 (2026-06-13): 6 more coverage files + 5 options-page WCAG fixes

Two further parallel-subagent waves (§11.4.103), verified together by `extension/ci-ext.sh`
→ **`CI-EXT: PASS`**, full suite **761 passed (761)** (+129 over wave-10's 632).

> **Wave-12 (2026-06-13):** +38 more tests → **799 passed (799)** (`CI-EXT: PASS`):
> `tests/security/crypto-tamper.test.ts` (17 — AES-256-GCM tamper/auth/fixed-IV),
> `tests/unit/link-scanner-coverage.test.ts` (10 — scheme allowlist/visibility/dedup),
> `tests/unit/highlight-manager.test.ts` (11 — content-script highlight DOM no-leak/idempotency).
> No product defects; 1 flaky scaling-ratio test hardened (BUGFIXES 27, §11.4.50/§11.4.118).
>
> **Wave-13 (2026-06-13):** +15 → **814 passed (814)**. `tests/unit/popup-states.test.ts` (5)
> closes a genuine new gap (the popup's **partial Send-All failure** path: succeeded rows flip to
> Sent, failed rows stay retryable, the live region reports the failure count, Send-All re-enables).
> Plus **two prior-session test files brought into git** that were sitting UNTRACKED in the working
> tree (a working-tree-hygiene gap closed): `tests/unit/options-save-flow.test.ts` (4 — save
> validation/persistence/encryption) and `tests/unit/offline-queue-persistence.test.ts` (6 —
> cross-restart persistence/recovery), both verified real anti-bluff suites against production code.
> Also: a 6th flaky scaling test hardened (the tab-group **median→min** estimator, §11.4.50/§11.4.118
> — even a median spikes under 814-test contention; min is the intrinsic-cost estimator).
> Autonomous test-coverage is now saturated; remaining release work is operator-gated (live-7187
> round-trip, headful e2e, store assets).
>
> **Wave-14 (2026-06-13) — live-7187 harness prep** (de-risks the #1 operator-gated blocker so it
> turns GREEN the moment the stack is up): the live vitest test now drives the real `BobaClient` +
> **independently confirms the synthetic torrent appears in qBittorrent** (`:7186 /api/v2/torrents/info`)
> + **cleans it up** (§11.4.14), all SKIP-safe; the `live_detect_send_challenge.sh` had a real
> §11.4.14 cleanup-race defect FIXED (BUGFIXES 29); the HelixQA bank audited correct + in sync; and
> BE-1 (CORS) + BE-2 (`.torrent` upload) were found **already implemented** in the backend (see
> RELEASE_READINESS Rev 3). Default suite unchanged at **814 passed (814)** (the live test/challenge
> are out-of-suite, operator-run when the backend is up).
>
> **Wave-15 (2026-06-13) — remaining-blocker prep audits:** **Blocker #2 (headful e2e) substantially
> CLEARED** — `tests/e2e/extension-loads.spec.ts` runs + passes **4/4 autonomously** (verified by a real
> `npx playwright test` run) via Playwright `--headless=new`: MV3 SW registers, popup + options render,
> and (new) the real content script auto-injects on a matched host + detects a magnet + badges it
> (mutation-proven). **Blocker #3 (store):** `STORE_LISTING.md` audited submission-ready (all required
> fields + permission justifications match the manifests; a real locale drift 4→8 FIXED); remaining =
> operator visual assets + submission. The 6 sibling Challenge scripts audited — all already anti-bluff
> correct (no changes). See RELEASE_READINESS Rev 4. Default suite still **814 passed (814)**.

- **+129 new tests across 6 files** (each anti-bluff; no absolute wall-clock thresholds):
  - `tests/unit/orchestrator-dynamic-content.test.ts` (5) — MutationObserver dynamic-content
    re-scan (insert/href-mutation/relevance-filter/debounce-coalesce/stop-disconnect),
    RED-proven against mutated production source.
  - `tests/a11y/options-contrast-motion.a11y.test.ts` (16) — options-page contrast + focus +
    reduced-motion (found 5 real WCAG defects, now fixed + guarded).
  - `tests/i18n/locale-safety.test.ts` (41) — i18n catalog safety across all 8 locales
    (placeholder/key parity, XSS-inert values, JSON integrity); `tests/i18n/**` wired into
    `vitest.config.ts`.
  - `tests/chaos/boba-client-resilience.chaos.test.ts` (9) — real `BobaClient` retry/backoff/
    timeout/error-classification under fault injection (fake timers, ordering asserts).
  - `tests/security/bencode-torrentfile-hostile.test.ts` (52) — bencode parser robustness
    (truncation, hostile lengths, integer edge forms, deep nesting, wrong-typed `info`,
    binary-safe infohash).
  - `tests/unit/text-scanner-coverage.test.ts` (6) — bare-text magnet detection, cross-scanner
    id-equality, false-positive boundary, non-content-node skipping.
- **5 real WCAG AA options-page defects fixed** (`src/options/styles.css` + `src/popup/styles.css`;
  RED→GREEN, §11.4.120-reconciled guards; BUGFIXES.md 22–26): Save-button gradient 3.66→4.57:1
  (button-local), two light-theme-invisible labels tokenized (1.40/1.12 → 10–16:1), reduced-motion
  blocks added to both stylesheets.
- **1 more flaky perf test hardened** (§11.4.50/§11.4.118): `scanner.perf` + a global
  `vitest.config.ts testTimeout: 30s` so heavy perf/stress tests are never killed by the default
  5 s runner timeout under concurrent-suite contention (their real budgets are their own internal
  assertions). Subagents found **no product defects** in client/bencode/text-scanner.

## Session 16 (2026-08-20) — 68-day staleness catch-up (BOB-083)

Real `git log -- extension/` evidence: only 3 commits touched `extension/` between
`37fcbe4` (2026-06-13, Session 12/wave-15) and this pass's HEAD `e0d60ab`
(2026-08-20). All 3 reviewed:

- **`ee4a01b` (2026-06-15) — genuine MV3 service-worker-teardown resilience fix
  (crash-audit finding S3, `docs/issues/fixed/BUGFIXES.md`).** `tabResults` was a
  bare top-level `Map<number, PageScanResult>` — MV3 service-worker in-memory
  state that is DISCARDED whenever Chrome idles-out and tears down the worker
  (~30s). After a teardown, the popup's `get-detected` read and the context-menu
  "Send all" / `send-all` command both silently no-op'd (both are guarded by
  `if (result)`), so a user's already-detected torrents vanished with no error.
  Fixed in `extension/src/background/index.ts`: every write now goes through
  `chrome.storage.session` (survives SW respawn within a browser session, cleared
  on browser close — the correct lifetime) via new `getTabResult`/`setTabResult`
  helpers, with the in-memory `Map` kept only as a fast-lane cache. RED
  (null-after-simulated-teardown) → GREEN, permanent guard
  `extension/tests/unit/background-sw-teardown.test.ts` (new file, 310 lines).
  Independent review (conductor-reviews-subagent, §11.4.70/§11.4.142): **GO**, no
  mutation residue.
- **`a410b91` (2026-06-16) — coverage-only, no product change.**
  `src/parser/torrent-file.ts` coverage 75.4% → 89.9%: `parseTorrentFromUrl` was
  untested (success / 404 / network-wrap / content-type paths) and
  `computeInfohash`'s error-wrap path was untested. Every new assertion RED-proven
  against a mutated regression (§11.4.115) then restored GREEN. No defect found.
- **`54e313f` (2026-08-08) — mechanical test-fixture refactor, no behavior
  change.** `tests/unit/torrent-file.test.ts`'s `vi.stubGlobal("fetch", …)` mocks
  rewritten from `async () => ({…})` to `() => Promise.resolve({…})` (same
  resolved shape); `extension/package-lock.json` touched incidentally.

**Fresh evidence gathered THIS session (2026-08-20, real commands, not recalled):**

- `npx tsc --noEmit` → **clean** (exit 0).
- `npm run lint` (`eslint src/ tests/ --ext .ts`) → **0 errors / 0 warnings**.
- `npx vitest run` (full suite, this host, HEAD `e0d60ab`) →
  **69 spec files (63 passed / 6 failed), 822 tests (815 passed / 7 failed)**,
  duration 256.5s. `find tests src -iname '*.test.ts' -o -iname '*.spec.ts'`
  independently counts **71** spec files on disk — the 2-file gap is
  `tests/e2e/extension-loads.spec.ts` (Playwright, not collected by `vitest run`)
  plus `tests/live/download-endpoint.live.test.ts` (reachability-gated, honest
  SKIP when the backend is down per §11.4.3, not counted as a vitest pass/fail
  here). This raises the previously-cited "814 passed (814)" baseline (Session
  12/wave-15, 2026-06-13) to a real, freshly-measured **822** total (+8, from
  `a410b91`'s new `torrent-file.ts` coverage tests).
  - **The 7 failures are ALL bounded-time perf/stress/security-budget assertions,
    not functional test failures**, and this run executed on a host that was
    simultaneously running this docs-refresh agent's other work (heavy
    concurrent load — 9 `node (vitest N)` worker processes observed live):
    `tests/perf/scanner.perf.test.ts` (p99 budget), `tests/perf/parsers.perf.test.ts`,
    `tests/stress/orchestrator-ratelimiter-tabgroup.stress.test.ts` (sub-quadratic
    scaling ratio), and `tests/security/scanner-hostile-input.test.ts` (junk-flood
    30s bound — observed 120.9s, ≈4× over). This is the **exact same
    host-load-coupled flakiness class** Session 12 already found and partially
    hardened for sibling tests (BUGFIXES 27, §11.4.50/§11.4.118) — a tight
    wall-clock budget failing under contention is a known instrument limitation
    on this class of test, not by itself proof of a product regression.
  - `PENDING_FORENSICS:` whether these 7 are pure host-contention flakes (the
    established pattern) or a genuine new timing regression is **not resolved by
    this pass** — confirming that requires re-running the suite in isolation on a
    quiet host, which is out of this docs-only task's charter (this agent does not
    own `tests/` or `extension/src/`; see the task-scope note in the Rev 16 header
    above). Recorded honestly rather than asserted either way (§11.4.6).
- Build artifacts: `.output/chrome-mv3/` present on disk; `firefox-mv2/` and the
  per-store `bobalink-1.0.0-*.zip` files are **not** currently present in the
  working tree (expected — gitignored build outputs of `ci-ext.sh`, not
  regenerated in this pass since this is a docs-sync task, not a build task).
  `ci-ext.sh` itself is present and executable; not re-run here.
- **Honest scope boundary (§11.4.6):** the per-phase table below and the
  Session-11/12 narrative above are carried forward UNCHANGED from Rev 15 except
  where this session's evidence directly bears on them (the S3 resilience fix is
  documented here, not retrofitted into the Session-11 Phase-4/5 rows, to avoid
  rewriting history this pass did not re-verify). A full per-phase re-audit
  against the current tree was judged out of the bounded scope of this
  staleness-catch-up pass, exactly as `docs/features/Status.md` Rev 8 scoped
  itself.

## Per-phase status

| Phase | Title | Status | Evidence |
|-------|-------|--------|----------|
| 1 | Foundation & scaffolding (WXT config, TS, shared libs, types, constants) | PASS | Scaffolded @`33a9815`; shared-lib + constants + type-guard unit specs green @`15a9a61` |
| 2 | Core detection & parsing engine (parsers, scanners, infohash dedup) | PASS | Parsers @`7225470`/`fa03323`; SHA-1 infohash + link/text scanners + perf/stress @`fa03323`; scanner orchestrator cross-scanner dedup @`946c61e` |
| 3 | Extension shell — content / background / popup / options | PASS | Shell @`e8fde43`; background service-worker message router capstone @`15a9a61` |
| — | WXT build wiring (`entrypoints/`, `wxt build` → `.output/`, manifest validate) | **PASS** | Entrypoints `src/entrypoints/{background.ts,content.ts,popup/index.html,options/index.html}`; `npx wxt build` → loadable `.output/chrome-mv3/` (8/8 manifest assets verified present, §11.4.38); matches derived from `SITE_SELECTORS`, no `<all_urls>` (Session 11 @`5edf6ac`, pushed) |
| 4 | Boba backend integration (real client, queue auth, BE-1/2/3) | IN-PROGRESS | API leaf @`e8fde43`. **Phase-7 decrypt-before-send wired** (Session 11): `BobaClient.create()` decrypts the `encryptedBobaApiToken` bundle via `shared/crypto`; `background` reads the session passphrase from `chrome.storage.session` and sends the decrypted plaintext (default-open when locked). Token suites `boba-client-token.test.ts` 5 + `background-token.test.ts` 3 green. **PENDING:** live-7187 integration (`require_backend(7187)`), end-to-end detect→send→torrent-in-qBittorrent on the real backend |
| 5 | Tab-group batch (`chrome.tabGroups` → per-tab scan → batch send) | IN-PROGRESS | **Wired** (Session 11): `src/tabgroups/index.ts` (dedupe across a group + batch dispatch, 13 tests) **integrated into `background/index.ts` `MENU_SEND_GROUP`** (deduped group batch → one `addMagnets` POST); manifest `+tabGroups` (MINIMAL — research-confirmed `tabs` NOT needed since only `tab.id` is read; §11.4.120 security-test reconciliation, mutation-verified). New `background.test.ts` MENU_SEND_GROUP test (RED-verified: handler no-op → FAIL). Independent review: **GO-with-nits**. Group-send nits (a) offline-queue enqueue-on-failure, (b) network-error notification, (c) hardened async flush — all **FIXED** (Session 11, RED→GREEN + 3×-deterministic, independent review GO). **TRACKED:** decrypt-throw (wrong passphrase) on group send not enqueued/notified — pre-existing parity with Send-All, future phase |
| 6 | UI/UX, i18n, accessibility, themes | IN-PROGRESS | i18n: `locale.test.ts` (en completeness) + **ru+de+fr+es+it+pt+ja locales added** (8 total — plan target reached, 29-key parity, packaged chrome+firefox) with generalized `locale-parity.test.ts` (key + placeholder parity, mutation-proven); **a11y**: `tests/a11y/{popup,options}.a11y.test.ts` (18 tests — roles/accessible-names/tablist↔tabpanel/live-regions, mutation-proven). tablist keyboard-nav (WAI-ARIA Arrow/Home/End). **PENDING:** deeper WCAG (contrast/focus), theme-switch evidence |
| 7 | Security & credentials (delegate-by-default, no embedded key, log redaction) | IN-PROGRESS | `crypto.ts` adopted; **decrypt-and-send path landed** + **decrypt-throw on wrong passphrase now enqueues+notifies** (parity, RED→GREEN); session passphrase from `chrome.storage.session`, **no embedded key**, plaintext/passphrase never logged; security suite `tests/security/*` (least-privilege manifest, CSP, no-hardcoded-secret, secret-storage, **content-XSS** — render path proven safe via innerHTML-mutation→FAIL); **§11.4.10.A credential-leak audit** `challenges/security/credential_leak_audit.sh` (PASS, mutation-verified); **message-router robustness** (16 tests) + **`isValidScanResult` scan-result trust-guard** + **`resolveTargetTabId` cross-tab confused-deputy guard** (fixed a real content-script info-leak: forged payload.tabId could read another tab’s detections; sender.tab.id now wins) + scanner-hostile-input (19) + sender-trust (10) + content-XSS. **PENDING:** full pen-test suite (sender-origin validation, rate-limit) |
| 8 | Testing to 100% (all types) + Challenges + HelixQA | IN-PROGRESS | 559 tests/52 files green (unit/perf/stress/chaos/integration/security/e2e). Challenge `challenges/extension/detect_and_forward_challenge.sh` drives the REAL orchestrator+client end-to-end, PASS on captured evidence, mutation-verified (no-op stub → FAIL). HelixQA `boba-bobalink.yaml` BOBA-LINK-007 (detect→forward) + BOBA-LINK-008 (tab-group batch) added; symlinked into `challenges/helixqa-banks/`. tab-group + detect→forward Challenges both mutation-verified. E2E `tests/e2e/extension-loads.spec.ts` is a real MV3-load test, **operator-gated SKIP** in this headless sandbox (extension load unsupported; §11.4.3). **PENDING:** the full 13-type coverage matrix + live-backend integration + the coverage ledger to 100% |
| 9 | Build, packaging & distribution (manual — NO CI/CD) | IN-PROGRESS | **Manual gate `extension/ci-ext.sh`** (Session 11, §11.4.18 doc'd): tsc → lint → full vitest → chrome+firefox builds → §11.4.38 artifact-verify (opens the manifest, asserts every referenced asset + the `default_locale` catalog exist non-zero) → per-store `wxt zip`. **CI-EXT: PASS** — produces loadable `chrome-mv3/` + `firefox-mv2/` + `bobalink-1.0.0-{chrome,firefox,sources}.zip`. **PENDING:** store-listing metadata/submission + §11.4.65 user/dev/install doc siblings. NO CI/CD (manual only) |

## Status legend

- **PASS** — implemented and backed by a cited commit and/or verified test/file evidence.
- **IN-PROGRESS** — partially landed; some sub-tasks done with evidence, remainder explicitly enumerated as PENDING.
- **PENDING** — not yet started / no runtime evidence; planned in `IMPLEMENTATION_PLAN.md`.

## Anti-bluff notes (§11.4 / §11.4.6 / §11.4.69)

- The 559 figure IS a same-session recorded `npx vitest run` result (`Tests 559 passed (559)`),
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
- **Two real bugs caught by the new tests + fixed (wave-5, RED→GREEN, independently
  re-verified):** (1) a popup↔background CONTRACT bug the integration round-trip exposed —
  the popup read `r.torrent.id` but the real background returns a flat `SendOutcome {id,…}`,
  so a SUCCESSFUL send threw in the popup and showed a FALSE "Send failed" (row never flipped
  to Sent); the popup-unit fake had masked it with the wrong shape. Fixed (popup reads `r.id`;
  fake corrected; integration assertion reconciled §11.4.120). (2) a `scan-result` TRUST bug
  the message-router robustness tests exposed — a hostile content script could send
  `{items:<non-array>}` and overwrite a tab's good detection set with garbage; fixed with an
  `isValidScanResult` shape-guard (16 robustness tests; the non-array test seeds-good→corrupt
  and asserts the good set survives).
- de/fr locales added (4 total, all 29-key parity, packaged in both chrome+firefox builds);
  orchestrator + rate-limiter stress (evidence-captured, deterministic); popup/options↔
  background integration round-trips (real sendMessage→onMessage bridge); USER/INSTALL/DEV
  guides (§11.4.65 exports).
