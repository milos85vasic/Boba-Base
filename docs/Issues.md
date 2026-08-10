# Issues — Open Workable Items

**Revision:** 5
**Last modified:** 2026-06-09T20:00:00Z
**Ticket prefix:** `BOB` (operator-mandated, 2026-06-06)
**Scope:** Open/active items only. Closed items migrate to [`Fixed.md`](Fixed.md).

> Tracking: this file + [`Issues_Summary.md`](Issues_Summary.md) are authoritative for open work.
> The SQLite single-source-of-truth + `docs_chain` engine (BOB-010) is complete.

---

## BOB-008 — RuTracker automated login blocked by CAPTCHA

**Status:** Operator-blocked
**Type:** Bug
**Created:** 2026-06-06
**Operator-Block-Details:** WHAT — RuTracker login with stored creds returns
no session cookie (CAPTCHA wall). WHY — automated user/pass login is
CAPTCHA-gated; self-resolution exhausted (creds correct + wired, login
attempted, `auth=True`). UNBLOCK — [A] operator completes the CAPTCHA flow
at `/api/v1/auth/rutracker/captcha` + `/login`. [B] operator pastes a fresh
`bb_session` cookie via `/auth/rutracker/cookie-login`. WHO — operator.

**Evidence:** live search per-tracker stat `rutracker status=error auth=True
error="login returned no session cookie — likely CAPTCHA"`.

## BOB-064 — Lava P1: Durable remote execution (systemd-linger helper)

**Status:** Queued
**Type:** Task
**Severity:** High

[Backfill from RD2-15/GA-05, audit doc 2026-08-08] Lava-porting finding P1 (Durable remote execution, Lava PLAYBOOK section 5). Problem Boba-Base shares: long QA/deploy runs on a remote host die when the SSH session ends. Root cause: remote systemd-logind KillUserProcesses reaps detached user processes (tmux/nohup/setsid all die). Fix: loginctl enable-linger + systemd-run --user --unit=<n> --collect bash runner.sh; poll systemctl --user is-active; sentinel file for completion. Avoid piping through tail -N (buffers until exit). Port: add containers submodule helper pkg/remoteexec (or scripts/lib/durable-run.sh) shared by both repos; wire scripts/deploy-remote.sh + run_all_challenges.sh to use it. TDD: a test launches a 60s sleeper via the helper, drops the SSH session, asserts it is STILL running after (fails against the old nohup approach). Source: docs/PORTING-FROM-LAVA.md. Per audit GA-05: NOT-DONE, still no tracked workable item for the four implemented-in-code Lava findings. Per audit RD2-15 [P0]: Create tracked workable items (BOB-064..067, via the workable-items tool — never raw MD edits) for the four Lava-porting findings, citing implementing commits as evidence, closed as Implemented.

## BOB-065 — Lava P2: Egress diagnosis and VPN-host SOCKS routing (containers pkg/egress)

**Status:** Queued
**Type:** Task
**Severity:** High

[Backfill from RD2-15/GA-05, audit doc 2026-08-08] Lava-porting finding P2 (Egress decision + VPN-host routing, Lava PLAYBOOK sections 0 and 4). Problem Boba-Base shares: on a datacenter host, trackers are network-blocked (DNS-fail/TLS-MITM, not Cloudflare so FlareSolverr cannot fix). Affects Jackett indexer fetches + merge_service/download-proxy + plugin engines. Diagnosis (port the script): curl https://api.ipify.org (host IP) + curl -o /dev/null -w %{http_code} https://<tracker>/ direct vs via a VPN-host SOCKS proxy. Different egress IP + 200 via proxy confirms. Fix: route outbound through a VPN-connected host (the nezha pattern). SOCKS tunnel ssh -D 127.0.0.1:1080 -N <vpnhost> (use --socks5-hostname for remote DNS); point Jackett + download-proxy + qBitTorrent-go at it (P3). For browser-cookie harvest, run the harvester ON the VPN host. Port: containers submodule pkg/egress (tunnel up/verify) + scripts/egress-via-vpn.sh glue; reuse Boba-Base existing ensure-macos-tunnel.sh style. TDD: assert the via-proxy egress IP != direct host IP AND a known-blocked tracker returns 200 via proxy. Source: docs/PORTING-FROM-LAVA.md. Per audit RD2-15 [P0]: Create tracked workable items (BOB-064..067) for the four Lava-porting findings, citing implementing commits as evidence, closed as Implemented.

## BOB-066 — Lava P3: BOBA_UPSTREAM_PROXY in download-proxy + qBitTorrent-go + Jackett + compose env-forward

**Status:** Queued
**Type:** Task
**Severity:** High

