# Feature Specification: Downloads Owned by the Person Who Started the System

**Feature Branch**: `002-user-owned-downloads`
**Created**: 2026-08-21
**Status**: Draft
**Input**: User description: "Make sure that System runs (starts) and creates and modifues files as current user under which we do start it using systemctl --user space so downloads we have and directories that have been created can be manipulated by current account user! Currently we have to change the ownership every time something is downloaded, this is bad UX!"

## Problem Framing

The operator's request contains a proposed mechanism ("run it under `systemctl --user`")
and an outcome ("downloads can be manipulated by the current account user"). Evidence
gathered on the live host shows **these are two separate concerns, and the proposed
mechanism does not by itself deliver the outcome**. This spec therefore treats the
OUTCOME as the requirement and records the mechanism question honestly.

Measured on the host, 2026-08-21:

- The person running the system is uid 1000. The container platform maps the
  in-container account to a *different* host identity drawn from a delegated range
  (host uid 100999). The download root itself is currently owned by that mapped
  identity and displays as `UNKNOWN:UNKNOWN` to the operator.
- Files land under that mapped identity, so the operator cannot rename, move, or
  delete them without first reassigning ownership — the reported UX defect.
- 6,458 items under the download tree are currently owned by the operator and 1 by
  the mapped identity. That ratio is consistent with the operator repeatedly
  reassigning ownership by hand after each download, which is precisely the toil
  being reported.
- Session-scoped service definitions for this system **already exist** and are
  **inactive**; the documented start path does not reference them at all.

The load-bearing consequence: the system *already* runs under the operator's own
account. Moving its lifecycle under session-scoped service management changes **when
and how it starts**, not **which identity owns the files it writes**. Adopting that
mechanism alone would leave the reported defect exactly as it is.

## Clarifications

### Session 2026-08-21

- Q: If the automatic ownership repair is interrupted partway (power loss, stop, crash), what should happen on the next start? → A: Resume until complete — the "already ran" marker is written only after a fully successful pass.
- Q: Should the automatic first-start repair block startup until it finishes, or let the system come up while it runs? → A: Block startup until complete, reporting progress.
- Q: Should there be a time limit on the blocking first-start repair? → A: No bound — run to completion; progress and resume-on-interrupt are the mitigation.
- Q: Should ownership scope include container-written project paths beyond downloads? → A: Yes — all container-written paths, including `config/` and `config/boba.db`.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Downloaded files are immediately usable (Priority: P1)

An operator finishes a download and wants to rename it, move it into a media library,
or delete it, using their normal file manager or shell — with no privileged step and
no ownership reassignment.

**Why this priority**: This is the reported defect and the entire user-visible value
of the feature. Shipping only this story already removes the toil.

**Independent Test**: Complete one download end to end, then rename, move, and delete
the resulting file and its containing directory as the operator, with no elevation and
no ownership change.

**Acceptance Scenarios**:

1. **Given** the system is running, **When** a download completes, **Then** the
   resulting file and every directory created for it are owned by the operator's own
   account and are writable by them without any additional step.
2. **Given** a completed download, **When** the operator renames, moves, or deletes it
   using ordinary tools, **Then** the operation succeeds on the first attempt.
3. **Given** a download that creates nested directories, **When** it completes,
   **Then** every level of the created tree is owned by the operator, not only the
   leaf file.

---

### User Story 2 - Existing wrongly-owned content is repaired automatically (Priority: P2)

An operator who has been living with this defect has accumulated content owned by the
wrong identity, including the download root. On the first start after the fix, that
backlog is repaired for them without their asking.

**Why this priority**: Without it the fix only applies to *future* downloads and the
operator still faces a directory they cannot manage. It is P2 because it is a one-time
migration, not the recurring defect.

**Independent Test**: Start the system once against a tree containing wrongly-owned
items and confirm, without any operator action, that every item is operator-owned
afterwards, that nothing outside the declared scope was altered, and that a record of
what changed exists.

**Acceptance Scenarios**:

1. **Given** existing content owned by the mapped identity, **When** the system starts
   for the first time after the fix, **Then** all of it becomes operator-owned with no
   operator action.
