# Boba — Release-Readiness Assessment (RW-18..21)

**Revision:** 1
**Last modified:** 2026-06-16T10:30:00Z
**Status:** assessment only — **NO tag created** (per task constraint + §11.4.40/§11.4.113)
**Baseline:** HEAD `8b9ef90` on `main`. Assembled by READ-ONLY investigation +
this-session live test runs. Anti-bluff (§11.4.6): every claim cites a captured log,
a live test run from this session, a commit, or a file. Hypotheses are labelled.
**Scope:** is the proxy / merge-service product (the shipped default Python path) +
its client apps tag-ready, and what concretely blocks a vN.0.0 tag.

---

## 1. Headline verdict

**NOT YET tag-ready for a clean vN.0.0**, but very close. The test suites are GREEN,
the distribution build exists for the client apps, and the default Python product is
debt-free per the plan. The blockers are: (a) the P0/P1 **security** items (RW-01..05)
are still OPEN in the plan and gate any release that exposes mutating endpoints on the
LAN; (b) two **OPERATOR-DECISION** items (RW-05 LAN threat model, RW-09 Go-parity scope)
must be resolved; (c) **release-packaging gaps** — `releases/0.1.0` ships the extension +
frontend but **not** the download-proxy/merge-service artefact, and there is **no
top-level proxy/merge v1.0.0 readiness ledger** (RW-20); (d) a full §11.4.40 retest must
be run on a clean baseline immediately before the tag.

Everything below is the evidence.

---

## 2. Test-suite state (verified live this session — counts NOT assumed)

| Suite | Claimed | **Verified this session** | Evidence |
|---|---|---|---|
| Python unit | 4209 | **4209 passed, 0 failed** | `qa-results/python-unit-resweep2.log` (16 Jun 01:59) — `4209 passed, 3 warnings in 434.11s`. The earlier `python-unit-resweep.log` (01:45) had 2 failures; commit `b7eb476` "fix(tests): close 2 residual full-suite failures (coverage + SSE flake)" fixed them, and resweep2 is the GREEN re-run. |
| Go `-race` | 13/13 | **13 packages OK with `-race`** | Ran `GOMAXPROCS=2 nice -n 19 go test -race -count=1 ./...` this session — all 13 `internal/*` packages `ok`; 3 `cmd/*` have no test files (entrypoints). |
| Frontend (Vitest) | 371 | **371 passed (30 files)** | Ran `npx vitest run` in `frontend/` this session — `Test Files 30 passed (30) / Tests 371 passed (371)`. |
| Extension (Vitest) | 816 | **814 passed (68 files)** | `qa-results/ci-ext_wave15_20260613.log` — `Test Files 68 passed (68) / Tests 814 passed (814) / CI-EXT: PASS`. (The "816" / "799" figures in older docs are superseded; 814 is the latest wave.) |

The 3 Python warnings are benign (a Starlette `httpx` deprecation + a `_bounded`
coroutine resource-warning in two deep-coverage tests — not failures). **All four suites
are GREEN.**

---

## 3. RW-NN status (DONE vs OPEN, with evidence)

### PHASE 1 — Security (P0/P1) — the real release gate
| Item | Status | Evidence / note |
|---|---|---|
| **RW-01** hooks auth + sandbox | **OPEN** | Plan §RW-01; no commit found closing it. P0. |
| **RW-02** default-open write surface | **OPEN** (gated on RW-05) | Plan §RW-02. P0. |
| **RW-03** SSRF block | **PARTIAL** | A guard exists — `routes.py:1254` logs "Refusing SSRF-unsafe download URL (non-public target); skipping". Needs verification it covers BOTH `/download/file` and `/download` non-tracker paths + a RED→GREEN regression guard per the acceptance. P0. |
| **RW-04** auth-consistency + Go CORS + Jackett | **PARTIAL** | Commit `37a8c45` "fix(security): P0 hardening — SSRF block, hook sandbox, consistent auth, Go CORS" touches these surfaces; needs per-item verification against the acceptance criteria. P1. |
| **RW-05** LAN threat model | **OPEN — OPERATOR-DECISION** | Bind tunnel `127.0.0.1` vs keep `0.0.0.0`+auth. Gates RW-02 aggressiveness. P1. |