[Backfill from RD2-15/GA-05, audit doc 2026-08-08] Lava-porting finding P3 (Configurable outbound proxy in the services, Lava PLAYBOOK section 3). download-proxy (Python): httpx/requests honor HTTP_PROXY/HTTPS_PROXY/ALL_PROXY/NO_PROXY env natively — add an explicit BOBA_UPSTREAM_PROXY config that sets these for tracker-bound clients, with loopback bypass (NO_PROXY=127.0.0.1,localhost,jackett). qBitTorrent-go: set http.Transport.Proxy (socks5 native, remote DNS) from a BOBA_UPSTREAM_PROXY env — mirror Lava internal/httpx/proxy.go. Jackett: has a built-in proxy setting (configure via its API/ServerConfig). Deploy gotcha (port): the env must be FORWARDED into the containers (docker-compose.yml env / the boba-ctl deploy) — Lava bug was a missing allow-list entry. Verify on distroless via podman inspect, not exec printenv. TDD: a test with a local proxy asserts the service tracker request traverses it; falsifiability: disable the wiring so the test fails. Source: docs/PORTING-FROM-LAVA.md. Per audit RD2-15 [P0]: Create tracked workable items (BOB-064..067) for the four Lava-porting findings, citing implementing commits as evidence, closed as Implemented.

## BOB-067 — Lava P4: Jackett cookie-login hardening + behaviorally-equivalent HelixQA fake

**Status:** Queued
**Type:** Task
**Severity:** High

[Backfill from RD2-15/GA-05, audit doc 2026-08-08] Lava-porting finding P4 (Jackett cookie-login hardening, Lava PLAYBOOK section 8). Add to Boba-Base existing cookie infra: Jackett management API (/api/v2.0/indexers, indexer /config) needs a dashboard session cookie (empty-password POST /UI/Dashboard) — the apikey only authorizes Torznab /results and /caps. If boba-jackett/extract-jackett-key.py only uses the apikey, ListIndexers/config silently 302 to /UI/Login. Critical for anti-bluff: the test fake MUST 302-without-cookie like real Jackett (behavioral equivalence) or the gap stays hidden. TDD: fake 302s management without the cookie; assert discovery succeeds via the cookie path; falsifiability: remove cookie login so 302 failure surfaces. Home: jackett integration + helixqa fakes. Source: docs/PORTING-FROM-LAVA.md. Per audit RD2-15 [P0]: Create tracked workable items (BOB-064..067) for the four Lava-porting findings, citing implementing commits as evidence, closed as Implemented.

## BOB-068 — RD2-00: unattributed, unreviewed Auto-commit mechanism pushing to main

**Status:** Queued
**Type:** Bug
**Severity:** High

[Backfill from GOVERNANCE_AUDIT_2026-08-08_ROUND2.md RD2-00, Rev-6 downgrade to P1] Three commits at HEAD carry the bare message Auto-commit with no body, no ticket reference, no TDD trail: 54e313f (26 files), 9c8f684 (6 files), 743097a (2 files). Two landed while the audit was in progress. Source unidentified: no crontab, no systemd timer, no matching process, no in-tree script emitting the string, no hooksPath, no PostToolUse/Stop hook. Timezone +0500 on newer commits does not match host +0300 MSK. RD2-00 Update: git reflog proves 9c8f684/743097a arrived via pull: Fast-forward from a +0500 host, matching the established 2026-06-28 cross-host rsync-sync pattern (55b8671/cdb555f). Update 2 (Rev-6): root cause is a second live Claude session (Opus 5, same +0500 host) that independently landed constitution commit 177f2b0 (new anchor §11.4.238) while this session was mid-edit on the identical anchor number. Downgrades severity from P0 to P1. Every such commit bypasses §2 wrapper, §11.4.43 TDD-fix, §11.4.92 5-pass eval, §11.4.125/§11.4.142/§11.4.194/§11.4.209 mandatory Fable-xhigh review, §11.4.234 dedicated commit/push script. Composes with RD2-10..13.

## BOB-069 — RD2-40: §11.4.238 QA-discovery-channel ledger — ongoing coverage-escape backfill

**Status:** Queued
**Type:** Task
**Severity:** High

