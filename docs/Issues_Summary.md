# Issues_Summary

Open workable items (current_location = Issues), regenerated from the SQLite single-source-of-truth (§11.4.12).

## Counts by Type × Status

| Type | Status | Count |
|---|---|---|
| Bug | Fixed (→ Fixed.md) | 9 |
| Bug | In progress | 2 |
| Bug | Operator-blocked | 1 |
| Bug | Queued | 8 |
| Bug | Ready for testing | 1 |
| Task | Completed (→ Fixed.md) | 1 |
| Task | In progress | 9 |
| Task | Operator-blocked | 3 |
| Task | Queued | 17 |
| Task | Ready for testing | 2 |
| **TOTAL** | | **53** |

## Items

| ATM ID | Type | Status | Severity | Description |
|---|---|---|---|---|
| BOB-008 | Bug | Operator-blocked | — | RuTracker automated login blocked by CAPTCHA |
| BOB-065 | Task | Queued | High | Lava P2: Egress diagnosis and VPN-host SOCKS routing (containers pkg/egress) |
| BOB-066 | Task | In progress | High | Lava P3: BOBA_UPSTREAM_PROXY in download-proxy + qBitTorrent-go + Jackett + compose env-forward |
| BOB-068 | Bug | In progress | High | RD2-00: unattributed, unreviewed Auto-commit mechanism pushing to main |
| BOB-069 | Task | In progress | High | RD2-40: §11.4.238 QA-discovery-channel ledger — ongoing coverage-escape backfill |
| BOB-074 | Task | In progress | Medium | RD2-07: DDoS-class testing fully absent from the mandated test-type matrix |
| BOB-077 | Task | Operator-blocked | High | RD2-10: Identify second host running the Auto-commit rsync/sync mechanism (OPERATOR-DECISION) |
| BOB-078 | Task | Queued | High | RD2-11: Once identified, wire Auto-commit mechanism through §11.4.234 dedicated commit/push script OR retire it |
| BOB-079 | Task | Queued | Medium | RD2-12: Retroactive attributed history notes for GA-18/21/22/25/26/27 changes (never rewrite published history) |
| BOB-080 | Task | Queued | High | RD2-13: Retroactive Fable-xhigh code review of the substantive Auto-commit diffs |
| BOB-082 | Task | Queued | High | RD2-15: Create BOB-064..067 workable items for the four Lava-porting findings (closes GA-05) |
| BOB-085 | Task | Queued | Medium | RD2-18: Create top-level Boba proxy/merge-service v1.0.0 readiness ledger (closes GA-10) |
| BOB-087 | Task | Completed (→ Fixed.md) | High | RD2-20: Wire docs_chain / commit-seam sync hook per §11.4.106(F) so DB writes cannot land without MD mirror |
| BOB-088 | Task | Queued | Medium | RD2-21: Complete/verify README Tracked-Items + Status Documents table row-completeness (GA-07 remainder) |
| BOB-090 | Task | In progress | Medium | RD2-25: HelixQA Challenge entry exercising all three start.sh subcommands end-to-end against real compose stack |
| BOB-092 | Bug | Queued | Medium | RD2-27: Remove test_live_stack_evidence.py:265 nnmclub SKIP-on-404 fallback + verify live 200 (closes GA-13) |
| BOB-093 | Task | In progress | High | RD2-28: Live compose bring-up + verify rutracker ReDoS regex bounds deployed to container (closes runtime half of GA-12) |
| BOB-094 | Task | In progress | Medium | RD2-29: Author tests/stress/test_tracker_fetch_stress_chaos.py with §11.4.85 fault injection |
| BOB-095 | Task | In progress | Medium | RD2-30: Author tests/stress/test_scheduler_hooks_sse_stress_chaos.py for Go-side triangle |
| BOB-097 | Task | Queued | Low | RD2-32: Author DDoS-class coverage for exposed download-proxy/merge endpoints (canonical impl of RD2-07) |
| BOB-100 | Task | Queued | Low | RD2-39: Bump submodules/jackett one commit (canonical impl of RD2-09) |
| BOB-101 | Task | Operator-blocked | High | GA-19/RW-09: Is --profile go parity still a release goal? (gates RW-10..13) — OPERATOR-DECISION |
| BOB-102 | Task | Operator-blocked | Medium | RW-05: LAN-exposure threat model — bind tunnel 127.0.0.1 or keep 0.0.0.0? — OPERATOR-DECISION |
| BOB-104 | Task | In progress | Medium | §11.4.238 followup: CodeGraph 1.5.0 nested-.gitignore regression challenge |
| BOB-106 | Task | Queued | Medium | §11.4.238 followup: §11.4.84 quiescence-check helper for the unattributed auto-commit path |
| BOB-107 | Task | Queued | Medium | §11.4.238 followup: pre-dispatch existence check for subagent task-brief source inputs |
| BOB-109 | Task | Queued | Medium | BOB-074 followup: scaling-class test coverage absent from mandated test-type matrix |
| BOB-110 | Task | Queued | Medium | BOB-074 followup: UX-class test coverage (accessibility/usability) absent |
| BOB-111 | Task | In progress | High | BOB-074 followup: configure real rate limiting for boba's 3 public HTTP endpoints |
| BOB-114 | Task | Queued | Medium | BOB-074 followup: self-validation golden-bad fixture for the rate-limit detector |
| BOB-120 | Bug | Queued | Critical | 3rd forced-logout incident 2026-08-18 23:45:49 — SIGKILL user@1000 + preventive-timer-inside-user-slice architectural gap |
| BOB-121 | Task | Ready for testing | Important | External watchdog for the forced-logout architectural gap (task #85, incident #3) |
| BOB-129 | Bug | Fixed (→ Fixed.md) | Medium | Potential production slowapi/starlette defect flagged by Task 105 subagent |
| BOB-131 | Bug | Fixed (→ Fixed.md) | Medium | qbittorrent-proxy podman conmon crash — pre-existing, surfaced during BOB-129 investigation |
| BOB-135 | Bug | Queued | Low | Test isolation: test_list_hooks_after_create fails in bulk suite (Permission denied /config) |
| BOB-136 | Task | Ready for testing | High | Closure seam does not bind: 4 tracker rows found stale in one sweep, and workable-items diff is blind to body_md drift |
| BOB-137 | Bug | In progress | High | Merge service on 7187 wedges while the same process still serves 7186 (GIL starvation by one spinning thread) |
| BOB-141 | Task | Queued | Low | CLAUDE.md claims the Go profile serves 7186/7187/7188 but its container binds only 7187 — doc contradicts the Dockerfile |
| BOB-143 | Bug | Queued | Medium | Orphaned .worktrees/ dirs (46M, unresolvable gitdir) pollute gate scan scope and manufacture false BOB-126-class findings |
| BOB-144 | Bug | Fixed (→ Fixed.md) | Low | /theme/stream calls the disconnect probe unguarded — fail-closed but via an uncaught traceback, inconsistent with the two SSE generators |
| BOB-145 | Bug | Fixed (→ Fixed.md) | High | Fix the 7187 wedge: offload and/or memoise Deduplicator.merge_results so O(N^2) regex work stops blocking the asyncio event loop |
| BOB-146 | Bug | Fixed (→ Fixed.md) | High | Constitution §11.4.252 detector undercounts by 29% (30 vs 42 AST ground truth) — 4 distinct blind spots make its output a floor, not a census |
| BOB-148 | Bug | Fixed (→ Fixed.md) | Medium | Standing red unit test nothing tracked: test_no_credentials asserts has_session False, gets True — real defect or non-hermetic test, undecided |
| BOB-149 | Bug | Queued | Low | Managed-plugin count diverges 43/42/48 across constitution, CLAUDE.md and the README badge; the badge is hand-maintained and unguarded |
| BOB-150 | Task | Queued | Low | pre_build_verification.sh invariant labels read N/44 but only 35 invariants are labelled |
| BOB-151 | Task | Queued | Medium | CM-SCRIPT-DOCS-SYNC is a named gate with no implementation, and 24 of 36 scripts have no companion doc |
| BOB-152 | Bug | Queued | Medium | Constitution sweep walks vendored third-party code: 82% of one gate's 38,291 findings come from submodules/ |
| BOB-153 | Bug | Fixed (→ Fixed.md) | Medium | Go profile cannot build: go.mod requires go 1.26.2 but the Dockerfile builder is golang:1.23-alpine |
| BOB-154 | Bug | Ready for testing | Medium | Host venv and production container run different starlette versions (1.4.1 vs 1.6.0) |
| BOB-155 | Bug | Fixed (→ Fixed.md) | High | workable-items diff reports 'DB and Markdown are in sync' having opened zero Markdown files when --issues/--fixed are omitted |
| BOB-156 | Bug | Queued | Medium | BOB-145 event-loop regression guard is load-sensitive and flaky: 8786ms under host load vs a 900-1500ms ceiling calibrated on a quiet host |
| BOB-157 | Bug | Fixed (→ Fixed.md) | High | Our own BOB-137 stall watchdog can segfault the merge service: faulthandler dump_traceback(all_threads=True) hits an unpatched CPython 3.12 defect |
| BOB-158 | Bug | Queued | High | tests/conftest.py cannot run on the production interpreter: binds asyncio.events._get_event_loop_policy, a 3.13+ private API, while production is 3.12.13 |
