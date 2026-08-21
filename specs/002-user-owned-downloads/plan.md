# Implementation Plan: Downloads Owned by the Person Who Started the System

**Branch**: `002-user-owned-downloads` | **Date**: 2026-08-21 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/002-user-owned-downloads/spec.md`

## Summary

Every file the system writes must be owned by the operator who started it, so downloads
are usable without a per-download ownership step, and the documented credential-database
backup becomes possible.

The cause is the rootless user-namespace mapping, not the lifecycle manager: with
`PUID=1000` the application lands at host uid **100999**, an identity with no host
account. The fix is **per-service and mixed**, because the two `linuxserver` images hang
under the mapping approach that works everywhere else (measured, see
[research.md](./research.md) R3):

- `qbittorrent`, `jackett` → **`PUID=0`/`PGID=0`** (the s6 app user becomes container-root,
  which the rootless mapping resolves to host uid 1000)
- `download-proxy`, `qbittorrent-proxy-go`, `boba-jackett` → **`userns_mode: keep-id`**

> **SUPERSEDED IN PART — see
> [research.md R9](./research.md#r9-correction--route-a-was-wrong-it-supersedes-r3s-route-a-verdict-and-r5s-route-table).**
> The third bullet above was WRONG and was never applied. All three of `download-proxy`,
> `qbittorrent-proxy-go`, and `boba-jackett` already run as container uid 0, which the
> rootless mapping already resolves to host uid 1000 — a write probe measured them
> already writing operator-owned files with no `userns_mode` change at all. Applying
> `keep-id` to them would have been a regression (the same hang R3 measured on the
> linuxserver images), not a no-op. `userns_mode: keep-id` is applied to **no service in
> this stack**; the `qbittorrent`/`jackett` bullet above (`PUID=0`/`PGID=0`) is the only
> route actually shipped. This project's own CLAUDE.md now states the corrected rule
> directly: "Never add `userns_mode: keep-id` to any service in this stack ... it hangs
> the linuxserver images (measured, twice) and is pointless for the root-running ones."

Plus a blocking, resumable first-start repair for the existing backlog, and a startup
precondition that refuses to run when a configured location cannot produce operator-owned
files.

## Technical Context

**Language/Version**: Bash (orchestration, repair, gates) · Python 3.12 (`download-proxy`) ·
Go (`boba-jackett`, `qbittorrent-proxy-go`) — no new language introduced
**Primary Dependencies**: Podman 5.7.1 rootless · podman-compose 1.5.0 (confirmed to
translate `userns_mode` → `--userns`, research.md R3) · `boba-ctl` · s6 (inside the
linuxserver images)
**Storage**: filesystem ownership metadata; a durable repair marker; an operator-readable
change record; `config/boba.db` (in scope, FR-012)
**Testing**: pytest for Python-side assertions · bash unit tests under `tests/unit/` (which
pre-build invariant 30 actually executes) · a paired §1.1 mutation for every new gate
**Target Platform**: Linux, rootless Podman, single-operator host (uid 1000, subuid base
100000)
**Project Type**: containerised multi-service platform; this change is configuration +
orchestration, not application code
**Performance Goals**: no self-imposed limit on the first-start repair (FR-004f); it runs
to completion. Steady-state overhead after the marker is written MUST be zero — no tree
walk on subsequent starts (FR-004a)
**Constraints**: rootless only (§11.4.161) · no privileged or system-wide service ·
must not relax any permission (FR-015) · `docker-compose.yml` changes require
`./start.sh --recreate`, never `--reload-python` (§11.4.235)
**Scale/Scope**: 5 compose services (one optional-profile) · 6,459 items in the download
tree today · 51 wrongly-owned items under `config/` · repair must not assume today's size

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Assessment | Verdict |
|---|---|---|
| **I. Container-First** | Change is confined to `docker-compose.yml` + lifecycle scripts, which the principle names as the contract. It requires both to move together, and the health check to cover every served port — already enforced by invariant 44 and untouched here. | **PASS** |
| **III. Credential & Secret Security** | `config/boba.db` enters scope. FR-015 forbids relaxing its mode 600. The change makes the documented backup *possible*, which the principle requires and which is currently broken. No secret is printed, logged, or moved. | **PASS** |
| **IV. Container Runtime Portability** | Both routes are rootless. `userns_mode: keep-id` is Podman-specific; Docker maps it differently. The project mandates rootless Podman (§11.4.161) and auto-detects runtime, so this is consistent — but it MUST be recorded as a Podman-coupled setting, see Complexity Tracking. *(As planned at Phase-0/Phase-1 gate time. As shipped, `keep-id` is applied to no service — see the Summary supersession above / research.md R9 — so the Podman-coupling note in Complexity Tracking below is likewise historical, not a live constraint.)* | **PASS (with note)** |
| **VI. Validation-Driven** | `./ci.sh` remains the gate; no CI/CD is added (Hard Stop #1 intact). | **PASS** |
| **IX. TDD** | RED already exists: research.md R1 reproduces host uid 100999 against the real image via `s6-setuidgid abc`. It fails pre-fix and passes post-fix. | **PASS** |
| **X. Hermetic Tests** | The RED repro needs a real container, so it is an integration test, not a unit test. It MUST be marked so and MUST skip (not fail) where no container runtime exists (§11.4.3). | **PASS (with obligation)** |
| **XII. Anti-Bluff** | Every claim in research.md is a pasted command result. Two flawed measurements were caught and recorded rather than silently corrected (R1 root-entrypoint confound; R3 blind grep). Ownership assertions must read the real uid, never "no error". | **PASS** |
| **XIII. Host-Session Safety** | No power-state transitions. The repair walks and chowns a large tree, so it MUST respect the 30-40% resource ceiling (`nice`/`ionice`). No `killpg` surface is introduced (§11.4.263). | **PASS (with obligation)** |

**Inherited universal constitution:**

| Anchor | Assessment |
|---|---|
| §11.4.201 guard-asserts-real-condition | FR-010b already requires the startup check to actually create a file and read back its owner, not probe a proxy. |
| §11.4.247 layer-move completeness | The move touches compose env, compose userns, lifecycle scripts, docs, and gates. R5's table is the completeness map; FR-016 forbids partial application. |
| §11.4.252 fail-closed | FR-010 refuses to start on an unusable location — fail-closed by design. |
| §11.4.253 idempotency | FR-004a/FR-004c require the repair to be re-runnable and to resume; the marker is written only on success. |
| §11.4.235 | Compose changes need `--recreate`. This must be an explicit task, not tribal knowledge. |

**Result: PASS. No unjustified violations. Two obligations carried into tasks (hermetic-skip, resource ceiling) and one note (Podman coupling).**

## Project Structure

### Documentation (this feature)

```text
specs/002-user-owned-downloads/
├── plan.md              # This file
├── research.md          # Phase 0 — measured evidence for every decision
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1 — runnable validation
├── contracts/           # Phase 1
│   ├── repair-cli.md            # the repair's invocation contract
│   └── startup-precondition.md  # the fail-closed ownership check
├── checklists/
│   └── requirements.md  # spec quality (16/16)
└── tasks.md             # Phase 2 — NOT created by /speckit-plan
```

### Source Code (repository root)

```text
docker-compose.yml                     # PUID/PGID per service; userns_mode planned per-service, shipped on none (research.md R9)
start.sh                               # invokes the precondition + repair before services
scripts/
├── boba-ctl.sh                        # compose wrapper (no userns logic; passes through)
├── lib/
│   └── ownership.sh                   # NEW — shared scope resolution + probe helpers
├── ownership_precondition.sh          # NEW — FR-010 fail-closed startup check
├── ownership_repair.sh                # NEW — FR-004 blocking, resumable repair
└── pre_build/
    └── check_cm_ownership_invariants.sh  # NEW — FR-011 regression gate
