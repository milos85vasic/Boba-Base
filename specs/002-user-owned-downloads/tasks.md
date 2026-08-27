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

- [x] T001 Create `config/owned_paths.yaml` with the E1 schema from data-model.md (`schema_version`, `paths[].{path,kind,optional,preserve_mode,recursive}`), seeded with the three measured entries: the `QBITTORRENT_DATA_DIR` download root (`downloads`), `config/` (`project-config`), and `config/boba.db` (`credential-store`, `preserve_mode: true`)
- [x] T002 [P] Document in `config/owned_paths.yaml` header WHY scope is declared rather than derived — compose env mixes served/dependency values and the download root is host-specific; deriving it reproduces the §11.4.201(1) false-positive refusal the healthcheck manifest already hit
- [x] T003 Create `scripts/lib/ownership.sh` with shared helpers: resolve the declared scope, resolve the operator uid, and a `probe_location()` that CREATES a real file, reads back its owner, and removes it (per contracts/startup-precondition.md — never infer from the parent directory or from "no error") [FR-010b, E4]

**Checkpoint**: `bash -n` clean on all new shell files; `config/owned_paths.yaml` parses.

---

## Phase 2: Foundational (Blocking Prerequisites)

**⚠️ MUST complete before ANY user story.** T004 is the RED that every later verification
depends on — without it there is no proof the defect exists or that a fix changed anything.

