# BOB-186 — Investigation: `workable-items diff` partial-read false-null

**Revision:** 1
**Last modified:** 2026-08-26T18:40:00Z
**Scope:** Investigation only. No source changed, no tracker DB or Markdown mutated.
**Label:** (T11/002-user-owned-downloads - milos85vasic - ? - xhigh)

## Verdict summary

| Question | Answer |
|---|---|
| Does `diff` still false-green on a partial read? | **NO** — fixed in constitution `5979128` (2026-08-25 21:06), live in both shipped binaries |
| Is the DB↔Markdown pair actually in sync right now? | **NO** — 8 real divergences, independently confirmed |
| Would committing the DB now commit a false green? | **NO** — the gate correctly refuses; it would commit a *known-red* divergence |

## 1. Reproduction — measured counts

Real corpus, gate-resolved binary (`constitution/scripts/workable-items/bin/workable-items`):

```
$ workable-items diff --db docs/workable_items.db --issues docs/Issues.md --fixed docs/Fixed.md
~ BOB-159 body differs (md=3366 bytes db=4917 bytes)
~ BOB-197 status: md="Queued" db="In progress"
~ BOB-197 body differs (md=2460 bytes db=4091 bytes)
~ BOB-198 body differs (md=2253 bytes db=3600 bytes)
~ BOB-199 body differs (md=3221 bytes db=6382 bytes)
- BOB-200 present in DB, absent in Markdown
- BOB-201 present in DB, absent in Markdown
- BOB-202 present in DB, absent in Markdown
diff: 8 difference(s) (compared 198 Markdown item(s) against 201 DB item(s); read docs/Issues.md, docs/Fixed.md)
EXIT=1
```

The BOB-186 shape (`--issues` without `--fixed`) no longer green-lights:

```
$ workable-items diff --db docs/workable_items.db --issues docs/Issues.md
diff: refusing to report a DB-vs-Markdown verdict that would silently exclude part of
the DB — the supplied Markdown path(s) do not account for 122 item(s) located in Fixed
(supply --fixed). ...
EXIT=1
```

With the opt-in `--partial-scope`, the verdict is scope-limited and never says "in sync":

```
diff: PARTIAL SCOPE — 8 difference(s) within the tracker(s) compared (compared 76
Markdown item(s); read .../Issues.md), and 122 of 201 DB item(s) were NOT compared:
122 in Fixed (no --fixed supplied).
EXIT=1
```

## 2. Root cause (pre-fix `sync.go`, commit `5979128^`)

Two independently-reasonable pieces combined into a false-null.

**(a) Scope narrowing — pre-fix lines 852–863**, the reverse "absent in Markdown" pass:

```go
for _, d := range dbItems {
    if d.CurrentLocation == "Issues" && *issuesPath == "" { continue }
    if d.CurrentLocation == "Fixed"  && *fixedPath  == "" { continue }
    if !parsedSeen[itemKey(d)] {
        fmt.Printf("- %s present in DB, absent in Markdown\n", d.AtmID)
        differences++
    }
}
```

Its own comment states the intent: skip rows whose tracker the caller never supplied,
"missing-in-Fixed lines would be their own class of false positive". Correct as a
false-positive guard — but the `continue` also removes those rows from `differences`
entirely, and nothing compensated.

**(b) Scope-unaware verdict — pre-fix lines 894–897:**

```go
if differences == 0 {
    fmt.Printf("diff: DB and Markdown are in sync (compared %d Markdown item(s) "+
        "against %d DB item(s); read %s)\n", len(parsed), len(dbItems), read)
    return exitOK
}
```

It prints `len(parsed)` (77 — only what was parsed) and `len(dbItems)` (184 — the whole
DB), then decides purely on `differences`. **The verdict printed both mismatched numbers
and never compared them.** A partially blind instrument returned the identical quiet
green a genuinely-synced corpus returns — §11.4.201(6) FALSE-NULL.

Root cause in one line: *a false-positive guard silently narrowed comparison SCOPE while
the verdict logic remained scope-unaware — no invariant tied covered-scope to verdict.*
The §11.4.201(1) fix created its §11.4.201(6) mirror image.

## 3. The fix (live)

`5979128` adds a scope-accounting guard (post-fix `sync.go:813–867`) keyed on **measured
DB content**, not on flag presence, and makes the verdict SHAPE a function of the measured
unaccounted set (`sync.go:1007–1032`). Comment at `sync.go:1007` is attributed verbatim to
`BOB-186`. Regression guard: `sync_diff_partial_scope_test.go`, 9 tests including
`TestDiffCmd_IssuesOnlyDoesNotClaimSyncWhileFixedRowsUncompared`,
`TestDiffCmd_PartialScopeOptInNeverClaimsSync`,
`TestDiffCmd_IssuesOnlyIsCompleteWhenDBHasNoFixedRows` (the false-positive guard).

Both shipped binaries carry it:

| Binary | mtime | sha256 (head) | guard string | `PARTIAL SCOPE` |
|---|---|---|---|---|
| `constitution/scripts/workable-items/bin/workable-items` (gate-resolved first) | Aug 25 21:50 | `298c3e66…` | 1 | 2 |
| `constitution/scripts/workable-items/workable-items` | Aug 25 20:37 | `e5412ffd…` | 1 | 2 |

