# Test-Type Matrix

**Revision:** 1
**Last modified:** 2026-08-18T14:54:02Z

Audit of boba's actual test-type coverage against the §11.4.27 mandated list
(unit / integration / e2e / full-automation / security / DDoS / scaling /
chaos / stress / performance / benchmarking / UI / UX / Challenges /
HelixQA). Produced as part of **BOB-074** (DDoS-class testing scaffold).

This is a **point-in-time audit** (2026-08-18) of directory/file presence and
counts, not a coverage-percentage measurement (§11.4.224's code-coverage
floor is a separate, unaddressed axis — see "Gaps" below).

## Method

- `challenges/scripts/*.sh` — enumerated by filename + first-comment-line
  description.
- `tests/` — enumerated by subdirectory (already type-organized) + file
  counts.
- `download-proxy/tests/` — does **not exist**; per the project's own
  documented gotcha ("Merge service tests live at `./tests/`, not
  `download-proxy/tests/`"), Python tests for the merge service live under
  the top-level `tests/` tree instead.
- `qBitTorrent-go/*/test*.go` — enumerated by package + `tests/{integration,
  e2e,security,contract}` top-level suites.
- `challenges/helixqa-banks/*.yaml` — enumerated by bank + test-case count.

## Coverage summary

| §11.4.27 mandated type | Status (pre-BOB-074) | Status (post-BOB-074) | Where |
|---|---|---|---|
| unit | Present | Present | `tests/unit/` (133 files), `qBitTorrent-go/internal/**/*_test.go` (40 files) |
| integration | Present | Present | `tests/integration/` (23 files), `qBitTorrent-go/tests/integration/` (2 files) |
| e2e | Present | Present | `tests/e2e/` (7 files), `qBitTorrent-go/tests/e2e/` (1 file), `frontend/e2e/` (3 Playwright specs) |
| full-automation | Present (cross-cutting) | Present | No dedicated directory — governed as a discipline across every suite (§11.4.98); not independently re-audited here |
| security | Present | Present | `tests/security/` (12 files), `qBitTorrent-go/tests/security/` (1 file), plus credential-focused challenges (`credential_leak_grep_challenge.sh`, `cred_roundtrip_challenge.sh`, `master_key_autogen_challenge.sh`, …) |
| **DDoS** | **ABSENT** | **Scaffolded** | `challenges/scripts/ddos_resilience_challenge.sh` (new, this commit) — see caveats below |
| **scaling** | **ABSENT** | **ABSENT** | No scaling-tagged directory, test file, or HelixQA bank anywhere in the tree. Followup filed. |
| chaos | Present (thin) | Present | `tests/chaos/` (2 files), `tests/stress_chaos/` (2 files), `qBitTorrent-go/internal/api/magnet_stress_chaos_test.go`, `qBitTorrent-go/tests/integration/scheduler_hooks_sse_stress_chaos_test.go` |
| stress | Present | Present | `tests/stress/` (10 files), `tests/load/locustfile.py` (Locust load profile) |
| performance | Present (thin) | Present | `tests/performance/test_concurrent_search.py` (1 file), `tests/benchmark/` (3 files) |
| benchmarking | Present | Present | `tests/benchmark/` (3 files + `baselines/`), Go `*_bench_test.go` (`crypto_bench_test.go`, `autoconfig_bench_test.go`) |
| UI | Present | Present | `frontend/src/**/*.spec.ts` (30 Vitest specs), `frontend/e2e/*.spec.ts` (3 Playwright specs) |
| **UX** | **ABSENT (distinct)** | **ABSENT (distinct)** | No test is framed around usability/accessibility/UX outcomes specifically; UI functional coverage exists (above) but nothing tags a UX dimension. Followup filed. |
| Challenges | Present | Present | `challenges/scripts/*.sh` — 26 scripts pre-BOB-074, 27 post (see enumeration below) |
| HelixQA | Present | Present | `challenges/helixqa-banks/*.yaml` — 7 banks, 61 test cases total; **none tag DDoS or scaling** (followup) |

**Gap count identified: 3** mandated types with zero representation at audit
time — DDoS, scaling, UX. This task (BOB-074) scaffolds DDoS (partial close —
see caveats). **scaling and UX remain fully open.**

## Enumeration — `challenges/scripts/*.sh` (27 scripts)

| Script | Primary type |
|---|---|
| `boba_db_file_perms_challenge.sh` | Security (file-permission gate) |
| `credential_leak_grep_challenge.sh` | Security (leak gate) |
| `credentials_wired_challenge.sh` | Integration / anti-bluff wiring guard |
| `cred_roundtrip_challenge.sh` | Integration (round-trip gate) |
| `ddos_resilience_challenge.sh` | **DDoS** (new, BOB-074) |
| `docs_chain_verify_challenge.sh` | Integration (docs/DB sync gate) |
| `download_proxy_deep_challenge.sh` | Unit/integration coverage gate |
| `durable_run_helper_challenge.sh` | Chaos/resilience regression guard |
| `env_db_drift_challenge.sh` | Integration (config drift gate) |
| `envfile_bindmount_atomic_challenge.sh` | Integration (atomicity) |
| `helixqa_jackett_fake_behavioral_equivalence_challenge.sh` | HelixQA equivalence guard |
| `host_no_auto_poweroff_challenge.sh` | Host-safety (CONST-033/034) |
| `host_no_auto_suspend_challenge.sh` | Host-safety (CONST-033) |
| `install_sh_idempotent_challenge.sh` | Integration (idempotency) |
| `iptorrents_cookie_flow_challenge.sh` | Integration/security (cred flow) |
| `jackett_autoconfig_clean_slate.sh` | Regression guard (CONST-032) |
| `jackett_cookie_login_hardening_challenge.sh` | Security hardening guard |
| `master_key_autogen_challenge.sh` | Security (key-gen gate) |
| `nnmclub_native_plugin_clarification_challenge.sh` | Integration clarification guard |
| `no_suspend_calls_challenge.sh` | Host-safety (source-tree gate) |
| `private_tracker_html_challenge.sh` | Unit (HTML-parsing coverage) |
| `run_all_challenges.sh` | Aggregator (not itself a test) |
| `search_deep_coverage_challenge.sh` | Unit coverage gate |
| `status_docs_freshness_challenge.sh` | Integration (doc-staleness gate) |
| `tmux_survives_oomd_pressure_challenge.sh` | Chaos (§11.4.238 coverage-escape guard) |
| `tracker_auth_live_challenge.sh` | Integration (live auth) |
| `upstream_proxy_wired_challenge.sh` | Integration (cross-layer wiring) |
| `workable_items_integrity_challenge.sh` | Integration (SSoT integrity) |

## Enumeration — `tests/` (Python, merge-search + shared)

| Subdirectory | File count | Type |
|---|---|---|
| `unit/` | 133 | unit |
| `integration/` | 23 | integration |
| `e2e/` | 7 | e2e |
| `security/` | 12 | security |
| `stress/` | 10 | stress |
| `stress_chaos/` | 2 | stress + chaos (combined) |
| `chaos/` | 2 | chaos |
| `concurrency/` | 3 | concurrency (unmandated but useful — see note) |
| `performance/` | 1 | performance |
| `benchmark/` | 3 (+ `baselines/`) | benchmarking |
| `load/` | 1 (`locustfile.py`) | stress/load |
| `property/` | 2 | property-based (unmandated but useful) |
| `contract/` | 4 | contract (unmandated but useful) |
| `observability/` | 2 | observability (unmandated but useful) |
| `docs/` | 3 | doc-consistency (unmandated but useful) |
| `hooks/` | 1 (`test_guard_forbidden_commands.sh`) | integration (git-hook guard) |
| `fixtures/`, `memory/`, `test_torrents/` | — | shared fixtures, not test files themselves |

Note: `concurrency/`, `property/`, `contract/`, `observability/`, and `docs/`
are not literal §11.4.27 vocabulary items but are real, useful test
disciplines this project has already adopted beyond the mandated floor.

## Enumeration — `qBitTorrent-go` (Go)

| Location | File count | Type |
|---|---|---|
| `internal/**/*_test.go` | 40 | unit |
| `tests/integration/*_test.go` | 2 | integration (one is `scheduler_hooks_sse_stress_chaos_test.go` — chaos-tagged) |
| `tests/e2e/*_test.go` | 1 | e2e |
| `tests/security/*_test.go` | 1 | security |
| `tests/contract/*_test.go` | 1 | contract |
| `internal/db/crypto_bench_test.go`, `internal/jackett/autoconfig_bench_test.go` | 2 | benchmarking |
| `internal/api/magnet_stress_chaos_test.go` | 1 | stress + chaos (combined) |

## Enumeration — `challenges/helixqa-banks/*.yaml`

| Bank | Test cases |
|---|---|
| `boba-boba-ctl.yaml` | 7 |
| `boba-bobalink.yaml` | 12 |
| `boba-docs-chain.yaml` | 3 |
| `boba-download-proxy.yaml` | 10 |
| `boba-frontend.yaml` | 10 |
| `boba-services.yaml` | 14 |
| `boba-tmux-session-hardening.yaml` | 5 |
| **Total** | **61** |

None of the 7 banks tag a DDoS or scaling scenario.

## Enumeration — `frontend/` (Angular 21, UI)

| Location | File count | Type |
|---|---|---|
| `src/**/*.spec.ts` | 30 | UI unit (Vitest) |
| `e2e/*.spec.ts` | 3 | UI e2e (Playwright) |

## Gaps + followups filed

Per §11.4.6 (no invented thresholds/fixes) these are filed as **followup
work items**, not silently fixed inside this task's scope
(`challenges/scripts/ddos_resilience_challenge.sh` +
`docs/testing/ddos_resilience.md` + this file only):

1. **Scaling-class testing is fully absent.** No test, script, or HelixQA
   bank distinguishes "scaling" (does the system handle a growing dataset /
   tracker count / concurrent-user count gracefully, e.g. horizontal
   scale-out of the merge-search fanout, DB growth under
   `challenges/helixqa-banks/boba-services.yaml`'s tracker set, or the
   `qbittorrent-proxy-go --profile go` swap) from "stress" (does it survive
   a burst). **Followup: file a Task workable item — "Scaling-class test
   coverage absent from boba's mandated test-type matrix" — scoped to at
   least one scaling dimension (e.g. tracker-count scale-out in merge
   search) with a real, measured baseline.**
2. **UX-class testing has no distinct representation.** UI functional
   coverage exists (Vitest + Playwright) but nothing is framed around
   usability/accessibility/UX outcomes (e.g. WCAG checks, keyboard-nav
   coverage, screen-reader labeling). **Followup: file a Task workable item
   — "UX-class test coverage (accessibility/usability) absent" — scoped to
   an axe-core or equivalent accessibility pass over the Angular frontend.**
3. **DDoS-class testing was fully absent; now scaffolded, not fully closed.**
   See `docs/testing/ddos_resilience.md` "Followups" for the two concrete
   items this scaffold surfaced:
   - No rate limiting exists anywhere in boba's stack (verified 2026-08-18:
     no `slowapi`/`limiter`/`throttle` in the Python service, no
     rate-limit middleware in either Go service, no nginx/reverse-proxy
     layer). **Followup: configure a real rate limit for the three public
     endpoints** (candidate approaches documented in
     `docs/testing/ddos_resilience.md`).
   - `boba-jackett`'s `/healthz`
     (`qBitTorrent-go/internal/jackettapi/health.go:60-63`) makes a
     synchronous, uncached `Jackett.GetCatalog()` call on every hit — under
     a cold-start concurrent burst this was measured to cause up to 98/150
     (65%) of health-check requests to time out at 3s, recovering to
     <50ms/request once the burst subsided. This is a genuine
     self-inflicted amplification vector: an attacker (or even a
     mis-configured monitoring probe hitting `/healthz` too aggressively)
     could make the Jackett-management API's own health surface appear
     down without ever touching Jackett itself. **Followup: file a Bug
     workable item citing this exact reproduction + recommended fixes
     (cache the Jackett liveness signal with a short TTL refreshed by a
     background ticker; add a tight timeout/circuit-breaker around the
     `GetCatalog` call so `/healthz` itself never blocks past ~250-500ms
     regardless of Jackett's state).** See `docs/testing/ddos_resilience.md`
     "Findings" for the full evidence.
   - The real fanout path (`POST /api/v1/search`, up to 43 real trackers)
     is deliberately **never** driven by the new challenge — see
     `docs/testing/ddos_resilience.md` "Scoping decisions" for why, and the
     followup this leaves open (a sandboxed/mocked-tracker DDoS variant
     that exercises the orchestration code path without touching real
     third-party tracker sites).
4. **§11.4.224 code-coverage floor** (≥85%, ~100% target) is a distinct,
   unaddressed axis from this test-*type* audit — this document counts
   *presence* of test types, not *coverage percentage* within them. Not
   remeasured here; out of this task's scope.

These followups are **documented here and in the DDoS doc rather than
inserted into `docs/workable_items.db` directly** — this task ran in
parallel with other subagents also touching shared project state, and a
concurrent SQLite write from this task risked a race with theirs. The
orchestrating session should register the followups above as tracked
workable items (§11.4.93/§11.4.202) once the parallel batch completes.
