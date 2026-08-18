# Task #68 / BOB-108 — workable-items `export` Revision-regression fix: captured evidence

**§11.4.5 / §11.4.44 / §11.4.115 anti-bluff captured-evidence artefact.** All commands below were
run for real, in this session, against the real repository tree (no mocks). Every result pasted
here was produced by an actual invocation of the fixed binary or `go test`, in the same session as
the fix commit.

## Fix commit

- Constitution submodule commit: `4a17867` — "fix(workable-items,export): stop `export`
  regressing §11.4.44 Revision counters below committed values"
- Pushed clean to all 8 named constitution remotes (origin, github, gitlab, gitflic, gitverse,
  vasic_digital_github, vasic_digital_gitlab, upstream) — verified by `git log --oneline -1` on
  every remote-tracking ref after a fresh `git fetch --all`, all report `4a17867`.
- Files: `constitution/scripts/workable-items/cmd/workable-items/export.go` (wired the fix),
  `export_revision.go` (new — `reconcileRevisionHeader`), `export_revision_test.go` (new — the
  RED-first regression tests).

## Bug reproduction (pre-fix, live, on the real repo tree)

Before any fix, docs/Issues.md and docs/Fixed.md were clean (`git status --porcelain` empty) at:

```
docs/Issues.md **Revision:** 8   **Last modified:** 2026-08-18T16:50:00Z
docs/Fixed.md  **Revision:** 17  **Last modified:** 2026-08-18T16:50:00Z
```

Running the PRE-FIX binary:

```
$ /tmp/workable-items-test export --db docs/workable_items.db --out-dir docs/ --no-formats
export: wrote docs/Issues.md
export: wrote docs/Fixed.md
export: wrote docs/Issues_Summary.md
export: wrote docs/Fixed_Summary.md
```

produced:

```
docs/Issues.md **Revision:** 6   **Last modified:** 2026-08-15T12:15:00Z   <- REGRESSED (8 -> 6)
docs/Fixed.md  **Revision:** 15  **Last modified:** 2026-08-15T12:15:00Z   <- REGRESSED (17 -> 15)
```

confirmed via `git diff --stat` (67 insertions in Issues.md, 4 in Fixed.md) and `head -6` on both
files. This reproduction was immediately reverted with `git checkout -- docs/Issues.md
docs/Fixed.md` — nothing from it was ever committed.

## RED-before-fix / GREEN-after-fix (unit tests, real SQLite, real binary dispatch)

`export_revision_test.go`'s two tests were run against the export.go call sites temporarily
disabled (`issuesText, err = issuesText, error(nil) // TEMP-RED-DISABLE`), reproducing the same
class of defect purely inside the test:

```
$ go test ./cmd/workable-items/... -run 'TestExportCmd_NeverRegressesRevisionBelowCommittedFile|TestExportCmd_PreservesRevisionWhenContentUnchanged' -v
--- FAIL: TestExportCmd_NeverRegressesRevisionBelowCommittedFile (0.01s)
    export_revision_test.go:89: export REGRESSED the committed §11.4.44 Revision (8 -> 6) ...
--- FAIL: TestExportCmd_PreservesRevisionWhenContentUnchanged (0.00s)
    export_revision_test.go:140: no-op regeneration must reproduce the committed file byte-for-byte ...
FAIL
```

With the fix restored (`reconcileRevisionHeader` wired back into export.go):

```
$ go test ./cmd/workable-items/... -run 'TestExportCmd_NeverRegressesRevisionBelowCommittedFile|TestExportCmd_PreservesRevisionWhenContentUnchanged' -v
--- PASS: TestExportCmd_NeverRegressesRevisionBelowCommittedFile (0.01s)
--- PASS: TestExportCmd_PreservesRevisionWhenContentUnchanged (0.00s)
PASS
```

## Full package suite (no new regressions)

```
$ go build ./...            # clean
$ go test ./... 2>&1 | grep -- "--- FAIL"
--- FAIL: TestDiffCmd_NoPathsSkipsMarkdownComparison (0.01s)
```

That single failure was confirmed PRE-EXISTING and unrelated: `git stash` of the fix commit +
`go test -run TestDiffCmd_NoPathsSkipsMarkdownComparison` on the clean baseline (commit `d79755a`,
before this fix) reproduces the identical failure verbatim. Zero new failures introduced by this
fix.

## Post-fix live verification against the real repo tree (this session)

```
$ head -4 docs/Issues.md; head -4 docs/Fixed.md      # pre-run, committed HEAD
**Revision:** 8   **Last modified:** 2026-08-18T16:50:00Z
**Revision:** 17  **Last modified:** 2026-08-18T16:50:00Z

$ /tmp/workable-items-fixed export --db docs/workable_items.db --out-dir docs/ --no-formats
export: wrote docs/Issues.md
export: wrote docs/Fixed.md
export: wrote docs/Issues_Summary.md
export: wrote docs/Fixed_Summary.md

$ head -4 docs/Issues.md; head -4 docs/Fixed.md      # run 1
**Revision:** 9   **Last modified:** 2026-08-18T19:14:11Z    <- earned bump (8 -> 9), NOT the DB's stale 6
**Revision:** 17  **Last modified:** 2026-08-18T16:50:00Z    <- PRESERVED byte-identical, no content change

$ /tmp/workable-items-fixed export --db docs/workable_items.db --out-dir docs/ --no-formats   # run 2 (idempotent)
$ head -4 docs/Issues.md; head -4 docs/Fixed.md
**Revision:** 9   **Last modified:** 2026-08-18T19:14:11Z    <- UNCHANGED from run 1 (no double-bump)
**Revision:** 17  **Last modified:** 2026-08-18T16:50:00Z    <- still byte-identical

$ git diff docs/Fixed.md   # empty — confirms the "preserve if unchanged" branch is byte-exact
$ git diff docs/Issues.md  # +7 sections (BOB-108..BOB-114, already resident in the DB but not yet
                            #  materialised into the committed file — a pre-existing, unrelated
                            #  DB-ahead-of-docs desync this run correctly surfaced per §11.4.93)
```

Issues.md's Revision correctly landed on 9 (`max(existing=8, DB's stale=6) + 1`), never on the
DB's stale 6 — the exact defect this fix closes. Fixed.md, whose content genuinely did not change
(nothing new closed), stayed perfectly byte-identical including its Revision and Last-modified —
proving the "preserve, never gratuitously bump" half of the fix on real production data, not just
the synthetic test fixtures.

## §11.4.44 monotonic-Revision audit (pre-fix vs post-fix)

| File | Committed (pre-fix) | Pre-fix `export` result | Post-fix `export` result |
|---|---|---|---|
| docs/Issues.md | Revision 8 | **Revision 6 (REGRESSION)** | Revision 9 (earned bump) |
| docs/Fixed.md  | Revision 17 | **Revision 15 (REGRESSION)** | Revision 17 (preserved, no bump) |