config/
└── owned_paths.yaml                   # NEW — declared in-scope locations (consumer DATA)
tests/
├── unit/
│   ├── test_ownership_precondition.sh # bash unit tests (invariant 30 runs these)
│   └── test_ownership_repair.sh
└── integration/
    └── test_container_writes_owned_files.py  # the RED from research.md R1
docs/
├── BOBA_DATABASE.md                   # backup procedure becomes performable (FR-013)
└── scripts/                           # §11.4.18 companion docs for each new script
```

**Structure decision**: no new service and no application code. The change is
configuration plus three small orchestration scripts, kept separate so each is
independently testable: a **probe** (shared), a **precondition** (fail-closed gate), and
a **repair** (blocking, resumable). The declared scope lives in `config/owned_paths.yaml`
as consumer DATA for the same reason `config/served_ports.yaml` does — it cannot be
safely derived, since compose env mixes served/dependency values and paths differ per
host.

## Complexity Tracking

Both rows below record the Phase-0/Phase-1 planning-time analysis. **As shipped**
(research.md R9), `keep-id` is applied to no service — the second row's Podman-coupling
concern therefore never materialised. Left unedited, per the same left-in-place-on-purpose
convention research.md R3/R5 use, because what was believed and why is the record.

| Item | Why it is needed | Simpler alternative rejected because |
|---|---|---|
| **Two different routes for one problem** *(as planned)* | The linuxserver images hang under `keep-id` (measured twice, R3); the Go/alpine services have no s6 root requirement. | A single uniform route is impossible: `keep-id` everywhere breaks qbittorrent — the service that writes downloads — and `PUID=0` everywhere would make non-s6 images run as root for no benefit. |
| **`userns_mode: keep-id` is Podman-specific** *(as planned; not shipped — see above)* | Docker interprets `userns_mode` differently (it has no `keep-id`), so this couples three services to Podman. | Acceptable: §11.4.161 already mandates rootless Podman project-wide and `run-all-tests.sh` is already podman-only. Recorded so a future Docker port knows it must revisit this, rather than discovering it as a silent behaviour change. |
| **A separate declared scope file** | Scope cannot be derived: compose env mixes served and dependency values, and the download root differs per host. | Deriving it would produce a false-positive refusal — the §11.4.201(1) failure the healthcheck gate already hit once when its manifest was seeded from prose instead of source. |
| **Repair blocks startup** | FR-004d — a background repair leaves a window where downloads land in a half-repaired tree. | Operator chose blocking in clarify Q2 after being shown the trade-off. |

## Phase 0 — Outline & Research

**Status: COMPLETE.** See [research.md](./research.md). All Technical Context unknowns
resolved by measurement on this host; zero `NEEDS CLARIFICATION` remain.

Two flawed measurements were caught during the pass and are recorded rather than
quietly corrected, because each would have produced a confidently wrong plan:

1. A repro run via `sh -c` executed as the container's **root entrypoint** instead of the
   `PUID` user, so test and control both landed at uid 1000 and the experiment
   distinguished nothing. Re-run through `s6-setuidgid abc`.
2. A support check grepped a thin entrypoint script and found 0 `userns` references —
   and 0 `network_mode` references, which is impossible for a working tool. The control
   needle exposed a blind instrument; against the real module the answer is 3 and 8.

## Phase 1 — Design & Contracts

**Status: COMPLETE.** Artifacts: [data-model.md](./data-model.md),
[contracts/repair-cli.md](./contracts/repair-cli.md),
[contracts/startup-precondition.md](./contracts/startup-precondition.md),
[quickstart.md](./quickstart.md).

## Constitution Re-Check (post-design)

| Concern raised by the design | Resolution |
|---|---|
| The repair chowns a large tree — host-safety risk? | `nice -n 19` + `ionice -c 3`, bounded to the declared scope. Obligation carried to tasks. **PASS** |
| `boba.db` mode must not widen | FR-015 is a requirement and gets its own assertion in the repair contract. **PASS** |
| Does a new blocking startup stage risk a hang? | FR-004e requires real progress reflecting completed work, and FR-004a makes stopping safe. **PASS** |
| Does the new gate have teeth? | FR-011's gate ships a paired §1.1 mutation; the RED from R1 is the fixture. **PASS** |
| Does anything become non-rootless? | No. Container-root under rootless Podman is host uid 1000, holding no host privilege. **PASS** |

**Result: PASS — no new violations introduced by the design.**
