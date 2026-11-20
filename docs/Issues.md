# Issues — Open Workable Items

**Revision:** 144
**Last modified:** 2026-11-20T19:08:54Z
**Ticket prefix:** `BOB` (operator-mandated, 2026-06-06)
**Scope:** Open/active items only. Closed items migrate to [`Fixed.md`](Fixed.md).

> Tracking: this file + [`Issues_Summary.md`](Issues_Summary.md) are authoritative for open work.
> The SQLite single-source-of-truth + `docs_chain` engine (BOB-010) is complete.

---

## BOB-008 — RuTracker automated login blocked by CAPTCHA

**Status:** Operator-blocked
**Type:** Bug
**Operator-Block-Details:** WHAT: Operator must physically drive the interactive CAPTCHA flow at /api/v1/auth/rutracker/captcha then /login once; no agent can solve a CAPTCHA (§11.4.52 honest operator_attended boundary). WHY: Cookie-paste path and cookies-file autoload path were both offered and NOT chosen (operator decision 2026-08-26, §11.4.66); the interactive one-time CAPTCHA flow was selected instead, narrowing but not lifting the block. UNBLOCK: [A] Operator drives the interactive CAPTCHA+login flow once; resulting bb_session verified PERSISTED and verified USED by a subsequent search -- CHOSEN path (recurs periodically as the session expires, cost accepted). [B] Operator provides a pre-obtained cookie via paste -- considered, NOT chosen. [C] Operator maintains a per-tracker cookies-file for autoload -- considered, NOT chosen. WHO: Operator (milosvasic)

**OPERATOR DECISION (2026-08-26, §11.4.66 interactive clarification): COMPLETE THE CAPTCHA FLOW ONCE**

Session establishment path is DECIDED: the operator drives the interactive CAPTCHA flow at `/api/v1/auth/rutracker/captcha` then `/login` once, and the proxy stores the resulting `bb_session`. The cookie-paste path and the cookies-file autoload path were both offered and NOT chosen. THE BLOCK NARROWS BUT DOES NOT LIFT: the operator must physically drive the flow — no agent can solve a CAPTCHA (§11.4.52 honest operator_attended boundary). AGENT PREP OWED BEFORE THE HAND-OFF, so the operator's single attempt succeeds rather than discovering a broken endpoint mid-flow: verify both endpoints are reachable and correctly wired end-to-end, verify the session is actually PERSISTED after a successful post (not merely accepted), and verify a stored session is actually USED by a subsequent search. Honest limitation to state up front: a stored bb_session expires, so this path requires repeating — that cost was accepted with the decision.

This answer is recorded as consumer DATA per §11.4.35 — it is the operator's stated choice, not an agent inference, and supersedes any prior agent-chosen default on this question. Options not chosen are named above so a future reader does not re-litigate a settled call (§11.4.112(5) bounded-verdict discipline applied to decisions).

--- prior item text follows ---

RuTracker automated login blocked by CAPTCHA

## BOB-065 — Lava P2: Egress diagnosis and VPN-host SOCKS routing (containers pkg/egress)

**Status:** In progress
**Type:** Task
**Severity:** High

Lava P2: Egress diagnosis and VPN-host SOCKS routing (containers pkg/egress)

=== ROUND-2, 2026-09-25 — the egress/VPN mechanism ALREADY EXISTS (2026-07-01, commit be5062d + submodule cde354f/e273fd2/3a52825), this item's own tracker row was just never reconciled against it ===

Root cause of the confusion: TWO different "containers submodule" paths exist in this tree. `constitution/submodules/containers` (an unrelated nested dependency, no pkg/ dir) is NOT what this item or docs/PORTING-FROM-LAVA.md mean. The REAL one is the project-root `submodules/containers` (.gitmodules -> vasic-digital/Containers.git), which already has a complete, hardened, unit-tested pkg/egress (egress.go + egress_test.go + wave20_eg2hard_test.go, 12/12 tests independently re-verified passing this round), and scripts/egress-via-vpn.sh already exists and is already git-tracked (fail-loud on missing host, real direct-egress-IP probing, honest failure when no tunnel exists).

