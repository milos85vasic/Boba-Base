# Quickstart: Validating Operator-Owned Downloads

**Feature**: 002-user-owned-downloads · **Date**: 2026-08-21

Runnable scenarios that prove the feature works end to end. Every check reads a **real
uid off a real file** — never "no error", never a configuration inspection.

## Prerequisites

- Rootless Podman (5.7.1 verified) and podman-compose (1.5.0 verified)
- The operator's own login session; `id -u` is the expected owner throughout
- The stack stoppable via `./start.sh` / `./stop.sh`
- Resource discipline: prefix long runs with `nice -n 19 ionice -c 3` (Principle XIII)

Record the baseline before changing anything:

```bash
id -u                                            # expect 1000
grep "^$(whoami):" /etc/subuid                   # expect 100000:65536 -> maps c-uid N to 100000+N-1
```

## Scenario 0 — Reproduce the defect first (RED)

**This must fail before the fix. If it passes now, stop — the premise is wrong.**

```bash
T=$(mktemp -d ./.ownck.XXXX); chmod 777 "$T"
podman run --rm -e PUID=1000 -e PGID=1000 -v "$PWD/$T":/downloads:Z \
  lscr.io/linuxserver/qbittorrent:latest \
  sh -c 's6-setuidgid abc touch /downloads/probe'
stat -c '%u (%U)' "$T/probe"; rm -rf "$T"
```

**Expected pre-fix**: `100999 (UNKNOWN)` — the reported defect.
**Expected post-fix**: `1000 (<you>)`.

> Run the write through `s6-setuidgid abc`, not a bare `sh -c touch`. A bare `touch`
> executes as the container's **root entrypoint**, lands at uid 1000 either way, and
> makes a broken system look fixed. This exact mistake was made and caught during
> research (research.md R1).

## Scenario 1 — New downloads are owned by you (US1 / FR-001–003 / SC-001)

```bash
./start.sh --recreate          # NOT --reload-python: a restart does not re-read compose
```

Complete one download, then:

```bash
DD=$(grep -E '^QBITTORRENT_DATA_DIR=' .env | cut -d= -f2- | tr -d '"')
find "$DD" -newermt '-10 minutes' -printf '%U %p\n' | sort -u | head
```

**Expected**: every uid is yours. Then prove usability rather than inferring it:

```bash
F=$(find "$DD" -newermt '-10 minutes' -type f | head -1)
mv "$F" "$F.renamed" && mv "$F.renamed" "$F" && echo "RENAME OK"
```

**Expected**: `RENAME OK`, with no elevation and no ownership step.

## Scenario 2 — The backlog is repaired automatically (US2 / FR-004 / SC-003)

With a wrongly-owned backlog present and no repair marker:

```bash
./start.sh --recreate
```

**Expected**: startup blocks with real progress (items processed / discovered), then:

```bash
find "$DD" ! -uid "$(id -u)" | wc -l      # expect 0
find config ! -uid "$(id -u)" | wc -l     # expect 0  (FR-012)
```

**Marker + record**: the marker exists and the change record lists what changed.

**Second start** (FR-004a): no tree walk, no progress output, startup at normal speed.

## Scenario 3 — An interrupted repair resumes (FR-004a — the correctness case)

```bash
./start.sh --recreate &                    # let the repair begin
sleep 5 && ./stop.sh                       # interrupt it mid-run
```

**Expected**: the marker is **absent** (written only on success).

```bash
./start.sh --recreate
```

**Expected**: the repair **resumes** and completes; afterwards `find ... ! -uid $(id -u)`
is 0. If instead the second start skipped the repair, the marker was written at start
rather than on success — the exact defect clarify Q1 closed.

## Scenario 4 — Unusable storage refuses startup (FR-010 / §11.4.201(1))

```bash
scripts/ownership_precondition.sh; echo "exit=$?"     # healthy: expect 0
```

Now point a declared location at storage that cannot produce owned files and re-run.

**Expected**: exit `1`, naming the location and what was wrong. **Both directions matter**
— a precondition that refuses a healthy system is as broken as one that passes a broken
one.

## Scenario 5 — The documented backup becomes possible (FR-013 / SC-007)

This is currently **impossible** and is the sharpest proof the fix landed:

```bash
cp config/boba.db /tmp/boba.db.bak && cp .env /tmp/.env.bak && echo "BACKUP OK"
stat -c '%a %U' config/boba.db
```

**Expected**: `BACKUP OK`, and mode still `600` owned by you — FR-015 forbids the repair
from relaxing it. A backup that succeeded because the file became world-readable is a
**failure**, not a pass.

## Scenario 6 — Every service is covered (FR-016)

```bash
podman compose --profile go up -d
```

Repeat Scenario 1 against the Go profile. **Expected**: identical ownership. A fix applied
to some services and not others returns the defect the moment an uncorrected one runs —
intermittently, which is harder to diagnose than the consistent defect being replaced.

## Scenario 7 — The regression gate has teeth (FR-011 / §1.1)

```bash
bash scripts/pre_build/check_cm_ownership_invariants.sh; echo "exit=$?"   # expect 0
```

Then revert one service's route in `docker-compose.yml` and re-run.

**Expected**: exit `1`. A gate that stays green when the defect is reintroduced is
decoration. Restore the file afterwards and confirm it is byte-identical.

## Full validation

```bash
nice -n 19 ionice -c 3 ./ci.sh
```

**Expected**: the 44-invariant pre-build gate passes, including the new ownership gate.

## Success criteria mapping

| Scenario | Covers |
|---|---|
| 0 | RED baseline (Principle IX / §11.4.115) |
| 1 | SC-001, SC-002 |
| 2 | SC-003, SC-004a |
| 3 | FR-004a resume semantics |
| 4 | FR-010, FR-010b |
| 5 | SC-007, FR-013, FR-015 |
| 6 | FR-016 |
| 7 | SC-006, FR-011 |
| full | SC-004, SC-005 |
