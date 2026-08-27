# T028 — Round-4 independent re-review of the round-4 remediation: **NO-GO**

**Revision:** 1
**Last modified:** 2026-08-26T15:40:00Z

Reviewer: independent agent, label `(T11/002-user-owned-downloads - milos85vasic - fable - ?)`,
structurally separate from the author of `evidence/T028-round4-remediation.md`
(sha256 first-16 measured this session) and from all three prior reviewers
(§11.4.142/§11.4.194/§11.4.209/§11.4.134). Reviewed state: HEAD `a3e1141` plus the
UNCOMMITTED round-4 working-tree edits. Artifact identities verified against the
remediation's claims (sha256 first-16 — **all MATCH, measured by this review**):
`lib/ownership.sh 43aad4b6850e958c`, `test_ownership_repair.sh f4d8de37b31ec1f8`,
`ownership_precondition.sh 6308d9e6eaa74f56` (unchanged since round 3),
`ownership_repair.sh ae025b74602414ca` **UNTOUCHED**, `config/owned_paths.yaml
26375798edfee773` **UNTOUCHED**. PRE-fix revision for the kill-matrix:
`HEAD:scripts/lib/ownership.sh` = `b1b4e7ce217c8635`, byte-verified before use.

**Verdict: NO-GO under §11.4.134 — 0 BLOCKING · 0 IMPORTANT · 0 MINOR · 2 NIT, both
NEW, both mine, both single-edit remediation shapes, both on surfaces authored THIS
round.** All five round-3 findings (R3-M1, R3-N1, R3-N2, R3-N3, R3-N4) are
**verified closed by execution** — none partially, none by prose. The rejected-fix
argument is **adjudicated in the author's favour, with a measurement showing the
author under-claimed** (§1). The tracker-querying Case 24 survived every blind-read
attack I could construct and killed both re-point mutations (§2). The fingerprint
byte-identity holds on every accepted input and the live marker cross-check is exact
(§3). Both N2/N3 corrections re-measured EXACT on this host (§5).

**Trajectory adjudication (7 → 3 → 5 → 2): genuine convergence, not exhaustion.**
Three facts support that verdict against the alternative. (1) The severity ceiling is
monotone-falling: 2 IMPORTANT (round 1) → 1 MINOR (round 2) → 1 MINOR (round 3) →
0 MINOR (this round); both residual NITs are a one-sentence doc edit and a ~4-line
loop. (2) No closed finding has reopened in any round — every closure I re-executed
held, so the count is not whack-a-mole churn. (3) Both new findings sit exclusively
on code authored and self-reviewed THIS round (the guide's new grammar section, the
new Case-24 tracker check) — old surfaces are exhausted, which is what convergence
looks like from inside.

Probe discipline: every destructive probe ran `--dry-run` against FIXTURE scopes via
`--scope`/`OWNED_PATHS_FILE`, `--state-dir` in scratch; mutations ran ONLY against
byte-verified scratch copies of the project (copy shas checked before every run);
the sanctioned suites were the only thing that mutated anything, inside their own
mktemp sandboxes. The real `config/owned_paths.yaml`, live `logs/ownership/` and the
operator's library were never written — `repair-marker.json` and
`docs/workable_items.db` were **read only** (post-review shas re-verified: marker
`00d4bd3dfa427ab3`, DB `2d8f186f48ea8257`, unchanged). `nice -n 19`; no `.venv`;
`pre_build_verification.sh` NOT run (T042 owns it); sibling-stream files
(`check_cm_export_charset_valid*`, `lan_route_auth*`, `tighten_*`,
`scripts/pre_build/lib/`) neither touched nor diffed; the one background lock-holder
process was killed by its captured integer pid > 1 only (§11.4.263). The author's
run logs were read but never trusted — every load-bearing number below is my own run.

---

## 1 — PRIORITY 1: the rejected fix, adjudicated — **the author is right, and under-claimed**

**My round-3 proposal ("refuse a parsed path that still contains `${`") is measured
insufficient.** Simulating the exact substitution on
`/tmp/decoy/${A:-${B}}/leaf`: with both unset the expansion is
`/tmp/decoy/${BOBA_R4REV_B}/leaf` (`contains ${` → my check fires); with
`A=/tmp/x` it is `/tmp/decoy//tmp/x}/leaf` — **`contains_dollar_brace=False`**. The
A-set corruption sails through my proposal with no `${` anywhere. Measured, exactly
as the author said.

