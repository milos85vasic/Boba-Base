# BobaLink Browser Extension — Release Readiness Report

**Revision:** 1
**Last modified:** 2026-06-10T23:30:00Z
**Scope:** BobaLink (`extension/`) — WXT + TypeScript Manifest-V3 cross-browser
extension that detects magnet links and `.torrent` URLs and forwards them to the
Boba merge service on port 7187. This report assesses release readiness at
**Session 11 / HEAD `5e44c85`**.
**Authority:** master plan `docs/browser_extension/IMPLEMENTATION_PLAN.md`
(9 phases); live state `docs/browser_extension/Status.md` (Rev 6);
`docs/browser_extension/coverage_ledger.md` (Rev 2); `extension/ci-ext.sh`.

> **Anti-bluff (§11.4.6 / §11.4.123).** Every claim below cites a real commit
> hash, a real test/file artifact, or `ci-ext.sh`. The verdict honestly
> distinguishes **code-complete + comprehensively tested** (what BobaLink is)
> from **released** (what it is NOT — live-backend round-trip + store assets are
> pending). Claims that could not be verified are flagged in §8.

---

## 1. Build state (HEAD `5e44c85`)

All figures are same-session recorded results cited in `Status.md` Rev 6 and the
`ci-ext.sh` manual gate — not static greps.

| Gate | Result | Source |
|------|--------|--------|
| Vitest suite | **527 passed / 49 spec files** (`npx vitest run` → `Tests 527 passed (527)`) | Status.md Rev 6 §"Baseline facts"; coverage_ledger §"Ground-truth baseline" |
| TypeScript | `npx tsc --noEmit` — **0 errors** | Status.md Rev 6; `ci-ext.sh` STEP 1 |
| Lint | `npm run lint` — **0 errors / 0 warnings** | Status.md Rev 6; `ci-ext.sh` STEP 2 |
| Manual gate | `extension/ci-ext.sh` → **`CI-EXT: PASS`** | Status.md Rev 6 Phase 9; `ci-ext.sh` final line |
| Chrome build | loadable `.output/chrome-mv3/` (`manifest_version:3`, SW, popup, options, content-script, icons 16/32/48/128, `_locales` (8: en/ru/de/fr/es/it/pt/ja)) | Status.md Rev 6; `ci-ext.sh` STEP 4–5 |
| Firefox build | loadable `.output/firefox-mv2/` | Status.md Rev 6; `ci-ext.sh` STEP 4 (`wxt build -b firefox`) |
| Per-store zips | `bobalink-1.0.0-{chrome,firefox,sources}.zip` (≥10 KiB asserted) | Status.md Rev 6; `ci-ext.sh` STEP 6 |
| Locales | **8 committed/built (en/ru/de/fr/es/it/pt/ja)** — 29-key + placeholder parity, mutation-proven (`locale-parity.test.ts` checks all 7 vs en) | Status.md Rev 6 Phase 6; built `.output/chrome-mv3/_locales/` = de/en/es/fr/it/ja/pt/ru (8) |

**Locale count — clarified (§8).** The plan targets **8** locales; the committed
and **built** state is **4** (en/ru/de/fr) — confirmed by inspecting the built
`.output/chrome-mv3/_locales/` directory (de/en/fr/ru) and the committed
`extension/src/public/_locales/`. The Chrome manifest packages only
`_locales` (8: en/ru/de/fr/es/it/pt/ja) per the §11.4.38 `ci-ext.sh` asset check; de/fr are present in
source and the parity test. **Stray `es/` and `it/` locale directories exist
UNTRACKED in the working tree** (not part of HEAD `5e44c85`) — they are NOT in
the release and should be either completed+committed or removed (see §8).

The §11.4.38 loadable claim is verified by `ci-ext.sh` STEP 5 **opening the
produced `manifest.json`** and asserting every referenced asset — including the
`default_locale → _locales/<locale>/messages.json` invariant — exists non-zero on
disk, not by "build exited 0."

---

## 2. The 6 reviewed Session-11 commits

All six are pushed and on `main` (fast-forward; **no force-push** per §11.4.113),
each independently code-reviewed per §11.4.125/§11.4.134/§11.4.142 (Status.md Rev 6
"Independent multi-lens subagent code-review … GO / GO-with-nits"). Verified via
`git log --oneline`:

| # | Commit | What landed (one line) |
|---|--------|------------------------|
| 1 | `024210f` | WXT build wiring (`entrypoints/` → `wxt build` → loadable `.output/`) + Phase 5/7 + test-type expansion |
| 2 | `5edf6ac` | Phase 5 wire-in — `MENU_SEND_GROUP` batched tab-group send (deduped group → one `addMagnets` POST) |
| 3 | `2011810` | wave-3 — Phase 5 nits + a11y + live-probe + Phase-8 coverage ledger + doc sync |
| 4 | `5fa78d9` | wave-4 — loadable-artifact `_locales` packaging fix + Phase-9 `ci-ext.sh` gate + Phase 6/7 depth |
| 5 | `e80c9d9` | wave-5 — 2 real bug fixes (popup false-failure + scan-result trust) + coverage/docs/locales |
| 6 | `5e44c85` | wave-6 — ReDoS + a11y-keyboard fixes + benchmarks + STORE_LISTING + HelixQA challenges (**HEAD**) |

---

## 3. Five real defects found and fixed by the test waves

Each defect was caught by a NEW test (not the original suite), RED-proven on the
pre-fix code (§11.4.115), fixed, and re-verified GREEN with zero regression
(496/47 stable). Independently re-verified per §11.4.134.

1. **`_locales` packaging — would have FAILED Chrome load.** The manifest
   declared `default_locale:"en"` + `__MSG_*__`, but the build packaged **no
   `_locales/`** (WXT copies from `src/public/`, the catalog lived at
   `src/_locales/`) — Chrome would have REJECTED the unpacked extension at load.
   Caught by the new `ci-ext.sh` §11.4.38 step that opens the artifact and checks
   the `default_locale → _locales/` invariant. Fixed by moving the catalog to
   `src/public/_locales/`; the permanent guard is `ci-ext.sh`. *(Fix: wave-4
   `5fa78d9`; this is the §11.4.108 "build-exit-0 ≠ deployable-artifact" lesson —
   §11.4.138 bluff-audit documented in Status.md Rev 6.)*

2. **Popup false-failure — popup↔background CONTRACT bug.** The popup read
   `r.torrent.id` but the real background returns a **flat** `SendOutcome {id,…}`,
   so a SUCCESSFUL send threw in the popup and showed a FALSE "Send failed" (row
   never flipped to Sent). The popup-unit fake had masked it with the wrong shape;
   exposed by the integration round-trip. Fixed (popup reads `r.id`; fake
   corrected; integration assertion reconciled §11.4.120). *(Fix: wave-5
   `e80c9d9`.)*

3. **Scan-result trust-overwrite — content-script trust bug.** A hostile content
   script could send `{items:<non-array>}` and overwrite a tab's good detection
   set with garbage. Fixed with an `isValidScanResult` shape-guard
   (`tests/security/message-router-robustness.test.ts`, 16 tests; the non-array
   test seeds-good→corrupt and asserts the good set survives). *(Fix: wave-5
   `e80c9d9`.)*

4. **ReDoS in `sanitizeDisplayName` — O(n²) → linear.** A hostile magnet `dn` of
   `'<'×100k` took 4s+ and could hang the content script. Fixed `/<[^>]*>/g` →
   `/<[^<>]*>/g` (a real HTML tag never contains `<`): linear time (400k:
   16s→24ms), output identical on valid input and strictly safer on hostile (now
   catches `<scr<script>ipt>` evasion). 19 hostile-input tests
   (`tests/security/scanner-hostile-input.test.ts`). *(Fix: wave-6 `5e44c85`,
   `src/parser/magnet.ts`.)*

5. **A11y keyboard gap — WAI-ARIA tablist arrow-key pattern (WCAG 2.1.1).** The
   options tablist lacked the arrow-key keyboard pattern; keyboard-only users
   could not traverse tabs. Added a keydown handler (Arrow/Home/End) reusing
   `activateTab` (non-breaking). 18 keyboard-nav tests
   (`tests/a11y/keyboard-nav.a11y.test.ts`). *(Fix: wave-6 `5e44c85`,
   `src/options/options.ts`.)*

---

## 4. Test-type coverage (from `coverage_ledger.md` Rev 2)

