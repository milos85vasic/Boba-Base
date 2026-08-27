# T028 — Round-3 independent re-review of the ownership-repair remediation: **NO-GO**

**Revision:** 1
**Last modified:** 2026-08-26T14:53:55Z

Reviewer: independent agent, label `(T11/002-user-owned-downloads - milos85vasic - fable - ?)`,
structurally separate from the author of `evidence/T028-round3-remediation.md`
(sha256 first-16 `4d5fcf41b1407497`) and from both prior reviewers
(§11.4.142/§11.4.194/§11.4.209/§11.4.134). Reviewed state: HEAD `a3e1141` plus the
UNCOMMITTED round-3 working-tree edits. Artifact identities verified against the
remediation's own claims (sha256, first 16 — all MATCH):
`lib/ownership.sh 99c76c3cd1417dcf`, `ownership_precondition.sh 6308d9e6eaa74f56`,
`test_ownership_repair.sh 9b2d994047d1c9f6`, `ownership_repair.sh ae025b74602414ca`
(unchanged, as claimed), `owned_paths.yaml 26375798edfee773` (unchanged, as claimed).
The PRE-fix revision used for reproduction is `HEAD:scripts/lib/ownership.sh`
= `b1b4e7ce217c8635`, byte-identical to what round 2 reviewed.

**Verdict: NO-GO under §11.4.134 — 0 BLOCKING · 0 IMPORTANT · 1 MINOR · 4 NIT, all
NEW, all mine, all enumerated with remediation shapes.** All three round-2 findings
(R2-M1, R2-N1, R2-N2) are **verified closed by execution**, the headline mid-path
rewrite claim is **verified true end to end** (reproduced pre-fix, closed post-fix, no
over-refusal), and every do-not-regress item reproduced green in my own runs. The
remaining iteration is one MINOR tracker-integrity edit plus three documentation
sentences and one two-line hardening — small and fully enumerated.

Probe discipline: every destructive probe ran under `--dry-run` against FIXTURE
scopes via `--scope`, with `--state-dir` in scratch; the sanctioned test suites are
the only thing that mutated anything (their own mktemp sandboxes). The real
`config/owned_paths.yaml`, the live `logs/ownership/`, and the operator's library
were never written. `nice -n 19`; no `.venv`; no process-group signals (§11.4.263).
The author's own run logs in the shared scratch dir were read but never trusted as
evidence — every load-bearing number below was re-measured by this review.

---

## 1 — The headline claim: the mid-path `${VAR}` rewrite — **VERIFIED TRUE, CLOSED, NOT OVER-CLOSED**

The author's self-found adjacent defect is real, was real on the pre-fix revision,
and is strictly worse than the R2-M1 it was found beside. Reproduced by this review
against the PRE-fix artifact (`b1b4e7ce…`, extracted from the immutable HEAD tree
into scratch — never the working tree), fixture scope declaring
`<sb>/fixture/decoy/${BOBA_R3_UNSET_ZZZ}/leaf` with the variable unset:

```
[ownership-repair] operator 1000:1000; scope …/mid-pre/config/owned_paths.yaml (1 declared locations)
[ownership-repair] would chown 1000:1000 (was 1000:10) …/mid-pre/fixture/decoy/leaf
[ownership-repair] would chown 1000:1000 (was 1000:10) …/mid-pre/fixture/decoy/leaf/victim2.bin
[ownership-repair] would chown 1000:1000 (was 1000:10) …/mid-pre/fixture/decoy/leaf/victim.bin
[ownership-repair] 1/1 …/fixture/decoy/leaf: 3/3 items processed
PRE-FIX EXIT=0
```

