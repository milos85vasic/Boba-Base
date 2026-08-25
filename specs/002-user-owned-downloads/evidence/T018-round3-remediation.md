# T018 round 3 — the re-review's five new findings, remediated

**Revision:** 1
**Last modified:** 2026-08-23T13:10:00Z

Round 2 closed all six original findings and returned the T018 substantive
verdict PASS, but raised five new ones. Dispositions below.

## IMPORTANT-3 — the guard was wired; the WIRING was unguarded. CLOSED.

The reviewer's RM-5 mutation deleted all four call sites in `start.sh` while
leaving both function definitions intact — and `test_credential_store_mode.sh`
stayed at 18/18, `test_start_reload_recreate.sh` at 11/11. A function nothing
calls enforces nothing (§11.4.196(F) configured-vs-in-use). This is the original
IMPORTANT-1 recurring one layer up.

Added wiring assertions to `tests/unit/test_credential_store_mode.sh`: each
function must be DEFINED exactly once and INVOKED at least twice (both start
paths), with a control needle — if the definition is not found the scan is BLIND
and a zero call-count proves nothing.

**Proof it bites** — RM-5 reproduced verbatim against the real `start.sh`:

| | unmutated | RM-5 (4 call sites deleted, definitions intact) |
|---|---|---|
| wiring assertions | PASS, "invoked 2 times" | **FAIL ×2, "invoked only 0 time(s)"** |
| suite | 24 passed / 0 failed | 22 passed / **2 failed** |

Restored byte-identical (sha verified), residue scan clean.

### It took three attempts, and both wrong versions are worth recording

The first helper used `grep -c … || echo 0`. `grep -c` PRINTS "0" *and* EXITS 1 on
no-match, so the fallback appended a SECOND line: the variable held `"0\n0"`, the
arithmetic comparison did not evaluate as intended, and the guard fell through to
its else branch — **reporting "invoked 0" and PASSING**. A guard that states the
right number and returns the wrong verdict.

The second dropped the fallback. Under this file's `set -euo pipefail` the
no-match exit-1 then ABORTED the script sixteen lines early, so the wiring block
never ran and produced **no verdict at all** — which my `grep 'wiring|RESULT'`
reported as silence, and which I nearly read as "the mutation was caught".

`|| true` is the correct form: grep still prints its count, only the STATUS is
neutralised. Both failures are §11.4.201 shapes — one a wrong verdict, one an
absent one — inside a guard written to catch a §11.4.196(F) gap.

## MINOR-4 — FR-015 semantics. CLOSED.

The assert tested `(mode & 0177) != 0`, which includes OWNER-EXECUTE. Reproduced:

| mode | old verdict | non-owner bits | correct? |
|---|---|---|---|
| 700 | **REFUSE** | 000 | no — false-positive refusal (§11.4.201(1)) |
| 500 | **REFUSE** | 000 | no — and 500 is *less* permissive than 600 in write |
| 2600 | **passes** | 000, setgid set | no — a special bit is a real widening |
| 640 / 666 | REFUSE | 040 / 066 | yes |
| 600 / 400 | passes | 000 | yes |

The refusal message also *stated* "mode 700 — more permissive than 600", which is
false. And `scripts/ownership_repair.sh:689` already strips setuid/setgid on the
explicit reasoning that "FR-015 is about the semantics … not the octal" — two
implementations of one requirement disagreeing.

