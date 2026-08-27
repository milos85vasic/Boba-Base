# T028 — Round-4 remediation: the round-3 MINOR and four NITs

**Revision:** 1
**Last modified:** 2026-08-26T15:16:37Z

Author: `(T11/002-user-owned-downloads - milos85vasic - ? - xhigh)`, responding to
`evidence/T028-review-ROUND3.md` (NO-GO — 0 BLOCKING / 0 IMPORTANT / 1 MINOR / 4 NIT).
Every load-bearing number below was **re-measured in this session**; the reviewer's
figures were read but never taken on trust (§11.4.6). Artifact identities after this
round: `lib/ownership.sh 43aad4b6850e958c`, `test_ownership_repair.sh f4d8de37b31ec1f8`,
`ownership_precondition.sh 6308d9e6eaa74f56`; `ownership_repair.sh ae025b74602414ca` and
`config/owned_paths.yaml 26375798edfee773` **UNTOUCHED** (unchanged since round 2).

Probe discipline: every destructive probe ran `--dry-run` against FIXTURE scopes via
`--scope`/`OWNED_PATHS_FILE`, `--state-dir` in scratch; only the sanctioned suites
mutated anything, inside their own mktemp sandboxes. The real `config/owned_paths.yaml`,
the live `logs/ownership/` and the operator's library were never written —
`logs/ownership/repair-marker.json` was **read only**. `nice -n 19`; no `.venv`; no
process-group signals (§11.4.263). `docs/workable_items.db` was **not edited** — only
`SELECT`ed; its working-tree delta is the operator's pre-existing BOB-201 filing
(HEAD has 0 rows for BOB-201, the worktree 1; file mtime 16:56, before this round's
first query).

---

## RED → GREEN (§11.4.224(A)/§11.4.115 — fixtures authored and observed failing FIRST)

| run | suite result | what it proves |
|---|---|---|
| baseline (round 3, as reviewed) | 124 / 0 / 0 | starting point |
| **RED** — both new fixtures added, no fix yet | **129 / 17 / 0** | 16 unresolved-spelling + 1 tracker-citation assertions fail; both golden-FALSE guards already PASS |
| **GREEN** — after the parser rule + the re-pointed citation | **146 / 0 / 0** | 22 net-new assertions, all green |

