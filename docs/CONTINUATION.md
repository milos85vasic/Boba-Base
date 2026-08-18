# Continue — Project Status Snapshot

**Revision:** 24
**Last modified:** 2026-08-18T21:10:20Z

## TERMINAL STATE (this write) — §11.4.126 endless-loop terminal condition MET

- **Pre-build: 27 passed / 0 failed** — all invariants GREEN including new CM-RESOURCE-PRESSURE-SIGNATURE-CHECK (invariant 25) and post-fix CM-DOCS-CHAIN-ENGINE-VERIFY (invariant 24)
- **3 boba remotes IN SYNC at `fab6707a`**
- **§11.4.209 review**: 0 BLOCKING / 0 IMPORTANT open / 5/6 MINOR fixed / 1 MINOR honest SKIP / 2 NIT non-blocking / Fable-xhigh re-review owed as §11.4.197 upgrade
- **§11.4.115(F) polarity**: 5/5 RED CONFIRMED across real pathological fixtures
- **Resource-pressure timer**: LIVE + ARMED (next fire 22:42 CEST)
- **1 subagent dispatched** for §11.4.108 rebuild + runtime-signature verification

## Session commit summary (~20 boba commits + 4+ constitution commits since 457cca4)

## SESSION 2026-08-15 → 2026-08-18 (Session 4db6eadb-03e7)

**Working state at last write:** 3 boba remotes IN SYNC at `9c282ff`. resource-pressure-signature-check systemd-user timer LIVE (next fire 22:42 CEST). 3 subagents in flight: Task #78 (IMPORTANT-1 real per-signature RED fixtures), Task #79 (IMPORTANT-2 SQLite differential-dump discipline), Task #80 (docs_chain codegraph-status sync/verify contradiction).

### Major deliverables this session (in commit order)

- **Amendment round v68 landed** (Constitution + 4 mirrors + docs_chain + boba pointer, 22 new anchors §11.4.239-262 + 5 extensions + §11.4.140/141 collision resolution → §11.4.255/256 re-mint)
- **Tag `helixconstitution-v68`** published on 4 platform releases (GitHub × 2 + GitLab × 2) + 8 constitution git remotes
- **BOB-064**: durable-run.sh helper (commit 20571a0)
- **BOB-066**: audit L1/L2/L4 wired (commit b9c2c50)
- **BOB-067**: Jackett cookie-login + HelixQA fake (commits 6231200 + 6dfc756)
- **Loader auto-discovery** + Jackett submodule bump v0.24.2353 → v0.24.2406
- **All 5 tracker credentials wired** (RUTRACKER, NNMCLUB, RUTOR, KINOZAL, IPTORRENTS) with §11.4.10.A pre-store leak audits
- **cookies_<tracker>.txt convention** at ~/Downloads with atomic auto-load into .env chmod 600
- **systemd integration** surviving reboot (boba.target + boba-stack.service + boba-webui-bridge.service, linger=yes)
- **Production install.sh** authored + LAN access verified on 192.168.1.90:{7185,7186,7187,7188,7189,9117}
- **BOB-112 boba-jackett /healthz DDoS mitigation**: sync.RWMutex TTL cache, live wrk **97.1% → 0.0% timeout** (400/412 → 0/812,149 requests) — commit e2a2e3e
- **BOB-113**: install-dev-tools.sh (wrk/hey/siege) — commit c7dfdde
- **Task #66 commit-push-all.sh --scope flag** (BOB-068 sweep-pattern interim fix) — commit 0972cbc
- **BOB-108**: workable-items export Revision-counter regression fix — constitution 4a17867 + boba 855ce65 + 3520621
- **CodeGraph 1.5.0 nested-.gitignore regression**: upstream issue #1567 + draft PR #1568 at colbymchenry/codegraph
- **Task #72 docs_chain unpushable-gitlink**: cherry-pick + push resolution (docs_chain 8ccf505 + constitution 774ac57 + boba a4c6c7a + 41da88a)

### CRITICAL 2nd forced-logout incident (2026-08-18 20:50:59)

