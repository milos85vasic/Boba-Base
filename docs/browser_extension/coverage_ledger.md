# BobaLink Browser Extension — Feature Coverage Ledger

**Revision:** 3
**Last modified:** 2026-06-13T09:22:00Z
**Scope:** BobaLink (`extension/`) — feature × test-type coverage ledger with a
per-feature autonomous-verification class (§11.4.25 full-automation-coverage,
§11.4.52 autonomous-validation).
**Authority:** master plan `docs/browser_extension/IMPLEMENTATION_PLAN.md`
(Phase 8, T8.5); live status `docs/browser_extension/Status.md` (Rev 4).

> §11.4.6 (no-guessing) / §11.4.5 (captured evidence): every ✓ cell cites a REAL
> test file backing it. A cell with no real test file is **PENDING** — never
> silently marked covered. The e2e row is honestly `OPERATOR_ATTENDED_ONLY` in
> this headless sandbox: the MV3-load test is real but SKIPs (no extension
> service worker registers — §11.4.3 topology dispatch), so it is not autonomous
> here.

## Ground-truth baseline (this session)

- Full suite: **632 passed / 56 spec files** (`npx vitest run` via `extension/ci-ext.sh`
  → `CI-EXT: PASS`, Session 12 / 2026-06-13) under
  `extension/tests/{unit,perf,stress,chaos,integration,security,a11y,e2e}` + `src/**`.
  (+73 over the 559 rc baseline.)
- **Session-12 coverage breadth added** (closing prior PENDING ledger gaps; all
  anti-bluff, no absolute wall-clock thresholds):
  - **stress/chaos breadth** beyond parsers+queue — `tests/stress/orchestrator-ratelimiter-tabgroup.stress.test.ts`
    (orchestrator junk-flood, real client FIFO-flood, rate-limiter engagement,
    tab-group at scale, chaos fault-injection).
  - **security — detection/infohash paths** — `tests/security/infohash-detection-hostile.test.ts`
    (hex/base32 boundary+case, `xt=` confusion, `.torrent` URL allowlist, SHA-1
    infohash correctness, hostile-repetition dedup).
  - **accessibility — focus + contrast (deeper WCAG)** — `tests/a11y/focus-and-contrast.a11y.test.ts`
    (WCAG 2.4.3/2.4.7/2.1.2 focus management + 1.4.3 computed contrast from the real CSS).
  - **DoS scaling (machine-independent)** — `tests/perf/orchestrator-scaling.perf.test.ts`
    (metamorphic sub-quadratic ratio + oracle self-validation).
- E2E (`tests/e2e/extension-loads.spec.ts`) is a real Playwright MV3-load test
  that **SKIPs-with-reason** in this headless/sandbox environment (no display /
  unpacked-extension load unsupported); it executes the popup/options assertions
  only on a headful-capable host. Honest gap per §11.4.3, never a faked PASS.
- Challenge: `challenges/extension/detect_and_forward_challenge.sh` drives the
  real orchestrator + client end-to-end (detect → POST `:7187/api/v1/download`),
  PASS on captured evidence, mutation-verified (no-op stub → FAIL).
- HelixQA bank: `challenges/helixqa-banks/boba-bobalink.yaml` (symlinked from
  `submodules/helixqa/banks/boba-bobalink.yaml`) — `http:` cases require a LIVE
  merge-service on `:7187`; reports connection failure if down (no fail-open).

## Legend

- **✓ `path`** — covered by the cited real test file (assertion on a
  user-observable outcome; fails against a no-op stub).
- **SKIP** — a real test exists but is operator-gated / topology-gated in this
  sandbox (e2e MV3 load; live-`:7187` HelixQA).
- **PENDING** — no real test file yet (tracked in Gaps).
- **N/A** — test type does not apply to this client-side feature.

### Autonomous-verification class (§11.4.52)

- **AUTONOMOUS_VERIFIED** — at least one autonomous path runs headlessly here
  with captured evidence + PASS/FAIL with no human in the loop.
- **AUTONOMOUS_DESIGNED** — an autonomous path exists/designed but its primary
  end-to-end proof is gated on an external dependency not present in this
  sandbox (live `:7187`, headful extension load).
- **OPERATOR_ATTENDED_ONLY** — the only proof path needs a host with a real
  display / operator (release blocker until promoted; tracked in Gaps).
