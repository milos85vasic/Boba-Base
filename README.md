<!--
  §11.4.44 revision marker (voluntary — Constitution.md §11.4.44 explicitly exempts
  README.md from the mandatory revision-header gate; tracked here anyway for
  freshness auditing per the §11.4.257/§11.4.259 refresh mandate).
  Revision: 2
  Last modified: 2026-08-19T17:00:43Z
-->
<h1 align="center">
  <img src="docs/assets/logo.png" alt="qBittorrent" width="160" />
  <br>
  Боба / Boba
</h1>

<p align="center">
  <strong>Multi-tracker meta-search for qBittorrent — self-hosted, containerised, private-tracker-aware.</strong>
</p>

<p align="center">
  <a href="#quick-start">Quick start</a> ·
  <a href="#tokens--api-keys">Tokens & keys</a> ·
  <a href="#documentation">Documentation</a> ·
  <a href="#architecture">Architecture</a> ·
  <a href="#testing">Testing</a> ·
  <a href="#contributing">Contributing</a>
</p>

<p align="center">
  <img alt="tests"          src="https://img.shields.io/badge/python%20tests-5499%20collected-blue">
  <img alt="vitest"         src="https://img.shields.io/badge/frontend%20tests-371%20collected-blue">
  <img alt="plugins"        src="https://img.shields.io/badge/plugins-43-blue">
  <img alt="merge"          src="https://img.shields.io/badge/merge_service-FastAPI%20%3A7187-orange">
  <img alt="ci"             src="https://img.shields.io/badge/ci-manual%20%28.%2Fci.sh%2C%20no%20auto--trigger%29-success">
  <img alt="pre-build"      src="https://img.shields.io/badge/pre--build%20invariants-49-blue">
  <img alt="challenges"     src="https://img.shields.io/badge/challenges-38-blue">
  <img alt="scan"           src="https://img.shields.io/badge/scanners-snyk%20%7C%20sonar%20%7C%20bandit%20%7C%20ruff%20%7C%20semgrep%20%7C%20trivy%20%7C%20gitleaks%20%7C%20pip--audit-red">
  <img alt="license"        src="https://img.shields.io/badge/license-Apache%202.0-green">
</p>

