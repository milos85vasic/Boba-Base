# Tasks: Downloads Owned by the Person Who Started the System

**Feature**: 002-user-owned-downloads
**Branch**: `002-user-owned-downloads`
**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

## Task Format

```
[ID] [markers] [Story] Description
```

**Markers**:
- **[P]**: Can run in parallel (different files, no dependencies)
- **[TDD]**: Must follow RED-GREEN-REFACTOR — write the test, WATCH IT FAIL, implement, watch it pass
- **[REVIEW]**: Requires independent code review before proceeding (§11.4.142 — every change, no exception)
- **[SUBAGENT]**: Can be delegated for parallel execution

**Why TDD is marked and not optional**: Principle IX makes it mandatory project-wide, and
§11.4.115 requires the RED to be observed against the genuinely-broken artifact. A test
written after the fix proves only that it agrees with the code.

## Path Conventions

Multi-service containerised platform. Paths are repository-root relative, per plan.md.

---

## Phase 1: Setup (Shared Infrastructure)

**Execution notes**: No special discipline required. These create the declared data and
shared helper every later phase reads.

- [ ] T001 Create `config/owned_paths.yaml` with the E1 schema from data-model.md (`schema_version`, `paths[].{path,kind,optional,preserve_mode,recursive}`), seeded with the three measured entries: the `QBITTORRENT_DATA_DIR` download root (`downloads`), `config/` (`project-config`), and `config/boba.db` (`credential-store`, `preserve_mode: true`)
- [ ] T002 [P] Document in `config/owned_paths.yaml` header WHY scope is declared rather than derived — compose env mixes served/dependency values and the download root is host-specific; deriving it reproduces the §11.4.201(1) false-positive refusal the healthcheck manifest already hit
- [ ] T003 Create `scripts/lib/ownership.sh` with shared helpers: resolve the declared scope, resolve the operator uid, and a `probe_location()` that CREATES a real file, reads back its owner, and removes it (per contracts/startup-precondition.md — never infer from the parent directory or from "no error")

**Checkpoint**: `bash -n` clean on all new shell files; `config/owned_paths.yaml` parses.

---

## Phase 2: Foundational (Blocking Prerequisites)

**⚠️ MUST complete before ANY user story.** T004 is the RED that every later verification
depends on — without it there is no proof the defect exists or that a fix changed anything.

- [ ] T004 [TDD] Write the integration RED in `tests/integration/test_container_writes_owned_files.py`: run `lscr.io/linuxserver/qbittorrent:latest` with `PUID=1000`, write via `s6-setuidgid abc` (NOT a bare `sh -c touch` — that runs as the container root entrypoint, lands at uid 1000 either way, and makes a broken system look fixed; this exact mistake was made and caught in research.md R1), then assert the file's owner uid equals the operator's. **WATCH IT FAIL with uid 100999 before writing any fix.**
- [ ] T005 [P] Mark T004's test as an integration test that SKIPs with an honest reason (§11.4.3) when no container runtime is available — it MUST NOT fail on a host without podman (Constitution Check obligation, plan.md Principle X)
- [ ] T006 [P] [SUBAGENT] Write `tests/unit/test_ownership_precondition.sh` covering the three contract cases: golden-bad (non-operator-owned location → exit 1), golden-good (owned location → exit 0), and the negative control (an `optional: true` location that is absent → exit 0, NOT a refusal)
- [ ] T007 [P] [SUBAGENT] Write `tests/unit/test_ownership_repair.sh` covering: golden-bad tree repaired, golden-good tree unchanged with an EMPTY change record, out-of-scope path untouched, interrupt→resume, and `preserve_mode` bits preserved

**Checkpoint**: T004 FAILS with uid 100999 (pasted evidence required). T006/T007 fail because their targets do not exist yet. This is the correct state — do not proceed until the RED is observed.

---

## Phase 3: User Story 1 — Downloaded files are immediately usable (Priority: P1) 🎯 MVP

