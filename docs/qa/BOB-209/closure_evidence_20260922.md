# BOB-209 closure evidence — 2026-09-22

## Fix (three defects, one function, `scripts/lib/ownership.sh` `probe_location()`)

1. **Asymmetric guards**: both the file branch and the directory/probe branch
   now check `stat`'s exit code AND output emptiness together (previously
   each checked only one half).
2. **Mislabelled verdict**: a `stat` failure (either branch) now echoes
   `stat-failed`, never the semantically-wrong `unwritable` (which stays
   reserved for the case `mktemp` itself could not create the probe — a
   genuine writability finding).
3. **Untrapped cleanup (§11.4.14)**: cleanup moved from a bare `rm -f`
   statement to a `RETURN` trap (covers every `return` path uniformly) plus
   saved/restored INT/TERM/HUP handlers — removes the probe first, restores
   whatever handler the caller already had (`ownership_repair.sh` installs
   its own top-level INT/TERM handlers), then re-raises so the caller's own
   handling still runs exactly as before.

## RED/GREEN evidence (via byte-identical pre-fix source run under the identical harness)

- File-branch empty-output: pre-fix `wrong-owner:` (malformed) → post-fix `stat-failed`.
- File-branch stat failure: pre-fix `unwritable` (mislabel) → post-fix `stat-failed`.
- Dir-branch stat failure leaking garbage output: pre-fix trusted the garbage
  as a uid (`wrong-owner:999999`) → post-fix `stat-failed`.
- Interrupt-between-mktemp-and-cleanup (a real SIGINT, deterministically
  timed via a shimmed `stat` that backgrounds the real stat, writes a
  checkpoint file, then sleeps; the harness polls for the checkpoint then
  signals): pre-fix strands a `.ownership-probe.*` file; post-fix leaves none.

## Independently re-verified this session

```
$ bash tests/unit/test_ownership_probe_location.sh
RESULT: 10 passed, 0 failed, 0 skipped
```

Plus the full `tests/unit/test_ownership_repair.sh` (146/146) and
`tests/pre_build/test_check_cm_ownership_invariants.sh` (42/42).

See `docs/qa/BOB-208/closure_evidence_20260922.md` for the combined
`git diff --stat`.