[Backfill from GOVERNANCE_AUDIT_2026-08-08_ROUND2.md Rev-6 addendum, priority downgraded P0->P1] §11.4.238 compliance MECHANISM STOOD UP AND EXERCISED 2026-08-08. docs/QA_DISCOVERY_LEDGER.md created with discovery-channel schema, seeded with 4 real entries from this session (RD2-22, RD2-41a, RD2-41b, BOB-008), each with a real coverage-escape audit citing the specific missing/blind check; 3 of 4 already closed with a genuine new automated check carrying real RED->GREEN evidence. CLAUDE.md Critical Constraints now points at the ledger and states the discovery-channel-split mandate. Closed-loop example exercised end-to-end: scripts/pre_build_verification.sh invariant 17 extended to run workable-items diff (not just validate) — RED-captured via tests/unit/test_pre_build_workable_items_diff_check.sh §1.1 paired mutation. Honest boundary (§11.4.6): full retroactive audit of every one of the ~50 GA-NN/RD2-NN findings in this document (each needs its own escape-audit entry) was NOT attempted — ledger is honest that it starts now (100% out-of-band in its own tracked split table) rather than backfilling a false complete history. BOB-009/BOB-010 evidence_path gap remains open. Priority: downgraded from P0-blocking to P1-ongoing — MECHANISM exists and applies to new findings; the remaining retroactive audit + BOB-009/010 closure is incremental.

## BOB-070 — RD2-41: pre-build mutation-marker scan carrier false-positive silently defeats entire pre-build gate

**Status:** Queued
**Type:** Bug
**Severity:** High

[Backfill from GOVERNANCE_AUDIT_2026-08-08_ROUND2.md Rev-6 addendum, RD2-41 P1 — arguably P0] scripts/docs_chain.sh (FIXED this session) and scripts/pre_build_verification.sh invariant 17 (FIXED this session) both hardcoded a non-existent bin/workable-items path, silently no-op ing/skipping DB-export and DB-validate steps on every run — root-caused and fixed via the resolution chain proven in constitution/scripts/reporting/report_item.sh (env override -> committed constitution copy -> on-demand go build). Regression guards: tests/unit/test_docs_chain_binary_resolution.sh (RED->GREEN) + tests/unit/test_pre_build_workable_items_invariant.sh (RED->GREEN). A SEPARATE, still-open defect surfaced while fixing this: pre_build_verification.sh pre-code-review mutation-marker scan aborts the ENTIRE script (exit 1) before invariant 17 is ever reached, on carrier false-positives — legitimate constitution/**/*_mutation_test.sh + *_test.go files that intentionally contain the literal strings MUTATED/# MUTATION as part of their OWN §1.1 testing logic (36 hits, all under constitution/scripts/{gates,multitrack,workable-items}/). Same §11.4.201 carrier-false-positive class as GA-24 + RD2-01. Practical impact: the ENTIRE pre-build gate has not completed a full run for as long as this false-positive has been live — no invariant past the mutation-marker check has been genuinely enforced. Fix needed: marker-scanner to exclude self-referential test/gate files (or use structural check than bare substring), matching the fix scoped for GA-24/RD2-01/RD2-36. Priority: P1, arguably P0.

## BOB-071 — RD2-01: guard-forbidden-commands.sh hook has live reproducible substring carrier false-positive

**Status:** Queued
**Type:** Bug
**Severity:** Medium

[Backfill from GOVERNANCE_AUDIT_2026-08-08_ROUND2.md RD2-01, P2] During this investigation the command echo === systemd system-level (may need no sudo for list) === was BLOCKED by the PreToolUse hook with BLOCKED — §6.U no-sudo, because the guard does a substring match for sudo against the ENTIRE command line, including inside an unrelated echo string (need no sudo for list). Exact §11.4.201 carrier-false-positive class GA-24 already documented for a different file — now independently reproduced live, proving structural pattern in guard matching approach not a one-off content gap. Fix: guard needs word-boundary / shell-token-aware matching (or restrict sudo/su check to actual command-invocation position) rather than an unanchored substring grep across the whole line, mirroring fix direction scoped for GA-24 (EXCLUDE_PATHS is band-aid per-file; root cause is matching strategy itself). Priority: P2 (annoying, self-correcting via retry, but real false-positive class that will keep recurring). Composes with RD2-36 (canonical remediation).

## BOB-072 — RD2-03: workable_items.db machine-caught SSoT integrity violations + 90% of closures have zero audit trail

**Status:** Queued
**Type:** Bug
**Severity:** High

[Backfill from GOVERNANCE_AUDIT_2026-08-08_ROUND2.md RD2-03, P1] constitution/scripts/workable-items/bin/workable-items validate --db docs/workable_items.db exits 1 with 2 real violations: BOB-009 and BOB-010 both have a closure evidence_path that does not resolve (narrative or multi-value text in a single-path field). Beyond the tool own catch, a direct SQL sweep shows 56 of 62 closed items (90%) have zero rows in item_history and all 62 closed items have empty closure_criteria and commit_ref columns — the constitution names this DB the authoritative SSoT for closure audit trails (§11.4.93/§11.4.148(D4)/§11.4.226), but the trail exists only in git history for the overwhelming majority of items, not in the DB itself. Fix: (1) fix BOB-009/BOB-010 evidence_path values via the workable-items tool proper update path (never raw SQL); (2) for the 56 audit-trail-empty closures, backfill item_history rows from git log where recoverable, and explicitly mark genuinely-unrecoverable ones (§11.4.6 — UNKNOWN rather than fabricated); (3) wire the docs_chain sync (see RD2-04) so future closures never land without a trail. Priority: P1. Composes with RD2-19.

