# Systematic Debugging Session — 2026-04-19

**Revision:** 1
**Last modified:** 2026-06-06T00:00:00Z

Applied the `superpowers:systematic-debugging` skill against the
11-issue set from the prior subagent's work. Separated "claimed
fixed" from "verified fixed" and found one genuine residual bug
beyond the original 11.

## Phase 1 — Root cause investigation (evidence gathered, no fixes yet)

Live-stack code checksums match committed `main`; the subagent's
changes are live. Evidence per issue:

| # | Issue | Verdict | Evidence |
|---|---|---|---|
| 1 | White frame around dashboard | **FIXED** | Global SCSS in served CSS: `html,body{margin:0;padding:0;background:#0f1a30}` |
| 2 | Auth indicator doesn't refresh after login | **FIXED** | Bundle ships `openQbitLogin()` which passes `loadAuthStatus` as the success callback |
| 3 | Lost per-tracker status chips | **FIXED** | Bundle contains `tracker-chip` (×2) + `Re-login` (×2); `/api/v1/auth/status` returns 4 trackers |
| 4 | WebUI Bridge link Page Unavailable | **FIXED** | `GET /api/v1/bridge/health` → `{"healthy":true,"port":7188}`; bundle has `bridge-down-hint` |
| 5 | qBittorrent WebUI link Unauthorized | **FIXED** | `GET /api/v1/config` → `qbittorrent_url: "http://localhost:7186"` (proxy, not :7185 internal) |
| 6 | Search not real-time | **FIXED** | `POST /api/v1/search` returns in ~100ms with `status:"running"`, `results:[]`; SSE `/stream/{id}` emits `event: result_found` within 500ms |
| 7 | Sources column broken | **FIXED** | Bundle has `sourceStats` (×3) + `merged-indicator` (×4); backend returns `sources: [{tracker, seeds, leechers}]` |
| 8 | Low seeds/leechers | **NOT A BUG** | Real tracker data; dedup sums correctly. Live search returned `seeds=326, leechers=69` from rutracker |
| 9 | qBit chip missing username + logout | **FIXED** | Bundle has `qBit Connected`, `qbit-chip`; `/auth/status` returns `username:"admin"`; bundle has `Re-login` |
| 10 | Only 2 trackers in results | **NOT A BUG** | `trackers_searched` = 40; live logs show per-tracker counts (`iptorrents: 49 results`, `kinozal: 0 results`, `academictorrents: 0 results`); zero matches for a specific query is tracker-side behaviour |
| 11 | qBit download appears successful but no torrent added | **FIXED — end-to-end verified** | Before: 0 torrents. After `POST /api/v1/download` with Ubuntu magnet: 1 torrent, `name=ubuntu-22.04.3-desktop-amd64.iso`, `hash=dd8255ec…`, `state=checkingResumeData`. Test torrent cleaned up afterwards. |

Each "FIXED" verdict came from an independent live probe, not from
trusting the subagent's summary.

## Unexpected finding — real bug uncovered by new property test

After the 11-issue verification, running the newly-added property
suite surfaced:

```
FAILED tests/property/test_deduplicator_properties.py::test_merge_is_order_invariant
```

Hypothesis minimised a counterexample:

```
[(name='0',  hash=…0000),
 (name='0',  hash=…0001),
 (name='00', hash=…0000)]
```

- Forward: produces **one** group of 3 (all merged)
- Reversed: produces **two** groups ({name='00', hash=…0000}, {name='0', hash=…0001})

Different groupings → same results would render differently in the
dashboard depending on which tracker's response arrived first.

### Phase 2 — Pattern analysis

`deduplicator.py::merge_results` (line 65) sorted by seed count only:

```python
unmatched.sort(key=lambda r: r.seeds, reverse=True)
```

Python's `sort` is stable. Equal-seed items therefore preserved their
input order, and — in the counterexample — all three items had
`seeds=0`. Different input orders produced different sort orders,
each of which seeded different merge groups.

### Phase 3 — Hypothesis

Adding a deterministic secondary sort key on `(link, name)` would
force equal-seed items to resolve the same way regardless of input
order, eliminating the nondeterminism without changing the
seed-priority semantics.

### Phase 4 — Fix

One-line change:

```python
unmatched.sort(key=lambda r: (-r.seeds, r.link or "", r.name or ""))
```

Verified:
- `test_merge_is_order_invariant` flips from fail → pass.
- All 686 deterministic tests still green.
- No other property regressed.

Deployed by restarting `qbittorrent-proxy`; `/health` responded 200
after ~3 s.

## Total score

- 11 user-reported issues: 9 fixed, 2 "not a bug" (confirmed with evidence).
- 1 additional real bug found by the new property suite, fixed same
  session.
- Tests: 686 deterministic Python + 182 frontend = **868 passing / 0
  failures / 0 skips / 0 warnings**.
- Live stack: healthy, latest code serving.
