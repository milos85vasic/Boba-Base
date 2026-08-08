# Governance & Constitution Compliance Audit — 2026-08-07

**Revision:** 1
**Last modified:** 2026-08-07T19:10:54Z
**Status:** active
**Scope:** Full-repository audit against the inherited Helix Constitution (constitution/CLAUDE.md,
constitution/Constitution.md) + verification of `docs/REMAINING_WORK_PLAN.md` (2026-06-14) closure
claims + live-toolchain health. Assembled from 6 parallel read-only subagent audits, 2026-08-07.
No file was modified by the audit itself; every finding below cites file:line, commit, or command
output as evidence (§11.4.6 — no guessing).

**Baseline:** HEAD `0d05ec1` on `main`. `docs/CONTINUATION.md` was last updated at commit `646b295`
(2026-06-16, "Session 14") — 21 commits / ~52 days behind HEAD at audit time.

---

## 0. How to execute this plan

Same discipline as `REMAINING_WORK_PLAN.md`: each `GA-NN` item is TDD-first (RED before fix,
§11.4.43/§11.4.115), gets a regression guard where it closes a defect (§11.4.135), and closes
only with pasted live command output (no self-certification words without evidence). Items
marked **OPERATOR-DECISION** are surfaced, not auto-executed. Non-contending items run in
parallel subagent streams (§11.4.70/§11.4.103).

---

## Phase 0 — Toolchain unblock (P0, prerequisite for verifying everything else)

### GA-01 — Python test toolchain is ABI-broken; no project `.venv`
- **Evidence:** live run of the documented command `python3 -m pytest tests/unit/ -q --import-mode=importlib`
  crashes during plugin auto-load: `ModuleNotFoundError: No module named 'rpds.rpds'` /
  `No module named 'pydantic_core._pydantic_core'`. `python3` resolves to 3.14.6; every native
  extension in `~/.local/lib/python3/site-packages` is compiled for `cpython-313`. No `.venv/`
  exists in the repo. **Zero tests can currently run** — `CONTINUATION.md`'s "4277 passed"
  claim is unreproducible today.
- **Blast radius:** blocks the entire unit suite, RW-21 verification, and 3 Challenge scripts
  (`download_proxy_deep_challenge.sh`, `private_tracker_html_challenge.sh`,
  `search_deep_coverage_challenge.sh`) that need `.venv`.
- **Fix:** create a project-pinned `.venv` (Python 3.12, matching `pyproject.toml`'s
  `target-version`/`mypy python_version`), `pip install -r tests/requirements.txt` (+ any
  `download-proxy` requirements), verify `pytest tests/unit/ -q --import-mode=importlib`
  actually collects and runs, paste the real N-passed/N-failed count. Document the exact
  bootstrap in `docs/TESTING.md` and `CONTINUATION.md`'s Quick-Start (which currently omits
  venv activation entirely).
- **Acceptance:** real pytest run completes (not crashes) with a captured summary line;
  count compared against the 4277 baseline and any delta explained.
- **Priority: P0.**

### GA-02 — Frontend Vitest toolchain broken (stale `node_modules`)
- **Evidence:** `cd frontend && npx vitest run` fails before any test executes:
  `Error: Cannot find module '@analogjs/vite-plugin-angular'` while loading `vitest.config.ts`.
  `frontend/node_modules` exists (332M) but is incomplete/stale.
- **Fix:** `cd frontend && npm ci` (or `npm install` if no lockfile match), re-run `npx vitest run`,
  capture the real pass count.
- **Priority: P0.**

### GA-03 — Extension Vitest toolchain never bootstrapped
- **Evidence:** `extension/node_modules` absent entirely. All 8 `challenges/extension/*.sh`
  scripts fail cleanly and honestly (`FAIL: vitest not installed ... run 'cd extension && npm install' first`)
  rather than false-passing — the challenges themselves are not buggy, the environment is
  just never set up. Blocks verification of the "379 passed / 33 spec files" claim in
  `CONTINUATION.md` Session 10.
- **Fix:** `cd extension && npm install`, re-run `npx vitest run` + all 8 extension challenges,
  capture real counts.
- **Priority: P1.**

---

## Phase 1 — Governance/tracking seam reconnection

