# BOB-192 — remediation evidence for the 10 ratcheted CM-NO-FAIL-OPEN-SKIP findings

**Revision:** 1
**Last modified:** 2026-09-23T17:19:25Z

| Field | Value |
|---|---|
| Item | BOB-192 (NOT closed by this document — tracker status is the caller's decision) |
| Base HEAD | 3528ef2 (working-tree change, not committed) |
| Gate | `bash scripts/pre_build/check_cm_no_fail_open_skip.sh` |
| RED/GREEN test | `tests/unit/test_bob192_fail_open_skip_remediation.py` (20 cases, local `http.server` fixtures on ephemeral ports — never the live stack) |

## 1. What was wrong

Each of the 10 baseline rows was a live-stack test helper that turned evidence the host ANSWERED into a SKIP
(HTTP >=400, a non-health body, an empty result set, a non-terminal search status, or an answered error swallowed by
a `URLError`/`RequestException` handler). A skip reads green, so the product failure was invisible (§11.4.69).

## 2. Fix shape (per file)

| File / helper | Before | After |
|---|---|---|
| test_jackett_autoconfig_real.py `jackett_ready` | skip on `>=500`; skip on any `RequestException` (incl. answered TooManyRedirects) | skip ONLY on `requests.ConnectionError`/`Timeout`; FAIL on any answered `>=400`; other answered transport errors propagate |
| test_merge_api.py `_qbit_login` | skip when qBittorrent answered but refused admin/admin | FAIL (admin/admin is a project contract); reachability stays gated by the `qbit_url` fixture |
| test_merge_api.py `test_download_magnet_added_to_real_qbittorrent` | skip when `status != "initiated"` | assert |
| test_merge_api.py `test_search_finds_real_results_for_common_query` | skip on answered empty result set | assert (same convention as test_buttons_api.py) |
| test_tracker_auth_live.py `_merge_service_required` | skip on status>=400, on body lacking `"status"`, and inside `except URLError` (HTTPError is a subclass) | environment-derived TCP connect probe: refused/timeout -> SKIP; then HTTPError / non-JSON / status != healthy -> FAIL |
| test_tracker_auth_live.py `_run_live_search` | skip when search never terminated; answered poll 5xx swallowed as "torn read" | FAIL on deadline; poll `HTTPError` -> FAIL immediately; only non-HTTP transport blips keep polling |
| tests/scaling/test_boba_scaling.py `_services_up` | skip when boba-jackett /healthz not 200 | TCP-port gates unchanged (env-derived skips); answered unhealthy /healthz -> FAIL |

Golden-FALSE guard (§11.4.201(1)): the unit file also proves a genuinely unreachable endpoint (closed port -> connection
refused) still SKIPs for jackett_ready, _merge_service_required and _services_up, and healthy answers pass through.

## 3. RED — against the pre-fix helpers (13 failed / 7 passed)

```
nice -n 19 .venv/bin/python -m pytest tests/unit/test_bob192_fail_open_skip_remediation.py -v --import-mode=importlib -p no:cacheprovider
tests/unit/test_bob192_fail_open_skip_remediation.py::test_jackett_ready_fails_on_answered_500 FAILED [  5%]
tests/unit/test_bob192_fail_open_skip_remediation.py::test_jackett_ready_fails_on_answered_404 FAILED [ 10%]
tests/unit/test_bob192_fail_open_skip_remediation.py::test_jackett_ready_fails_on_answered_redirect_loop FAILED [ 15%]
tests/unit/test_bob192_fail_open_skip_remediation.py::test_jackett_ready_still_skips_when_unreachable PASSED [ 20%]
tests/unit/test_bob192_fail_open_skip_remediation.py::test_qbit_login_fails_on_answered_rejection FAILED [ 25%]
tests/unit/test_bob192_fail_open_skip_remediation.py::test_qbit_login_fails_on_answered_403 FAILED [ 30%]
tests/unit/test_bob192_fail_open_skip_remediation.py::test_qbit_login_accepts_modern_204_with_cookie PASSED [ 35%]
tests/unit/test_bob192_fail_open_skip_remediation.py::test_download_magnet_fails_when_qbit_refuses_add FAILED [ 40%]
tests/unit/test_bob192_fail_open_skip_remediation.py::test_search_common_query_fails_on_empty_result_set FAILED [ 45%]
tests/unit/test_bob192_fail_open_skip_remediation.py::test_merge_required_fails_on_answered_500 FAILED [ 50%]
tests/unit/test_bob192_fail_open_skip_remediation.py::test_merge_required_fails_on_non_health_body FAILED [ 55%]
tests/unit/test_bob192_fail_open_skip_remediation.py::test_merge_required_fails_on_unhealthy_status_field FAILED [ 60%]
tests/unit/test_bob192_fail_open_skip_remediation.py::test_merge_required_accepts_healthy PASSED [ 65%]
tests/unit/test_bob192_fail_open_skip_remediation.py::test_merge_required_still_skips_when_unreachable PASSED [ 70%]
tests/unit/test_bob192_fail_open_skip_remediation.py::test_live_search_fails_when_search_never_terminates FAILED [ 75%]
tests/unit/test_bob192_fail_open_skip_remediation.py::test_live_search_fails_when_poll_answers_500 FAILED [ 80%]
tests/unit/test_bob192_fail_open_skip_remediation.py::test_live_search_returns_terminal_payload PASSED [ 85%]
tests/unit/test_bob192_fail_open_skip_remediation.py::test_scaling_gate_fails_on_answered_unhealthy_healthz FAILED [ 90%]
tests/unit/test_bob192_fail_open_skip_remediation.py::test_scaling_gate_accepts_healthy PASSED [ 95%]
tests/unit/test_bob192_fail_open_skip_remediation.py::test_scaling_gate_still_skips_when_port_closed PASSED [100%]

E           Failed: FAIL-OPEN: answered failure was converted into a SKIP: Jackett unhealthy (500)
E       Failed: helper returned normally on an answered failure (fail-open PASS)
E           Failed: FAIL-OPEN: answered failure was converted into a SKIP: Jackett unreachable
E           Failed: FAIL-OPEN: answered failure was converted into a SKIP: real qBittorrent login did not succeed in this environment: 200 'Fails.'
E           Failed: FAIL-OPEN: answered failure was converted into a SKIP: real qBittorrent login did not succeed in this environment: 403 'Forbidden'
E           Failed: FAIL-OPEN: answered failure was converted into a SKIP: real qBittorrent did not accept the magnet add in this environment: {'status': 'failed', 'added_count': 0, 'results': []}
E           Failed: FAIL-OPEN: answered failure was converted into a SKIP: real search for 'ubuntu' returned 0 results — no tracker reachable/authenticated in this environment (errors=[], tracker_stats=[])
E           Failed: FAIL-OPEN: answered failure was converted into a SKIP: merge service unreachable at http://127.0.0.1:<port>/health: <HTTPError 500: 'Internal Server Error'>. Start the stack with `./start.sh -p` to run this credential guard.
E           Failed: FAIL-OPEN: answered failure was converted into a SKIP: merge service at http://127.0.0.1:<port>/health did not return a health body
E       Failed: helper returned normally on an answered failure (fail-open PASS)
E           Failed: FAIL-OPEN: answered failure was converted into a SKIP: live search did not reach a terminal state within 1s (last status='running'). Treated as an operator-blocked transient, not a credential failure.
E           Failed: FAIL-OPEN: answered failure was converted into a SKIP: live search did not reach a terminal state within 1s (last status='running'). Treated as an operator-blocked transient, not a credential failure.
E           Failed: FAIL-OPEN: answered failure was converted into a SKIP: boba-jackett /healthz not ok (SKIP-OK BOB-109)
======================== 13 failed, 7 passed in 11.40s =========================
```

The 7 RED-phase passes are the golden-FALSE / healthy-path cases (they must pass both before and after).

## 4. GREEN — after the fix (20 passed)

```
tests/unit/test_bob192_fail_open_skip_remediation.py::test_download_magnet_fails_when_qbit_refuses_add PASSED [ 70%]
tests/unit/test_bob192_fail_open_skip_remediation.py::test_jackett_ready_fails_on_answered_404 PASSED [  5%]
tests/unit/test_bob192_fail_open_skip_remediation.py::test_jackett_ready_fails_on_answered_500 PASSED [ 10%]
tests/unit/test_bob192_fail_open_skip_remediation.py::test_jackett_ready_fails_on_answered_redirect_loop PASSED [ 55%]
tests/unit/test_bob192_fail_open_skip_remediation.py::test_jackett_ready_still_skips_when_unreachable PASSED [ 35%]
tests/unit/test_bob192_fail_open_skip_remediation.py::test_live_search_fails_when_poll_answers_500 PASSED [ 90%]
tests/unit/test_bob192_fail_open_skip_remediation.py::test_live_search_fails_when_search_never_terminates PASSED [ 65%]
tests/unit/test_bob192_fail_open_skip_remediation.py::test_live_search_returns_terminal_payload PASSED [100%]
tests/unit/test_bob192_fail_open_skip_remediation.py::test_merge_required_accepts_healthy PASSED [ 15%]
tests/unit/test_bob192_fail_open_skip_remediation.py::test_merge_required_fails_on_answered_500 PASSED [ 50%]
tests/unit/test_bob192_fail_open_skip_remediation.py::test_merge_required_fails_on_non_health_body PASSED [ 25%]
tests/unit/test_bob192_fail_open_skip_remediation.py::test_merge_required_fails_on_unhealthy_status_field PASSED [ 75%]
tests/unit/test_bob192_fail_open_skip_remediation.py::test_merge_required_still_skips_when_unreachable PASSED [ 60%]
tests/unit/test_bob192_fail_open_skip_remediation.py::test_qbit_login_accepts_modern_204_with_cookie PASSED [ 30%]
tests/unit/test_bob192_fail_open_skip_remediation.py::test_qbit_login_fails_on_answered_403 PASSED [ 85%]
tests/unit/test_bob192_fail_open_skip_remediation.py::test_qbit_login_fails_on_answered_rejection PASSED [ 45%]
tests/unit/test_bob192_fail_open_skip_remediation.py::test_scaling_gate_accepts_healthy PASSED [ 95%]
tests/unit/test_bob192_fail_open_skip_remediation.py::test_scaling_gate_fails_on_answered_unhealthy_healthz PASSED [ 20%]
tests/unit/test_bob192_fail_open_skip_remediation.py::test_scaling_gate_still_skips_when_port_closed PASSED [ 40%]
tests/unit/test_bob192_fail_open_skip_remediation.py::test_search_common_query_fails_on_empty_result_set PASSED [ 80%]
============================= 20 passed in 10.85s ==============================
```

## 5. Finding SET — before / after

Before (baseline rows, identical to `--list` before the change):

```
tests/integration/test_jackett_autoconfig_real.py:jackett_ready:STATUS#1
tests/integration/test_jackett_autoconfig_real.py:jackett_ready:UNREACH#1
tests/integration/test_merge_api.py:TestDownloadEndpoint.test_download_magnet_added_to_real_qbittorrent:STATUS#1
tests/integration/test_merge_api.py:TestSearchEndpoint.test_search_finds_real_results_for_common_query:EMPTY#1
tests/integration/test_merge_api.py:_qbit_login:STATUS#1
tests/integration/test_tracker_auth_live.py:_merge_service_required:EMPTY#1
tests/integration/test_tracker_auth_live.py:_merge_service_required:STATUS#1
tests/integration/test_tracker_auth_live.py:_merge_service_required:UNREACH#1
tests/integration/test_tracker_auth_live.py:_run_live_search:EMPTY#1
tests/scaling/test_boba_scaling.py:_services_up:EMPTY#1
```

After (`check_cm_no_fail_open_skip.sh --list`): **empty set** (the command printed nothing, rc=0).

Gate run with the fix applied but the OLD baseline still in place — all 10 rows reported STALE, proving each
finding is gone by KEY (set comparison, not count):

```
STALE: tests/integration/test_jackett_autoconfig_real.py:jackett_ready:STATUS#1 — no live finding; remove the row (the ratchet must tighten, §11.4.227(A))
STALE: tests/integration/test_jackett_autoconfig_real.py:jackett_ready:UNREACH#1 — no live finding; remove the row (the ratchet must tighten, §11.4.227(A))
STALE: tests/integration/test_merge_api.py:TestDownloadEndpoint.test_download_magnet_added_to_real_qbittorrent:STATUS#1 — no live finding; remove the row (the ratchet must tighten, §11.4.227(A))
STALE: tests/integration/test_merge_api.py:TestSearchEndpoint.test_search_finds_real_results_for_common_query:EMPTY#1 — no live finding; remove the row (the ratchet must tighten, §11.4.227(A))
STALE: tests/integration/test_merge_api.py:_qbit_login:STATUS#1 — no live finding; remove the row (the ratchet must tighten, §11.4.227(A))
STALE: tests/integration/test_tracker_auth_live.py:_merge_service_required:EMPTY#1 — no live finding; remove the row (the ratchet must tighten, §11.4.227(A))
STALE: tests/integration/test_tracker_auth_live.py:_merge_service_required:STATUS#1 — no live finding; remove the row (the ratchet must tighten, §11.4.227(A))
STALE: tests/integration/test_tracker_auth_live.py:_merge_service_required:UNREACH#1 — no live finding; remove the row (the ratchet must tighten, §11.4.227(A))
STALE: tests/integration/test_tracker_auth_live.py:_run_live_search:EMPTY#1 — no live finding; remove the row (the ratchet must tighten, §11.4.227(A))
STALE: tests/scaling/test_boba_scaling.py:_services_up:EMPTY#1 — no live finding; remove the row (the ratchet must tighten, §11.4.227(A))
FAIL: CM-NO-FAIL-OPEN-SKIP: 0 finding(s) (0 baselined, 0 new, 10 stale) across 414 test files, 61 skip sites; control-needle: seen
rc=1
```

Gate run after removing the 10 rows in the same change (baseline now holds zero keys):

```
PASS: CM-NO-FAIL-OPEN-SKIP: 0 finding(s) (0 baselined, 0 new, 0 stale) across 414 test files, 61 skip sites; control-needle: seen
rc=0
```

The zero is not a blind zero: `control-needle: seen` and 61 skip sites scanned across 414 test files (§11.4.201(6)).

## 6. Live stack run of the affected files (stack untouched, running on 7185-7189/9117)

```
nice -n 19 timeout 580 .venv/bin/python -m pytest tests/integration/test_jackett_autoconfig_real.py \
  tests/integration/test_merge_api.py tests/integration/test_tracker_auth_live.py -v --import-mode=importlib -p no:cacheprovider -rs
tests/integration/test_tracker_auth_live.py::test_private_tracker_credentials_authenticate[iptorrents] PASSED [  3%]
tests/integration/test_tracker_auth_live.py::test_private_tracker_credentials_authenticate[nnmclub] PASSED [  7%]
tests/integration/test_tracker_auth_live.py::test_private_tracker_credentials_authenticate[kinozal] FAILED [ 11%]
tests/integration/test_tracker_auth_live.py::test_private_tracker_credentials_authenticate[rutracker] FAILED [ 15%]
tests/integration/test_tracker_auth_live.py::test_public_tracker_returns_results_without_auth[rutor] PASSED [ 19%]
tests/integration/test_jackett_autoconfig_real.py::test_module_orchestrator_is_idempotent_on_second_invocation PASSED [ 23%]
tests/integration/test_merge_api.py::TestHooksEndpoint::test_create_hook_missing_name_returns_422 FAILED [ 26%]
tests/integration/test_merge_api.py::TestHooksEndpoint::test_create_hook_invalid_event_returns_400 FAILED [ 30%]
tests/integration/test_merge_api.py::TestHooksEndpoint::test_hook_lifecycle_create_list_delete FAILED [ 34%]
tests/integration/test_merge_api.py::TestHooksEndpoint::test_delete_nonexistent_hook_returns_404 FAILED [ 38%]
tests/integration/test_merge_api.py::TestHooksEndpoint::test_create_hook_returns_hook_id FAILED [ 42%]
tests/integration/test_merge_api.py::TestMagnetEndpoint::test_generate_magnet_without_hash FAILED [ 46%]
tests/integration/test_merge_api.py::TestMagnetEndpoint::test_generate_magnet_with_hash FAILED [ 50%]
tests/integration/test_merge_api.py::TestMagnetEndpoint::test_generate_magnet_invalid_request FAILED [ 53%]
tests/integration/test_merge_api.py::TestActiveDownloadsEndpoint::test_active_downloads_returns_real_list PASSED [ 57%]
tests/integration/test_merge_api.py::TestHealthEndpoint::test_health_returns_200 PASSED [ 61%]
tests/integration/test_merge_api.py::TestSearchEndpoint::test_search_finds_real_results_for_common_query PASSED [ 65%]
tests/integration/test_merge_api.py::TestSearchEndpoint::test_search_with_empty_query_returns_422 PASSED [ 69%]
tests/integration/test_merge_api.py::TestSearchEndpoint::test_search_with_missing_body_returns_422 PASSED [ 73%]
tests/integration/test_merge_api.py::TestSearchEndpoint::test_search_with_valid_query_real_orchestrator PASSED [ 76%]
tests/integration/test_merge_api.py::TestAbortSearchEndpoint::test_abort_unknown_search PASSED [ 80%]
tests/integration/test_merge_api.py::TestAbortSearchEndpoint::test_abort_existing_search PASSED [ 84%]
tests/integration/test_merge_api.py::TestDownloadEndpoint::test_download_empty_urls_rejected_at_boundary FAILED [ 88%]
tests/integration/test_merge_api.py::TestDownloadEndpoint::test_download_magnet_added_to_real_qbittorrent FAILED [ 92%]
tests/integration/test_merge_api.py::TestSearchByIdEndpoint::test_get_unknown_search_returns_404 PASSED [ 96%]
tests/integration/test_merge_api.py::TestSearchByIdEndpoint::test_get_existing_search_returns_200 PASSED [100%]
================== 12 failed, 14 passed in 119.81s (0:01:59) ===================
```

Every remediated helper ran on the live stack and passed through (jackett_ready, _qbit_login, _merge_service_required,
_run_live_search and the empty-result search assertion all reached their test bodies). None of the 12 failures is
produced by a remediated helper; they were already failing (or would have) at HEAD and are reported, not re-skipped:

1. **10 x HTTP 401 in test_merge_api.py** (TestHooksEndpoint x5, TestMagnetEndpoint x3, TestDownloadEndpoint x2): the live
   merge service has `BOBA_API_TOKEN` set (`routes.py` token dependency answers `401 "Unauthorized: valid API token
   required"`; confirmed with `curl -X POST /api/v1/magnet` -> 401) and the integration file sends no token. Each
   failing assertion (`resp.status_code == 200/400/404/422`) precedes any line this change touched, so HEAD fails
   identically. UNTRACKED: needs its own item (the test must carry the token from the environment, or skip with an
   honest `BOBA_API_TOKEN`-derived reason).
2. **test_private_tracker_credentials_authenticate[kinozal]**: `authenticated=False, status='empty', error=''` — the
   test body's genuine credential verdict (not a helper). A real finding, UNTRACKED in docs/Issues.md.
3. **test_private_tracker_credentials_authenticate[rutracker]**: `authenticated=True, status='error'`, upstream 403
   bot-protection challenge — the known BOB-172 defect.

Scaling gate (`_services_up`) was exercised live directly (the scaling module itself was NOT run: it writes the
committed docs/qa/BOB-109 corpus):

```
live _services_up gate returned None (no skip, no fail) against 7189/9117
```

Related meta-test still green (`tests/unit/test_no_runtime_service_skips.py`): `7 passed`. `ruff check` on the 5 files: clean.

## 7. Open item created by this change (outside the allowed file scope)

`tests/pre_build/test_check_cm_no_fail_open_skip.sh` **case 9** hard-codes that the BOB-192 rows are still present
(`grep -qF 'tests/integration/test_tracker_auth_live.py:_merge_service_required:' baseline`). With the baseline now
correctly empty it reports `FAIL: case 9: expected rc=0 on the real tree; got rc=0 ...` (the gate itself is rc=0; only
the pinned-debt grep fails). That self-test must be updated to assert the empty SET in the same commit as this change;
it was outside this task's permitted files, so it is left for the caller.