- **NOT_APPLICABLE** — feature class does not warrant the path.

## Coverage matrix

| Feature / flow | unit | integration | security | stress | chaos | e2e | challenge | Autonomous-verification class |
|----------------|------|-------------|----------|--------|-------|-----|-----------|-------------------------------|
| Magnet detection (BEP-9 parse, scan, highlight) | ✓ `tests/unit/magnet.test.ts`, `tests/unit/link-scanner.test.ts`, `tests/unit/text-scanner.test.ts`, `tests/unit/content.test.ts` | ✓ `tests/integration/pipeline.test.ts` (STAGE 1) | PENDING | ✓ `tests/stress/parsers.stress.test.ts` | ✓ `tests/stress/parsers.stress.test.ts` (input-corruption) | SKIP `tests/e2e/extension-loads.spec.ts` | ✓ `challenges/extension/detect_and_forward_challenge.sh` | AUTONOMOUS_VERIFIED |
| `.torrent` infohash (bencode → SHA-1) | ✓ `tests/unit/torrent-file.test.ts`, `tests/unit/bencode.test.ts` | ✓ `tests/integration/pipeline.test.ts` (STAGE 1 `.torrent` link) | PENDING | ✓ `tests/stress/parsers.stress.test.ts` | ✓ `tests/stress/parsers.stress.test.ts` (corrupt bencode) | N/A | PENDING (challenge covers magnet path only) | AUTONOMOUS_VERIFIED |
| Cross-scanner dedup (by lowercase infohash) | ✓ `tests/unit/orchestrator.test.ts`, `tests/unit/scanner-base.test.ts` | ✓ `tests/integration/pipeline.test.ts` (STAGE 1: magnet×2 → 1) | PENDING | PENDING | PENDING | N/A | ✓ `challenges/extension/detect_and_forward_challenge.sh` (exact deduped infohash) | AUTONOMOUS_VERIFIED |
| Send → Boba `:7187/api/v1/download` | ✓ `tests/unit/boba-client.test.ts`, `tests/unit/api-queue.test.ts` | ✓ `tests/integration/pipeline.test.ts` (STAGE 2/2b: captured request URL + body) | PENDING | PENDING | ✓ `tests/chaos/queue.chaos.test.ts` (send-failure injection) | SKIP `tests/e2e/extension-loads.spec.ts` | ✓ `challenges/extension/detect_and_forward_challenge.sh` | AUTONOMOUS_DESIGNED (live-`:7187` HelixQA `boba-bobalink.yaml` SKIPs when backend down) |
| Offline FIFO queue (persist, retry, dead-letter, SW-restart) | ✓ `tests/unit/api-queue.test.ts` | ✓ `tests/integration/pipeline.test.ts` (STAGE 3/3b/3c persist + round-trip + drain) | PENDING | ✓ `tests/stress/queue.stress.test.ts` (≥1000 enqueue, FIFO, concurrent) | ✓ `tests/chaos/queue.chaos.test.ts` (corruption, soft/hard fail, dead-letter) | N/A | PENDING | AUTONOMOUS_VERIFIED |
| Popup UI (detected list, Send, Send-All, status) | ✓ `tests/unit/popup.test.ts`, `tests/a11y/popup.a11y.test.ts` (9 ARIA) | — | PENDING | N/A | N/A | SKIP `tests/e2e/extension-loads.spec.ts` (renders popup.html) | N/A | AUTONOMOUS_VERIFIED (DOM via jsdom; visual render gated on e2e load) |
| Options UI (7 tabs, save/load config) | ✓ `tests/unit/options.test.ts`, `tests/a11y/options.a11y.test.ts` (9 ARIA) | — | ✓ `tests/security/secret-storage.test.ts` | N/A | N/A | SKIP `tests/e2e/extension-loads.spec.ts` (7 tabs) | N/A | AUTONOMOUS_VERIFIED |
| Background routing (SW message router, menus, badge, alarms) | ✓ `tests/unit/background.test.ts`, `tests/unit/background-token.test.ts` | — | PENDING | N/A | N/A | SKIP `tests/e2e/extension-loads.spec.ts` (SW registers) | N/A | AUTONOMOUS_VERIFIED |
| Token decrypt-before-send (no embedded key, session passphrase) | ✓ `tests/unit/crypto.test.ts`, `tests/unit/boba-client-token.test.ts`, `tests/unit/background-token.test.ts` | ✓ `tests/integration/pipeline.test.ts` (STAGE 2c forward) | ✓ `tests/security/secret-storage.test.ts`, `tests/security/no-hardcoded-secret.test.ts` | PENDING | PENDING | N/A | N/A | AUTONOMOUS_VERIFIED |
| Tab-group batch (dedup across group → one POST) | ✓ `tests/unit/tabgroups.test.ts`, `tests/unit/background.test.ts` (`MENU_SEND_GROUP`) | — | ✓ `tests/security/manifest-least-privilege.test.ts` (`tabGroups` minimal, no `tabs`) | PENDING | PENDING | N/A | PENDING (tab-group end-to-end Challenge) | AUTONOMOUS_VERIFIED (unit/integration headless; live multi-tab e2e PENDING) |
| i18n (locale-key completeness) | ✓ `tests/unit/locale.test.ts` | — | N/A | N/A | N/A | N/A | N/A | AUTONOMOUS_VERIFIED (en catalog; additional locales PENDING) |
| Manifest least-privilege / CSP (cross-cutting) | — | — | ✓ `tests/security/manifest-least-privilege.test.ts`, `tests/security/csp.test.ts` | N/A | N/A | N/A | PENDING (cred-leak grep Challenge) | AUTONOMOUS_VERIFIED |

