# Implementation Plan: Zero-Shortcomings Evidence-Backed Audit & Closure

**Branch**: `003-zero-shortcomings-audit` | **Date**: 2026-09-25 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/003-zero-shortcomings-audit/spec.md`

## Summary

Build one orchestrating audit tool (`scripts/zero_shortcomings_audit.sh`) that unifies
this project's THREE already-tracked "unfinished / gap / shortcoming" surfaces — the
open workable-items backlog (`docs/workable_items.db`, 41 open items as of 2026-09-25),
the named-but-unimplemented governance-gate ledger (`constitution/scripts/gates/`, 414
unimplemented vs. a 403 baseline per BOB-237), and the coverage-escape discovery ledger
(`docs/QA_DISCOVERY_LEDGER.md`, entries missing a closing `new-check`) — into one
enumeration, drives each enumerated item to a genuine terminal state through the
project's own existing per-domain test frameworks with independently re-producible
evidence, and wires itself into the existing manual `scripts/pre_build_verification.sh`
gate suite as a recurring, non-CI mechanism so the zero-open-findings state is checked on
every commit rather than only once.

Two of the three enumeration surfaces already have working tools
(`constitution/scripts/workable-items`, `constitution/scripts/gates/gate_ledger.sh`) —
this plan consumes them rather than rebuilding them. The genuinely new engineering is:
(1) a parser for the coverage-escape ledger's Markdown schema, (2) the independent
re-verification harness that closes FR-004/005/006/013, (3) the evidence-corruption
guard that closes FR-008 (the exact class this session already hit once, live, against
`docs/qa/BOB-109/*.json`), and (4) wiring all of it into the existing manual gate suite
per Principle VI's "no CI/CD" hard stop.

## Technical Context

**Language/Version**: Bash (the orchestrator itself, consistent with every other
top-level `scripts/*.sh` entry point in this project — Principle VI/VII); the tool
dispatches into whichever per-domain runtime an enumerated item's own tests already use
(Python 3.12 / pytest, Go 1.26+ / `go test -race`, TypeScript / Vitest) — no new language
is introduced for closure work itself.
**Primary Dependencies**: `constitution/scripts/workable-items` (tracker CLI, existing),
`constitution/scripts/gates/gate_ledger.sh` + `cm_gate_ledger_ratchet.sh` (gate-ledger
scanner, existing), `docs/QA_DISCOVERY_LEDGER.md` (coverage-escape ledger, existing
document, no existing parser), `sqlite3` CLI (already a project dependency via the
tracker), the project's existing color-print helper library (`scripts/lib/*` — reused
per Principle VII, never re-implemented).
**Storage**: `docs/workable_items.db` (SQLite, existing — no schema change). The audit
tool's own run history is appended to `docs/qa/zero_shortcomings_audit/<run-id>.log`
(new, plain-text, following the existing `docs/qa/<run-id>/` evidence convention already
used by every closure this session).
**Testing**: `tests/audit/test_zero_shortcomings_audit.sh` (new, bash test harness
following the exact pattern of `tests/unit/test_ownership_repair.sh` and siblings
already in this repo — golden-good/golden-bad fixtures, paired §1.1 mutations); the tool
invokes but never replaces each item's own existing test suite (pytest / go test /
Vitest / bash) for closure verification.
**Target Platform**: Linux host, rootless Podman containers (existing project target,
Principle IV) — no new platform surface.
**Project Type**: Cross-cutting maintenance/audit tool spanning the existing repository;
not a new service, not a new container (Principle I is unaffected — no
`docker-compose.yml` change).
**Performance Goals**: A full three-surface enumeration pass completes in well under one
minute (it reads existing ledgers/DB queries; it does not itself run the full test
suite) so it is cheap enough to run on every `scripts/commit-push-all.sh` invocation
without materially slowing the existing 58-invariant pre-build sweep. Per-item closure
verification work is separately time-boxed and risk-ordered (FR-012) so a bounded
working session still closes the highest-value items first.
**Constraints**: Scope is bounded to the three already-tracked surfaces confirmed in
the spec (Q1, Option A) — never an unbounded fresh discovery pass. Must never corrupt
existing tracked evidence as a side effect of verification (FR-008 — the BOB-109 JSON
class this session already reproduced once, live). Must respect Principle XIII host
resource limits (30–40% of host resources; `nice`/`ionice`/`GOMAXPROCS` bounds on any
heavy per-item test run it dispatches). Must serialize concurrent edits to the same file
(FR-011) using the project's existing `--scope` convention on
`scripts/commit-push-all.sh` and subagent file-scope discipline — no new locking
primitive is invented. Operator-blocked items are excluded from autonomous closure and
must be reported with their existing recorded blocking condition intact (FR-007).
Because Principle VI is an absolute "NO CI/CD PIPELINES" hard stop, the "standing,
recurring" mechanism (FR-009) CANNOT be a cron job, a GitHub Action, or any hosted
scheduler — it MUST be wired as an explicit stage inside the existing manual
`scripts/pre_build_verification.sh` gate, which already runs on every
`scripts/commit-push-all.sh` invocation.

## Constitution Check

*GATE: Must pass before proceeding. Re-check after design phase.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Container-First Architecture | PASS | No new service, no `docker-compose.yml` change. The audit tool is a script, not a container. |
| II. Plugin Contract Integrity | PASS (N/A unless an enumerated item touches a plugin) | The audit tool itself does not touch the plugin contract; any enumerated backlog item that does still follows Principle II unchanged. |
| III. Credential & Secret Security | NEEDS ATTENTION | Evidence artifacts (FR-004/012's captured command output) MUST NOT capture credential values — closure evidence for any tracker-credential-adjacent item must redact per §11.4.10.A before being written to `docs/qa/<id>/`. Addressed explicitly in Phase 1 data model (`ClosureEvidenceArtifact.redaction_applied`). |
| IV. Container Runtime Portability | PASS | No new runtime-detection logic; nothing in this feature touches Podman/Docker selection. |
| V. Private Tracker Bridge Pattern | N/A | Only relevant if a specific enumerated backlog item touches the bridge; unaffected by this feature itself. |
| VI. Validation-Driven Development | PASS | The orchestrator script itself passes `bash -n`; per-item closure work continues to use `./ci.sh` / `ruff` / `go test` / `ng test` exactly as today. The "NO CI/CD" hard stop directly shapes the FR-009 design decision (wired into the manual gate, never a scheduler) — see Constraints above. |
| VII. Operational Simplicity | PASS | One dedicated entry point (`scripts/zero_shortcomings_audit.sh`) with `-h/--help`, using the shared color-print helpers — consistent with every other top-level script. |
| VIII. IPTorrents Freeleech Policy | N/A | Not touched by this feature unless a specific enumerated item is tracker-download-related. |
| IX. Test-Driven Development | PASS | FR-004 mandates RED-before-fix for every item this feature closes; the audit tool's own new logic (ledger parser, re-verification harness, evidence-corruption guard) is itself built RED-first per `tests/audit/test_zero_shortcomings_audit.sh`. |
| X. Hermetic Test Discipline | NEEDS ATTENTION | The audit tool's OWN unit-level tests (ledger parsing, enumeration diffing) must be hermetic/mocked against fixture ledgers — never the live `docs/workable_items.db` or the live `docs/QA_DISCOVERY_LEDGER.md`. Its integration-level tests may read the real DB/ledger read-only. Its evidence-corruption guard (FR-008) is precisely a hermeticity enforcement mechanism applied to every OTHER item's closure work, not only to itself. Addressed in Phase 1. |
| XI. Minimal Source Commentary | PASS (N/A) | The orchestrator lives under `scripts/`, not `download-proxy/src/` — Principle XI's no-comments rule does not apply. Normal Bash commenting conventions (Principle VI) apply instead. |
| XII. Anti-Bluff Captured Evidence | PASS | This principle is the one this entire feature exists to operationalize; every functional requirement in the spec is a direct instantiation of it (captured evidence, no self-certification words, RED-before-fix, no flaky-test tolerance, evidence bundle per closure). |
| XIII. Host-Session Safety | NEEDS ATTENTION | Dispatching per-item closure verification (which may include multi-minute bulk test suites, per this session's own BOB-135 27-minute run) must stay within the 30–40% host-resource ceiling. The orchestrator MUST cap its own parallelism and apply `nice`/`ionice` to any heavy dispatched work, and MUST NEVER touch host power-state (Principle XIII's absolute forbidden list is unaffected — this feature adds no new process class that could plausibly trigger it). Addressed in Phase 1 (`ExecutionPolicy` entity) and in `quickstart.md`'s resource-bound verification step. |

**Result**: No VIOLATIONS. Three principles (III, X, XIII) need explicit design
attention, each addressed by name in Phase 1 below — none requires a Complexity
Tracking justification, since each is satisfied by design rather than overridden.

**Post-design re-check** (after Phase 1 — `data-model.md` / `contracts/cli.md` /
`quickstart.md`): all three NEEDS ATTENTION items now resolve to PASS.
- III (Credential & Secret Security): closed by `ClosureEvidenceArtifact.redaction_applied`
  (data-model.md) — mandatory before any credential-adjacent item's evidence is written.
- X (Hermetic Test Discipline): closed by the FR-008 evidence-corruption guard
  (`AuditRunRecord.corruption_incidents`, research.md §5, quickstart.md Step 3) —
  reproduces and prevents the exact live incident this session hit against
  `docs/qa/BOB-109/*.json`.
- XIII (Host-Session Safety): closed by the `ExecutionPolicy` entity (data-model.md) —
  explicit `nice_level`, `ionice_class`, `max_parallel_items`, and
  `resource_ceiling_pct` fields read from one single-source-of-truth location.

No new violations were introduced by the Phase 1 design. Ready for `/speckit-tasks`.

## Project Structure

### Documentation (this feature)

```text
specs/003-zero-shortcomings-audit/
├── spec.md              # Feature specification
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md         # Phase 1 output
├── quickstart.md         # Phase 1 output
├── contracts/
│   └── cli.md            # Phase 1 output — the orchestrator's own CLI contract
├── tasks.md              # Task breakdown (/speckit.superspec.tasks output)
└── checklists/
    └── requirements.md    # Already generated by /speckit-specify
```

### Source Code (repository root)

```text
scripts/
├── zero_shortcomings_audit.sh        # NEW — the single orchestrating entry point
├── lib/
│   └── audit_ledger_parser.sh        # NEW — parses docs/QA_DISCOVERY_LEDGER.md's schema
├── pre_build_verification.sh          # MODIFIED — one new non-blocking enumeration
│                                       # invariant added (FR-009's recurring wiring)
└── (existing workable-items / gate_ledger tooling — consumed, not modified)

tests/
└── audit/
    └── test_zero_shortcomings_audit.sh # NEW — bash test harness: golden-good/golden-bad
                                          # fixture ledgers, paired §1.1 mutations,
                                          # the evidence-corruption-guard reproduction

docs/
├── qa/
│   └── zero_shortcomings_audit/
│       └── <run-id>.log               # NEW — one append-only run record per invocation
└── QA_DISCOVERY_LEDGER.md             # EXISTING — read-only input, never auto-edited
                                          # by this tool (closing an escape entry stays
                                          # a human/agent edit, per its own established
                                          # convention)
```

**Structure Decision**: This is a cross-cutting audit/process tool, not a new service —
it lives entirely under `scripts/` + `tests/audit/` + `docs/qa/`, exactly where every
other project-level script and its evidence already live (Principle VII). No new
top-level directory, no new container, no new `docker-compose.yml` entry. The tool
CONSUMES the two existing enumeration mechanisms (workable-items CLI, gate-ledger
scanner) via their existing CLI surfaces rather than re-implementing them — the only new
parsing logic is for the coverage-escape ledger, which today has a well-defined
Markdown schema (see `docs/QA_DISCOVERY_LEDGER.md`'s own "## Schema" section) but no
existing automated reader.

## Execution Strategy

### TDD Requirements

- [x] `scripts/lib/audit_ledger_parser.sh`: strict RED-first, because a parsing defect
      here (a false-negative that misses an open escape entry, or a false-positive that
      reports a closed one as open) is precisely the "bluff" class this whole feature
      exists to eliminate — the parser needs golden-good and golden-bad fixture ledgers
      before any real ledger is ever read.
- [x] The evidence-corruption guard (FR-008): strict RED-first, reproducing the EXACT
      live incident this session already hit (a diagnostic test run overwriting
      `docs/qa/BOB-109/*.json` with fresh, less-favorable live-system output) as the RED
      case, then the guard as the fix that makes it GREEN.
- [x] The independent re-verification harness (FR-004/006/013): RED-first against a
      seeded item whose recorded evidence is deliberately stale/wrong, confirming the
      harness reopens it rather than trusting the stored claim.

### Parallel Execution Opportunities

- [x] Building the ledger parser (`scripts/lib/audit_ledger_parser.sh`) and building the
      evidence-corruption guard are independent — no shared files, dispatch in parallel.
- [x] Once both exist, the per-item closure work Story 2 unblocks is itself
      highly parallel across items that touch disjoint files — exactly the subagent
      dispatch pattern already established and proven this session (see this session's
      own BOB-187/159/196/223/097/175 dispatch batch as the working precedent),
      serialized only where two items would touch the same file (FR-011).
- [x] Wiring the new pre-build invariant (FR-009) can proceed independently of the
      per-item closure backlog, once the orchestrator's enumeration mode (read-only,
      non-blocking) is stable — it does not need to wait for every item to be closed
      first.

### Human Checkpoints

1. After the orchestrator's enumeration mode is built — verify its three-surface count
   against each surface's own independent query (spec Story 1's own acceptance bar)
   before trusting it to drive any closure work.
2. After the evidence-corruption guard is built — verify it against the real BOB-109
   incident class before it is relied on for any other item's closure.
3. After each batch of item closures — verify behavior matches the item's own
   acceptance criteria via independent re-run (never trust the closing agent's own
   report alone — this session's own established discipline).
4. Before wiring the new pre-build invariant as BLOCKING (as opposed to advisory) —
   confirm it does not introduce a new false-positive refusal class per §11.4.201(1),
   since this project's own constitution treats a false-positive refusal as equally
   severe to the gap it closes.
5. Before merge — final review against this spec's six Success Criteria.

### Review Gates

- [x] `scripts/lib/audit_ledger_parser.sh` (the coverage-escape schema reader): review
      before it is trusted as an enumeration source, since a parsing defect here is
      silent and hard to notice later.
- [x] The evidence-corruption guard: review before integration, since it runs on every
      future closure and a defect in it could itself corrupt evidence.
- [x] The new `scripts/pre_build_verification.sh` invariant: review before it is
      switched from advisory to blocking, per Human Checkpoint 4 above.

## Complexity Tracking

*No entries — Constitution Check produced no violations requiring justification.*