NEW THIS ROUND: tests/integration/test_egress_via_vpn.py -- scripts/egress-via-vpn.sh previously had no dedicated test (only a bare `bash -n` cited in its own commit). Adds 7 tests covering presence/exec-bit/syntax/usage/fail-loud-on-missing-host/fail-honest-on-dead-tunnel/real-direct-probe, plus the item's own exact acceptance criterion as an honestly `@pytest.mark.skipif`-gated test (SKIP: no VPN host configured, §11.4.3) -- ready to run unmodified the moment BOBA_VPN_HOST is configured. Independently re-verified: 6 passed, 1 honestly skipped.

REMAINING WORK: (1) an operator-provisioned, SSH-reachable VPN host set via BOBA_VPN_HOST; (2) running the skipped test (or `scripts/egress-via-vpn.sh diagnose <known-blocked-tracker>`) against it to produce the item's own exact acceptance evidence (via-proxy egress IP != direct host IP AND a known-blocked tracker returns 200 via proxy). No tracker is currently blocked from this sandbox host, so "known-blocked" is necessarily operator/time-dependent and cannot be hardcoded.

EVIDENCE: docs/qa/BOB-065/investigation_20260925.md.

## BOB-069 — RD2-40: §11.4.238 QA-discovery-channel ledger — ongoing coverage-escape backfill

**Status:** In progress
**Type:** Task
**Severity:** High

RD2-40: §11.4.238 QA-discovery-channel ledger — ongoing coverage-escape backfill

[BOB-136 adoption audit 2026-08-21 -> In progress] a4173c8 stood up the ledger + 4 followups; 709b06c closed 2 Important review findings (CODEGRAPH-1.5.0-GITIGNORE entry, BOB-108 filed). The BOB-009/010 evidence_path gap this item names as remaining open was closed under BOB-086 (f78f383). NOT terminal by the item's own text: it is explicitly scoped 'P1-ongoing', with the full retroactive audit of the ~50 GA-NN/RD2-NN findings deliberately NOT attempted.

## BOB-080 — RD2-13: Retroactive Fable-xhigh code review of the substantive Auto-commit diffs

**Status:** Queued
**Type:** Task
**Severity:** High

[Backfill from GOVERNANCE_AUDIT_2026-08-08_ROUND2.md RD2-13, P1] Retroactively run the mandatory independent Fable-xhigh code review (§11.4.125/§11.4.142/§11.4.209) against the substantive diffs the Auto-commit mechanism introduced (start.sh three new functions especially, since they have zero test coverage — see Root Cause 4 / RD2-24) — even though the changes already landed, a post-hoc review closes the governance gap and will surface RD2-24 (GA-27 missing tests) if not already caught. Priority: P1.

## BOB-085 — RD2-18: Create top-level Boba proxy/merge-service v1.0.0 readiness ledger (closes GA-10)

**Status:** Queued
**Type:** Task
**Severity:** Medium

[Backfill from GOVERNANCE_AUDIT_2026-08-08_ROUND2.md RD2-18, P2 — closes GA-10] Create the top-level Boba (proxy/merge-service) v1.0.0 readiness ledger (GA-10) — dedupe with the browser_extension existing one as the template. GA-10 evidence: only docs/RELEASE_READINESS_20260616.html/.md/.pdf (dated point-in-time snapshot) and the extension own ledger exist; no top-level proxy/merge-service ledger created. Priority: P2.

## BOB-090 — RD2-25: HelixQA Challenge entry exercising all three start.sh subcommands end-to-end against real compose stack

**Status:** In progress
**Type:** Task
**Severity:** Medium

RD2-25: HelixQA Challenge entry exercising all three start.sh subcommands end-to-end against real compose stack

