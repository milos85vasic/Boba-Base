# BOB-174 closure evidence — 2026-09-23 (staleness-corrected closure)

## Finding
This item was ALREADY FIXED in a prior session (commits `5eb2781` +
`80a8750`, landed by 2026-09-01 per the pre-existing evidence pack's file
timestamps) — the tracker was simply never synced to reflect it. Discovered
while surveying the open backlog and cross-checking BOB-174's own text
against current source.

## Fix (already landed)
Full existing evidence at `docs/qa/BOB-174/EVIDENCE.md` (Revision 2,
§11.4.44 header, 378+ lines) + `docs/qa/BOB-174/DESIGN_DECISION.md`, both
with HTML/PDF/DOCX exports already present. Source (`download-proxy/src/api/hooks.py`)
carries explicit in-code citations:
- `_load_hooks` raises `HookStoreCorruptError` distinguishing MISSING (empty
  list, unchanged behaviour) from CORRUPT (explicit error) — closes A1.
- `_save_hooks` uses tmp-file + os.replace atomic write, reusing
  `theme_state.py`'s existing `_write_atomic` pattern (§11.4.28) — closes A5.
- create/delete refuse rather than destroy on a corrupt store — closes A2.
- A3 (VALID_EVENTS/HookEventType drift guard) addressed per commit history.

## Independent verification (coordinator, from clean shell, 2026-09-23)
```
$ .venv/bin/python -m pytest tests/unit/api_layer/test_bob174_corrupt_hook_store.py -q
...................................
35 passed, 1 warning in 5.65s
```
The pre-existing evidence pack's own Revision 2 records that an independent
review found zero defects in the shipped code (only in the evidence pack's
own stale figures, which were corrected in place — a transparency the
document itself documents).

## Status
Fixed (already landed, tracker sync only). Closed by coordinator.
