# BOB-096 — Chaos coverage for `qBitTorrent-go/tests/integration/jackett_db_test.go`

**Ticket:** BOB-096
**Scope:** extend the boba-jackett DB integration suite with `§11.4.85`-class
process-death, resource-exhaustion, and concurrent-kill chaos scenarios.
**Date:** 2026-08-19
**Race detector:** clean (`go test -race`, 3× deterministic re-run).

## Scenarios added

| # | Scenario | Test function | §11.4.85 class |
|---|----------|---------------|----------------|
| 1 | Resource-exhaustion — file-descriptor pressure via `os.Pipe()` (bounded per §12.6) | `TestChaos_FileDescriptorExhaustion` | (d) |
| 2 | Concurrent-kill via `context.CancelFunc` from a second goroutine while the first is writing | `TestChaos_ConcurrentContextCancelWrite` | (a-extra) |

## Scenarios already present (kept, referenced for completeness)

| # | Scenario | Test function | §11.4.85 class |
|---|----------|---------------|----------------|
| 3 | Process-kill (SIGKILL of a helper subprocess mid-transaction) | `TestChaos_MidTransactionSIGKILLRecovery` | (a) |
| 4 | Byte-level DB file corruption | `TestChaos_DBFileByteCorruption` | (b) |
| 5 | Concurrent-writer contention (40 goroutines, direct repo layer) | `TestChaos_ConcurrentWriterContentionRepo` | (c) |
| 6 | WAL sidecar corruption + reopen | `TestChaos_WALSidecarCorruptionRecovery` | (a-analogue) |
| 7 | Master-key rotation mid-flight (K1→K2 forward + K1 reverse) | `TestChaos_MasterKeyRotationMidflight` | (e-analogue) |

## §11.4.115 RED-first evidence — captured live

For `TestChaos_ConcurrentContextCancelWrite`, invariant (ii) ("every confirmed
write round-trips") was proven falsifiable by injecting a phantom name
`KILL_PHANTOM` into `finalNames` with no corresponding DB row.

- `RED_phantom_mutation.log` — captures the FAIL:
  `(ii) confirmed-write KILL_PHANTOM lost after cancel: repos: credential not found`
  → `FAIL: TestChaos_ConcurrentContextCancelWrite`
- Mutation reverted; `GREEN_after_restore.log` captures the immediate PASS
  under identical race conditions.

Falsification narratives for the other invariants (i, iii on FD + cancel
tests; all invariants on the pre-existing tests) are recorded in the
per-test doc-comments per §1.1.

## Anti-bluff assertions (§11.4.5 / §11.4.107)

- Byte-equal plaintext round-trip via `Credential.Username`/`Password`,
  not "no error".
- `sql.DB` row count vs writer-confirmed count exact equality.
- Categorised error on FD-pressure Upsert failure (non-empty `err.Error()`).
- Durability boundary: BASELINE / PRECOMMIT rows always survive; uncommitted
  rows never surface.
- Panic guard: every DB access under chaos wrapped in `recover()` → `t.Fatalf`.

## Cleanup (§11.4.14)

- `TestChaos_FileDescriptorExhaustion` closes every `os.Pipe()` pair via
  both `defer cleanup()` and `t.Cleanup(cleanup)` (belt-and-braces).
- `TestChaos_ConcurrentContextCancelWrite` registers `t.Cleanup(cancel)` so
  the context is cancelled even on early test bailout.
- `t.TempDir()` handles DB + evidence-log cleanup automatically.

## Host safety (§12.6, §12.12, §11.4.161)

- FD pressure capped at `min(RLIMIT_NOFILE.soft / 4, 512)` — never
  destabilises the host FD table.
- No `sudo`, no rootful container, no host power-management calls.
- `GOMAXPROCS=2 nice -n 19 ionice -c 3` throughout.

## Determinism (§11.4.50)

Three consecutive `-race -count=3` runs — all GREEN
(`race_detector_3x.log`).

## Run log files

- `bob096_run_verbose.log` — verbose PASS output for the two new tests.
- `full_chaos_suite.log` — full `TestChaos*` suite under `-race`.
- `new_chaos_scenarios.log` — first run of the two additions.
- `RED_phantom_mutation.log` — captured RED (invariant (ii) fails).
- `GREEN_after_restore.log` — GREEN immediately after restoring source.
- `race_detector_3x.log` — 3× deterministic race-clean run.

## Skipped chaos class (honest, tracked)

`§11.4.85 (d) disk-full` remains deferred as a follow-up `§11.4.197` item —
a filesystem-quota fixture belongs in a container-scoped harness rather
than a host-shared test file. Recorded in the test-file doc-comment.
