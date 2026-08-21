# T013 — startup timing baseline, captured BEFORE any compose change

**Measured**: 2026-08-21 · host: this workstation · runtime: rootless podman

| what | value |
|---|---|
| `./start.sh --recreate` wall clock | ~42s (command return) |
| `qbittorrent-proxy` reaches `healthy` | +68s after return |
| **total cold start → healthy** | **110s** |

## Why this had to be captured first

SC-005 caps the added startup cost of the ownership precondition (FR-010). A cap is
meaningless without the number it is measured against, and that number must come from the
UNMODIFIED configuration — once `PUID`/`userns_mode` change, every later measurement
includes the change being assessed.

The task list numbered this task AFTER the compose edits (T008–T012). That ordering is
wrong and was corrected at execution time: editing compose does not alter the running
system (only `--recreate` does), but it does mean any baseline taken afterwards would have
had to come from a stashed tree — measuring a state that no longer exists on disk. Captured
here instead, with the tree verifiably unmodified (`git diff --stat docker-compose.yml`
empty) and the stack cold (7187 → HTTP 000).

## Honest scope (§11.4.6)

One run, one host. This is a REFERENCE POINT for the SC-005 delta, not a performance
characterisation — a single sample cannot separate the precondition's cost from ordinary
run-to-run variance. T035 re-measures under the same conditions and compares; if the delta
approaches the cap, the correct response is more samples, not a louder claim from this one.