Now: refuse iff `(mode & 0077) != 0` (any non-owner access) **or**
`(mode & 06000) != 0` (setuid/setgid; sticky is inert on a file, matching the
repair's own `8#1777` mask). The message names which condition tripped, and the
refusal now prints a remediation path (§11.4.234(D)), which its sibling
`run_ownership_precondition` already did and this one did not.

Four RED cases added first and observed failing (700 refused, 500 refused, 2600
passed silently, no remediation path), then GREEN.

### Five pre-existing needles broke — reconciled, not weakened (§11.4.120)

Five tests asserted the OLD message wording and went exit-code-correct /
needle-mismatched. Re-sealed on the new wording, which is strictly MORE specific
(it names which principal gained what). Discriminator run: mutating the refusal so
it stops naming the reason → **3 tests fail**; restored → 24/24. The reconciled
needles still bite.

## MINOR-5 — a false invariant in a security comment. CLOSED.

`harden_config_permissions`'s header claimed "Nothing here can grant access that
did not already exist." Measured false: a 400 store comes out 600, granting
owner-write. Materially harmless — the owner can chmod anyway — but an inaccurate
claim in a security-invariant comment is the very defect class this feature exists
to close. Corrected to state the exception explicitly and narrow the guarantee to
what actually holds: no NON-OWNER principal gains anything.

## MINOR-6 — and the reviewer's count was low. CLOSED.

Reported as one section comment disagreeing with its own `echo`. A systematic
pairing audit found **two**: line 1507 said 40 vs echo 41, line 1627 said 33 vs
echo 45. Both fixed; re-audit reports 0 remaining. A count is a lead, the lines
are the finding — the same correction the BOB-168 reviewer accepted against its
own off-by-one.

Caveat on my own instrument, stated because it matters: the audit script's summary
line printed "0 audited" while it was fixing 2, an f-string escaping bug in the
tally that did not affect the detection loop. The fix is verified by the
re-audit's independent zero, not by that tally.

## NIT-2 — BOB-150's stale title: addressed if its literals matched; otherwise
recorded as not-fixed rather than claimed.

## Still owed

T042 — the full gate — remains owed and un-run; the tree is not quiescent. The
invariant count is now **50**, not 49, since `CM-EXPORT-CHARSET-VALID` was wired
in the same window.

## Round 3 review → round 4: MINOR-7 and NIT-3

**MINOR-7 — CLOSED, and the finding was correct against me.** My wiring guard
counted call sites `>= 2` ANYWHERE in the file and reported the result as
*"both start paths covered"*. Those are different claims, and the reviewer proved
the gap with a fixture holding both calls inside `--recreate` and none on the
default path: the guard PASSED while a plain `./start.sh` had no credential-store
assertion at all. A message asserting something the check never measured is
§11.4.6 — the same class as the IMPORTANT-2 this feature already fixed once.

Rewritten to resolve the two DISPATCH REGIONS and require a call in EACH, anchored
on the condition TEXT (`if [[ "$recreate_flag" == true ]]; then` … matching `fi`)
rather than line numbers — `main()` has been restructured in each of the last two
rounds, which is exactly how a partial drop happens.

Both directions proven, on the real `start.sh`:

| mutation | result |
|---|---|
| unmutated | 25/25; region resolved 1202-1211; each function 1 call per path |
| delete DEFAULT-path calls, keep `--recreate` (the reviewer's fixture) | **23 passed / 2 FAILED** — "never called on the DEFAULT ./start.sh path" |
| delete `--recreate` calls, keep default | **23 passed / 2 FAILED** — "never called on the --recreate path" |

Restored byte-identical (sha verified); sibling `test_start_reload_recreate.sh`
still 11/11.

**NIT-3 — CLOSED, after I first made it worse.** The MINOR-5 correction had been
APPENDED while the false sentences were left standing, so the block still opened
with *"this function only ever REMOVES permission bits"* and closed with
*"Nothing here grants that did not already exist"* — the unqualified form of the
very sentence the correction identifies as false.

My first attempt patched the opening line in place and left a dangling `# bits.`
fragment mid-sentence — patching around a problem instead of rewriting it, which
is how the residue arose in the first place. Rewritten as a whole block, now
stating separately WHAT HOLDS (no group/other principal gains access; that is what
FR-015 asks) and WHAT DOES NOT (it does not only remove bits; a 400 store comes
out 600, granting owner-write). No unqualified absolute remains.

The reviewer's semantic endorsement of MINOR-4 is worth recording because it is
stronger than the argument I made: the strict-octal counter-reading **collapses on
its own terms** — it would refuse 700 as `> 600` yet must accept 500 as `< 600`,
while 500 is precisely what the old mask refused. Strict-octal was never the
stricter option, only a differently wrong one. And the decisive ground is
intra-feature consistency: `ownership_repair.sh:689` states this reading in writing
and implements it, so two implementations of one requirement now agree where they
previously contradicted each other.

Noted, not disputed: 700/500/100 now pass SILENTLY where they previously refused
loudly. Nothing is granted to a non-owner so it is not a relaxation, and the
success line prints the actual mode, so an anomalous 700 stays visible.