## Gaps (highest-priority missing coverage — tracked follow-ups)

1. **Live `:7187` integration / end-to-end Challenge (Phase 4).** The send-flow
   integration substitutes the network boundary (`fetchImpl` stub) and the
   HelixQA bank (`challenges/helixqa-banks/boba-bobalink.yaml`) SKIPs when the
   merge-service is down. PENDING: a `require_backend(7187)` integration that
   actually POSTs to a running backend and asserts the torrent appears in
   qBittorrent (detect → send → server-side add), plus BE-1 (CORS) / BE-2
   (`.torrent` multipart upload) backend work. Promotes "Send → :7187" from
   AUTONOMOUS_DESIGNED → AUTONOMOUS_VERIFIED.

2. **E2E real-extension load (Phase 8).** `tests/e2e/extension-loads.spec.ts` is
   real but `OPERATOR_ATTENDED_ONLY` in this sandbox (no MV3 unpacked-extension
   load; no display). PENDING: run on a headful-capable host so the
   popup/options/SW assertions actually execute, and add a real multi-tab
   tab-group e2e (Phase 5) and an offline-queue-durability e2e (SW termination).

3. **`.torrent` infohash end-to-end Challenge.** The detect→forward Challenge
   covers the magnet path; the `.torrent`-file forward path has no challenge-
   level captured-evidence run yet. PENDING.

4. **Additional locales + deeper-WCAG + theme evidence (Phase 6).** `locale.test.ts`
   guards only the `en` catalog; the plan targets 8 locales. Structural ARIA a11y
   IS now covered (`tests/a11y/popup.a11y.test.ts` + `options.a11y.test.ts` — 18
   tests: roles / accessible-names / tablist↔tabpanel / live-regions, mutation-proven).
   PENDING: 7 more locale catalogs + a locale-switch render test, the deeper WCAG 2.1
   AA checks a static HTML parse cannot cover (contrast ratios, focus order, keyboard
   traversal), and dark/light theme-switch evidence.

5. **Security depth (Phase 7).** Present: least-privilege manifest, CSP,
   no-hardcoded-secret, secret-storage. PENDING: §11.4.10.A pre-store
   credential-leak audit + pre-commit grep gate, a cred-leak-grep Challenge, and
   a fuller pen-test suite (magnet/`dn` XSS sanitization, `sender.id`/`sender.url`
   validation, log-redaction proof).

6. **Stress/chaos breadth beyond parsers + queue.** §11.4.85 stress+chaos exist
   for parsers and the offline queue. PENDING: stress/chaos for the scanner
   orchestrator (10k-link page, frame-budget), the BobaClient rate-limiter under
   API flood, and tab-group batching under many tabs.

7. **Per-store packaging + manual gate (Phase 9).** No `extension/ci-ext.sh`
   manual gate, per-store zips, bundle-size assertion, or §11.4.65 doc siblings
   yet. PENDING (NO CI/CD — manual only).
