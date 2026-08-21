# Contract: Ownership Startup Precondition

**Feature**: 002-user-owned-downloads · **Implements**: FR-010, FR-010a, FR-010b
**Artifact**: `scripts/ownership_precondition.sh`

## Purpose

Refuse to start when a configured location cannot produce operator-owned files, so the
operator never receives content they cannot manage. Fail-closed by operator decision
(clarify session, 2026-08-21): starting with a warning was explicitly rejected because a
missed warning silently reproduces the defect this feature exists to remove.

## Invocation

```bash
scripts/ownership_precondition.sh [--scope <path-to-owned_paths.yaml>] [--quiet]
```

Defaults resolve from the project root. No stdin. Read-only apart from one probe file per
declared location, which it creates and removes.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | every declared location can produce operator-owned files |
| `1` | at least one location cannot — startup MUST NOT proceed |
| `2` | the check could not run (scope file missing/unparseable, no interpreter) |

`2` is NOT a pass. A check that cannot run has asserted nothing, and reporting that as
success is the §11.4.201(6) blind-instrument failure.

## The probe (FR-010b — the load-bearing rule)

For each declared location the check MUST:

1. create a real file in that location,
2. read back its owner uid,
3. compare against the operator's uid,
4. remove the probe file.

It MUST NOT infer ownership from the parent directory, from configuration, or from the
absence of an error. **A probe that passes because it never wrote anything is a false
pass** — that is the exact defect class this project has hit repeatedly, and the reason
this rule is stated as a contract rather than left to implementation taste.

## Output on refusal (FR-010a)

Must name the location and what was wrong with it:

```
OWNERSHIP-PRECONDITION: FAIL
  - /run/media/.../Downloads: probe file created but owned by uid 100999, expected 1000
  - config/boba.db: not readable by the operator (mode 600, owner does not resolve)
Startup refused. Fix the location(s) above, or run scripts/ownership_repair.sh.
```

Never a bare "precondition failed" — the operator must be able to act without further
diagnosis.

## Both directions (§11.4.201(1))

A guard that refuses a healthy system is as broken as one that passes a broken one. The
paired test MUST include:

- **golden-bad**: a location that produces non-operator-owned files → exit `1`
- **golden-good**: a location that produces operator-owned files → exit `0`
- **negative control**: an `optional: true` location that is simply absent → exit `0`,
  NOT a refusal

## Wiring

Runs in `start.sh` **before** any service that writes to an in-scope location. Its
non-zero exit blocks startup.
