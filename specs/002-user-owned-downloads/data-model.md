# Phase 1 Data Model: Downloads Owned by the Person Who Started the System

**Feature**: 002-user-owned-downloads · **Date**: 2026-08-21

This feature stores almost nothing. Its "data" is mostly *filesystem ownership metadata*
plus three small durable artifacts: a scope declaration, a completion marker, and a
change record. Each is defined below with the validation rules the requirements impose.

---

## E1. Owned-Path Scope (declared, `config/owned_paths.yaml`)

The authoritative list of locations that MUST end up operator-owned. Consumer DATA
(§11.4.35), not derived.

| Field | Type | Rules |
|---|---|---|
| `schema_version` | int | present; `1` |
| `paths[].path` | string | absolute, or relative to project root; MUST exist at check time or be explicitly marked `optional: true` |
| `paths[].kind` | enum | `downloads` \| `project-config` \| `credential-store` |
| `paths[].optional` | bool | default `false`; an absent non-optional path is an error, not a skip |
| `paths[].preserve_mode` | bool | default `false`; when `true` the repair MUST NOT alter permission bits (FR-015) |
| `paths[].recursive` | bool | default `true` |

**Why declared, not derived (FR-012 rationale)**: compose environment mixes served and
dependency values under one indistinguishable naming shape, and the download root differs
per host. Deriving it would produce exactly the false-positive refusal §11.4.201(1)
forbids — the same trap the healthcheck manifest fell into when it was seeded from prose
rather than source.

**Seed content (from measurement, research.md R6)**:

| path | kind | preserve_mode |
|---|---|---|
| the configured download root (`QBITTORRENT_DATA_DIR`) | `downloads` | false |
| `config/` | `project-config` | false |
| `config/boba.db` | `credential-store` | **true** (mode 600 must survive) |

---

## E2. Repair Marker

Records that the automatic repair completed **successfully**, so it does not re-walk on
every start (FR-004a).

| Field | Type | Rules |
|---|---|---|
| `completed_at` | ISO 8601 UTC | written **only** after a fully successful pass |
| `scope_fingerprint` | sha256 | hash of the sorted declared scope; a scope change invalidates the marker and re-arms the repair |
| `items_changed` | int | count of items whose ownership was altered |

**State transitions** — the load-bearing part, and the correctness hole clarify Q1 closed:

```
ABSENT ──first start──> RUNNING ──success──> COMPLETE
                           │
                           └──interrupted──> ABSENT   (marker never written)
                                                │
                                                └──next start──> RUNNING …
```

- The marker is written **only** on success. An interrupted run leaves it absent, so the
  next start resumes and keeps resuming until it completes.
- Writing on *start* instead would let one crash mark the repair done and permanently
  skip the remainder — the run-once optimisation would defeat the repair it optimises.
- `scope_fingerprint` mismatch ⇒ treat as ABSENT. Adding a path to E1 must re-arm the
  repair, otherwise new scope is silently never repaired.

---

## E3. Change Record

The mitigation that keeps the operator's accepted automatic-repair risk recoverable
(FR-004b). Written **before** the change it describes.

| Field | Type | Rules |
|---|---|---|
| `path` | string | absolute |
| `previous_uid` / `previous_gid` | int | recorded before mutation |
| `previous_mode` | octal | recorded before mutation |
| `new_uid` / `new_gid` | int | |
| `changed_at` | ISO 8601 UTC | |
| `outcome` | enum | `changed` \| `skipped` \| `failed` |

