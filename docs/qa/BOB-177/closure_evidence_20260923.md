# BOB-177 closure evidence — 2026-09-23

## Fix

Collapsed the 5 duplicated 4-line HTTP-refusal guard wirings in
`download-proxy/src/merge_service/search.py` (rutracker-cookie,
rutracker-credential, kinozal, nnmclub, iptorrents) into one shared
`SearchOrchestrator._check_search_response(tracker_name, status, body) -> bool`
helper. Confirmed (by reading each site in full before editing) the
original 4-line blocks were genuinely identical logic — no discrepancy
found, the collapse is behavior-preserving. A future sixth tracker site
now structurally cannot ship unguarded.

## Independently re-verified this session (coordinator, including an
independently-authored wiring-deletion mutation at the reviewer's
original finding site — kinozal — against the FULL 1067-test suite)

```
$ .venv/bin/python -m pytest tests/unit/merge_service/test_bob177_guard_wiring_collapse.py -q --import-mode=importlib
20 passed in 12.64s

$ grep -n "_check_search_response" download-proxy/src/merge_service/search.py
1467: def _check_search_response(self, tracker_name, status, body) -> bool:
1543 / 1621 / 1802 / 1912 / 2081: (all 5 call sites confirmed present)
```

Independent mutation (deleted the kinozal call site's 2-line guard call,
NOT reusing the subagent's own probe — authored fresh):
```
$ (deleted lines 1801-1803 at the kinozal site in a local copy)
$ .venv/bin/python -m pytest tests/unit/merge_service/ -q --import-mode=importlib
FAILED tests/unit/merge_service/test_bob177_guard_wiring_collapse.py::TestKinozalWiring::test_refusal_is_stashed_and_results_empty
1 failed, 1066 passed, 1 warning in 266.99s
```
Genuine reproduction: deleting the wiring at the kinozal site (the
reviewer's original BOB-172 finding) reddens exactly one test — the
kinozal-wiring-proof test — confirming the fix's core mechanism.

```
$ (restored the fixed search.py from a saved backup)
$ git diff --stat download-proxy/src/merge_service/search.py
1 file changed, 45 insertions(+), 25 deletions(-)   (matches the subagent's own reported diff size exactly)
$ .venv/bin/python -m pytest tests/unit/merge_service/test_bob177_guard_wiring_collapse.py -q --import-mode=importlib
20 passed in 2.75s
```

## Subagent's own firsthand reproduction (not independently re-verified
in full by the coordinator, given the ~4.5min-per-run cost of the full
suite, but internally consistent with the coordinator's own spot-check
above and worth recording)

Firsthand-reproduced the reviewer's original finding at ALL 5 sites
pre-fix (each site's wiring deletion left the 1047-test suite fully
green — blind), and confirmed the SAME mutation pattern reddens at all 5
sites post-fix. Ran the full 1067-test suite 3 consecutive times post-fix:
identical `1067 passed, 0 failed` each time (150-290s per run, under real
host contention from a concurrent track sharing this checkout).

## Honest boundary

The item's own text referenced an "883 tests" baseline (from BOB-172's
original review); this session's suite is 1047-1067 tests (grown since,
including this fix's own 20 new tests) — noted, not a discrepancy in the
fix itself.

## git diff --stat

```
download-proxy/src/merge_service/search.py | 70 +++++++++++++++++++-----------
1 file changed, 45 insertions(+), 25 deletions(-)
```
Plus new `tests/unit/merge_service/test_bob177_guard_wiring_collapse.py`
(396 lines, 20 tests).
