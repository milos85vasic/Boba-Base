# BOB-179 — closure evidence

captured: 2026-09-25   branch: main

NOTE: no credential VALUE appears in this artifact or in any test fixture
committed with it — variable NAMES only (§11.4.10). All test fixture values
are synthetic placeholders (`test-user-not-a-real-account`,
`test-value-not-a-real-secret`, `SYNTHETIC-TEST-FIXTURE-VALUE`), never real
session material.

## Scope

The BOB-172 independent review (2026-08-22/23) stated two gaps in the
five-site refusal-not-reported-as-empty fix, both explicitly PRE-EXISTING
and neither a regression from BOB-172:

- **Gap A** — an exception raised BEFORE `resp.status` is read is swallowed
  by each `_search_*` method's `except Exception:` clause (`logger.error`;
  `return results`) before `_search_one`'s own error handling can observe
  it. A connection-refused / DOWN tracker was reported identically to a
  genuinely empty one: `status="empty"`, `error=None`, `http_status=None`.
- **Gap B** — a session-expiry redirect (`302 -> login page -> 200`) parses
  to zero rows and reports empty, because `_classify_upstream_http_status`
  correctly treats any 2xx as usable and all five private-tracker search
  GETs use aiohttp's default `allow_redirects=True`.

Both are now CLOSED as FIXES (not §11.4.112 structurally-impossible
classifications — the item's own FIX DIRECTION text was correct that both
were fixable, and no evidence emerged during investigation to the
contrary).

## Root cause / systematic-debugging (§11.4.102)

Investigation confirmed both gaps genuinely present in
`download-proxy/src/merge_service/search.py` as described, via direct
source reading (not assumed from the prior review's own words):

- Gap A: `_search_rutracker` (both the `RUTRACKER_COOKIES` branch and the
  `RUTRACKER_USERNAME`/`RUTRACKER_PASSWORD` branch), `_search_nnmclub`, and
  `_search_iptorrents` each had a bare `except Exception as e:
  logger.error(...)` with **no** diagnostic stash — confirmed by reading
  every one of the four methods' exception handlers before touching any of
  them. `_search_kinozal` was the ONE exception: its except clause already
  stashed a diagnostic, added earlier this same session as the BOB-235 fix
  for the identical defect class on kinozal specifically (confirmed by
  reading the file fresh per this item's own instruction not to assume
  prior state, since kinozal/search.py had been touched this session for
  BOB-137/BOB-235 before this item started).
- A SECOND call frame for the SAME defect class, not separately named by
  the review's Gap A text, was found during investigation:
  `_nnmclub_login`'s own `except Exception as e:` (the login-leg helper
  `_search_nnmclub` delegates to when `NNMCLUB_COOKIES` is unset and
  username/password auth is used) also swallowed the exception with no
  diagnostic — and a failure there never reaches `_search_nnmclub`'s own
  except at all, since `_nnmclub_login` never re-raises. Closed as part of
  this item's Gap A fix (see FIX below).
