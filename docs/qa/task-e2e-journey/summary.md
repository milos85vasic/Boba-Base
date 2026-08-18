# §11.4.143 Real End-User Journey Validation — boba merge-search + qBittorrent

**Revision:** 1
**Last modified:** 2026-08-18T23:35:00Z
**Run date:** 2026-08-18
**Scope:** Real HTTP calls against the live, currently-deployed boba stack (no mocks, no synthetic data, no deep-link shortcuts). Freeleech-only per CLAUDE.md.

## Journey narrative

1. **Dashboard** — `GET http://localhost:7187/` -> 200, Angular app shell served ("Боба Dashboard"). Evidence: `dashboard_response.html`, `dashboard_curl_meta.log`.

2. **Health check** — `GET http://localhost:7187/api/v1/healthz` -> 200, `{"status":"ok","service":"merge-search","version":"1.0.0"}`. Evidence: `healthz_response.json`.

3. **Real multi-tracker search** — `POST http://localhost:7187/api/v1/search/sync` with `{"query":"Ubuntu","category":"all","limit":50,"validate_trackers":false}` -> 200 in 77.1s (real network fan-out, not synthetic).
   - 42 trackers searched, 19 success, 14 error (real upstream failures: DNS failures, HTTP 403s, per-tracker deadline timeouts), 10 empty.
   - 1640 raw results, 468 deduplicated/merged results returned.
   - Top contributors: torlock (400), rutor (260), torrentdownload (243), linuxtracker (132), snowfl (124), piratebay (100), jackett (58), nnmclub (50), iptorrents (49, authenticated: true).
   - Evidence: `search_response.json`, `search_response_raw.log`, `tracker_stats.json`.

4. **Freeleech discovery** — the "Ubuntu" query's top-50 merged results were dominated by high-seed public trackers, crowding IPTorrents' results out of the seed-sorted top 50. Follow-up searches scoped to `"trackers":["iptorrents"]`:
   - "Ubuntu" (iptorrents-only) -> 49 raw / 22 merged, 0 freeleech.
   - "2024" (iptorrents-only) -> 49 raw / 23 merged, 3 freeleech.
   - "1080p" (iptorrents-only) -> 49 raw / 42 merged, 8 freeleech (e.g. "The Bourne Legacy 2012 1080p BluRay HDR10 DTS-HD MA 5 1 x265-GeneMige [free]").
   - "S01E01" (iptorrents-only) -> empty response body (likely MAX_CONCURRENT_SEARCHES throttle after two back-to-back live searches; not chased further).
   - Evidence: `search_ipt_2024.json`, `search_ipt_1080p.json` (= `search_response_freeleech_candidates.json`), `search_ipt_S01E01.json` (empty), `search_iptorrents_only.json` / `search_iptorrents_only_raw.log`.
   - The `[free]` tag is produced server-side by `plugins/iptorrents.py` regex-detecting `<span class="free">` on the tracker's own results page, confirming this is real tracker-page freeleech state.

5. **Download proxy real fetch + qBittorrent add** — selected the freeleech candidate "The Bourne Legacy 2012 1080p BluRay HDR10 DTS-HD MA 5 1 x265-GeneMige [free]" (`desc_link: https://iptorrents.com/t/7646525`).
   - `POST http://localhost:7187/api/v1/download` (this route lives on the merge-search service, port 7187, not the raw proxy on 7186 — an initial attempt against `:7186` correctly failed with a raw-socket 400, confirming the real port map; corrected and re-run against `:7187`).
   - -> 200, `{"download_id":"ccaf4eb1-...","status":"initiated","urls_count":1,"added_count":1,"results":[{"status":"added","method":"proxy"}]}`.
   - Proves the real chain: merge service recognized `iptorrents.com` as a tracker domain -> fetched the `.torrent` through the download-proxy's authenticated tracker-cookie path -> POSTed the fetched bytes into qBittorrent's own `/api/v2/torrents/add`.
   - Evidence: `download_response.log`, `qbit_add_response.log`.

6. **Registration verification** — logged into qBittorrent's WebUI (admin/admin per CLAUDE.md) via the download-proxy passthrough on `:7186`, queried `/api/v2/torrents/info`.
   - Torrent was genuinely registered: hash `62931a1fe5eef06c875553ec7290f261b2d8e81a`, name "The Bourne Legacy 2012 1080p BluRay HDR10 DTS-HD MA 5 1 x265-GeneMige", private: true, state: downloading, num_seeds: 39, num_leechs: 5.
   - Evidence: `qbit_torrent_info_pretty.json`, `qbit_torrent_info.json`, `qbit_torrent_info.log`.

