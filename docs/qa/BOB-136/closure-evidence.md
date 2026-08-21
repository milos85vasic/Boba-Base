# BOB-136 — closure evidence

**Item:** Closure seam does not bind: 4 tracker rows found stale in one sweep,
and `workable-items diff` is blind to body_md drift
**Type:** Task · **Closed:** 2026-08-21 · **HEAD at capture:** 57e20c0

Every acceptance clause below was verified by INVOCATION, not by reading source
or usage text (§11.4.226 — a runtime-layer claim needs runtime-class evidence).

## (a) The flagless `diff` no longer returns a clean verdict without reading Markdown

    $ workable-items diff --db docs/workable_items.db
    exit=1
    diff: at least one of --issues / --fixed is required — refusing to report a
    DB-vs-Markdown verdict without reading any Markdown (pass --db-only to run
    just the DB-internal integrity checks)

The explicit escape says what it did NOT do, rather than implying a comparison:

    $ workable-items diff --db docs/workable_items.db --db-only
    diff: DB-internal checks passed — 164 item(s) inspected; no Markdown compared (--db-only)

CONTROL NEEDLE (§11.4.201(7)(b)) — the refusal above is only evidence if the
binary still works on the same DB when given the flags. It does:

    $ workable-items diff --db docs/workable_items.db --issues docs/Issues.md --fixed docs/Fixed.md
    diff: DB and Markdown are in sync (compared 164 Markdown item(s) against 164 DB item(s);
    read docs/Issues.md, docs/Fixed.md)

Without that third line the exit=1 above would be indistinguishable from a
broken binary refusing everything.

## (b) No caller uses the flagless form

    CHECK B flagless-diff callers ..... PASS (0 callers of the false-null form)

## (c) A sweep flags non-terminal rows whose id appears in a merged commit

Wired as pre-build invariant 49, verified at three layers:

- SOURCE   — `pre_build_verification.sh:1818` invokes the gate script
- ARTIFACT — the driver advertises 49/49 (was 48 before this wiring)
- RUNTIME  — the gate executes:

      structural commit<->item links .. 220
      control needle (§11.4.201(7)(b)) . PASS (4/4 known links seen)
      CHECK A closure seam .............. PASS (0 stale rows, 0 untracked ids)

The needle matters for the same reason as in (a): CHECK A's zero is only
meaningful because the instrument was proven able to see 4/4 known links
through the same path. A blind sweep and a clean repo both report zero.

## The two blockers the body's last Progress line named are drained

That line read: *"20 stale rows and 2 untracked ids remain to drain, and the
gate is not wired into pre_build_verification.sh"*. All three conditions are
now false. `N_UNTRK > 0` fails the gate (check_cm_closure_seam_binds.sh:617),
so CHECK A PASS entails untracked ids are zero as well as stale rows — a fact
the PASS message did not previously state, and which misled a reader of this
very closure before it was corrected to report both counts.

## Honest boundary (§11.4.6) — what this does NOT claim

The seam only sees work that DECLARES its id in a commit message. A fix landing
under a message naming no item stays invisible to it. That is BOB-136's own
second defect, and acceptance clause (d) scoped it out explicitly: *"this does
not claim to prevent all drift."* Closing this item does not close that gap.

## Reproduce

    bash scripts/pre_build/check_cm_closure_seam_binds.sh
    bash tests/pre_build/test_check_cm_closure_seam_binds.sh    # 30/30