**The shipped declared-spelling rule holds on every attack I authored.** Parser-level
matrix (17 spellings, fixture scopes, direct `ownership_scope_entries` probes):

| spelling | result |
|---|---|
| `${A:-${B}}` both unset / A set / B set / both set | **refused rc 2 in all four** — and the four stderr transcripts are **byte-identical** (`cmp`), so the "identical whether or not `A` is set" invariant holds to the byte. I could not break it: the rule's only inputs are `raw` and `VAR_RE`, evaluated before any substitution, so the environment structurally cannot reach the verdict. |
| `${}` / `${1}` / unterminated `${VAR` / literal `${` in a dirname | refused rc 2 (condition 2, unconsumed opener) |
| `${A:-}` whole-path | refused rc 2 as shape (1) — empty declaration |
| `${A:-}` mid-path | ACCEPTED (documented RM4 design) |
| literal `}` in a dirname · literal `{` · `${A:-x}}` (stranded literal `}`) · a VALUE containing `${` | **all ACCEPTED** — the golden-FALSE carve-outs hold live |
| bare `$VAR` (no braces), set or unset | ACCEPTED as a literal path — see R4-N1 |

End-to-end: the motivating case — nested + `optional: true` — refuses the WHOLE run,
exit 2, entry and spelling named (`--dry-run`, fixture scope, scratch state dir).

**The adjudicating mutation (M-G, mine, nobody had written it): I implemented my own
rejected proposal in a scratch copy** (shipped rule → `if False:`; post-expansion
`"${" in path` → vanished; both edits assert-count-verified) and ran the full suite.
**Result: 138/8/0 — eight assertions kill it**, and the failure list is the whole
argument in machine form:

* `nested ${A:-${B}}, A set — the corrupted-path variant`: **"a path the grammar
  could not resolve was accepted … a silent skip that exits 0"** and **"the surviving
  location was MUTATED despite the refusal"** — the exact case the author said I would
  miss, pinned by a fixture.
* `golden-FALSE, a VALUE containing ${`: **"the rule reached into a variable's VALUE,
  refusing an env-writer-controlled path (§11.4.201(1))"** — my proposal is not only
  insufficient, it OVER-refuses: a post-expansion check judges values, which the
  shipped raw-only rule can never do. The author argued insufficiency; the suite
  proves my proposal was wrong in **both directions**.

The author's own two mutations reproduce: disabling the rule kills 16 assertions
(kill-matrix, §6); the golden-FALSE guards pass on BOTH revisions, so they are
false-positive guards, not fix-agreeing assertions.

**Adjudication: the rejection stands, on evidence stronger than the author claimed.**

---

## 2 — PRIORITY 2: the tracker-querying Case 24 — **held; two bounded gaps found on it (R4-N2)**

Structure verified: the suite runs `set -uo pipefail` with separate PASS/FAIL/SKIP
counters; `finish` exits non-zero only on FAIL, and a SKIP is printed with its reason
and counted in the RESULT line — **a SKIP is never a green** and never silent
(§11.4.201(6) satisfied; the RESULT line shows `1 skipped` in every SKIP run below).

Attacks, all against byte-verified scratch copies (project tree, suite `f4d8de37…`,
lib `43aad4b6…`, DB `2d8f186f…`):

| attack | result |
|---|---|
| re-point citation → `BOB-159` (**the exact round-3 defect**) | **KILLED**: 145/1/0 — "cites BOB-159, but that item's body never mentions symlinks" — the check would have caught R3-M1 |
| re-point → `BOB-99999` (no such item) | **KILLED**: 145/1/0 — distinct diagnosis, "no such item exists in the tracker" |
| DB file absent | **SKIP** (145/0/1) — "the tracker cannot be read here … unjudged rather than approved" |
| `items` table renamed (schema change) | **SKIP** (145/0/1) — "BLIND read, not … absence (§11.4.201(7)(b))" |
| DB `chmod 000` (unreadable) | **SKIP** (145/0/1) — same blind-read route |
| DB replaced with non-SQLite garbage | **SKIP** (145/0/1) — same route |
| held `BEGIN EXCLUSIVE` writer for the whole run | **PASS 146/0/0, correctly** — the DB is WAL-journaled (`PRAGMA journal_mode` = `wal`), so a held writer never blinds readers on this host; my pre-run probe query succeeded through the lock. No false SKIP, no false PASS. |