The first RED run failed Case 24 with the **wrong** diagnosis ("no such item exists")
because my `sqlite3` call was over-escaped and returned empty — a §11.4.201(6)
false-null in my own instrument. It was fixed and re-measured before being accepted as
a RED; the corrected run names the real defect ("that item's body never mentions
symlinks"). The blind read is recorded rather than quietly repaired.

---

## R3-M1 (MINOR) — the dangling `BOB-159` citation

**Independently reproduced** (control-needled): BOB-159's body is 4758 chars with **0**
occurrences of `symlink`/`intermediate`; the same query path sees **30** hits for
`warm|repair` through that body (needle) and **0** for a nonsense string (negative
control). The reviewer's finding is exact.

* The in-source clause now cites **BOB-201**, the item that actually records the static
  intermediate-symlink reach, and states in one sentence what round 3 got wrong and why
  it mattered (§11.4.214).
* **Case 24 no longer pins a string.** It reads the cited id *out of* the fence and asks
  the tracker two separate questions — does the item EXIST, and does its body actually
  record this reach — with three honest outcomes rather than two: a **blind** read
  (`sqlite3` absent, DB absent, or zero rows) is a **SKIP**, never a pass and never a
  fail (§11.4.201(1)/§11.4.3).

Paired mutations against the strengthened check (post-fix tree, copies only):

| mutation | result |
|---|---|
| re-point the citation to `BOB-159` — **the exact round-3 defect** | **FAIL** — "cites BOB-159, but that item's body never mentions symlinks" |
| cite `BOB-99999` (no such item) | **FAIL** — distinct diagnosis, "no such item exists in the tracker" |
| remove the tracker DB entirely | **SKIP** — "unjudged rather than approved" (no false pass, no false fail) |

The first row is the point: **this check would have caught R3-M1.**

---

## R3-N1 (NIT) — nested `${A:-${B}}`, and the reviewer's proposed fix was not sufficient

Reproduced first (control-needled against a well-formed `${VAR:-default}` through the
same path): both unset → literal row `…/${BOBA_R4_B}/leaf`; `A` set → corrupted row
`…//tmp/x}/leaf`.

**The suggested remediation — "refuse a parsed path that still contains `${`" — closes
only half of it.** Case (a) contains `${`; case (b) resolves to `…/tmp/x}`, which
contains no `${` at all and would have sailed through. Measured, not reasoned about.

The rule shipped instead judges the **declared spelling** on two decidable conditions:

1. any matched default text that itself contains `${` (the nesting), and
2. any `${` the grammar could not consume at all, found in the residue `VAR_RE.sub("", raw)`
   (`${}`, `${1}`, an unterminated `${VAR`).

Because it reads only `raw` — the tracked scope file — it can never reach into a
variable's *value*, and because only an unconsumed **opener** counts, a literal `}` in a
directory name is untouched. Both are pinned as golden-FALSE fixtures. The refusal is
**identical whether or not `A` is set**, which is the correct invariant: a malformed
declaration is malformed regardless of the environment.

It lands in the existing `vanished` list, so it inherits whole-run refusal, exit 2, no
stdout rows, no marker, and — the motivating case — `optional: true` is not an escape.

| mutation | result |
|---|---|
| disable only the new rule (`if False:`) | **16 assertions die**, both golden-FALSE still pass — the rule is load-bearing |
| make it **over**-refuse (any `}` in the residue) | **golden-FALSE CATCHES it**: "exit 2, 7 item(s) still wrongly owned — the rule judged a brace CHARACTER instead of the interpolation (§11.4.201(1))" |

The second row is why the golden-FALSE half is not decoration: the rule is pinned from
both sides.

---

## R3-N2 (NIT) — the `set -e` mechanism the evidence asserted

Re-measured on `GNU bash 5.2.37(1)-release` **independently** of the reviewer:
mid-sequence `[[ -n "" ]] && rm …; echo next` **survives** (rc 0, `next` printed);
the `while`-body-tail variant **survives**; only a **function-tail** occurrence kills
(rc 1). Both shipped guard sites are mid-sequence (`:1041` is followed by
`cannot_run`, `:1044` by the next `if`), so neither was ever fatal.

`T028-round3-remediation.md` now carries a **CORRECTION block** with that measurement
table. The finding is **not withdrawn** — the shapes are real and the `{ …; } || :`
guards stay, because they state the intent and remain safe if a later edit moves either
statement into a tail position, which *is* the fatal shape. What was wrong was an
asserted mechanism stated as fact without measurement, and it is recorded as such.

---

## R3-N3 (NIT) — the deny comment's causal attribution

Re-measured every degenerate value myself:

| value | computed | outcome |
|---|---|---|
| `HOME` unset / `HOME=` / `HOME=/` | `/.local/share/containers` (3 components) | **KEPT** — a harmless narrow phantom |
| `XDG_DATA_HOME=/` | `/containers` (1 component) | **DISCARDED by the depth floor** |
| relative `HOME` or `XDG_DATA_HOME` | — | **DISCARDED by the `== /*` guard**, a *different* branch |

The comment blamed an unset `HOME` for the depth-floor discard. It now names both
guards separately and states which value reaches which — including that an ordinary
root like `/data/Downloads` is still accepted under those same degenerate values.
Comment only; the behaviour was correct throughout and never broadens.

---

## R3-N4 (NIT) — a value emitted while refusing, and a hash drift the naive fix would have added

Reproduced with a proven-seeing instrument (a good scope yields a real fingerprint
through the same path): a refused scope returned **rc 2** while printing
`e3b0c44298fc1c14…`, the sha256 of the empty string.

The three-line shape the review suggested introduces a defect of its own, which I found
by measuring rather than assuming: command substitution strips trailing newlines, so
re-adding one unconditionally hashes `"\n"` instead of `""` for a scope that parses to
**zero rows** — and `paths: []` returns **rc 0**, so that path is reachable. The shipped
version branches on empty and is **byte-identical to the pipe it replaces for every
input**:

| scope | old pipe | new function |
|---|---|---|
| `paths: []` | `e3b0c442…` | `e3b0c442…` |
| one entry | `3e693746…` | `3e693746…` |
| three entries | `2a156afb…` | `2a156afb…` |
| **live shipped scope** | `c41619d2…` | `c41619d2…` |

and the live value equals the fingerprint inside
`logs/ownership/repair-marker.json`, which was written on 2026-08-25 by the **old**
code — so no completion marker silently re-arms.

---

## Ordering violation — addendum only (still OPEN, still not mine to close)

The 20:52:21 journal line was re-read this round; its truncated clause is real:
`…; marker logs/ownership/repair-marker.json`. The marker itself (read-only) records
`items_changed 0`, `record_file null` and a `scope_fingerprint` that **still equals
what the current shipped scope computes today** — so the six-location scope is latched
"done" and *remains* latched, which is stronger than "as of that run". Added to the
**same** `tasks.md` record (`grep -c T028` = 1, box still `- [ ] T028`) per §11.4.214.
Round 1's 51-items-vs-0-discovered contradiction stays **UNKNOWN**; nothing here
settled it.

---

## Do-not-regress — reproduced in this session

```
tests/unit/test_ownership_repair.sh         RESULT: 146 passed, 0 failed, 0 skipped   (was 124/0/0 + 22 new)
tests/unit/test_ownership_precondition.sh   RESULT: 29 passed, 0 failed, 0 skipped
  incl. negative control: all 6 SHIPPED entries ACCEPT under three QBITTORRENT_DATA_DIR values
check_cm_ownership_invariants.sh            PASS, exit 0
check_cm_no_production_mutation_residue.sh  scanned 272 file(s); 0 hit(s); 1 audited waiver(s); exit 0
bash -n  lib/ownership.sh, ownership_precondition.sh, ownership_repair.sh, suite   all clean
ownership_repair.sh     ae025b74602414ca   UNTOUCHED
config/owned_paths.yaml 26375798edfee773   UNTOUCHED
shipped-scope control needle (live env, read-only): 6 rows, RC=0
REVERT KILL-MATRIX (current suite vs PRE-fix lib b1b4e7ce217c8635, byte-verified scratch tree):
  100 passed, 46 failed  — the reviewer's 30 plus this round's 16 new; both golden-FALSE
  fixtures PASS on BOTH revisions, so they are false-positive guards, not fix-agreeing assertions
```

Docs (§11.4.18/§11.4.44/§11.4.65): `ownership_repair.md` Revision 4→5 gains a
"grammar is exactly two forms" section with the refusal message and both golden-FALSE
carve-outs; `ownership_precondition.md` Revision 4→5 adds the new cause to its exit-2
enumeration; `.html`/`.pdf` twins regenerated for both. No other doc was touched by
this round's export runs (verified by mtime).

## Not closed, and not claimed closed

Unchanged from round 3 and still honestly open: the `podman unshare` fallback is never
exercised against a real subuid-owned item; `CONTAINER_RUNTIME` is an unvalidated
command name at that site; `BATCH_SIZE=256` scale behaviour is cold; a
`storage.conf`-relocated graphroot is outside the deny's reach; **the ordering
violation itself**; and BOB-201's resolve-or-accept decision is operator-owned (§11.4.66).
