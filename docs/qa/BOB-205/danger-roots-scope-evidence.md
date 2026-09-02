# BOB-205 — closure evidence

**Revision:** 1
**Last modified:** 2026-09-02T11:10:00Z

`cmd/boba-ctl` (the container orchestrator — a shell-exec and mutation surface)
was absent from `DANGER_ROOTS`, so it was never scanned by the danger-root
invariant at all.

Evidence is captured at this TRACKED path deliberately. BOB-127's closure cited
`.superpowers/sdd/…`, an untracked scratchpad that a rate-limited agent never
persisted — the proof was unproducible the moment it was needed (§11.4.226,
§11.4.215). This file is in-repo so the same failure cannot recur here.

## Layer 1 — SOURCE

`scripts/pre_build_verification.sh:1682`

    DANGER_ROOTS=(download-proxy/src plugins scripts qBitTorrent-go frontend/src cmd/boba-ctl)

with the rationale recorded at :1677.

## Layer 2 — RUNTIME (the guard executes and passes)

    $ bash tests/pre_build/test_bob205_danger_roots_scope.sh
    VERDICT: GREEN (primary=PASS secondary=PASS)
    exit 0

## Layer 3 — MECHANIZED

The audit is a standing gate, not a one-off check: invariant 39 in
`scripts/pre_build_verification.sh`. It is ADVISORY by design, so widening the
scope cannot newly block a build — it can only widen what is observed.

## Layer 4 — §1.1 PAIRED MUTATION

Removing `cmd/boba-ctl` from `DANGER_ROOTS` moves the probe needle from 1 hit
back to 0 and both oracles go RED; restoring it returns both to GREEN. The
guard therefore catches its own negation and is not a tautology.

## Honest boundary (§11.4.6)

This closes the SCOPE defect — the orchestrator is now scanned. It does not
assert `cmd/boba-ctl` is free of danger-root findings; that is what the now-
enabled scan reports on each run. The tracker entry's own note stands: a
hand-maintained `DANGER_ROOTS` list has the §11.4.251 shape, and a directory
added tomorrow will be missed just as silently. That structural weakness is
NOT fixed here and remains worth its own item.
