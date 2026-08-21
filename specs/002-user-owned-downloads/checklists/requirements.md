# Specification Quality Checklist: Downloads Owned by the Person Who Started the System

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-08-21
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

- Items marked incomplete require spec updates before `/speckit-clarify` or `/speckit-plan`

### Validation iteration 1 — 2026-08-21

**Two [NEEDS CLARIFICATION] markers remain** (under the 3 limit). Both are genuine
operator decisions with no reasonable default, and both were retained deliberately
rather than guessed:

1. Whether the one-time ownership repair runs automatically or only on explicit
   invocation. This changes ownership of existing data, so an automatic default is a
   destructive-by-surprise risk on a large library. Scope + data-safety impact.
2. Whether the system refuses to start or warns when configured storage cannot produce
   operator-owned files. Refusing guarantees the operator never receives unmanageable
   content but can block startup on a removable volume.

Both are surfaced as questions to the operator rather than resolved here.

**Content-quality note.** The spec deliberately avoids naming the specific platform
mechanism that would implement FR-001/FR-002, even though investigation identified a
concrete candidate. Naming it would be an implementation detail leaking into the
specification, and it would also foreclose the alternative route recorded under
Dependencies. The *evidence* (a distinct mapped identity owning created files) is
stated because it is an observed fact about current behaviour, not a design choice.

**Framing note — this is the load-bearing content of the spec.** The operator's
request asserted a causal link ("run under session-scoped services SO downloads are
manipulable") that the gathered evidence does not support: the system already runs
under the operator's own account, and lifecycle management does not determine file
ownership. The spec keeps the operator's requested mechanism as User Story 3 (it has
independent value) while making the reported defect P1 so it is not blocked behind a
lifecycle change. This was recorded rather than quietly reinterpreted.


### Validation iteration 2 — 2026-08-21 (post-clarification)

**ALL ITEMS PASS.** Both markers resolved by operator decision:

1. One-time repair trigger → **automatic on first start** (FR-004). The spec had
   RECOMMENDED explicit invocation; the operator chose automatic. That choice is
   recorded as theirs, and FR-004a (run once, not every start) plus FR-004b (record
   what changed BEFORE changing it) were added so the accepted risk stays
   recoverable. The recommendation is preserved in Assumptions rather than deleted,
   so a future reader sees the trade-off that was weighed.
2. Unusable storage → **refuse to start, naming the location** (FR-010), with
   FR-010a (name it and say what was wrong) and FR-010b (assert the REAL condition —
   that a file created there is actually operator-owned — not a proxy for it; a
   check that passes because it never wrote anything is a false pass).

Mechanically re-verified rather than eyeballed:
- `NEEDS CLARIFICATION` markers: **0**
- Tech nouns inside the Success Criteria section (lines 175-196 pre-edit): **0**.
  `systemctl` appears only in the template-required verbatim Input quote and in
  Problem Framing where it names the operator's proposed mechanism; `uid` appears
  only in Problem Framing as observed evidence and in Assumptions defining "current
  user". None leaks into requirements or success criteria.
- Leftover template placeholders: **0**, needle-checked (the detection pattern
  returns 1 against a synthetic `[FEATURE NAME]`, so the zero is real and not a
  blind scan).
- Raw `$ARGUMENTS` tokens: **0**.
- All four mandatory sections present.

Ready for `/speckit-plan`.

### Validation iteration 3 — 2026-08-21 (post-`/speckit-clarify`)

**16/16 → 16/16 items passing. No state changes; no regressions.** Four clarifying
questions were asked and integrated; the spec became more complete, not less.

Re-evaluated rather than assumed, with the two items most at risk from the scope
widening checked explicitly:

- **"Scope is clearly bounded"** — still passes. Scope WIDENED (FR-012: container-written
  project paths, not only downloads) but remains explicitly bounded: the in-scope
  definition is stated on the entity, and the Out of Scope section survives and was
  itself corrected rather than left contradicting the new scope.
- **"No implementation details"** — passes. A framework/language scan initially
  reported 7 hits, which would have failed this item. All 7 were the substring `gin`
  inside "chan**gin**g" and "lo**gin**" — carriers, not instances. Zero real framework
  nouns. Recorded because the detection pattern fell into exactly the substring trap
  it was written to catch, and a reader re-running that scan will see the same 7.
- **"Success criteria are technology-agnostic"** — passes, verified by scanning the
  Success Criteria section in isolation: 0 technology nouns inside it. The `uid` and
  `systemctl` mentions elsewhere are observed evidence in Problem Framing and the
  template-required verbatim Input quote.
- **"No [NEEDS CLARIFICATION] markers remain"** — 0.

Contradiction scan: 0 obsolete statements. Q4 invalidated two earlier statements (the
Out of Scope line and the matching Assumption, both of which had placed "internal
state the operator never handles directly" out of scope). Both were REPLACED rather
than supplemented, so no contradictory text survives — verified by scanning for the
superseded wording and finding 0 occurrences.

Structure: exactly 4 `- Q:` bullets under one `### Session 2026-08-21`, matching the
4 questions asked; 0 duplicates; the only new headings are `## Clarifications` and
that session subheading.

**The material finding of this session** was not a wording gap. Checking whether the
scope question was real surfaced that `config/boba.db` is mode 600 under an owner
that does not resolve — so the backup procedure `docs/BOBA_DATABASE.md` §3 instructs
the operator to perform, and whose omission that same document warns means total
credential loss, is currently IMPOSSIBLE to perform. The spec had placed that file
out of scope. That is now FR-012/FR-013 and SC-007.
