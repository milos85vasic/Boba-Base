-- BOB-066 audit-and-close subagent — apply audit note + status bump + history event.
-- Every UPDATE is keyed on atm_id='BOB-066'; NEVER a table-wide write.
BEGIN;

UPDATE items
   SET description = description || char(10) || char(10) ||
       '--- AUDIT NOTE 2026-08-15 (BOB-066 audit-and-close subagent) ---' || char(10) ||
       'Cross-layer audit via challenges/scripts/upstream_proxy_wired_challenge.sh:' || char(10) ||
       '- L1 (Python download-proxy): WIRED — config/proxy.py exports apply_proxy_env + aiohttp_session_kwargs; main.py:97 calls apply_proxy_env at boot; all 9 aiohttp.ClientSession sites in merge_service/search.py carry _tracker_session_kwargs()=trust_env.' || char(10) ||
       '- L2 (qBitTorrent-go): WIRED — internal/httpx/proxy.go exports Configure/NewTransport/Proxy; cmd/qbittorrent-proxy/main.go:29 calls httpx.Configure(cfg.UpstreamProxy); internal/api/download.go:65 installs httpx.NewTransport().' || char(10) ||
       '- L3 (Jackett): NOT WIRED (residual gap) — neither the jackett container env-forward nor a Jackett ServerConfig.ProxyUrl API-based wiring exists. Fix requires either a jackett service env-block addition in docker-compose.yml OR a new qBittorrent-go/internal/jackettconfig module. Recommendation: file a scoped follow-up ticket.' || char(10) ||
       '- L4 (docker-compose env-forward): 3/5 wired — download-proxy, qbittorrent-proxy-go, qbittorrent all env-forward BOBA_UPSTREAM_PROXY + HTTP_PROXY/HTTPS_PROXY/NO_PROXY; jackett + boba-jackett do NOT (boba-jackett is loopback-only so not required).' || char(10) ||
       'Challenge verdict: 9 PASS / 0 FAIL / 3 honest SKIP; self-validate GREEN; RED polarity (11.4.115) proven with 9 negated presence-detectors.' || char(10) ||
       'Evidence: qa-results/bob066/20260815T115831Z/challenge_green.log, challenge_red.log, challenge_selfvalidate.log' || char(10) ||
       'STATUS DECISION: kept In progress — closing as Completed would be a 11.4.6/11.4.108 bluff while L3 remains un-wired.'
 WHERE atm_id = 'BOB-066';

UPDATE items
   SET status = 'In progress'
 WHERE atm_id = 'BOB-066';

INSERT INTO item_history (atm_id, event_type, by, on_date, reason, evidence_path)
VALUES ('BOB-066', 'Updated', 'AI', '2026-08-15',
        'audit-complete-L1-L2-L4-partial-L3-residual-gap',
        'qa-results/bob066/20260815T115831Z/challenge_green.log');

COMMIT;

.print --- BOB-066 after apply ---
SELECT atm_id, status, substr(description, -600) FROM items WHERE atm_id = 'BOB-066';
.print --- item_history for BOB-066 ---
SELECT id, event_type, by, on_date, reason, evidence_path FROM item_history WHERE atm_id = 'BOB-066' ORDER BY id DESC LIMIT 3;
