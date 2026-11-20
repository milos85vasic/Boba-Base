=== BOB-066 four-layer cross-layer verifier ===
RED_MODE=0  (0=GREEN guard, 1=reproduce pre-fix defect state)

--- L1: download-proxy (Python) ---
  [PASS] L1 config/proxy.py exports apply_proxy_env + aiohttp_session_kwargs
  [PASS] L1 apply_proxy_env() invoked at boot in download-proxy/src/main.py
  [PASS] L1 aiohttp ClientSession sites carry trust_env (9 uses of _tracker_session_kwargs)

--- L2: qBitTorrent-go ---
  [PASS] L2 internal/httpx/proxy.go exports Configure + NewTransport + Proxy honoring BOBA_UPSTREAM_PROXY
  [PASS] L2 httpx.Configure(cfg.UpstreamProxy) called in cmd/qbittorrent-proxy/main.go
  [PASS] L2 httpx.NewTransport() used in internal/api (torrent-download client)

--- L3: Jackett ---
  [PASS] L3 Jackett proxy wired via env-forward OR ServerConfig.ProxyUrl

--- L4: docker-compose.yml env-forward ---
  [PASS] L4 docker-compose.yml service 'download-proxy' env-forwards proxy vars
  [PASS] L4 docker-compose.yml service 'qbittorrent-proxy-go' env-forwards proxy vars
  [PASS] L4 docker-compose.yml service 'qbittorrent' env-forwards proxy vars
  [PASS] L4 docker-compose.yml service 'jackett' env-forwards proxy vars
  [SKIP] L4 'boba-jackett' env-forward absent (not tracker-bound: talks to Jackett loopback + local DB only)

==========================================
Summary: PASS=11  FAIL=0  SKIP=1
==========================================
PASS: upstream_proxy_wired_challenge — every wired layer verified; residual gaps honestly SKIP'd