**Goal**: New content the system writes is owned by the operator, so it can be renamed,
moved, and deleted with no ownership step.

**Independent test**: Complete one download, then rename/move/delete it as the operator
with no elevation (quickstart Scenario 1).

### Implementation for User Story 1

- [ ] T008 [US1] Set `PUID=0` / `PGID=0` for the `qbittorrent` service in `docker-compose.yml`, with an inline comment recording WHY: `keep-id` hangs this image (research.md R3, measured twice), and container-root under rootless Podman IS host uid 1000 — it holds no host privilege
- [ ] T009 [P] [US1] Set `PUID=0` / `PGID=0` for the `jackett` service in `docker-compose.yml` with the same rationale comment
- [ ] T010 [P] [US1] Add `userns_mode: "keep-id"` to the `download-proxy` service in `docker-compose.yml` (verified on alpine, research.md R3; podman-compose 1.5.0 translates it at `podman_compose.py:1208`)
- [ ] T011 [US1] Verify `userns_mode: "keep-id"` on `qbittorrent-proxy-go` INDIVIDUALLY before adopting it — research.md R5 records this as asserted-not-demonstrated for the built Go images. If it hangs like the linuxserver images, fall back to Route B and record the measurement
- [ ] T012 [US1] Verify and apply the same for `boba-jackett` individually (it writes `config/boba.db`, so FR-012 depends on it)
- [ ] T013 [US1] Apply with `./start.sh --recreate` — NOT `--reload-python`. A restart does not re-read `docker-compose.yml`; this distinction already cost a false "fixed" earlier in this project (§11.4.235)
- [ ] T014 [TDD] [US1] Re-run `tests/integration/test_container_writes_owned_files.py`: it MUST now report the operator's uid. Paste the before (100999) and after (1000) output together — that pairing is the evidence, not the after alone
- [ ] T015 [US1] Run [quickstart.md](./quickstart.md) Scenario 1 end to end against a REAL download and paste the terminal output, including the rename/move/delete round-trip (§11.4 requires an actual end-user invocation, not a test-harness result)
- [ ] T016 [REVIEW] [US1] Independent review of the `docker-compose.yml` changes before proceeding (§11.4.142/§11.4.209): confirm no service that mounts an in-scope path was missed, and that no permission was relaxed

**Checkpoint**: US1 is independently shippable. New downloads are operator-owned; the pre-existing backlog is NOT yet repaired and the operator will still see old wrongly-owned items.

---

## Phase 4: User Story 2 — Existing content is repaired automatically (Priority: P2)

**Goal**: The pre-existing backlog — including the download root and `config/boba.db` —
becomes operator-owned on the first start after the fix, with no operator action.

**Independent test**: Start once against a wrongly-owned tree; confirm every item is
operator-owned afterwards, nothing outside scope changed, and a change record exists
(quickstart Scenario 2).

### Implementation for User Story 2

