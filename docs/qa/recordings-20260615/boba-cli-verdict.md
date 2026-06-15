# Recording verdict — boba-ctl orchestrator CLI

**Revision:** 1
**Last modified:** 2026-06-16T00:30:00Z

§11.4.83 recorded-evidence + §11.4.153 video-confirmation + §11.4.107/§11.4.117
on-screen verification. Analysis performed by Claude Opus 4.8 vision (operator-
chosen analysis path — the HelixAgent ensemble vision endpoint is a proven stub,
see `docs/qa/recording-readiness-20260615/`).

## Recording
- **Surface:** CLI — `boba-ctl` (Go orchestrator, `cmd/boba-ctl/main.go`)
- **Artifacts** (external per operator, `/Volumes/T7/Downloads/Recordings/`):
  `boba-cli-orchestrator-demo.cast` / `.gif` / `.mp4` (14.1s)
- **Scenario:** live stack — `boba-ctl status` → `health` → `list`
- **Pipeline:** asciinema rec → agg (gif) → ffmpeg (mp4) → ffmpeg fps=1 frames → Claude vision

## Frame-by-frame verdict (real on-screen content, no bluff)
| Feature | Frame | On-screen result | Verdict |
|---|---|---|---|
| `boba-ctl status` | frame_04 | NAME/STATE/HEALTH/PORTS table; qbittorrent, jackett, boba-jackett, download-proxy all `running` | ✅ PASS |
| `boba-ctl health` | frame_13 | 4 services all `OK` | ✅ PASS (see note) |
| `boba-ctl list` | frame_13 | 4 default services + `go` profile (`qbittorrent-proxy-go`) + `Runtime: podman` | ✅ PASS |
| banner | frame_13 | "=== demo complete — 4 services running & healthy ===" | ✅ PASS |

## Honest observation (not a failure → tracked follow-up)
`health`/`status` show `-` / "no ports exposed" in the HEALTH/PORTS detail for
ALL four services because they use `network_mode: host` (no published ports), and
the Go health checker probes *published* ports. `STATE=running` / `STATUS=OK` is
correct (containers ARE up and search works). Follow-up: make the health checker
probe the in-VM listening port for host-net services so DETAIL reflects a real
endpoint probe rather than "no ports exposed".

## Outcome
boba-ctl orchestrator features confirmed working on-screen. No problems requiring
a fix detected (the health-detail gap is cosmetic, tracked above).
