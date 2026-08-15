# BOB-066 Evidence — Cross-Layer BOBA_UPSTREAM_PROXY Audit

**Revision:** 1
**Last modified:** 2026-08-15T12:15:00Z
**Item:** BOB-066 — Lava P3: BOBA_UPSTREAM_PROXY in download-proxy + qBitTorrent-go + Jackett + compose env-forward
**Status:** In progress (L1/L2/L4-partial WIRED; L3 residual gap)
**Verifier:** `challenges/scripts/upstream_proxy_wired_challenge.sh`
**Run id:** `20260815T115831Z`

## §11.4.108 Runtime signature — three-mode verifier evidence

Anti-bluff coverage per §11.4.115 polarity switch + §11.4.107(10) self-validation.
Each mode's exit code is captured; every mode required to exit 0 for closure eligibility.

### Mode 1 — `--self-validate` (analyzer-honesty against a synthetic golden-BAD tree)

The verifier runs its OWN detector chain against a temp tree where every wire
is DELIBERATELY ABSENT (stub `main.py` without `apply_proxy_env`, stub `search.py`
with zero `trust_env`, stub `httpx/proxy.go` with no `Configure/NewTransport/Proxy`,
empty `docker-compose.yml`). PASS = every detector correctly returned FAIL on
the bad tree → the analyzer is not a bluff.

```
=== self-validate: run detectors against a synthetic golden-BAD tree ===
PASS: self-validate — every detector correctly FAILED on the golden-BAD tree
```
**Exit: 0** — analyzer honesty confirmed.

### Mode 2 — GREEN (`RED_MODE=0`, default) — real tree

```
=== BOB-066 four-layer cross-layer verifier ===
RED_MODE=0  (0=GREEN guard, 1=reproduce pre-fix defect state)

--- L1: download-proxy (Python) ---
  [PASS] L1 config/proxy.py exports apply_proxy_env + aiohttp_session_kwargs
  [PASS] L1 apply_proxy_env() invoked at boot in download-proxy/src/main.py
  [PASS] L1 aiohttp ClientSession sites carry trust_env (9 uses of _tracker_session_kwargs)

--- L2: qBitTorrent-go ---
  [PASS] L2 internal/httpx/proxy.go exports Configure + NewTransport + Proxy honoring BOBA_UPSTREAM_PROXY
  [PASS] L2 httpx.Configure(cfg.UpstreamProxy) called in cmd/qbittorrent-proxy/main.go
  [PASS] L2 httpx.NewTransport() used in internal/api (torrent-download client)

--- L3: Jackett ---
  [SKIP] L3 Jackett proxy honor: reason=extension_absent (neither compose env-forward nor ServerConfig.ProxyUrl wired) — tracked as BOB-066 residual

--- L4: docker-compose.yml env-forward ---
  [PASS] L4 docker-compose.yml service 'download-proxy' env-forwards proxy vars
  [PASS] L4 docker-compose.yml service 'qbittorrent-proxy-go' env-forwards proxy vars
  [PASS] L4 docker-compose.yml service 'qbittorrent' env-forwards proxy vars
  [SKIP] L4 'jackett' env-forward absent (see L3 SKIP; tracked)
  [SKIP] L4 'boba-jackett' env-forward absent (not tracker-bound: talks to Jackett loopback + local DB only)

==========================================
Summary: PASS=9  FAIL=0  SKIP=3
Notes:
  - L3 residual: Jackett has neither env-forward nor ServerConfig.ProxyUrl wired — see BOB-066 description
==========================================
PASS: upstream_proxy_wired_challenge — every wired layer verified; residual gaps honestly SKIP'd
```
**Exit: 0** — 9 PASS / 0 FAIL / 3 honest SKIP (§11.4.3 / §11.4.69 `extension_absent`).

### Mode 3 — RED (`RED_MODE=1`) — §11.4.115 polarity flip