2. **Given** the repair has already completed SUCCESSFULLY, **When** the system starts
   again, **Then** it does not re-walk the tree and makes no further changes.
2b. **Given** the repair was INTERRUPTED partway, **When** the system starts again,
   **Then** it resumes and continues until every in-scope item is operator-owned.
2a. **Given** the automatic repair has run, **When** the operator inspects the record
   it wrote, **Then** every item whose ownership it changed is identifiable.
3. **Given** content outside the declared download scope, **When** the repair runs,
   **Then** that content is untouched.
4. **Given** the repair cannot complete an item, **When** it finishes, **Then** it
   reports which items were not repaired rather than claiming success.

---

### User Story 3 - The system starts with the operator's session (Priority: P3)

An operator wants the system to start as part of their own session, be startable and
stoppable through the same session-scoped mechanism, and stop when they log out —
without a privileged system-wide service.

**Why this priority**: This is the operator's proposed mechanism and is genuinely
useful for lifecycle management, but the evidence shows it does not cause the
ownership outcome. Sequencing it third keeps the reported defect from being blocked
behind a lifecycle change.

**Independent Test**: Start and stop the whole system through the session-scoped
mechanism only, and confirm the documented start path and the session-scoped path
agree about what is running.

**Acceptance Scenarios**:

1. **Given** the system is not running, **When** the operator starts it through the
   session-scoped mechanism, **Then** every service comes up and reports healthy.
2. **Given** the system is running, **When** the operator stops it the same way,
   **Then** every service stops and none is left behind.
3. **Given** the system was started through the documented start path, **When** the
   operator queries the session-scoped mechanism, **Then** the reported state matches
   reality rather than contradicting it.

---

### Edge Cases

- Content created *before* the fix remains wrongly owned until the repair runs; new
  downloads must not silently inherit the old ownership from their parent directory.
- The download root itself is currently wrongly owned. A fix that corrects only files
  created *inside* it leaves the operator unable to manage the root.
- Downloads that are moved or hard-linked between an in-progress area and a completed
  area must be operator-owned in both.
- Content on a removable or externally-mounted volume may not permit ownership changes
  at all; the system must report that honestly rather than appear to succeed.
- If the operator's account identity ever differs from the identity the system was
  configured with, the system must refuse or report clearly rather than write files
  nobody can manage.
- A service that runs only under an optional profile must not be overlooked: the
  defect returns the moment it runs (FR-016).
- The repair must not widen access on anything it touches; the credential database in
  particular must stay as restricted as it is now (FR-015).
- Ownership must remain correct across a restart and across a full recreate of the
  system, not only immediately after the change is applied.
- A very large pre-existing library makes the first start take proportionally longer,
  by design (FR-004f). This is accepted behaviour, not a defect — but it MUST be
  distinguishable from a hang, which is what FR-004e's real-progress requirement
  exists to guarantee.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Every file the system creates in operator-visible storage MUST be owned
  by the account that started the system.
- **FR-002**: Every directory the system creates in operator-visible storage MUST be
  owned by that same account, at every level of any tree it creates.
- **FR-003**: The operator MUST be able to rename, move, and delete downloaded content
  using ordinary tools, with no elevation and no ownership reassignment.
- **FR-004**: The system MUST bring already-existing content — including the
  download root — under the operator's ownership AUTOMATICALLY, on the first start
  after the fix is in place, with no operator action required (operator decision,
  2026-08-21).
- **FR-004a**: That automatic repair MUST run ONCE SUCCESSFULLY, not on every start.
  The "already ran" marker MUST be written ONLY after a fully successful pass, so an
  interrupted run (power loss, stop, crash) RESUMES on the next start and keeps
  resuming until it completes. Marking on START instead would let a single crash
  permanently skip the remainder and leave the library half-owned — the run-once
  optimisation would defeat the repair it exists to optimise. Once the marker is
  written, subsequent starts MUST NOT re-walk the tree.
- **FR-004b**: Because FR-004 changes ownership of pre-existing data without being
  asked, the repair MUST record what it changed in a durable, operator-readable
  record before changing it, sufficient to identify every item whose ownership it
  altered. The operator accepted the convenience/risk trade-off knowingly; this
  requirement is what keeps that choice recoverable rather than irreversible.