**"Records the reach" is a real anchor today**: BOB-201 exists (`Bug/Queued`,
2553-char description), its **title itself names the exact reach** ("lexical fence
does not resolve intermediate symlink components — a static symlink can steer the
walk outside the declared scope"), 5 `symlink` occurrences, and it is the only
symlink-mentioning item in the tracker — so the assertion is anchored to the right
item, not substring luck. Honestly stated: the implementation is `grep -qi 'symlink'`
over title+description, one notch weaker than its pass-message — recorded inside
R4-N2. **The author's instrument false-null is confirmed both ways**: the remediation
records the over-escaped first RED rather than repairing it silently, and my own
needle through the same path sees (COUNT(*) = 200 rows; BOB-201 count = 1; body read
returns the real 2553-char text). The `_C24_EXISTS`-fails-while-`_C24_ROWS`-succeeded
window (which would mis-route a blind read to FAIL) was analysed and bounded: on a
WAL host writers cannot produce it, and every constructible blind state (absent /
unreadable / corrupt / schema-changed) blinds ALL three queries → SKIP. Not graded.

**R4-N2 (the gap that IS graded)**: my novel mutation — appending a SECOND
`Tracked as BOB-159` citation AFTER the real one — **survives: 146/0/0**. The
extraction pipes through `head -1`, so only the FIRST citation is ever judged; a
future edit adding a second residual-reach clause with a dangling id passes the very
check built this round to catch dangling citations. §4.

---

## 3 — PRIORITY 3: the N4 byte-identity — **verified, including the live marker**

Old pipe re-extracted from HEAD (`ownership_scope_entries | LC_ALL=C sort |
sha256sum | cut -d' ' -f1`) and run side-by-side with the shipped function through
the SAME current parser:

| scope | old pipe | new function | verdict |
|---|---|---|---|
| `paths: []` | `e3b0c44298fc1c14…` rc 0 | same rc 0 | IDENTICAL |
| one entry (my fixture) | `ff508f730d5e7eef…` rc 0 | same | IDENTICAL |
| three entries (my fixture) | `6dbf9349e7e1a15b…` rc 0 | same | IDENTICAL |
| **live shipped scope** (read-only) | `c41619d2…` | `c41619d2…` | IDENTICAL — **and equals the on-disk marker written 2026-08-25 by the OLD code**, so no completion marker silently re-arms |
| refused scope (`${UNSET}` mid-path) | `e3b0c442…` on stdout, rc 2 | **empty stdout**, rc 2 | divergent BY DESIGN — this divergence IS the R3-N4 fix |

The naive-fix hazard is real: `$( )` strips the trailing newline, and an
unconditional `printf '%s\n'` would hash `"\n"` for a zero-row scope — the shipped
empty-branch removes exactly that. One precision note, ungraded: the comment's
"byte-identical … for every input" strictly excludes the refused input (where the
divergence is the documented fix, stated two sentences earlier in the same block) —
context disambiguates completely; read it as "every input on which the pipe emitted
a value". Structural analysis closes the domain: every parser row carries four tabs
and exactly one trailing newline, so no input can make the strip/re-add asymmetric.

---

## 4 — PRIORITY 4: the marker latch — **verified live; consequence stated plainly**

Independently re-measured: `logs/ownership/repair-marker.json` (mode 0600, mtime
2026-08-25 20:52:21, read-only) records `items_changed 0`, `record_file null`,
`scope_fingerprint c41619d212648a692bca539c1b3836d136b5c5c54058dacc0f81680c70120c3b`
— and the fingerprint the current shipped scope + live environment computes today
**equals it** (measured through both the old pipe and the new function). The latch is
live NOW, not merely as of the 20:52 run.

**What `start.sh` does today, given that marker** (code path read this round):
`run_ownership_gate` runs the precondition (live probe — new-file ownership at each
of the six locations), then `ownership_repair.sh` with no `--force`; the repair
computes `c41619d2…`, `marker_is_valid` (`:537-538`) matches it, and the run logs
**"already complete for this scope … nothing to do"** and exits 0 — the walk of
existing items does not run, and will not run until the scope file or its
interpolated environment changes, or an operator passes `--force`.

**Is the marker correct?** Yes, as far as it claims: it asserts a COMPLETED PASS
with zero changes, not a completed repair-of-items — `items_changed 0` /
`record_file null` say exactly that, and the journal proves the pass was real (0/0
at all six locations including the real library). It asserts nothing that was not
established. What it *latches* is the designed E2 behaviour; the residual — items
going wrong AFTER 20:52 are not re-walked until re-arm, while the per-start
precondition only probes NEW-file ownership — is the already-tracked BOB-159
warm-window class, not a new fact. The ordering violation **stays OPEN, unchanged,
on the same tasks.md record** — verified: `grep -c T028` = 1, box `- [ ] T028`, the
round-4 ledger addendum sits on that record, and the 51-items-vs-0-discovered
contradiction remains honestly **UNKNOWN**. Nothing here closes any of it, and
nothing claims to.

---

## 5 — PRIORITY 5: the N2/N3 corrections — **both re-measured EXACT on this host**

**N2** (`GNU bash 5.2.37(1)-release`, my own probes): mid-sequence
`[[ -n "" ]] && rm …; echo next` **survives** (rc 0, `next` printed); the
while-body variant **survives** (rc 0); the function-tail variant **dies** (rc 1).
The CORRECTION block in `T028-round3-remediation.md:115-127` states exactly this
table, keeps the finding un-withdrawn, and both shipped guard sites
(`ownership_precondition.sh:1041` followed by `cannot_run`, `:1044` followed by the
next `if`) are mid-sequence — the correction is right, and the `{ …; } || :` guards
remain correct insurance against a future tail-position move.

**N3** (direct `ownership_fence_runtime_trees` probes): `HOME`
unset/empty/`/` → `/.local/share/containers` (3 components) **KEPT** as the narrow
phantom; `XDG_DATA_HOME=/` → `/containers` (1 component) **DISCARDED by the depth
floor**; relative `HOME` and relative `XDG_DATA_HOME` → **DISCARDED by the `== /*`
guard, a different branch**; trailing-slash `HOME` normalises; and under
HOME-unset AND `HOME=/` an ordinary `/data/Downloads` is still **ACCEPTED** — the
deny never broadens. The rewritten comment (`lib/ownership.sh:700-711`) now names
both guards with the right causal attributions, matching measurement row for row.
The correction is not itself wrong.

---

## 6 — Reviewer-authored mutations (§11.4.194(6)(d)) — all byte-verified

Every mutation was applied by count-asserted replace (count-1 before, old-absent +
new-present after) and the artifact hash-restored afterwards (`43aad4b6850e958c`
re-verified after each). One instrument incident of my own, recorded rather than
repaired silently: my first M-H `sed` **silently failed to apply** (delimiter
collision) and the ensuing 146/0/0 was a run of the UNMUTATED artifact — the
byte-verification caught it (`new-present=0, old-left=1`), the run was voided, and
the mutation was re-applied via verified Python replace. This is the same
silently-unapplied-`sed` false-PASS class the task brief warned about, caught by the
mandated discipline.

| # | mutation (mine unless noted) | result |
|---|---|---|
| M-A | re-point citation → BOB-159 (author also ran) | **KILLED** 145/1/0, right diagnosis |
| M-B | re-point → BOB-99999 (author also ran) | **KILLED** 145/1/0, distinct diagnosis |
| M-C | tracker DB absent (author also ran) | **SKIP** 145/0/1 — never a pass, never a fail |
| M-D | `items` table renamed | **SKIP** 145/0/1 — blind read routed honestly |
| M-E | held `BEGIN EXCLUSIVE` writer for the whole run | **PASS** 146/0/0, correctly — WAL readers unaffected (probe query succeeded through the lock); no false SKIP |
| M-E2 | DB `chmod 000` | **SKIP** 145/0/1 |
| M-E3 | DB replaced with garbage bytes | **SKIP** 145/0/1 |
| M-F | **second dangling `Tracked as BOB-159` appended after the real citation** | **SURVIVED** 146/0/0 — `head -1` judges only the first citation → **R4-N2** |
| M-G | **the rejected reviewer proposal implemented in place of the shipped rule** | **KILLED by 8 assertions** — including the A-set corrupted-path fixture AND the value-`${` golden-FALSE proving the proposal over-refuses; the adjudicating measurement of §1 |
| M-H | fingerprint `printf '%s\n'` → `printf '%s'` | **SURVIVED — proven an EQUIVALENT MUTANT**: `od` shows GNU sort re-adds the missing trailing newline, so the byte stream into sha256sum is identical; the survival is correct, not a gap |
| M-H2 | fingerprint `sort` → `sort -r` | **SURVIVED** 146/0/0 — a self-consistent suite cannot see cross-version VALUE stability (repair and suite compute through the same lib). The DANGEROUS direction is pinned (M-H3); the value-stability property is established by the §3 three-way measurement (old pipe = new fn = on-disk marker), which is inherently a cross-version check no unit assertion can replace. Honest boundary, recorded ungraded; an optional golden-value assertion on a fixed fixture would add drift detection at review time. |
| M-H3 | fingerprint → constant | **KILLED by 4 assertions** — "the fingerprint did not change when the scope did", "the stale marker suppressed the run", record-rotation, fingerprint-prose — the re-arm safety property is genuinely guarded |
| M-P | parser matrix: 17 spellings × env states (§1), incl. the novel bare-`$VAR` attack | bare `$VAR` + `optional: true` → **silent skip, exit 0** (dry-run, literal printed in the skip line) → **R4-N1**; all documented refusals and all golden-FALSE accepts behave exactly as claimed; nested-refusal stderr byte-identical across all four env states |

---

## 7 — New findings this round

### R4-N1 — NIT: the guide's "anything else is refused" over-claims — a bare `$VAR` is NOT refused, and with `optional: true` it silently skips, exit 0 (§11.4.6)

`docs/scripts/ownership_repair.md` §"The grammar is exactly two forms — anything
else is refused" states "**Those two forms are the whole grammar**, and a spelling
outside it is refused rather than substituted." Measured: `path:
/tmp/…/$BOBA_R4REV_A/leaf` — outside both forms — is NOT refused; it survives as a
literal path component (set or unset, since only `${` openers are judged), and a
real `--dry-run` with `optional: true` logs `absent, declared optional — skipped`
and **exits 0** — the same optional-escape shape as R3-N1, one grammar step away
(the realistic operator typo is `path: /data/$USER/downloads`). The LIB's own
comment is precise (it names only the two `${` shapes it refuses) — only the guide
generalises beyond measurement, the exact stated-mechanism class R3-N2 was.
Bounds identical to R3-N1: reachable only by writing the spelling INTO the tracked
scope file; the skip line prints the literal so it is visible; non-optional entries
fail honestly (exit 1). **Refusing bare `$` in code would be WRONG** — it would
false-refuse real `$`-named directories (an NTFS-mounted download disk carries a
literal `$RECYCLE.BIN`), a §11.4.201(1) class the current design correctly avoids.
**Remediation shape: one guide sentence** — bare `$NAME` is literal by design,
never expanded, never refused (and why) — plus softening the section heading's
"anything else". No code change wanted.

### R4-N2 — NIT: Case 24's tracker check judges only the FIRST `Tracked as` citation, and approximates "records this reach" as "mentions symlink" (§11.4.194(6)(d)/§11.4.214)

Measured (M-F): with a second, dangling `Tracked as BOB-159` appended AFTER the real
BOB-201 citation, the suite reports **146/0/0** — the extraction ends in `head -1`,
so the check built this round to catch dangling citations cannot see a dangling
SECOND citation; a later edit adding another residual-reach clause re-opens the
R3-M1 shape invisibly. Secondary, same block: the pass-message "really records the
symlink reach" is implemented as `grep -qi 'symlink'` over title+description —
anchored exactly today (BOB-201's title names this precise reach and is the
tracker's only symlink-mentioning item), but generically satisfied by ANY
symlink-mentioning item. **Remediation shape: one edit** — loop over EVERY extracted
`BOB-[0-9]+` citation instead of `head -1` (~4 lines), and optionally tighten the
content probe to `intermediate.*symlink|symlink.*intermediate`-class matching.
Today's artifact state (exactly one citation, correctly pointed) is verified clean.

---

## 8 — Do-not-regress: all reproduced by this review's own runs

```
tests/unit/test_ownership_repair.sh        RESULT: 146 passed, 0 failed, 0 skipped   (my run)
tests/unit/test_ownership_precondition.sh  RESULT: 29 passed, 0 failed, 0 skipped    (my run)
  incl. negative control: all 6 SHIPPED entries ACCEPT under three QBITTORRENT_DATA_DIR values
check_cm_ownership_invariants.sh           PASS, exit 0 (rc captured directly, not through a pipeline)
check_cm_no_production_mutation_residue.sh scanned 272 file(s); 0 hit(s); 1 audited waiver(s); exit 0
  (the waiver is check_cm_export_charset_valid.sh:46 — a SIBLING stream's, not this change)
bash -n  lib/ownership.sh ownership_precondition.sh ownership_repair.sh suite   all clean
shipped-scope control needle (live env, read-only): 6 rows, RC=0
ownership_repair.sh     ae025b74602414ca  UNTOUCHED (verified)
config/owned_paths.yaml 26375798edfee773  UNTOUCHED (verified)
REVERT KILL-MATRIX (current suite vs pre-fix lib b1b4e7ce217c8635, byte-verified scratch tree):
  RESULT: 100 passed, 46 failed — matches the author's claim exactly.
  Families: 25 vanished-entry + 16 unresolved-spelling + 4 fence-boundary + 1 empty-scope.
  All 9 golden-FALSE assertions PASS on the pre-fix artifact too → false-positive guards,
  not fix-agreeing assertions. Every new fixture is RED-capable (§11.4.224(C)).
guides: ownership_repair.md Revision 5, ownership_precondition.md Revision 5,
  .html/.pdf twins regenerated (twin mtimes ≥ their .md, both pairs)
tasks.md: grep -c T028 = 1; box still `- [ ] T028`; round-4 addendum on the SAME record
docs/workable_items.db read-only claim verified: HEAD blob has 0 BOB-201 rows, worktree 1
  (the delta is the operator's pre-existing filing, not this round's edit); post-review
  sha 2d8f186f48ea8257 unchanged
```

The author's intermediate RED state (129/17/0) was not reproduced — it existed only
in uncommitted intermediate trees; the kill-matrix independently establishes the
load-bearing property (RED-capability of every new assertion), the same position
round 3 took on round 3's RED logs.

## 9 — Honestly-open items — honesty confirmed, none closed, none claimed closed

Verified still stated and still open: `podman unshare` fallback never exercised
against a real subuid-owned item (the `unshare chown` path sits at
`ownership_repair.sh:377-386`); `CONTAINER_RUNTIME` an unvalidated command name at
the same site; `BATCH_SIZE=256` (`:256`) cold at scale; the `storage.conf`-relocated
graphroot stated in-source as outside the deny's reach (`lib/ownership.sh:694`); the
ordering violation (OPEN, §4); the 51-items-vs-0-discovered contradiction
(**UNKNOWN**, unchanged); BOB-201's resolve-or-accept decision operator-owned
(§11.4.66).

## 10 — What this round did not analyse

The `.html`/`.pdf` twin CONTENT (presence + freshness verified only); the author's
uncommitted intermediate RED/GREEN trees; `start.sh`'s warm-path interaction with
BOB-159 (out of T028 scope); sibling-stream artifacts (by instruction).

## Verdict

**NO-GO under §11.4.134 — 0 BLOCKING · 0 IMPORTANT · 0 MINOR · 2 NIT.** Every
round-3 finding is closed and verified by execution; the rejected-fix dispute is
settled in the author's favour by a mutation that implements my own proposal and
watches eight assertions kill it; the tracker-querying fixture, the fingerprint
rewrite, and both corrections all held under independent attack. What remains is one
guide sentence (R4-N1) and one ~4-line loop plus an optional one-word probe
tightening (R4-N2) — both on this round's newest surfaces, neither touching
`ownership_repair.sh` or the scope file. The trajectory is genuine convergence; one
more minimal iteration closes the loop, and under §11.4.134 the box stays unchecked
until it does.
