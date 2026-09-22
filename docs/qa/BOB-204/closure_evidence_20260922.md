# BOB-204 closure evidence — 2026-09-22

## Finding

BOB-204 ("Credential DELETE reports 204 success while the .env plaintext
delete error is discarded — credential survives on disk") was already fixed
at `main` HEAD `a66188d` ("feat(release): harden magnet-hash validation,
credential-delete safety, LAN auth, systemd reboot-survival"), landed in a
prior session before `docs/Issues.md` was updated to reflect it — a tracker
staleness gap, not an open defect.

Independently re-verified this session by a dedicated subagent via
reproduce-then-restore (no working-tree changes were made or left behind;
`git diff --stat` on `qBitTorrent-go/` returned empty before and after).

## Fix location (current HEAD)

`qBitTorrent-go/internal/jackettapi/credentials.go`:

- **DELETE handler** (`HandleDeleteCredential`, lines 261-328): Jackett
  cascade error checked (288-297, returns `502 jackett_cascade_failed`),
  `envfile.Delete` error checked AND read-back-verified (299-319, returns
  `500 env_delete_failed` / `500 env_delete_unverified`), DB delete error
  checked (322-325); `204` emitted only at line 327 after all three succeed.
- **Rollback claim honesty** (`HandleUpsertCredential` lines 192-204;
  `rollbackCredential` lines 406-447): the rollback's own error is checked
  (`rbErr`); response code is `env_write_failed_db_rollback_failed` when the
  rollback itself couldn't be verified, vs. `env_write_failed_db_rolled_back`
  only when `rollbackCredential` re-reads the row and confirms every field
  (kind/username/password/cookies) genuinely matches the pre-call snapshot
  (lines 429-446).

## RED evidence (pre-fix behaviour, reproduced by temporarily restoring the
commit immediately before the fix, `git show 4b54e99:...`, then restoring
current HEAD byte-for-byte afterward — verified via empty `git diff --stat`)

Command: `cd qBitTorrent-go && GOMAXPROCS=2 go test ./internal/jackettapi/... -run 'BOB204' -v`

```
=== RUN   TestRED_BOB204_DeleteFailOpenLeavesCredentialOnDisk
    bob204_failclosed_test.go:137: FAIL-OPEN (§11.4.252): DELETE returned 204 No Content while RUTRACKER_USERNAME and RUTRACKER_PASSWORD are STILL PRESENT in .env (db row removed=true). The operator is told the credential is deleted while the plaintext remains on disk.
--- FAIL: TestRED_BOB204_DeleteFailOpenLeavesCredentialOnDisk (0.01s)
=== RUN   TestRED_BOB204_DeleteFailOpenOnJackettCascade
    bob204_failclosed_test.go:196: FAIL-OPEN (§11.4.252): DELETE returned 204 while the Jackett cascade delete failed (HTTP 500) — indexer rutracker-idx is left configured at Jackett against a credential reported deleted
--- FAIL: TestRED_BOB204_DeleteFailOpenOnJackettCascade (0.01s)
=== RUN   TestRED_BOB204_RollbackClaimIsFalse
    bob204_failclosed_test.go:255: FALSE ROLLBACK CLAIM (§11.4/§11.4.6): response asserts `env_write_failed_db_rolled_back`, but the DB row still carries the username the failed request introduced (has_username=true, prior was false). The compensating Upsert no-ops on nil fields (COALESCE keeps the new value) so it returns no error to check.
--- FAIL: TestRED_BOB204_RollbackClaimIsFalse (0.00s)
--- PASS: TestGOLDENFALSE_BOB204_HealthyPathsUnaffected (0.00s)
--- PASS: TestPOSITIVE_BOB204_HealthyJackettCascadeStillDeletes (0.01s)
--- PASS: TestPOSITIVE_BOB204_RollbackRestoresOverwrittenValue (0.00s)
FAIL
FAIL	github.com/milos85vasic/qBitTorrent-go/internal/jackettapi	0.038s
```

## GREEN evidence (current HEAD, restored byte-identical)

```
=== RUN   TestRED_BOB204_DeleteFailOpenLeavesCredentialOnDisk
--- PASS: TestRED_BOB204_DeleteFailOpenLeavesCredentialOnDisk (0.01s)
=== RUN   TestRED_BOB204_DeleteFailOpenOnJackettCascade
--- PASS: TestRED_BOB204_DeleteFailOpenOnJackettCascade (0.01s)
=== RUN   TestRED_BOB204_RollbackClaimIsFalse
--- PASS: TestRED_BOB204_RollbackClaimIsFalse (0.01s)
=== RUN   TestGOLDENFALSE_BOB204_HealthyPathsUnaffected
--- PASS: TestGOLDENFALSE_BOB204_HealthyPathsUnaffected (0.02s)
=== RUN   TestPOSITIVE_BOB204_HealthyJackettCascadeStillDeletes
--- PASS: TestPOSITIVE_BOB204_HealthyJackettCascadeStillDeletes (0.02s)
=== RUN   TestPOSITIVE_BOB204_RollbackRestoresOverwrittenValue
--- PASS: TestPOSITIVE_BOB204_RollbackRestoresOverwrittenValue (0.01s)
PASS
ok  	github.com/milos85vasic/qBitTorrent-go/internal/jackettapi	0.079s
```

## Negative control (golden-FALSE)

`TestGOLDENFALSE_BOB204_HealthyPathsUnaffected` passes both before and after
— proves the fix does not fail-closed on the healthy path.
`TestPOSITIVE_BOB204_HealthyJackettCascadeStillDeletes` and
`TestPOSITIVE_BOB204_RollbackRestoresOverwrittenValue` additionally prove the
working-cascade and true-rollback-restore branches, both PASS.

## Full scoped package suite

`go test ./internal/jackettapi/... -v` — all tests in the package (60+,
including unrelated ones) PASS.

## Working-tree state

`git status --porcelain` and `git diff --stat` both empty for
`qBitTorrent-go/` before and after this verification — no code changes were
needed or made this session.

## Test files (pre-existing, tracked, reachable via `git log` back to `5c9b9e0`)

- `qBitTorrent-go/internal/jackettapi/bob204_failclosed_test.go` — 3 RED tests
- `qBitTorrent-go/internal/jackettapi/bob204_positive_test.go` — 2 positive-path proofs