- Gap B: confirmed all five private-tracker search GETs
  (`_search_rutracker` cookie path, `_search_rutracker` credential path,
  `_search_kinozal`'s `browse.php` GET, `_search_nnmclub`'s
  `tracker.php` GET, `_search_iptorrents`'s `/t` GET) call
  `session.get(...)` with no `allow_redirects` keyword — aiohttp's default
  is `True`. Confirmed `_classify_upstream_http_status`'s own docstring and
  behaviour (`if 200 <= status < 300: return None`) is correct by design
  and was left untouched.

## FIX

### Gap A

Each of the four affected `except Exception:` clauses now stashes:

```python
self._last_public_tracker_diag[<tracker>] = {
    "error_type": e.__class__.__name__,
    "error": f"<Tracker> request failed[: <leg>]: {e}",
    "stderr_tail": "",
    "deadline_hit": False,
    "deadline_seconds": 0.0,
}
```

— the EXACT dialect the BOB-235 kinozal fix (this session, prior to
BOB-179) established for this defect class, reused verbatim rather than
inventing a second one (§11.4.28). Applied at:

1. `_search_rutracker` — cookie-path except (`RuTracker request failed
   (cookie path): ...`)
2. `_search_rutracker` — credential-path except (`RuTracker request
   failed: ...`)
3. `_search_nnmclub` — search-leg except (`NNMClub request failed: ...`)
4. `_nnmclub_login` — login-leg except (`NNMClub login request failed:
   ...`) — the additional call frame found during investigation
5. `_search_iptorrents` — except (`IPTorrents request failed: ...`)

`_search_kinozal` was already fixed (BOB-235) and is unchanged by this
item.

### Gap B

A new function, `_detect_session_expired_redirect(tracker_name,
requested_url, history, final_url, final_status=None)`, added immediately
after `_classify_upstream_http_status` in `search.py`:

- Returns `None` (no session-expiry signature) when `history` is
  empty/falsy — the overwhelming common case, and the one that matters
  most: it means NO redirect occurred, so a legitimate 200 search-results
  page that happens to mention the word "login" somewhere in its body
  never reaches any further check in this function at all.
- Returns `None` when a redirect DID occur but the final resolved path
  equals the requested path (e.g. an http→https upgrade landing back on
  the same search endpoint).
- Returns `None` when the final resolved path does not contain the
  substring `"login"` (the marker shared by every one of this module's own
  login endpoints).
- Otherwise returns a diagnostic dict in the SAME shape
  `_classify_upstream_http_status` already returns (§11.4.28), with
  `error_type: "upstream_session_expired"`.

It is a **DISTINCT** detector — it inspects only `resp.history`/`resp.url`
(authoritative aiohttp-level facts about what happened on the wire), never
a body-text proxy, and it is **NOT** a widening of
`_classify_upstream_http_status`'s status-code trigger: that function's own
code, docstring, and test coverage are byte-for-byte unchanged by this
item (`diff`-verified — see the RED/GREEN section below, where the
negative-control tests pinning `_classify_upstream_http_status`'s existing
behaviour stay green throughout).

Wired in at all five search-GET call sites, immediately AFTER
`_check_search_response` (which correctly passes the response through —
it's a 2xx) and BEFORE the row parser runs, capturing `resp.history` and
`resp.url` while still inside the `async with` block (matching this file's
own existing convention for capturing `resp.status`).

### Stub reconciliation (§11.4.120)

Five sibling unit-test files' fake aiohttp-response stubs modelled an
INCOMPLETE aiohttp contract — no `.history`/`.url` attributes — and started
raising `AttributeError` once the Gap B wiring read them (an
`AttributeError` inside the `try` block, itself then caught and diagnosed
by the Gap A fix — which is how the incompleteness surfaced, rather than a
silent skip). Per the SAME reconciliation discipline this log's earlier
BOB-172 section already establishes ("the stub was wrong; the guard is
right" — completing an aiohttp-contract field on a stub is not weakening a
test, and making the PRODUCT code tolerate a missing attribute via
`getattr(..., default)` was rejected there for a §11.4.252 fail-open
reason that applies identically here):

- `tests/unit/merge_service/test_bob172_tracker_http_error_not_empty.py`
  — `_FakeResponse.__init__` gained `self.history = ()` / `self.url = ""`.
- `tests/unit/merge_service/test_bob177_guard_wiring_collapse.py` —
  `_FakeResp.__init__`, same two lines.
- `tests/unit/merge_service/test_bob178_kinozal_login_status_diagnostic.py`
  — `_FakeResp.__init__`, same two lines.
- `tests/unit/merge_service/test_bob235_kinozal_connect_failure_diagnostic.py`
  — `_FakeResp.__init__`, same two lines.
- `tests/unit/merge_service/test_nnmclub_session_login.py` — `_FakeResp`
  already carried the BOB-172-era `status`-completion comment; extended
  with the identical `.history`/`.url` completion.

ZERO assertions were touched in any of the five files.

## RED — observed BEFORE the fix (5 wiring call-sites + except-clause
diagnostics temporarily reverted; `_detect_session_expired_redirect`
left defined but unwired, so it could not fire)

```
$ .venv/bin/python -m pytest tests/unit/merge_service/test_bob179_stated_gaps_closure.py \
    -q --import-mode=importlib -p no:randomly

FAILED ...TestGapAConnectionRefusedSetsDiagnostic::test_rutracker_cookie_path
FAILED ...TestGapAConnectionRefusedSetsDiagnostic::test_rutracker_credential_path
FAILED ...TestGapAConnectionRefusedSetsDiagnostic::test_nnmclub_search_leg_with_explicit_cookies
FAILED ...TestGapAConnectionRefusedSetsDiagnostic::test_nnmclub_login_leg_with_username_password
FAILED ...TestGapAConnectionRefusedSetsDiagnostic::test_iptorrents
FAILED ...TestGapBRedirectToLoginSetsDiagnostic::test_rutracker_cookie_path
FAILED ...TestGapBRedirectToLoginSetsDiagnostic::test_rutracker_credential_path
FAILED ...TestGapBRedirectToLoginSetsDiagnostic::test_kinozal
FAILED ...TestGapBRedirectToLoginSetsDiagnostic::test_nnmclub
FAILED ...TestGapBRedirectToLoginSetsDiagnostic::test_iptorrents
10 failed, 8 passed in 1.39s
```

Every failure is `AssertionError: ... diag is None` — exactly the
BOB-172/BOB-172-review false-null signature the item names. The 8 that
passed pre-fix are, by construction, the two negative-control classes
(§11.4.201(1) — must be green both before AND after) plus the 4 isolated
`_detect_session_expired_redirect` unit tests, which exercise the function
directly and do not depend on any call-site wiring.

Method: the fix's 5 wiring call-sites and the 5 except-clause diagnostic
stashes were reverted to their pre-BOB-179 text via the exact inverse of
each edit applied (verified byte-identical to the intended pre-fix state
by inspection of each reverted block); the file still compiled
(`py_compile`) throughout. After capturing the RED run above, the fix was
restored and a `diff` against a pre-revert backup copy of the file
confirmed byte-identical restoration — no drift between the RED experiment
and the shipped fix.

## GREEN — after the fix (restored, diff-confirmed identical to the
intended shipped state)