[BOB-136 adoption audit 2026-08-21 -> In progress] a9366c9 bumped submodules/helixqa to HelixDevelopment/qa@00c5ca4 adding banks/boba-start-sh-reload.yaml (3 cases, all three subcommands). The bank EXISTS but has never been EXECUTED: the commit states honestly that the helixqa binary was not built in-session (§11.4.3 SKIP feature_disabled_by_config) and 'live bin/helixqa list demo is deferred', with only YAML-parse evidence captured. This item's acceptance is end-to-end execution against the real compose stack — artifact-class evidence cannot close a runtime-class acceptance (§11.4.226).

## BOB-093 — RD2-28: Live compose bring-up + verify rutracker ReDoS regex bounds deployed to container (closes runtime half of GA-12)

**Status:** In progress
**Type:** Task
**Severity:** High

RD2-28: Live compose bring-up + verify rutracker ReDoS regex bounds deployed to container (closes runtime half of GA-12)

[BOB-136 adoption audit 2026-08-21 -> In progress] 1c0389a proved 3 of the 4 sub-steps with strong runtime evidence: the bounded regex is confirmed in the DEPLOYED /config/qBittorrent/nova3/engines/rutracker.py inside the running container (sha256 76a6bd2e..), with a self-validated challenge + §11.4.115 RED (mutated unsafe form FAILs) and GREEN verdict JSON. The 4th sub-step is NOT met: 'capture timing of a large rutracker result page (<2s)' was not exercised — in docs/qa/BOB-093/live_search_smoke.txt rutracker returned status=empty, results_count=0 in 164ms, so no large page was ever timed.

## BOB-095 — RD2-30: Author tests/stress/test_scheduler_hooks_sse_stress_chaos.py for Go-side triangle

**Status:** In progress
**Type:** Task
**Severity:** Medium

RD2-30: Author tests/stress/test_scheduler_hooks_sse_stress_chaos.py for Go-side triangle

[BOB-136 adoption audit 2026-08-21 -> In progress] d5c8c3e authored qBitTorrent-go/internal/service/sse_broker_stress_chaos_test.go (462 lines, 6 scenarios, 2 RED captures) and found+fixed a real double-unsubscribe 'close of closed channel' defect. But this item names a THREE-component triangle: sse_broker.go + internal/api/hooks.go + internal/api/scheduler_api.go. Only sse_broker.go is covered — there is no stress_chaos test anywhere under qBitTorrent-go/internal/api/. 1 of 3, partial.

## BOB-101 — GA-19/RW-09: Is --profile go parity still a release goal? (gates RW-10..13) — OPERATOR-DECISION

**Status:** Operator-blocked
**Type:** Task
**Operator-Block-Details:** WHAT: Operator decision 2026-08-26: Go --profile go parity remains a goal but is deferred past v1.0.0; no implementation expected for this milestone. WHY: Operator decision deferred past v1.0.0 UNBLOCK: [A] operator re-evaluates Go --profile go parity for a post-v1.0.0 milestone and records a new decision · [B] operator removes the deferral and funds the parity work as a v1.0.0 blocker WHO: User
**Severity:** High

**OPERATOR DECISION (2026-08-26, §11.4.66 interactive clarification): DEFER PAST v1.0.0**

Go `--profile go` parity remains a goal but is NO LONGER a v1.0.0 release blocker. RW-10..13 move to a post-1.0 milestone and stop gating the tag. Nothing advertised is removed, so §11.4.122 stays clean and no §11.4.90 Obsolete closure is warranted. The BOB-141 measured fact stands unchanged: the Go container's Dockerfile runs ONE binary binding only :7187; nothing binds :7186 or :7188 despite compose setting PROXY_PORT/BRIDGE_PORT. CLAUDE.md's port map already describes what the container ACTUALLY does and needs no amendment under this decision.

This answer is recorded as consumer DATA per §11.4.35 — it is the operator's stated choice, not an agent inference, and supersedes any prior agent-chosen default on this question. Options not chosen are named above so a future reader does not re-litigate a settled call (§11.4.112(5) bounded-verdict discipline applied to decisions).

