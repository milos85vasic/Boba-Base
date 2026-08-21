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

**AMENDED 2026-08-21 (finding X1, operator-approved option C).** The first version of this
contract said only "create a real file in that location". Implementing it exposed that the
instruction was underspecified in the way that matters: it never said WHOSE write to probe.

A host-side probe run as the operator creates an operator-owned file and reports `ok` —
even for the download root, which is owned by uid 100999 and still contains 100999-owned
items. Measured during Phase 1: `probe_location` returned `ok` for exactly that directory.
The defect this feature exists to fix is that **container** writes land at 100999, so a
host-side probe answers a different question than FR-010 asks. That is a PROXY standing in
for the real condition — §11.4.201 — inside the check written to prevent proxies.

The check MUST therefore report on TWO distinct probes, and MUST NOT let either speak for
the other:

**P1 — container-write probe (the real condition).** Run a throwaway container that writes
into the declared location as the service's configured user, then read the resulting owner
back from the host and compare against the operator's uid. This reproduces the failing
path exactly (research.md R1 does the same thing) and is the only probe that can observe
the defect.

**P2 — host-write probe (necessary, not sufficient).** Create a file in the location as the
operator, read its owner back, remove it. Proves the location is writable and on a
filesystem that carries ownership at all. A P2 failure is decisive on its own; a P2 pass
proves only that the operator can write there.

**Reporting rules — each probe speaks only for itself:**

- P1 fails ⇒ **refuse**. This is the condition FR-010 names.
- P2 fails ⇒ **refuse**. The location is unusable regardless of P1.
- P1 unavailable (no container runtime) ⇒ the check MUST report an honest
  `runtime_unavailable` SKIP for P1 (§11.4.3), fall back to asserting the per-service
  ownership route declared in `docker-compose.yml`, and state plainly that a route
  assertion verifies CONFIGURATION, not BEHAVIOUR. It MUST NOT report the fallback as
  though the real condition had been checked.
- Both pass ⇒ `ok`.

**Never** infer ownership from the parent directory, from configuration alone, or from the
absence of an error. **A probe that passes because it never wrote anything is a false
pass** — that is the exact defect class this project has hit repeatedly, and the reason
this rule is stated as a contract rather than left to implementation taste.

**Declared FILES** (e.g. the credential store) have no write to probe: reading the target's
own owner IS the real condition there, not a proxy for it.

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
