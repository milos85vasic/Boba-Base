# Issues_Summary

Open workable items (current_location = Issues), regenerated from the SQLite single-source-of-truth (§11.4.12).

## Counts by Type × Status

| Type | Status | Count |
|---|---|---|
| Bug | Operator-blocked | 1 |
| Bug | Queued | 6 |
| Task | In progress | 1 |
| Task | Operator-blocked | 3 |
| Task | Queued | 28 |
| **TOTAL** | | **39** |

## Items

| ATM ID | Type | Status | Severity | Description |
|---|---|---|---|---|
| BOB-008 | Bug | Operator-blocked | — | RuTracker automated login blocked by CAPTCHA |
| BOB-065 | Task | Queued | High | Lava P2: Egress diagnosis and VPN-host SOCKS routing (containers pkg/egress) |
| BOB-066 | Task | In progress | High | Lava P3: BOBA_UPSTREAM_PROXY in download-proxy + qBitTorrent-go + Jackett + compose env-forward |
| BOB-068 | Bug | Queued | High | RD2-00: unattributed, unreviewed Auto-commit mechanism pushing to main |
| BOB-069 | Task | Queued | High | RD2-40: §11.4.238 QA-discovery-channel ledger — ongoing coverage-escape backfill |
| BOB-070 | Bug | Queued | High | RD2-41: pre-build mutation-marker scan carrier false-positive silently defeats entire pre-build gate |
| BOB-071 | Bug | Queued | Medium | RD2-01: guard-forbidden-commands.sh hook has live reproducible substring carrier false-positive |
| BOB-074 | Task | Queued | Medium | RD2-07: DDoS-class testing fully absent from the mandated test-type matrix |
| BOB-076 | Task | Queued | Low | RD2-09: submodules/jackett fork 1 commit behind upstream (informational) |
| BOB-077 | Task | Operator-blocked | High | RD2-10: Identify second host running the Auto-commit rsync/sync mechanism (OPERATOR-DECISION) |
| BOB-078 | Task | Queued | High | RD2-11: Once identified, wire Auto-commit mechanism through §11.4.234 dedicated commit/push script OR retire it |
| BOB-079 | Task | Queued | Medium | RD2-12: Retroactive attributed history notes for GA-18/21/22/25/26/27 changes (never rewrite published history) |
| BOB-080 | Task | Queued | High | RD2-13: Retroactive Fable-xhigh code review of the substantive Auto-commit diffs |
| BOB-081 | Task | Queued | High | RD2-14: Author CONTINUATION.md Session 15 entry (currently 53 days / 24+ commits behind HEAD) |
| BOB-082 | Task | Queued | High | RD2-15: Create BOB-064..067 workable items for the four Lava-porting findings (closes GA-05) |
| BOB-083 | Task | Queued | Medium | RD2-16: Regenerate browser_extension/features/codegraph Status.md + Summary/HTML/PDF siblings |
| BOB-084 | Task | Queued | High | RD2-17: Reconcile BOB-008 DB/MD body drift via the workable-items tool |
| BOB-085 | Task | Queued | Medium | RD2-18: Create top-level Boba proxy/merge-service v1.0.0 readiness ledger (closes GA-10) |
| BOB-086 | Task | Queued | Medium | RD2-19: Fix BOB-009/BOB-010 evidence_path + backfill item_history for 56 silent closures |
| BOB-087 | Task | Queued | High | RD2-20: Wire docs_chain / commit-seam sync hook per §11.4.106(F) so DB writes cannot land without MD mirror |
| BOB-088 | Task | Queued | Medium | RD2-21: Complete/verify README Tracked-Items + Status Documents table row-completeness (GA-07 remainder) |
| BOB-089 | Task | Queued | High | RD2-24: RED-first tests for start.sh reload_python/reload_plugins/recreate_stack (closes test-half of GA-27) |
| BOB-090 | Task | Queued | Medium | RD2-25: HelixQA Challenge entry exercising all three start.sh subcommands end-to-end against real compose stack |
| BOB-091 | Bug | Queued | High | RD2-26: Relocate mocked SearchOrchestrator tests to unit/ + author real-service replacements (closes GA-14/15/16) |
| BOB-092 | Bug | Queued | Medium | RD2-27: Remove test_live_stack_evidence.py:265 nnmclub SKIP-on-404 fallback + verify live 200 (closes GA-13) |
| BOB-093 | Task | Queued | High | RD2-28: Live compose bring-up + verify rutracker ReDoS regex bounds deployed to container (closes runtime half of GA-12) |
| BOB-094 | Task | Queued | Medium | RD2-29: Author tests/stress/test_tracker_fetch_stress_chaos.py with §11.4.85 fault injection |
| BOB-095 | Task | Queued | Medium | RD2-30: Author tests/stress/test_scheduler_hooks_sse_stress_chaos.py for Go-side triangle |
| BOB-096 | Task | Queued | Medium | RD2-31: Extend qBitTorrent-go jackett_db_test.go with real process-kill/resource-exhaustion fault injection |
| BOB-097 | Task | Queued | Low | RD2-32: Author DDoS-class coverage for exposed download-proxy/merge endpoints (canonical impl of RD2-07) |
| BOB-098 | Task | Queued | Medium | RD2-34: Parametrize 20 hardcoded /Volumes/T7 paths in helixqa banks with PROJECT_ROOT (closes GA-23) |
| BOB-099 | Bug | Queued | Medium | RD2-36: Fix guard-forbidden-commands.sh substring-match false-positive class + add const033-poweroff-signal-triage carrier to EXCLUDE_PATHS |
| BOB-100 | Task | Queued | Low | RD2-39: Bump submodules/jackett one commit (canonical impl of RD2-09) |
| BOB-101 | Task | Operator-blocked | High | GA-19/RW-09: Is --profile go parity still a release goal? (gates RW-10..13) — OPERATOR-DECISION |
| BOB-102 | Task | Operator-blocked | Medium | RW-05: LAN-exposure threat model — bind tunnel 127.0.0.1 or keep 0.0.0.0? — OPERATOR-DECISION |
| BOB-104 | Task | Queued | Medium | Coverage-escape followup (docs/QA_DISCOVERY_LEDGER.md, BOB-075 agent-code-reading finding, commit e6162f7): CodeGraph 1.5.0 (up from documented 0.9.9) walked into nested-.gitignore-excluded frontend/node_modules and extension/node_modules (32,260 files / 514,456 nodes vs the 2026-06-06 baseline of 509 files / 8,906 nodes) instead of honoring frontend/.gitignore + extension/.gitignore per git check-ignore -v. Author a challenge (challenges/scripts/codegraph_gitignore_honor_challenge.sh or equivalent, e.g. wrapping 'codegraph doctor --sniff-gitignore-honor' if that subcommand exists, else a real re-index + file-count assertion) with §11.4.115 RED_MODE polarity: RED_MODE=1 reproduces the blowup against the live nested-.gitignore tree, RED_MODE=0 asserts the resync stays within the documented baseline order of magnitude. Full evidence: docs/codegraph/Status.md lines 91-118. |
| BOB-105 | Task | Queued | Medium | Coverage-escape followup (docs/QA_DISCOVERY_LEDGER.md, meta-defect found during this session's §11.4.140/141 collision resolution, boba commit 136a22c + constitution commits 5ed8c80..e5f2891): §11.4.227(B) anchor-block-integrity (exactly-once heading per anchor per governance file, byte-identical lockstep across mirrors, no anchor-number collision) is fully specified in constitution prose but its own named gate CM-ANCHOR-BLOCK-INTEGRITY is explicitly 'gate-code = separate work item, NOT claimed shipped' — the §11.4.140/§11.4.141 double-mandate collision this session's Phase 0 resolved was verified entirely BY HAND (md5 of moved anchor bodies, manual grep counts pasted into a commit message), not by a runnable script. Propose + author a challenge (in this project's challenges/scripts/, since this project cannot edit the constitution submodule's own gate-code from this ticket) that greps every governance file (CLAUDE.md/AGENTS.md/QWEN.md/GEMINI.md/Constitution.md, wherever this project's constitution submodule checkout exposes them) for '### §11.4.NNN' heading occurrences and FAILs on >1-per-file-per-anchor or on two DIFFERENT anchor bodies sharing one NNN, per §11.4.227(B). Do NOT touch constitution-owned files while implementing this — the check reads them read-only. |
| BOB-106 | Task | Queued | Medium | Coverage-escape followup (docs/QA_DISCOVERY_LEDGER.md RD2-00/BOB-068 entry, docs/GOVERNANCE_AUDIT_2026-08-08_ROUND2.md RD2-00): 20 bare 'Auto-commit' commits exist in this repo's git history (confirmed via git log --oneline --all --grep, e.g. 54e313f/9c8f684/743097a/de9270b/1c36777/41179c2/7c529ca) with no ATM-NNN reference and no TDD trail, landing via ordinary git pull fast-forward from a second session/host with push access to the same remotes (mismatched commit timezone vs the investigating host, per RD2-00 Update). §11.4.84 working-tree-quiescence has no mechanical guard on this path — no gate flags a commit reaching main with a bare/templated message and no ticket citation. Author a §11.4.84 quiescence-check helper (e.g. challenges/scripts/no_unattributed_autocommit_challenge.sh) that scans the commit range since the last known-good release tag and FAILs on any commit message matching a closed bare/templated pattern (e.g. ^Auto-commit$, ^sync: ) with no ATM-NNN or task/PR reference, wired into scripts/pre_build_verification.sh or the §11.4.234 commit-push-all.sh entrypoint. BOB-068 (RD2-00) remains the tracking item for identifying/stopping the source; this item is specifically the new automated CHECK. |
| BOB-107 | Task | Queued | Medium | Coverage-escape followup (docs/QA_DISCOVERY_LEDGER.md SCRATCH-LOSS-2026-08-18 entry, evidence: .superpowers/sdd/task-phase1a-report.md line 21): the Phase 1a subagent (a1cc331d) discovered at task start that 5 source files its brief named as required reads (curriculum_amendment_plan_v1.md, ai_curriculum_modules_27_35_extracted.md, and 3 curriculum_analysis_modules_*.md gap analyses) were absent from the session scratchpad — root cause per that subagent's own investigation: the prior producer subagent (ae59171f) hit its session rate limit (a §11.4.147(e) API-quota crash) before writing them. curriculum_amendment_plan_v1.md remains absent from the live scratchpad as of this session's re-check. No mechanical check verifies a task brief's declared input files exist and are non-empty before the downstream consumer subagent is dispatched. Author a pre-dispatch precondition helper (project-side orchestration tooling, e.g. a small script the conductor runs before Task/Agent dispatch when a brief names required input paths) that fails closed with an actionable 'missing input, respawn the producer' message rather than silently letting a downstream agent proceed on absent evidence and fabricate content unsupported by its named sources. |
