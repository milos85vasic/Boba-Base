# BOB-176 closure evidence — 2026-09-23

## Fix

`_get_enabled_trackers()` in `download-proxy/src/merge_service/search.py`
gated rutracker on `RUTRACKER_USERNAME and RUTRACKER_PASSWORD` only,
ignoring `RUTRACKER_COOKIES` — even though `_search_rutracker` itself
treats cookies as the PREFERRED auth path, and the nnmclub sibling gate
already honours its own cookies variable. Fixed to mirror the nnmclub
gate's shape exactly:
```python
if os.getenv("RUTRACKER_COOKIES") or (os.getenv("RUTRACKER_USERNAME") and os.getenv("RUTRACKER_PASSWORD")):
```

## Audit of other trackers (acceptance criterion e)

Investigated kinozal and iptorrents firsthand: neither references any
`*_COOKIES` environment variable anywhere in its search-site body (grep
across `download-proxy/src/` + `scripts/load-tracker-cookies.sh`: zero
matches) — both perform an unconditional username/password login with no
cookie-bypass branch to be asymmetric against. Their existing
username/password-only enablement gates are therefore already consistent
with their own search logic. rutor is fully public/unauthenticated
(no gate); jackett gates on an API key, not cookies. **Only rutracker had
the described asymmetry** — confirmed, not merely asserted, via a
dedicated executable test (`test_kinozal_and_iptorrents_have_no_cookies_bypass_to_be_asymmetric_against`)
proving even fabricated cookies env vars leave both trackers disabled
without username+password.

## Independently re-verified this session (coordinator, including a
genuine paired-mutation revert/restore)

```
$ .venv/bin/python -m pytest tests/unit/merge_service/test_bob176_rutracker_cookies_enablement.py -v --import-mode=importlib
... 6 passed in 0.62s

$ grep -n "RUTRACKER_COOKIES.*or" download-proxy/src/merge_service/search.py
1248: if os.getenv("RUTRACKER_COOKIES") or (os.getenv("RUTRACKER_USERNAME") and os.getenv("RUTRACKER_PASSWORD")):

$ git stash push -m "coordinator-verify-bob176" -- download-proxy/src/merge_service/search.py
$ .venv/bin/python -m pytest tests/unit/merge_service/test_bob176_rutracker_cookies_enablement.py -v --import-mode=importlib
FAILED test_cookies_only_config_enables_rutracker
AssertionError: RUTRACKER_COOKIES alone did not enable rutracker -- the
enablement gate is still ignoring cookies even though _search_rutracker
treats them as the preferred auth path and the nnmclub sibling gate
already honours its own cookies variable.
1 failed, 5 passed in 0.61s

$ git stash pop
$ .venv/bin/python -m pytest tests/unit/merge_service/test_bob176_rutracker_cookies_enablement.py -q --import-mode=importlib
6 passed in 0.63s
```
Genuine reproduction confirmed independently — reverting the source alone
reproduces the exact defect signature; restoring returns to green. The
mandatory negative control (§11.4.201(1)) is proven by a passing test:
`test_credential_less_config_disables_rutracker` and two additional
regression guards (lone username, lone password, neither with cookies) —
rutracker stays disabled in every credential-less/partial-credential
shape, the fix is purely additive.

## Honest boundary (not silenced, per the subagent's own report)

`tests/conftest.py` carries an unrelated PROSE comment referencing
"BOB-176 root cause" for a completely different, already-closed defect
(a `sys.modules` pollution issue from 2026-09-01) — a casual-comment
ID coincidence, not a tracker-DB collision (the actual BOB-176 tracked
item is unambiguous); noted for awareness, does not affect this closure.

## git diff --stat

```
download-proxy/src/merge_service/search.py | 10 +++++++++-
1 file changed, 9 insertions(+), 1 deletion(-)
```
Plus new `tests/unit/merge_service/test_bob176_rutracker_cookies_enablement.py`
(199 lines, 6 tests).
