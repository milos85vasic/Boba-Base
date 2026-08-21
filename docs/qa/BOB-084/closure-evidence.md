# BOB-084 closure evidence

**Item:** BOB-084 (RD2-17) — Reconcile BOB-008 DB/MD body drift via the workable-items tool
**Type:** Task · **Closed as:** Completed (→ Fixed.md) per §11.4.33
**Closed:** 2026-08-21

## Acceptance criterion (from the item's own body_md)

> "Reconcile BOB-008 DB/MD body drift (RD2-04) via the workable-items tool."

RD2-04's own evidence line, from `docs/GOVERNANCE_AUDIT_2026-08-08_ROUND2.md`:

    ~ BOB-008 body differs (md=703 bytes db=576 bytes)

## Verdict: ALREADY SATISFIED — the drift was reconciled at 443e938, via the tool

The work landed under a commit whose message did not carry the ATM id, so the row
was never reconciled — the same drift class recorded for BOB-076 / BOB-091 / BOB-117.
`443e938  docs(governance): Session 15 sync — audit round 2, BOB-008 fix, Track 11, doc exports`
states it verbatim in its own body:

> "docs/Issues.md + docs/workable_items.db: BOB-008 DB<->MD body drift fixed
>  via `workable-items sync md-to-db`"

That names the engine, which is what the acceptance criterion requires.

## Verification — re-derived independently, not inherited from the commit message

### 1. RED — the exact RD2-04 finding reproduces at the commit it was filed against (§11.4.199)

Same instrument, same flags, materialising `54e313f`'s tracked DB + Markdown into a temp tree:

    $ workable-items diff --db db.sqlite --issues Issues.md --fixed Fixed.md
    ~ BOB-008 body differs (md=703 bytes db=576 bytes)
    diff: 1 difference(s) (compared 63 Markdown item(s) against 63 DB item(s); read Issues.md, Fixed.md)

Byte-for-byte the audit's line. The defect was real and the instrument sees it.

### 2. GREEN — the same command at HEAD

    $ workable-items diff --db docs/workable_items.db --issues docs/Issues.md --fixed docs/Fixed.md
    diff: DB and Markdown are in sync (compared 157 Markdown item(s) against 157 DB item(s); read docs/Issues.md, docs/Fixed.md)

The verdict names the two files it read — the BOB-155 fix. The flagless form was never
used as evidence here; it opens zero Markdown files and its clean verdict is worthless.

### 3. The reconciliation commit, located by bisecting the instrument over history

Every commit touching the tracker between `54e313f` and `3eaf39a` was materialised and
re-measured. `54e313f` drifted; `443e938` is the first commit that reads clean at the
same 63-item count:

    54e313f  ~ BOB-008 body differs (md=703 db=576)     <- RD2-04 filed here
    443e938  in sync (63 vs 63)                          <- reconciled here, via sync md-to-db

### 4. Per-item byte comparison at HEAD — not just the aggregate verdict

    BOB-008 DB body_md : 1334 bytes  sha256 146aee858776599c
    BOB-008 Issues.md  : 1333 bytes  sha256 9f1119e30cd212ee
    normalised diff (trailing blank lines stripped both sides): IDENTICAL

The one-byte delta is the section's trailing newline, which the extractor includes and
the column does not. Control needle on the same extractor against a deliberately
different item returned a difference, so the "identical" reading is not a blind zero
(§11.4.201(7)(b)).

### 5. The clean verdict is not a FALSE-NULL — the oracle is proven able to see BOB-008 drift

`workable-items diff` is structurally blind to body-only drift (that blindness is BOB-136).
The independent re-parse oracle in `scripts/hooks/docs-sync-commit-seam.sh` is not, and its
§11.4.107(10) self-test happens to pick BOB-008 as its golden-bad victim — the first Issues
item by id with a body over 40 bytes. So the needle is seeded into *this very item*:

    $ bash scripts/hooks/docs-sync-commit-seam.sh --self-test
    golden-good     PASS  (clean tree reproduces tracked DB; oracle does not false-fire)
    golden-bad      PASS  (seeded body drift DETECTED and named: BOB-008)
    self-test PASS — oracle validated in both polarities

An instrument that detects seeded drift in BOB-008 and then reports none is reporting
absence of drift, not absence of sight.

### 6. Standing checks at HEAD

    $ workable-items validate --db docs/workable_items.db
    validate: OK — 157 items, all invariants satisfied

    $ bash scripts/hooks/docs-sync-commit-seam.sh --files docs/Issues.md docs/Fixed.md docs/workable_items.db
    CHECK 1 workable-items validate ......... PASS
    CHECK 2 workable-items diff ............. PASS
    CHECK 3 body_md drift oracle ............ PASS

## Honest boundary (§11.4.6)

This closes the one-time reconciliation only. The *mechanical prevention* of the class is
BOB-087's scope, which remains open on its third seam — see `docs/qa/BOB-087/`.