## BOB-073 — RD2-04: workable_items.db and Issues.md/Fixed.md have drifted (BOB-008 body differs)

**Status:** Queued
**Type:** Bug
**Severity:** High

[Backfill from GOVERNANCE_AUDIT_2026-08-08_ROUND2.md RD2-04, P1] workable-items diff --db docs/workable_items.db --issues docs/Issues.md --fixed docs/Fixed.md reports: ~ BOB-008 body differs (md=703 bytes db=576 bytes). Root cause: 54e313f rewrote the DB (file grew 135168->229376 bytes, two new BOB-008 item_history rows dated 2026-08-08) but did NOT touch docs/Issues.md/Fixed.md in the same commit — a live §11.4.106(F) write-seam violation (mandated commit-time doc/DB sync hook did not fire, or does not exist). Fix: reconcile BOB-008 body between DB and MD via the workable-items tool (sync or md-to-db/db-to-md as appropriate — determine which side is authoritative for this specific drift), then verify/wire the commit-seam sync hook per §11.4.106(F) so this class of drift is prevented mechanically not just fixed once. Priority: P1 (composes directly with RD2-00 — this drift is a direct symptom of the unattributed-commit problem). Composes with RD2-17 (canonical remediation) and RD2-20.

## BOB-074 — RD2-07: DDoS-class testing fully absent from the mandated test-type matrix

**Status:** Queued
**Type:** Task
**Severity:** Medium

[Backfill from GOVERNANCE_AUDIT_2026-08-08_ROUND2.md RD2-07, P2] tests/ has 18 subdirectories covering unit/integration/e2e/security/chaos/stress/performance/benchmark/UI (13 of the constitution ~14 mandated categories present). tests/load/locustfile.py covers throughput/scale only. No file anywhere mentions DDoS, flood, or attack-resilience testing — a distinct mandated category per §11.4.27, and not legitimately N/A given this is an internet-facing FastAPI/Gin service with public HTTP endpoints reachable over a LAN tunnel. Fix: author tests/ddos/ (or extend tests/load/) with rate-limit-enforcement, malformed-request-flood, and resource-exhaustion-under-attack coverage for the exposed download-proxy/merge-service endpoints. Priority: P2. Canonical implementation: RD2-32.

## BOB-075 — RD2-08: docs/features/Status.md and docs/codegraph/Status.md are stale

**Status:** Queued
**Type:** Task
**Severity:** High

[Backfill from GOVERNANCE_AUDIT_2026-08-08_ROUND2.md RD2-08, P1] docs/features/Status.md — Revision: 7, Last modified: 2026-06-16T23:30:00Z — same ~2-month staleness class as CONTINUATION.md. docs/codegraph/Status.md — Revision: 1, 2026-06-06T14:40:00Z — even further behind. Fix: fold into the same remediation pass as GA-04/GA-08 (RD2-16) since they share the exact root cause: the doc-sync mechanism was not invoked after the recent commit wave. Priority: P1 (same class as the already-P0-adjacent GA-04). Composes with RD2-16.

## BOB-076 — RD2-09: submodules/jackett fork 1 commit behind upstream (informational)

**Status:** Queued
**Type:** Task
**Severity:** Low

[Backfill from GOVERNANCE_AUDIT_2026-08-08_ROUND2.md RD2-09, P3 informational] git submodule status + fetch shows submodules/jackett 1 commit behind origin/master (e12342eb4, a trivial false-positive fix). All other submodules (constitution, challenges, containers, helixqa) are exactly at their upstream tip. Fix: bump when convenient; not blocking anything. Priority: P3. Canonical implementation: RD2-39.

## BOB-077 — RD2-10: Identify second host running the Auto-commit rsync/sync mechanism (OPERATOR-DECISION)

**Status:** Operator-blocked
**Type:** Task
**Operator-Block-Details:** WHAT: OPERATOR must identify which second host holds push credentials + confirms whether the rsync/sync mechanism is intentional or a stale job to retire. This session cannot inspect a host it has no access to (§11.4.6/§11.4.101). WHY: This session cannot inspect or reach the +0500 host that produced the Auto-commit fast-forwards (§11.4.6 no-guessing, §11.4.101 reversible-safe default). UNBLOCK: [A] operator names the second host + confirms intentional (proceed to RD2-11 wiring) · [B] operator confirms stale/misconfigured (retire the job) · [C] operator confirms the second live Claude session/device is the source (Rev-6 Update 2 root cause, proceed to per-session discipline enforcement) WHO: Operator
**Severity:** High