7. **Immediate cleanup (bandwidth discipline)** — the torrent had already begun downloading real bytes by the time registration was confirmed (downloaded: 33,118,337 bytes / progress 0.47%; qBittorrent starts fetching pieces the instant it has peers). Per task constraint, it was immediately:
   - `POST /api/v2/torrents/stop` (hash) -> 200
   - `POST /api/v2/torrents/delete` (hash, deleteFiles=true) -> 200
   - Re-queried `/api/v2/torrents/info?hashes=<hash>` -> `[]` (confirmed removed, including partial data).
   - Evidence: `qbit_cleanup.log`.
   - Honest disclosure: approximately 33-43MB of real content bytes were downloaded before the stop command completed (network I/O latency between add and stop is not instantaneous against a live swarm with active seeders). This was minimized and fully cleaned up — no files remain on disk (deleteFiles=true).

## Anti-bluff checklist (section 11.4.6 / 11.4.143 / CLAUDE.md)

- [x] Real curl invocations against live localhost endpoints (no mocks)
- [x] Real JSON captured from :7187/api/v1/search/sync (1640 raw / 468 merged results, real tracker errors included verbatim)
- [x] Real per-tracker diagnostics captured (tracker_stats.json) including genuine failures, reported honestly
- [x] Freeleech-ONLY: the one torrent added to qBittorrent was confirmed freeleech:true / tagged [free] before selection
- [x] No non-freeleech download was ever added to qBittorrent
- [x] Torrent was NOT deliberately downloaded to completion — bandwidth minimized, cleaned up immediately
- [x] Port-mapping error (initial 7186 attempt) reported honestly rather than silently corrected and hidden
- [x] Empty S01E01 response reported honestly rather than omitted

## Per-endpoint result summary

| # | Endpoint | Method | Result | Evidence |
|---|---|---|---|---|
| 1 | :7187/ | GET | 200, dashboard HTML | dashboard_response.html |
| 2 | :7187/api/v1/healthz | GET | 200, status ok | healthz_response.json |
| 3 | :7187/api/v1/search/sync (all trackers, "Ubuntu") | POST | 200, 42 trackers / 1640 raw / 468 merged | search_response.json |
| 4 | :7187/api/v1/search/sync (iptorrents only, "1080p") | POST | 200, 8 freeleech results found | search_ipt_1080p.json |
| 5 | :7186/api/v1/download (wrong port) | POST | 400 (raw-proxy error page) — corrected | download_response.log |
| 6 | :7187/api/v1/download (correct port) | POST | 200, added_count: 1, status: added | download_response.log |
| 7 | :7186/api/v2/torrents/info (via qbit passthrough) | GET | 200, torrent registered + downloading | qbit_torrent_info_pretty.json |
| 8 | :7186/api/v2/torrents/stop + /delete | POST | 200 + 200, confirmed removed | qbit_cleanup.log |

## Concerns / honest gaps for follow-up (not fixed in this QA pass)

1. IPTorrents seed/leech counts read 0/0 in the merge-service's own parsed result rows, while qBittorrent's live swarm data for the same torrent showed num_seeds: 39, num_leechs: 5. This suggests the IPTorrents plugin's seed/leech column parsing may not be capturing real values from the tracker's results page — worth a dedicated investigation.
2. "S01E01" iptorrents-only query returned an empty HTTP body with no error surfaced to curl — worth checking whether this was a 429 (MAX_CONCURRENT_SEARCHES) silently swallowed, or a different failure mode; not chased further since evidence goals were already met.
3. IPTORRENTS_USERNAME/PASSWORD credentials are live and working (authenticated: true on every iptorrents tracker_stats entry) — this run consumed real, authenticated private-tracker capacity; no cookie/session errors observed.

## Bottom line

The full real user journey — dashboard -> search (real multi-tracker fan-out) -> freeleech discovery -> proxy-authenticated download -> qBittorrent registration -> verified cleanup — was driven end-to-end through boba's actual deployed HTTP surface with zero mocks and zero deep-link shortcuts, satisfying section 11.4.143's real-user-journey mandate and CLAUDE.md's freeleech-only constraint.