The scope declared a path containing an unresolved variable; the pre-fix parser
silently rewrote it to `…/decoy/leaf`, the fence accepted it (absolute, deep enough
— the depth floor is provably NOT a backstop for this shape), and the walk targeted
a tree the scope never declared, exit 0. The MUTATION half (an actual chown, not
just targeting) was proven separately by my revert kill-matrix (§3, RM12): against
the pre-fix artifact the suite's Case 23M sandbox records
`the repair CHOWNED a tree the scope never declared` as a live FAIL.

**Closed:** the same scope against the working tree refuses with exit 2, naming the
entry index, the raw spelling, the rewritten path AND the unresolved variable:

```
ownership:   entry 1 — path: '…/decoy/${BOBA_R3_UNSET_ZZZ}/leaf' — it expanded to
             '…/decoy//leaf', a DIFFERENT path than declared: ${BOBA_R3_UNSET_ZZZ}
             is unset or empty and the entry supplies no ':-' default
POST-FIX EXIT=2
```

**Not over-closed (§11.4.201(1)):** my own mid-path golden-FALSE —
`…/fixture/mid/${BOBA_R3_UNSET_ZZZ:-real}/leaf` — resolved, walked, and named
exactly the declared tree (`GOLDEN-FALSE EXIT=0`); the shipped `${VAR:-default}`
whole-path shape likewise (suite Case 23G). Both golden-FALSE fixtures also PASS
against the PRE-fix artifact in my kill-matrix, which proves they are false-positive
guards rather than fix-agreeing assertions.

---

## 2 — Round-2 findings: verified status

### R2-M1 (partial-empty scope silently narrowed) — **CLOSED, verified by execution**

* The refusal lives in the shared parser (`ownership_scope_entries`), returns 2,
  writes NOTHING to stdout on refusal (suite sub-probe: no survivor rows), and
  names WHICH entry and WHY. Verified by direct parser probes and end-to-end runs.
* **Whole-run refusal, marker argument verified structurally:** the marker's
  fingerprint is computed over the parsed entries (`ownership_scope_fingerprint`
  = `ownership_scope_entries | sort | sha256sum`), `start.sh:978-1010` runs the
  repair and hard-refuses the boot on any non-zero exit — and the twin decision the
  author cites really is recorded ~20 lines from the fence consumption
  (`ownership_repair.sh:486-490`, "ONE BAD ENTRY REFUSES THE WHOLE RUN …"), so the
  §11.4.251 second-dialect argument stands.
* **`optional: true` is genuinely not an escape hatch:** the suite's dedicated
  sub-probe passes live and DIES on the revert (kill-matrix: all 5 assertions of
  the `vanished entry marked optional: true` family fail against pre-fix).
* Sibling consumer: `ownership_precondition.sh` on a vanished-entry fixture exits 2
  and REPLAYS the reader's own lines (measured this round — transcript in §3, RM-P),
  so its cause line no longer states a cause never established.
* Shipped scope unreachable from the new rule, as claimed: my shipped-scope control
  needle (real `config/owned_paths.yaml`, live env, read-only) → 6 rows, RC=0; the
  precondition suite's negative control (all 6 shipped entries ACCEPT under three
  `QBITTORRENT_DATA_DIR` values) passed in my run. The fixtures are the only
  coverage standing behind the new rules — and the kill-matrix proves they stand
  (§3, RM12).

### R2-N1 (fence honest boundary: static intermediate symlinks) — **CLOSED as graded, but see R3-M1**

