# T028 — Round-5 remediation: the two round-4 NITs, closed by execution

**Revision:** 1
**Last modified:** 2026-08-26T18:30:00Z
**Author:** `(T11/002-user-owned-downloads - milos85vasic - ? - xhigh)` — the AUTHOR
of this round, structurally separate from the reviewer who will re-review it
(§11.4.240 producer ≠ verifier).
**Reviewed input:** `evidence/T028-review-ROUND4.md` — NO-GO, 0 BLOCKING / 0
IMPORTANT / 0 MINOR / **2 NIT**.

Scope of this round, deliberately minimal per the round-4 verdict ("one minimal
iteration — one sentence + one small loop — closes the loop"): **R4-N1** (a guide
sentence contradicted by measurement) and **R4-N2** (Case 24 judged only the first
citation). Nothing else was reworked. `scripts/ownership_repair.sh`,
`config/owned_paths.yaml`, `scripts/lib/ownership.sh` and
`scripts/ownership_precondition.sh` are **byte-identical to the round-4 reviewed
state** — verified below.

## Artifact identities (sha256 first-16, measured this round)

| artifact | before | after | note |
|---|---|---|---|
| `tests/unit/test_ownership_repair.sh` | `f4d8de37b31ec1f8` | **`52b59c9efa40af3e`** | R4-N2 fix |
| `docs/scripts/ownership_repair.md` | `da367390046cd906` | **`fc65c69107c021a8`** | R4-N1 fix, Revision 5 → 6 |
| `scripts/lib/ownership.sh` | `43aad4b6850e958c` | `43aad4b6850e958c` | **UNCHANGED** |
| `scripts/ownership_precondition.sh` | `6308d9e6eaa74f56` | `6308d9e6eaa74f56` | **UNCHANGED** |
| `scripts/ownership_repair.sh` | `ae025b74602414ca` | `ae025b74602414ca` | **UNTOUCHED** |
| `config/owned_paths.yaml` | `26375798edfee773` | `26375798edfee773` | **UNTOUCHED** |
| `docs/workable_items.db` | `2d8f186f48ea8257` | `2d8f186f48ea8257` | read-only |
| `logs/ownership/repair-marker.json` | `00d4bd3dfa427ab3` | `00d4bd3dfa427ab3` | read-only |

Probe discipline: every destructive probe ran `--dry-run` against FIXTURE scopes via
`--scope`, `--state-dir` in scratch. Every mutation ran against a **byte-verified
scratch copy** built by `mkscratch.sh`, which copies the six files the suite reads and
**asserts each copy's sha matches the source** before use. `nice -n 19`; no `.venv`;
`pre_build_verification.sh` NOT run (T042 owns it); sibling-stream files untouched and
undiffed; the real scope file, live state dir, marker and the operator's library were
never written.

---

## 1 — Control needle before any RED (§11.4.201(7)(b))

A RED is only evidence if the harness can see. The clean scratch tree was run FIRST:

```
RESULT: 146 passed, 0 failed, 0 skipped     rc=0
```

Identical to the live baseline, so the scratch harness is faithful and a
difference observed in it is a real difference, not an artifact of the copy.

## 2 — R4-N2: Case 24 judged only the FIRST citation

### RED — the current `head -1` version PASSES a second dangling citation

