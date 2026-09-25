# BOB-234 — closure evidence (2026-09-23)

| Field | Value |
|---|---|
| Revision | 1 |
| Last modified | 2026-09-23T00:00:00Z |
| Item | BOB-234 (Bug) |
| Evidence class | runtime (live merge service :7187 + download-proxy :7186, token-armed) |

No token value appears anywhere in this file or in the changed sources (§11.4.10).

## Root cause

`tests/integration/test_merge_api.py` used a bare `requests.Session`. The live merge
service runs with `BOBA_API_TOKEN` armed (BOB-197), and
`download-proxy/src/api/routes.py::require_api_token` answers 401 unless the request
carries `Authorization: Bearer <token>` or `X-Boba-Token: <token>`.

Second defect found while fixing (same root cause, previously masked because the test
never got past the 401): the download test's cleanup `POST :7186/api/v2/torrents/delete`
was also unauthenticated. The :7186 proxy (`plugins/download_proxy.py`) gates deletes
with the same token, so the cleanup got 401. Its response was never checked, and the test
torrent was left in qBittorrent. Observed live: after the first green run, one
`itest-74e5b1dd` torrent (tags `Boba, Боба`) remained. An unauthenticated delete returned
401. The same delete with the token returned 200 and the torrent was removed.

## Fix (test-side only)

- NEW `tests/integration/merge_api_auth.py`:
  - `resolve_api_token()` reads the environment first, then the repo `.env`.
  - `MergeTokenSession` sends `X-Boba-Token` only to the merge-service origin
    (scheme+host+port match).
  - `assert_token_usable()` probes `POST /api/v1/magnet`. It FAILS loudly (never skips)
    when the service is armed and the token is missing, or when the token is rejected.
  - `qbit_delete_confirmed()` sends the token to the :7186 delete, asserts HTTP 200 and
    polls until the hash is gone.
- `tests/integration/test_merge_api.py`: new `api_token` fixture; `session` is now a
  `MergeTokenSession`; the download cleanup uses `qbit_delete_confirmed`.
- NEW `tests/unit/test_bob234_merge_api_sends_token.py`: 14 tests against a real local
  `http.server` (401 without the header, 200 with it).

## RED -> GREEN

- RED (unit): collection failed with `ModuleNotFoundError: tests.integration.merge_api_auth`.
  The cleanup tests then failed (2 failed / 12 passed) before `qbit_delete_confirmed` existed.
- Pre-fix live behaviour: 10 x HTTP 401, recorded in docs/Issues.md BOB-234.
- Paired mutation (session reverted to a bare `requests.Session`, then restored with
  cmp-verified byte identity): 8 failed (hooks x5, magnet x3).
- Wrong-token negative control (`BOBA_API_TOKEN=<wrong>` in env): the fixture fails with
  "rejected the BOBA_API_TOKEN taken from environment (POST /api/v1/magnet -> HTTP 401)".
  It does not skip.
- GREEN: `tests/unit/test_bob234_merge_api_sends_token.py` + `tests/integration/test_merge_api.py`
  gave `34 passed in 73.86s`.

## Debris (CM-NO-TEST-TAG-DEBRIS / §11.4.14)

```
PRE  torrents 0 tags ['1080p', 'Boba', 'Боба'] boba-hyphen-tags [] hooks 0 itest_scripts 0
POST torrents 0 tags ['1080p', 'Boba', 'Боба'] boba-hyphen-tags [] hooks 0 itest_scripts 0
CM-NO-TEST-TAG-DEBRIS: PASS — no 'boba-' test debris among 3 live tag(s)
```

The torrent left by the first (pre-cleanup-fix) run was removed manually with an
authenticated delete. The final run left none.

## Honest gaps

- The production tags `Boba`/`Боба` were already in qBittorrent's tag list before the
  final run. They are production tags, not `boba-` debris. The test does not delete tags
  (deleting shared production tags could affect real torrents).
- Other integration files that call token-gated routes were not audited (out of scope).
  They may have the same 401 latent defect.

## Addendum — diff-scoped cleanup (CM-NO-UNSCOPED-LIVE-DESTRUCTION)

The first commit attempt was refused by invariant `CM-NO-UNSCOPED-LIVE-DESTRUCTION`
because `qbit_delete_confirmed` deleted by hash with no baseline. Reworked to the
gate's pattern: `qbit_snapshot_hashes` is taken BEFORE the add; the delete runs
only when the hash is in `after - before`; an unreadable baseline (`None`)
disarms the delete. Evidence (this session):

- `pytest tests/unit/test_bob234_merge_api_sends_token.py` -> 17 passed.
- Mutation (drop the `before is None` guard and the `h not in added` guard):
  2 failed (`..._disarmed_when_baseline_unreadable`,
  `..._never_deletes_a_preexisting_torrent`), 15 passed; restored -> 17 passed.
- `bash scripts/pre_build/check_cm_no_unscoped_live_destruction.sh` -> PASS, 10 files, all scoped.
- Live `pytest tests/integration/test_merge_api.py` -> 20 passed; `check_cm_no_test_tag_debris.sh` -> PASS.