- [x] T004 [TDD] Write the integration RED in `tests/ownership/test_container_writes_owned_files.py` (shipped path — planned as `tests/integration/`, landed under `tests/ownership/` alongside the feature's other integration coverage; a stale `tests/integration/__pycache__/` entry is the only trace of the original path): run `lscr.io/linuxserver/qbittorrent:latest` with `PUID=1000`, write via `s6-setuidgid abc` (NOT a bare `sh -c touch` — that runs as the container root entrypoint, lands at uid 1000 either way, and makes a broken system look fixed; this exact mistake was made and caught in research.md R1), then assert the file's owner uid equals the operator's. **WATCH IT FAIL with uid 100999 before writing any fix.** [FR-001]
- [x] T005 [P] Mark T004's test as an integration test that SKIPs with an honest reason (§11.4.3) when no container runtime is available — it MUST NOT fail on a host without podman (Constitution Check obligation, plan.md Principle X)
- [x] T006 [P] [SUBAGENT] Write `tests/unit/test_ownership_precondition.sh` covering the three contract cases: golden-bad (non-operator-owned location → exit 1), golden-good (owned location → exit 0), and the negative control (an `optional: true` location that is absent → exit 0, NOT a refusal)
- [x] T007 [P] [SUBAGENT] Write `tests/unit/test_ownership_repair.sh` covering: golden-bad tree repaired, golden-good tree unchanged with an EMPTY change record, out-of-scope path untouched, interrupt→resume, and `preserve_mode` bits preserved

**Checkpoint**: T004 FAILS with uid 100999 (pasted evidence required). T006/T007 fail because their targets do not exist yet. This is the correct state — do not proceed until the RED is observed.

---

## Phase 3: User Story 1 — Downloaded files are immediately usable (Priority: P1) 🎯 MVP

**Goal**: New content the system writes is owned by the operator, so it can be renamed,
moved, and deleted with no ownership step.

**Independent test**: Complete one download, then rename/move/delete it as the operator
with no elevation (quickstart Scenario 1).

### Implementation for User Story 1

- [x] T008 [US1] Set `PUID=0` / `PGID=0` for the `qbittorrent` service in `docker-compose.yml`, with an inline comment recording WHY: `keep-id` hangs this image (research.md R3, measured twice), and container-root under rootless Podman IS host uid 1000 — it holds no host privilege [FR-001, FR-002, FR-016]
- [x] T009 [P] [US1] Set `PUID=0` / `PGID=0` for the `jackett` service in `docker-compose.yml` with the same rationale comment [FR-016]
- [x] ~~T010~~ **CLOSED — no change required (measured 2026-08-21)**: `download-proxy` was measured to write as host uid **1000** already (probe: write a real file into a host-mounted path, read the owner back from the host; control = the linuxserver app user reading 100999, proving the probe can see the defect). It runs as root, and container-root IS the host operator under rootless podman. `keep-id` would change nothing useful and would leave it with no usable root — the hang measured in research.md R3. Applying `keep-id` here would have been a regression, not a fix. Evidence: `specs/002-user-owned-downloads/evidence/T014-T017-us1-green.md`.
- [x] ~~T011~~ **CLOSED — no change required (measured 2026-08-21)**: `qBitTorrent-go/Dockerfile` declares no `USER`, so `qbittorrent-proxy-go` runs as root and inherits the same correct mapping as the other root-running services. The individual verification this task asked for is exactly what closed it. Applying `keep-id` here would have been a regression, not a fix. Evidence: `specs/002-user-owned-downloads/evidence/T014-T017-us1-green.md`.
- [x] ~~T012~~ **CLOSED — no change required (measured 2026-08-21)**: `boba-jackett` was measured to write as host uid **1000** already, by the same probe and control. Applying `keep-id` here would have been a regression, not a fix. Evidence: `specs/002-user-owned-downloads/evidence/T014-T017-us1-green.md`.
- [x] T013 [US1] Capture a start-to-healthy TIMING BASELINE before any compose change (`time ./start.sh --recreate` plus per-service healthy time from `podman ps`), recorded in `specs/002-user-owned-downloads/` — SC-005 compares against this, and US2 deliberately ADDS a blocking startup stage, so without a pre-change number SC-005 is unfalsifiable [SC-005]
- [x] T014 [US1] Apply with `./start.sh --recreate` — NOT `--reload-python`. A restart does not re-read `docker-compose.yml`; this distinction already cost a false "fixed" earlier in this project (§11.4.235) [FR-001, FR-002]
- [x] T015 [TDD] [US1] Re-run `tests/ownership/test_container_writes_owned_files.py` (shipped path — see the T004 note): it MUST now report the operator's uid. Paste the before (100999) and after (1000) output together — that pairing is the evidence, not the after alone [FR-001, SC-001]
- [x] T016 [US1] Verify ownership PERSISTS: after T015 passes, run `./stop.sh && ./start.sh`, re-check `find "$DD" ! -uid $(id -u) | wc -l` is 0, then `./start.sh --recreate` and re-check again. "Ownership was correct once" is not the claim FR-007 makes [FR-007, SC-004]
- [x] T017 [US1] Run [quickstart.md](./quickstart.md) Scenario 1 end to end against a REAL download and paste the terminal output, including the rename/move/delete round-trip (§11.4 requires an actual end-user invocation, not a test-harness result) [FR-003, SC-001, SC-002]
- [x] T018 [REVIEW] [US1] Independent review of the `docker-compose.yml` changes before proceeding (§11.4.142/§11.4.209): confirm no service that mounts an in-scope path was missed, and that no permission was relaxed — **GO, zero findings, round 4** (`evidence/T018-review-GO.md`). Measured on the current `docker-compose.yml`: `userns_mode` active keys **0**, `user:` keys **0**, `PUID=0`/`PGID=0` preserved on the two linuxserver services (deliberate per CLAUDE.md), credential store **600**, world-writable under `config/` **0**, group-writable **0**. Four rounds, iterated to zero-finding/zero-warning per §11.4.134. Round 4 also corrected the reviewer's OWN round-3 audit: its bracket-only instrument saw 41 of 50 gate labels and reported one denominator while two were live — §11.4.201(6) inside the reviewer's instrument, re-derived on a three-form control-needled scan. Does NOT discharge T042 or the §11.4.185 manual-QA gate.

**Checkpoint**: US1 is independently shippable. New downloads are operator-owned; the pre-existing backlog is NOT yet repaired and the operator will still see old wrongly-owned items.

---

## Phase 4: User Story 2 — Existing content is repaired automatically (Priority: P2)

**Goal**: The pre-existing backlog — including the download root and `config/boba.db` —
becomes operator-owned on the first start after the fix, with no operator action.

**Independent test**: Start once against a wrongly-owned tree; confirm every item is
operator-owned afterwards, nothing outside scope changed, and a change record exists
(quickstart Scenario 2).

### Implementation for User Story 2

- [x] T019 [TDD] [US2] Implement `scripts/ownership_repair.sh` per contracts/repair-cli.md, driving T007 from RED to GREEN: blocking, scope-fenced, `--dry-run` / `--force` / `--scope` flags, exit codes 0/1/2 [FR-004, FR-004c, FR-005, FR-006]
- [x] T020 [US2] Implement the E3 change record in `scripts/ownership_repair.sh`: write each entry BEFORE mutating (so a crash still leaves a trail), including `previous_uid`/`previous_gid`/`previous_mode` and an `outcome` of `changed`/`skipped`/`failed`. Paths, uids and modes ONLY — never file contents, never credential values (§11.4.10) [FR-004b]
- [x] T021 [US2] Decide and document the change record's location and format — deferred from clarify by design (research.md R7). Constraint: operator-readable, MUST NOT live only inside a container, and `docs/qa/` is for QA evidence so it is the wrong home for an operational log
- [x] T022 [TDD] [US2] Implement the E2 repair marker with `scope_fingerprint` in `scripts/ownership_repair.sh`: write it ONLY after a fully successful pass, so an interrupted run resumes. A scope-file change MUST invalidate the fingerprint and re-arm the repair, or newly-declared paths are silently never repaired [FR-004a]
- [x] T023 [TDD] [US2] Implement FR-015 mode preservation: entries marked `preserve_mode` keep their exact bits. Assert `config/boba.db` is still mode 600 after repair — a repair that "succeeds" by widening a credential store trades a usability defect for a security one [FR-015]
- [x] T024 [US2] Implement FR-004e real progress in `scripts/ownership_repair.sh` (items processed / items discovered), not a spinner or fixed-step estimate — the requirement exists so a long run is distinguishable from a hang [FR-004e]
- [x] T025 [US2] Wire the repair into `start.sh` so it BLOCKS every download-writing service until complete (FR-004d), running under `nice -n 19 ionice -c 3` (Principle XIII — the tree may be large and the host runs mission-critical work) [FR-004d, FR-004f, SC-004a]
- [x] T026 [TDD] [US2] Prove the interrupt→resume path via [quickstart.md](./quickstart.md) Scenario 3 against `scripts/ownership_repair.sh`: start, kill mid-repair, confirm the marker is ABSENT, restart, confirm it resumes and completes. If the second start skips the repair, the marker was written at start instead of on success — the exact defect clarify Q1 closed [FR-004a]
- [x] T027 [US2] Run quickstart Scenario 5 and paste the output: `cp config/boba.db` + `cp .env` succeed in one operation, and `boba.db` is still mode 600. This is the FR-013 proof that the documented backup procedure became performable [FR-013, SC-007]
- [x] T028 [REVIEW] [US2] **ORDERING VIOLATION — recorded honestly, not laundered.** This task's own wording ("before it is allowed to run against real data") was NOT honoured: `scripts/ownership_repair.sh` already ran against real data via the live `./start.sh` at **2026-08-21T17:01:55** (`journalctl --user`, unit `boba-stack.service`: `[ownership-repair] operator 1000:1000; scope .../config/owned_paths.yaml (3 declared locations)` through `... complete: 0 item(s) repaired`), **before** this checkbox was ever checked. Two things partially cover the gap without closing it: (1) T018's independent review (Fable substrate, `evidence/T018-review-NOGO.md`) DID read `ownership_repair.sh` — see its MINOR-3 ("the repair's scope fence has no test") and the "repair's destructive-tool safety read clean" paragraph — so the script was not run against real data completely unreviewed; (2) the review round that produced this note re-examined the repair alongside the rest of the feature. Neither is the DEDICATED T028 review this task names, run in the order this task specifies, so the checkbox stays unchecked rather than being marked done on the strength of partial coverage. Independent review of `scripts/ownership_repair.sh` before it is allowed to run against real data (it mutates ownership of the operator's library). **2026-08-25 — the dedicated review RAN: NO-GO** (`evidence/T028-review-NOGO.md`), 0 BLOCKING / 2 IMPORTANT / 3 MINOR / 2 NIT; remediation dispatched, checkbox stays unchecked per §11.4.134 (zero findings AND zero warnings required). Headline IMPORTANT-2: there is **no containment fence on the declared path itself** — `absolutise()` at :379-385 passes absolute paths through unnormalised and its `|| p="/"` branch maps `/` to `/`, while `config/owned_paths.yaml:87` ships `- path: "${QBITTORRENT_DATA_DIR:-/mnt/DATA}"`, so an untracked-by-design `.env` value selects the recursively-chowned tree and `QBITTORRENT_DATA_DIR=/` reaches the walk intact (conductor re-verified the code path independently). IMPORTANT-1: an empty-parsing scope exits **0** with a marker, while the sibling `ownership_precondition.sh` correctly exits 2 on the same fixture — two readers of one scope file disagree. The 2026-08-21 real-data run is **provably harmless**: the reviewer read `39af66c`, the revision that actually ran (today's file postdates it), and its `discovered -eq 0 → continue` short-circuit means `chown(2)` was never invoked; the counter was separately proven live, not constant. **The ordering violation itself remains OPEN — a later review cannot un-violate it.** **2026-08-26 — round 2 (`evidence/T028-review-ROUND2.md`): NO-GO, 0 BLOCKING / 0 IMPORTANT / 1 MINOR / 2 NIT**; all seven round-1 findings verified closed by execution, 10 of 12 reviewer-authored mutations killed. **SECOND real-data run recorded against THIS SAME violation, not minted as a new one (§11.4.214 — a recurrence links, it never re-mints).** `scripts/ownership_repair.sh` ran against real data a second time at **2026-08-25 20:52:21** local (`journalctl --user`, unit `boba-stack.service`, pid 1169590) — after round 1's NO-GO and 17 minutes before the remediation commit `8a08d49` landed, so which exact working-tree bytes ran is not reconstructable. Its harmlessness is therefore proven REVISION-INDEPENDENTLY, and re-verified from the journal and from git objects by the round-3 author: the run reports `(6 declared locations)` and `0/0 items need repair` at ALL SIX, including the real library `/run/media/milosvasic/DATA4TB/Downloads`, then `complete: 0 item(s) repaired; no change record (nothing was changed)`; and BOTH candidate revisions carry the `discovered -eq 0 → continue` short-circuit (`7b45113:760`, HEAD `:980`, each read from the immutable object), whose body logs `0/0` and `continue`s before the chown batch — so `chown(2)` was never invoked either way. This supersedes round 1's "the currently-shipped scope has never been exercised by a real run": it now has been, harmlessly, at all six declared locations. Round 1's unresolved contradiction (51 items recorded at uid 100999 in the provenance vs 0 discovered) remains **UNKNOWN** — nothing in rounds 2 or 3 settled it. **The ordering violation stays OPEN and covers BOTH runs; neither run is closed by either later review.** **2026-08-26 — LEDGER ADDENDUM (round 4, same record, §11.4.214 — a recurrence links, it never re-mints).** Both evidence documents and this record quoted the 20:52:21 journal line TRUNCATED before its final clause. The full line reads `[ownership-repair] complete: 0 item(s) repaired; no change record (nothing was changed); marker logs/ownership/repair-marker.json` — so that run also **wrote a completion marker**. Re-read from the journal and from the marker itself this round: `logs/ownership/repair-marker.json` (mode 0600, written 20:52) records `completed_at 2026-08-25T18:52:21Z`, `items_changed 0`, `record_file null`, and `scope_fingerprint c41619d212648a692bca539c1b3836d136b5c5c54058dacc0f81680c70120c3b` — which **still equals the fingerprint the current shipped scope computes today**. The real six-location scope is therefore latched "done" as of that run and REMAINS latched, so `./start.sh` skips the repair until the scope or its interpolated environment changes. No false statement was made previously — a marker is the designed output of an honest 0/0 walk and the fingerprint re-arms on any scope change — but the clause belongs in the ledger, and the fact that the latch is still live today is stronger than "as of that run". Round 1's contradiction (51 items at uid 100999 in the provenance vs 0 discovered) remains **UNKNOWN**; round 4 settled nothing about it and claims nothing. **2026-08-26 — LEDGER ADDENDUM (round 5, same record, §11.4.214).** Round 4's re-review returned **NO-GO, 0 BLOCKING / 0 IMPORTANT / 0 MINOR / 2 NIT** (`evidence/T028-review-ROUND4.md`); the round-5 remediation (`evidence/T028-round5-remediation.md`) closed both by execution and touched nothing else — `ownership_repair.sh` (`ae025b74602414ca`), `config/owned_paths.yaml` (`26375798edfee773`), `lib/ownership.sh` (`43aad4b6850e958c`) and `ownership_precondition.sh` (`6308d9e6eaa74f56`) are byte-identical to the round-4 reviewed state. **R4-N2** (Case 24's `head -1` judged only the FIRST `Tracked as` citation) carries a RED→GREEN flip in BOTH halves: the reviewer's M-F mutation SURVIVED at 146/0/0 on the round-4 suite and is KILLED at 145/1/0 by the round-5 loop; and a novel decoy item mentioning `symlink` incidentally but never `intermediate` PASSED the round-4 probe and FAILs the tightened one — round 4's probe was anchored by luck, not by construction. CENSUS CORRECTED 2026-08-26 by the round-5 reviewer: the tracker holds 201 items of which EXACTLY ONE (BOB-201) mentions symlinks — the earlier phrasing '1 of 200 items mentioning symlinks' was wrong and is withdrawn. The luck was not dilution but the single-token grep: a rebuilt decoy (BOB-88888, symlink x1, intermediate x0, token counts byte-verified) PASSES round-4 semantics and is killed at 145/1/0 by round 5. **R4-N1** was fixed in the GUIDE, not the code, and the reviewer's reasoning was confirmed by fresh measurement: a real directory named `$RECYCLE.BIN` is walked normally today (`0/0 items need repair`, exit 0), so refusing a bare `$` would be a §11.4.201(1) false refusal against a live configuration. **A NEW out-of-band observation was recorded and deliberately NOT filed or fixed** (§5 of the remediation doc): a scope entry omitting `kind` shifts every tab-separated field left in `ownership_repair.sh:493`, so `optional: true` is read from `preserve_mode`'s slot and the entry is treated as non-optional — NOT reachable from the shipped scope (all six entries declare `kind`), status **UNKNOWN**, resolution operator-owned (§11.4.66). The ordering violation and the 51-vs-0 contradiction **both remain OPEN/UNKNOWN**; round 5 settled neither and claims nothing about either. **2026-08-26 — ROUND 5 RE-REVIEW: GO — 0 BLOCKING / 0 IMPORTANT / 0 MINOR / 0 NIT / 0 warnings** (`evidence/T028-review-ROUND5.md`, Revision 1). Verbatim verdict: the dedicated independent review of `scripts/ownership_repair.sh` that this task names is complete with zero findings and zero warnings, and the checkbox may be checked on this verdict. **Checkbox CHECKED 2026-08-26 on that GO** — §11.4.134 satisfied (zero findings AND zero warnings). The reviewer authored three novel mutations: the POINTEE-decay mutant (BOB-201's body stripped of every `intermediate` variant in a scratch DB) was KILLED 145/1/0, proving the check watches tracker CONTENT not merely the pointer; a lowercase-citation mutant survived and was adjudicated the shape boundary of any lexical convention (ungraded, strictly narrower than the closed NIT); a legitimate far-from-fence citation fails loudly and was adjudicated correct conservatism (ungraded). Its own partial-mutation incident (an all-caps INTERMEDIATE surviving a replace, caught by byte-verify at 3->1 not 0, run voided and redone) is the fifth such incident this session, each caught by the mandated discipline. **WHAT THIS GO DOES NOT CLOSE:** the ORDERING VIOLATION on this same record stays **OPEN** — a later review cannot un-violate an ordering, and every round has said so; the 51-items-at-uid-100999 vs 0-discovered contradiction stays **UNKNOWN**; `podman unshare` has still never been exercised against a real subuid-owned item; `CONTAINER_RUNTIME` is still an unvalidated command name; `BATCH_SIZE=256` is still cold at scale; a `storage.conf`-relocated graphroot is still outside the deny's reach. The out-of-band field-collapse observation recorded above as 'NOT filed' HAS SINCE BEEN FILED as **BOB-202** (conductor, 2026-08-26, mechanism independently re-measured before filing: TAB is an IFS-whitespace character in bash so consecutive tabs collapse rather than delimiting an empty field); the reviewer confirmed that mechanism and strengthened it with a counter-probe showing a non-whitespace `IFS=:` PRESERVES the empty field, making the IFS-whitespace attribution load-bearing. The intermediate-symlink reach is filed as **BOB-201**. Both carry operator-owned §11.4.66 decisions. **2026-08-26 — THE 51-AT-UID-100999 CONTRADICTION IS SUBSTANTIALLY SETTLED** (directed forensic investigation, `docs/qa/T028-uid100999/uid100999-provenance-investigation.md`; same record, no re-mint §11.4.214). **H1 HOLDS — the 51 were HISTORICAL.** The decisive measurement distinguishes a rewrite (mtime resets) from a chown (mtime preserved): 140 `config/` entries carry mtimes PREDATING the 16:06 provenance measurement, ALL 140 are uid 1000 today, ZERO at any other uid — and they include files only the qBittorrent container writes, with mtimes untouched from long before `PUID=0` (`categories.json` 2026-04-27, `rss/feeds.json`, `GeoDB/dbip-country-lite.mmdb` 2026-08-08). Content untouched + ownership now the operator's ⇒ a **chown**, not regeneration under `PUID=0`. It was NOT the repair (0 changed on both runs, `items_changed: 0`, no change record) and NOT project tooling (`grep -n chown start.sh setup.sh install.sh install-plugin.sh stop.sh` → no matches). So the provenance and the `0/0` runs were BOTH true, at different times. **H2 (scope mismatch) REFUTED** — `systemctl --user cat` confirms `WorkingDirectory=/run/media/milosvasic/DATA4TB/Projects/boba`, so run 1's relative `config` label resolved to exactly the measured path. **H3 (blind walk — the §11.4.201(6) FALSE-NULL, the serious one) REFUTED** by four independent checks: the predicate at `:963` is sound; `:967-978` CAPTURE find's stderr rather than converting failure to a silent zero; run 1's downloads leg was ABSOLUTE and still returned 0/0; today's walks returned empty stderr. `findmnt` confirms **btrfs** on both mounts, which stores real owner uids — an exFAT/NTFS mount would have reported the mounting user unconditionally and made every reading meaningless. **Present-day measurement, control-needled:** `config/` 264 walked / 264 at uid 1000 / **0 at 100999**; the real library 7681 walked / 7681 / **0**. The instrument was PROVEN not blind to the target uid — the same `find -printf '%U\n'` resolves 16 distinct uids in the podman graphroot including **35 items at uid 100999**. **H4 confirmed only NARROWLY:** `research.md` §R6 records **NO COMMAND** (R1 and R2 of the same document paste theirs), so the 51 is UNDERIVABLE from the record — a real defect in the provenance's evidentiary quality, but explicitly NOT proof the number was false, and weaker than the two figures retracted this session (those were shown unreproducible AT their stated scope). **STILL UNKNOWN, honestly:** WHO performed the chown and exactly WHEN inside the 55-minute window 16:06 → 17:01:55 (which contains the `PUID=0` commit at 16:40) — §R6 itself notes the operator had been "reassigning ownership by hand", the only candidate known, but no captured evidence names an agent; and a bulk ctime event at 2026-08-25 20:52:18 that stamped 246 of 264 `config/` entries (many sharing the nanosecond) while mtimes still span 2026-03-09→08-26, DESTROYING ctime forensics for the original window — its obvious candidate is REFUTED by measurement, since `./config:/config` appears at compose lines 48/165/247/307 with **no `:Z` or `:z`** on any. No mechanism established, none asserted (§11.4.6). **WHAT WOULD SETTLE THE REMAINDER:** a timestamped shell history; a btrfs snapshot predating 2026-08-21T17:01:55 (its owner uids would confirm or refute the 51 directly at its stated scope); or operator recollection (§11.4.66) — the only path likely to name the agent.

**Coverage note**: FR-004g (repair-vs-active-download concurrency) has NO task and needs
none — it is out of scope BY CONSTRUCTION because T025 blocks every download-writing
service during the repair. Recorded so a coverage audit sees a decision, not an omission.

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

- [x] T029 [P] [SUBAGENT] [US3] Audit the existing units in `scripts/systemd/user/` (`boba-stack.service`, `boba.target`, `boba-webui-bridge.service`, `boba-resource-pressure-check.{service,timer}`) — they are currently `linked`/`inactive`; establish whether they work as-is before changing them
- [x] T030 [US3] Reconcile the units with `start.sh` so the two paths cannot contradict each other about what is running (FR-009). `start.sh` currently has 0 systemd references, so decide deliberately which owns lifecycle rather than leaving both half-wired [FR-008, FR-009]
- [x] T031 [US3] Ensure the units invoke the ownership precondition and repair on the same path `start.sh` does, so starting via systemd cannot bypass FR-010
- [x] T032 **[PARTIAL — scenario blocked by an unrelated build defect, BOB-153]**: the go profile cannot build (go.mod requires go 1.26.2, the Dockerfile builder is golang:1.23-alpine), and it would collide on 7187 with the live Python proxy. FR-016 coverage for that service therefore rests on surface-equivalent measurement (final stage alpine:3.19, no USER directive, so it runs as container root and inherits the correct mapping) rather than a live probe — recorded as the weaker evidence it is. Original: [US3] Run [quickstart.md](./quickstart.md) Scenario 6 (Go profile, `docker-compose.yml`) and paste output — FR-016 requires every service, including optional-profile ones; a fix applied to some returns the defect intermittently [FR-016, SC-003]

**Checkpoint**: All three user stories complete and independently verifiable.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [x] T033 [TDD] Implement `scripts/ownership_precondition.sh` per contracts/startup-precondition.md, driving T006 from RED to GREEN — exit 0/1/2, where 2 (cannot run) is NOT a pass [FR-010, FR-010a]
- [x] T034 [TDD] Implement `scripts/pre_build/check_cm_ownership_invariants.sh` (FR-011): assert every compose service that mounts an in-scope path declares a route (E5 completeness map), and FAIL when it checked ZERO services — a quiet zero from a blind instrument is not a clean tree (§11.4.201(6)) [FR-011, FR-014, SC-006]
- [x] T035 [TDD] Write the paired §1.1 mutation `tests/pre_build/test_check_cm_ownership_invariants.sh` (shipped path — planned as `scripts/pre_build/check_cm_ownership_invariants_mutation_test.sh`; landed under `tests/pre_build/` with the project's `test_<name>.sh` naming convention for paired mutation tests, alongside the gate's other invariant coverage) for T034's gate: revert one service's route and confirm the gate FAILs; restore and confirm byte-identical with zero residue. A gate whose mutation does not make it fail is decoration
- [x] T036 **[landed as invariant 33, printed as `[45/48]`]** — measured 2026-08-21: the runner's own in-source comment now reads "THE INVARIANT NUMBER IS THE PART THAT ROTS" and the block that once explained why slot 45 was free was already false by the commit that added it, because that same commit renumbered the printed label to `[45/48]` (`scripts/pre_build_verification.sh` around the `CM-OWNERSHIP-INVARIANTS` block). The section-comment header still reads "Invariant 33"; the line actually printed at runtime is `[45/48] CM-OWNERSHIP-INVARIANTS: ...`. Both numbers are real — one is the historical slot label, the other the runner's current position count — and this note exists so a future reader does not treat either alone as stale. The denominator's disagreement with the real invariant count is pre-existing and is filed as BOB-150. Original text: Wire the new gate into `scripts/pre_build_verification.sh` as invariant 45, following the invariant-44 pattern, and renumber the total consistently
- [x] T037 [P] [SUBAGENT] Write `docs/scripts/ownership_repair.md` and `docs/scripts/ownership_precondition.md` companion guides (§11.4.18 requires one per script — and do not cross-reference a doc that does not exist yet, a mistake made on the healthcheck gate this week)
- [x] T038 [P] Update `docs/BOBA_DATABASE.md` §3 to state that the backup procedure is now performable, replacing any wording that assumed it already was
- [x] T039 [P] Run `bash scripts/compute-badges.sh` if any counted artifact changed — it now regenerates exports itself, so it will not leave the tree stale
- [x] T040 File the discovery-channel entry in `docs/QA_DISCOVERY_LEDGER.md` (§11.4.238): this defect was reported by the operator, not found by automated QA, so it is a coverage escape and requires the escape audit plus the new automated check that would have caught it (T034 is that check)
- [ ] T041 [REVIEW] Final independent review of the whole change set (`git diff main...HEAD`) (§11.4.125) before the release gate
- [ ] T042 Run the full **52**-invariant gate via `bash scripts/commit-push-all.sh` with NO `BOBA_SYNC_SKIP_CI` (count RE-MEASURED 2026-08-26: **43** bracket-form + **9** `run_const_gate` invocations = **52**, matching the single `/52` denominator the file itself carries on all 43 bracket labels. The prior "50" here recorded a 2026-08-25 measurement of 41+9; the gate has since grown by two bracket-form invariants and the denominator was updated with it, so 50 became stale — not wrong-at-the-time, stale. A bracket-only scan sees 43 against a /52 denominator and reads as a stale denominator; the missing 9 carry their labels as a string ARGUMENT (`run_const_gate "33/52" ...`), invisible to a bracket-literal grep — the §11.4.201(7)(a) carrier-vs-thing miss that has now bit THREE separate audits of this file. Two-form control-needled instrument: needle `CM-EXPORT-CHARSET-VALID` 5 hits, negative control 0.) — this change touches executable surfaces, so the long gate must actually run [SC-004, SC-005]
      RUN 1 (2026-08-23): 43 passed, 1 failed — VOID, not a product defect. Invariant 30
      caught `download-proxy/src/merge_service/search.py` mtime-moving mid-run; content is
      byte-identical to HEAD, so it was non-quiescence (a sibling reviewer's RED
      reconstruction restored at 11:37:01, inside the window), not a bad restore. I had
      checked process-quiescence, not tree-quiescence, with four agents live. Must RE-RUN
      on a genuinely quiescent tree. Evidence: evidence/T042-gate-run-1-VOID.md.
      NOTE: the harness reported exit 0 while the gate reported 1 failure — that 0 is the
      backgrounded launcher's status, not the gate's. Read the log, never the notification.

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
- **T033 (precondition) sits in Phase 6 but is needed by T031.** If US3 is done early,
  pull T033 forward — it has no dependency on US1/US2.

### Within Each User Story

Tests → implementation → real-invocation evidence → review.

### Parallel Opportunities

| Group | Tasks | Why safe |
|---|---|---|
| Foundational tests | T005, T006, T007 | different files, no shared state |
| Compose service edits | T009 only | different service blocks; T008 first to establish the comment pattern |
| Docs polish | T037, T038, T039 | different files, no code dependency |
| Cross-story | Phase 5 (US3) alongside Phase 3/4 | US3 touches lifecycle only, never ownership |

**Not parallelisable**: T008–T009 and T014 all edit `docker-compose.yml` (T010–T012 turned out to need no edit at all) (T013 is a timing
capture, not an edit). Serialise them or take
the §11.4.84 quiescence risk of two writers in one file.

**[SUBAGENT] candidates**: T029 (unit audit), T037/T038 (docs), T006/T007 (unit tests) —
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
committed config before claiming anything works (T014/T015). This exact confusion already
produced a false "fixed" in this project once.

---

## RESUMPTION STATE — written 2026-08-27T04:05Z

**40 of 42 complete. T041 and T042 remain.** Full detail in `docs/CONTINUATION.md`
(Revision 28); this block is the short form so `superspec execute` has it inline.

### T041 — final independent review
Blocked only by the four in-flight chains below reaching a §11.4.134 GO. Two
review rounds were killed mid-run by a session limit and are OWED, not done:

- **BOB-102 round 14 review** — OWED. Round 13 landed PASS=197 FAIL=0.
- **BOB-195 round 16 review** — OWED. Round 15 landed 144 assertions, 0 failures.
- **BOB-221 round 5 remediation** — round 4 review returned NO-GO
  (0 BLOCKING / 1 IMPORTANT / 4 MINOR / 3 NIT).
- **BOB-207** — 0 BLOCKING; a short re-review closes it.

### T042 — the 52-invariant gate
Will report **3 failures of 39** bash suites until BOB-205 closes. Measured, and
correcting an earlier analysis: **no rc=124 and no rc=127 exist** in the executed
set. Two suites do time out, but the driver excludes them by basename before the
run loop — reading the raw glob instead of the loop produced that phantom.

Also required: a **quiescent tree** at gate time. Invariant 30's no-trace half
fails if any tracked export moves mid-run, which happened repeatedly while four
agents were live.

### The one remaining product blocker
`tests/pre_build/test_bob205_danger_roots_scope.sh` is still `rc=1` (BOB-205,
Queued). The other two intentional REDs now pass: BOB-207 was fixed outright, and
BOB-221's mechanism landed.
