# BOB-207 — follow-up items, drafted and ready to file

**Revision:** 1
**Last modified:** 2026-08-27T00:00:00Z

## Why these are drafted rather than filed

§11.4.202 requires a reported item to land in the SQLite SSoT **and** drive the
derived documents back into sync (`docs/Issues.md`, `docs/Issues_Summary.md`).
`docs/workable_items.db`, `docs/Issues.md` and `docs/Issues_Summary.md` all
carry uncommitted modifications from prior work, three work streams are live in
this checkout, and this stream is under a no-commit/no-stage constraint — so it
cannot complete the DB→docs regeneration cycle. Filing the DB row alone would
leave the tracker internally divergent, which §11.4.186 gates against.

Highest allocated id at drafting time: **BOB-225**. Ids below are placeholders
to be assigned at filing.

---

## ITEM 1 — repair-side walk over foreign-owned INTERIOR directories is untested

**Type:** Task · **Status:** Queued · **Severity:** medium
**Layer:** integration (the unprivileged-harness constraint does not bind there)

**WHAT.** `tests/unit/test_ownership_repair.sh` seeds the foreign uid onto
**files and symlinks only**; interior directories stay operator-owned. Case 22
seeds a foreign declared **root** (`seed_wrong -D`), but only on the *failure*
path — a shimmed `chown` that must fail — so no case walks a tree whose
**interior** directories carry a foreign uid and succeeds.

**WHY IT MATTERS.** Production first-start repair faces exactly that shape:
research.md R6 measured the download root and `config/` with foreign-owned
directories throughout. The repair must chown those directories, and on a
directory the kernel does **not** clear `S_ISGID` on `chown(2)` (see ITEM 2),
so directory repair has behaviour that file repair does not.

**NOT ALREADY COVERED.** `tests/ownership/test_container_writes_owned_files.py::`
`test_container_written_directory_is_owned_by_the_operator` covers the
**creation** side (FR-002) — a container writing a directory. It does not
exercise the **repair** walk over a pre-existing foreign-owned directory tree.
The DECLARED GAPS bullet in the unit suite has been tightened so it can no
longer be read as claiming repair-side coverage.

**WHY UNIT-LEVEL IS THE WRONG HOME.** Seeding interior directories foreign
would leave the harness unable to create the symlinks Cases 8/9/18 add *after*
seeding — an operator cannot write into a directory they no longer own. The
integration layer has no such constraint.

**ACCEPTANCE.** An integration test seeds a tree with foreign-owned interior
directories, runs `scripts/ownership_repair.sh` to completion, and asserts
every directory ends operator-owned, with a paired §1.1 mutation that makes it
fail.

**FR refs:** FR-002, FR-004, FR-012 · **Discovery channel (§11.4.238):**
independent code review of the BOB-207 re-base, not the automated regime.

---

## ITEM 2 — directory `setgid` is silently dropped by the mode-restore mask

**Type:** Bug · **Status:** Queued · **Severity:** medium

**WHAT.** `scripts/ownership_repair.sh:892-893` masks the restored mode with
`8#1777`. Its in-source rationale is that the kernel clears `S_ISUID`/`S_ISGID`
on `chown(2)`, so the high bits cannot be restored anyway. That holds for
**files**. It does **not** hold for **directories**: Linux does not clear
`S_ISGID` on a directory `chown(2)`, and on a directory `S_ISGID` means group
inheritance for newly created children. A foreign-owned `2755` directory
repaired through that path therefore loses its inheritance bit, silently.

**PRE-EXISTING, NOT INTRODUCED.** Byte-identical at HEAD
`a3e1141777914f3d71d62a6cd32a4c79c7f43842`; outside the BOB-207 change.

**BOB-207 SHRINKS THE HAZARD.** With the walk narrowed to uid, a setgid
directory the operator **already owns** is never selected, so it is never
chowned and never mode-restored. The exposure is now limited to directories
that are *both* foreign-owned *and* setgid — the ITEM 1 shape.

**ACCEPTANCE.** Decide (operator, §11.4.66) whether directory setgid must
survive repair. If yes: preserve `S_ISGID` for directories, with a test that
fails against the current mask. If no: record the decision in-source so the
next reader does not re-derive the question.

**FR refs:** FR-015, FR-005 · **Related:** ITEM 1 (same directory shape).
