# BOB-166 — fix design notes (scoping only, nothing implemented)

Captured 2026-08-21 while the defect was fresh. This is a SCOPE for whoever
takes the item, not a patch. Everything below is read from source; nothing
was changed.

## Where the hole is

`constitution/scripts/workable-items/cmd/workable-items/mutate.go`

    main.go:123      case "update":  runUpdate(args[1:])
    mutate.go:69     func runUpdate(...)
    mutate.go:152    if set["status"] {
    mutate.go:153        ns := normalizeStatus(*status)
    mutate.go:154        // normalizeStatus never returns a non-closed-set value, but guard
    mutate.go:155        // explicitly so a typo'd --status surfaces rather than silently
    mutate.go:156        // mapping to Queued. ...
    mutate.go:158        cur.Status = ns
    mutate.go:159    }

The validation asks exactly one question — *is this a legal §11.4.15 value?* —
and a terminal status IS legal. Nothing asks the second question: *is this
status legal FOR THIS ROW'S LOCATION?* So `Fixed (→ Fixed.md)` is accepted on a
row whose `current_location` is still `Issues`, producing the state §11.4.19
forbids.

## The sibling that already gets this right

`move` documents precisely the invariant `update` lacks (mutate.go:18-21):

    - move — the general REVERSE-OF-CLOSE relocation ... with an optional new
             status ... Refuses any destination/status pair that would create
             an INTEG-03 desync.

So the codebase already has the CONCEPT (a destination/status pair can be
invalid) and a name for the failure (INTEG-03 desync). `update` simply never
consults it. That matters for the fix: this is reusing an existing invariant
at a seam that skipped it, NOT inventing a new rule (§11.4.227 — an anchor's
done state is its SEAM landing, not its text landing).

## Shape of the fix

1. In `runUpdate`, after `ns := normalizeStatus(*status)`, refuse when `ns` is
   terminal AND the resulting location would be `Issues`. The message must name
   the correct path rather than just saying no:

       update: refusing to set terminal status "Fixed (→ Fixed.md)" on BOB-NNN
       while it is located in Issues — a terminal status without the migration
       leaves the row in the OPEN tracker (§11.4.19 requires the move to be
       atomic). Use instead:
         workable-items close BOB-NNN --db <p> --status fixed --evidence <path>
       or, if the row is genuinely already closed elsewhere:
         workable-items move --id BOB-NNN --db <p> --to Fixed --why <text>

   Naming both paths matters: `close` is right for a NEW closure (it demands
   evidence), `move` for reconciling an already-closed row.

2. Extend `validate` with a status↔location coherence invariant so the EXISTING
   ten rows are caught, not just future writes. A guard on the write seam alone
   leaves the current corpus silently wrong — the §11.4.146(D3) full-table-sweep
   argument: a diff-only check misses rows written before the guard existed, and
   raw-SQL writers bypass the CLI entirely.

## Test-first obligations (§11.4.224)

- RED before the guard: a test that performs the exact reproduction
  (`update --status 'Fixed (→ Fixed.md)'` on a Queued row in Issues) and asserts
  the resulting row is NOT in the forbidden state. It must FAIL on today's code —
  verify that, do not assume it.
- Paired §1.1 mutation: remove the refusal; the test must go red. A guard never
  observed failing is unvalidated instrumentation (§11.4.115(F)).
- NEGATIVE CONTROL, non-negotiable (§11.4.201(1)): `update --status` on a
  NON-terminal value must still work, and a terminal status on a row ALREADY in
  `Fixed` must still work — otherwise the guard becomes a false-positive refusal
  that blocks legitimate edits, which is a FAIL-bluff of equal severity to the
  hole it closes.

## Constraint that is easy to miss

This code lives in the CONSTITUTION submodule and is consumed by other projects
(§11.4.28). The fix must carry NO boba literal — no `BOB-` prefix, no
`docs/Issues.md` path. It is a statement about the engine's own closed-set
semantics, which is what makes it safe to land there. Per §11.4.26 the submodule
must be fetched and pulled BEFORE editing, and pushed to all its upstreams after.

## Evidence already captured

- `evidence_absence_measurement_20260821.log` — all ten rows have ZERO evidence
  rows, control-needled against two rows closed via `close` (1 each). Splits the
  drain into two classes: BOB-087/BOB-129 have unrecorded artifacts on disk;
  eight have nothing.