- [ ] T017 [TDD] [US2] Implement `scripts/ownership_repair.sh` per contracts/repair-cli.md, driving T007 from RED to GREEN: blocking, scope-fenced, `--dry-run` / `--force` / `--scope` flags, exit codes 0/1/2
- [ ] T018 [US2] Implement the E3 change record in `scripts/ownership_repair.sh`: write each entry BEFORE mutating (so a crash still leaves a trail), including `previous_uid`/`previous_gid`/`previous_mode` and an `outcome` of `changed`/`skipped`/`failed`. Paths, uids and modes ONLY — never file contents, never credential values (§11.4.10)
- [ ] T019 [US2] Decide and document the change record's location and format — deferred from clarify by design (research.md R7). Constraint: operator-readable, MUST NOT live only inside a container, and `docs/qa/` is for QA evidence so it is the wrong home for an operational log
- [ ] T020 [TDD] [US2] Implement the E2 repair marker with `scope_fingerprint` in `scripts/ownership_repair.sh`: write it ONLY after a fully successful pass, so an interrupted run resumes. A scope-file change MUST invalidate the fingerprint and re-arm the repair, or newly-declared paths are silently never repaired
- [ ] T021 [TDD] [US2] Implement FR-015 mode preservation: entries marked `preserve_mode` keep their exact bits. Assert `config/boba.db` is still mode 600 after repair — a repair that "succeeds" by widening a credential store trades a usability defect for a security one
- [ ] T022 [US2] Implement FR-004e real progress in `scripts/ownership_repair.sh` (items processed / items discovered), not a spinner or fixed-step estimate — the requirement exists so a long run is distinguishable from a hang
- [ ] T023 [US2] Wire the repair into `start.sh` so it BLOCKS every download-writing service until complete (FR-004d), running under `nice -n 19 ionice -c 3` (Principle XIII — the tree may be large and the host runs mission-critical work)
- [ ] T024 [TDD] [US2] Prove the interrupt→resume path via [quickstart.md](./quickstart.md) Scenario 3 against `scripts/ownership_repair.sh`: start, kill mid-repair, confirm the marker is ABSENT, restart, confirm it resumes and completes. If the second start skips the repair, the marker was written at start instead of on success — the exact defect clarify Q1 closed
- [ ] T025 [US2] Run quickstart Scenario 5 and paste the output: `cp config/boba.db` + `cp .env` succeed in one operation, and `boba.db` is still mode 600. This is the FR-013 proof that the documented backup procedure became performable
- [ ] T026 [REVIEW] [US2] Independent review of `scripts/ownership_repair.sh` before it is allowed to run against real data (it mutates ownership of the operator's library)

**Checkpoint**: US1 + US2 deliver the whole reported defect — new content is owned correctly AND the backlog is repaired.

---

## Phase 5: User Story 3 — The system starts with the operator's session (Priority: P3)

**Goal**: Start/stop the whole system through session-scoped units, without a privileged
system-wide service.

**Independent test**: Start and stop everything through the session-scoped mechanism only,
and confirm it and the documented start path agree about what is running.

**Note**: This is the operator's originally-requested mechanism. It is P3 because
research.md R2 established it does NOT cause the ownership outcome — the units already
exist and are inactive, and `start.sh` references systemd zero times.

### Implementation for User Story 3

- [ ] T027 [P] [SUBAGENT] [US3] Audit the existing units in `scripts/systemd/user/` (`boba-stack.service`, `boba.target`, `boba-webui-bridge.service`, `boba-resource-pressure-check.{service,timer}`) — they are currently `linked`/`inactive`; establish whether they work as-is before changing them
- [ ] T028 [US3] Reconcile the units with `start.sh` so the two paths cannot contradict each other about what is running (FR-009). `start.sh` currently has 0 systemd references, so decide deliberately which owns lifecycle rather than leaving both half-wired
- [ ] T029 [US3] Ensure the units invoke the ownership precondition and repair on the same path `start.sh` does, so starting via systemd cannot bypass FR-010
- [ ] T030 [US3] Run [quickstart.md](./quickstart.md) Scenario 6 (Go profile, `docker-compose.yml`) and paste output — FR-016 requires every service, including optional-profile ones; a fix applied to some returns the defect intermittently

**Checkpoint**: All three user stories complete and independently verifiable.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T031 [TDD] Implement `scripts/ownership_precondition.sh` per contracts/startup-precondition.md, driving T006 from RED to GREEN — exit 0/1/2, where 2 (cannot run) is NOT a pass
- [ ] T032 [TDD] Implement `scripts/pre_build/check_cm_ownership_invariants.sh` (FR-011): assert every compose service that mounts an in-scope path declares a route (E5 completeness map), and FAIL when it checked ZERO services — a quiet zero from a blind instrument is not a clean tree (§11.4.201(6))
- [ ] T033 [TDD] Write the paired §1.1 mutation `scripts/pre_build/check_cm_ownership_invariants_mutation_test.sh` for T032's gate: revert one service's route and confirm the gate FAILs; restore and confirm byte-identical with zero residue. A gate whose mutation does not make it fail is decoration
- [ ] T034 Wire the new gate into `scripts/pre_build_verification.sh` as invariant 45, following the invariant-44 pattern, and renumber the total consistently
- [ ] T035 [P] [SUBAGENT] Write `docs/scripts/ownership_repair.md` and `docs/scripts/ownership_precondition.md` companion guides (§11.4.18 requires one per script — and do not cross-reference a doc that does not exist yet, a mistake made on the healthcheck gate this week)
- [ ] T036 [P] Update `docs/BOBA_DATABASE.md` §3 to state that the backup procedure is now performable, replacing any wording that assumed it already was
- [ ] T037 [P] Run `bash scripts/compute-badges.sh` if any counted artifact changed — it now regenerates exports itself, so it will not leave the tree stale
- [ ] T038 File the discovery-channel entry in `docs/QA_DISCOVERY_LEDGER.md` (§11.4.238): this defect was reported by the operator, not found by automated QA, so it is a coverage escape and requires the escape audit plus the new automated check that would have caught it (T032 is that check)
- [ ] T039 [REVIEW] Final independent review of the whole change set (`git diff main...HEAD`) (§11.4.125) before the release gate
- [ ] T040 Run the full 44+1-invariant gate via `bash scripts/commit-push-all.sh` with NO `BOBA_SYNC_SKIP_CI` — this change touches executable surfaces, so the long gate must actually run

---

## Dependencies & Execution Order

### Phase Dependencies

```
Phase 1 Setup ──> Phase 2 Foundational (RED) ──┬──> Phase 3 US1 (P1) ──> Phase 4 US2 (P2)
                                               │                              │
                                               └──> Phase 5 US3 (P3) ─────────┤
                                                                              v
                                                                     Phase 6 Polish
```

- **Phase 2 blocks everything.** T004's RED must be observed failing before any fix, or
  there is no evidence the fix changed anything (§11.4.115).
- **US2 depends on US1**: repairing the backlog while new writes still land wrongly-owned
  would leave the operator chasing the defect.
- **US3 is independent of US1/US2** — it can proceed in parallel; it does not touch
  ownership.
- **T031 (precondition) sits in Phase 6 but is needed by T029.** If US3 is done early,
  pull T031 forward — it has no dependency on US1/US2.

### Within Each User Story

Tests → implementation → real-invocation evidence → review.

### Parallel Opportunities

| Group | Tasks | Why safe |
|---|---|---|
| Foundational tests | T005, T006, T007 | different files, no shared state |
| Compose service edits | T009, T010 | different service blocks; T008 first to establish the comment pattern |
| Docs polish | T035, T036, T037 | different files, no code dependency |
| Cross-story | Phase 5 (US3) alongside Phase 3/4 | US3 touches lifecycle only, never ownership |

**Not parallelisable**: T008–T013 all edit `docker-compose.yml`. Serialise them or take
the §11.4.84 quiescence risk of two writers in one file.

**[SUBAGENT] candidates**: T027 (unit audit), T035/T036 (docs), T006/T007 (unit tests) —
each has a disjoint file scope.

---

## Implementation Strategy

### MVP scope

**Phase 1 + Phase 2 + Phase 3 (US1).** That alone removes the reported toil for all new
downloads — the operator stops chowning after every download. The backlog remains until
US2, which is a visible but bounded gap, and it is honest to ship in that order because
US1's value does not depend on US2.

### Incremental delivery

1. **US1** → new downloads usable. Reported defect gone going forward.
2. **US2** → backlog repaired, and `boba.db` backup becomes possible (arguably the more
   serious finding, since it silently blocked a documented disaster-recovery procedure).
3. **US3** → the lifecycle mechanism originally requested, now correctly framed as a
   convenience rather than the fix.

### The trap most likely to waste a cycle

`./start.sh --reload-python` does NOT re-read `docker-compose.yml`. Every compose change
in Phase 3 needs `--recreate`, and the served config must be verified against the
committed config before claiming anything works (T013/T014). This exact confusion already
produced a false "fixed" in this project once.
