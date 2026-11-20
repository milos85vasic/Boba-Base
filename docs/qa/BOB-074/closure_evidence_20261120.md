============================= test session starts ==============================
platform linux -- Python 3.12.14, pytest-9.1.1, pluggy-1.6.0 -- /home/milosvasic/Projects/boba/.venv/bin/python
cachedir: .pytest_cache
benchmark: 5.3.0 (defaults: timer=time.perf_counter disable_gc=False min_rounds=5 min_time=0.000005 max_time=1.0 calibration_precision=10 warmup=False warmup_iterations=100000)
Using --randomly-seed=3999218808
hypothesis profile 'default'
rootdir: /home/milosvasic/Projects/boba
configfile: pyproject.toml
plugins: anyio-4.14.2, schemathesis-4.25.2, benchmark-5.3.0, xdist-3.8.0, asyncio-1.4.0, cov-7.1.0, docker-3.2.5, playwright-0.9.0, base-url-2.1.0, repeat-0.9.4, locust-2.46.4, randomly-4.1.0, timeout-2.4.0, hypothesis-6.167.1, respx-0.23.1
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
timeout: 60.0s
timeout method: signal
timeout func_only: False
collecting ... collected 40 items

tests/ddos/test_request_flood.py::TestServiceSurvivesTheBurst::test_flooding_client_does_not_deny_service_to_another_client PASSED [  2%]
tests/ddos/test_request_flood.py::TestServiceSurvivesTheBurst::test_health_still_answers_after_the_burst PASSED [  5%]
tests/ddos/test_request_flood.py::TestCappedBurstIsRefusedNotServed::test_refusal_body_is_the_opaque_token_not_a_stack_trace PASSED [  7%]
tests/ddos/test_request_flood.py::TestCappedBurstIsRefusedNotServed::test_burst_serves_only_up_to_the_limit_and_refuses_the_rest PASSED [ 10%]
tests/ddos/test_request_flood.py::TestCappedBurstIsRefusedNotServed::test_burst_produces_no_5xx PASSED [ 12%]
tests/ddos/test_request_flood.py::TestSseStreamFloodIsRefused::test_sse_stream_burst_is_refused_without_5xx PASSED [ 15%]
tests/ddos/test_payload_abuse.py::TestOversizedUploadIsRefused::test_service_survives_the_oversized_upload PASSED [ 17%]
tests/ddos/test_payload_abuse.py::TestOversizedUploadIsRefused::test_undersized_upload_is_not_refused_by_the_size_guard PASSED [ 20%]
tests/ddos/test_payload_abuse.py::TestOversizedUploadIsRefused::test_oversized_torrent_upload_is_refused_with_413 PASSED [ 22%]
tests/ddos/test_payload_abuse.py::TestOversizedJsonBody::test_oversized_body_cannot_bypass_the_rate_limiter PASSED [ 25%]
tests/ddos/test_payload_abuse.py::TestOversizedJsonBody::test_oversized_query_does_not_5xx_and_service_stays_live PASSED [ 27%]
tests/ddos/test_malformed_flood.py::TestMalformedJsonFloodSurvives::test_invalid_json_body_flood_on_search_produces_no_5xx PASSED [ 30%]
tests/ddos/test_malformed_flood.py::TestMalformedJsonFloodSurvives::test_empty_json_object_flood_on_search_is_refused_not_5xx PASSED [ 32%]
tests/ddos/test_malformed_flood.py::TestMalformedFloodDoesNotBlockBystander::test_malformed_search_flood_does_not_deny_bystander_health PASSED [ 35%]
tests/ddos/test_malformed_flood.py::TestMalformedAuthQbittorrentFloodSurvives::test_missing_fields_flood_on_auth_qbittorrent_produces_no_5xx PASSED [ 37%]
tests/ddos/test_malformed_flood.py::TestMalformedDownloadFloodSurvives::test_invalid_url_list_flood_on_download_produces_no_5xx PASSED [ 40%]
tests/ddos/test_malformed_flood.py::TestMalformedMagnetFloodSurvives::test_missing_fields_flood_on_magnet_produces_no_5xx PASSED [ 42%]
tests/ddos/test_auth_stress_chaos.py::TestQbitAuthBurstSurvives::test_qbittorrent_unreachable_under_repeated_calls_reports_error_not_5xx PASSED [ 45%]
tests/ddos/test_auth_stress_chaos.py::TestQbitAuthBurstSurvives::test_burst_of_login_attempts_produces_no_5xx_and_survives PASSED [ 47%]
tests/ddos/test_auth_stress_chaos.py::TestQbitAuthBurstSurvives::test_repeated_failed_login_attempts_credential_stuffing_shaped_no_5xx PASSED [ 50%]
tests/ddos/test_auth_stress_chaos.py::TestActiveDownloadsBurstSurvives::test_flooding_client_does_not_deny_service_to_another_client PASSED [ 52%]
tests/ddos/test_auth_stress_chaos.py::TestActiveDownloadsBurstSurvives::test_qbittorrent_unreachable_reports_empty_result_not_5xx PASSED [ 55%]
tests/ddos/test_auth_stress_chaos.py::TestActiveDownloadsBurstSurvives::test_burst_produces_no_5xx_and_service_survives PASSED [ 57%]
tests/ddos/test_auth_stress_chaos.py::TestQbitAuthBystanderNotBlocked::test_auth_flood_does_not_block_bystander_health_check PASSED [ 60%]
tests/ddos/test_resource_exhaustion.py::TestSearchAdmissionControl::test_queue_full_is_refused_with_429 PASSED [ 62%]
tests/ddos/test_resource_exhaustion.py::TestSearchAdmissionControl::test_shedding_never_produces_a_5xx PASSED [ 65%]
tests/ddos/test_resource_exhaustion.py::TestSearchAdmissionControl::test_service_still_answers_health_while_shedding PASSED [ 67%]
tests/ddos/test_resource_exhaustion.py::TestSearchAdmissionControl::test_admission_control_sheds_a_client_with_an_untouched_per_ip_budget PASSED [ 70%]
tests/ddos/test_resource_exhaustion.py::TestSearchAdmissionControl::test_below_the_cap_the_search_is_admitted PASSED [ 72%]
tests/ddos/test_resource_exhaustion.py::test_cap_knob_is_real_not_hardcoded PASSED [ 75%]
tests/ddos/test_download_trigger_stress_chaos.py::TestMagnetTriggerBurstSurvives::test_burst_of_magnet_requests_produces_no_5xx_and_survives PASSED [ 77%]
tests/ddos/test_download_trigger_stress_chaos.py::TestMagnetTriggerBurstSurvives::test_oversized_download_urls_list_does_not_5xx_or_hang PASSED [ 80%]
tests/ddos/test_download_trigger_stress_chaos.py::TestDownloadFileTriggerBurstSurvives::test_burst_of_magnet_download_file_requests_produces_no_5xx_and_survives PASSED [ 82%]
tests/ddos/test_download_trigger_stress_chaos.py::TestDownloadFileTriggerBurstSurvives::test_flooding_client_does_not_deny_service_to_another_client PASSED [ 85%]
tests/ddos/test_download_trigger_stress_chaos.py::TestDownloadTriggerPayloadShapedAbuse::test_qbittorrent_unreachable_under_repeated_calls_reports_connection_failed_not_5xx PASSED [ 87%]
tests/ddos/test_download_trigger_stress_chaos.py::TestDownloadTriggerPayloadShapedAbuse::test_oversized_download_urls_list_is_bounded_by_code_not_by_payload_size PASSED [ 90%]
tests/ddos/test_download_trigger_stress_chaos.py::TestDownloadTriggerBurstSurvives::test_burst_produces_no_5xx_and_service_survives PASSED [ 92%]
tests/ddos/test_download_trigger_stress_chaos.py::TestDownloadTriggerBurstSurvives::test_flooding_client_does_not_deny_service_to_another_client PASSED [ 95%]
tests/ddos/test_slow_request.py::test_slow_request_body_does_not_starve_concurrent_clients PASSED [ 97%]
tests/ddos/test_slow_request.py::test_slow_handler_does_not_starve_concurrent_clients PASSED [100%]

=============================== warnings summary ===============================
.venv/lib/python3.12/site-packages/fastapi/testclient.py:1
  /home/milosvasic/Projects/boba/.venv/lib/python3.12/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================== 40 passed, 1 warning in 10.12s ========================
