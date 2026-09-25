# Phase 1 Data Model: Zero-Shortcomings Evidence-Backed Audit & Closure

None of the entities below require a new database or a schema migration. Three already
exist as-is in this project (referenced, not modified); two are new, lightweight,
file-based records introduced by this feature.

## Existing entities (referenced, unmodified)

### WorkableItem

Already defined in `docs/workable_items.db` (§11.4.93/§11.4.95). Fields this feature
reads: `atm_id`, `type` (Bug|Feature|Task), `status`, `current_location` (Issues|Fixed),
`reopens_count`, `last_modified`, `operator_block_details` (present only when
`status = 'Operator-blocked'`). **This feature never adds a column** — it only queries
these existing fields for enumeration (FR-001) and risk-ordering (FR-012).

### GovernanceGate

Already defined by `constitution/scripts/gates/gate_ledger_baseline.txt` /
`gate_ledger_deferrals.tsv` / `gate_ledger_removals.tsv` and produced by
`cm_gate_ledger_ratchet.sh`. Fields this feature reads: gate name (`CM-*`), state
(Implemented|Deferred|Unimplemented), and — for Deferred gates — the tracked item id the
deferral points at. **This feature never edits these files** — implementing or deferring
a specific gate remains its own separate, reviewed change (see plan.md's Constitution
Check note that BOB-237-class governance-corpus work is constitution-submodule-owned,
out of this feature's direct write-scope).

## New entities

### CoverageEscapeRecord

A structured view this feature's parser (`scripts/lib/audit_ledger_parser.sh`) produces
by reading one `### ` entry block from `docs/QA_DISCOVERY_LEDGER.md`. Not a new storage
format — the Markdown document remains the source of truth; this is a transient,
in-memory (or scratch-file) representation the orchestrator computes on each run.

| Field | Type | Source | Notes |
|---|---|---|---|
| `id` | string | ledger entry's `**id:**` field | `BOB-NNN` or a short slug per the ledger's own schema |
| `date` | ISO date | ledger entry's `**date:**` field | |
| `channel` | enum | ledger entry's `**channel:**` field | `automated-helixqa` \| `manual-qa` \| `operator-report` \| `agent-code-reading` \| `incidental-discovery` |
| `summary` | string | the entry's heading text | One line, human-readable |
| `escape_audit_present` | boolean | whether `**escape-audit:**` field exists and is non-empty | Required for any non-`automated-helixqa` channel per the ledger's own schema |
| `new_check_present` | boolean | whether `**new-check:**` field exists and is non-empty | **This is the field FR-003's enumeration keys on** — absent/empty means the escape is still open |

**Validation rule**: An entry with `channel != automated-helixqa` and
`escape_audit_present = false` is itself a malformed ledger entry (violates the ledger's
own documented schema) and is reported as a distinct finding, separate from — and in
addition to — an open (`new_check_present = false`) escape.

### ClosureEvidenceArtifact

Formalizes the pattern this session's closures (`docs/qa/<id>/closure_evidence_<date>.md`)
already follow by convention, adding the explicit fields the independent-re-verification
harness (FR-004/006/013) and the credential-redaction requirement (Constitution Check,
Principle III) depend on.

| Field | Type | Notes |
|---|---|---|
| `item_id` | string | The `WorkableItem.atm_id` (or gate name / `CoverageEscapeRecord.id`) this evidence closes |
| `command` | string | The exact command invoked to produce the evidence — what independent re-verification re-runs |
| `exit_code` | integer | Captured at run time |
| `result_summary` | string | The command's own reported outcome where applicable (e.g. "32 passed, 0 failed") — the semantic comparison target for re-verification, per research.md §4 |
| `captured_at` | ISO datetime | When this evidence was produced |
| `redaction_applied` | boolean | MUST be `true` for any item touching tracker credentials, cookies, or `BOBA_MASTER_KEY`-adjacent surfaces (Constitution Check, Principle III / §11.4.10.A) before the artifact is written |
| `reproducible` | boolean, derived | Set by the re-verification harness after re-running `command` and comparing `exit_code` + `result_summary` against a fresh run; `false` triggers automatic reopen (FR-013) |

**State transition**: `reproducible` starts unset at creation time (the artifact has not
yet been independently re-checked); it is set to `true` or `false` the first time the
re-verification harness processes it, and MUST be re-evaluated (never assumed to remain
`true` forever) if the underlying command's target environment changes materially (for
example, a live-service-dependent command re-checked after that service's state
changed).

### AuditRunRecord

One record per invocation of `scripts/zero_shortcomings_audit.sh`, appended to
`docs/qa/zero_shortcomings_audit/<run-id>.log` (new, plain-text, append-only — no
existing tracked file is edited by writing this).

| Field | Type | Notes |
|---|---|---|
| `run_id` | string | Timestamp + PID, matching this project's existing `run_id` convention (e.g. `20260925T113437Z-pid3872998`, already used across this session's own QA evidence) |
| `mode` | enum | `enumerate-only` \| `closure-pass` \| `standing-check` (the pre-build-invariant invocation) |
| `surface_counts` | object | `{backlog_open, gates_unimplemented, escapes_open}` — the three raw counts from surfaces 1–3 at this run |
| `corruption_incidents` | list of file paths | Any FR-008 evidence-corruption detections this run caught and reverted; empty list on a clean run |
| `items_closed` | list of item ids | Only populated in `closure-pass` mode |
| `items_reopened` | list of item ids | Only populated when FR-013 fires during this run |

**Validation rule**: A `standing-check` run is always `mode = enumerate-only` in effect
(read-only, non-mutating) — it MUST NEVER attempt closure work itself; closure only
happens in an explicit, operator-or-agent-initiated `closure-pass` invocation. This
keeps the pre-build-wired recurring check (FR-009) cheap and side-effect-free, per the
plan's stated Performance Goal.

### ExecutionPolicy

A fixed, non-persisted configuration object read once per orchestrator invocation,
encoding the Principle XIII host-resource bounds every dispatched closure-verification
command must respect.

| Field | Type | Default | Notes |
|---|---|---|---|
| `max_parallel_items` | integer | 3 | Mirrors this session's own proven working band (3–6 concurrent subagents, per the inherited constitution's parallel-agent guidance) |
| `nice_level` | integer | 19 | Applied to any dispatched heavy test-suite process, per Principle XIII |
| `ionice_class` | integer | 3 (idle) | Applied identically |
| `resource_ceiling_pct` | integer | 40 | The upper bound this feature must never let its own dispatched work exceed, per Principle XIII's 30–40% host-resource limit |

**Validation rule**: `ExecutionPolicy` values are read from a single, greppable location
in `scripts/zero_shortcomings_audit.sh` (never hardcoded redundantly in multiple
places) so a future host-resource tuning change touches one line, consistent with this
project's own §11.4.6 no-guessing / single-source-of-truth discipline.
