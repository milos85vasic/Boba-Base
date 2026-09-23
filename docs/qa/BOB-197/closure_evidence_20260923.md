# BOB-197 closure evidence — 2026-09-23

## Operator decision (already recorded, 2026-08-26)
"Arm BOBA_API_TOKEN and keep 0.0.0.0, backed by a BOOT-TIME invariant that
refuses to start LAN-bound with the token unset." The token was already
generated/armed in `.env` in a prior session; this item is specifically
the still-owed boot-time invariant.

## Defect
`download-proxy/src/main.py`'s `start_fastapi_server()` configured uvicorn
with `MERGE_SERVICE_HOST` defaulting to `0.0.0.0` (LAN-bound) with no
check that `BOBA_API_TOKEN` was armed before serving — the service started
open on a default deployment.

## Fix
New `_refuse_if_lan_bound_and_unarmed(host)` function, called after
`merge_host` is resolved and before the uvicorn server starts. Reuses the
existing `config.proxy._is_loopback` helper (no new closed-set check
invented). Refuses (via `os._exit(1)`, NOT `sys.exit`/`SystemExit`) only
when host is non-loopback AND the token is unset/empty. Uses `os._exit`
specifically because `start_fastapi_server()` runs on a daemon thread —
empirically verified `SystemExit` raised there does NOT terminate the
process (only the daemon thread silently dies while the main thread
continues, the original-proxy thread keeps serving on 7186 with no error —
exactly the partial-boot anti-pattern §11.4.254 exists to prevent).

## Independent verification (coordinator, from clean shell)
```
$ .venv/bin/python -m pytest tests/unit/test_main.py::TestStartFastapiServerBootTimeLanAuthInvariant tests/unit/test_main.py::TestRefuseIfLanBoundAndUnarmed tests/unit/test_main.py::TestMainFastAPIServer -v
14 passed in 2.94s
```
All 4 pre-existing `TestMainFastAPIServer` tests (which the fix's real
`os._exit(1)` would otherwise have silently killed under an unarmed
ambient shell) also pass — confirming the implementing agent's disclosed
regression-fix (arming `BOBA_API_TOKEN` in those tests' env mocks) is
correct.

### RED independently reproduced (via git stash, not trusted from report)
```
$ git stash push -m "..." -- download-proxy/src/main.py
$ .venv/bin/python -m pytest tests/unit/test_main.py::TestStartFastapiServerBootTimeLanAuthInvariant -v
FAILED test_start_fastapi_server_refuses_lan_bound_default_without_token
  Failed: DID NOT RAISE SystemExit
FAILED test_start_fastapi_server_refuses_lan_bound_explicit_without_token
2 failed, 2 passed
$ git stash pop   # byte-identical restore confirmed via py_compile
$ .venv/bin/python -m pytest tests/unit/test_main.py::TestStartFastapiServerBootTimeLanAuthInvariant -q
4 passed
```
Genuine "DID NOT RAISE SystemExit" on the pre-fix code, exactly matching
the defect description — not a synthetic/constructed RED.

### Golden-FALSE both cases confirmed (part of the same 14-test run)
Loopback+token-unset does not refuse; LAN-bound+token-armed does not
refuse (the deployment's actual current happy-path state).

## Note found honestly by the implementing agent, not acted on (out of
   this item's scope): host was under extreme, unrelated resource
   contention throughout this dispatch (4 parallel subagents + this
   coordinator's own gate sweep drove load average to 175+ and swap to
   full exhaustion) — some invocations appeared to stall from pure CPU/
   memory starvation, independently confirmed harmless once contention
   eased. Not a code defect.

## Status
Fixed. Closed by coordinator after independent re-verification, including
a from-scratch RED reproduction distinct from the implementing agent's own
report.
