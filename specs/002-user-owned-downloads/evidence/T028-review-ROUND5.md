# T028 — Round-5 independent re-review of the round-5 remediation: **GO**

**Revision:** 1
**Last modified:** 2026-08-26T16:19:23Z

Reviewer: independent agent, label `(T11/002-user-owned-downloads - milos85vasic - fable - ?)`,
structurally separate from the round-5 author (§11.4.240) and from all four prior
reviewers (§11.4.142/§11.4.194/§11.4.209/§11.4.134). Reviewed state: HEAD `a3e1141`
plus the uncommitted round-5 working-tree edits. Artifact identities verified by
this review (sha256 first-16, measured before AND after every probe):
`tests/unit/test_ownership_repair.sh 52b59c9efa40af3e` (round-5),
`docs/scripts/ownership_repair.md fc65c69107c021a8` (Revision 6),
`scripts/lib/ownership.sh 43aad4b6850e958c`, `scripts/ownership_precondition.sh
6308d9e6eaa74f56` (both UNCHANGED since round 4), `scripts/ownership_repair.sh
ae025b74602414ca` **UNTOUCHED**, `config/owned_paths.yaml 26375798edfee773`
**UNTOUCHED**. Pre-fix revision for the kill-matrix: `HEAD:scripts/lib/ownership.sh`
= `b1b4e7ce217c8635`, byte-verified before use.

**One deliberate delta from the remediation's table**: `docs/workable_items.db` is
`2812a0a89317f21a`, not the remediation's `2d8f186f48ea8257` — the conductor filed
**BOB-202** between the remediation and this review. Delta verified: HEAD blob has
198 items and neither BOB-201 nor BOB-202; the worktree has 201; the id-set diff is
exactly {BOB-200, BOB-201, BOB-202}, of which the first two were already present at
the round-4/5 measured state (200 rows) — so the remediation-to-now delta is the
BOB-202 filing alone. The DB and `logs/ownership/repair-marker.json`
(`00d4bd3dfa427ab3`) were **read-only** to this review; both shas re-verified
unchanged after the last probe.

## Verdict

**GO under §11.4.134 — 0 BLOCKING · 0 IMPORTANT · 0 MINOR · 0 NIT.** Both round-4
NITs are closed by execution and survived every attack I could construct, including
two mutations nobody had written. In one unambiguous sentence: **the dedicated
independent review of `scripts/ownership_repair.sh` that T028 names is complete with
zero findings and zero warnings, and the T028 checkbox may be checked on this
verdict** — noting, as every round has, that checking the box completes the task, it
does not and cannot un-violate the ordering violation recorded on the same record,
which stays OPEN.

Probe discipline: every destructive probe ran `--dry-run` against FIXTURE scopes via
`--scope`, `--state-dir` in scratch; every mutation ran against byte-verified scratch
copies (each copy's sha asserted against the source before every run; each restore
re-verified — one self-copy restore slip was caught by exactly that check and
corrected); the real scope file, live state dir, marker and the operator's library
were never written; `nice -n 19`; no `.venv`; `pre_build_verification.sh` NOT run
(T042 owns it); sibling-stream files neither touched nor diffed (the residue log's
waiver line was read from my own gate run's output, not from the sibling file). The
author's numbers were never inherited — every load-bearing number below is my run.

---

## 1 — PRIORITY 1: the luck-anchored-probe adjudication — **the author is right, verified from the census up**

**The census claim is exact.** Measured on the live tracker (read-only, 201 rows):
exactly ONE item mentions `symlink` (BOB-201) and exactly ONE mentions
`intermediate` (BOB-201). Round 4's single-token probe was therefore satisfiable by
ANY symlink-mentioning item and was anchored to the right one only because the
tracker happened to contain no other — coincidence, not construction. "Anchored by
LUCK" is the accurate description, and it is to the author's credit that the author
found it against its own round-4-approved surface.

**The decoy reproduces in both directions.** I built the decoy myself in a scratch
DB (BOB-88888, body mentions `symlink` once, `intermediate` zero times — token
counts byte-verified) and re-pointed the fence citation at it (count-asserted
replace, BOB-201-citation 1→0, BOB-88888-citation 0→1):

| check | verdict |
|---|---|
| round-4 semantics | **PASS** — "linked to BOB-88888, which EXISTS and really records the symlink reach" |
| round-5 suite (actual bytes) | **FAIL 145/1/0** — "BOB-88888(exists, but its body never says: intermediate)" |

**Provenance caveat, stated plainly (§11.4.6):** the round-4 suite
(`f4d8de37b31ec1f8`) exists in no git object — it was uncommitted working-tree
state. The round-4 half of both flips was verified against a RECONSTRUCTION of the
round-4 check's semantics (`grep … | head -1` extraction + `grep -qi 'symlink'`
content probe), which the round-4 review §2/§7 and the round-5 remediation §2
document identically and independently. The reconstruction passes clean on the
unmutated artifact (BOB-201), which is its control needle. The same caveat applies
to the M-F RED below. I judge the reconstruction faithful; it is not the original
bytes, and nothing stronger is available.

