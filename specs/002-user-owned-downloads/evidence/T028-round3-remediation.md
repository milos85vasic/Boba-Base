# T028 — Round-3 remediation of `scripts/ownership_repair.sh` (author side)

**Revision:** 1
**Last modified:** 2026-08-26T00:00:00Z

Author: `(T11/002-user-owned-downloads - milos85vasic - ? - xhigh)`. Responds to
`evidence/T028-review-ROUND2.md` (NO-GO, 0 BLOCKING / 0 IMPORTANT / 1 MINOR / 2 NIT).
Nothing already verified closed in round 2 was reworked.

Artifact identities after remediation (sha256, first 16):
`lib/ownership.sh 99c76c3cd1417dcf`, `ownership_precondition.sh 6308d9e6eaa74f56`,
`test_ownership_repair.sh 9b2d994047d1c9f6`, `ownership_repair.sh ae025b74602414ca`
(**unchanged** — the repair script itself needed no edit), `owned_paths.yaml
26375798edfee773` (**unchanged** — the shipped scope was never touched).

All destructive probes ran under fixture scopes via `--scope`; `config/owned_paths.yaml`,
`logs/ownership/` and the operator's real library were never written (`git status
--porcelain config/owned_paths.yaml logs/` empty throughout). `nice -n 19`; no `.venv`.

---

## RED → GREEN (§11.4.224 / §11.4.115 — fixture authored first, observed failing first)

| run | suite result | what it proves |
|---|---|---|
| `baseline-before` | **86 passed, 0 failed, 0 skipped** | round-2 baseline reproduced before any edit |
| `red` (Case 23 added, no fix) | **88 passed, 23 failed** | R2-M1 reproduces; the 2 new passes are the control needle and the golden-FALSE, so the fixture is not vacuous |
| `red2` (adjacent probes added, no fix) | **89 passed, 25 failed** | the adjacent mid-path case reproduces |
| `green1` (parser fixed) | **114 passed, 0 failed, 0 skipped** | all 25 flipped; the 86 baseline assertions still pass |
| `green2` (Case 24 + NIT fixes) | **124 passed, 0 failed, 0 skipped** | R2-N1/R2-N2 covered |
| `final` (reproduction) | **124 passed, 0 failed, 0 skipped** | 124 reproduced twice |

Verbatim RED, the defect itself (2-entry scope, entry 1 `${UNSET_VAR}`):

```
FAIL: vanished entry [unset ${VAR}, no default]: exit 0 — a DECLARED location vanished
      and the run reported SUCCESS (§11.4.201(6) false-null; the marker latches the miss)
FAIL: … the run announced '(1 declared locations)' and proceeded
FAIL: … a COMPLETION MARKER was written for a scope with a vanished declaration
FAIL: … the surviving location was MUTATED despite the refusal
```

Verbatim RED for the adjacent case (`<root>/decoy/${UNSET}/leaf`):

```
FAIL: vanished entry [unresolved ${VAR} mid-path]: exit 0 — an unset variable collapsed the
      declared path into a DIFFERENT well-formed path and the run proceeded
FAIL: … the repair CHOWNED a tree the scope never declared
```

Verbatim GREEN, same fixtures:

```
ownership: 1 declared entry in …/config/owned_paths.yaml resolved to no usable location:
ownership:   entry 1 — path: '${BOBA_T028_UNSET_QQQ}' — it expanded to an empty path:
             ${BOBA_T028_UNSET_QQQ} is unset or empty and the entry supplies no ':-' default