**Root cause:** the mandated tracking chain (CONTINUATION.md → Issues.md/Fixed.md/workable_items.db
→ README entry-point) stopped being touched on 2026-06-16 while real engineering work (19
substantive commits) kept landing cleanly and correctly on `main`. The code is fine; the seam
that is supposed to keep governance docs synced with code was silently disconnected — precisely
the "prose exists, nobody wired the seam" failure mode the constitution's own §11.4.205/§11.4.226/
§11.4.227 anchors describe.

### GA-04 — `CONTINUATION.md` 52-day / 21-commit staleness gap
- **Evidence:** `git log --oneline 646b295..HEAD` = 21 commits (19 substantive), spanning
  2026-06-16T23:30 → 2026-08-07T21:52, none reflected in the file. Themed: Cyrillic/UTF-8
  encoding-fix wave (6 commits, `029c045`..`cdec407`), tracker/plugin fixes (7), egress/proxy/
  Jackett feature wave (4: `2f160cd`,`4e62eca`,`b44a2e4`,`be5062d`), doc-sync (1), host-mirror
  sync (2, no-op for CONTINUATION purposes).
- **Violates:** §12.10 / §11.4.131 (standing session-resumption file, always current).
- **Fix:** author a new "Session 15" entry summarizing all 19 substantive commits by theme,
  update `**Last commit:**`/`**Last modified:**`/`**Revision:**`, reconcile the "In flight —
  NEXT ITEM" section (the P0 Cyrillic item it names as in-flight is now DONE per commit
  `4aee3c4`/`8918d4b` — verify and close it in the doc).
- **Priority: P0.**