Mutation **M-F** (the round-4 reviewer's, re-applied by me): a plausible future edit
adding a SECOND residual-reach clause whose id is dangling, appended AFTER the real
BOB-201 citation. Applied by count-asserted Python replace, then byte-verified:

```
[byte-verify] citations=2 (was 1)   new-present=1 (want 1)
```

Run against the **round-4 suite** (`f4d8de37b31ec1f8`):

```
PASS: fence boundary [R2-N1]: the residual reach is linked to BOB-201, which EXISTS
      and really records the symlink reach (§11.4.197/§11.4.214)
RESULT: 146 passed, 0 failed, 0 skipped     rc=0
```

**That is the RED.** The check built in round 4 to catch dangling citations reports
full coverage while a dangling `BOB-159` sits two lines below the real one, unasked.

### The fix

`head -1` → `sort -u` + a loop over **every distinct** citation, and the content probe
tightened from `symlink` alone to **both** `symlink` AND `intermediate`. One
**aggregate** verdict is emitted regardless of how many ids are cited, so the suite's
assertion count does not drift with the fence's prose (it stays 146). Verdict order is
**FAIL > SKIP > PASS**: a proven dangling citation is a defect whether or not some
other id read blind, and a blind read anywhere forbids a PASS because approving on a
quiet nothing is the §11.4.201(6) false-null.

### GREEN — the same mutation, the fixed suite

```
FAIL: fence boundary [R2-N1]: the fence's citation(s) BOB-159(exists, but its body
      never says: symlink intermediate) — a citation that does not resolve to an item
      recording THIS reach looks like coverage and is none, so no tracker query can
      find the defect (§11.4.214)
RESULT: 145 passed, 1 failed, 0 skipped     rc=1
```

**M-F killed.** Clean control on the same fixed suite: `146 passed, 0 failed, 0 skipped`.

### The content tightening is load-bearing, not decoration (M-R5-1, mine, novel)

Round 4's probe was anchored by LUCK, not by construction: measured on this tracker,
BOB-201 is the **only** symlink-mentioning item (1 of 200 rows), so ANY
symlink-mentioning item satisfied a message claiming the item "really records the
symlink reach". I built the fixture that exposes it — a decoy item mentioning
`symlink` incidentally and never `intermediate` — and pointed the citation at it:

| suite | verdict |
|---|---|
| **round-4** (`symlink` only) | **PASS 146/0/0** — "linked to BOB-88888 … really records the symlink reach" |
| **round-5** (both tokens) | **FAIL 145/1/0** — "BOB-88888(exists, but its body never says: intermediate)" |

Both halves of R4-N2 therefore carry a RED→GREEN flip, not just the `head -1` half.

**Why two independent whole-body greps and not an adjacency regex** (§11.4.201(1)): an
adjacency pattern requires same-line co-occurrence, so a future re-wording naming
"symlink" in the title and "intermediate" three paragraphs down would be REFUSED while
genuinely recording the reach. Both-tokens is strictly stronger than round 4's probe,
robust to word order and line breaks, and is exactly the discriminator the round-3
forensic used (BOB-159 carries **zero** occurrences of each; BOB-201 carries both, its
title reading "intermediate symlink components"). It remains a **PROXY** — it asserts
both concepts are present, never that the prose is correct (§11.4.6).

### Properties round 4 earned — all re-verified on the FIXED suite

| attack | verdict | diagnosis |
|---|---|---|
| re-point → `BOB-159` (the round-3 defect) | **FAIL** 145/1/0 | "exists, but its body never says: symlink intermediate" |
| re-point → `BOB-99999` (no such item) | **FAIL** 145/1/0 | "no such item exists in the tracker" — **distinct** |
| tracker DB absent | **SKIP** 145/0/1 | "…is absent — the tracker cannot be read here, so the citations are unjudged rather than approved" |
| DB `chmod 000` | **SKIP** 145/0/1 | "no rows at all — treating this as a BLIND read, not as absence" |
| DB replaced with garbage bytes | **SKIP** 145/0/1 | same blind-read route |
| `items` table renamed (schema change) | **SKIP** 145/0/1 | same blind-read route |
| **golden-FALSE**: a SECOND, *correctly-pointed* citation | **PASS** 146/0/0 | the loop does not over-refuse |

Every blind state routes to a **counted, printed SKIP** — never a green, never a fail.
The two failure diagnoses remain distinct. The golden-FALSE row is the §11.4.201(1)
guard on my own new loop: adding a citation is not, by itself, a finding.

### Honest boundary on the new code (§11.4.6, measured not assumed)

The per-id **blind-body** branch is defensive and **not data-reachable** on this
schema. Measured: an item whose title AND description are both empty yields a body of
`" "` (length 1, non-empty), so it routes to the token check and FAILs correctly
rather than skipping. That branch fires only if a per-id query fails while the
whole-table control needle succeeded. Recorded as insurance, not as covered ground.

## 3 — R4-N1: the guide sentence, corrected against measurement

I reproduced the behaviour myself rather than inherit the claim. Fixture scopes,
`--dry-run`, scratch state dir, `BOBA_R5_A` unset:

| declared path | optional | result |
|---|---|---|
| `…/$BOBA_R5_A/leaf` (bare `$`) | `true` | `absent, declared optional — skipped`, **exit 0** |
| `…/$BOBA_R5_A/leaf` (bare `$`) | `false` | `declared path does not exist and is not optional`, exit 1 |
| `…/${BOBA_R5_A}/leaf` (braced) | `true` | **refused, exit 2** — the shipped rule |
| `…/$RECYCLE.BIN/dl` on a REAL directory of that name | `false` | **`0/0 items need repair`, exit 0** |

So the guide's "**Those two forms are the whole grammar**, and a spelling outside it is
refused" was false as written: a bare `$NAME` is neither expanded nor refused.

**The fix is the sentence, not the code, and the reviewer's reasoning is confirmed by
my own measurement**: the last row above is a real, working configuration today — a
Windows-formatted download disk carries a literal `$RECYCLE.BIN`. Refusing a bare `$`
would be a §11.4.201(1) false-positive refusal against a live config, which this
project treats as exactly as serious as a false pass. The false-refusal surface is
measurably **non-empty**, so the "measure it and show it empty" bar for a code change
is not met — and cannot be.

Guide edits (`docs/scripts/ownership_repair.md`, Revision 5 → 6):

1. Heading: "The grammar is exactly two forms — anything else is refused" →
   "**Two interpolation forms are supported — any other `${…}` spelling is refused**".
2. Body: "the whole grammar" → "the whole of what is **interpolated**", and "a
   spelling outside it" → "any *other* `${…}` spelling".
3. Two new paragraphs stating the measured behaviour: a bare `$NAME` is a literal path
   component, its `optional: true` exit-0 skip (with the literal printed, so it is
   visible), the practical reading ("read a bare `$` as a typo for `${…}` unless you
   really mean a `$`-named directory"), and why refusing it in code would be wrong,
   citing the measured `$RECYCLE.BIN` case.

No stale references to the renamed heading exist anywhere in `docs/scripts/*.md`,
`lib/ownership.sh`, `ownership_repair.sh` or `ownership_precondition.sh` (grep: none).
`.html` / `.pdf` / `.docx` twins regenerated for this one file only — the project-wide
generator was deliberately NOT run, because its sweep would have regenerated
sibling-stream twins this round is forbidden to touch. Twins verified fresh
(mtime ≥ `.md`), charset declared (the BOB-169 guard), new content present in all
three, and the PDF text layer clean (22 correct `§`, **0** mojibake markers).

## 4 — Instrument incidents, recorded rather than repaired silently

**(a) A malformed probe scope misread `optional`.** My first R4-N1 probe used a scope
file carrying only `path` and `optional`, and the run reported "does not exist and is
**not optional**" — the opposite of the finding under test. I did not report that
number. Re-measured with a faithful scope file (the shipped shape: `schema_version`
plus `path`/`kind`/`optional`/`preserve_mode`/`recursive`) it reproduces the reviewer's
result exactly. The discriminator was isolated: a **non-empty `kind`**.

**(b) My own reasoning was wrong and the measurement corrected it.** I asserted that
bash `read` with a non-whitespace `IFS` preserves empty fields. Measured:

```
$ printf 'P\t\t1\t0\t1\n' | while IFS=$'\t' read -r a b c d e; do echo "kind=[$b] opt=[$c]"; done
kind=[1] opt=[0]
```

It does **not**. Consecutive tabs collapse, every field shifts left, and the row's
`optional` is read from `preserve_mode`'s slot. This is why (a) happened, and it is a
reminder that a "that's how the shell works" claim is a §11.4.6 guess until run.

## 5 — NEW out-of-band observation — NOT filed, NOT closed, operator-owned

The isolation in §4 surfaced something that is **not** in this round's remit and that I
have deliberately **not** acted on. Recorded here so it is not lost (§11.4.6/§11.4.238):

> A scope entry that omits `kind` produces the parser row `<path>\t\t1\t0\t1`
> (`ownership_scope_entries` — `kind` defaults to `""` at `lib/ownership.sh:263`
> via `e.get("kind", "")`, so nothing refuses it). The consumer at
> `ownership_repair.sh:493` reads it with `while IFS=$'\t' read -r e_path e_kind
> e_opt e_pres e_rec`, which collapses the empty field — so `optional` is read
> from `preserve_mode`'s value and `recursive` comes back empty. Reproduced: an
> entry with `optional: true` but no `kind` is treated as **non-optional**.

Bounds, stated honestly: **not reachable from the shipped scope** — all six shipped
entries declare `kind` (shipped-scope needle: 6 rows, RC=0, all five fields populated).
It requires a hand-written scope file omitting a field the parser silently tolerates.
I did **not** fix it: `ownership_repair.sh` must remain `ae025b74602414ca` this round,
this round's remit is two NITs, and I have not root-caused whether the right repair is
in the parser (refuse an entry without `kind`), the consumer (a `-d` / positional read
that tolerates empty fields), or the schema. **Status: UNKNOWN / unfiled.** Whether to
file it and how to resolve it is operator-owned (§11.4.66); §11.4.238 also makes it a
coverage-escape candidate, since no automated check discovered it.

## 6 — Do-not-regress — every item re-run this round, rc captured directly

```
tests/unit/test_ownership_repair.sh        RESULT: 146 passed, 0 failed, 0 skipped   rc=0
tests/unit/test_ownership_precondition.sh  RESULT: 29 passed, 0 failed, 0 skipped    rc=0
  incl. negative controls: absent optional -> exit 0 not a refusal; no refusal banner;
  all 6 SHIPPED entries ACCEPT under three QBITTORRENT_DATA_DIR values
check_cm_ownership_invariants.sh           PASS, rc=0
check_cm_no_production_mutation_residue.sh scanned 272 file(s); 0 hit(s); 1 audited waiver(s); rc=0
  (the waiver is a SIBLING stream's, not this change)
bash -n  lib/ownership.sh  ownership_precondition.sh  ownership_repair.sh  suite   all clean
shipped-scope control needle (live env, read-only): 6 rows, RC=0
ownership_repair.sh     ae025b74602414ca  UNTOUCHED
config/owned_paths.yaml 26375798edfee773  UNTOUCHED
REVERT KILL-MATRIX (fixed suite vs pre-fix lib b1b4e7ce217c8635, byte-verified):
  RESULT: 100 passed, 46 failed          <- reproduces exactly
  Families: 25 vanished-entry + 16 unresolved-spelling + 4 fence-boundary + 1 empty-scope
  9 golden-FALSE assertions PASS on the pre-fix artifact too -> false-positive guards
  The new empty-ids branch is RED-capable: the pre-fix lib carries NO citation and the
  loop FAILs it with "the documented residual reach names no tracked item"
guide: ownership_repair.md Revision 6; .html/.pdf/.docx twins regenerated, all fresh
tasks.md: grep -c T028 = 1; box still `- [ ] T028`; round-5 addendum on the SAME record
```

## 7 — Still open — untouched, unclosed, unclaimed

The ordering violation (1 record, box unchecked, no re-mint); the
51-items-vs-0-discovered contradiction still **UNKNOWN**; `podman unshare` never
exercised against a real subuid-owned item; `CONTAINER_RUNTIME` an unvalidated command
name; `BATCH_SIZE=256` cold at scale; a `storage.conf`-relocated graphroot outside the
deny's reach; BOB-201's resolve-or-accept decision operator-owned (§11.4.66); and the
new §5 observation. Nothing here closes any of them and nothing claims to.

The two mutations the round-4 reviewer graded honestly were left alone as instructed:
**M-H** (proven equivalent mutant — `sort` re-adds the trailing newline, `od`-proof)
and **M-H2** (`sort -r`; cross-version fingerprint value-stability is un-pinnable by a
self-consistent suite, and the dangerous direction is pinned by M-H3's 4 kills).

**T028's checkbox is NOT checked by this document.** Under §11.4.134 the reviewer's
zero-finding GO does that.
