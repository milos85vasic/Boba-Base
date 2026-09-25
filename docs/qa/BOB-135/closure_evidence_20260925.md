# BOB-135 — closure evidence: full bulk-suite verification (2026-09-25)

**Item:** BOB-135 — Test isolation: `test_list_hooks_after_create` fails in bulk
suite (Permission denied `/config`).

**Fix (already landed, prior session):** commit `dc85a9a25d772bd95037428b71ee7fcfb38ef42e`
— `fix(BOB-135): the permanent guard for a defect that hid behind a swallowed
exception`. Root cause: importing `api.hooks` sets both
`sys.modules["api.hooks"]` and `sys.modules["api"].hooks`; a test that purges
and re-imports (`api_layer/test_hooks_coverage.py`) repoints both at a fresh
module, and under pytest 9.1.1's `monkeypatch.resolve()` this silently
desynced the two references for the rest of the session, causing a later
test's write to hit a stale module whose fixture-patched `/config` path had
already been torn down — surfacing as a misleading `PermissionError:
/config` (the swallowed exception's side effect, not its cause). Guard added:
`tests/unit/test_module_attr_isolation_guard.py`.

**This round's verification task:** confirm the fix holds under the actual
adversarial condition it targets — bulk-suite execution with randomized test
order (`pytest-randomly`) across the FULL unit suite, not just the guard file
in isolation.

## Command

```
timeout 2700 .venv/bin/python3 -m pytest tests/unit --import-mode=importlib -q \
  --timeout=60 -p randomly --randomly-seed=12345 -rf
```

## Result

```
FAILED tests/unit/test_bob129_slowapi_response_contract.py::TestDecoratedEndpointContract::test_every_decorated_endpoint_declares_response_or_is_exempt
FAILED tests/unit/test_bob192_fail_open_skip_remediation.py::test_download_magnet_fails_when_qbit_refuses_add
2 failed, 5027 passed, 4 skipped, 5 warnings in 1645.72s (0:27:25)
```

**BOB-135's own tests are NOT in the failure list** — `test_list_hooks_after_create`
(`tests/unit/api_layer/test_hooks_endpoints.py`) and
`test_module_attr_isolation_guard.py` (the new permanent guard) both ran and
passed among the 5027 passed, under this exact adversarial random-seed
bulk-suite ordering that originally exposed the defect. `pytest -q` prints
only `.` for a pass and an explicit `FAILED` line per failure — their absence
from the FAILED list is the positive evidence, cross-checked against the
`-rf` (re-list-failures) summary which enumerates every failure by name.

## The 2 unrelated failures — investigated, not waved past (§11.4.4)

Both failures reproduce in isolation (order-independent, not a bulk-suite
artifact) and are genuine, pre-existing regressions on already-closed items,
unrelated to BOB-135's defect class:

1. **BOB-129 regression** (reopened + refixed this session, see
   `docs/qa/BOB-129/reopen_20260925.md`): commit `1ef4246` (BOB-167) decorated
   `stream_theme` with `@_rl("sse_stream")` without adding it to BOB-129's
   `_RESPONSE_RETURNING_EXEMPTIONS` set. Fixed by adding the exemption entry
   (the endpoint's single return path is a `StreamingResponse`, same shape as
   the already-exempted `search_stream`). RED→GREEN→RED→GREEN proof in the
   linked evidence file.

2. **BOB-241 test-wiring drift** (new item, filed + closed this session, see
   `docs/qa/BOB-192/test_wiring_fix_20260925.md`): BOB-234 added a mandatory
   `api_token` fixture parameter to
   `TestDownloadEndpoint.test_download_magnet_added_to_real_qbittorrent`; a
   direct plain-call site in `test_bob192_fail_open_skip_remediation.py`
   (bypassing pytest fixture injection) was never updated. Fixed by passing a
   placeholder token (the mock server performs zero token validation).

Both fixes independently re-verified by the conductor: combined run of both
touched files —

```
27 passed, 1 warning in 12.06s
```

## Verdict

BOB-135's fix holds under the exact adversarial condition (bulk-suite,
randomized order, full unit tree) that originally exposed the defect. The two
other failures surfaced by the same run were unrelated pre-existing
regressions, independently root-caused, fixed, and verified this session.

Closing BOB-135 as Completed.