**M-F re-executed, both halves.** My re-application of the round-4 reviewer's
mutation (second dangling `Tracked as BOB-159` after the real citation; citations
1→2 byte-verified): round-4 semantics **PASS** (BOB-201 judged, the dangling
BOB-159 two lines below never asked — the RED); round-5 suite **FAIL 145/1/0**
naming "BOB-159(exists, but its body never says: symlink intermediate)" (the
GREEN). Clean control on the same suite: 146/0/0.

**The two-greps-vs-adjacency call is adjudicated CORRECT.** The judged body is
`title || ' ' || description` — a MULTI-LINE string (BOB-201's description spans
paragraphs), and `grep` is line-oriented, so a same-line adjacency pattern
(`intermediate.*symlink|symlink.*intermediate`) would refuse a legitimate future
re-wording that names "symlink" in the title and "intermediate" paragraphs down —
a §11.4.201(1) false refusal of an item genuinely recording the reach. Two
independent whole-body greps are strictly stronger than round 4's one-token probe,
order- and line-break-robust, and use exactly the discriminator the round-3
forensic used (BOB-159 carries zero occurrences of each token; BOB-201 carries
both). The in-code comment labels it a PROXY honestly. Right trade, rightly argued.

**The loop, attacked (every mutation byte-verified, every restore hash-verified):**

| # | attack (mine) | result |
|---|---|---|
| A1 | fence with ZERO citations (citation phrase removed, count-asserted) | **FAIL** 145/1/0 — "the documented residual reach names no tracked item" |
| A2 | DUPLICATE of the same correct citation (`Tracked as BOB-201` twice) | **PASS** 146/0/0 — `sort -u` dedupes, id list prints one `BOB-201`, no over-refusal (the golden-FALSE direction) |
| A5 | mixed: valid citation processed FIRST in loop order, dangling `BOB-999` second | **FAIL** 145/1/0 — "BOB-999(no such item exists in the tracker)", the distinct diagnosis; FAIL beats the valid id's clean read (M-F already proved the invalid-first direction) |
| B1 | tracker DB absent | **SKIP** 145/0/1, counted and printed — never a green, never a fail |
| B2 | DB replaced with garbage bytes | **SKIP** 145/0/1 — "BLIND read, not … absence (§11.4.201(7)(b))" |
| — | assertion-count drift | total is **146 in every run above** (0, 1 and 2 distinct citations) — one aggregate verdict regardless of the fence's prose, exactly as claimed |

The remaining blind states (chmod 000, schema rename) were re-verified by the
author on the fixed suite and by round 4 on the same routing code; I spot-checked
the two above and the routing is identical (one `sqlite3 2>/dev/null` needle
gate). The blind-body branch is confirmed not data-reachable by SQL semantics:
`COALESCE(NULL,'')||' '||COALESCE(NULL,'')` = `' '` (length 1), so even a
NULL-everything row routes to the token check and FAILs rather than skipping.

## 2 — PRIORITY 2: R4-N1 — **re-measured exactly; the sentence was the right fix**

All four rows of the remediation's table reproduce on this host (fixture scopes,
`--dry-run`, scratch state dirs, probe variable unset):

| declared path | optional | my result |
|---|---|---|
| `…/$BOBA_R5REV_A/leaf` (bare `$`) | true | `absent, declared optional — skipped`, **exit 0**, literal printed |
| same | false | `declared path does not exist and is not optional`, exit 1 |
| `…/${BOBA_R5REV_A}/leaf` (braced) | true | **whole-scope refusal, exit 2** — "refusing the WHOLE scope … nothing was touched" |
| `…/$RECYCLE.BIN/dl`, a REAL directory of that name, non-optional | false | **`0/0 items need repair`, exit 0** — walked normally |