[Backfill from GOVERNANCE_AUDIT_2026-08-08_ROUND2.md RD2-10, P0 OPERATOR-DECISION] Root-caused as far as this host allows (see RD2-00 Update): reflog proves the two newest commits arrived via plain pull: Fast-forward from a +0500 host, matching this project established 2026-06-28 cross-host rsync-sync pattern (cdb555f/55b8671). Needs operator input to go further — which second host runs it, and is it the intended mechanism (just needs a real message + review gate) or a stale job to retire. Not auto-executed (§11.4.6/§11.4.101 — this session cannot inspect or guess at a host it has no access to). Rev-6 update: root cause narrowed to a second live Claude session (Opus 5, same +0500 host) that independently landed constitution 177f2b0. Priority: P0 (operator-blocked).

## BOB-078 — RD2-11: Once identified, wire Auto-commit mechanism through §11.4.234 dedicated commit/push script OR retire it

**Status:** Queued
**Type:** Task
**Severity:** High

[Backfill from GOVERNANCE_AUDIT_2026-08-08_ROUND2.md RD2-11, P0] Once identified (RD2-10): either wire it through a real §11.4.234 dedicated commit/push script (with the hook-validation stages this project already has via .claude/settings.json PreToolUse guard, extended to a real pre-commit content check) or shut it down if it serves no purpose. Priority: P0. Blocked on RD2-10.

## BOB-079 — RD2-12: Retroactive attributed history notes for GA-18/21/22/25/26/27 changes (never rewrite published history)

**Status:** Queued
**Type:** Task
**Severity:** Medium

[Backfill from GOVERNANCE_AUDIT_2026-08-08_ROUND2.md RD2-12, P1] Retroactively give proper, attributed, reviewed commit messages / history notes to the technically-correct changes the Auto-commit mechanism already made (GA-18, GA-21, GA-22, GA-25, GA-26, GA-27) — this can be a documentation/changelog note rather than a history rewrite (§11.4.113 — never rewrite published history), citing the git-history evidence per §11.4.124 investigate-before-attribute pattern. Priority: P1.

## BOB-080 — RD2-13: Retroactive Fable-xhigh code review of the substantive Auto-commit diffs

**Status:** Queued
**Type:** Task
**Severity:** High

[Backfill from GOVERNANCE_AUDIT_2026-08-08_ROUND2.md RD2-13, P1] Retroactively run the mandatory independent Fable-xhigh code review (§11.4.125/§11.4.142/§11.4.209) against the substantive diffs the Auto-commit mechanism introduced (start.sh three new functions especially, since they have zero test coverage — see Root Cause 4 / RD2-24) — even though the changes already landed, a post-hoc review closes the governance gap and will surface RD2-24 (GA-27 missing tests) if not already caught. Priority: P1.

## BOB-081 — RD2-14: Author CONTINUATION.md Session 15 entry (currently 53 days / 24+ commits behind HEAD)

**Status:** Queued
**Type:** Task
**Severity:** High

[Backfill from GOVERNANCE_AUDIT_2026-08-08_ROUND2.md RD2-14, P0 — closes GA-04] Author a new CONTINUATION.md Session 15 entry summarizing every substantive commit since 646b295 by theme (Cyrillic/UTF-8 fix wave, tracker/plugin fixes, egress/proxy/Jackett feature wave, the two governance audits, RD2-00 discovery). Update **Last commit:**/**Last modified:**/**Revision:**. GA-04 evidence: still Revision: 19, Last modified: 2026-06-16T23:55:00Z, Session 14 — ~53 days / 24+ commits behind HEAD. Priority: P0.

## BOB-082 — RD2-15: Create BOB-064..067 workable items for the four Lava-porting findings (closes GA-05)

**Status:** Queued
**Type:** Task
**Severity:** High

[Backfill from GOVERNANCE_AUDIT_2026-08-08_ROUND2.md RD2-15, P0 — closes GA-05] Create tracked workable items (BOB-064..067, via the workable-items tool — never raw MD edits) for the four Lava-porting findings, citing implementing commits as evidence, closed as Implemented. GA-05 evidence: grep -in lava|BOB-06[4-7] docs/Issues.md docs/Fixed.md returns zero hits. Priority: P0. NOTE: BOB-064..067 have been created 2026-08-10 as Task/Queued (the four Lava P1..P4 items); the closed-as-Implemented status flip (citing per-finding implementing commits) remains owed under this item.

## BOB-083 — RD2-16: Regenerate browser_extension/features/codegraph Status.md + Summary/HTML/PDF siblings

**Status:** Queued
**Type:** Task
**Severity:** Medium

