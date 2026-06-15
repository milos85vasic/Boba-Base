# Recording verdict — Web dashboard search flow (the #1 fixed feature)

**Revision:** 1
**Last modified:** 2026-06-16T00:40:00Z

§11.4.143 real-user-journey + §11.4.83 recorded evidence + §11.4.107/§11.4.117
on-screen verification. Analysis by Claude Opus 4.8 vision (operator-chosen).

## Recording
- **Surface:** Web — Боба Dashboard (Angular SPA served at :7187), driven through
  its OWN UI in a real browser (playwright), NOT a deep-link/intent shortcut.
- **Artifacts** (`/Volumes/T7/Downloads/Recordings/`): `boba-web-search-flow.mp4`
  + frames `boba-web-01-dashboard.png` / `-02-search-results.png` /
  `-03-results-grid.png` (full grid) / `-04-rows-closeup.png`.
- **Journey:** launch dashboard → type `debian` in the search box → submit →
  live results → completed.
- **Tunnel:** macOS↔podman-VM SSH forward (`scripts/ensure-macos-tunnel.sh`) so
  the host-net :7187 is reachable for the browser.

## Frame verdict (real on-screen content, no bluff)
| Step | Frame | On-screen result | Verdict |
|---|---|---|---|
| Dashboard loaded | 01 | "Боба Dashboard", qBit Connected — admin, 4 auth chips (rutracker/kinozal/nnmclub/iptorrents), **29 Trackers**, search box + Results/Downloads/Trackers/Schedules/Hooks tabs | ✅ PASS |
| Search in progress | 02 | `debian` typed; **"Found 829 results..."** with live spinner + Abort; **1 Active Search** | ✅ PASS — live grid updates (confirms BUG-2 fix on real UI) |
| Results grid | 03 | full-page: hundreds of debian result rows densely populated | ✅ PASS |
| Search complete | 04 | **"Found 829 results (288 merged)"**, **1 Completed**, Search button restored, result rows with action buttons | ✅ PASS — full pipeline: 29-tracker fan-out → 829 raw → 288 deduped → completed |

## Additional confirmed pages (dashboard tour — `boba-web-dashboard-tour.mp4`)
| Page/feature | Frame | On-screen result | Verdict |
|---|---|---|---|
| Trackers tab navigation | boba-web-05-trackers-tab.png | tab switches to Trackers (active/underlined); per-tracker stats header renders below the completed 829/288 search | ✅ PASS |
| Jackett credentials page (`/jackett`) | boba-web-06-jackett-page.png | boba-jackett UI: "Credentials — encrypted at rest and mirrored to .env", "+ Add credential", empty-state "No credentials yet" | ✅ PASS (renders + routes) |

## Outcome
The operator's #1 complaint ("search flows do not work at all") is verifiably
RESOLVED on the actual user-facing web dashboard: a real typed query returns 829
results merged to 288, live-updating, through the real browse-search UI. No
problems detected requiring a fix. (Single/selected-provider modes were
separately live-proven via the API in c68bb3f; a UI per-provider-filter
recording is a follow-up if the dashboard exposes that control.)
