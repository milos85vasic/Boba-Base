# Fixed_Summary

Closed workable items (current_location = Fixed), regenerated from the SQLite single-source-of-truth (§11.4.53).

## Counts by Type × Status

| Type | Status | Count |
|---|---|---|
| Bug | Fixed (→ Fixed.md) | 22 |
| Feature | Implemented (→ Fixed.md) | 17 |
| Task | Completed (→ Fixed.md) | 13 |
| Task | Fixed (→ Fixed.md) | 4 |
| Task | Implemented (→ Fixed.md) | 17 |
| **TOTAL** | | **73** |

## Items

| # | Level | Status | Type | Fixed-In Tag(s) | One-line description |
|---|---|---|---|---|---|
| 1 | — | Fixed (→ Fixed.md) | Bug | — | BOB-001 — start.sh BSD-sed incompatibility aborted the boot |
| 2 | — | Fixed (→ Fixed.md) | Bug | — | BOB-002 — start.sh `podman unshare` incompatible with macOS remote podman |
| 3 | — | Fixed (→ Fixed.md) | Bug | — | BOB-003 — macOS tunnel port detection broken (ports never forwarded) |
| 4 | — | Completed (→ Fixed.md) | Task | — | BOB-004 — Private-tracker credentials stored securely + verified working |
| 5 | — | Fixed (→ Fixed.md) | Task | — | BOB-005 — Public-tracker plugins all raised an unhandled exception (systemic) |
| 6 | — | Implemented (→ Fixed.md) | Feature | — | BOB-006 — NNMClub username/password login wired — NNMClub now uses the operator's `NNMCLUB_USERNAME`/`NNMCLUB_PASSWORD` (in . |
| 7 | — | Completed (→ Fixed.md) | Task | — | BOB-007 — RuTor documented as public (no-auth) — RuTor is a public tracker with no login endpoint; `RUTOR_USERNAME/PASSWORD` are |
| 8 | — | Completed (→ Fixed.md) | Task | — | BOB-009 — Containers submodule integrated with Go wrapper |
| 9 | — | Completed (→ Fixed.md) | Task | — | BOB-010 — Workable-items SQLite DB integrated + pre-build gate wired (§11.4.93/§11.4.95) |
| 10 | — | Implemented (→ Fixed.md) | Feature | — | BOB-011 — DOCX export support added — `generate_markdown_exports. |
| 11 | — | Completed (→ Fixed.md) | Task | — | BOB-012 — Export-sync gate expanded to all docs (§11.4.65) |
| 12 | — | Fixed (→ Fixed.md) | Bug | — | BOB-013 — torrentkitty `_parse_size` reported 0 for every KB/MB/GB/TB size |
| 13 | — | Fixed (→ Fixed.md) | Bug | — | BOB-014 — Go `generateID()` collided under burst (UnixNano-only) |
| 14 | — | Fixed (→ Fixed.md) | Task | — | BOB-015 — Remaining public-tracker failures are external / non-deterministic |
| 15 | — | Fixed (→ Fixed.md) | Task | — | BOB-016 — Jackett plugin crashed (`Pool(0)`) when zero indexers are configured |
| 16 | — | Fixed (→ Fixed.md) | Bug | — | BOB-017 — NNMClub plugin self-heal crashed on invalid ICON |
| 17 | — | Completed (→ Fixed.md) | Task | — | BOB-018 — Jackett server image updated to latest |
| 18 | — | Completed (→ Fixed.md) | Task | — | BOB-019 — Jackett added as a reference submodule (latest release) |
| 19 | — | Completed (→ Fixed.md) | Task | — | BOB-020 — CodeGraph initialized + wired (§11.4.78/79/80) |
| 20 | — | Fixed (→ Fixed.md) | Bug | — | BOB-021 — env_loader flaky test: KEY2 leak across test ordering |
| 21 | — | Fixed (→ Fixed.md) | Bug | — | BOB-022 — AsyncMock warning in search deep-coverage tests |
| 22 | — | Implemented (→ Fixed.md) | Feature | — | BOB-023 — gamestorrents plugin deep-coverage tests + B-substring bug documented |
| 23 | — | Fixed (→ Fixed.md) | Bug | — | BOB-024 — gamestorrents `_parse_size` B-substring bug fixed |
| 24 | — | Implemented (→ Fixed.md) | Feature | — | BOB-025 — eztv.py deep-coverage tests (54 tests) — 54 tests covering MyHtmlParser (size units, date patterns, defaults, special chars), |
| 25 | — | Implemented (→ Fixed.md) | Feature | — | BOB-026 — piratebay.py deep-coverage tests + import-order bug documented |
| 26 | — | Implemented (→ Fixed.md) | Feature | — | BOB-027 — solidtorrents.py deep-coverage tests (37 tests) |
| 27 | — | Implemented (→ Fixed.md) | Feature | — | BOB-028 — limetorrents.py deep-coverage tests (52 tests) |
| 28 | — | Implemented (→ Fixed.md) | Feature | — | BOB-029 — torlock.py deep-coverage tests (55 tests) |
| 29 | — | Implemented (→ Fixed.md) | Feature | — | BOB-030 — nyaa.py deep-coverage tests + missing import re bug documented |
| 30 | — | Implemented (→ Fixed.md) | Feature | — | BOB-031 — kickass.py deep-coverage tests + comma-size gap documented |
| 31 | — | Implemented (→ Fixed.md) | Feature | — | BOB-032 — anilibra.py deep-coverage tests (49 tests) |
| 32 | — | Fixed (→ Fixed.md) | Bug | — | BOB-033 — kickass.py crash guards added (BOB-015 defense-in-depth) |
| 33 | — | Implemented (→ Fixed.md) | Feature | — | BOB-034 — torrentgalaxy.py + yts.py deeper coverage (80 new tests) |
| 34 | — | Fixed (→ Fixed.md) | Bug | — | BOB-035 — nyaa.py missing import re fixed — `download_torrent()` called `re. |
| 35 | — | Fixed (→ Fixed.md) | Bug | — | BOB-036 — kickass.py comma-separated size regex fixed |
| 36 | — | Implemented (→ Fixed.md) | Feature | — | BOB-037 — rutor.py deep-coverage tests (83 tests) — 83 tests covering date normalization, pagination math, config, proxy, |
| 37 | — | Implemented (→ Fixed.md) | Feature | — | BOB-038 — tokyotoshokan.py deep-coverage tests (60 tests) |
| 38 | — | Implemented (→ Fixed.md) | Feature | — | BOB-039 — snowfl.py deep-coverage tests (30 tests) |
| 39 | — | Implemented (→ Fixed.md) | Feature | — | BOB-040 — torrentdownload.py deep-coverage tests (35 tests) |
| 40 | — | Implemented (→ Fixed.md) | Feature | — | BOB-041 — linuxtracker.py deep-coverage tests (30 tests) |
| 41 | — | Implemented (→ Fixed.md) | Task | — | BOB-042 — audiobookbay.py deep-coverage tests + missing import re fixed |
| 42 | — | Implemented (→ Fixed.md) | Task | — | BOB-043 — one337x.py deep-coverage tests + B-substring fixed |
| 43 | — | Implemented (→ Fixed.md) | Task | — | BOB-044 — extratorrent.py deep-coverage tests + B-substring fixed |
| 44 | — | Implemented (→ Fixed.md) | Task | — | BOB-045 — torrentfunk.py deep-coverage tests + B-substring fixed |
| 45 | — | Implemented (→ Fixed.md) | Task | — | BOB-046 — torrentproject.py deep-coverage tests — 36 tests covering MyHTMLParser (handle_starttag/endtag/data), feed, fetch_magnet. |
| 46 | — | Implemented (→ Fixed.md) | Task | — | BOB-047 — therarbg.py deep-coverage tests + B-substring fixed |
| 47 | — | Implemented (→ Fixed.md) | Task | — | BOB-048 — academictorrents.py deep-coverage tests — 48 tests covering XML parsing, concurrent. |
| 48 | — | Implemented (→ Fixed.md) | Task | — | BOB-049 — ali213.py deep-coverage tests — 25 tests covering threaded gamepage handling, retry loop (20 ceiling), magnet extraction. |
| 49 | — | Implemented (→ Fixed.md) | Task | — | BOB-050 — yourbittorrent.py deep-coverage tests — 30 tests covering HTMLParser, download_file, 7 categories. |
| 50 | — | Implemented (→ Fixed.md) | Task | — | BOB-051 — glotorrents.py deep-coverage tests — 40 tests covering pagination, 9 categories, magnet extraction, sleep. |
| 51 | — | Implemented (→ Fixed.md) | Task | — | BOB-052 — pctorrent.py deep-coverage tests + B-substring pre-fixed |
| 52 | — | Implemented (→ Fixed.md) | Task | — | BOB-053 — rockbox.py deep-coverage tests — 32 tests covering datetime, sleep(3) pagination, kb/mb/gb sizes. |
| 53 | — | Implemented (→ Fixed.md) | Task | — | BOB-054 — bitru.py deep-coverage tests + B-substring fixed |
| 54 | — | Implemented (→ Fixed.md) | Task | — | BOB-055 — btsow.py deep-coverage tests — Tests covering data-list card parsing, search, download_torrent. |
| 55 | — | Implemented (→ Fixed.md) | Task | — | BOB-056 — torrentscsv.py deep-coverage tests — 33 tests covering CSV parsing, search, download_torrent. |
| 56 | — | Implemented (→ Fixed.md) | Task | — | BOB-057 — xfsub.py deep-coverage tests + B-substring fixed |
| 57 | — | Implemented (→ Fixed.md) | Task | — | BOB-058 — yihua.py deep-coverage tests + B-substring fixed |
| 58 | — | Fixed (→ Fixed.md) | Task | — | BOB-059 — bt4g.py tests fixed (was hanging) — 3 tests had bugs: infinite loop from constant `return_value` (should use |
| 59 | Low | Fixed (→ Fixed.md) | Bug | — | BOB-060 — Public-tracker plugins crash on degenerate/empty upstream responses |
| 60 | High | Fixed (→ Fixed.md) | Bug | — | BOB-061 — Unit suite hang + order-dependent test-pollution (non-deterministic failures) |
| 61 | Medium | Fixed (→ Fixed.md) | Bug | — | BOB-062 — Unbounded plugin pagination loops + unbounded network I/O (hang risk) |
| 62 | Low | Completed (→ Fixed.md) | Task | — | BOB-063 — pirateiro test-isolation: add to conftest isolation + standing regression guard |
| 63 | — | Completed (→ Fixed.md) | Task | — | BOB-064 — Lava P1: Durable remote execution (systemd-linger helper) |
| 64 | — | Completed (→ Fixed.md) | Task | — | BOB-067 — Lava P4: Jackett cookie-login hardening + behaviorally-equivalent HelixQA fake |
| 65 | High | Fixed (→ Fixed.md) | Bug | — | BOB-072 — RD2-03: workable_items.db machine-caught SSoT integrity violations + 90% of closures have zero audit trail |
| 66 | High | Fixed (→ Fixed.md) | Bug | — | BOB-073 — RD2-04: workable_items.db and Issues.md/Fixed.md have drifted (BOB-008 body differs) |
| 67 | High | Completed (→ Fixed.md) | Task | — | BOB-075 — RD2-08: docs/features/Status.md and docs/codegraph/Status.md are stale |
| 68 | Medium | Completed (→ Fixed.md) | Task | — | BOB-103 — Land docs_chain (git@github.com:vasic-digital/docs_chain.git) as depth-1 reusable-engine submodule at constitution/submodules/docs_chain/ pinned to helixcode-v1.1.0. Build engine binary. Wire pre-build gate invariant 24 CM-DOCS-CHAIN-ENGINE-VERIFY into scripts/pre_build_verification.sh (real docs_chain verify --all against .docs_chain/contexts). Add challenges/scripts/docs_chain_verify_challenge.sh with §11.4.115 RED_MODE polarity. Retire scripts/docs_chain.sh misnomer wrapper by renaming to scripts/workable-items-export.sh (git mv, history preserved) and updating active callers (pre_build_verification.sh + 2 test files + 3 current-state docs). Constitution commit 47d41f8 pushed to all 6 mirrors. Boba-side commit follows this workable-item creation. [Reconciled 2026-08-18 via BOB-072/073 SSoT-integrity remediation: original item's Fixed-location DB row was deleted by a Fixed.md md-to-db reparse before this restoration ran (BOB-103 had never been written into docs/Fixed.md text) — original item_history rows (id=66 Opened 2026-08-15, id=67 Completed 2026-08-15, evidence challenges/scripts/docs_chain_verify_challenge.sh) survive untouched and remain the authoritative closure record; this add+close pair is a mechanical items-row restoration, not a re-performance of the original 2026-08-15 work.] |
| 69 | Medium | Fixed (→ Fixed.md) | Bug | — | BOB-108 — workable-items export (constitution/scripts/workable-items/workable-items export --db docs/workable_items.db --out-dir docs) regenerates docs/Issues.md and docs/Fixed.md from the tool's own internal revision counter, which does not track manually-bumped §11.4.44 revision headers landed by a prior commit outside the tool's own write path. Discovered during BOB-069 (.superpowers/sdd/task-bob069-report.md, Concerns section): an export invocation reverted docs/Issues.md Revision 7->6 and docs/Fixed.md Revision 16->15, both regressions relative to the already-committed HEAD values bumped manually in commit 82d9842. Worked around manually by re-bumping both headers forward (Issues.md->8, Fixed.md->17) per §11.4.44 (monotonic revision is non-negotiable) rather than shipping the regression. Recommendation: fix upstream in constitution/scripts/workable-items so 'export' reads the CURRENT on-disk **Revision:** header (or the DB's own last-known value, whichever is higher) before regenerating, instead of relying solely on an internal counter that can trail a manually-edited file. |
| 70 | High | Fixed (→ Fixed.md) | Bug | — | BOB-112 — qBitTorrent-go/internal/jackettapi/health.go:60-63 -- HandleHealth makes a synchronous, uncached call to Jackett.GetCatalog() on every single hit to /healthz, with no cache, no distinct timeout, and no circuit breaker. Measured evidence (docs/testing/ddos_resilience.md Findings, 2026-08-18, RED_MODE=0, three independent live runs): up to 98/150 (65%) of health-check requests timed out at 3s under a modest cold-start concurrent burst (10-50 concurrency), recovering to <50ms/request once the burst subsided. This is a genuine self-inflicted DDoS amplification vector: an attacker or a mis-configured monitoring probe hitting /healthz too aggressively can make the Jackett-management API's own health surface appear down without ever touching Jackett itself. Recommended fixes: cache the Jackett liveness signal with a short TTL refreshed by a background ticker; add a tight timeout/circuit-breaker around the GetCatalog call so /healthz itself never blocks past ~250-500ms regardless of Jackett's state. Discovered + scaffolded by BOB-074 (commit ae2b5cb, challenges/scripts/ddos_resilience_challenge.sh); tracked as SDD session task #64 in .superpowers/sdd/progress.md prior to this DB filing -- this item is the canonical, tracked workable-items record for that reference (§11.4.93 SSoT, §11.4.214 recurrence-links-not-mints: no prior BOB-NNN existed for this defect, verified by title/description search before minting). |
| 71 | High | Fixed (→ Fixed.md) | Bug | — | BOB-115 — unresolvableClosureEvidence() (constitution/scripts/workable-items/cmd/workable-items/sync.go) checked evidence-path resolvability for EVERY item_history row belonging to a terminally-closed item, regardless of the row's event_type. BOB-010's real closure (history id=4, event=Completed) recorded a resolvable evidence_path; a LATER Updated event (history id=64, on=2026-08-10) recorded evidence_path=scripts/docs_chain.sh, a path that stopped resolving after that script was git-mv'd to scripts/workable-items-export.sh (commits 0558399/d9d512d). validate flagged the Updated row as an unresolvable closure claim, mechanically blocking every subsequent commit via commit-push-all.sh (BOBA_SYNC_SKIP_CI=1 was required to land 1f42357). Fix: added AND h.event_type IN (Fixed, Implemented, Completed, Obsolete) to the query, reusing the SAME closed set correct_evidence.go's closureEvents / assign.go's hasClosureEvidence already recognise. Regression guard: TestClosureEvidence_UpdatedEventOnClosedItem_UnresolvablePath_NoViolation, RED-then-GREEN + paired mutation proof captured at docs/qa/task-54/RED-GREEN-transcript.md. |
| 72 | Critical | Fixed (→ Fixed.md) | Bug | — | BOB-116 — On 2026-08-18 the operator reported being fully logged out from host milosvasic account after returning from lid-closed state, finding themselves at the GDM greeter -- the 2nd such incident on this project (1st was 2026-07-07, which produced the §12.12 anchor). Root-cause investigation (docs/incidents/2026-08-18-perceived-forced-logout-2nd.md) traced it to a resource-pressure cascade: a §12.12 EAGAIN/SocketException(11) cascade across Jackett trackers at 20:45:48, a pathological 15 GB ugrep from a Task#52 subagent, an HTTP flood at 20:49:00, and multi-fleet concurrent container pressure, culminating in systemd logging user@1000.service Main process exited, code=killed, status=9/KILL at 20:50:59 -- no standing check consulted that signal before session termination, and CONST-033 triage confirmed no actual host suspend/poweroff occurred (this is a resource-exhaustion user-session OOM-kill, not a CONST-033 violation). Comprehensive fixes landed this session: new 5-signature proactive detector challenges/scripts/resource_pressure_signature_challenge.sh (commit 1f42357); five REAL per-signature §11.4.115(F) RED fixtures under challenges/fixtures/resource_pressure/ replacing an initially-overstated threshold-mutation polarity claim, verified via verify_resource_pressure_polarity.sh with RED confirmed 5/5 FAIL 0 SKIP 0 (commit efbb8a6); wiring into scripts/pre_build_verification.sh invariant 25 (CM-RESOURCE-PRESSURE-SIGNATURE-CHECK) plus an hourly systemd --user timer boba-resource-pressure-check.timer, now LIVE and armed (commit ecb3bfe); a §11.4.238 QA-discovery-ledger entry FORCED-LOGOUT-2026-08-18-2ND documenting the coverage escape (commit 98412bf); a fix for a CONST-033 challenge false-positive caused by scratchpad/.superpowers path scanning (part of commit 1f42357); 8 machine-evidence artifacts under docs/qa/BOB-076/ (journalctl, oomctl, cgtop, PSI readings, ps LRSS snapshot, challenge pass/forced-fail logs, lid+session events); and a persistent-memory incident playbook at ~/.claude-claude4/.../memory/forced_logout_incidents.md. NOTE ON ID COLLISION (documented honestly per §11.4.6/§11.4.54): all of the commits above and the docs/qa/ evidence directory used the label BOB-076 for this incident, but BOB-076 was ALREADY a distinct, legitimately-minted workable item (RD2-09: submodules/jackett fork 1 commit behind upstream, Type=Task, Status=Queued, minted 2026-08-15 -- three days before this incident) at the time those commits landed. §11.4.54 forbids ID reuse, so this item is filed under a fresh monotonic ID instead of overwriting BOB-076; the real BOB-076 (jackett submodule bump) is untouched and unrelated to this incident -- it was independently already resolved via commit 99a486e. See docs/incidents/2026-08-18-perceived-forced-logout-2nd.md for full forensic detail and docs/QA_DISCOVERY_LEDGER.md entry FORCED-LOGOUT-2026-08-18-2ND for the coverage-escape audit. |
| 73 | Medium | Fixed (→ Fixed.md) | Bug | — | BOB-119 — docs/MERGE_SEARCH_DIAGNOSTICS.md line ~128 states 'Default: 1 (all trackers exposed; dead ones filtered by DEAD_PUBLIC_TRACKERS)' for ENABLE_DEAD_TRACKERS. This is factually wrong: download-proxy/src/merge_service/search.py:1032 reads os.getenv('ENABLE_DEAD_TRACKERS', '0') (default string '0') and docker-compose.yml:177 sets ENABLE_DEAD_TRACKERS=\0 (also default 0). The sibling doc docs/DEAD_TRACKERS_EXPLAINED.md correctly states 'With ENABLE_DEAD_TRACKERS=0 (default): 24 public trackers active, 14 excluded' — confirmed against the current DEAD_PUBLIC_TRACKERS frozenset (14 entries, names match exactly). MERGE_SEARCH_DIAGNOSTICS.md's stated default is the one document that disagrees with the source of truth, and could mislead an operator into believing dead trackers are shown to end users by default when they are actually filtered out by default. Found during a §11.4.6 bluff audit (docs/qa/task-bluff-audit/). Fix direction: correct 'Default: 1' to 'Default: 0' in MERGE_SEARCH_DIAGNOSTICS.md to match search.py/docker-compose.yml. |