| Test type | Present? | Evidence |
|-----------|----------|----------|
| **unit** | ✓ | magnet/link/text scanners, bencode, torrent-file, orchestrator, boba-client, api-queue, popup, options, background, crypto, locale (across `tests/unit/` + `src/**`) |
| **integration** | ✓ | `tests/integration/pipeline.test.ts` (STAGE 1–3: detect → POST `:7187` request URL+body → queue persist+drain; real `sendMessage→onMessage` bridge) |
| **security** | ✓ | `tests/security/*` — manifest least-privilege, CSP, no-hardcoded-secret, secret-storage, content-XSS, message-router-robustness (16), scanner-hostile-input (19); + `challenges/security/credential_leak_audit.sh` (§11.4.10.A, mutation-verified) |
| **stress** | ✓ | `tests/stress/parsers.stress.test.ts`, `tests/stress/queue.stress.test.ts` (≥1000 enqueue, FIFO, concurrent) |
| **chaos** | ✓ | `tests/chaos/queue.chaos.test.ts` (corruption, soft/hard fail, dead-letter, send-failure injection) |
| **performance / benchmark** | ✓ | parser/scanner/crypto benchmarks `tests/perf/*` (distributions captured, 10×-regression-catching, 3×-deterministic) |
| **e2e** | **SKIP (operator-gated)** | `tests/e2e/extension-loads.spec.ts` is a real Playwright MV3-load test; SKIPs-with-reason in this headless sandbox (§11.4.3) — no display / unpacked-extension load |
| **accessibility (a11y)** | ✓ | `tests/a11y/{popup,options}.a11y.test.ts` (18 — roles/accessible-names/tablist↔tabpanel/live-regions) + `tests/a11y/keyboard-nav.a11y.test.ts` (18), mutation-proven |
| **Challenge** | ✓ (partial) | `challenges/extension/detect_and_forward_challenge.sh` drives the REAL orchestrator+client end-to-end, PASS on captured evidence, mutation-verified (no-op stub → FAIL); + `decrypt_and_send_challenge.sh`, `offline_queue_recovery_challenge.sh` |
| **HelixQA** | ✓ (bank present; live-gated) | `boba-bobalink.yaml` BOBA-LINK-007/008/009/010; `http:` cases require live `:7187` (report connection failure if down — no fail-open) |

**Not yet covered (tracked Gaps in ledger):** security for the detection/infohash
paths (PENDING cells), `.torrent` infohash end-to-end Challenge, deeper WCAG
(contrast/focus), 4 more locales toward the plan's 8, stress/chaos breadth beyond
parsers+queue (scanner orchestrator, rate-limiter flood, tab-group at scale).

---

## 5. Readiness verdict per phase (1–9)

| Phase | Title | Verdict | Basis (cited) |
|-------|-------|---------|---------------|
| 1 | Foundation & scaffolding | **PASS** | Status.md: scaffolded `33a9815`; shared-lib/constants/type-guard specs green `15a9a61` |
| 2 | Core detection & parsing engine | **PASS** | Status.md: parsers `7225470`/`fa03323`; SHA-1 infohash + scanners + perf/stress `fa03303`; orchestrator dedup `946c61e` |
| 3 | Extension shell (content/bg/popup/options) | **PASS** | Status.md: shell `e8fde43`; background SW message-router capstone `15a9a61`; WXT build wiring → loadable `.output/` (`5edf6ac`) |
| 4 | Boba backend integration | **IN-PROGRESS** | Status.md: API leaf `e8fde43` + Phase-7 decrypt-before-send wired; **PENDING** live-7187 integration + detect→send→torrent-in-qBittorrent (see §6 BLOCKER) |
| 5 | Tab-group batch | **IN-PROGRESS** | Status.md: wired into `MENU_SEND_GROUP` (13 tests, RED-verified, `+tabGroups` minimal-privilege); review GO-with-nits → nits FIXED; **PENDING** tab-group end-to-end Challenge + multi-tab e2e |
| 6 | UI/UX, i18n, accessibility, themes | **IN-PROGRESS** | Status.md: 4 locales (parity-proven) + a11y structural + keyboard-nav; **PENDING** 4 more locales (target 8), deeper WCAG, theme-switch evidence |
| 7 | Security & credentials | **IN-PROGRESS** | Status.md: decrypt-and-send + decrypt-throw parity, no embedded key, security suite + §11.4.10.A audit; **PENDING** fuller pen-test (sender-origin validation, rate-limit) |
| 8 | Testing to 100% + Challenges + HelixQA | **IN-PROGRESS** | coverage_ledger: 496/47 across 7 test-type dirs + a11y + Challenges + HelixQA bank; **PENDING** full 13-type matrix + live-backend + ledger→100% |
| 9 | Build, packaging & distribution (manual) | **IN-PROGRESS** | Status.md/`ci-ext.sh`: `CI-EXT: PASS`, per-store zips, STORE_LISTING.md; **PENDING** store-listing submission + remaining §11.4.65 doc siblings. NO CI/CD |

**Summary:** Phases 1–3 **PASS**; Phases 4–9 **IN-PROGRESS** (each with landed,
evidence-backed sub-tasks plus explicitly enumerated PENDING items). No phase is
fully PENDING.

---

## 6. Release blockers / operator-required items (§11.4.6 — no overclaim)

These MUST be resolved before store submission. They are honestly stated as
**blocked / operator-required**, not silently assumed clean.

1. **Live-7187 round-trip — INFRA-BLOCKED (honest SKIP, must be GREEN before
   submission).** The send-flow integration substitutes the network boundary
   (`fetchImpl` stub) and the HelixQA `boba-bobalink.yaml` `http:` cases SKIP when
   the merge-service is down (no fail-open — §11.4.68). The full **detect → send →
   torrent appears in qBittorrent** path against a running `:7187` backend has **no
   captured-evidence run** (ledger Gap 1; Status.md Phase 4 PENDING). This promotes
   "Send → :7187" from `AUTONOMOUS_DESIGNED` → `AUTONOMOUS_VERIFIED` and is a hard
   release gate. Also pending: BE-1 (CORS for extension origins) and BE-2
   (`.torrent` multipart upload) backend work.

