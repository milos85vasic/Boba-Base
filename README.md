<!--
  §11.4.44 revision marker (voluntary — Constitution.md §11.4.44 explicitly exempts
  README.md from the mandatory revision-header gate; tracked here anyway for
  freshness auditing per the §11.4.257/§11.4.259 refresh mandate).
  Revision: 1
  Last modified: 2026-08-18T23:15:00Z
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
  <img alt="tests"          src="https://img.shields.io/badge/python%20tests-5260%20collected-blue">
  <img alt="vitest"         src="https://img.shields.io/badge/frontend%20tests-371%20collected-blue">
  <img alt="plugins"        src="https://img.shields.io/badge/plugins-48-blue">
  <img alt="merge"          src="https://img.shields.io/badge/merge_service-FastAPI%20%3A7187-orange">
  <img alt="ci"             src="https://img.shields.io/badge/ci-manual%20%28.%2Fci.sh%2C%20no%20auto--trigger%29-success">
  <img alt="pre-build"      src="https://img.shields.io/badge/pre--build%20invariants-25-blue">
  <img alt="challenges"     src="https://img.shields.io/badge/challenges-31-blue">
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
    - pre-build invariants: informational count from the highest `[N/N]` label
      in `scripts/pre_build_verification.sh` (currently `[25/25]`, includes the
      new CM-DOCS-CHAIN-ENGINE-VERIFY + CM-RESOURCE-PRESSURE-SIGNATURE-CHECK
      invariants) — a count, not an asserted current PASS across all 25.
    - challenges: informational count of `challenges/scripts/*.sh` (31),
      including the new resource_pressure_signature_challenge.sh +
      verify_resource_pressure_polarity.sh + the ddos_resilience_challenge.sh
      `--healthz` mode extension — a count, not an asserted current PASS.
  tests/vitest/plugins/merge/scan/license badges are carried forward unverified
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

The mandated entry point (§11.4.57 / §11.4.212) for every tracker and status document in this
repository — `Last modified` and `Revision` are sourced verbatim from each document's own
revision header (§11.4.44); a `—` means the document currently carries no revision header or has
no HTML/PDF export yet (never fabricated).

| Document | Last modified | Revision | Markdown | HTML | PDF |
|---|---|---|---|---|---|
| Issues | 2026-08-18T19:17:52Z | 10 | [Markdown](docs/Issues.md) | [HTML](docs/Issues.html) | [PDF](docs/Issues.pdf) |
| Issues_Summary | — | — | [Markdown](docs/Issues_Summary.md) | [HTML](docs/Issues_Summary.html) | [PDF](docs/Issues_Summary.pdf) |
| Fixed | 2026-08-18T20:55:14Z | 20 | [Markdown](docs/Fixed.md) | [HTML](docs/Fixed.html) | [PDF](docs/Fixed.pdf) |
| Fixed_Summary | — | — | [Markdown](docs/Fixed_Summary.md) | [HTML](docs/Fixed_Summary.html) | [PDF](docs/Fixed_Summary.pdf) |
| CONTINUATION | 2026-08-18T21:10:20Z | 24 | [Markdown](docs/CONTINUATION.md) | [HTML](docs/CONTINUATION.html) | [PDF](docs/CONTINUATION.pdf) |
| PORTING-FROM-LAVA | 2026-07-01T16:18:43Z | 1 | [Markdown](docs/PORTING-FROM-LAVA.md) | — (not yet exported) | — (not yet exported) |
| REMAINING_WORK_PLAN | 2026-08-07T19:10:54Z | 2 | [Markdown](docs/REMAINING_WORK_PLAN.md) | [HTML](docs/REMAINING_WORK_PLAN.html) | [PDF](docs/REMAINING_WORK_PLAN.pdf) |
| GOVERNANCE_AUDIT_2026-08-07 | 2026-08-07T19:10:54Z | 1 | [Markdown](docs/GOVERNANCE_AUDIT_2026-08-07.md) | — (not yet exported) | — (not yet exported) |
| browser_extension/Status | 2026-06-13T13:10:00Z | 15 | [Markdown](docs/browser_extension/Status.md) | [HTML](docs/browser_extension/Status.html) | [PDF](docs/browser_extension/Status.pdf) |
| browser_extension/Status_Summary | 2026-06-10T20:05:00Z | 3 | [Markdown](docs/browser_extension/Status_Summary.md) | [HTML](docs/browser_extension/Status_Summary.html) | [PDF](docs/browser_extension/Status_Summary.pdf) |
| browser_extension/RELEASE_READINESS | 2026-06-13T13:10:00Z | 4 | [Markdown](docs/browser_extension/RELEASE_READINESS.md) | [HTML](docs/browser_extension/RELEASE_READINESS.html) | [PDF](docs/browser_extension/RELEASE_READINESS.pdf) |
| COMPLETION_STATUS | 2026-06-06T00:00:00Z | 1 | [Markdown](docs/COMPLETION_STATUS.md) | [HTML](docs/COMPLETION_STATUS.html) | [PDF](docs/COMPLETION_STATUS.pdf) |
| RELEASE_READINESS_20260616 | 2026-06-16T10:30:00Z | 1 | [Markdown](docs/RELEASE_READINESS_20260616.md) | [HTML](docs/RELEASE_READINESS_20260616.html) | [PDF](docs/RELEASE_READINESS_20260616.pdf) |
| features/Status | 2026-08-18T13:33:41Z | 8 | [Markdown](docs/features/Status.md) | [HTML](docs/features/Status.html) | [PDF](docs/features/Status.pdf) |
| features/Status_Summary | 2026-06-16T23:30:00Z | 7 | [Markdown](docs/features/Status_Summary.md) | [HTML](docs/features/Status_Summary.html) | [PDF](docs/features/Status_Summary.pdf) |
| QA_DISCOVERY_LEDGER | 2026-08-18T22:10:00Z | 9 | [Markdown](docs/QA_DISCOVERY_LEDGER.md) | [HTML](docs/QA_DISCOVERY_LEDGER.html) | [PDF](docs/QA_DISCOVERY_LEDGER.pdf) |