The last row is the adjudication: the false-refusal surface of a bare-`$` refusal
rule is **measurably non-empty today** (a Windows-formatted disk's `$RECYCLE.BIN`
is a working configuration), so the "measure it and show it empty" bar for a code
change cannot be met, and a code refusal would be precisely the §11.4.201(1)
false-positive machine. Fixing the SENTENCE was correct.

**The guide edit verified line-by-line** (`ownership_repair.md`, Revision 6,
§11.4.44 header valid): heading now "Two interpolation forms are supported — any
other `${…}` spelling is refused"; "the whole of what is interpolated"; the new
bare-`$NAME` paragraphs state exactly the measured behaviours (exit-0 skip with
visible literal, exit-1 non-optional, the typo reading, the `$RECYCLE.BIN`
rationale). No stale "anything else is refused" anywhere in `docs/scripts/*.md`,
the lib, the repair or the precondition (grep: none). **Twins**: `.html`/`.pdf`/
`.docx` all fresh (mtimes 17:53:2x ≥ md 17:52:41) and all three carry the new
content; **no sibling twin moved in this round's window** — the sibling-stream
files' mtimes (charset 17:10, precondition-guide 17:15 = round 4's own regen,
lan_routes 17:29) all strictly predate this round's 17:52+ edits. **PDF text
layer: exactly 22 `§`, 0 mojibake** — and my mojibake detector was needle-proven
(a planted `Â§` through the same pipeline returns 1).

## 3 — PRIORITY 3: BOB-202 — **mechanism CONFIRMED, unreachability CONFIRMED, the decline was right**

**The mechanism is right, and I strengthened it.** On GNU bash 5.2.37: control
needle first (`P\tdir\t1\t0\t1` → all five fields land correctly), then the
empty-kind row `P\t\t1\t0\t1` → `kind=[1] opt=[0] pres=[1] rec=[]` — every field
after the omission shifts left, `optional` is read from `preserve_mode`'s slot.
**Counter-probe (mine):** the same shape through a NON-whitespace delimiter
(`IFS=:` on `P::1:0:1`) preserves the empty field (`kind=[]`, no shift) — so the
IFS-*whitespace* attribution in BOB-202 is the load-bearing mechanism, not an
incidental description. The filed item's WHAT/MEASURED/CONSEQUENCE text matches
the machine behaviour exactly, including the conductor's recorded first-probe
false-null (reproduced: `printf` without a trailing newline makes `read` return
non-zero at EOF, the loop body never runs, and BOTH cases print nothing — the
with-newline control needle is what catches it).

**Unreachability from the shipped scope is proven, not asserted.** All six shipped
entries declare `kind` (read from `config/owned_paths.yaml` directly, and the live
needle emits 6 fully-populated rows, RC=0). Structurally, `kind` is the ONLY
empty-able field in a parser row: `optional`/`preserve_mode`/`recursive` emit
literal `"0"`/`"1"` and an empty `e_path` row is `continue`d at
`ownership_repair.sh:494`. The defect surface is exactly the omitted/empty `kind`,
exactly as filed. `ownership_repair.sh:493` is also the only collapsing consumer:
the precondition reads whole rows and splits via `split_tsv` (readarray), and the
gate parses in Python.

**A fact that strengthens the filing (recorded for the operator decision, not a
finding):** the project already measured this exact collapse class on 2026-08-21 —
`ownership_precondition.sh:565-578` documents "TAB is an IFS *whitespace*
character, so bash collapses a RUN of tabs" with its own compose-rows forensic,
and ships `split_tsv` (`:580`, `readarray -d $'\t'`) as the consumer-layer repair.
BOB-202's acceptance criterion (1) asks which layer owns the fix; the repo
contains a working precedent for the consumer layer, in the sibling script, with
in-source rationale. Worth citing in the item when the operator takes it up; the
mechanism and bounds as filed are correct without it. If anything this sharpens
the §11.4.238 note: the class was KNOWN in-repo and recurred in a second consumer
unseen by any automated check.

**The author's decline to fix was right on all three grounds**: (a)
`ae025b74602414ca` was load-bearing for the round-4/5 do-not-regress set and for
this very filing's reachability statement — touching the repair would have voided
every cross-round number; (b) the remit was two NITs (§11.4.134 minimal
iteration); (c) the layer question is real and operator-owned (§11.4.66), the more
so given the `split_tsv` precedent. Record honestly → conductor re-measures →
files: that is the §11.4.238 flow working as designed.