--- prior item text follows ---

GA-19/RW-09: Is --profile go parity still a release goal? (gates RW-10..13) — OPERATOR-DECISION

## BOB-121 — External watchdog for the forced-logout architectural gap (task #85, incident #3)

**Status:** Ready for testing
**Type:** Task
**Severity:** Important
**Created-By:** Claude

Phase 1 design-only proposal: the BOB-116/task-77 resource-pressure preventive systemd --user timer runs inside user@1000.service, the exact pool it monitors, so it cannot fire when that pool dies (proven by incident #3, docs/qa/BOB-120/, 22:42+22:57 fires then blocked 23:45:49-23:49:00). Recommends Option B (user crontab reusing pre-existing crond.service in system.slice, no new root service) kept alongside the existing timer, with Option A (new root-owned systemd unit) as escalation path if Phase 1.5 live cron/cgroup verification is adverse. Proposal: docs/proposals/external-watchdog-for-forced-logout-architectural-gap.md. Operator decision required per §11.4.66 before any implementation -- NOT implemented in this task.



**Progress 2026-08-21:** Flight recorder built, installed, and recording. First finding: NOTHING was watching at all — the root watchdog is LoadState=not-found and the BOB-116 user timer inactive. The blocking spike REFUTED the proposal's rationale while confirming its conclusion: this vixie-cron does invoke pam_systemd so the tick lands in session-N.scope, but that scope is a SIBLING of user@1000.service, and the real incident killed exactly one unit (73 'user@1000.service: Killing process' lines while session-18.scope merely deactivated). So the recorder does not need to survive — its SCHEDULER does, and crond in system.slice survived all seven incidents. Captures the pre-event memory/PSI/thread ramp that nothing post-hoc can recover, plus boot id, the gap itself, unit start timestamp, cgroup pids, and OOM cgroup attribution. Evidence: 5 records under real cron at exact 60s spacing; a staged analogue on a DISPOSABLE unit reaching 'VERDICT: SESSION TEARDOWN'; golden-good against the REAL BOB-120 log giving the correct diagnosis (k_unit_kill=1, k_oom=0); healthy-host quiet under load 8.15. NOT CLOSED — two operator decisions are owed: whether to keep it installed (one crontab line, zero signals, zero power verbs, 32K, reversible via uninstall.sh), and the root system.slice watchdog which is written but needs one `su`. UNTESTED AGAINST A REAL FORCED LOGOUT: survival is inferred from cgroup topology, not observed, and it does NOT hold against a whole-slice sweep or KillUserProcesses=yes.
## BOB-170 — Capture one quiescent GREEN run of the scaling growth gate, which has never executed under its own loadavg<=0.75/cpu precondition and has no scheduled window that would make it

**Status:** Queued
**Type:** Task
**Severity:** Medium
**Created-By:** Claude
**Assigned-To:** Claude

WHAT. The BOB-109 scaling suite gates its two timing tests on loadavg_1m/nproc <= 0.75 — on this 8-cpu host, a 1-minute load average at or below 6.0 — and SKIPs loudly otherwise. That gate is correct and was adopted for a good reason (§11.4.201(8)): the author validated a 2.10 growth-exponent threshold, then observed it FALSE-FAIL correct code at load 11.06 (baseline span 2.136), and at load 15-23 measured baseline spans of 2.358 against injected-cubic mutants at 2.278-2.331 — the signal is smaller than the noise and the two are not separable in either direction. Gating was the honest response.

THE PROBLEM. The gate has consequently NEVER RUN under its own precondition. Every recorded run today measured load 9.15-23; the independent reviewer measured 9.66 during review; the conductor measured 6.45 at its lowest. GREEN polarity WAS observed — at loads 9.4-11.6 (span 1.882) and in three stability runs (1.759/1.832/1.848) — but never once beneath the shipped ceiling. The author states this honestly as an inference from data rather than a run they can paste, and the reviewer confirmed the inference is sound (quiescence is strictly more favourable). Sound inference is still not an observed run.

WHY THAT MATTERS (§11.4.226). A registered, topology-present guard that never executes is indistinguishable from a guard that would fail if it did. Nothing currently ensures it ever runs: no freshness contract, no scheduled quiet-window invocation, no tracked item — which is precisely the unexecuted-standing-guard class §11.4.226 names, where registration gets treated as coverage while execution is nobody's job. The forensic precedent in that anchor is two standing guards that, when finally executed, immediately emitted latent FAILs.

ACCEPTANCE. (a) Execute both quiescence-gated timing tests on a host whose 1-minute loadavg is genuinely <= 0.75/cpu — no agent fleet, no concurrent build — and capture the run as an artifact showing the resolved load reading alongside the measured span exponent, so the precondition is provable from the artifact and not asserted. (b) Record the observed GREEN polarity in the item and in the test source, replacing the current honest-inference note. (c) If the gate FAILS under genuine quiescence, that is the finding this item exists to surface, and it reopens the threshold-calibration question rather than being worked around. (d) Establish a freshness contract per §11.4.226: how stale a quiescent verdict may be before the gate counts as uncovered again, so this does not silently return to never-executing.

HONEST BOUNDARY. This item does not claim the gate is wrong. The evidence points the other way — quiescence is strictly more favourable than the loads where GREEN was already observed. It claims only that the run has not happened, and that an unexecuted guard cannot be cited as coverage.

PROVENANCE. Raised as IMPORTANT-2 by the independent Fable-substrate reviewer of the BOB-109 work, and independently corroborated: the reviewer verified the SKIP is loud and prints its resolved numbers, and confirmed the shipped tests do SKIP at today's load.

## BOB-172 — rutracker search endpoint returns HTTP 403 with Cloudflare challenge markers and zero login markers, so one of three merge-search trackers silently contributes no results

**Status:** Operator-blocked
**Type:** Bug
**Operator-Block-Details:** WHAT: Choose how the merge service reaches rutracker for SEARCH (not just login) given real-time re-verified 2026-09-25: GET /forum/tracker.php?nm=... returns 403 with cf-mitigated: challenge, zero login markers, in ~21-27ms -- Cloudflare's edge decides before serving content, before any JS challenge runs. WHY: Attempted: (a) full realistic Chrome-header-set request vs the merge service's bare default request -- identical 403 in ~21ms, ruling out header tuning; (b) live-probed all 3 configured rutracker mirrors -- rutracker.org and rutracker.net both cf-mitigated:challenge, rutracker.nl fails TLS verification entirely; (c) no code path can solve a Cloudflare edge-layer challenge without external infrastructure or a supplied clearance token -- changing shipped capability, needing §11.4.122 operator sign-off. UNBLOCK: Operator picks ONE: [1] Deploy a challenge-solving service (FlareSolverr or equivalent) and route the rutracker search GET through it -- not deployed today, same class of gap as kinozal/BOB-235; [2] Accept a supplied cf_clearance cookie -- RUTRACKER_COOKIES already forwards supplied cookies but the code only checks for bb_session, never cf_clearance (the actual token this wall checks) -- would need a small code change plus an operator refresh cadence via the existing scripts/load-tracker-cookies.sh pattern; [3] Route rutracker searches through Jackett's own rutracker indexer if its scraper has a working bypass -- unverified, needs a separate boba-jackett indexer-health check; [4] Mark rutracker SEARCH unsupported per §11.4.90/BOB-172 acceptance(d) -- README.md:167 still lists RuTracker with no caveat, unlike kickass/eztv which already carry this exact honest-capability-boundary treatment in docs/MERGE_SEARCH_DIAGNOSTICS.md. WHO: repository operator UNBLOCK: Operator picks ONE: [1] Deploy a challenge-solving service (FlareSolverr or equivalent) and route the rutracker search GET through it; [2] Accept a supplied cf_clearance cookie (RUTRACKER_COOKIES already forwards supplied cookies but only checks bb_session, never cf_clearance); [3] Route rutracker searches through Jackett's own rutracker indexer if its scraper has a working bypass; [4] Mark rutracker SEARCH unsupported per §11.4.90/BOB-172 acceptance(d)
**Severity:** High
**Created-By:** Claude
**Assigned-To:** Claude

WHAT. The rutracker SEARCH endpoint is refused by bot protection while the site itself is fully reachable. Measured unauthenticated 2026-08-21 (no cookie file read, no credential value in any artifact — §11.4.10):

  GET /forum/index.php            -> 200, 96283 B, <title>RuTracker.org</title>, challenge markers 0
  GET /forum/tracker.php?nm=debian -> 403,  5351 B, challenge markers 1, LOGIN markers 0, trs-tr- 0

The zero login markers are the load-bearing detail: the server is not asking us to authenticate, it is refusing the request before authentication is considered. Supplying valid credentials or a fresh cookie jar therefore does NOT address this.

WHY IT MATTERS. rutracker is one of the three trackers the merge service fans a query across (with kinozal and nnmclub). A 403 on its search path means it contributes nothing to every merged result set, silently — the fan-out still 'succeeds', it just returns one fewer tracker's worth of results. From a user's seat this looks like thin results, not an outage.

IT EXPLAINS TWO PREVIOUSLY-UNEXPLAINED OBSERVATIONS. docs/qa/BOB-093/live_search_smoke.txt records rutracker returning status=empty, results_count=0 in 164ms, and the BOB-136 adoption audit reached the same observation independently. Both recorded the symptom; neither had the cause. 164ms is far too fast for a real search across a remote forum and is exactly what an immediate 403 costs.

IT ALSO BLOCKS BOB-093's FOURTH SUB-STEP. That item requires timing a large rutracker result page under 2s. No large page has ever been obtained, and this is why. That sub-step is not merely waiting on credentials, as previously assumed — it is unmeetable until the 403 is resolved.

PROVENANCE, INCLUDING A CORRECTION I MADE MID-INVESTIGATION (§11.4.199). An independent reviewer reported a Cloudflare challenge served to curl even with cookies. Verifying, I probed index.php, got a clean 200 with no challenge markers, and was one step from recording their claim as REFUTED. That would have been wrong for a textbook reason: index.php is not the search path, so my probe never reached the precondition, and a repro that misses the precondition proves nothing — it is not evidence of absence. Probing the actual search endpoint reproduced it immediately. The reviewer was substantially right; my probe was aimed at the wrong endpoint. Recorded because the near-miss is the instructive part, and because the two probes TOGETHER give a sharper result than either the original claim or my near-refutation: not 'rutracker is behind Cloudflare' (the index is open), but 'the SEARCH endpoint specifically is refused'.

ACCEPTANCE. (a) Determine whether the 403 is permanent policy, rate/reputation-based, or triggered by a client signature the plugin can legitimately present (user-agent, header order, TLS fingerprint) — by measurement, not assumption, and WITHOUT evasion techniques that would violate the site's terms. (b) Whatever the outcome, the failure must become LOUD: a tracker returning 403 must be reported as a tracker ERROR in the merge result, never folded into 'empty' — a silent contributor is the §11.4.201(6) false-null at the product layer, and it is what let this sit unexplained across two separate investigations. (c) A test asserting that a 403 from any tracker surfaces as an error and not as zero results, with a paired §1.1 mutation. (d) If the endpoint is genuinely unavailable to us, record that as an honest capability boundary (§11.4.112) and stop advertising rutracker as a live search source until it is — including in the README and the merge-service docs.

HONEST BOUNDARY. Measured from ONE host, ONE time, UNAUTHENTICATED. Whether an authenticated session with a browser-like client succeeds was NOT tested and must not be assumed either way. The finding is that the current code path gets a 403; it is not a claim about what every client would get.

## BOB-184 — Icon-glyph controls are unverified for non-text contrast because neither contrast oracle can measure them

**Status:** Queued
**Type:** Task
**Severity:** Medium
**Created-By:** Claude
**Assigned-To:** Claude

Three icon-glyph controls (.bridge-retry, .theme-toggle, .caret) render text made of non-BMP code points. axe-core declines to decide their contrast, reporting them under the incomplete channel with messageKey nonBmp and resolving NEITHER fgColor NOR bgColor, so the Python recomputation in docs/qa/BOB-164/axe_contrast_scan.py cannot decide either: 40 such nodes across 16 palette x mode combinations. BOB-164 round 2 stopped them being scored as silent passes by naming them GLYPH_UNMEASURED, printing them on every run and fencing them, so any NEW unmeasured glyph node blocks. What remains genuinely unproven is their contrast itself: as non-text user-interface components they owe 3:1 under WCAG SC 1.4.11, and no oracle in this repo measures that today. Acceptance: a measurement path that resolves the effective foreground and backdrop for glyph controls (for example reading getComputedStyle colour against the composited backdrop, or replacing the glyphs with inline SVG carrying explicit fill tokens), each of the three controls shown to clear 3:1 in all 16 palette x mode combinations, and the GLYPH_UNMEASURED fence shrunk by exactly the nodes then proven.

## BOB-185 — Rendered-DOM contrast oracle cannot see data-driven nodes, leaving badge and status pills arithmetic-only

**Status:** Queued
**Type:** Task
**Severity:** Medium
**Created-By:** Claude
**Assigned-To:** Claude

docs/qa/BOB-164/axe_contrast_scan.py scans a static dist with no backend, so every node whose existence depends on fetched data is absent from the page it measures: the results table renders empty, so .type-badge and .quality-badge never appear, and the hooks list renders empty, so .status pills never appear. That is precisely why the BOB-164 round-1 regression went unseen in a rendered DOM even though it was scanned in all 16 themes, and it is why round 2 had to close the class in the arithmetic oracle instead. Those nodes are now covered by frontend/src/app/models/style-contrast.spec.ts, which extracts declared foreground-on-fill pairs from the stylesheets, but that is an ARITHMETIC claim about declared colour pairs, not a rendered-pixel one: it cannot see opacity applied by an ancestor, a composited backdrop, or a cascade this repo's static extractor does not model. Acceptance: the scan drives the dashboard with seeded fixture data (a stub backend, a route fixture, or an injected component harness) so the badge and status nodes are present in the DOM, axe measures them directly, and a control needle proves the rendered oracle sees a seeded sub-floor badge before any clean result from it is believed.

## BOB-211 — LATENT + OPERATOR-GATED: on a uid-flattening mount whose uid is not the operator, chown fails EPERM with no fstype-aware diagnosis, and fmask/dmask silently defeat the preserve_mode 600 contract

**Status:** Queued
**Type:** Bug
**Severity:** minor

STATUS: LATENT on this host (measured: all six declared locations sit on ONE btrfs mount, fully ownership-expressive) and OPERATOR-GATED for verification. Retained from the dismissed BOB-206 rather than discarded with it, because the scenario is well-founded elsewhere: the declared mount is a udisks auto-mounted REMOVABLE NVMe, so another operator's portable drive being exFAT or NTFS is entirely ordinary.

TWO RESIDUALS:
(1) REPAIR-LAYER DIAGNOSIS. On a uid-flattening mount whose flattened uid is NOT the operator, probe_location correctly REFUSES (verified: uid=0 and uid=100999 both refuse). But it then hands ownership_repair.sh a chown that will return EPERM, and nothing in the repair path is fstype-aware — so the operator sees a permission failure whose real remedy is a REMOUNT OPTION, which no message says. Reasoned, NOT proven: the shim used to verify BOB-206 models the stat READ, not the chown WRITE, and cannot settle whether chown actually fails.
(2) MODE CONTRACT. vfat flattens MODE via fmask/dmask, so the preserve_mode: true / 600 contract on .env and config/boba.db would be silently unenforceable there. §11.4.10-adjacent: a credential file believed to be 600 that is world-readable by mount option is a leak the mode check cannot see.

WHY OPERATOR-GATED: a genuine end-to-end RED needs a real uid-flattening mount. The privilege-free route is bindfs -u <uid> (FUSE; fusermount IS present and user_allow_other IS set) — but bindfs is ABSENT on this host, as are mkfs.vfat and losetup. So verification needs either a bindfs install or a privileged loopback mount. Neither was attempted (§11.4.21 — high-blast-radius host mutation is operator-gated).

ALSO RECORDED: NO test anywhere exercises a uid-flattening filesystem — vfat/exfat/ntfs/flatten/loopback/mkfs/losetup/bindfs/fusermount all measure 0 across the three ownership test files, needle-proven (probe_location = 3 hits through the same instrument).

ACCEPTANCE: (1) operator decides whether to install bindfs or provide a privileged loopback so the RED can be built; (2) if verified, the repair path gains fstype-aware diagnosis naming the remount remedy; (3) the mode contract either detects mode-flattening mounts and refuses, or documents honestly that it cannot be enforced there.

DISCOVERY CHANNEL (§11.4.238): retained residual from the BOB-206 verification stream.

## BOB-235 — Live kinozal credential test reports authenticated=False, status='empty', error='' — cause UNKNOWN

**Status:** Operator-blocked
**Type:** Bug
**Operator-Block-Details:** WHAT: Choose how the merge service reaches Kinozal (kinozal.tv resolves to 127.0.0.1 here; kinozal.guru sits behind a Cloudflare challenge) WHY: Attempted: (a) diagnostics now surface the real failure (code half fixed + tested); (b) no code path can bypass a Cloudflare challenge or change host DNS; (c) picking a mirror, a challenge solver or dropping a tracker changes shipped capability and needs an operator decision (§11.4.122) UNBLOCK: Operator picks ONE: [1] KINOZAL_MIRRORS=https://kinozal.guru in .env + ./start.sh --recreate; [2] change the roster primary host in trackers.py; [3] supply a cf_clearance cookie / FlareSolverr / Jackett kinozal indexer; [4] mark Kinozal unsupported (Obsolete, feature-removed per §11.4.90) WHO: repository operator
**Created-By:** Claude

Live kinozal credential test reports authenticated=False, status='empty', error='' (found 2026-09-23). ROOT CAUSES (docs/qa/BOB-235/investigation_20260923.md): (A) operator/environment: kinozal.tv publishes A record 127.0.0.1 (host, container, DoH Cloudflare+Google all agree; rutracker.org resolves normally as control), KINOZAL_MIRRORS is empty so search.py falls back to kinozal.tv; the live mirror kinozal.guru answers every non-browser client with a Cloudflare 403 'Just a moment' challenge (login POST, curl, aiohttp, operator cookies with two user-agents; no cf_clearance cookie; KINOZAL_COOKIES is loaded into the container but no code reads it). (B) code defect FIXED under TDD (RED 2 failed/1 passed, GREEN 19 passed): _search_kinozal's except branch only logged and stashed no diagnostic, so the chip read empty with error=None; it now stashes error_type + 'Kinozal request failed: <msg>'. Needs ./start.sh --reload-python to be live. Credential validity is UNKNOWN (no request ever reached a login endpoint) - do not rotate credentials on this evidence. Operator-Block-Details: WHAT: choose (1) reachable domain - set KINOZAL_MIRRORS=https://kinozal.guru + ./start.sh --recreate, or change the roster primary in trackers.py; (2) how to pass the Cloudflare challenge - FlareSolverr (not deployed), cf_clearance cookie + code that actually reads KINOZAL_COOKIES, Jackett's kinozal indexer, or mark kinozal operator-blocked; (3) optionally re-export a kinozal-only cookie file. WHY: every agent-reachable path was exhausted - DNS, mirrors, login POST, cookies, env propagation all measured. UNBLOCK CONDITION: the live test authenticates or the operator marks kinozal unsupported. WHO: repository operator.