<!--
  §11.4.259 badge-provenance note (closed vocabulary: GREEN=success, AMBER=yellow,
  RED=critical/red, GRAY=lightgrey/N/A-with-reason — never hand-picked colors).
  A full self-validated badge-computer (golden-good/golden-bad per §11.4.107(10))
  is NOT wired this session — that is tracked as a separate §11.4.197 gate-code
  item, not claimed shipped. Provenance of the badges above, verified 2026-08-18:
    - ci: GREEN — verified `.github/workflows/` absent + `ci.sh` present and
      executable (CLAUDE.md Hard Stop: "CI IS MANUAL — permanent"). This badge
      previously read "ci-auto" (nightly/security triggers) which is FALSE per
      the current Hard Stop rule and has been corrected, not merely refreshed.
    - pre-build invariants: DERIVED — informational count from the highest
      `[N/N]` label in `scripts/pre_build_verification.sh`; a count, not an
      asserted current PASS across all of them. This bullet previously said the
      badge was hand-updated because compute-badges.sh's `awk` filter "only
      matches `alt=\"tests\"` / `alt=\"vitest\"`" and "does not actually rewrite
      this badge line". Both claims are now false: the filter rewrites the
      pre-build, challenges and plugins lines too, and the script verifies each
      rewritten line is present in README before reporting it (the earlier
      hardcoded "(unchanged, cross-checked...)" string was removed when that
      §11.4 badge-layer bluff was fixed). Corrected 2026-08-21 alongside BOB-149
      — a stale note asserting a tool is broken is the same doc-vs-code drift
      class BOB-149 filed, in the very file that drift lives in.
    - challenges: informational count of `challenges/scripts/*.sh` (31),
      including the new resource_pressure_signature_challenge.sh +
      verify_resource_pressure_polarity.sh + the ddos_resilience_challenge.sh
      `--healthz` mode extension — a count, not an asserted current PASS.
    - plugins: DERIVED, not carried forward (BOB-149). `scripts/compute-badges.sh`
      now parses install-plugin.sh's `PLUGINS=()` curated roster — THE canonical
      managed roster per constitution Principle II — behind a §11.4.201(7)(b)
      control needle, and rewrites this badge line like every other derived
      badge. It previously read 48, an April-2026 count of `plugins/*.py` FILES
      relabelled "plugin engines" and never refreshed after a community/ reorg;
      nothing in the repository equals 48 today. Cross-checked at build time by
      `scripts/pre_build_verification.sh` invariant 46 (CM-PLUGIN-COUNT).
  tests/vitest/merge/scan/license badges are carried forward unverified
  this session (out of this task's scope) — see docs/TESTING.md for the current
  authoritative per-suite counts.
-->

---

## Features

- **Merge Search Service** — FastAPI service (`:7187`) that fans out across 40+ trackers, deduplicates results, streams via SSE.
- **Real-time results** — `result_found` events arrive as each tracker completes, no blocking.
- **Private-tracker bridge** — Authenticated downloads via `webui-bridge.py` for RuTracker, Kinozal, NNM-Club, IPTorrents.
- **Freeleech-only IPTorrents** — Automation never costs ratio (see [constitution VIII](.specify/memory/constitution.md)).
- **Opt-in quality stack** — SonarQube + Snyk + Semgrep + Trivy + Gitleaks + bandit + pip-audit behind `docker-compose.quality.yml`.
- **Opt-in observability** — Prometheus + Grafana dashboards behind the same profile system.
- **Hook system** — Register scripts via `POST /api/v1/hooks` for search / download events.
- **Angular 21 SPA dashboard** — dark-themed, signals-based, per-tracker status chips with CAPTCHA re-login, virtual-scroll-ready sort.
- **PWA-ready** — favicon + launcher icons + web manifest ship from `frontend/public/`.
- **Container-first** — rootless Podman or Docker, single `./start.sh` boot.
- **Resource-pressure early-warning** — [`challenges/scripts/resource_pressure_signature_challenge.sh`](challenges/scripts/resource_pressure_signature_challenge.sh) checks 5 independently-falsifiable host-pressure signatures (runaway RSS, thread-count vs `ulimit -u`, container EAGAIN cascades, swap pressure, cgroup memory pressure) so a forced-logout precursor is caught *before* `user@1000.service` gets SIGKILLed, not after. Wired into `scripts/pre_build_verification.sh` invariant 25 and a standing `boba-resource-pressure-check.timer` systemd-user unit. See [incident writeup](docs/incidents/2026-08-18-perceived-forced-logout-2nd.md).

---

## Quick start

```bash
git clone https://github.com/milos85vasic/qBitTorrent.git
cd qBitTorrent

# Optional: configure tracker credentials + tokens
cp .env.example .env
$EDITOR .env            # see "Tokens & API keys" below

./setup.sh              # one-time
./start.sh              # Angular build + containers + plugin sync
```

Then visit:

| URL | Purpose | Auth |
|---|---|---|
| [http://localhost:7187/](http://localhost:7187/) | Merge-search dashboard (SPA) | — |
| [http://localhost:7187/docs](http://localhost:7187/docs) | FastAPI Swagger UI | — |
| [http://localhost:7187/openapi.json](http://localhost:7187/openapi.json) | OpenAPI schema | — |
| [http://localhost:7186/](http://localhost:7186/) | qBittorrent WebUI proxy | `admin` / `admin` |
| [http://localhost:7185/](http://localhost:7185/) | qBittorrent internal (container) | — |
| [http://localhost:7188/](http://localhost:7188/) | WebUI bridge (private-tracker downloads) | — |

---

## Tokens & API keys

**⚠ Configure any credentials you need in `.env` before running `./start.sh`.** The single source of truth is **[`docs/TOKENS_AND_KEYS.md`](docs/TOKENS_AND_KEYS.md)** — which variable is mandatory, which is optional, and **where to register** for each one.

### Tracker credentials — env vars AND cookies files (auto-loaded)

Boba supports **two mechanisms** for tracker auth, and both are respected together:

1. **Env vars in `.env`** — `<TRACKER>_USERNAME` / `<TRACKER>_PASSWORD` / `<TRACKER>_COOKIES`.
2. **Cookies files in `~/Downloads/`** — canonical naming `cookies_<tracker>.txt` (lowercase), Netscape TSV format exported from a logged-in browser session.

The loader `scripts/load-tracker-cookies.sh` auto-invokes before every
`boba-svc up`, `boba-svc restart`, `install.sh` Stage 6, and `start.sh` boot —
so refreshing a session is a one-step *browser re-export → restart*. Source
directory defaults to `$HOME/Downloads`, overridable via
`TRACKER_COOKIE_DIR` or `--dir <path>`.

See the **[Tracker Credentials Manual](docs/guides/tracker-credentials.md)**
for the per-tracker matrix, browser-export step-by-step, precedence rules,
and the security posture (§11.4.10.A leak audit, cookie-value-never-logged).
Common questions: **[FAQ](docs/FAQ.md)**.

Downloads and directories the system creates are owned by the account that started it —
no `chown` step after every download. See the
**[File Ownership Guide](docs/guides/file-ownership.md)** for why that requires
`PUID=0` under rootless Podman, how to verify it on your own machine, and how to repair
content created before the fix.

### At a glance

| Category | Mandatory | Optional | Documentation |
|---|---|---|---|
| qBittorrent WebUI | — | `WEBUI_USERNAME`, `WEBUI_PASSWORD` | [§1](docs/TOKENS_AND_KEYS.md#1-qbittorrent-webui-built-in) |
| Private trackers | per-tracker | — | [§2](docs/TOKENS_AND_KEYS.md#2-private-tracker-credentials) |
| Public tracker uplift | — | `JACKETT_API_KEY`, … | [§3](docs/TOKENS_AND_KEYS.md#3-public-tracker-api-keys-optional) |
| Metadata enrichment | — | `TMDB_API_KEY`, `TVDB_API_KEY`, … | [§4](docs/TOKENS_AND_KEYS.md#4-metadata-enrichment-apis-optional) |
| Security scanning | — | `SNYK_TOKEN`, `SONAR_TOKEN`, … | [§5](docs/TOKENS_AND_KEYS.md#5-security-scanner-tokens-opt-in-ci--local-scans) |
| Observability | — | `GRAFANA_USER`, `GRAFANA_PASSWORD` | [§6](docs/TOKENS_AND_KEYS.md#6-observability-endpoints-opt-in-compose-profile) |
| Orchestrator tuning | — | `ALLOWED_ORIGINS`, `MAX_CONCURRENT_TRACKERS`, … | [§7](docs/TOKENS_AND_KEYS.md#7-orchestrator-tuning-optional--phase-3) |

### Where to register (fast links)

| Provider | Signup | Notes |
|---|---|---|
| RuTracker | <https://rutracker.org/forum/register.php> | Username + password |
| Kinozal | <https://kinozal.tv/signup.php> | May require invite |
| NNM-Club | <https://nnmclub.to/forum/ucp.php?mode=register> | Cookie-based auth |
| IPTorrents | <https://iptorrents.com/> | Invite-only; freeleech enforced |
| Jackett | <https://github.com/Jackett/Jackett> | Self-hosted indexer |
| TMDb | <https://www.themoviedb.org/signup> | v3 auth API key |
| TVDb | <https://thetvdb.com/api-information> | Subscription API |
| MusicBrainz | <https://musicbrainz.org/doc/MusicBrainz_API> | Free — needs UA only |
| Snyk | <https://app.snyk.io/> | Account → Auth Token |
| SonarCloud | <https://sonarcloud.io/account/security/> | Or run the compose SonarQube |
| Gitleaks | <https://gitleaks.io/> | Optional commercial license |

---

## Documentation

Everything the platform offers, indexed:

### Tracked-Items + Status Documents

<!-- doc-link-section:begin -->
The mandated entry point (§11.4.57 / §11.4.212) for every tracker and status document in this
repository — `Last modified` and `Revision` are sourced verbatim from each document's own
revision header (§11.4.44); a `—` means the document currently carries no revision header or has
no HTML/PDF export yet (never fabricated). Regenerated by
[`scripts/testing/update_readme_doc_links.sh`](scripts/testing/update_readme_doc_links.sh) —
never hand-typed (§11.4.57).

| Document | Last modified | Revision | Markdown | HTML | PDF |
|---|---|---|---|---|---|
| Issues | 2026-08-21T19:41:44Z | 40 | [Markdown](docs/Issues.md) | [HTML](docs/Issues.html) | [PDF](docs/Issues.pdf) |
| Issues_Summary | — | — | [Markdown](docs/Issues_Summary.md) | [HTML](docs/Issues_Summary.html) | [PDF](docs/Issues_Summary.pdf) |
| Fixed | 2026-08-21T19:41:44Z | 25 | [Markdown](docs/Fixed.md) | [HTML](docs/Fixed.html) | [PDF](docs/Fixed.pdf) |
| Fixed_Summary | — | — | [Markdown](docs/Fixed_Summary.md) | [HTML](docs/Fixed_Summary.html) | [PDF](docs/Fixed_Summary.pdf) |
| CONTINUATION | 2026-08-20T12:17:48Z | 27 | [Markdown](docs/CONTINUATION.md) | [HTML](docs/CONTINUATION.html) | [PDF](docs/CONTINUATION.pdf) |
| PORTING-FROM-LAVA | 2026-07-01T16:18:43Z | 1 | [Markdown](docs/PORTING-FROM-LAVA.md) | [HTML](docs/PORTING-FROM-LAVA.html) | [PDF](docs/PORTING-FROM-LAVA.pdf) |
| REMAINING_WORK_PLAN | 2026-08-07T19:10:54Z | 2 | [Markdown](docs/REMAINING_WORK_PLAN.md) | [HTML](docs/REMAINING_WORK_PLAN.html) | [PDF](docs/REMAINING_WORK_PLAN.pdf) |
| COMPLETION_STATUS | 2026-06-06T00:00:00Z | 1 | [Markdown](docs/COMPLETION_STATUS.md) | [HTML](docs/COMPLETION_STATUS.html) | [PDF](docs/COMPLETION_STATUS.pdf) |
| RELEASE_READINESS_20260616 | 2026-06-16T10:30:00Z | 1 | [Markdown](docs/RELEASE_READINESS_20260616.md) | [HTML](docs/RELEASE_READINESS_20260616.html) | [PDF](docs/RELEASE_READINESS_20260616.pdf) |
| QA_DISCOVERY_LEDGER | 2026-08-21T15:05:00Z | 16 | [Markdown](docs/QA_DISCOVERY_LEDGER.md) | [HTML](docs/QA_DISCOVERY_LEDGER.html) | [PDF](docs/QA_DISCOVERY_LEDGER.pdf) |
| GOVERNANCE_AUDIT_2026-08-07 | 2026-08-07T19:10:54Z | 1 | [Markdown](docs/GOVERNANCE_AUDIT_2026-08-07.md) | [HTML](docs/GOVERNANCE_AUDIT_2026-08-07.html) | [PDF](docs/GOVERNANCE_AUDIT_2026-08-07.pdf) |
| GOVERNANCE_AUDIT_2026-08-08_ROUND2 | 2026-08-09T12:54:30Z | 6 | [Markdown](docs/GOVERNANCE_AUDIT_2026-08-08_ROUND2.md) | [HTML](docs/GOVERNANCE_AUDIT_2026-08-08_ROUND2.html) | [PDF](docs/GOVERNANCE_AUDIT_2026-08-08_ROUND2.pdf) |
| browser_extension/Status | 2026-08-20T12:27:23Z | 16 | [Markdown](docs/browser_extension/Status.md) | [HTML](docs/browser_extension/Status.html) | [PDF](docs/browser_extension/Status.pdf) |
| browser_extension/Status_Summary | 2026-08-20T12:27:23Z | 4 | [Markdown](docs/browser_extension/Status_Summary.md) | [HTML](docs/browser_extension/Status_Summary.html) | [PDF](docs/browser_extension/Status_Summary.pdf) |
| browser_extension/RELEASE_READINESS | 2026-06-13T13:10:00Z | 4 | [Markdown](docs/browser_extension/RELEASE_READINESS.md) | [HTML](docs/browser_extension/RELEASE_READINESS.html) | [PDF](docs/browser_extension/RELEASE_READINESS.pdf) |
| codegraph/Status | 2026-08-18T13:33:41Z | 2 | [Markdown](docs/codegraph/Status.md) | [HTML](docs/codegraph/Status.html) | [PDF](docs/codegraph/Status.pdf) |
| codegraph/Status_Summary | 2026-08-20T12:27:23Z | 1 | [Markdown](docs/codegraph/Status_Summary.md) | [HTML](docs/codegraph/Status_Summary.html) | [PDF](docs/codegraph/Status_Summary.pdf) |
| features/Status | 2026-08-21T00:00:00Z | 10 | [Markdown](docs/features/Status.md) | [HTML](docs/features/Status.html) | [PDF](docs/features/Status.pdf) |
| features/Status_Summary | 2026-08-20T12:27:23Z | 8 | [Markdown](docs/features/Status_Summary.md) | [HTML](docs/features/Status_Summary.html) | [PDF](docs/features/Status_Summary.pdf) |
<!-- doc-link-section:end -->

### Getting started & operation

- [`docs/README.md`](docs/README.md) — secondary index of every file directly under `docs/`
- [`docs/USER_MANUAL.md`](docs/USER_MANUAL.md) — end-user walkthrough
- [`docs/TOKENS_AND_KEYS.md`](docs/TOKENS_AND_KEYS.md) — **⭐ credentials / tokens / env vars (mandatory vs optional + registration links)**
- [`docs/DESIGN_SYSTEM.md`](docs/DESIGN_SYSTEM.md) — runtime-switchable palette catalogue (8 palettes, dark + light, Darcula default)
- [`docs/PLUGINS.md`](docs/PLUGINS.md) — the 43 plugin engines
- [`docs/PLUGIN_TROUBLESHOOTING.md`](docs/PLUGIN_TROUBLESHOOTING.md) — what to check when a plugin breaks
- [`docs/MAGNET_LINKS.md`](docs/MAGNET_LINKS.md) — magnet link implementation guide
- [`docs/DOWNLOAD_FIX.md`](docs/DOWNLOAD_FIX.md) — RuTracker plugin download fix
- [`docs/RELEASE_TORRENT_UPLOAD_FIX.md`](docs/RELEASE_TORRENT_UPLOAD_FIX.md) — release report: torrent file upload fix
- [`docs/JACKETT_INTEGRATION.md`](docs/JACKETT_INTEGRATION.md) — Jackett integration
- [`docs/DEAD_TRACKERS_EXPLAINED.md`](docs/DEAD_TRACKERS_EXPLAINED.md) — dead public tracker status
- [`docs/TRACKER_AUTH_TESTING.md`](docs/TRACKER_AUTH_TESTING.md) — tracker credentials live testing
- [`docs/MERGE_SEARCH_DIAGNOSTICS.md`](docs/MERGE_SEARCH_DIAGNOSTICS.md) — merge-search diagnostics + rebuild/restart contract

### Architecture & subsystems

- [`docs/architecture/`](docs/architecture/) — 5 Mermaid diagrams (topology, search lifecycle, plugin execution, bridge, shutdown)
- [`docs/DATA_MODEL.md`](docs/DATA_MODEL.md) — Pydantic schemas & lifecycle (no relational DB)
- [`docs/CONCURRENCY.md`](docs/CONCURRENCY.md) — asyncio semaphore + TTL caches + retry/backoff
- [`docs/OBSERVABILITY.md`](docs/OBSERVABILITY.md) — Prometheus + Grafana + OpenTelemetry
- [`docs/PERFORMANCE.md`](docs/PERFORMANCE.md) — benchmark + load + stress test layout
- [`docs/api/openapi.json`](docs/api/openapi.json) — frozen OpenAPI spec (diffed in CI)
- [`docs/API_Summary.md`](docs/API_Summary.md) — API domain summary
- [`docs/Architecture_Summary.md`](docs/Architecture_Summary.md) — architecture domain summary
- [`docs/CODEGRAPH.md`](docs/CODEGRAPH.md) — CodeGraph code-intelligence integration (also indexed above in Tracked-Items via `codegraph/Status`)
- [`docs/CodeGraph_Summary.md`](docs/CodeGraph_Summary.md) — CodeGraph domain summary
- [`docs/MULTITRACK.md`](docs/MULTITRACK.md) — multi-track development registration (Track 11 rationale)
- [`docs/CROSS_APP_THEME_PLAN.md`](docs/CROSS_APP_THEME_PLAN.md) — cross-app theme plan

### Quality & security

- [`docs/SECURITY.md`](docs/SECURITY.md) — threat model + credential storage
- [`docs/SCANNING.md`](docs/SCANNING.md) — Snyk + Sonar + Semgrep + Trivy + Gitleaks + bandit + pip-audit
- [`docs/QUALITY_STACK.md`](docs/QUALITY_STACK.md) — the opt-in `docker-compose.quality.yml` stack
- [`docs/AGENT_GUARDRAILS.md`](docs/AGENT_GUARDRAILS.md) — §11.4.109 anti-forgetting enforcement (subagent constitutional preamble + orchestrator pre-action checklist)
- [`docs/CONSTITUTION_ADDENDUM_QUALITY.md`](docs/CONSTITUTION_ADDENDUM_QUALITY.md) — constitution addendum: quality stack (Principle I exception)
- [`docs/PLUGIN_AUDIT.md`](docs/PLUGIN_AUDIT.md) — plugin audit matrix
- [`docs/TEST_RESULTS.md`](docs/TEST_RESULTS.md) — snapshot of last full test run
- [`docs/TEST_SUITE_GUIDE.md`](docs/TEST_SUITE_GUIDE.md) — test suite guide
- [`docs/testing/`](docs/testing/) — DDoS resilience + test-type matrix notes

### Incidents & QA evidence

Per §11.4.238, automated HelixQA coverage is the discovery layer — manual/operator/agent-found
defects are confirmation-only, and every out-of-band finding gets a coverage-escape-audit entry
here.

- [`docs/QA_DISCOVERY_LEDGER.md`](docs/QA_DISCOVERY_LEDGER.md) — the discovery-channel ledger + coverage-escape schema (also indexed above in Tracked-Items)
- [`docs/incidents/`](docs/incidents/) — host-safety + CONST-033 forensic investigations, including the latest [2026-08-18 2nd perceived forced-logout](docs/incidents/2026-08-18-perceived-forced-logout-2nd.md) triage (root cause: partial, §11.4.6 `UNCONFIRMED:` boundary honestly stated; preventive gate: the resource-pressure signature challenge above)
- [`docs/qa/`](docs/qa/) — per-item captured machine evidence (§11.4.5 / §11.4.69 / §11.4.83), one directory per workable item / task run — e.g. [`docs/qa/BOB-116/`](docs/qa/BOB-116/)
- [`docs/history/BOB-079-attributed-auto-commit-history.md`](docs/history/BOB-079-attributed-auto-commit-history.md) — retroactive, evidenced attribution for the 14 unattributed `Auto-commit`/`sync:` commits in `v1.0.0-rc..HEAD` (BOB-079/RD2-12). Attribution is read from each commit's DIFF, never its subject line; 3 of 14 are evidence-backed and 11 are recorded literally as UNKNOWN (§11.4.6 — a fabricated attribution is worse than an absent one). A forward-only record, never a history rewrite (§11.4.113)
- [`docs/HOST_POWER_MANAGEMENT.md`](docs/HOST_POWER_MANAGEMENT.md) — CONST-033 host power management hard ban
- [`docs/guides/forced-logout-flight-recorder.md`](docs/guides/forced-logout-flight-recorder.md) — the flight-recorder guide for perceived-forced-logout triage

### Research, planning, migration & session archives

Working documents, dated research notes, superseded-implementation plans, and dated session
reports — browsable indexes rather than individually curated, since new dated entries land
continuously and any per-file categorization here would drift the moment a new one is added.

- [`docs/research/`](docs/research/) — dated investigation write-ups (tracker discovery, plugin audits, browser-extension corpus)
- [`docs/superpowers/`](docs/superpowers/) — long-horizon implementation plans + design specs
- [`docs/browser_extension/`](docs/browser_extension/) — architecture, changelog, install, store listing, user guide, coverage ledger, and internal `_analysis`/`_plan` working notes (Status docs indexed above in Tracked-Items)
- [`docs/migration/`](docs/migration/) — Python-to-Go migration spec + parity gaps
- [`docs/plans/`](docs/plans/) — dated implementation plans
- [`docs/proposals/`](docs/proposals/) — architectural proposals under consideration
- [`docs/demos/`](docs/demos/) — dated demo write-ups
- [`docs/issues/`](docs/issues/) — frozen post-mortems for specific incidents (distinct from the live `docs/Issues.md` tracker above)
- [`docs/systemd/UNITS.md`](docs/systemd/UNITS.md) — systemd unit reference
- [`docs/SESSION_REPORT_2026-04-19.md`](docs/SESSION_REPORT_2026-04-19.md) — rolling session report
- [`docs/SYSTEMATIC_DEBUGGING_2026-04-19.md`](docs/SYSTEMATIC_DEBUGGING_2026-04-19.md) — systematic debugging session log
- [`docs/Demos_Summary.md`](docs/Demos_Summary.md) — demos domain summary
- [`docs/Migration_Summary.md`](docs/Migration_Summary.md) — migration domain summary
- [`docs/Scripts_Summary.md`](docs/Scripts_Summary.md) — scripts domain summary
- [`docs/Superpowers_Summary.md`](docs/Superpowers_Summary.md) — superpowers domain summary

### Manual QA

Per §11.4.185, automated gates are necessary but not sufficient — every release deliverable
requires a final human confirmation pass. Per-session manual-QA checklists live under
[`docs/manual-qa/`](docs/manual-qa/), one file per session, in the §11.4.153 per-feature
Status/video-confirmation format.

- [`docs/manual-qa/2026-08-18-session-manual-qa-checklist.md`](docs/manual-qa/2026-08-18-session-manual-qa-checklist.md) — 12-feature checklist covering the boba-stack reachability, cross-tracker search/dedup, download flow, BOB-112 `/healthz` DDoS mitigation, constitution v68 landing, resource-pressure timer, CONST-033 challenge, and pre-build gate for the `457cca4`→`63f3f88` session range

### Testing

- [`docs/TESTING.md`](docs/TESTING.md) — catalogue of every test type (30 rows)
- [`docs/COVERAGE_BASELINE.md`](docs/COVERAGE_BASELINE.md) — per-module coverage gates
- [`tests/README.md`](tests/README.md) — layout of the `tests/` tree

### Development

- [`CONTRIBUTING.md`](CONTRIBUTING.md) — contribution workflow
- [`CLAUDE.md`](CLAUDE.md) — Claude Code agent protocol (TDD + rebuild-reboot)
- [`AGENTS.md`](AGENTS.md) — runtime development guidance
- [`.specify/memory/constitution.md`](.specify/memory/constitution.md) — **binding architectural contract (v1.1.0)**
- [`docs/scripts/`](docs/scripts/) — per-script user guides (§11.4.18), one `<name>.md` per `scripts/*.sh` / `challenges/scripts/*.sh` — e.g. [`commit-push-all.md`](docs/scripts/commit-push-all.md), [`capture-workable-items-db-delta.md`](docs/scripts/capture-workable-items-db-delta.md), [`regenerate-continuation-exports.md`](docs/scripts/regenerate-continuation-exports.md)

### Courses (self-paced, Asciinema)

- [`courses/01-operator/`](courses/01-operator/) — Your first search
- [`courses/02-plugin-author/`](courses/02-plugin-author/) — Authoring a nova3 plugin
- [`courses/03-contributor/`](courses/03-contributor/) — TDD + rebuild-reboot deep dive
- [`courses/04-security-ops/`](courses/04-security-ops/) — Threat model + scanner bundle

### Release / CI

- [`CHANGELOG.md`](CHANGELOG.md)
- [`releases/README.md`](releases/README.md) — release artefacts layout
- [`docs/OUT_OF_SANDBOX.md`](docs/OUT_OF_SANDBOX.md) — items requiring external credentials (HelixQA / OpenCode / submodule orgs)

---

## Architecture

```
                       ┌───────────────────────────────┐
                       │       qbittorrent-proxy        │
                       │      (python:3.12-alpine)      │
  http://:7186 ────────┤                                 │
   Download proxy      │  Download proxy (:7186) ────────┼──► qBittorrent (:7185)
                       │                                 │
  http://:7187 ────────┤  Merge search service (:7187)   │
   Angular SPA +       │  ├── /api/v1/search + SSE       │
   FastAPI             │  ├── /api/v1/bridge/health      │
                       │  └── /api/v1/auth/...           │
                       └───────────────────────────────┘
                                     ▲
  http://:7188 ── webui-bridge.py (host process) — private-tracker bridge

Opt-in (docker-compose.quality.yml):
   http://:9000   SonarQube              profile: quality
   http://:9090   Prometheus             profile: observability
   http://:3000   Grafana                profile: observability
   (run-once)     Snyk / Semgrep /
                  Trivy / Gitleaks       profile: run-once
```

Full Mermaid renders in [`docs/architecture/`](docs/architecture/).

---

## Testing

```bash
# Non-live-HTTP suites — run anywhere, ~10s
python3 -m pytest tests/unit/ tests/e2e/ tests/contract/ --no-cov -q

# Benchmarks — dedupe perf + live-HTTP fan-out benchmarks, ~4min
python3 -m pytest tests/benchmark/ --no-cov -q

# Security — hits the live merge service, needs stack up
python3 -m pytest tests/security/ --no-cov -q

# Integration — same
python3 -m pytest tests/integration/ --no-cov -q -m "not requires_credentials"

# Frontend
npx --prefix frontend ng test --watch=false

# Full scanner sweep (non-interactive; skips scanners with missing tokens)
./scripts/scan.sh --all

# Pre-build invariant sweep — 25 checks (workable-items integrity, docs-chain
# sync, resource-pressure signature, mutation-residue, §11.4.238 discovery
# ledger freshness, ...) run before every build
./scripts/pre_build_verification.sh

# HelixQA Challenges — 31 scripts under challenges/scripts/, e.g.:
./challenges/scripts/resource_pressure_signature_challenge.sh
./challenges/scripts/ddos_resilience_challenge.sh --healthz
```

See [`docs/TESTING.md`](docs/TESTING.md) for the 30-row test-type catalogue.

---

## Releases

Non-interactive builder at [`scripts/build-releases.sh`](scripts/build-releases.sh) produces artefacts under [`releases/<version>/`](releases/README.md):

```bash
./scripts/build-releases.sh              # all targets, all channels
./scripts/build-releases.sh frontend     # one target
./scripts/build-releases.sh --channel release
```

Each artefact ships with `SHA256SUMS` + `BUILD_INFO.json`.

---

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) and the TDD protocol in [`CLAUDE.md`](CLAUDE.md). PRs must keep the following green:

- Python unit + e2e + contract (`pytest` — 4501 tests collected, see docs/TESTING.md)
- Frontend Vitest (`ng test` — 371 tests collected, see docs/TESTING.md)
- Ruff + bandit + shellcheck (via `scripts/scan.sh`)

---

## License

Apache 2.0 — see [`LICENSE`](LICENSE).
