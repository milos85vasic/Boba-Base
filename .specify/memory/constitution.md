<!--
Sync Impact Report:
- Version change: 1.2.0 → 1.3.0 (MINOR)
- Bump rationale: 2 new principles added (Anti-Bluff Captured Evidence,
  Host-Session Safety), plus material expansions to Principles I, II, III,
  IV, V, VI to reflect four months of codebase evolution (Aug 2026 drift
  review). No principle removed or redefined incompatibly.
- Modified principles (title unchanged unless noted):
  I.   Container-First Architecture — service list 2 → 5, resource limits
       + rootless Podman mandate added.
  II.  Plugin Contract Integrity — 12 → 43 managed plugins, roster-backed
       fingerprint sync (constitution §11.4.86) added.
  III. Credential & Secret Security — cookies-file autoload (operator
       mandate 2026-08-15) + boba.db encrypted vault + BOBA_MASTER_KEY /
       BOBA_API_TOKEN added.
  IV.  Container Runtime Portability — start.sh owns orchestration,
       rootless Podman required (Hard Stop #3 / constitution §11.4.161).
  V.   Private Tracker Bridge Pattern — Go binary variant under
       `--profile go` documented alongside Python webui-bridge.py.
  VI.  Validation-Driven Development — GitHub Actions permanently removed
       (Hard Stop #1), `./ci.sh` canonical, ruff configured in
       pyproject.toml, Angular 21 + Go test paths added.
- New principles:
  XII.  Anti-Bluff Captured Evidence (wraps constitution §11.4 / §11.4.5 /
        §11.4.107 into a project-level covenant with `docs/qa/<run-id>/`
        evidence discipline).
  XIII. Host-Session Safety (wraps constitution §CONST-033 / §12 host
        power-state ban + container mem_limit / pids_limit / oom_score_adj
        into a project-level rule).
- Added sections: Governance section now cites `constitution/` submodule
  as the supreme inherited authority (§11.4.35 canonical-root inheritance).
- Removed sections: (none)
- Templates requiring updates:
  ✅ plan-template.md — Constitution Check section is generic
     ("[Gates determined based on constitution file]"); no hard-coded
     principle names — no changes needed.
  ✅ spec-template.md — no constitution refs — no changes needed.
  ✅ tasks-template.md — no constitution refs — no changes needed.
  ✅ checklist-template.md — generic — no changes needed.
  ✅ agent-file-template.md — generic — no changes needed.
  ✅ .claude/skills/speckit-*/SKILL.md — no principle refs (grep clean)
     — no changes needed.
- Follow-up TODOs (deferred, tracked here rather than embedded as bracket
  tokens):
  1. TODO(COVERAGE_GATE): Principle X keeps the 49% coverage gate as-is.
     The inherited Helix Universal Constitution §11.4.224 mandates a
     ≥85% floor with a §11.4.224(E) exclusion-list fence. Raising the
     Boba gate is an operator §11.4.66 decision (options: hard floor /
     §11.4.135-style monotone-decrease ratchet / per-corpus phase-in /
     changed-code-only with deadline) that MUST be recorded before
     first enforcement. No autonomous ratchet change is applied here.
  2. TODO(BOB_MASTER_KEY_ROTATION): CORRECTED 2026-08-20 — an earlier
     revision of this note claimed "no rotation procedure exists",
     which was inaccurate (§11.4.6). A DOCUMENTED procedure does
     exist at `docs/BOBA_DATABASE.md` § "Key Rotation". The real
     defect is narrower and worse: that procedure prescribes
     `./bin/boba-jackett rotate-key` and `envfile-replace`, and
     BOTH subcommands are ABSENT from `qBitTorrent-go/**/*.go`
     (verified by control-needle-checked search, §11.4.201(7)(b)).
     The section was also titled "Manual rotation" while
     `internal/bootstrap/bootstrap.go` writes `§ "Key Rotation"`
     into every operator's `.env` — a dangling pointer, now fixed
     by renaming the heading. Implementing the two subcommands is
     a §11.4.197 tracked feature, not a constitutional change.
-->

# qBitTorrent Platform Constitution

## Core Principles

### I. Container-First Architecture

All services MUST run as containerized workloads orchestrated via
`docker-compose.yml`. The platform comprises exactly FIVE container
services — `qbittorrent` (the BitTorrent client), `jackett` (indexer
aggregator), `qbittorrent-proxy` (the Python download-proxy /
FastAPI merge service), `qbittorrent-proxy-go` (opt-in Go alternative
under compose profile `go`), and `boba-jackett` (Go service owning the
Jackett management API and encrypted credential vault) — plus one
optional host process (`webui-bridge.py`).

- Every service MUST be defined in `docker-compose.yml` with explicit
  image or build context, port mappings, volume mounts, restart
  policies, and health checks.
- Every container MUST declare `mem_limit`, `pids_limit`, and
  `oom_score_adj: 500` so it dies before the user session under host
  memory pressure (per constitution §CONST-033 operational note and
  §11.4.161 rootless container mandate).
- New services MUST NOT be added without updating `docker-compose.yml`
  AND all lifecycle scripts (`start.sh`, `stop.sh`), AND at least one
  health-check endpoint responding on the service's port.
- Volume mounts MUST use `./tmp/` (mapped to `/shared-tmp`) for
  inter-container file exchange (torrent files, temporary downloads).
- Network mode MUST be `host` for all services to enable seamless
  localhost communication.
- The `config/` directory tree is the single source of truth for
  runtime configuration and MUST NOT contain secrets. `config/boba.db`
  is the encrypted credential/config store owned by `boba-jackett` —
  see Principle III.

**Rationale**: Container-first ensures reproducible deployments,
environmental consistency, and clean service isolation. Per-container
resource limits are an explicit host-safety requirement — an
unbounded container that OOM-kills the user session is a §CONST-033
violation. The compose file is the contract; drift between
`docker-compose.yml`, lifecycle scripts, and this principle is itself
a defect.

### II. Plugin Contract Integrity

Every search plugin MUST conform to the qBittorrent nova3 engine
contract. Plugins are Python classes deployed to
`config/qBittorrent/nova3/engines/`.

- Each plugin MUST define class attributes: `url`, `name`,
  `supported_categories` (dict mapping category name to ID string).
- Each plugin MUST implement `search(self, what, cat='all')` producing
  output exclusively through `novaprinter.print()`.
- Each plugin MUST implement `download_torrent(self, url)` returning
  a magnet link or file path.
- Private-tracker plugins MUST read credentials from environment
  variables using the `try: import novaprinter` optional-dependency
  pattern for standalone testability.
- Plugins MUST be validated with `python3 -m py_compile` before
  installation. Syntax-invalid plugins MUST NOT be deployed.
- The `install-plugin.sh` managed list is the canonical curated set
  (currently 43 entries: academictorrents, ali213, anilibra,
  audiobookbay, bitru, bt4g, btsow, bitsearch, extratorrent, eztv,
  gamestorrents, glotorrents, iptorrents, jackett, kickass, kinozal,
  limetorrents, linuxtracker, megapeer, nnmclub, nyaa, one337x,
  pctorrent, piratebay, pirateiro, rockbox, rutor, rutracker, snowfl,
  solidtorrents, therarbg, tokyotoshokan, torlock, torrentdownload,
  torrentfunk, torrentgalaxy, torrentkitty, torrentproject,
  torrentscsv, xfsub, yihua, yourbittorrent, yts). Additional files
  in `plugins/` (utility modules such as `env_loader.py`, `helpers.py`,
  `novaprinter.py`, `nova2.py`; assets in `plugins/community/` and
  `plugins/webui_compatible/`) are NOT search plugins and are handled
  separately.
- The canonical plugin roster is roster-backed per constitution
  §11.4.86: a change to `install-plugin.sh`'s `PLUGINS=()` array or
  to any plugin's source triggers re-sync of derived docs (roster
  count in `README.md`, `AGENTS.md`, `PLUGIN_STATUS.md`, and this
  principle's enumeration if the curated set changes).

**Rationale**: The plugin contract is the extensibility backbone.
Violations cause silent search failures or broken downloads that are
hard to diagnose in a containerized environment. Roster fingerprinting
keeps docs from silently diverging as plugins are added or retired.

### III. Credential & Secret Security

Credentials MUST NEVER appear in version control. The project uses a
layered environment-variable loading system with strict priority rules,
supplemented by an encrypted SQLite vault owned by `boba-jackett`.

- `.env` is in `.gitignore` and MUST NEVER be committed. `.env.example`
  is the template with placeholder values only.
- Environment loading priority (first wins): shell environment →
  `./.env` → `~/.qbit.env` → container env from compose.
- Private-tracker credentials (`RUTRACKER_*`, `KINOZAL_*`,
  `NNMCLUB_*`, `IPTORRENTS_*`) MUST be loaded from environment
  variables, never hardcoded.
- Per-tracker cookies files at `${TRACKER_COOKIE_DIR:-$HOME/Downloads}
  /cookies_<tracker>.txt` (lowercase; `rutracker`, `nnmclub`, `rutor`,
  `kinozal` today) are auto-loaded into `.env` as
  `<TRACKER>_COOKIES=...` by `scripts/load-tracker-cookies.sh` before
  every `boba-svc up|restart`, `install.sh` Stage 6, and `start.sh`
  boot (operator mandate 2026-08-15). Every write is atomic, `chmod
  600`, and §11.4.10.A leak-audited. Cookie VALUES MUST NEVER enter
  logs, test reports, or commit messages; variable NAMES are
  loggable, values are not.
- `config/boba.db` is the authoritative encrypted vault for
  `tracker_credentials`, indexer overrides, and autoconfig history.
  `BOBA_MASTER_KEY` (32-byte hex AES-256-GCM key) MUST be present at
  boot — auto-generated on first run by `bootstrap.EnsureMasterKey`
  and mirrored by `start.sh ensure_boba_master_key`. Loss of
  `BOBA_MASTER_KEY` == total credential loss; back up `/config/boba.db`
  and `.env` together.
- `BOBA_API_TOKEN` (optional, per `docs/GOVERNANCE_AUDIT_2026-08-08_
  ROUND2.md` RD2-22) gates the mutating download/hooks/schedules/theme
  routes when set; unset leaves routes OPEN for backward compatibility
  (§11.4.122 no-silent-removal).
- WebUI credentials `admin`/`admin` are hardcoded by design in
  `start.sh`, `docker-compose.yml`, and scripts — do NOT change them.
- `.ruff_cache/` MUST remain in `.gitignore`.
- No secret values MAY appear in log output, test reports, or commit
  messages.

**Rationale**: Tracker credentials are user-specific and sensitive.
Hardcoded admin credentials are an intentional development default
documented in AGENTS.md. The encrypted vault + cookies-file autoload
close the gap where operators previously had to hand-edit `.env` for
every session-cookie refresh.

### IV. Container Runtime Portability

All shell scripts MUST auto-detect the container runtime, preferring
Podman (rootless) over Docker. The detection pattern is consistent
across all lifecycle scripts.

- Runtime detection order: `podman` (preferred, rootless required per
  constitution §11.4.161) → `docker`.
- Compose command detection: `podman-compose` → `docker compose` →
  `docker-compose`.
- All scripts MUST use the shared pattern: `detect_container_runtime()`
  setting `CONTAINER_RUNTIME` and `COMPOSE_CMD` variables.
- File operations inside container volumes MUST account for Podman
  rootless ownership: use `podman unshare cp` when copying plugins.
- Container orchestration is owned EXCLUSIVELY by the project's own
  orchestrator (`start.sh` and its subcommands `--reload-python`,
  `--reload-plugins`, `--recreate`); operators MUST NOT type raw
  `podman`/`docker` commands directly for container lifecycle (Hard
  Stop #3 per `docs/GOVERNANCE_AUDIT_2026-08-07.md` GA-27).
- `run-all-tests.sh` currently hardcodes Podman commands — this is a
  known limitation documented in AGENTS.md.

**Rationale**: Podman rootless is the primary target on Linux, but
Docker compatibility MUST be maintained. Consistent auto-detection
prevents user-facing errors. The single-entrypoint orchestrator
prevents ad-hoc `podman rm` invocations from leaving the stack in a
broken half-state.

### V. Private Tracker Bridge Pattern

Private-tracker downloads through the WebUI MUST be proxied through a
bridge process (port 7188) that routes requests to `nova2dl.py` with
proper authentication. The bridge exists in two implementations
(pick one per profile):

- **Python bridge (default)**: `webui-bridge.py` at the repository
  root, started manually (`python3 webui-bridge.py`) as a host
  process. NOT a container.
- **Go bridge (opt-in)**: the `webui-bridge` binary built from
  `qBitTorrent-go/cmd/webui-bridge/`, wired by compose profile `go`.

Both implementations share the same contract:

- The bridge intercepts download URLs matching known private tracker
  domains and delegates to `nova2dl.py` (Python) or its Go equivalent
  for authenticated downloads.
- Direct WebUI downloads bypass `nova2dl.py` and WILL fail for
  private trackers — this is the fundamental problem the bridge
  solves.
- Private-tracker URL patterns are defined in `PRIVATE_TRACKERS` dict
  (Python) / the equivalent Go registry, and MUST be kept in sync
  with plugin capabilities.
- WebUI-compatible plugin variants in `plugins/webui_compatible/` are
  alternatives for environments where the bridge cannot run.

**Rationale**: qBittorrent WebUI does not natively support
authenticated torrent downloads. The bridge pattern is an
architectural necessity, not an optional enhancement. Ship parity
between Python and Go implementations MUST be preserved — a plugin
that works via one bridge but silently fails via the other is a
Principle V violation.

### VI. Validation-Driven Development

All code changes MUST pass syntax validation, lint, and the test
suite before being considered complete. CI is manual and permanent;
there is no hosted CI pipeline.

- **NO CI/CD PIPELINES** (Hard Stop #1, permanent): the repository
  MUST NOT contain `.github/workflows/*.yml`, `.gitlab-ci.yml`,
  `Jenkinsfile`, `.travis.yml`, `.circleci/`, or any equivalent
  automated pipeline. All GitHub Actions workflow files have been
  removed. Do NOT create new ones.
- `./ci.sh` is the sole canonical validation entry point (`./ci.sh
  --quick` for syntax + unit only, `./ci.sh` for the full manual
  gate: syntax + unit + integration + e2e + container health).
- Bash scripts MUST pass `bash -n` syntax check.
- Python files MUST pass `python3 -m py_compile` syntax check.
- Python lint is `ruff` with the configuration in `pyproject.toml`
  (target `py312`, line 120, rule set `E,F,W,I,UP,B,SIM,RUF,ASYNC,
  S,PT,C4,TID`). `ruff check --fix .` and `ruff format .` are the
  fix/format entry points.
- The test suite (`./test.sh`, `./run-all-tests.sh`, `./ci.sh`) MUST
  be run after any change to plugins, scripts, or configuration.
- Plugin installation MUST be verified with `install-plugin.sh
  --verify`.
- Angular 21 dashboard (`frontend/`): `ng build` (production) and
  `ng test` (Vitest unit) MUST pass before frontend commits.
- Go backend (`qBitTorrent-go/`): `go test -race ./...` MUST pass
  before Go commits.

**Rationale**: In a containerized multi-service platform, a broken
plugin or script causes cascading failures. Manual CI is a deliberate
choice — the trade-off is that discipline lives in this document and
in `./ci.sh`, not in a hosted CI report.

### VII. Operational Simplicity

The platform MUST be operable with minimal commands. Setup, start,
stop, and testing each have dedicated scripts with consistent UX.

- `setup.sh` is the one-command onboarding: creates directories,
  installs plugins, generates config, starts containers.
- `start.sh` / `stop.sh` are the lifecycle commands with documented
  flags (`-p` pull, `-s` status, `-r` remove, `--purge` clean images,
  plus `start.sh` subcommands `--reload-python`, `--reload-plugins`,
  `--recreate` per Principle IV).
- All scripts MUST use the shared color-print helpers (`print_info`,
  `print_success`, `print_warning`, `print_error`) for consistent
  user feedback.
- All scripts MUST implement `-h, --help` with usage examples.
- Directory structure under the data directory (`Incomplete/`,
  `Torrents/All/`, `Torrents/Completed/`) is auto-created on start.
- The `config/qBittorrent/config/qBittorrent.conf` configuration file
  is auto-generated on first start. Stale configs at the wrong path
  are detected and cleaned up.

**Rationale**: The target audience is users deploying a torrent
platform, not Kubernetes operators. One-command operations reduce
support burden and onboarding friction.

### VIII. IPTorrents Freeleech Policy

IPTorrents is a ratio-sensitive private tracker. Automated downloads
MUST be freeleech-only to protect the user's ratio.

- All automated tests and download automation MUST ONLY download
  freeleech torrents from IPTorrents.
- Freeleech detection is performed by checking the `<span class="free">`
  HTML element in search results, and via the `&free=on` URL parameter
  for freeleech-only filtering.
- Freeleech results MUST be tagged with `IPTorrents [free]` in the
  `tracker_display` field of search results.
- Non-freeleech IPTorrents downloads cost upload ratio and MUST NEVER
  be triggered by automation, tests, or scheduled tasks.
- The `freeleech` boolean field on `SearchResult` MUST be present and
  accurate for all IPTorrents results.

**Rationale**: Downloading non-freeleech torrents from IPTorrents
without seeding back degrades the user's ratio and risks account
suspension. Automation must be ratio-safe by default.

### IX. Test-Driven Development

Every bug fix and feature MUST follow the TDD cycle.

- Write a failing test first (RED) that reproduces the defect on the
  CURRENT (broken) artifact per constitution §11.4.115 — not a
  synthetic failure the fix is then written to agree with.
- Observe the failure to confirm the test exercises the right code
  path.
- Write the minimal code to make the test pass (GREEN).
- Verify the full suite still passes.
- Only then commit.

This discipline applies to Python source, plugins, shell scripts, and
frontend TypeScript. A commit that changes production code without a
corresponding test change MUST be rejected in review.

**Rationale**: TDD is the primary defence against the "green tests,
broken product" anti-pattern. Tests written after the fact validate
what the author thinks the code does, not what it actually does.

### X. Hermetic Test Discipline

The test suite is the source of truth for correctness. Tests MUST be
hermetic, well-isolated, and located in the canonical directory.

- All merge-service tests MUST live in `./tests/`, NEVER in
  `download-proxy/tests/`.
- Unit tests MUST be heavily mocked and MUST NOT require running
  containers.
- Integration and E2E tests MAY require running containers but MUST
  fail loudly (not skip silently) when services are unavailable.
- Coverage gate is 49% and MUST be maintained or raised. Raising the
  gate requires updating `docs/COVERAGE_BASELINE.md` simultaneously.
  (Note: the inherited Helix Universal Constitution §11.4.224
  mandates a ≥85% floor; adoption of that higher floor is an
  operator §11.4.66 decision — see the Sync Impact Report
  TODO(COVERAGE_GATE).)
- `sys.modules` isolation for unit tests MUST NOT leak into
  integration or E2E tests.
- Event loop state MUST NOT leak between tests; async tests MUST use
  function-scoped loops.
- Test mocks MUST explicitly set `mock.pid = <int > 1>` when standing
  in for subprocess/proc objects — the default `MagicMock.__int__ ==
  1` triggers `os.killpg(1, ...)` == `kill(-1, ...)` and forcibly
  logs out the operator (BOB-116/120/123/124/125/126 forensic anchor,
  constitution §11.4.263). Mocking a `.pid` without an explicit `int
  > 1` is a defect.

**Rationale**: Hermetic tests give fast feedback during development.
Leaky isolation produces flaky failures that erode trust in the
suite and hide real regressions. Explicit `mock.pid` is the
project-specific instantiation of constitution §11.4.263's
process-group signal-safety mandate.

### XI. Minimal Source Commentary

The merge service Python source (`download-proxy/src/`) MUST contain
NO comments or docstrings. This is an intentional project convention.

- Comments explaining "what" the code does are forbidden; the code
  must be self-explanatory.
- Comments explaining "why" a non-obvious decision was made belong in
  the commit message or in `docs/`, not in source.
- Type hints on public methods are encouraged; they serve as
  machine-readable documentation.
- Test files, plugin files, scripts, and documentation are exempt
  from this rule.

**Rationale**: Comments rot. Commit messages and living docs are the
single source of truth for design rationale. Minimal commentary
forces clarity through naming and structure.

### XII. Anti-Bluff Captured Evidence

Every PASS for a user-visible feature MUST cite captured physical
evidence produced during the test / challenge run. This is the
project-level instantiation of the inherited Helix Universal
Constitution §11.4 (Anti-Bluff Covenant), §11.4.5 (captured-evidence
quality), §11.4.69 (universal sink-side evidence taxonomy), and
§11.4.107 (AV/test-validation techniques).

- Test PASS on a user-visible feature MUST assert on user-observable
  outcomes (DB rows, file content, response body fields, container
  state, DOM text, rendered HTML attributes, browser console errors)
  — NOT just HTTP status codes / "no error".
- Every new test MUST fail against a no-op stub of the feature it
  tests. If it does not, it is a bluff and MUST be strengthened or
  deleted.
- Challenges MUST drive the feature end-to-end via the actual user
  path (real HTTP, real file mutation, real container interaction),
  never a shortcut that skips the transition where the bug lives.
- For any new HTTP endpoint / CLI command / user-facing behavior:
  terminal output of an actual end-user invocation MUST be pasted in
  the same session as the change. Self-certification words
  ("verified", "tested", "working", "complete", "fixed", "passing")
  without pasted evidence are forbidden.
- Flaky tests are bluffs; they MUST be hardened or deleted, never
  retried until green.
- Regression tests MUST fail against the pre-fix code (revert the
  fix, confirm the test fails, then re-apply — per §11.4.115).
- Every feature that ships MUST carry an end-to-end evidence bundle
  under `docs/qa/<run-id>/` (per §11.4.83) — recorded transcripts,
  attached materials, structured assertions. A feature with no QA
  transcript is itself a PASS-bluff.
- No hardcoded `localhost` / `127.0.0.1` for client-facing URLs.
  Any URL, API base, CORS origin, or service address returned to a
  browser MUST derive from the request's `Host` header,
  `window.location`, or an explicit `PUBLIC_HOST` env var.

**Rationale**: The whole platform previously had episodes where tests
were green while the feature was broken for the end user. The
covenant is what makes "green" mean "usable." This principle
apparently duplicates rules present in the constitution submodule, and
it does — deliberately — because a bluff shipping in Boba specifically
is measured against Boba's own governing document, not only the
inherited one.

### XIII. Host-Session Safety

The project's scripts, tests, and automation MUST NOT compromise the
operator's host session. This is the project-level instantiation of
the inherited Helix Universal Constitution §CONST-033 (host
power-management hard ban) and §12 (host-session safety).

- STRICTLY FORBIDDEN: any code that triggers a host-level power-state
  transition. This includes `systemctl {suspend,hibernate,poweroff,
  halt,reboot,...}`, `loginctl {suspend,...}`, `pm-suspend`,
  `shutdown`, `dbus-send` / `busctl` calls to
  `org.freedesktop.login1.Manager.{Suspend,PowerOff,...}` or
  `org.freedesktop.UPower.{Suspend,...}`, and any `gsettings`
  mutation of `sleep-inactive-{ac,battery}-type` to anything except
  `nothing` or `blank`. See constitution §CONST-033 for the full
  forbidden list.
- Verification commands (`bash challenges/scripts/no_suspend_calls_
  challenge.sh` and `bash challenges/scripts/host_no_auto_poweroff_
  challenge.sh`) MUST pass before any change touching automation or
  scripts is considered complete.
- Every container MUST enforce its own resource ceiling
  (`mem_limit`, `pids_limit`, `oom_score_adj: 500`) so it dies before
  the user session under host memory pressure. See Principle I.
- Test process-group signal safety per Principle X: `killpg(pgid, ...)`
  where `pgid <= 1` is a disaster syscall (`kill(-1, sig)` = SIGKILL
  every UID-1000 process). Validate `isinstance(pgid, int) and pgid
  > 1` before every `os.killpg` / `syscall.Kill(-pgid, sig)` /
  `pkill -g` / `kill -<pgid>` call.
- Tests and challenges MUST be strictly limited to 30–40% of host
  system resources. Use `GOMAXPROCS=2`, `nice -n 19`, `ionice -c 3`
  for background heavy jobs. Exceeding the limits crashes the host
  and destroys operator work.
- Before diagnosing a "computer froze / logged me out" report as our
  fault, run the constitution §CONST-033 operational-note triage
  (uptime discontinuity check, `journalctl -k` for `will suspend`,
  OOM-kill decode with `oom_memcg` cgroup path). Container
  `libpod-...` OOM = containment working as designed, not our
  violation.

**Rationale**: The host runs mission-critical parallel CLI agents
and container workloads. Historical incidents (auto-suspend
2026-04-26 → data loss; poweroff 2026-04-28 → data loss; six forced
logouts on 2026-08-18/19 traced to `kill(-1, SIGKILL)` in a mocked
test) established that this class of failure is worse than any
missed feature. Host safety is non-negotiable.

## Security Requirements

- `.env` file MUST have `600` permissions: `chmod 600 .env`. Same
  applies to every per-tracker cookies file at
  `~/Downloads/cookies_<tracker>.txt`.
- All inter-container communication uses `localhost` via
  `network_mode: host`. No inter-container TLS is required.
- Ports exposed on the host and their firewall requirements:
  - `7185` — qBittorrent WebUI (container-internal, proxied via 7186)
  - `7186` — download-proxy → qBittorrent WebUI. MUST be firewalled
    from public access in production deployments.
  - `7187` — merge search service (FastAPI or Go). MUST be
    firewalled from public access in production deployments.
  - `7188` — webui-bridge. MUST NOT be exposed outside localhost.
  - `7189` — boba-jackett management API. MUST be firewalled from
    public access; when `BOBA_API_TOKEN` is set, unauthenticated
    external access is rejected — leaving it unset in a public
    deployment is a Principle III / Security violation.
  - `9117` — Jackett. MUST be firewalled from public access.
- No root escalation: containers run with `PUID=1000`/`PGID=1000`.
  Rootless Podman is required per Principle IV.
- `BOBA_MASTER_KEY` presence MUST be enforced at boot by
  `bootstrap.EnsureMasterKey`; a missing key on a populated
  `boba.db` is a Principle III violation and MUST fail the boot
  with an actionable error, never silently regenerate.
- Empty root files (`CONFIG`, `SCRIPT`, `EOF`) MUST NOT be removed
  — they may be referenced by existing tooling.
- The `tools/` and `Upstreams/` directories contain auxiliary scripts
  and upstream references that MUST NOT be modified without explicit
  justification.

## Development Workflow & Quality Gates

### Before Every Commit

1. Run `bash -n` on all modified shell scripts.
2. Run `python3 -m py_compile` on all modified Python files.
3. Run `ruff check .` (project-configured, see Principle VI); fix
   with `ruff check --fix .` and `ruff format .`.
4. For frontend changes: `cd frontend && ng test` (Vitest); for a
   production build check: `ng build`.
5. For Go changes: `cd qBitTorrent-go && go test -race ./...`.
6. Run `./test.sh --quick` (or `./ci.sh --quick`) to validate basic
   setup integrity.
7. Verify no secrets appear in `git diff` output (§11.4.10.A leak
   audit against the specific values being added).
8. If touching a user-visible feature: capture end-to-end evidence
   under `docs/qa/<run-id>/` per Principle XII.

### Before Every Release

1. Run `./ci.sh` — the full manual gate MUST pass.
2. Run `./run-all-tests.sh` — the full suite MUST pass.
3. Run `./install-plugin.sh --verify` — every managed plugin (43
   entries per Principle II) MUST be installed and syntactically
   valid.
4. Verify `docker-compose.yml` passes `$COMPOSE_CMD config`.
5. Run `bash challenges/scripts/no_suspend_calls_challenge.sh` and
   `bash challenges/scripts/host_no_auto_poweroff_challenge.sh` per
   Principle XIII — both MUST pass.
6. Update `README.md`, `PLUGIN_STATUS.md`, and `CHANGELOG.md`.
7. Follow the inherited Helix Universal Constitution §11.4.185
   manual-QA-final gate: no release tag is created until a QA-team
   manual pass confirms the release-cycle scope.

### Code Conventions

- **Bash**: `set -euo pipefail`, `[[ ]]` conditionals, quoted
  variables, `snake_case` functions, `UPPER_CASE` constants,
  4-space indent. Shared color-print helpers for all output.
- **Python**: PEP 8, type hints on public methods, `try: import
  novaprinter` pattern (optional dependency), no project-level
  `requirements.txt` — only `tests/requirements.txt`. `ruff` config
  in `pyproject.toml` is authoritative (`py312`, line 120, rule set
  `E,F,W,I,UP,B,SIM,RUF,ASYNC,S,PT,C4,TID`).
- **TypeScript / Angular 21** (`frontend/`): Angular CLI defaults,
  Vitest for unit tests, ng-lint clean.
- **Go** (`qBitTorrent-go/`): `go fmt` clean, `go vet` clean,
  `go test -race` clean.
- **YAML/Compose**: 2-space indent, inline comments, descriptive
  service names, documented environment variables.
- **Commit messages**: Conventional commits (`feat:`, `fix:`, `docs:`,
  `test:`, `chore:`, `refactor:`).

## Governance

This constitution is the supreme governing document for the qBitTorrent
Platform (Boba) project. It supersedes all other project-specific
practices, conventions, and ad-hoc decisions.

- The `constitution/` submodule (the Helix Universal Constitution
  and its `constitution/CLAUDE.md` / `constitution/AGENTS.md`) is
  the CANONICAL ROOT (per constitution §11.4.35 canonical-root
  inheritance). All rules there apply unconditionally to this
  project. This document EXTENDS the inherited rules but MUST NOT
  weaken any universal clause. On any disagreement between this
  constitution and the submodule, the submodule wins.
- Boba is Track 11 in the operator's multi-track development fleet
  (permanently adopted 2026-08-08 per `docs/MULTITRACK.md`). Trunk
  (`main`) work always labels `T1` per the constitution's hard-coded
  TRUNK RULE (never overridden); non-trunk work from this checkout
  labels `T11`.
- QA discovery-channel ledger (§11.4.238): automated HelixQA
  coverage MUST be the discovery layer; manual QA / operator reports
  / agent-found defects are confirmation-only, and any defect found
  out-of-band is itself a coverage-escape release blocker. See
  `docs/QA_DISCOVERY_LEDGER.md`.
- All PRs and code reviews MUST verify compliance with these
  principles AND with the inherited universal constitution.
- Amendments to THIS project constitution require: (1) a written
  proposal documenting the change and rationale, (2) approval from
  the project maintainer, and (3) a migration plan if the change
  affects existing deployments. Amendments to the inherited
  submodule follow that submodule's own §11.4.26 workflow.
- Complexity beyond what is described here MUST be justified in the
  PR description with reference to the specific principle it serves.
- Use `AGENTS.md` for runtime development guidance that supplements
  (but does not contradict) this constitution.
- The `CONTRIBUTING.md` file governs external contribution workflow
  and MUST remain consistent with the principles herein.

**Version**: 1.3.0 | **Ratified**: 2026-04-13 | **Last Amended**: 2026-08-20