ownership: refusing the WHOLE scope, not only these entries: the completion
ownership:   marker's fingerprint claims EVERY declared location, so a partial
ownership:   walk that exited 0 would latch the miss on every later start.
```

---

## R2-M1 — the decision, and why

**Refuse the whole run, in the shared parser.** Four reasons, recorded in-source at
`scripts/lib/ownership.sh` (the `ownership_scope_entries` header):

1. **The marker latches the miss.** Its fingerprint is computed over the PARSED entries
   and `start.sh` reads it as "already repaired", so a partial walk that exits 0 does not
   miss a location once — it misses it on every subsequent start.
2. **The identical decision is already recorded 20 lines away** for the declared-path
   fence (`ownership_repair.sh:485-489`): "ONE BAD ENTRY REFUSES THE WHOLE RUN … Refusing
   per-entry and proceeding with the rest would silently repair a partial scope while
   writing a marker that claims the whole one." Two answers to one question inside one
   file is the second dialect §11.4.251 forbids.
3. **Magnitude is not a semantic boundary.** `paths: []` (all entries vanish) is already
   exit 2; letting 1-of-2 exit 0 puts the operator's model on an arbitrary cliff.
4. **§11.4.252 fail-closed / §11.4.101 safe-reversible.** A refusal costs one env fix; a
   silent partial repair costs an unrepaired tree behind a green marker.

`optional: true` is explicitly **not** an escape hatch: it declares the path may be ABSENT
from the filesystem, not that the DECLARATION may be absent. Pinned as its own sub-probe.

**Why the parser and not the consumer:** the parser is the only layer still holding the raw
spelling and the variable name (§11.4.241 — strongest rung that can see the invariant), and
it gives all three consumers (repair, precondition, `check_cm_ownership_invariants.sh`) one
predicate instead of three crosschecks that could disagree about expansion semantics. Pinned
by a sub-probe that calls `ownership_scope_entries` directly and requires rc=2.

**Adjacent case found while fixing this, closed with it (§11.4.238):** a `${VAR}` without a
default that resolves empty MID-path does not empty the path — it silently rewrites it.
Measured: `<root>/decoy/${UNSET}/leaf` → `<root>/decoy/leaf`, fence-accepted (absolute, deep
enough), walked and chowned a tree the scope never declared. The fence's depth floor is **not**
a backstop — it only catches collapses landing on `/` or a bare top-level directory. Declared
deliberately here rather than smuggled in.

**Golden-FALSE (§11.4.201(1)), both halves:** `${VAR:-default}` — the shipped scope's first
entry shape — and an interpolated `${VAR:-default}` mid-path are NOT refused and really repair.
Both passed on unfixed code, so they are false-positive guards, not fix-agreeing assertions.

**Case 16 reconciled, not weakened (§11.4.120):** shape (c) (`every ${VAR} expands empty`) is
now caught one layer earlier and no longer prints "no locations". `_c16_probe` gained a
per-shape evidence regex, so each of the three shapes now asserts the evidence ITS OWN cause
produces — strictly more specific than the one generic phrase for three different causes.
Exit-2 and no-marker assertions unchanged for all three.

**Sibling consumer (§11.4.247):** `ownership_precondition.sh` discarded the reader's stderr
(`2>/dev/null`) and printed a cause line naming only the three file-level causes. Left alone,
my change would have made that message state a cause never established (§11.4.6). It now
captures and replays the reader's own lines and names the new cause. Two `[[ … ]] && rm`
shapes introduced by that edit (one as a statement, one inside a `while` body) were caught
and guarded with `{ …; } || :` before the run.

> **CORRECTION (round 4, R3-N2 — §11.4.6).** The sentence that stood here claimed that
> "under `set -euo pipefail` either would have killed the check before `cannot_run`
> printed". **Measurement contradicts that mechanism.** Re-measured on this host
> (`GNU bash 5.2.37(1)-release`), independently of the reviewer who raised it:
>
> | shape | result under `set -euo pipefail` |
> |---|---|
> | mid-sequence `[[ -n "" ]] && rm …; echo next` — **the position the shipped code occupies** | **SURVIVES** — `next` printed, caller rc 0 |
> | same shape as the tail of a `while` body | **SURVIVES** — loop completed, rc 0 |
> | same shape as the tail of a **function** | **DIES** — caller rc 1, nothing printed |
>
> Both guarded sites (`ownership_precondition.sh:1041`, `:1044`) are mid-sequence —
> `:1041` is followed by `cannot_run`, `:1044` by the next `if` — so neither was ever
> fatal, and the claimed FAIL-bluff would not have occurred. The finding itself stands
> and is not withdrawn: the two shapes are real, the `{ …; } || :` guards are correct,
> and they remain worth keeping because they state the intent explicitly and stay safe
> if a later edit moves either statement into a tail position, which IS the fatal shape.
> What was wrong was the asserted mechanism, stated as fact without being measured —
> exactly the §11.4.6 error this correction records rather than deletes. An independent
> re-hunt found no third hazard: the remaining bare `[[ … ]] &&` statements
> (`:790`, `:958`, `:963`, `:987`, `:1094`) are all mid-sequence or `&& continue`.

---

## R2-N1 — documentation only, as graded

One paragraph added to the fence's HONEST BOUNDARY (`scripts/lib/ownership.sh`) stating that
the fence **judges the spelling** and the kernel resolves intermediate components, that the
static (no-race) form was MEASURED, that a symlinked FINAL component *is* contained, that what
bounds the intermediate case is who can write components above the declared root, and the
BOB-159 link. Machine-checked by Case 24 so the sentence cannot silently disappear.

## R2-N2 — the deny, with its golden-FALSE set

Implemented rather than only documented. `ownership_fence_runtime_trees()` computes
`${XDG_DATA_HOME:-$HOME/.local/share}/containers` and the fence refuses it and anything under
it, for **absolute** entries only (relative entries are bounded by project containment, which
is stronger — same split the system-tree rule already uses).

Honest limit stated in-source and in both guides: it resolves the default and the
XDG-relocated graphroot (pure string operations) and **not** one relocated in `storage.conf`
or `CONTAINERS_STORAGE_CONF`, because reading those would make the fence depend on filesystem
state at check time — the raceable property the lexical normaliser exists to avoid.

A degenerate computed value (relative, or shallower than the depth floor because `HOME` was
unset) is **discarded**, so the deny can never broaden into a top-level prefix. Case 24 drives
`ownership_path_fence()` directly with a controlled `HOME` — a pure string predicate touching
nothing real, never the operator's own `$HOME` — and asserts:

* REFUSED: the storage root, and a path inside it.
* ACCEPTED (golden-FALSE): `$HOME/Downloads`, `$HOME/.local/share`, the near-miss sibling
  `.local/share/containerz`, and this host's real library shape
  `/run/media/<user>/<disk>/Downloads`.
* ACCEPTED with `HOME` unset — the degenerate-value guard.
* End-to-end: a `$HOME`-rooted download tree is still walked and really repaired.

The refuse and accept cases share one helper, so a helper whose rc was always 0 would have
failed the two refuse cases — the instrument is proven bidirectional by construction.

---

## The ordering violation — NOT closed, and it now covers BOTH runs

Recorded on the SAME open record in `tasks.md` (§11.4.214 — a recurrence links, it never
re-mints; `grep -c "T028"` = 1, checkbox still `- [ ] T028`). The second run was
re-verified independently rather than transcribed from the round-2 review:

* `journalctl --user`, unit `boba-stack.service`, pid 1169590, **2026-08-25 20:52:21** —
  `(6 declared locations)`, `0/0 items need repair` at **all six** including the real library
  `/run/media/milosvasic/DATA4TB/Downloads`, then `complete: 0 item(s) repaired; no change
  record (nothing was changed)`.
* Both candidate revisions carry the short-circuit, each read from the immutable git object:
  `7b45113:760` and `HEAD:980`, whose body is `log_info "…0/0 items need repair"; continue`
  — before the chown batch. So `chown(2)` was never invoked either way.

Round 1's unresolved contradiction (51 items recorded at uid 100999 in the provenance vs 0
discovered) remains **UNKNOWN**; nothing in this round settled it.

---

## Verification (all reproduced)

```
tests/unit/test_ownership_repair.sh        124 passed, 0 failed, 0 skipped   (×2)
tests/unit/test_ownership_precondition.sh   29 passed, 0 failed, 0 skipped   (×2)
  — incl. its negative control: all 6 SHIPPED entries ACCEPT under three
    different QBITTORRENT_DATA_DIR values (the deny did not touch the product)
