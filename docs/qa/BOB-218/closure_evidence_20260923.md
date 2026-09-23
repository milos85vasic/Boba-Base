# BOB-218 closure evidence — 2026-09-23

## Three defects, all fixed via TDD

**Defect 1** (main — false rollback claim with real downstream harm):
`tools/README.md` claimed "the backup is restored" on write failure;
`shutil.copy2` only ever copied FORWARD (backup creation), never restored
it; the plugin write opened in truncating mode, so a mid-write failure
left a corrupt, non-importable plugin the operator believed was restored.
Fixed by implementing genuine atomicity — new `_atomic_write()` writes to
a private temp file in the target's own directory, then `os.replace()`s it
onto the target (a same-filesystem atomic rename on POSIX); the target is
NEVER opened in truncating mode in the write path, so any failure leaves
it byte-identical to its pre-attempt state. README corrected to describe
this accurately.

**Defect 2** (doc-only): README claimed JSON output goes to stdout; the
code already correctly wrote to a file (`open(args.output, "w")`) — only
the doc claim was wrong (the code needed no fix here). README corrected in
both places it made this claim.

**Defect 3** (signal handling): `_extract_version`'s bare `except:`
silently swallowed `KeyboardInterrupt` during the 14-URL upstream sweep.
Narrowed to `except (OSError, UnicodeDecodeError):`, letting
`KeyboardInterrupt`/`SystemExit` propagate normally (they inherit from
`BaseException`, not `Exception`, so this narrowing alone is sufficient).

## Independently re-verified this session (coordinator)

```
$ .venv/bin/python -m pytest tests/unit/test_bob218_plugin_update_rollback.py -v --import-mode=importlib
... 7 passed in 0.45s

$ .venv/bin/python -m pytest tests/unit/test_bob217_plugin_update_pinned_hash_verification.py -v --import-mode=importlib
... 7 passed in 0.50s
(confirms the earlier BOB-217 supply-chain fix, landed earlier this
session in the same file, is unaffected)

$ .venv/bin/ruff check tools/plugin_update_automation.py
All checks passed!

$ grep -n "_atomic_write\|os.replace" tools/plugin_update_automation.py
234:  ... _atomic_write never opens ...
238:  self._atomic_write(local_path, upstream_content)
250:  def _atomic_write(self, target_path: str, content: str) -> None:
275:  os.replace(tmp_path, target_path)
```
Implementation confirmed present exactly as reported.

## Honest boundary (not silenced)

`_atomic_write`'s temp-file naming (pid + microsecond timestamp) is not
`tempfile.mkstemp`-grade collision-proof — a deliberate, documented
proportionality choice for a single-host, single-invocation developer tool
with no pre-existing concurrent-writer requirement. `os.replace` itself
(a single atomic POSIX syscall) is not separately failure-injected in the
RED test, only the temp-file write step is — judged an acceptable,
lower-priority gap given the specific acceptance criterion ("write to temp
file and rename atomically rather than truncating in place," which is
satisfied).

## git diff --stat

```
tools/README.md                   | 20 +++++++++----
tools/plugin_update_automation.py | 63 +++++++++++++++++++++++++++++++++++++--
2 files changed, 75 insertions(+), 8 deletions(-)
```
Plus new `tests/unit/test_bob218_plugin_update_rollback.py` (7 tests).
