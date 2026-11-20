=== RUN   TestRED_UnsetToken_EveryMethodPasses
--- PASS: TestRED_UnsetToken_EveryMethodPasses (0.00s)
=== RUN   TestGREEN_SetToken_MutatingMethodWithNoHeaderIs401
--- PASS: TestGREEN_SetToken_MutatingMethodWithNoHeaderIs401 (0.00s)
=== RUN   TestGREEN_SetToken_WrongTokenIs401
--- PASS: TestGREEN_SetToken_WrongTokenIs401 (0.00s)
=== RUN   TestGREEN_SetToken_CorrectTokenSucceeds
--- PASS: TestGREEN_SetToken_CorrectTokenSucceeds (0.00s)
=== RUN   TestGREEN_SetToken_ReadMethodsAlwaysPass
--- PASS: TestGREEN_SetToken_ReadMethodsAlwaysPass (0.00s)
=== RUN   TestGREEN_EmptyBearerIsRejected
--- PASS: TestGREEN_EmptyBearerIsRejected (0.00s)
=== RUN   TestGREEN_TokenReadPerRequest
--- PASS: TestGREEN_TokenReadPerRequest (0.00s)
=== RUN   TestCORS_AllowedOriginsEnv_PythonParity
=== RUN   TestCORS_AllowedOriginsEnv_PythonParity/unset_falls_back_to_the_Python_default_allowlist
=== RUN   TestCORS_AllowedOriginsEnv_PythonParity/empty_string_falls_back_to_defaults,_never_an_empty_allowlist
=== RUN   TestCORS_AllowedOriginsEnv_PythonParity/whitespace-only_falls_back_to_defaults
=== RUN   TestCORS_AllowedOriginsEnv_PythonParity/commas-only_falls_back_to_defaults
=== RUN   TestCORS_AllowedOriginsEnv_PythonParity/single_origin_replaces_the_defaults_entirely
=== RUN   TestCORS_AllowedOriginsEnv_PythonParity/several_origins,_comma-separated_and_individually_trimmed
=== RUN   TestCORS_AllowedOriginsEnv_PythonParity/wildcard_alone_echoes_the_specific_origin
=== RUN   TestCORS_AllowedOriginsEnv_PythonParity/wildcard_mixed_with_a_host_is_still_a_wildcard_(per-element,_as_Python)
--- PASS: TestCORS_AllowedOriginsEnv_PythonParity (0.00s)
    --- PASS: TestCORS_AllowedOriginsEnv_PythonParity/unset_falls_back_to_the_Python_default_allowlist (0.00s)
    --- PASS: TestCORS_AllowedOriginsEnv_PythonParity/empty_string_falls_back_to_defaults,_never_an_empty_allowlist (0.00s)
    --- PASS: TestCORS_AllowedOriginsEnv_PythonParity/whitespace-only_falls_back_to_defaults (0.00s)
    --- PASS: TestCORS_AllowedOriginsEnv_PythonParity/commas-only_falls_back_to_defaults (0.00s)
    --- PASS: TestCORS_AllowedOriginsEnv_PythonParity/single_origin_replaces_the_defaults_entirely (0.00s)
    --- PASS: TestCORS_AllowedOriginsEnv_PythonParity/several_origins,_comma-separated_and_individually_trimmed (0.00s)
    --- PASS: TestCORS_AllowedOriginsEnv_PythonParity/wildcard_alone_echoes_the_specific_origin (0.00s)
    --- PASS: TestCORS_AllowedOriginsEnv_PythonParity/wildcard_mixed_with_a_host_is_still_a_wildcard_(per-element,_as_Python) (0.00s)
=== RUN   TestCORS_DefaultOriginsFollowMergeServicePort
--- PASS: TestCORS_DefaultOriginsFollowMergeServicePort (0.00s)
=== RUN   TestCORS_ExtensionOrigins
--- PASS: TestCORS_ExtensionOrigins (0.00s)
=== RUN   TestCORS_ExtensionOriginsGetNoCredentials
--- PASS: TestCORS_ExtensionOriginsGetNoCredentials (0.00s)
=== RUN   TestCORS_Headers
--- PASS: TestCORS_Headers (0.00s)
=== RUN   TestCORS_Options
--- PASS: TestCORS_Options (0.00s)
=== RUN   TestCORS_NoWildcardWithCredentials
--- PASS: TestCORS_NoWildcardWithCredentials (0.00s)
=== RUN   TestCORS_WildcardConfigured_NeverWildcardWithCredentials
--- PASS: TestCORS_WildcardConfigured_NeverWildcardWithCredentials (0.00s)
=== RUN   TestLogger_NoPanic
{"level":"info","method":"GET","path":"/test","status":200,"latency":0.0123,"client_ip":"","time":"2026-11-20T18:09:21+01:00","message":"request"}
--- PASS: TestLogger_NoPanic (0.00s)
=== RUN   TestRED_DisabledLimiter_NeverGates
--- PASS: TestRED_DisabledLimiter_NeverGates (0.00s)
=== RUN   TestGREEN_OverBudgetReturns429
--- PASS: TestGREEN_OverBudgetReturns429 (0.00s)
=== RUN   TestGREEN_PerIPScope_DifferentIPNotThrottled
--- PASS: TestGREEN_PerIPScope_DifferentIPNotThrottled (0.00s)
=== RUN   TestChaos_ConcurrentBurst_NoCrashNo5xx
--- PASS: TestChaos_ConcurrentBurst_NoCrashNo5xx (0.00s)
=== RUN   TestGin_RateLimit_Integrates
--- PASS: TestGin_RateLimit_Integrates (0.00s)
PASS
ok  	github.com/milos85vasic/qBitTorrent-go/internal/middleware	1.032s
=== RUN   TestWiring_ServerHandlerRateLimitsTheRealMux
--- PASS: TestWiring_ServerHandlerRateLimitsTheRealMux (0.01s)
=== RUN   TestControl_UnderBudgetIsNotRefused
--- PASS: TestControl_UnderBudgetIsNotRefused (0.01s)
=== RUN   TestControl_DisabledLimiterStillServes
--- PASS: TestControl_DisabledLimiterStillServes (0.01s)
PASS
ok  	github.com/milos85vasic/qBitTorrent-go/cmd/boba-jackett	1.061s