scripts/pre_build/check_cm_ownership_invariants.sh          PASS, exit 0
scripts/pre_build/check_cm_no_production_mutation_residue.sh
                            scanned 272 file(s); 0 hit(s); 1 audited waiver(s), exit 0
bash -n  lib/ownership.sh, ownership_precondition.sh, ownership_repair.sh, the suite   all clean
```

Shipped-scope control needle, run against the real `config/owned_paths.yaml` with the live
environment: 6 rows, `RC=0` — the new rules are unreachable from the product configuration,
which is exactly why R2-M1 needed a fixture.

Companion guides updated in the same change (§11.4.18) and their `.html`/`.pdf` twins
regenerated and verified non-degenerate through to the PDF text layer (§11.4.38). Only those
two documents' twins were regenerated — a repo-wide exporter run would have swept other
agents' in-flight `.md` edits in this shared checkout (§11.4.84).

## Not closed by this round (§11.4.6)

* The ordering violation (above) — open, and not the author's to close.
* Carried forward from round 2 unchanged: the `podman unshare` fallback has still never run
  against a real subuid-owned item; `CONTAINER_RUNTIME` is still an unvalidated command name;
  `BATCH_SIZE=256` scale behaviour over the 6458-item library is still cold.
* R2-N1's residual reach (static intermediate symlinks) is documented and BOB-159-tracked,
  not removed — by decision, since removing it would require abandoning the lexical fence.
* A graphroot relocated via `storage.conf` is outside F4, stated rather than implied.