The sentence exists in the fence header ("IT JUDGES THE SPELLING; THE KERNEL
RESOLVES THE PATH"), states the static no-race form as MEASURED, bounds it by
who-can-write-above-the-root, and is machine-checked by Case 24 (both checks die on
the revert). The sentence does not overstate — it under-claims, correctly. The
"Tracked as BOB-159" clause inside it, however, is a dangling tracking claim — the
new MINOR below (R3-M1).

### R2-N2 (container-storage deny) — **CLOSED, verified by execution + adversarial probes**

Suite Case 24 passed live (refuse storage root + inside; accept `$HOME/Downloads`,
`$HOME/.local/share`, `containerz` sibling, the real library shape; HOME-unset
degenerate; end-to-end `$HOME`-rooted real repair) and its refuse cases die on the
revert. My own degenerate-value attack — the round's specific instruction — held
completely; transcripts in §3 (RM10/RM11). The deny **never broadens into a
top-level prefix** under any degenerate value I could author.

### Case 16 reconciliation — **GENUINE (§11.4.120), not a weakening**

Shape (c) gained a cause-specific evidence regex
(`resolved to no usable location|empty path`); shapes (a)/(b) keep the old one;
exit-2 and no-marker assertions unchanged for all three. The §11.4.120
discriminator: against the PRE-fix artifact (where shape (c) still prints the old
"contains no locations" phrase) the reconciled assertion **FAILS** —
`empty scope [every ${VAR} expands empty]: output never matched /resolved to no
usable location|empty path/` is the first FAIL line of my kill-matrix. A weakened
tautology would have passed both revisions; this passes exactly one.

---

## 3 — Reviewer-authored mutations (§11.4.194(6)(d)) — none previously written

| # | Mutation | Result |
|---|----------|--------|
| RM1 | Pre-fix mid-path `${UNSET}` repro (fixture, dry-run) | **Defect CONFIRMED pre-fix** (walk targeted the undeclared tree, exit 0); **KILLED post-fix** (exit 2, entry+variable named). |
| RM2 | Mid-path `${VAR:-real}` golden-FALSE post-fix | **Not over-refused** — resolved, walked, named exactly the declared tree, exit 0. |
| RM3 | `${VAR:-}` explicit-empty default, WHOLE path | **KILLED** — refused as shape (1), "it expanded to an empty path" (message correctly does not blame the variable — a default was supplied; the declaration itself is nothing). Matches the in-source rule verbatim. |
| RM4 | `${VAR:-}` explicit-empty default, MID-path | **ACCEPTED BY DOCUMENTED DESIGN** — `/tmp/decoy//leaf` row emitted; the header explicitly classifies `${VAR:-}` as the operator stating what empty means. A deliberate spelling; I accept the design. |
| RM5 | Nested `${A:-${B}}`, both unset / A set | **SURVIVED at the grammar edge — new finding R3-N1.** Both-unset → literal row `${BOBA_R3_B}`; A=/tmp/x → corrupted row `/tmp/x}` (the regex consumes through the inner `}` and strands the outer one). End-to-end with `optional: true`, both unset: `…/${BOBA_R3_B}: absent, declared optional — skipped` → **exit 0**. |
| RM6 | TWO unset vars in one mid-path | **KILLED** — refused; the diagnosis names BOTH variables (`dict.fromkeys` dedup order preserved). |
| RM7 | Var set to whitespace-only, mid-path | **KILLED (honest).** Set-is-set: row `/tmp/decoy/ /leaf`; walks only a literally-named dir, honest exit 1 otherwise. No silent nothing. |
| RM8 | TRAILING unset var (`…/decoy/${U}` — the superset-walk shape, pre-fix it would have walked ALL of decoy) | **KILLED** — refused as shape (2), "expanded to '…/decoy/', a DIFFERENT path than declared". |
| RM9 | Var set to `a/b` and to `..` mid-path | **ACCEPTED, correctly** — set values are env-writer-controlled exactly as `QBITTORRENT_DATA_DIR` itself is; normalisation + fence judge the result; no capability gained. |
| RM10 | Degenerate deny values: `HOME` unset / `HOME=` / `HOME=/` / trailing slash / relative; `XDG_DATA_HOME=/`, `/x`, relative | **HELD.** Unset/empty/`/` HOME each compute the narrow 3-component phantom `/.local/share/containers` (kept, harmless — see R3-N3 for the comment drift); trailing slash normalises correctly; relative HOME and relative XDG **discarded**; `XDG_DATA_HOME=/` → `/containers` (1 component) **discarded by the floor guard** — and a 1-component declared root is refused by the depth floor anyway. Under `HOME=/`, an ordinary root `/data/Downloads` is still ACCEPTED. **The deny never broadened.** |
| RM11 | Prefix near-misses `…/containersXYZ` and `…/containers2/storage` | **ACCEPTED** — the `== "${rt}" || == "${rt}"/*` match is slash-boundary-exact. |
| RM12 | **Revert kill-matrix**: the post-fix SUITE run against the PRE-fix artifact (scratch project, byte-verified copies) | **30 assertions die**: all four Case-23 vanished-entry families (5 assertions each), the mid-path pair (including `the repair CHOWNED a tree the scope never declared` — the mutation half of the headline), the shared-predicate triple, Case 16(c)'s reconciled regex, both R2-N1 doc checks, both container-storage refusals. `RESULT: 94 passed, 30 failed`. Every new fixture is RED-capable (§11.4.224(C)); golden-FALSE fixtures pass on BOTH revisions. |
| RM13 | `set -e` semantics of the author's claimed hazard shapes (bash 5.2.37) | **Exposed R3-N2** — both claimed-fatal positions SURVIVE unguarded (`[[ -n "" ]] && rm …; next` prints next; while-body-tail variant survives); only the function-tail variant dies (rc 1). |
| RM14 | BOB-159 body probe (sqlite, control-needled) | **Exposed R3-M1** — 4674-char description, **0** occurrences of `symlink`/`intermediate` (needle: 10 hits for `warm|repair` through the same path); NO item in the whole tracker mentions symlinks. |

Not attempted, with reasons: `${1}`/`${}` (outside the `[A-Za-z_]` grammar, left
literal, walks nothing silently); var set to `.` (subsumed by RM9's normalise-only
family); NUL/very-long-path (round 2's recorded reasons stand unchanged).

Instrument honesty: every zero above was control-needled (the RM14 needle is in the
table; the shipped-scope needle's positive control is the 6-row read; the kill-matrix
run doubles as the needle for every suite assertion). No `| head` pipeline fed an
exit-code read this round (the round-2 SIGPIPE lesson applied).

---

## 4 — New findings this round

### R3-M1 — MINOR: "Tracked as BOB-159" is a dangling tracking claim for the static intermediate-symlink reach (§11.4.197/§11.4.6/§11.4.214)

The fence's HONEST BOUNDARY (new this round, `scripts/lib/ownership.sh`) states the
measured static intermediate-symlink reach and closes with "Tracked as BOB-159."
Measured: BOB-159 exists (`Bug/Queued`, "Warm ./start.sh over an already-running
stack leaves the FR-004d repair window open"), its 4674-character description
contains **zero** occurrences of `symlink` or `intermediate` (control needle: 10
hits for `warm|repair` through the same sqlite+grep path), and **no item in the
entire workable-items DB mentions symlinks at all**. Provenance of the drift:
round 1 linked the TOCTOU/**race** variant to BOB-159 per §11.4.214 ("warm-start
write window" — defensible, the race needs a window); round 2's M5 upgraded the
class to a **static, no-race** reach; round 3 baked "Tracked as BOB-159" into the
artifact for the static form — which no tracker item records. This is exactly the
lost-defect shape §11.4.214 warns about: no tracker query can find the static reach.
Case 24's machine check (`grep -qi 'BOB-159' "${LIB}"`) pins the STRING, not the
tracking — it cannot see that the pointee is empty of the pointed-at content.
**Remediation shape:** append the static intermediate-symlink residual to BOB-159's
description (if the operator considers it in-scope for that item) or mint a linked
item and update the in-source clause; one tracker edit plus at most one comment word.

### R3-N1 — NIT: an out-of-grammar nested `${A:-${B}}` survives the parser as a literal/corrupted path; with `optional: true` it silently skips, exit 0

Measured (RM5): both-unset yields the literal row `${BOBA_R3_B}` (the `[^}]*`
default cannot span the inner `}`; the outer `}` is stranded), A-set yields
`/tmp/x}`. Non-optional entries then fail honestly ("does not exist", exit 1), but
an `optional: true` entry logs `…/${BOBA_R3_B}: absent, declared optional — skipped`
and the run exits 0 (a real run writes the marker). Bounds that keep it NIT: only
reachable by writing malformed nesting INTO the tracked scope file (not via env);
the skip line prints the unexpanded literal, so it is visible; the grammar the new
header documents is `${VAR}`/`${VAR:-default}` only. **Remediation shape:** after
expansion, refuse a parsed path that still contains `${` — two lines in the same
`vanished` machinery, message "the entry's spelling was not fully resolved".

### R3-N2 — NIT: the remediation evidence asserts a `set -e` failure mechanism that measurement contradicts (§11.4.6)

`T028-round3-remediation.md` states the two self-caught `[[ … ]] && rm` shapes
"under `set -euo pipefail` either would have killed the check before `cannot_run`
printed". Measured on this host's bash 5.2.37 (RM13): the mid-sequence position
(exactly where the shipped code sits) and the while-body variant both SURVIVE
unguarded — `reached_next_statement` prints, rc 0; only a function-**tail**
occurrence kills the caller. The shipped `{ … } || :` guards are correct and
harmless either way; the finding is the stated-as-fact mechanism in the evidence
document, not the code. My independent hunt for a third hazard found none: the four
remaining bare `[[ ]] &&` statements in the precondition (`:958,:963,:987,:1094`)
are all mid-sequence, the non-fatal shape. **Remediation shape:** one sentence
correction in the evidence file (or a struck clause).

### R3-N3 — NIT: the deny's degenerate-value comment attributes the depth-floor discard to the wrong variable (§11.4.6)

`ownership_fence_runtime_trees`'s header says a computed value "shallower than the
depth floor **because HOME was unset** is DISCARDED". Measured (RM10): HOME
unset/empty computes `/.local/share/containers` — 3 components, which is KEPT as a
harmless narrow phantom deny, not discarded; the shallow-discard branch is actually
reached via a degenerate `XDG_DATA_HOME` (`/` → `/containers`, 1 component,
discarded). The guard's BEHAVIOUR is correct in every probed case and never
broadens; only the comment's causal attribution is wrong. **Remediation shape:** one
comment line.

### R3-N4 — NIT: `ownership_scope_fingerprint` emits the empty-string sha256 on stdout while returning rc≠0 on a refused scope

Measured: against a refused scope the function prints
`e3b0c44298fc1c14…` (sha256 of "") and returns 2 — the pipeline's `sha256sum`
runs on empty input before `pipefail` surfaces the parser's 2. Every CURRENT
consumer guards the rc (`ownership_repair.sh:442` checks `if ! FINGERPRINT=$(…)`;
the suite's `sb_fingerprint`/`marker_present` propagate it), so there is no live
defect — but the round-3 change made rc≠0 reachable from a new cause (vanished
entries), and a future caller that captures stdout without checking rc would
receive a plausible-looking "fingerprint" of a scope that refused to parse.
**Remediation shape:** compute entries first, return before hashing on failure —
three lines.

---

## 5 — The ordering violation (NOT closed here) and the real-run ledger — **honesty confirmed**

* `grep -c "T028" tasks.md` = **1**; the box is still `- [ ] T028`; the record
  covers BOTH real runs on the same open violation (§11.4.214 — links, no re-mint).
* The 2026-08-25 20:52:21 run **independently re-verified from the journal** (unit
  `boba-stack.service`, pid 1169590): `(6 declared locations)`, `0/0 items need
  repair` at all six including `/run/media/milosvasic/DATA4TB/Downloads`, then
  `complete: 0 item(s) repaired; no change record (nothing was changed)`.
* Both candidate revisions' short-circuit **re-read from the immutable objects**:
  `7b45113` and HEAD `a3e1141` each carry
  `discovered -eq 0 → log "0/0 items need repair"; continue` (at :759-762 and
  :979-982 respectively — the author's cited `:760`/`:980` fall inside both blocks),
  before the chown batch. `chown(2)` was never invoked either way.
* **Ledger addendum (recorded, ungraded):** the same journal line ends
  `…; marker logs/ownership/repair-marker.json` — the 20:52 run also wrote a
  completion marker. Both evidence documents quote the line truncated before that
  clause. No false statement was made (the marker is the designed output of an
  honest 0/0 walk, and the fingerprint re-arms on any scope/env change), but the
  clause belongs in the ledger: the real 6-location scope is latched "done" as of
  that run's fingerprint.
* Round 1's contradiction (51 items at uid 100999 in the provenance vs 0
  discovered) — **still honestly UNKNOWN** in tasks.md and in both evidence files;
  nothing this round settled it, and nothing claims to.

Author's declared un-closed items, each verified honestly stated: the
`podman unshare` fallback is still never exercised against a real subuid-owned item
(the `"${RUNTIME}" unshare chown` line sits unexercised at `ownership_repair.sh:731`);
`CONTAINER_RUNTIME` is still an unvalidated command name at the same site;
`BATCH_SIZE=256` scale behaviour is still cold (the 20:52 run walked 6458 items but
discovered 0); the `storage.conf`-relocated graphroot is stated in-source as outside
the deny's reach. None claimed closed; none closed.

---

## 6 — Do-not-regress: all reproduced by this review's own runs

```
tests/unit/test_ownership_repair.sh        RESULT: 124 passed, 0 failed, 0 skipped   (my run)
tests/unit/test_ownership_precondition.sh  RESULT: 29 passed, 0 failed, 0 skipped    (my run)
  incl. negative control: all 6 SHIPPED entries ACCEPT under three
  QBITTORRENT_DATA_DIR values (unset-default, foreign path, real library)
check_cm_ownership_invariants.sh           PASS, exit 0
check_cm_no_production_mutation_residue.sh scanned 272 file(s); 0 hit(s); 1 audited waiver(s); exit 0
bash -n  lib/ownership.sh ownership_precondition.sh ownership_repair.sh suite   all clean
config/owned_paths.yaml 26375798edfee773  UNTOUCHED (matches rounds 2 and 3)
ownership_repair.sh     ae025b74602414ca  UNTOUCHED (matches rounds 2 and 3)
shipped-scope control needle (live env, read-only): 6 rows, RC=0
start.sh:978-1010: repair exit != 0 refuses the boot, loud, reasons replayed (fail-closed)
```

Author transcript cross-check (read, not relied on): the RED→GREEN table's counts
(86 → 88/23 → 89/25 → 114/0 → 124/0 → 124/0 ×2) match the logs in the shared
scratch dir line for line; my kill-matrix independently establishes the only
load-bearing property (RED-capability of every new fixture).

## 7 — What this round did not analyse

Intermediate uncommitted states between the author's `red`/`green` logs (only the
final working tree was reviewed); the guides' regenerated `.html`/`.pdf` twins were
confirmed present and modified but their content was not proofread; `start.sh`'s
warm-path interaction with BOB-159's operator decision (out of T028's scope).

## Verdict

**NO-GO** under §11.4.134 — 1 MINOR + 4 NIT remain, all new this round. The
dangerous work is done and verified: the headline mid-path rewrite was real,
is closed at the right layer, does not over-refuse, and every new fixture provably
dies on the revert. R2-M1, R2-N1 and R2-N2 are closed. What remains is one tracker
edit (R3-M1), one two-line parser hardening (R3-N1), and three sentence-level
corrections (R3-N2/N3/N4) — one more small iteration closes the loop.