[Backfill from GOVERNANCE_AUDIT_2026-08-08_ROUND2.md RD2-16, P1] Regenerate docs/browser_extension/Status.md, docs/features/Status.md, docs/codegraph/Status.md + their Status_Summary.md/HTML/PDF siblings (§11.4.45/§11.4.56). Priority: P1. Composes with RD2-08.

## BOB-084 — RD2-17: Reconcile BOB-008 DB/MD body drift via the workable-items tool

**Status:** Queued
**Type:** Task
**Severity:** High

[Backfill from GOVERNANCE_AUDIT_2026-08-08_ROUND2.md RD2-17, P1] Reconcile BOB-008 DB/MD body drift (RD2-04) via the workable-items tool. Priority: P1. Composes with RD2-04 (evidence source) and RD2-20 (preventive fix).

## BOB-085 — RD2-18: Create top-level Boba proxy/merge-service v1.0.0 readiness ledger (closes GA-10)

**Status:** Queued
**Type:** Task
**Severity:** Medium

[Backfill from GOVERNANCE_AUDIT_2026-08-08_ROUND2.md RD2-18, P2 — closes GA-10] Create the top-level Boba (proxy/merge-service) v1.0.0 readiness ledger (GA-10) — dedupe with the browser_extension existing one as the template. GA-10 evidence: only docs/RELEASE_READINESS_20260616.html/.md/.pdf (dated point-in-time snapshot) and the extension own ledger exist; no top-level proxy/merge-service ledger created. Priority: P2.

## BOB-086 — RD2-19: Fix BOB-009/BOB-010 evidence_path + backfill item_history for 56 silent closures

**Status:** Queued
**Type:** Task
**Severity:** Medium

[Backfill from GOVERNANCE_AUDIT_2026-08-08_ROUND2.md RD2-19, P2] Fix BOB-009/BOB-010 evidence_path values + backfill item_history audit trails for the 56 silent closures where recoverable from git log (RD2-03). Rev-6 note: no workable-items subcommand exists to fix a historical closure evidence_path — see Root Cause 2 in the audit. Priority: P2.

## BOB-087 — RD2-20: Wire docs_chain / commit-seam sync hook per §11.4.106(F) so DB writes cannot land without MD mirror

**Status:** Queued
**Type:** Task
**Severity:** High

[Backfill from GOVERNANCE_AUDIT_2026-08-08_ROUND2.md RD2-20, P0] Wire (or fix) the docs_chain / commit-seam sync hook per §11.4.106(F) so a docs/workable_items.db write can never again land without its MD mirror in the same commit — this is the mechanical fix that prevents Root Cause 2 from recurring, not just a one-time catch-up. Priority: P0.

## BOB-088 — RD2-21: Complete/verify README Tracked-Items + Status Documents table row-completeness (GA-07 remainder)

**Status:** Queued
**Type:** Task
**Severity:** Medium

[Backfill from GOVERNANCE_AUDIT_2026-08-08_ROUND2.md RD2-21, P1] Complete/verify the README Tracked-Items + Status Documents table row-completeness (GA-07 remaining half). Not independently re-verified this round whether every mandated doc (CONTINUATION.md, Issues.md, Fixed.md, PORTING-FROM-LAVA.md, both new GA/RD2 audit docs, every Status.md/Status_Summary.md pair) actually has a row. Priority: P1.

## BOB-089 — RD2-24: RED-first tests for start.sh reload_python/reload_plugins/recreate_stack (closes test-half of GA-27)

**Status:** Queued
**Type:** Task
**Severity:** High

[Backfill from GOVERNANCE_AUDIT_2026-08-08_ROUND2.md RD2-24, P1 TDD — closes test-coverage half of GA-27] Author RED-first tests for start.sh reload_python(), reload_plugins(), recreate_stack() — real executing tests through the actual invocation path (per §11.4.224(A): never a bash -n parse-check alone), asserting exit status + the documented side effects (pycache-clear-then-restart, restart-only, down-then-up) against a live or realistically-mocked container runtime. Verification: tests fail against a stubbed/reverted version of the three functions, pass against current start.sh (§11.4.115). GA-27 evidence: grep -rln reload_python|reload_plugins|recreate_stack tests/ challenges/ returns zero hits — shipped with no test-first coverage, a direct §11.4.224 violation. Priority: P1.

## BOB-090 — RD2-25: HelixQA Challenge entry exercising all three start.sh subcommands end-to-end against real compose stack

**Status:** Queued
**Type:** Task
**Severity:** Medium

[Backfill from GOVERNANCE_AUDIT_2026-08-08_ROUND2.md RD2-25, P2] Add a HelixQA Challenge entry exercising all three start.sh subcommands (reload_python, reload_plugins, recreate_stack) end-to-end against the real compose stack. Priority: P2.

