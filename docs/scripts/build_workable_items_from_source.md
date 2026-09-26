# build_workable_items_from_source.sh

**Revision:** 1
**Last modified:** 2026-09-26T13:00:00Z

## Overview

`scripts/pre_build/build_workable_items_from_source.sh` builds the
`workable-items` binary from its **current** Go source and prints the path of
the freshly built file. It never returns a binary that already exists on disk.
Pre-build invariant 17 (`CM-WORKABLE-ITEMS-VALIDATE`) resolves its binary
through this script.

## Why this exists

Invariant 17 used to resolve its binary through a candidate loop whose first
entry was the git-tracked `constitution/scripts/workable-items/bin/workable-items`.
A tracked binary wins that loop on every fresh clone, so the gate ran whatever
an older build could see. On 2026-08-25 the shipped binary was six days behind
its source and lacked the terminal-status guards the source had, so ten
mis-located tracker rows passed the gate (BOB-188).

The operator decision recorded on BOB-188 (2026-08-26) is **build on demand**:
build from source, or refuse when the Go toolchain is absent. Because this
script builds fresh on every call, a stale binary cannot be selected at all.

## Prerequisites

- Go on `PATH` (the same toolchain the `qBitTorrent-go` backend already needs).
- A C compiler for cgo (the tool links `github.com/mattn/go-sqlite3`).
- The `constitution` submodule checked out.

## Usage

```bash
bin="$(bash scripts/pre_build/build_workable_items_from_source.sh)" || rc=$?
"$bin" validate --db docs/workable_items.db
rm -rf "$(dirname "$bin")"      # the caller owns cleanup
```

Override the source directory (used by the test fixture):

```bash
BOBA_WI_SRC_DIR=/path/to/workable-items bash scripts/pre_build/build_workable_items_from_source.sh
```

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | Built; the absolute path of the binary is on stdout |
| 1 | `go build` failed — no path printed |
| 2 | Source directory missing, or it has no `cmd/workable-items` |
| 3 | REFUSED — Go is not on `PATH`; no binary on disk is used instead |

## Edge cases

- A compile error never falls back to an older binary: exit 1 with nothing on stdout.
- A missing toolchain is a refusal (exit 3), and invariant 17 turns it into a
  FAIL, not a silent SKIP.
- The binary lives in a `mktemp -d` directory named `boba-wi-build.*`; invariant
  17 removes only a directory matching that name.

## Internal behaviour

Resolve the source directory, check for `go`, `go build -o <tmpdir>/workable-items
./cmd/workable-items`, verify the output is an executable file, print its path.
A warm Go build cache makes a rebuild take about two seconds (measured
2026-09-26).

## Related scripts

- `scripts/pre_build/check_cm_workable_items_binary_fresh.sh` — invariant 52,
  fingerprint check on the shipped binary, kept as defence-in-depth for as long
  as a shipped binary exists on disk.
- `tests/pre_build/test_build_workable_items_from_source.sh` — RED/GREEN cases,
  a negative control that replays the old candidate loop, and a paired mutation.

## Last verified

2026-09-26 — `bash tests/pre_build/test_build_workable_items_from_source.sh`
reported 6 passed, 0 failed.