## 4 — PRIORITY 4: the instrument incident — **recorded correctly; the discarded number appears nowhere as a result**

§4 of the remediation records both the malformed-scope wrong-direction probe and
the corrected IFS reasoning, with the discarded number appearing ONLY inside the
incident narrative, explicitly voided ("I did not report that number"). The only
other "not optional" in the doc is the legitimate optional-false row of §3's
table — a different, correct case. No other evidence doc cites the voided probe
(the T033 grep hits are unrelated word-senses). Confirmed both ways.

## 5 — Reviewer-authored mutations (§11.4.194(6)(d)) — all byte-verified, one incident of my own

| # | mutation | result |
|---|---|---|
| M-F (re-run) | second dangling `Tracked as BOB-159` after the real citation | **KILLED** 145/1/0 (round-5); **survives round-4 semantics** (reconstruction) — the R4-N2 flip |
| decoy (re-built) | symlink-only item cited (BOB-88888, scratch DB) | **KILLED** 145/1/0 by round-5; passes round-4 semantics — the luck adjudication |
| A1 | zero-citation fence | **KILLED** — "names no tracked item" |
| A2 | duplicate correct citation | **survives correctly** — golden-FALSE, dedup works, no over-refusal |
| A5 | valid-first + dangling `BOB-999` | **KILLED** with the distinct no-such-item diagnosis |
| **M-R5-REV-A** | **novel, nobody's: the POINTEE decays** — BOB-201's body loses every case-variant of `intermediate` in a scratch DB (byte-verified 0 left, `symlink` still 7) while the citation stays put | **KILLED** 145/1/0 — "BOB-201(exists, but its body never says: intermediate)". The check watches the ITEM, not just the pointer: tracker-side drift that re-words the item away from recording the reach is caught. No prior round tested this direction. |
| **M-R5-REV-B** | **novel, nobody's: a LOWERCASE dangling citation** `Tracked as bob-159` | **SURVIVED** 146/0/0 — the extraction is case-sensitive, adjudicated below |
| A3 | **novel: a legitimate `Tracked as BOB-202` reference far from the fence** (real item, different subject, tokens 0/0) | **FAILs loudly** 145/1/0 — adjudicated below |

**My own instrument incident, recorded not hidden:** my first M-R5-REV-A replace
missed an all-caps `INTERMEDIATE` in BOB-201's description (byte-verify:
`intermediate 3 → 1`, not 0) and the ensuing 146/0/0 was a run against an
INCOMPLETELY-mutated fixture — **voided**, the variant replaced, `0 left`
re-verified, re-run → the kill above. The byte-verify discipline the brief
mandates caught it; this is the fifth incident of the silently-partial-mutation
class this session and the discipline held every time.

**Adjudication of the two survivors (both mine, both ungraded, reasons stated):**
* **M-R5-REV-B (case-sensitivity):** a `Tracked as bob-159` is invisible to the
  extraction. This is the shape boundary of ANY lexical citation convention — the
  same file deliberately distinguishes citation (`Tracked as BOB-201`, `:637`)
  from narrative (`Round 3 cited BOB-159 here`, `:639`, bare id, correctly
  invisible), so the convention is load-bearing and modeled in-file. The surface
  is strictly narrower than the NIT just closed (it needs a future edit AND a
  case-typo against every surrounding example AND a dangling id), and widening the
  extraction to case-insensitive would still not close the class (`Tracked-as`,
  `tracked under`, … escape identically). Recorded as an instrument-shape honest
  boundary, not a defect — the round-4 precedent for exactly this category (M-H2:
  "honest boundary, recorded ungraded").
* **A3 (extraction scope):** the extraction is file-wide while the content
  requirement is fence-specific, so a hypothetical future LEGITIMATE citation of a
  different-subject item elsewhere in `lib/ownership.sh` would be refused with a
  fence-attributed message. Measured: loud, immediate, names the id and the
  missing tokens — a self-announcing false refusal at edit time, not a silent
  false pass; the current artifact carries exactly one citation (in the fence);
  and the in-file escape (bare-id narrative spelling) is already the file's own
  convention. Fence-scoping the extraction would need fragile lexical fence
  delimiters — a worse trade. Deliberate conservatism, adjudicated as correct
  design; recorded, ungraded.

M-H and M-H2 were left alone as previously adjudicated, per instruction.

## 6 — Do-not-regress: all reproduced by this review's own runs

