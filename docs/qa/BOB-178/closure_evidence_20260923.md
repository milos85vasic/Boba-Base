# BOB-178 closure evidence — 2026-09-23

## Fix

`_search_kinozal`'s login-response handling in
`download-proxy/src/merge_service/search.py` previously returned `[]` on
any non-(200,301,302) login status with NO diagnostic set — the exact
BOB-172 false-null signature (a refusal reported as empty, indistinguishable
from "no matches"). Fixed by stashing a diagnostic before the early
return, reusing the shared `_classify_upstream_http_status` helper (the
same dialect the kinozal search-leg's own `_check_search_response` call
already speaks) with a manual fallback for the one edge case where the
classifier itself would return `None` (an atypical 2xx status like 201
that is not in kinozal's own accepted `(200, 301, 302)` set).

## Independently re-verified this session (coordinator, including a
genuine paired-mutation revert/restore)

```
$ .venv/bin/python -m pytest tests/unit/merge_service/test_bob178_kinozal_login_status_diagnostic.py -v --import-mode=importlib
... 10 passed in 0.76s

$ grep -n -A8 "_classify_upstream_http_status(login_resp.status" download-proxy/src/merge_service/search.py
1812: diag = _classify_upstream_http_status(login_resp.status, "") or {...}
1820: self._last_public_tracker_diag["kinozal"] = diag
(confirmed present exactly as reported)

$ git stash push -m "coordinator-verify-bob178" -- download-proxy/src/merge_service/search.py
$ .venv/bin/python -m pytest tests/unit/merge_service/test_bob178_kinozal_login_status_diagnostic.py -q --import-mode=importlib
7 failed, 3 passed in 0.83s
(the 3 passes are the negative-control healthy-login tests, correctly
unaffected by the revert)

$ git stash pop
$ .venv/bin/python -m pytest tests/unit/merge_service/test_bob178_kinozal_login_status_diagnostic.py -q --import-mode=importlib
10 passed in 0.74s
```
Genuine reproduction confirmed independently — reverting the source alone
reproduces the exact 7-failed/3-passed signature; restoring returns to
green.

## Golden-FALSE (healthy login unaffected)

`TestNegativeControlHealthyLoginIsNeverStashed`, parametrized over
kinozal's own three accepted login statuses (200, 301, 302): all assert
no diagnostic is stashed for a healthy login, pass both before and after
the fix.

## Honest boundary (not silenced, per the subagent's own report)

A DISTINCT, latent, structurally-similar gap remains open and out of this
item's scope: kinozal never checks cookie PRESENCE after a
successfully-statused login (unlike rutracker/nnmclub, which check ONLY
cookie presence, never HTTP status) — this fix addresses the HTTP-status
classification gap the item's own acceptance criterion names (a stubbed
403 producing a non-None error), not that separate presence-check gap.

A `hawkscan-post-commit` system hook fired misleadingly during both the
subagent's and the coordinator's `git stash`/`git stash pop` plumbing
operations, claiming a commit had happened — no `git commit` was ever
run by either (confirmed: HEAD unchanged throughout); the notification
was correctly ignored as a harness anomaly, not a real event to act on.

## git diff --stat

```
download-proxy/src/merge_service/search.py | 37 +++++++++++++++++++++++++++++-
1 file changed, 36 insertions(+), 1 deletion(-)
```
Plus new `tests/unit/merge_service/test_bob178_kinozal_login_status_diagnostic.py`
(253 lines, 10 tests).
