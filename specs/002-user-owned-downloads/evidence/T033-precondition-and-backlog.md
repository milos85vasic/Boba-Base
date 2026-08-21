# Startup precondition GREEN — and a finding that changes what US2 can be validated against

**Date**: 2026-08-21

## The precondition (T033)

`scripts/ownership_precondition.sh` — 20 passed / 0 failed / **0 skipped** (re-run
independently, not taken from the agent's report). Against the real scope:

```
  - .../Downloads:      OK (P2 host write and P1 in-container write both landed at uid 1000)
  - .../boba/config:    OK (P2 host write and P1 in-container write both landed at uid 1000)
  - .../config/boba.db: OK (declared file, owned by uid 1000; no write probe applies)
  OWNERSHIP-PRECONDITION: OK   exit=0
```

It PROBES rather than infers — it writes a real file and reads the owner back. Ownership of
a location cannot be read off the location itself: a directory owned by the operator can
still receive files owned by someone else, which is exactly the defect this feature exists
to fix.

### A real bug the green suite could not see

After the suite went green, running the script against the REAL scope produced
`no compose service mounts this location` for `config/` and the download root — while five
services mount them. Cause: TAB is an IFS **whitespace** character, so
`IFS=$'\t' read -r a b c d e` COLLAPSES runs of tabs, and a row with empty middle fields
(a `build:` service has no `image:`; a route-B service has no `keep-id`) shifts every later
column into oblivion:

```
collapsing read -> a=[svc] b=[/a,/b] c=[] d=[] e=[]
readarray -d     -> a=[svc] b=[]     c=[] d=[] e=[/a,/b]
```

The unit fixtures contain no compose service at all, so **only the real invocation could
expose it**. A green suite is not the same as a working script; this is the §11.4.108
SOURCE-green-is-not-RUNTIME-green gap inside a single file.

## SC-007 / FR-013 — the documented backup is now possible

Previously impossible: the operator could not read their own credential store.

```
mode=600 owner=milosvasic(1000)  config/boba.db
BACKUP OK (81920 bytes)
mode still 600
```

The mode check is not decoration. A backup that succeeded because the file had become
world-readable would be a **failure**, not a pass — it would trade a usability defect for a
security one (FR-015).

## THE FINDING: on this host the wrongly-owned backlog is already ZERO

```
config                 262 items,    0 NOT operator-owned
.../Downloads         6458 items,    0 NOT operator-owned
```

**Control needle first** (§11.4.201(7)) — a zero from an unvalidated instrument is not
evidence, and a blind scan and a clean tree return the identical quiet zero. A file was
planted at a mapped uid via `podman unshare chown`:

```
planted file owner (host view): 100998
find ! -uid 1000 detects it?   YES (1) — instrument PROVEN seeing
rc=0  stderr=0 bytes
```

So the zeros are real. Two causes, both measured:

1. `config/` — the linuxserver s6 init chowns its `/config` tree to `PUID:PGID` on every
   boot. With `PUID=0` that resolves to host uid 1000, so the recreate in T014 repaired
   those 262 items as a **side effect of the US1 fix**. Container log confirms the identity
   took: `User UID: 0 / User GID: 0`.
2. The download root was already almost clean — the pre-fix census recorded 6458 items at
   uid 1000 and **1** at 100999.

### What this means for US2, stated honestly

US2 (repair pre-existing wrongly-owned content, FR-004) **cannot be validated against a real
backlog on this host, because there is no longer one to repair.** That is a genuine coverage
boundary, not a pass:

- quickstart Scenario 2 is not runnable here as written.
- The repair's validation therefore rests on `tests/unit/test_ownership_repair.sh`
  (7 cases / 22 assertions), which was itself proven passable against a reference
  implementation before any implementation existed.
- The feature is still warranted: other hosts, restored backups, and content written before
  the fix all still need it. Deleting US2 because this host happens to be clean would be
  fixing the measurement rather than the problem.

### One benign warning worth documenting

`usermod: user abc is currently used by process 1` appears at boot under `PUID=0`. It is
NOT a failure — `id -u abc` returns 0, so the identity change took, and the write probe
confirms files land at host uid 1000. Recorded so a future reader does not misread it as
the fix failing.

---

## ADDENDUM — the repair's real-uid fallback is no longer unproven

The T019 agent recorded an honest gap: `podman unshare chown` runs only after a plain
`chown` fails, and NOTHING in the unit suite can reach that branch, because an unprivileged
process cannot create a foreign-uid fixture. It therefore shipped with no machine evidence,
and the agent correctly refused to claim it worked.

That fixture IS constructible — via `podman unshare chown`, the same mechanism the control
needle used. Built and run:

```
BEFORE   items NOT operator-owned: 6      (uid 100999 — operator CANNOT delete them)

[ownership-repair] operator 1000:1000; scope .../scope.yaml (2 declared locations)
[ownership-repair] 1/2 .../downloads: 4/4 items processed
[ownership-repair] 2/2 .../config:    2/2 items processed
[ownership-repair] complete: 6 item(s) repaired
exit=0

AFTER    items NOT operator-owned: 0
         operator can now delete? YES
```

The change record is real and machine-parseable — 6 lines, 0 malformed, carrying the exact
defect signature rather than a generic success message:

```
{'path': '.../downloads',           'previous_uid': 100999, 'new_uid': 1000, 'outcome': 'changed'}
{'path': '.../downloads/movie.mkv', 'previous_uid': 100999, 'new_uid': 1000, 'outcome': 'changed'}
{'path': '.../downloads/sub',       'previous_uid': 100999, 'new_uid': 1000, 'outcome': 'changed'}
```

Marker keys: `completed_at`, `items_changed`, `scope_fingerprint` — E2 satisfied.

The fixture's validity was itself checked before trusting the result: the operator was
confirmed UNABLE to delete a planted file beforehand. A fixture the operator could already
delete would not have been the defect, and repairing it would have proven nothing.

Fixture and test log removed afterwards; tree clean.