Under RED each presence-detector's polarity flips: PRESENT code becomes FAIL
(because the pre-fix defect state RED simulates would have it ABSENT). On a
tree where the fix has landed, EXPECT many FAILs — that IS the signal the
polarity switch + detectors work end-to-end (they would have caught the defect
if the code were un-wired). `fail == 0` under RED would mean detectors ignore
polarity OR the tree was reverted — both bluffs surfaced here.

```
==========================================
Summary: PASS=0  FAIL=9  SKIP=3
==========================================
RED-MODE VERIFY: 9 presence-detectors correctly negated under RED — polarity switch works, RED→GREEN flip proven
```
**Exit: 0** — 9 detectors correctly negated → RED→GREEN flip proven.

## §11.4.108 four-layer audit — per-layer runtime signatures

| Layer | Sub-requirement | Runtime signature | Status |
|---|---|---|---|
| **L1** | Python download-proxy honors `BOBA_UPSTREAM_PROXY` (urllib subprocs + aiohttp) | `download-proxy/src/main.py:97` calls `apply_proxy_env()`; 9 `aiohttp.ClientSession` sites in `merge_service/search.py` carry `_tracker_session_kwargs()=trust_env`; `config/proxy.py` exports the API + `UPSTREAM_PROXY_ENV="BOBA_UPSTREAM_PROXY"` sentinel | **WIRED** |
| **L2** | qBitTorrent-go `http.Transport.Proxy` honors `BOBA_UPSTREAM_PROXY` (or standard chain) | `internal/httpx/proxy.go` exports `Configure/NewTransport/Proxy`; `cmd/qbittorrent-proxy/main.go:29` calls `httpx.Configure(cfg.UpstreamProxy)` at boot; `internal/api/download.go:65` installs `httpx.NewTransport()` on the torrent-download client; socks5:// supported natively (remote DNS) | **WIRED** |
| **L3** | Jackett — env-forward OR `ServerConfig.ProxyUrl` | Neither path present. `jackett` container has no proxy env-forward; no Go code touches `ProxyUrl`/`ProxyType`/`ServerConfig` in `qBitTorrent-go/internal/`. | **RESIDUAL GAP** |
| **L4** | `docker-compose.yml` env-forward for every tracker-touching service | `download-proxy`, `qbittorrent-proxy-go`, `qbittorrent` all env-forward `BOBA_UPSTREAM_PROXY` + `HTTP_PROXY` + `HTTPS_PROXY` + `NO_PROXY` (with default bypass hosts). `jackett` + `boba-jackett` do NOT (boba-jackett is loopback-only so not required). | **3/5 WIRED** (Jackett gap = L3) |

## Recommended follow-up for L3

File a scoped ticket (e.g. `BOB-066b`) implementing ONE of:
- **(a)** Add proxy env-forward to the `jackett` service block in `docker-compose.yml` (mirror the block at lines 15-20 of the `qbittorrent` service). Simplest fix.
- **(b)** Add `qBitTorrent-go/internal/jackettconfig/proxy.go` that on Jackett-config load reads `BOBA_UPSTREAM_PROXY` and PATCHes Jackett's `ServerConfig.json` `ProxyType`/`ProxyUrl` fields (Jackett will honor them for its own indexer HTTP egress). Requires a boba-jackett boot-time step + safe file-write discipline.

## Status decision (§11.4.6 / §11.4.108 / §11.4.226)

BOB-066 is NOT closed as Completed because L3 remains un-wired: closing with 3/4
sub-requirements met would be a §11.4.226 evidence-class-at-closure violation
(the reported defect layer includes L3, and a source-green closure of an
un-wired layer is exactly the pattern the anchor forbids). Bumped Queued →
In progress; `item_history` entry #65 records the audit with this evidence
path; description carries the AUDIT NOTE 2026-08-15 block naming L1/L2/L4
wired + L3 residual + follow-up recommendation.