## BOB-091 — RD2-26: Relocate mocked SearchOrchestrator tests to unit/ + author real-service replacements (closes GA-14/15/16)

**Status:** Queued
**Type:** Bug
**Severity:** High

[Backfill from GOVERNANCE_AUDIT_2026-08-08_ROUND2.md RD2-26, P1 — closes GA-14/15/16] For each of tests/integration/test_merge_api.py, tests/e2e/test_full_pipeline.py, tests/contract/test_tracker_stats_contract.py: (a) relocate the existing mocked version into tests/unit/ under an honest name (the coverage is valuable as unit-level route-contract testing — keep it, just where it belongs); (b) author a real-service replacement in the original directory using the repo existing live-stack fixtures (tests/fixtures/compose.py, tests/fixtures/services.py, tests/integration/test_fixtures_bring_up_services.py already prove this pattern works here). Verification: each relocated/replaced file directory-appropriate real-service test actually issues a real HTTP call to a real running service and asserts on the real response — no @patch/monkeypatch targeting SearchOrchestrator anywhere outside tests/unit/. Priority: P1.

## BOB-092 — RD2-27: Remove test_live_stack_evidence.py:265 nnmclub SKIP-on-404 fallback + verify live 200 (closes GA-13)

**Status:** Queued
**Type:** Bug
**Severity:** Medium

[Backfill from GOVERNANCE_AUDIT_2026-08-08_ROUND2.md RD2-27, P1 — closes GA-13] tests/e2e/test_live_stack_evidence.py:265 — with the live stack up, confirm curl :7187/api/v1/auth/nnmclub/status returns 200 (redeploy first if source≠artifact drift persists — see Root Cause 6), remove the skip fallback entirely, let the real assertion run. Priority: P1.

## BOB-093 — RD2-28: Live compose bring-up + verify rutracker ReDoS regex bounds deployed to container (closes runtime half of GA-12)

**Status:** Queued
**Type:** Task
**Severity:** High

[Backfill from GOVERNANCE_AUDIT_2026-08-08_ROUND2.md RD2-28, P1 — closes runtime-verification half of GA-12] Bring up the live compose stack (./start.sh), run ./install-plugin.sh, verify grep {0,512} config/qBittorrent/nova3/engines/rutracker.py on the container, and capture timing of a large rutracker result page (<2s per the original RW-06 acceptance criterion). GA-12 status: DONE (source) at plugins/rutracker.py:140 confirmed {0,512}/{0,256}-bounded; runtime unverified (no live container stack running at investigation time). Priority: P1.

## BOB-094 — RD2-29: Author tests/stress/test_tracker_fetch_stress_chaos.py with §11.4.85 fault injection

**Status:** Queued
**Type:** Task
**Severity:** Medium

[Backfill from GOVERNANCE_AUDIT_2026-08-08_ROUND2.md RD2-29, P2, parallelizable] Author tests/stress/test_tracker_fetch_stress_chaos.py (download-proxy tracker-fetch + cookie-auth path, overlapping the already-fixed SSRF surface) with real §11.4.85 fault injection (process-kill, network-fault, resource-exhaustion — not just concurrency). Verification: each new chaos test is negation-proven (fails without the fault-tolerance code, passes with it), captured evidence per §11.4.5/§11.4.69/§11.4.107. Priority: P2. Composes with GA-20.

## BOB-095 — RD2-30: Author tests/stress/test_scheduler_hooks_sse_stress_chaos.py for Go-side triangle

**Status:** Queued
**Type:** Task
**Severity:** Medium

[Backfill from GOVERNANCE_AUDIT_2026-08-08_ROUND2.md RD2-30, P2, parallelizable] Author tests/stress/test_scheduler_hooks_sse_stress_chaos.py covering the Go-side internal/service/sse_broker.go + internal/api/hooks.go + internal/api/scheduler_api.go triangle. Verification: each new chaos test is negation-proven (fails without the fault-tolerance code, passes with it), captured evidence per §11.4.5/§11.4.69/§11.4.107. Priority: P2. Composes with GA-20.

## BOB-096 — RD2-31: Extend qBitTorrent-go jackett_db_test.go with real process-kill/resource-exhaustion fault injection

**Status:** Queued
**Type:** Task
**Severity:** Medium

[Backfill from GOVERNANCE_AUDIT_2026-08-08_ROUND2.md RD2-31, P2] Extend qBitTorrent-go/tests/integration/jackett_db_test.go with real process-kill / resource-exhaustion fault injection (currently concurrency-only per GA-20). Priority: P2.

## BOB-097 — RD2-32: Author DDoS-class coverage for exposed download-proxy/merge endpoints (canonical impl of RD2-07)

