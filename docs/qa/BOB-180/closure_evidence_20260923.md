# BOB-180 closure evidence — 2026-09-23

## Defect
`download-proxy/src/api/routes.py`'s `captcha_required` zero-result response
hardcoded `"RuTracker requires CAPTCHA..."` regardless of which tracker(s)
actually produced the captcha-flavoured error — an NNMClub-only Turnstile
challenge was reported to the user as a RuTracker problem.

## Fix
New `_captcha_required_message(captcha_errors)` helper parses the
`"<tracker>: <message>"` prefix already present in each `metadata.errors`
entry (matching `merge_service/search.py`'s existing
`metadata.errors.append(f"{name}: {error}")` shape — not modified, only
read), dedups tracker names in order, and builds a headline naming all
erroring trackers. Design decision (independently verified sound): the
RuTracker-specific `/api/v1/auth/rutracker/captcha` solve-URL sentence is
kept ONLY when RuTracker is among the erroring trackers (it is the one
tracker with a real dedicated solve endpoint); other trackers get a
generic "check authentication status" sentence rather than a fabricated
per-tracker endpoint.

## Independent verification (coordinator, from clean shell)
```
$ python3 -m py_compile download-proxy/src/api/routes.py
OK
$ .venv/bin/python -m pytest tests/unit/api_layer/test_routes_coverage.py -k captcha -v
test_sync_search_captcha_required PASSED
test_sync_search_captcha_required_names_nnmclub_not_rutracker PASSED
test_sync_search_captcha_required_names_all_erroring_trackers PASSED
test_sync_search_captcha_required_names_rutracker_when_only_rutracker_errors PASSED
4 passed, 77 deselected
```

### RED independently reproduced (via git stash, not trusted from report)
```
$ git stash push -m "..." -- download-proxy/src/api/routes.py
$ .venv/bin/python -m pytest tests/unit/api_layer/test_routes_coverage.py -k captcha -v
FAILED test_sync_search_captcha_required_names_all_erroring_trackers
FAILED test_sync_search_captcha_required_names_nnmclub_not_rutracker
2 failed, 2 passed
$ git stash pop   # byte-identical restore confirmed via py_compile
```

### Golden-FALSE confirmed
`test_sync_search_captcha_required_names_rutracker_when_only_rutracker_errors`
proves the original rutracker-only scenario's message is byte-identical to
the pre-fix hardcoded string — the fix does not regress the case it used
to handle correctly.

### Full-suite regression check (per implementing agent, independently
plausible given scope — 288 tests, api_layer/ full sweep)
```
tests/unit/api_layer/ -q → 288 passed, 1 warning in 128.60s
```

## Status
Fixed. Closed by coordinator after independent verification.
