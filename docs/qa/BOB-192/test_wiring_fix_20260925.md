# BOB-192 test-wiring fix — stale direct-call site after BOB-234 signature change

**Revision:** 1
**Last modified:** 2026-09-25T11:02:42Z

## Discovery

Found during a full bulk pytest run (5033 tests, random seed 12345) and confirmed
via an isolated re-run of the specific test — order-independent, reproduces every
time. This is a **test-wiring bug, not a product defect**.

## Root cause

`tests/unit/test_bob192_fail_open_skip_remediation.py::test_download_magnet_fails_when_qbit_refuses_add`
calls the real integration test's method **body** directly for reuse, bypassing
pytest's normal fixture injection:

```python
t = merge_api_mod.TestDownloadEndpoint()
_must_fail_not_skip(
    lambda: t.test_download_magnet_added_to_real_qbittorrent(srv.url, srv.url, requests.Session())
)
```

The target method,
`TestDownloadEndpoint.test_download_magnet_added_to_real_qbittorrent`
(`tests/integration/test_merge_api.py:524`), has signature:

```python
def test_download_magnet_added_to_real_qbittorrent(self, merge_url, qbit_url, session, api_token):
```

`api_token` is normally injected by pytest via the `api_token` fixture
(`tests/integration/test_merge_api.py:101-109`), which resolves a real
`BOBA_API_TOKEN` against a live service. This parameter was added as part of the
BOB-234 fix — a real security fix where an unauthenticated torrent-delete cleanup
call was silently getting 401'd and leaving the test torrent behind on the real
qBittorrent instance (see the comment directly above the `finally:` block in the
target method, citing BOB-234).

Because the bob192 call site invokes the method as a **plain function call** (not
through pytest, so no fixture injection happens), it was never updated when
`api_token` was added to the signature. It now fails with:

```
TypeError: TestDownloadEndpoint.test_download_magnet_added_to_real_qbittorrent() missing 1 required positional argument: 'api_token'
```

### Verification that this is a pure test-wiring fix

