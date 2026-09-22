# BOB-181 closure evidence — 2026-09-23

## Status: fix already present, uncredited, on `main` since 2026-09-02

Independent investigation (subagent + coordinator, both confirmed
independently) found `scripts/generate_markdown_exports.sh` **already**
implements fix direction (a) from the item's own acceptance criteria: it
accepts optional `.md` path arguments and, when given, scopes the run to
exactly those files (hard-erroring on a non-existent/non-`.md` path), only
falling back to the historical whole-tree sweep when invoked with zero
arguments.

```
$ git log --oneline -1 60729c9 -- scripts/generate_markdown_exports.sh
60729c9 fix(qbittorrent,start.sh): repair admin/admin WebUI login, boot abort, and untagged downloads
```
The argument-handling landed as an **uncredited side-effect** of that
unrelated commit (2026-09-02) — its message never mentions BOB-181, and the
tracker was never synced to this reality, leaving BOB-181 `Queued` against
code that had already fixed it. This is exactly the doc/DB-vs-code drift
class several other items closed this session were.

## Independently verified this session (coordinator, re-running the
subagent's own work from a clean shell)

```
$ git status --short tests/unit/test_generate_markdown_exports_path_arg.sh scripts/generate_markdown_exports.sh
?? tests/unit/test_generate_markdown_exports_path_arg.sh
```
(`scripts/generate_markdown_exports.sh` carries no diff — genuinely untouched.)

```
$ bash tests/unit/test_generate_markdown_exports_path_arg.sh
...
  PASS: explicit-arg run: named target.md WAS converted (sanity — the run is not vacuous)
  PASS: explicit-arg run: no decoy outside the requested scope was touched — run is correctly scoped
  PASS: no-argument run: full-tree sweep behaviour is UNCHANGED (target + decoys all converted)
RESULT: 3 passed, 0 failed
```

```
$ bash tests/unit/test_generate_markdown_exports_path_arg.sh historical
...
  PASS: explicit-arg run: named target.md WAS converted (sanity — the run is not vacuous)
  FAIL: explicit-arg run: a decoy OUTSIDE the requested scope was touched — argument was silently discarded (BOB-181)
  ...
RESULT: 2 passed, 1 failed
```
(RED evidence against the true pre-fix commit content `d61abdf`, embedded
hermetically in the test as a fixture — the real historical defect
genuinely reproduces; the current script genuinely does not.)

## What this session actually added

A permanent §11.4.135 regression guard,
`tests/unit/test_generate_markdown_exports_path_arg.sh`, that: (1) proves
the CURRENT script's argument-scoping behaviour against a fully isolated
`mktemp -d` tree (never touches the real repo tree), (2) proves the
no-argument default (full sweep) is unchanged, (3) carries the true
historical pre-fix script content as an embedded fixture so the defect this
guard protects against can be demonstrated on demand without a live git
history lookup, and (4) is deterministic (3 consecutive identical runs).

## Honest boundary

No source change was made — writing a fabricated "fix" onto code that
already behaves correctly would itself have been a bluff (§11.4.115/§11.4.6).
The genuine gap this session closes is the MISSING regression guard + the
tracker/code attribution drift, not a code defect.

## git diff --stat

```
tests/unit/test_generate_markdown_exports_path_arg.sh | new file, 337 lines
```
