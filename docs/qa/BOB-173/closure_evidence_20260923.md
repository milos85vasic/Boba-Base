# BOB-173 closure evidence — 2026-09-23 (staleness-corrected closure)

## Finding
This item was ALREADY FIXED in a prior session (commit `ca0cbf4`,
2026-08-22, "fix(BOB-173): a webhook API that reported success when the
write had failed") — the tracker was simply never synced to reflect it.
Discovered while investigating BOB-174 (whose own evidence pack states it
was measured "on the already-BOB-173-fixed tree").

## Fix (already landed)
`download-proxy/src/api/hooks.py`'s `_save_hooks` no longer swallows every
exception and returns `None` — it now propagates failure so both call sites
(create/delete) can translate a persistence failure into a non-2xx HTTP
response rather than silently reporting success.

## Independent verification (coordinator, from clean shell, 2026-09-23)
```
$ .venv/bin/python -m pytest tests/unit/api_layer/test_bob173_hook_persistence_failure.py -q
..........
10 passed, 1 warning in 1.91s
```
Commit `ca0cbf4` confirms independent review returned GO with zero blocking
and zero important findings at landing time.

## Status
Fixed (already landed, tracker sync only). Closed by coordinator.
