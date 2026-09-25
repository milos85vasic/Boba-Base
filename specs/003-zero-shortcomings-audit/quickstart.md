# Quickstart: Zero-Shortcomings Evidence-Backed Audit & Closure

This validates the feature end-to-end using the project's real state — no mocked
surfaces. See [`contracts/cli.md`](./contracts/cli.md) for the full command reference and
[`data-model.md`](./data-model.md) for the entities referenced below.

## Prerequisites

- A working checkout of this repository with `docs/workable_items.db` present and
  `constitution/` initialized as a submodule (already true for any normal clone).
- `sqlite3` on `PATH` (already a project dependency).
- No live container stack required for `enumerate` or `standing-check` mode — both are
  pure reads against tracked files. `verify-closure` may require a live stack only for
  items whose own evidence command needs one (the tool does not itself start or stop
  containers).

## Step 1 — Prove Story 1 (complete, verifiable enumeration)

```bash
scripts/zero_shortcomings_audit.sh enumerate
```

**Expected outcome**: A report with three sections (backlog / gates / escapes), each
with a count and a list of ids. Cross-check each count against its own ground truth,
per the spec's own Story 1 acceptance bar:

```bash
# Ground truth 1 — backlog
constitution/scripts/workable-items/workable-items validate --db docs/workable_items.db
sqlite3 docs/workable_items.db "SELECT count(*) FROM items WHERE status NOT LIKE '%(→ Fixed.md)' AND status != 'Obsolete';"

# Ground truth 2 — gate ledger
bash constitution/scripts/gates/cm_gate_ledger_ratchet.sh

# Ground truth 3 — coverage-escape ledger (manual spot-check)
grep -c '^### ' docs/QA_DISCOVERY_LEDGER.md
grep -c '\*\*new-check:\*\*' docs/QA_DISCOVERY_LEDGER.md
```

The enumerate report's three counts MUST exactly match these three ground-truth
queries' results. A mismatch in either direction (the tool over-counting or
under-counting) fails Story 1's independent test and must be treated as a defect in the
tool itself before any closure work proceeds on its output.

## Step 2 — Prove Story 2 (evidence-backed closure, independently reproducible)

Pick any item this feature has closed (or, for a first dry run, seed a throwaway test
item):

```bash
scripts/zero_shortcomings_audit.sh verify-closure BOB-<id>
```

**Expected outcome (genuine closure)**: exit `0`, reporting the re-run's result matches
the recorded `ClosureEvidenceArtifact`.

**Expected outcome (deliberately corrupted evidence — the negative control)**: hand-edit
one closed item's stored `result_summary` in its evidence file to a plausible-but-wrong
value, then re-run `verify-closure` against it:

```bash
scripts/zero_shortcomings_audit.sh verify-closure BOB-<id> --reopen-on-mismatch
```

**Expected outcome**: exit `1`, and — with `--reopen-on-mismatch` — the item is
reopened in the tracker (confirm via `workable-items validate`, which will now show the
item back in a non-terminal state). This is the FR-013 negative control: a bluff
closure MUST be caught and reversed, never silently trusted.

## Step 3 — Prove Story 2's evidence-corruption guard (FR-008)

Reproduce the real incident this feature's design is modeled on (research.md §5):

1. Note the current content hash of an UNRELATED item's evidence file, e.g.
   `sha256sum docs/qa/BOB-159/closure_evidence_20260925.md`.
2. Run a `verify-closure` (or any closure-verification dispatch) for a DIFFERENT item
   whose command is known (for test purposes) to have a side effect that touches that
   unrelated file.
3. **Expected outcome**: the orchestrator detects the change to the unrelated tracked
   file, reverts it (`git status` shows it clean again, hash matches step 1), and the
   incident appears in the run's `AuditRunRecord.corruption_incidents` list in
   `docs/qa/zero_shortcomings_audit/<run-id>.log`.

## Step 4 — Prove Story 3 (the standing mechanism is durable, not a one-time snapshot)

```bash
scripts/pre_build_verification.sh
```

**Expected outcome**: the new invariant's `standing-check` stage appears in the output,
runs `scripts/zero_shortcomings_audit.sh standing-check` internally, and reports the
current surface counts — without anyone having to separately remember to run the audit.

Then, the deliberate-regression negative control:

```bash
# Deliberately name one new, real, unimplemented governance gate in a scratch doc
# (do NOT commit this — it's a throwaway verification step)
echo "CM-SCRATCH-VERIFICATION-ONLY is a named gate with no implementation" >> /tmp/scratch_doc.md
```

Re-run `scripts/pre_build_verification.sh` and confirm the standing-check stage's
reported `gates_unimplemented` count has NOT changed (since the scratch doc above is
outside the gate-ledger scanner's real scan paths) — this confirms the mechanism reports
only genuinely-tracked findings, not an over-broad grep. Clean up the scratch file
afterward; it was never meant to be tracked.

## Success criteria cross-check

Once Steps 1–4 all produce their expected outcomes, this feature satisfies the spec's
own Success Criteria SC-001 through SC-006 for the surfaces and items exercised in this
quickstart. Full-backlog closure (all 41 items) is the ongoing Story 2 work this plan's
`tasks.md` breaks down — this quickstart proves the MECHANISM works, not that every
item is yet closed.