### GA-05 — Lava P1–P4 porting work never landed as tracked workable items
- **Evidence:** `docs/PORTING-FROM-LAVA.md` (created `be5062d`, 2026-07-01) maps 4 items to
  Lava-audit finding numbers: P1 §5 durable remote-exec, P2 §0/§4 egress/VPN routing, P3 §3
  configurable outbound proxy, P4 §8 Jackett cookie-session login. All four are implemented
  in code (`scripts/deploy-remote.sh`, `containers/pkg/remote/executor.go`,
  `scripts/egress-via-vpn.sh`, `download-proxy/src/config/proxy.py`,
  `qBitTorrent-go/internal/httpx/proxy.go`, commit `2f160cd` explicitly "port Lava §8
  finding") — but `grep -in "lava|egress|BOBA_UPSTREAM_PROXY|durable-run|remote-exec"
  docs/Issues.md docs/Fixed.md` returns zero hits. A §6/§9 item ("anti-bluff QA
  verdict/diagnostics strengthening") is listed applicable in the porting doc's own triage
  table but no commit closes it — status unknown.
- **Violates:** §11.4.148 / §11.4.202 / §11.4.208 (every actionable finding must land as a
  tracked item, not merely a commit message).
- **Fix:** create BOB-064..067 via the `workable-items` tool (not raw MD edits, to keep
  DB↔MD custody intact — `workable-items validate`/`diff` already confirmed the DB↔MD pair
  is internally in sync, just frozen at BOB-063), cite the implementing commit + file as
  evidence, close as Implemented/Fixed. Determine the true status of the §6/§9 item and
  either close it with evidence or track it honestly as open.
- **Priority: P0.**

### GA-06 — `docs/PORTING-FROM-LAVA.md` missing §11.4.44 revision header
- **Evidence:** `grep -n Revision docs/PORTING-FROM-LAVA.md` → empty.
- **Fix:** add `**Revision:** N` / `**Last modified:**` header block.
- **Priority: P2.**

### GA-07 — README.md has no §11.4.57/§11.4.212 doc-link entry-point section
- **Evidence:** `README.md`'s `## Documentation` section (lines 108–162) links 20+ docs but
  contains **zero** references to `docs/Issues.md`, `docs/Fixed.md`, `docs/CONTINUATION.md`,
  `docs/PORTING-FROM-LAVA.md`, `docs/browser_extension/Status.md`,
  `docs/browser_extension/RELEASE_READINESS.md`, `docs/COMPLETION_STATUS.md`, or
  `docs/RELEASE_READINESS_20260616.md`. Every tracker/status doc audited here is an orphan
  relative to README.
- **Violates:** §11.4.57 (`Tracked-Items + Status Documents` mandated section) / §11.4.212
  (README as canonical entry point for ALL project documentation).
- **Fix:** add the mandated table (Document | Last modified | Revision | Markdown | HTML | PDF)
  covering every tracker/status doc in the repo, including this audit doc and
  `REMAINING_WORK_PLAN.md`.
- **Priority: P0** (structural, repo-wide).

### GA-08 — `docs/browser_extension/Status.md` stale by 4 commits
- **Evidence:** Rev 15, `2026-06-13T13:10:00Z`. Commits since, untouched in the doc:
  `a410b91` (coverage), `0897248` (video-confirm), `ee4a01b` (crash-hardening), `0dc247b`
  (qBittorrent 5.x compat).
- **Fix:** update Status.md + regenerate `Status_Summary.md` + HTML/PDF siblings
  (§11.4.45/§11.4.56).
- **Priority: P2.**

### GA-09 — `workable_items.db`: BOB-008 missing `operator_block_details` row
- **Evidence:** `workable-items validate --db docs/workable_items.db` → 1 violation:
  "BOB-008: Operator-blocked with no operator_block_details row (§11.4.148 D3)". The prose
  in `Issues.md` DOES contain the `**Operator-Block-Details:**` line — this is a DB-column
  population gap, not a doc gap.
- **Fix:** populate via the `workable-items` tool's proper subcommand (not raw SQL).
- **Priority: P3.**

### GA-10 — No successor to `docs/RELEASE_READINESS_20260616.md`; no top-level v1.0.0 ledger
- **Evidence:** the doc is a self-labeled point-in-time snapshot (HEAD `8b9ef90`); 20 commits
  since have touched the audited surfaces. Its own text names "no top-level proxy/merge-service
  v1.0.0 readiness ledger" as an open blocker — this is RW-20 in the existing plan, still
  NOT-DONE (confirmed by the RW-plan verification agent).
- **Fix:** create the ledger doc (dedupes with RW-20 — track under one ticket, not two).
- **Priority: P2.**

---

## Phase 2 — Security correctness gaps (corrections to RW-plan closure claims)

### GA-11 — RW-02 incomplete: 2 mutating routes still unauthenticated
- **Evidence:** `routes.py`/`scheduler.py`'s auth rollout covers download/upload/file/magnet
  (routes.py) and POST/DELETE schedules — but `PATCH /api/v1/schedules/{id}`
  (`scheduler.py:108`) and `PUT /api/v1/theme` (`routes.py:82`) have **no**
  `Depends(require_api_token)`. Confirmed by omission: `tests/security/test_hooks_schedules_auth.py:194-198`'s
  own `_MUTATING` enumeration never included them — the original fix and its test were
  scoped incompletely together.
- **Fix (TDD):** RED — extend `_MUTATING` to include PATCH schedule + PUT theme, confirm the
  new assertions fail (401 expected, currently unauthenticated) → add
  `Depends(require_api_token)` to both routes → GREEN → live curl-verify 401-unauth /
  200-with-token on a running container.
- **Priority: P0** (security).

### GA-12 — RW-06 unverifiable: rutracker ReDoS fix not confirmed deployed
- **Evidence:** source fix present (`plugins/rutracker.py:140`, `{0,512}` bound); no live
  container running on the audit host to check `config/qBittorrent/nova3/engines/rutracker.py`
  (the installed copy) or measure live parse timing — a §11.4.108 SOURCE≠ARTIFACT/RUNTIME
  gap that is unverified, not necessarily unfixed.
- **Fix:** bring up the compose stack (`./start.sh`), run `./install-plugin.sh`, verify
  `grep '{0,512}' config/qBittorrent/nova3/engines/rutracker.py` on the container, capture
  timing of a large rutracker result page.
- **Priority: P1** (needs live stack).

### GA-13 — RW-07 partial: nnmclub e2e SKIP-on-404 fallback never removed
- **Evidence:** `tests/e2e/test_live_stack_evidence.py:265` still contains the skip fallback;
  the acceptance criterion ("un-skip") is unmet regardless of live container state — the
  route existing in source (`download-proxy/src/api/auth.py:350`) isn't what was asked for.
- **Fix:** with the live stack up, confirm `curl :7187/api/v1/auth/nnmclub/status` → 200,
  remove the skip fallback, let the assertion run for real, capture the pass.
- **Priority: P1** (needs live stack).

---

## Phase 3 — Test-type integrity (constitution's "non-unit tests hit real services" rule)

### GA-14, GA-15, GA-16 — Three test files mislabeled by directory mock the exact system under test
- **Evidence:**
  - `tests/integration/test_merge_api.py` (577 lines) — own docstring: "Uses FastAPI TestClient
    with mocked SearchOrchestrator." Every route test `@patch("api.routes._get_orchestrator")`.
  - `tests/e2e/test_full_pipeline.py` — docstring claims "End-to-end", but patches
    `SearchOrchestrator._get_enabled_trackers`/`_search_tracker` with a synthetic fake — no
    real tracker HTTP call ever happens.
  - `tests/contract/test_tracker_stats_contract.py:80-81` — same `monkeypatch.setattr` pattern
    on the same two methods.
- **Violates:** CLAUDE.md's inherited rule: "Mocks, stubs... are permitted ONLY in unit tests
  ... All other test types MUST interact with real fully implemented System" (§11.4.27).
- **Fix:** for each file — (a) relocate the mocked version into `tests/unit/` under an honest
  name (the coverage IS valuable as unit-level route-contract testing), AND (b) author a new
  real-service replacement in the original directory using the project's EXISTING live-stack
  fixtures (`tests/fixtures/compose.py`, `tests/fixtures/services.py`,
  `tests/integration/test_fixtures_bring_up_services.py` already demonstrate this pattern is
  viable in this repo) so the directory's contract (integration/e2e/contract = real services)
  is actually met.
- **Priority: P1** (each file independent, parallelizable).

### GA-17 — `#legacy-untriaged` skip-tag family never actually triaged
- **Evidence:** ~10 sites (`tests/e2e/test_public_trackers_return_results.py:128`,
  `tests/unit/test_openapi_frozen.py:15,23`, `tests/unit/test_plugin_smoke.py:45`,
  `tests/docs/test_no_broken_links.py:51`, `tests/fixtures/services.py:9`, others) carry
  `SKIP-OK: #legacy-untriaged` — syntactically satisfies the format, but the "ticket" is a
  literal placeholder admitting it was never triaged.
- **Fix:** triage each site individually — determine the real reason, either fix/un-skip or
  replace the placeholder with a real ticket id + reason.
- **Priority: P3.**

### GA-18 — 7 permanently-skipped dead Jackett-autoconfig Python tests
- **Evidence:** `tests/contract/test_jackett_autoconfig_contract.py:18,24`,
  `tests/integration/test_jackett_autoconfig_real.py:71,77,83`,
  `tests/e2e/test_jackett_autoconfig_e2e.py:32,38`,
  `tests/security/test_jackett_autoconfig_secrets.py:41` — all skip with "endpoint moved to
  boba-jackett:7189". Migration confirmed deliberate:
  `download-proxy/src/api/__init__.py:301-306` explicitly removes the Python endpoint in
  favour of the Go service (RW-13 evidence).
- **Fix (§11.4.124 investigate-before-remove — investigation above already satisfies the
  proof requirement):** delete these dead test bodies in one dedicated commit citing the
  git-history/migration evidence; the replacement coverage lives in
  `qBitTorrent-go/tests/integration/jackett_db_test.go` and the Go autoconfig package.
- **Priority: P3.**

---

## Phase 4 — Go backend parity (blocked on operator decision)

### GA-19 — OPERATOR-DECISION: is `--profile go` parity still a release goal?
- **Evidence:** this is RW-09, unresolved since 2026-06-14. `docs/migration/PARITY_GAPS.md`
  and `docs/features/Status.md:52,194` are unrevised ("Last audited 2026-04-27", 6 ported / 4
  partial / 8 missing). Confirmed-missing since the plan was written: scheduler driver loop
  (`qBitTorrent-go` scheduler files have no `time.Ticker`), metadata enricher (no equivalent
  package), public-tracker plugin fan-out (no `exec.Command` fan-out in
  `internal/service`). Jackett autoconfig (RW-13) is now PARTIAL — implemented as its own Go
  service, canonical per `download-proxy/src/api/__init__.py:301-306`, but BEP48/scrape
  validation and a CAPTCHA REST endpoint are still absent from the Go side.
- **This gates:** RW-10 (scheduler driver — "highest-impact silent functional hole on the Go
  path" per the RW-plan's own words), RW-11 (enricher), RW-12 (plugin fan-out), the remainder
  of RW-13, and GA-20's stress/chaos items RW-14/RW-15 to the extent they're Go-path-specific.
- **Decision needed:** commit real scope to close the 3 missing Go subsystems (multi-day
  effort), or mark the Go backend a documented future blueprint and stop implying it's a
  near-term parity target in Status.md.
- **Priority: P1, surfaced via §11.4.66 — not auto-executed.**

### GA-20 — RW-14/RW-15 stress/chaos coverage claims were inaccurate; still NOT-DONE
- **Evidence:** commit `a410b91` ("close Go + extension coverage gaps RW-14/RW-16") actually
  added Go `internal/jackett`/`internal/logging` unit tests and an extension parser test —
  NOT §11.4.85-conformant stress/chaos coverage for the tracker-fetch/cookie-auth path
  (RW-14) or the scheduler+hooks+SSE-broker surface (RW-15). No matching test files exist.
  `RW-16`'s Go-DB concurrent-write test (`jackett_db_test.go:440-500`) predates the plan
  (commit `8936545`, 2026-04-27) and has no fault-injection — genuinely PARTIAL, not the
  chaos coverage the plan calls for.
- **Fix:** author real `tests/stress/test_tracker_fetch_stress_chaos.py` (download-proxy
  cookie-auth path, overlapping the RW-03 SSRF surface) and
  `tests/stress/test_scheduler_hooks_sse_stress_chaos.py`, plus a chaos-fault-injection
  extension to the existing Go DB concurrency test (process-kill / resource-exhaustion, not
  just concurrent writes). Correct the historical claim in a follow-up doc note (§11.4.6 —
  don't leave the false "closed" claim standing).
- **Priority: P2.**

---

## Phase 5 — Challenges / HelixQA infrastructure bugs

### GA-21 — `jackett_autoconfig_clean_slate.sh` polls a retired endpoint
- **Evidence:** 3 references to `/api/v1/jackett/autoconfig/last` (lines 8, 58, 62) — this
  endpoint was deliberately removed per CLAUDE.md ("The Python `/api/v1/jackett/autoconfig/last`
  endpoint was removed"). The challenge would always fail step 5 against the current
  architecture.
- **Fix:** update to poll the Go `:7189` autoconfig-runs API
  (`GET /api/v1/jackett/autoconfig/runs` or `/runs/{id}` per `qBitTorrent-go/internal/jackettapi/router.go`).
- **Priority: P1.**

### GA-22 — All 6 HelixQA bank symlinks are dangling absolute macOS paths
- **Evidence:** `challenges/helixqa-banks/*.yaml` → symlinks to
  `/Volumes/T7/Projects/Boba/submodules/helixqa/banks/*.yaml`, authored on a different dev
  machine. Broken on this (and any non-that-exact-Mac) host. The real files exist and are
  correct at `submodules/helixqa/banks/*.yaml` (37-entry populated submodule, confirmed not
  empty).
- **Fix:** replace with relative symlinks (`ln -sf ../../submodules/helixqa/banks/<name>.yaml`).
- **Priority: P1.**

### GA-23 — HelixQA bank action steps hardcode `/Volumes/T7/Projects/Boba/...`
- **Evidence:** e.g. `boba-boba-ctl.yaml`: `cd /Volumes/T7/Projects/Boba/cmd/boba-ctl && go build ...`;
  `boba-docs-chain.yaml`: `bash /Volumes/T7/Projects/Boba/scripts/docs_chain.sh`. Non-portable
  to this or any other checkout.
- **Fix:** parametrize with a `$PROJECT_ROOT`/`$REPO_ROOT` variable the HelixQA runner
  resolves at invocation time, or make paths script-relative.
- **Priority: P2.**

### GA-24 — `no_suspend_calls_challenge.sh` false-positives on a governance doc
- **Evidence:** flags `constitution/docs/scripts/guard-forbidden-commands.md` because that
  doc *quotes* the forbidden systemctl/loginctl verbs it documents/enforces. Its
  `EXCLUDE_PATHS` allowlist covers `CONSTITUTION.md`/`AGENTS.md`/`CLAUDE.md` but not this
  file — a carrier false-positive, the exact §11.4.201 pattern the constitution itself warns
  about.
- **Fix:** add the file to `EXCLUDE_PATHS` in
  `scripts/host-power-management/check-no-suspend-calls.sh`.
- **Priority: P3.**

---

## Phase 6 — CONST-033 real signal (HIGH — project's own hard-ban class)

### GA-25 — `host_no_auto_poweroff_challenge.sh` found 1 genuine post-fix poweroff broadcast
- **Evidence:** 4/5 checks pass; 1 fails — a "will power off" journal broadcast recorded
  AFTER the documented fix marker (`2026-04-28T20:54:31+03:00`).
- **This is the exact incident class CLAUDE.md's own CONST-033 Operational Note exists for.**
  Per that note, the correct response is triage BEFORE assuming host-code causation and
  BEFORE dismissing it: (1) `uptime` cross-check against any alleged downtime window, (2)
  `journalctl -k --since "24 hours ago" | grep -iE "will suspend|systemd-suspend"`, (3)
  `journalctl -k --since "24 hours ago" | grep -iE "oom-kill|killed process"` + decode the
  `oom_memcg` cgroup path if present, (4) re-run both CONST-033 challenges, (5) document
  findings in `docs/incidents/<date>-*.md` regardless of outcome. **Only read-only diagnostic
  commands** — nothing that triggers a power-state transition, per the absolute Hard Ban.
- **Priority: P0** — triage this first, independent of everything else in this plan, given
  the project's own stated severity for this incident class (prior data-loss history cited
  in CLAUDE.md).

---

## Phase 7 — Gate-scoping bug

### GA-26 — `ruff check .` sweeps `submodules/containers/` (a separately-governed submodule)
- **Evidence:** `[tool.ruff]` in `pyproject.toml` has no `exclude`/`extend-exclude` at all.
  71 ruff violations found; sampled violations are exclusively in
  `submodules/containers/scripts/resource-policy/*.py` — a submodule that owns its own
  engineering standards per §11.4.28 decoupling. This inflates boba's own lint-gate count
  with debt that isn't boba's to fix.
- **Fix:** add `extend-exclude = ["submodules/", "constitution/", ".worktrees/"]` to
  `[tool.ruff]`, re-run `ruff check .`, report the TRUE boba-only violation count (may be 0,
  may be nonzero — verify, don't assume).
- **Priority: P2.**

---

## Phase 8 — Governance-layer ambiguity (needs operator clarification)

### GA-27 — OPERATOR-DECISION: Hard Stop #3 vs. this project's documented maintenance workflow
- **Evidence:** the inherited constitution's Hard Stop #3 states container orchestration
  must be owned exclusively by the project's own binary/orchestrator, with direct
  `docker`/`podman` commands "prohibited as workflows." This project's own CLAUDE.md
  "Critical Constraints" section explicitly prescribes direct `podman exec
  qbittorrent-proxy ...`, `podman restart qbittorrent-proxy`, and `podman compose down &&
  podman compose up -d` as the mandated procedure for Python-source reload, plugin reload,
  and compose/env changes.
- **Decision needed:** either (a) formally classify this as an intentional, documented
  exception per §11.4.17 (with a one-line rationale — e.g. "restart-level granularity below
  full stack lifecycle is exempt because start.sh/stop.sh don't yet expose it"), or (b)
  extend `start.sh`/`stop.sh` with subcommands that wrap these exact operations (e.g.
  `./start.sh --restart-proxy`, `./start.sh --reload-plugins`) so operators never type raw
  podman commands, closing the gap for real.
- **Priority: P1, surfaced via §11.4.66 — not auto-executed.**

---

## Summary table

| Phase | Items | Blocking on live infra? | Blocking on operator decision? |
|---|---|---|---|
| 0 — Toolchain unblock | GA-01..03 | No | No |
| 1 — Governance/tracking | GA-04..10 | No | No |
| 2 — Security corrections | GA-11..13 | GA-12/13 yes | No |
| 3 — Test-type integrity | GA-14..18 | GA-14..16 partial (real-service replacements) | No |
| 4 — Go parity | GA-19..20 | No | **GA-19 yes** |
| 5 — Challenge/HelixQA bugs | GA-21..24 | No | No |
| 6 — CONST-033 signal | GA-25 | No (read-only triage) | No |
| 7 — Gate scoping | GA-26 | No | No |
| 8 — Governance ambiguity | GA-27 | No | **GA-27 yes** |

**Cross-reference:** GA-11..13, GA-19..20 correct/extend `docs/REMAINING_WORK_PLAN.md`'s
RW-02/06/07/09/14/15 entries — that document's status table should be updated in the same
pass to avoid two divergent trackers describing the same defects (§11.4.186 anti-divergence).

**Definition of done for this audit:** every GA item above reaches DONE (with live-captured
evidence), OPERATOR-DECISION items (GA-19, GA-27) are resolved, `REMAINING_WORK_PLAN.md`'s
corrected items are reconciled, README carries the doc-link section, CONTINUATION.md is
current, and every fix ships with a regression guard + (where the surface is user-facing)
a HelixQA Challenge entry.