**Rules**:
- Append-only. One entry per item whose ownership was altered.
- Written **before** mutating, so a crash mid-repair still leaves a record of what was
  already touched (this is what makes E2's resume safe rather than blind).
- `failed` entries are mandatory — FR-006 forbids reporting success for items not
  changed.
- It MUST be operator-readable and MUST NOT live only inside a container.
- **Deliberately unspecified here**: exact location and serialisation. Deferred from the
  clarify session as an implementation decision. Constraint: `docs/qa/` is for QA
  evidence and is the wrong home for an operational log.
- Contains paths, uids and modes only — never file contents, never credential values
  (§11.4.10). `boba.db` appears as a path; its contents never do.

---

## E4. Ownership Probe Result (transient)

Produced by the startup precondition (FR-010) and by the regression gate (FR-011). Not
persisted.

| Field | Type | Rules |
|---|---|---|
| `path` | string | the location probed |
| `probe_uid` | int | uid of a file **actually created** in that location |
| `expected_uid` | int | the operator's uid |
| `verdict` | enum | `ok` \| `wrong-owner` \| `unwritable` \| `absent` |

**Rule (FR-010b)**: `probe_uid` MUST come from creating a real file in the real location
and reading its owner back, then removing it. Inferring from the parent directory's owner,
from configuration, or from "no error" is a proxy — and a probe that passes because it
never wrote anything is a false pass.

---

## E5. Service Ownership Route (configuration, not stored)

Per-service record of which mechanism applies. Lives in `docker-compose.yml`; reproduced
here as the FR-016 completeness map.

> **SUPERSEDED — see
> [research.md R9](./research.md#r9-correction--route-a-was-wrong-it-supersedes-r3s-route-a-verdict-and-r5s-route-table).**
> The original table below (planned at Phase-0/Phase-1 design time, before any
> implementation) assigned Route A (`userns_mode: keep-id`) to `download-proxy`,
> `qbittorrent-proxy-go`, and `boba-jackett`. Measurement at implementation time showed
> all three already run as container uid 0 and already write host-uid-1000 files — Route
> A was never applied to them because it would have been a regression (the same hang R3
> measured on the linuxserver images), not a no-op. `userns_mode: keep-id` is applied to
> **no service in this stack**; `docker-compose.yml` carries no `userns_mode` key at all
> (grep-verified 2026-08-21). Route B (`PUID=0`/`PGID=0`) is the only route shipped. The
> planned table is left below unedited — what was believed, and why, is the record —
> followed by the table as actually shipped.

| Service | Route (as planned, Phase 0/1) | Setting | Evidence |
|---|---|---|---|
| `qbittorrent` | B | `PUID=0` / `PGID=0` | keep-id hangs this image (R3) |
| `jackett` | B | `PUID=0` / `PGID=0` | same |
| `download-proxy` | A | `userns_mode: keep-id` | verified on alpine (R3) |
| `qbittorrent-proxy-go` | A | `userns_mode: keep-id` | **to verify per-service** (R5 boundary) |
| `boba-jackett` | A | `userns_mode: keep-id` | **to verify per-service**; writes `boba.db` |

### As shipped (research.md R9)

| Service | Route | Setting | Evidence |
|---|---|---|---|
| `qbittorrent` | B | `PUID=0` / `PGID=0` | keep-id hangs this image (R3); re-confirmed |
| `jackett` | B | `PUID=0` / `PGID=0` | same |
| `download-proxy` | **none** | no `userns_mode` change | write probe: already host uid 1000 (R9) |
| `qbittorrent-proxy-go` | **none** | no `userns_mode` change | runs as container uid 0, no `USER` directive (R9) |
| `boba-jackett` | **none** | no `userns_mode` change | write probe: already host uid 1000 (R9) |

**Validation rule**: every service that mounts an E1 path MUST appear in this table with a
route. A service that mounts an in-scope path and has neither setting is an FR-016
violation — partial application returns the defect the moment that service runs. "None"
above is a recorded, evidenced route decision (already-correct, verified by write probe),
not an omission.

---

## Relationships

```
Owned-Path Scope (E1) ──declares──> locations
        │                              │
        │                              ├──probed by──> Probe Result (E4)  [precondition + gate]
        │                              └──repaired by──> Change Record (E3)
        │
        └──fingerprint──> Repair Marker (E2)   [scope change re-arms the repair]

Service Route (E5) ──governs──> what ownership NEW files get
                                (E1..E3 only handle the pre-existing backlog)
```

The separation matters: **E5 prevents the defect; E1–E3 clean up its history.** A change
that only does the second is the current manual workaround, automated.