Independently confirmed (read both files, did not skip verification per
§11.4.6/§11.4.102 of this project's constitution):

1. `api_token`'s only use inside the target method is in the `finally:` cleanup
   block: `qbit_delete_confirmed(session, qbit_url, random_hash, api_token, before)`
   (`tests/integration/test_merge_api.py:556`).
2. `qbit_delete_confirmed` (`tests/integration/merge_api_auth.py:161-199`) uses
   the token only as an HTTP header (`{TOKEN_HEADER: token}`) sent to
   `/api/v2/torrents/delete` on the qBittorrent proxy — no other use.
3. The bob192 test's local mock `serve()` fixture
   (`tests/unit/test_bob192_fail_open_skip_remediation.py:59-109`) stubs
   `("POST", "/api/v2/torrents/delete"): (200, "", {})` as a bare static
   `(status, body, headers)` tuple. The `_Server`/`H` handler
   (`_serve` method, lines 67-80) never inspects request headers at all — it
   reads the body length, looks up the route by `(method, path)`, and returns
   the fixed response. **Zero token validation of any kind.**
4. Additionally, `before = qbit_snapshot_hashes(session, qbit_url, api_token)`
   (called before the delete cleanup path is even reached) does a `GET` to
   `/api/v2/torrents/info`, which has no route stub in this test, so it falls
   through to the handler's default `(404, "not found", {})` — making
   `qbit_snapshot_hashes` return `None`, which disarms the delete entirely
   (`qbit_delete_confirmed`'s `if before is None: return`). The delete-cleanup
   code path is not even exercised in this specific test scenario, but the
   token-validation-absence finding above holds regardless.

Since the mock server performs zero token validation on the path where the token
would matter, any placeholder string value is behaviorally correct — this
confirms the fix is a pure test-wiring correction, not a question of product
behavior.

## Other stale call sites (step 3)

Searched the whole `tests/` tree:

```
$ grep -rn "test_download_magnet_added_to_real_qbittorrent" tests/
tests/unit/test_bob192_fail_open_skip_remediation.py:201:        lambda: t.test_download_magnet_added_to_real_qbittorrent(srv.url, srv.url, requests.Session(), "test-token")
tests/integration/test_merge_api.py:524:    def test_download_magnet_added_to_real_qbittorrent(self, merge_url, qbit_url, session, api_token):
```

Only one call site exists (the one fixed here). Also cross-checked every other
direct plain-function-call site in
`tests/unit/test_bob192_fail_open_skip_remediation.py` against its target's
current signature (`_qbit_login`, `test_search_finds_real_results_for_common_query`,
`_merge_service_required`, `_run_live_search`, `_services_up.__wrapped__`) — all
match their current target signatures. No other stale-signature call sites found.

## Fix

`tests/unit/test_bob192_fail_open_skip_remediation.py` — added the missing 4th
positional argument (`"test-token"`, a clearly-labeled placeholder never
validated by the stub server) plus an inline comment explaining why:

```diff
     t = merge_api_mod.TestDownloadEndpoint()
     _must_fail_not_skip(
-        lambda: t.test_download_magnet_added_to_real_qbittorrent(srv.url, srv.url, requests.Session())
+        # This call bypasses pytest fixture injection (plain method call, not a
+        # collected test), so the real `api_token` fixture never runs. The
+        # value below is a placeholder: the stubbed `/api/v2/torrents/delete`
+        # route above does zero token validation, so any string is behaviorally
+        # correct here (BOB-234 added `api_token` for the real service's auth,
+        # not for this mock).
+        lambda: t.test_download_magnet_added_to_real_qbittorrent(srv.url, srv.url, requests.Session(), "test-token")
     )
```

## Evidence — before

```
$ .venv/bin/python -m pytest tests/unit/test_bob192_fail_open_skip_remediation.py::test_download_magnet_fails_when_qbit_refuses_add -v
...
tests/unit/test_bob192_fail_open_skip_remediation.py::test_download_magnet_fails_when_qbit_refuses_add FAILED [100%]

=================================== FAILURES ===================================
_______________ test_download_magnet_fails_when_qbit_refuses_add _______________

merge_api_mod = <module '_bob192_merge_api' from '/home/milosvasic/Projects/boba/tests/integration/test_merge_api.py'>
serve = <function serve.<locals>._start at 0x7506540afec0>

    def test_download_magnet_fails_when_qbit_refuses_add(merge_api_mod, serve):
        srv = serve(
            {
                ("POST", "/api/v1/download"): _json(200, {"status": "failed", "added_count": 0, "results": []}),
                ("POST", "/api/v2/torrents/delete"): (200, "", {}),
            }
        )
        t = merge_api_mod.TestDownloadEndpoint()
>       _must_fail_not_skip(
            lambda: t.test_download_magnet_added_to_real_qbittorrent(srv.url, srv.url, requests.Session())
        )

tests/unit/test_bob192_fail_open_skip_remediation.py:200:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
tests/unit/test_bob192_fail_open_skip_remediation.py:128: in _must_fail_not_skip
    fn()
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

>       lambda: t.test_download_magnet_added_to_real_qbittorrent(srv.url, srv.url, requests.Session())
                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    )
E   TypeError: TestDownloadEndpoint.test_download_magnet_added_to_real_qbittorrent() missing 1 required positional argument: 'api_token'

tests/unit/test_bob192_fail_open_skip_remediation.py:201: TypeError
=========================== short test summary info ============================
FAILED tests/unit/test_bob192_fail_open_skip_remediation.py::test_download_magnet_fails_when_qbit_refuses_add
============================== 1 failed in 0.66s ===============================
```

## Evidence — after

```
$ .venv/bin/python -m pytest tests/unit/test_bob192_fail_open_skip_remediation.py::test_download_magnet_fails_when_qbit_refuses_add -v
...
tests/unit/test_bob192_fail_open_skip_remediation.py::test_download_magnet_fails_when_qbit_refuses_add PASSED [100%]

============================== 1 passed in 0.74s ==============================
```

## Full-file regression check (after)

```
$ .venv/bin/python -m pytest tests/unit/test_bob192_fail_open_skip_remediation.py -v
...
collected 20 items

tests/unit/test_bob192_fail_open_skip_remediation.py::test_scaling_gate_still_skips_when_port_closed PASSED [  5%]
tests/unit/test_bob192_fail_open_skip_remediation.py::test_merge_required_accepts_healthy PASSED [ 10%]
tests/unit/test_bob192_fail_open_skip_remediation.py::test_download_magnet_fails_when_qbit_refuses_add PASSED [ 15%]
tests/unit/test_bob192_fail_open_skip_remediation.py::test_merge_required_still_skips_when_unreachable PASSED [ 20%]
tests/unit/test_bob192_fail_open_skip_remediation.py::test_search_common_query_fails_on_empty_result_set PASSED [ 25%]
tests/unit/test_bob192_fail_open_skip_remediation.py::test_jackett_ready_still_skips_when_unreachable PASSED [ 30%]
tests/unit/test_bob192_fail_open_skip_remediation.py::test_jackett_ready_fails_on_answered_redirect_loop PASSED [ 35%]
tests/unit/test_bob192_fail_open_skip_remediation.py::test_qbit_login_accepts_modern_204_with_cookie PASSED [ 40%]
tests/unit/test_bob192_fail_open_skip_remediation.py::test_merge_required_fails_on_unhealthy_status_field PASSED [ 45%]
tests/unit/test_bob192_fail_open_skip_remediation.py::test_live_search_fails_when_search_never_terminates PASSED [ 50%]
tests/unit/test_bob192_fail_open_skip_remediation.py::test_merge_required_fails_on_answered_500 PASSED [ 55%]
tests/unit/test_bob192_fail_open_skip_remediation.py::test_jackett_ready_fails_on_answered_500 PASSED [ 60%]
tests/unit/test_bob192_fail_open_skip_remediation.py::test_jackett_ready_fails_on_answered_404 PASSED [ 65%]
tests/unit/test_bob192_fail_open_skip_remediation.py::test_merge_required_fails_on_non_health_body PASSED [ 70%]
tests/unit/test_bob192_fail_open_skip_remediation.py::test_qbit_login_fails_on_answered_rejection PASSED [ 75%]
tests/unit/test_bob192_fail_open_skip_remediation.py::test_scaling_gate_fails_on_answered_unhealthy_healthz PASSED [ 80%]
tests/unit/test_bob192_fail_open_skip_remediation.py::test_scaling_gate_accepts_healthy PASSED [ 85%]
tests/unit/test_bob192_fail_open_skip_remediation.py::test_live_search_returns_terminal_payload PASSED [ 90%]
tests/unit/test_bob192_fail_open_skip_remediation.py::test_qbit_login_fails_on_answered_403 PASSED [ 95%]
tests/unit/test_bob192_fail_open_skip_remediation.py::test_live_search_fails_when_poll_answers_500 PASSED [100%]

============================= 20 passed in 10.98s ==============================
```

20/20 passed. Zero regressions.

## Scope

Only `tests/unit/test_bob192_fail_open_skip_remediation.py` was modified.
`tests/integration/test_merge_api.py` was read for verification only, not
modified — its `api_token` fixture and the target method's signature are
correct as-is; the bug was entirely in the unit-test call site.
