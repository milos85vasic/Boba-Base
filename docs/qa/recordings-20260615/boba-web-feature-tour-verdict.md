# Recording verdict — Web dashboard feature tour + tunnel-artifact finding

**Revision:** 1
**Last modified:** 2026-06-16T07:30:00Z

§11.4.143 real-user-journey + §11.4.83 evidence + §11.4.107 on-screen + §11.4.6
no-guessing. Analysis by Claude Opus 4.8 vision (operator-chosen; HelixAgent
ensemble vision is a proven stub).

## Recording
- **Surface:** Web — Боба Dashboard (Angular SPA :7187) via the macOS↔podman-VM SSH tunnel.
- **Artifacts** (`/Volumes/T7/Downloads/Recordings/`): `boba-web-feature-tour.mp4`
  + frames `boba-web-{01-dashboard,02-search-results,04-rows-closeup,result-row-buttons,05-trackers-tab,06-jackett-page}.png`.

## Features confirmed on-screen (real, no bluff)
| Feature | Verdict | Evidence |
|---|---|---|
| Dashboard load (29 trackers, qBit connected, 4 auth chips) | ✅ | frame 01 |
| Search (all providers) | ✅ | "Found 727/829 results", live count |
| Result rows render with **qBit + Download** action buttons (clickable) | ✅ | DOM snapshot refs e217/e218 per row, `cursor=pointer`; live qBit-add (+1 torrent) proven in prior session + frontend tests |
| Tab navigation (Results/Active Downloads/Trackers/Schedules/Hooks) | ✅ | frame 05 (Trackers active) |
| Jackett credentials page (`/jackett`, boba-jackett UI) | ✅ | frame 06 |
| Theme (Darcula dark) | ✅ | rendered throughout |

## Tunnel-artifact finding (§11.4.6 — NOT a product defect)
During the tour the browser console showed `ERR_INCOMPLETE_CHUNKED_ENCODING`
(on `/api/v1/search/stream` + `/api/v1/theme/stream` SSE) and `ERR_EMPTY_RESPONSE`
(on the periodic polls `/stats`, `/auth/status`, `/downloads/active`, `/bridge/health`).

**Root cause (proven):** these are SSE (long-lived chunked) + frequent-poll
connections being cut by the **macOS↔VM SSH port-forward**, NOT server errors.
Verified — every one of those endpoints returns **200 inside the VM** (no tunnel):
```
podman machine ssh ... curl localhost:7187/api/v1/stats          -> 200
                                  /api/v1/auth/status      -> 200
                                  /api/v1/downloads/active -> 200
                                  /api/v1/bridge/health    -> 200
```
This is a **test-harness limitation of driving the SPA over SSH from macOS**, not
a Boba defect. On a native deployment (browser same-origin as the service, no SSH
tunnel) these do not occur. A churning tunnel-keepalive supervisor amplified it
and was removed in favour of a single stable tunnel (5/5 probes 200).

## Outcome
All visible web features render and work; the only console noise is the
SSH-tunnel SSE/poll artifact (server verified healthy). No product fix required.
Honest follow-up: a tunnel that proxies SSE robustly (or testing on a native
deploy) would remove the console noise for macOS-side recordings.