2. **E2E MV3-load — OPERATOR_ATTENDED.** `tests/e2e/extension-loads.spec.ts` is a
   real Playwright MV3-load test that **SKIPs-with-reason** in this headless
   sandbox (no display / unpacked-extension load unsupported — §11.4.3). It must be
   run on a **headful-capable host** so the popup/options/SW assertions actually
   execute (ledger Gap 2). Operator-required: a real-display test host.

3. **Store assets — operator TODOs.** Store screenshots, promotional images, and
   the listing submission itself are operator deliverables. `STORE_LISTING.md`
   (Chrome/Firefox copy + permission justifications) exists (`5e44c85`), but the
   actual store-listing media + submission are not producible autonomously.

4. **Working-tree hygiene (operator decision).** Untracked `es/` and `it/` locale
   directories exist in `extension/src/public/_locales/` but are NOT in HEAD
   `5e44c85`. Either complete+commit them (toward the 8-locale target) or remove
   them before release so the tree matches the committed/built 4-locale state.

**Bottom line:** BobaLink is **loadable, packaged, and comprehensively
unit/integration/security/stress/chaos/perf/a11y-tested** — but a **store release
should wait** on (a) the live-backend detect→send→torrent-in-qBittorrent round-trip
turning GREEN and (b) the operator store assets. The extension is **code-complete +
comprehensively tested, NOT yet released.**

---

## 7. Honest classification

- **What BobaLink IS (verified):** code-complete through Phase 3; comprehensively
  multi-type tested (496/47 green, tsc 0, lint 0); loadable chrome-mv3 + firefox-mv2;
  per-store zips; `ci-ext.sh = CI-EXT PASS`; 5 real defects found-and-fixed by the
  test waves (RED-proven, zero-regression); all 6 Session-11 commits independently
  code-reviewed and pushed fast-forward (no force-push).
- **What BobaLink is NOT (yet):** **released.** The live-backend round-trip is
  INFRA-BLOCKED (honest SKIP), the real MV3-load e2e is OPERATOR_ATTENDED, and store
  media/submission are operator TODOs.

---

## 8. Status.md / ledger claims that could NOT be fully verified at write time

Per §11.4.6, items flagged rather than asserted:

1. **Locale count discrepancy (clarified, not a defect).** Status.md Rev 6 says
   "4 total (en/ru/de/fr)" — this matches the **committed + built** state (built
   `.output/chrome-mv3/_locales/` = de/en/fr/ru). A raw `ls` of
   `src/public/_locales/` shows 5–6 dirs because **`es/` and `it/` are UNTRACKED**
   working-tree artifacts (not in HEAD). The committed/built reality is **4**; the
   Chrome manifest packages `_locales` (8: en/ru/de/fr/es/it/pt/ja). **Flagged** so the 8-locale plan
   target and the stray dirs are reconciled (see §6.4).

2. **Spec-file count: 47 vs 48.** Status.md and the ledger cite **47** spec files
   (the same-session `npx vitest run` figure); a static `find … -name '*.test.ts'`
   returns **48** on disk. The 47 is the recorded vitest-run count and is the
   load-bearing figure; the 1-file delta is not material (a file may be
   un-collected/empty) but is noted for accuracy.

3. **The "496 passed / tsc 0 / lint 0 / CI-EXT PASS" run was NOT re-executed in
   this docs-only ZERO-RISK session.** These figures are cited from Status.md Rev 6
   and `5e44c85`'s commit message as **same-session recorded** results from the
   implementing session — this report does not re-run them (strict docs-only
   scope). They are reported as cited evidence, not as freshly re-captured here.

---

## Sources verified 2026-06-10

- `docs/browser_extension/Status.md` (Rev 6) — per-phase status, baseline facts, §11.4.138 bluff-audit
- `docs/browser_extension/coverage_ledger.md` (Rev 2) — feature × test-type matrix, Gaps
- `docs/browser_extension/IMPLEMENTATION_PLAN.md` (Rev 1) — 9-phase plan, BE-1/2/3, 8-locale target
- `extension/ci-ext.sh` — manual gate (tsc → lint → vitest → builds → §11.4.38 asset verify → zips)
- `git log --oneline` — the 6 Session-11 commits (`024210f 5edf6ac 2011810 5fa78d9 e80c9d9 5e44c85`)
- built `extension/.output/chrome-mv3/_locales/` (de/en/fr/ru) + committed `extension/src/public/_locales/`
