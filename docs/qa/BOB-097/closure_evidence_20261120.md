============================= test session starts ==============================
platform linux -- Python 3.12.14, pytest-9.1.1, pluggy-1.6.0 -- /home/milosvasic/Projects/boba/.venv/bin/python
cachedir: .pytest_cache
benchmark: 5.3.0 (defaults: timer=time.perf_counter disable_gc=False min_rounds=5 min_time=0.000005 max_time=1.0 calibration_precision=10 warmup=False warmup_iterations=100000)
Using --randomly-seed=681977870
hypothesis profile 'default'
rootdir: /home/milosvasic/Projects/boba
configfile: pyproject.toml
plugins: anyio-4.14.2, schemathesis-4.25.2, benchmark-5.3.0, xdist-3.8.0, asyncio-1.4.0, cov-7.1.0, docker-3.2.5, playwright-0.9.0, base-url-2.1.0, repeat-0.9.4, locust-2.46.4, randomly-4.1.0, timeout-2.4.0, hypothesis-6.167.1, respx-0.23.1
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
timeout: 60.0s
timeout method: signal
timeout func_only: False
collecting ... collected 15 items

tests/ddos/test_auth_stress_chaos.py::TestQbitAuthBurstSurvives::test_burst_of_login_attempts_produces_no_5xx_and_survives PASSED [  6%]
tests/ddos/test_auth_stress_chaos.py::TestQbitAuthBurstSurvives::test_qbittorrent_unreachable_under_repeated_calls_reports_error_not_5xx PASSED [ 13%]
tests/ddos/test_auth_stress_chaos.py::TestQbitAuthBurstSurvives::test_repeated_failed_login_attempts_credential_stuffing_shaped_no_5xx PASSED [ 20%]
tests/ddos/test_auth_stress_chaos.py::TestActiveDownloadsBurstSurvives::test_flooding_client_does_not_deny_service_to_another_client PASSED [ 26%]
tests/ddos/test_auth_stress_chaos.py::TestActiveDownloadsBurstSurvives::test_qbittorrent_unreachable_reports_empty_result_not_5xx PASSED [ 33%]
tests/ddos/test_auth_stress_chaos.py::TestActiveDownloadsBurstSurvives::test_burst_produces_no_5xx_and_service_survives PASSED [ 40%]
tests/ddos/test_auth_stress_chaos.py::TestQbitAuthBystanderNotBlocked::test_auth_flood_does_not_block_bystander_health_check PASSED [ 46%]
tests/ddos/test_download_trigger_stress_chaos.py::TestMagnetTriggerBurstSurvives::test_burst_of_magnet_requests_produces_no_5xx_and_survives PASSED [ 53%]
tests/ddos/test_download_trigger_stress_chaos.py::TestMagnetTriggerBurstSurvives::test_oversized_download_urls_list_does_not_5xx_or_hang PASSED [ 60%]
tests/ddos/test_download_trigger_stress_chaos.py::TestDownloadTriggerBurstSurvives::test_burst_produces_no_5xx_and_service_survives PASSED [ 66%]
tests/ddos/test_download_trigger_stress_chaos.py::TestDownloadTriggerBurstSurvives::test_flooding_client_does_not_deny_service_to_another_client PASSED [ 73%]
tests/ddos/test_download_trigger_stress_chaos.py::TestDownloadFileTriggerBurstSurvives::test_burst_of_magnet_download_file_requests_produces_no_5xx_and_survives PASSED [ 80%]
tests/ddos/test_download_trigger_stress_chaos.py::TestDownloadFileTriggerBurstSurvives::test_flooding_client_does_not_deny_service_to_another_client PASSED [ 86%]
tests/ddos/test_download_trigger_stress_chaos.py::TestDownloadTriggerPayloadShapedAbuse::test_qbittorrent_unreachable_under_repeated_calls_reports_connection_failed_not_5xx PASSED [ 93%]
tests/ddos/test_download_trigger_stress_chaos.py::TestDownloadTriggerPayloadShapedAbuse::test_oversized_download_urls_list_is_bounded_by_code_not_by_payload_size PASSED [100%]

=============================== warnings summary ===============================
.venv/lib/python3.12/site-packages/fastapi/testclient.py:1
  /home/milosvasic/Projects/boba/.venv/lib/python3.12/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================== 15 passed, 1 warning in 3.60s =========================
