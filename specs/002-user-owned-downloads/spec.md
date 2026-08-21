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
2. **Given** the repair has already run, **When** the system starts again, **Then** it
   does not re-walk the tree and makes no further changes.
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
- Ownership must remain correct across a restart and across a full recreate of the
  system, not only immediately after the change is applied.

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
- **FR-004a**: That automatic repair MUST run ONCE, not on every start. Subsequent
  starts MUST NOT re-walk the tree.
- **FR-004b**: Because FR-004 changes ownership of pre-existing data without being
  asked, the repair MUST record what it changed in a durable, operator-readable
  record before changing it, sufficient to identify every item whose ownership it
  altered. The operator accepted the convenience/risk trade-off knowingly; this
  requirement is what keeps that choice recoverable rather than irreversible.
- **FR-004c**: The operator MUST also be able to invoke the same repair explicitly,
  for content added later by other means.
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

### Key Entities

- **Operator account**: the identity that starts the system and must own everything it
  writes.
- **Mapped identity**: the distinct host identity the container platform currently
  attributes created files to; the source of the defect.
- **Operator-visible storage**: the configured download locations — completed content,
  in-progress content, and the root that contains them.
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
- The download locations already configured are the operator-visible storage in scope.
  Internal state that the operator never handles directly is out of scope.
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
- Repairing content outside the declared download locations.

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