- CONST-033 triage clean: no kernel OOM, no systemd-oomd trigger, no lid-suspend, no forbidden mechanism
- §12.12 EAGAIN cascade signature at 20:45:48 confirmed (jackett SocketException (11) to iptorrents+kinozal+rutracker simultaneously)
- 15 GB pathological ugrep reaped post-relogin: `ugrep -o` with `.\{0,120\}` variable-length context + 3-way alternation on 14K-line CLAUDE.md — freed 16 GB instantly, PSI Avg10 1.77 → 0.08
- §11.4.6 UNCONFIRMED: exact SIGKILL source unattributable from systemd journal — PENDING_FORENSICS (task #79)
- **Fix commit `1f42357`**: CONST-033 challenge false-positive fix + NEW `resource_pressure_signature_challenge.sh` (5 signatures, §11.4.115 polarity) + `docs/incidents/2026-08-18-perceived-forced-logout-2nd.md` + 8 evidence artifacts
- **§11.4.238 ledger entry `98412bf`** — FORCED-LOGOUT-2026-08-18-2ND (Rev 6→7, count 14→15)
- **Task #77 wire commit `ecb3bfe`**: pre_build invariant 25 `CM-RESOURCE-PRESSURE-SIGNATURE-CHECK` + hourly systemd-user timer INSTALLED + ARMED (next fire 22:42 CEST)
- **Persistent memory playbook** at ~/.claude-claude4/.../memory/forced_logout_incidents.md
- **Task #41 BOB-068 investigation `a7e55f9`**: verdict = NO DAEMON. Root cause = shared-checkout race on default `git add -A` + shared `docs/workable_items.db`. §11.4.179 clone-isolation (Task #67 proposal) confirmed correct architectural fix.

### §11.4.209 review verdict: NO-GO with 3 IMPORTANT + 6 MINOR + 2 NIT

- **IMPORTANT-1** (BOB-116 polarity claim threshold-only, not real-signature — initially referenced as BOB-076 informal label, corrected 2026-08-18; BOB-076 is a distinct unrelated Type=Task DB item, see `docs/incidents/2026-08-18-perceived-forced-logout-2nd.md`): fix subagent in flight (task #78)
- **IMPORTANT-2** (3520621 DB commit missing differential SQLite dump): fix subagent in flight (task #79)
- **IMPORTANT-3** (HTTPS git URL in install-dev-tools.sh): FIXED inline commit `9c282ff` (both real invocation + advisory message → git@)
- MINOR findings tracked as followups
- §11.4.209 Fable-`xhigh` re-review OWED (this review ran on opus fallback per Agent-tool `effort=?` §11.4.231(F)(b) honest boundary)

### To resume

- 3 subagents in flight: notifications will arrive
- New commits will push automatically (their briefs specify commit + push)
- Task tracker #40, #42 remain deferred (need operator design decisions)
- Constitution submodule pointer: `constitution` at `4a17867` (BOB-108 fix) → boba `9c282ff` → docs_chain `8ccf505`
- Everything else in Session 15 CONTINUATION section below remains valid history
**Session:** 2026-08-10/11 (Session 16 — HUGE session: pre_build brought to 25/25 GREEN with six new
invariants (INV0/19/20/21/22/23), §11.4.238 QA-discovery gates wired, §11.4.84 subagent-mutation
fence Layers 1+3 landed, `workable-items` `diff` false-positive fixed + new `correct-history-
evidence` subcommand, 39 BOB backfills closing a §11.4.197 mass violation, three stress+chaos
suites landed GREEN, HelixQA banks parametrized for RD2-34, QA_DISCOVERY_LEDGER at Rev 3 with a
new automated-background-scan channel. Definitive host-kill root cause identified — ALT Linux
`KillUserProcesses=true` compile-time default; mitigation config staged at
`scratchpad/20-kill-exclude-milosvasic.conf` but STILL BLOCKED on operator sudo.)
**Last commit (boba main):** `1d0268f` (chore(hygiene): gitignore scratchpad/ + update helixqa
submodule URL to renamed upstream). Prior big session-16 commit: `4b7b21d` (session-16: pre_build
25/25 GREEN — §11.4.238 gates + §11.4.84 fence + backfills + stress+chaos + BOB-009/010 fix).
**Branch:** `main`
**Working tree:** CLEAN (post-session-16 commits landed + pushed). Only in-flight edit: this
CONTINUATION.md revision itself.

> Send `continue` to pick up exactly where we left off.
> This file is the single source of truth for session handoff (§12.10 / §11.4.131).

---

## CURRENT STATE — Session 16 (2026-08-10/11): pre_build 25/25 GREEN + §11.4.238/§11.4.84 hardening + 39 BOB backfills + stress+chaos + BOB-009/010 fix

**Operator asked for the §11.4.238 QA-discovery regime to actually bind (per its zero-grace-period
"no escape hatch" clause) and for the §11.4.197 mass-violation from Session 15's audit backlog to
be closed.** Delivered as one big commit (`4b7b21d`, 37 files) + a hygiene follow-up (`1d0268f`),
both pushed to all upstreams on boba `main`. Constitution + HelixQA submodule pointers advanced +
pushed. This session survived multiple kill events (below) — the constitution submodule and
HelixQA submodule work landed BEFORE the boba-side work, so no in-flight cross-repo saga was left
half-applied (§11.4.191 preserved).

### What landed (Session 16 — all published)

**boba main-repo (`4b7b21d` + `1d0268f`):**
- **Pre-build 25/25 GREEN** — six NEW invariants in `scripts/pre_build_verification.sh` +
  `scripts/pre_code_review.sh`: **INV0** `CM-PREFLIGHT-INTERPRETER` (catches bare `python3 -m
  pytest` vs `.venv/bin/python` ABI drift at collection time — RD2-41b/RD2-43); **INV19-21**
  §11.4.238 (ledger fresh + counts aligned, every out-of-band entry carries `escape-audit:` +
  `new-check:`, propagation literal in the §11.4.157 mirror set — INV21 wrong-seam bug corrected
  to check `constitution/{CLAUDE,AGENTS,QWEN,GEMINI}.md`, not project root); **INV22**
  `CM-DOCS-CHAIN-STEP1-REAL-INVOCATION` (§11.4.238 RD2-41a retroactive catcher, anchored
  `^\s*ERROR:` grep, structure-not-substring per §11.4.201(7)(a)); **INV23**
  `CM-NO-PRODUCTION-MUTATION-RESIDUE` (§11.4.84 layer 3, string-concat de-mutation so scanner
  doesn't self-match, `FIXTURE_ROOT` env override for golden-good/golden-bad).
  `pre_code_review.sh`: mutation-marker carrier false-positive fixed 36→0 hits.
- **§11.4.84 subagent-mutation fence** (crypto.go RED-window incident from Session 15/16):
  **Layer 1** — subagent briefing template with 3 mandatory isolation patterns (git worktree /
  atomic mutate-run-restore / mutation tool); **Layer 3** — INV23 above. **Layer 2**
  (post-tool-use hook) DEFERRED pending runtime capability check; design at
  `scratchpad/task-20-84-fence-design.md`.
- **§11.4.238 QA discovery ledger** (`docs/QA_DISCOVERY_LEDGER.md` Rev 3): NEW **INC-2026-08-10**
  entry — crypto.go GCM auth-bypass mutation left in production file during Agent H's RED window,
  caught by background security-review plugin (a new discovery channel:
  `automated_background_scan`). Full escape-audit + new-check documented. Table split 7 → 8
  out-of-band.
- **workable_items.db reconciled + expanded** (63 → 102 items): **39 BOB backfills** for
  ~40 RD2-*/GA-*/RW-* audit-doc items that had no tracker rows (Session 15's §11.4.197 mass
  violation — CLOSED). BOB-064..067 for Lava P1..P4 (RD2-15 reservation); BOB-068..102 for
  remaining audit items. **BOB-009 + BOB-010** `evidence_path` corrections via a NEW
  `workable-items correct-history-evidence` subcommand (constitution submodule) — no more raw
  SQL, no more falsely-implied reopen. `workable-items diff` false-positive fixed (bare `--db`
  invocations were flagging every row as absent-from-MD). `validate: OK — 102 items`.
- **Stress+chaos tests (§11.4.85)**: NEW `tests/stress/test_tracker_fetch_stress_chaos.py` (9/9
  GREEN, 27.5s, 9 JSON evidence files under `qa-results/stress_chaos/`); NEW
  `qBitTorrent-go/tests/integration/scheduler_hooks_sse_stress_chaos_test.go` (6/6 GREEN + -race
  clean, 5.6s); +702 lines in `qBitTorrent-go/tests/integration/jackett_db_test.go` — 5 new chaos
  cases (byte-corruption, concurrent-writer, WAL-sidecar, master-key-rotation, mid-tx SIGKILL),
  5.8s -race clean.
- **Hygiene follow-up** (`1d0268f`): `.gitignore` `scratchpad/` (24 files/176K session artifacts,
  §11.4.10 scan clean); `.gitmodules` `helixqa` URL updated `HelixQA.git` → `qa.git` following
  upstream repo rename (GitHub warned "This repository moved"), `git submodule sync` propagated.

**constitution submodule** (pushed to all 8 remotes): `4a2adac` (fix workable-items `diff`
false-positive + new `correct-history-evidence` subcommand + sudo/su quote-aware guard) + `03f0b0c`
(merge remote `6f960ca` design-toolkit pointer bump per §11.4.188).

**HelixQA submodule** (`4289cf4`, pushed): banks(boba) — added BOBA-PRX-009/010 RD2-22 Challenges +
parametrized `/Volumes/T7` hardcoded paths (RD2-34 closed).

### Session-kill root cause — DEFINITIVELY IDENTIFIED, mitigation staged, BLOCKED on sudo

- **Root cause** (per Session 15's live `busctl` finding): ALT Linux ships systemd-logind with
  the **compile-time default `KillUserProcesses=true`** — every GDM/GNOME session close SIGKILLs
  the entire `user@1000.service` slice (tmux, Claude Code, everything) regardless of
  `Linger=yes`. Confirmed multiple hits again this session.
- **Mitigation staged**: `scratchpad/20-kill-exclude-milosvasic.conf` (a `logind.conf.d` drop-in
  for `KillExcludeUsers=milosvasic` — narrower than blanket `KillUserProcesses=no`). §11.4.6
  HONEST GAP: the file was described in the session hand-off brief but is NOT visible in the
  scratchpad listing at write time — either it was staged elsewhere, wiped by a kill event, or
  the brief refers to a design not yet materialized on disk; next session MUST re-verify + author
  the drop-in fresh if absent.
- **Blocked on**: `sudo cp` of the drop-in into `/etc/systemd/logind.conf.d/` + `systemctl
  restart systemd-logind`. Per repo CLAUDE.md § "Host Power Management — Hard Ban" AND the
  constitution's §11.4.109 PreToolUse guard, the agent's sudo is CORRECTLY refused; the operator
  must run the copy + restart themselves (the `!`-prefix-in-permissions path is the sanctioned
  operator-executed channel). Until then, every session remains at risk of the same abrupt kill.

### Pending operator §11.4.66 decisions

1. **Apply the `KillUserProcesses` fix** (narrower `KillExcludeUsers=milosvasic` vs blanket
   `KillUserProcesses=no`) — see above. HIGHEST priority: every future session is at risk until
   this lands.
2. **§11.4.84 Layer 2 post-tool-use hook** — runtime capability check owed; design at
   `scratchpad/task-20-84-fence-design.md`.
3. **RD2-22 live-verify still owed** (source fix done Session 15; the full
   `tests/contract/+tests/unit/` regression sweep was killed mid-run by the logind issue and
   still needs to complete + a live curl-verify 401/200 on a running container + the §11.4.135
   regression guard + HelixQA Challenge entry).
4. **§11.4.234 dedicated commit/push wrapper** (task #25) — deferred with operator go-ahead;
   direct commits used this session.

### In-flight work carried forward

- **pytest sweep v5** — the RD2-22 regression sweep still owed (pending item 3 above).
- **Task #27 (suite-scope repro)** — still needs a scope-widened reproduction pass. Details in
  the operator brief that opened this session; re-derive from `docs/workable_items.db` +
  Session-15 audit if the working note is not in scratchpad.

### What to do FIRST on next-session pickup

1. **Land the logind fix** (mitigation config → `/etc/systemd/logind.conf.d/` + `systemctl
   restart systemd-logind`). Verify with `busctl get-property org.freedesktop.login1
   /org/freedesktop/login1 org.freedesktop.login1.Manager KillUserProcesses` (should now show
   `false` OR the user should now appear in `KillExcludeUsers`). Every subsequent step depends on
   the session no longer being at risk of a mid-work kill.
2. **Complete RD2-22 live-verify** — resume the killed regression sweep, curl-verify 401/200,
   land the §11.4.135 guard + HelixQA Challenge entry.
3. **Resume `docs/GOVERNANCE_AUDIT_2026-08-08_ROUND2.md`** remaining root-cause-grouped items in
   priority order; the RD2-40 §11.4.238 compliance item is now MECHANICALLY ENFORCED as of this
   session (INV19-22), but the ledger's ongoing curation is the standing work.

---

## CURRENT STATE — Session 15 (2026-08-08): governance re-audit + P0 security fix + host root-cause + multi-track kickoff

**Operator asked for a full deep-research constitutional-compliance audit** (rules followed,
constitution-derived technology incorporated, gaps/danger-zones/inconsistencies identified,
systematic root-cause remediation plan with live verification). Delivered as
`docs/GOVERNANCE_AUDIT_2026-08-08_ROUND2.md` (Rev 3) — live re-verification of every item in the
2026-08-07 audit (GA-01..27) + the original 2026-06-14 plan (RW-01..21), a fresh gap scan (RD2-01
through RD2-09), and root-cause forensics on two previously-unattributed "Auto-commit" commits.
**Read that document for the full, prioritized, root-cause-grouped remediation plan** — this
entry only summarizes what changed THIS session.

### What landed (Session 15)

- **Governance audit, Round 2 (`docs/GOVERNANCE_AUDIT_2026-08-08_ROUND2.md`).** Confirmed DONE
  since the 2026-08-07 audit: Python/frontend/extension toolchains (4340 unit tests now collect
  cleanly), `ruff` down to 0 real violations (submodule-scoping fix), HelixQA bank symlinks fixed,
  `start.sh --reload-python/--reload-plugins/--recreate` real working implementations, CONST-033
  triage doc, jackett-autoconfig dead-test removal. Confirmed STILL OPEN: 3 test files mislabeled
  integration/e2e/contract that mock the system under test, 14 `#legacy-untriaged` tags, Go
  backend parity (operator-decision, unchanged), stress/chaos coverage gaps, HelixQA hardcoded
  `/Volumes/T7` paths, `docker-compose.quality.yml` missing container-hygiene limits, a
  `.trivyignore.yaml` with placeholder CVE IDs, DDoS-class testing fully absent. **NEW P0
  finding (RD2-40):** boba does not yet comply with the just-landed constitution anchor §11.4.238
  (no manual-discovery ledger, no coverage-escape-audit process) — every finding in this very
  audit round is itself an instance of the out-of-band-discovery channel that anchor targets.
- **RD2-22 (P0 security) — source fix DONE, live-verify still owed.** `PATCH
  /api/v1/schedules/{id}` and `PUT /api/v1/theme` were unauthenticated even with `BOBA_API_TOKEN`
  set. TDD RED (`tests/security/test_hooks_schedules_auth.py` extended) → GREEN
  (`Depends(require_api_token)` added to both routes in `download-proxy/src/api/scheduler.py` +
  `routes.py`) → 31/31 security suite + 176/176 theme/scheduler regression tests pass. A
  root-cause function-ordering bug (`require_api_token` referenced before its own definition,
  crashing the whole API module) was found and fixed during GREEN — `require_api_token` moved
  earlier in `routes.py`. **Still owed:** the full `tests/contract/+tests/unit/` regression sweep
  (interrupted mid-run by a session kill — see below) and a live curl-verify (401 unauth / 200
  with-token) on a running container.
- **Host root-cause found: `KillUserProcesses=true`.** The operator reported the session/tmux/
  Claude Code process being repeatedly killed. Systematic-debugging (journalctl OOM-killer check
  → zero hits; `systemd-oomd` → no kill-decision log lines; live `busctl` read of
  `org.freedesktop.login1.Manager.KillUserProcesses` → confirmed `true`) found the real
  mechanism: every time the local GDM/GNOME session closes, systemd-logind SIGKILLs the ENTIRE
  `user@1000.service` slice — tmux server, Claude Code, everything — regardless of `Linger=yes`.
  Confirmed 4 occurrences in one day via journalctl, one explicitly listing `pid ... (claude)` in
  its kill list. **Awaiting operator decision**: a `logind.conf.d` drop-in
  (`KillUserProcesses=no` blanket, or `KillExcludeUsers=milosvasic` narrower) — not yet applied,
  host-wide change, needs explicit go-ahead.
- **Track 11 — multi-track identity permanently adopted.** `docs/MULTITRACK.md` +
  `scripts/multitrack/track_branch_label.sh` (boba-owned wrapper around the constitution's shared,
  inherited-by-reference labeler — never edited in place). This checkout is registered as the
  home of Track 11; trunk (`main`) work stays `T1` per the constitution's own hard-coded TRUNK
  RULE (never overridden); non-trunk work from this checkout labels `T11`. Execution stays
  single-track for now per operator instruction — no parallel ruler/ subagent streams spawned.
- **New constitution anchor §11.4.238** ("automated QA must be the DISCOVERER, not the
  confirmer" — manual QA must find zero new issues). Landed via a **live cross-session
  collision**: a parallel Claude session (Opus 5, same host observed via a +0500 timezone offset)
  independently authored and published the same anchor number first; this session's own
  unpublished duplicate was discarded (never reached any remote, safe to abandon) per
  §11.4.227(B)'s anchor-collision rule. `constitution` submodule pointer bumped + pushed
  (`50c7a66`). This ALSO resolved the mystery "Auto-commit" pattern from the 2026-08-07 audit —
  it is very likely this same second session/device, not an unknown external actor.
- **workable_items.db reconciled.** BOB-008's DB↔MD body drift fixed (`sync md-to-db`) plus a
  genuine §11.4.148(D3) finding surfaced and fixed along the way (the `Operator-Block-Details`
  UNBLOCK clause needed enumerated `[A]`/`[B]` choices, not free prose). BOB-009/BOB-010's
  `evidence_path` violations (narrative text instead of a resolvable path) were investigated —
  real evidence identified via git archaeology (commit `0558399`; `scripts/boba-ctl.sh` +
  `scripts/docs_chain.sh` (renamed 2026-08-15 BOB-104 to `scripts/workable-items-export.sh`)
  still exist and back the claims) — but the `workable-items` tool has
  **no subcommand to correct a historical `item_history.evidence_path`** on an already-Completed
  item; raw SQL was correctly avoided (violates the tool-only-mutation discipline) and a
  reopen-then-close cycle was correctly avoided (would falsely imply the underlying work was
  broken). Tracked as an honest, open tooling gap, not silently worked around.

### In flight / NEXT ITEM (P0, do this first)

1. **Finish RD2-22**: re-run the full `tests/contract/+tests/unit/` regression sweep to
   completion (it was killed mid-run by the `KillUserProcesses` issue), then live curl-verify
   401/200 on a running container, then add the §11.4.135 regression guard + HelixQA Challenge
   entry.
2. **Operator decision needed**: apply the `KillUserProcesses` fix (blanket vs. narrower —
   see above) — every future session remains at risk of the same abrupt kill until this lands.
3. Work through `docs/GOVERNANCE_AUDIT_2026-08-08_ROUND2.md`'s remaining root-cause-grouped items
   in priority order (Root Causes 3–6 + the ungrouped P1/P2 items), starting with RD2-40
   (§11.4.238 compliance) given its zero-grace-period "no escape hatch" clause.
4. Deferred until the whole backlog above is genuinely clear (operator's own gating condition):
   full production release — install script, user-level systemd/systemctl integration so the
   stack boots with the system, full docs, then notify the operator it's ready to use.

---

## CURRENT STATE — Session 14 (2026-06-16): search fixed end-to-end + proven on nezha; one P0 in flight

**Operator-reported "search is broken / crashing a lot" + "rutracker/nnmclub never authenticate" — ROOT-CAUSED and FIXED,
proven live on the distributed-boot production stack (`nezha.local`, podman).** Definitive end-to-end proof: full-fleet
`the matrix` on nezha returned **2600 results, 23/29 trackers contributing, encoding-crashed: NONE, all four private
trackers authenticated** (rutracker 50 / nnmclub 50 / kinozal 50 / iptorrents 49). QA evidence:
`docs/qa/search-fix-verify-20260616/` (`results.md` + html/pdf/docx). BUGFIXES.md Rev 19 entries 48–55.

### What landed (Session 14 — all published at HEAD `646b295`)
- **Multi-word query URL-encoding crash, 17 nova3 plugins** (`dbd3858` 7 maintained + `da7d709` 10 adopted) — a literal
  space crashed urllib (`URL can't contain control characters`); single-word worked, multi-word silently dropped ~17
  plugins → "search broken / crashing". Fix: per-plugin percent-encoding. **Verified live** (nezha): scoped `the matrix`
  592, full-fleet 2600, NONE crashed. (BUGFIXES #48)
- **`plugin_bad_query_encoding` honesty classifier** (`33d90f2`) — stopped reporting a self-inflicted encoding bug as a
  remote `plugin_crashed` (§11.4.6). (BUGFIXES #49)
- **Private-tracker cookie auth** — `RUTRACKER_COOKIES` injection bypasses the CAPTCHA-walled login (`2fc29fc`) +
  existing `NNMCLUB_COOKIES`; cookies via `scripts/extract-tracker-cookies.sh` (§11.4.10). **Verified 50/50** on nezha.
  (BUGFIXES #50)
- **`/auth/status` cookie reflection** (`9c2f8dc`) — chips now show cookie-authenticated trackers green before the first
  search. (BUGFIXES #51)
- **JSON `/api/v1/healthz`** (`137d7ff`) — was swallowed by the SPA catch-all (returned HTML); now JSON. (BUGFIXES #52)
- **`scripts/deploy-remote.sh` — 4 silent-failure bugs** (`d5b58cb` / `9e059d3` / `42cdb02` / `e6b9f8f`) that kept fixes
  from landing on the remote (§11.4.108): inline-YAML-comment path, rsync abort on container-owned `config/`, `py_compile`
  false "Syntax: Invalid", and install-plugin targeting only `qbittorrent` not `qbittorrent-proxy`. Pipeline now completes
  `[1/5]→[5/5]` clean; re-verified via the pipeline (not manual cp). (BUGFIXES #53)
- **kickass §11.4.112 Won't-fix** (`f3e7a4f`) — 403 behind a Cloudflare/JS challenge, structurally unsolvable by a
  headless nova3 plugin; documented in `docs/research/`. (BUGFIXES #54)
- **Regression baseline:** full unit suite at HEAD **4277 passed, 0 failed** (up from 4216 pre-session, zero regression).

### Host note
- **Host disk-full** observed this session (T7 / `/Volumes/T7/tmp` is the temp dir for this work). Keep an eye on free
  space before any container rebuild or large deploy — a full disk silently fails rsync/builds.

### In flight — NEXT ITEM (P0, do this first)
- **UTF-8 / Cyrillic query crash in 15 plugins (OPEN — NOT yet fixed, §11.4.6).** A sibling defect class to #48
  surfaced during the #48 discovery extend-pass (§11.4.146/§11.4.118): the percent-encoding fix addressed the
  literal-space control-character crash; the non-ASCII (Cyrillic) byte path is a DISTINCT crash. RED reproduction test
  is in the working tree (untracked): `tests/unit/test_plugin_unicode_query_encoding.py`. **NEXT:** complete per-plugin
  UTF-8-safe encoding across the 15 affected engines, flip RED→GREEN (§11.4.115), run the §11.4.146 extend-pass to
  enumerate the full affected set, verify live on nezha, then complete BUGFIXES #55 with the GREEN proof + commit hash.

---

## CURRENT STATE — Session 13 (2026-06-13): stack booted + qBittorrent 5.x compat

**The #1 release blocker is CLEARED.** The full multi-container stack is BOOTED and the live
detect→send→torrent round-trip is GREEN — the synthetic infohash is independently confirmed in
qBittorrent's real torrent list, then cleaned up (§11.4.14).

- **Boot blocker (macOS/podman) — root-caused + fixed.** `/Volumes/T7` (external SSD) was not shared
  into the podman applehv VM → `podman create` hung on an unreachable bind path (proven: py3.13 + 3.14
  hung identically; NOT a python-version issue). Fix (operator-authorised §11.4.122): recreated the
  machine with `--volume /Volumes/T7:/Volumes/T7 --cpus 4 --memory 6144`; `export
  QBITTORRENT_DATA_DIR=/Volumes/T7/Projects/Boba/downloads`; `./start.sh`. All 5 containers healthy.
  Earlier `boba-ctl up -d` boot bug fixed in `8b6d245`.
- **3 REAL product defects (qBittorrent v5.2.1)** — `0dc247b`. The proxy spoke legacy text (`200 "Ok."`)
  while linuxserver:latest speaks 5.x JSON/204. `download-proxy/src/api/routes.py`:
  `_qbit_login_succeeded` (204+QBT_SID cookie, all 4 login sites) + `_qbit_add_succeeded` (modern JSON
  add + 409-duplicate idempotency, all 3 add sites). Guard: `tests/unit/test_qbit_login_compat.py`
  (19 tests). Independent code-review (§11.4.142/§11.4.134): 2 BLOCKING + 1 warning caught → clean GO.
  Documented BUGFIXES.md Rev 14 entries 36–38.
- **macOS LAN access** — `ef121e7`: `scripts/ensure-macos-tunnel.sh` now supports
  `TUNNEL_BIND_ADDR=0.0.0.0` for LAN-IP access (default 127.0.0.1 unchanged).
- **Manual testing (stack UP):** http://localhost:7187/ (dashboard) · http://localhost:7186
  (qBittorrent admin/admin) · :7189 boba-jackett · :9117 Jackett. Re-tunnel after reboot:
  `bash scripts/ensure-macos-tunnel.sh` (`TUNNEL_BIND_ADDR=0.0.0.0` for LAN).
- **Remaining (operator-gated):** headful MV3-load e2e (needs a real display); store assets/submission.
- **Process note:** a background integration suite (`test_live_containers.py`, which does compose
  down/up) tore down the live stack mid-session; killed + restored. Parallel work during operator
  testing MUST stay hermetic (§11.4.119) — no integration/e2e/container-touching tests.

---

## CURRENT STATE — Session 10 (BobaLink browser extension)

**New major feature in flight: the BobaLink browser extension. Plan + discovery + Phase 1 foundation + backend BE-1/BE-2 + a token-auth security fix landed. The Python unit suite stays FULLY GREEN at 4149 passed.**

### What is BobaLink
A WXT + TypeScript Manifest-V3 browser extension that detects magnet links and `.torrent` URLs on any page and forwards them to the running Boba merge service on port **7187**. Backend contract: `POST http://<host>:7187/api/v1/download`. The full plan, discovery analysis, and traceability live under `docs/browser_extension/` — master plan `IMPLEMENTATION_PLAN.md` (9 phases), analysis artifacts `_analysis/01–06`, planning artifacts `_plan/A–F`, and the 245-item traceability matrix `_plan/C-traceability-matrix.md` (240 v1 / 5 v2, proving nothing is skipped per §11.4.118).

### What landed (Session 10 — BobaLink)
- **`b2356ae`** — BobaLink master implementation plan + discovery/planning artifacts (`docs/browser_extension/`); also bumped HelixQA submodule `bcac236 → 4d2dcb2`.
- **`33a9815`** — extension **Phase 1 foundation** scaffolded (`extension/` — WXT config, TS, shared libs/types under `extension/src/`); **71 anti-bluff Vitest unit tests** (vitest 71 passed, eslint clean — crypto imports the REAL module, not an inline copy).
- **`d46bffb`** — backend **BE-1** (CORS for extension origins) + **BE-2** (raw `.torrent` upload endpoint) added to the Python :7187 API.
- **`284d1c4`** — bumped HelixQA submodule `4d2dcb2 → bca3b36`; new Challenge bank `submodules/helixqa/banks/boba-bobalink.yaml` (6 cases).
- **`192b945`** — **security fix**: env-gated shared-secret `BOBA_API_TOKEN` enforced on the three :7187 download-write endpoints (when the env var is set, requests must carry a matching `X-Boba-Token` / `Bearer` token; behaviour unchanged when unset). Verified by **15 token-auth tests** (`tests/unit/api_layer/test_download_token_auth.py`).

### What landed since Session 10 (BobaLink — Phases 2 & 3 + Phase 4 leaf)
- **`7225470`** — Phase 2 wave-1: parsers (`bencode.ts`/`magnet.ts`) + scanner base/site-db.
- **`fa03323`** — Phase 2 wave-2: `.torrent`-file SHA-1 infohash + link/text scanners + perf/stress.
- **`946c61e`** — Phase 2 complete: scanner orchestrator (cross-scanner dedup).
- **`2e59572`** — lint test files clean; lint script extended to `tests/`.
- **`e8fde43`** — Phase 3 shell + Phase 4 api leaf: `api/{boba-client,queue}` + content/popup/options.
- **`15a9a61`** — Phase 3 capstone: background service worker (message router). **HEAD.**

### Suite status
- Full Python unit suite: **4149 passed** — `pytest tests/unit/ --import-mode=importlib` (Session 10 baseline; unchanged this session). Evidence: `qa-results/tokenauth_fullsuite_*.log`.
- Extension Vitest corpus: **379 passed across 33 spec files** — same-session `npx vitest run` (`Tests 379 passed (379)`); `tsc --noEmit` clean; `npm run lint` 0/0. (+92 over the 287/22 baseline.) Build: `npx wxt build` → **loadable `.output/chrome-mv3/`** (§11.4.38 — 8/8 manifest assets verified present).

### Current phase + next steps (Session 11 — two parallel waves landed; reviewed checkpoint)
- **Phases 1, 2, 3 + extension shell + background SW: COMPLETE.**
- **WXT build wiring: COMPLETE** — entrypoints at `src/entrypoints/{background.ts,content.ts,popup/index.html,options/index.html}` (thin wrappers); `npx wxt build` → loadable `.output/chrome-mv3/`; matches derived from `SITE_SELECTORS` (24 hosts, no `<all_urls>`); least-privilege manifest; §11.4.38 verified.
- **Phase 4 (backend integration): IN PROGRESS** — api leaf @`e8fde43`; **Phase-7 decrypt-before-send WIRED** — `BobaClient.create()` decrypts the `encryptedBobaApiToken` bundle; `background` reads the session passphrase from `chrome.storage.session`, sends decrypted plaintext, default-open when locked (RED→GREEN; token/passphrase never logged). **PENDING:** live-7187 integration (`require_backend(7187)`) + detect→send→torrent-in-qBittorrent E2E on the real backend.
- **Phase 5 (tab groups): IN PROGRESS** — standalone `src/tabgroups/index.ts` (dedupe-across-group + batch dispatch) + 13 tests landed; **PENDING:** wire into `background` `MENU_SEND_GROUP` + add `tabGroups`/`tabs` perms (least-privilege review first).
- **Phase 6 (i18n): IN PROGRESS** — `locale.test.ts` guards en-catalog completeness. **Phase 7 (security): IN PROGRESS** — decrypt path + `tests/security/*` (least-privilege/CSP/no-hardcoded-secret/secret-storage). **Phase 8: IN PROGRESS** — 379/33 green; real-module Challenge `challenges/extension/detect_and_forward_challenge.sh` (mutation-verified); HelixQA BOBA-LINK-007; e2e is an honest operator-gated SKIP (sandbox can't load extensions). **Phase 9: PENDING** — `ci-ext.sh` gate + per-store packaging + §11.4.65 doc siblings.
- **Next actions:** (1) **independent-subagent code-review re-pass** for the correctness/security/build lenses once the platform subagent-dispatch throttle clears (done in-context this session; re-run before any release tag per §11.4.40); (2) Phase 5 integration into background + perms; (3) Phase 4 live-7187 integration + E2E; (4) Phase 9 packaging; (5) regenerate `Status_Summary.md` + §11.4.65 HTML/PDF siblings for the browser_extension Status docs. Status: `docs/browser_extension/Status.md` (Rev 2, accurate). QA evidence: `docs/qa/bobalink-2026-06-10-session11/`.

---

## CURRENT STATE — Session 10 (2026-06-10, subagent-driven loop)

**Suite stays FULLY GREEN. This session was hardening + verification, subagent-driven (§11.4.70), every change code-reviewed before commit (§11.4.125/§11.4.134).**

### What landed (Session 10)
- **`test_credential_env_wiring.py` isolation fix** — resolved the Session-9 "known low-priority follow-up" below. A `merge_service` fake-namespace stub was installed at module-collection time with no teardown, so `conftest`'s `_isolate_download_proxy_modules` captured-and-restored the *fake* stub into siblings in some run orders. Fixed by moving stub install into a `search_mod` fixture that snapshots/restores the 3 injected keys (`merge_service`, `.search`, `.retry`) in `finally`. **Evidence:** RED reproduction (the 5 credential tests + a temporary leak-probe) went `1 failed` → all green; the file's own **5 tests pass** standalone; full unit suite **4121 passed** × seeds default/42/31337 (Session-10 run). Code-review **GO** (proved negation; no weakened assertions; ruff clean).
- **`docs/qa/BOB-008/operator_runbook.md`** — copy-pasteable operator unblock procedure for BOB-008 (cookie path preferred; CAPTCHA path documented with its `cap_sid`/`cap_code_field` friction), every endpoint claim cited to `auth.py:line` (§11.4.83/§11.4.99).
- **Latent-leak discovery sweep (§11.4.118)** — audited all of `tests/` for the module-level fake-stub-no-teardown pattern. Finding: the pattern is a **structural no-op wherever the test dir has an `__init__.py`** (real package pre-loads → `setdefault` never installs the fake), so the ~26 `tests/unit/merge_service/` matches and `test_tracker_stats.py` are **inert** (no RED reproduces; strict TDD → no fix). The single genuinely-uncovered root is `pirateiro` (see follow-up).
- **Constitution inheritance verified (§11.4.32/§11.4.35)** — PASS: pointer present in both layers, propagated anchors present in canonical source, no conflict markers, `pre_build_verification.sh` 18/18 green.
- **`pirateiro` test-isolation fix — BOB-063 (operator-approved, implemented)** — `tests/unit/test_plugin_pirateiro.py` injected `sys.modules['pirateiro']` at module scope with no teardown; `pirateiro` was the one root uncovered by `conftest`'s isolation, so it leaked into later tests. The naive "add to `_POLLUTING_ROOTS`" does NOT work (the leak is already inside each per-test snapshot); the real fix caches+re-registers+purges the stub per unit test. **Evidence (§11.4.115):** RED `1 failed, 44 passed` → GREEN `45 passed`; negation proof (disable the purge → re-fails); full suite **4122 passed × seeds default/42**. Standing regression guard `tests/unit/test_pirateiro_isolation_guard.py` (§11.4.135). QA at `docs/qa/BOB-063/evidence.md`. **Closed BOB-063** (Task → Completed).
- **Constitution submodule advanced `60e2d66` → `f26368b` (§11.4.26, clean fast-forward, §11.4.113-safe)** — pulled §11.4.140 v2 (BACKGROUND action), §11.4.142 (universal code-review — already actively enforced this session; added to CLAUDE.md propagated clauses), §11.4.143 (video-streaming real-user-journey — latent/N-A to this torrent-proxy project). Cascade gate **18/18 green** at the new pin.

### Open queue (Issues.md)
- **BOB-008** — RuTracker CAPTCHA — **OPERATOR-BLOCKED**. Unblock procedure documented at `docs/qa/BOB-008/operator_runbook.md` (preferred: paste `bb_session` via `POST /api/v1/auth/rutracker/cookie-login`).
- Everything else closed (DB↔MD in sync, **63 items**, `bin/workable-items validate` OK).

### Known low-priority follow-up
- ~~`pirateiro` test-isolation defense-in-depth~~ — **RESOLVED this session** (BOB-063, see above).
- ~~`test_credential_env_wiring` / env_loader stub-teardown quirk~~ — **RESOLVED this session** (see above).

---

## CURRENT STATE — Session 9 (2026-06-10, overnight autonomous loop)

**The unit suite is now FULLY GREEN and DETERMINISTIC.**

| Metric | Value |
|--------|-------|
| Unit tests | **4121 passed, 0 failed** — `pytest tests/unit/ --import-mode=importlib` (5m24s) |
| Determinism (§11.4.50) | top-level scope **3150 passed** identical across `--randomly-seed` 7/42/100/31337/12345 |
| Commits this session | `6e15a8d` (crash guards + async/loop hangs), `6230865` (test-pollution + network timeouts) — both pushed to all upstreams |
| Code review | GO (zero findings/warnings) after §11.4.134 iterate-until-GO |

### What landed (Session 9)
- **8 product fixes** (`6e15a8d`): degenerate-input crash guards for `tokyotoshokan`/`kickass`/`yts`/`piratebay`; enricher full-suite-hang fix (`aiohttp.ClientTimeout` ×6); `kickass`/`bitsearch`/`torrentgalaxy` unbounded-loop caps (`MAX_PAGES=50`); mutation-scanner `.venv` scope fix; +7 download_proxy tests. Closed **BOB-060**.
- **Test-suite stabilization** (`6230865`): eliminated all §11.4.50 order-dependent pollution — `tests/conftest.py` `_CORRECT_MS_PATH` repo-root fix (the dominant bug: corrupted `merge_service.__path__` → broke 11 tests incl. all `scheduler_api`), extended `_POLLUTING_ROOTS`, + per-test `socket.socket` & `os.environ` snapshot/restore. Network-I/O timeout hardening (`search.py`/`routes.py`/`helpers.py`/`eztv.py`). Closed **BOB-061**, **BOB-062**.

### Open queue (Issues.md)
- **BOB-008** — RuTracker CAPTCHA — **OPERATOR-BLOCKED**: needs you to complete the CAPTCHA at `/api/v1/auth/rutracker/captcha` + `/login`, OR paste a fresh `bb_session` cookie via `/auth/rutracker/cookie-login`. Cannot be solved autonomously.
- Everything else closed (DB↔MD in sync, 62 items, `bin/workable-items validate` OK).

### How to run the suite (both work now)
- Monolithic: `.venv/bin/python -m pytest tests/unit/ -q --import-mode=importlib` → 4121 passed.
- Per-scope (faster, parallelizable): `tests/unit/merge_service/` (801) · `tests/unit/api_layer/` (170) · `tests/unit/*.py` top-level (3150).
- Always pass `--import-mode=importlib` (the `merge_service.deduplicator` lazy import needs it; a bare per-file run errors).

### Known low-priority follow-up (NOT blocking — suite is green)
- A residual `test_credential_env_wiring` / env_loader `sys.modules`-stub ordering quirk surfaces only in narrow isolated file-combos; it does NOT manifest in the full top-level scope (5 seeds green) because the new env/`sys.modules` isolation covers it there. Tighten the env_loader stub teardown if it ever resurfaces.

---

## Session 8 Summary

| Metric | Value |
|--------|-------|
| Test files | 47 test modules (222 `test_*.py` files total across all suites) |
| Test cases | 4,074+ passed |
| Coverage (unit) | 88%+ (gate: 49%) |
| Bugs fixed | 21 (BOB-001 through BOB-025, minus BOB-008) |
| Submodules aligned | constitution, challenges, containers, helixqa, jackett |
| Ruff / Mypy | pre-existing warnings only, 0 new |

### Bug Tracker

21 bugs fixed across Session 8:
- 10 B-substring parsing fixes
- 3 `import re` missing fixes
- 2 comma-size parsing fixes
- 2 crash guards
- 1 bt4g hang fix
- 1 dedup circular import fix
- 1 env_loader flaky test fix
- 1 pirateiro full test suite (44/44)

**1 remaining:** BOB-008 (RuTracker CAPTCHA) — operator-blocked, needs manual cookie paste.

### Test File Inventory

```
tests/unit/merge_service/          (31 files)
  test_cors_config.py
  test_dead_tracker_bucket.py
  test_deadline_tunable.py
  test_deduplicator.py
  test_deduplicator_edge.py
  test_diag_no_stale_leakage.py
  test_edge_case_challenges.py
  test_enricher.py
  test_enricher_edge.py
  test_hooks.py
  test_html_parsers.py
  test_jackett_autoconfig.py
  test_nnmclub_session_login.py
  test_private_tracker_html_fixtures.py
  test_public_plugin_harness.py
  test_public_plugin_harness_broad.py
  test_public_tracker_capture.py
  test_public_tracker_subprocess_timeout.py
  test_quality_detection.py
  test_scheduler.py
  test_scheduler_coverage.py
  test_search_concurrency.py
  test_search_coverage.py
  test_search_deep_coverage.py
  test_search_error_paths.py
  test_session_encryption.py
  test_theme_endpoint.py
  test_tracker_stats.py
  test_ttl_caches.py
  test_validator.py
  test_validator_coverage.py

tests/unit/api_layer/              (14 files)
  test_auth_coverage_extra.py
  test_concurrent_writers.py
  test_cors_config.py
  test_hooks_coverage.py
  test_hooks_endpoints.py
  test_hooks_remaining.py
  test_nnmclub_auth_endpoints.py
  test_routes_coverage.py
  test_sse_disconnect.py
  test_sse_token_auth.py
  test_theme_state_coverage.py
  test_theme_stream.py
  test_tracker_stats_sse.py

tests/unit/                        (55 files, infrastructure + plugin tests)
  test_auth.py, test_auth_coverage.py, test_auth_models.py
  test_config.py, test_main.py, test_dashboard.py
  test_content_type_refinement.py
  test_credential_env_wiring.py
  test_download_proxy_coverage.py, test_download_proxy_deep.py
  test_download_merged.py
  test_env_loader.py
  test_freeleech.py
  test_graceful_shutdown.py
  test_helpers.py
  test_log_filter.py
  test_merge_trackers.py
  test_novaprinter.py
  test_private_tracker_search.py
  test_public_tracker_subprocess.py
  test_retry_policy.py
  test_routes.py, test_routes_coverage.py
  test_scheduler_api.py
  test_sorting_weights.py
  test_sse_disconnect.py
  test_streaming.py
  test_theme_injector.py, test_theme_wiring.py
  test_webui_theme_injector.py
  test_ui_module.py, test_ui_sorting.py
  test_plugin_*.py                  (39 plugin modules: eztv, piratebay, solidtorrents,
                                     limetorrents, torlock, gamestorrents, nyaa, kickass,
                                     anilibra, torrentgalaxy, yts, rutor, tokyotoshokan,
                                     snowfl, torrentdownload, linuxtracker, kinozal,
                                     nnmclub, rutracker, megapeer, jackett, audiobookbay,
                                     one337x, extratorrent, torrentfunk, torrentproject,
                                     therarbg, academictorrents, ali213, yourbittorrent,
                                     glotorrents, pctorrent, rockbox, bitru, btsow,
                                     torrentscsv, xfsub, yihua, pirateiro, bt4g, iptorrents)
  test_*_guards.py, test_*_deep.py  (crash guards + deep coverage variants)
  test_ci_infra.py, test_ci_workflows.py
  test_community_plugins_compile.py
  test_courses_scaffold.py, test_course_scripts_lint.py
  test_docs_presence.py
  test_frontend_spec_coverage.py
  test_install_plugin_json_config.py
  test_jackett_integration.py, test_jackett_plugin_pool.py
  test_nnmclub_config_selfheal.py, test_nnmclub_plugin_login.py
  test_no_runtime_service_skips.py
  test_openapi_frozen.py
  test_page_title.py, test_footer_restored.py
  test_palette_catalog.py, test_palette_catalog_python_mirror.py
  test_quality_compose.py, test_quality_detection.py
  test_readme_landing_page.py
  test_runtime_requirements_includes_new_deps.py
  test_scan_script_non_interactive.py
  test_scanner_configs.py
  test_service_fixtures.py
  test_shadow_tokens.py
  test_socks_udp.py
  test_start_sh_copy_plugins_framework.py
  test_toolchain_config.py
  test_tracker_validator.py
  test_website_config.py
  test_branding_assets.py
  test_architecture_diagrams.py
  test_build_releases_non_interactive.py
  tests/benchmark/                  (3)
  tests/chaos/                      (2)
  tests/concurrency/                (3)
  tests/contract/                   (5)
  tests/docs/                       (3)
  tests/e2e/                        (7)
  tests/integration/                (19)
  tests/memory/                     (1)
  tests/observability/              (2)
  tests/performance/                (1)
  tests/property/                   (2)
  tests/security/                   (10)
  tests/stress/                     (2)
```

### Commits (latest 10+)

```
c8254ee fix: 21 test failures, pirateiro 44/44, coverage gate 88%, dedup circular import
ccd0dc9 fix: env_loader flaky test + coverage baseline 88.14% + minor test fixes
3d1819c docs: finalize Session 8 — Fixed.md Rev 12, 59 items, 18 bugs, 41 plugins
f924841 test: wave 8 — btsow/torrentscsv/xfsub/yihua (170 tests) + bt4g fix + 2 fixes
6773203 test: wave 7 — yourbittorrent/glotorrents/pctorrent/rockbox/bitru (164 tests) + bitru fix
f191401 test: wave 6 — torrentfunk/torrentproject/therarbg/academictorrents/ali213 (178 tests) + 2 fixes
1446cc5 test: wave 5 — audiobookbay/one337x/extratorrent (155 tests) + 3 fixes
fd543b0 docs: update CONTINUATION.md for Session 8 (4 waves, 23 plugins)
aae4069 test: wave 4 — kinozal/nnmclub/rutracker/megapeer/jackett + megapeer B-substring fix
e3b7acb test: wave 3 — rutor/tokyotoshokan/snowfl/torrentdownload/linuxtracker + nyaa/kickass fixes
```

---

## Coverage Snapshot

| Module | Coverage |
|--------|----------|
| api/__init__.py | 98% |
| api/auth.py | 91% |
| api/routes.py | 95% |
| api/streaming.py | 99% |
| main.py | 94% |
| deduplicator.py | 94% |
| enricher.py | 100% |
| hooks.py | 95% |
| jackett_autoconfig.py | 99% |
| scheduler.py | 93% |
| search.py | ~90% |
| validator.py | 92% |
| theme_injector.py | 99% |
| env_loader.py | 100% |
| download_proxy.py | ~95% |
| **TOTAL (unit)** | **88%+** |

---

## Known Issues

1. **BOB-008**: RuTracker CAPTCHA — operator-blocked (needs manual cookie paste)
2. Go backend is a skeleton (documented in AGENTS.md)
3. Containers may be down on session start — `bash start.sh` first
4. macOS + podman `network_mode: host` does NOT forward ports — `ensure-macos-tunnel.sh` handles this

---

## Quick-Start

```bash
# One-time venv bootstrap (gitignored .venv/ — see docs/TESTING.md "Bootstrap")
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r tests/requirements.txt

# Pre-build gate
bash scripts/pre_build_verification.sh

# Unit tests
.venv/bin/python -m pytest tests/unit/ -q --import-mode=importlib

# Coverage
.venv/bin/python -m pytest tests/unit/ --cov=download-proxy/src --cov=plugins --cov-report=term --import-mode=importlib

# Lint + typecheck
.venv/bin/ruff check . && .venv/bin/mypy download-proxy/src/

# Frontend
cd frontend && npx vitest run

# Containers
bash start.sh && bash stop.sh
```

---

## Architecture

| Port | Service | Tech |
|------|---------|------|
| 7185 | qBittorrent WebUI | LinuxServer (`admin`/`admin`) |
| 7186 | Download Proxy | Python HTTP |
| 7187 | Merge Search Service | FastAPI + Angular SPA |
| 7188 | WebUI Bridge | Python (host process) |
| 7189 | boba-jackett | Go/Gin |
| 9117 | Jackett | LinuxServer (auto-configured) |
