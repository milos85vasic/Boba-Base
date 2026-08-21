# T026 — interrupt → resume, proven against the real script

**Date**: 2026-08-21 · 4041-item fixture · real `scripts/ownership_repair.sh`

## Why not quickstart Scenario 3 verbatim

Scenario 3 as written is `./start.sh --recreate &` … `./stop.sh` … `./start.sh --recreate`.
That stops and restarts the LIVE stack. Six agents were running and the operator was using
the machine, so the same property was proven against the real script in a sandbox instead.
This is a deviation and it is recorded as one — what is NOT covered by it is the
`start.sh` INTEGRATION (FR-004d blocking-before-services), which remains integration-layer.

## The measurements

Baseline, so "partial" could be aimed rather than hoped for:

```
full uninterrupted pass: rc=0 in 138863ms over 4041 items -> 4041/4041 repaired
```

**Run 1 — interrupt at 60s (a genuine mid-run point, not a pre-start one):**

```
SIGTERM -> pid 3494286 (identity confirmed via /proc/<pid>/cmdline before signalling)
rc=143
repaired so far: 2816/4041   <- genuinely PARTIAL
marker after interrupt: ABSENT
```

A FIRST ATTEMPT WAS INVALID AND IS RECORDED AS SUCH: interrupting after 2s gave
`0 of 4041 repaired` — the script was still walking, so resuming from it would have been an
ordinary fresh run and would have proven nothing about resume. The baseline above is what
made a real mid-run point choosable.

**Run 2 — resume:**

```
wrongly-owned before resume: 1225      <- a FRESH run would see 4041
resume rc=0 in 12s
wrongly-owned after resume: 0
marker after success: PRESENT
```

The `1225` is the load-bearing number. It is the discriminator between RESUMING and
RESTARTING: a script that ignored the partial state would have found 4041 items to do and
taken ~139s, not 12s.

**Run 3 — the marker makes the next start a no-op:**

```
rc=0 in 1s   (vs 138863ms for a full pass)
[ownership-repair] already complete for this scope (marker: logs/ownership/repair-marker.json)
```

## What this establishes

The marker is written ONLY on successful completion. That is the whole point of the
clarification this feature made: a marker written at START would make an interrupted repair
look finished forever, and the backlog would never be repaired — silently, with the system
reporting success.

## Honest notes

- §11.4.263 was observed: the pid was validated as an integer > 1 AND its identity confirmed
  from `/proc/<pid>/cmdline` before any signal. No process group was signalled.
- 138863ms for 4041 items is NOT a representative throughput figure. Six agents were running;
  the authoring agent measured 20,204 items in 33s on a quieter host. The timing here was
  used only to locate a mid-run interrupt point, not as a performance claim.
- Fixture and repair log removed; tree clean.
