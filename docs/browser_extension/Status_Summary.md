# BobaLink Browser Extension — Status Summary

**Revision:** 1
**Last modified:** 2026-06-10T11:55:33Z
**Companion of:** `docs/browser_extension/Status.md` (§11.4.56 two-audience summary).

---

## Page 1 — For the team (plain language)

BobaLink is a browser extension that spots torrent download links (magnet links and
`.torrent` files) on any web page and sends them, with one click, to the Boba
dashboard so the download starts automatically.

**What works today:**

- The detection engine is built and tested: it reads torrent links, computes the
  unique fingerprint of each torrent, and removes duplicates.
- The extension's visible parts are built: the page overlay that highlights links,
  the popup window with a "Send" button, the options screen, and the background
  worker that ties everything together and queues sends when offline.
- The piece that talks to the Boba dashboard (the client + the offline queue) is in
  place, and the dashboard side already accepts requests from the extension.

**What is still pending:**

- **Packaging the extension into an installable file is not finished** — the build
  tool is configured but the final "build and zip" step has not been wired up, so
  there is no installable extension yet.
- **Sending many tabs at once** (tab-group batch), **translations into more
  languages**, the **full accessibility/theme polish**, and the **hardened
  credential/security model** are all still to come.
- **End-to-end proof** — actually clicking "Send" and seeing the torrent appear in
  qBittorrent — has not yet been recorded against a live dashboard.

**Team / operator actions:** none required right now. The next milestone is wiring the
build so an installable extension exists, then capturing the live "click → download
appears" proof.

---

## Page 2 — For software engineers

**HEAD:** `15a9a61` · **Branch:** `main` · **Test corpus:** 287 Vitest cases / 22 spec files.

### Commit provenance

| Phase | Status | Commit(s) |
|-------|--------|-----------|
| 1 Foundation | PASS | `33a9815` (scaffold), libs/types/constants present @`15a9a61` |
| 2 Detection/parsing | PASS | `7225470`, `fa03323` (parsers + infohash + scanners + perf/stress), `946c61e` (orchestrator dedup) |
| 3 Shell | PASS | `e8fde43` (content/popup/options), `15a9a61` (background SW message router) |
| 4 Backend integration | IN-PROGRESS | `e8fde43` (api leaf: `boba-client.ts`/`queue.ts`); backend BE-1/BE-2 on Python :7187. Live-7187 integration/security/chaos/E2E PENDING |
| WXT build wiring | IN-PROGRESS | `wxt.config.ts` @`15a9a61`; no `entrypoints/`, no `.output/`, no entrypoint wrappers |
| 5 Tab-group batch | PENDING | not implemented |
| 6 UI/UX/i18n/a11y | PENDING | only `_locales/en` present |
| 7 Security & credentials | PENDING | crypto unit specs only; credential model not landed |
| 8 Testing-to-100% + Challenges + HelixQA | IN-PROGRESS | unit/perf/stress present; bank `submodules/helixqa/banks/boba-bobalink.yaml` (@`284d1c4`); matrix/Challenges/live-suite PENDING |
| 9 Build/packaging/distribution | PENDING | no `ci-ext.sh`, no per-store zips, no artifact |

### Per-file spec counts (`grep -cE '\b(it|test)\('`)

`bencode.test.ts` 40 · `torrent-file.test.ts` 28 · `magnet.test.ts` 22 ·
`constants.test.ts` 19 · `errors.test.ts` 16 · `utils.test.ts` 16 ·
`boba-client.test.ts` 15 · `options.test.ts` 15 · `scanner-base.test.ts` 15 ·
`site-db.test.ts` 14 · `api-queue.test.ts` 11 · `background.test.ts` 11 ·
`crypto.test.ts` 11 · `popup.test.ts` 9 · `storage.test.ts` 9 ·
`content.test.ts` 7 · `events.test.ts` 7 · `link-scanner.test.ts` 7 ·
`orchestrator.test.ts` 6 · `text-scanner.test.ts` 5 · `parsers.perf.test.ts` 3 ·
`parsers.stress.test.ts` (present).

### Key file paths

- Build config: `extension/wxt.config.ts`, `extension/vitest.config.ts`, `extension/package.json`.
- Source root: `extension/src/{parser,scanner,content,background,popup,options,api,shared,types}`.
- Tests: `extension/tests/{unit,perf,stress}`.
- Plan: `docs/browser_extension/IMPLEMENTATION_PLAN.md` (9 phases) + `_analysis/` + `_plan/`.

### Anti-bluff caveat (§11.4.6)

The 287 figure is a static spec-case count, not a same-session `vitest run` green capture.
PASS rows cite commit provenance. Upgrading them to same-session captured-evidence requires a
`vitest run --coverage` artifact under `docs/qa/bobalink-2026-06-10-session11/` (next step).