```
tests/unit/test_ownership_repair.sh        RESULT: 146 passed, 0 failed, 0 skipped   rc=0  (live tree, my run)
  scratch control needle first: identical 146/0/0 rc=0 on the byte-verified copy
tests/unit/test_ownership_precondition.sh  RESULT: 29 passed, 0 failed, 0 skipped    rc=0
  negative controls present (5 marked lines incl. all-6-shipped-entries ACCEPT)
check_cm_ownership_invariants.sh           PASS, rc=0 (rc captured directly)
check_cm_no_production_mutation_residue.sh scanned 272 file(s); 0 hit(s); 1 audited waiver(s); rc=0
  waiver = check_cm_export_charset_valid.sh:46 — a SIBLING stream's (read from my run's log)
bash -n  lib/ownership.sh  ownership_precondition.sh  ownership_repair.sh  suite   all clean
shipped-scope control needle (live env, read-only): 6 rows, RC=0
ownership_repair.sh     ae025b74602414ca  UNTOUCHED (verified before and after)
config/owned_paths.yaml 26375798edfee773  UNTOUCHED (verified before and after)
REVERT KILL-MATRIX (round-5 suite 52b59c9e… vs pre-fix lib b1b4e7ce217c8635, byte-verified):
  RESULT: 100 passed, 46 failed — reproduces exactly.
  DISJOINT family classification (mine): 25 vanished-entry + 16 unresolved-spelling
  + 4 fence-boundary + 1 empty-scope = 46 — matches the claim exactly.
  All 9 golden-FALSE assertions PASS on the pre-fix artifact → false-positive guards.
  The new empty-ids branch is RED-capable: the pre-fix lib carries NO citation and
  the loop FAILs it with "the documented residual reach names no tracked item".
guide: ownership_repair.md Revision 6; twins .html/.pdf/.docx fresh; PDF 22 §, 0 mojibake
  (needle-proven detector); sibling twins unmoved in this round's window
tasks.md: grep -c T028 = 1; box `- [ ] T028` at review time; round-5 addendum on the SAME record
docs/workable_items.db  2812a0a89317f21a  read-only, unchanged post-review
  (differs from the remediation's 2d8f186f48ea8257 by exactly the BOB-202 filing — verified §0)
logs/ownership/repair-marker.json 00d4bd3dfa427ab3  read-only, unchanged post-review
```

## 7 — Honestly-open items — honesty confirmed, none closed, none claimed closed

Verified still stated and still open: the **ordering violation** (1 record, box
unchecked at review time, no re-mint, both real-data runs on the same record); the
**51-items-vs-0-discovered** contradiction — **UNKNOWN**, unchanged, settled by
nothing in round 5; `podman unshare` never exercised against a real subuid-owned
item (fallback at `ownership_repair.sh:377-386` region, read); `CONTAINER_RUNTIME`
an unvalidated command name (the set-but-empty honour rule read in-source);
`BATCH_SIZE=256` (`:256`) cold at scale; the `storage.conf`-relocated graphroot
outside the deny (honest-limit comment at `lib/ownership.sh:694` region, read);
**BOB-201** resolve-or-accept and **BOB-202** layer-choice both operator-owned
(§11.4.66). One ledger note, ungraded: the tasks.md round-5 addendum says the §5
observation was "deliberately NOT filed" — true when written; the conductor filed
it as BOB-202 afterwards, and this document is the ledger continuity for that fact.

## 8 — What this round did not analyse

The round-4 suite's original bytes (not in any git object — reconstruction used,
§1); the `.docx`/`.html` twin content beyond charset/new-content/mojibake spot
checks; `start.sh`'s warm-path interaction with BOB-159 (out of T028 scope);
sibling-stream artifacts (by instruction); `pre_build_verification.sh` (T042's).

## Verdict, restated for the record

**GO — 0 BLOCKING · 0 IMPORTANT · 0 MINOR · 0 NIT · 0 warnings (§11.4.134).**
R4-N2's closure carries a verified RED→GREEN flip in both halves and survived
seven attacks including two nobody had written; R4-N1's closure is the correct
§11.4.201(1) call proven by a non-empty false-refusal measurement I reproduced;
BOB-202's mechanism is confirmed three ways (probe, non-whitespace counter-probe,
the project's own 2026-08-21 sibling forensic) and is unreachable from the shipped
scope; every do-not-regress number reproduces exactly; every still-open item is
stated honestly and none is closed. The convergence trajectory (7 → 3 → 5 → 2 →
0) terminates here. **T028's checkbox may be checked on this verdict.**
