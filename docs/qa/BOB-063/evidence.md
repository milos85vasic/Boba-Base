# BOB-063 — pirateiro test-isolation defense-in-depth — QA evidence

**Revision:** 1
**Last modified:** 2026-06-10T05:12:40Z
**Ticket:** BOB-063 (Task — add pirateiro isolation to conftest; close it as Completed)
**Scope:** QA evidence (§11.4.83 docs/qa, §11.4.115 RED-on-broken polarity proof, §11.4.135 standing regression guard)

## Defect (discovered §11.4.118)
`tests/unit/test_plugin_pirateiro.py:32` registers `sys.modules["pirateiro"] = <plugins/community/pirateiro.py>`
at module-collection scope with no teardown. `pirateiro` was the one root NOT in
`tests/conftest.py` `_POLLUTING_ROOTS`, so `_isolate_download_proxy_modules`' per-test
snapshot captured it and the leak persisted to every later `tests/unit/` test. Benign in the
current suite (real module, no other importer) but a latent masking hazard.

## Root cause (§11.4.6 / §11.4.102 — investigated, not guessed)
Because the stub is in `sys.modules` BEFORE any per-test snapshot, simply adding `pirateiro`
to `_POLLUTING_ROOTS` does NOT fix it — the leak is already inside each test's `saved`
snapshot, so the restore re-adds it. Deferring the injection into a helper broke 22 tests
whose `@patch("pirateiro.retrieve_url")` decorators resolve the target before the test body.

## Fix (conftest-only)
Cache the stub on first sight (`_PIRATEIRO_STUB`), re-register it before pirateiro-file tests
(so their `@patch` setup resolves), and purge it on teardown of every unit test.
`tests/unit/test_plugin_pirateiro.py` left byte-identical.

## RED → GREEN evidence (§11.4.115 polarity switch)
- RED command: `.venv/bin/python -m pytest tests/unit/test_plugin_pirateiro.py tests/unit/test_pirateiro_isolation_guard.py -p no:randomly -q --import-mode=importlib`
- RED (pre-fix): `AssertionError: sys.modules['pirateiro'] leaked into this test (value: <module 'pirateiro' from '.../plugins/community/pirateiro.py'>)` → **1 failed, 44 passed**
- GREEN (post-fix, same command): **45 passed in 0.65s**
- Negation proof (§11.4.115): with the `sys.modules.pop("pirateiro", None)` teardown line disabled, the guard FAILS again (`1 failed, 44 passed`); restored → passes. The guard is not a tautology.
- Full unit suite (default seed): **4122 passed, 3 warnings in 266.03s** (4121 + 1 new guard)
- Full unit suite (`--randomly-seed=42`): **4122 passed, 3 warnings in 269.13s** (order-independent)

## Standing regression guard (§11.4.135)
`tests/unit/test_pirateiro_isolation_guard.py` — permanent test asserting `"pirateiro" not in
sys.modules` at the start of a fresh unit test; FAILS pre-fix, PASSES post-fix.

## Code review
Reviewed under §11.4.125/§11.4.134/§11.4.142 before commit — see the session commit's GO.
