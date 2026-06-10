# QA Evidence — BobaLink Session 11 (2026-06-10)

**Revision:** 1
**Last modified:** 2026-06-10T11:55:33Z
**Run ID:** `bobalink-2026-06-10-session11`
**Scope:** BobaLink browser extension (`extension/`) — §11.4.83 per-feature QA evidence directory for the 6-stream parallel session in flight at HEAD `15a9a61`.

> This directory holds the captured runtime evidence produced by the current
> parallel session's test/build streams. Per §11.4.83, a feature is not "done"
> until its auditable runtime evidence lands here. Per §11.4.6, this README only
> describes the evidence that the session's streams will deposit — it does NOT
> claim any artifact exists until the producing stream writes it.

## Evidence this session is expected to produce

The 6-stream parallel session is mutating `extension/` concurrently with this
status-doc stream. As each stream completes, it deposits its captured artifacts here:

| Artifact | Producing stream | What it proves |
|----------|------------------|----------------|
| `vitest_run.log` + `coverage/` | unit/spec stream | Same-session `vitest run --coverage` green capture (upgrades the Status.md PASS rows from commit-provenance to same-session evidence) |
| `integration_7187.log` | integration stream | Live-backend integration against the Boba merge service on :7187 (`require_backend(7187)` → SKIP-with-reason if down, never fail-open per §11.4.3/§11.4.68) |
| `security_review.md` | security stream | No qBittorrent/tracker credentials sent from the extension; no embedded decrypt key; passkey log redaction; manifest least-privilege + MV3 CSP audit |
| `stress/` (`latency.json`, `categorised_errors.txt`) | stress stream | §11.4.85 sustained-load (≥100 iters / ≥30s) + concurrent contention (≥10 parallel) on the parsers/scanners with p50/p95/p99 |
| `chaos/` (`recovery_trace.log`) | chaos stream | §11.4.85 backend-drop-mid-send → offline-queue recovery; storage-quota + SW-termination fault injection |
| `token_send_wire.txt` | E2E / token-send stream | Wire capture of a real detect→send request to :7187 (`POST /api/v1/download`), including the env-gated `X-Boba-Token`/`Bearer` header behaviour, and the resulting torrent row appearing in qBittorrent |
| `wxt_build/` (`build.log`, `manifest.json`, `bundle_listing.txt`) | WXT build stream | `wxt build` → `.output/` artifact listing + generated MV3 manifest + bundle-size check (≤350 KB per Plan §T9.1); proves the §11.4.38 installable-asset chain |

## Provenance anchors (verified at session start)

- HEAD: `15a9a61` (Phase 3 capstone — background service worker message router).
- Recent history: `e8fde43` (Phase 3 shell + Phase 4 api leaf), `2e59572` (lint),
  `946c61e` (Phase 2 orchestrator dedup), `fa03323` (Phase 2 wave-2),
  `7225470` (Phase 2 wave-1), `192b945` (env-gated `BOBA_API_TOKEN` security fix).
- Test corpus at session start: 287 Vitest cases / 22 spec files
  (`extension/tests/{unit,perf,stress}`).

## Anti-bluff (§11.4.6 / §11.4.69)

Each artifact above is described as EXPECTED, not present. No PASS may be claimed for
any feature until its row's artifact is actually written here by the producing stream
and cites a user-observable outcome (a torrent row in qBittorrent, a green coverage
report, a positive wire capture). Absent artifacts remain PENDING in
`docs/browser_extension/Status.md`.