> **Security is the dominant blocker.** Commits `37a8c45` and `1108fc1` did P0
> hardening, but the plan still lists RW-01..05 as the open exposure set, and no
> RED→GREEN regression-guard evidence per their acceptance criteria was found this
> session. Until each is verified closed (or the LAN surface is removed via RW-05 =
> bind loopback), a release that exposes the mutating endpoints is not honestly tag-ready.

### PHASE 2 — Functional correctness + deployment
| Item | Status | Evidence |
|---|---|---|
| **RW-06** deploy rutracker ReDoS fix | **DONE (verified)** | The installed engine `config/qBittorrent/nova3/engines/rutracker.py` contains the `{0,512}` bound (verified this session, matches `plugins/rutracker.py`). §11.4.108 source==artifact signature present. |
| **RW-07** nnmclub `/auth/.../status` drift | **OPEN/UNVERIFIED** | Plan says route 404s on the container; not re-probed this session (tunnel intermittently down per `qa-results/tunnel-keepalive-testsession.log`). Likely resolved with the RW-06 restart — needs a live 200 probe to confirm. |
| **RW-08** search latency / sync reset | **DIAGNOSED (this session)** | Full root-cause + fix proposal in `docs/qa/rw08-latency-diagnosis-20260616.md`. Not yet fixed (P2). |

### PHASE 3 — Go parity
| Item | Status | Evidence |
|---|---|---|
| **RW-09..13** Go backend parity | **OPEN — OPERATOR-DECISION (RW-09)** | `docs/migration/PARITY_GAPS.md`: 6 ported / 4 partial / 8 missing. Go path is opt-in (`--profile go`) and NOT the shipped product. Deferred-by-design unless RW-09 = yes. Does NOT block a Python-path release. |

### PHASE 4 — Coverage
| Item | Status | Evidence |
|---|---|---|
| **RW-14..17** stress/chaos gaps | **PARTIAL/IN PROGRESS** | `qa-results/` has `pipeline_stress/`, `pipeline_chaos/`, `search_stress/`, `search_orch_stress/`, `plugin_stress/`, `enricher_stress/` directories — substantial §11.4.85 coverage landed. Remaining surfaces (tracker-fetch/cookie-auth, scheduler/hooks/SSE-broker, boba-jackett autoconfig) per plan; RW-17 gate-enforcement audit not confirmed this session. P2. |

### PHASE 5 — Docs / release / housekeeping
| Item | Status | Evidence |
|---|---|---|
| **RW-18** export `courses/0{1..4}-*/{README,script}.md` | **OPEN** | The 8 source `.md` exist (`courses/0{1..4}-*/`); **no `.html`/`.pdf` siblings present** → §11.4.65 export still pending. LOW. |
| **RW-19** stale extension RELEASE_READINESS locale claim | **DONE** | `docs/browser_extension/RELEASE_READINESS.md` now states "8 committed + built" and §8 explicitly notes the 4→8 claim is FIXED. |
| **RW-20** top-level proxy/merge v1.0.0 readiness ledger | **OPEN** | Only the extension has a readiness report; `docs/` has `RELEASE_TORRENT_UPLOAD_FIX.*` but **no proxy/merge-service v1.0.0 ledger**. Must exist before promoting `v1.0.0-rc` → `1.0.0`. LOW but a named pre-tag gate. |
| **RW-21** contract tests green under 3.12 | **LIKELY GREEN** | Contract tests are part of the 4209-green Python suite (run under the repo `.venv`, py3.13). New magnet/download endpoints are in the frozen `docs/api/openapi.json` per the plan; confirm under the intended interpreter. INFO. |