**Status:** Queued
**Type:** Task
**Severity:** Low

[Backfill from GOVERNANCE_AUDIT_2026-08-08_ROUND2.md RD2-32, P3] Author DDoS-class coverage (RD2-07) for the exposed download-proxy/merge endpoints. Priority: P3.

## BOB-098 — RD2-34: Parametrize 20 hardcoded /Volumes/T7 paths in helixqa banks with PROJECT_ROOT (closes GA-23)

**Status:** Queued
**Type:** Task
**Severity:** Medium

[Backfill from GOVERNANCE_AUDIT_2026-08-08_ROUND2.md RD2-34, P1 — closes GA-23] submodules/helixqa/banks/*.yaml — parametrize the 20 hardcoded /Volumes/T7/Projects/Boba/... paths with $PROJECT_ROOT (GA-23) — lands in the submodule per §11.4.28 decoupling, not boba own tree. GA-23 evidence: grep -rn /Volumes/T7 submodules/helixqa/banks/*.yaml returns 20 hits. Priority: P1.

## BOB-099 — RD2-36: Fix guard-forbidden-commands.sh substring-match false-positive class + add const033-poweroff-signal-triage carrier to EXCLUDE_PATHS

**Status:** Queued
**Type:** Bug
**Severity:** Medium

[Backfill from GOVERNANCE_AUDIT_2026-08-08_ROUND2.md RD2-36, P2] Fix guard-forbidden-commands.sh substring-match false-positive class (RD2-01) — word-boundary/token-aware matching, not another EXCLUDE_PATHS band-aid; also add the newly-discovered docs/incidents/2026-08-07-const033-poweroff-signal-triage.md carrier to EXCLUDE_PATHS as an immediate stopgap (GA-24 residual). Priority: P2. Composes with RD2-01, GA-24 residual, and RD2-41 (same class in mutation-marker scan).

## BOB-100 — RD2-39: Bump submodules/jackett one commit (canonical impl of RD2-09)

**Status:** Queued
**Type:** Task
**Severity:** Low

[Backfill from GOVERNANCE_AUDIT_2026-08-08_ROUND2.md RD2-39, P3] Bump submodules/jackett one commit (RD2-09). Priority: P3.

## BOB-101 — GA-19/RW-09: Is --profile go parity still a release goal? (gates RW-10..13) — OPERATOR-DECISION

**Status:** Operator-blocked
**Type:** Task
**Operator-Block-Details:** WHAT: OPERATOR must decide whether Go --profile go parity remains a v1.0.0 release goal; gates downstream RW-10..13. WHY: §11.4.66 forbids autonomous decision on release scope; §11.4.122 forbids silent removal of an existing capability. UNBLOCK: [A] operator states YES — parity remains a release goal (schedule RW-10..13 work) · [B] operator states NO — mark parity Obsolete/superseded per §11.4.90 (reason=feature-removed with operator citation, §11.4.122) WHO: Operator
**Severity:** High

[Backfill from GOVERNANCE_AUDIT_2026-08-08_ROUND2.md GA-19/RW-09, OPERATOR-DECISION] Confirmed unchanged: zero time.Ticker anywhere in qBitTorrent-go, no enricher package, zero exec.Command fan-out. Is --profile go parity still a release goal? Gates RW-10..13. Surfaced only, not auto-executed, per §11.4.66. Priority: OPERATOR-DECISION.

## BOB-102 — RW-05: LAN-exposure threat model — bind tunnel 127.0.0.1 or keep 0.0.0.0? — OPERATOR-DECISION

**Status:** Operator-blocked
**Type:** Task
**Operator-Block-Details:** WHAT: OPERATOR must decide LAN-exposure posture: bind tunnel to 127.0.0.1 (loopback-only) OR keep 0.0.0.0 (LAN-reachable, relying on post-RD2-22 complete auth coverage). WHY: This is a security-posture policy call the agent cannot make autonomously (§11.4.66 operator-decision, §11.4.101 high-blast-radius reversible-only-if-explicit). UNBLOCK: [A] operator states BIND 127.0.0.1 (loopback-only; agent will change compose/service binding + regression-test LAN unreachability) · [B] operator states KEEP 0.0.0.0 (rely on §RD2-22 completed auth coverage; agent will add a permanent §11.4.135 LAN-auth regression guard) WHO: Operator
**Severity:** Medium

[Backfill from GOVERNANCE_AUDIT_2026-08-08_ROUND2.md RW-05 ungrouped, OPERATOR-DECISION] LAN-exposure threat model — bind the tunnel 127.0.0.1 or keep 0.0.0.0 with the now-complete auth coverage (post Root Cause 3)? Priority: OPERATOR-DECISION.