### Getting started & operation

- [`docs/USER_MANUAL.md`](docs/USER_MANUAL.md) — end-user walkthrough
- [`docs/TOKENS_AND_KEYS.md`](docs/TOKENS_AND_KEYS.md) — **⭐ credentials / tokens / env vars (mandatory vs optional + registration links)**
- [`docs/DESIGN_SYSTEM.md`](docs/DESIGN_SYSTEM.md) — runtime-switchable palette catalogue (8 palettes, dark + light, Darcula default)
- [`docs/PLUGINS.md`](docs/PLUGINS.md) — the 48 plugin engines
- [`docs/PLUGIN_TROUBLESHOOTING.md`](docs/PLUGIN_TROUBLESHOOTING.md) — what to check when a plugin breaks

### Architecture & subsystems

- [`docs/architecture/`](docs/architecture/) — 5 Mermaid diagrams (topology, search lifecycle, plugin execution, bridge, shutdown)
- [`docs/DATA_MODEL.md`](docs/DATA_MODEL.md) — Pydantic schemas & lifecycle (no relational DB)
- [`docs/CONCURRENCY.md`](docs/CONCURRENCY.md) — asyncio semaphore + TTL caches + retry/backoff
- [`docs/OBSERVABILITY.md`](docs/OBSERVABILITY.md) — Prometheus + Grafana + OpenTelemetry
- [`docs/PERFORMANCE.md`](docs/PERFORMANCE.md) — benchmark + load + stress test layout
- [`docs/api/openapi.json`](docs/api/openapi.json) — frozen OpenAPI spec (diffed in CI)

### Quality & security

- [`docs/SECURITY.md`](docs/SECURITY.md) — threat model + credential storage
- [`docs/SCANNING.md`](docs/SCANNING.md) — Snyk + Sonar + Semgrep + Trivy + Gitleaks + bandit + pip-audit
- [`docs/QUALITY_STACK.md`](docs/QUALITY_STACK.md) — the opt-in `docker-compose.quality.yml` stack

### Incidents & QA evidence

Per §11.4.238, automated HelixQA coverage is the discovery layer — manual/operator/agent-found
defects are confirmation-only, and every out-of-band finding gets a coverage-escape-audit entry
here.

- [`docs/QA_DISCOVERY_LEDGER.md`](docs/QA_DISCOVERY_LEDGER.md) — the discovery-channel ledger + coverage-escape schema (also indexed above in Tracked-Items)
- [`docs/incidents/`](docs/incidents/) — host-safety + CONST-033 forensic investigations, including the latest [2026-08-18 2nd perceived forced-logout](docs/incidents/2026-08-18-perceived-forced-logout-2nd.md) triage (root cause: partial, §11.4.6 `UNCONFIRMED:` boundary honestly stated; preventive gate: the resource-pressure signature challenge above)
- [`docs/qa/`](docs/qa/) — per-item captured machine evidence (§11.4.5 / §11.4.69 / §11.4.83), one directory per workable item / task run — e.g. [`docs/qa/BOB-116/`](docs/qa/BOB-116/)

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

- Python unit + e2e + contract (`pytest` — 4442 tests collected, see docs/TESTING.md)
- Frontend Vitest (`ng test` — 371 tests collected, see docs/TESTING.md)
- Ruff + bandit + shellcheck (via `scripts/scan.sh`)

---

## License

Apache 2.0 — see [`LICENSE`](LICENSE).