---

## 4. Distribution build (`releases/0.1.0`)

- **Extension (BobaLink):** built — `releases/0.1.0/extension/{debug,release}/` contains
  chrome + firefox + sources zips (`bobalink-1.0.0-*.zip`), `SHA256SUMS`, `BUILD_INFO.json`,
  `build.log`. Tagged `v1.0.0-rc` (2026-06-11).
- **Frontend (Angular):** built — `releases/0.1.0/frontend/{debug,release}/frontend-b7eb4761fd22.tar.gz`
  + `SHA256SUMS` + `BUILD_INFO.json`.
- **download-proxy / merge-service:** **NOT in `releases/0.1.0`.** The `releases/README.md`
  layout *documents* a `download-proxy/{source,container-image}/` slot, but no such artefact
  was produced for 0.1.0. **Gap:** the core shipped product has no distribution artefact in
  the release tree.
- `RELEASE_NOTES.md` (0.1.0): "Targets requested: extension; Builds completed: 1" — confirms
  only the extension was built for this release pass.

So "both apps" (extension + frontend) are built; the **server product is not packaged**.

---

## 5. docs/features Status (288 features)

`docs/features/Status.md` (Rev 6): **288 feature rows** (one per real unit). Per-row Video
tally: **28 VIDEO-CONFIRMED**, **14 PENDING (UI — film next)**, **246 N/A (no UI —
test-covered)**. Honest classification per §11.4.143/§11.4.6 — a row is VIDEO-CONFIRMED only
when a committed recording shows it. The 14 PENDING are user-visible controls not yet
*individually* filmed (not failures); the 246 N/A are non-UI units confirmed by their
cited tests + the journey that drives them.

---

## 6. Concrete blockers to a vN.0.0 tag (honest, prioritized)

1. **[P0 — security] RW-01, RW-02, RW-03** — close + verify each with a RED→GREEN
   regression guard (§11.4.135), redeployed and §11.4.108-verified on the container.
   These are the real exposure on a `0.0.0.0` LAN tunnel.
2. **[P1 — decision] RW-05 LAN threat model** — operator must choose loopback vs
   LAN+auth; it sets how aggressive RW-02 must be (could close most surface at once).
3. **[P1 — verify] RW-04, RW-07** — confirm the partial security fixes (`37a8c45`) meet
   each acceptance; live-probe the nnmclub status route returns 200.
4. **[P1/P5 — packaging] RW-20 + download-proxy artefact** — produce the proxy/merge
   v1.0.0 readiness ledger AND a download-proxy distribution artefact in `releases/`.
5. **[P2 — robustness] RW-08** — fix the sync-over-tunnel reset (heartbeat/SSE) + tune
   the fan-out deadline; diagnosis ready in `docs/qa/rw08-latency-diagnosis-20260616.md`.
6. **[P5 — docs] RW-18** — export the 8 course `.md` files to `.html`/`.pdf` (§11.4.65).
7. **[decision] RW-09** — declare Go parity in-scope or deferred-by-design.
8. **[gate] §11.4.40 full retest** on a clean baseline immediately before the tag — the
   suites are green now but the authoritative pre-tag retest has not been run post-all-fixes.

**Not blockers:** Go-path parity (opt-in, not shipped); the 14 PENDING-UI feature rows
(filmed-next, not broken); BOB-008 RuTracker CAPTCHA (irreducible human step, surrounding
mechanism tested).

---

## 7. One-line readiness statement

The four test suites are GREEN (Python 4209, Go 13/13 `-race`, frontend 371, extension
814) and the client apps are built, but the project is **not yet tag-ready**: the P0
security items (RW-01/02/03) remain open, two operator decisions (RW-05/RW-09) are
unresolved, the server product is unpackaged with no v1.0.0 ledger (RW-20), and the
§11.4.40 pre-tag full retest still has to run on a clean baseline. **Do NOT tag until
those close.**