```
$ .venv/bin/python -m pytest tests/unit/merge_service/test_bob179_stated_gaps_closure.py \
    -q --import-mode=importlib -p no:randomly

18 passed in 1.28s
```

## Negative controls (§11.4.201(1), mandatory — the over-fire direction)

Both gap classes carry their own, both green before AND after the fix:

- **Gap A**: `TestGapANegativeControlHealthyRoundTripStashesNothing` — a
  healthy round-trip through the rutracker credential path and through
  `_nnmclub_login`'s own username/password login leg (the two NEW call
  frames this item's fix touches) stashes NO diagnostic. The three other
  call frames (rutracker cookie path, kinozal, iptorrents) are already
  covered by the pre-existing sibling negative controls in
  `test_bob177_guard_wiring_collapse.py` / `test_bob235_kinozal_connect_failure_diagnostic.py`,
  whose healthy-path behaviour this item does not change.
- **Gap B**: `TestGapBNegativeControls` —
  (a) `test_legitimate_200_mentioning_login_in_body_is_not_flagged`: a
  real 200 response with NO redirect (`resp.history` empty) whose body
  text merely mentions the word "login" must NOT be flagged — proves the
  detector keys on aiohttp's redirect bookkeeping, never a body scan;
  (b) `test_redirect_that_lands_back_on_the_search_endpoint_is_not_flagged`:
  a redirect DID occur but the final path equals the requested search
  path — not a session-expiry signature, must NOT be flagged.

A guard that over-fired on either negative control would be a WORSE defect
than the false-null being fixed (§11.4.201(1)) — it would report a healthy,
working search as an error.

## Full relevant suite (post-fix)

```
$ .venv/bin/python -m pytest tests/unit/merge_service/ \
    tests/unit/test_merge_trackers.py tests/unit/test_private_tracker_search.py \
    -q --import-mode=importlib -p no:randomly

1159 passed in 160.66s (0:02:40)
```

`ruff check` on every file this item touched (`search.py` + the 6 test
files): all checks passed.

## Files changed

- `download-proxy/src/merge_service/search.py` — `_detect_session_expired_redirect`
  added; Gap A diagnostic-stashing added to `_search_rutracker` (both
  branches), `_search_nnmclub`, `_nnmclub_login`, `_search_iptorrents`; Gap
  B detector wired into all five private-tracker search-GET sites.
- `tests/unit/merge_service/test_bob179_stated_gaps_closure.py` — new,
  18 tests (this item's own RED/GREEN + negative controls + detector-unit
  coverage).
- `tests/unit/merge_service/test_bob172_tracker_http_error_not_empty.py`,
  `test_bob177_guard_wiring_collapse.py`,
  `test_bob178_kinozal_login_status_diagnostic.py`,
  `test_bob235_kinozal_connect_failure_diagnostic.py`,
  `test_nnmclub_session_login.py` — stub reconciliation only
  (`.history = ()` / `.url = ""` added to each file's fake-response stub);
  zero assertions touched.
- `docs/qa/BOB-172/fix_evidence_20260822.log` — stated-gaps closure
  paragraph appended (both gaps marked CLOSED, summary of the fix and
  proof, pointer to this file for full detail).
- `docs/qa/BOB-179/closure_evidence_20260925.md` — this file.

## Not closed by this item (out of scope, unchanged)

- BOB-177, BOB-178, BOB-180 — cited in the 2026-08-23 stated-gaps note as
  "also tracked from the same review, and likewise not closed by this
  change" at the time; BOB-177 and BOB-178 have since been closed
  separately (visible in `docs/Fixed.md`) — BOB-179 did not touch or
  re-verify either. BOB-180 status was not investigated by this item.