Grep control needle: known-present `"DB and Markdown are in sync"` → 1 hit; negative
control `ZZZ_NOT_PRESENT_NEEDLE_20260826` → 0 hits, exit 1. Instrument proven seeing.

## 4. Control needles (§11.4.201(7)(b))

| Needle | Method | Result |
|---|---|---|
| **Negative control** (false-positive guard) | regenerate MD from the COPY DB, diff | `in sync (compared 201 … against 201 …)`, exit 0 — instrument is not stuck-on-FAIL, and 201-vs-201 is the counts-account-for-each-other property |
| **Needle A** — Issues leg | flip `BOB-008` status in the clean copy | detected: `~ BOB-008 status: md="In progress" db="Operator-blocked"`, exit 1 |
| **Needle B** — Fixed leg (class-matched to BOB-186) | delete `BOB-067` from the clean Fixed copy | detected: `- BOB-067 present in DB, absent in Markdown` (200 vs 201), exit 1 — the Fixed leg is genuinely READ, not merely "accounted for" |

Each needle byte-verified applied before the run (before/after grep counts differed).

## 5. Independent enumeration of the current divergence

Not trusting the tool — `sqlite3` + `grep` on the real files:

```
db_issues=79  md_issues=76
-- in DB, NOT in Issues.md --   BOB-200  BOB-201  BOB-202
-- in Issues.md, NOT in DB --   (none)
db_fixed=122  md_fixed=122      (both directions empty)
```

`BOB-197` independently confirmed: `docs/Issues.md:1466` reads `**Status:** Queued`;
DB `items.status` = `In progress`.

Body sizes independently confirmed larger in DB for all four `~ body differs` items
(e.g. BOB-159 md-section 3267 B vs DB `length(body_md)` 4905 B).

**Direction of drift:** the DB is AHEAD; `docs/Issues.md` is stale. Regenerating from the
DB produces a 193 436 B Issues.md vs the committed 175 630 B. `docs/Fixed.md` is fully
current (item-wise byte-identical; the only delta is the §11.4.44 header, Rev 32 on disk
vs Rev 24 stored).

## 6. Blast radius for the imminent commit

- Worktree state: `M docs/workable_items.db` **only**. `Issues.md` / `Fixed.md` are clean
  at `d7cf05d`. So this is a DB-moved-ahead-of-Markdown state, not a race.
- `core.hooksPath` is UNSET (§11.4.234(B)) — automatic git hooks do NOT gate the commit.
- `scripts/commit-push-all.sh:378,386` calls `_docs_sync_seam_check` unconditionally,
  which delegates to `scripts/hooks/docs-sync-commit-seam.sh`. Its CHECK 2 runs
  `diff --issues --fixed` and is **not** behind `BOBA_SYNC_SKIP_CI` (that flag gates only
  CHECK 4, line 327). CHECK 2 will FAIL → the commit is REFUSED.
- `scripts/pre_build_verification.sh:585` invariant 17 also passes both paths → `fail`.
- **Residual risk:** a raw `git commit` bypasses all of it, because hooks are disconnected.

## 7. Remediation direction (NOT applied)

- **BOB-186 itself is already fixed** in code, binary, and test. Its tracker row is still
  `Status: Queued` in `Issues`. Remediation = close the item citing `5979128` +
  `sync_diff_partial_scope_test.go`; no code work is owed.
- **The current divergence** is a separate, live condition. Verified safe on copies:
  in-place `sync db-to-md` bumps Issues Rev 75→76 (monotone, §11.4.44 respected), leaves
  Fixed at 32 (content unchanged), and yields `in sync (201 vs 201)`. Regenerating to a
  *new* path instead would regress the headers to the DB-stored 34/24 — use in-place.
- Choose the authoritative side first: DB-is-right → `sync db-to-md`; Markdown-is-right →
  `sync md-to-db`. Given BOB-200/201/202 exist only in the DB, DB-is-right is indicated.

## 8. Honest gaps

- `UNKNOWN:` whether the two shipped binaries are byte-for-byte reproducible from current
  HEAD source — not rebuilt (no `.venv`/build run authorised here). Both were proven to
  carry the guard and to behave identically on the real corpus, which is the property
  that matters for this defect.
- No claim is made about defect classes `diff` does not compare (revision headers,
  summary docs, `Issues_Summary.md`/`Fixed_Summary.md`); CHECK 3 of the commit seam and
  invariant 18 cover adjacent ground and were not exercised here.

## Files read (no writes outside this directory)

`constitution/scripts/workable-items/cmd/workable-items/sync.go`,
`.../sync_diff_partial_scope_test.go`, `scripts/pre_build_verification.sh`,
`scripts/hooks/docs-sync-commit-seam.sh`, `scripts/commit-push-all.sh`,
`docs/workable_items.db` (read-only), `docs/Issues.md`, `docs/Fixed.md`.

Post-run integrity check — real artifacts untouched:

```
ad8157f877a25f586d425e12b3ac596d383a794f900dcc5d3174f416b238894e  docs/workable_items.db
a8657a4280bc72f85fae59849acb33990a97500e353c1bc0c41807c9b9b8b3d2  docs/Issues.md
9354fe29b4d56f01969ba1642a3f8620a37466cc347e206a6870def2e8f57331  docs/Fixed.md
```
