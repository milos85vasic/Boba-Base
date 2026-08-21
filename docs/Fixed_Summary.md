# Fixed_Summary

Closed workable items (current_location = Fixed), regenerated from the SQLite single-source-of-truth (§11.4.53).

## Counts by Type × Status

| Type | Status | Count |
|---|---|---|
| Bug | Fixed (→ Fixed.md) | 41 |
| Feature | Implemented (→ Fixed.md) | 17 |
| Task | Completed (→ Fixed.md) | 26 |
| Task | Fixed (→ Fixed.md) | 4 |
| Task | Implemented (→ Fixed.md) | 17 |
| **TOTAL** | | **105** |

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
| 65 | High | Fixed (→ Fixed.md) | Bug | — | BOB-070 — RD2-41: pre-build mutation-marker scan carrier false-positive silently defeats entire pre-build gate |
| 66 | Medium | Fixed (→ Fixed.md) | Bug | — | BOB-071 — RD2-01: guard-forbidden-commands.sh hook has live reproducible substring carrier false-positive |
| 67 | High | Fixed (→ Fixed.md) | Bug | — | BOB-072 — RD2-03: workable_items.db machine-caught SSoT integrity violations + 90% of closures have zero audit trail |
| 68 | High | Fixed (→ Fixed.md) | Bug | — | BOB-073 — RD2-04: workable_items.db and Issues.md/Fixed.md have drifted (BOB-008 body differs) |
| 69 | High | Completed (→ Fixed.md) | Task | — | BOB-075 — RD2-08: docs/features/Status.md and docs/codegraph/Status.md are stale |
| 70 | Low | Completed (→ Fixed.md) | Task | — | BOB-076 — RD2-09: submodules/jackett fork 1 commit behind upstream (informational) |
| 71 | Medium | Completed (→ Fixed.md) | Task | — | BOB-079 — RD2-12: Retroactive attributed history notes for GA-18/21/22/25/26/27 changes (never rewrite published history) |
| 72 | High | Completed (→ Fixed.md) | Task | — | BOB-081 — RD2-14: Author CONTINUATION.md Session 15 entry (currently 53 days / 24+ commits behind HEAD) |
| 73 | Medium | Completed (→ Fixed.md) | Task | — | BOB-083 — RD2-16: Regenerate browser_extension/features/codegraph Status.md + Summary/HTML/PDF siblings |
| 74 | High | Completed (→ Fixed.md) | Task | — | BOB-084 — RD2-17: Reconcile BOB-008 DB/MD body drift via the workable-items tool |
| 75 | Medium | Completed (→ Fixed.md) | Task | — | BOB-086 — RD2-19: Fix BOB-009/BOB-010 evidence_path + backfill item_history for 56 silent closures |
| 76 | High | Completed (→ Fixed.md) | Task | — | BOB-089 — RD2-24: RED-first tests for start.sh reload_python/reload_plugins/recreate_stack (closes test-half of GA-27) |
| 77 | High | Fixed (→ Fixed.md) | Bug | — | BOB-091 — RD2-26: Relocate mocked SearchOrchestrator tests to unit/ + author real-service replacements (closes GA-14/15/16) |
| 78 | Medium | Completed (→ Fixed.md) | Task | — | BOB-096 — RD2-31: Extend qBitTorrent-go jackett_db_test.go with real process-kill/resource-exhaustion fault injection |
| 79 | Medium | Completed (→ Fixed.md) | Task | — | BOB-098 — RD2-34: Parametrize 20 hardcoded /Volumes/T7 paths in helixqa banks with PROJECT_ROOT (closes GA-23) |
| 80 | Medium | Fixed (→ Fixed.md) | Bug | — | BOB-099 — RD2-36: Fix guard-forbidden-commands.sh substring-match false-positive class + add const033-poweroff-signal-triage carrier to EXCLUDE_PATHS |
| 81 | Medium | Completed (→ Fixed.md) | Task | — | BOB-103 — Incorporate Docs Chain submodule per §11.4.106/§11.4.28(C) |
| 82 | Medium | Completed (→ Fixed.md) | Task | — | BOB-105 — §11.4.238 followup: mechanical §11.4.227(B) anchor-block-integrity check |
| 83 | Medium | Fixed (→ Fixed.md) | Bug | — | BOB-108 — constitution scripts/workable-items export reverts docs/Issues.md + docs/Fixed.md revision counters |
| 84 | High | Fixed (→ Fixed.md) | Bug | — | BOB-112 — boba-jackett /healthz amplifies under cold-start concurrent burst via uncached Jackett.GetCatalog() call |
| 85 | Low | Completed (→ Fixed.md) | Task | — | BOB-113 — BOB-074 followup: add wrk to dev tooling for DDoS/load challenges |
| 86 | High | Fixed (→ Fixed.md) | Bug | — | BOB-115 — Fix workable-items validate over-scoping to Updated-events (BOB-010 id=64 pattern) |
| 87 | Critical | Fixed (→ Fixed.md) | Bug | — | BOB-116 — 2nd forced-logout incident: user@1000.service SIGKILLed after resource-pressure cascade (perceived host suspend) |
| 88 | High | Fixed (→ Fixed.md) | Bug | — | BOB-117 — rutracker login diag still uses forbidden §11.4.6 'likely' vocabulary + wrong error_type (unfixed sibling of nnmclub fix) |
| 89 | High | Fixed (→ Fixed.md) | Bug | — | BOB-118 — README.md python-tests badge claims 585 passing; pytest --collect-only measures 5235 (9x stale/wrong) |
| 90 | Medium | Fixed (→ Fixed.md) | Bug | — | BOB-119 — docs/MERGE_SEARCH_DIAGNOSTICS.md states ENABLE_DEAD_TRACKERS default=1; actual code + compose default=0 (contradicts sibling doc) |
| 91 | High | Fixed (→ Fixed.md) | Bug | — | BOB-122 — IPTorrents seed/leech parsing reports 0/0 despite real swarm data — outdated markup selectors in plugins/iptorrents.py AND download-proxy/src/merge_service/search.py |
| 92 | Critical | Fixed (→ Fixed.md) | Bug | — | BOB-123 — 4th forced-logout incident 2026-08-19 00:37:11 — PAM/Linger contradiction breakthrough (retro-registered: id used in 6 commits with no tracker row) |
| 93 | Critical | Fixed (→ Fixed.md) | Bug | — | BOB-124 — 5th forced-logout 2026-08-19 15:28:22 — architectural install-gap: 4 authored preventive gates never installed by operator |
| 94 | Critical | Fixed (→ Fixed.md) | Bug | — | BOB-125 — 6th forced-logout 2026-08-19 16:04:54 — RESOLVED via BOB-126 (root cause was pytest kill(-1,9)) |
| 95 | Critical | Fixed (→ Fixed.md) | Bug | — | BOB-126 — 7th forced-logout 2026-08-19 16:43:43 — REAL ROOT CAUSE: pytest kill(-1,9) via MagicMock.__int__==1; §11.4.263 anchor + boba defense-in-depth |
| 96 | Low | Fixed (→ Fixed.md) | Bug | — | BOB-127 — Task 8 audit: 2 tests fired real killpg/getpgid on hardcoded PIDs (fixed 8bedc5a) |
| 97 | Medium | Fixed (→ Fixed.md) | Bug | — | BOB-128 — killpg-carrier collision between CM-TEST-MOCK-PID-PATCHED-WHEN-REAL-PID and sibling CM-KILLPG-PGID-GUARD (retro-registered: id used in 3 commits with no tracker row) |
| 98 | Low | Fixed (→ Fixed.md) | Bug | — | BOB-130 — Badge-test timeout deterministic — synced_fixtures fixture 93s vs --timeout=60 |
| 99 | High | Fixed (→ Fixed.md) | Bug | — | BOB-132 — qbittorrent-proxy post-recovery: unhealthy — connection refused to qbittorrent sidecar on localhost:7185 |
| 100 | Critical | Fixed (→ Fixed.md) | Bug | — | BOB-133 — CRITICAL: fleet-wide container dead-but-healthy — podman stale-cache masks service outage |
| 101 | High | Fixed (→ Fixed.md) | Bug | — | BOB-138 — qbittorrent-proxy health check probes only 7186, so a dead 7187 merge service reports healthy forever |
| 102 | Medium | Fixed (→ Fixed.md) | Bug | — | BOB-139 — SSE _client_gone() swallows every exception into 'client still connected', so a raising disconnect probe streams forever (fail-open) |
| 103 | Medium | Completed (→ Fixed.md) | Task | — | BOB-140 — Upstream the healthcheck-covers-served-ports gate into constitution/scripts/gates/ and thin boba's copy to a delegator (§11.4.177) |
| 104 | High | Fixed (→ Fixed.md) | Bug | — | BOB-142 — SearchRequest fields were unbounded, so one request could amplify into a 43-tracker fan-out carrying arbitrary payload |
| 105 | Medium | Completed (→ Fixed.md) | Task | — | BOB-147 — Triage all 36 §11.4.252 fail-open hits: 9 real defects fixed, 14 correct idioms, 14 vendored |
