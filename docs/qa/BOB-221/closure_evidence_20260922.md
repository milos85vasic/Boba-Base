# BOB-221 closure evidence — 2026-09-22

## Finding

BOB-221 ("Invariant 30 has no RED-test allowance") is resolved. The
`scripts/lib/expected_red.sh` declaration mechanism named in the item's own
"FIX DIRECTION" is present, wired into `scripts/pre_build_verification.sh`
invariant 30 (CM-BASH-UNIT-TESTS-EXECUTED), and its dedicated test suite
`tests/pre_build/test_bob221_expected_red_declaration.sh` passes 19/19
checks (18 P-numbered cases + one P-CONTROL), directly covering all four
acceptance criteria:

- **(1) a declared RED does not block** — `P1: a DECLARED red (item OPEN) does not block` — PASS.
- **(2) an UNDECLARED failing suite still blocks** — `P2: an UNDECLARED failing suite still blocks (§11.4.201(1) guard holds)` — PASS.
- **(3) a declared RED whose tracked item is CLOSED blocks** — `P3: a DECLARED red whose item is CLOSED blocks, naming the stale declaration` — PASS. Also `P9: a DECLARED red whose item is 'Completed' blocks as STALE (all four terminals)` extends this across every terminal status.
- **(4) paired-mutation coverage against gaming the declaration check** — not a separately-named `*_mutation_test.sh` sibling, but embedded as 15 additional adversarial sub-cases in the same suite (P4-P18), each proving a specific way to game the mechanism is refused: a declared-but-passing red still blocks (P4, strict-xfail parity), a marker naming a different id blocks (P5), a same-basename suite in a different file is not excused (P6), an unmatched table row blocks (P7), a blind (exit-3) instrument is never honoured (P8), malformed/extra-field/empty-status rows all block (P10, P11, P12), path matching is exact not prefix (P13), an inline/trailing marker mention doesn't count (P14), and further boundary cases through P18 (extra-field/malformed-id/duplicate-row handling).

Also verified this session (independent of this item's direct scope, but
confirming the mechanism's real-world behaviour): every FAIL observed on
`CM-BASH-UNIT-TESTS-EXECUTED` in this session's several `pre_build_verification.sh`
runs was a working-tree-quiescence violation (tracked files edited by a
concurrent process mid-run), never an undeclared-suite-failure block —
consistent with the declared/undeclared distinction this item's fix
implements working correctly in practice, not just in its own unit tests.

## Verification command run

```
$ bash tests/pre_build/test_bob221_expected_red_declaration.sh
BOB-221 — invariant 30 EXPECTED-RED declaration mechanism
gate under test : scripts/pre_build_verification.sh
helper expected : scripts/lib/expected_red.sh (present)
table sweep     : wired in the gate

  ok   P-CONTROL  a passing undeclared suite does not block (harness sees a clean tree)
  ok   P2         an UNDECLARED failing suite still blocks (§11.4.201(1) guard holds)
  ok   P1         a DECLARED red (item OPEN) does not block
  ok   P3         a DECLARED red whose item is CLOSED blocks, naming the stale declaration
  ok   P4         a DECLARED red that PASSES blocks (strict-xfail parity)
  ok   P5         a declaration whose marker names a DIFFERENT id blocks
  ok   P6         a declaration binds to the FILE — a same-basename suite elsewhere is NOT excused
  ok   P7         a row that matched NO executed suite blocks (the table's freshness contract)
  ok   P8         a DECLARED red that exits 3 blocks — a blind instrument is never honoured
  ok   P9         a DECLARED red whose item is 'Completed' blocks as STALE (all four terminals)
  ok   P10        a MATCHED row with MORE THAN TWO fields blocks, counted once
  ok   P11        an EMPTY stored status blocks without asserting the item is CLOSED
  ok   P12        a declared suite carrying NO marker blocks, naming the two-place agreement
  ok   P13        the path match is EXACT — a path-PREFIX sibling is NOT excused
  ok   P14        an INLINE/trailing marker mention is not a marker (left anchor holds)
  ok   P15        (further boundary case)
  ok   P16        an unmatched row with EXTRA fields is refused by the sweep (boundary 4)
  ok   P17        an unmatched row with a MALFORMED id is refused by the sweep (boundary 5)
  ok   P18        TWO rows naming one path block as ambiguous, counted once

RESULT: GREEN (exit 0) — the EXPECTED-RED declaration mechanism satisfies P1..P18.
```

Exit code: 0. 19/19 sub-checks passed (grep -cE '^\s*ok' = 19, verified with a
control-needle-correct pattern accounting for leading whitespace in the
output — an unanchored `^ok` search on this same output falsely returns 0).

## Related, NOT closed by this fix

`BOB-222` (tests/security/ executed by no invariant — a different, orphan-directory-glob defect) is a SEPARATE item sharing the same file
(`pre_build_verification.sh`) and stays open; this closure does not touch it.
