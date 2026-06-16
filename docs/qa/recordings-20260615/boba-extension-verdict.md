# Recording verdict — BobaLink browser extension (gap CLOSED)

**Revision:** 1
**Last modified:** 2026-06-16T08:05:00Z

§11.4.143 real-user-journey + §11.4.83 evidence + §11.4.107/§11.4.117 on-screen +
§11.4.123 (built the method — the prior "tooling-limited" was a research trigger,
not acceptance). Analysis by Claude Opus 4.8 vision.

## How the prior blocker was closed
The Playwright MCP can't launch a `--load-extension` browser. So I built a real
harness — `extension/scripts/record-features.mjs` — that loads the BUILT MV3
artifact (`.output/chrome-mv3`) into a Chromium persistent context
(`--headless=new --load-extension=...`) with `recordVideo` on, and drives genuine
user journeys. The existing `tests/e2e/extension-loads.spec.ts` proved MV3 loads
on this host (4/4 pass), so recording is real, not faked.

## Recordings (`/Volumes/T7/Downloads/Recordings/`, `boba-` prefix)
| File | Scenario | On-screen verdict |
|---|---|---|
| `boba-extension-scan-detect.mp4` | content-script scan on a matched tracker host (rutracker fixture, routed — no live network) | ✅ the real content script detects the magnet and appends a **🌐 MAGNET** badge inside the anchor; the non-torrent link is correctly **NOT** badged (discriminating detection) |
| `boba-extension-popup.mp4` | the BobaLink popup the user opens | ✅ header + logo + "No server" status, "No server configured · Open Options", **Refresh** + **Send All** buttons, "DETECTED TORRENTS" section with empty-state ("Browse a torrent site to detect…"), Options link |
| `boba-extension-options.mp4` | the options/settings page | ✅ 7 tabs (Server / Download Prefs / Queue / Notifications / Detection / UI / Security); Server config (name "Boba", URL http://localhost:7187, Auth, Boba API token, Session passphrase, timeout); **Save settings** |
| `boba-extension-tour.mp4` | scan → popup → options concatenated | the three above |

Extension id resolved live: `okacdgimolhjpopdibpmdbmdidpimmbj` (valid MV3).

## Outcome
The BobaLink extension's real-use UI + the genuine content-script detection are
now **video-confirmed** (not just unit-tested). No defect detected — detection
badges the magnet and skips the non-torrent, popup + options render fully. The
harness is reproducible (`node scripts/record-features.mjs <dir>`) for future
re-confirmation.