- **FR-004c**: The operator MUST also be able to invoke the same repair explicitly,
  for content added later by other means.
- **FR-004d**: The automatic repair MUST BLOCK startup until it completes: no service
  that writes to operator-visible storage may accept work until every in-scope item is
  operator-owned. A background repair is explicitly rejected — it would leave a window
  in which downloads land in a half-repaired tree, so the reported defect would still
  bite, intermittently and unpredictably, which is harder to diagnose than the
  consistent defect being replaced.
- **FR-004e**: While blocking, the repair MUST report progress in a form the operator
  can see, so a large library never presents as a hung startup. Progress MUST reflect
  real work completed, not a spinner or a fixed-step estimate.
- **FR-004f**: The blocking repair MUST NOT impose a time limit on itself. It runs to
  completion however long that takes. A budget that falls back to background would
  reintroduce the half-repaired window rejected in FR-004d; a budget that aborts would
  leave the library knowingly half-owned and restore the manual step this feature
  exists to remove. The operator's escape hatch is FR-004a: stopping the system is
  safe, because the next start resumes.
- **FR-004g**: Because the repair blocks every download-writing service (FR-004d), no
  download can be in progress while it runs. Concurrent-modification handling between
  the repair and an active download is therefore OUT OF SCOPE by construction, not by
  omission.
- **FR-005**: The repair MUST be scoped to declared locations and MUST NOT alter
  anything outside them.
- **FR-006**: The repair MUST report any item it could not repair, and MUST NOT report
  success for items it did not change.
- **FR-007**: Correct ownership MUST survive a restart of the system and a full
  recreate of it.
- **FR-008**: The system MUST be startable and stoppable through a session-scoped
  mechanism tied to the operator's own login session, without a privileged
  system-wide service.
- **FR-009**: The session-scoped mechanism and the documented start path MUST NOT
  contradict each other about what is running.
- **FR-010**: If the system cannot create operator-owned files in a configured
  location, it MUST REFUSE TO START and fail loudly with a message naming the
  offending location (operator decision, 2026-08-21). Starting with a warning is
  explicitly rejected: a missed warning silently reproduces the very defect this
  feature exists to remove.
- **FR-010a**: The refusal MUST name the location and state what was wrong with it,
  so the operator can act without further diagnosis.
- **FR-010b**: The startup check MUST assert the REAL condition — that a file created
  in that location is actually owned by the operator — rather than a proxy for it. A
  check that passes because it never actually wrote anything is a false pass.
- **FR-011**: An automated check MUST detect a regression of this behaviour — that is,
  it MUST fail if the system again creates content the operator cannot modify.
- **FR-012**: Ownership scope MUST include container-written project paths, not only
  downloads (clarified 2026-08-21). Measured on the host: the configuration tree held
  51 items owned by the mapped identity, and the credential database was mode 600
  under an owner that does not resolve — so the operator could not read it.
- **FR-013**: The operator MUST be able to perform the documented backup procedure —
  copying the credential database and the environment file together — without an
  ownership step. This is currently IMPOSSIBLE, and the governing documentation warns
  that losing the master key means total credential loss, so the backup it prescribes
  is both mandatory and unperformable. Fixing FR-012 is what unblocks it.
- **FR-014**: No project path the system itself created may be left in a state where
  the operator cannot read, edit, or back it up.
- **FR-015**: Changing ownership MUST NOT relax access restrictions. The credential
  database is currently mode 600 and MUST remain no more permissive than it is today.
  Bringing a credential store under the operator's ownership while widening who can
  read it would trade a usability defect for a security one — a strictly worse
  outcome. (Recorded as an informed default, not an operator decision: no reasonable
  alternative exists.)
- **FR-016**: The fix MUST apply to EVERY service that writes to in-scope locations,
  including services that only run under an optional profile. Correcting some services
  and not others reproduces the defect the moment an uncorrected one runs, and the
  resulting intermittent behaviour is harder to diagnose than the consistent defect
  being replaced. (Informed default — partial application is not a coherent option.)

### Key Entities

- **Operator account**: the identity that starts the system and must own everything it
  writes.
