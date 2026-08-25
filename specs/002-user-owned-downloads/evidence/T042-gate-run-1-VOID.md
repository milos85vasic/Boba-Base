# T042 — full 49-invariant gate, run 1: VOID on one invariant

**Revision:** 1
**Last modified:** 2026-08-23T11:40:00Z

## Verdict

`=== Result: 43 passed, 1 failed ===`

The single FAIL is **invariant 30, `CM-BASH-UNIT-TESTS-EXECUTED`**:

```
FAIL [1]: CM-BASH-UNIT-TESTS-EXECUTED: 1 tracked file(s) mtime-moved while the
bash suite ran: download-proxy/src/merge_service/search.py
      Either a suite restored with plain 'cp' where 'cp -p' is required (content AND
      mtime must be put back), or the tree was not quiescent — a concurrent editor
      wrote to it mid-run (§11.4.84). Re-run on a quiescent tree to tell them apart.
```

## This is a TRUE POSITIVE, and the cause is mine

The gate offered two hypotheses and told me how to separate them. Separated:

| Check | Result |
|---|---|
| `git diff --stat` on the file | empty |
| `git status --porcelain` on the file | empty |
| file mtime | `2026-08-23 11:37:01` |
| gate finish | `~11:38` |

Content is **byte-identical to HEAD** — so it is not the `cp`-vs-`cp -p` hypothesis.
It is the second one: **the tree was not quiescent.** The BOB-172 reviewer was
mid-way through its RED reconstruction (swap in HEAD's pre-fix `search.py`, run,
restore) and its restore landed at 11:37:01, inside the gate's window.

I launched the gate having checked the wrong quiescence signal — `pgrep` for a
running `pre_build_verification` and a count of dirty paths — while four subagents
were live and one had already told me it was about to swap that exact file.
My own memory note says the long gate needs a quiescent tree; I checked
process-quiescence and called it tree-quiescence. Those are different properties.

**The verdict on invariant 30 is VOID, not FAILED-as-a-product-defect.** The other
43 invariants passed, but the run as a whole was taken against a moving tree, so
T042 is **NOT complete** — it must re-run once the four streams finish.

## Second finding: the harness exit code is the LAUNCHER's, not the gate's

The background-task notification reported **exit code 0** while the gate reported
1 failure. `scripts/pre_build_verification.sh:1831-1834` is correct:

```bash
if [[ "${FAIL_COUNT}" -gt 0 ]]; then
    exit 1
fi
exit 0
```

verified by control (`FAIL_COUNT=1` through that construct yields exit 1). The
gate exits 1. The 0 came from the backgrounded launcher, which returns
immediately and reports its own status — the §11.4.201(12) shape at the
task-harness layer.

**Operational rule this establishes: never read a backgrounded gate's verdict
from the harness exit code. Read the log.** Had I trusted the notification I
would have recorded a clean T042 pass over a run with a FAIL in it.

## Owed

Re-run T042 on a genuinely quiescent tree — no live subagents, not merely no
running gate — and verify invariant 30 goes green.
