# Boba Proxy / Merge Service — v1.0.0 Release Readiness Ledger

**Revision:** 1
**Last modified:** 2026-11-21T00:00:00Z
**Scope:** The default Python product: `download-proxy/` merge service (`:7187`),
download proxy (`:7186`), WebUI bridge host process (`:7188`), and the Angular
dashboard served from the merge service.
**Authority:** `docs/RELEASE_READINESS_20260616.md` (point-in-time RW-18..21
assessment), `docs/browser_extension/RELEASE_READINESS.md` (template),
`docs/USER_MANUAL.md`, `docs/PLUGINS.md`, `docs/SECURITY.md`.

> **Anti-bluff (§11.4.6 / §11.4.123).** Every claim below cites a real test
> run, a real commit hash, or a file artifact. The verdict honestly
> distinguishes **code-complete + comprehensively tested** from **released**.

---

## 1. Headline verdict

**NOT YET tag-ready for a clean v1.0.0**, but the Python product is feature-complete,
test-green, and deployable in a trusted-LAN configuration. The remaining blockers are
operator-gated or documented honest capability boundaries:

1. **Tracker search endpoints behind Cloudflare challenges** (BOB-172 RuTracker,
   BOB-235 Kinozal) — no autonomous code path can solve these; operator must choose
   FlareSolverr, clearance cookie, Jackett bypass, or mark search unsupported.
2. **RuTracker interactive CAPTCHA login** (BOB-008) — operator must drive the one-time
   interactive flow.
3. **VPN-host egress verification** (BOB-065) — operator must provision an SSH-reachable
   VPN host and a known-blocked tracker to capture the acceptance run.
4. **External watchdog deployment** (BOB-121) — artifacts exist; operator must run one
   install script.
5. **Go `--profile go` parity** (BOB-101) — operator-deferred past v1.0.0; does not
   block the Python path.

These are recorded as operator decisions in `docs/Issues.md` and are not silently
ignored.

---

## 2. Test-suite state (verified live 2026-11-20)

| Suite | Verified | Evidence |
|---|---|---|
| Python unit | **4209+ passed, 0 failed** | `scripts/pre_build_verification.sh` gate family; `./ci.sh` hermetic unit suite |
| Go unit + race | **13 packages OK with `-race`** | `cd qBitTorrent-go && GOMAXPROCS=2 nice -n 19 go test -race -count=1 ./...` |
| Frontend Vitest | **371+ passed** | `cd frontend && npx vitest run` |
| Bash unit / pre_build | **all discovered suites run** | `scripts/pre_build_verification.sh` invariant 30 |
| Stress / chaos | **6/6 PASS** | `qBitTorrent-go/tests/integration/scheduler_hooks_sse_stress_chaos_test.go` |
| Scaling | **4/4 PASS** | `tests/scaling/test_scaling_envelope.py` |
| Accessibility contrast | **0 violations / 0 unmeasured glyphs** | `docs/qa/BOB-164/axe_contrast_scan.py` |

---

## 3. Product surfaces

| Surface | State | Notes |
|---|---|---|
| Merge search (`:7187`) | Complete | 40+ trackers, deduplication, enrichment, validation, SSE streaming |
| Download proxy (`:7186`) | Complete | qBittorrent WebUI proxy, authenticated private-tracker downloads |
| WebUI bridge (`:7188`) | Complete | Private-tracker auth bridging (RuTracker, Kinozal, NNM-Club, IPTorrents) |
| Angular dashboard | Complete | Standalone SPA, theme system, settings, search/hooks UI |
| Jackett auto-config | Complete | `boba-jackett` (:7189) owns credentials + indexer overrides |
| Container orchestration | Complete | `start.sh` / `stop.sh` auto-detect podman/docker, network_mode host |

---

## 4. Honest capability boundaries

- RuTracker **search** returns HTTP 403 with Cloudflare challenge markers from the
current host path (BOB-172). Login is CAPTCHA-gated (BOB-008).
- Kinozal **search** is unreachable from this host: `kinozal.tv` resolves to
`127.0.0.1`; `kinozal.guru` serves a Cloudflare challenge (BOB-235).
- IPTorrents downloads are **freeleech-only** by policy; non-freeleech results are
refused by the deduplicator.
- VPN-egress routing is implemented and unit-tested, but end-to-end verification
requires an operator-provisioned VPN host (BOB-065).

---

## 5. Concrete blockers to v1.0.0

| # | Blocker | Item | Resolution path |
|---|---|---|---|
| 1 | RuTracker search 403 | BOB-172 | Operator picks one of four unblock options in Issues.md |
| 2 | RuTracker CAPTCHA login | BOB-008 | Operator drives interactive `/api/v1/auth/rutracker/captcha` flow |
| 3 | Kinozal reachability | BOB-235 | Operator picks mirror / challenge solver / unsupported |
| 4 | VPN egress acceptance | BOB-065 | Operator provides `BOBA_VPN_HOST` and known-blocked tracker |
| 5 | Watchdog deployment | BOB-121 | Operator runs `scripts/flight-recorder/install.sh` or system-slice variant |
| 6 | Go parity | BOB-101 | Operator-deferred past v1.0.0; not a Python-path blocker |

---

## 6. Verdict

The proxy / merge-service product is **functionally complete, test-green, and
release-candidate quality** on the Python path. A clean `v1.0.0` tag waits on the
six operator-gated items above and a final §11.4.40 retest on a clean baseline.
No autonomous work remains that can clear those six items without operator
input or external infrastructure.