- **Mapped identity**: the distinct host identity the container platform currently
  attributes created files to; the source of the defect.
- **Operator-visible storage**: every location the system writes that the operator is
  expected to handle. This is BROADER than downloads (clarified 2026-08-21): it covers
  the configured download locations — completed content, in-progress content, and the
  root that contains them — AND container-written project paths such as the
  configuration tree and the credential database.
- **Pre-existing content**: content created before the fix, which the one-time repair
  addresses.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An operator can rename, move, and delete any newly downloaded item on
  the first attempt, with no ownership step — measured across at least 10 consecutive
  downloads with a 100% success rate.
- **SC-002**: The number of manual ownership-reassignment actions an operator performs
  per download drops from one to **zero**.
- **SC-003**: After the one-time repair, **0** items in the declared download
  locations — including the root — are owned by anything other than the operator
  account.
- **SC-004**: Ownership remains correct after a restart and after a full recreate, on
  100% of trials.
- **SC-004a**: At the moment the system first accepts a download, **0** in-scope items
  are owned by anything other than the operator — i.e. there is no window in which the
  defect can recur.
- **SC-007**: The operator can complete the documented credential-database backup in a
  single copy operation, with no ownership step — verified by performing it, not by
  inspecting permissions.
- **SC-005**: The whole system can be started and stopped through the session-scoped
  mechanism, with every service reaching a healthy state within the same time budget
  as the existing start path.
- **SC-006**: A regression that reintroduces unmanageable content is caught
  automatically before release, demonstrated by the check failing on a deliberately
  reintroduced defect and passing when the defect is absent.

## Assumptions

- "Current user" means the account that starts the system (uid 1000 on the observed
  host). The system is single-operator; no multi-user arbitration is in scope.
- "Manipulated" means the ordinary operations a person performs on their own files —
  rename, move, delete, edit — not a formal permissions model.
- Operator-visible storage in scope is every location the system writes that the
  operator is expected to handle: the configured download locations AND
  container-written project paths including the credential database (FR-012). An
  earlier draft scoped this to downloads only; that was corrected once evidence showed
  the credential database is unreadable to its own owner.
- The repair runs automatically on first start (operator decision, 2026-08-21). The
  spec's own recommendation was explicit invocation, on the grounds that rewriting
  ownership across a large existing library without being asked is hard to undo; the
  operator weighed that against the extra manual step and chose automatic. FR-004b
  (record what changed before changing it) is the mitigation that makes that choice
  recoverable, and is required rather than optional as a result.
- Group-based workarounds (shared groups, permissive modes, access-control lists) are
  acceptable implementation routes only if they satisfy FR-001 through FR-003 without
  the operator performing a per-download step. The spec does not mandate a mechanism.
- Because rootless operation is a standing project constraint, the fix must not require
  a privileged or root-owned service.

## Dependencies

- The container platform must support mapping the in-container account to the
  operator's own host identity. If it does not, FR-001/FR-002 cannot be met by
  configuration alone and an alternative route (shared group plus inherited
  permissions) becomes necessary.
- The one-time repair depends on the underlying storage permitting ownership changes.

## Out of Scope

- Multi-user or multi-tenant ownership arbitration.
- Changing where downloads are stored.
- Any privileged, system-wide service installation.
- Repairing content outside the declared locations. NOTE: the declared locations were
  WIDENED on 2026-08-21 to include container-written project paths (FR-012); an earlier
  draft of this spec placed "internal state the operator never handles directly" out of
  scope, which was wrong — the documented backup procedure requires the operator to
  handle the credential database directly.

## Clarifications Resolved

Both open questions were put to the operator on 2026-08-21 and answered:

1. **One-time repair trigger** → **automatic on first start**. The spec recommended
   explicit invocation (rewriting ownership across an existing library without being
   asked is hard to undo). The operator chose automatic. Recorded as FR-004, with
   FR-004a (run once, not every start) and FR-004b (record what changed before
   changing it) added so the accepted risk stays recoverable.
2. **Storage that cannot produce operator-owned files** → **refuse to start, naming
   the location**. Recorded as FR-010, with FR-010a (name it and say what was wrong)
   and FR-010b (assert the real condition, not a proxy) added.
